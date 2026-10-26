"""HTTP surface for the gated Flow 1 Cleanup Kit prototype.

The router is always registered, but every route returns 404 unless
``VIBECUT_ENABLE_CLEANUP`` is explicitly enabled. It is a planning API only:
no render is queued and no job is mutated.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

import cleanup


class CleanupPlanBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    story_id: str | None = None
    artifact_id: str | None = None
    aspect: str
    method: str
    boxes: list[object] | None = None
    attestation: bool | str | None = None
    range: dict | list | None = None


def cleanup_enabled() -> bool:
    return os.environ.get("VIBECUT_ENABLE_CLEANUP", "0").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _require_enabled() -> None:
    if not cleanup_enabled():
        raise HTTPException(404, "Cleanup is not enabled in this build.")


router = APIRouter(dependencies=[Depends(_require_enabled)])


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
