"""Source Check: turn OCR samples into text tracklets and a SourceReport.

The module is pure planning data. It reads a job's stored analysis, optional
0.5 fps OCR samples and optional audio statistics, and returns one report:

* ``tracklets`` — persistent on-screen text regions with source-normalized
  boxes, time ranges and a rule-based kind;
* ``audio`` — speech coverage and a music estimate;
* ``faces`` and ``quality`` — existing evidence plus simple thresholds;
* ``recommendation`` — ``clean_then_compose`` / ``compose`` / ``music_first``;
* ``clean_prefill`` — advisory Clean layer entries;
* ``warnings`` and ``policy`` — the kind and rights gates.

Policy is keyed on the detected kind, never on a caller label:

* a ``watermark`` tracklet is always refused;
* ``handle_or_logo`` cleanup needs an own-footage attestation;
* no report claims "clean" when the full text pass did not run.

Nothing here calls ffmpeg, Vision, the network or a model pack. The sampler,
frame reader and audio extractor are injected by ``routes_check``.
"""

from __future__ import annotations

from difflib import SequenceMatcher
import hashlib
import inspect
import json
import logging
import math
import os
import re
import subprocess
import time
import wave
from bisect import bisect_right
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np

LOGGER = logging.getLogger(__name__)

from .. import ink as inkmod
from .. import textmatch
from . import rights

SCHEMA_VERSION = 1
REPORT_DIR = "check"
REPORT_FILE = "source_report.json"

# A subtitle changes every few seconds, so the scan reads two frames a second.
# That puts each edge of a text's time within a quarter second.
# Burned-in captions can last under half a second, so two frames a second missed some.
DEFAULT_SAMPLE_FPS = 4.0
DEFAULT_MAX_FRAMES = 3600
TRACKLET_MAX_GAP = 4.5
# The sampler can read a frame or two late, so a line can still be on screen
# just after the reading that no longer shows it. Two frames at 30 fps.
SAMPLE_SLACK = 0.067
# Each line of text is its own tracklet, so a long video has many.
MAX_TRACKLETS = 1000
# Two readings are one line when this much of the words match; OCR misreads a
# few characters from frame to frame.
LINE_MATCH = 0.6
# Fill planning, as multiples of the video's own noise. Picture change around a
# line up to the first is still; the second sets how fast fills rise with motion.
MOTION_NOISE_FLOOR = 0.5
MOTION_STILL_TIMES = 4.0
MOTION_KEY_TIMES = 4.0
MOTION_MOST_KEYS = 6.0
MAX_RANGES = 200

KINDS = rights.KINDS
RECOMMENDATIONS = ("clean_then_compose", "compose", "music_first")

WATERMARK_MESSAGE = "Use your original file — it has no watermark."
UNCONFIRMED_MESSAGE = (
    "Full-frame text sampling did not run. Treat a clean result as unconfirmed."
)
RIGHTS_MESSAGE = (
    "Own-footage attestation missing. The Clean layer stays locked until you attest."
)

# Approximate fallback when scene OCR exists but the record carried no box.
APPROX_BOX = {"x": 0.08, "y": 0.70, "w": 0.84, "h": 0.20}

_PLATFORM_TOKENS = (
    "tiktok", "tik tok", "douyin", "抖音", "xiaohongshu", "小红书",
    "rednote", "red note", "kwai", "快手", "youtube", "instagram",
    "facebook", "reels", "shorts", "threads", "snapchat", "capcut",
    "剪映", "watermark", "水印",
)
_PLATFORM_RE = re.compile(
    "|".join(re.escape(token) for token in _PLATFORM_TOKENS), re.IGNORECASE,
)
_AT_HANDLE_RE = re.compile(r"(?<![0-9A-Za-z])@[0-9A-Za-z_.]{2,}")
_URL_HANDLE_RE = re.compile(
    r"(?:https?://|www\.)[^\s]+"
    r"|\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:com|net|org|io|co|me|ee|link|tv)"
    r"(?:/[^\s]*)?",
    re.IGNORECASE,
)
_CALL_TO_ACTION_RE = re.compile(
    r"\b(?:follow|subscribe|link\s+in\s+bio|dm\s+me|watch\s+full|full\s+video)\b",
    re.IGNORECASE,
)
_UI_WORD_RE = re.compile(
    r"\b(?:build\w*|deploy|dashboard|accounts?|analytics|payments?|pricing|"
    r"support|settings|workspace|components?|security|performance|memory|"
    r"application|lighthouse|recorder|preview|projects?|tools?|integrations?|"
    r"generating|implementing|optimizing|analyzing|creators?|linkspace|"
    r"linktree|linktr)\b",
    re.IGNORECASE,
)
_CODE_RE = re.compile(
    r"https?://|www\.|\.(?:json|tsx?|jsx?|css|html?|py|md)\b|"
    r"className|import\s+[\w{*]|const\s+\w+|function\s*\w*\(|"
    r"[{}<>]",
    re.IGNORECASE,
)
_WATERMARK_LITERAL_RE = re.compile(r"water\s*mark|©|\(c\)\s*\d{4}", re.IGNORECASE)

# Screen-recording chrome: status bars, tab bars and app navigation labels.
# These are UI text, not baked-in captions, so they are never pre-filled for
# cleaning and never count towards "baked captions need cleaning".
_UI_TEXT_RE = re.compile(
    r"^(?:"
    r"\d{1,2}:\d{2}(?:\s*[ap]m)?"
    r"|\d{1,3}\s*%"
    r"|(?:wi-?fi|lte|5g|4g|3g)"
    r"|(?:settings|home|search|profile|share|back|cancel|done|next|send|"
    r"reply|menu|inbox|activity|notifications|following|for you|explore|"
    r"library|discover|messages|sign in|log in|subscribe|edit)"
    r")$",
    re.IGNORECASE,
)
SCREEN_TEXT_MESSAGE = (
    "Screen-recording UI text. It is not a baked-in caption and is not "
    "pre-filled for cleaning."
)


class CheckError(RuntimeError):
    """The source cannot be checked."""


# ---------------------------------------------------------------- geometry


def _number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def normalize_box(raw: Any) -> dict | None:
    """Validate one normalized box with a top-left origin."""
    if isinstance(raw, (list, tuple)) and len(raw) == 4:
        raw = {"x": raw[0], "y": raw[1], "w": raw[2], "h": raw[3]}
    if not isinstance(raw, dict):
        return None
    x = _number(raw.get("x"), -1.0)
    y = _number(raw.get("y"), -1.0)
    w = _number(raw.get("w"), 0.0)
    h = _number(raw.get("h"), 0.0)
    if w <= 0 or h <= 0 or x < 0 or y < 0 or x >= 1 or y >= 1:
        return None
    w = min(w, 1.0 - x)
    h = min(h, 1.0 - y)
    if w <= 0.002 or h <= 0.002:
        return None
    return {"x": round(x, 6), "y": round(y, 6), "w": round(w, 6), "h": round(h, 6)}


def _area(box: dict) -> float:
    return float(box["w"]) * float(box["h"])


def _center(box: dict) -> tuple[float, float]:
    return (
        float(box["x"]) + float(box["w"]) / 2.0,
        float(box["y"]) + float(box["h"]) / 2.0,
    )


def _iou(a: dict, b: dict) -> float:
    left = max(a["x"], b["x"])
    top = max(a["y"], b["y"])
    right = min(a["x"] + a["w"], b["x"] + b["w"])
    bottom = min(a["y"] + a["h"], b["y"] + b["h"])
    if right <= left or bottom <= top:
        return 0.0
    intersection = (right - left) * (bottom - top)
    union = _area(a) + _area(b) - intersection
    return intersection / union if union > 0 else 0.0


def _union(a: dict, b: dict) -> dict:
    left = min(a["x"], b["x"])
    top = min(a["y"], b["y"])
    right = max(a["x"] + a["w"], b["x"] + b["w"])
    bottom = max(a["y"] + a["h"], b["y"] + b["h"])
    return {
        "x": round(left, 6), "y": round(top, 6),
        "w": round(min(1.0, right) - left, 6),
        "h": round(min(1.0, bottom) - top, 6),
    }


def _similar(a: dict, b: dict) -> float:
    """Return a positive match score for two boxes of the same text region."""
    overlap = _iou(a, b)
    if overlap >= 0.25:
        return overlap
    ax, ay = _center(a)
    bx, by = _center(b)
    dx = abs(ax - bx)
    dy = abs(ay - by)
    width_ratio = min(a["w"], b["w"]) / max(a["w"], b["w"])
    height_ratio = min(a["h"], b["h"]) / max(a["h"], b["h"])
    if dx <= 0.04 and dy <= 0.03 and width_ratio >= 0.25 and height_ratio >= 0.5:
        return 0.32
    if dx <= 0.08 and dy <= 0.02 and height_ratio >= 0.75:
        return 0.24
    return 0.0


# ---------------------------------------------------------------- observations


def _normalized_text(text: Any) -> str:
    """One rule, shared with the edge check and the leak tool."""
    return textmatch.normalize(text)


def _observation(
    *,
    start: float,
    end: float,
    text: str,
    box: dict,
    confidence: float,
    source: str,
    approximate: bool = False,
) -> dict:
    return {
        "start": round(max(0.0, start), 3),
        "end": round(max(start, end), 3),
        "t": round((max(0.0, start) + max(start, end)) / 2.0, 3),
        "text": " ".join(str(text or "").split())[:400],
        "box": box,
        "confidence": round(_clamp(confidence), 4),
        "source": source,
        "approximate": bool(approximate),
    }


# OCR lines below this confidence are dropped; up to the noisy floor they
# must also read like words. Low-confidence reads of B-roll were mostly
# junk ("^9UM.", "OII8C", "4HIH}") that inflated "regions need cleaning".
OCR_MIN_CONFIDENCE = 0.4
OCR_NOISY_CONFIDENCE = 0.7
# A read this unsure counts only when the frames around it read the same words:
# thin text over leaves reads badly, and noise does not repeat.
OCR_WEAK_CONFIDENCE = 0.25
# Two pieces on one line further apart than this (share of frame width) are
# separate text.
LINE_PIECE_GAP = 0.04
_OCR_CLEAN_TOKEN = re.compile(r"^[\"'(\[]?[^\W\d_]+(?:['’-][^\W\d_]+)*[.,!?:;)\]\"'…]*$|^\d+(?:[.,:]\d+)*[%.,!?]?$")


