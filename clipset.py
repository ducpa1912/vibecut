"""Transcript-native clip sets: 3-6 non-overlapping stories per source.

A clip set is deliberately smaller than a timeline editor and larger than one
reel. Each story starts on a sentence boundary, opens on its first sentence,
and ends on a terminal payoff sentence. Stories are scored with six observable
signals, then selected greedily with a non-overlap rule and a proximity
penalty. The score describes the cut we can see; it is not a reach prediction.
"""

from __future__ import annotations

import copy
import math
import re
from typing import Iterable

from pipeline import hook_text_score

MIN_STORY_S = 20.0
MAX_STORY_S = 75.0
MIN_STORIES = 3
MAX_STORIES = 6
STORY_WEIGHTS = {
    "hook_score": 0.26,
    "speech_coherence": 0.22,
    "audio_energy": 0.13,
    "visual_quality": 0.13,
    "payoff_position": 0.14,
    "novelty": 0.12,
}
ORDERS = ("source", "score", "arc")
EVIDENCE_TYPES = ("transcript", "visual", "audio", "structure")


class ClipSetError(ValueError):
    """Invalid clip-set parameters or edit."""


_SENTENCE_SPLIT = re.compile(r"(?<=[。！？])\s*|(?<=[.!?])\s+")
_DANGLING = {
    "a", "an", "and", "as", "at", "because", "but", "by", "for", "from",
    "however", "if", "in", "into", "like", "of", "on", "or", "so", "than",
    "that", "the", "then", "to", "which", "while", "with", "yet",
}
_STOPWORDS = {
    "about", "after", "again", "also", "because", "been", "before", "being",
    "both", "could", "does", "doing", "done", "from", "have", "having",
    "here", "into", "just", "more", "most", "much", "only", "other", "over",
    "same", "should", "some", "such", "than", "that", "their", "them", "then",
    "there", "these", "they", "this", "those", "through", "under", "very",
    "what", "when", "where", "which", "while", "will", "with", "would",
    "your", "you", "the", "and", "for", "are", "was", "were", "has", "had",
}


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if math.isfinite(number) else fallback


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _clean(text: str) -> str:
    return " ".join(str(text or "").split())


def _clip_text(value: str, limit: int = 64) -> str:
    text = _clean(value)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def _split_text(text: str) -> list[str]:
    value = _clean(text)
    if not value:
        return []
    return [part.strip() for part in _SENTENCE_SPLIT.split(value) if part and part.strip()]


def _terminal_text(text: str) -> bool:
    value = _clean(text)
    if not value:
        return False
    if re.search(r"[,;:，、；：\-–—]$", value):
        return False
    words = re.findall(r"[A-Za-z']+", value)
    if words and words[-1].lower() in _DANGLING:
        return False
    return True


def _scene_for_span(start: float, end: float, scenes: list[dict]) -> int | None:
    best_id: int | None = None
    best = 0.0
    for scene in scenes:
        overlap = _overlap(
            start, end,
            _safe_float(scene.get("start")),
            _safe_float(scene.get("end")),
        )
        if overlap > best:
            best = overlap
            best_id = scene.get("id")
    if best > 0.12:
        return best_id
    if not scenes:
        return None
    midpoint = (start + end) / 2
    nearest = min(
        scenes,
        key=lambda scene: abs(
            (_safe_float(scene.get("start")) + _safe_float(scene.get("end"))) / 2
            - midpoint
        ),
    )
    return nearest.get("id")


def _scene_span_ids(start: float, end: float, scenes: list[dict]) -> list[int]:
    ids = [
        int(scene["id"])
        for scene in scenes
        if _overlap(
            start, end,
            _safe_float(scene.get("start")),
            _safe_float(scene.get("end")),
        ) > 0.12
    ]
    if not ids:
        scene_id = _scene_for_span(start, end, scenes)
        if scene_id is not None:
            ids = [int(scene_id)]
    return sorted(set(ids))


def _timed_parts(
    text: str,
    start: float,
    end: float,
    scene: int | None,
    source: str,
    scenes: list[dict],
) -> list[dict]:
    parts = _split_text(text)
    if not parts or end <= start:
        return []
    total_chars = sum(max(1, len(part)) for part in parts)
    span = end - start
    cursor = start
    out: list[dict] = []
    for index, part in enumerate(parts):
        if index == len(parts) - 1:
            stop = end
        else:
            stop = cursor + span * len(part) / total_chars
        mid = (cursor + stop) / 2
        item_scene = scene if scene is not None else _scene_for_span(cursor, stop, scenes)
        item_scenes = [int(scene)] if scene is not None else _scene_span_ids(cursor, stop, scenes)
        if item_scenes:
            item_scene = item_scenes[0]
        out.append({
            "start": round(cursor, 3),
            "end": round(stop, 3),
            "text": part,
            "scene": item_scene,
            "scenes": item_scenes,
            "source": source,
            "mid": round(mid, 3),
        })
        cursor = stop
    return out


