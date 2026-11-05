"""HTTP surface for Flow 1 Clean.

The Cleanup Kit router is always registered, but its planning and Clean
routes return 404 unless ``VIBECUT_ENABLE_CLEANUP`` is enabled. The rights
router is not gated: T4 records the server-side attestation at Import/Check.

The original plan endpoint stays a pure planner. The Wave 3 routes add:

* ``POST /api/jobs/{id}/cleanup/layers`` — turn Check tracklets into Edit
  Clean layers, gated by detected kind and the stored rights record;
* ``POST /api/jobs/{id}/cleanup/residual`` — render Clean-only frames and
  report OCR text left inside the cleaned regions;
* ``GET/POST /api/jobs/{id}/rights`` — store the own-footage attestation on
  the job. No browser storage is authoritative.
"""

from __future__ import annotations

import logging
import math
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

import cleanup
import compose_render
import detect
import edits
import pipeline
import render
import rights
import vision

LOGGER = logging.getLogger("vibecut.cleanup")


class CleanupPlanBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    story_id: str | None = None
    artifact_id: str | None = None
    aspect: str
    method: str
    boxes: list[object] | None = None
    attestation: bool | str | None = None
    range: dict | list | None = None


class CleanLayersBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tracklet_ids: list[str] | None = None


class ResidualBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edit_id: str = Field(min_length=1, max_length=64)
    times: list[float] | None = Field(
        default=None, max_length=cleanup.RESIDUAL_MAX_FRAMES,
    )
    start: float | None = None
    end: float | None = None
    fps: float = Field(default=cleanup.RESIDUAL_DEFAULT_FPS, gt=0.0, le=30.0)
    max_frames: int = Field(default=cleanup.RESIDUAL_DEFAULT_FRAMES, ge=1)
    quality: str = "final"


class RightsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attested: bool
    source: Literal["import", "check"]


def cleanup_enabled() -> bool:
    """Clean is core: on unless the operator explicitly disables it.

    Unset, blank and unknown values keep Clean on. ``0``, ``false``, ``no``
    and ``off`` are the explicit off switches.
    """
    value = os.environ.get("VIBECUT_ENABLE_CLEANUP")
    if value is None or not value.strip():
        return True
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _require_enabled() -> None:
    if not cleanup_enabled():
        raise HTTPException(404, "Cleanup is not enabled in this build.")


router = APIRouter(dependencies=[Depends(_require_enabled)])
rights_router = APIRouter()


def _job_app():
    import app

    return app


def _clips(value) -> list[dict]:
    result = []
    for index, item in enumerate(value or []):
        if not isinstance(item, dict):
            continue
        try:
            start = float(item.get("start") or 0.0)
            end = float(item.get("end", start + float(item.get("dur") or 0.0)))
        except (TypeError, ValueError):
            continue
        duration = float(item.get("dur") or (end - start))
        result.append({
            "scene": item.get("scene", index),
            "start": round(start, 3),
            "end": round(end, 3),
            "dur": round(max(0.0, duration), 3),
            "role": str(item.get("role") or "beat"),
        })
    return result


def _span(clips: list[dict], fallback: float = 0.0) -> dict:
    if clips:
        return {
            "start": min(clip["start"] for clip in clips),
            "end": max(clip["end"] for clip in clips),
        }
    return {"start": 0.0, "end": round(max(0.0, float(fallback or 0.0)), 3)}


def _clip_sets(job: dict) -> list[dict]:
    value = job.get("clip_sets") or []
    if isinstance(value, dict):
        return [record for record in value.values() if isinstance(record, dict)]
    return [record for record in value if isinstance(record, dict)]


