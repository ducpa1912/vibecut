"""Routes the Studio view adds from now on (lane: ``studio``).

New Studio endpoints go here, not into ``app.py``, so the lanes stop
editing the same file (see ``docs/branching.md``). Existing Studio routes
stay where they are. Use ``import app`` inside a handler when it needs app
helpers; importing at module level would be circular.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
import logging

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict

router = APIRouter()
LOGGER = logging.getLogger("vibecut.studio")


def _fill_refused(message: str, *, job_id: str, at: float) -> HTTPException:
    """A refused fill test, with its reason in the server log as well."""
    LOGGER.warning("Fill test refused for %s at %.2f s: %s", job_id, at, message)
    return HTTPException(422, message)


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
    # None keeps the old "all allowed regions" behaviour. An explicit list is
    # the found-text list's ticks, so Remove all only touches what was ticked.
    tracklet_ids: list[str] | None = None
    # Clean has two methods. auto picks AI fill when an engine is ready, else
    # Blur; ai and blur are explicit.
    method: str = "auto"
    fill_method: str = "sttn"

    model_config = ConfigDict(extra="forbid")


class FillPreviewBody(BaseModel):
    t: float = 0.0
    method: str = "lama"
    # Draft Clean layers for a preview before saving. None means the saved Edit.
    clean: list[dict] | None = None
    # Only these Clean layer ids take part in the comparison.
    layer_ids: list[str] | None = None

    model_config = ConfigDict(extra="forbid")


class TranslateTranscriptBody(BaseModel):
    target: str = ""
    source: str = ""
    provider: str = "auto"
    force: bool = False

    model_config = ConfigDict(extra="forbid")


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


def _apply_clean_method(
    layers: list[dict],
    method: str,
    fill_method: str,
) -> list[dict]:
    """Turn Check's default layers into the method chosen in Edit.

    Clean has two methods, AI fill and Blur. Check's mid-frame cover companion
    is dropped for both: a cover is an effect the creator adds, not a Clean
    method.
    """
    out: list[dict] = []
    for layer in layers:
        if str(layer.get("label") or "") == "Mid-frame caption cover":
            continue
        item = dict(layer)
        if method == "ai":
            item["kind"] = "fill"
            item["method"] = fill_method
        else:
            item["kind"] = "blur"
            item.pop("method", None)
        out.append(item)
    return out


def _data_url(path: Path) -> str:
    import base64

    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _read_source_frame(path: Path, width: int, height: int, at: float):
    """One RGB frame from the source at ``at`` seconds."""
    import subprocess

    import numpy as np

    import render

    command = [
        render._ffmpeg(), "-v", "error", "-nostdin",
        "-ss", f"{max(0.0, float(at)):.6f}", "-i", str(path),
        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{int(width)}x{int(height)}", "pipe:1",
    ]
    completed = subprocess.run(command, capture_output=True, timeout=60, check=False)
    expected = int(width) * int(height) * 3
    if completed.returncode != 0 or len(completed.stdout) < expected:
        tail = (completed.stderr or b"")[-800:].decode("utf-8", "replace")
        raise HTTPException(500, f"Could not read the preview frame. {tail}".strip())
    return np.frombuffer(
        completed.stdout[:expected], dtype=np.uint8,
    ).reshape((int(height), int(width), 3)).copy()


def _preview_filter_chain(segment: dict, out_w: int, out_h: int) -> str:
    """The source-side clean, crop, scale and colour chain for one frame."""
    parts = [str(item) for item in segment.get("pre_filters") or []]
    crop = segment.get("crop") or {}
    try:
        crop_w = int(crop.get("w") or 0)
        crop_h = int(crop.get("h") or 0)
        crop_x = int(crop.get("x") or 0)
        crop_y = int(crop.get("y") or 0)
    except (TypeError, ValueError):
        crop_w = crop_h = 0
    if crop_w > 1 and crop_h > 1:
        parts.append(f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}")
    parts.extend([f"scale={out_w}:{out_h}:flags=lanczos", "setsar=1"])
    parts.extend(str(item) for item in segment.get("post_filters") or [])
    return ",".join(part for part in parts if part)


def _render_preview_jpeg(png: Path, output: Path, chain: str) -> None:
    """Encode one PNG through the same crop/colour chain as the beat."""
    import subprocess

    import render

    command = [
        render._ffmpeg(), "-y", "-v", "error", "-i", str(png),
        "-vf", chain, "-frames:v", "1", "-q:v", "2", str(output),
    ]
    completed = subprocess.run(command, capture_output=True, timeout=90, check=False)
    if completed.returncode != 0 or not output.is_file():
        tail = (completed.stderr or b"")[-1200:].decode("utf-8", "replace")
        raise HTTPException(500, f"Could not prepare the fill preview. {tail}".strip())


def _layers_in_story(layers: list[dict], story: dict) -> tuple[list[dict], list[dict]]:
    """Keep Clean layers whose text is on screen during this story.

    Check tracklets cover the whole source; a moment needs only the text
    inside its own ``start``-``end``. Ranges are clipped to the story. A
    layer without ranges is on screen the whole time and is kept.
    """
    start = float(story.get("start") or 0.0)
    end = float(story.get("end") or 0.0)
    if end <= start:
        return layers, []
    kept: list[dict] = []
    outside: list[dict] = []
    for layer in layers:
        ranges = [item for item in layer.get("ranges") or [] if isinstance(item, dict)]
        if not ranges:
            kept.append(layer)
            continue
        clipped = []
        for item in ranges:
            left = max(start, float(item.get("start") or 0.0))
            right = min(end, float(item.get("end") or 0.0))
            if right - left > 0.05:
                clipped.append({"start": round(left, 3), "end": round(right, 3)})
        if clipped:
            kept.append({**layer, "ranges": clipped})
        else:
            outside.append(layer)
    return kept, outside


@router.get("/api/fill/status")
def fill_status() -> dict:
    """Which text-fill engines are usable on this machine.

    The UI only offers AI fill when an engine's model and package are both
    present. The single-frame preview always uses LaMa, so it reports that
    separately.
    """
    import app
    from features import ai_fill as textfill

    directory = textfill.models_dir(app.DATA)
    methods = {}
    for method in textfill.METHODS:
        problem = textfill.method_problem(method, directory)
        methods[method] = {
            "id": method,
            "label": textfill.METHOD_COPY.get(method, method),
            "ready": problem is None,
            "reason": problem or "",
        }
    default = next(
        (method for method in ("sttn", "lama") if methods[method]["ready"]),
        None,
    )
    return {
        "methods": methods,
        "default": default,
        "preview": "lama" if methods["lama"]["ready"] else None,
        "models_dir": str(directory),
    }


@router.post("/api/jobs/{job_id}/transcript/translate")
def translate_transcript(job_id: str, body: TranslateTranscriptBody) -> dict:
    """Translate the whole transcript once, then reuse the disk memo.

    The Edit calls this only after the creator chooses a target language.
    Opening the Audio tool or switching moments never calls a provider.
    """
    import app
    import audio
    import pipeline

    job = app.load_job(job_id)
    segments = pipeline.read_transcript(app._job_dir(job_id)) or []
    if not segments:
        raise HTTPException(404, "No transcript for this job.")
    engine = (job.get("analysis") or {}).get("engine") or {}
    source = str(body.source or engine.get("transcript_language") or "en").split("-")[0]
    target = str(body.target or "").split("-")[0]
    if not target:
        raise HTTPException(422, "Choose a target language first.")
    source_lines = [str(item.get("text") or "").strip() for item in segments]
    source_lines = [line for line in source_lines if line]
    started = time.time()
    if body.force:
        audio.clear_translation_memo(source_lines, source, target, body.provider)
    try:
        translated = audio.translate_lines(source_lines, source, target, body.provider)
    except audio.AudioError as exc:
        raise HTTPException(502, str(exc)) from exc
    lines = []
    index = 0
    for item in segments:
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        lines.append({
            "start": round(float(item.get("start") or 0.0), 2),
            "end": round(float(item.get("end") or 0.0), 2),
            "source": text,
            "text": translated[index] if index < len(translated) else text,
        })
        index += 1
    return {
        "source": source,
        "target": target,
        "provider": audio.translation_status().get("provider") or "",
        "lines": lines,
        "latency_ms": round((time.time() - started) * 1000),
    }


@router.get(
    "/api/jobs/{job_id}/check/tracklets/{tracklet_id}/thumb",
    responses={200: {"content": {"image/jpeg": {}}}},
)
def tracklet_thumb(job_id: str, tracklet_id: str):
    """A small crop of one found text region, for the found-text list."""
    import math
    import subprocess

    import app
    import detect
    import render

    job = app.load_job(job_id)
    app.require_source(job)
    report = detect.load_report(app._job_dir(job_id))
    if report is None:
        raise HTTPException(404, "Run Check first.")
    tracklet = next(
        (
            item for item in report.get("tracklets") or []
            if isinstance(item, dict) and str(item.get("id") or "") == tracklet_id
        ),
        None,
    )
    if tracklet is None:
        raise HTTPException(404, "That text region is not in the latest Check.")
    box = tracklet.get("box") if isinstance(tracklet.get("box"), dict) else None
    if not box:
        raise HTTPException(404, "That text region has no box to crop.")
    ranges = [item for item in tracklet.get("ranges") or [] if isinstance(item, dict)]
    if ranges:
        first = ranges[0]
        start = float(first.get("start") or 0.0)
        end = float(first.get("end") or start)
        at = start + max(0.0, min(0.25, (end - start) / 2.0))
    else:
        at = 0.0
    source = job.get("source") or {}
    width = int(source.get("width") or 0)
    height = int(source.get("height") or 0)
    if width < 2 or height < 2:
        raise HTTPException(409, "The source size is not available for a thumbnail.")
    base_x0 = int(math.floor(float(box.get("x") or 0.0) * width))
    base_y0 = int(math.floor(float(box.get("y") or 0.0) * height))
    base_x1 = int(math.ceil((float(box.get("x") or 0.0) + float(box.get("w") or 0.0)) * width))
    base_y1 = int(math.ceil((float(box.get("y") or 0.0) + float(box.get("h") or 0.0)) * height))
    pad_x = max(6, int(round((base_x1 - base_x0) * 0.06)))
    pad_y = max(4, int(round((base_y1 - base_y0) * 0.35)))
    x0 = max(0, base_x0 - pad_x)
    y0 = max(0, base_y0 - pad_y)
    x1 = min(width, base_x1 + pad_x)
    y1 = min(height, base_y1 + pad_y)
    crop_w = max(2, x1 - x0)
    crop_h = max(2, y1 - y0)
    source_path = Path(str(source.get("path") or ""))
    if not source_path.is_file():
        raise HTTPException(404, "The source video for this job is missing.")
    command = [
        render._ffmpeg(), "-v", "error", "-nostdin",
        "-ss", f"{max(0.0, at):.3f}", "-i", str(source_path),
        "-frames:v", "1",
        "-vf", f"crop={crop_w}:{crop_h}:{x0}:{y0},scale=240:-2",
        "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1",
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, timeout=20, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise HTTPException(500, "Could not read a frame for this text region.") from exc
    if completed.returncode != 0 or not completed.stdout:
        tail = (completed.stderr or b"")[-800:].decode("utf-8", "replace")
        raise HTTPException(500, f"Could not crop the text region. {tail}".strip())
    return Response(
        content=completed.stdout,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=86400"},
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


@router.delete("/api/jobs/{job_id}/clip-sets/{set_id}/stories/{story_id}")
def delete_story(job_id: str, set_id: str, story_id: str, request: Request) -> dict:
    """Remove one moment from a set. Its Edits and renders keep their own files."""
    import app

    if not app._setup_origin_ok(request):
        raise HTTPException(403, "Cross-site writes are blocked.")
    job = app._clipset_job(job_id)
    record = app._clip_set_in_job(job, set_id)
    stories = list(record.get("stories") or [])
    kept = [story for story in stories if str(story.get("id")) != story_id]
    if len(kept) == len(stories):
        raise HTTPException(404, "Moment not found.")
    record["stories"] = kept
    record["available"] = len(kept)
    record["note"] = None
    record["updated"] = app.time.time()
    app._store_clip_set(job_id, record)
    return {"clip_set": record}


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
    from features import ai_fill as textfill

    if not app._setup_origin_ok(request):
        raise HTTPException(403, "Cross-site writes are blocked.")
    body = body or AutoCleanBody()
    method = str(body.method or "auto").strip().lower()
    if method not in {"auto", "ai", "blur"}:
        raise HTTPException(422, "method must be auto, ai or blur.")
    fill_method = str(body.fill_method or "sttn").strip().lower()
    if fill_method not in textfill.METHODS:
        raise HTTPException(422, "fill_method must be sttn or lama.")
    if method == "auto":
        ready = [
            item for item in (fill_method, *textfill.METHODS)
            if textfill.method_problem(item, textfill.models_dir(app.DATA)) is None
        ]
        method = "ai" if ready else "blur"
        if ready:
            fill_method = ready[0]
    job = app.load_job(job_id)
    job_dir = app._job_dir(job_id)
    try:
        edit = edits.load_edit(job_dir, edit_id)
    except edits.EditError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    if edit is None:
        raise HTTPException(404, "Edit not found.")
    story = _edit_story(job, edit)
    if story is None:
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
        include_handles=bool(body.include_handles),
        selected=None if body.tracklet_ids is None else body.tracklet_ids,
    )
    generated = _apply_clean_method(
        list(built.get("layers") or []), method, fill_method,
    )
    in_story, outside = _layers_in_story(generated, story)
    merged = cleanup.merge_auto_clean_layers(edit.get("clean") or [], in_story)
    skipped = [
        {
            "tracklet_id": item.get("tracklet_id"),
            "kind": item.get("kind"),
            "reason": item.get("reason"),
        }
        for item in built.get("refused") or []
    ]
    skipped.extend(
        {
            "tracklet_id": item.get("tracklet_id"),
            "kind": item.get("tracklet_kind") or item.get("kind"),
            "reason": "This text is not on screen during this moment.",
        }
        for item in outside
    )
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
        "updated": merged["updated"],
        "added": len(merged["layers"]),
        "skipped": skipped,
        "warnings": warnings,
    }


def _draft_edit(
    edit: dict,
    clean: list[dict] | None,
    layer_ids: list[str] | None,
) -> tuple[dict, str]:
    """The Edit with unsaved Clean layers, scoped to some ids. Nothing is saved.

    Returns (edit, tag); the tag tells a draft's cached results apart.
    """
    import hashlib
    import json

    import edits as edits_module

    scoped_ids = {str(item) for item in (layer_ids or []) if str(item)}
    if clean is None and not scoped_ids:
        return edit, ""
    try:
        layers = (
            edits_module.normalize_clean(clean)
            if clean is not None
            else list(edit.get("clean") or [])
        )
    except edits_module.EditError as exc:
        raise HTTPException(422, str(exc)) from exc
    if scoped_ids:
        layers = [layer for layer in layers if str(layer.get("id")) in scoped_ids]
        if not layers:
            raise HTTPException(
                422, "Select a Clean layer that is part of this Edit.",
            )
    try:
        drafted = edits_module.build_edit(
            story_ref=edit.get("story_ref"),
            aspect=edit.get("aspect"),
            sequence=edit.get("sequence"),
            clean=layers,
            reframe=edit.get("reframe"),
            motion=edit.get("motion"),
            color=edit.get("color"),
            graphics=edit.get("graphics"),
            captions=edit.get("captions"),
            audio=edit.get("audio"),
            border=edit.get("border"),
            output=edit.get("output"),
            assets=edit.get("assets"),
            version=edit.get("version") or 1,
            parent=edit.get("parent"),
            created=edit.get("created"),
            renderer_version=edit.get("renderer_version"),
        )
    except edits_module.EditError as exc:
        raise HTTPException(422, str(exc)) from exc
    tag = hashlib.sha1(
        json.dumps(
            {"clean": layers, "ids": sorted(scoped_ids)},
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8"),
    ).hexdigest()[:12]
    return drafted, tag


def _edit_fill_rows(job_id: str, job: dict, edit: dict, story: dict) -> list[dict]:
    """One cost row per beat of this Edit that has an AI fill."""
    import app
    import render
    import routes_edits
    from features import ai_fill as textfill

    out_w, out_h = render._dims(edit["aspect"], "draft")
    compiled = routes_edits._compiled_preview(job_id, job, edit, story, size=(out_w, out_h))
    fps = int((edit.get("output") or {}).get("fps") or render.OUT_FPS)
    job_dir = app._job_dir(job_id)
    rows = []
    for segment in compiled.get("segments") or []:
        plan = segment.get("fill")
        if not plan:
            continue
        rows.append(textfill.estimate_span(
            meta=job.get("source") or {},
            start=float(segment["start"]),
            duration=int(segment["frames"]) / fps,
            layers=plan.get("layers") or [],
            method=plan.get("method") or textfill.DEFAULT_METHOD,
            cache_dir=job_dir / "fill",
            data_root=job_dir.parent.parent,
        ))
    return rows


class FillEstimateBody(BaseModel):
    clean: list[dict] | None = None

    model_config = ConfigDict(extra="forbid")


@router.post("/api/jobs/{job_id}/edits/{edit_id}/fill-estimate")
def fill_estimate(
    job_id: str,
    edit_id: str,
    request: Request,
    body: FillEstimateBody | None = None,
) -> dict:
    """How long AI fill will add to this Edit's render. Runs nothing."""
    import app
    import routes_edits
    from features import ai_fill as textfill

    if not app._setup_origin_ok(request):
        raise HTTPException(403, "Cross-site writes are blocked.")
    body = body or FillEstimateBody()
    job, edit, story = routes_edits._fresh_story(job_id, edit_id)
    edit, _tag = _draft_edit(edit, body.clean, None)
    return textfill.estimate_summary(
        _edit_fill_rows(job_id, job, edit, story), app.DATA,
    )


