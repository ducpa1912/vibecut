"""DuckSuite edit documents.

A full-video edit is created first. A story edit is either a manual range or a
smart story candidate. Clean layers live on the edit.
"""

from __future__ import annotations

import json
import secrets
import time
from pathlib import Path
from typing import Any


class EditError(ValueError):
    pass


def edits_dir(data_root: Path, project_id: str) -> Path:
    path = Path(data_root) / "projects" / project_id / "edits"
    path.mkdir(parents=True, exist_ok=True)
    return path


def edit_path(data_root: Path, project_id: str, edit_id: str) -> Path:
    if not edit_id.startswith("ed_") or "/" in edit_id:
        raise EditError("Invalid edit id.")
    return edits_dir(data_root, project_id) / f"{edit_id}.json"


def _clip(scene: dict | None, start: float, end: float, role: str = "body") -> dict:
    return {
        "scene": (scene or {}).get("id"),
        "start": round(float(start), 3),
        "end": round(float(max(start, end)), 3),
        "dur": round(float(max(0.0, end - start)), 3),
        "role": role,
    }


def _full_clips(check: dict) -> list[dict]:
    scenes = [item for item in check.get("scenes") or [] if isinstance(item, dict)]
    if scenes:
        return [
            _clip(scene, float(scene.get("start") or 0.0), float(scene.get("end") or 0.0))
            for scene in scenes
            if float(scene.get("end") or 0.0) > float(scene.get("start") or 0.0)
        ]
    meta = check.get("meta") or {}
    duration = float(meta.get("duration") or 0.0)
    return [_clip(None, 0.0, duration)] if duration > 0 else []


def create_full(project_id: str, check: dict, data_root: Path) -> dict:
    now = time.time()
    edit_id = f"ed_{secrets.token_hex(6)}"
    meta = check.get("meta") or {}
    duration = float(meta.get("duration") or 0.0)
    edit = {
        "schema": 1,
        "id": edit_id,
        "project_id": project_id,
        "kind": "full",
        "title": "Full video",
        "created": now,
        "updated": now,
        "source": {
            "fingerprint": meta.get("fingerprint") or "",
            "duration": duration,
            "width": int(meta.get("width") or 0),
            "height": int(meta.get("height") or 0),
            "fps": float(meta.get("fps") or 0.0),
        },
        "start": 0.0,
        "end": round(duration, 3),
        "clips": _full_clips(check),
        "clean": [],
        "captions": None,
        "audio": {"mode": "original"},
    }
    save_edit(edit, data_root)
    return edit


def create_story(
    project_id: str,
    check: dict,
    data_root: Path,
    *,
    story_id: str = "",
    start: float | None = None,
    end: float | None = None,
    title: str = "",
) -> dict:
    story = None
    if story_id:
        for item in (check.get("stories") or {}).get("stories") or []:
            if str(item.get("id")) == story_id:
                story = item
                break
        if story is None:
            raise EditError("Story not found in this check.")

    if story is not None:
        start = float(story.get("start") or 0.0)
        end = float(story.get("end") or 0.0)
        clips = [
            _clip(
                {"id": clip.get("scene")} if clip.get("scene") is not None else None,
                float(clip.get("start") or 0.0),
                float(clip.get("end") or 0.0),
                str(clip.get("role") or "body"),
            )
            for clip in story.get("clips") or []
            if float(clip.get("end") or 0.0) > float(clip.get("start") or 0.0)
        ]
        title = title or str(story.get("title") or "Smart story")
    else:
        meta = check.get("meta") or {}
        duration = float(meta.get("duration") or 0.0)
        start = max(0.0, float(start if start is not None else 0.0))
        end = min(duration, float(end if end is not None else duration))
        if end <= start:
            raise EditError("Story end must be after its start.")
        clips = [_clip(None, start, end)]
        title = title or "Story"

    if not clips:
        raise EditError("This story has no clips.")

    now = time.time()
    edit_id = f"ed_{secrets.token_hex(6)}"
    meta = check.get("meta") or {}
    edit = {
        "schema": 1,
        "id": edit_id,
        "project_id": project_id,
        "kind": "story",
        "story_id": story_id or "",
        "title": title[:120],
        "created": now,
        "updated": now,
        "source": {
            "fingerprint": meta.get("fingerprint") or "",
            "duration": float(meta.get("duration") or 0.0),
            "width": int(meta.get("width") or 0),
            "height": int(meta.get("height") or 0),
            "fps": float(meta.get("fps") or 0.0),
        },
        "start": round(float(start or 0.0), 3),
        "end": round(float(end or 0.0), 3),
        "clips": clips,
        "clean": [],
        "captions": None,
        "audio": {"mode": "original"},
    }
    save_edit(edit, data_root)
    return edit