def _artifact_source(app, job: dict, artifact_id: str) -> dict:
    job_dir = app._job_dir(job["id"])
    manifest = app.artifacts.load_manifest(job_dir, artifact_id)
    if manifest is None:
        raise HTTPException(404, "Artifact not found.")
    if manifest.get("status") != "ready":
        raise HTTPException(409, "Artifact is not ready for cleanup.")
    if not app.artifacts.has_media(job_dir, artifact_id):
        raise HTTPException(409, "Artifact media is missing.")
    spec = manifest.get("spec") or {}
    clips = _clips(spec.get("clips"))
    source = (job.get("source") or {})
    span = _span(clips, float(source.get("duration") or 0.0))
    aspect = str(spec.get("aspect") or "")
    if aspect not in cleanup.SUPPORTED_ASPECTS:
        aspect = "9:16"
    width, height = cleanup.ASPECT_DIMENSIONS[aspect]
    return {
        "type": "artifact",
        "artifact_id": artifact_id,
        "story_id": spec.get("story_id") or None,
        "clip_set_id": None,
        "media": f"artifacts/{artifact_id}/reel.mp4",
        "aspect": aspect,
        "width": width,
        "height": height,
        "duration": round(span["end"] - span["start"], 3),
        "span": span,
        "clips": clips,
    }


def _story_source(app, job: dict, story_id: str) -> dict:
    if job.get("status") != "ready" or not job.get("analysis"):
        raise HTTPException(409, "Analysis is not ready yet.")
    matches = []
    for record in _clip_sets(job):
        for story in record.get("stories") or []:
            if isinstance(story, dict) and story.get("id") == story_id:
                matches.append((record, story))
    if not matches:
        raise HTTPException(404, "Story not found.")
    if len(matches) > 1:
        raise HTTPException(
            409,
            "Story id is ambiguous in this job; select a finished artifact instead.",
        )
    record, story = matches[0]
    clips = _clips(story.get("clips"))
    source = job.get("source") or {}
    fallback = float(story.get("end") or source.get("duration") or 0.0)
    span = {
        "start": round(float(story.get("start") or 0.0), 3),
        "end": round(fallback, 3),
    }
    if span["end"] <= span["start"]:
        span = _span(clips, fallback)
    return {
        "type": "story",
        "artifact_id": None,
        "story_id": story_id,
        "clip_set_id": record.get("id"),
        "media": None,
        "aspect": None,
        "width": int(source.get("width") or 0) or None,
        "height": int(source.get("height") or 0) or None,
        "duration": round(span["end"] - span["start"], 3),
        "span": span,
        "clips": clips,
    }


def _job_source(job: dict) -> dict:
    source = job.get("source") or {}
    duration = round(float(source.get("duration") or 0.0), 3)
    return {
        "type": "job",
        "artifact_id": None,
        "story_id": None,
        "clip_set_id": None,
        "media": None,
        "aspect": None,
        "width": int(source.get("width") or 0) or None,
        "height": int(source.get("height") or 0) or None,
        "duration": duration,
        "span": {"start": 0.0, "end": duration},
        "clips": [],
    }


@router.post("/api/jobs/{job_id}/cleanup/plan")
def cleanup_plan(job_id: str, body: CleanupPlanBody) -> dict:
    _require_enabled()
    if body.story_id and body.artifact_id:
        raise HTTPException(422, "Send story_id or artifact_id, not both.")

    app = _job_app()
    job = app.load_job(job_id)
    if body.artifact_id:
        source = _artifact_source(app, job, body.artifact_id)
    elif body.story_id:
        source = _story_source(app, job, body.story_id)
    else:
        source = _job_source(job)

    analysis = job.get("analysis") or {}
    analysis_ready = job.get("status") == "ready" and bool(analysis)
    try:
        plan = cleanup.build_plan(
            job_id=job_id,
            source=source,
            aspect=body.aspect,
            method=body.method,
            boxes=body.boxes,
            time_range=body.range,
            attestation=body.attestation,
            scenes=analysis.get("scenes") or [],
            analysis_ready=analysis_ready,
        )
    except cleanup.CleanupStateError as exc:
        raise HTTPException(409, str(exc)) from exc
    except cleanup.CleanupError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "plan": plan,
        "quality_report": plan["quality_report"],
        "warnings": plan["warnings"],
    }


