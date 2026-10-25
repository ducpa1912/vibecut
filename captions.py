"""Canonical speech-timed caption engine shared by every output surface.

The renderer, SRT/VTT export, review links, and artifact identity all describe
the same cue list. The module reads the transcript analysis already wrote,
builds deterministic cues per cut, and stores versioned sidecars under
``data/jobs/<id>/caption_tracks``.

Trust-core callers also use the lightweight compatibility API:
``CUE_WIDTH``, :func:`caption_text`, :func:`chunk_text`, :func:`reel_cues`,
and :func:`cue_tuples`. Those adapters preserve the pre-Caption-Studio contract
without maintaining a second cue engine.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

CUE_WIDTH = 72
MIN_CUE = 0.6
MAX_CUE = 4.0
TIME_EPSILON = 0.002
DATA = Path(
    os.environ.get("VIBECUT_DATA", Path(__file__).resolve().parent / "data"),
).expanduser().resolve()

DEFAULT_STYLE_ID = "clean"
STYLE_DEFAULTS: dict[str, Any] = {
    "font": "Arial Unicode",
    "font_size": 56,
    "color": "#FFFFFF",
    "stroke_color": "#000000",
    "stroke_width": 3,
    "background": "#000000",
    "background_opacity": 0.0,
    "position": "bottom",
    "safe_zone": {"top": 0.08, "right": 0.08, "bottom": 0.16, "left": 0.08},
    "max_chars": 28,
    "max_lines": 2,
    "uppercase": False,
}
STYLE_PRESETS: dict[str, dict[str, Any]] = {
    "clean": {},
    "bold": {
        "font_size": 62,
        "stroke_width": 6,
        "max_chars": 22,
        "max_lines": 2,
        "uppercase": True,
    },
    "boxed": {
        "font_size": 52,
        "stroke_width": 2,
        "background": "#000000",
        "background_opacity": 0.66,
        "max_chars": 26,
        "max_lines": 2,
    },
    "minimal": {
        "font_size": 46,
        "stroke_width": 1,
        "max_chars": 32,
        "max_lines": 2,
        "safe_zone": {"top": 0.07, "right": 0.07, "bottom": 0.12, "left": 0.07},
    },
}
STYLE_KEYS = tuple(STYLE_DEFAULTS)
SENTENCE_RE = re.compile(r"(?<=[.!?…。！？；;])\s*")


class CaptionError(ValueError):
    """Base error for caption construction and validation."""


class CaptionStyleError(CaptionError):
    """A caption style is malformed or unknown."""


class CaptionValidationError(CaptionError):
    """A cue list violates timing or safe-area constraints."""


@dataclass
class CaptionCue:
    """One displayable cue in reel time."""

    id: str
    start: float
    end: float
    text: str
    clip_index: int
    scene: int | None = None
    source_segment: int | None = None
    style_safe: bool = True

    @property
    def duration(self) -> float:
        return max(0.0, float(self.end) - float(self.start))

    def to_dict(self) -> dict:
        return asdict(self)

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)

    @classmethod
    def from_value(cls, value: Any) -> "CaptionCue":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            return cls(
                id=str(value.get("id") or ""),
                start=float(value.get("start") or 0.0),
                end=float(value.get("end") or 0.0),
                text=str(value.get("text") or ""),
                clip_index=int(value.get("clip_index") or 0),
                scene=_optional_int(value.get("scene")),
                source_segment=_optional_int(value.get("source_segment")),
                style_safe=bool(value.get("style_safe", True)),
            )
        raise CaptionError("Caption cue must be a mapping.")


@dataclass
class CaptionTrack:
    """A persisted, versioned cue list plus the style used to render it."""

    id: str
    job_id: str
    version: int
    target: int
    cues: list[CaptionCue] = field(default_factory=list)
    style: dict = field(default_factory=dict)
    style_id: str = DEFAULT_STYLE_ID
    cue_hash: str = ""
    style_hash: str = ""
    clip_hash: str = ""
    hook_scene: int | None = None
    parent_id: str | None = None
    source: str = "none"
    warnings: list[str] = field(default_factory=list)
    clip_windows: list[dict] = field(default_factory=list)
    created: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        value = asdict(self)
        value["cues"] = [cue.to_dict() for cue in self.cues]
        return value

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)

    @classmethod
    def from_dict(cls, value: dict) -> "CaptionTrack":
        return cls(
            id=str(value.get("id") or ""),
            job_id=str(value.get("job_id") or ""),
            version=int(value.get("version") or 1),
            target=int(value.get("target") or 0),
            cues=[CaptionCue.from_value(item) for item in value.get("cues") or []],
            style=normalize_style(value.get("style") or {}),
            style_id=str(value.get("style_id") or DEFAULT_STYLE_ID),
            cue_hash=str(value.get("cue_hash") or ""),
            style_hash=str(value.get("style_hash") or ""),
            clip_hash=str(value.get("clip_hash") or ""),
            hook_scene=_optional_int(value.get("hook_scene")),
            parent_id=str(value["parent_id"]) if value.get("parent_id") else None,
            source=str(value.get("source") or "none"),
            warnings=[str(item) for item in value.get("warnings") or []],
            clip_windows=[
                {
                    "index": int(item.get("index") or 0),
                    "scene": _optional_int(item.get("scene")),
                    "start": float(item.get("start") or 0.0),
                    "end": float(item.get("end") or 0.0),
                    "duration": float(item.get("duration") or 0.0),
                }
                for item in value.get("clip_windows") or []
                if isinstance(item, dict)
            ],
            created=float(value.get("created") or time.time()),
        )


# ---------------------------------------------------------------- styles


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _finite_number(value: Any, default: float, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    if not math.isfinite(number):
        number = default
    return max(low, min(high, number))


def _clean_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if value is None:
        return default
    return bool(value)


def _clean_color(value: Any, default: str) -> str:
    text = str(value or "").strip()
    if text.startswith("#"):
        text = text[1:]
    if len(text) in (3, 4):
        text = "".join(char * 2 for char in text)
    if len(text) in (6, 8) and all(char in "0123456789abcdefABCDEF" for char in text):
        return "#" + text.upper()
    return default


def _clean_safe_zone(value: Any) -> dict:
    source = value if isinstance(value, dict) else {}
    result = {}
    for key, default in STYLE_DEFAULTS["safe_zone"].items():
        result[key] = round(_finite_number(source.get(key, default), default, 0.0, 0.45), 3)
    if result["left"] + result["right"] > 0.9 or result["top"] + result["bottom"] > 0.9:
        raise CaptionStyleError("Caption safe zone leaves no room for text.")
    return result


def normalize_style(style: dict | None = None, *, style_id: str | None = None) -> dict:
    """Return a complete, bounded style dictionary.

    Unknown keys are ignored so old settings and future producer fields do not
    break a render. Invalid values fall back to the preset default rather than
    poisoning an entire track.
    """
    source = dict(STYLE_DEFAULTS)
    if isinstance(style, dict):
        source.update({key: value for key, value in style.items() if key in STYLE_KEYS})
        if "size" in style and "font_size" not in style:
            source["font_size"] = style["size"]
        if "stroke" in style and "stroke_width" not in style:
            if isinstance(style["stroke"], str) and style["stroke"].startswith("#"):
                source["stroke_color"] = style["stroke"]
            else:
                source["stroke_width"] = style["stroke"]
        zone_value = style.get("safe_zone", style.get("safe-zone"))
        if isinstance(zone_value, dict):
            source["safe_zone"] = {**STYLE_DEFAULTS["safe_zone"], **zone_value}
    identifier = str(
        style_id
        or (style.get("id") if isinstance(style, dict) else None)
        or DEFAULT_STYLE_ID
    )
    requested_font = str(source.get("font") or STYLE_DEFAULTS["font"]).strip()
    if Path(requested_font).expanduser().is_file():
        font = requested_font[:200]
    else:
        font = " ".join(requested_font.split())[:200]
    position = str(source.get("position") or "bottom").strip().lower()
    if position not in {"top", "center", "bottom"}:
        position = "bottom"
    return {
        "id": identifier,
        "font": font or STYLE_DEFAULTS["font"],
        "font_size": int(round(_finite_number(
            source.get("font_size"), STYLE_DEFAULTS["font_size"], 12, 200,
        ))),
        "color": _clean_color(source.get("color"), STYLE_DEFAULTS["color"]),
        "stroke_color": _clean_color(
            source.get("stroke_color"), STYLE_DEFAULTS["stroke_color"],
        ),
        "stroke_width": int(round(_finite_number(
            source.get("stroke_width"), STYLE_DEFAULTS["stroke_width"], 0, 20,
        ))),
        "background": _clean_color(
            source.get("background"), STYLE_DEFAULTS["background"],
        ),
        "background_opacity": round(_finite_number(
            source.get("background_opacity"),
            STYLE_DEFAULTS["background_opacity"], 0.0, 1.0,
        ), 3),
        "position": position,
        "safe_zone": _clean_safe_zone(source.get("safe_zone")),
        "max_chars": int(round(_finite_number(
            source.get("max_chars"), STYLE_DEFAULTS["max_chars"], 8, 120,
        ))),
        "max_lines": int(round(_finite_number(
            source.get("max_lines"), STYLE_DEFAULTS["max_lines"], 1, 4,
        ))),
        "uppercase": _clean_bool(source.get("uppercase"), False),
    }


def default_style_settings() -> dict:
    return {
        "default": DEFAULT_STYLE_ID,
        "styles": {
            key: normalize_style({**STYLE_DEFAULTS, **(value or {})}, style_id=key)
            for key, value in STYLE_PRESETS.items()
        },
    }


def normalize_style_settings(raw: dict | None) -> dict:
    """Merge saved styles onto the built-in presets and validate them."""
    if raw is not None and not isinstance(raw, dict):
        raise CaptionStyleError("Caption styles must be an object.")
    raw = raw or {}
    styles_raw = raw.get("styles")
    if styles_raw is not None and not isinstance(styles_raw, dict):
        raise CaptionStyleError("Caption styles.styles must be an object.")
    styles = default_style_settings()["styles"]
    for style_id, value in (styles_raw or {}).items():
        key = _clean_style_id(style_id)
        if not key:
            raise CaptionStyleError("Caption style ids must contain letters, numbers, - or _.")
        if not isinstance(value, dict):
            raise CaptionStyleError(f"Caption style {key} must be an object.")
        styles[key] = normalize_style({**STYLE_DEFAULTS, **value}, style_id=key)
    default = _clean_style_id(raw.get("default") or DEFAULT_STYLE_ID) or DEFAULT_STYLE_ID
    if default not in styles:
        default = DEFAULT_STYLE_ID if DEFAULT_STYLE_ID in styles else next(iter(styles))
    return {"default": default, "styles": styles}


def _clean_style_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 48:
        return ""
    if not all(char.isalnum() or char in "-_" for char in text):
        return ""
    return text


def style_settings(settings: dict | None = None) -> dict:
    section = (settings or {}).get("caption_styles")
    try:
        return normalize_style_settings(section)
    except CaptionStyleError:
        return default_style_settings()


def resolve_style(
    style_id: str | None = None,
    *,
    settings: dict | None = None,
    overrides: dict | None = None,
) -> dict:
    """Resolve the default or a named style, then apply request overrides."""
    section = style_settings(settings)
    requested = _clean_style_id(style_id) if style_id else section["default"]
    if not requested:
        raise CaptionStyleError("Unknown caption style.")
    if requested not in section["styles"]:
        raise CaptionStyleError(f"Unknown caption style: {requested}.")
    merged = {**section["styles"][requested]}
    if overrides:
        if not isinstance(overrides, dict):
            raise CaptionStyleError("Caption style overrides must be an object.")
        merged.update({key: value for key, value in overrides.items() if key in STYLE_KEYS})
    return normalize_style(merged, style_id=requested)


def style_hash(style: dict) -> str:
    normalized = normalize_style(style)
    normalized.pop("id", None)
    return _hash_json(normalized)


# ---------------------------------------------------------------- text helpers


def normalize_text(text: Any) -> str:
    return " ".join(str(text or "").replace("\r", "\n").split())


def split_sentences(text: str) -> list[str]:
    """Split on sentence punctuation without requiring spaces (CJK safe)."""
    value = normalize_text(text)
    if not value:
        return []
    parts = [part.strip() for part in SENTENCE_RE.split(value) if part.strip()]
    return parts or [value]


def _hard_split(word: str, width: int) -> list[str]:
    if width <= 0:
        return [word]
    return [word[index:index + width] for index in range(0, len(word), width)] or [word]


def wrap_lines(text: str, max_chars: int) -> list[str]:
    """Word-boundary wrapping with character fallback for CJK and long tokens."""
    value = normalize_text(text)
    if not value:
        return []
    width = max(8, int(max_chars))
    if len(value) <= width:
        return [value]
    words = value.split()
    if len(words) <= 1:
        return _hard_split(value, width)
    lines: list[str] = []
    current = ""
    for word in words:
        pieces = _hard_split(word, width) if len(word) > width else [word]
        for piece in pieces:
            candidate = f"{current} {piece}".strip()
            if len(candidate) <= width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = piece
    if current:
        lines.append(current)
    return lines or [value]


# ---------------------------------------------------------- trust-core adapter


def caption_text(scene: dict | None) -> str:
    """Scene speech/OCR text, matching the trust-core caption contract."""
    return normalize_text(
        (scene or {}).get("speech") or (scene or {}).get("ocr") or "",
    )


def chunk_text(text: str, width: int = CUE_WIDTH) -> list[str]:
    """Trust-core chunk adapter on top of the full word wrapper."""
    value = normalize_text(text)
    if not value:
        return [""] if str(text or "") == "" else []
    return wrap_lines(value, width)


def _compat_duration(clip: dict) -> float:
    value = clip.get("duration")
    if value is None:
        value = clip.get("dur")
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


def reel_cues(
    plan: dict,
    clips: Iterable[dict] | None,
    scenes: Iterable[dict] | None,
) -> list[dict]:
    """Trust-core scene-level cue contract used by artifact fallbacks.

    Full Caption Studio tracks use :func:`cues_for_plan`; this adapter keeps
    older artifact and render callers on the same module with the original
    ``CUE_WIDTH`` chunk semantics.
    """
    by_id = {
        scene.get("id"): scene
        for scene in scenes or []
        if isinstance(scene, dict)
    }
    cues: list[dict] = []
    offset = 0.0
    for clip in clips or []:
        if not isinstance(clip, dict):
            continue
        scene = by_id.get(clip.get("scene")) or {}
        text = caption_text(scene)
        duration = _compat_duration(clip)
        if text and duration > 0:
            chunks = chunk_text(text)
            share = duration / max(1, len(chunks))
            for index, chunk in enumerate(chunks):
                start = round(offset + index * share, 3)
                end = round(min(offset + duration, offset + (index + 1) * share), 3)
                if end <= start:
                    continue
                cues.append({
                    "start": start,
                    "end": end,
                    "text": chunk,
                    "scene": clip.get("scene"),
                })
        offset += duration
    return cues


def cue_tuples(cues: Iterable[dict]) -> list[tuple[float, float, str]]:
    """Tuple form used by the ffmpeg caption burner."""
    return [
        (float(cue.get("start") or 0.0), float(cue.get("end") or 0.0),
         str(cue.get("text") or ""))
        for cue in cues
        if isinstance(cue, dict)
    ]


def parse_srt(text: str) -> list[dict]:
    """Parse a saved SRT back into the canonical cue shape for preview."""
    cues: list[dict] = []
    for block in str(text or "").strip().split("\n\n"):
        lines = block.splitlines()
        if len(lines) < 3:
            continue
        match = re.match(
            r"(\d\d):(\d\d):(\d\d),(\d{3}) --> (\d\d):(\d\d):(\d\d),(\d{3})",
            lines[1],
        )
        if not match:
            continue
        values = [int(value) for value in match.groups()]
        start = values[0] * 3600 + values[1] * 60 + values[2] + values[3] / 1000
        end = values[4] * 3600 + values[5] * 60 + values[6] + values[7] / 1000
        cues.append({
            "start": round(start, 3),
            "end": round(end, 3),
            "text": "\n".join(lines[2:]),
        })
    return cues


def _text_chunks(text: str, style: dict) -> list[str]:
    """Sentence-aware chunks, each within max_chars * max_lines."""
    chunks: list[str] = []
    for sentence in split_sentences(text):
        if style.get("uppercase"):
            sentence = sentence.upper()
        lines = wrap_lines(sentence, int(style["max_chars"]))
        max_lines = max(1, int(style["max_lines"]))
        for index in range(0, len(lines), max_lines):
            chunk = "\n".join(lines[index:index + max_lines]).strip()
            if chunk:
                chunks.append(chunk)
    return chunks


def _visible_weight(text: str) -> int:
    return max(1, len(normalize_text(text)))


def _split_words_evenly(text: str, count: int, style: dict) -> list[str]:
    value = normalize_text(text)
    words = value.split()
    if count <= 1:
        return [text]
    if len(words) <= 1:
        if not value:
            return [text]
        size = max(1, math.ceil(len(value) / count))
        return _hard_split(value, size)
    total = sum(len(word) + 1 for word in words)
    target = max(1, math.ceil(total / count))
    groups: list[str] = []
    current: list[str] = []
    size = 0
    for word in words:
        current.append(word)
        size += len(word) + 1
        if size >= target and len(groups) < count - 1:
            groups.append(" ".join(current))
            current = []
            size = 0
    if current:
        groups.append(" ".join(current))
    return groups or [text]


def _line_count(text: str) -> int:
    return len([line for line in str(text).splitlines() if line.strip()])


def _style_safe(text: str, style: dict) -> bool:
    lines = [line for line in str(text).splitlines() if line.strip()]
    if not lines or len(lines) > int(style["max_lines"]):
        return False
    return all(len(line) <= int(style["max_chars"]) for line in lines)


# ---------------------------------------------------------------- transcript


def read_transcript_segments(job_dir: Path | None) -> list[dict]:
    """Read the same transcript analysis used for speech, with Apple fallback."""
    if job_dir is None:
        return []
    directory = Path(job_dir) / "transcript"
    for name in ("transcript.json", "transcript_apple.json"):
        path = directory / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        segments: list[dict] = []
        raw_segments = data.get("segments") if isinstance(data, dict) else None
        for item in raw_segments if isinstance(raw_segments, list) else []:
            if not isinstance(item, dict):
                continue
            text = normalize_text(item.get("text"))
            if not text:
                continue
            try:
                start = float(item.get("start", 0.0))
                end = float(item.get("end", start))
            except (TypeError, ValueError):
                continue
            if not math.isfinite(start) or not math.isfinite(end) or end <= start:
                continue
            segments.append({
                "index": len(segments),
                "start": start,
                "end": end,
                "text": text,
            })
        if segments:
            return segments
    return []


def _clip_windows(plan: dict) -> list[dict]:
    windows: list[dict] = []
    offset = 0.0
    for index, clip in enumerate(plan.get("clips") or []):
        if not isinstance(clip, dict):
            continue
        try:
            start = float(clip.get("start") or 0.0)
            end = float(
                clip.get("end")
                if clip.get("end") is not None
                else start + float(clip.get("dur") or clip.get("duration") or 0.0)
            )
        except (TypeError, ValueError):
            continue
        if not math.isfinite(start) or not math.isfinite(end) or end <= start:
            continue
        duration = end - start
        windows.append({
            "index": len(windows),
            "scene": clip.get("scene"),
            "start": start,
            "end": end,
            "duration": duration,
            "offset": offset,
        })
        offset += duration
    return windows


def clip_hash(clips: Iterable[dict] | None) -> str:
    rows = []
    for clip in clips or []:
        if not isinstance(clip, dict):
            continue
        rows.append({
            "scene": clip.get("scene"),
            "start": round(float(clip.get("start") or 0.0), 3),
            "end": round(float(
                clip.get("end")
                if clip.get("end") is not None
                else float(clip.get("start") or 0.0)
                + float(clip.get("dur") or clip.get("duration") or 0.0)
            ), 3),
            "role": str(clip.get("role") or "beat"),
        })
    return _hash_json(rows)


def _slice_segment_text(segment: dict, start: float, end: float) -> str:
    """Approximate the words spoken inside a partially used segment."""
    seg_start = float(segment["start"])
    seg_end = float(segment["end"])
    seg_duration = max(0.001, seg_end - seg_start)
    overlap_start = max(start, seg_start)
    overlap_end = min(end, seg_end)
    if overlap_end <= overlap_start:
        return ""
    if overlap_start <= seg_start + TIME_EPSILON and overlap_end >= seg_end - TIME_EPSILON:
        return str(segment.get("text") or "")
    words = str(segment.get("text") or "").split()
    if len(words) <= 1:
        return " ".join(words)
    first = int(math.floor((overlap_start - seg_start) / seg_duration * len(words)))
    last = int(math.ceil((overlap_end - seg_start) / seg_duration * len(words)))
    first = max(0, min(len(words) - 1, first))
    last = max(first + 1, min(len(words), last))
    return " ".join(words[first:last])


def _scene_for(plan: dict, clip_index: int, scene_id: Any) -> dict:
    scenes = plan.get("_scenes") or plan.get("scenes") or []
    for scene in scenes:
        if isinstance(scene, dict) and scene.get("id") == scene_id:
            return scene
    clips = plan.get("clips") or []
    if 0 <= clip_index < len(clips) and isinstance(clips[clip_index], dict):
        return clips[clip_index]
    return {}


def _raw_pieces(
    plan: dict,
    windows: list[dict],
    segments: list[dict],
    style: dict,
    warnings: list[str],
) -> tuple[list[dict], list[str]]:
    """Build timed text pieces before duration fitting."""
    pieces: list[dict] = []
    used: list[str] = []
    for window in windows:
        clip_start = window["start"]
        clip_end = window["end"]
        local_pieces: list[dict] = []
        for position, segment in enumerate(segments):
            if not isinstance(segment, dict):
                continue
            try:
                segment_index = int(segment.get("index", position))
                segment_start = float(segment["start"])
                segment_end = float(segment["end"])
            except (KeyError, TypeError, ValueError):
                continue
            if not math.isfinite(segment_start) or not math.isfinite(segment_end):
                continue
            if segment_end <= segment_start:
                continue
            overlap_start = max(clip_start, segment_start)
            overlap_end = min(clip_end, segment_end)
            if overlap_end - overlap_start <= 0.04:
                continue
            text = _slice_segment_text(segment, overlap_start, overlap_end)
            if not normalize_text(text):
                continue
            local_pieces.append({
                "start": overlap_start,
                "end": overlap_end,
                "text": text,
                "source_segment": segment_index,
            })
        if local_pieces:
            used.append("transcript")
        else:
            scene = _scene_for(plan, window["index"], window["scene"])
            speech = normalize_text(scene.get("speech"))
            ocr = normalize_text(scene.get("ocr"))
            text = speech or ocr
            if text:
                used.append("speech" if speech else "ocr")
                warnings.append(
                    f"Clip {window['index'] + 1}: no transcript coverage; "
                    f"fallback to {'scene speech' if speech else 'OCR text'}."
                )
                local_pieces.append({
                    "start": clip_start,
                    "end": clip_end,
                    "text": text,
                    "source_segment": None,
                })
            else:
                used.append("none")
                warnings.append(
                    f"Clip {window['index'] + 1}: no transcript, speech or OCR text."
                )
        for piece in local_pieces:
            chunks = _text_chunks(piece["text"], style)
            if not chunks:
                continue
            weights = [_visible_weight(chunk) for chunk in chunks]
            total = max(1, sum(weights))
            duration = max(0.0, float(piece["end"]) - float(piece["start"]))
            cursor = float(piece["start"])
            for index, chunk in enumerate(chunks):
                share = duration * weights[index] / total
                end = float(piece["end"]) if index == len(chunks) - 1 else cursor + share
                pieces.append({
                    "start": cursor,
                    "end": max(cursor, end),
                    "text": chunk,
                    "source_segment": piece["source_segment"],
                    "clip_index": window["index"],
                    "scene": window["scene"],
                })
                cursor = end
    return pieces, used


def _source_label(used: list[str]) -> str:
    values = {value for value in used if value != "none"}
    if not values:
        return "none"
    if values == {"transcript"}:
        return "transcript"
    if len(values) == 1:
        return next(iter(values))
    return "mixed"


def _piece_times(piece: dict, style: dict) -> list[dict]:
    text = str(piece.get("text") or "").strip()
    if not text:
        return []
    return [{
        "start": float(piece["start"]),
        "end": float(piece["end"]),
        "text": text,
        "source_segment": piece.get("source_segment"),
        "clip_index": piece["clip_index"],
        "scene": piece.get("scene"),
    }]


def _fit_cue_text_and_timing(cue: dict, style: dict) -> list[dict]:
    """Split a long cue at word boundaries so no cue exceeds MAX_CUE."""
    duration = max(0.0, float(cue["end"]) - float(cue["start"]))
    if duration <= MAX_CUE + TIME_EPSILON:
        return [cue]
    count = max(2, int(math.ceil(duration / MAX_CUE)))
    chunks: list[str] = []
    for _ in range(10):
        parts = _split_words_evenly(cue["text"], count, style)
        chunks = []
        for part in parts:
            chunks.extend(_text_chunks(part, style))
        if len(chunks) >= count:
            break
        count += 1
    if len(chunks) <= 1:
        return [cue]
    weights = [_visible_weight(chunk) for chunk in chunks]
    total = max(1, sum(weights))
    result = []
    cursor = float(cue["start"])
    for index, chunk in enumerate(chunks):
        end = float(cue["end"]) if index == len(chunks) - 1 else cursor + duration * weights[index] / total
        result.append({
            **cue,
            "start": cursor,
            "end": max(cursor, end),
            "text": chunk,
        })
        cursor = end
    return result


def _merge_text(left: str, right: str, style: dict) -> str | None:
    lines = wrap_lines(f"{normalize_text(left)} {normalize_text(right)}", int(style["max_chars"]))
    if len(lines) > int(style["max_lines"]):
        return None
    return "\n".join(lines)


def _fit_clip_cues(cues: list[dict], window: dict, style: dict, warnings: list[str]) -> list[dict]:
    """Enforce order, overlap, clip bounds, 0.6s minimum and 4.0s maximum."""
    clip_start = window["start"]
    clip_end = window["end"]
    clip_duration = window["duration"]
    items = []
    for cue in cues:
        start = max(clip_start, min(clip_end, float(cue["start"])))
        end = max(start, min(clip_end, float(cue["end"])))
        if end - start < 0.01:
            continue
        items.append({**cue, "start": start, "end": end})
    items.sort(key=lambda item: (float(item["start"]), float(item["end"])))

    # Never overlap and never start before the clip.
    previous_end = clip_start
    ordered: list[dict] = []
    for cue in items:
        start = max(previous_end, float(cue["start"]))
        end = min(clip_end, max(start, float(cue["end"])))
        if end - start < 0.02:
            if ordered:
                merged = _merge_text(ordered[-1]["text"], cue["text"], style)
                if merged:
                    ordered[-1]["text"] = merged
                    ordered[-1]["end"] = max(ordered[-1]["end"], end)
            continue
        ordered.append({**cue, "start": start, "end": end})
        previous_end = end

    # Split anything longer than the maximum.
    split: list[dict] = []
    for cue in ordered:
        split.extend(_fit_cue_text_and_timing(cue, style))

    # Enforce the minimum by merging neighbours or borrowing silence.
    index = 0
    while index < len(split):
        cue = split[index]
        duration = float(cue["end"]) - float(cue["start"])
        if duration >= MIN_CUE - TIME_EPSILON:
            index += 1
            continue
        next_cue = split[index + 1] if index + 1 < len(split) else None
        merged = None
        if next_cue is not None:
            gap = float(next_cue["start"]) - float(cue["end"])
            combined = float(next_cue["end"]) - float(cue["start"])
            if gap <= 0.6 and combined <= MAX_CUE + TIME_EPSILON:
                merged = _merge_text(cue["text"], next_cue["text"], style)
                if merged:
                    split[index] = {
                        **cue,
                        "end": next_cue["end"],
                        "text": merged,
                    }
                    split.pop(index + 1)
                    continue
        target_end = min(clip_end, float(cue["start"]) + MIN_CUE)
        if next_cue is not None:
            target_end = min(target_end, float(next_cue["start"]))
        if target_end > float(cue["end"]):
            cue = {**cue, "end": target_end}
            split[index] = cue
            duration = target_end - float(cue["start"])
        if duration < MIN_CUE - TIME_EPSILON:
            previous = split[index - 1] if index > 0 else None
            earliest = float(previous["end"]) if previous else clip_start
            target_start = max(earliest, float(cue["end"]) - MIN_CUE)
            if target_start < float(cue["start"]):
                cue = {**cue, "start": target_start}
                split[index] = cue
                duration = float(cue["end"]) - target_start
        if duration < MIN_CUE - TIME_EPSILON and clip_duration >= MIN_CUE:
            warnings.append(
                f"Clip {window['index'] + 1}: cue at {cue['start']:.2f}s is "
                f"{duration:.2f}s; speech density cannot meet the 0.6s minimum."
            )
        index += 1

    # Rounding must not reintroduce overlap.
    result: list[dict] = []
    last_end = clip_start
    for cue in split:
        start = round(max(last_end, float(cue["start"])), 3)
        end = round(min(clip_end, float(cue["end"])), 3)
        if end <= start:
            continue
        text = str(cue["text"]).strip()
        if not text:
            continue
        result.append({
            **cue,
            "start": start,
            "end": end,
            "text": text,
            "style_safe": _style_safe(text, style),
        })
        last_end = end
    return result


def _cues_from_pieces(
    pieces: list[dict],
    windows: list[dict],
    style: dict,
    warnings: list[str],
) -> list[dict]:
    cue_rows: list[dict] = []
    timed = []
    for piece in pieces:
        timed.extend(_piece_times(piece, style))
    by_clip: dict[int, list[dict]] = {}
    for cue in timed:
        by_clip.setdefault(int(cue["clip_index"]), []).append(cue)
    for window in windows:
        local = by_clip.get(window["index"]) or []
        fitted = _fit_clip_cues(local, window, style, warnings)
        for cue in fitted:
            cue_rows.append({
                **cue,
                "start": round(
                    float(cue["start"]) - window["start"] + window["offset"], 3,
                ),
                "end": round(
                    float(cue["end"]) - window["start"] + window["offset"], 3,
                ),
            })
    for index, cue in enumerate(cue_rows, 1):
        cue["id"] = f"c{index:03d}"
    return cue_rows


def build_cues(
    plan: dict,
    *,
    style: dict | None = None,
    segments: list[dict] | None = None,
) -> tuple[list[dict], str, list[str]]:
    """Build cue dictionaries from a plan. Pure and deterministic."""
    normalized_style = normalize_style(style)
    windows = _clip_windows(plan)
    warnings: list[str] = []
    pieces, used = _raw_pieces(plan, windows, segments or [], normalized_style, warnings)
    cues = _cues_from_pieces(pieces, windows, normalized_style, warnings)
    return cues, _source_label(used), warnings


def cues_for_plan(
    plan: dict,
    clips: list[dict] | None = None,
    scenes: list[dict] | None = None,
    *,
    style: dict | None = None,
    segments: list[dict] | None = None,
) -> list[dict]:
    """The single cue path used by burn-in, generic exports and previews."""
    supplied = plan.get("_caption_cues")
    if supplied:
        return [_cue_payload(item) for item in supplied]
    working = dict(plan)
    if clips is not None:
        working["clips"] = clips
    if scenes is not None:
        working["_scenes"] = scenes
    chosen_style = normalize_style(style or plan.get("_caption_style") or {})
    chosen_segments = (
        segments
        if segments is not None
        else plan.get("_transcript_segments") or []
    )
    cues, _source, _warnings = build_cues(
        working, style=chosen_style, segments=chosen_segments,
    )
    return cues


def _cue_payload(value: Any) -> dict:
    if isinstance(value, CaptionCue):
        return value.to_dict()
    if isinstance(value, dict):
        return {
            "id": str(value.get("id") or ""),
            "start": round(float(value.get("start") or 0.0), 3),
            "end": round(float(value.get("end") or 0.0), 3),
            "text": str(value.get("text") or ""),
            "clip_index": int(value.get("clip_index") or 0),
            "scene": _optional_int(value.get("scene")),
            "source_segment": _optional_int(value.get("source_segment")),
            "style_safe": bool(value.get("style_safe", True)),
        }
    if isinstance(value, (tuple, list)) and len(value) >= 3:
        return {
            "id": "",
            "start": round(float(value[0] or 0.0), 3),
            "end": round(float(value[1] or 0.0), 3),
            "text": str(value[2] or ""),
            "clip_index": int(value[3]) if len(value) > 3 else 0,
            "scene": None,
            "source_segment": None,
            "style_safe": True,
        }
    raise CaptionError("Caption cue must be a mapping.")


def cue_hash(cues: Iterable[dict | CaptionCue] | None) -> str:
    rows = []
    for cue in cues or []:
        value = _cue_payload(cue)
        rows.append({
            "start": round(float(value["start"]), 3),
            "end": round(float(value["end"]), 3),
            "text": str(value["text"]),
            "clip_index": int(value["clip_index"]),
            "scene": _optional_int(value["scene"]),
            "source_segment": _optional_int(value["source_segment"]),
        })
    return _hash_json(rows)


def total_duration(plan: dict) -> float:
    return round(sum(window["duration"] for window in _clip_windows(plan)), 3)


# ---------------------------------------------------------------- track storage


def _hash_json(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:16]


def track_id(
    *,
    job_id: str,
    target: int,
    clip_key: str,
    cue_key: str,
    style_key: str,
    version: int = 1,
) -> str:
    digest = _hash_json({
        "job": job_id,
        "target": int(target),
        "clips": clip_key,
        "cues": cue_key,
        "style": style_key,
        "version": int(version),
    })
    return f"cap_{digest}"


def tracks_dir(job_dir: Path) -> Path:
    return Path(job_dir) / "caption_tracks"


def track_path(job_dir: Path, track_id_value: str) -> Path:
    clean = str(track_id_value or "").strip()
    if not clean or not all(char.isalnum() or char in "-_" for char in clean):
        raise CaptionError("Invalid caption track id.")
    return tracks_dir(job_dir) / f"{clean}.json"


def save_track(job_dir: Path, track: CaptionTrack) -> Path:
    path = track_path(job_dir, track.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    temporary.write_text(
        json.dumps(track.to_dict(), ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return path


def load_track(job_dir: Path, track_id_value: str) -> CaptionTrack | None:
    try:
        path = track_path(job_dir, track_id_value)
    except CaptionError:
        return None
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        return CaptionTrack.from_dict(data)
    except (TypeError, ValueError):
        return None


def list_tracks(job_dir: Path) -> list[dict]:
    directory = tracks_dir(job_dir)
    if not directory.is_dir():
        return []
    rows = []
    for path in sorted(directory.glob("cap_*.json")):
        track = load_track(job_dir, path.stem)
        if track is None:
            continue
        rows.append({
            "id": track.id,
            "version": track.version,
            "target": track.target,
            "cue_count": len(track.cues),
            "style_id": track.style_id,
            "created": track.created,
        })
    rows.sort(key=lambda row: float(row.get("created") or 0), reverse=True)
    return rows


def build_track(
    job: dict,
    plan: dict,
    style: dict | str | None = None,
    *,
    settings: dict | None = None,
    overrides: dict | None = None,
    segments: list[dict] | None = None,
    job_dir: Path | None = None,
    version: int = 1,
    parent_id: str | None = None,
) -> CaptionTrack:
    """Build and persist a deterministic caption track for a cut."""
    if isinstance(style, str):
        chosen_style = resolve_style(style, settings=settings, overrides=overrides)
    elif style is None:
        chosen_style = resolve_style(None, settings=settings, overrides=overrides)
    elif isinstance(style, dict):
        merged_style = dict(style)
        if overrides:
            merged_style.update({
                key: value for key, value in overrides.items() if key in STYLE_KEYS
            })
        chosen_style = normalize_style(merged_style)
    else:
        raise CaptionStyleError("Caption style must be a name or an object.")
    job_id = str(job.get("id") or "")
    if job_dir is None and job_id and "/" not in job_id and ".." not in job_id:
        job_dir = DATA / "jobs" / job_id
    working = dict(plan)
    scenes = (job.get("analysis") or {}).get("scenes")
    if scenes:
        working["_scenes"] = scenes
    if segments is None and job_dir is not None:
        segments = read_transcript_segments(job_dir)
    cues, source, warnings = build_cues(
        working, style=chosen_style, segments=segments or [],
    )
    target = int(plan.get("target") or 0)
    cue_key = cue_hash(cues)
    style_key = style_hash(chosen_style)
    clip_key = clip_hash(plan.get("clips"))
    identifier = track_id(
        job_id=job_id,
        target=target,
        clip_key=clip_key,
        cue_key=cue_key,
        style_key=f"{style_key}:{chosen_style['id']}",
        version=version,
    )
    track = CaptionTrack(
        id=identifier,
        job_id=job_id,
        version=int(version),
        target=target,
        cues=[CaptionCue.from_value(cue) for cue in cues],
        style=chosen_style,
        style_id=str(chosen_style.get("id") or DEFAULT_STYLE_ID),
        cue_hash=cue_key,
        style_hash=style_key,
        clip_hash=clip_key,
        hook_scene=_optional_int(plan.get("hook_scene")),
        parent_id=parent_id,
        source=source,
        warnings=list(dict.fromkeys(warnings)),
        clip_windows=[
            {
                "index": window["index"],
                "scene": _optional_int(window.get("scene")),
                "start": round(window["start"], 3),
                "end": round(window["end"], 3),
                "duration": round(window["duration"], 3),
            }
            for window in _clip_windows(working)
        ],
        created=round(time.time(), 3),
    )
    if job_dir is not None:
        existing = load_track(job_dir, identifier)
        if existing is not None:
            return existing
        save_track(job_dir, track)
    return track


# ---------------------------------------------------------------- editing


def _normalize_edited_cue(
    raw: dict | CaptionCue,
    index: int,
    style: dict,
    fallback: CaptionCue | None,
) -> CaptionCue:
    if isinstance(raw, CaptionCue):
        raw = raw.to_dict()
    if not isinstance(raw, dict):
        raise CaptionValidationError("Every cue must be an object.")
    cue_id = str(raw.get("id") or (fallback.id if fallback else f"c{index + 1:03d}"))
    text = str(raw.get("text") if raw.get("text") is not None else (fallback.text if fallback else ""))
    if style.get("uppercase"):
        text = text.upper()
    text = "\n".join(
        line.strip() for line in str(text).replace("\r", "\n").splitlines() if line.strip()
    )
    clip_index = raw.get("clip_index", fallback.clip_index if fallback else None)
    scene = raw.get("scene", fallback.scene if fallback else None)
    source_segment = raw.get(
        "source_segment", fallback.source_segment if fallback else None,
    )
    start_value = raw.get("start")
    end_value = raw.get("end")
    if start_value is None:
        start_value = fallback.start if fallback else 0.0
    if end_value is None:
        end_value = fallback.end if fallback else start_value
    try:
        start = float(start_value)
        end = float(end_value)
    except (TypeError, ValueError):
        raise CaptionValidationError("Cue times must be numbers.") from None
    try:
        clip_index = int(clip_index if clip_index is not None else 0)
    except (TypeError, ValueError):
        raise CaptionValidationError("Cue clip_index must be an integer.") from None
    return CaptionCue(
        id=cue_id,
        start=round(start, 3),
        end=round(end, 3),
        text=text,
        clip_index=clip_index,
        scene=_optional_int(scene),
        source_segment=_optional_int(source_segment),
        style_safe=_style_safe(text, style),
    )


def _reflow_style(cues: list[CaptionCue], style: dict) -> list[CaptionCue]:
    """Re-wrap explicit cue text so text-affecting style edits stay safe."""
    result: list[CaptionCue] = []
    for cue in cues:
        text = cue.text.upper() if style.get("uppercase") else cue.text
        lines = wrap_lines(text, int(style["max_chars"]))
        max_lines = max(1, int(style["max_lines"]))
        chunks = [
            "\n".join(lines[index:index + max_lines])
            for index in range(0, len(lines), max_lines)
        ] or [text]
        if len(chunks) == 1:
            result.append(CaptionCue(
                id=cue.id,
                start=cue.start,
                end=cue.end,
                text=chunks[0],
                clip_index=cue.clip_index,
                scene=cue.scene,
                source_segment=cue.source_segment,
                style_safe=_style_safe(chunks[0], style),
            ))
            continue
        weights = [_visible_weight(chunk) for chunk in chunks]
        total = max(1, sum(weights))
        duration = max(0.0, cue.end - cue.start)
        cursor = cue.start
        for index, chunk in enumerate(chunks):
            end = cue.end if index == len(chunks) - 1 else cursor + duration * weights[index] / total
            result.append(CaptionCue(
                id=cue.id if index == 0 else f"{cue.id}-{index + 1}",
                start=round(cursor, 3),
                end=round(end, 3),
                text=chunk,
                clip_index=cue.clip_index,
                scene=cue.scene,
                source_segment=cue.source_segment,
                style_safe=_style_safe(chunk, style),
            ))
            cursor = end
    return result


def edit_track(
    track: CaptionTrack,
    *,
    cues: list[dict | CaptionCue] | None = None,
    style: dict | None = None,
    style_id: str | None = None,
    overrides: dict | None = None,
    settings: dict | None = None,
    clips: list[dict] | None = None,
    total: float | None = None,
    job_dir: Path | None = None,
) -> tuple[CaptionTrack, bool]:
    """Apply cue or style edits. Returns ``(track, changed)``.

    An unchanged edit returns the original track. A changed edit gets a new
    deterministic id, ``version + 1`` and ``parent_id`` pointing at the source
    version; the old sidecar is left intact.
    """
    if style is None and style_id is not None:
        new_style = resolve_style(style_id, settings=settings, overrides=overrides)
    elif style is not None:
        base = (
            resolve_style(style_id, settings=settings, overrides=overrides)
            if style_id
            else dict(track.style)
        )
        if overrides and not style_id:
            base.update(overrides)
        new_style = normalize_style(
            {**base, **style},
            style_id=style.get("id") or base.get("id") or track.style_id,
        )
    elif overrides:
        new_style = normalize_style({**track.style, **overrides}, style_id=track.style_id)
    else:
        new_style = normalize_style(track.style, style_id=track.style_id)

    fallback_by_id = {cue.id: cue for cue in track.cues}
    if cues is not None:
        def fallback_for(index: int, raw: dict) -> CaptionCue | None:
            matched = fallback_by_id.get(str(raw.get("id") or ""))
            if matched is not None:
                return matched
            if 0 <= index < len(track.cues):
                return track.cues[index]
            return None

        new_cues = [
            _normalize_edited_cue(raw, index, new_style, fallback_for(index, raw))
            for index, raw in enumerate(cues)
        ]
    elif any(
        new_style[key] != track.style.get(key)
        for key in ("max_chars", "max_lines", "uppercase")
    ):
        new_cues = _reflow_style(track.cues, new_style)
    else:
        new_cues = [
            CaptionCue(
                id=cue.id,
                start=cue.start,
                end=cue.end,
                text=cue.text,
                clip_index=cue.clip_index,
                scene=cue.scene,
                source_segment=cue.source_segment,
                style_safe=_style_safe(cue.text, new_style),
            )
            for cue in track.cues
        ]

    validate_track(new_cues, style=new_style, clips=clips, total=total)
    new_cue_hash = cue_hash(new_cues)
    new_style_hash = style_hash(new_style)
    if (
        new_cue_hash == track.cue_hash
        and new_style_hash == track.style_hash
        and str(new_style.get("id") or "") == track.style_id
    ):
        return track, False

    new_version = track.version + 1
    identifier = track_id(
        job_id=track.job_id,
        target=track.target,
        clip_key=track.clip_hash,
        cue_key=new_cue_hash,
        style_key=f"{new_style_hash}:{new_style['id']}",
        version=new_version,
    )
    edited = CaptionTrack(
        id=identifier,
        job_id=track.job_id,
        version=new_version,
        target=track.target,
        cues=new_cues,
        style=new_style,
        style_id=str(new_style.get("id") or track.style_id),
        cue_hash=new_cue_hash,
        style_hash=new_style_hash,
        clip_hash=track.clip_hash,
        hook_scene=track.hook_scene,
        parent_id=track.id,
        source=track.source,
        warnings=list(track.warnings),
        clip_windows=[dict(item) for item in track.clip_windows],
        created=round(time.time(), 3),
    )
    if job_dir is not None:
        save_track(job_dir, edited)
    return edited, True


# ---------------------------------------------------------------- validation


def _clip_windows_for_validation(clips: Iterable[dict] | None) -> dict[int, tuple[float, float]]:
    windows: dict[int, tuple[float, float]] = {}
    offset = 0.0
    for index, clip in enumerate(clips or []):
        if not isinstance(clip, dict):
            continue
        try:
            start = float(clip.get("start") or 0.0)
            end = float(
                clip.get("end")
                if clip.get("end") is not None
                else start + float(clip.get("dur") or clip.get("duration") or 0.0)
            )
        except (TypeError, ValueError):
            continue
        windows[index] = (offset, offset + max(0.0, end - start))
        offset += max(0.0, end - start)
    return windows


def validate_track(
    value: CaptionTrack | Iterable[dict | CaptionCue] | dict,
    *,
    style: dict | None = None,
    clips: list[dict] | None = None,
    total: float | None = None,
    require_limits: bool = False,
) -> None:
    """Reject malformed tracks before they reach a render or export."""
    saved_windows: list[dict] = []
    if isinstance(value, CaptionTrack):
        cues = [cue.to_dict() for cue in value.cues]
        chosen_style = normalize_style(style or value.style)
        saved_windows = value.clip_windows
    elif isinstance(value, dict) and "cues" in value:
        cues = [_cue_payload(cue) for cue in value.get("cues") or []]
        chosen_style = normalize_style(style or value.get("style") or {})
        saved_windows = [
            item for item in value.get("clip_windows") or [] if isinstance(item, dict)
        ]
    else:
        cues = [_cue_payload(cue) for cue in value]
        chosen_style = normalize_style(style)
    if clips is None and saved_windows:
        clips = [
            {
                "start": 0.0,
                "end": float(item.get("duration") or 0.0),
                "dur": float(item.get("duration") or 0.0),
                "scene": item.get("scene"),
            }
            for item in saved_windows
        ]
    windows = _clip_windows_for_validation(clips)
    bounds = total
    if bounds is None and windows:
        bounds = max(end for _start, end in windows.values())
    previous_end = 0.0
    for cue in cues:
        start = float(cue["start"])
        end = float(cue["end"])
        text = str(cue["text"]).strip()
        if not text:
            raise CaptionValidationError("Caption text is empty.")
        if not math.isfinite(start) or not math.isfinite(end):
            raise CaptionValidationError("Cue times must be finite.")
        if end <= start:
            raise CaptionValidationError(
                f"Cue at {start:.3f}s has zero or negative duration.",
            )
        if require_limits and (end - start < MIN_CUE - TIME_EPSILON or end - start > MAX_CUE + TIME_EPSILON):
            raise CaptionValidationError(
                f"Cue at {start:.3f}s is outside {MIN_CUE}-{MAX_CUE}s.",
            )
        if start < -TIME_EPSILON:
            raise CaptionValidationError(f"Cue at {start:.3f}s starts before zero.")
        if bounds is not None and end > float(bounds) + TIME_EPSILON:
            raise CaptionValidationError(
                f"Cue at {start:.3f}s ends outside the cut.",
            )
        if start < previous_end - 1e-6:
            raise CaptionValidationError(
                f"Cue at {start:.3f}s overlaps the previous cue.",
            )
        previous_end = max(previous_end, end)
        clip_index = int(cue.get("clip_index") or 0)
        if windows:
            window = windows.get(clip_index)
            if window is None:
                raise CaptionValidationError(
                    f"Cue at {start:.3f}s references missing clip {clip_index}.",
                )
            clip_start, clip_end = window
            if start < clip_start - TIME_EPSILON or end > clip_end + TIME_EPSILON:
                raise CaptionValidationError(
                    f"Cue at {start:.3f}s is outside clip {clip_index + 1}.",
                )
        lines = _line_count(text)
        if lines > int(chosen_style["max_lines"]):
            raise CaptionValidationError(
                f"Cue at {start:.3f}s has {lines} lines; "
                f"the style allows {chosen_style['max_lines']}.",
            )


# ---------------------------------------------------------------- preview


def safe_zone_rects(style: dict, width: int = 1080, height: int = 1920) -> dict:
    """Normalized platform and caption rectangles for the caption preview."""
    chosen = normalize_style(style)
    zone = chosen["safe_zone"]
    left = round(float(zone["left"]), 4)
    right = round(float(zone["right"]), 4)
    top = round(float(zone["top"]), 4)
    bottom = round(float(zone["bottom"]), 4)
    frame = {
        "x": left,
        "y": top,
        "w": round(max(0.01, 1.0 - left - right), 4),
        "h": round(max(0.01, 1.0 - top - bottom), 4),
    }
    line_height = float(chosen["font_size"]) * 1.22 / max(1, height)
    box_height = round(min(
        frame["h"],
        max(0.03, line_height * int(chosen["max_lines"]) + 0.02),
    ), 4)
    if chosen["position"] == "top":
        box_y = frame["y"]
    elif chosen["position"] == "center":
        box_y = frame["y"] + (frame["h"] - box_height) / 2
    else:
        box_y = frame["y"] + frame["h"] - box_height
    caption = {
        "x": frame["x"],
        "y": round(box_y, 4),
        "w": frame["w"],
        "h": box_height,
    }
    return {
        "platform": frame,
        "caption": caption,
        "top_reserved": {"x": 0.0, "y": 0.0, "w": 1.0, "h": top},
        "bottom_reserved": {"x": 0.0, "y": round(1.0 - bottom, 4), "w": 1.0, "h": bottom},
    }