@router.get("/api/jobs/{job_id}/fill-estimate")
def job_fill_estimate(job_id: str, set_id: str, aspect: str) -> dict:
    """The same figure for every saved Edit of a clip set in one shape."""
    import app
    import routes_edits
    from features import ai_fill as textfill

    job = app.load_job(job_id)
    rows: list[dict] = []
    for key, edit_id in (job.get("story_edits") or {}).items():
        if not (str(key).startswith(f"{set_id}:") and str(key).endswith(f":{aspect}")):
            continue
        try:
            fresh_job, edit, story = routes_edits._fresh_story(job_id, str(edit_id))
        except HTTPException:
            # A stale Edit cannot render; Finish says so on its own row.
            continue
        rows.extend(_edit_fill_rows(job_id, fresh_job, edit, story))
    return textfill.estimate_summary(rows, app.DATA)


class FillSampleBody(BaseModel):
    t: float = 0.0
    seconds: float = 1.0
    clean: list[dict] | None = None
    layer_ids: list[str] | None = None

    model_config = ConfigDict(extra="forbid")


# One running sample per job, so Cancel can reach it.
_SAMPLE_CANCELS: dict[str, threading.Event] = {}


@router.post("/api/jobs/{job_id}/edits/{edit_id}/fill-sample")
def fill_sample(
    job_id: str,
    edit_id: str,
    request: Request,
    body: FillSampleBody | None = None,
) -> dict:
    """Run the layer's real engine on about a second at the playhead.

    The one-frame preview always uses LaMa. This shows what the render's own
    engine does, in motion. Nothing is saved, and the clip is cached.
    """
    import base64
    import math
    import shutil
    import uuid

    from PIL import Image

    import app
    import render
    import routes_edits
    from features import ai_fill as textfill

    if not app._setup_origin_ok(request):
        raise HTTPException(403, "Cross-site writes are blocked.")
    body = body or FillSampleBody()
    if not math.isfinite(float(body.t)) or not math.isfinite(float(body.seconds)):
        raise HTTPException(422, "t and seconds must be finite numbers.")
    if textfill.busy():
        raise HTTPException(409, "AI fill is busy with a render. Try again when it finishes.")
    job, edit, story = routes_edits._fresh_story(job_id, edit_id)
    edit, _tag = _draft_edit(edit, body.clean, body.layer_ids)
    source = job.get("source") or {}
    source_path = Path(str(source.get("path") or ""))
    width = int(source.get("width") or 0)
    height = int(source.get("height") or 0)
    if not source_path.is_file():
        raise HTTPException(404, "The source video for this job is missing.")
    out_w, out_h = render._dims(edit["aspect"], "draft")
    compiled = routes_edits._compiled_preview(job_id, job, edit, story, size=(out_w, out_h))
    segments = compiled.get("segments") or []
    if not segments:
        raise HTTPException(422, "This Edit has no frames to preview.")
    at = max(0.0, min(float(body.t), float(segments[-1].get("out_end") or 0.0) - 0.01))
    try:
        _index, segment = render._compiled_segment_at(compiled, at)
    except render.PipelineError as exc:
        raise HTTPException(422, str(exc)) from exc
    plan = segment.get("fill") or {}
    if not plan.get("layers"):
        raise _fill_refused(
            "This layer is not AI fill here: it may be Blur, off this beat, or outside the crop.",
            job_id=job_id, at=at,
        )
    method = plan.get("method") or textfill.DEFAULT_METHOD
    fps = float(source.get("fps") or render.OUT_FPS)
    begin = float(segment.get("start") or 0.0) + max(0.0, at - float(segment.get("out_start") or 0.0))
    beat_end = float(segment.get("start") or 0.0) + float(segment.get("out_end") or 0.0) - float(segment.get("out_start") or 0.0)
    span = max(0.2, min(float(body.seconds), 2.0, beat_end - begin))
    job_dir = app._job_dir(job_id)
    cancel = threading.Event()
    _SAMPLE_CANCELS[job_id] = cancel
    try:
        clip = textfill.prepare_span(
            source=str(source_path),
            meta=source,
            start=begin,
            duration=span,
            layers=plan["layers"],
            method=method,
            cache_dir=job_dir / "fill" / "sample",
            data_root=job_dir.parent.parent,
            ffmpeg=render._ffmpeg(),
            cancel_event=cancel,
        )
    except textfill.FillCancelled as exc:
        raise HTTPException(409, "Test cancelled.") from exc
    except textfill.FillError as exc:
        raise HTTPException(409, str(exc)) from exc
    finally:
        _SAMPLE_CANCELS.pop(job_id, None)
        textfill.release_fillers()
    if clip is None:
        raise _fill_refused(
            "This layer has no text to fill in the next second. Move to where its text shows.",
            job_id=job_id, at=at,
        )
    chain = _preview_filter_chain(segment, out_w, out_h)
    tmp = job_dir / "renders" / f"tmp_fill_sample_{uuid.uuid4().hex}"
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        middle = span / 2
        pictures = {
            "before": _read_source_frame(source_path, width, height, begin + middle),
            "after": _read_source_frame(Path(clip["path"]), width, height, middle),
        }
        urls = {}
        for name, picture in pictures.items():
            png = tmp / f"{name}.png"
            jpg = tmp / f"{name}.jpg"
            final = tmp / f"{name}_final.jpg"
            Image.fromarray(picture).save(png)
            _render_preview_jpeg(png, jpg, chain)
            render._burn_frame(
                jpg, compiled.get("overlays") or [], final,
                out_w, out_h, at + middle, job_dir.parent.parent / "cache" / "layers",
            )
            urls[name] = _data_url(final)
        movie = tmp / "sample.mp4"
        _run_ffmpeg([
            render._ffmpeg(), "-y", "-v", "error", "-i", str(clip["path"]),
            "-vf", chain, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(movie),
        ])
        video = "data:video/mp4;base64," + base64.b64encode(movie.read_bytes()).decode("ascii")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {
        **urls,
        "video": video,
        "method": method,
        "label": textfill.METHOD_COPY.get(method, method),
        "seconds": round(span, 2),
        "frames": int(round(span * fps)),
        "cached": bool(clip.get("cached")),
        "time": round(at, 3),
    }


