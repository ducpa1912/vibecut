"""Pure primitives for the atomic story trim transaction.

Nothing here touches the filesystem, the job store, requests or ffmpeg. The
routes in :mod:`routes_trim` own the transaction; this module owns the maths:

* the source-sentence pool between neighbouring stories;
* sentence-range validation (15-90 s, no neighbour overlap);
* output/source time mapping through the old and new clips;
* graphic layer ripple (moved, clipped, outside, pinned);
* the receipt shape and the undo token.

Time mapping rule (R2_TRIM_PLAN 2.2): output time maps to source time through
the **old** clips, then source time maps back to output time through the
**new** clips. Times outside a clip edge extrapolate from that edge, so a fully
outside layer is detected instead of silently clamped.
"""

from __future__ import annotations

import copy
import re
import uuid
from typing import Any, Iterable

MIN_STORY_S = 15.0
MAX_STORY_S = 90.0
POOL_WINDOW_S = 90.0
EPS = 0.001

STORY_PINS = ("source", "story_start", "story_end")
DEFAULT_PIN = "source"

_RECEIPT_RE = re.compile(r"^tr_[a-f0-9]{24}$")


class TrimRangeError(ValueError):
    """A range the caller asked for is not valid for this story."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------- stories


def story_revision(story: dict | None) -> int:
    """The story's revision; a missing value reads as 0."""
    try:
        return max(0, int((story or {}).get("revision") or 0))
    except (TypeError, ValueError, AttributeError):
        return 0


def sentence_ids(story: dict | None) -> list[int]:
    ids: list[int] = []
    for sentence in (story or {}).get("sentences") or []:
        try:
            ids.append(int(sentence.get("id")))
        except (TypeError, ValueError):
            continue
    return ids


def story_summary(story: dict | None) -> dict:
    """The compact story shape shared by GET trim and TrimResult."""
    story = story or {}
    return {
        "id": story.get("id"),
        "start": round(_number(story.get("start")), 3),
        "end": round(_number(story.get("end")), 3),
        "dur": round(_number(story.get("dur")), 3),
        "sentence_ids": sentence_ids(story),
    }


def range_signature(story: dict | None) -> tuple:
    """What counts as a range change for the revision rule."""
    story = story or {}
    return (
        round(_number(story.get("start")), 3),
        round(_number(story.get("end")), 3),
        round(_number(story.get("dur")), 3),
        tuple(sentence_ids(story)),
    )


def bump_revision(story: dict, previous: dict | None = None) -> dict:
    """Bump ``story``'s revision when its range changed from ``previous``."""
    value = dict(story)
    revision = story_revision(previous)
    if previous is None or range_signature(previous) != range_signature(value):
        revision += 1
    value["revision"] = revision
    return value


def with_revision(story: dict, revision: int) -> dict:
    value = copy.deepcopy(story)
    value["revision"] = max(0, int(revision))
    return value


# ---------------------------------------------------------------- pool


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(default)
    if number != number or number in (float("inf"), float("-inf")):
        return float(default)
    return number


def _span(sentence: dict) -> tuple[float, float]:
    start = _number(sentence.get("start"))
    end = _number(sentence.get("end"), start + _number(sentence.get("dur")))
    if end <= start:
        end = start + max(0.0, _number(sentence.get("dur")))
    return start, end


def neighbour_bounds(stories: Iterable[dict], story: dict) -> dict:
    """Nearest stories before and after ``story`` in source time."""
    story_id = str((story or {}).get("id") or "")
    start = _number((story or {}).get("start"))
    end = _number((story or {}).get("end"))
    before = None
    after = None
    for other in stories or []:
        if not isinstance(other, dict):
            continue
        if str(other.get("id") or "") == story_id:
            continue
        other_start = _number(other.get("start"))
        other_end = _number(other.get("end"))
        if other_end <= start + EPS:
            if before is None or other_end > _number(before.get("end")):
                before = other
        elif other_start >= end - EPS:
            if after is None or other_start < _number(after.get("start")):
                after = other
    return {
        "before": (
            {"id": before.get("id"), "end": round(_number(before.get("end")), 3)}
            if before else None
        ),
        "after": (
            {"id": after.get("id"), "start": round(_number(after.get("start")), 3)}
            if after else None
        ),
        "_before": before,
        "_after": after,
    }