def create_story_from_scenes(
    project_id: str,
    check: dict,
    data_root: Path,
    *,
    scene_ids: list[int],
    title: str = "",
) -> dict:
    by_id = {
        int(scene.get("id")): scene
        for scene in check.get("scenes") or []
        if isinstance(scene, dict) and scene.get("id") is not None
    }
    ordered = [by_id[int(scene_id)] for scene_id in scene_ids if int(scene_id) in by_id]
    if not ordered:
        raise EditError("Select at least one scene for the story.")
    clips = [
        _clip(scene, float(scene.get("start") or 0.0), float(scene.get("end") or 0.0))
        for scene in ordered
        if float(scene.get("end") or 0.0) > float(scene.get("start") or 0.0)
    ]
    if not clips:
        raise EditError("The selected scenes have no usable duration.")
    duration = sum(float(clip.get("dur") or 0.0) for clip in clips)
    meta = check.get("meta") or {}
    now = time.time()
    edit_id = f"ed_{secrets.token_hex(6)}"
    edit = {
        "schema": 1,
        "id": edit_id,
        "project_id": project_id,
        "kind": "story",
        "story_id": "selected-scenes",
        "scene_ids": [int(scene.get("id")) for scene in ordered],
        "title": (title or "Selected scenes")[:120],
        "created": now,
        "updated": now,
        "source": {
            "fingerprint": meta.get("fingerprint") or "",
            "duration": float(meta.get("duration") or 0.0),
            "width": int(meta.get("width") or 0),
            "height": int(meta.get("height") or 0),
            "fps": float(meta.get("fps") or 0.0),
        },
        "start": 0.0,
        "end": round(duration, 3),
        "clips": clips,
        "clean": [],
        "captions": None,
        "audio": {"mode": "original"},
    }
    save_edit(edit, data_root)
    return edit


def split_at(edit: dict, data_root: Path, output_time: float) -> dict:
    """Split the clip under an output-timeline time into two clips."""
    time_value = max(0.0, float(output_time))
    clips = [clip for clip in edit.get("clips") or [] if isinstance(clip, dict)]
    if not clips:
        raise EditError("This edit has no clips.")
    cursor = 0.0
    for index, clip in enumerate(clips):
        start = float(clip.get("start") or 0.0)
        end = float(clip.get("end") or 0.0)
        duration = max(0.0, end - start)
        if time_value < cursor + duration - 0.02:
            offset = max(0.02, time_value - cursor)
            split = start + offset
            if split <= start + 0.02 or split >= end - 0.02:
                raise EditError("Move the playhead inside a clip to split it.")
            first = _clip({"id": clip.get("scene")}, start, split, str(clip.get("role") or "body"))
            second = _clip({"id": clip.get("scene")}, split, end, str(clip.get("role") or "body"))
            clips[index:index + 1] = [first, second]
            edit["clips"] = clips
            if edit.get("kind") != "story":
                edit["end"] = max(float(edit.get("end") or 0.0), end)
            save_edit(edit, data_root)
            return edit
        cursor += duration
    raise EditError("Move the playhead inside a clip to split it.")


