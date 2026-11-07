"""Minimal DuckSuite render: cut clips, fill clean layers, concat."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from duckcore import caption_burn, captions, edits, media
from duckcore.store import ProjectStore


class RenderError(RuntimeError):
    pass


class RenderCancelled(RenderError):
    pass


def _target_size(meta: dict) -> tuple[int, int]:
    width = max(2, int(meta.get("width") or 0))
    height = max(2, int(meta.get("height") or 0))
    if width >= height:
        out_h = 1080
        out_w = max(2, int(round(width * out_h / height)))
    else:
        out_w = 1080
        out_h = max(2, int(round(height * out_w / width)))
    return out_w + (out_w % 2), out_h + (out_h % 2)


def _video_codec() -> list[str]:
    override = os.environ.get("DUCK_RENDER_ENCODER", "").strip().lower()
    if override in {"h264_videotoolbox", "videotoolbox"} or (
        not override and sys.platform == "darwin"
    ):
        return ["-c:v", "h264_videotoolbox", "-q:v", "65"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]


def _run(command: list[str], timeout: float = 3600) -> None:
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RenderError((result.stderr or result.stdout or "ffmpeg failed")[-800:])


def _fill_layers(edit: dict) -> list[dict]:
    return [
        layer for layer in edit.get("clean") or []
        if isinstance(layer, dict)
        and layer.get("enabled") is not False
        and layer.get("kind") == "fill"
    ]


def render_edit(
    project: dict,
    edit: dict,
    data_root: Path,
    *,
    progress: Callable[[float, str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> Path:
    from duckcore.engine import pipeline, textfill

    def check_cancel() -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise RenderCancelled("Render cancelled.")

    source = str(project["source_path"])
    meta = pipeline.probe(source)
    out_w, out_h = _target_size(meta)
    fps = float(meta.get("fps") or 30.0)
    target_fps = 24 if abs(fps - 24.0) < 0.6 else 30
    project_id = str(project["id"])
    job_dir = Path(data_root) / "projects" / project_id
    cache = job_dir / "fill"
    output_dir = job_dir / "renders"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    output = output_dir / f"{edit['id']}_{stamp}.mp4"
    clips = [clip for clip in edit.get("clips") or [] if float(clip.get("end") or 0) > float(clip.get("start") or 0)]
    if not clips:
        raise RenderError("This edit has no clips.")

    layers = _fill_layers(edit)
    segments: list[Path] = []
    ffmpeg = media.ffmpeg()
    try:
        for index, clip in enumerate(clips):
            check_cancel()
            start = float(clip.get("start") or 0.0)
            duration = max(0.04, float(clip.get("end") or 0.0) - start)
            if progress:
                progress(index / max(1, len(clips)), f"Rendering clip {index + 1}/{len(clips)}")
            filled = None
            if layers:
                filled = textfill.prepare_span(
                    source=source,
                    meta=meta,
                    start=start,
                    duration=duration,
                    layers=layers,
                    method="lama",
                    cache_dir=cache,
                    data_root=data_root,
                    ffmpeg=ffmpeg,
                    cancel_event=cancel_event,
                    progress=(
                        (lambda fraction, message: progress(
                            (index + max(0.0, min(1.0, float(fraction)))) / max(1, len(clips)),
                            message,
                        ))
                        if progress is not None else None
                    ),
                )
            segment = output_dir / f".{edit['id']}_{index:04d}.mp4"
            scale = (
                f"scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,"
                f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps={target_fps}"
            )
            if filled:
                command = [
                    ffmpeg, "-y", "-v", "error",
                    "-i", str(filled["path"]),
                    "-ss", f"{start:.6f}", "-t", f"{duration:.6f}", "-i", source,
                    "-map", "0:v:0", "-map", "1:a?",
                    "-vf", scale,
                    *_video_codec(),
                    "-c:a", "aac", "-b:a", "192k", "-shortest",
                    str(segment),
                ]
            else:
                command = [
                    ffmpeg, "-y", "-v", "error",
                    "-ss", f"{start:.6f}", "-t", f"{duration:.6f}", "-i", source,
                    "-map", "0:v:0", "-map", "0:a?",
                    "-vf", scale,
                    *_video_codec(),
                    "-c:a", "aac", "-b:a", "192k", "-shortest",
                    str(segment),
                ]
            _run(command)
            segments.append(segment)

        if progress:
            progress(0.96, "Joining clips")
        listing = output_dir / f".{edit['id']}_concat.txt"
        listing.write_text(
            "".join(f"file '{segment.as_posix()}'\n" for segment in segments),
            encoding="utf-8",
        )
        _run([
            ffmpeg, "-y", "-v", "error",
            "-f", "concat", "-safe", "0", "-i", str(listing),
            "-c", "copy", "-movflags", "+faststart", str(output),
        ])
        listing.unlink(missing_ok=True)
        for segment in segments:
            segment.unlink(missing_ok=True)

        track = edit.get("captions")
        if isinstance(track, dict) and track.get("cues"):
            output.with_suffix(".srt").write_text(captions.srt(track), encoding="utf-8")
            if track.get("burn"):
                if progress:
                    progress(0.97, "Burning captions")
                captioned = output.with_name(f".{output.stem}.captions.mp4")
                caption_burn.burn_captions(
                    output, track, captioned,
                    width=out_w, height=out_h, fps=float(target_fps), ffmpeg=ffmpeg,
                )
                captioned.replace(output)

        voice = edit.get("voice")
        if isinstance(voice, dict) and voice.get("audio"):
            voice_path = job_dir / str(voice["audio"])
            if voice_path.is_file():
                if progress:
                    progress(0.985, "Mixing voice-over")
                mixed = output.with_name(f".{output.stem}.voice.mp4")
                if voice.get("mode") == "voice_only" or not media.has_audio(output):
                    _run([
                        ffmpeg, "-y", "-v", "error",
                        "-i", str(output), "-i", str(voice_path),
                        "-map", "0:v:0", "-map", "1:a:0",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                        "-shortest", "-movflags", "+faststart", str(mixed),
                    ])
                else:
                    _run([
                        ffmpeg, "-y", "-v", "error",
                        "-i", str(output), "-i", str(voice_path),
                        "-filter_complex",
                        "[0:a]volume=0.22[o];[1:a]volume=1.0[v];"
                        "[o][v]amix=inputs=2:duration=first:dropout_transition=0[a]",
                        "-map", "0:v:0", "-map", "[a]",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                        "-shortest", "-movflags", "+faststart", str(mixed),
                    ])
                mixed.replace(output)

        if progress:
            progress(1.0, "Render complete")
        return output
    except Exception:
        for segment in segments:
            segment.unlink(missing_ok=True)
        raise

class RenderQueue:
    def __init__(self, data_root: Path):
        self.data_root = Path(data_root)
        self.path = self.data_root / "state.db"
        self.lock = threading.Lock()
        self.paused = False
        self.cancel_events: dict[str, threading.Event] = {}
        self._init()
        threading.Thread(target=self._loop, daemon=True, name="duck-render-queue").start()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _init(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS render_queue (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    edit_id TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    state TEXT NOT NULL,
                    stage TEXT NOT NULL DEFAULT 'Queued',
                    progress REAL NOT NULL DEFAULT 0,
                    message TEXT NOT NULL DEFAULT '',
                    output TEXT NOT NULL DEFAULT '',
                    created REAL NOT NULL,
                    updated REAL NOT NULL
                )
                """
            )
            connection.execute(
                """
                UPDATE render_queue
                SET state = 'queued', stage = 'Queued',
                    message = 'Resuming after restart', updated = ?
                WHERE state IN ('running', 'cancelling')
                """,
                (time.time(),),
            )

    def _row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "edit_id": row["edit_id"],
            "title": row["title"],
            "state": row["state"],
            "stage": row["stage"],
            "progress": row["progress"],
            "message": row["message"],
            "output": row["output"],
            "created": row["created"],
            "updated": row["updated"],
        }

    def enqueue(self, project_id: str, edit_id: str, title: str) -> dict:
        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT * FROM render_queue
                WHERE project_id = ? AND edit_id = ?
                  AND state IN ('queued', 'running', 'cancelling')
                ORDER BY created DESC LIMIT 1
                """,
                (project_id, edit_id),
            ).fetchone()
            if existing is not None:
                return self._row(existing)
            item_id = f"rq_{uuid.uuid4().hex[:12]}"
            now = time.time()
            connection.execute(
                """
                INSERT INTO render_queue
                    (id, project_id, edit_id, title, state, stage, progress,
                     message, output, created, updated)
                VALUES (?, ?, ?, ?, 'queued', 'Queued', 0, ?, '', ?, ?)
                """,
                (item_id, project_id, edit_id, title, "Waiting to render", now, now),
            )
            row = connection.execute(
                "SELECT * FROM render_queue WHERE id = ?", (item_id,)
            ).fetchone()
        return self._row(row)

    def start(self, project_id: str, edit_id: str) -> dict:
        from duckcore import edits

        edit = edits.get_edit(self.data_root, project_id, edit_id)
        return self.enqueue(project_id, edit_id, str(edit.get("title") or ""))

    def status(self, project_id: str, edit_id: str) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM render_queue
                WHERE project_id = ? AND edit_id = ?
                ORDER BY created DESC LIMIT 1
                """,
                (project_id, edit_id),
            ).fetchone()
        if row is None:
            return {
                "state": "idle", "stage": "Not rendered", "progress": 0.0,
                "message": "", "output": "",
            }
        return self._row(row)

    def list(self, limit: int = 50) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT r.*, p.name AS project_name
                FROM render_queue r
                LEFT JOIN projects p ON p.id = r.project_id
                ORDER BY r.created DESC LIMIT ?
                """,
                (max(1, min(200, int(limit))),),
            ).fetchall()
        result = []
        for row in rows:
            item = self._row(row)
            item["project_name"] = row["project_name"] or ""
            result.append(item)
        return result

    def pause(self) -> dict:
        self.paused = True
        return {"paused": True}

    def resume(self) -> dict:
        self.paused = False
        return {"paused": False}

    def cancel(self, project_id: str, edit_id: str) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM render_queue
                WHERE project_id = ? AND edit_id = ?
                  AND state IN ('queued', 'running', 'cancelling')
                ORDER BY created DESC LIMIT 1
                """,
                (project_id, edit_id),
            ).fetchone()
            if row is None:
                return self.status(project_id, edit_id)
            item = self._row(row)
            if item["state"] == "queued":
                connection.execute(
                    "UPDATE render_queue SET state='cancelled', stage='Cancelled', message='Cancelled', updated=? WHERE id=?",
                    (time.time(), item["id"]),
                )
            else:
                event = self.cancel_events.get(item["id"])
                if event is not None:
                    event.set()
                connection.execute(
                    "UPDATE render_queue SET state='cancelling', stage='Cancelling', message='Stopping the render', updated=? WHERE id=?",
                    (time.time(), item["id"]),
                )
        return self.status(project_id, edit_id)

    def _next(self) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM render_queue WHERE state='queued' ORDER BY created ASC LIMIT 1"
            ).fetchone()
        return self._row(row) if row else None

    def _update(self, item_id: str, **values) -> None:
        allowed = {"state", "stage", "progress", "message", "output"}
        fields = [key for key in values if key in allowed]
        if not fields:
            return
        values["updated"] = time.time()
        assignments = ", ".join(f"{key} = ?" for key in fields) + ", updated = ?"
        params = [values[key] for key in fields] + [values["updated"], item_id]
        with self._connect() as connection:
            connection.execute(
                f"UPDATE render_queue SET {assignments} WHERE id = ?", params,
            )

    def _loop(self) -> None:
        while True:
            if self.paused:
                time.sleep(0.5)
                continue
            item = self._next()
            if item is None:
                time.sleep(0.5)
                continue
            event = threading.Event()
            self.cancel_events[item["id"]] = event
            self._update(
                item["id"], state="running", stage="Rendering",
                progress=0.01, message="Starting render",
            )
            try:
                from duckcore import edits
                from duckcore.store import ProjectStore

                store = ProjectStore(self.data_root)
                project = store.get(item["project_id"])
                edit = edits.get_edit(self.data_root, item["project_id"], item["edit_id"])

                def progress(fraction: float, message: str) -> None:
                    self._update(
                        item["id"], state="running", stage="Rendering",
                        progress=max(0.01, min(0.99, float(fraction))),
                        message=message,
                    )

                output = render_edit(
                    project, edit, self.data_root,
                    progress=progress, cancel_event=event,
                )
                if event.is_set():
                    self._update(
                        item["id"], state="cancelled", stage="Cancelled",
                        progress=1.0, message="Render cancelled",
                    )
                else:
                    self._update(
                        item["id"], state="done", stage="Done",
                        progress=1.0, message="Render complete", output=str(output),
                    )
            except Exception as exc:  # noqa: BLE001
                cancelled = event.is_set()
                self._update(
                    item["id"],
                    state="cancelled" if cancelled else "failed",
                    stage="Cancelled" if cancelled else "Failed",
                    progress=1.0,
                    message="Render cancelled" if cancelled else str(exc)[:500],
                )
            finally:
                self.cancel_events.pop(item["id"], None)