def build_pool(
    sentences: Iterable[dict],
    stories: Iterable[dict],
    story: dict,
    *,
    window_s: float = POOL_WINDOW_S,
) -> tuple[list[dict], dict]:
    """Source sentences the story may grow or shrink into.

    The pool is one contiguous slice of the source sentence list. It starts at
    the previous story's end (or the start of the source) and stops at the next
    story's start, capped at ``window_s`` seconds on each side of the current
    range. Current story sentences are always included.
    """
    rows = [
        sentence for sentence in (sentences or [])
        if isinstance(sentence, dict) and sentence.get("id") is not None
    ]
    rows.sort(key=lambda item: (_span(item)[0], _number(item.get("id"))))
    bounds = neighbour_bounds(stories, story)
    before = bounds["_before"]
    after = bounds["_after"]
    low = _number(before.get("end")) if before else float("-inf")
    high = _number(after.get("start")) if after else float("inf")
    current_start = _number(story.get("start"))
    current_end = _number(story.get("end"))
    window_low = current_start - max(0.0, float(window_s))
    window_high = current_end + max(0.0, float(window_s))
    current_ids = set(sentence_ids(story))

    eligible: list[int] = []
    for index, sentence in enumerate(rows):
        start, end = _span(sentence)
        try:
            sentence_id = int(sentence.get("id"))
        except (TypeError, ValueError):
            continue
        inside_bounds = start >= low - EPS and end <= high + EPS
        inside_window = end >= window_low - EPS and start <= window_high + EPS
        if sentence_id in current_ids or (inside_bounds and inside_window):
            eligible.append(index)
    if not eligible:
        return [], bounds

    first = min(eligible)
    last = max(eligible)
    pool: list[dict] = []
    for index in range(first, last + 1):
        sentence = rows[index]
        start, end = _span(sentence)
        pool.append({
            "id": sentence.get("id"),
            "start": round(start, 3),
            "end": round(end, 3),
            "dur": round(max(0.0, end - start), 3),
            "text": str(sentence.get("text") or ""),
        })
    return pool, bounds


# ---------------------------------------------------------------- range


def validate_range(
    pool: list[dict],
    start_sentence: int,
    end_sentence: int,
    *,
    before: dict | None = None,
    after: dict | None = None,
    min_s: float = MIN_STORY_S,
    max_s: float = MAX_STORY_S,
) -> dict:
    """Validate one contiguous sentence range and return its span."""
    index = {}
    for position, sentence in enumerate(pool or []):
        try:
            index[int(sentence.get("id"))] = position
        except (TypeError, ValueError):
            continue
    try:
        start_id = int(start_sentence)
        end_id = int(end_sentence)
    except (TypeError, ValueError) as exc:
        raise TrimRangeError("range_invalid", "Sentence bounds must be integers.") from exc
    if start_id not in index or end_id not in index:
        raise TrimRangeError(
            "range_invalid",
            "The requested sentences are not in this story's source pool.",
        )
    first = index[start_id]
    last = index[end_id]
    if first > last:
        raise TrimRangeError(
            "range_invalid",
            "start_sentence must come before end_sentence in the source.",
        )
    selected = pool[first:last + 1]
    start = min(_number(item.get("start")) for item in selected)
    end = max(_number(item.get("end")) for item in selected)
    duration = round(sum(
        max(0.0, _number(item.get("dur"), _number(item.get("end")) - _number(item.get("start"))))
        for item in selected
    ), 3)
    if duration < float(min_s) - EPS:
        raise TrimRangeError(
            "too_short",
            f"The trimmed story is {duration:.1f}s; the minimum is {float(min_s):.0f}s.",
        )
    if duration > float(max_s) + EPS:
        raise TrimRangeError(
            "too_long",
            f"The trimmed story is {duration:.1f}s; the maximum is {float(max_s):.0f}s.",
        )
    if before is not None and start < _number(before.get("end")) - EPS:
        raise TrimRangeError(
            "overlaps_neighbour",
            "The range overlaps the story before it.",
        )
    if after is not None and end > _number(after.get("start")) + EPS:
        raise TrimRangeError(
            "overlaps_neighbour",
            "The range overlaps the story after it.",
        )
    return {
        "start_sentence": start_id,
        "end_sentence": end_id,
        "sentences": selected,
        "start": round(start, 3),
        "end": round(end, 3),
        "duration": duration,
    }


# ---------------------------------------------------------------- time map