@router.post("/api/jobs/{job_id}/edits/{edit_id}/fill-sample/cancel")
def cancel_fill_sample(job_id: str, edit_id: str, request: Request) -> dict:
    import app

    if not app._setup_origin_ok(request):
        raise HTTPException(403, "Cross-site writes are blocked.")
    event = _SAMPLE_CANCELS.get(job_id)
    if event is not None:
        event.set()
    return {"cancelled": event is not None}


@router.post("/api/jobs/{job_id}/edits/{edit_id}/fill-preview")
def fill_preview(
    job_id: str,
    edit_id: str,
    request: Request,
    body: FillPreviewBody | None = None,
) -> dict:
    """Before/after JPEGs of one frame with LaMa filling the AI-fill boxes.

    This is deliberately one frame, not a render: the full render still does
    the whole span. The returned images share the crop, colour and overlays,
    so the slider compares only the fill. Results are cached by Edit hash,
    frame and model stamp.
    """
    import hashlib
    import math
    import shutil
    import uuid

    from PIL import Image

    import app
    import render
    import routes_edits
    from features import ai_fill as textfill

    if not app._setup_origin_ok(request):
        raise HTTPException(403, "Cross-site writes are blocked.")
    body = body or FillPreviewBody()
    method = str(body.method or "lama").strip().lower()
    if method != "lama":
        raise HTTPException(422, "The single-frame preview uses the LaMa model.")
    if not math.isfinite(float(body.t)):
        raise HTTPException(422, "t must be a finite time in seconds.")
    job, edit, story = routes_edits._fresh_story(job_id, edit_id)
    edit, draft_tag = _draft_edit(edit, body.clean, body.layer_ids)
    source = job.get("source") or {}
    source_path = Path(str(source.get("path") or ""))
    width = int(source.get("width") or 0)
    height = int(source.get("height") or 0)
    out_w, out_h = render._dims(edit["aspect"], "draft")
    compiled = routes_edits._compiled_preview(
        job_id, job, edit, story, size=(out_w, out_h),
    )
    segments = compiled.get("segments") or []
    if not segments:
        raise HTTPException(422, "This Edit has no frames to preview.")
    total = float(segments[-1].get("out_end") or 0.0)
    frame = max(0, int(round(float(body.t) * render.OUT_FPS)))
    last_frame = max(0, int(round(total * render.OUT_FPS)) - 1)
    frame = min(frame, last_frame)
    at = frame / render.OUT_FPS
    try:
        _index, segment = render._compiled_segment_at(compiled, at)
    except render.PipelineError as exc:
        raise HTTPException(422, str(exc)) from exc
    fill_plan = segment.get("fill") or {}
    fill_layers = [item for item in fill_plan.get("layers") or [] if isinstance(item, dict)]
    if not fill_layers:
        raise HTTPException(
            422,
            "This frame has no AI fill layer. Choose AI fill and remove the found text first.",
        )
    if not source_path.is_file():
        raise HTTPException(404, "The source video for this job is missing.")
    if width < 2 or height < 2:
        raise HTTPException(409, "The source size is not available for a fill preview.")
    fps = float(source.get("fps") or render.OUT_FPS)
    source_time = float(segment.get("start") or 0.0) + max(
        0.0, at - float(segment.get("out_start") or 0.0),
    )
    rects = textfill.masks.frame_rects(
        fill_layers,
        start=source_time - (0.5 / max(1.0, fps)),
        fps=fps,
        frames=1,
        width=width,
        height=height,
    )[0]
    if not rects:
        raise HTTPException(422, "No AI fill region is active at this frame.")

    directory = textfill.models_dir(app.DATA)
    problem = textfill.missing_model("lama", directory)
    if problem:
        raise HTTPException(409, problem)
    model_path = textfill.model_path("lama", directory)
    stamp = model_path.stat()
    key = hashlib.sha1(
        (
            f"{edit['hash']}:{draft_tag}:{frame}:{out_w}x{out_h}:lama:"
            f"{stamp.st_size}:{stamp.st_mtime_ns}:{source.get('fingerprint')}"
        ).encode("utf-8"),
    ).hexdigest()[:20]
    job_dir = app._job_dir(job_id)
    cache_dir = job_dir / "fill" / "preview"
    before_jpg = cache_dir / f"{key}_before.jpg"
    after_jpg = cache_dir / f"{key}_after.jpg"
    if before_jpg.is_file() and after_jpg.is_file():
        return {
            "before": _data_url(before_jpg),
            "after": _data_url(after_jpg),
            "width": out_w,
            "height": out_h,
            "time": round(at, 3),
            "method": "lama",
            "cached": True,
        }

    frame_rgb = _read_source_frame(source_path, width, height, source_time)
    try:
        tight_rects = textfill.masks.frame_rects(
            [
                layer for layer in fill_layers
                if textfill.masks.uses_text_mask(layer, width, height)
            ],
            start=source_time - (0.5 / max(1.0, fps)),
            fps=fps,
            frames=1,
            width=width,
            height=height,
        )[0]
        filled_rgb = textfill.fill_frame(
            frame_rgb, rects, data_root=job_dir.parent.parent, method="lama",
            tight_rects=tight_rects,
        )
    except textfill.FillError as exc:
        raise HTTPException(409, str(exc)) from exc
    tmp = job_dir / "renders" / f"tmp_fill_preview_{uuid.uuid4().hex}"
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        before_png = tmp / "before.png"
        after_png = tmp / "after.png"
        Image.fromarray(frame_rgb).save(before_png)
        Image.fromarray(filled_rgb).save(after_png)
        chain = _preview_filter_chain(segment, out_w, out_h)
        before_raw = tmp / "before_raw.jpg"
        after_raw = tmp / "after_raw.jpg"
        _render_preview_jpeg(before_png, before_raw, chain)
        _render_preview_jpeg(after_png, after_raw, chain)
        before_final = tmp / "before_final.jpg"
        after_final = tmp / "after_final.jpg"
        layer_cache = job_dir.parent.parent / "cache" / "layers"
        render._burn_frame(
            before_raw, compiled.get("overlays") or [], before_final,
            out_w, out_h, at, layer_cache,
        )
        render._burn_frame(
            after_raw, compiled.get("overlays") or [], after_final,
            out_w, out_h, at, layer_cache,
        )
        cache_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(before_final, before_jpg)
        shutil.copyfile(after_final, after_jpg)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {
        "before": _data_url(before_jpg),
        "after": _data_url(after_jpg),
        "width": out_w,
        "height": out_h,
        "time": round(at, 3),
        "method": "lama",
        "cached": False,
    }


