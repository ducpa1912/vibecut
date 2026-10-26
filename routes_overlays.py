"""Gated HTTP surface for Flow 2 overlay plans.

The router is registered unconditionally, but every route returns 404 unless
``VIBECUT_ENABLE_OVERLAYS`` is truthy. Planning is read-only: it loads a job,
validates a plan, and returns JSON. It never writes ``overlays.json``, starts
ffmpeg, or calls a network service.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import overlays


class OverlayLayerBody(BaseModel):
    id: str | None = None
    kind: str
    text: str
    start: float
    end: float
    anchor: str | None = None
    box: dict | None = None
    z: int | None = None
    style: dict = Field(default_factory=dict)
    safe_zone: bool = True
    opacity: float = 1.0

    model_config = {"extra": "forbid"}


class OverlayPlanBody(BaseModel):
    story_id: str | None = None
    artifact_id: str | None = None
    aspect: str
    layers: list[OverlayLayerBody] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


def require_feature() -> None:
    """Hide the whole Flow 2 surface when the flag is off."""

    if not overlays.enabled():
        raise HTTPException(404, "Not found.")


router = APIRouter(dependencies=[Depends(require_feature)])


def _find_story(job: dict, story_id: str) -> list[tuple[dict, dict]]:
    matches: list[tuple[dict, dict]] = []
    records = job.get("clip_sets")
    if isinstance(records, dict):
        records = list(records.values())
    if not isinstance(records, list):
        return matches
    for record in records:
        if not isinstance(record, dict):
            continue
        stories = record.get("stories")
        if not isinstance(stories, list):
            continue
        for story in stories:
            if isinstance(story, dict) and str(story.get("id") or "") == story_id:
                matches.append((record, story))
    return matches


def _load_artifact(job_id: str, artifact_id: str) -> dict:
    import app
    import artifacts

    if not artifacts.is_safe_artifact_id(artifact_id):
        raise HTTPException(404, "Artifact not found.")
    manifest = artifacts.load_manifest(app._job_dir(job_id), artifact_id)
    if manifest is None:
        raise HTTPException(404, "Artifact not found.")
    return manifest


@router.post("/api/jobs/{job_id}/overlays/plan")
def plan_overlays(job_id: str, body: OverlayPlanBody) -> dict:
    if not overlays.enabled():
        raise HTTPException(404, "Not found.")

    import app

    job = app.load_job(job_id)
    story_id = (body.story_id or "").strip() or None
    artifact_id = (body.artifact_id or "").strip() or None

    artifact = None
    if artifact_id:
        artifact = _load_artifact(job_id, artifact_id)

    story = None
    clip_set_id = None
    if story_id:
        matches = _find_story(job, story_id)
        if not matches:
            raise HTTPException(404, "Story not found.")
        if len(matches) > 1:
            raise HTTPException(
                409,
                "Story id is ambiguous across clip sets; use artifact_id instead.",
            )
        record, story = matches[0]
        clip_set_id = str(record.get("id") or "") or None

    try:
        plan = overlays.build_plan(
            job,
            body.aspect,
            [layer.model_dump() for layer in body.layers],
            story=story,
            artifact=artifact,
            clip_set_id=clip_set_id,
        )
    except overlays.OverlayError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc

    return {
        "plan": plan.as_dict(),
        "warnings": list(plan.warnings),
        "hash": plan.hash,
    }
