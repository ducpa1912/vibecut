"""Deterministic, local-only overlay plans for Flow 2.

This module is intentionally pure: it validates normalized overlay layers,
computes their boxes in a vertical frame, warns about platform safe zones and
analysis face boxes, and returns a stable plan that can be written to
``overlays.json``. It never starts ffmpeg, reads a render, or writes a file.

Coordinates are normalized to the output frame: ``x``/``y`` are the top-left
corner, ``w``/``h`` are the box size, and every value is in ``0..1``. The
anchor string is ``<vertical>-<horizontal>`` where vertical is ``top``,
``center`` or ``bottom`` and horizontal is ``left``, ``center`` or ``right``.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import unicodedata
from dataclasses import dataclass, replace
from typing import Any

SCHEMA_VERSION = 1
MAX_LAYERS = 12
MAX_TEXT_LENGTH = 160
MAX_LINES = 4
MIN_DURATION = 0.2
MAX_TIMELINE = 3600.0
Z_MIN = 0
Z_MAX = 99
FACE_OVERLAP_RATIO = 0.05

KINDS = ("hook", "title", "caption", "lower_third", "cta")
ASPECTS = ("9:16", "4:5", "1:1", "16:9", "16:10")
VERTICAL = ("top", "center", "bottom")
HORIZONTAL = ("left", "center", "right")

FLAG = "VIBECUT_ENABLE_OVERLAYS"
FLAG_ON = frozenset({"1", "true", "yes", "on"})

CANVAS = {
    "9:16": {"w": 1080, "h": 1920},
    "4:5": {"w": 1080, "h": 1350},
}

# Advisory platform chrome. These are deliberately conservative rectangles,
# not platform guarantees. A layer that intersects one still renders; the plan
# reports a warning so the creator can move it.
SAFE_AREAS = {
    "9:16": {"x": 0.05, "y": 0.05, "w": 0.90, "h": 0.87},
    "4:5": {"x": 0.05, "y": 0.05, "w": 0.90, "h": 0.88},
    "1:1": {"x": 0.05, "y": 0.05, "w": 0.90, "h": 0.90},
    "16:9": {"x": 0.05, "y": 0.05, "w": 0.90, "h": 0.90},
    "16:10": {"x": 0.05, "y": 0.05, "w": 0.90, "h": 0.90},
}
RESERVED_ZONES = {
    "9:16": (
        {"name": "top-ui", "x": 0.0, "y": 0.0, "w": 1.0, "h": 0.05},
        {"name": "bottom-ui", "x": 0.0, "y": 0.92, "w": 1.0, "h": 0.08},
        {"name": "right-ui", "x": 0.88, "y": 0.30, "w": 0.12, "h": 0.62},
    ),
    "4:5": (
        {"name": "top-ui", "x": 0.0, "y": 0.0, "w": 1.0, "h": 0.05},
        {"name": "bottom-ui", "x": 0.0, "y": 0.93, "w": 1.0, "h": 0.07},
        {"name": "right-ui", "x": 0.88, "y": 0.30, "w": 0.12, "h": 0.63},
    ),
    "1:1": (
        {"name": "top-ui", "x": 0.0, "y": 0.0, "w": 1.0, "h": 0.05},
        {"name": "bottom-ui", "x": 0.0, "y": 0.95, "w": 1.0, "h": 0.05},
    ),
    "16:9": (
        {"name": "top-ui", "x": 0.0, "y": 0.0, "w": 1.0, "h": 0.05},
        {"name": "bottom-ui", "x": 0.0, "y": 0.95, "w": 1.0, "h": 0.05},
    ),
    "16:10": (
        {"name": "top-ui", "x": 0.0, "y": 0.0, "w": 1.0, "h": 0.05},
        {"name": "bottom-ui", "x": 0.0, "y": 0.95, "w": 1.0, "h": 0.05},
    ),
}

DEFAULT_ANCHOR = {
    "hook": "top-center",
    "title": "center",
    "caption": "bottom-center",
    "lower_third": "bottom-left",
    "cta": "center",
}
DEFAULT_BOX = {
    "hook": (0.76, 0.16),
    "title": (0.76, 0.14),
    "caption": (0.76, 0.12),
    "lower_third": (0.64, 0.14),
    "cta": (0.64, 0.10),
}

# Anchor positions respect platform chrome at the edges. A bottom-aligned
# caption ends above the usual caption/CTA bar; a right-aligned layer ends
# before the action rail.
ANCHOR_MARGIN = {
    "left": 0.05,
    "right": 0.12,
    "top": 0.05,
    "bottom": 0.08,
}

STYLE_DEFAULTS = {
    "font": "sans",
    "size": 44,
    "weight": 800,
    "color": "#ffffff",
    "background": "none",
    "stroke": "#000000",
    "align": "center",
    "uppercase": False,
    "shadow": True,
}
STYLE_KEYS = tuple(STYLE_DEFAULTS)
FONTS = {"sans": "sans", "sans-serif": "sans", "serif": "serif", "mono": "mono", "monospace": "mono"}
HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")

_ANCHOR_ALIASES = {
    "top": "top-center",
    "bottom": "bottom-center",
    "left": "center-left",
    "right": "center-right",
    "center": "center",
    "middle": "center",
}


class OverlayError(ValueError):
    """Base error for an invalid overlay plan."""

    status_code = 422


class OverlayInputError(OverlayError):
    """The request shape or a top-level option is malformed."""

    status_code = 400


class OverlayConflict(OverlayError):
    """The artifact/story context conflicts with the requested plan."""

    status_code = 409


@dataclass(frozen=True)
class OverlayLayer:
    """One normalized overlay layer in output-frame coordinates."""

    id: str
    kind: str
    text: str
    start: float
    end: float
    anchor: str
    box: dict[str, float]
    z: int
    style: dict[str, Any]
    safe_zone: bool
    opacity: float
    rect: dict[str, float]

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "duration": round(self.end - self.start, 3),
            "anchor": self.anchor,
            "box": dict(self.box),
            "rect": dict(self.rect),
            "z": self.z,
            "style": dict(self.style),
            "safe_zone": self.safe_zone,
            "opacity": self.opacity,
        }


@dataclass(frozen=True)
class OverlayPlan:
    """A deterministic overlay plan plus its advisory warnings."""

    job_id: str
    aspect: str
    layers: tuple[OverlayLayer, ...]
    warnings: tuple[dict, ...] = ()
    story_id: str | None = None
    artifact_id: str | None = None
    clip_set_id: str | None = None
    story_title: str | None = None
    duration: float | None = None

    def payload(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "job_id": self.job_id,
            "story_id": self.story_id,
            "artifact_id": self.artifact_id,
            "clip_set_id": self.clip_set_id,
            "story_title": self.story_title,
            "aspect": self.aspect,
            "duration": self.duration,
            "canvas": dict(CANVAS[self.aspect]),
            "safe_zones": {
                "safe_area": dict(SAFE_AREAS[self.aspect]),
                "reserved": [dict(zone) for zone in RESERVED_ZONES[self.aspect]],
            },
            "limits": {
                "max_layers": MAX_LAYERS,
                "max_text_length": MAX_TEXT_LENGTH,
                "max_lines": MAX_LINES,
            },
            "count": len(self.layers),
            "layers": [layer.as_dict() for layer in self.layers],
        }

    @property
    def hash(self) -> str:
        return overlay_hash(self.payload())

    def as_dict(self) -> dict:
        value = self.payload()
        value["hash"] = self.hash
        return value


# ---------------------------------------------------------------- feature flag


def enabled(environ: dict[str, str] | os._Environ | None = None) -> bool:
    """Return whether the Flow 2 overlay surface is enabled.

    Default is off. Only an explicit truthy value turns it on.
    """

    source = os.environ if environ is None else environ
    return str(source.get(FLAG, "")).strip().lower() in FLAG_ON


# ---------------------------------------------------------------- primitive validation


def normalize_aspect(value: object) -> str:
    aspect = str(value or "").strip().replace("x", ":").replace("/", ":")
    if aspect not in ASPECTS:
        raise OverlayInputError("aspect must be 9:16, 4:5, 1:1, 16:9 or 16:10.")
    return aspect


def normalize_text(value: object) -> str:
    """NFC-normalize, trim, and collapse overlay text deterministically."""

    if not isinstance(value, str):
        raise OverlayError("Overlay text must be a string.")
    text = unicodedata.normalize("NFC", value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for raw in text.split("\n"):
        line = " ".join(raw.split())
        if line:
            lines.append(line)
    cleaned = "\n".join(lines)
    if not cleaned:
        raise OverlayError("Overlay text cannot be empty.")
    if len(lines) > MAX_LINES:
        raise OverlayError(f"Overlay text supports at most {MAX_LINES} lines.")
    if len(cleaned) > MAX_TEXT_LENGTH:
        raise OverlayError(
            f"Overlay text is longer than {MAX_TEXT_LENGTH} characters."
        )
    for char in cleaned:
        if unicodedata.category(char) == "Cc" and char != "\n":
            raise OverlayError("Overlay text contains a control character.")
    return cleaned


def normalize_kind(value: object) -> str:
    kind = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if kind == "lowerthird":
        kind = "lower_third"
    if kind not in KINDS:
        raise OverlayError(
            "kind must be one of: " + ", ".join(KINDS) + "."
        )
    return kind


def normalize_anchor(value: object) -> str:
    raw = str(value or "").strip().lower().replace("_", "-").replace(" ", "-")
    raw = re.sub(r"-+", "-", raw).strip("-")
    if not raw:
        raise OverlayError("anchor cannot be empty.")
    if raw in _ANCHOR_ALIASES:
        return _ANCHOR_ALIASES[raw]
    parts = raw.split("-")
    if len(parts) != 2:
        raise OverlayError(
            "anchor must be <vertical>-<horizontal>, for example bottom-center."
        )
    if parts[0] in VERTICAL and parts[1] in HORIZONTAL:
        vertical, horizontal = parts
    elif parts[1] in VERTICAL and parts[0] in HORIZONTAL:
        horizontal, vertical = parts
    else:
        raise OverlayError(
            "anchor must use top/center/bottom and left/center/right."
        )
    return "center" if vertical == horizontal == "center" else f"{vertical}-{horizontal}"


def normalize_color(value: object, *, allow_none: bool = False) -> str:
    if allow_none and str(value or "").strip().lower() in {"", "none", "transparent"}:
        return "none"
    text = str(value or "").strip().lower()
    if not HEX_RE.match(text):
        raise OverlayError("Colors must be #rgb, #rrggbb, #rrggbbaa, or none.")
    if len(text) == 4:
        text = "#" + "".join(char * 2 for char in text[1:])
    return text


def _strict_bool(value: object, default: bool, label: str) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
    raise OverlayError(f"{label} must be a boolean.")


def normalize_box(value: object, kind: str) -> dict[str, float]:
    default_w, default_h = DEFAULT_BOX[kind]
    if value is None:
        width, height = default_w, default_h
    elif isinstance(value, dict):
        allowed = {"w", "h", "width", "height"}
        unknown = set(value) - allowed
        if unknown:
            raise OverlayError(
                "box supports only w, h, width, and height."
            )
        raw_w = value.get("w", value.get("width"))
        raw_h = value.get("h", value.get("height"))
        if "w" in value and "width" in value and value["w"] != value["width"]:
            raise OverlayError("box w and width disagree.")
        if "h" in value and "height" in value and value["h"] != value["height"]:
            raise OverlayError("box h and height disagree.")
        width = default_w if raw_w is None else raw_w
        height = default_h if raw_h is None else raw_h
    else:
        raise OverlayError("box must be an object with w and h.")
    try:
        width = float(width)
        height = float(height)
    except (TypeError, ValueError) as exc:
        raise OverlayError("box w and h must be numbers.") from exc
    if not math.isfinite(width) or not math.isfinite(height):
        raise OverlayError("box w and h must be finite.")
    if not 0.05 <= width <= 1.0:
        raise OverlayError("box w must be between 0.05 and 1.0.")
    if not 0.03 <= height <= 1.0:
        raise OverlayError("box h must be between 0.03 and 1.0.")
    return {"w": round(width, 4), "h": round(height, 4)}


def normalize_style(value: object) -> dict[str, Any]:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise OverlayError("style must be an object.")
    unknown = set(value) - set(STYLE_KEYS)
    if unknown:
        raise OverlayError(
            "Unknown style keys: " + ", ".join(sorted(str(key) for key in unknown)) + "."
        )
    style = dict(STYLE_DEFAULTS)
    if "font" in value:
        font = str(value["font"] or "").strip().lower()
        if font not in FONTS:
            raise OverlayError("style.font must be sans, serif, or mono.")
        style["font"] = FONTS[font]
    if "size" in value:
        try:
            size = float(value["size"])
        except (TypeError, ValueError) as exc:
            raise OverlayError("style.size must be a number.") from exc
        if not math.isfinite(size) or not 12 <= size <= 160:
            raise OverlayError("style.size must be between 12 and 160.")
        style["size"] = int(round(size))
    if "weight" in value:
        try:
            weight = float(value["weight"])
        except (TypeError, ValueError) as exc:
            raise OverlayError("style.weight must be a number.") from exc
        if not math.isfinite(weight) or not 100 <= weight <= 900:
            raise OverlayError("style.weight must be between 100 and 900.")
        style["weight"] = int(round(weight))
    if "color" in value:
        style["color"] = normalize_color(value["color"])
    if "background" in value:
        style["background"] = normalize_color(value["background"], allow_none=True)
    if "stroke" in value:
        style["stroke"] = normalize_color(value["stroke"], allow_none=True)
    if "align" in value:
        align = str(value["align"] or "").strip().lower()
        if align not in HORIZONTAL:
            raise OverlayError("style.align must be left, center, or right.")
        style["align"] = align
    for key in ("uppercase", "shadow"):
        if key in value:
            style[key] = _strict_bool(value[key], bool(STYLE_DEFAULTS[key]), f"style.{key}")
    return style


def normalize_rect(anchor: str, box: dict[str, float]) -> dict[str, float]:
    if anchor == "center":
        vertical = horizontal = "center"
    else:
        vertical, horizontal = anchor.split("-")
    width = float(box["w"])
    height = float(box["h"])
    if horizontal == "left":
        x = ANCHOR_MARGIN["left"]
    elif horizontal == "right":
        x = 1.0 - ANCHOR_MARGIN["right"] - width
    else:
        x = (1.0 - width) / 2.0
    if vertical == "top":
        y = ANCHOR_MARGIN["top"]
    elif vertical == "bottom":
        y = 1.0 - ANCHOR_MARGIN["bottom"] - height
    else:
        y = (1.0 - height) / 2.0
    x = min(max(x, 0.0), max(0.0, 1.0 - width))
    y = min(max(y, 0.0), max(0.0, 1.0 - height))
    return {
        "x": round(x, 4),
        "y": round(y, 4),
        "w": round(width, 4),
        "h": round(height, 4),
    }


def _finite_time(value: object, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise OverlayError(f"{label} must be a number.") from exc
    if not math.isfinite(number):
        raise OverlayError(f"{label} must be finite.")
    return round(number, 3)


def _z_value(value: object) -> int | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise OverlayError("z must be an integer from 0 to 99.") from exc
    if not math.isfinite(number) or not number.is_integer():
        raise OverlayError("z must be an integer from 0 to 99.")
    z = int(number)
    if z < Z_MIN or z > Z_MAX:
        raise OverlayError(f"z must be between {Z_MIN} and {Z_MAX}.")
    return z


def _opacity(value: object) -> float:
    try:
        number = float(1.0 if value is None else value)
    except (TypeError, ValueError) as exc:
        raise OverlayError("opacity must be a number between 0 and 1.") from exc
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise OverlayError("opacity must be between 0 and 1.")
    return round(number, 3)


def _time_overlap(first: dict, second: dict) -> bool:
    return first["start"] < second["end"] and second["start"] < first["end"]


def normalize_layers(
    raw_layers: object,
    *,
    max_end: float | None = None,
) -> list[OverlayLayer]:
    """Validate layers, assign z and ids, and return them in paint order."""

    if not isinstance(raw_layers, (list, tuple)):
        raise OverlayError("layers must be a list.")
    if not raw_layers:
        raise OverlayError("layers must contain at least one overlay.")
    if len(raw_layers) > MAX_LAYERS:
        raise OverlayError(f"A plan supports at most {MAX_LAYERS} layers.")
    limit = MAX_TIMELINE if max_end is None else min(MAX_TIMELINE, float(max_end))
    cleaned: list[dict[str, Any]] = []
    explicit_z: list[int] = []
    used_ids: set[str] = set()
    for index, raw in enumerate(raw_layers):
        if not isinstance(raw, dict):
            raise OverlayError(f"Layer {index + 1} must be an object.")
        layer_id = str(raw.get("id") or "").strip()
        if layer_id:
            if not ID_RE.match(layer_id):
                raise OverlayError(
                    f"Layer {index + 1} id must start with a letter and use "
                    "letters, digits, _ or - (max 32 characters)."
                )
            if layer_id in used_ids:
                raise OverlayError(f"Duplicate layer id: {layer_id}.")
            used_ids.add(layer_id)
        text = normalize_text(raw.get("text"))
        start = _finite_time(raw.get("start"), "start")
        end = _finite_time(raw.get("end"), "end")
        if start < 0:
            raise OverlayError(f"Layer {index + 1} start cannot be negative.")
        if end <= start:
            raise OverlayError(f"Layer {index + 1} end must be later than start.")
        if end - start < MIN_DURATION:
            raise OverlayError(
                f"Layer {index + 1} must stay on screen for at least "
                f"{MIN_DURATION:g} seconds."
            )
        if end > limit + 0.001:
            raise OverlayError(
                f"Layer {index + 1} ends after the {limit:g}s plan window."
            )
        kind = normalize_kind(raw.get("kind"))
        anchor = normalize_anchor(raw.get("anchor") or DEFAULT_ANCHOR[kind])
        box = normalize_box(raw.get("box"), kind)
        z = _z_value(raw.get("z"))
        if z is not None:
            if z in explicit_z:
                raise OverlayError(f"Duplicate z-order: {z}.")
            explicit_z.append(z)
        cleaned.append({
            "index": index,
            "id": layer_id,
            "kind": kind,
            "text": text,
            "start": start,
            "end": end,
            "anchor": anchor,
            "box": box,
            "z": z,
            "style": normalize_style(raw.get("style")),
            "safe_zone": _strict_bool(raw.get("safe_zone"), True, "safe_zone"),
            "opacity": _opacity(raw.get("opacity")),
        })

    for first_index, first in enumerate(cleaned):
        for second in cleaned[first_index + 1:]:
            if (
                first["kind"] == second["kind"]
                and first["text"].casefold() == second["text"].casefold()
                and _time_overlap(first, second)
            ):
                raise OverlayError(
                    f"Duplicate {first['kind']} overlay text: "
                    f"\"{first['text']}\"."
                )

    used_z = set(explicit_z)
    next_z = Z_MIN
    for item in cleaned:
        if item["z"] is None:
            while next_z in used_z:
                next_z += 1
            if next_z > Z_MAX:
                raise OverlayError("No z-order slots remain.")
            item["z"] = next_z
            used_z.add(next_z)
            next_z += 1

    cleaned.sort(key=lambda item: (
        item["z"], item["start"], item["end"], item["index"],
    ))

    auto_id = 1
    for item in cleaned:
        if not item["id"]:
            while f"ov{auto_id:02d}" in used_ids:
                auto_id += 1
            item["id"] = f"ov{auto_id:02d}"
            used_ids.add(item["id"])
            auto_id += 1

    return [
        OverlayLayer(
            id=item["id"],
            kind=item["kind"],
            text=item["text"],
            start=item["start"],
            end=item["end"],
            anchor=item["anchor"],
            box=dict(item["box"]),
            z=item["z"],
            style=dict(item["style"]),
            safe_zone=item["safe_zone"],
            opacity=item["opacity"],
            rect=normalize_rect(item["anchor"], item["box"]),
        )
        for item in cleaned
    ]


# ---------------------------------------------------------------- geometry


def _intersection_area(first: dict, second: dict) -> float:
    left = max(float(first["x"]), float(second["x"]))
    top = max(float(first["y"]), float(second["y"]))
    right = min(
        float(first["x"]) + float(first["w"]),
        float(second["x"]) + float(second["w"]),
    )
    bottom = min(
        float(first["y"]) + float(first["h"]),
        float(second["y"]) + float(second["h"]),
    )
    return max(0.0, right - left) * max(0.0, bottom - top)


def _outside_area(rect: dict, area: dict) -> float:
    return max(0.0, rect["w"] * rect["h"] - _intersection_area(rect, area))


def safe_zone_warnings(plan: OverlayPlan) -> list[dict]:
    warnings: list[dict] = []
    area = SAFE_AREAS[plan.aspect]
    for layer in plan.layers:
        layer_area = layer.rect["w"] * layer.rect["h"]
        if layer_area <= 0:
            continue
        zones = []
        for zone in RESERVED_ZONES[plan.aspect]:
            overlap = _intersection_area(layer.rect, zone)
            if overlap / layer_area > 0.005:
                zones.append(zone["name"])
        if not zones and _outside_area(layer.rect, area) / layer_area > 0.005:
            zones.append("outside-safe-area")
        if not zones:
            continue
        warnings.append({
            "code": "safe_zone",
            "severity": "warning",
            "layer_id": layer.id,
            "zones": zones,
            "message": (
                f"{layer.kind.replace('_', ' ').title()} overlay intersects "
                f"{plan.aspect} reserved zones: {', '.join(zones)}."
            ),
        })
    return warnings


def _scene_faces(scene: dict) -> list[dict]:
    result: list[dict] = []
    candidates = []
    raw_faces = scene.get("faces")
    if isinstance(raw_faces, list):
        candidates.extend(raw_faces)
    attention = scene.get("attention")
    if isinstance(attention, dict) and isinstance(attention.get("face"), dict):
        candidates.append(attention["face"])
    for raw in candidates:
        if not isinstance(raw, dict):
            continue
        try:
            x = float(raw.get("x"))
            y = float(raw.get("y"))
            w = float(raw.get("w"))
            h = float(raw.get("h"))
            confidence = float(raw.get("confidence", 1.0))
        except (TypeError, ValueError):
            continue
        if not all(math.isfinite(value) for value in (x, y, w, h, confidence)):
            continue
        if confidence < 0.35 or w <= 0 or h <= 0:
            continue
        if w * h < 0.003:
            continue
        box = {
            "x": min(max(x, 0.0), 1.0),
            "y": min(max(y, 0.0), 1.0),
            "w": min(max(w, 0.0), 1.0),
            "h": min(max(h, 0.0), 1.0),
        }
        if box["x"] + box["w"] > 1.0:
            box["w"] = max(0.0, 1.0 - box["x"])
        if box["y"] + box["h"] > 1.0:
            box["h"] = max(0.0, 1.0 - box["y"])
        if box["w"] * box["h"] <= 0:
            continue
        if box not in result:
            result.append(box)
    return result


def _source_size(job: dict) -> tuple[float, float]:
    source = job.get("source") if isinstance(job.get("source"), dict) else {}
    try:
        width = float(source.get("width") or 0.0)
        height = float(source.get("height") or 0.0)
    except (TypeError, ValueError):
        width = height = 0.0
    if width <= 0 or height <= 0:
        return 0.0, 0.0
    return width, height


def _crop_for(scene: dict, aspect: str) -> tuple[float, float]:
    crops = scene.get("crops")
    crop = crops.get(aspect) if isinstance(crops, dict) else None
    if not isinstance(crop, dict):
        crop = scene.get("crop")
    try:
        cx = float((crop or {}).get("cx", 0.5))
        cy = float((crop or {}).get("cy", 0.5))
    except (TypeError, ValueError):
        cx = cy = 0.5
    if not math.isfinite(cx):
        cx = 0.5
    if not math.isfinite(cy):
        cy = 0.5
    return min(max(cx, 0.0), 1.0), min(max(cy, 0.0), 1.0)


def _map_face(
    face: dict,
    scene: dict,
    aspect: str,
    source_size: tuple[float, float],
) -> dict:
    width, height = source_size
    cx, cy = _crop_for(scene, aspect)
    if width <= 0 or height <= 0:
        return dict(face)
    source_ar = width / height
    target_ar = 1080 / 1920 if aspect == "9:16" else 1080 / 1350
    if source_ar > target_ar:
        crop_w = target_ar / source_ar
        crop_h = 1.0
    else:
        crop_w = 1.0
        crop_h = source_ar / target_ar
    x0 = cx - crop_w / 2.0
    y0 = cy - crop_h / 2.0
    return {
        "x": round((face["x"] - x0) / crop_w, 4),
        "y": round((face["y"] - y0) / crop_h, 4),
        "w": round(face["w"] / crop_w, 4),
        "h": round(face["h"] / crop_h, 4),
    }


def _clip_rect(rect: dict) -> dict:
    x = min(max(float(rect["x"]), 0.0), 1.0)
    y = min(max(float(rect["y"]), 0.0), 1.0)
    w = min(max(float(rect["w"]), 0.0), 1.0 - x)
    h = min(max(float(rect["h"]), 0.0), 1.0 - y)
    return {"x": x, "y": y, "w": w, "h": h}


def face_overlap_warnings(plan: OverlayPlan, job: dict) -> list[dict]:
    """Warn when an overlay box overlaps an analysis face box.

    Face boxes in job analysis are normalized to the source frame. They are
    mapped through the scene's crop for the requested aspect when source
    dimensions are available. Timing compares the layer window with scene
    windows; story edit ordering is not reconstructed.
    """

    analysis = job.get("analysis") if isinstance(job.get("analysis"), dict) else {}
    scenes = analysis.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        return []
    if not any(_scene_faces(scene) for scene in scenes if isinstance(scene, dict)):
        return []
    source_size = _source_size(job)
    warnings: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for layer in plan.layers:
        for scene_index, scene in enumerate(scenes):
            if not isinstance(scene, dict):
                continue
            try:
                scene_start = float(scene.get("start") or 0.0)
                scene_end = float(
                    scene.get("end") or scene_start + float(scene.get("dur") or 0.0)
                )
            except (TypeError, ValueError):
                continue
            if not math.isfinite(scene_start) or not math.isfinite(scene_end):
                continue
            if not (layer.start < scene_end and scene_start < layer.end):
                continue
            best_overlap = 0.0
            face_count = 0
            for face in _scene_faces(scene):
                mapped = _clip_rect(_map_face(face, scene, plan.aspect, source_size))
                overlap = _intersection_area(layer.rect, mapped)
                if overlap <= 0:
                    continue
                ratio = overlap / max(
                    1e-9, layer.rect["w"] * layer.rect["h"],
                )
                if ratio >= FACE_OVERLAP_RATIO:
                    best_overlap = max(best_overlap, ratio)
                    face_count += 1
            if best_overlap <= 0:
                continue
            scene_id = scene.get("id")
            scene_key = (
                str(scene_id) if scene_id is not None else f"#{scene_index}"
            )
            key = (layer.id, scene_key)
            if key in seen:
                continue
            seen.add(key)
            warnings.append({
                "code": "face_overlap",
                "severity": "warning",
                "layer_id": layer.id,
                "scene_id": scene_id,
                "face_count": max(1, face_count),
                "overlap": round(best_overlap, 3),
                "message": (
                    f"{layer.kind.replace('_', ' ').title()} overlay overlaps "
                    f"a detected face in scene {scene_id}."
                ),
            })
    return warnings


# ---------------------------------------------------------------- plan


def _number(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _story_seconds(story: dict | None) -> float:
    if not isinstance(story, dict):
        return 0.0
    for key in ("dur", "duration"):
        value = _number(story.get(key))
        if value > 0:
            return value
    clips = story.get("clips")
    if isinstance(clips, list):
        total = sum(_number(clip.get("dur")) for clip in clips if isinstance(clip, dict))
        if total > 0:
            return total
    start = _number(story.get("start"))
    end = _number(story.get("end"))
    return max(0.0, end - start)


def _artifact_seconds(manifest: dict | None, job: dict) -> float:
    if not isinstance(manifest, dict):
        return 0.0
    spec = manifest.get("spec") if isinstance(manifest.get("spec"), dict) else {}
    target = _number(spec.get("target"))
    if target > 0:
        return target
    clips = spec.get("clips")
    if isinstance(clips, list):
        total = sum(_number(clip.get("dur")) for clip in clips if isinstance(clip, dict))
        if total > 0:
            return total
    source = job.get("source") if isinstance(job.get("source"), dict) else {}
    return max(0.0, _number(source.get("duration")))


def _plan_seconds(story: dict | None, artifact: dict | None, job: dict) -> float:
    if isinstance(artifact, dict):
        value = _artifact_seconds(artifact, job)
        if value > 0:
            return value
    if isinstance(story, dict):
        value = _story_seconds(story)
        if value > 0:
            return value
    source = job.get("source") if isinstance(job.get("source"), dict) else {}
    return max(0.0, _number(source.get("duration")))


def build_plan(
    job: dict,
    aspect: object,
    raw_layers: object,
    *,
    story: dict | None = None,
    artifact: dict | None = None,
    clip_set_id: str | None = None,
) -> OverlayPlan:
    """Build one deterministic overlay plan without touching the job."""

    if not isinstance(job, dict) or not job.get("id"):
        raise OverlayInputError("A job is required to build an overlay plan.")
    chosen_aspect = normalize_aspect(aspect)

    artifact_story = ""
    artifact_spec_story = ""
    artifact_aspect = ""
    if isinstance(artifact, dict):
        spec = artifact.get("spec") if isinstance(artifact.get("spec"), dict) else {}
        artifact_aspect = str(spec.get("aspect") or artifact.get("aspect") or "")
        artifact_spec_story = str(spec.get("story_id") or "").strip()
        artifact_story = artifact_spec_story or str(
            artifact.get("story_id") or ""
        ).strip()
        if artifact_aspect and artifact_aspect != chosen_aspect:
            raise OverlayConflict(
                f"Artifact aspect is {artifact_aspect}, not {chosen_aspect}."
            )
    if isinstance(story, dict):
        story_value = str(story.get("id") or "").strip()
        if isinstance(artifact, dict):
            if not artifact_spec_story:
                raise OverlayConflict(
                    "Artifact spec has no story id; explicit story context "
                    "cannot be verified."
                )
            if not story_value or story_value != artifact_spec_story:
                raise OverlayConflict("The artifact belongs to a different story.")

    duration = round(_plan_seconds(story, artifact, job), 3)
    max_end = duration if duration > 0 else MAX_TIMELINE
    layers = normalize_layers(raw_layers, max_end=max_end)

    story_id = None
    story_title = None
    if isinstance(story, dict):
        story_id = str(story.get("id") or "") or None
        story_title = str(story.get("title") or "") or None
    elif artifact_story:
        story_id = artifact_story

    artifact_id = None
    if isinstance(artifact, dict):
        artifact_id = str(artifact.get("artifact_id") or "") or None

    plan = OverlayPlan(
        job_id=str(job["id"]),
        aspect=chosen_aspect,
        layers=tuple(layers),
        story_id=story_id,
        artifact_id=artifact_id,
        clip_set_id=str(clip_set_id) if clip_set_id else None,
        story_title=story_title,
        duration=duration if duration > 0 else None,
    )
    warnings = tuple(safe_zone_warnings(plan) + face_overlap_warnings(plan, job))
    return replace(plan, warnings=warnings)


# ---------------------------------------------------------------- Edit text layers

# Overlay plans predate the Edit document. Their ``caption`` kind is a generic
# on-screen text slot; in an Edit that becomes an ``emphasis`` word layer.
# Every other kind maps one to one.
EDIT_TEXT_KINDS = {
    "hook": "hook",
    "title": "title",
    "caption": "emphasis",
    "lower_third": "lower_third",
    "cta": "cta",
}


def _edit_text_entry(layer: OverlayLayer) -> dict:
    """Map one validated overlay layer to an Edit ``graphics`` text entry."""
    return {
        "id": layer.id,
        "type": "text",
        "kind": EDIT_TEXT_KINDS[layer.kind],
        "text": layer.text,
        "start": layer.start,
        "end": layer.end,
        "anchor": layer.anchor,
        "box": dict(layer.box),
        "z": layer.z,
        "style": dict(layer.style),
        "safe_zone": layer.safe_zone,
        "opacity": layer.opacity,
    }


def edit_text_layer(
    raw: object,
    *,
    max_end: float | None = None,
) -> dict:
    """Validate one overlay layer and return an Edit text layer.

    The overlay validators stay the single source of truth for text, timing,
    anchor, box, z-order, style and opacity. ``max_end`` caps the layer at the
    story duration, exactly as :func:`build_plan` does.
    """
    layer = normalize_layers([raw], max_end=max_end)[0]
    return _edit_text_entry(layer)


def edit_text_layers(
    raw_layers: object,
    *,
    max_end: float | None = None,
) -> list[dict]:
    """Validate overlay layers and return them as Edit ``graphics`` entries."""
    return [
        _edit_text_entry(layer)
        for layer in normalize_layers(raw_layers, max_end=max_end)
    ]


def plan_text_layers(plan: OverlayPlan) -> list[dict]:
    """Return a validated plan's layers as Edit ``graphics`` text entries."""
    return [_edit_text_entry(layer) for layer in plan.layers]


def overlay_hash(payload: dict) -> str:
    """Return a stable ``ov_`` hash over the canonical plan payload."""

    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "ov_" + hashlib.sha256(encoded).hexdigest()[:32]