# ---------------------------------------------------------------- media assets


class SceneAssetBody(BaseModel):
    source_job_id: str = ""
    scene: int = 0

    model_config = ConfigDict(extra="forbid")


class VideoPathBody(BaseModel):
    path: str = ""
    name: str = ""

    model_config = ConfigDict(extra="forbid")


class VideoUrlBody(BaseModel):
    url: str = ""
    name: str = ""
    rights: bool | None = None

    model_config = ConfigDict(extra="forbid")


def _asset_root(job_id: str) -> Path:
    import app

    root = app._job_dir(job_id) / "assets"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _asset_row(root: Path, path: Path, kind: str = "video") -> dict:
    import pipeline

    try:
        meta = pipeline.probe(str(path))
    except Exception:
        meta = {}
    return {
        "id": path.stem,
        "kind": kind,
        "name": path.stem,
        "path": f"assets/{path.name}",
        "width": int(meta.get("width") or 0),
        "height": int(meta.get("height") or 0),
        "duration": round(float(meta.get("duration") or 0.0), 3),
        "has_audio": bool(meta.get("has_audio")),
    }


def _run_ffmpeg(args: list[str]) -> None:
    import subprocess

    completed = subprocess.run(args, capture_output=True, text=True)
    if completed.returncode != 0:
        raise HTTPException(422, (completed.stderr or completed.stdout or "Media conversion failed.")[-1200:])