# ---------------------------------------------------------------- clean layers


def _job_rights(job: dict) -> dict:
    rights = job.get("rights")
    return dict(rights) if isinstance(rights, dict) else {}


def _attested(job: dict) -> bool:
    return rights.job_attested(job)


@router.post("/api/jobs/{job_id}/cleanup/layers")
def cleanup_layers(job_id: str, body: CleanLayersBody) -> dict:
    """Build Edit Clean layers from the stored Check report.

    The rights attestation is read from the job, never from this request.
    Watermarks, handles and logos need the own-footage attestation; a kind the
    policy blocks comes back in ``refused``.
    """
    app = _job_app()
    job = app.load_job(job_id)
    report = detect.load_report(app._job_dir(job_id))
    if report is None:
        raise HTTPException(409, "Check has not run for this job.")
    tracklets = [item for item in report.get("tracklets") or [] if isinstance(item, dict)]
    if not tracklets:
        raise HTTPException(409, "Check found no text tracklets to clean.")
    known = {str(item.get("id")) for item in tracklets}
    if body.tracklet_ids is not None:
        unknown = sorted(set(body.tracklet_ids) - known)
        if unknown:
            raise HTTPException(422, f"Unknown tracklet ids: {', '.join(unknown)}.")
    attested = _attested(job)
    if rights.lock_enabled() and not attested:
        raise HTTPException(409, detect.RIGHTS_MESSAGE)
    built = cleanup.tracklet_clean_layers(
        tracklets,
        attested=attested,
        selected=body.tracklet_ids,
        job=job,
    )
    return {
        **built,
        "rights": _job_rights(job),
        "report_created": report.get("created"),
        "policy": report.get("policy") or {},
    }


# ---------------------------------------------------------------- residual OCR


class ResidualFailure(Exception):
    """A residual request failed with a clear reason for the API caller."""

    def __init__(self, reason: str, status: int = 500) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status = int(status)


class ResidualTimeout(ResidualFailure):
    """The per-request residual deadline expired."""

    def __init__(self, seconds: float) -> None:
        super().__init__(
            f"Residual check exceeded its {seconds:.0f} s budget. "
            "Reduce max_frames or measure a shorter range.",
            504,
        )


def _render_frame(job: dict, compiled: dict, t: float, quality: str, aspect: str) -> bytes:
    return render.render_story_frame(
        str(job["source"]["path"]),
        job["source"],
        _job_app()._job_dir(job["id"]),
        compiled,
        t,
        quality=quality,
        aspect=aspect,
    )


def _probe_images(directory: Path) -> dict:
    return vision.probe_images(directory)


def _story_for_edit(job: dict, edit: dict) -> tuple[dict, dict]:
    set_id = edit["story_ref"]["set_id"]
    story_id = edit["story_ref"]["story_id"]
    record = next(
        (item for item in _clip_sets(job) if str(item.get("id") or "") == set_id),
        None,
    )
    if record is None:
        raise HTTPException(409, "The Edit's clip set is missing from this job.")
    story = next(
        (
            item for item in record.get("stories") or []
            if isinstance(item, dict) and str(item.get("id") or "") == story_id
        ),
        None,
    )
    if story is None:
        raise HTTPException(409, "The Edit's story is missing from its clip set.")
    return record, story


