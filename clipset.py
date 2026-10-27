"""Transcript-native clip sets: 3-6 non-overlapping stories per source.

A clip set is deliberately smaller than a timeline editor and larger than one
reel. Each story starts on a sentence boundary, opens on its first sentence,
and ends on a terminal payoff sentence. Stories are scored with six observable
signals, then selected greedily with a non-overlap rule and a proximity
penalty. The score describes the cut we can see; it is not a reach prediction.
"""

from __future__ import annotations

import bisect
import copy
import hashlib
import json
import math
import re
from typing import Iterable

from pipeline import hook_text_score

MIN_STORY_S = 20.0
MAX_STORY_S = 75.0
MIN_STORIES = 3
MAX_STORIES = 6
SENTENCE_LIMIT = 4000
CANDIDATE_LIMIT = 8000
STORY_WEIGHTS = {
    "hook_score": 0.26,
    "speech_coherence": 0.22,
    "audio_energy": 0.13,
    "visual_quality": 0.13,
    "payoff_position": 0.14,
    "novelty": 0.12,
}
ORDERS = ("source", "score", "arc")
EVIDENCE_TYPES = ("transcript", "scene", "visual", "audio", "structure")


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


class _SceneIndex:
    """Sorted scene lookup so sentence extraction does not rescan every scene."""

    def __init__(self, scenes: list[dict]):
        self.scenes = sorted(
            (
                scene for scene in scenes
                if _safe_float(scene.get("end")) > _safe_float(scene.get("start"))
            ),
            key=lambda scene: (_safe_float(scene.get("start")), scene.get("id")),
        )
        self.starts = [_safe_float(scene.get("start")) for scene in self.scenes]
        self.ends = [_safe_float(scene.get("end")) for scene in self.scenes]
        self.by_id = {
            int(scene["id"]): scene
            for scene in self.scenes
            if scene.get("id") is not None
        }

    def ids_for(self, start: float, end: float) -> list[int]:
        if not self.scenes or end <= start:
            return []
        index = max(0, bisect.bisect_right(self.starts, start) - 1)
        first = index
        while first > 0 and self.ends[first - 1] > start + 0.001:
            first -= 1
        ids: list[int] = []
        cursor = first
        while cursor < len(self.scenes) and self.starts[cursor] < end - 0.001:
            scene = self.scenes[cursor]
            overlap = _overlap(start, end, self.starts[cursor], self.ends[cursor])
            if overlap > 0.12:
                ids.append(int(scene["id"]))
            cursor += 1
        return sorted(set(ids))

    def primary(self, start: float, end: float) -> int | None:
        best_id: int | None = None
        best = 0.0
        for scene_id in self.ids_for(start, end):
            scene = self.by_id.get(scene_id)
            if scene is None:
                continue
            overlap = _overlap(
                start, end,
                _safe_float(scene.get("start")),
                _safe_float(scene.get("end")),
            )
            if overlap > best:
                best = overlap
                best_id = scene_id
        if best_id is not None:
            return best_id
        nearest = self.nearest(start, end)
        return None if nearest is None else int(nearest["id"])

    def nearest(self, start: float, end: float) -> dict | None:
        if not self.scenes:
            return None
        midpoint = (start + end) / 2
        return min(
            self.scenes,
            key=lambda scene: abs(
                (_safe_float(scene.get("start")) + _safe_float(scene.get("end"))) / 2
                - midpoint
            ),
        )


# A sentence cut starts this far before its first measured word (never
# before the previous sentence's last word), so the attack is not clipped.
WORD_LEAD_S = 0.08