@router.get("/api/jobs/{job_id}/assets")
def list_job_assets(job_id: str) -> dict:
    import app

    app.load_job(job_id)
    root = _asset_root(job_id)
    rows = []
    for path in sorted(root.glob("*.mp4")):
        rows.append(_asset_row(root, path))
    return {"assets": rows}


@router.post("/api/jobs/{job_id}/assets/from-scene")
def add_scene_asset(job_id: str, body: SceneAssetBody) -> dict:
    import shutil
    import subprocess
    import uuid

    import app

    app.load_job(job_id)
    if not body.source_job_id:
        raise HTTPException(422, "Choose a source video.")
    source_job = app.load_job(body.source_job_id)
    app.require_source(source_job)
    scenes = (source_job.get("analysis") or {}).get("scenes") or []
    scene = next(
        (item for item in scenes if int(item.get("id", -1)) == int(body.scene)),
        None,
    )
    if not scene:
        raise HTTPException(404, "That scene is not in the source video.")
    start = float(scene.get("start") or 0.0)
    end = float(scene.get("end") or start)
    if end - start < 0.2:
        raise HTTPException(422, "That scene is too short to add.")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise HTTPException(500, "ffmpeg is not available.")
    asset_id = f"asset_{uuid.uuid4().hex[:12]}"
    output = _asset_root(job_id) / f"{asset_id}.mp4"
    source_path = str((source_job.get("source") or {}).get("path") or "")
    _run_ffmpeg([
        ffmpeg, "-y", "-v", "error",
        "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}",
        "-i", source_path,
        "-map", "0:v:0", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
        "-movflags", "+faststart", str(output),
    ])
    return {"asset": _asset_row(_asset_root(job_id), output)}




