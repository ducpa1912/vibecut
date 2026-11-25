"""Canonical speech-timed caption engine shared by every output surface.

The renderer, SRT/VTT export, review links, and artifact identity all describe
the same cue list. The module reads the transcript analysis already wrote,
builds deterministic cues per cut, and stores versioned sidecars under
``data/jobs/<id>/caption_tracks``. Both the renderer and the export layer call
:func:`cues_for_plan`, so cue text and timing cannot drift between the burned
MP4, the caption-only preview, the artifact SRT/VTT, and the subtitle file.

Trust-core callers also use the lightweight compatibility API:
``CUE_WIDTH``, :func:`caption_text`, :func:`chunk_text`, :func:`reel_cues`,
and :func:`cue_tuples`. Those adapters preserve the pre-Caption-Studio contract
without maintaining a second cue engine.

Sparse speech policy: a short word held over a long silence is capped at
``MAX_CUE`` seconds and reported in ``warnings`` rather than stretched into a
cue longer than four seconds. Cue timing is quantized to rendered frames when
the job source duration is known, matching the burned video.
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
FRAME_FPS = 30
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
SENTENCE_END_RE = re.compile(r"[.!?…。！？；;]+")
ABBREVIATIONS = frozenset({
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc",
    "e.g", "i.e", "u.s", "u.k", "a.m", "p.m", "fig", "dept",
    "est", "inc", "ltd", "corp", "approx",
})
EMOJI_ZWJ = "\u200d"
EMOJI_VARIATION = frozenset({"\ufe0e", "\ufe0f"})
EMOJI_MODIFIERS = frozenset(chr(code) for code in range(0x1F3FB, 0x1F400))
REGIONAL_INDICATORS = frozenset(chr(code) for code in range(0x1F1E6, 0x1F200))


class CaptionError(ValueError):
    """Base error for caption construction and validation."""


class CaptionStyleError(CaptionError):
    """A caption style is malformed or unknown."""


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
    transcript_id: str | None = None

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
            transcript_id=(
                str(value["transcript_id"]) if value.get("transcript_id") else None
            ),
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
        styles[key] = normalize_style(
            apply_style_overrides(styles.get(key) or {}, value),
            style_id=key,
        )
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
    return apply_style_overrides(
        section["styles"][requested],
        overrides,
    ) | {"id": requested}


def apply_style_overrides(style: dict, overrides: dict | None) -> dict:
    """Merge overrides onto a style, preserving the base safe zone."""
    base = dict(style)
    if overrides is None:
        return normalize_style(base, style_id=base.get("id"))
    if not isinstance(overrides, dict):
        raise CaptionStyleError("Caption style overrides must be an object.")
    zone = overrides.get("safe_zone", overrides.get("safe-zone"))
    if isinstance(zone, dict):
        base["safe_zone"] = {
            **(base.get("safe_zone") or STYLE_DEFAULTS["safe_zone"]),
            **zone,
        }
        overrides = {
            key: value for key, value in overrides.items()
            if key not in {"safe_zone", "safe-zone"}
        }
    base.update(overrides)
    return normalize_style(base, style_id=base.get("id"))


def style_hash(style: dict) -> str:
    normalized = normalize_style(style)
    normalized.pop("id", None)
    return _hash_json(normalized)


# ---------------------------------------------------------------- text helpers


def normalize_text(text: Any) -> str:
    return " ".join(str(text or "").replace("\r", "\n").split())


def split_sentences(text: str) -> list[str]:
    """Split on sentence punctuation without breaking decimals/abbreviations."""
    value = normalize_text(text)
    if not value:
        return []
    parts: list[str] = []
    cursor = 0
    for match in SENTENCE_END_RE.finditer(value):
        mark = match.group(0)
        after = match.end()
        if mark == ".":
            before = value[match.start() - 1] if match.start() else ""
            following = value[after] if after < len(value) else ""
            if before.isdigit() and following.isdigit():
                continue
            token = re.search(r"([A-Za-z][A-Za-z.]*)$", value[:match.start()])
            token_text = token.group(1) if token else ""
            if token_text.lower().strip(".") in ABBREVIATIONS:
                continue
            if len(token_text) == 1 and following.isalpha():
                # Initials and dotted forms such as U.S. or e.g.
                continue
        chunk = value[cursor:after].strip()
        if chunk:
            parts.append(chunk)
        cursor = after
    tail = value[cursor:].strip()
    if tail:
        parts.append(tail)
    return parts or [value]


def _grapheme_clusters(text: str) -> list[str]:
    """Small grapheme grouping so emoji ZWJ sequences are never split."""
    clusters: list[str] = []
    for char in text:
        if not clusters:
            clusters.append(char)
            continue
        previous = clusters[-1]
        if (
            char == EMOJI_ZWJ
            or previous.endswith(EMOJI_ZWJ)
            or char in EMOJI_VARIATION
            or char in EMOJI_MODIFIERS
            or (
                char in REGIONAL_INDICATORS
                and previous[-1] in REGIONAL_INDICATORS
                and len(previous) == 1
            )
        ):
            clusters[-1] += char
        else:
            clusters.append(char)
    return clusters or [text]


def _hard_split(word: str, width: int) -> list[str]:
    if width <= 0:
        return [word]
    clusters = _grapheme_clusters(word)
    return [
        "".join(clusters[index:index + width])
        for index in range(0, len(clusters), width)
    ] or [word]


def _visible_length(text: str) -> int:
    return len(_grapheme_clusters(text))


def wrap_lines(text: str, max_chars: int) -> list[str]:
    """Word-boundary wrapping with character fallback for CJK and long tokens."""
    value = normalize_text(text)
    if not value:
        return []
    width = max(8, int(max_chars))
    if _visible_length(value) <= width:
        return [value]
    words = value.split()
    if len(words) <= 1:
        return _hard_split(value, width)
    lines: list[str] = []
    current = ""
    for word in words:
        pieces = _hard_split(word, width) if _visible_length(word) > width else [word]
        for piece in pieces:
            candidate = f"{current} {piece}".strip()
            if _visible_length(candidate) <= width:
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
    return max(1, _visible_length(normalize_text(text)))


def _split_words_evenly(text: str, count: int, style: dict) -> list[str]:
    value = normalize_text(text)
    words = value.split()
    if count <= 1:
        return [text]
    if len(words) <= 1:
        if not value:
            return [text]
        size = max(1, math.ceil(_visible_length(value) / count))
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


def _style_safe(text: str, style: dict) -> bool:
    lines = [line for line in str(text).splitlines() if line.strip()]
    if not lines or len(lines) > int(style["max_lines"]):
        return False
    return all(
        _visible_length(line) <= int(style["max_chars"])
        for line in lines
    )


# ---------------------------------------------------------------- transcript


def read_transcript_v2(job_dir: Path | None) -> dict | None:
    """Newest Transcript v2 for a job, if one exists."""
    if job_dir is None:
        return None
    try:
        import stt  # noqa: PLC0415 - keeps caption-only imports light
    except Exception:  # noqa: BLE001
        return None
    try:
        value = stt.load_latest_transcript(Path(job_dir))
    except Exception:  # noqa: BLE001
        return None
    return value if isinstance(value, dict) else None


def _v2_words_by_segment(transcript: dict) -> dict[int, list[dict]]:
    grouped: dict[int, list[dict]] = {}
    for raw in transcript.get("words") or []:
        if not isinstance(raw, dict):
            continue
        text = normalize_text(raw.get("w") or raw.get("word"))
        if not text:
            continue
        try:
            start = float(raw.get("start", 0.0))
            end = float(raw.get("end", start))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(start) or not math.isfinite(end) or end <= start:
            continue
        try:
            index = int(raw.get("segment") or 0)
        except (TypeError, ValueError):
            index = 0
        grouped.setdefault(index, []).append({
            "w": text,
            "start": start,
            "end": end,
            "confidence": raw.get("confidence"),
        })
    return grouped


def _segments_from_v2(transcript: dict) -> list[dict]:
    words_by_segment = _v2_words_by_segment(transcript)
    segments: list[dict] = []
    for position, item in enumerate(transcript.get("segments") or []):
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
        index = len(segments)
        segment = {
            "index": index,
            "start": start,
            "end": end,
            "text": text,
        }
        words = words_by_segment.get(position)
        if words:
            segment["words"] = words
        segments.append(segment)
    return segments


def read_transcript_segments(job_dir: Path | None) -> list[dict]:
    """Read speech timing: Transcript v2 words first, legacy JSON as fallback."""
    if job_dir is None:
        return []
    transcript = read_transcript_v2(job_dir)
    if transcript is not None:
        segments = _segments_from_v2(transcript)
        if segments:
            return segments
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


def _frames_for(start: float, duration: float, source_duration: float) -> int:
    """Mirror render._frames_for so cue times land on rendered frames."""
    frames = max(1, int(round(duration * FRAME_FPS)))
    if source_duration > 0:
        room = max(1, int((source_duration - start) * FRAME_FPS + 1e-6))
        frames = min(frames, room)
    return frames


def _clip_windows(plan: dict, source_duration: float | None = None) -> list[dict]:
    windows: list[dict] = []
    offset = 0.0
    source = float(source_duration or 0.0)
    for clip in plan.get("clips") or []:
        if not isinstance(clip, dict):
            continue
        try:
            start = max(0.0, float(clip.get("start") or 0.0))
            raw_end = float(
                clip.get("end")
                if clip.get("end") is not None
                else start + float(clip.get("dur") or clip.get("duration") or 0.0)
            )
        except (TypeError, ValueError):
            continue
        if not math.isfinite(start) or not math.isfinite(raw_end) or raw_end <= start:
            continue
        if source > 0:
            frames = _frames_for(start, max(0.2, raw_end - start), source)
            duration = frames / FRAME_FPS
            end = start + duration
        else:
            duration = raw_end - start
            end = raw_end
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
    text = str(segment.get("text") or "")
    words = text.split()
    if len(words) <= 1:
        clusters = _grapheme_clusters(normalize_text(text))
        single_script = bool(re.search(
            r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]", text,
        )) or not re.search(r"[A-Za-z0-9]", text)
        if len(clusters) > 1 and single_script:
            first = int(math.floor(
                (overlap_start - seg_start) / seg_duration * len(clusters),
            ))
            last = int(math.ceil(
                (overlap_end - seg_start) / seg_duration * len(clusters),
            ))
            first = max(0, min(len(clusters) - 1, first))
            last = max(first + 1, min(len(clusters), last))
            return "".join(clusters[first:last])
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


def _ends_sentence(text: str) -> bool:
    value = str(text or "").rstrip("\"'”’)]}")
    return bool(value) and value[-1] in ".!?…。！？"


def _join_caption_words(words: Iterable[str]) -> str:
    values = [value for value in words if value]
    if not values:
        return ""
    cjk = re.compile(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]")
    if all(cjk.search(value) for value in values):
        return "".join(values)
    return " ".join(values)


def _format_word_cue(words: list[dict], style: dict) -> str:
    text = _join_caption_words([str(word["w"]) for word in words])
    if style.get("uppercase"):
        text = text.upper()
    return "\n".join(wrap_lines(text, int(style["max_chars"])))


def _segment_words(segment: dict, start: float, end: float) -> list[dict]:
    """The segment's measured words that belong to the window ``[start, end)``.

    A word belongs to the one window holding its midpoint. Taking every word
    that merely overlapped repeated a boundary word in two adjacent clips
    (``…HAS TO`` / ``TO LOOK…``); a word mostly outside the cut is not heard.
    """
    rows: list[dict] = []
    for raw in segment.get("words") or []:
        if not isinstance(raw, dict):
            continue
        text = normalize_text(raw.get("w") or raw.get("word"))
        if not text:
            continue
        try:
            word_start = float(raw.get("start", 0.0))
            word_end = float(raw.get("end", word_start))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(word_start) or not math.isfinite(word_end):
            continue
        if word_end <= start + TIME_EPSILON or word_start >= end - TIME_EPSILON:
            continue
        middle = (word_start + word_end) / 2.0
        if middle < start or middle >= end:
            continue
        word_start = max(start, word_start)
        word_end = min(end, word_end)
        if word_end <= word_start:
            continue
        rows.append({"w": text, "start": word_start, "end": word_end})
    rows.sort(key=lambda item: (item["start"], item["end"]))
    return rows


def _word_cues(words: list[dict], style: dict) -> list[dict]:
    """Group measured words into display cues and keep their real times."""
    groups: list[list[dict]] = []
    current: list[dict] = []
    for word in words:
        candidate = current + [word]
        text = _format_word_cue(candidate, style)
        if current and not _style_safe(text, style):
            groups.append(current)
            current = [word]
        else:
            current = candidate
        if _ends_sentence(str(word["w"])) and current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    cues: list[dict] = []
    for group in groups:
        start = float(group[0]["start"])
        end = float(group[-1]["end"])
        text = _format_word_cue(group, style)
        if not text or end <= start:
            continue
        cues.append({"start": start, "end": end, "text": text})
    return cues


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
        word_covered = False
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
            # Words belong to their segment already; the clip decides which
            # of them are heard, so test against the clip, not the overlap.
            words = _segment_words(segment, clip_start, clip_end)
            if segment.get("words"):
                word_covered = True
                # Measured words are the truth: none heard here means no
                # text, never a character-share guess of the segment.
                for cue in _word_cues(words, style):
                    local_pieces.append({
                        "start": cue["start"],
                        "end": cue["end"],
                        "text": cue["text"],
                        "source_segment": segment_index,
                        "word_timed": True,
                    })
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
        if local_pieces or word_covered:
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
            if piece.get("word_timed"):
                pieces.append({
                    "start": float(piece["start"]),
                    "end": float(piece["end"]),
                    "text": piece["text"],
                    "source_segment": piece.get("source_segment"),
                    "clip_index": window["index"],
                    "scene": window["scene"],
                })
                continue
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


def _cap_cue(cue: dict, warnings: list[str], reason: str = "") -> dict:
    if float(cue["end"]) - float(cue["start"]) <= MAX_CUE + TIME_EPSILON:
        return cue
    capped = {**cue, "end": round(float(cue["start"]) + MAX_CUE, 3)}
    suffix = f" {reason}" if reason else ""
    warnings.append(
        f"Clip {int(cue.get('clip_index') or 0) + 1}: cue at "
        f"{float(cue['start']):.2f}s capped at {MAX_CUE:.1f}s;{suffix}".strip()
    )
    return capped


def _fit_cue_text_and_timing(
    cue: dict,
    style: dict,
    warnings: list[str] | None = None,
) -> list[dict]:
    """Split a long cue at word boundaries so no cue exceeds MAX_CUE."""
    warnings = warnings if warnings is not None else []
    duration = max(0.0, float(cue["end"]) - float(cue["start"]))
    if duration <= MAX_CUE + TIME_EPSILON:
        return [cue]
    words = normalize_text(cue["text"]).split()
    if len(words) <= 1:
        return [_cap_cue(cue, warnings, "sparse speech")]
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
        return [_cap_cue(cue, warnings, "sparse speech")]
    weights = [_visible_weight(chunk) for chunk in chunks]
    total = max(1, sum(weights))
    result = []
    cursor = float(cue["start"])
    for index, chunk in enumerate(chunks):
        end = float(cue["end"]) if index == len(chunks) - 1 else cursor + duration * weights[index] / total
        result.append(_cap_cue({
            **cue,
            "start": cursor,
            "end": max(cursor, end),
            "text": chunk,
        }, warnings, "sparse speech"))
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
            warnings.append(
                f"Clip {window['index'] + 1}: dropped a cue shorter than 0.01s "
                f"at {start:.3f}s."
            )
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
            merged = None
            if ordered:
                merged = _merge_text(ordered[-1]["text"], cue["text"], style)
                if merged:
                    ordered[-1]["text"] = merged
                    ordered[-1]["end"] = max(ordered[-1]["end"], end)
            if not merged:
                warnings.append(
                    f"Clip {window['index'] + 1}: dropped a cue shorter than "
                    f"0.02s at {start:.3f}s."
                )
            continue
        ordered.append({**cue, "start": start, "end": end})
        previous_end = end

    # Split anything longer than the maximum.
    split: list[dict] = []
    for cue in ordered:
        split.extend(_fit_cue_text_and_timing(cue, style, warnings))

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
            warnings.append(
                f"Clip {window['index'] + 1}: dropped a cue that rounded to "
                f"zero duration at {start:.3f}s."
            )
            continue
        text = str(cue["text"]).strip()
        if not text:
            warnings.append(
                f"Clip {window['index'] + 1}: dropped an empty cue at {start:.3f}s."
            )
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
    # Rounded clip boundaries can leave a 1ms seam between clips. Clamp once
    # more in reel order so the persisted track never overlaps.
    total = round(
        (windows[-1]["offset"] + windows[-1]["duration"]) if windows else 0.0,
        3,
    )
    last_end = 0.0
    clean: list[dict] = []
    for cue in cue_rows:
        start = round(max(last_end, float(cue["start"])), 3)
        end = round(min(total, float(cue["end"])), 3)
        if end <= start:
            warnings.append(
                f"Dropped a cue that rounded to zero duration at {start:.3f}s."
            )
            continue
        cue["start"] = start
        cue["end"] = end
        clean.append(cue)
        last_end = end
    for index, cue in enumerate(clean, 1):
        cue["id"] = f"c{index:03d}"
    return clean


def build_cues(
    plan: dict,
    *,
    style: dict | None = None,
    segments: list[dict] | None = None,
    source_duration: float | None = None,
) -> tuple[list[dict], str, list[str]]:
    """Build cue dictionaries from a plan. Pure and deterministic."""
    normalized_style = normalize_style(style)
    windows = _clip_windows(plan, source_duration)
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
    source_duration: float | None = None,
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
    chosen_source = (
        source_duration
        if source_duration is not None
        else plan.get("_source_duration")
    )
    cues, _source, _warnings = build_cues(
        working, style=chosen_style, segments=chosen_segments,
        source_duration=chosen_source,
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


def total_duration(plan: dict, source_duration: float | None = None) -> float:
    return round(
        sum(window["duration"] for window in _clip_windows(plan, source_duration)),
        3,
    )


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
        chosen_style = apply_style_overrides(style, overrides)
    else:
        raise CaptionStyleError("Caption style must be a name or an object.")
    job_id = str(job.get("id") or "")
    if job_dir is None and job_id and "/" not in job_id and ".." not in job_id:
        job_dir = DATA / "jobs" / job_id
    working = dict(plan)
    transcript_v2: dict | None = None
    scenes = (job.get("analysis") or {}).get("scenes")
    if scenes:
        working["_scenes"] = scenes
    if segments is None and job_dir is not None:
        transcript_v2 = read_transcript_v2(job_dir)
        if transcript_v2 is not None:
            segments = _segments_from_v2(transcript_v2)
        if not segments:
            segments = read_transcript_segments(job_dir)
    source_duration = float(
        (job.get("source") or {}).get("duration")
        or plan.get("_source_duration")
        or 0.0
    )
    cues, source, warnings = build_cues(
        working, style=chosen_style, segments=segments or [],
        source_duration=source_duration,
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
                "start": round(window["start"], 6),
                "end": round(window["end"], 6),
                "duration": round(window["duration"], 6),
            }
            for window in _clip_windows(working, source_duration)
        ],
        created=round(time.time(), 3),
        transcript_id=(
            str(transcript_v2.get("id"))
            if transcript_v2 and transcript_v2.get("id") else None
        ),
    )
    if job_dir is not None:
        existing = load_track(job_dir, identifier)
        if existing is not None:
            return existing
        save_track(job_dir, track)
    return track


# ---------------------------------------------------------------- editing


# ---------------------------------------------------------------- validation


# ---------------------------------------------------------------- preview