def _noisy_token(token: str) -> bool:
    if not _OCR_CLEAN_TOKEN.match(token):
        return True
    letters = [char for char in token if char.isalpha()]
    # An upper-case letter after a lower-case one inside a word ("biO").
    return any(
        left.islower() and right.isupper() for left, right in zip(letters, letters[1:])
    )


def ocr_line_is_junk(text: str, confidence: float) -> bool:
    """True for OCR reads too unsure or too garbled to show or clean."""
    if confidence < OCR_MIN_CONFIDENCE:
        return True
    if confidence >= OCR_NOISY_CONFIDENCE:
        return False
    tokens = text.split()
    if not tokens:
        return True
    # Unspaced scripts (CJK) can't be judged by token shape.
    if len(tokens) == 1 and not re.search(r"[A-Za-z0-9]", tokens[0]):
        return False
    noisy = sum(1 for token in tokens if _noisy_token(token))
    return noisy * 2 >= len(tokens)


def merge_lines(
    lines: Iterable[dict],
    *,
    start: float,
    end: float,
    source: str,
    approximate: bool = False,
    keep_weak: bool = False,
) -> list[dict]:
    """Join pieces of one OCR line from a frame, so each box holds one line.

    Stacked lines stay apart: joined, a caption and a logo above it make one
    box over everything between them. ``keep_weak`` keeps unsure reads, marked,
    for :func:`_rescue_weak_reads` to judge against the frames around them.
    """
    items = []
    for line in lines or []:
        if not isinstance(line, dict):
            continue
        text = " ".join(str(line.get("text") or "").split())
        box = normalize_box(line.get("box"))
        if not text or box is None:
            continue
        confidence = _clamp(_number(line.get("confidence"), 0.5))
        weak = ocr_line_is_junk(text, confidence)
        if weak and not (keep_weak and confidence >= OCR_WEAK_CONFIDENCE):
            continue
        items.append({
            "text": text,
            "box": box,
            "confidence": confidence,
            "weak": weak,
        })
    items.sort(key=lambda item: (item["box"]["y"], item["box"]["x"]))
    merged: list[dict] = []
    for item in items:
        target = None
        for block in merged:
            box = block["box"]
            shared_height = min(box["y"] + box["h"], item["box"]["y"] + item["box"]["h"]) - max(
                box["y"], item["box"]["y"],
            )
            across = max(box["x"], item["box"]["x"]) - min(
                box["x"] + box["w"], item["box"]["x"] + item["box"]["w"],
            )
            if shared_height >= 0.5 * min(box["h"], item["box"]["h"]) and across <= LINE_PIECE_GAP:
                target = block
                break
        if target is None:
            merged.append({
                "text": item["text"],
                "box": dict(item["box"]),
                "confidence": item["confidence"],
                "lines": 1,
                "weak": item["weak"],
            })
            continue
        total = target["lines"] + 1
        target["confidence"] = (
            target["confidence"] * target["lines"] + item["confidence"]
        ) / total
        target["text"] = f"{target['text']} {item['text']}".strip()
        target["box"] = _union(target["box"], item["box"])
        target["lines"] = total
        target["weak"] = target["weak"] and item["weak"]
    return [
        {
            **_observation(
                start=start, end=end, text=block["text"], box=block["box"],
                confidence=block["confidence"], source=source,
                approximate=approximate,
            ),
            **({"weak": True} if block["weak"] else {}),
        }
        for block in merged
    ]


def observations_from_scenes(scenes: Iterable[dict]) -> list[dict]:
    """Build observations from the analysis scene OCR, keeping real boxes."""
    observations: list[dict] = []
    for scene in scenes or []:
        if not isinstance(scene, dict):
            continue
        scene_start = _number(scene.get("start"), 0.0)
        scene_end = _number(
            scene.get("end"), scene_start + _number(scene.get("dur"), 0.0),
        )
        if scene_end <= scene_start:
            continue
        # The record is one still at the scene midpoint. Treating the whole
        # scene as text evidence would overstate persistence, so keep a short
        # window around the frame.
        mid = _number(scene.get("mid"), (scene_start + scene_end) / 2.0)
        start = max(scene_start, mid - 2.0)
        end = min(scene_end, mid + 2.0)
        if end <= start:
            continue
        lines = []
        boxes = scene.get("ocr_boxes") or []
        if isinstance(boxes, list):
            for item in boxes:
                if not isinstance(item, dict):
                    continue
                lines.append({
                    "text": item.get("text"),
                    "box": item.get("box"),
                    "confidence": item.get("confidence"),
                })
        if lines:
            blocks = merge_lines(
                lines, start=start, end=end, source="scene",
            )
            _mark_screen_frame(blocks, len(lines))
            observations.extend(blocks)
            continue
        text = " ".join(str(scene.get("ocr") or "").split())
        if text:
            # Keep the text even without geometry so "no text" is never claimed.
            observations.append(_observation(
                start=start, end=end, text=text, box=dict(APPROX_BOX),
                confidence=0.5, source="scene", approximate=True,
            ))
    return observations


def _large_box(box: dict) -> bool:
    """Large display type, not a subtitle or screen UI label."""
    try:
        w = float(box.get("w") or 0.0)
        h = float(box.get("h") or 0.0)
    except (TypeError, ValueError):
        return False
    return h >= 0.12 or (h >= 0.09 and w >= 0.50) or (w * h >= 0.10)


def _track_samples(values: list[dict]) -> list[dict]:
    """Keep one per-sample box per OCR read, not only the union box."""
    samples: dict[float, dict] = {}
    for value in values:
        try:
            at = round(float(value.get("start") or 0.0), 3)
            box = value.get("box") or {}
            if not box:
                continue
            samples[at] = {
                "t": at,
                "box": {
                    "x": round(float(box.get("x") or 0.0), 6),
                    "y": round(float(box.get("y") or 0.0), 6),
                    "w": round(float(box.get("w") or 0.0), 6),
                    "h": round(float(box.get("h") or 0.0), 6),
                },
            }
        except (TypeError, ValueError):
            continue
    return [samples[key] for key in sorted(samples)][:600]


def _mark_screen_frame(blocks: list[dict], line_count: int) -> None:
    """Mark blocks from a text-heavy frame as screen-recording UI evidence."""
    if line_count < 6:
        return
    for block in blocks:
        if _large_box(block.get("box") or {}):
            continue
        block["screen_frame"] = True


def observations_from_samples(samples: Iterable[dict]) -> list[dict]:
    """Build observations from pipeline ``read_text_samples`` frames."""
    observations: list[dict] = []
    for sample in samples or []:
        if not isinstance(sample, dict):
            continue
        start = _number(sample.get("start"), _number(sample.get("t"), 0.0))
        end = _number(sample.get("end"), start)
        if end <= start:
            end = start + 1e-3
        lines = sample.get("text") or []
        blocks = merge_lines(
            lines, start=start, end=end, source="sample", keep_weak=True,
        )
        _mark_screen_frame(blocks, len(lines))
        observations.extend(blocks)
    return observations


# ---------------------------------------------------------------- clustering


def _merge_ranges(ranges: list[dict], gap: float) -> list[dict]:
    merged: list[dict] = []
    for item in sorted(ranges, key=lambda value: value["start"]):
        if merged and item["start"] - merged[-1]["end"] <= gap:
            merged[-1]["end"] = max(merged[-1]["end"], item["end"])
        else:
            merged.append({"start": item["start"], "end": item["end"]})
    return merged[:MAX_RANGES]


def _texts(observations: list[dict]) -> list[tuple[float, str]]:
    values = []
    for item in observations:
        text = _normalized_text(item.get("text"))
        if text:
            values.append((float(item["t"]), text))
    values.sort(key=lambda pair: pair[0])
    return values


def _change_gaps(tracklet: dict) -> list[float]:
    values = tracklet.get("_texts") or []
    gaps = []
    for (previous_t, previous), (current, text) in zip(values, values[1:]):
        if text != previous:
            gap = current - previous_t
            if gap > 0:
                gaps.append(gap)
    return gaps


def cluster_observations(
    observations: Iterable[dict],
    *,
    max_gap: float = TRACKLET_MAX_GAP,
) -> list[dict]:
    """Group observations into persistent tracklets by geometry and time."""
    tracks: list[dict] = []
    for item in sorted(
        (value for value in observations or [] if isinstance(value, dict)),
        key=lambda value: (value["start"], value["box"]["y"], value["box"]["x"]),
    ):
        best = None
        best_score = 0.0
        for track in tracks:
            if item["start"] - track["_end"] > max_gap:
                continue
            score = _similar(item["box"], track["_last_box"])
            if score <= 0:
                continue
            if _normalized_text(item["text"]) == _normalized_text(track["_last_text"]):
                score += 0.05
            if score > best_score:
                best = track
                best_score = score
        if best is None:
            tracks.append({
                "_last_box": dict(item["box"]),
                "_last_text": item["text"],
                "_end": item["end"],
                "_first": item["start"],
                "observations": [item],
            })
            continue
        best["observations"].append(item)
        best["_last_box"] = dict(item["box"])
        best["_last_text"] = item["text"]
        best["_end"] = max(best["_end"], item["end"])
    return tracks


def _is_corner(box: dict) -> bool:
    left = box["x"] + box["w"] <= 0.36
    right = box["x"] >= 0.64
    top = box["y"] + box["h"] <= 0.34
    bottom = box["y"] >= 0.66
    return bool((left or right) and (top or bottom))


def _platform_mark(text: str) -> bool:
    value = " ".join(str(text or "").split())
    if not value:
        return False
    if _WATERMARK_LITERAL_RE.search(value):
        return True
    stripped = re.sub(r"[^0-9A-Za-z\u3400-\u9fff ]", " ", value).strip()
    tokens = [token for token in stripped.casefold().split() if token]
    if not tokens or len(tokens) > 3:
        return False
    lowered = " ".join(tokens)
    return any(
        lowered == token or lowered == f"@{token}" or lowered.startswith(f"{token} ")
        for token in _PLATFORM_TOKENS
    )


def _handle_mark(text: str) -> bool:
    value = " ".join(str(text or "").split())
    if not value:
        return False
    return bool(
        _AT_HANDLE_RE.search(value)
        or _URL_HANDLE_RE.search(value)
        or _CALL_TO_ACTION_RE.search(value)
    )