def _attach_video_asset(job_id: str, source_path: str, name: str = "") -> dict:
    """Copy or remux one full video into the job's asset folder."""
    import shutil
    import uuid

    import app

    app.load_job(job_id)
    source = Path(source_path).expanduser()
    if not source.is_file():
        raise HTTPException(404, "That video file is not on this Mac.")
    root = _asset_root(job_id)
    asset_id = f"video_{uuid.uuid4().hex[:12]}"
    output = root / f"{asset_id}.mp4"
    if source.suffix.lower() == ".mp4":
        shutil.copyfile(source, output)
    else:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise HTTPException(500, "ffmpeg is not available.")
        _run_ffmpeg([
            ffmpeg, "-y", "-v", "error", "-i", str(source),
            "-map", "0:v:0", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
            "-movflags", "+faststart", str(output),
        ])
    row = _asset_row(root, output)
    row["name"] = (name or source.stem)[:120] or "Full video"
    return {"asset": row}


@router.post("/api/jobs/{job_id}/assets/video")
async def add_video_asset(job_id: str, file: UploadFile = File(...)) -> dict:
    import shutil
    import tempfile

    import app

    app.load_job(job_id)
    suffix = Path(getattr(file, "filename", "") or "video.mp4").suffix.lower()
    if suffix not in {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}:
        raise HTTPException(422, "Upload an MP4, MOV, MKV, WEBM, M4V or AVI video.")
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        with handle as target:
            shutil.copyfileobj(file.file, target)
        return _attach_video_asset(
            job_id, handle.name, Path(getattr(file, "filename", "") or "Full video").stem,
        )
    finally:
        try:
            Path(handle.name).unlink()
        except OSError:
            pass