def ensure_audio_tracks(edit: dict) -> list[dict]:
    if isinstance(edit.get("audio_tracks"), list):
        return edit["audio_tracks"]
    rows = []
    dub = edit.get("dub")
    voice = edit.get("voice")
    music = edit.get("music")
    if isinstance(dub, dict):
        dub.setdefault("id", f"at_{secrets.token_hex(5)}")
        rows.append({
            "id": dub["id"], "kind": "dub",
            "name": dub.get("voice") or "Dub", "audio": dub.get("audio"),
            "duration": dub.get("duration") or 0.0, "start": 0.0,
            "volume": 1.0, "mode": "voice_only",
        })
    if isinstance(voice, dict):
        voice.setdefault("id", f"at_{secrets.token_hex(5)}")
        rows.append({
            "id": voice["id"], "kind": "voice",
            "name": voice.get("voice") or "Voice-over", "audio": voice.get("audio"),
            "duration": voice.get("duration") or 0.0, "start": 0.0,
            "volume": 1.0, "mode": voice.get("mode") or "voice_over",
            "engine": voice.get("engine") or "",
        })
    if isinstance(music, dict):
        music.setdefault("id", f"at_{secrets.token_hex(5)}")
        rows.append({
            "id": music["id"], "kind": "music",
            "name": music.get("name") or "Music", "audio": music.get("audio"),
            "duration": music.get("duration") or 0.0, "start": 0.0,
            "volume": float(music.get("volume") or 0.25),
        })
    edit["audio_tracks"] = rows
    return rows


def remove_audio_track(edit: dict, track_id: str) -> list[dict]:
    rows = ensure_audio_tracks(edit)
    remaining = [row for row in rows if str(row.get("id")) != str(track_id)]
    if len(remaining) == len(rows):
        raise KeyError(track_id)
    edit["audio_tracks"] = remaining
    for key in ("voice", "dub", "music"):
        item = edit.get(key)
        if isinstance(item, dict) and str(item.get("id")) == str(track_id):
            edit.pop(key, None)
    return remaining


def slip_clip(edit: dict, data_root: Path, clip_index: int, delta: float) -> dict:
    clips = [clip for clip in edit.get("clips") or [] if isinstance(clip, dict)]
    if clip_index < 0 or clip_index >= len(clips):
        raise EditError("Clip not found.")
    clip = clips[clip_index]
    start = float(clip.get("start") or 0.0)
    end = float(clip.get("end") or 0.0)
    duration = max(0.0, end - start)
    if duration <= 0:
        raise EditError("This clip has no duration.")
    source_duration = float((edit.get("source") or {}).get("duration") or end)
    lower = float(clips[clip_index - 1].get("end") or 0.0) if clip_index else 0.0
    upper = float(clips[clip_index + 1].get("start") or source_duration) if clip_index + 1 < len(clips) else source_duration
    new_start = max(lower, min(upper - duration, start + float(delta)))
    if abs(new_start - start) < 0.001:
        raise EditError("The clip is already at its slip limit.")
    clip["start"] = round(new_start, 3)
    clip["end"] = round(new_start + duration, 3)
    clip["dur"] = round(duration, 3)
    edit["clips"] = clips
    save_edit(edit, data_root)
    return edit


def save_edit(edit: dict, data_root: Path) -> dict:
    edit["updated"] = time.time()
    path = edit_path(data_root, str(edit["project_id"]), str(edit["id"]))
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(edit, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)
    return edit


def get_edit(data_root: Path, project_id: str, edit_id: str) -> dict:
    path = edit_path(data_root, project_id, edit_id)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise KeyError(edit_id) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise EditError("Edit file is unreadable.") from exc
    if not isinstance(value, dict):
        raise EditError("Edit file is not an object.")
    return value


def list_edits(data_root: Path, project_id: str) -> list[dict]:
    rows = []
    for path in edits_dir(data_root, project_id).glob("ed_*.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            rows.append({
                "id": value.get("id"),
                "kind": value.get("kind"),
                "title": value.get("title"),
                "story_id": value.get("story_id"),
                "start": value.get("start"),
                "end": value.get("end"),
                "clean": len(value.get("clean") or []),
                "updated": value.get("updated"),
            })
    rows.sort(key=lambda item: float(item.get("updated") or 0.0), reverse=True)
    return rows