def _screen_text_mark(text: str, box: dict) -> bool:
    """Return True for UI chrome in a screen recording.

    Known UI labels are accepted in a small block. An unknown top-status or
    bottom-tab label is accepted only when it is short, mixed case and small;
    an all-caps corner mark stays a logo target, not screen text.
    """
    value = " ".join(str(text or "").split())
    if not value:
        return False
    area = _area(box)
    height = float(box["h"])
    y = float(box["y"])
    if height > 0.08 or area > 0.06:
        return False
    edge_band = y + height <= 0.20 or y >= 0.85
    if _UI_TEXT_RE.match(value):
        return bool(edge_band)
    if len(value) > 30:
        return False
    top_band = y + height <= 0.14 and height <= 0.07 and area <= 0.05
    bottom_band = y >= 0.90 and height <= 0.06 and area <= 0.03
    if not (top_band or bottom_band):
        return False
    return not value.isupper()



def _word_pop(text: str, box: dict, corner: bool) -> bool:
    """Word-pop captions: 1-4 words, large type, centred, mid-frame.

    They sit above the caption band and change every 0.3-1.5 s, so each word
    becomes its own short tracklet. Without this rule they read as screen
    text (even over a screen recording) and could never be cleaned.
    """
    words = re.findall(r"\w+", str(text or ""))
    if not 1 <= len(words) <= 4 or corner:
        return False
    if not any(char.isalpha() for char in text):
        return False
    height = float(box["h"])
    centre = float(box["x"]) + float(box["w"]) / 2.0
    top = float(box["y"])
    return (
        height >= 0.035
        and abs(centre - 0.5) <= 0.18
        and 0.30 <= top <= 0.85
        and _area(box) <= 0.08
    )


def classify(tracklet: dict, duration: float) -> tuple[str, float]:
    """Return ``(kind, rule_confidence)`` for one tracklet."""
    box = tracklet["box"]
    area = _area(box)
    width = float(box["w"])
    height = float(box["h"])
    y = float(box["y"])
    bottom = y + height
    observed = tracklet.get("duration") or 0.0
    samples = int(tracklet.get("samples") or 0)
    gaps = _change_gaps(tracklet)
    changes = len(gaps)
    median_gap = float(np.median(gaps)) if gaps else 0.0
    text = str(tracklet.get("text_sample") or "")
    corner = _is_corner(box)
    watermark_like = _platform_mark(text)
    handle_like = _handle_mark(text)

    # A platform mark in a small corner is a watermark. A title card that
    # happens to name a platform is not.
    if watermark_like and (corner or area <= 0.04) and area <= 0.12:
        return "watermark", 0.9
    if _WATERMARK_LITERAL_RE.search(text):
        return "watermark", 0.95

    if handle_like and corner and area <= 0.10:
        return "handle_or_logo", 0.8

    if _large_box(box) and any(char.isalpha() for char in text) and not corner:
        return "title", 0.8

    # A line of display type across the top of the frame is a title card, even
    # when the OCR box is smaller than the usual title. Captions sit lower.
    if (
        bottom <= 0.42 and height >= 0.05 and width >= 0.30
        and area <= 0.12 and any(char.isalpha() for char in text)
        and not corner
    ):
        return "title", 0.7

    if _word_pop(text, box, corner):
        return "subtitle", 0.75

    if tracklet.get("screen_frame"):
        return "screen_text", 0.75

    if _screen_text_mark(text, box):
        rule = 0.8 if (_is_corner(box) or samples >= 2) else 0.65
        return "screen_text", rule

    # Screen-recording body text, menus and code are small and wide. Captions
    # and word-pop titles use a larger face. Height separates the two on real
    # screen-recorded sources better than position alone.
    if height <= 0.024 and area <= 0.03:
        return "screen_text", 0.7
    letters = [char for char in text if char.isalpha()]
    upper_ratio = (
        sum(1 for char in letters if char.isupper()) / len(letters)
        if letters else 0.0
    )
    if (
        len(text) <= 20 and width <= 0.20 and height <= 0.06
        and upper_ratio >= 0.8 and not corner
    ):
        return "screen_text", 0.55
    if height <= 0.25 and area <= 0.20 and (
        len(text) >= 40 or _UI_WORD_RE.search(text)
    ):
        return "screen_text", 0.6
    if len(text) >= 80 and area <= 0.5:
        return "screen_text", 0.6
    if _CODE_RE.search(text) and area <= 0.30:
        return "screen_text", 0.6
    if (
        y + height <= 0.20 and height <= 0.05 and width >= 0.10
        and not text.isupper()
    ):
        return "screen_text", 0.55

    if corner and area <= 0.03 and samples >= 2 and observed >= 2.0:
        return "handle_or_logo", 0.65

    lower_band = y >= 0.58
    caption_shape = height <= 0.20 and (
        (lower_band and width >= 0.28) or (y >= 0.42 and width >= 0.45)
    )
    if caption_shape:
        if changes >= 2 and 0.5 <= median_gap <= 7.0:
            return "subtitle", 0.85
        if changes == 1 and median_gap <= 7.0 and bottom >= 0.66:
            return "subtitle", 0.75
        if changes == 0 and samples <= 1 and y >= 0.66 and width >= 0.42 and len(text) >= 10:
            return "subtitle", 0.6
        if (
            changes == 0 and samples >= 2 and width >= 0.55
            and bottom >= 0.72 and len(text) >= 20
        ):
            return "subtitle", 0.65

    # Mid-frame word-pop captions sit above the caption band but are larger
    # than UI text and change every few seconds.
    if (
        y >= 0.45 and height >= 0.028 and width >= 0.25 and area <= 0.08
        and (changes >= 1 or samples <= 3)
    ):
        return "subtitle", 0.65

    if area <= 0.014 and height <= 0.055 and bottom >= 0.74 and samples >= 1:
        return "credit", 0.6

    if (
        lower_band and width >= 0.12 and bottom <= 0.96
        and area <= 0.09 and height <= 0.22 and changes <= 1
    ):
        rule = 0.7 if observed >= 1.0 else 0.55
        return "lower_third", rule

    if area >= 0.035 or (height >= 0.08 and width >= 0.20):
        return "title", 0.8

    if area <= 0.014 and (y <= 0.18 or bottom >= 0.82):
        return "credit", 0.5

    if duration and observed >= max(2.0, 0.5 * duration) and area >= 0.02:
        return "title", 0.55
    return "lower_third" if y >= 0.5 else "title", 0.45


def _track_box(track: dict) -> dict:
    values = track["observations"]
    box = dict(values[0]["box"])
    for value in values[1:]:
        box = _union(box, value["box"])
    return box


def _join_returning_text(tracks: list[dict]) -> list[dict]:
    """One track per text and area, however long the text was off screen."""
    joined: list[dict] = []
    for track in tracks:
        words = {_normalized_text(item["text"]) for item in track["observations"]} - {""}
        box = _track_box(track)
        match = next(
            (
                other for other in joined
                if words & other["_words"] and _similar(box, other["_box"]) >= 0.3
            ),
            None,
        )
        if match is None:
            joined.append({**track, "_words": words, "_box": box})
            continue
        match["observations"].extend(track["observations"])
        match["_words"] |= words
        match["_box"] = _union(match["_box"], box)
    return joined


def _stable_tracklet_id(item: dict, used: set[str]) -> str:
    """An id from the text and area, so a rescan keeps it for the same text."""
    cx, cy = _center(item["box"])
    text = _normalized_text(item.get("text_sample"))
    seed = f"{text}|{round(cx / 0.05)}|{round(cy / 0.05)}"
    if not text:
        ranges = item.get("ranges") or [{}]
        seed += f"|{round(float(ranges[0].get('start') or 0.0), 1)}"
    base = f"trk_{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:10]}"
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _keep_text_outside_scope(report: dict, previous: dict | None, start: float, end: float) -> None:
    """A scene scan adds to the last report, so it does not lose the rest."""
    if not isinstance(previous, dict) or previous.get("status") != "ready":
        return

    def outside(ranges: Any) -> list[dict]:
        pieces: list[dict] = []
        for item in ranges if isinstance(ranges, list) else []:
            if not isinstance(item, dict):
                continue
            low, high = _number(item.get("start"), 0.0), _number(item.get("end"), 0.0)
            if low < start:
                pieces.append({"start": low, "end": min(high, start)})
            if high > end:
                pieces.append({"start": max(low, end), "end": high})
        return [piece for piece in pieces if piece["end"] > piece["start"]]

    # The id comes from the words and the area, so text seen again in this scan
    # has the same id. It joins its old row instead of listing twice.
    current = {str(item.get("id")): item for item in report.get("tracklets") or []}
    kept: list[dict] = []
    for item in previous.get("tracklets") or []:
        rest = outside(item.get("ranges"))
        if not rest:
            continue
        match = current.get(str(item.get("id")))
        if match is None:
            kept.append({**item, "ranges": rest})
            continue
        match["ranges"] = _merge_ranges(
            sorted([*(match.get("ranges") or []), *rest], key=lambda value: value["start"]),
            0.0,
        )
        if isinstance(match.get("box"), dict) and isinstance(item.get("box"), dict):
            match["box"] = _union(match["box"], item["box"])
    if not kept and not any(
        outside(item.get("ranges")) for item in previous.get("tracklets") or []
    ):
        return
    report["tracklets"] = sorted(
        [*kept, *(report.get("tracklets") or [])],
        key=lambda item: (
            _number((item.get("ranges") or [{}])[0].get("start"), 0.0), str(item.get("id") or ""),
        ),
    )
    known = {str(item.get("id")) for item in report["tracklets"]}
    seen = {str(entry.get("tracklet_id")) for entry in report.get("clean_prefill") or []}
    report["clean_prefill"] = [
        *(report.get("clean_prefill") or []),
        *(
            entry for entry in previous.get("clean_prefill") or []
            if str(entry.get("tracklet_id")) in known and str(entry.get("tracklet_id")) not in seen
        ),
    ]
    # The whole video was read, so this stays a whole-video report.
    if not previous.get("scope"):
        report.pop("scope", None)


def _same_line(first: str, second: str) -> bool:
    """Two readings of one line, allowing for OCR misreads."""
    a, b = _normalized_text(first), _normalized_text(second)
    if not a or not b or a == b:
        return True
    # Text typing itself on, or a read that caught part of the line.
    if min(len(a), len(b)) >= 4 and (a in b or b in a):
        return True
    return SequenceMatcher(None, a, b, autojunk=False).ratio() >= LINE_MATCH


