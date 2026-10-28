"""HTTP surface for cloned voices.

* Setup, **My voice**: record or upload the creator's own voice.
* Edit, **Clone the video voice**: clone the speaker of the open video.

Both end in the same store (`voice_clone`): a reference sample kept on this
Mac that OpenRouter's HeyGen Voice Turbo clones on every speech request. A
clone shows up as a HeyGen Voice Turbo voice in every voice picker. Writes need
the same-origin check Setup uses, and every clone needs an explicit consent
flag.
"""

from __future__ import annotations

import json
import shutil
import threading
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

import job_queue
import voice_clone

router = APIRouter()

UPLOAD_SUFFIXES = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".webm", ".flac", ".mp4", ".mov"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".mkv", ".avi"}
CANDIDATE_KIND = "voice-candidates"
CANDIDATE_DIR = "voice-candidates"
CANDIDATE_COUNT = 5
#: Quiet-gap band energy this close to the speech band means music is present.
MUSIC_RESIDUAL_DB = -24.0
CANDIDATE_CANCELS: dict[str, threading.Event] = {}
CANDIDATE_STAGES: dict[str, str] = {}
CANDIDATE_RESULTS: dict[str, dict] = {}
CANDIDATE_ERRORS: dict[str, str] = {}


class VideoCloneBody(BaseModel):
    name: str = ""
    language: str = ""
    consent: bool = False
    start: float | None = None
    end: float | None = None
    candidate: int | None = None

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


def _candidate_dir(job_id: str) -> Path:
    return _app()._job_dir(job_id) / CANDIDATE_DIR


def _candidate_file(job_id: str, index: int) -> Path:
    return _candidate_dir(job_id) / f"candidate-{index:02d}.wav"


def _short_error(exc: Exception) -> str:
    text = str(exc).splitlines()[0].strip() if str(exc) else exc.__class__.__name__
    return text[:180]


def _read_candidate_report(job_id: str) -> dict:
    path = _candidate_dir(job_id) / "report.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, HTTPException):
        return {}
    return data if isinstance(data, dict) else {}


def _set_stage(job_id: str, stage: str) -> None:
    CANDIDATE_STAGES[job_id] = str(stage or "")


def _run_candidate_search(job_id: str, cancel_event: threading.Event, out_dir: Path) -> dict:
    """Background worker: clean the source and keep 3-5 candidate WAVs."""
    import voice_extract

    app = _app()
    job = app.load_job(job_id)
    source = Path(str((job.get("source") or {}).get("path") or ""))
    if not source.is_file():
        raise voice_clone.CloneError("The source video for this job is missing.", 404)
    _set_stage(job_id, "preparing")
    try:
        report = voice_extract.find_voice_candidates(
            source, out_dir,
            cancel_event=cancel_event,
            on_stage=lambda stage: _set_stage(job_id, stage),
        )
        report = dict(report)
        report["job_id"] = job_id
        report.setdefault("candidates", [])
        CANDIDATE_RESULTS[job_id] = report
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
            CANDIDATE_ERRORS[job_id] = _short_error(exc)
            _set_stage(job_id, "failed")
        raise