def _word_boundaries(
    parts: list[str],
    words: list[dict] | None,
    start: float,
    end: float,
) -> list[float] | None:
    """Inner sentence edges placed on measured word edges, or None.

    Character-share timing guesses where each sentence of a multi-sentence
    segment starts. The guess lands mid-word, which cut the first word of a
    story and repeated a word across adjacent clips. With word timings each
    word is assigned to one sentence by its position in the text, and the
    edge sits just before that sentence's first word.
    """
    rows = sorted(
        (
            row for row in words or []
            if isinstance(row, dict) and str(row.get("w") or "").strip()
            and _safe_float(row.get("end")) > _safe_float(row.get("start"))
        ),
        key=lambda row: (_safe_float(row.get("start")), _safe_float(row.get("end"))),
    )
    if len(parts) < 2 or len(rows) < len(parts):
        return None
    spaced = any(" " in part for part in parts)

    def weight(value: str) -> int:
        return max(1, len(value.split()) if spaced else len(value.replace(" ", "")))

    part_weights = [weight(part) for part in parts]
    word_weights = [1 if spaced else weight(str(row["w"])) for row in rows]
    part_total = float(sum(part_weights))
    word_total = float(sum(word_weights))
    edges: list[float] = []
    cumulative = 0.0
    for value in part_weights[:-1]:
        cumulative += value
        edges.append(cumulative / part_total)
    owner: list[int] = []
    seen = 0.0
    for value in word_weights:
        middle = (seen + value / 2.0) / word_total
        seen += value
        owner.append(sum(1 for edge in edges if middle >= edge))
    groups: list[list[dict]] = [[] for _ in parts]
    for index, row in zip(owner, rows):
        groups[index].append(row)
    if any(not group for group in groups):
        return None
    bounds: list[float] = []
    for index in range(1, len(groups)):
        first = _safe_float(groups[index][0].get("start"))
        last = _safe_float(groups[index - 1][-1].get("end"))
        edge = max(last, first - WORD_LEAD_S)
        edge = min(max(edge, start), end)
        if bounds and edge <= bounds[-1]:
            return None
        bounds.append(edge)
    return bounds


def _timed_parts(
    text: str,
    start: float,
    end: float,
    scene: int | None,
    source: str,
    scene_index: _SceneIndex,
    words: list[dict] | None = None,
) -> list[dict]:
    parts = _split_text(text)
    if not parts or end <= start:
        return []
    total_chars = sum(max(1, len(part)) for part in parts)
    span = end - start
    cursor = start
    bounds = _word_boundaries(parts, words, start, end)
    out: list[dict] = []
    for index, part in enumerate(parts):
        if index == len(parts) - 1:
            stop = end
        elif bounds is not None:
            stop = bounds[index]
        else:
            stop = cursor + span * len(part) / total_chars
        mid = (cursor + stop) / 2
        item_scene = scene if scene is not None else scene_index.primary(cursor, stop)
        item_scenes = (
            [int(scene)] if scene is not None
            else scene_index.ids_for(cursor, stop)
        )
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
    stats: dict | None = None,
    scene_index: _SceneIndex | None = None,
) -> list[dict]:
    """Return sentence units in source order.

    Transcript segments win when present. Scenes with no transcript coverage
    fall back to their speech or on-screen text, so partial transcripts merge
    instead of hiding the second half of a source. Nothing is synthesized when
    both sources are empty.
    """
    if scene_index is None:
        scene_index = _SceneIndex(list(scenes or []))
    scene_list = scene_index.scenes
    raw: list[dict] = []

    if isinstance(transcript_segments, dict):
        transcript_segments = transcript_segments.get("segments") or []
    transcript_raw: list[dict] = []
    coverage: dict[int, float] = {}
    transcript_texts: set[str] = set()
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
        transcript_texts.add(text.casefold())
        scene = segment.get("scene")
        try:
            scene = int(scene) if scene is not None else None
        except (TypeError, ValueError):
            scene = None
        transcript_raw.extend(_timed_parts(
            text, start, end, scene, "transcript", scene_index,
            words=segment.get("words"),
        ))
        if segment.get("words") and stats is not None:
            stats["word_timed"] = True
        for scene_id in scene_index.ids_for(start, end):
            scene = scene_index.by_id.get(scene_id)
            if scene is None:
                continue
            coverage[scene_id] = coverage.get(scene_id, 0.0) + _overlap(
                start, end,
                _safe_float(scene.get("start")),
                _safe_float(scene.get("end")),
            )

    raw.extend(transcript_raw)
    partial_scenes = 0
    if transcript_raw:
        for scene in scene_list:
            try:
                scene_id = int(scene.get("id"))
            except (TypeError, ValueError):
                continue
            duration = max(
                0.001,
                _safe_float(scene.get("end")) - _safe_float(scene.get("start")),
            )
            if coverage.get(scene_id, 0.0) / duration >= 0.15:
                continue
            text = _clean(scene.get("speech") or scene.get("ocr"))
            if not text or text.casefold() in transcript_texts:
                continue
            raw.extend(_timed_parts(
                text,
                _safe_float(scene.get("start")),
                _safe_float(scene.get("end")),
                scene_id,
                "scene",
                scene_index,
            ))
            partial_scenes += 1
    else:
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
                scene_index,
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
    total = len(deduped)
    returned = deduped[:SENTENCE_LIMIT]
    if stats is not None:
        stats.update({
            "sentence_total": total,
            "sentence_returned": len(returned),
            "truncated": total > len(returned),
            "partial_scene_fallback": partial_scenes,
        })
    return returned


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