def _line_runs(values: list[dict]) -> list[list[dict]]:
    """Split one area's readings into the separate lines shown in it.

    A new run starts when the words change, the box moves away, or the text
    leaves the screen for longer than one missed frame.
    """
    runs: list[list[dict]] = []
    for value in values:
        last = runs[-1] if runs else None
        if last is not None:
            window = max(0.001, float(value["end"]) - float(value["start"]))
            words = max((item["text"] for item in last), key=len)
            if (
                float(value["start"]) - float(last[-1]["end"]) <= 1.5 * window
                and _same_line(value["text"], words)
                and _similar(value["box"], last[-1]["box"]) > 0
            ):
                last.append(value)
                continue
        runs.append([value])
    return runs


def _run_range(run: list[dict], duration: float) -> dict:
    """The time a line is on screen, from the frames that read it.

    A sampled frame says the text was there at that moment, and it changed
    somewhere between two frames. A layer that starts late shows the text, so
    the range reaches back to the reading before, and past the last one by the
    sampler's slack.
    """
    start = float(run[0]["start"])
    end = float(run[-1]["end"])
    if run[0].get("source") == "sample":
        step = float(run[0]["end"]) - float(run[0]["start"])
        start = max(0.0, start - step)
        end = max(start + 0.001, float(run[-1]["end"]) + SAMPLE_SLACK)
    if duration > 0:
        end = min(duration, end)
    return {"start": round(start, 3), "end": round(end, 3)}