def measure_residual(
    job: dict,
    edit: dict,
    job_dir: Path | str,
    *,
    times: list[float] | None = None,
    start: float | None = None,
    end: float | None = None,
    fps: float = cleanup.RESIDUAL_DEFAULT_FPS,
    max_frames: int = cleanup.RESIDUAL_DEFAULT_FRAMES,
    quality: str = "final",
    story: dict | None = None,
    timeout: float = cleanup.RESIDUAL_TIMEOUT_SECONDS,
) -> dict:
    """Render Clean-only frames and return the residual report.

    The route and the inline preflight share this function so both get the
    same hard frame cap, deadline and error shape. Expected failures raise
    :class:`ResidualFailure`; the HTTP layer turns them into JSON.
    """
    quality = str(quality or "").strip().lower()
    if quality not in {"draft", "final"}:
        raise ResidualFailure("quality must be draft or final.", 422)
    if not edit.get("clean"):
        raise ResidualFailure("This Edit has no Clean layers to measure.", 422)
    limit = int(cleanup.RESIDUAL_MAX_FRAMES)
    try:
        frame_limit = int(max_frames)
    except (TypeError, ValueError) as exc:
        raise ResidualFailure("max_frames must be an integer.", 422) from exc
    if frame_limit < 1:
        raise ResidualFailure("max_frames must be at least 1.", 422)
    if frame_limit > limit:
        raise ResidualFailure(
            f"max_frames is capped at {limit} frames per request.", 422,
        )
    if times is not None and len(times) > limit:
        raise ResidualFailure(
            f"times is capped at {limit} values per request.", 422,
        )
    if story is None:
        try:
            _record, story = _story_for_edit(job, edit)
        except HTTPException as exc:
            raise ResidualFailure(str(exc.detail), exc.status_code) from exc

    measure = edits.build_edit(
        story_ref=edit["story_ref"],
        aspect=edit["aspect"],
        clean=edit["clean"],
        reframe=edit["reframe"],
        motion=[],
        color={"preset": "none"},
        graphics=[],
        captions={"enabled": False},
        audio=edit.get("audio"),
        created=edit.get("created"),
        renderer_version=edit.get("renderer_version"),
    )
    out_w, out_h = render._dims(edit["aspect"], quality)
    try:
        compiled = compose_render.compile_edit(
            measure,
            clips=story.get("clips") or [],
            source=job.get("source") or {},
            scenes=(job.get("analysis") or {}).get("scenes") or [],
            include_captions=False,
            size=(out_w, out_h),
            motion_engine=compose_render.EDIT_MOTION_ENGINE,
        )
    except compose_render.ComposeError as exc:
        raise ResidualFailure(
            str(exc), int(getattr(exc, "status_code", 422)),
        ) from exc

    total = float((compiled.get("segments") or [{}])[-1].get("out_end") or 0.0)
    if times is not None:
        moments: list[float] = []
        for value in times:
            try:
                moment = float(value)
            except (TypeError, ValueError) as exc:
                raise ResidualFailure("times must be numbers.", 422) from exc
            if not math.isfinite(moment):
                raise ResidualFailure("times must be finite numbers.", 422)
            if moment < 0.0 or moment >= total - 1e-9:
                raise ResidualFailure(
                    f"times must be between 0 and the story duration ({total:.3f}s).",
                    422,
                )
            moments.append(round(moment, 3))
        if not moments:
            raise ResidualFailure("times must contain at least one value.", 422)
        sample_times = moments
    else:
        try:
            sample_times = cleanup.residual_times(
                compiled,
                start=start,
                end=end,
                fps=fps,
                max_frames=frame_limit,
            )
        except cleanup.CleanupError as exc:
            raise ResidualFailure(str(exc), 422) from exc

    deadline = time.monotonic() + max(0.0, float(timeout))
    directory = (
        Path(job_dir) / "cleanup" / f"residual-{uuid.uuid4().hex}"
    )
    samples: list[dict] = []
    records: dict = {}
    try:
        directory.mkdir(parents=True, exist_ok=True)
        for index, moment in enumerate(sample_times):
            if time.monotonic() >= deadline:
                raise ResidualTimeout(float(timeout))
            payload = _render_frame(job, compiled, moment, quality, edit["aspect"])
            name = f"{index:04d}.jpg"
            (directory / name).write_bytes(payload)
            samples.append({"t": moment, "file": name})
        records = _probe_images(directory) or {}
        for sample in samples:
            record = records.get(sample["file"]) or {}
            sample["text"] = pipeline.ocr_lines(record)
    except ResidualFailure:
        raise
    except Exception as exc:  # noqa: BLE001 - route must return JSON, not 500 HTML
        LOGGER.exception(
            "residual render failed for job %s edit %s",
            job.get("id"), edit.get("id"),
        )
        raise ResidualFailure(
            f"Residual render failed: {type(exc).__name__}: {exc}", 500,
        ) from exc
    finally:
        shutil.rmtree(directory, ignore_errors=True)

    report = cleanup.residual_report(
        samples,
        layers=edit["clean"],
        compiled=compiled,
        target_pct=cleanup.RESIDUAL_TARGET_PCT,
    )
    report["ocr_available"] = bool(records)
    report["faces"] = cleanup.face_overlap_report(
        samples,
        layers=edit["clean"],
        compiled=compiled,
        scenes=(job.get("analysis") or {}).get("scenes") or [],
    )
    report["edit_id"] = edit["id"]
    report["edit_hash"] = edit["hash"]
    report["quality"] = quality
    if not records:
        report["pass"] = None
        report["warnings"] = ["Vision OCR was unavailable; residual text is unknown."]
    else:
        report["warnings"] = []
    return report