def _scene_metrics(scenes: list[dict]) -> dict[int, dict]:
    metrics: dict[int, dict] = {}
    for scene in scenes:
        if scene.get("id") is None:
            continue
        visual = _clamp(_safe_float(scene.get("visual_score"), 50.0) / 100.0)
        if scene.get("black"):
            visual *= 0.25
        elif scene.get("freeze"):
            visual *= 0.6
        metrics[int(scene["id"])] = {
            "visual": visual,
            "audio": _clamp(_safe_float(scene.get("audio_score"), 50.0) / 100.0),
            "hook": _clamp(_safe_float(scene.get("hook"), 50.0) / 100.0),
        }
    return metrics


def _metric_mean(scene_ids: Iterable[int], metrics: dict[int, dict], key: str) -> float:
    values = [metrics[scene_id][key] for scene_id in scene_ids if scene_id in metrics]
    return sum(values) / len(values) if values else 0.5


def _keyword_set(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9']+|[\u4e00-\u9fff]{2,}", (text or "").lower())
    return {word for word in words if len(word) > 2 and word not in _STOPWORDS}


def _sentence_stats(sentences: list[dict]) -> dict[int, dict]:
    stats: dict[int, dict] = {}
    for sentence in sentences:
        try:
            sentence_id = int(sentence.get("id"))
        except (TypeError, ValueError):
            continue
        text = _clean(sentence.get("text"))
        words = re.findall(r"[a-z0-9']+|[\u4e00-\u9fff]", text.lower())
        stats[sentence_id] = {
            "dur": max(0.0, _safe_float(sentence.get("dur"))),
            "terminal": _terminal_text(text),
            "hook": _clamp(hook_text_score(text)),
            "keywords": _keyword_set(text),
            "word_count": len(words),
        }
    return stats


def source_fingerprint(sentences: list[dict]) -> str:
    """Stable fingerprint for rejecting stale sentence edits after cleanup."""
    payload = [
        [
            sentence.get("id"),
            round(_safe_float(sentence.get("start")), 3),
            round(_safe_float(sentence.get("end")), 3),
            str(sentence.get("text") or ""),
            sentence.get("scene"),
            sentence.get("source"),
        ]
        for sentence in sentences
    ]
    encoded = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:32]


def _story_text(story: dict) -> str:
    parts = [str(story.get("title") or "")]
    for sentence in story.get("sentences") or []:
        parts.append(str(sentence.get("text") or ""))
    return " ".join(part for part in parts if part)


def _novelty(
    story: dict,
    selected: list[dict],
    selected_spans: list[tuple[float, float]] | None = None,
) -> float:
    if not selected:
        return 1.0
    duration = max(0.001, _safe_float(story.get("dur")))
    start = _safe_float(story.get("start"))
    end = _safe_float(story.get("end"))
    if selected_spans is None:
        selected_spans = [
            (_safe_float(other.get("start")), _safe_float(other.get("end")))
            for other in selected
        ]
    overlap = 0.0
    for other_start, other_end in selected_spans:
        overlap += _overlap(start, end, other_start, other_end)
    temporal = 1.0 - _clamp(overlap / duration)
    words = story.get("_keywords")
    if not isinstance(words, set):
        words = _keyword_set(_story_text(story))
    best = 0.0
    for other in selected:
        other_words = other.get("_keywords")
        if not isinstance(other_words, set):
            other_words = _keyword_set(_story_text(other))
        if not words or not other_words:
            continue
        best = max(best, len(words & other_words) / len(words | other_words))
    lexical = 1.0 - best
    return round(_clamp(0.6 * temporal + 0.4 * lexical), 4)


