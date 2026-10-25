"""Plan-only tightening: filler/silence removal plus simple punch-ins.

The transform never writes media, never mutates the source plan, and never
mutates the job. It keeps the hook first and the payoff last, stays inside each
original clip's source window, and emits hard cuts only. No J/L cuts, SFX, or
B-roll are introduced.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

TOKEN_RE = re.compile(r"\S+")
WORD_RE = re.compile(r"[^\w']+", re.UNICODE)
SILENCE_START_RE = re.compile(r"silence_start:\s*(-?\d+(?:\.\d+)?)")
SILENCE_END_RE = re.compile(r"silence_end:\s*(-?\d+(?:\.\d+)?)")

FILLER_SINGLE = frozenset({
    "um", "uh", "uhm", "umm", "erm", "er", "ah", "eh", "hmm", "hm", "mm", "mmm",
    "like", "basically", "actually", "literally", "honestly",
})
FILLER_MULTI = frozenset({
    ("you", "know"),
    ("i", "mean"),
    ("kind", "of"),
    ("sort", "of"),
    ("you", "see"),
    ("you", "know", "what"),
})
@dataclass(frozen=True)
class TightenOptions:
    remove_filler: bool = True
    remove_silence: bool = True
    punch_ins: bool = True
    min_silence: float = 0.65
    silence_pad: float = 0.08
    filler_pad: float = 0.02
    min_clip: float = 0.25
    punch_scale: float = 1.06
    punch_min_duration: float = 1.5


@dataclass(frozen=True)
class Word:
    text: str
    start: float
    end: float


def _bool(value: object, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return fallback


def _number(value: object, fallback: float, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(number):
        return fallback
    return max(low, min(high, number))


def normalize_options(raw: dict | None) -> TightenOptions:
    raw = raw if isinstance(raw, dict) else {}
    defaults = TightenOptions()
    return TightenOptions(
        remove_filler=_bool(
            raw.get(
                "remove_filler",
                raw.get("remove_fillers", raw.get("filler_removal", raw.get("filler"))),
            ),
            defaults.remove_filler,
        ),
        remove_silence=_bool(
            raw.get(
                "remove_silence",
                raw.get("remove_silences", raw.get("silence_removal", raw.get("silence"))),
            ),
            defaults.remove_silence,
        ),
        punch_ins=_bool(
            raw.get("punch_ins", raw.get("punch_in", raw.get("punch"))),
            defaults.punch_ins,
        ),
        min_silence=_number(raw.get("min_silence"), defaults.min_silence, 0.2, 5.0),
        silence_pad=_number(raw.get("silence_pad"), defaults.silence_pad, 0.0, 0.5),
        filler_pad=_number(raw.get("filler_pad"), defaults.filler_pad, 0.0, 0.25),
        min_clip=_number(raw.get("min_clip"), defaults.min_clip, 0.1, 2.0),
        punch_scale=_number(raw.get("punch_scale"), defaults.punch_scale, 1.0, 1.35),
        punch_min_duration=_number(
            raw.get("punch_min_duration"), defaults.punch_min_duration, 0.5, 20.0,
        ),
    )


def _merge(intervals: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    ordered = sorted(
        (max(0.0, float(start)), max(0.0, float(end)))
        for start, end in intervals
        if float(end) > float(start)
    )
    merged: list[tuple[float, float]] = []
    for start, end in ordered:
        if not merged or start > merged[-1][1] + 0.0005:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def _subtract(
    start: float,
    end: float,
    removals: Iterable[tuple[float, float]],
) -> list[tuple[float, float]]:
    keeps: list[tuple[float, float]] = []
    cursor = start
    for remove_start, remove_end in _merge(removals):
        if remove_end <= start or remove_start >= end:
            continue
        remove_start = max(start, remove_start)
        remove_end = min(end, remove_end)
        if remove_start > cursor + 0.0005:
            keeps.append((cursor, remove_start))
        cursor = max(cursor, remove_end)
    if cursor < end - 0.0005:
        keeps.append((cursor, end))
    return keeps


def _normal_word(text: str) -> str:
    return WORD_RE.sub("", str(text or "").lower()).replace("’", "'")


def _word_estimate(text: str, start: float, end: float) -> list[Word]:
    tokens = [token for token in TOKEN_RE.findall(str(text or "")) if token.strip()]
    span = max(0.0, end - start)
    if not tokens or span <= 0:
        return []
    unit = span / len(tokens)
    return [
        Word(token, round(start + index * unit, 4), round(start + (index + 1) * unit, 4))
        for index, token in enumerate(tokens)
    ]


def _words_from_values(
    raw: object,
    *,
    clip_start: float,
    clip_end: float,
) -> list[Word]:
    if not isinstance(raw, list):
        return []
    words: list[Word] = []
    rel_start = float("inf")
    rel_end = 0.0
    for item in raw:
        if not isinstance(item, dict):
            return []
        text = str(item.get("text") or item.get("word") or "").strip()
        try:
            start = float(item.get("start"))
            end = float(item.get("end"))
        except (TypeError, ValueError):
            return []
        if not text or not math.isfinite(start) or not math.isfinite(end) or end <= start:
            continue
        rel_start = min(rel_start, start)
        rel_end = max(rel_end, end)
        words.append(Word(text, start, end))
    if not words:
        return []
    clip_duration = max(0.0, clip_end - clip_start)
    if rel_end <= clip_duration + 0.15 and clip_start > 0.15 and rel_start >= -0.001:
        words = [Word(item.text, item.start + clip_start, item.end + clip_start) for item in words]
    return words


def _clip_words(clip: dict, scene: dict | None, start: float, end: float) -> list[Word]:
    explicit = clip.get("words")
    if explicit is None and isinstance(scene, dict):
        explicit = (
            scene.get("words")
            or scene.get("word_times")
            or scene.get("word_timestamps")
        )
    words = _words_from_values(explicit, clip_start=start, clip_end=end)
    if not words:
        clip_text = str(clip.get("text") or "").strip()
        if clip_text:
            words = _word_estimate(clip_text, start, end)
        elif isinstance(scene, dict):
            try:
                scene_start = float(scene.get("start") or start)
                scene_end = float(scene.get("end") or end)
            except (TypeError, ValueError):
                scene_start, scene_end = start, end
            text = str(scene.get("speech") or scene.get("ocr") or "").strip()
            words = _word_estimate(text, scene_start, scene_end)
    clipped: list[Word] = []
    for word in sorted(words, key=lambda item: (item.start, item.end)):
        word_start = max(start, word.start)
        word_end = min(end, word.end)
        if word_end - word_start <= 0.01:
            continue
        clipped.append(Word(word.text, round(word_start, 4), round(word_end, 4)))
    return clipped


def _filler_intervals(words: list[Word], pad: float) -> list[tuple[float, float]]:
    normalized = [_normal_word(word.text) for word in words]
    marked: set[int] = set()
    intervals: list[tuple[float, float]] = []
    for index in range(len(words)):
        for size in (3, 2):
            if index + size > len(words):
                continue
            phrase = tuple(normalized[index:index + size])
            if phrase in FILLER_MULTI:
                start = words[index].start
                end = words[index + size - 1].end
                intervals.append((start - pad, end + pad))
                marked.update(range(index, index + size))
        if index in marked:
            continue
        if normalized[index] in FILLER_SINGLE:
            intervals.append((words[index].start - pad, words[index].end + pad))
            marked.add(index)
    return _merge(intervals)


def _silence_intervals(
    words: list[Word],
    start: float,
    end: float,
    options: TightenOptions,
    explicit: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    intervals: list[tuple[float, float]] = []
    if words:
        ordered = sorted(words, key=lambda item: (item.start, item.end))
        first_gap = ordered[0].start - start
        if first_gap > options.min_silence:
            intervals.append((start, ordered[0].start - options.silence_pad))
        for previous, current in zip(ordered, ordered[1:]):
            gap = current.start - previous.end
            if gap > options.min_silence:
                intervals.append((
                    previous.end + options.silence_pad,
                    current.start - options.silence_pad,
                ))
        last_gap = end - ordered[-1].end
        if last_gap > options.min_silence:
            intervals.append((ordered[-1].end + options.silence_pad, end))
    for silence_start, silence_end in explicit:
        overlap_start = max(start, silence_start)
        overlap_end = min(end, silence_end)
        if overlap_end - overlap_start > 0.01:
            intervals.append((overlap_start, overlap_end))
    return _merge(intervals)


def _normalize_silences(raw: object) -> list[tuple[float, float]]:
    if not isinstance(raw, (list, tuple)):
        return []
    values: list[tuple[float, float]] = []
    for item in raw:
        if isinstance(item, dict):
            start, end = item.get("start"), item.get("end")
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            start, end = item[0], item[1]
        else:
            continue
        try:
            start_f = float(start)
            end_f = float(end)
        except (TypeError, ValueError):
            continue
        if math.isfinite(start_f) and math.isfinite(end_f) and end_f > start_f >= 0:
            values.append((start_f, end_f))
    return values


def _role_for_piece(role: str, index: int, count: int) -> str:
    if role == "hook":
        return "hook" if index == 0 else "beat"
    if role == "payoff":
        return "payoff" if index == count - 1 else "beat"
    return role or "beat"


def _scene_crop(scenes: dict, scene_id: object) -> tuple[float, float]:
    try:
        scene = scenes.get(int(scene_id)) or {}
    except (TypeError, ValueError):
        scene = {}
    crop = scene.get("crop") if isinstance(scene, dict) else None
    crop = crop if isinstance(crop, dict) else {}
    try:
        cx = float(crop.get("cx", 0.5))
        cy = float(crop.get("cy", 0.5))
    except (TypeError, ValueError):
        cx, cy = 0.5, 0.5
    return max(0.0, min(1.0, cx)), max(0.0, min(1.0, cy))


def _source_hash(clips: list[dict]) -> str:
    payload = json.dumps(clips, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def tighten_plan(
    plan: dict,
    scenes: list[dict] | None = None,
    *,
    options: dict | TightenOptions | None = None,
    silences: list[dict] | list[tuple] | None = None,
) -> dict:
    """Return a new tightened plan. The source plan and scenes are untouched."""
    if not isinstance(plan, dict):
        raise ValueError("plan must be an object")
    source_plan = copy.deepcopy(plan)
    source_clips = [
        copy.deepcopy(clip)
        for clip in (source_plan.get("clips") or [])
        if isinstance(clip, dict)
    ]
    settings = options if isinstance(options, TightenOptions) else normalize_options(options)
    scene_rows = scenes if isinstance(scenes, list) else source_plan.get("_scenes") or []
    scene_map: dict[int, dict] = {}
    for scene in scene_rows:
        if not isinstance(scene, dict) or scene.get("id") is None:
            continue
        try:
            scene_id = int(scene["id"])
        except (TypeError, ValueError):
            continue
        scene_map[scene_id] = scene
    if silences is None:
        silences = source_plan.get("silences") or source_plan.get("_silences")
    explicit_silences = _normalize_silences(silences)
    output: list[dict] = []
    filler_removed = 0.0
    silence_removed = 0.0

    for original in source_clips:
        try:
            start = float(original.get("start"))
            end = float(original.get("end"))
        except (TypeError, ValueError):
            try:
                start = float(original.get("start") or 0.0)
                duration = float(original.get("dur") or 0.0)
                end = start + duration
            except (TypeError, ValueError):
                output.append(copy.deepcopy(original))
                continue
        if not math.isfinite(start) or not math.isfinite(end) or end - start <= 0.01:
            output.append(copy.deepcopy(original))
            continue
        role = str(original.get("role") or "beat")
        try:
            scene_id = int(original.get("scene"))
        except (TypeError, ValueError):
            scene_id = None
        scene = scene_map.get(scene_id) if scene_id is not None else None
        words = _clip_words(original, scene, start, end)
        filler_intervals = (
            _filler_intervals(words, settings.filler_pad) if settings.remove_filler else []
        )
        scene_silences = (
            _normalize_silences(scene.get("silences")) if isinstance(scene, dict) else []
        )
        silence_intervals = (
            _silence_intervals(
                words, start, end, settings, [*explicit_silences, *scene_silences],
            )
            if settings.remove_silence else []
        )
        if role in {"hook", "payoff"}:
            filler_intervals = [
                item for item in filler_intervals
                if item[0] > start + 0.0005 and item[1] < end - 0.0005
            ]
            silence_intervals = [
                item for item in silence_intervals
                if item[0] > start + 0.0005 and item[1] < end - 0.0005
            ]
        filler_removed += sum(
            max(0.0, min(end, item[1]) - max(start, item[0]))
            for item in filler_intervals
        )
        silence_removed += sum(
            max(0.0, min(end, item[1]) - max(start, item[0]))
            for item in silence_intervals
        )
        removals = _merge([*filler_intervals, *silence_intervals])
        keeps = _subtract(start, end, removals)
        keeps = [
            (piece_start, piece_end)
            for piece_start, piece_end in keeps
            if piece_end - piece_start >= settings.min_clip
        ]
        if not keeps:
            output.append(copy.deepcopy(original))
            continue
        for index, (piece_start, piece_end) in enumerate(keeps):
            piece = copy.deepcopy(original)
            piece["start"] = round(piece_start, 3)
            piece["end"] = round(piece_end, 3)
            piece["dur"] = round(piece_end - piece_start, 3)
            piece["role"] = _role_for_piece(role, index, len(keeps))
            piece["_tighten"] = {
                "piece": index + 1,
                "of": len(keeps),
                "source_start": round(start, 3),
                "source_end": round(end, 3),
            }
            output.append(piece)

    punch_count = 0
    if settings.punch_ins:
        for clip in output:
            try:
                duration = float(clip.get("dur") or 0.0)
            except (TypeError, ValueError):
                duration = 0.0
            if clip.get("role") != "beat" or duration < settings.punch_min_duration:
                continue
            if "punch" in clip:
                continue
            cx, cy = _scene_crop(scene_map, clip.get("scene"))
            clip["punch"] = {
                "scale": round(settings.punch_scale, 4),
                "cx": round(cx, 4),
                "cy": round(cy, 4),
                "source": "tighten",
            }
            punch_count += 1

    source_total = round(sum(
        max(0.0, float(clip.get("dur") or 0.0)) for clip in source_clips
    ), 3)
    total = round(sum(max(0.0, float(clip.get("dur") or 0.0)) for clip in output), 3)
    result = source_plan
    result["clips"] = output
    result["clip_count"] = len(output)
    result["total"] = total
    result["tightened"] = True
    result["tighten"] = {
        "version": 1,
        "source_clip_count": len(source_clips),
        "source_total": source_total,
        "source_hash": _source_hash(source_clips),
        "removed_seconds": round(max(0.0, source_total - total), 3),
        "filler_removed_seconds": round(max(0.0, filler_removed), 3),
        "silence_removed_seconds": round(max(0.0, silence_removed), 3),
        "punch_ins": punch_count,
        "options": {
            "remove_filler": settings.remove_filler,
            "remove_silence": settings.remove_silence,
            "punch_ins": settings.punch_ins,
            "min_silence": settings.min_silence,
            "min_clip": settings.min_clip,
        },
        "preserved_roles": ["hook", "payoff"],
        "cuts": "hard",
        "j_l_cuts": False,
        "sfx": False,
        "broll": False,
    }
    result["note"] = (
        f"Tightened {source_total:.1f}s to {total:.1f}s"
        f" with {punch_count} punch-in{'s' if punch_count != 1 else ''}."
    )
    if isinstance(result.get("reasoning"), dict):
        result["reasoning"]["tighten_note"] = (
            "Clip timings were tightened after selection. "
            "Selection reasoning still describes the source cut."
        )
    return result


def detect_silences(
    path: Path | str,
    *,
    noise_db: float = -32.0,
    min_duration: float = 0.65,
    timeout: float = 180.0,
) -> list[dict]:
    """Optional ffmpeg silencedetect helper; returns absolute source ranges."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not Path(path).is_file():
        return []
    try:
        result = subprocess.run(
            [
                ffmpeg, "-hide_banner", "-nostats", "-i", str(path),
                "-af", f"silencedetect=noise={noise_db}dB:d={min_duration}",
                "-f", "null", "-",
            ],
            capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    ranges: list[dict] = []
    start: float | None = None
    for line in (result.stderr or "").splitlines():
        start_match = SILENCE_START_RE.search(line)
        if start_match:
            start = max(0.0, float(start_match.group(1)))
            continue
        end_match = SILENCE_END_RE.search(line)
        if end_match and start is not None:
            end = max(start, float(end_match.group(1)))
            if end > start:
                ranges.append({"start": round(start, 3), "end": round(end, 3)})
            start = None
    return ranges
