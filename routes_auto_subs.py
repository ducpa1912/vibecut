"""Batch auto-subtitles for every story in a clip set (lane: ``studio``).

One request builds the caption tracks; the Studio frontend attaches the
returned track ids to each story Edit. New routes stay outside ``app.py``
(see ``docs/branching.md``), so ``app`` is imported inside the handler.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

LOGGER = logging.getLogger("vibecut.routes_auto_subs")

router = APIRouter()


class AutoSubtitlesBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    set_id: str
    aspect: str = "9:16"
    style_id: str | None = None
    story_ids: list[str] = []


def _target_stories(
    record: dict,
    story_ids: list[str],
) -> tuple[list[dict], list[dict]]:
    """The requested stories, or every story when none are named.

    Unknown ids are failures, not a dead batch: the rest still build.
    """
    stories = [
        story for story in (record.get("stories") or [])
        if isinstance(story, dict)
    ]
    wanted = [str(value) for value in story_ids if str(value).strip()]
    if not wanted:
        return stories, []

    by_id = {str(story.get("id") or ""): story for story in stories}
    targets: list[dict] = []
    failed: list[dict] = []
    seen: set[str] = set()
    for story_id in wanted:
        if story_id in seen:
            continue
        seen.add(story_id)
        story = by_id.get(story_id)
        if story is None:
            failed.append({
                "story_id": story_id,
                "error": "Story not found in this clip set.",
            })
            continue
        targets.append(story)
    return targets, failed


@router.post("/api/jobs/{job_id}/auto-subtitles")
def auto_subtitles(job_id: str, body: AutoSubtitlesBody, request: Request) -> dict:
    """Build one caption track per story, at each story's stored duration.

    Builds tracks only: it never creates or patches an Edit. Per-story errors
    are reported in ``failed`` and do not stop the remaining stories.
    """
    import app

    if not app._setup_origin_ok(request):
        raise HTTPException(403, "Cross-site writes are blocked.")

    job = app.load_job(job_id)
    if job.get("status") != "ready" or not job.get("analysis"):
        raise HTTPException(409, "Analysis is not ready yet.")

    try:
        app.edits.normalize_aspect(body.aspect)
    except app.edits.EditError as exc:
        raise HTTPException(400, str(exc)) from exc

    record = app._clip_set_in_job(job, body.set_id)
    style = app._caption_style_for(body.style_id)
    if not any(
        isinstance(story, dict) for story in (record.get("stories") or [])
    ):
        raise HTTPException(400, "This clip set has no stories.")

    job_dir = app._job_dir(job_id)
    if not app.caption_engine.read_transcript_segments(job_dir):
        raise HTTPException(
            409,
            "No transcript for this job. Transcribe the speech first.",
        )

    targets, failed = _target_stories(record, body.story_ids)
    if not targets and not failed:
        raise HTTPException(400, "This clip set has no stories.")

    tracks: list[dict] = []
    for story in targets:
        story_id = str(story.get("id") or "")
        try:
            plan = app._story_track_plan(
                job,
                app._story_plan(job, record, story, body.set_id),
            )
            track = app.caption_engine.build_track(
                job, plan, style, job_dir=job_dir,
            )
            if not track.cues:
                raise ValueError("No caption cues were built for this story.")
            tracks.append({
                "story_id": story_id,
                "track_id": track.id,
                "cue_count": len(track.cues),
                "style_id": track.style_id,
            })
        except Exception as exc:  # noqa: BLE001 - one story must not stop the batch
            detail = getattr(exc, "detail", None) or str(exc) or exc.__class__.__name__
            LOGGER.warning(
                "Auto-subtitles failed for %s %s:%s: %s",
                job_id, body.set_id, story_id, detail,
            )
            failed.append({"story_id": story_id, "error": str(detail)})

    return {"tracks": tracks, "failed": failed}