def _proximity_penalty(
    story: dict,
    selected: list[dict],
    selected_spans: list[tuple[float, float]] | None = None,
) -> float:
    if not selected:
        return 0.0
    if selected_spans is None:
        selected_spans = [
            (_safe_float(other.get("start")), _safe_float(other.get("end")))
            for other in selected
        ]
    start = _safe_float(story.get("start"))
    end = _safe_float(story.get("end"))
    gap = min(
        max(0.0, max(other_start - end, start - other_end))
        for other_start, other_end in selected_spans
    )
    return 0.06 * max(0.0, 1.0 - min(gap, 8.0) / 8.0)


def _speech_coherence(
    sentences: list[dict],
    stats: dict[int, dict] | None = None,
    keywords: set[str] | None = None,
    word_count: int | None = None,
) -> float:
    if not sentences:
        return 0.0
    stats = stats or {}
    total = 0.0
    spoken = 0.0
    complete = 0
    for sentence in sentences:
        try:
            sentence_id = int(sentence.get("id"))
        except (TypeError, ValueError):
            sentence_id = -1
        item = stats.get(sentence_id)
        if item:
            duration = max(0.0, _safe_float(item.get("dur")))
            total += duration
            if item.get("word_count"):
                spoken += duration
            complete += 1 if item["terminal"] else 0
        else:
            duration = max(0.0, _safe_float(sentence.get("dur")))
            total += duration
            if _clean(sentence.get("text")):
                spoken += duration
            complete += 1 if _terminal_text(sentence.get("text")) else 0
    total = max(0.001, total)
    coverage = _clamp(spoken / total)
    complete_ratio = complete / max(1, len(sentences))
    if word_count is None:
        joined = " ".join(_clean(item.get("text")) for item in sentences)
        word_count = len(re.findall(r"[a-z0-9']+|[\u4e00-\u9fff]", joined.lower()))
    if keywords is None:
        keywords = _keyword_set(" ".join(
            _clean(item.get("text")) for item in sentences
        ))
    variety = len(keywords) / max(1, word_count)
    richness = _clamp((variety - 0.15) / 0.65)
    return round(_clamp(0.55 * coverage + 0.30 * complete_ratio + 0.15 * richness), 4)


def _hook_signal(
    sentences: list[dict],
    scene_ids: list[int],
    by_id: dict[int, dict],
    stats: dict[int, dict] | None = None,
    scene_hook: float | None = None,
) -> float:
    if not sentences:
        return 0.0
    try:
        sentence_id = int(sentences[0].get("id"))
    except (TypeError, ValueError):
        sentence_id = -1
    item = (stats or {}).get(sentence_id)
    text_score = (
        item["hook"] if item
        else _clamp(hook_text_score(_clean(sentences[0].get("text"))))
    )
    scene_score = (
        scene_hook if scene_hook is not None
        else _scene_mean(scene_ids, by_id, "hook")
    )
    return round(_clamp(0.70 * text_score + 0.30 * scene_score), 4)


def _payoff_signal(
    sentences: list[dict],
    end: float,
    source_duration: float,
    stats: dict[int, dict] | None = None,
) -> float:
    if not sentences:
        return 0.0
    try:
        sentence_id = int(sentences[-1].get("id"))
    except (TypeError, ValueError):
        sentence_id = -1
    item = (stats or {}).get(sentence_id)
    terminal = (
        (1.0 if item["terminal"] else 0.35)
        if item
        else (1.0 if _terminal_text(sentences[-1].get("text")) else 0.35)
    )
    source_duration = max(_safe_float(source_duration), end, 1.0)
    late = _clamp((end / source_duration) / 0.68)
    return round(_clamp(0.70 * terminal + 0.30 * late), 4)


