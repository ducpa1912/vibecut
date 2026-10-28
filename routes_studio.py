"""Routes the Studio view adds from now on (lane: ``studio``).

New Studio endpoints go here, not into ``app.py``, so the lanes stop
editing the same file (see ``docs/branching.md``). Existing Studio routes
stay where they are. Use ``import app`` inside a handler when it needs app
helpers; importing at module level would be circular.
"""

from __future__ import annotations

import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()


class SpeechRetryBody(BaseModel):
    language: str = ""

    model_config = {"extra": "forbid"}


@router.post("/api/jobs/{job_id}/transcribe")
def retry_speech(job_id: str, request: Request, body: SpeechRetryBody | None = None):
    """Read the speech of an analysed video again, without re-importing it.

    The one speech-only retry: it runs ``pipeline.retry_speech`` on the voice
    queue (task kind ``transcribe``), so frames, crops and plans stay as they
    are. Poll and cancel it through ``/api/jobs/{id}/voice-tasks/transcribe``.
    Stories are built from speech; a video read before a transcription route
    was ready has none, and the next Find stories uses what this attaches.
    """
    import app

    if not app._setup_origin_ok(request):
        raise HTTPException(403, "Cross-site writes are blocked.")
    job = app.load_job(job_id)
    source = job.get("source") or {}
    if job.get("status") != "ready" or not (job.get("analysis") or {}).get("scenes"):
        raise HTTPException(409, "Wait for the video to finish reading first.")
    if not source.get("has_audio"):
        raise HTTPException(
            400,
            "This video has no sound track, so there is no speech to read. "
            "Download or export it again with audio.",
        )
    if not Path(str(source.get("path") or "")).is_file():
        raise HTTPException(404, "The source video for this job is missing.")
    settings = app.settings_store.load_settings()
    stt_cfg = app.workflow_config.effective(settings.get("workflows"), "stt")
    stt = app.pipeline.stt
    if not any(
        stt._engine_ready(route["provider"], route["model"])
        for route in stt.resolve_routes(list(stt_cfg.get("routes") or []))
    ):
        raise HTTPException(
            400,
            "No transcription engine is ready on this machine. Add an OpenRouter "
            "key in Setup (or a Groq or Deepgram key).",
        )
    language = str((body.language if body else "") or "").strip().lower()
    options = {"speech_language": language, "speech_language_explicit": language} if language else {}
    job_dir = app._job_dir(job_id)

    def work(cancel: threading.Event) -> dict:
        result = app.pipeline.retry_speech(job, job_dir, options)
        transcript = result.get("transcript")
        if transcript is None:
            if result.get("reason") and not result.get("engine", {}).get("stt_attempted"):
                raise HTTPException(400, result["reason"])
            raise HTTPException(502, "Transcription failed on every route. Check the key in Setup and try again.")

        def apply(record: dict) -> None:
            analysis = record.setdefault("analysis", {})
            analysis["scenes"] = result["scenes"]
            analysis["transcript"] = transcript
            analysis.setdefault("engine", {}).update(result["engine"])
            record.setdefault("options", {})["transcribe"] = True

        if cancel.is_set():
            raise HTTPException(409, "Cancelled. The video was not updated.")
        app.update_job(job_id, apply)
        return {
            "segments": transcript["segments"],
            "language": transcript["language"],
            "provider": result["engine"].get("transcript_provider"),
            "no_speech": transcript["no_speech"],
        }

    return app._voice_task("transcribe", job_id, work, reuse=True)