@router.post("/api/jobs/{job_id}/cleanup/residual")
def cleanup_residual(job_id: str, body: ResidualBody) -> dict:
    """Render Clean-only frames and measure OCR text left inside Clean regions.

    Body failures are 4xx JSON with a reason. A render or OCR failure is a
    500 JSON reason with the traceback in the server log; a long request gets
    a 504 after the shared deadline. No failure falls through as an HTML 500.
    """
    app = _job_app()
    job = app.load_job(job_id)
    if job.get("status") != "ready" or not job.get("analysis"):
        raise HTTPException(409, "Analysis is not ready yet.")
    try:
        edit = edits.load_edit(app._job_dir(job_id), body.edit_id)
    except edits.EditError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    if edit is None:
        raise HTTPException(404, "Edit not found.")
    try:
        return measure_residual(
            job,
            edit,
            app._job_dir(job_id),
            times=body.times,
            start=body.start,
            end=body.end,
            fps=body.fps,
            max_frames=body.max_frames,
            quality=body.quality,
        )
    except ResidualFailure as exc:
        if exc.status >= 500:
            LOGGER.error(
                "residual failed for job %s edit %s: %s",
                job_id, body.edit_id, exc.reason, exc_info=exc,
            )
        else:
            LOGGER.warning(
                "residual rejected for job %s edit %s: %s",
                job_id, body.edit_id, exc.reason, exc_info=exc,
            )
        raise HTTPException(exc.status, exc.reason) from exc
    except Exception as exc:  # noqa: BLE001 - keep the JSON error contract
        LOGGER.exception(
            "residual crashed for job %s edit %s", job_id, body.edit_id,
        )
        raise HTTPException(
            500,
            f"Residual check failed: {type(exc).__name__}: {exc}",
        ) from exc


# ---------------------------------------------------------------- rights


def _rights_payload(job: dict) -> dict:
    record = _job_rights(job)
    return {
        "attested": rights.normalize_attestation(record.get("attested")),
        "at": record.get("at"),
        "source": record.get("source"),
    }


@rights_router.get("/api/jobs/{job_id}/rights")
def get_rights(job_id: str) -> dict:
    app = _job_app()
    job = app.load_job(job_id)
    return {"rights": _rights_payload(job)}


@rights_router.post("/api/jobs/{job_id}/rights")
def set_rights(job_id: str, body: RightsBody) -> dict:
    """Store the own-footage attestation server-side.

    The timestamp is server time. ``source`` records where the attestation was
    captured: Import or Check. This file is the only source of truth for the
    Clean rights gate; the browser keeps no authoritative copy.
    """
    app = _job_app()
    record = {
        "attested": bool(body.attested),
        "at": round(time.time(), 3),
        "source": body.source,
    }

    def mutate(job: dict) -> None:
        job["rights"] = dict(record)

    job = app.update_job(job_id, mutate)
    return {"rights": _rights_payload(job)}
