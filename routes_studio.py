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


class RevealPathBody(BaseModel):
    path: str = ""

    model_config = {"extra": "forbid"}


class AddStoryBody(BaseModel):
    scene_ids: list[int] = []
    title: str = ""

    model_config = {"extra": "forbid"}


class AutoCleanBody(BaseModel):
    include_handles: bool = False

    model_config = {"extra": "forbid"}


def _edit_story(job: dict, edit: dict) -> dict | None:
    """Resolve an Edit's story inside this job, or ``None``."""
    reference = edit.get("story_ref") or {}
    set_id = str(reference.get("set_id") or "")
    story_id = str(reference.get("story_id") or "")
    raw = job.get("clip_sets")
    records = raw.values() if isinstance(raw, dict) else raw or []
    record = next(
        (
            item for item in records
            if isinstance(item, dict) and str(item.get("id") or "") == set_id
        ),
        None,
    )
    if record is None:
        return None
    return next(
        (
            item for item in record.get("stories") or []
            if isinstance(item, dict) and str(item.get("id") or "") == story_id
        ),
        None,
    )


@router.post("/api/path/reveal")
def reveal_path(body: RevealPathBody, request: Request) -> dict:
    """Show a video path in Finder before it is imported."""
    import app

    if not app._setup_origin_ok(request):
        raise HTTPException(403, "Cross-site writes are blocked.")
    path = Path(body.path).expanduser()
    if not path.is_absolute() or not path.is_file():
        raise HTTPException(404, "That file is not on this Mac.")
    if app.sys.platform != "darwin":
        raise HTTPException(501, "Reveal in Finder works on a Mac only.")
    try:
        app.subprocess.Popen(
            ["open", "-R", str(path)],
            stdout=app.subprocess.DEVNULL, stderr=app.subprocess.DEVNULL,
        )
    except OSError as exc:
        raise HTTPException(500, "Could not open Finder.") from exc
    return {"revealed": True, "path": str(path)}


@router.post("/api/jobs/{job_id}/clip-sets/{set_id}/stories")
def add_story(job_id: str, set_id: str, body: AddStoryBody) -> dict:
    """Append one custom moment made from selected scenes."""
    import app
    import clipset

    job = app._clipset_job(job_id)
    record = app._clip_set_in_job(job, set_id)
    app._clip_set_source_state(job, record)
    sentences, scenes, transcript = app._clipset_pool(job, record)
    known = {int(scene["id"]) for scene in scenes if scene.get("id") is not None}
    selected = sorted({int(value) for value in body.scene_ids if int(value) in known})
    if not selected:
        raise HTTPException(400, "Pick at least one scene.")
    banned = sorted(known - set(selected))
    chosen = [scene for scene in scenes if int(scene["id"]) in set(selected)]
    span = sum(
        max(0.0, float(scene.get("end") or 0.0) - float(scene.get("start") or 0.0))
        for scene in chosen
    )
    try:
        document = clipset.build_clipset(
            scenes,
            transcript,
            float((job.get("source") or {}).get("duration") or 0.0),
            count=3,
            min_s=clipset.LENGTH_FLOOR_S,
            max_s=min(clipset.LENGTH_CEIL_S, max(clipset.LENGTH_FLOOR_S, span)),
            locks=selected,
            ban_scenes=banned,
            order="source",
        )
    except clipset.ClipSetError as exc:
        raise HTTPException(400, str(exc)) from exc
    stories = list(document.get("stories") or [])
    if not stories:
        raise HTTPException(409, "Those scenes do not make a 15–180 s story.")
    story = stories[0]
    for existing in record.get("stories") or []:
        left, right = float(existing.get("start") or 0), float(existing.get("end") or 0)
        start, end = float(story.get("start") or 0), float(story.get("end") or 0)
        if min(right, end) - max(left, start) > 0.01:
            raise HTTPException(409, "That story already exists, or overlaps one already in this set.")
    title = str(body.title or "").strip()
    if title:
        story["title"] = clipset._clean(title)[:120]
    stories_out = list(record.get("stories") or []) + [story]
    stories_out.sort(key=lambda item: (float(item.get("start") or 0), str(item.get("id") or "")))
    record["stories"] = stories_out
    record["available"] = len(stories_out)
    record["complete"] = len(stories_out) >= int(record.get("requested") or 0)
    record["note"] = None
    record["updated"] = app.time.time()
    app._store_clip_set(job_id, record)
    return {"clip_set": record, "story": story}


@router.delete("/api/jobs/{job_id}/clip-sets/{set_id}")
def delete_clip_set(job_id: str, set_id: str, request: Request) -> dict:
    """Remove one Studio moment set. Edits and renders keep their own files."""
    import app

    if not app._setup_origin_ok(request):
        raise HTTPException(403, "Cross-site writes are blocked.")
    job = app.load_job(job_id)
    records = app._clip_set_records(job)
    if not any(str(record.get("id")) == set_id for record in records):
        raise HTTPException(404, "Clip set not found.")

    def mutate(current: dict) -> None:
        value = current.get("clip_sets")
        if isinstance(value, list):
            current["clip_sets"] = [
                record for record in value
                if not (isinstance(record, dict) and str(record.get("id")) == set_id)
            ]
        else:
            current["clip_sets"] = {
                key: record for key, record in (value or {}).items()
                if str(key) != set_id
            }

    app.update_job(job_id, mutate)
    return {"ok": True, "id": set_id}


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


@router.post("/api/jobs/{job_id}/edits/{edit_id}/auto-clean")
def auto_clean(
    job_id: str,
    edit_id: str,
    request: Request,
    body: AutoCleanBody | None = None,
) -> dict:
    """Build Clean layers from the latest Check report for one Edit.

    The Edit is never written: the response carries only the layers the
    frontend has not applied yet, and autosave saves the merged Edit. The
    rights gate, watermark refusal and screen-text refusal stay in
    :func:`cleanup.tracklet_clean_layers`, never in this route.
    """
    import app
    import cleanup
    import detect
    import edits

    if not app._setup_origin_ok(request):
        raise HTTPException(403, "Cross-site writes are blocked.")
    job = app.load_job(job_id)
    job_dir = app._job_dir(job_id)
    try:
        edit = edits.load_edit(job_dir, edit_id)
    except edits.EditError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    if edit is None:
        raise HTTPException(404, "Edit not found.")
    if _edit_story(job, edit) is None:
        raise HTTPException(404, "The story for this Edit is not in this job.")
    report = detect.load_report(job_dir)
    if report is None:
        raise HTTPException(404, "Run Scan footage first.")
    tracklets = [
        item for item in report.get("tracklets") or [] if isinstance(item, dict)
    ]
    built = cleanup.tracklet_clean_layers(
        tracklets,
        job=job,
        settings=app.settings_store.load_settings(),
        include_handles=bool(body.include_handles) if body else False,
    )
    merged = cleanup.merge_auto_clean_layers(
        edit.get("clean") or [], built.get("layers") or [],
    )
    skipped = [
        {
            "tracklet_id": item.get("tracklet_id"),
            "kind": item.get("kind"),
            "reason": item.get("reason"),
        }
        for item in built.get("refused") or []
    ]
    skipped.extend(merged["skipped"])
    warnings = [str(item) for item in built.get("warnings") or []]
    if not tracklets:
        warnings.insert(
            0,
            "Scan footage found no usable text overlays to clean. "
            "Run Scan footage again if the video changed.",
        )
    return {
        "layers": merged["layers"],
        "added": len(merged["layers"]),
        "skipped": skipped,
        "warnings": warnings,
    }
