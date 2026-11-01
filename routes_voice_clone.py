"""HTTP surface for cloned voices.

* Setup, **My voice**: record or upload the creator's own voice.
* Edit, **Clone the video voice**: clone the speaker of the open video.
* Setup, **Library backup**: move every clone to another Mac as a ZIP.

Both end in the same store (`voice_clone`): a reference sample kept on this
Mac that OpenRouter's HeyGen Voice Turbo clones on every speech request. A
clone shows up as a HeyGen Voice Turbo voice in every voice picker. Writes need
the same-origin check Setup uses, and every clone needs an explicit consent
flag.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import threading
import uuid
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

import editions
import job_queue
import voice_audio
import voice_clone
import voice_errors
import voice_persona
import voice_readiness
import voice_reference
import voice_takes


def _voice_room_on() -> None:
    """Every voice clone route is part of the hidden Voice Room feature."""
    if not editions.feature_on("voice_room"):
        raise HTTPException(404, "Not found")


router = APIRouter(dependencies=[Depends(_voice_room_on)])

UPLOAD_SUFFIXES = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".webm", ".flac", ".mp4", ".mov"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".mkv", ".avi"}
CANDIDATE_KIND = "voice-candidates"
CANDIDATE_DIR = "voice-candidates"
CANDIDATE_COUNT = 5
#: The default search window. A 17-minute video can take minutes to decode and
#: separate; the first two minutes usually hold enough clean speech. The UI can
#: ask for the whole video with ``full=1``.
SEARCH_WINDOW_SECONDS = 120.0
#: Quiet-gap band energy this close to the speech band means music is present.
MUSIC_RESIDUAL_DB = -24.0
#: My voice cleaning runs inside the upload request; it reads at most this
#: much of the file, which is twice what a clone sample keeps.
UPLOAD_CLEAN_SECONDS = 2 * voice_clone.MAX_SAMPLE_SECONDS
NO_SOUND = "This video has no sound track, so there is no voice to clone."
#: A voice library backup holds only clone metadata and samples. The version
#: lets a later import refuse a manifest it does not understand.
LIBRARY_VERSION = 1
LIBRARY_MANIFEST = "manifest.json"
LIBRARY_MANIFEST_BYTES = 1024 * 1024
LIBRARY_MAX_VOICES = 500
CANDIDATE_CANCELS: dict[str, threading.Event] = {}
CANDIDATE_STAGES: dict[str, str] = {}
CANDIDATE_RESULTS: dict[str, dict] = {}
CANDIDATE_ERRORS: dict[str, str] = {}
#: Jobs whose candidate state stays in memory; older ones fall back to the
#: report on disk. Guards against tables that grow for the life of the app.
CANDIDATE_MEMORY = 64
_CANDIDATE_LOCK = threading.RLock()
_CANDIDATE_TABLES = (CANDIDATE_CANCELS, CANDIDATE_STAGES, CANDIDATE_RESULTS, CANDIDATE_ERRORS)
#: Cancel switches for long clone requests, keyed by the client's task id.
#: The page sends a fresh id with each clone and `DELETE /api/voices/tasks/{id}`
#: to cancel it; the request then stops cleaning and never saves a clone.
VOICE_TASK_CANCELS: dict[str, threading.Event] = {}
VOICE_TASK_MEMORY = 64
VOICE_TASK_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
CANCELLED = "Cancelled. No voice was cloned."
_TASK_LOCK = threading.Lock()


def _task_event(task_id: str) -> threading.Event | None:
    """The cancel switch for one clone request, made on first use."""
    if not task_id:
        return None
    if not VOICE_TASK_ID.match(task_id):
        raise HTTPException(400, voice_errors.BAD_TASK)
    with _TASK_LOCK:
        event = VOICE_TASK_CANCELS.get(task_id)
        if event is None:
            event = VOICE_TASK_CANCELS[task_id] = threading.Event()
            while len(VOICE_TASK_CANCELS) > VOICE_TASK_MEMORY:
                VOICE_TASK_CANCELS.pop(next(iter(VOICE_TASK_CANCELS)), None)
        return event


def _task_done(task_id: str) -> None:
    with _TASK_LOCK:
        VOICE_TASK_CANCELS.pop(task_id, None)


def _stop_if_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise HTTPException(409, CANCELLED)


def _remember(table: dict, job_id: str, value) -> None:
    """Store one job's entry, dropping the oldest jobs past the cap.

    Cancel switches are not capped: each one is removed when its search ends.
    """
    with _CANDIDATE_LOCK:
        table.pop(job_id, None)
        table[job_id] = value
        if table is CANDIDATE_CANCELS:
            return
        while len(table) > CANDIDATE_MEMORY:
            table.pop(next(iter(table)), None)


def forget_job(job_id: str) -> None:
    """Drop every in-memory candidate entry for a deleted job."""
    with _CANDIDATE_LOCK:
        cancel = CANDIDATE_CANCELS.get(job_id)
        if cancel is not None:
            cancel.set()
        for table in _CANDIDATE_TABLES:
            table.pop(job_id, None)


class VideoCloneBody(BaseModel):
    name: str = ""
    language: str = ""
    consent: bool = False
    start: float | None = None
    end: float | None = None
    candidate: int | None = None
    #: Client task id; `DELETE /api/voices/tasks/{task}` cancels this clone.
    task: str = ""

    model_config = {"extra": "forbid"}


class RenameBody(BaseModel):
    name: str

    model_config = {"extra": "forbid"}


class SampleBody(BaseModel):
    text: str = ""
    rate: float = 1.0

    model_config = {"extra": "forbid"}


class AnyVoiceSampleBody(BaseModel):
    engine: str
    voice: str = ""
    text: str = ""
    rate: float = 1.0

    model_config = {"extra": "forbid"}


class TakeStarBody(BaseModel):
    starred: bool = True

    model_config = {"extra": "forbid"}


class TakeSaveBody(BaseModel):
    name: str = ""

    model_config = {"extra": "forbid"}


class TakeCleanupBody(BaseModel):
    confirm: bool = False
    days: int | None = None

    model_config = {"extra": "forbid"}


class LockBody(BaseModel):
    locked: bool = True

    model_config = {"extra": "forbid"}


class KeepBody(BaseModel):
    take_id: str = ""

    model_config = {"extra": "forbid"}


class ReferenceCloneBody(BaseModel):
    name: str = ""
    language: str = ""
    consent: bool = False
    start: float | None = None
    end: float | None = None
    task: str = ""

    model_config = {"extra": "forbid"}


class VoiceoverBody(BaseModel):
    engine: str = "heygen"
    voice: str = ""
    text: str = ""
    rate: float = 1.0
    language: str = ""
    label: str = ""
    clone: str = ""
    selfcheck: bool = True
    #: Client task id; `DELETE /api/voices/tasks/{task}` stops this voiceover.
    task: str = ""

    model_config = {"extra": "forbid"}


def _app():
    import app

    return app


def _guard(request: Request) -> None:
    if not _app()._setup_origin_ok(request):
        raise HTTPException(403, voice_errors.CROSS_SITE)


def _fail(exc: voice_clone.CloneError) -> HTTPException:
    return HTTPException(exc.status_code, voice_errors.clean(str(exc)))


def _work_dir() -> Path:
    path = voice_clone.settings_store.DATA / "cache" / "voice-clone" / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


def _candidate_dir(job_id: str) -> Path:
    return _app()._job_dir(job_id) / CANDIDATE_DIR


def _candidate_file(job_id: str, index: int) -> Path:
    return _candidate_dir(job_id) / f"candidate-{index:02d}.wav"


def _short_error(exc: Exception) -> str:
    text = str(exc).splitlines()[0].strip() if str(exc) else exc.__class__.__name__
    return voice_errors.clean(text, "That step failed. Try again.")


def _read_candidate_report(job_id: str) -> dict:
    path = _candidate_dir(job_id) / "report.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, HTTPException):
        return {}
    return data if isinstance(data, dict) else {}


def _upload_head(raw: Path, work: Path, cancel_event: threading.Event | None = None) -> Path:
    """The first ``UPLOAD_CLEAN_SECONDS`` as mono PCM, so cleaning time is bounded."""
    import audio  # noqa: PLC0415 - audio imports voice_clone

    head = work / "head.wav"
    audio._run([
        audio._ffmpeg(), "-y", "-v", "error", "-i", str(raw), "-vn",
        "-t", f"{UPLOAD_CLEAN_SECONDS:.0f}", "-ac", "1", "-ar", "48000",
        "-c:a", "pcm_s16le", str(head),
    ], timeout=300, cancel_event=cancel_event)
    return head


def _silent_reference(path: Path) -> bool:
    """True when a reference holds no speech. An unreadable file is not silence."""
    import voice_audio

    try:
        return bool(voice_audio.analyse(path).get("silent"))
    except (RuntimeError, OSError, ValueError):
        return False


def _refuse_silent(path: Path) -> None:
    """Stop before a silent clip becomes a voice, with the fix in the message."""
    if _silent_reference(path):
        raise HTTPException(400, voice_errors.NO_SPEECH)


def _set_stage(job_id: str, stage: str) -> None:
    _remember(CANDIDATE_STAGES, job_id, str(stage or ""))


def _run_candidate_search(
    job_id: str,
    cancel_event: threading.Event,
    out_dir: Path,
    *,
    start: float = 0.0,
    seconds: float = 0.0,
    fast: bool = False,
) -> dict:
    """Background worker: clean the source and keep 3-5 candidate WAVs.

    ``seconds`` above zero searches only that window of the source. The whole
    video is still available when the caller asks for it. ``fast`` skips the
    separation model and uses the ffmpeg denoise gate, so the first result is
    quick; a clean search can run afterwards.
    """
    import audio
    import voice_extract

    app = _app()
    job = app.load_job(job_id)
    source = Path(str((job.get("source") or {}).get("path") or ""))
    if not source.is_file():
        raise voice_clone.CloneError("The source video for this job is missing.", 404)
    window_path: Path | None = None
    search_source = source
    offset = 0.0
    _set_stage(job_id, "preparing")
    try:
        if seconds > 0:
            duration = float((job.get("source") or {}).get("duration") or 0.0)
            start = max(0.0, float(start))
            if duration > 0:
                # An unknown length (0) keeps the full window instead of 1 s.
                start = min(start, max(0.0, duration - 1.0))
                seconds = max(1.0, min(float(seconds), max(1.0, duration - start)))
            window_path = out_dir / "search-window.wav"
            audio._run([
                audio._ffmpeg(), "-y", "-v", "error",
                "-ss", f"{start:.3f}", "-t", f"{seconds:.3f}", "-i", str(source),
                "-vn", "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(window_path),
            ], timeout=600, cancel_event=cancel_event)
            search_source = window_path
            offset = start
        report = voice_extract.find_voice_candidates(
            search_source, out_dir,
            cancel_event=cancel_event,
            separate=False if fast else "best",
            denoise="afftdn" if fast else "auto",
            on_stage=lambda stage: _set_stage(job_id, stage),
        )
        report = dict(report)
        report["job_id"] = job_id
        report.setdefault("candidates", [])
        report["window_offset"] = round(offset, 3)
        report["window_seconds"] = round(seconds, 3) if seconds > 0 else 0.0
        report["fast"] = bool(fast)
        _remember(CANDIDATE_RESULTS, job_id, report)
        with _CANDIDATE_LOCK:
            CANDIDATE_ERRORS.pop(job_id, None)
        try:
            (out_dir / "report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8",
            )
        except OSError:
            pass
        _set_stage(job_id, "done")
        return report
    except Exception as exc:
        if cancel_event.is_set():
            _set_stage(job_id, "cancelled")
        else:
            _remember(CANDIDATE_ERRORS, job_id, _short_error(exc))
            _set_stage(job_id, "failed")
        raise
    finally:
        if window_path is not None:
            try:
                window_path.unlink()
            except OSError:
                pass
        # The search is over; its cancel switch is no longer needed. A newer
        # search for the same job keeps its own event.
        with _CANDIDATE_LOCK:
            if CANDIDATE_CANCELS.get(job_id) is cancel_event:
                CANDIDATE_CANCELS.pop(job_id, None)


def _public_candidate(job_id: str, item: dict, models: dict, offset: float = 0.0) -> dict:
    window = item.get("window") or [item.get("start") or 0.0, item.get("end") or 0.0]
    try:
        start, end = float(window[0]), float(window[1])
    except (TypeError, ValueError, IndexError):
        start, end = 0.0, 0.0
    start += offset
    end += offset
    quality = item.get("quality") or {}
    summary = {
        key: quality.get(key)
        for key in ("snr_db", "music_noise_residual_db", "noise_floor_dbfs", "peak_dbfs")
    }
    index = int(item.get("index") or 0)
    return {
        "index": index,
        "start": round(start, 3),
        "end": round(end, 3),
        "window": [round(start, 3), round(end, 3)],
        "duration": round(float(item.get("duration") or 0.0), 3),
        "score": item.get("score"),
        "speech_fraction": item.get("speech_fraction"),
        "quality": summary,
        "warnings": list(item.get("warnings") or []),
        "engines": dict(models or {}),
        "audio_url": f"/api/jobs/{job_id}/voices/candidates/{index}/audio",
    }


def _candidate_state(job_id: str) -> dict:
    app = _app()
    task = app.voice_pool.find_key(CANDIDATE_KIND, job_id)
    report = CANDIDATE_RESULTS.get(job_id) or _read_candidate_report(job_id)
    if task is not None:
        state = task.status
        if state == "interrupted":
            state = "cancelled"
        error = task.error
        result = task.result if isinstance(task.result, dict) else {}
    elif CANDIDATE_ERRORS.get(job_id):
        state, error, result = "failed", CANDIDATE_ERRORS[job_id], {}
    elif CANDIDATE_STAGES.get(job_id) == "cancelled" and not report:
        state, error, result = "cancelled", "Search cancelled.", {}
    elif report:
        state, error, result = "done", None, report
    else:
        state, error, result = "idle", None, {}
    report = result or report or {}
    models = report.get("models") or {}
    offset = float(report.get("window_offset") or 0.0)
    candidates = []
    if state == "done":
        candidates = [
            _public_candidate(job_id, item, models, offset)
            for item in report.get("candidates") or []
            if isinstance(item, dict)
        ]
    return {
        "job_id": job_id,
        "state": state,
        "stage": CANDIDATE_STAGES.get(job_id, ""),
        "error": error,
        "candidates": candidates,
        "warnings": list(report.get("warnings") or []),
        "models": models,
        "window": {
            "start": round(offset, 3),
            "seconds": round(float(report.get("window_seconds") or 0.0), 3),
        },
        "fast": bool(report.get("fast")),
    }


@router.get("/api/voices/clones")
def list_clones() -> dict:
    return {
        "available": voice_clone.available(),
        "voices": voice_clone.list_clones(),
        "limits": {
            "min_seconds": voice_clone.MIN_SAMPLE_SECONDS,
            "max_seconds": voice_clone.MAX_SAMPLE_SECONDS,
        },
    }


def _library_bad_manifest() -> HTTPException:
    return HTTPException(400, voice_errors.BAD_MANIFEST)


def _library_manifest(raw: bytes) -> list[dict]:
    """The clone rows in a backup manifest, with every identity checked."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _library_bad_manifest() from exc
    if not isinstance(data, dict):
        raise _library_bad_manifest()
    if str(data.get("version") or "") != str(LIBRARY_VERSION):
        raise HTTPException(400, voice_errors.OLD_BACKUP)
    voices = data.get("voices")
    if not isinstance(voices, list) or len(voices) > LIBRARY_MAX_VOICES:
        raise _library_bad_manifest()
    rows: list[dict] = []
    seen: set[str] = set()
    for item in voices:
        if not isinstance(item, dict):
            raise _library_bad_manifest()
        voice_id = str(item.get("voice_id") or "")
        if not voice_clone.is_voice_id(voice_id) or voice_id in seen:
            raise _library_bad_manifest()
        source = item.get("source")
        if source is not None and source not in voice_clone.SOURCES:
            raise _library_bad_manifest()
        created = item.get("created", 0)
        seconds = item.get("sample_seconds", 0)
        if isinstance(created, bool) or not isinstance(created, (int, float)):
            raise _library_bad_manifest()
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
            raise _library_bad_manifest()
        name = item.get("name")
        language = item.get("language")
        seen.add(voice_id)
        rows.append({
            "voice_id": voice_id,
            "name": name if isinstance(name, str) else "",
            "language": language if isinstance(language, str) else "",
            "source": source or "me",
            "created": float(created),
            "sample_seconds": float(seconds),
        })
    return rows