def _score_story(
    story: dict,
    scenes: list[dict],
    source_duration: float,
    novelty: float = 1.0,
    build_evidence: bool = True,
    scene_by_id: dict[int, dict] | None = None,
    sentence_stats: dict[int, dict] | None = None,
    scene_metrics: dict[int, dict] | None = None,
) -> float:
    sentences = story.get("sentences") or []
    by_id = scene_by_id
    if by_id is None:
        by_id = {
            int(scene["id"]): scene
            for scene in scenes
            if scene.get("id") is not None
        }
    scene_ids = [int(value) for value in story.get("scenes") or []]
    if scene_metrics is None:
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
        scene_hook = None
    else:
        visual = _metric_mean(scene_ids, scene_metrics, "visual")
        audio = _metric_mean(scene_ids, scene_metrics, "audio")
        scene_hook = _metric_mean(scene_ids, scene_metrics, "hook")
    stats = sentence_stats or {}
    keywords = story.get("_keywords")
    word_count = story.get("_word_count")
    if stats and keywords is None:
        keywords = _keyword_set(_story_text(story))
    signals = {
        "hook_score": _hook_signal(
            sentences, scene_ids, by_id, stats, scene_hook,
        ),
        "speech_coherence": _speech_coherence(
            sentences, stats, keywords, word_count,
        ),
        "audio_energy": round(audio, 4),
        "visual_quality": round(visual, 4),
        "payoff_position": _payoff_signal(
            sentences, _safe_float(story.get("end")), source_duration, stats,
        ),
        "novelty": round(_clamp(novelty), 4),
    }
    total = sum(STORY_WEIGHTS[key] * signals[key] for key in STORY_WEIGHTS)
    story["_base_total"] = round(
        sum(
            STORY_WEIGHTS[key] * signals[key]
            for key in STORY_WEIGHTS
            if key != "novelty"
        ),
        9,
    )
    story["score_breakdown"] = signals
    story["score"] = round(total * 100, 2)
    story["evidence"] = (
        _story_evidence(story, scenes, signals)
        if build_evidence else []
    )
    return total


def _story_evidence(story: dict, scenes: list[dict], signals: dict) -> list[dict]:
    sentences = story.get("sentences") or []
    if not sentences:
        return []
    first = sentences[0]
    last = sentences[-1]
    first_source = str(first.get("source") or "transcript")
    last_source = str(last.get("source") or "transcript")
    evidence = [
        {
            "type": "transcript" if first_source == "transcript" else "scene",
            "text": f"Hook line ({first_source}): {_clip_text(first.get('text'), 120)}",
            "scene": first.get("scene"),
            "time": round(_safe_float(first.get("start")), 3),
        },
        {
            "type": "transcript" if last_source == "transcript" else "scene",
            "text": f"Payoff line ({last_source}): {_clip_text(last.get('text'), 120)}",
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


def _clips_for_sentences(
    sentences: list[dict],
    scenes: list[dict],
    scene_by_id: dict[int, dict] | None = None,
) -> list[dict]:
    by_id = scene_by_id or {
        int(scene["id"]): scene for scene in scenes if scene.get("id") is not None
    }
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
    scene_by_id: dict[int, dict] | None = None,
    sentence_stats: dict[int, dict] | None = None,
    scene_ids: list[int] | None = None,
    scene_metrics: dict[int, dict] | None = None,
    duration: float | None = None,
    start: float | None = None,
    end: float | None = None,
) -> dict | None:
    ordered = list(sentences)
    if not ordered:
        return None
    if start is None:
        start = min(_safe_float(item.get("start")) for item in ordered)
    if end is None:
        end = max(_safe_float(item.get("end")) for item in ordered)
    if duration is None:
        duration = _story_duration(ordered)
    if duration <= 0:
        return None
    clips = (
        _clips_for_sentences(ordered, scenes, scene_by_id)
        if materialize else []
    )
    if materialize and not clips:
        return None
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
        "scenes": scene_ids if scene_ids is not None else _story_scene_ids(ordered),
    }
    if sentence_stats:
        keywords: set[str] = set()
        word_count = 0
        for sentence in ordered:
            try:
                sentence_id = int(sentence.get("id"))
            except (TypeError, ValueError):
                continue
            item = sentence_stats.get(sentence_id)
            if item is None:
                continue
            keywords.update(item["keywords"])
            word_count += item["word_count"]
        story["_keywords"] = set(keywords)
        story["_word_count"] = word_count
    if edited:
        story["edited"] = True
    _score_story(
        story, scenes, source_duration,
        novelty=1.0,
        build_evidence=materialize,
        scene_by_id=scene_by_id,
        sentence_stats=sentence_stats,
        scene_metrics=scene_metrics,
    )
    return story