def timeline(clips: Iterable[dict] | None) -> float:
    """Output duration: the sum of rendered clip durations."""
    total = 0.0
    for clip in clips or []:
        if not isinstance(clip, dict):
            continue
        start = _number(clip.get("start"))
        end = _number(clip.get("end"), start + _number(clip.get("dur")))
        duration = _number(
            clip.get("dur", clip.get("duration")),
            end - start,
        )
        total += max(0.0, duration)
    return round(total, 3)


def out_to_source(time_value: float, clips: Iterable[dict] | None) -> float:
    """Map output time to source time through one clip list."""
    value = [
        clip for clip in (clips or [])
        if isinstance(clip, dict)
    ]
    if not value:
        return float(time_value)
    first = value[0]
    last = value[-1]
    first_start = _number(first.get("start"))
    last_start = _number(last.get("start"))
    last_end = _number(last.get("end"), last_start + _number(last.get("dur")))
    t = float(time_value)
    if t <= 0:
        return first_start + t
    cursor = 0.0
    for clip in value:
        start = _number(clip.get("start"))
        end = _number(clip.get("end"), start + _number(clip.get("dur")))
        duration = max(0.0, _number(
            clip.get("dur", clip.get("duration")), end - start,
        ))
        if t <= cursor + duration + EPS:
            return start + max(0.0, min(duration, t - cursor))
        cursor += duration
    total = timeline(value)
    return last_end + (t - total)


def source_to_out(time_value: float, clips: Iterable[dict] | None) -> float:
    """Map source time to output time through one clip list."""
    value = [
        clip for clip in (clips or [])
        if isinstance(clip, dict)
    ]
    if not value:
        return float(time_value)
    source = float(time_value)
    first = value[0]
    last = value[-1]
    first_start = _number(first.get("start"))
    if source <= first_start:
        return source - first_start
    cursor = 0.0
    previous_end = None
    for clip in value:
        start = _number(clip.get("start"))
        end = _number(clip.get("end"), start + _number(clip.get("dur")))
        duration = max(0.0, _number(
            clip.get("dur", clip.get("duration")), end - start,
        ))
        if previous_end is not None and source < start - EPS:
            return cursor
        if start - EPS <= source <= end + EPS:
            return cursor + max(0.0, min(duration, source - start))
        cursor += duration
        previous_end = end
    last_end = _number(
        last.get("end"),
        _number(last.get("start")) + _number(last.get("dur")),
    )
    return timeline(value) + (source - last_end)


def map_time(
    time_value: float,
    old_clips: Iterable[dict] | None,
    new_clips: Iterable[dict] | None,
) -> float:
    """Output time -> source through old clips -> output through new clips."""
    return source_to_out(out_to_source(time_value, old_clips), new_clips)


# ---------------------------------------------------------------- ripple


def layer_pin(layer: dict) -> str:
    """A layer's story pin; ``source`` when absent."""
    if not isinstance(layer, dict):
        return DEFAULT_PIN
    value = str(layer.get("pin") or "").strip().lower().replace("-", "_")
    if value in STORY_PINS:
        return value
    # Accept the plan's ``anchor`` spelling as an alias. A positional anchor
    # such as "bottom-center" is not a pin and keeps its old meaning.
    alias = str(layer.get("anchor") or "").strip().lower().replace("-", "_")
    if alias in STORY_PINS:
        return alias
    return DEFAULT_PIN