def _library_member(info: zipfile.ZipInfo) -> PurePosixPath:
    """A member path that cannot escape the archive root."""
    name = str(info.filename or "").replace("\\", "/")
    path = PurePosixPath(name)
    drive = bool(path.parts and re.match(r"^[A-Za-z]:", path.parts[0]))
    if (
        not name or "\x00" in name or name.startswith("/") or path.is_absolute()
        or ".." in path.parts or drive
    ):
        raise HTTPException(400, voice_errors.UNSAFE_BACKUP)
    return path


def _library_samples(archive: zipfile.ZipFile, voice_ids: set[str]) -> dict[str, zipfile.ZipInfo]:
    """Map each archive sample to its manifest voice; reject any other file."""
    samples: dict[str, zipfile.ZipInfo] = {}
    for info in archive.infolist():
        path = _library_member(info)
        if info.is_dir():
            continue
        if path.name == LIBRARY_MANIFEST and len(path.parts) == 1:
            continue
        parts = path.parts
        if len(parts) == 1:
            filename = parts[0]
        elif len(parts) == 2 and parts[0] == "samples":
            filename = parts[1]
        else:
            raise HTTPException(
                400, voice_errors.MISMATCHED_BACKUP,
            )
        stem = Path(filename).stem
        if (
            Path(filename).suffix.lower() != ".mp3"
            or not voice_clone.is_voice_id(stem)
            or stem not in voice_ids
        ):
            raise HTTPException(
                400, voice_errors.MISMATCHED_BACKUP,
            )
        if stem in samples:
            raise HTTPException(400, voice_errors.DUPLICATE_SAMPLE)
        samples[stem] = info
    return samples