def _candidate_end_indices(
    sentences: list[dict],
    start_index: int,
    min_s: float,
    max_s: float,
    sentence_stats: dict[int, dict] | None = None,
) -> list[int]:
    first = _safe_float(sentences[start_index].get("start"))
    ends: list[int] = []
    for index in range(start_index, len(sentences)):
        span = _safe_float(sentences[index].get("end")) - first
        if span < min_s:
            continue
        if span > max_s:
            break
        sentence = sentences[index]
        if sentence_stats:
            try:
                sentence_id = int(sentence.get("id"))
            except (TypeError, ValueError):
                sentence_id = -1
            item = sentence_stats.get(sentence_id)
            terminal = item["terminal"] if item else _terminal_text(sentence.get("text"))
        else:
            terminal = _terminal_text(sentence.get("text"))
        if terminal:
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
    limit: int = CANDIDATE_LIMIT,
    scene_by_id: dict[int, dict] | None = None,
    sentence_stats: dict[int, dict] | None = None,
    scene_metrics: dict[int, dict] | None = None,
    stats: dict | None = None,
) -> list[dict]:
    """Enumerate sentence-boundary stories, cap, then score only survivors."""
    if not sentences or not scenes:
        if stats is not None:
            stats.update({"candidate_total": 0, "candidate_scored": 0})
        return []
    banned = {int(value) for value in (ban_scenes or [])}
    prefix = [0.0]
    for sentence in sentences:
        prefix.append(prefix[-1] + _safe_float(sentence.get("dur")))
    specs: list[dict] = []
    for start_index, first in enumerate(sentences):
        first_scene_ids = {int(value) for value in first.get("scenes") or []}
        if banned and first_scene_ids & banned:
            continue
        start = _safe_float(first.get("start"))
        if start + min_s > source_duration + 0.5:
            break
        scene_ids: set[int] = set()
        cursor = start_index
        for end_index in _candidate_end_indices(
            sentences, start_index, min_s, max_s, sentence_stats,
        ):
            for index in range(cursor, end_index + 1):
                for value in sentences[index].get("scenes") or []:
                    try:
                        scene_ids.add(int(value))
                    except (TypeError, ValueError):
                        continue
            cursor = end_index + 1
            duration = round(prefix[end_index + 1] - prefix[start_index], 3)
            if duration < min_s - 0.001 or duration > max_s + 0.001:
                continue
            if not scene_ids:
                continue
            if banned and scene_ids & banned:
                continue
            end = _safe_float(sentences[end_index].get("end"))
            specs.append({
                "start_index": start_index,
                "end_index": end_index,
                "start": start,
                "end": end,
                "duration": duration,
                "scene_ids": sorted(scene_ids),
                "story_id": (
                    f"st_{int(round(start * 1000)):07d}_"
                    f"{int(round(end * 1000)):07d}"
                ),
            })
    total = len(specs)
    if limit > 0 and total > limit:
        step = (total - 1) / max(1, limit - 1)
        specs = [specs[int(round(index * step))] for index in range(limit)]
    candidates: list[dict] = []
    for spec in specs:
        selected = sentences[spec["start_index"]:spec["end_index"] + 1]
        story = _story_from_sentences(
            selected, scenes, source_duration, spec["story_id"],
            materialize=False,
            scene_by_id=scene_by_id,
            sentence_stats=sentence_stats,
            scene_ids=spec["scene_ids"],
            scene_metrics=scene_metrics,
            duration=spec["duration"],
            start=spec["start"],
            end=spec["end"],
        )
        if story is None:
            continue
        candidates.append(story)
    if stats is not None:
        stats.update({
            "candidate_total": total,
            "candidate_scored": len(candidates),
        })
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
    selected_spans: list[tuple[float, float]] | None = None,
) -> int:
    if selected_spans is None:
        selected_spans = [
            (_safe_float(item.get("start")), _safe_float(item.get("end")))
            for item in selected
        ]
    spans = sorted([
        *selected_spans,
        (_safe_float(story.get("start")), _safe_float(story.get("end"))),
    ])
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
    selected_spans = [
        (_safe_float(other.get("start")), _safe_float(other.get("end")))
        for other in selected
    ]
    for candidate in candidates:
        if _overlaps(candidate, selected, selected_spans):
            continue
        novelty = _novelty(candidate, selected, selected_spans)
        base = candidate.get("_base_total")
        if base is None:
            base = _weighted_total(candidate.get("score_breakdown") or {}, novelty)
        else:
            base = float(base) + STORY_WEIGHTS["novelty"] * novelty
        penalty = _proximity_penalty(candidate, selected, selected_spans)
        capacity = _capacity_after(
            candidate, selected, source_duration, min_s, selected_spans,
        )
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


