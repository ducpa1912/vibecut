"""Hook/cover matrix metadata for one story.

The matrix is a payload, not a renderer. It exposes three hooks, three cover
frames, nine deterministic cells and nine sequential job descriptors. Other
layers own queueing, artifacts and rendering. Nothing here starts a render.
"""

from __future__ import annotations

import math

import clipset
import selection


class MatrixError(ValueError):
    """A story cannot produce a complete 3x3 hook/cover matrix."""


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if math.isfinite(number) else fallback


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _clip_text(value: str, limit: int = 64) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _cover_frame(
    story: dict,
    scenes: list[dict],
    hook_text: str,
    payoff_text: str,
) -> list[dict]:
    by_id = {int(scene["id"]): scene for scene in scenes if scene.get("id") is not None}
    frames: list[dict] = []
    for clip in story.get("clips") or []:
        try:
            scene_id = int(clip.get("scene"))
        except (TypeError, ValueError):
            continue
        scene = by_id.get(scene_id)
        if scene is None:
            continue
        start = max(
            _safe_float(clip.get("start")),
            _safe_float(scene.get("start")),
        )
        end = min(
            _safe_float(clip.get("end")),
            _safe_float(scene.get("end")),
        )
        if end <= start:
            continue
        midpoint = round((start + end) / 2, 3)
        visual = _clamp(_safe_float(scene.get("visual_score"), 50.0) / 100.0)
        hook = _clamp(_safe_float(scene.get("hook"), 50.0) / 100.0)
        face = 1.0 if scene.get("face") else 0.0
        clean = 0.0 if scene.get("black") or scene.get("freeze") else 1.0
        score = 0.55 * visual + 0.20 * hook + 0.15 * face + 0.10 * clean
        frames.append({
            "scene": scene_id,
            "time": midpoint,
            "start": round(start, 3),
            "end": round(end, 3),
            "score": round(score, 4),
            "visual": round(visual, 4),
        })
    frames.sort(key=lambda item: (
        -item["score"],
        item["scene"],
        item["time"],
    ))

    chosen: list[dict] = []
    seen: set[tuple[int, float]] = set()
    for frame in frames:
        key = (frame["scene"], round(frame["time"], 3))
        if key in seen:
            continue
        seen.add(key)
        chosen.append(frame)
        if len(chosen) >= 3:
            break

    # One long scene can still yield three distinct cover times.
    if len(chosen) < 3 and frames:
        source = frames[0]
        span = max(0.01, source["end"] - source["start"])
        for fraction in (0.30, 0.50, 0.70, 0.20, 0.80, 0.10, 0.90):
            time = round(source["start"] + span * fraction, 3)
            key = (source["scene"], round(time, 3))
            if key in seen:
                continue
            seen.add(key)
            chosen.append({**source, "time": time})
            if len(chosen) >= 3:
                break

    texts = [hook_text, payoff_text, str(story.get("title") or "")]
    covers: list[dict] = []
    for index, frame in enumerate(chosen):
        text = texts[index % len(texts)] if texts else ""
        covers.append({
            "id": f"cv_{story.get('id')}_{index}",
            "story_id": story.get("id"),
            "scene": frame["scene"],
            "time": round(frame["time"], 3),
            "text": _clip_text(text, 48),
            "score": round(frame["score"] * 100, 2),
            "why": (
                f"Cover frame {index + 1}: scene {frame['scene']} at "
                f"{frame['time']:.2f}s, visual {frame['visual'] * 100:.0f}/100."
            ),
            "evidence": [{
                "type": "visual",
                "text": (
                    f"Visual score {frame['visual'] * 100:.0f}/100 at "
                    f"{frame['time']:.2f}s."
                ),
                "scene": frame["scene"],
                "time": round(frame["time"], 3),
            }],
        })
    return covers


def _ensure_three_hooks(story: dict) -> list[dict]:
    return selection.hook_candidates(story, 3)


def build_matrix(story: dict, scenes: list[dict], target: int | None = None) -> dict:
    """Build one deterministic hook/cover matrix. No renders are queued."""
    story_id = str(story.get("id") or "story")
    if not story.get("clips"):
        raise MatrixError(f"Story {story_id} has no materialized clips.")
    duration = _safe_float(story.get("dur"))
    target = int(target) if target is not None else int(round(duration))
    target = max(1, min(180, target))
    hooks = _ensure_three_hooks(story)
    if len(hooks) < 3:
        raise MatrixError(
            f"Story {story_id} has {len(hooks)}/3 distinct hook candidates."
        )
    hook_text = str((hooks[0] or {}).get("text") or (story.get("hook") or {}).get("text") or "")
    payoff_text = str((story.get("payoff") or {}).get("text") or "")
    covers = _cover_frame(story, scenes, hook_text, payoff_text)
    if len(covers) < 3:
        raise MatrixError(
            f"Story {story_id} has {len(covers)}/3 distinct cover frames."
        )
    plan = clipset.story_to_plan(story, scenes, target=target)

    cells: list[dict] = []
    jobs: list[dict] = []
    order = 1
    for hook_index, hook in enumerate(hooks):
        for cover_index, cover in enumerate(covers):
            cell_id = f"cell_{story_id}_{hook_index + 1}_{cover_index + 1}"
            cells.append({
                "id": cell_id,
                "order": order,
                "hook_index": hook_index,
                "cover_index": cover_index,
                "hook": hook.get("id"),
                "cover": cover.get("id"),
            })
            jobs.append({
                "id": f"mx_{story_id}_{order:02d}",
                "sequence": order,
                "status": "planned",
                "kind": "hook_cover",
                "story_id": story_id,
                "story_title": story.get("title"),
                "target": target,
                "hook": hook.get("id"),
                "cover": cover.get("id"),
                "cell": cell_id,
                "metadata": {
                    "hook_text": hook.get("text"),
                    "hook_start": hook.get("start"),
                    "hook_end": hook.get("end"),
                    "cover_text": cover.get("text"),
                    "cover_scene": cover.get("scene"),
                    "cover_time": cover.get("time"),
                },
            })
            order += 1

    return {
        "id": f"mx_{story_id}",
        "version": 2,
        "story_id": story_id,
        "story_title": story.get("title"),
        "target": target,
        "hooks": hooks,
        "covers": covers,
        "cells": cells,
        "jobs": jobs,
        "job_count": len(jobs),
        "sequential": True,
        "complete": True,
        "plan": plan,
        "note": (
            "Matrix metadata only. No renders are queued; queue jobs "
            "sequentially in the listed order."
        ),
    }


def build_matrix_for_stories(
    stories: list[dict],
    scenes: list[dict],
    target: int | None = None,
) -> dict:
    matrices: list[dict] = []
    errors: list[dict] = []
    for story in stories or []:
        story_id = str(story.get("id") or "story")
        try:
            matrices.append(build_matrix(story, scenes, target=target))
        except MatrixError as exc:
            errors.append({
                "story_id": story_id,
                "story_title": story.get("title"),
                "error": str(exc),
                "complete": False,
            })
    if not stories:
        errors.append({
            "story_id": None,
            "story_title": None,
            "error": "No stories are available for a hook/cover matrix.",
            "complete": False,
        })
    return {
        "version": 2,
        "matrices": matrices,
        "errors": errors,
        "count": len(matrices),
        "error_count": len(errors),
        "complete": not errors,
        "job_count": sum(matrix.get("job_count", 0) for matrix in matrices),
        "note": (
            "No renders were started."
            if not errors
            else "No renders were started; incomplete stories are listed in errors."
        ),
    }