@router.post("/api/jobs/{job_id}/assets/video-path")
def add_video_path_asset(job_id: str, body: VideoPathBody) -> dict:
    import app

    app.load_job(job_id)
    if not str(body.path or "").strip():
        raise HTTPException(422, "Choose a video file or enter a full path.")
    return _attach_video_asset(job_id, body.path, body.name)




@router.post("/api/jobs/{job_id}/assets/video-url")
def add_video_url_asset(job_id: str, body: VideoUrlBody) -> dict:
    """Download a public video link into this job as one asset."""
    import threading
    import uuid

    from url_ingest import registry

    import app

    app.load_job(job_id)
    app._require_import_rights(body.rights)
    try:
        url = app._validate_remote_ingest_url(body.url)
        provider_settings = app._ingest_provider_settings()
        order = app._ingest_provider_order(url, None, provider_settings)
        chain = app._ingest_provider_chain(provider_settings, order)
        options = registry.options_from_settings(provider_settings)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc
    root = _asset_root(job_id)
    asset_id = f"video_{uuid.uuid4().hex[:12]}"
    destination = root / f"{asset_id}.mp4"
    try:
        result = chain.download(
            url, destination, options, lambda *_args, **_kwargs: None,
            threading.Event(),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc
    downloaded = Path(getattr(result, "path", destination))
    if downloaded != destination and downloaded.is_file():
        import shutil
        shutil.move(str(downloaded), destination)
    if not destination.is_file():
        raise HTTPException(502, "The downloader did not produce a video file.")
    row = _asset_row(root, destination)
    row["name"] = (body.name or getattr(result, "title", "") or url)[:120] or "Linked video"
    return {"asset": row}


@router.post("/api/jobs/{job_id}/assets/photo")
async def add_photo_asset(job_id: str, file: UploadFile = File(...)) -> dict:
    import shutil
    import uuid

    import app

    app.load_job(job_id)
    suffix = Path(getattr(file, "filename", "") or "photo.jpg").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}:
        raise HTTPException(422, "Upload a JPG, PNG, WEBP or HEIC image.")
    asset_id = f"photo_{uuid.uuid4().hex[:12]}"
    root = _asset_root(job_id)
    raw = root / f".{asset_id}{suffix}"
    output = root / f"{asset_id}.mp4"
    try:
        with raw.open("wb") as handle:
            shutil.copyfileobj(file.file, handle)
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise HTTPException(500, "ffmpeg is not available.")
        _run_ffmpeg([
            ffmpeg, "-y", "-v", "error",
            "-loop", "1", "-i", str(raw), "-t", "2.5",
            "-vf", "scale=1080:-2:flags=lanczos",
            "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
        ])
        row = _asset_row(root, output, kind="photo")
        row["name"] = Path(getattr(file, "filename", "Photo")).stem[:120] or "Photo"
        return {"asset": row}
    finally:
        try:
            raw.unlink()
        except OSError:
            pass