def source_sentences(
    scenes: Iterable[dict] | None,
    transcript_segments: Iterable[dict] | dict | None = None,
) -> list[dict]:
    """Return sentence units in source order.

    Transcript segments win when present. If they are absent, scene speech and
    on-screen text become the fallback units. Nothing is synthesized when both
    sources are empty.
    """
    scene_list = [
        scene for scene in (scenes or [])
        if _safe_float(scene.get("end")) > _safe_float(scene.get("start"))
    ]
    scene_list.sort(key=lambda scene: (_safe_float(scene.get("start")), scene.get("id")))
    raw: list[dict] = []

    if isinstance(transcript_segments, dict):
        transcript_segments = transcript_segments.get("segments") or []
    for segment in sorted(
        transcript_segments or [],
        key=lambda item: _safe_float(item.get("start")),
    ):
        text = _clean(segment.get("text"))
        if not text:
            continue
        start = _safe_float(segment.get("start"))
        end = _safe_float(segment.get("end"), start)
        if end <= start:
            end = start + 0.2
        scene = segment.get("scene")
        try:
            scene = int(scene) if scene is not None else None
        except (TypeError, ValueError):
            scene = None
        raw.extend(_timed_parts(text, start, end, scene, "transcript", scene_list))

    if not raw:
        for scene in scene_list:
            text = _clean(scene.get("speech") or scene.get("ocr"))
            if not text:
                continue
            try:
                scene_id = int(scene.get("id"))
            except (TypeError, ValueError):
                scene_id = None
            raw.extend(_timed_parts(
                text,
                _safe_float(scene.get("start")),
                _safe_float(scene.get("end")),
                scene_id,
                "scene",
                scene_list,
            ))

    raw.sort(key=lambda item: (
        _safe_float(item.get("start")),
        _safe_float(item.get("end")),
        -1 if item.get("scene") is None else int(item["scene"]),
        str(item.get("text") or ""),
    ))
    deduped: list[dict] = []
    for item in raw:
        if not item.get("text"):
            continue
        if deduped:
            previous = deduped[-1]
            if (
                previous.get("text") == item.get("text")
                and abs(_safe_float(previous.get("start")) - _safe_float(item.get("start"))) < 0.05
                and previous.get("scene") == item.get("scene")
            ):
                continue
        item["id"] = len(deduped)
        item["dur"] = round(
            max(0.0, _safe_float(item.get("end")) - _safe_float(item.get("start"))),
            3,
        )
        deduped.append(item)
    return deduped[:4000]


def _sentence_ids(story: dict) -> list[int]:
    ids: list[int] = []
    for sentence in story.get("sentences") or []:
        try:
            ids.append(int(sentence.get("id")))
        except (TypeError, ValueError):
            continue
    return ids


def _story_scene_ids(sentences: list[dict]) -> list[int]:
    ids: set[int] = set()
    for sentence in sentences:
        for value in sentence.get("scenes") or []:
            try:
                ids.add(int(value))
            except (TypeError, ValueError):
                continue
        scene = sentence.get("scene")
        if scene is not None:
            try:
                ids.add(int(scene))
            except (TypeError, ValueError):
                pass
    return sorted(ids)


def _story_duration(sentences: list[dict]) -> float:
    return round(sum(max(0.0, _safe_float(item.get("dur"))) for item in sentences), 3)


def _scene_mean(
    scene_ids: Iterable[int],
    by_id: dict[int, dict],
    key: str,
    default: float = 50.0,
) -> float:
    values: list[float] = []
    for scene_id in scene_ids:
        scene = by_id.get(scene_id)
        if scene is None:
            continue
        value = _safe_float(scene.get(key), default) / 100.0
        values.append(_clamp(value))
    if not values:
        return 0.5
    return sum(values) / len(values)


