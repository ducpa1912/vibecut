"""Append a second video to the one open project.

DuckSuite keeps one source master per project. Importing into a project joins
the new file to that master, then appends scenes and clips at the end. Existing
scene times stay valid because the old master keeps its place at the start.

The append path normalizes only the new video, then joins with stream copy when
the streams match. The old master is not re-encoded, so repeated imports do not
degrade it. A full re-encode is kept as a fallback for mismatched streams.
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from duckcore import edits, media
from duckcore.store import ProjectStore


class AppendError(ValueError):
    pass


PENDING_TIMEOUT = 900.0
_PROJECT_LOCKS_GUARD = threading.Lock()
_PROJECT_LOCKS: dict[str, threading.Lock] = {}
_CHECK_WRITE_LOCK = threading.Lock()
_ACTIVE_LOCK = threading.Lock()
_ACTIVE_READS: dict[str, float] = {}
_IN_FLIGHT: dict[str, int] = {}
_IN_FLIGHT_LOCK = threading.Lock()
JOB_STALE = 6 * 3600


def is_appending(project_id: str) -> bool:
    with _IN_FLIGHT_LOCK:
        return _IN_FLIGHT.get(project_id, 0) > 0


def _project_lock(project_id: str) -> threading.Lock:
    with _PROJECT_LOCKS_GUARD:
        return _PROJECT_LOCKS.setdefault(project_id, threading.Lock())


def append_locked(
    project_id: str,
    new_source: str | Path,
    mode: str,
    *,
    store: ProjectStore,
    data_root: Path,
    checks: Any = None,
    renders: Any = None,
    cleanup: bool = False,
) -> dict:
    with _IN_FLIGHT_LOCK:
        _IN_FLIGHT[project_id] = _IN_FLIGHT.get(project_id, 0) + 1
    try:
        with _project_lock(project_id):
            return append_video(
                project_id, new_source, mode,
                store=store, data_root=data_root, checks=checks,
                renders=renders, cleanup=cleanup,
            )
    finally:
        with _IN_FLIGHT_LOCK:
            count = _IN_FLIGHT.get(project_id, 0) - 1
            if count > 0:
                _IN_FLIGHT[project_id] = count
            else:
                _IN_FLIGHT.pop(project_id, None)


_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()


def _job_update(job_id: str, **values: Any) -> None:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return
        job.update(values)
        job["updated"] = time.time()


def job_status(job_id: str) -> dict:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return dict(job)


def busy(project_id: str) -> bool:
    if is_appending(project_id) or active_job(project_id) is not None:
        return True
    with _ACTIVE_LOCK:
        return project_id in _ACTIVE_READS


def active_job(project_id: str) -> dict | None:
    now = time.time()
    with _JOBS_LOCK:
        for job in _JOBS.values():
            if job.get("project_id") != project_id or job.get("state") not in {"queued", "running"}:
                continue
            if now - float(job.get("updated") or 0.0) > JOB_STALE:
                job.update({
                    "state": "failed", "stage": "Failed",
                    "error": "The import worker stopped responding.",
                    "updated": now,
                })
                continue
            return dict(job)
    return None


def start_job(
    project_id: str,
    new_source: str | Path,
    mode: str,
    *,
    store: ProjectStore,
    data_root: Path,
    checks: Any = None,
    renders: Any = None,
    cleanup: bool = False,
) -> dict:
    if active_job(project_id) is not None or is_appending(project_id):
        raise AppendError("An import is already running for this project.")
    job_id = f"aj_{uuid.uuid4().hex[:12]}"
    now = time.time()
    with _JOBS_LOCK:
        for key, row in list(_JOBS.items()):
            if row.get("state") not in {"queued", "running"} and now - float(row.get("updated") or 0.0) > 3600:
                _JOBS.pop(key, None)
        for row in _JOBS.values():
            if row.get("project_id") == project_id and row.get("state") in {"queued", "running"}:
                raise AppendError("An import is already running for this project.")
        _JOBS[job_id] = {
            "id": job_id,
            "project_id": project_id,
            "state": "queued",
            "stage": "Queued",
            "progress": 0.0,
            "error": "",
            "warning": "",
            "started": now,
            "updated": now,
        }
    try:
        threading.Thread(
            target=_run_job,
            args=(job_id, project_id, str(new_source), mode, store, data_root, checks, renders, cleanup),
            daemon=True,
            name=f"duck-append-job-{project_id}",
        ).start()
    except Exception as exc:  # noqa: BLE001
        _job_update(job_id, state="failed", stage="Failed", error=str(exc)[:300])
    return job_status(job_id)


def _run_job(
    job_id: str,
    project_id: str,
    new_source: str,
    mode: str,
    store: ProjectStore,
    data_root: Path,
    checks: Any,
    renders: Any,
    cleanup: bool,
) -> None:
    _job_update(job_id, state="running", stage="Joining video", progress=0.05)
    try:
        result = append_locked(
            project_id, new_source, mode,
            store=store, data_root=data_root, checks=checks,
            renders=renders, cleanup=cleanup,
        )
    except Exception as exc:  # noqa: BLE001
        _job_update(
            job_id, state="failed", stage="Failed",
            error=str(exc)[:500], progress=1.0,
        )
        if cleanup:
            _remove_source(Path(new_source), Path(data_root))
        return

    _job_update(
        job_id,
        stage="Reading new scenes",
        progress=0.72 if mode == "scenes" else 0.82,
        scenes=result.get("scenes"),
        offset=result.get("offset"),
        duration=result.get("duration"),
    )
    warning = ""
    try:
        deadline = time.time() + PENDING_TIMEOUT * 2
        while checks is not None and time.time() < deadline:
            status = checks.status(project_id)
            current = status.get("result") if isinstance(status.get("result"), dict) else {}
            meta = current.get("append") or {}
            analysis = meta.get("analysis")
            if analysis != "pending":
                if analysis == "failed":
                    warning = meta.get("error") or "The new video was added, but its speech read failed."
                break
            time.sleep(1.0)
        else:
            if checks is not None:
                warning = "The new video was added, but its speech read did not finish."
    except Exception as exc:  # noqa: BLE001
        warning = f"The new video was added, but its read did not finish: {str(exc)[:200]}"
    _job_update(
        job_id, state="done", stage="Done", progress=1.0,
        warning=warning,
    )


def _project_dir(data_root: Path, project_id: str) -> Path:
    return Path(data_root) / "projects" / project_id


def _check_path(data_root: Path, project_id: str) -> Path:
    return _project_dir(data_root, project_id) / "check.json"


def _load_check(data_root: Path, project_id: str) -> dict:
    path = _check_path(data_root, project_id)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AppendError("Run Check once before importing more video.") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise AppendError("The Check result is unreadable.") from exc
    if not isinstance(value, dict) or not value.get("scenes"):
        raise AppendError("Run Check once before importing more video.")
    return value


def _save_check(data_root: Path, project_id: str, result: dict) -> None:
    path = _check_path(data_root, project_id)
    with _CHECK_WRITE_LOCK:
        temporary = path.with_name(f".{path.stem}-{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(path)


def _run(command: list[str], timeout: float = 3600.0) -> None:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AppendError(f"ffmpeg could not join the videos: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        raise AppendError(
            "ffmpeg could not join the videos. " + (detail[-1] if detail else "")
        )


def _stream_duration(path: Path, stream: str = "a:0") -> float:
    result = subprocess.run(
        [
            media.ffprobe(), "-v", "error", "-select_streams", stream,
            "-show_entries", "stream=duration",
            "-of", "default=nw=1:nk=1", str(path),
        ],
        capture_output=True, text=True, timeout=60,
    )
    try:
        return max(0.0, float(result.stdout.strip()))
    except ValueError:
        return 0.0


def _signature(path: Path) -> tuple:
    result = subprocess.run(
        [
            media.ffprobe(), "-v", "error",
            "-show_entries",
            "stream=codec_type,codec_name,profile,level,pix_fmt,width,height,"
            "sample_rate,channels",
            "-of", "json", str(path),
        ],
        capture_output=True, text=True, timeout=60,
    )
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return ()
    rows = []
    for stream in data.get("streams") or []:
        rows.append(tuple(sorted(
            (str(key), str(value))
            for key, value in stream.items()
            if value not in (None, "", "unknown") and key != "duration"
        )))
    return tuple(rows)


def _normalize_new(new: Path, new_meta: dict, output: Path, old_meta: dict) -> None:
    """Encode the new clip to the master's size, rate and audio shape."""
    from duckcore.engine import pipeline

    width = max(2, int(old_meta.get("width") or 1920) // 2 * 2)
    height = max(2, int(old_meta.get("height") or 1080) // 2 * 2)
    fps = float(old_meta.get("fps") or 30.0)
    duration = max(0.05, float(new_meta.get("duration") or media.duration(new)))
    old_audio = bool(old_meta.get("has_audio"))
    new_audio = bool(new_meta.get("has_audio"))
    args = [media.ffmpeg(), "-y", "-v", "error", "-hwaccel", "none", "-i", str(new)]
    if old_audio and not new_audio:
        args += [
            "-f", "lavfi", "-t", f"{duration:.6f}", "-i",
            "anullsrc=channel_layout=stereo:sample_rate=48000",
        ]
    video_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps:.3f}"
    )
    args += [
        "-map", "0:v:0", "-vf", video_filter,
        "-c:v", "h264_videotoolbox", "-q:v", "65",
        "-pix_fmt", "yuv420p", "-video_track_timescale", "30000",
    ]
    if old_audio:
        args += [
            "-map", "1:a:0" if not new_audio else "0:a:0",
            "-af", f"apad=whole_dur={duration:.6f}",
            "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k",
        ]
    else:
        args += ["-an"]
    args += ["-t", f"{duration:.6f}", "-movflags", "+faststart", str(output)]
    _run(args)


