"""HTTP surface for cloned voices.

* Setup, **My voice**: record or upload the creator's own voice.
* Edit, **Clone the video voice**: clone the speaker of the open video.

Both end in the same store (`voice_clone`), and an active clone shows up as a
HeyGen Voice Turbo voice in every voice picker. Writes need the same-origin
check Setup uses, and every clone needs an explicit consent flag.
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

import voice_clone

router = APIRouter()

UPLOAD_SUFFIXES = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".webm", ".flac", ".mp4", ".mov"}


class VideoCloneBody(BaseModel):
    name: str = ""
    language: str = ""
    consent: bool = False
    start: float | None = None
    end: float | None = None

    model_config = {"extra": "forbid"}


class RenameBody(BaseModel):
    name: str

    model_config = {"extra": "forbid"}


class SampleBody(BaseModel):
    text: str = ""
    rate: float = 1.0

    model_config = {"extra": "forbid"}


def _app():
    import app

    return app


def _guard(request: Request) -> None:
    if not _app()._setup_origin_ok(request):
        raise HTTPException(403, "Cross-site voice writes are blocked.")


def _fail(exc: voice_clone.CloneError) -> HTTPException:
    return HTTPException(exc.status_code, str(exc))


def _work_dir() -> Path:
    path = voice_clone.settings_store.DATA / "cache" / "voice-clone" / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


def _finish(record: dict) -> dict:
    """Give HeyGen a short moment so most clones come back ACTIVE."""
    try:
        return voice_clone.wait_active(record["voice_id"], timeout=30)
    except voice_clone.CloneError:
        return record


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


@router.post("/api/voices/clones")
def clone_my_voice(
    request: Request,
    file: UploadFile = File(...),
    name: str = Form(""),
    language: str = Form(""),
    consent: bool = Form(False),
) -> dict:
    """Clone the creator's own voice from a recording or an uploaded file."""
    _guard(request)
    if not voice_clone.available():
        raise HTTPException(400, "Add a HeyGen API key in Setup to clone a voice.")
    if not consent:
        raise HTTPException(400, "Confirm this is your own voice before cloning it.")
    suffix = Path(file.filename or "voice.webm").suffix.lower() or ".webm"
    if suffix not in UPLOAD_SUFFIXES:
        raise HTTPException(400, "Use a WAV, MP3, M4A, OGG, WebM or FLAC recording.")
    work = _work_dir()
    try:
        raw = work / f"upload{suffix}"
        size = 0
        with raw.open("wb") as handle:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > voice_clone.MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "That recording is over 100 MB.")
                handle.write(chunk)
        sample = work / "sample.wav"
        try:
            seconds = voice_clone.prepare_sample(raw, sample)
            record = voice_clone.create_clone(
                sample, name=name or "My voice", source="me", consent=consent,
                language=language, seconds=seconds,
            )
        except voice_clone.CloneError as exc:
            raise _fail(exc) from exc
        return _finish(record)
    finally:
        shutil.rmtree(work, ignore_errors=True)


@router.post("/api/jobs/{job_id}/voices/clone")
def clone_video_voice(job_id: str, body: VideoCloneBody, request: Request) -> dict:
    """Clone the speaker of the job's source video from its speech segments."""
    _guard(request)
    app = _app()
    job = app.load_job(job_id)
    if not voice_clone.available():
        raise HTTPException(400, "Add a HeyGen API key in Setup to clone a voice.")
    if not body.consent:
        raise HTTPException(
            400, "Confirm you own this voice or have the speaker's permission to clone it.",
        )
    source = Path(str((job.get("source") or {}).get("path") or ""))
    if not source.is_file():
        raise HTTPException(404, "The source video for this job is missing.")
    if body.start is not None and body.end is not None and body.end <= body.start:
        raise HTTPException(400, "The end must come after the start.")

    segments: list[dict] = []
    language = body.language
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
        sample = work / "sample.wav"
        title = Path(str((job.get("source") or {}).get("name") or "video")).stem
        try:
            seconds = voice_clone.prepare_sample(
                source, sample, windows=windows, start=start, duration=duration,
            )
            record = voice_clone.create_clone(
                sample, name=body.name or f"{title} voice"[:64], source="video",
                consent=body.consent, language=language, job_id=job_id,
                seconds=seconds,
            )
        except voice_clone.CloneError as exc:
            raise _fail(exc) from exc
        result = _finish(record)
        result["used_transcript"] = bool(windows)
        return result
    finally:
        shutil.rmtree(work, ignore_errors=True)


@router.get("/api/voices/clones/{voice_id}")
def clone_status(voice_id: str) -> dict:
    if not voice_clone.is_voice_id(voice_id):
        raise HTTPException(404, "No such cloned voice.")
    try:
        return voice_clone.refresh(voice_id)
    except voice_clone.CloneError as exc:
        raise _fail(exc) from exc


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


@router.post("/api/voices/clones/{voice_id}/sample")
def clone_sample(voice_id: str, body: SampleBody) -> FileResponse:
    """Speak a short line in a cloned voice through the normal HeyGen route."""
    import audio

    record = voice_clone.get_clone(voice_id)
    if record is None:
        raise HTTPException(404, "No such cloned voice.")
    if record.get("status") != "ACTIVE":
        raise HTTPException(409, "This voice is not ready yet.")
    text = " ".join((body.text or "").split())[:300] or "Hi, this is my cloned voice in VibeCut."
    cache = voice_clone.settings_store.DATA / "cache" / "voice"
    cache.mkdir(parents=True, exist_ok=True)
    try:
        path = audio.voice_sample(
            "heygen", voice_id, text, cache, rate=body.rate,
            language=str(record.get("language") or ""),
        )
    except audio.AudioError as exc:
        raise HTTPException(400, str(exc)) from exc
    return FileResponse(path, media_type="audio/wav", filename="cloned-voice.wav")