def _public_candidate(job_id: str, item: dict, models: dict) -> dict:
    window = item.get("window") or [item.get("start") or 0.0, item.get("end") or 0.0]
    try:
        start, end = float(window[0]), float(window[1])
    except (TypeError, ValueError, IndexError):
        start, end = 0.0, 0.0
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
    task = app.analysis_pool.find_key(CANDIDATE_KIND, job_id)
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
    candidates = []
    if state == "done":
        candidates = [
            _public_candidate(job_id, item, models)
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
        raise HTTPException(400, "Add an OpenRouter key in Setup to clone a voice.")
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
            report = voice_extract.extract_clean_voice(
                raw, clean_dir,
                separate="best" if separate else False,
                denoise="auto",
                target_seconds=voice_clone.MAX_SAMPLE_SECONDS,
            )
            residual = (report.get("quality") or {}).get("music_noise_residual_db")
            if not separate and residual is not None and float(residual) > MUSIC_RESIDUAL_DB:
                report = voice_extract.extract_clean_voice(
                    raw, work / "clean-music",
                    separate="best", denoise="auto",
                    target_seconds=voice_clone.MAX_SAMPLE_SECONDS,
                    use_cache=False,
                )
            source = Path(str(report.get("path") or raw))
            warnings = list(report.get("warnings") or [])
            cleaned = True
        except Exception as exc:  # noqa: BLE001 - cleaning must never block a clone
            warning = f"Used the raw recording: cleaning failed ({_short_error(exc)})."
            source = raw
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
def start_candidate_search(job_id: str, request: Request) -> dict:
    """Start the clean voice candidate search for this job's source."""
    _guard(request)
    app = _app()
    job = app.load_job(job_id)
    source = Path(str((job.get("source") or {}).get("path") or ""))
    if not source.is_file():
        raise HTTPException(404, "The source video for this job is missing.")
    existing = app.analysis_pool.find_key(CANDIDATE_KIND, job_id)
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
    CANDIDATE_RESULTS.pop(job_id, None)
    CANDIDATE_ERRORS.pop(job_id, None)
    cancel_event = threading.Event()
    CANDIDATE_CANCELS[job_id] = cancel_event
    _set_stage(job_id, "queued")
    app.analysis_pool.submit_tracked(
        _run_candidate_search, job_id, cancel_event, out_dir,
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
    app.analysis_pool.cancel_key(CANDIDATE_KIND, job_id)
    _set_stage(job_id, "cancelled")
    return _candidate_state(job_id)


@router.get("/api/jobs/{job_id}/voices/candidates/{index}/audio")
def candidate_audio(job_id: str, index: int) -> FileResponse:
    """Serve one cleaned candidate WAV for the Edit picker."""
    _app().load_job(job_id)
    if index < 1 or index > CANDIDATE_COUNT:
        raise HTTPException(404, "No such voice candidate.")
    path = _candidate_file(job_id, index)
    if not path.is_file():
        raise HTTPException(404, "No such voice candidate.")
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
    app = _app()
    job = app.load_job(job_id)
    if not voice_clone.available():
        raise HTTPException(400, "Add an OpenRouter key in Setup to clone a voice.")
    if not body.consent:
        raise HTTPException(
            400, "Confirm you own this voice or have the speaker's permission to clone it.",
        )
    source = Path(str((job.get("source") or {}).get("path") or ""))
    if not source.is_file():
        raise HTTPException(404, "The source video for this job is missing.")
    title = Path(str((job.get("source") or {}).get("name") or "video")).stem
    language = body.language or _transcript_language(job_id)

    if body.candidate is not None:
        if body.candidate < 1 or body.candidate > CANDIDATE_COUNT:
            raise HTTPException(400, "Pick one of the voice clips that were found.")
        candidate = _candidate_file(job_id, body.candidate)
        if not candidate.is_file():
            raise HTTPException(404, "Find the best voice clips before cloning one.")
        work = _work_dir()
        try:
            sample = work / "sample.mp3"
            try:
                seconds = voice_clone.prepare_sample(candidate, sample)
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
        raise HTTPException(400, "The end must come after the start.")

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

            report = voice_extract.extract_clean_voice(
                raw, work / "clean",
                target_seconds=voice_clone.MAX_SAMPLE_SECONDS,
            )
            seconds = voice_clone.prepare_sample(Path(str(report["path"])), sample)
            cleaned = True
        except Exception as exc:  # noqa: BLE001 - optional engines must never fail a clone
            warning = (
                f"Used the raw cut: clean voice extraction failed ({_short_error(exc)})."
            )
            sample = raw
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


@router.get("/api/voices/clones/{voice_id}")
def clone_status(voice_id: str) -> dict:
    record = voice_clone.get_clone(voice_id)
    if record is None:
        raise HTTPException(404, "No such cloned voice.")
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


@router.post("/api/voices/clones/{voice_id}/sample")
def clone_sample(voice_id: str, body: SampleBody) -> FileResponse:
    """Speak a short line in a cloned voice through OpenRouter HeyGen Turbo."""
    import audio

    record = voice_clone.get_clone(voice_id)
    if record is None:
        raise HTTPException(404, "No such cloned voice.")
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


# ---------------------------------------------------------------- Voice Room


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
def any_voice_sample(body: AnyVoiceSampleBody) -> FileResponse:
    """Speak a short line in any voice on this machine, no video needed."""
    import audio
    import tts

    engine = body.engine.strip().lower()
    if engine not in tts.SYNTHESIZERS:
        raise HTTPException(400, "Unknown voice engine.")
    text = " ".join((body.text or "").split())[:300] or "This is how this voice sounds in VibeCut."
    record = voice_clone.get_clone(body.voice) if engine == "heygen" else None
    cache = voice_clone.settings_store.DATA / "cache" / "voice"
    cache.mkdir(parents=True, exist_ok=True)
    try:
        path = audio.voice_sample(
            engine, body.voice, text, cache, rate=max(0.5, min(2.0, body.rate)),
            language=str((record or {}).get("language") or ""),
        )
    except audio.AudioError as exc:
        raise HTTPException(400, str(exc)) from exc
    return FileResponse(path, media_type="audio/wav", filename="voice-sample.wav")