def ripple_graphics(
    graphics: Iterable[dict] | None,
    old_clips: Iterable[dict] | None,
    new_clips: Iterable[dict] | None,
    *,
    old_duration: float | None = None,
    new_duration: float | None = None,
) -> tuple[list[dict], dict]:
    """Ripple text and graphic layers from the old range to the new one.

    Returns ``(layers, receipt_layers)``. Layers are never deleted: a layer
    fully outside the new range keeps its old times and gains ``hidden: true``.
    """
    old_total = timeline(old_clips) if old_duration is None else _number(old_duration)
    new_total = timeline(new_clips) if new_duration is None else _number(new_duration)
    moved: list[Any] = []
    clipped: list[Any] = []
    outside: list[Any] = []
    pinned: list[Any] = []
    result: list[dict] = []
    for raw in graphics or []:
        if not isinstance(raw, dict):
            continue
        item = copy.deepcopy(raw)
        layer_id = item.get("id")
        if item.get("hidden"):
            outside.append(layer_id)
            result.append(item)
            continue
        pin = layer_pin(item)
        if pin == "story_start":
            # Keep the offset from time 0. The card is never moved by a trim.
            pinned.append(layer_id)
            result.append(item)
            continue
        if pin == "story_end":
            offset_start = old_total - _number(item.get("start"))
            offset_end = old_total - _number(item.get("end"))
            item["start"] = round(
                min(new_total, max(0.0, new_total - offset_start)), 3,
            )
            item["end"] = round(
                min(new_total, max(0.0, new_total - offset_end)), 3,
            )
            if item["end"] <= item["start"]:
                item["end"] = round(min(new_total, item["start"] + 0.001), 3)
            pinned.append(layer_id)
            result.append(item)
            continue

        start = _number(item.get("start"))
        end = _number(item.get("end"), start)
        mapped_start = map_time(start, old_clips, new_clips)
        mapped_end = map_time(end, old_clips, new_clips)
        if mapped_end <= EPS or mapped_start >= new_total - EPS:
            item["hidden"] = True
            outside.append(layer_id)
            result.append(item)
            continue
        if mapped_start < -EPS or mapped_end > new_total + EPS:
            item["start"] = round(max(0.0, mapped_start), 3)
            item["end"] = round(min(new_total, mapped_end), 3)
            if item["end"] <= item["start"]:
                item["hidden"] = True
                outside.append(layer_id)
            else:
                clipped.append(layer_id)
            result.append(item)
            continue
        item["start"] = round(mapped_start, 3)
        item["end"] = round(mapped_end, 3)
        moved.append(layer_id)
        result.append(item)
    return result, {
        "moved": moved,
        "clipped": clipped,
        "outside": outside,
        "pinned": pinned,
    }


def empty_layer_receipt() -> dict:
    return {"moved": [], "clipped": [], "outside": [], "pinned": []}


def merge_layer_receipt(target: dict, source: dict) -> dict:
    for key in ("moved", "clipped", "outside", "pinned"):
        target.setdefault(key, [])
        for value in source.get(key) or []:
            if value not in target[key]:
                target[key].append(value)
    return target


# ---------------------------------------------------------------- receipt


def new_receipt_id() -> str:
    return "tr_" + uuid.uuid4().hex[:24]


def validate_receipt_id(value: str) -> str:
    text = str(value or "").strip()
    if not _RECEIPT_RE.match(text):
        raise TrimRangeError("range_invalid", "Undo token is not valid.")
    return text


def undo_token(receipt_id: str) -> str:
    """The undo token is the receipt id; undo writes a new receipt."""
    return validate_receipt_id(receipt_id)


def make_receipt(
    *,
    receipt_id: str,
    at: float,
    kind: str,
    job_id: str,
    set_id: str,
    story_id: str,
    old_story: dict,
    new_story: dict,
    old_revision: int,
    new_revision: int,
    layers: dict | None = None,
    captions: dict | None = None,
    before_edits: dict | None = None,
    after_edits: dict | None = None,
    before_caption: str | None = None,
    after_caption: str | None = None,
    invalidated_artifacts: Iterable[str] | None = None,
) -> dict:
    """Build the receipt that holds the full before state for undo."""
    value = copy.deepcopy(new_story or {})

    def receipt_range(story: dict) -> dict:
        ids = sentence_ids(story)
        return {
            "start_sentence": ids[0] if ids else None,
            "end_sentence": ids[-1] if ids else None,
            "start": round(_number(story.get("start")), 3),
            "end": round(_number(story.get("end")), 3),
            "dur": round(_number(story.get("dur")), 3),
        }

    old = receipt_range(old_story)
    new = receipt_range(value)
    return {
        "id": receipt_id,
        "at": round(float(at), 3),
        "kind": str(kind),
        "job_id": str(job_id),
        "set_id": str(set_id),
        "story_id": str(story_id),
        "revision": int(new_revision),
        "old": old,
        "new": new,
        "layers": {
            key: list((layers or {}).get(key) or [])
            for key in ("moved", "clipped", "outside", "pinned")
        },
        "captions": dict(captions or {}),
        "before": {
            "revision": int(old_revision),
            "story": copy.deepcopy(old_story),
            "edits": copy.deepcopy(before_edits or {}),
            "caption_track": before_caption or None,
        },
        "after": {
            "revision": int(new_revision),
            "edits": dict(after_edits or {}),
            "caption_track": after_caption or None,
        },
        "invalidated_artifacts": list(dict.fromkeys(
            str(item) for item in invalidated_artifacts or [] if item
        )),
        "stale_aspects": [],
    }