def _concat_copy(old: Path, new: Path, output: Path) -> None:
    listing = output.with_name(".append-copy.txt")
    listing.write_text(
        f"file '{old.as_posix()}'\nfile '{new.as_posix()}'\n", encoding="utf-8",
    )
    try:
        _run([
            media.ffmpeg(), "-y", "-v", "error",
            "-fflags", "+genpts", "-f", "concat", "-safe", "0", "-i", str(listing),
            "-c", "copy", "-avoid_negative_ts", "make_zero",
            "-movflags", "+faststart", str(output),
        ])
    finally:
        listing.unlink(missing_ok=True)


def _join_encode(old: Path, new: Path, output: Path, old_meta: dict, new_meta: dict) -> None:
    width = max(2, int(old_meta.get("width") or 1920) // 2 * 2)
    height = max(2, int(old_meta.get("height") or 1080) // 2 * 2)
    fps = float(old_meta.get("fps") or 30.0)
    old_duration = max(0.05, float(old_meta.get("duration") or 0.0))
    new_duration = max(0.05, float(new_meta.get("duration") or 0.0))

    def video(index: int) -> str:
        return (
            f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps:.3f}[v{index}]"
        )

    def audio(index: int, duration: float, present: bool) -> str:
        if present:
            return (
                f"[{index}:a]aresample=48000,"
                f"aformat=sample_fmts=fltp:channel_layouts=stereo[a{index}]"
            )
        return (
            f"anullsrc=channel_layout=stereo:sample_rate=48000,"
            f"atrim=duration={duration:.6f}[a{index}]"
        )

    graph = ";".join([
        video(0), video(1),
        audio(0, old_duration, bool(old_meta.get("has_audio"))),
        audio(1, new_duration, bool(new_meta.get("has_audio"))),
        "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]",
    ])
    _run([
        media.ffmpeg(), "-y", "-v", "error",
        "-hwaccel", "none", "-i", str(old), "-i", str(new),
        "-filter_complex", graph,
        "-map", "[v]", "-map", "[a]",
        "-c:v", "h264_videotoolbox", "-q:v", "65",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(output),
    ])


def _join_master(
    old: Path, new: Path, output: Path, old_meta: dict, new_meta: dict,
) -> tuple[float, float, dict]:
    """Join old master and new clip. Returns offset, duration, combined meta."""
    from duckcore.engine import pipeline

    old_duration = media.duration(old) or float(old_meta.get("duration") or 0.0)
    new_duration = media.duration(new) or float(new_meta.get("duration") or 0.0)
    if old_duration <= 0 or new_duration <= 0:
        raise AppendError("Could not read the video durations.")
    normalized = output.with_name(".append-normalized.mp4")
    lossless = False
    measured = old_duration
    try:
        try:
            _normalize_new(new, new_meta, normalized, old_meta)
            old_signature = _signature(old)
            new_signature = _signature(normalized)
            if not old_signature or not new_signature or old_signature != new_signature:
                raise AppendError("The new clip does not match the master streams.")
            _concat_copy(old, normalized, output)
            combined = pipeline.probe(output)
            combined_duration = float(combined.get("duration") or 0.0)
            audio_ok = True
            if old_meta.get("has_audio"):
                audio_ok = _stream_duration(output) >= combined_duration - 0.5
            boundary = _stream_duration(output, "v:0") - _stream_duration(normalized, "v:0")
            if (
                combined_duration >= old_duration + new_duration - 0.5
                and audio_ok
                and abs(boundary - old_duration) <= 0.25
            ):
                lossless = True
                measured = boundary
            else:
                output.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            output.unlink(missing_ok=True)
        finally:
            normalized.unlink(missing_ok=True)
        if not lossless:
            _join_encode(old, new, output, old_meta, new_meta)
            measured = old_duration
        combined = pipeline.probe(output)
        duration = float(combined.get("duration") or 0.0)
        if duration <= 0:
            raise AppendError("The joined video has no duration.")
        return round(measured, 3), round(duration, 3), combined
    except Exception:
        output.unlink(missing_ok=True)
        raise


def _scene(global_id: int, start: float, end: float, deep: bool = False) -> dict:
    return {
        "id": global_id,
        "start": round(float(start), 3),
        "end": round(float(end), 3),
        "dur": round(max(0.0, float(end) - float(start)), 3),
        "mid": round((float(start) + float(end)) / 2.0, 3),
        "motion_raw": 0.0,
        "deep": deep,
        "ocr": "",
        "faces": [],
        "salient": [],
        "visual": {"sharp": 0.0, "bright": 0.55, "contrast": 0.0, "saturation": 0.0, "color": 0.0},
    }


def _offset_scene(scene: dict, offset: float, global_id: int) -> dict:
    value = {**scene}
    value["id"] = global_id
    value["start"] = round(float(scene.get("start") or 0.0) + offset, 3)
    value["end"] = round(float(scene.get("end") or 0.0) + offset, 3)
    value["dur"] = round(max(0.0, value["end"] - value["start"]), 3)
    value["mid"] = round((value["start"] + value["end"]) / 2.0, 3)
    return value


def _prepare_edit(
    project: dict, result: dict, new_scenes: list[dict], data_root: Path,
) -> tuple[dict, Path, bool]:
    project_id = str(project["id"])
    meta = result.get("meta") or {}
    duration = float(meta.get("duration") or 0.0)
    full_edit = None
    for row in edits.list_edits(data_root, project_id):
        if row.get("kind") == "full":
            try:
                full_edit = edits.get_edit(data_root, project_id, str(row["id"]))
            except KeyError:
                full_edit = None
            break
    created = False
    if full_edit is None:
        now = time.time()
        full_edit = {
            "schema": 1,
            "id": f"ed_{uuid.uuid4().hex[:12]}",
            "project_id": project_id,
            "kind": "full",
            "title": "Full video",
            "created": now,
            "updated": now,
            "source": {
                "fingerprint": meta.get("fingerprint") or "",
                "duration": duration,
                "width": int(meta.get("width") or 0),
                "height": int(meta.get("height") or 0),
                "fps": float(meta.get("fps") or 0.0),
            },
            "start": 0.0,
            "end": round(duration, 3),
            "clips": edits._full_clips(result),
            "clean": [],
            "captions": None,
            "audio": {"mode": "original"},
        }
        created = True
    known = {clip.get("scene") for clip in full_edit.get("clips") or []}
    for scene in new_scenes:
        if scene.get("id") in known:
            continue
        full_edit.setdefault("clips", []).append(edits._clip(
            scene, float(scene.get("start") or 0.0), float(scene.get("end") or 0.0),
        ))
    full_edit["end"] = round(duration, 3)
    source = dict(full_edit.get("source") or {})
    source.update({
        "fingerprint": meta.get("fingerprint") or "",
        "duration": duration,
        "width": int(meta.get("width") or 0),
        "height": int(meta.get("height") or 0),
        "fps": float(meta.get("fps") or 0.0),
    })
    full_edit["source"] = source
    return full_edit, edits.edit_path(data_root, project_id, str(full_edit["id"])), created


def _commit(
    project: dict,
    result: dict,
    full_edit: dict,
    edit_path: Path,
    edit_created: bool,
    combined: Path,
    store: ProjectStore,
    data_root: Path,
) -> None:
    project_id = str(project["id"])
    check_path = _check_path(data_root, project_id)
    check_backup = check_path.read_text(encoding="utf-8") if check_path.is_file() else None
    edit_backup = None if edit_created or not edit_path.is_file() else edit_path.read_text(encoding="utf-8")
    old_source = str(project["source_path"])
    backup = combined.parent / ".commit"
    backup.mkdir(parents=True, exist_ok=True)
    if check_backup is not None:
        (backup / "check.json").write_text(check_backup, encoding="utf-8")
    if edit_backup is not None:
        (backup / "edit.json").write_text(edit_backup, encoding="utf-8")
    (backup / "marker.json").write_text(json.dumps({
        "project_id": project_id,
        "old_source": old_source,
        "edit_path": str(edit_path),
        "edit_created": edit_created,
    }), encoding="utf-8")
    try:
        _save_check(data_root, project_id, result)
        edits.save_edit(full_edit, data_root)
        store.update_source(project_id, combined)
    except Exception:
        if check_backup is not None:
            check_path.write_text(check_backup, encoding="utf-8")
        if edit_created:
            edit_path.unlink(missing_ok=True)
        elif edit_backup is not None:
            edit_path.write_text(edit_backup, encoding="utf-8")
        try:
            store.update_source(project_id, old_source)
        except Exception:
            pass
        shutil.rmtree(backup, ignore_errors=True)
        raise
    try:
        (backup / "committed").write_text("1", encoding="utf-8")
    except OSError:
        pass
    shutil.rmtree(backup, ignore_errors=True)


def recover_commits(store: ProjectStore, data_root: Path) -> None:
    """Roll back an append interrupted between check, edit and source writes."""
    imports = Path(data_root) / "imports"
    if not imports.is_dir():
        return
    for folder in imports.iterdir():
        marker = folder / ".commit" / "marker.json"
        if not folder.is_dir() or not marker.is_file():
            continue
        try:
            if (folder / ".commit" / "committed").is_file():
                shutil.rmtree(folder / ".commit", ignore_errors=True)
                continue
            data = json.loads(marker.read_text(encoding="utf-8"))
            project_id = str(data["project_id"])
            check_path = _check_path(Path(data_root), project_id)
            backup = check_path.parent / "check.json"
            saved = folder / ".commit" / "check.json"
            if saved.is_file():
                check_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(saved, backup)
            edit_path = Path(str(data["edit_path"]))
            if bool(data.get("edit_created")):
                edit_path.unlink(missing_ok=True)
            else:
                saved_edit = folder / ".commit" / "edit.json"
                if saved_edit.is_file():
                    edit_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(saved_edit, edit_path)
            old_source = str(data.get("old_source") or "")
            if old_source and Path(old_source).is_file():
                store.update_source(project_id, old_source)
        except Exception:
            continue
        shutil.rmtree(folder, ignore_errors=True)


def _archive_source(old_path: Path, project_id: str, data_root: Path) -> None:
    old_path = old_path.resolve()
    root = data_root.resolve()
    if not old_path.is_file() or not old_path.is_relative_to(root):
        return
    history = _project_dir(data_root, project_id) / "history"
    try:
        history.mkdir(parents=True, exist_ok=True)
        target = history / f"source_{int(time.time() * 1000)}{old_path.suffix or '.mp4'}"
        shutil.move(str(old_path), str(target))
        for stale in sorted(
            (item for item in history.iterdir() if item.is_file()),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )[5:]:
            stale.unlink(missing_ok=True)
        parent = old_path.parent
        if parent != root and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
    except OSError:
        pass


def _remove_source(path: Path, data_root: Path) -> None:
    path = path.resolve()
    root = data_root.resolve()
    imports = root / "imports"
    try:
        if path.is_relative_to(imports) and path.is_file():
            path.unlink(missing_ok=True)
            parent = path.parent
            if parent != root and parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
    except OSError:
        pass


def _refresh_preview(project: dict, data_root: Path) -> None:
    source = Path(str(project["source_path"]))
    preview = media.preview_path(data_root, str(project["id"]))
    try:
        threading.Thread(
            target=media.ensure_preview,
            args=(source, preview),
            kwargs={"force": True},
            daemon=True,
            name=f"duck-preview-{project['id']}",
        ).start()
    except Exception:  # noqa: BLE001
        pass


def _full_edit(data_root: Path, project_id: str) -> dict | None:
    for row in edits.list_edits(data_root, project_id):
        if row.get("kind") == "full":
            try:
                return edits.get_edit(data_root, project_id, str(row["id"]))
            except KeyError:
                return None
    return None


def expire_pending(
    data_root: Path, project_id: str, result: dict | None = None,
) -> dict | None:
    """Return an updated result when an abandoned background read expires."""
    try:
        current = copy.deepcopy(result) if isinstance(result, dict) else _load_check(data_root, project_id)
    except AppendError:
        return None
    meta = dict(current.get("append") or {})
    if meta.get("analysis") != "pending":
        return None
    with _ACTIVE_LOCK:
        active = _ACTIVE_READS.get(project_id, 0.0)
    if time.time() - active < 60.0:
        return None
    started = float(meta.get("analysis_started") or meta.get("at") or 0.0)
    if time.time() - started < PENDING_TIMEOUT:
        return None
    meta["analysis"] = "failed"
    meta["analysis_finished"] = time.time()
    meta["error"] = "The import read stopped before it finished."
    current["append"] = meta
    _save_check(data_root, project_id, current)
    return current


def append_video(
    project_id: str,
    new_source: str | Path,
    mode: str,
    *,
    store: ProjectStore,
    data_root: Path,
    checks: Any = None,
    renders: Any = None,
    analysis: bool = True,
    cleanup: bool = False,
) -> dict:
    from duckcore.engine import pipeline

    mode = str(mode or "").strip().lower()
    if mode not in {"scenes", "full"}:
        raise AppendError("Choose Add scenes or Use full video.")
    project = store.get(project_id)
    old_path = Path(str(project["source_path"]))
    new_path = Path(new_source).expanduser().resolve()
    if not old_path.is_file():
        raise AppendError("The project source video is missing.")
    if not new_path.is_file():
        raise AppendError("The new video file is missing.")
    if not new_path.is_relative_to(Path(data_root).resolve()):
        raise AppendError("The new video must be copied into the DuckSuite data folder.")
    if new_path == old_path.resolve():
        raise AppendError("That video is already this project's source.")
    if checks is not None:
        status = checks.status(project_id)
        if status.get("state") in {"queued", "running", "cancelling"}:
            raise AppendError("Wait for Check to finish first.")
    if renders is not None and renders.busy_for(project_id):
        raise AppendError("Wait for the render to finish first.")
    for row in store.list():
        if str(row.get("id")) != project_id and Path(str(row.get("source_path"))).resolve() == new_path:
            raise AppendError("That video is another project's source.")

    existing = _load_check(data_root, project_id)
    append_meta = dict(existing.get("append") or {})
    if append_meta.get("analysis") == "pending":
        expired = expire_pending(data_root, project_id, existing)
        if expired is None:
            raise AppendError("Wait for the last import to finish reading its scenes.")
        existing = expired

    old_meta = pipeline.probe(old_path)
    new_meta = pipeline.probe(new_path)
    folder = Path(data_root) / "imports" / uuid.uuid4().hex[:12]
    folder.mkdir(parents=True, exist_ok=True)
    combined = folder / "source.mp4"
    try:
        offset, duration, combined_meta = _join_master(
            old_path, new_path, combined, old_meta, new_meta,
        )
        result = _load_check(data_root, project_id)
        old_scenes = [item for item in result.get("scenes") or [] if isinstance(item, dict)]
        next_id = max([int(item.get("id") or 0) for item in old_scenes] + [-1]) + 1

        new_scenes: list[dict] = []
        local_scenes: list[dict] = []
        scan_info: dict = {}
        if mode == "scenes":
            try:
                local_scenes, scan_info = pipeline.scan_scenes(
                    str(new_path), float(new_meta.get("duration") or 0.0),
                    lambda fraction, message: None,
                )
            except Exception as exc:
                raise AppendError(f"Scene detection failed: {exc}") from exc
            for index, scene in enumerate(local_scenes):
                new_scenes.append(_offset_scene(scene, offset, next_id + index))
        else:
            new_scenes = [_scene(next_id, offset, duration)]
            new_duration = media.duration(new_path) or float(new_meta.get("duration") or 0.0)
            local_scenes = [_scene(0, 0.0, new_duration, deep=True)]

        started = time.time()
        result["meta"] = combined_meta
        result["source"] = {
            "path": str(combined),
            "duration": combined_meta.get("duration"),
            "width": combined_meta.get("width"),
            "height": combined_meta.get("height"),
            "fps": combined_meta.get("fps"),
        }
        result["scenes"] = [*old_scenes, *new_scenes]
        result["append"] = {
            "mode": mode,
            "at": started,
            "analysis_started": started,
            "offset": round(offset, 3),
            "scenes": len(new_scenes),
            "analysis": "pending" if analysis else "complete",
        }

        full_edit, edit_path, edit_created = _prepare_edit(project, result, new_scenes, data_root)
        _commit(project, result, full_edit, edit_path, edit_created, combined, store, data_root)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise

    project = store.get(project_id)
    old_resolved = old_path.resolve()
    shared = any(
        str(row.get("id")) != project_id
        and Path(str(row.get("source_path"))).resolve() == old_resolved
        for row in store.list()
    )
    if not shared:
        _archive_source(old_path, project_id, Path(data_root))
    _refresh_preview(project, data_root)
    if checks is not None:
        checks.adopt(project_id, result)
    if analysis:
        try:
            threading.Thread(
                target=_analyze_append,
                args=(
                    str(project_id), str(new_path), new_meta, result,
                    local_scenes, new_scenes, scan_info, offset, str(data_root),
                    checks, cleanup,
                ),
                daemon=True,
                name=f"duck-append-{project_id}",
            ).start()
        except Exception as exc:  # noqa: BLE001
            result["append"]["analysis"] = "failed"
            result["append"]["error"] = f"The read could not start: {str(exc)[:200]}"
            _save_check(data_root, project_id, result)
            if checks is not None:
                checks.adopt(project_id, result)
            if cleanup:
                _remove_source(new_path, Path(data_root))
    elif cleanup:
        _remove_source(new_path, Path(data_root))

    return {
        "project": project,
        "mode": mode,
        "scenes": len(new_scenes),
        "offset": round(offset, 3),
        "duration": round(duration, 3),
        "check": result,
    }


def _analyze_append(
    project_id: str,
    new_source: str,
    new_meta: dict,
    result: dict,
    local_scenes: list[dict],
    global_scenes: list[dict],
    scan_info: dict,
    offset: float,
    data_root_value: str,
    checks: Any,
    cleanup: bool = False,
) -> None:
    data_root = Path(data_root_value)
    task_dir = _project_dir(data_root, project_id) / "append" / uuid.uuid4().hex[:10]
    task_dir.mkdir(parents=True, exist_ok=True)
    with _ACTIVE_LOCK:
        _ACTIVE_READS[project_id] = time.time()

    def beat(stage: str, fraction: float, message: str) -> None:
        with _ACTIVE_LOCK:
            _ACTIVE_READS[project_id] = time.time()
    global_by_local = {
        int(local.get("id") or 0): int(global_scene.get("id") or 0)
        for local, global_scene in zip(local_scenes, global_scenes)
    }
    try:
        from duckcore.engine import pipeline, stt

        analysis = pipeline.analyze_source(
            new_source,
            new_meta,
            task_dir,
            {
                "ocr": True,
                "smart_crop": False,
                "crop_tracking": False,
                "transcribe": True,
                "job_id": project_id,
                "request_id": project_id,
            },
            beat,
            scenes=local_scenes,
            scan_info=scan_info,
        )
        fresh = _load_check(data_root, project_id)
        token = dict(fresh.get("append") or {})
        if abs(float(token.get("at") or 0.0) - float((result.get("append") or {}).get("at") or 0.0)) > 0.001:
            return
        fresh_scenes = [item for item in fresh.get("scenes") or [] if isinstance(item, dict)]
        by_id = {int(scene.get("id") or 0): index for index, scene in enumerate(fresh_scenes)}
        analyzed = {int(scene.get("id") or 0): scene for scene in analysis.get("scenes") or []}
        for local_id, local in analyzed.items():
            index = by_id.get(global_by_local.get(local_id, -1))
            if index is None:
                continue
            keep = {"id", "start", "end", "dur", "mid"}
            fresh_scenes[index] = {**local, **{key: fresh_scenes[index][key] for key in keep if key in fresh_scenes[index]}}
        fresh["scenes"] = fresh_scenes

        package = stt.load_latest_transcript(task_dir) or {}
        old = stt.load_latest_transcript(_project_dir(data_root, project_id)) or {}
        merged = None
        if package.get("segments"):
            segments, words = stt._shift_rows(
                list(package.get("segments") or []),
                list(package.get("words") or []),
                offset,
            )
            all_segments = list(old.get("segments") or []) + segments
            all_words = list(old.get("words") or []) + words
            merged = stt.build_transcript(
                engine=str(package.get("engine") or "append"),
                model=str(package.get("model") or ""),
                language=str(package.get("language") or old.get("language") or "en"),
                segments=all_segments,
                words=all_words,
                audio_duration=float(fresh.get("meta", {}).get("duration") or 0.0),
                source_hash=str(fresh.get("meta", {}).get("fingerprint") or ""),
            )
            stt.save_transcript(_project_dir(data_root, project_id), merged)
            fresh["transcript"] = {
                "provider": merged.get("engine"),
                "language": merged.get("language"),
                "segments": len(merged.get("segments") or []),
                "text": str(merged.get("text") or "")[:4000],
            }
            try:
                from duckcore import captions

                full_edit = _full_edit(data_root, project_id)
                if full_edit is not None:
                    captions.append_appended(
                        full_edit, merged, data_root, offset,
                        scene_ids={int(scene.get("id") or 0) for scene in global_scenes},
                    )
            except Exception as exc:  # noqa: BLE001
                token["caption_error"] = str(exc)[:200]
                fresh["append"] = token

        token = dict(fresh.get("append") or {})
        token["analysis"] = "done"
        token["analysis_finished"] = time.time()
        fresh["append"] = token
        _save_check(data_root, project_id, fresh)
        if checks is not None:
            checks.adopt(project_id, fresh)
    except Exception as exc:  # noqa: BLE001
        try:
            fresh = _load_check(data_root, project_id)
            append = dict(fresh.get("append") or {})
            append["analysis"] = "failed"
            append["analysis_finished"] = time.time()
            append["error"] = str(exc)[:300]
            fresh["append"] = append
            _save_check(data_root, project_id, fresh)
            if checks is not None:
                checks.adopt(project_id, fresh)
        except Exception:
            pass
    finally:
        with _ACTIVE_LOCK:
            _ACTIVE_READS.pop(project_id, None)
        shutil.rmtree(task_dir, ignore_errors=True)
        if cleanup:
            _remove_source(Path(new_source), data_root)