def _line_tracklets(item: dict, values: list[dict], duration: float) -> list[dict]:
    """One tracklet per line, each with its own tight box and time."""
    lines: list[list[list[dict]]] = []
    for run in _line_runs(values):
        words = _normalized_text(max((value["text"] for value in run), key=len, default=""))
        home = next(
            (
                line for line in lines
                if words and words == _normalized_text(
                    max((value["text"] for value in line[0]), key=len, default=""),
                )
            ),
            None,
        )
        if home is None:
            lines.append([run])
        else:
            home.append(run)
    out = []
    for line in lines:
        seen = [value for run in line for value in run]
        box = dict(seen[0]["box"])
        for value in seen[1:]:
            box = _union(box, value["box"])
        spans = _merge_ranges([_run_range(run, duration) for run in line], 0.0)
        out.append({
            **item,
            "box": box,
            "ranges": spans,
            "text_sample": max((value["text"] for value in seen), key=len, default="")[:80],
            "track": _track_samples(seen),
            "large": _large_box(box),
            "samples": len({int(value["start"] // 2.0) for value in seen}),
            "duration": round(sum(span["end"] - span["start"] for span in spans), 3),
            "approximate": any(value.get("approximate") for value in seen),
        })
    return out


def _rescue_weak_reads(observations: list[dict]) -> list[dict]:
    """Keep an unsure read only when a neighbouring frame read the same words."""
    ordered = sorted(observations, key=lambda value: value["start"])
    kept = []
    for index, item in enumerate(ordered):
        if not item.get("weak"):
            kept.append(item)
            continue
        window = 1.5 * max(0.001, float(item["end"]) - float(item["start"]))
        for other in (*ordered[max(0, index - 40):index], *ordered[index + 1:index + 41]):
            if (
                abs(float(other["start"]) - float(item["start"])) <= window
                and float(other["start"]) != float(item["start"])
                and _similar(item["box"], other["box"]) > 0
                and _same_line(item["text"], other["text"])
            ):
                kept.append(item)
                break
    return kept


def _inside_share(inner: dict, outer: dict) -> float:
    """How much of ``inner`` sits inside ``outer``."""
    width = min(inner["x"] + inner["w"], outer["x"] + outer["w"]) - max(inner["x"], outer["x"])
    height = min(inner["y"] + inner["h"], outer["y"] + outer["h"]) - max(inner["y"], outer["y"])
    if width <= 0 or height <= 0:
        return 0.0
    return width * height / max(1e-9, _area(inner))


def _same_text_at_same_time(first: dict, second: dict) -> bool:
    """Two readings of one piece of text, near each other in time and place."""
    close_in_time = any(
        min(a["end"], b["end"]) - max(a["start"], b["start"]) > -0.6
        for a in first["ranges"] for b in second["ranges"]
    )
    return (
        close_in_time
        and _inside_share(second["box"], first["box"]) >= 0.6
        and _same_line(first["text_sample"], second["text_sample"])
    )


def _without_repeats(items: list[dict]) -> list[dict]:
    """One tracklet per text. Separate areas can read the same line twice."""
    kept: list[dict] = []
    for item in sorted(items, key=lambda value: -_area(value["box"])):
        home = next((other for other in kept if _same_text_at_same_time(other, item)), None)
        if home is None:
            kept.append(item)
            continue
        home["ranges"] = _merge_ranges([*home["ranges"], *item["ranges"]], 0.0)
        home["box"] = _union(home["box"], item["box"])
        home["duration"] = round(sum(span["end"] - span["start"] for span in home["ranges"]), 3)
        home["samples"] = int(home.get("samples") or 0) + int(item.get("samples") or 0)
        if len(_normalized_text(item["text_sample"])) > len(_normalized_text(home["text_sample"])):
            home["text_sample"] = item["text_sample"]
        if item["kind"] == "subtitle":
            home["kind"] = "subtitle"
    return kept


def _mark_minor(items: list[dict]) -> None:
    """Flag what is likely in the scene, not on top of it: Clean leaves it unticked.

    Words on a product show up in many places, and small print sits far below
    the size of the video's main text. They stay listed and can be ticked.
    """
    heights = sorted(item["box"]["h"] for item in items)
    usual = heights[len(heights) // 2] if heights else 0.0
    for item in items:
        places = sum(
            1 for other in items
            if not (_similar(item["box"], other["box"]) > 0)
            and _same_line(item["text_sample"], other["text_sample"])
        )
        if places >= 2 or item["box"]["h"] < 0.6 * usual:
            item["minor"] = True


def plan_fills(tracklets: list[dict], frames: list[dict], motion: dict | None, source: dict) -> None:
    """Give each line a fill plan from how the picture moves around it, in this video.

    ``fill_plan.keys`` is AI fills per second: 0 means one for the whole line. It
    is read against this video's own quietest parts, its noise, so a grainy video
    is not treated as a moving one. Lines with no reading keep no plan.
    """
    maps = (motion or {}).get("maps") or []
    usable = [item for item in maps if item is not None]
    if not usable or len(maps) != len(frames):
        return
    scale = float((motion or {}).get("scale") or 1.0)
    noise = max(MOTION_NOISE_FLOOR, float(np.percentile(np.stack(usable), 5)) / scale)
    rows, cols = usable[0].shape
    aspect = float(source.get("height") or 16) / float(source.get("width") or 9)
    for tracklet in tracklets:
        box = tracklet["box"]
        margin_y = max(float(box["h"]), 0.01)
        margin_x = margin_y * aspect
        ring = np.zeros((rows, cols), dtype=bool)
        ring[
            int(max(0.0, box["y"] - margin_y) * rows):int(np.ceil(min(1.0, box["y"] + box["h"] + margin_y) * rows)),
            int(max(0.0, box["x"] - margin_x) * cols):int(np.ceil(min(1.0, box["x"] + box["w"] + margin_x) * cols)),
        ] = True
        ring[
            int(box["y"] * rows):int(np.ceil((box["y"] + box["h"]) * rows)),
            int(box["x"] * cols):int(np.ceil((box["x"] + box["w"]) * cols)),
        ] = False
        if not ring.any():
            continue
        readings = [
            float(change[ring].mean()) / scale
            for frame, change in zip(frames, maps)
            if change is not None and any(
                float(span["start"]) <= float(frame["start"]) <= float(span["end"])
                for span in tracklet.get("ranges") or []
            )
        ]
        if not readings:
            continue
        # The middle reading: one jump, such as a cut, is not how the line moves.
        moved = float(np.median(readings))
        keys = 0.0
        if moved > MOTION_STILL_TIMES * noise:
            keys = min(MOTION_MOST_KEYS, 1.0 + moved / (MOTION_KEY_TIMES * noise))
        tracklet["fill_plan"] = {
            "motion": round(moved, 2),
            "noise": round(noise, 2),
            "keys": round(keys, 1),
        }



def edge_end_from_hits(
    hits: Iterable[float],
    end: float,
    *,
    fps: float = 30.0,
    forward: float = 0.15,
) -> float:
    """The end that a set of matching frame times supports.

    Pure so the rule can be tested without OCR: the last frame where the words
    are present, plus one frame, never more than ``forward`` past the old end.
    """
    times = sorted(float(value) for value in hits if float(value) >= 0.0)
    if not times:
        return float(end)
    step = 1.0 / max(1.0, float(fps))
    return min(float(end) + float(forward), times[-1] + step)


def _probe_edges(
    folder: Path,
    files: list[Path],
    *,
    lo: float,
    fps: float,
    words: str,
    vision: Any,
) -> list[float]:
    """Frame times in ``folder`` whose OCR matches ``words``."""
    records = vision.probe_images(folder, files=files)
    hits: list[float] = []
    for index, path in enumerate(files):
        record = records.get(path.name) or {}
        for line in record.get("text") or []:
            if float(line.get("confidence") or 0.0) < 0.3:
                continue
            if textmatch.same_text(line.get("text"), words):
                hits.append(lo + index / fps)
                break
    return hits


def refine_tracklet_edges(
    tracklets: list[dict],
    source: str,
    job_dir: Path,
    *,
    fps: float = 30.0,
    window: float = 0.4,
    forward: float = 0.15,
    width: int = 0,
    height: int = 0,
) -> int:
    """Move each line's end to the last frame that really shows it.

    A 4 fps read knows an edge to a quarter second, and OCR can miss a frame, so
    a range could end before the last frame of text. Around each end this reads
    the source at its own frame rate and keeps the last frame where the line is
    still there. It never widens a range past one frame.
    """
    from . import vision
    from .textfill import mask as masks
    from duckcore import media
    import shutil
    import subprocess
    import tempfile

    if os.environ.get("DUCK_EDGE_REFINE", "1").strip().lower() in {"0", "off", "false", "no"}:
        return 0
    if not tracklets or not vision.available() or not Path(source).is_file():
        LOGGER.info(
            "edge refine skipped: tracklets=%s vision=%s source=%s",
            len(tracklets or []), vision.available(), Path(source).is_file(),
        )
        return 0
    fps = max(1.0, float(fps))
    ffmpeg = media.ffmpeg()

    def ink_edge(box: dict, start: float, end: float) -> tuple[float, float] | None:
        """The line's real edges from its ink, or None when there is no ink."""
        from duckcore import inkcheck

        if width < 2 or height < 2 or end <= start:
            return None
        rect = inkcheck.search_rect({"box": box}, width, height)
        try:
            built = inkmod.build(source, rect, start=start, end=end, fps=fps)
        except inkmod.InkError as exc:
            LOGGER.warning("ink edge failed near %.3f s: %s", end, exc)
            return None
        if built is None:
            return None
        # The line's own extent, not a glyph it shares with the next line. One
        # frame of guard each side for a fading frame under the threshold.
        step = 1.0 / fps
        return max(0.0, built.start - step), built.end + step

    changed = 0
    for tracklet in tracklets:
        words = textmatch.compact(tracklet.get("text_sample"))
        if not words:
            continue
        for span in tracklet.get("ranges") or []:
            end = float(span.get("end") or 0.0)
            if end <= 0.0:
                continue
            edge = ink_edge(tracklet.get("box") or {}, float(span.get("start") or 0.0), end)
            if edge is not None:
                start, new_end = edge
                if abs(start - float(span.get("start") or 0.0)) > 0.001 or abs(new_end - end) > 0.001:
                    span["start"] = round(start, 3)
                    span["end"] = round(new_end, 3)
                    changed += 1
                continue
            # A short card can sit far inside the padded edge (a 66 ms title
            # ended at 0.317 s), so look further back than forward.
            lo = max(0.0, end - float(window))
            hi = end + float(forward)
            temp = Path(tempfile.mkdtemp(prefix="edge-", dir=job_dir))
            try:
                subprocess.run(
                    [ffmpeg, "-y", "-v", "error", "-ss", f"{lo:.3f}", "-to", f"{hi:.3f}",
                     "-i", source, "-vf", f"fps={fps:.3f},scale=960:-2", "-q:v", "4",
                     str(temp / "%04d.jpg")],
                    check=True, capture_output=True,
                )
                files = sorted(temp.glob("*.jpg"))
                if not files:
                    continue
                hits = _probe_edges(
                    temp, files, lo=lo, fps=fps, words=words, vision=vision,
                )
                new = edge_end_from_hits(
                    hits, end, fps=fps, forward=float(forward),
                )
                if abs(new - end) > 0.001:
                    span["end"] = round(new, 3)
                    changed += 1
            except (OSError, subprocess.SubprocessError) as exc:
                LOGGER.warning("edge refine failed near %.3f s: %s", end, exc)
            finally:
                shutil.rmtree(temp, ignore_errors=True)
    return changed


def build_tracklets(
    observations: Iterable[dict],
    duration: float,
    *,
    max_gap: float = TRACKLET_MAX_GAP,
    max_tracklets: int = MAX_TRACKLETS,
) -> list[dict]:
    """Cluster observations and attach the public tracklet fields."""
    observed = _rescue_weak_reads([
        value for value in observations or [] if isinstance(value, dict)
    ])
    tracks = _join_returning_text(cluster_observations(observed, max_gap=max_gap))
    duration = max(0.0, float(duration or 0.0))
    items: list[dict] = []
    for track in tracks:
        values = sorted(track["observations"], key=lambda value: value["start"])
        box = dict(values[0]["box"])
        for value in values[1:]:
            box = _union(box, value["box"])
        ranges = _merge_ranges(
            [{"start": value["start"], "end": value["end"]} for value in values],
            max_gap,
        )
        observed = sum(item["end"] - item["start"] for item in ranges)
        confidence = sum(value["confidence"] for value in values) / len(values)
        texts = _texts(values)
        text_sample = max(
            (value["text"] for value in values), key=len, default="",
        )[:80]
        item = {
            "id": "",
            "kind": "title",
            "box": box,
            "ranges": ranges,
            "text_sample": text_sample,
            "confidence": round(confidence, 3),
            # In two-second steps, whatever the scan's rate: classify() counts
            # how long text lasted, not how often it was read.
            "samples": len({int(value["start"] // 2.0) for value in values}),
            "duration": round(observed, 3),
            "approximate": any(value.get("approximate") for value in values),
            "screen_frame": (
                sum(1 for value in values if value.get("screen_frame"))
                >= max(1, len(values) / 2.0)
            ),
            "_texts": texts,
            "_observed": observed,
            "_sources": sorted({value.get("source") for value in values}),
        }
        kind, rule = classify(item, duration)
        item["kind"] = kind
        item["confidence"] = round(_clamp(
            0.6 * confidence + 0.4 * rule
            + (0.05 if len(values) >= 3 else 0.0),
        ), 3)
        items.extend(_line_tracklets(item, values, duration))
    items = _without_repeats(items)
    _mark_minor(items)
    items.sort(key=lambda value: (
        value["ranges"][0]["start"] if value["ranges"] else 0.0,
        value["box"]["y"], value["box"]["x"],
    ))
    limit = max(0, int(max_tracklets))
    used_ids: set[str] = set()
    for item in items[:limit]:
        item["id"] = _stable_tracklet_id(item, used_ids)
    result = []
    for item in items[:limit]:
        item.pop("_texts", None)
        item.pop("_observed", None)
        item.pop("_sources", None)
        result.append(item)
    return result


# ---------------------------------------------------------------- signals


def speech_signal(scenes: Iterable[dict], duration: float) -> dict:
    """Measure speech coverage from the analysis transcript attachment."""
    scenes = [scene for scene in scenes or [] if isinstance(scene, dict)]
    duration = max(0.0, float(duration or 0.0))
    if not scenes or duration <= 0:
        return {
            "available": False, "speech_seconds": 0.0, "speech_ratio": None,
            "ranges": [], "transcript": False,
        }
    spoken = [
        scene for scene in scenes
        if str(scene.get("speech") or "").strip()
    ]
    ranges = _merge_ranges([
        {
            "start": round(_number(scene.get("start"), 0.0), 3),
            "end": round(_number(scene.get("end"), 0.0), 3),
        }
        for scene in spoken
        if _number(scene.get("end"), 0.0) > _number(scene.get("start"), 0.0)
    ], 0.0)
    seconds = sum(item["end"] - item["start"] for item in ranges)
    return {
        "available": True,
        "speech_seconds": round(seconds, 3),
        "speech_ratio": round(min(1.0, seconds / duration), 4),
        "ranges": ranges,
        "transcript": True,
    }


def _db(value: Any, default: float = -60.0) -> float:
    return _number(value, default)


def music_from_scenes(scenes: Iterable[dict]) -> dict:
    """Fallback music estimate from scene audio levels.

    Without the source audio this can only say that non-speech spans carry
    steady energy. It never distinguishes music from noise.
    """
    scenes = [scene for scene in scenes or [] if isinstance(scene, dict)]
    if not scenes:
        return {
            "available": False, "present": None, "score": 0.0,
            "method": "scene_levels", "speech_aware": False,
        }
    total = 0.0
    loud = 0.0
    signal = False
    speech_aware = any(str(scene.get("speech") or "").strip() for scene in scenes)
    for scene in scenes:
        span = max(0.0, _number(scene.get("end"), 0.0) - _number(scene.get("start"), 0.0))
        if _db(scene.get("audio_mean")) > -59.0:
            signal = True
        if span <= 0:
            continue
        if speech_aware and str(scene.get("speech") or "").strip():
            continue
        total += span
        if _db(scene.get("audio_mean")) > -38.0 and _number(scene.get("silence"), 1.0) < 0.5:
            loud += span
    score = loud / total if total > 0 else 0.0
    available = bool(total > 0)
    return {
        "available": available,
        "present": bool(score >= 0.35) if signal else False,
        "score": round(score, 3),
        "method": "scene_levels",
        "speech_aware": speech_aware,
        "non_speech_seconds": round(total, 3),
    }


def _read_mono(path: Path) -> tuple[int, np.ndarray]:
    with wave.open(str(path), "rb") as reader:
        rate = reader.getframerate()
        channels = reader.getnchannels()
        width = reader.getsampwidth()
        raw = reader.readframes(reader.getnframes())
    if width != 2:
        return rate, np.zeros(0, dtype=np.float32)
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return rate, samples


def _in_spans(moment: float, starts: list[float], spans: list[tuple[float, float]]) -> bool:
    index = bisect_right(starts, moment) - 1
    return index >= 0 and spans[index][0] <= moment < spans[index][1]


def music_from_wav(
    path: Path | str,
    speech_ranges: Iterable[dict] | None = None,
    *,
    window_s: float = 0.2,
) -> dict:
    """Estimate music presence from energy stability and spectral flatness.

    Speech spans are excluded. A steady bed scores high; silence and sparse
    speech score low. This is deliberately conservative: ``present`` is only
    true with enough sustained non-speech energy.
    """
    path = Path(path)
    try:
        rate, samples = _read_mono(path)
    except (OSError, wave.Error):
        return {
            "available": False, "present": None, "score": 0.0,
            "method": "energy_stability", "speech_aware": False,
        }
    size = max(1, int(rate * window_s))
    if rate <= 0 or len(samples) < size:
        return {
            "available": False, "present": None, "score": 0.0,
            "method": "energy_stability", "speech_aware": False,
        }
    spans = sorted(
        (
            (_number(item.get("start"), 0.0), _number(item.get("end"), 0.0))
            for item in (speech_ranges or [])
            if isinstance(item, dict)
            and _number(item.get("end"), 0.0) > _number(item.get("start"), 0.0)
        ),
    )
    starts = [span[0] for span in spans]
    speech_aware = bool(spans)

    levels: list[float] = []
    flatness: list[float] = []
    zero_cross: list[float] = []
    for offset in range(0, len(samples) - size + 1, size):
        block = samples[offset:offset + size]
        moment = (offset + size / 2) / rate
        if speech_aware and _in_spans(moment, starts, spans):
            continue
        rms = float(np.sqrt(np.mean(block * block) + 1e-12))
        levels.append(20.0 * math.log10(rms + 1e-8))
        signs = np.signbit(block)
        zero_cross.append(float(np.mean(signs[1:] != signs[:-1])))
        spectrum = np.abs(np.fft.rfft(block * np.hanning(len(block)))) + 1e-9
        flatness.append(float(np.exp(np.mean(np.log(spectrum))) / np.mean(spectrum)))

    if not levels:
        return {
            "available": False, "present": None, "score": 0.0,
            "method": "energy_stability", "speech_aware": speech_aware,
        }
    level = np.asarray(levels, dtype=float)
    active = level > -42.0
    if not np.any(active):
        return {
            "available": True, "present": False, "score": 0.0,
            "flatness": 0.0, "speech_aware": speech_aware,
            "non_speech_seconds": round(len(levels) * window_s, 3),
            "method": "energy_stability",
        }
    stability = 1.0 - min(1.0, float(np.std(level[active])) / 12.0)
    coverage = float(np.mean(active))
    flatness_mean = float(np.mean(np.asarray(flatness)[active]))
    zero_cross_mean = float(np.mean(np.asarray(zero_cross)[active]))
    tonal = 1.0 - min(1.0, flatness_mean / 0.35)
    score = _clamp(0.55 * stability + 0.25 * coverage + 0.20 * tonal)
    seconds = len(levels) * window_s
    present = bool(seconds >= 5.0 and score >= 0.45 and coverage >= 0.5)
    return {
        "available": True,
        "present": present,
        "score": round(score, 3),
        "flatness": round(flatness_mean, 4),
        "zero_crossing": round(zero_cross_mean, 4),
        "speech_aware": speech_aware,
        "non_speech_seconds": round(seconds, 3),
        "method": "energy_stability",
    }


def faces_signal(scenes: Iterable[dict], duration: float) -> dict:
    scenes = [scene for scene in scenes or [] if isinstance(scene, dict)]
    duration = max(0.0, float(duration or 0.0))
    ranges = []
    boxes: list[dict] = []
    seen: set[tuple] = set()
    count = 0
    for scene in scenes:
        faces = scene.get("faces")
        if not faces:
            attention = scene.get("attention") or {}
            face = attention.get("face")
            faces = [face] if isinstance(face, dict) else []
        if not isinstance(faces, list) or not faces:
            continue
        start = _number(scene.get("start"), 0.0)
        end = _number(scene.get("end"), 0.0)
        if end <= start:
            continue
        ranges.append({"start": round(start, 3), "end": round(end, 3)})
        count = max(count, len(faces))
        for face in faces:
            if not isinstance(face, dict):
                continue
            box = normalize_box(face)
            if box is None or len(boxes) >= 20:
                continue
            key = tuple(round(box[name], 3) for name in ("x", "y", "w", "h"))
            if key in seen:
                continue
            seen.add(key)
            boxes.append({
                **box,
                "confidence": round(_clamp(_number(face.get("confidence"), 0.5)), 3),
            })
    merged = _merge_ranges(ranges, 0.0)
    seconds = sum(item["end"] - item["start"] for item in merged)
    return {
        "present": bool(merged),
        "count": count,
        "coverage": round(min(1.0, seconds / duration), 4) if duration else 0.0,
        "ranges": merged,
        "boxes": boxes,
    }


def quality_signal(source: dict) -> dict:
    source = source or {}
    width = int(_number(source.get("width"), 0))
    height = int(_number(source.get("height"), 0))
    fps = _number(source.get("fps"), 0.0)
    duration = _number(source.get("duration"), 0.0)
    size = _number(source.get("size"), 0.0)
    orientation = "square"
    if width and height:
        orientation = "portrait" if height > width else ("landscape" if width > height else "square")
    bitrate = (size * 8.0 / duration / 1_000_000.0) if duration > 0 and size > 0 else 0.0
    pixels = float(width * height)
    bits_per_pixel = (
        bitrate * 1_000_000.0 / (pixels * max(fps, 1.0))
        if bitrate > 0 and pixels > 0 else 0.0
    )
    issues: list[dict] = []
    short_side = min(width, height) if width and height else 0
    if short_side and short_side < 720:
        issues.append({
            "code": "low_resolution",
            "severity": "warning",
            "message": f"Source is {width}×{height}. Reframing to 9:16 will upscale.",
        })
    if bitrate and bitrate < 1.5:
        issues.append({
            "code": "low_bitrate",
            "severity": "warning",
            "message": f"Bitrate is {bitrate:.1f} Mbps. Detail may fall apart after cropping.",
        })
    if bits_per_pixel and bits_per_pixel < 0.025:
        issues.append({
            "code": "heavy_compression",
            "severity": "warning",
            "message": "This file is heavily compressed. Cleanup blur may look worse.",
        })
    if not width or not height:
        issues.append({
            "code": "unknown_dimensions",
            "severity": "warning",
            "message": "Source dimensions are missing; quality checks are limited.",
        })
    return {
        "width": width,
        "height": height,
        "fps": round(fps, 3),
        "duration": round(duration, 3),
        "orientation": orientation,
        "bitrate_mbps": round(bitrate, 3),
        "bits_per_pixel": round(bits_per_pixel, 5),
        "issues": issues,
    }


def _speech_available(analysis: dict) -> bool:
    transcript = analysis.get("transcript")
    if isinstance(transcript, dict) and transcript:
        return True
    engine = analysis.get("engine") or {}
    return bool(engine.get("whisper"))


# ---------------------------------------------------------------- attestation


def normalize_attestation(value: Any) -> bool:
    """Compatibility alias for :func:`rights.normalize_attestation`."""
    return rights.normalize_attestation(value)


def _job_attestation(job: dict) -> tuple[bool, str | None]:
    rights = job.get("rights")
    if isinstance(rights, dict) and "attested" in rights:
        return normalize_attestation(rights.get("attested")), "job"
    if "attestation" in job:
        return normalize_attestation(job.get("attestation")), "job"
    options = job.get("options")
    if isinstance(options, dict) and "attestation" in options:
        return normalize_attestation(options.get("attestation")), "job_options"
    return False, None


# ---------------------------------------------------------------- report


def _tracklet_ref(tracklet: dict) -> dict:
    return {
        "tracklet_id": tracklet["id"],
        "kind": tracklet["kind"],
        "box": dict(tracklet["box"]),
        "ranges": [dict(item) for item in tracklet["ranges"]],
    }


def _policy_job(job: dict | None, attested: bool | None) -> dict | None:
    """Let an explicit ``attested`` override the job's stored record.

    Check's report builder may hold a request-level attestation that has not
    been written to the job yet. Server gates pass the job only, so their
    evidence always comes from the stored record.
    """
    if attested is None:
        return job
    if job is None:
        return {"rights": {"attested": bool(attested)}}
    merged = dict(job)
    merged["rights"] = {"attested": bool(attested)}
    return merged


def cleanup_block_reason(
    kind: str,
    *,
    attested: bool | None = None,
    job: dict | None = None,
    settings: dict | None = None,
) -> str | None:
    """Thin wrapper over :func:`rights.clean_block_reason`.

    Older callers pass ``attested`` only. New callers pass the job and let
    ``rights`` decide with the stored setting.
    """
    return rights.clean_block_reason(
        kind, job=_policy_job(job, attested), settings=settings,
    )


def clean_prefill(
    tracklets: Iterable[dict],
    *,
    attested: bool | None = None,
    job: dict | None = None,
    settings: dict | None = None,
) -> list[dict]:
    """Advisory Clean layer entries. Never enables a refused watermark."""
    policy_job = _policy_job(job, attested)
    entries: list[dict] = []
    for tracklet in tracklets:
        kind = tracklet["kind"]
        box = tracklet["box"]
        entry = {
            **_tracklet_ref(tracklet),
            "action": "blur",
            "enabled": False,
            "confidence": tracklet["confidence"],
            "reason": "",
            "blocked": cleanup_block_reason(
                kind, job=policy_job, settings=settings,
            ),
        }
        entry["enabled"] = entry["blocked"] is None
        if kind == "handle_or_logo":
            edge = (
                box["x"] + box["w"] <= 0.28
                or box["x"] >= 0.72
                or box["y"] + box["h"] <= 0.18
                or box["y"] >= 0.82
            )
            entry["action"] = "crop_guard" if edge else "blur"
            entry["enabled"] = False
            entry["blocked"] = cleanup_block_reason(
                kind, job=policy_job, settings=settings,
            )
            entry["reason"] = (
                "Own handle or logo. Off by default; enable it for your own footage."
            )
            entries.append(entry)
            continue
        if kind == "subtitle":
            entry["action"] = "delogo"
            entry["reason"] = (
                "Remove burned-in subtitle by interpolating nearby pixels. "
                "Review the patch at 1×; it is not generative repair."
            )
            entries.append(entry)
            continue
        if kind == "title":
            entry["action"] = "delogo"
            entry["reason"] = "Remove burned-in title by interpolating nearby pixels."
            entries.append(entry)
            continue
        if kind == "lower_third":
            entry["action"] = "delogo"
            entry["reason"] = "Remove burned-in lower third by interpolating nearby pixels."
            entries.append(entry)
            continue
        if kind == "credit":
            entry["action"] = "delogo"
            entry["reason"] = "Remove small burned-in credit by interpolating nearby pixels."
            entries.append(entry)
            continue
        entry["action"] = "blur"
        entry["reason"] = "Burned-in lower third."
        entries.append(entry)
    return entries


def _report_warnings(
    tracklets: list[dict],
    *,
    audio: dict,
    quality: dict,
    text: dict,
    attested: bool,
    sampled_error: str | None,
    truncated: bool,
    lock: bool = True,
) -> list[dict]:
    warnings: list[dict] = []
    watermarks = [item["id"] for item in tracklets if item["kind"] == "watermark"]
    handles = [item["id"] for item in tracklets if item["kind"] == "handle_or_logo"]
    if watermarks:
        warnings.append({
            "code": "watermark_detected",
            "severity": "warning",
            "message": WATERMARK_MESSAGE,
            "tracklet_ids": watermarks,
        })
    if handles and not attested:
        warnings.append({
            "code": "handle_requires_attestation",
            "severity": "warning",
            "message": (
                "A handle or logo was found. Cleaning it needs the own-footage "
                "attestation."
            ),
            "tracklet_ids": handles,
        })
    if not attested and lock:
        warnings.append({
            "code": "rights_not_attested",
            "severity": "warning",
            "message": RIGHTS_MESSAGE,
            "tracklet_ids": [],
        })
    if not text.get("confirmed"):
        warnings.append({
            "code": "text_unconfirmed",
            "severity": "warning",
            "message": UNCONFIRMED_MESSAGE,
            "tracklet_ids": [],
        })
    if sampled_error:
        warnings.append({
            "code": "sampled_pass_failed",
            "severity": "warning",
            "message": f"Text sampling failed: {sampled_error[:200]}",
            "tracklet_ids": [],
        })
    if text.get("present") and any(
        item["kind"] == "subtitle"
        and float(item["box"]["y"]) < 0.62
        and float(item["box"]["y"]) + float(item["box"]["h"]) > 0.45
        for item in tracklets
    ):
        warnings.append({
            "code": "mid_frame_text",
            "severity": "warning",
            "message": (
                "Burned-in text crosses the middle of the frame. Cleanup may leave "
                "a visible patch; check the result at 1×."
            ),
            "tracklet_ids": [
                item["id"] for item in tracklets if item["kind"] == "subtitle"
            ],
        })
    if audio.get("transcript") and audio.get("speech_ratio") is not None:
        if float(audio["speech_ratio"]) <= 0.02:
            warnings.append({
                "code": "no_speech",
                "severity": "info",
                "message": "No speech found. A music bed is recommended.",
                "tracklet_ids": [],
            })
    elif not audio.get("has_audio", True):
        warnings.append({
            "code": "no_audio",
            "severity": "info",
            "message": "This video has no sound track. Add music or a voice-over in Edit.",
            "tracklet_ids": [],
        })
    elif audio.get("no_speech"):
        warnings.append({
            "code": "no_speech",
            "severity": "info",
            "message": "No speech found. A music bed is recommended.",
            "tracklet_ids": [],
        })
    else:
        state = str(audio.get("speech_state") or "unknown")
        if state == "off":
            warnings.append({
                "code": "speech_off",
                "severity": "warning",
                "message": (
                    "Speech was off at import, so captions cannot be built. "
                    "Turn Speech on and import this video again."
                ),
                "tracklet_ids": [],
            })
        elif state == "engine_empty":
            detail = str(audio.get("speech_error") or "").strip()
            language = str(audio.get("speech_language") or "auto")
            suffix = f" Engine: {detail[:180]}" if detail else ""
            warnings.append({
                "code": "speech_engine_empty",
                "severity": "warning",
                "message": (
                    f"Speech was on, but no engine returned a transcript "
                    f"(language: {language}).{suffix} Retry speech on this "
                    "video; re-importing is not needed. If it still fails, "
                    "check Setup → Engines."
                ),
                "tracklet_ids": [],
            })
        else:
            warnings.append({
                "code": "speech_unknown",
                "severity": "warning",
                "message": (
                    "Speech was not read for this video, so captions can't be "
                    "built. Run the read again with Speech on."
                ),
                "tracklet_ids": [],
            })
    for issue in quality.get("issues") or []:
        warnings.append({
            "code": issue["code"],
            "severity": issue.get("severity") or "warning",
            "message": issue["message"],
            "tracklet_ids": [],
        })
    if truncated:
        warnings.append({
            "code": "tracklets_truncated",
            "severity": "warning",
            "message": (
                f"More than {MAX_TRACKLETS} text regions were found. Only the "
                "first ones are listed."
            ),
            "tracklet_ids": [],
        })
    return warnings


def build_report(
    job: dict,
    observations: Iterable[dict],
    *,
    fps: float = DEFAULT_SAMPLE_FPS,
    sampled: dict | None = None,
    music: dict | None = None,
    attestation: Any = None,
    engine: dict | None = None,
    created: float | None = None,
    sampled_error: str | None = None,
    settings: dict | None = None,
    scope: dict | None = None,
) -> dict:
    """Assemble the SourceReport from job evidence and text observations."""
    job = job or {}
    source = job.get("source") or {}
    analysis = job.get("analysis") or {}
    scenes = analysis.get("scenes") or []
    duration = _number(source.get("duration"), 0.0)
    if duration <= 0:
        ends = [
            _number(scene.get("end"), 0.0)
            for scene in scenes if isinstance(scene, dict)
        ]
        duration = max(ends, default=0.0)

    observations = list(observations or [])
    all_tracklets = build_tracklets(
        observations, duration, max_tracklets=MAX_TRACKLETS + 1,
    )
    truncated = len(all_tracklets) > MAX_TRACKLETS
    tracklets = all_tracklets[:MAX_TRACKLETS]
    try:
        import tempfile

        refine_tracklet_edges(
            tracklets,
            str((job.get("source") or {}).get("path") or ""),
            Path(tempfile.gettempdir()),
            fps=float((job.get("source") or {}).get("fps") or 30.0),
            width=int((job.get("source") or {}).get("width") or 0),
            height=int((job.get("source") or {}).get("height") or 0),
        )
    except Exception as exc:  # noqa: BLE001 - a refinement miss never fails a Check
        import sys

        print(f"edge refine skipped: {exc!r}", file=sys.stderr)

    requested = normalize_attestation(attestation)
    existing, source_of_attestation = _job_attestation(job)
    attested = bool(requested or existing)
    attestation_source = "check_request" if requested else source_of_attestation

    sampled = sampled or {}
    frames = int(_number(sampled.get("frames"), 0))
    vision_ok = bool(sampled.get("vision"))
    # A clean result needs the full sampled pass. Scene OCR alone only covers
    # the deep shortlist, so it can find text but cannot confirm its absence.
    confirmed = bool(sampled.get("ran")) and frames > 0 and vision_ok

    text_present = bool(tracklets)
    text_seconds = sum(
        item["end"] - item["start"]
        for tracklet in tracklets for item in tracklet["ranges"]
    )
    text = {
        "present": text_present,
        "confirmed": confirmed,
        "sampled_fps": round(float(fps or DEFAULT_SAMPLE_FPS), 3),
        "frames_read": frames,
        "ocr_available": vision_ok,
        "tracklets": len(tracklets),
        "coverage": round(min(1.0, text_seconds / duration), 4) if duration else 0.0,
        "approximate": any(item.get("approximate") for item in tracklets),
    }

    speech = speech_signal(scenes, duration)
    transcript_available = _speech_available(analysis) or any(
        str(scene.get("speech") or "").strip()
        for scene in scenes if isinstance(scene, dict)
    )
    if not transcript_available:
        speech.update({
            "available": False,
            "speech_seconds": 0.0,
            "speech_ratio": None,
            "ranges": [],
            "transcript": False,
        })
    music = music or music_from_scenes(scenes)
    if not source.get("has_audio"):
        music = {
            "available": False, "present": False, "score": 0.0,
            "method": "none", "speech_aware": False,
        }
    audio_features_data = analysis.get("audio") or {}
    analysis_engine = analysis.get("engine") or {}
    no_speech = bool((analysis.get("transcript") or {}).get("no_speech"))
    options = job.get("options") or {}
    stt_enabled = analysis_engine.get("stt_enabled")
    if stt_enabled is None and "transcribe" in options:
        stt_enabled = bool(options.get("transcribe"))
    if transcript_available:
        speech_state = "read"
    elif not source.get("has_audio"):
        speech_state = "no_audio"
    elif no_speech:
        speech_state = "no_speech"
    elif stt_enabled is False:
        speech_state = "off"
    elif stt_enabled is True:
        speech_state = "engine_empty"
    else:
        speech_state = "unknown"
    speech_error = str(analysis_engine.get("stt_error") or "").strip()
    speech_language = (
        analysis_engine.get("transcript_language")
        or (analysis.get("transcript") or {}).get("language")
        or None
    )
    audio = {
        "available": bool(speech["available"] or audio_features_data.get("available")),
        "has_audio": bool(source.get("has_audio")),
        "speech_seconds": speech["speech_seconds"],
        "speech_ratio": speech["speech_ratio"],
        "speech_ranges": speech["ranges"],
        "transcript": bool(transcript_available),
        # The read ran and its loudness gate found no speech (QA #23).
        "no_speech": no_speech,
        "speech_state": speech_state,
        "language": speech_language,
        "speech_language": analysis_engine.get("stt_language") or "auto",
        "speech_error": speech_error or None,
        "music": music,
    }
    faces = faces_signal(scenes, duration)
    quality = quality_signal(source)

    cleanable = [
        item for item in tracklets
        if item["kind"] in {"subtitle", "title", "lower_third", "credit"}
    ]
    handle_tracklets = [
        item for item in tracklets if item["kind"] == "handle_or_logo"
    ]
    watermark_tracklets = [
        item for item in tracklets if item["kind"] == "watermark"
    ]
    screen_text_tracklets = [
        item for item in tracklets if item["kind"] == "screen_text"
    ]
    recommendation = "compose"
    reasons: list[str] = []
    if cleanable or (handle_tracklets and attested):
        recommendation = "clean_then_compose"
        reasons.append(
            f"{len(cleanable) + (len(handle_tracklets) if attested else 0)} "
            "baked-in text regions need cleaning."
        )
    elif (
        not source.get("has_audio")
        or (
            speech["speech_ratio"] is not None
            and float(speech["speech_ratio"]) <= 0.05
        )
    ):
        recommendation = "music_first"
        reasons.append("The source has little or no speech.")
    else:
        reasons.append("No baked-in text was found on the sampled frames.")
    if screen_text_tracklets:
        reasons.append(
            "Screen-recording UI text was found; it is not a baked-in caption."
        )
    if not text["confirmed"]:
        reasons.append("Text presence is unconfirmed.")
    if watermark_tracklets:
        reasons.append("A platform mark was found.")

    prefill = clean_prefill(
        tracklets, attested=attested, job=job, settings=settings,
    )
    policy = {
        "clean_allowed": bool(attested or not rights.lock_enabled(settings)),
        "rights_attested": bool(attested),
        "attestation_source": attestation_source,
        "handle_or_logo_ids": [item["id"] for item in handle_tracklets],
        "screen_text_ids": [item["id"] for item in screen_text_tracklets],
        "requires_attestation": [
            item["id"] for item in [*handle_tracklets, *watermark_tracklets]
        ] if not attested else [],
    }
    warnings = _report_warnings(
        tracklets,
        audio=audio,
        quality=quality,
        text=text,
        attested=attested,
        sampled_error=sampled_error,
        truncated=truncated,
        lock=rights.lock_enabled(settings),
    )
    created = time.time() if created is None else float(created)
    return {
        "schema": SCHEMA_VERSION,
        "status": "ready",
        "complete": True,
        "job_id": job.get("id"),
        "created": round(created, 3),
        "source": {
            "name": source.get("name"),
            "duration": round(duration, 3),
            "width": int(_number(source.get("width"), 0)),
            "height": int(_number(source.get("height"), 0)),
            "fps": round(_number(source.get("fps"), 0.0), 3),
            "has_audio": bool(source.get("has_audio")),
        },
        "text": text,
        "tracklets": tracklets,
        "audio": audio,
        "faces": faces,
        "quality": quality,
        "recommendation": recommendation,
        "recommendation_reasons": reasons,
        "clean_prefill": prefill,
        **({"scope": dict(scope)} if scope else {}),
        "policy": policy,
        "rights": {
            "attested": bool(attested),
            "source": attestation_source,
        },
        "warnings": warnings,
        "engine": engine or {},
        "error": None,
    }


# ---------------------------------------------------------------- storage


def report_path(job_dir: Path) -> Path:
    return Path(job_dir) / REPORT_DIR / REPORT_FILE


def write_report(job_dir: Path, report: dict) -> Path:
    directory = Path(job_dir) / REPORT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / REPORT_FILE
    temporary = directory / f".{REPORT_FILE}.{os.getpid()}.tmp"
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return path


def load_report(job_dir: Path) -> dict | None:
    path = report_path(job_dir)
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def state_report(job: dict, state: str, *, error: str | None = None) -> dict:
    """Return a small SourceReport-shaped envelope for queued/running work."""
    return {
        "schema": SCHEMA_VERSION,
        "status": state,
        "complete": False,
        "job_id": (job or {}).get("id"),
        "created": round(time.time(), 3),
        "source": {
            key: ((job or {}).get("source") or {}).get(key)
            for key in ("name", "duration", "width", "height", "fps", "has_audio")
        },
        "text": {
            "present": None, "confirmed": False, "sampled_fps": DEFAULT_SAMPLE_FPS,
            "frames_read": 0, "ocr_available": False, "tracklets": 0,
            "coverage": 0.0, "approximate": False,
        },
        "tracklets": [],
        "audio": {"available": False},
        "faces": {
            "present": False, "count": 0, "coverage": 0.0,
            "ranges": [], "boxes": [],
        },
        "quality": {},
        "recommendation": None,
        "recommendation_reasons": [],
        "clean_prefill": [],
        "policy": {
            "clean_allowed": False,
            "rights_attested": False,
            "handle_or_logo_ids": [],
            "screen_text_ids": [],
            "requires_attestation": [],
        },
        "rights": {"attested": False, "source": None},
        "warnings": [],
        "engine": {},
        "error": error,
    }


# ---------------------------------------------------------------- orchestration


def _sampler_payload(value: Any) -> tuple[list[dict], bool, int, float | None]:
    if isinstance(value, dict):
        frames = value.get("frames") or []
        vision = bool(value.get("vision"))
        fps = value.get("fps")
        return (
            [item for item in frames if isinstance(item, dict)],
            vision,
            len(frames),
            _number(fps, 0.0) if fps is not None else None,
        )
    frames = [item for item in (value or []) if isinstance(item, dict)]
    return frames, bool(frames), len(frames), None


def _accepts(function, name: str) -> bool:
    try:
        parameters = inspect.signature(function).parameters
    except (TypeError, ValueError):
        return False
    return name in parameters or any(
        item.kind is inspect.Parameter.VAR_KEYWORD for item in parameters.values()
    )


def _extra_text_times(
    path: str,
    scenes: list[dict],
    duration: float,
    *,
    fps: float,
    window: tuple[float, float],
    cadence: float,
    limit: int = 180,
) -> list[float]:
    """Moments the 4 fps pass can miss: frame 0, after every cut, and onsets.

    A line that appears and disappears inside one 0.25 s window is read only
    if a reading lands on it. These extra stills are cheap next to a render.
    """
    first, last = window
    wanted: list[float] = []
    if first <= 0.001:
        wanted.append(0.0)
    step = 1.0 / max(1.0, float(fps))
    for scene in scenes:
        at = _number(scene.get("start"), 0.0)
        if first <= at + step < last:
            wanted.append(round(at + step, 3))
    if os.environ.get("DUCK_ONSET_SCAN", "1").strip().lower() not in {"0", "off", "false", "no"}:
        try:
            wanted.extend(inkmod.onset_moments(path))
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    grid = max(0.05, 1.0 / max(0.1, float(cadence)))
    out: list[float] = []
    for at in sorted(wanted):
        if at < first or at >= last:
            continue
        # A reading the timed pass already takes needs no second look. It
        # reads the frame at each grid time, not a window, so only a moment
        # on top of one of those frames is covered.
        phase = (at - first) % grid
        if min(phase, grid - phase) < 0.06:
            continue
        if out and at - out[-1] < 0.2:
            continue
        out.append(round(at, 3))
        if len(out) >= limit:
            break
    return out


def _accepts_progress(function) -> bool:
    try:
        parameters = inspect.signature(function).parameters
    except (TypeError, ValueError):
        return False
    return "progress" in parameters or any(
        item.kind is inspect.Parameter.VAR_KEYWORD for item in parameters.values()
    )


def run_check(
    job_id: str,
    job: dict,
    job_dir: Path,
    *,
    sampler: Callable[..., Any] | None = None,
    audio_extractor: Callable[..., Any] | None = None,
    attestation: Any = None,
    sample_text: bool = True,
    fps: float = DEFAULT_SAMPLE_FPS,
    max_frames: int = DEFAULT_MAX_FRAMES,
    progress: Callable[[float, str], None] | None = None,
    start: float = 0.0,
    end: float | None = None,
) -> dict:
    """Run one Check pass and persist its SourceReport.

    ``sampler`` returns ``{"frames": [...], "vision": bool}`` (the pipeline
    0.5 fps pass). ``audio_extractor`` returns a 16 kHz mono wav path for the
    music estimate. Both are optional and may be faked by tests.
    """
    started = time.time()
    job = dict(job or {})
    job.setdefault("id", job_id)
    source = job.get("source") or {}
    analysis = job.get("analysis") or {}
    scenes = analysis.get("scenes") or []
    duration = _number(source.get("duration"), 0.0)
    path = str(source.get("path") or "")

    if progress is not None:
        original_progress = progress
        last_value = [0.0]

        def progress(fraction: float, message: str) -> None:  # noqa: F811
            value = max(last_value[0], min(1.0, float(fraction)))
            last_value[0] = value
            original_progress(value, message)

    window_start = max(0.0, min(duration, float(start or 0.0)))
    window_end = duration if end is None else max(window_start, min(duration, float(end)))
    scoped = window_start > 0.001 or window_end < duration - 0.001
    if scoped:
        scenes = [
            scene for scene in scenes
            if _number(scene.get("end"), 0.0) > window_start
            and _number(scene.get("start"), 0.0) < window_end
        ]
    observations = observations_from_scenes(scenes)
    sampled: dict = {"ran": False, "frames": 0, "vision": False}
    sampled_error: str | None = None
    sample_frames: list[dict] = []
    motion_maps: dict | None = None
    if sample_text and sampler is not None and path:
        if progress:
            progress(0.05, f"Sampling text at {fps:g} frames a second")
        kwargs = {"fps": fps, "max_frames": max_frames}
        if scoped:
            kwargs["start"] = window_start
            kwargs["end"] = window_end
        if _accepts(sampler, "times"):
            extra = _extra_text_times(
                path, scenes, duration,
                fps=_number(source.get("fps"), 30.0),
                window=(window_start, window_end),
                cadence=fps,
            )
            if extra:
                kwargs["times"] = extra
                if progress:
                    progress(0.05, f"Sampling text at {fps:g} frames a second "
                                   f"+ {len(extra)} cut and onset frames")
        if progress and _accepts_progress(sampler):
            # Frame-level progress maps into Check's 5-65% sampling band.
            kwargs["progress"] = lambda fraction, message: progress(
                0.05 + 0.60 * max(0.0, min(1.0, float(fraction))), message,
            )
        try:
            payload = sampler(path, Path(job_dir), duration, **kwargs)
        except Exception as exc:  # noqa: BLE001
            sampled_error = str(exc)[:300]
            payload = None
        frames, vision, count, used_fps = _sampler_payload(payload)
        sample_frames = frames
        motion_maps = payload.get("motion") if isinstance(payload, dict) else None
        # Scene readings are one still with a four-second window. Once the timed
        # pass has read the frames they only stretch the text's time and box.
        if vision and count:
            observations = []
        observations.extend(observations_from_samples(frames))
        sampled = {
            "ran": True,
            "frames": count,
            "vision": vision,
            "fps": used_fps or fps,
            "extra": len(kwargs.get("times") or []),
        }
        if progress:
            progress(0.65, f"Read text on {count} frames")

    music = None
    audio_error: str | None = None
    if audio_extractor is not None and source.get("has_audio") and path:
        if progress:
            progress(0.7, "Listening for music")
        wav = None
        try:
            wav = audio_extractor(path, True, Path(job_dir))
            if wav:
                spans = speech_signal(scenes, duration).get("ranges") or []
                music = music_from_wav(wav, spans)
        except Exception as exc:  # noqa: BLE001
            audio_error = str(exc)[:300]
        finally:
            if wav:
                try:
                    Path(wav).unlink()
                except OSError:
                    pass
    if music is None or not music.get("available"):
        music = music_from_scenes(scenes)

    if progress:
        progress(0.9, "Grouping on-screen text")
    engine = {
        "vision": bool(sampled.get("vision")),
        "sampled_pass": bool(sampled.get("ran")),
        "sample_fps": round(_number(sampled.get("fps"), fps), 3),
        "extra_frames": int(sampled.get("extra") or 0),
        "sampler_error": sampled_error,
        "audio_error": audio_error,
        "music": bool(music.get("available")),
    }
    report = build_report(
        job, observations,
        fps=_number(sampled.get("fps"), fps),
        sampled=sampled,
        music=music,
        attestation=attestation,
        engine=engine,
        sampled_error=sampled_error,
        scope=(
            {"start": round(window_start, 3), "end": round(window_end, 3)}
            if scoped else None
        ),
    )
    report["timings"] = {"total": round(time.time() - started, 3)}
    report["progress"] = 1.0
    plan_fills(report.get("tracklets") or [], sample_frames, motion_maps, report.get("source") or {})
    if scoped:
        _keep_text_outside_scope(report, load_report(job_dir), window_start, window_end)
    write_report(job_dir, report)
    if progress:
        progress(1.0, "Check complete")
    return report