def _keyword_set(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9']+|[\u4e00-\u9fff]{2,}", (text or "").lower())
    return {word for word in words if len(word) > 2 and word not in _STOPWORDS}


def _story_text(story: dict) -> str:
    parts = [str(story.get("title") or "")]
    for sentence in story.get("sentences") or []:
        parts.append(str(sentence.get("text") or ""))
    return " ".join(part for part in parts if part)


def _novelty(story: dict, selected: list[dict]) -> float:
    if not selected:
        return 1.0
    duration = max(0.001, _safe_float(story.get("dur")))
    start = _safe_float(story.get("start"))
    end = _safe_float(story.get("end"))
    overlap = 0.0
    for other in selected:
        overlap += _overlap(
            start, end,
            _safe_float(other.get("start")),
            _safe_float(other.get("end")),
        )
    temporal = 1.0 - _clamp(overlap / duration)
    words = _keyword_set(_story_text(story))
    best = 0.0
    for other in selected:
        other_words = _keyword_set(_story_text(other))
        if not words or not other_words:
            continue
        best = max(best, len(words & other_words) / len(words | other_words))
    lexical = 1.0 - best
    return round(_clamp(0.6 * temporal + 0.4 * lexical), 4)


def _proximity_penalty(story: dict, selected: list[dict]) -> float:
    if not selected:
        return 0.0
    gap = min(
        max(
            0.0,
            max(
                _safe_float(other.get("start")) - _safe_float(story.get("end")),
                _safe_float(story.get("start")) - _safe_float(other.get("end")),
            ),
        )
        for other in selected
    )
    return 0.06 * max(0.0, 1.0 - min(gap, 8.0) / 8.0)


def _speech_coherence(sentences: list[dict]) -> float:
    if not sentences:
        return 0.0
    total = max(0.001, sum(max(0.0, _safe_float(item.get("dur"))) for item in sentences))
    spoken = sum(
        max(0.0, _safe_float(item.get("dur")))
        for item in sentences if _clean(item.get("text"))
    )
    coverage = _clamp(spoken / total)
    complete = sum(1 for item in sentences if _terminal_text(item.get("text")))
    complete_ratio = complete / max(1, len(sentences))
    joined = " ".join(_clean(item.get("text")) for item in sentences)
    words = re.findall(r"[a-z0-9']+|[\u4e00-\u9fff]", joined.lower())
    variety = len(set(words)) / max(1, len(words))
    richness = _clamp((variety - 0.25) / 0.65)
    return round(_clamp(0.55 * coverage + 0.30 * complete_ratio + 0.15 * richness), 4)


def _hook_signal(sentences: list[dict], scene_ids: list[int], by_id: dict[int, dict]) -> float:
    text = _clean(sentences[0].get("text")) if sentences else ""
    text_score = _clamp(hook_text_score(text))
    scene_score = _scene_mean(scene_ids, by_id, "hook")
    return round(_clamp(0.70 * text_score + 0.30 * scene_score), 4)


def _payoff_signal(
    sentences: list[dict],
    end: float,
    source_duration: float,
) -> float:
    if not sentences:
        return 0.0
    terminal = 1.0 if _terminal_text(sentences[-1].get("text")) else 0.35
    source_duration = max(_safe_float(source_duration), end, 1.0)
    late = _clamp((end / source_duration) / 0.68)
    return round(_clamp(0.70 * terminal + 0.30 * late), 4)


def _score_story(
    story: dict,
    scenes: list[dict],
    source_duration: float,
    novelty: float = 1.0,
    build_evidence: bool = True,
) -> float:
    sentences = story.get("sentences") or []
    by_id = {
        int(scene["id"]): scene
        for scene in scenes
        if scene.get("id") is not None
    }
    scene_ids = [int(value) for value in story.get("scenes") or []]
    visual_values: list[float] = []
    audio_values: list[float] = []
    for scene_id in scene_ids:
        scene = by_id.get(scene_id)
        if scene is None:
            continue
        visual = _clamp(_safe_float(scene.get("visual_score"), 50.0) / 100.0)
        if scene.get("black"):
            visual *= 0.25
        elif scene.get("freeze"):
            visual *= 0.6
        visual_values.append(visual)
        audio_values.append(_clamp(_safe_float(scene.get("audio_score"), 50.0) / 100.0))
    visual = sum(visual_values) / len(visual_values) if visual_values else 0.5
    audio = sum(audio_values) / len(audio_values) if audio_values else 0.5
    signals = {
        "hook_score": _hook_signal(sentences, scene_ids, by_id),
        "speech_coherence": _speech_coherence(sentences),
        "audio_energy": round(audio, 4),
        "visual_quality": round(visual, 4),
        "payoff_position": _payoff_signal(
            sentences, _safe_float(story.get("end")), source_duration,
        ),
        "novelty": round(_clamp(novelty), 4),
    }
    total = sum(STORY_WEIGHTS[key] * signals[key] for key in STORY_WEIGHTS)
    story["score_breakdown"] = signals
    story["score"] = round(total * 100, 2)
    story["evidence"] = _story_evidence(story, scenes, signals) if build_evidence else []
    return total


def _story_evidence(story: dict, scenes: list[dict], signals: dict) -> list[dict]:
    sentences = story.get("sentences") or []
    if not sentences:
        return []
    first = sentences[0]
    last = sentences[-1]
    evidence = [
        {
            "type": "transcript",
            "text": f"Hook line: {_clip_text(first.get('text'), 120)}",
            "scene": first.get("scene"),
            "time": round(_safe_float(first.get("start")), 3),
        },
        {
            "type": "transcript",
            "text": f"Payoff line: {_clip_text(last.get('text'), 120)}",
            "scene": last.get("scene"),
            "time": round(_safe_float(last.get("start")), 3),
        },
    ]
    by_id = {int(scene["id"]): scene for scene in scenes if scene.get("id") is not None}
    scene_ids = [int(value) for value in story.get("scenes") or []]
    visual_scene = max(
        (by_id[scene_id] for scene_id in scene_ids if scene_id in by_id),
        key=lambda scene: _safe_float(scene.get("visual_score")),
        default=None,
    )
    if visual_scene is not None:
        evidence.append({
            "type": "visual",
            "text": (
                f"Visual quality {_safe_float(visual_scene.get('visual_score')):.0f}/100"
                + (" with a face" if visual_scene.get("face") else "")
                + ("; black frame" if visual_scene.get("black") else "")
            ),
            "scene": visual_scene.get("id"),
            "time": round(
                (_safe_float(visual_scene.get("start")) + _safe_float(visual_scene.get("end"))) / 2,
                3,
            ),
        })
    audio_scene = max(
        (by_id[scene_id] for scene_id in scene_ids if scene_id in by_id),
        key=lambda scene: _safe_float(scene.get("audio_score")),
        default=None,
    )
    if audio_scene is not None:
        evidence.append({
            "type": "audio",
            "text": f"Audio energy {_safe_float(audio_scene.get('audio_score')):.0f}/100",
            "scene": audio_scene.get("id"),
            "time": round(
                (_safe_float(audio_scene.get("start")) + _safe_float(audio_scene.get("end"))) / 2,
                3,
            ),
        })
    evidence.append({
        "type": "structure",
        "text": (
            f"{story.get('dur', 0):.1f}s story from "
            f"{_safe_float(story.get('start')):.1f}s to {_safe_float(story.get('end')):.1f}s; "
            f"terminal payoff at {signals.get('payoff_position', 0):.2f}."
        ),
        "scene": first.get("scene"),
        "time": round(_safe_float(first.get("start")), 3),
    })
    if signals.get("novelty", 1.0) < 0.999:
        evidence.append({
            "type": "structure",
            "text": f"Novelty {signals['novelty']:.2f} against earlier picks.",
            "scene": first.get("scene"),
            "time": round(_safe_float(first.get("start")), 3),
        })
    return evidence


def _clips_for_sentences(sentences: list[dict], scenes: list[dict]) -> list[dict]:
    by_id = {int(scene["id"]): scene for scene in scenes if scene.get("id") is not None}
    clips: list[dict] = []
    for sentence in sentences:
        start = _safe_float(sentence.get("start"))
        end = _safe_float(sentence.get("end"))
        if end <= start:
            continue
        scene_ids = sentence.get("scenes") or (
            [sentence.get("scene")] if sentence.get("scene") is not None else []
        )
        prepared: list[tuple[float, int, dict]] = []
        for scene_id in scene_ids:
            try:
                scene_id = int(scene_id)
            except (TypeError, ValueError):
                continue
            scene = by_id.get(scene_id)
            if scene is None:
                continue
            prepared.append((_safe_float(scene.get("start")), scene_id, scene))
        for _, scene_id, scene in sorted(prepared, key=lambda item: (item[0], item[1])):
            clip_start = max(start, _safe_float(scene.get("start")))
            clip_end = min(end, _safe_float(scene.get("end")))
            if clip_end - clip_start < 0.18:
                continue
            clips.append({
                "scene": scene_id,
                "start": round(clip_start, 3),
                "end": round(clip_end, 3),
                "dur": round(clip_end - clip_start, 3),
                "role": "beat",
                "why": f"Sentence {sentence.get('id')}: {_clip_text(sentence.get('text'), 72)}",
            })
    if not clips:
        return []
    clips[0]["role"] = "hook"
    if len(clips) > 1:
        clips[-1]["role"] = "payoff"
    return clips


def _story_from_sentences(
    sentences: list[dict],
    scenes: list[dict],
    source_duration: float,
    story_id: str,
    title: str | None = None,
    edited: bool = False,
    materialize: bool = True,
) -> dict | None:
    ordered = [dict(sentence) for sentence in sentences]
    if not ordered:
        return None
    start = min(_safe_float(item.get("start")) for item in ordered)
    end = max(_safe_float(item.get("end")) for item in ordered)
    duration = _story_duration(ordered)
    if duration <= 0:
        return None
    clips = _clips_for_sentences(ordered, scenes) if materialize else []
    hook = dict(ordered[0])
    payoff = dict(ordered[-1])
    story = {
        "id": story_id,
        "title": title or _clip_text(hook.get("text"), 64) or f"Story at {start:.1f}s",
        "start": round(start, 3),
        "end": round(end, 3),
        "dur": duration,
        "clips": clips,
        "sentences": ordered,
        "hook": hook,
        "payoff": payoff,
        "evidence": [],
        "score_breakdown": {},
        "score": 0.0,
        "scenes": _story_scene_ids(ordered),
    }
    if edited:
        story["edited"] = True
    _score_story(
        story, scenes, source_duration,
        novelty=1.0, build_evidence=materialize,
    )
    return story


def _candidate_end_indices(
    sentences: list[dict],
    start_index: int,
    min_s: float,
    max_s: float,
) -> list[int]:
    first = _safe_float(sentences[start_index].get("start"))
    ends: list[int] = []
    for index in range(start_index, len(sentences)):
        span = _safe_float(sentences[index].get("end")) - first
        if span < min_s:
            continue
        if span > max_s:
            break
        if _terminal_text(sentences[index].get("text")):
            ends.append(index)
    if len(ends) > 6:
        picks = sorted({
            ends[round(quantile * (len(ends) - 1))]
            for quantile in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
        })
        return picks
    return ends


def candidate_stories(
    sentences: list[dict],
    scenes: list[dict],
    source_duration: float,
    min_s: float = MIN_STORY_S,
    max_s: float = MAX_STORY_S,
    ban_scenes: Iterable[int] | None = None,
    limit: int = 20000,
) -> list[dict]:
    """Enumerate sentence-boundary stories, then reject banned scenes."""
    if not sentences or not scenes:
        return []
    banned = {int(value) for value in (ban_scenes or [])}
    candidates: list[dict] = []
    for start_index, first in enumerate(sentences):
        first_scene_ids = set(first.get("scenes") or [first.get("scene")])
        first_scene_ids.discard(None)
        if banned and first_scene_ids & banned:
            continue
        start = _safe_float(first.get("start"))
        if start + min_s > source_duration + 0.5:
            break
        for end_index in _candidate_end_indices(sentences, start_index, min_s, max_s):
            selected = sentences[start_index:end_index + 1]
            duration = _story_duration(selected)
            if duration < min_s - 0.001 or duration > max_s + 0.001:
                continue
            scene_ids = set(_story_scene_ids(selected))
            if banned and scene_ids & banned:
                continue
            story_id = (
                f"st_{int(round(start * 1000)):07d}_"
                f"{int(round(_safe_float(selected[-1].get('end')) * 1000)):07d}"
            )
            story = _story_from_sentences(
                selected, scenes, source_duration, story_id,
                materialize=False,
            )
            if story is None:
                continue
            candidates.append(story)
    if limit > 0 and len(candidates) > limit:
        step = (len(candidates) - 1) / max(1, limit - 1)
        candidates = [
            candidates[int(round(index * step))]
            for index in range(limit)
        ]
    return candidates


def _weighted_total(breakdown: dict, novelty: float) -> float:
    values = {key: _clamp(_safe_float(breakdown.get(key))) for key in STORY_WEIGHTS}
    values["novelty"] = _clamp(novelty)
    return sum(STORY_WEIGHTS[key] * values[key] for key in STORY_WEIGHTS)


def _capacity_after(
    story: dict,
    selected: list[dict],
    source_duration: float,
    min_s: float,
) -> int:
    spans = sorted(
        (_safe_float(item.get("start")), _safe_float(item.get("end")))
        for item in [*selected, story]
    )
    merged: list[list[float]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1] + 0.001:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    capacity = 0
    cursor = 0.0
    for start, end in merged:
        if start - cursor >= min_s - 0.001:
            capacity += int((start - cursor) // min_s)
        cursor = max(cursor, end)
    if source_duration - cursor >= min_s - 0.001:
        capacity += int((source_duration - cursor) // min_s)
    return capacity


def _pick_best(
    candidates: list[dict],
    selected: list[dict],
    source_duration: float,
    min_s: float,
    count: int,
    locked: bool = False,
) -> tuple[dict | None, float]:
    best: dict | None = None
    best_novelty = 1.0
    best_key: tuple[float, float, float, str] | None = None
    required = max(0, count - len(selected) - 1)
    for candidate in candidates:
        if _overlaps(candidate, selected):
            continue
        novelty = _novelty(candidate, selected)
        base = _weighted_total(candidate.get("score_breakdown") or {}, novelty)
        penalty = _proximity_penalty(candidate, selected)
        capacity = _capacity_after(candidate, selected, source_duration, min_s)
        shortfall = max(0, required - capacity)
        adjusted = base - penalty + (0.03 if locked else 0.0) - 0.08 * shortfall
        key = (
            round(adjusted, 9),
            round(base, 9),
            -_safe_float(candidate.get("start")),
            str(candidate.get("id") or ""),
        )
        if best_key is None or key > best_key:
            best = candidate
            best_novelty = novelty
            best_key = key
    return best, best_novelty


def _overlaps(story: dict, selected: list[dict]) -> bool:
    start = _safe_float(story.get("start"))
    end = _safe_float(story.get("end"))
    return any(
        _overlap(
            start, end,
            _safe_float(other.get("start")),
            _safe_float(other.get("end")),
        ) > 0.001
        for other in selected
    )


def _materialize_story(
    candidate: dict,
    scenes: list[dict],
    source_duration: float,
    novelty: float,
    locked: bool,
) -> dict:
    story = copy.deepcopy(candidate)
    story["clips"] = _clips_for_sentences(story.get("sentences") or [], scenes)
    story["title"] = (
        story.get("title")
        or _clip_text((story.get("hook") or {}).get("text"), 64)
        or f"Story at {_safe_float(story.get('start')):.1f}s"
    )
    _score_story(story, scenes, source_duration, novelty, build_evidence=True)
    story["locked"] = locked
    return story


def _select_stories(
    candidates: list[dict],
    count: int,
    scenes: list[dict],
    source_duration: float,
    locks: Iterable[int] | None = None,
    order: str = "source",
    min_s: float = MIN_STORY_S,
) -> list[dict]:
    effective_locks = {int(value) for value in (locks or [])}
    selected: list[dict] = []
    remaining = list(candidates)

    # A lock forces its best non-overlapping story in before ordinary ranking.
    for scene_id in sorted(effective_locks):
        if len(selected) >= count:
            break
        options = [
            story for story in remaining
            if scene_id in (story.get("scenes") or [])
            and not _overlaps(story, selected)
        ]
        best, novelty = _pick_best(
            options, selected, source_duration, min_s, count, locked=True,
        )
        if best is None:
            continue
        selected.append(_materialize_story(
            best, scenes, source_duration, novelty, locked=True,
        ))
        remaining = [item for item in remaining if item is not best]

    while len(selected) < count:
        best, novelty = _pick_best(
            remaining, selected, source_duration, min_s, count,
        )
        if best is None:
            break
        selected.append(_materialize_story(
            best,
            scenes,
            source_duration,
            novelty,
            locked=bool(set(best.get("scenes") or []) & effective_locks),
        ))
        remaining.remove(best)

    return _order_stories(selected, order)


def _order_stories(stories: list[dict], order: str) -> list[dict]:
    ordered = sorted(stories, key=lambda story: (
        _safe_float(story.get("start")),
        str(story.get("id") or ""),
    ))
    if order == "score":
        ordered.sort(key=lambda story: (
            -_safe_float(story.get("score")),
            _safe_float(story.get("start")),
            str(story.get("id") or ""),
        ))
    return ordered


def _validate_params(count: int, min_s: float, max_s: float, order: str) -> None:
    try:
        count = int(count)
    except (TypeError, ValueError):
        raise ClipSetError("count must be an integer from 3 to 6.") from None
    if count < MIN_STORIES or count > MAX_STORIES:
        raise ClipSetError("count must be an integer from 3 to 6.")
    min_s = _safe_float(min_s, MIN_STORY_S)
    max_s = _safe_float(max_s, MAX_STORY_S)
    if min_s < MIN_STORY_S or max_s > MAX_STORY_S or max_s < min_s:
        raise ClipSetError("min_s and max_s must fit inside 20-75 seconds.")
    if order not in ORDERS:
        raise ClipSetError("order must be source, score or arc.")


def build_clipset(
    scenes: list[dict],
    transcript_segments: Iterable[dict] | dict | None = None,
    source_duration: float | None = None,
    count: int = 3,
    min_s: float = MIN_STORY_S,
    max_s: float = MAX_STORY_S,
    locks: Iterable[int] | None = None,
    ban_scenes: Iterable[int] | None = None,
    order: str = "source",
) -> dict:
    """Build a clip-set document. Returns fewer stories, never filler."""
    _validate_params(count, min_s, max_s, order)
    scenes = list(scenes or [])
    duration = _safe_float(source_duration)
    if duration <= 0:
        duration = max(
            (_safe_float(scene.get("end")) for scene in scenes),
            default=0.0,
        )
    sentences = source_sentences(scenes, transcript_segments)
    banned = sorted({int(value) for value in (ban_scenes or [])})
    effective_locks = sorted({int(value) for value in (locks or [])} - set(banned))
    candidates = candidate_stories(
        sentences, scenes, duration, min_s, max_s, banned,
    )
    stories = _select_stories(
        candidates, int(count), scenes, duration, effective_locks, order, min_s,
    )
    for story in stories:
        story["locked"] = bool(set(story.get("scenes") or []) & set(effective_locks))

    used_transcript = any(item.get("source") == "transcript" for item in sentences)
    used_scene = any(item.get("source") == "scene" for item in sentences)
    note = None
    if not stories:
        if duration < min_s:
            note = (
                f"Source is {duration:.1f}s; a story needs at least "
                f"{_safe_float(min_s):.0f}s."
            )
        elif not sentences:
            note = "No transcript or scene text was available for a story."
        else:
            note = (
                f"No non-overlapping story of {_safe_float(min_s):.0f}-"
                f"{_safe_float(max_s):.0f}s was found."
            )
    elif len(stories) < int(count):
        note = (
            f"Only {len(stories)} non-overlapping stor"
            f"{'y' if len(stories) == 1 else 'ies'} fit; requested {int(count)}."
        )
    return {
        "requested": int(count),
        "min_s": round(_safe_float(min_s), 3),
        "max_s": round(_safe_float(max_s), 3),
        "order": order,
        "locks": effective_locks,
        "ban_scenes": banned,
        "excluded_sentences": [],
        "stories": stories,
        "available": len(stories),
        "candidate_count": len(candidates),
        "sentence_count": len(sentences),
        "source": {
            "transcript": used_transcript,
            "scene_text": used_scene,
            "fallback": "transcript" if used_transcript else ("scene_text" if used_scene else "none"),
        },
        "note": note,
        "warnings": [],
    }


def _parse_sentence_ids(value) -> list[int] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ClipSetError("sentences must be a list of sentence ids.")
    ids: list[int] = []
    seen: set[int] = set()
    for item in value:
        if isinstance(item, dict):
            item = item.get("id")
        if isinstance(item, bool):
            raise ClipSetError("Sentence ids must be integers.")
        try:
            sentence_id = int(item)
        except (TypeError, ValueError):
            raise ClipSetError("Sentence ids must be integers.") from None
        if sentence_id in seen:
            raise ClipSetError(f"Sentence {sentence_id} is repeated.")
        seen.add(sentence_id)
        ids.append(sentence_id)
    return ids


def apply_edits(
    document: dict,
    sentences_pool: list[dict],
    scenes: list[dict],
    source_duration: float,
    *,
    excluded_sentences: Iterable[int] | None = None,
    locks: Iterable[int] | None = None,
    ban_scenes: Iterable[int] | None = None,
    bans: Iterable[int] | None = None,
    story_patches: list[dict] | None = None,
    stories: list[dict] | None = None,
    order: str | None = None,
    min_s: float | None = None,
    max_s: float | None = None,
) -> dict:
    """Apply sentence select/reorder/exclude and scene lock/ban edits.

    Excludes remove a sentence from every story. A story patch controls the
    sentence order for that story. Bans always win: a banned scene is never
    kept, even when the same scene is locked.
    """
    value = copy.deepcopy(document)
    patches_from_param = list(story_patches or []) + list(stories or [])
    pool = {
        int(sentence["id"]): sentence
        for sentence in sentences_pool
        if sentence.get("id") is not None
    }
    excluded = {
        int(item) for item in (
            excluded_sentences
            if excluded_sentences is not None
            else value.get("excluded_sentences") or []
        )
    }
    requested_locks = {
        int(item) for item in (
            locks if locks is not None else value.get("locks") or []
        )
    }
    banned = (
        {int(item) for item in (value.get("ban_scenes") or [])}
        if ban_scenes is None and bans is None
        else (
            {int(item) for item in (ban_scenes or [])}
            | {int(item) for item in (bans or [])}
        )
    )
    effective_locks = requested_locks - banned
    if order is None:
        order = str(value.get("order") or "source")
    if order not in ORDERS:
        raise ClipSetError("order must be source, score or arc.")

    patches: dict[str, dict] = {}
    for patch in patches_from_param:
        if not isinstance(patch, dict) or not patch.get("id"):
            raise ClipSetError("Every story patch needs a story id.")
        patch_id = str(patch["id"])
        if patch_id in patches:
            raise ClipSetError(f"Story {patch_id} is patched twice.")
        patches[patch_id] = patch

    rebuilt: list[dict] = []
    for story in value.get("stories") or []:
        story_id = str(story.get("id"))
        patch = patches.pop(story_id, None)
        ids = _sentence_ids(story)
        if patch is not None and "sentences" in patch:
            ids = _parse_sentence_ids(patch.get("sentences")) or []
        ids = [sentence_id for sentence_id in ids if sentence_id not in excluded]
        ordered: list[dict] = []
        for sentence_id in ids:
            sentence = pool.get(sentence_id)
            if sentence is None:
                raise ClipSetError(f"Sentence {sentence_id} does not exist.")
            ordered.append(sentence)
        if not ordered:
            continue
        if banned and set(_story_scene_ids(ordered)) & banned:
            continue
        title = None
        if patch is not None and patch.get("title") is not None:
            title = _clean(patch.get("title")) or None
        next_story = _story_from_sentences(
            ordered,
            scenes,
            source_duration,
            story_id,
            title=title,
            edited=bool(patch),
        )
        if next_story is None:
            continue
        rebuilt.append(next_story)

    if patches:
        missing = next(iter(patches))
        raise ClipSetError(f"Story {missing} does not exist.")

    rebuilt.sort(key=lambda story: (
        _safe_float(story.get("start")),
        str(story.get("id") or ""),
    ))
    prior: list[dict] = []
    for story in rebuilt:
        novelty = _novelty(story, prior)
        _score_story(story, scenes, source_duration, novelty)
        story["locked"] = bool(set(story.get("scenes") or []) & effective_locks)
        prior.append(story)
    rebuilt = _order_stories(rebuilt, order)

    if min_s is not None:
        value["min_s"] = round(_safe_float(min_s), 3)
    if max_s is not None:
        value["max_s"] = round(_safe_float(max_s), 3)
    value["order"] = order
    value["excluded_sentences"] = sorted(excluded)
    value["locks"] = sorted(effective_locks)
    value["ban_scenes"] = sorted(banned)
    value["stories"] = rebuilt
    value["available"] = len(rebuilt)
    warnings: list[str] = []
    low = _safe_float(value.get("min_s"), MIN_STORY_S)
    high = _safe_float(value.get("max_s"), MAX_STORY_S)
    for story in rebuilt:
        duration = _safe_float(story.get("dur"))
        if duration < low - 0.001 or duration > high + 0.001:
            warnings.append(
                f"{story.get('id')} is {duration:.1f}s outside {low:.0f}-{high:.0f}s."
            )
    value["warnings"] = warnings
    requested = int(value.get("requested") or 0)
    if not rebuilt:
        value["note"] = "No story remains after the edit."
    elif len(rebuilt) < requested:
        value["note"] = (
            f"Only {len(rebuilt)} non-overlapping stor"
            f"{'y' if len(rebuilt) == 1 else 'ies'} remain; requested {requested}."
        )
    else:
        value["note"] = None
    return value


def story_to_plan(
    story: dict,
    scenes: list[dict],
    target: int | None = None,
    set_id: str | None = None,
) -> dict:
    """Map a story to the existing plan clip schema."""
    clips = copy.deepcopy(story.get("clips") or [])
    if not clips:
        clips = _clips_for_sentences(story.get("sentences") or [], scenes)
    total = round(sum(_safe_float(clip.get("dur")) for clip in clips), 3)
    if target is None:
        target = int(round(_safe_float(story.get("dur"), total)))
    target = max(1, min(180, int(target)))
    sentences = story.get("sentences") or []
    ids = _sentence_ids(story)
    source_order = ids == sorted(ids)
    roles = [str(clip.get("role") or "beat") for clip in clips]
    hook_why = (
        f"Story opens on sentence {story.get('hook', {}).get('id')}: "
        f"{_clip_text((story.get('hook') or {}).get('text'), 96)}"
    )
    payoff_why = (
        f"Story ends on sentence {story.get('payoff', {}).get('id')}: "
        f"{_clip_text((story.get('payoff') or {}).get('text'), 96)}"
    )
    source_span = {
        "start": round(_safe_float(story.get("start")), 3),
        "end": round(_safe_float(story.get("end")), 3),
    }
    evidence = [
        str(item.get("text"))
        for item in story.get("evidence") or []
        if item.get("text")
    ]
    plan = {
        "target": target,
        "total": total,
        "hook_scene": clips[0].get("scene") if clips else None,
        "auto": False,
        "clip_count": len(clips),
        "clips": clips,
        "note": f"Clip set story {story.get('id')}",
        "hook_why": hook_why,
        "payoff_why": payoff_why,
        "story_id": story.get("id"),
        "title": story.get("title"),
        "clip_set_id": set_id,
        "score_breakdown": story.get("score_breakdown") or {},
    }
    plan["reasoning"] = {
        "target": target,
        "source_duration": source_span["end"],
        "summary": (
            f"Clip-set story {story.get('id')} has {len(clips)} clip"
            f"{'s' if len(clips) != 1 else ''}, {total:.1f}s total. "
            "It starts on a sentence boundary and ends on its payoff sentence."
        ),
        "hook": {
            "headline": hook_why,
            "evidence": evidence[:2],
            "alternatives": [],
        },
        "structure": {
            "roles": roles,
            "clip_count": len(clips),
            "beat_count": sum(1 for role in roles if role == "beat"),
            "body_order": "source" if source_order else "manual",
            "body_in_source_order": source_order,
            "hook_first": bool(roles and roles[0] == "hook"),
            "source_span": source_span,
            "why": (
                "Sentence order is unchanged."
                if source_order
                else "Sentences were reordered for this story."
            ),
        },
        "payoff": {
            "headline": payoff_why,
            "evidence": evidence[-2:],
            "why_late": None,
            "position_pct": 100.0 if clips else None,
            "late_zone_pct": 68.0,
            "candidates": 1 if clips else 0,
        },
        "selection": {
            "strategy": (
                "Transcript story: sentence-boundary opening, non-overlapping "
                "body, terminal payoff."
            ),
            "evidence": evidence,
            "kept": [
                {
                    "scene": clip.get("scene"),
                    "role": clip.get("role"),
                    "start": clip.get("start"),
                    "end": clip.get("end"),
                    "dur": clip.get("dur"),
                    "why": clip.get("why"),
                    "evidence": [],
                }
                for clip in clips
            ],
            "target_budget": {
                "target": target,
                "source_duration": source_span["end"],
                "total": total,
                "headroom": round(max(0.0, target - total), 3),
                "over_target": round(max(0.0, total - target), 3),
            },
        },
    }
    return plan