@router.get("/api/jobs/{job_id}/assets/{asset_id}")
def get_job_asset(job_id: str, asset_id: str):
    import app
    from fastapi.responses import FileResponse

    app.load_job(job_id)
    path = _asset_root(job_id) / f"{asset_id}.mp4"
    if not path.is_file():
        raise HTTPException(404, "Asset not found.")
    return FileResponse(path, media_type="video/mp4")


@router.get("/api/jobs/{job_id}/assets/{asset_id}/thumb")
def get_job_asset_thumb(job_id: str, asset_id: str):
    import shutil
    import subprocess

    import app
    from fastapi.responses import FileResponse

    app.load_job(job_id)
    root = _asset_root(job_id)
    path = root / f"{asset_id}.mp4"
    if not path.is_file():
        raise HTTPException(404, "Asset not found.")
    thumb = root / f".{asset_id}.jpg"
    if not thumb.is_file() or thumb.stat().st_size < 512:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise HTTPException(500, "ffmpeg is not available.")
        _run_ffmpeg([
            ffmpeg, "-y", "-v", "error", "-ss", "0.05", "-i", str(path),
            "-frames:v", "1", "-vf", "scale=360:-2", "-q:v", "3", str(thumb),
        ])
    return FileResponse(thumb, media_type="image/jpeg")