def _copy_library_sample(archive: zipfile.ZipFile, info: zipfile.ZipInfo, target: Path) -> int:
    limit = voice_clone.MAX_REFERENCE_BYTES
    if info.file_size > limit:
        raise HTTPException(413, voice_errors.BIG_SAMPLE)
    size = 0
    with archive.open(info) as reader, target.open("wb") as writer:
        while chunk := reader.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                raise HTTPException(413, voice_errors.BIG_SAMPLE)
            writer.write(chunk)
    return size


def _sample_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _library_digests() -> set[str]:
    """Fingerprints of the samples already in this library."""
    digests: set[str] = set()
    for row in voice_clone.list_clones():
        try:
            digests.add(_sample_digest(voice_clone.sample_path(row["voice_id"])))
        except OSError:
            continue
    return digests


def _restore_library(path: Path, work: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        for info in infos:
            _library_member(info)
        manifests = [info for info in infos if info.filename == LIBRARY_MANIFEST]
        if len(manifests) != 1:
            raise HTTPException(400, voice_errors.BAD_MANIFEST)
        if manifests[0].file_size > LIBRARY_MANIFEST_BYTES:
            raise _library_bad_manifest()
        rows = _library_manifest(archive.read(manifests[0]))
        samples = _library_samples(archive, {row["voice_id"] for row in rows})
        limit = voice_clone.MAX_UPLOAD_BYTES
        if sum(info.file_size for info in samples.values()) > limit:
            raise HTTPException(413, voice_errors.BIG_BACKUP)
        imported = 0
        skipped = 0
        # Restoring the same backup twice must not duplicate every voice: a
        # sample already in the library is counted, not cloned again.
        present = _library_digests()
        already = 0
        for row in rows:
            info = samples.get(row["voice_id"])
            if info is None:
                skipped += 1
                continue
            sample = work / f"{row['voice_id']}.mp3"
            if _copy_library_sample(archive, info, sample) == 0:
                skipped += 1
                continue
            digest = _sample_digest(sample)
            if digest in present:
                already += 1
                continue
            try:
                voice_clone.create_clone(
                    sample,
                    name=row["name"],
                    source=row["source"],
                    consent=True,
                    language=row["language"],
                    seconds=row["sample_seconds"],
                )
                imported += 1
                present.add(digest)
            except (OSError, voice_clone.CloneError):
                skipped += 1
    return {"imported": imported, "skipped": skipped, "already": already}


@router.get("/api/voices/library/export")
def export_library() -> Response:
    """Every cloned voice and its sample as a ZIP, built in memory."""
    rows = voice_clone.list_clones()
    voices: list[dict] = []
    samples: list[tuple[str, bytes]] = []
    for row in rows:
        path = voice_clone.sample_path(row["voice_id"])
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        voices.append({
            "voice_id": row["voice_id"],
            "name": row.get("name") or "",
            "language": row.get("language") or "",
            "source": row.get("source") or "me",
            "created": row.get("created") or 0,
            "sample_seconds": row.get("sample_seconds") or 0,
        })
        samples.append((f"{row['voice_id']}.mp3", raw))
    manifest = {
        "version": LIBRARY_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "voices": voices,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(
            LIBRARY_MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=1),
        )
        for name, raw in samples:
            archive.writestr(name, raw)
    filename = f"vibecut-voice-library-{datetime.now(timezone.utc):%Y%m%d-%H%M}.zip"
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/api/voices/library/import")
def import_library(
    request: Request,
    file: UploadFile = File(...),
    consent: bool = Form(False),
) -> dict:
    """Restore a voice library. Existing clones are never touched."""
    _guard(request)
    if not consent:
        raise HTTPException(
            400, voice_errors.CONSENT_RESTORE,
        )
    work = _work_dir()
    try:
        path = work / "library.zip"
        size = 0
        with path.open("wb") as handle:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > voice_clone.MAX_UPLOAD_BYTES:
                    raise HTTPException(413, voice_errors.BIG_BACKUP)
                handle.write(chunk)
        if size == 0:
            raise HTTPException(400, voice_errors.EMPTY_FILE)
        if not zipfile.is_zipfile(path):
            raise HTTPException(400, voice_errors.UNREADABLE_BACKUP)
        try:
            return _restore_library(path, work)
        except HTTPException:
            raise
        except (
            zipfile.BadZipFile, zlib.error, RuntimeError,
            NotImplementedError, EOFError, KeyError,
        ) as exc:
            raise HTTPException(400, voice_errors.UNREADABLE_BACKUP) from exc
    finally:
        shutil.rmtree(work, ignore_errors=True)


@router.post("/api/voices/detect-language")
def detect_language(request: Request, file: UploadFile = File(...)) -> dict:
    """Detect the spoken language of a short recording, on this Mac only."""
    _guard(request)
    suffix = Path(file.filename or "voice.webm").suffix.lower() or ".webm"
    if suffix not in UPLOAD_SUFFIXES:
        raise HTTPException(400, voice_errors.BAD_FORMAT)
    work = _work_dir()
    try:
        import audio

        raw = work / f"detect{suffix}"
        size = 0
        with raw.open("wb") as handle:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > voice_clone.MAX_UPLOAD_BYTES:
                    raise HTTPException(413, voice_errors.TOO_LARGE)
                handle.write(chunk)
        if size == 0:
            raise HTTPException(400, voice_errors.EMPTY_FILE)
        wav = work / "detect.wav"
        try:
            audio._run([
                audio._ffmpeg(), "-y", "-v", "error", "-i", str(raw),
                "-t", "45", "-vn", "-ac", "1", "-ar", "16000",
                "-c:a", "pcm_s16le", str(wav),
            ], timeout=300)
        except audio.AudioError as exc:
            raise HTTPException(400, voice_errors.clean(str(exc), voice_errors.UNREADABLE)) from exc
        _refuse_silent(wav)
        import stt

        result = stt.transcribe(wav, work, 45.0, lambda *_: None, language="")
        if not result or not result.get("language"):
            raise HTTPException(
                400,
                "Could not detect the language. Local Whisper is needed; pick the language manually.",
            )
        code = str(result["language"]).lower().replace("_", "-").split("-")[0]
        return {"language": code, "text": str(result.get("text") or "")[:160]}
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------- reference


@router.post("/api/voices/reference")
def upload_reference(request: Request, file: UploadFile = File(...)) -> dict:
    """Keep a reference upload and propose a clean 10-15 s window.

    The clip over 15 s never goes to the cloud whole: the trimmer uses this
    session and the clone is cut from it.
    """
    _guard(request)
    suffix = Path(file.filename or "voice.wav").suffix.lower() or ".wav"
    if suffix not in UPLOAD_SUFFIXES:
        raise HTTPException(400, voice_errors.BAD_FORMAT)
    work = _work_dir()
    try:
        raw = work / f"reference{suffix}"
        size = 0
        with raw.open("wb") as handle:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > voice_clone.MAX_UPLOAD_BYTES:
                    raise HTTPException(413, voice_errors.TOO_LARGE)
                handle.write(chunk)
        if size == 0:
            raise HTTPException(400, voice_errors.EMPTY_FILE)
        try:
            return voice_reference.create(
                raw, suffix=suffix, name=Path(file.filename or "Recording").stem,
            )
        except voice_reference.ReferenceError as exc:
            raise HTTPException(exc.status_code, voice_errors.clean(str(exc))) from exc
    finally:
        shutil.rmtree(work, ignore_errors=True)


@router.get("/api/voices/reference/{ref_id}/audio")
def reference_audio(ref_id: str) -> FileResponse:
    """The decoded reference for the trimmer's preview and waveform."""
    try:
        path = voice_reference.audio_path(ref_id)
    except voice_reference.ReferenceError as exc:
        raise HTTPException(exc.status_code, voice_errors.clean(str(exc))) from exc
    return FileResponse(path, media_type="audio/wav", filename=f"{ref_id}.wav")


@router.delete("/api/voices/reference/{ref_id}")
def discard_reference(ref_id: str, request: Request) -> dict:
    _guard(request)
    return {"deleted": voice_reference.delete(ref_id)}


def _clone_reference(
    ref_id: str, body: ReferenceCloneBody, cancel_event: threading.Event | None,
) -> dict:
    if not voice_clone.available():
        raise HTTPException(400, voice_errors.NO_KEY)
    if not body.consent:
        raise HTTPException(400, voice_errors.CONSENT_CLONE)
    meta = voice_reference.get(ref_id)
    if meta is None:
        raise HTTPException(
            404,
            voice_errors.fix(
                "That reference is not on this Mac any more",
                "Upload the recording again, choose 8-15 s, then clone it",
            ),
        )
    try:
        start, end = voice_reference.window_for(meta, body.start, body.end)
    except voice_reference.ReferenceError as exc:
        raise HTTPException(exc.status_code, voice_errors.clean(str(exc))) from exc
    length = round(end - start, 2)
    if length > voice_audio.MAX_REFERENCE_SECONDS + 0.05:
        raise HTTPException(
            400,
            voice_errors.trim_too_long(length, voice_audio.MAX_REFERENCE_SECONDS),
        )
    if length < voice_audio.MIN_REFERENCE_SECONDS - 0.05:
        raise HTTPException(
            400,
            voice_errors.trim_too_short(length, voice_audio.MIN_REFERENCE_SECONDS),
        )
    source = voice_reference.source_path(ref_id)
    work = _work_dir()
    try:
        cut = work / "cut.wav"
        try:
            voice_audio.cut(source, cut, start, end)
        except RuntimeError as exc:
            raise HTTPException(400, voice_errors.clean(str(exc), voice_errors.UNREADABLE)) from exc
        _stop_if_cancelled(cancel_event)
        cleaned = False
        warning = ""
        sample_source = cut
        try:
            import voice_extract

            report = voice_extract.extract_clean_voice(
                cut, work / "clean",
                target_seconds=voice_audio.MAX_REFERENCE_SECONDS,
                cancel_event=cancel_event,
            )
            sample_source = Path(str(report["path"]))
            cleaned = True
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001 - cleaning is optional
            _stop_if_cancelled(cancel_event)
            warning = f"Used the raw cut: cleaning failed ({_short_error(exc)})."
            sample_source = cut
        sample = work / "sample.mp3"
        try:
            try:
                seconds = voice_clone.prepare_sample(sample_source, sample)
            except voice_clone.CloneError:
                if not cleaned:
                    raise
                cleaned = False
                warning = "Used the raw cut: the cleaned clip was too short."
                seconds = voice_clone.prepare_sample(cut, sample)
            if _silent_reference(sample) and cleaned:
                cleaned = False
                warning = "Used the raw cut: the cleaned clip had no speech."
                seconds = voice_clone.prepare_sample(cut, sample)
            _refuse_silent(sample)
            _stop_if_cancelled(cancel_event)
            record = voice_clone.create_clone(
                sample,
                name=body.name or f"{meta.get('name') or 'My'} voice"[:64],
                source="me",
                consent=body.consent,
                language=body.language,
                seconds=seconds,
            )
        except voice_clone.CloneError as exc:
            raise _fail(exc) from exc
        voice_reference.delete(ref_id)
        return {
            **record,
            "trim": {"start": start, "end": end, "seconds": length},
            "cleaned": cleaned,
            "warning": warning,
            "warnings": [],
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)


@router.post("/api/voices/reference/{ref_id}/clone")
def clone_reference(ref_id: str, body: ReferenceCloneBody, request: Request) -> dict:
    """Clone from the chosen range of a reference session."""
    _guard(request)
    cancel_event = _task_event(body.task)
    try:
        return _clone_reference(ref_id, body, cancel_event)
    finally:
        _task_done(body.task)


@router.post("/api/voices/clones")
def clone_my_voice(
    request: Request,
    file: UploadFile = File(...),
    name: str = Form(""),
    language: str = Form(""),
    consent: bool = Form(False),
    task: str = Form(""),
) -> dict:
    """Clone the creator's own voice from a recording or an uploaded file."""
    _guard(request)
    cancel_event = _task_event(task)
    try:
        return _clone_my_voice(file, name, language, consent, cancel_event)
    finally:
        _task_done(task)


def _clone_my_voice(
    file: UploadFile, name: str, language: str, consent: bool,
    cancel_event: threading.Event | None,
) -> dict:
    if not voice_clone.available():
        raise HTTPException(400, voice_errors.NO_KEY)
    if not consent:
        raise HTTPException(400, voice_errors.CONSENT_CLONE)
    suffix = Path(file.filename or "voice.webm").suffix.lower() or ".webm"
    if suffix not in UPLOAD_SUFFIXES:
        raise HTTPException(400, voice_errors.BAD_FORMAT)
    work = _work_dir()
    try:
        raw = work / f"upload{suffix}"
        size = 0
        with raw.open("wb") as handle:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > voice_clone.MAX_UPLOAD_BYTES:
                    raise HTTPException(413, voice_errors.TOO_LARGE)
                handle.write(chunk)
        sample = work / "sample.mp3"
        cleaned = False
        warning = ""
        warnings: list[str] = []
        source = raw
        try:
            import voice_extract

            # A home recording is usually clean: denoise and VAD trim only, so
            # the request stays fast. Separation runs only for a video upload
            # or when the denoise report still shows music in the gaps.
            separate = suffix in VIDEO_SUFFIXES
            clean_dir = work / "clean"
            _stop_if_cancelled(cancel_event)
            head = _upload_head(raw, work, cancel_event=cancel_event)
            report = voice_extract.extract_clean_voice(
                head, clean_dir,
                separate="best" if separate else False,
                denoise="auto",
                target_seconds=voice_clone.MAX_SAMPLE_SECONDS,
                cancel_event=cancel_event,
            )
            residual = (report.get("quality") or {}).get("music_noise_residual_db")
            if not separate and residual is not None and float(residual) > MUSIC_RESIDUAL_DB:
                report = voice_extract.extract_clean_voice(
                    head, work / "clean-music",
                    separate="best", denoise="auto",
                    target_seconds=voice_clone.MAX_SAMPLE_SECONDS,
                    use_cache=False,
                    cancel_event=cancel_event,
                )
            source = Path(str(report.get("path") or raw))
            warnings = list(report.get("warnings") or [])
            cleaned = True
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001 - cleaning must never block a clone
            _stop_if_cancelled(cancel_event)
            warning = f"Used the raw recording: cleaning failed ({_short_error(exc)})."
            source = raw
        _stop_if_cancelled(cancel_event)
        try:
            try:
                seconds = voice_clone.prepare_sample(source, sample)
            except voice_clone.CloneError:
                if not cleaned:
                    raise
                # The cleaned clip came out too short to clone; the raw upload
                # is still a valid sample.
                cleaned = False
                warning = "Used the raw recording: the cleaned clip was too short."
                seconds = voice_clone.prepare_sample(raw, sample)
            if _silent_reference(sample) and cleaned:
                # The cleaner can keep only a pause. The raw upload is the
                # fair second chance before refusing the clone.
                cleaned = False
                warning = "Used the raw recording: the cleaned clip had no speech."
                seconds = voice_clone.prepare_sample(raw, sample)
            _refuse_silent(sample)
            _stop_if_cancelled(cancel_event)
            record = voice_clone.create_clone(
                sample, name=name or "My voice", source="me", consent=consent,
                language=language, seconds=seconds,
            )
        except voice_clone.CloneError as exc:
            raise _fail(exc) from exc
        return {**record, "cleaned": cleaned, "warning": warning, "warnings": warnings}
    finally:
        shutil.rmtree(work, ignore_errors=True)


@router.post("/api/jobs/{job_id}/voices/candidates")
def start_candidate_search(
    job_id: str, request: Request, full: bool = False, start: float = 0.0,
    fast: bool = False,
) -> dict:
    """Start the clean voice candidate search for this job's source.

    By default it searches the first two minutes, which keeps a long video
    quick. ``full=1`` searches the whole source; ``start`` moves the window.
    ``fast=1`` skips the separation model and uses the ffmpeg denoise gate.
    """
    _guard(request)
    app = _app()
    job = app.load_job(job_id)
    source = Path(str((job.get("source") or {}).get("path") or ""))
    if not source.is_file():
        raise HTTPException(404, voice_errors.MISSING_SOURCE)
    if (job.get("source") or {}).get("has_audio") is False:
        # A silent source would decode to silence and run every model on it.
        raise HTTPException(400, NO_SOUND)
    existing = app.voice_pool.find_key(CANDIDATE_KIND, job_id)
    if existing is not None and existing.state in {
        job_queue.QueueState.QUEUED, job_queue.QueueState.RUNNING,
    }:
        return _candidate_state(job_id)
    out_dir = _candidate_dir(job_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("candidate-*.wav"):
        try:
            old.unlink()
        except OSError:
            pass
    try:
        (out_dir / "report.json").unlink()
    except OSError:
        pass
    with _CANDIDATE_LOCK:
        CANDIDATE_RESULTS.pop(job_id, None)
        CANDIDATE_ERRORS.pop(job_id, None)
    duration = float((job.get("source") or {}).get("duration") or 0.0)
    start = max(0.0, float(start or 0.0))
    seconds = 0.0 if full else SEARCH_WINDOW_SECONDS
    if seconds and (not duration or seconds >= duration):
        # A short video, or one whose length is unknown, is searched whole.
        seconds = 0.0
    cancel_event = threading.Event()
    _remember(CANDIDATE_CANCELS, job_id, cancel_event)
    _set_stage(job_id, "queued")
    app.voice_pool.submit_tracked(
        _run_candidate_search, job_id, cancel_event, out_dir,
        start=start, seconds=seconds, fast=bool(fast),
        kind=CANDIDATE_KIND, key=job_id,
    )
    return _candidate_state(job_id)


@router.get("/api/jobs/{job_id}/voices/candidates")
def candidate_search_state(job_id: str) -> dict:
    """State, progress stage and the finished candidates."""
    _app().load_job(job_id)
    return _candidate_state(job_id)


@router.delete("/api/jobs/{job_id}/voices/candidates")
def cancel_candidate_search(job_id: str, request: Request) -> dict:
    """Cancel the running search. A running extraction stops at its next check."""
    _guard(request)
    app = _app()
    app.load_job(job_id)
    cancel_event = CANDIDATE_CANCELS.get(job_id)
    if cancel_event is not None:
        cancel_event.set()
    app.voice_pool.cancel_key(CANDIDATE_KIND, job_id)
    _set_stage(job_id, "cancelled")
    return _candidate_state(job_id)


@router.get("/api/jobs/{job_id}/voices/candidates/{index}/audio")
def candidate_audio(job_id: str, index: int) -> FileResponse:
    """Serve one cleaned candidate WAV for the Edit picker."""
    _app().load_job(job_id)
    if index < 1 or index > CANDIDATE_COUNT:
        raise HTTPException(404, voice_errors.MISSING_CLIP)
    path = _candidate_file(job_id, index)
    if not path.is_file():
        raise HTTPException(404, voice_errors.MISSING_CLIP)
    return FileResponse(path, media_type="audio/wav", filename=path.name)


def _transcript_language(job_id: str) -> str:
    path = _app()._job_dir(job_id) / "transcript" / "transcript.json"
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError, AttributeError):
        return ""
    return str(data.get("language") or "")


@router.post("/api/jobs/{job_id}/voices/clone")
def clone_video_voice(job_id: str, body: VideoCloneBody, request: Request) -> dict:
    """Clone the speaker of the job's source, from a candidate or a range."""
    _guard(request)
    cancel_event = _task_event(body.task)
    try:
        return _clone_video_voice(job_id, body, cancel_event)
    finally:
        _task_done(body.task)


def _clone_video_voice(
    job_id: str, body: VideoCloneBody, cancel_event: threading.Event | None,
) -> dict:
    app = _app()
    job = app.load_job(job_id)
    if not voice_clone.available():
        raise HTTPException(400, voice_errors.NO_KEY)
    if not body.consent:
        raise HTTPException(
            400, voice_errors.CONSENT_VIDEO,
        )
    source = Path(str((job.get("source") or {}).get("path") or ""))
    if not source.is_file():
        raise HTTPException(404, voice_errors.MISSING_SOURCE)
    if (job.get("source") or {}).get("has_audio") is False:
        raise HTTPException(400, NO_SOUND)
    title = Path(str((job.get("source") or {}).get("name") or "video")).stem
    language = body.language or _transcript_language(job_id)

    if body.candidate is not None:
        if body.candidate < 1 or body.candidate > CANDIDATE_COUNT:
            raise HTTPException(400, voice_errors.PICK_CLIP)
        candidate = _candidate_file(job_id, body.candidate)
        if not candidate.is_file():
            raise HTTPException(404, voice_errors.FIND_CLIPS)
        work = _work_dir()
        try:
            sample = work / "sample.mp3"
            try:
                seconds = voice_clone.prepare_sample(candidate, sample)
                _refuse_silent(sample)
                _stop_if_cancelled(cancel_event)
                record = voice_clone.create_clone(
                    sample, name=body.name or f"{title} voice"[:64], source="video",
                    consent=body.consent, language=language, job_id=job_id,
                    seconds=seconds,
                )
            except voice_clone.CloneError as exc:
                raise _fail(exc) from exc
            return {
                **record,
                "candidate": body.candidate,
                "cleaned": True,
                "used_transcript": False,
                "warning": "",
            }
        finally:
            shutil.rmtree(work, ignore_errors=True)

    if body.start is not None and body.end is not None and body.end <= body.start:
        raise HTTPException(400, voice_errors.END_BEFORE_START)

    segments: list[dict] = []
    transcript = app._job_dir(job_id) / "transcript" / "transcript.json"
    if transcript.is_file():
        try:
            data = json.loads(transcript.read_text())
            segments = [item for item in data.get("segments", []) if isinstance(item, dict)]
            language = language or str(data.get("language") or "")
        except (OSError, json.JSONDecodeError, AttributeError):
            segments = []
    windows = voice_clone.speech_windows(segments, start=body.start, end=body.end)
    start = float(body.start or 0.0)
    duration = (
        float(body.end) - start if body.end is not None else voice_clone.MAX_SAMPLE_SECONDS
    )

    work = _work_dir()
    try:
        raw = work / "range.mp3"
        sample = work / "sample.mp3"
        try:
            raw_seconds = voice_clone.prepare_sample(
                source, raw, windows=windows, start=start, duration=duration,
            )
        except voice_clone.CloneError as exc:
            raise _fail(exc) from exc
        cleaned = False
        warning = ""
        seconds = raw_seconds
        try:
            import voice_extract

            _stop_if_cancelled(cancel_event)
            report = voice_extract.extract_clean_voice(
                raw, work / "clean",
                target_seconds=voice_clone.MAX_SAMPLE_SECONDS,
                cancel_event=cancel_event,
            )
            seconds = voice_clone.prepare_sample(Path(str(report["path"])), sample)
            cleaned = True
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001 - optional engines must never fail a clone
            _stop_if_cancelled(cancel_event)
            warning = (
                f"Used the raw cut: clean voice extraction failed ({_short_error(exc)})."
            )
            sample = raw
        _refuse_silent(sample)
        _stop_if_cancelled(cancel_event)
        try:
            record = voice_clone.create_clone(
                sample, name=body.name or f"{title} voice"[:64], source="video",
                consent=body.consent, language=language, job_id=job_id,
                seconds=seconds,
            )
        except voice_clone.CloneError as exc:
            raise _fail(exc) from exc
        return {
            **record,
            "cleaned": cleaned,
            "used_transcript": bool(windows),
            "warning": warning,
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)


@router.delete("/api/voices/tasks/{task_id}")
def cancel_voice_task(task_id: str, request: Request) -> dict:
    """Cancel a running clone request. It stops at its next check and saves nothing.

    A cancel that arrives before its request starts still counts: the switch
    is made here and the request finds it set.
    """
    _guard(request)
    event = _task_event(task_id)
    if event is not None:
        event.set()
    return {"cancelled": task_id}


@router.get("/api/voices/clones/{voice_id}")
def clone_status(voice_id: str) -> dict:
    record = voice_clone.get_clone(voice_id)
    if record is None:
        raise HTTPException(404, voice_errors.MISSING_VOICE)
    return record


@router.patch("/api/voices/clones/{voice_id}")
def rename_clone(voice_id: str, body: RenameBody, request: Request) -> dict:
    _guard(request)
    try:
        return voice_clone.rename(voice_id, body.name)
    except voice_clone.CloneError as exc:
        raise _fail(exc) from exc


@router.delete("/api/voices/clones/{voice_id}")
def delete_clone(voice_id: str, request: Request) -> dict:
    _guard(request)
    try:
        voice_clone.delete_clone(voice_id)
    except voice_clone.CloneError as exc:
        raise _fail(exc) from exc
    return {"deleted": voice_id}


@router.post("/api/voices/clones/{voice_id}/lock")
def lock_clone(voice_id: str, body: LockBody, request: Request) -> dict:
    """Freeze or release the reference. Unlocking warns that takes may differ."""
    _guard(request)
    try:
        record = voice_clone.lock(voice_id, bool(body.locked))
    except voice_clone.CloneError as exc:
        raise _fail(exc) from exc
    if not body.locked:
        record["unlock_warning"] = (
            "Unlocked. Later takes may sound different if the reference is replaced, "
            "so lock the voice again when it sounds right."
        )
    return record


@router.post("/api/voices/clones/{voice_id}/keep")
def keep_take_on_voice(voice_id: str, body: KeepBody, request: Request) -> dict:
    """Pin a take's script, rate and language on this voice, or clear them."""
    _guard(request)
    if not body.take_id:
        try:
            return voice_clone.set_keep(voice_id, None)
        except voice_clone.CloneError as exc:
            raise _fail(exc) from exc
    take = voice_takes.get_take(body.take_id)
    if take is None:
        raise HTTPException(404, voice_errors.MISSING_TAKE)
    if str(take.get("clone_voice") or "") != str(voice_id):
        raise HTTPException(
            400,
            voice_errors.fix(
                "That take was made in another voice",
                "Choose a take from this voice, then keep it",
            ),
        )
    settings = take.get("settings") or {}
    try:
        return voice_clone.set_keep(voice_id, {
            "take_id": body.take_id,
            "text": settings.get("text") or "",
            "rate": settings.get("rate") or 1.0,
            "language": settings.get("language") or "",
        })
    except voice_clone.CloneError as exc:
        raise _fail(exc) from exc


def _audio_message(exc: Exception) -> str:
    """A speech failure that always ends with a step the creator can take."""
    message = voice_errors.clean(
        str(exc), "The voice could not speak that line. Check the voice and the key in Setup, then try again.",
    )
    if voice_errors.has_next_step(message):
        return message
    return voice_errors.fix(message, "Check the voice and the key in Setup, then try again.")


def _cached_line(engine: str, voice: str, text: str, rate: float, language: str, cache) -> bool:
    """True when this exact line is already on this Mac, so nothing is sent."""
    import tts

    try:
        target = tts.line_cache_path(
            cache, engine, "", voice, text, rate, language, suffix=".wav",
        )
        return target.is_file() and target.stat().st_size > 512
    except (OSError, ValueError):
        return False


def _keep_preview(path, *, engine: str, voice: str, text: str, rate: float,
                  language: str, label: str, clone: str, cache) -> None:
    """History is a convenience: a failed copy never fails the preview."""
    try:
        voice_takes.record_preview(
            path, engine=engine, voice=voice, text=text, rate=rate,
            language=language, label=label, clone=clone,
            cached=_cached_line(engine, voice, text, rate, language, cache),
        )
    except Exception:  # noqa: BLE001 - never break playback for history
        pass


@router.get("/api/voices/clones/{voice_id}/persona")
def export_voice_file(voice_id: str, include_reference: bool = False) -> Response:
    """A .vcutvoice file: manifest, short preview, and the clip only if ticked."""
    record = voice_clone.get_clone(voice_id)
    if record is None:
        raise HTTPException(404, voice_errors.MISSING_VOICE)
    cache = voice_clone.settings_store.DATA / "cache" / "voice"
    try:
        preview = voice_persona.preview_path(record, cache)
        data = voice_persona.build(record, preview, bool(include_reference))
    except voice_persona.PersonaError as exc:
        raise HTTPException(exc.status_code, voice_errors.clean(str(exc))) from exc
    filename = voice_persona.filename(record)
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/api/voices/personas/import")
def import_voice_file(
    request: Request,
    file: UploadFile = File(...),
    consent: bool = Form(False),
    name: str = Form(""),
) -> dict:
    """Import a .vcutvoice file. Nothing existing is overwritten."""
    _guard(request)
    raw = bytearray()
    while chunk := file.file.read(1024 * 1024):
        raw.extend(chunk)
        if len(raw) > voice_persona.MAX_IMPORT_BYTES:
            raise HTTPException(413, "That voice file is over 60 MB. Import a smaller one, then try again.")
    try:
        return voice_persona.import_voice(bytes(raw), consent=bool(consent), name=name)
    except voice_persona.PersonaError as exc:
        raise HTTPException(exc.status_code, voice_errors.clean(str(exc))) from exc
    except voice_clone.CloneError as exc:
        raise _fail(exc) from exc


@router.post("/api/voices/clones/{voice_id}/sample")
def clone_sample(voice_id: str, body: SampleBody, request: Request) -> FileResponse:
    """Speak a short line in a cloned voice through OpenRouter HeyGen Turbo."""
    _guard(request)
    import audio

    record = voice_clone.get_clone(voice_id)
    if record is None:
        raise HTTPException(404, voice_errors.MISSING_VOICE)
    try:
        voice_clone.verify_lock(record)
    except voice_clone.CloneError as exc:
        raise _fail(exc) from exc
    text = " ".join((body.text or "").split())[:300] or "Hi, this is my cloned voice in VibeCut."
    rate = max(0.5, min(2.0, body.rate))
    locked = record.get("locked") if isinstance(record.get("locked"), dict) else {}
    language = str(locked.get("language") or record.get("language") or "")
    cache = voice_clone.settings_store.DATA / "cache" / "voice"
    cache.mkdir(parents=True, exist_ok=True)
    try:
        path = audio.voice_sample(
            "heygen", voice_id, text, cache, rate=rate, language=language,
        )
    except audio.AudioError as exc:
        raise HTTPException(400, _audio_message(exc)) from exc
    _keep_preview(
        path, engine="heygen", voice=voice_id, text=text, rate=rate,
        language=language, label=str(record.get("name") or "Cloned voice"),
        clone=voice_id, cache=cache,
    )
    return FileResponse(path, media_type="audio/wav", filename="cloned-voice.wav")


# ---------------------------------------------------------------- Voice Room


@router.get("/api/voices/readiness")
def voice_readiness_check() -> dict:
    """OpenRouter key, clone engine and local Whisper, each Ready or Failed."""
    return voice_readiness.checklist()


@router.get("/api/voices/catalog")
def voice_catalog() -> dict:
    """Every voice engine and the voices it can speak on this machine."""
    import audio
    import tts

    status = tts.voice_engine_status()
    engines = []
    for engine in tts.SYNTHESIZERS:
        info = status.get(engine) or {}
        available = bool(info.get("available"))
        voices: list[dict] = []
        error = ""
        if available:
            try:
                voices = [
                    voice for voice in tts.list_voices(engine)
                    if isinstance(voice, dict) and voice.get("id") is not None
                ]
            except audio.AudioError as exc:
                error = str(exc)
        engines.append({
            "id": engine,
            "label": tts.engine_label(engine),
            "available": available,
            "local": engine in tts.LOCAL_ENGINES,
            "install": str(info.get("install") or ""),
            "clone": bool(info.get("clone")),
            "voices": voices,
            "error": error,
        })
    return {
        "engines": engines,
        "clones": voice_clone.list_clones(),
        "clone_available": voice_clone.available(),
    }


@router.post("/api/voices/sample")
def any_voice_sample(body: AnyVoiceSampleBody, request: Request) -> FileResponse:
    """Speak a short line in any voice on this machine, no video needed."""
    _guard(request)
    import audio
    import tts

    engine = body.engine.strip().lower()
    if engine not in tts.SYNTHESIZERS:
        raise HTTPException(400, voice_errors.NO_ENGINE)
    text = " ".join((body.text or "").split())[:300] or "This is how this voice sounds in VibeCut."
    record = voice_clone.get_clone(body.voice) if engine == "heygen" else None
    rate = max(0.5, min(2.0, body.rate))
    language = str((record or {}).get("language") or "")
    cache = voice_clone.settings_store.DATA / "cache" / "voice"
    cache.mkdir(parents=True, exist_ok=True)
    try:
        path = audio.voice_sample(
            engine, body.voice, text, cache, rate=rate, language=language,
        )
    except audio.AudioError as exc:
        raise HTTPException(400, _audio_message(exc)) from exc
    _keep_preview(
        path, engine=engine, voice=body.voice, text=text, rate=rate,
        language=language,
        label=str((record or {}).get("name") or body.voice or "Stock voice"),
        clone=body.voice if record else "", cache=cache,
    )
    return FileResponse(path, media_type="audio/wav", filename="voice-sample.wav")


# ------------------------------------------------------------------ takes


def _take_fail(exc: voice_takes.TakeError) -> HTTPException:
    return HTTPException(exc.status_code, voice_errors.clean(str(exc)))


@router.get("/api/voices/takes")
def list_takes() -> dict:
    """Every preview and voiceover, starred first, then newest."""
    return {
        "takes": voice_takes.list_takes(),
        "cleanup": voice_takes.cleanup_plan(),
        "limits": {
            "cleanup_days": voice_takes.CLEANUP_DAYS,
            "max_script_chars": voice_takes.MAX_SCRIPT_CHARS,
            "self_check_threshold": voice_takes.SELF_CHECK_THRESHOLD,
        },
    }


@router.get("/api/voices/takes/cleanup")
def take_cleanup_plan(days: int = voice_takes.CLEANUP_DAYS) -> dict:
    """What a cleanup would remove. Nothing is deleted."""
    return voice_takes.cleanup_plan(days=max(1, min(3650, int(days))))


@router.post("/api/voices/takes/cleanup")
def take_cleanup(body: TakeCleanupBody, request: Request) -> dict:
    """Remove old unstarred takes, only after the page confirms."""
    _guard(request)
    days = voice_takes.CLEANUP_DAYS if body.days is None else max(1, min(3650, int(body.days)))
    return voice_takes.cleanup(confirm=bool(body.confirm), days=days)


@router.get("/api/voices/takes/{take_id}")
def one_take(take_id: str) -> dict:
    take = voice_takes.get_take(take_id)
    if take is None:
        raise HTTPException(404, voice_errors.MISSING_TAKE)
    return take


@router.patch("/api/voices/takes/{take_id}")
def star_take(take_id: str, body: TakeStarBody, request: Request) -> dict:
    _guard(request)
    try:
        return voice_takes.star(take_id, body.starred)
    except voice_takes.TakeError as exc:
        raise _take_fail(exc) from exc


@router.delete("/api/voices/takes/{take_id}")
def delete_take(take_id: str, request: Request) -> dict:
    _guard(request)
    try:
        voice_takes.delete(take_id)
    except voice_takes.TakeError as exc:
        raise _take_fail(exc) from exc
    return {"deleted": take_id}


@router.get("/api/voices/takes/{take_id}/audio")
def take_audio(take_id: str) -> FileResponse:
    try:
        path = voice_takes.audio_path(take_id)
    except voice_takes.TakeError as exc:
        raise _take_fail(exc) from exc
    return FileResponse(path, media_type="audio/wav", filename=f"{take_id}.wav")


@router.post("/api/voices/takes/{take_id}/save-voice")
def save_take_as_voice(take_id: str, body: TakeSaveBody, request: Request) -> dict:
    """Make a new clone from the reference behind a take."""
    _guard(request)
    try:
        return voice_takes.save_as_voice(take_id, body.name)
    except voice_takes.TakeError as exc:
        raise _take_fail(exc) from exc
    except voice_clone.CloneError as exc:
        raise _fail(exc) from exc


@router.post("/api/voices/voiceovers")
def make_voiceover(body: VoiceoverBody, request: Request) -> dict:
    """Speak a whole script in sentence lines and keep it as one take."""
    _guard(request)
    import tts

    engine = str(body.engine or "").strip().lower()
    if engine not in tts.SYNTHESIZERS:
        raise HTTPException(
            400,
            voice_errors.NO_ENGINE,
        )
    clone = body.clone or (body.voice if voice_clone.is_clone(body.voice) else "")
    language = body.language
    if clone:
        record = voice_clone.get_clone(clone)
        if record is None:
            raise HTTPException(404, voice_errors.MISSING_VOICE)
        try:
            voice_clone.verify_lock(record)
        except voice_clone.CloneError as exc:
            raise _fail(exc) from exc
        locked = record.get("locked") if isinstance(record.get("locked"), dict) else {}
        language = (
            str(locked.get("language") or "")
            or language
            or str(record.get("language") or "")
        )
    cancel_event = _task_event(body.task)
    task = str(body.task or "")
    voice_takes.set_progress(task, "running", "Preparing the lines", 0.0)
    try:
        result = voice_takes.create_voiceover(
            text=body.text,
            engine=engine,
            voice=body.voice,
            rate=max(0.5, min(2.0, body.rate)),
            language=language,
            label=body.label or " ".join(str(body.text or "").split())[:48],
            clone=clone,
            selfcheck=bool(body.selfcheck),
            cancel_event=cancel_event,
            progress=lambda fraction, stage: voice_takes.set_progress(
                task, "running", stage, fraction,
            ),
        )
        voice_takes.set_progress(task, "done", "Done", 1.0)
        return result
    except voice_takes.TakeError as exc:
        state = "cancelled" if exc.status_code == 409 and "Cancel" in str(exc) else "failed"
        voice_takes.set_progress(task, state, str(exc), 0.0)
        raise _take_fail(exc) from exc
    finally:
        _task_done(body.task)


@router.get("/api/voices/tasks/{task_id}")
def voice_task_progress(task_id: str) -> dict:
    """What a running voiceover is doing. Read-only; the DELETE stops it."""
    return voice_takes.progress(task_id)