def _overlaps(
    story: dict,
    selected: list[dict],
    selected_spans: list[tuple[float, float]] | None = None,
) -> bool:
    start = _safe_float(story.get("start"))
    end = _safe_float(story.get("end"))
    if selected_spans is None:
        selected_spans = [
            (_safe_float(other.get("start")), _safe_float(other.get("end")))
            for other in selected
        ]
    return any(
        _overlap(start, end, other_start, other_end) > 0.001
        for other_start, other_end in selected_spans
    )


def _materialize_story(
    candidate: dict,
    scenes: list[dict],
    source_duration: float,
    novelty: float,
    locked: bool,
    scene_by_id: dict[int, dict] | None = None,
    sentence_stats: dict[int, dict] | None = None,
    scene_metrics: dict[int, dict] | None = None,
) -> dict | None:
    story = copy.deepcopy(candidate)
    story["clips"] = _clips_for_sentences(
        story.get("sentences") or [], scenes, scene_by_id,
    )
    if not story["clips"]:
        return None
    story["title"] = (
        story.get("title")
        or _clip_text((story.get("hook") or {}).get("text"), 64)
        or f"Story at {_safe_float(story.get('start')):.1f}s"
    )
    _score_story(
        story, scenes, source_duration, novelty,
        build_evidence=True,
        scene_by_id=scene_by_id,
        sentence_stats=sentence_stats,
        scene_metrics=scene_metrics,
    )
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
    scene_by_id: dict[int, dict] | None = None,
    sentence_stats: dict[int, dict] | None = None,
    scene_metrics: dict[int, dict] | None = None,
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
        blocked: set[int] = set()
        while best is not None:
            story = _materialize_story(
                best, scenes, source_duration, novelty, locked=True,
                scene_by_id=scene_by_id,
                sentence_stats=sentence_stats,
                scene_metrics=scene_metrics,
            )
            remaining = [item for item in remaining if item is not best]
            if story is not None:
                selected.append(story)
                break
            blocked.add(id(best))
            usable = [item for item in options if id(item) not in blocked]
            best, novelty = _pick_best(
                usable, selected, source_duration, min_s, count, locked=True,
            )

    while len(selected) < count:
        best, novelty = _pick_best(
            remaining, selected, source_duration, min_s, count,
        )
        if best is None:
            break
        remaining.remove(best)
        story = _materialize_story(
            best,
            scenes,
            source_duration,
            novelty,
            locked=bool(set(best.get("scenes") or []) & effective_locks),
            scene_by_id=scene_by_id,
            sentence_stats=sentence_stats,
            scene_metrics=scene_metrics,
        )
        if story is not None:
            selected.append(story)

    ordered = _order_stories(selected, order)
    for story in ordered:
        story.pop("_keywords", None)
        story.pop("_word_count", None)
        story.pop("_base_total", None)
    return ordered


def _arc_order_stories(stories: list[dict]) -> list[dict]:
    """Strongest hook first, strongest remaining payoff last, middle in source order."""
    ordered = sorted(stories, key=lambda story: (
        _safe_float(story.get("start")),
        str(story.get("id") or ""),
    ))
    if len(ordered) <= 1:
        return ordered
    hook = max(
        ordered,
        key=lambda story: (
            _safe_float((story.get("score_breakdown") or {}).get("hook_score")),
            -_safe_float(story.get("start")),
            str(story.get("id") or ""),
        ),
    )
    remaining = [story for story in ordered if story is not hook]
    if not remaining:
        return ordered
    payoff = max(
        remaining,
        key=lambda story: (
            _safe_float((story.get("score_breakdown") or {}).get("payoff_position")),
            _safe_float(story.get("start")),
            str(story.get("id") or ""),
        ),
    )
    middle = [story for story in remaining if story is not payoff]
    return [hook, *middle, payoff]


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
    elif order == "arc":
        ordered = _arc_order_stories(ordered)
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
    source_stats: dict = {}
    candidate_stats: dict = {}
    scene_index = _SceneIndex(scenes)
    scene_metrics = _scene_metrics(scenes)
    sentences = source_sentences(
        scenes, transcript_segments, stats=source_stats,
        scene_index=scene_index,
    )
    sentence_stats = _sentence_stats(sentences)
    banned = sorted({int(value) for value in (ban_scenes or [])})
    effective_locks = sorted({int(value) for value in (locks or [])} - set(banned))
    candidates = candidate_stories(
        sentences, scenes, duration, min_s, max_s, banned,
        scene_by_id=scene_index.by_id,
        sentence_stats=sentence_stats,
        scene_metrics=scene_metrics,
        stats=candidate_stats,
    )
    stories = _select_stories(
        candidates, int(count), scenes, duration, effective_locks, order, min_s,
        scene_by_id=scene_index.by_id,
        sentence_stats=sentence_stats,
        scene_metrics=scene_metrics,
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
    warnings: list[str] = []
    if source_stats.get("truncated"):
        warnings.append(
            f"Only the first {source_stats.get('sentence_returned')} of "
            f"{source_stats.get('sentence_total')} sentences were used "
            f"(limit {SENTENCE_LIMIT})."
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
        "complete": len(stories) >= int(count),
        "candidate_count": len(candidates),
        "candidate_total": candidate_stats.get("candidate_total", len(candidates)),
        "candidate_scored": candidate_stats.get("candidate_scored", len(candidates)),
        "sentence_count": len(sentences),
        "source_fingerprint": source_fingerprint(sentences),
        # "words": sentence edges sit on measured word edges. Older sets used
        # character-share timing and keep it, so their fingerprints still match.
        "sentence_timing": "words" if source_stats.get("word_timed") else "text",
        "source": {
            "transcript": used_transcript,
            "scene_text": used_scene,
            "fallback": "transcript" if used_transcript else ("scene_text" if used_scene else "none"),
            "partial_scene_fallback": source_stats.get("partial_scene_fallback", 0),
            "sentence_total": source_stats.get("sentence_total", len(sentences)),
            "truncated": bool(source_stats.get("truncated")),
        },
        "note": note,
        "warnings": warnings,
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
    sentence_stats = _sentence_stats(list(pool.values()))
    scene_by_id = {
        int(scene["id"]): scene
        for scene in scenes
        if scene.get("id") is not None
    }
    scene_metrics = _scene_metrics(scenes)
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
            scene_by_id=scene_by_id,
            sentence_stats=sentence_stats,
            scene_metrics=scene_metrics,
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
    for index, left in enumerate(rebuilt):
        for right in rebuilt[index + 1:]:
            if _overlap(
                _safe_float(left.get("start")),
                _safe_float(left.get("end")),
                _safe_float(right.get("start")),
                _safe_float(right.get("end")),
            ) > 0.01:
                raise ClipSetError(
                    f"Stories {left.get('id')} and {right.get('id')} overlap after edit."
                )
    prior: list[dict] = []
    for story in rebuilt:
        novelty = _novelty(story, prior)
        _score_story(
            story, scenes, source_duration, novelty,
            scene_by_id=scene_by_id,
            sentence_stats=sentence_stats,
            scene_metrics=scene_metrics,
        )
        story["locked"] = bool(set(story.get("scenes") or []) & effective_locks)
        prior.append(story)
    rebuilt = _order_stories(rebuilt, order)
    for story in rebuilt:
        story.pop("_keywords", None)
        story.pop("_word_count", None)
        story.pop("_base_total", None)

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
    value["complete"] = len(rebuilt) >= int(value.get("requested") or 0)
    warnings: list[str] = list(dict.fromkeys(value.get("warnings") or []))
    low = _safe_float(value.get("min_s"), MIN_STORY_S)
    high = _safe_float(value.get("max_s"), MAX_STORY_S)
    for story in rebuilt:
        duration = _safe_float(story.get("dur"))
        if duration < low - 0.001 or duration > high + 0.001:
            message = (
                f"{story.get('id')} is {duration:.1f}s outside {low:.0f}-{high:.0f}s."
            )
            if message not in warnings:
                warnings.append(message)
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
        raise ClipSetError(
            f"Story {story.get('id')} has no materialized clips."
        )
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
