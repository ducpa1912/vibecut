"""Versioned per-story Edit documents for the Studio editor.

An Edit is the single document behind Flow 1 and Flow 2: Clean, reframe,
motion, color, graphics, captions and audio. Versions are immutable sidecars
under ``jobs/<id>/edits/<edit_id>.json``. The job only stores a pointer::

    job["story_edits"]["{set_id}:{story_id}:{aspect}"] -> edit_id

Every write creates a new version whose ``parent`` is the previous version.
Undo and restore also create versions, so history is append-only and
``history_store`` stays the audit trail. Nothing here starts ffmpeg, probes
media, or calls the network.

Coordinate contract
-------------------
* ``clean`` boxes use source-frame coordinates (0..1) and render before crop.
* ``graphics`` and caption cues use output-frame coordinates and render after
  crop.
* ``motion`` changes the crop window itself.

Hash contract
-------------
The content hash is sha256 over canonical JSON (sorted keys, no whitespace,
UTF-8) exactly like :func:`overlays.overlay_hash`. ``hash`` covers every layer
and every asset reference (LUT, sticker, music, voice). ``created``,
``version`` and ``parent`` are not content, so restoring the same layers keeps
the same ``hash`` but creates a new ``id``.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Iterable

import overlays

SCHEMA_VERSION = 1
RENDERER_VERSION = 1
MAX_CLEAN = 32
MAX_MOTION = 8
MAX_GRAPHICS = 32
MAX_TIMELINE = 4 * 3600.0
MAX_TEXT_LENGTH = 400
MAX_ID = 64

ASPECTS = ("9:16", "4:5", "1:1", "16:9", "16:10")
CLEAN_KINDS = ("crop_guard", "blur", "plate", "mask")
MOTION_KINDS = ("punch_in", "snap_zoom", "push", "shake")
TEXT_KINDS = ("hook", "title", "lower_third", "cta", "emphasis")
FX_KINDS = ("arrow", "circle", "underline", "progress_bar", "sticker")
AUDIO_MODES = ("original", "original_bed", "voice_over", "dub", "music_only")
REFRAME_MODES = ("auto", "center", "manual")

_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_EDIT_ID_RE = re.compile(r"^ed_[a-f0-9]{32}$")
_HASH_RE = re.compile(r"^[a-f0-9]{16,64}$")
_SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9_./-]{1,240}$")
_FORBIDDEN_RE = re.compile(
    r"inpaint|generative|delogo|watermark|"
    r"voice[\s_-]*clon|avatar|stock[\s_-]*b-?roll",
    re.IGNORECASE,
)

# Eight in-house colour looks. Values are absolute, not deltas, so an Edit's
# stored colour plan is self-contained and deterministic across releases.
COLOR_PRESETS: dict[str, dict[str, float]] = {
    "none": {
        "exposure": 0.0, "contrast": 0.0, "saturation": 0.0,
        "temperature": 0.0, "vignette": 0.0, "grain": 0.0, "sharpen": 0.0,
    },
    "warm_film": {
        "exposure": 0.02, "contrast": 0.08, "saturation": -0.05,
        "temperature": 0.25, "vignette": 0.18, "grain": 0.12, "sharpen": 0.05,
    },
    "cool_fade": {
        "exposure": 0.01, "contrast": -0.08, "saturation": -0.12,
        "temperature": -0.30, "vignette": 0.10, "grain": 0.05, "sharpen": 0.0,
    },
    "vivid_pop": {
        "exposure": 0.04, "contrast": 0.18, "saturation": 0.28,
        "temperature": 0.04, "vignette": 0.0, "grain": 0.0, "sharpen": 0.20,
    },
    "soft_matte": {
        "exposure": 0.06, "contrast": -0.20, "saturation": -0.08,
        "temperature": 0.08, "vignette": 0.0, "grain": 0.04, "sharpen": 0.0,
    },
    "golden_hour": {
        "exposure": 0.03, "contrast": 0.06, "saturation": 0.10,
        "temperature": 0.45, "vignette": 0.12, "grain": 0.06, "sharpen": 0.04,
    },
    "teal_orange": {
        "exposure": 0.0, "contrast": 0.14, "saturation": 0.12,
        "temperature": -0.10, "vignette": 0.08, "grain": 0.03, "sharpen": 0.10,
    },
    "mono_contrast": {
        "exposure": 0.02, "contrast": 0.24, "saturation": -1.0,
        "temperature": 0.0, "vignette": 0.14, "grain": 0.10, "sharpen": 0.12,
    },
    "clean_bright": {
        "exposure": 0.10, "contrast": 0.04, "saturation": 0.05,
        "temperature": 0.0, "vignette": 0.0, "grain": 0.0, "sharpen": 0.12,
    },
}

_PRESET_RANGES = {
    "exposure": (-1.0, 1.0),
    "contrast": (-1.0, 1.0),
    "saturation": (-1.0, 1.0),
    "temperature": (-1.0, 1.0),
    "vignette": (0.0, 1.0),
    "grain": (0.0, 1.0),
    "sharpen": (0.0, 1.0),
}

_STORY_REF_KEYS = frozenset({
    "set_id", "story_id", "clip_hash", "title", "duration", "clip_count",
})
_CLEAN_KEYS = frozenset({
    "id", "kind", "box", "ranges", "z", "color", "opacity", "radius", "label",
    "tracklet_id", "tracklet_kind",
})
# Detected Check kinds an optional Clean layer may name. The layer's own
# ``kind`` remains the cleanup method; ``tracklet_kind`` carries provenance
# for the save-time policy gate in routes_edits.
TRACKLET_KINDS = (
    "subtitle", "title", "lower_third", "handle_or_logo", "watermark",
    "credit", "screen_text",
)
_REFRAME_KEYS = frozenset({
    "mode", "cx", "cy", "zoom", "crop_path_ref", "overrides",
})
_MOTION_KEYS = frozenset({
    "id", "kind", "start", "end", "amount", "ramp", "seed", "hidden",
})
_COLOR_KEYS = frozenset({
    "preset", "lut", *_PRESET_RANGES,
})
_GRAPHIC_TEXT_KEYS = frozenset({
    "id", "type", "kind", "text", "start", "end", "anchor", "box", "z",
    "style", "safe_zone", "opacity", "pin", "hidden",
})
_GRAPHIC_FX_KEYS = frozenset({
    "id", "type", "kind", "start", "end", "anchor", "box", "z", "color",
    "thickness", "opacity", "asset", "pin", "hidden",
})
# Optional story pins for text/graphic layers. ``anchor`` keeps its existing
# positional meaning (bottom-center); a pin value may also arrive under the
# plan's ``anchor`` spelling and is normalized to ``pin`` before storage.
STORY_PINS = ("source", "story_start", "story_end")
_CAPTIONS_KEYS = frozenset({"track_id", "style_id", "enabled"})
_AUDIO_KEYS = frozenset({
    "mode", "duck_db", "loudness", "music", "voice", "translate",
    "script_overrides", "mode_chosen",
})
TRANSLATE_MODES = ("literal", "smooth", "viral", "fun", "creative", "sad", "chill")
_LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})?$")
_TOP_KEYS = frozenset({
    "schema_version", "renderer_version", "id", "version", "parent", "hash",
    "created", "story_ref", "aspect", "clean", "reframe", "motion", "color",
    "graphics", "captions", "audio",
})


class EditError(ValueError):
    """Base error for an invalid Edit document."""

    status_code = 422


class EditInputError(EditError):
    """The request shape is malformed."""

    status_code = 400


class EditConflict(EditError):
    """A version conflict, stale story or immutable-write violation."""

    status_code = 409


class EditNotFound(EditError):
    """The requested Edit version does not exist."""

    status_code = 404


class EditCorrupt(EditError):
    """A stored Edit sidecar failed validation."""

    status_code = 500


# ---------------------------------------------------------------- primitives


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )


def content_hash(payload: dict) -> str:
    """Return the stable ``edh_`` content hash for an Edit payload."""
    return "edh_" + hashlib.sha256(
        canonical_json(payload).encode("utf-8"),
    ).hexdigest()[:32]


def edit_id(content_hash_value: str, version: int, parent: str | None) -> str:
    payload = {
        "hash": str(content_hash_value),
        "version": int(version),
        "parent": parent,
    }
    return "ed_" + hashlib.sha256(
        canonical_json(payload).encode("utf-8"),
    ).hexdigest()[:32]


def story_key(set_id: str, story_id: str, aspect: str) -> str:
    return f"{set_id}:{story_id}:{aspect}"


def clip_snapshot_hash(clips: Iterable[dict] | None) -> str:
    """Hash the story's clip windows like ``captions.clip_hash`` does."""
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
    return hashlib.sha1(
        canonical_json(rows).encode("utf-8"),
    ).hexdigest()[:16]


def _number(
    value: Any,
    label: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool):
        raise EditError(f"{label} must be a finite number.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise EditError(f"{label} must be a finite number.") from exc
    if not math.isfinite(number):
        raise EditError(f"{label} must be a finite number.")
    if minimum is not None and number < minimum - 1e-9:
        raise EditError(f"{label} must be at least {minimum:g}.")
    if maximum is not None and number > maximum + 1e-9:
        raise EditError(f"{label} must be at most {maximum:g}.")
    return number


def _integer(
    value: Any,
    label: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool):
        raise EditError(f"{label} must be an integer.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise EditError(f"{label} must be an integer.") from exc
    if not math.isfinite(number) or not number.is_integer():
        raise EditError(f"{label} must be an integer.")
    result = int(number)
    if minimum is not None and result < minimum:
        raise EditError(f"{label} must be at least {minimum}.")
    if maximum is not None and result > maximum:
        raise EditError(f"{label} must be at most {maximum}.")
    return result


def _strict_bool(value: Any, default: bool, label: str) -> bool:
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
    raise EditError(f"{label} must be a boolean.")


def _safe_id(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not _ID_RE.match(text):
        raise EditError(
            f"{label} must start with a letter and use letters, digits, _ or - "
            f"(max {MAX_ID} characters)."
        )
    return text


def _check_forbidden(*values: Any) -> None:
    for value in values:
        text = str(value or "")
        if text and _FORBIDDEN_RE.search(text):
            raise EditError(
                "Inpainting, watermark removal, stock B-roll, avatars and voice "
                "cloning are not supported."
            )


def _json_copy(value: Any, label: str, depth: int = 0) -> Any:
    """Copy a JSON value and reject non-finite numbers or deep nesting."""
    if depth > 12:
        raise EditError(f"{label} is nested too deeply.")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise EditError(f"{label} contains a non-finite number.")
        return value
    if isinstance(value, (list, tuple)):
        return [_json_copy(item, label, depth + 1) for item in value[:4000]]
    if isinstance(value, dict):
        return {
            str(key): _json_copy(item, label, depth + 1)
            for key, item in list(value.items())[:400]
        }
    raise EditError(f"{label} must contain JSON values only.")


def _unknown(value: dict, allowed: frozenset[str], label: str) -> None:
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        raise EditError(f"{label} has unknown keys: {', '.join(unknown)}.")


# ---------------------------------------------------------------- layer normalizers


def normalize_aspect(value: Any) -> str:
    aspect = str(value or "").strip().replace("x", ":").replace("/", ":")
    if aspect not in ASPECTS:
        raise EditError("aspect must be 9:16, 4:5, 1:1, 16:9 or 16:10.")
    return aspect


def normalize_story_ref(value: Any, *, require_hash: bool = True) -> dict:
    if not isinstance(value, dict):
        raise EditError("story_ref must be an object.")
    _unknown(value, _STORY_REF_KEYS, "story_ref")
    set_id = _safe_id(value.get("set_id"), "story_ref.set_id")
    story_id = _safe_id(value.get("story_id"), "story_ref.story_id")
    clip_hash = str(value.get("clip_hash") or "").strip().lower()
    if require_hash and not _HASH_RE.match(clip_hash):
        raise EditError("story_ref.clip_hash must be a clip snapshot hash.")
    title = str(value.get("title") or "").strip()[:240]
    duration = _number(
        value.get("duration") or 0.0, "story_ref.duration",
        minimum=0.0, maximum=36000.0,
    )
    clip_count = _integer(
        value.get("clip_count") or 0, "story_ref.clip_count",
        minimum=0, maximum=1000,
    )
    return {
        "set_id": set_id,
        "story_id": story_id,
        "clip_hash": clip_hash,
        "title": title,
        "duration": round(duration, 3),
        "clip_count": clip_count,
    }


def _normalize_box(value: Any, default_w: float, default_h: float, label: str) -> dict:
    if value is None:
        width, height = default_w, default_h
    elif isinstance(value, dict):
        unknown = set(value) - {"w", "h", "width", "height"}
        if unknown:
            raise EditError(f"{label} supports only w, h, width and height.")
        raw_w = value.get("w", value.get("width"))
        raw_h = value.get("h", value.get("height"))
        if "w" in value and "width" in value and value["w"] != value["width"]:
            raise EditError(f"{label} w and width disagree.")
        if "h" in value and "height" in value and value["h"] != value["height"]:
            raise EditError(f"{label} h and height disagree.")
        width = default_w if raw_w is None else raw_w
        height = default_h if raw_h is None else raw_h
    else:
        raise EditError(f"{label} must be an object with w and h.")
    width = _number(width, f"{label}.w", minimum=0.02, maximum=1.0)
    height = _number(height, f"{label}.h", minimum=0.02, maximum=1.0)
    return {"w": round(width, 4), "h": round(height, 4)}


def normalize_source_box(value: Any, label: str = "clean box") -> dict:
    if isinstance(value, (list, tuple)) and len(value) == 4:
        value = {"x": value[0], "y": value[1], "w": value[2], "h": value[3]}
    if not isinstance(value, dict):
        raise EditError(f"{label} must be an object with x, y, w and h.")
    unknown = set(value) - {"x", "y", "w", "h"}
    if unknown:
        raise EditError(f"{label} supports only x, y, w and h.")
    x = _number(value.get("x"), f"{label}.x", minimum=0.0, maximum=1.0)
    y = _number(value.get("y"), f"{label}.y", minimum=0.0, maximum=1.0)
    width = _number(value.get("w"), f"{label}.w", minimum=0.001, maximum=1.0)
    height = _number(value.get("h"), f"{label}.h", minimum=0.001, maximum=1.0)
    if x + width > 1.0 + 1e-6 or y + height > 1.0 + 1e-6:
        raise EditError(f"{label} must stay inside the source frame (0 to 1).")
    return {
        "x": round(x, 6),
        "y": round(y, 6),
        "w": round(min(width, 1.0 - x), 6),
        "h": round(min(height, 1.0 - y), 6),
    }


def _normalize_ranges(value: Any, label: str) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise EditError(f"{label} must be a list of time ranges.")
    if len(value) > 64:
        raise EditError(f"{label} supports at most 64 ranges.")
    ranges = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise EditError(f"{label}[{index}] must be an object.")
        unknown = set(raw) - {"start", "end"}
        if unknown:
            raise EditError(f"{label}[{index}] supports only start and end.")
        start = _number(
            raw.get("start"), f"{label}[{index}].start",
            minimum=0.0, maximum=MAX_TIMELINE,
        )
        end = _number(
            raw.get("end"), f"{label}[{index}].end",
            minimum=0.0, maximum=MAX_TIMELINE,
        )
        if end <= start:
            raise EditError(f"{label}[{index}] end must be later than start.")
        ranges.append({"start": round(start, 3), "end": round(end, 3)})
    ranges.sort(key=lambda item: (item["start"], item["end"]))
    merged: list[dict] = []
    for item in ranges:
        if merged and item["start"] <= merged[-1]["end"] + 1e-6:
            merged[-1]["end"] = max(merged[-1]["end"], item["end"])
        else:
            merged.append(dict(item))
    return merged


def normalize_clean(value: Any) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise EditError("clean must be a list.")
    if len(value) > MAX_CLEAN:
        raise EditError(f"An Edit supports at most {MAX_CLEAN} clean layers.")
    used: set[str] = set()
    layers: list[dict] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise EditError(f"clean[{index}] must be an object.")
        _unknown(raw, _CLEAN_KEYS, f"clean[{index}]")
        kind = str(raw.get("kind") or "").strip().lower().replace("-", "_")
        if kind not in CLEAN_KINDS:
            raise EditError(
                "clean kind must be one of: " + ", ".join(CLEAN_KINDS) + "."
            )
        layer_id = str(raw.get("id") or "").strip()
        if layer_id:
            layer_id = _safe_id(layer_id, f"clean[{index}].id")
        else:
            layer_id = f"cl{index + 1:02d}"
        if layer_id in used:
            raise EditError(f"Duplicate clean layer id: {layer_id}.")
        used.add(layer_id)
        label = " ".join(str(raw.get("label") or "").split())[:80]
        _check_forbidden(label)
        color = overlays.normalize_color(raw.get("color", "#000000"))
        opacity = _number(
            raw.get("opacity", 1.0), f"clean[{index}].opacity",
            minimum=0.0, maximum=1.0,
        )
        radius = _integer(
            raw.get("radius", 24), f"clean[{index}].radius",
            minimum=2, maximum=64,
        )
        z = _integer(raw.get("z", 0), f"clean[{index}].z", minimum=0, maximum=99)
        layer = {
            "id": layer_id,
            "kind": kind,
            "box": normalize_source_box(raw.get("box"), f"clean[{index}].box"),
            "ranges": _normalize_ranges(raw.get("ranges"), f"clean[{index}].ranges"),
            "z": z,
            "color": color,
            "opacity": round(opacity, 3),
            "radius": radius,
            "label": label,
        }
        tracklet_id = raw.get("tracklet_id")
        if tracklet_id is not None:
            layer["tracklet_id"] = _safe_id(
                tracklet_id, f"clean[{index}].tracklet_id",
            )
        tracklet_kind = str(raw.get("tracklet_kind") or "").strip().lower()
        tracklet_kind = tracklet_kind.replace("-", "_")
        if tracklet_kind:
            if tracklet_kind not in TRACKLET_KINDS:
                raise EditError(
                    f"clean[{index}].tracklet_kind must be one of: "
                    + ", ".join(TRACKLET_KINDS) + "."
                )
            layer["tracklet_kind"] = tracklet_kind
        layers.append(layer)
    layers.sort(key=lambda item: (item["z"], item["id"]))
    return layers


def normalize_reframe(value: Any) -> dict:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise EditError("reframe must be an object.")
    _unknown(value, _REFRAME_KEYS, "reframe")
    mode = str(value.get("mode") or "auto").strip().lower()
    if mode not in REFRAME_MODES:
        raise EditError("reframe.mode must be auto, center or manual.")
    cx = _number(value.get("cx", 0.5), "reframe.cx", minimum=0.0, maximum=1.0)
    cy = _number(value.get("cy", 0.5), "reframe.cy", minimum=0.0, maximum=1.0)
    zoom = _number(value.get("zoom", 1.0), "reframe.zoom", minimum=1.0, maximum=2.0)
    ref = value.get("crop_path_ref")
    crop_path_ref = None
    if ref is not None:
        crop_path_ref = str(ref).strip()
        if (
            not _SAFE_PATH_RE.match(crop_path_ref)
            or ".." in crop_path_ref
        ):
            raise EditError("reframe.crop_path_ref must be a safe analysis path.")
    overrides = value.get("overrides")
    if overrides is None:
        overrides = {}
    if not isinstance(overrides, dict):
        raise EditError("reframe.overrides must be an object.")
    _unknown(overrides, frozenset({"cx", "cy", "zoom"}), "reframe.overrides")
    clean_overrides: dict[str, float] = {}
    if "cx" in overrides:
        clean_overrides["cx"] = round(_number(
            overrides["cx"], "reframe.overrides.cx", minimum=0.0, maximum=1.0,
        ), 4)
    if "cy" in overrides:
        clean_overrides["cy"] = round(_number(
            overrides["cy"], "reframe.overrides.cy", minimum=0.0, maximum=1.0,
        ), 4)
    if "zoom" in overrides:
        clean_overrides["zoom"] = round(_number(
            overrides["zoom"], "reframe.overrides.zoom",
            minimum=1.0, maximum=2.0,
        ), 4)
    return {
        "mode": mode,
        "cx": round(cx, 4),
        "cy": round(cy, 4),
        "zoom": round(zoom, 4),
        "crop_path_ref": crop_path_ref,
        "overrides": clean_overrides,
    }


_MOTION_DEFAULTS = {
    "punch_in": {"amount": 0.08, "ramp": 0.40},
    "snap_zoom": {"amount": 0.12, "ramp": 0.20},
    "push": {"amount": 0.06, "ramp": 0.0},
    "shake": {"amount": 0.010, "ramp": 0.20},
}


def normalize_motion(value: Any) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise EditError("motion must be a list.")
    if len(value) > MAX_MOTION:
        raise EditError(f"An Edit supports at most {MAX_MOTION} motion layers.")
    used: set[str] = set()
    layers: list[dict] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise EditError(f"motion[{index}] must be an object.")
        _unknown(raw, _MOTION_KEYS, f"motion[{index}]")
        kind = str(raw.get("kind") or "").strip().lower().replace("-", "_")
        if kind not in MOTION_KINDS:
            raise EditError(
                "motion kind must be one of: " + ", ".join(MOTION_KINDS) + "."
            )
        layer_id = str(raw.get("id") or "").strip()
        if layer_id:
            layer_id = _safe_id(layer_id, f"motion[{index}].id")
        else:
            layer_id = f"mo{index + 1:02d}"
        if layer_id in used:
            raise EditError(f"Duplicate motion layer id: {layer_id}.")
        used.add(layer_id)
        start = _number(
            raw.get("start", 0.0), f"motion[{index}].start",
            minimum=0.0, maximum=MAX_TIMELINE,
        )
        end = _number(
            raw.get("end"), f"motion[{index}].end",
            minimum=0.0, maximum=MAX_TIMELINE,
        )
        if end <= start:
            raise EditError(f"motion[{index}] end must be later than start.")
        defaults = _MOTION_DEFAULTS[kind]
        amount_min = 0.001 if kind == "shake" else 0.01
        amount_max = 0.05 if kind == "shake" else 0.50
        amount = _number(
            raw.get("amount", defaults["amount"]),
            f"motion[{index}].amount",
            minimum=amount_min, maximum=amount_max,
        )
        ramp = _number(
            raw.get("ramp", defaults["ramp"]),
            f"motion[{index}].ramp",
            minimum=0.0, maximum=10.0,
        )
        seed = _integer(
            raw.get("seed", 0), f"motion[{index}].seed",
            minimum=0, maximum=2_147_483_647,
        )
        layer = {
            "id": layer_id,
            "kind": kind,
            "start": round(start, 3),
            "end": round(end, 3),
            "amount": round(amount, 4),
            "ramp": round(ramp, 3),
            "seed": seed,
        }
        # A trim hides a motion layer that falls outside the new range. The
        # key is only stored when set, so older Edits hash exactly as before.
        if raw.get("hidden"):
            layer["hidden"] = _strict_bool(
                raw.get("hidden"), False, f"motion[{index}].hidden",
            )
        layers.append(layer)
    layers.sort(key=lambda item: (item["start"], item["end"], item["id"]))
    return layers


def _normalize_lut(value: Any) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise EditError("color.lut must be an object.")
    _unknown(value, frozenset({"path", "hash"}), "color.lut")
    path = str(value.get("path") or "").strip()
    if (
        not path
        or len(path) > 240
        or "\x00" in path
        or any(ord(char) < 32 for char in path)
    ):
        raise EditError("color.lut.path is required.")
    file_hash = str(value.get("hash") or "").strip().lower()
    if not _HASH_RE.match(file_hash):
        raise EditError("color.lut.hash must be an asset content hash.")
    return {"path": path, "hash": file_hash}


def normalize_color(value: Any) -> dict:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise EditError("color must be an object.")
    _unknown(value, _COLOR_KEYS, "color")
    preset = str(value.get("preset") or "none").strip().lower().replace("-", "_")
    if preset not in COLOR_PRESETS:
        raise EditError(
            "color.preset must be one of: " + ", ".join(sorted(COLOR_PRESETS)) + "."
        )
    numbers = dict(COLOR_PRESETS[preset])
    for key, (low, high) in _PRESET_RANGES.items():
        if key in value:
            numbers[key] = _number(
                value[key], f"color.{key}", minimum=low, maximum=high,
            )
    result = {"preset": preset, "lut": _normalize_lut(value.get("lut"))}
    for key in _PRESET_RANGES:
        result[key] = round(numbers[key], 4)
    return result


def _graphic_id(raw: dict, index: int, prefix: str, used: set[str]) -> str:
    layer_id = str(raw.get("id") or "").strip()
    if layer_id:
        layer_id = _safe_id(layer_id, f"graphics[{index}].id")
    else:
        layer_id = f"{prefix}{index + 1:02d}"
    if layer_id in used:
        raise EditError(f"Duplicate graphics layer id: {layer_id}.")
    used.add(layer_id)
    return layer_id


def _graphic_pin(raw: dict, index: int) -> str | None:
    """Validate an optional story pin; ``anchor`` is accepted as an alias."""
    for key in ("pin", "anchor"):
        if key not in raw:
            continue
        value = str(raw.get(key) or "").strip().lower().replace("-", "_")
        if not value and key == "pin":
            continue
        if key == "anchor" and value not in STORY_PINS:
            # A positional anchor ("bottom-center") is not a story pin.
            continue
        if value not in STORY_PINS:
            raise EditError(
                f"graphics[{index}].{key} must be one of: "
                + ", ".join(STORY_PINS)
                + "."
            )
        return value
    return None


def _graphic_times(raw: dict, index: int) -> tuple[float, float]:
    start = _number(
        raw.get("start"), f"graphics[{index}].start",
        minimum=0.0, maximum=MAX_TIMELINE,
    )
    end = _number(
        raw.get("end"), f"graphics[{index}].end",
        minimum=0.0, maximum=MAX_TIMELINE,
    )
    if end <= start:
        raise EditError(f"graphics[{index}] end must be later than start.")
    return round(start, 3), round(end, 3)


def normalize_graphics(value: Any) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise EditError("graphics must be a list.")
    if len(value) > MAX_GRAPHICS:
        raise EditError(f"An Edit supports at most {MAX_GRAPHICS} graphics layers.")
    used: set[str] = set()
    layers: list[dict] = []
    text_index = 0
    fx_index = 0
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise EditError(f"graphics[{index}] must be an object.")
        kind = str(raw.get("kind") or "").strip().lower().replace("-", "_")
        raw_type = str(raw.get("type") or "").strip().lower()
        if raw_type in {"text", "graphic", "fx", ""}:
            is_text = raw_type in {"text", ""} and kind in TEXT_KINDS
        else:
            raise EditError(f"graphics[{index}].type must be text or fx.")
        if raw_type == "text" and kind not in TEXT_KINDS:
            raise EditError(f"graphics[{index}].type is text but kind is not a text kind.")
        if raw_type in {"graphic", "fx"} and kind not in FX_KINDS:
            raise EditError(f"graphics[{index}].type is fx but kind is not an fx kind.")
        if raw_type == "" and kind in FX_KINDS:
            is_text = False
        if not is_text and kind not in FX_KINDS:
            raise EditError(
                "graphics kind must be a text kind ("
                + ", ".join(TEXT_KINDS)
                + ") or an fx kind ("
                + ", ".join(FX_KINDS)
                + ")."
            )
        start, end = _graphic_times(raw, index)
        pin = _graphic_pin(raw, index)
        if is_text:
            _unknown(raw, _GRAPHIC_TEXT_KEYS, f"graphics[{index}]")
            layer_id = _graphic_id(raw, index, "tx", used)
            text = str(raw.get("text") or "")
            _check_forbidden(text)
            try:
                text = overlays.normalize_text(text)
            except ValueError as exc:
                raise EditError(f"graphics[{index}].text: {exc}") from exc
            if len(text) > MAX_TEXT_LENGTH:
                raise EditError(
                    f"graphics[{index}].text is longer than {MAX_TEXT_LENGTH} "
                    "characters."
                )
            if kind == "emphasis":
                default_box = (0.60, 0.12)
                default_anchor = "center"
            else:
                default_box = overlays.DEFAULT_BOX[kind]
                default_anchor = overlays.DEFAULT_ANCHOR[kind]
            anchor_raw = raw.get("anchor")
            if pin is not None and str(anchor_raw or "").strip().lower().replace(
                "-", "_",
            ) in STORY_PINS:
                anchor_raw = None
            try:
                anchor = overlays.normalize_anchor(
                    anchor_raw or default_anchor,
                )
                style = overlays.normalize_style(raw.get("style"))
            except ValueError as exc:
                raise EditError(f"graphics[{index}]: {exc}") from exc
            z = _integer(
                raw.get("z", 10 + text_index), f"graphics[{index}].z",
                minimum=0, maximum=99,
            )
            layer = {
                "id": layer_id,
                "type": "text",
                "kind": kind,
                "text": text,
                "start": start,
                "end": end,
                "anchor": anchor,
                "box": _normalize_box(
                    raw.get("box"), default_box[0], default_box[1],
                    f"graphics[{index}].box",
                ),
                "z": z,
                "style": style,
                "safe_zone": _strict_bool(
                    raw.get("safe_zone"), True, f"graphics[{index}].safe_zone",
                ),
                "opacity": round(_number(
                    raw.get("opacity", 1.0), f"graphics[{index}].opacity",
                    minimum=0.0, maximum=1.0,
                ), 3),
            }
            if pin is not None:
                layer["pin"] = pin
            if "hidden" in raw:
                layer["hidden"] = _strict_bool(
                    raw.get("hidden"), False, f"graphics[{index}].hidden",
                )
            layers.append(layer)
            text_index += 1
        else:
            _unknown(raw, _GRAPHIC_FX_KEYS, f"graphics[{index}]")
            layer_id = _graphic_id(raw, index, "fx", used)
            color = overlays.normalize_color(raw.get("color", "#ffffff"))
            thickness = _integer(
                raw.get("thickness", 6), f"graphics[{index}].thickness",
                minimum=1, maximum=32,
            )
            z = _integer(
                raw.get("z", 20 + fx_index), f"graphics[{index}].z",
                minimum=0, maximum=99,
            )
            asset = raw.get("asset")
            asset_out = None
            if asset is not None:
                if not isinstance(asset, dict):
                    raise EditError(f"graphics[{index}].asset must be an object.")
                _unknown(asset, frozenset({"id", "hash"}), f"graphics[{index}].asset")
                asset_id = _safe_id(asset.get("id"), f"graphics[{index}].asset.id")
                asset_hash = str(asset.get("hash") or "").strip().lower()
                if not _HASH_RE.match(asset_hash):
                    raise EditError(
                        f"graphics[{index}].asset.hash must be an asset content hash."
                    )
                asset_out = {"id": asset_id, "hash": asset_hash}
            if kind == "sticker" and asset_out is None:
                raise EditError(f"graphics[{index}] sticker needs an asset.")
            if kind != "sticker" and asset_out is not None:
                raise EditError(
                    f"graphics[{index}] asset is only valid for a sticker."
                )
            default_box = {
                "arrow": (0.30, 0.12),
                "circle": (0.30, 0.30),
                "underline": (0.40, 0.06),
                "progress_bar": (0.70, 0.02),
                "sticker": (0.24, 0.24),
            }[kind]
            anchor_raw = raw.get("anchor")
            if pin is not None and str(anchor_raw or "").strip().lower().replace(
                "-", "_",
            ) in STORY_PINS:
                anchor_raw = None
            layer = {
                "id": layer_id,
                "type": "fx",
                "kind": kind,
                "start": start,
                "end": end,
                "anchor": overlays.normalize_anchor(
                    anchor_raw or "center",
                ),
                "box": _normalize_box(
                    raw.get("box"), default_box[0], default_box[1],
                    f"graphics[{index}].box",
                ),
                "z": z,
                "color": color,
                "thickness": thickness,
                "opacity": round(_number(
                    raw.get("opacity", 1.0), f"graphics[{index}].opacity",
                    minimum=0.0, maximum=1.0,
                ), 3),
                "asset": asset_out,
            }
            if pin is not None:
                layer["pin"] = pin
            if "hidden" in raw:
                layer["hidden"] = _strict_bool(
                    raw.get("hidden"), False, f"graphics[{index}].hidden",
                )
            layers.append(layer)
            fx_index += 1
    layers.sort(key=lambda item: (item["z"], item["start"], item["end"], item["id"]))
    return layers


def normalize_captions(value: Any) -> dict:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise EditError("captions must be an object.")
    _unknown(value, _CAPTIONS_KEYS, "captions")
    track_id = value.get("track_id")
    if track_id is not None:
        track_id = str(track_id).strip()
        if not _ID_RE.match(track_id):
            raise EditError("captions.track_id is not a valid caption track id.")
    style_id = value.get("style_id")
    if style_id is not None:
        style_id = str(style_id).strip()
        if not _ID_RE.match(style_id):
            raise EditError("captions.style_id is not a valid caption style id.")
    return {
        "track_id": track_id or None,
        "style_id": style_id or None,
        "enabled": _strict_bool(value.get("enabled"), True, "captions.enabled"),
    }


def normalize_audio(value: Any) -> dict:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise EditError("audio must be an object.")
    _unknown(value, _AUDIO_KEYS, "audio")
    mode = str(value.get("mode") or "original").strip().lower().replace("-", "_")
    if mode not in AUDIO_MODES:
        raise EditError("audio.mode must be one of: " + ", ".join(AUDIO_MODES) + ".")
    duck_db = _number(
        value.get("duck_db", -12.0), "audio.duck_db",
        minimum=-60.0, maximum=0.0,
    )
    loudness = value.get("loudness")
    if loudness is None:
        loudness = {}
    if not isinstance(loudness, dict):
        raise EditError("audio.loudness must be an object.")
    _unknown(loudness, frozenset({"lufs", "true_peak"}), "audio.loudness")
    lufs = _number(
        loudness.get("lufs", -14.0), "audio.loudness.lufs",
        minimum=-30.0, maximum=-5.0,
    )
    true_peak = _number(
        loudness.get("true_peak", -1.5), "audio.loudness.true_peak",
        minimum=-9.0, maximum=0.0,
    )
    result = {
        "mode": mode,
        "duck_db": round(duck_db, 3),
        "loudness": {"lufs": round(lufs, 3), "true_peak": round(true_peak, 3)},
    }
    for key in ("music", "voice"):
        if key in value and value[key] is not None:
            raw = value[key]
            if not isinstance(raw, dict):
                raise EditError(f"audio.{key} must be an object.")
            if "file_hash" in raw:
                _check_hash(raw.get("file_hash"), f"audio.{key}.file_hash")
            result[key] = _json_copy(raw, f"audio.{key}")
    if value.get("translate") is not None:
        raw = value["translate"]
        if not isinstance(raw, dict):
            raise EditError("audio.translate must be an object.")
        _unknown(raw, frozenset({"source", "target", "mode"}), "audio.translate")
        source = str(raw.get("source") or "").strip()
        if source and not _LANGUAGE_RE.match(source):
            raise EditError(
                "audio.translate.source must be a language code such as en or zh."
            )
        target = str(raw.get("target") or "").strip()
        if not _LANGUAGE_RE.match(target):
            raise EditError(
                "audio.translate.target must be a language code such as zh or pt-BR."
            )
        mode = str(raw.get("mode") or "literal").strip().lower().replace("-", "_")
        if mode not in TRANSLATE_MODES:
            raise EditError(
                "audio.translate.mode must be one of: "
                + ", ".join(TRANSLATE_MODES) + "."
            )
        result["translate"] = {}
        if source:
            result["translate"]["source"] = source[:16]
        result["translate"]["target"] = target[:16]
        result["translate"]["mode"] = mode
    if value.get("script_overrides") is not None:
        raw = value["script_overrides"]
        if not isinstance(raw, dict):
            raise EditError("audio.script_overrides must be an object.")
        overrides: dict[str, str] = {}
        for key, text in raw.items():
            scene = str(key or "").strip()
            if not scene or len(scene) > 64:
                raise EditError(
                    "audio.script_overrides keys must be scene ids of 64 characters or fewer."
                )
            if not isinstance(text, str):
                raise EditError("audio.script_overrides values must be text.")
            line = text.strip()
            if not line:
                continue
            if len(line) > 600:
                raise EditError(
                    "audio.script_overrides lines must be 600 characters or fewer."
                )
            overrides[scene] = line
        if len(overrides) > 200:
            raise EditError("audio.script_overrides holds at most 200 lines.")
        if overrides:
            result["script_overrides"] = overrides
    # Stored only when set, so older Edits keep their hash. It tells a picked
    # "original" (keep the sound) from the default every Edit starts with.
    if value.get("mode_chosen") is not None:
        if not isinstance(value["mode_chosen"], bool):
            raise EditError("audio.mode_chosen must be true or false.")
        if value["mode_chosen"]:
            result["mode_chosen"] = True
    return result


def _check_hash(value: Any, label: str) -> str:
    text = str(value or "").strip().lower()
    if not _HASH_RE.match(text):
        raise EditError(f"{label} must be an asset content hash.")
    return text


# ---------------------------------------------------------------- document


def build_edit(
    *,
    story_ref: Any,
    aspect: Any,
    clean: Any = None,
    reframe: Any = None,
    motion: Any = None,
    color: Any = None,
    graphics: Any = None,
    captions: Any = None,
    audio: Any = None,
    version: int = 1,
    parent: str | None = None,
    created: float | None = None,
    renderer_version: int | None = None,
) -> dict:
    """Build one normalized, immutable Edit version."""
    version = _integer(version, "version", minimum=1, maximum=1_000_000)
    if renderer_version is None:
        renderer_version = RENDERER_VERSION
    renderer_version = _integer(
        renderer_version, "renderer_version", minimum=1, maximum=1000,
    )
    if parent is not None:
        parent = str(parent)
        if not _EDIT_ID_RE.match(parent):
            raise EditError("parent must be an Edit id.")
    content = {
        "schema_version": SCHEMA_VERSION,
        "renderer_version": renderer_version,
        "story_ref": normalize_story_ref(story_ref),
        "aspect": normalize_aspect(aspect),
        "clean": normalize_clean(clean),
        "reframe": normalize_reframe(reframe),
        "motion": normalize_motion(motion),
        "color": normalize_color(color),
        "graphics": normalize_graphics(graphics),
        "captions": normalize_captions(captions),
        "audio": normalize_audio(audio),
    }
    content_hash_value = content_hash(content)
    identifier = edit_id(content_hash_value, version, parent)
    stamp = time.time() if created is None else _number(
        created, "created", minimum=0.0,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "renderer_version": renderer_version,
        "id": identifier,
        "version": version,
        "parent": parent,
        "hash": content_hash_value,
        "created": round(stamp, 3),
        "story_ref": content["story_ref"],
        "aspect": content["aspect"],
        "clean": content["clean"],
        "reframe": content["reframe"],
        "motion": content["motion"],
        "color": content["color"],
        "graphics": content["graphics"],
        "captions": content["captions"],
        "audio": content["audio"],
    }


def normalize_edit(value: Any) -> dict:
    """Validate a stored Edit and verify its immutable hash and id."""
    if not isinstance(value, dict):
        raise EditCorrupt("Edit document must be an object.")
    try:
        _unknown(value, _TOP_KEYS, "edit")
    except EditError as exc:
        raise EditCorrupt(str(exc)) from exc
    for key in ("id", "hash", "version", "story_ref", "aspect"):
        if key not in value:
            raise EditCorrupt(f"Edit is missing {key}.")
    version = _integer(value.get("version"), "version", minimum=1, maximum=1_000_000)
    parent = value.get("parent")
    if parent is not None:
        parent = str(parent)
        if not _EDIT_ID_RE.match(parent):
            raise EditCorrupt("Edit parent id is invalid.")
    normalized = build_edit(
        story_ref=value.get("story_ref"),
        aspect=value.get("aspect"),
        clean=value.get("clean"),
        reframe=value.get("reframe"),
        motion=value.get("motion"),
        color=value.get("color"),
        graphics=value.get("graphics"),
        captions=value.get("captions"),
        audio=value.get("audio"),
        version=version,
        parent=parent,
        created=value.get("created"),
        renderer_version=value.get("renderer_version", RENDERER_VERSION),
    )
    stored_hash = str(value.get("hash") or "")
    stored_id = str(value.get("id") or "")
    if normalized["hash"] != stored_hash:
        raise EditCorrupt("Edit content does not match its hash.")
    if normalized["id"] != stored_id:
        raise EditCorrupt("Edit content does not match its id.")
    return normalized


def restored_edit(target: dict, *, parent_edit: dict, created: float | None = None) -> dict:
    """Create a new version carrying ``target``'s layers after ``parent_edit``."""
    if target.get("aspect") != parent_edit.get("aspect"):
        raise EditConflict("Edit aspects differ; restore inside one aspect.")
    if target.get("story_ref", {}).get("set_id") != parent_edit.get("story_ref", {}).get("set_id"):
        raise EditConflict("Edits belong to different clip sets.")
    if target.get("story_ref", {}).get("story_id") != parent_edit.get("story_ref", {}).get("story_id"):
        raise EditConflict("Edits belong to different stories.")
    return build_edit(
        story_ref=parent_edit["story_ref"],
        aspect=parent_edit["aspect"],
        clean=target["clean"],
        reframe=target["reframe"],
        motion=target["motion"],
        color=target["color"],
        graphics=target["graphics"],
        captions=target["captions"],
        audio=target["audio"],
        version=int(parent_edit["version"]) + 1,
        parent=str(parent_edit["id"]),
        created=created,
    )


# ---------------------------------------------------------------- storage


def edits_dir(job_dir: Path | str) -> Path:
    return Path(job_dir) / "edits"


def edit_path(job_dir: Path | str, edit_id_value: str) -> Path:
    edit_id_value = str(edit_id_value or "").strip()
    if not _EDIT_ID_RE.match(edit_id_value):
        raise EditNotFound("Edit not found.")
    return edits_dir(job_dir) / f"{edit_id_value}.json"


def save_edit(job_dir: Path | str, edit: dict) -> dict:
    """Write one immutable sidecar. Re-saving identical bytes is a no-op."""
    normalized = normalize_edit(edit)
    path = edit_path(job_dir, normalized["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = load_edit(job_dir, normalized["id"])
        if existing is not None and existing["hash"] == normalized["hash"]:
            return existing
        raise EditConflict("Edit version content is immutable.")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(normalized, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except OSError:
            pass
    return normalized


def load_edit(job_dir: Path | str, edit_id_value: str) -> dict | None:
    try:
        path = edit_path(job_dir, edit_id_value)
    except EditNotFound:
        return None
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EditCorrupt("Edit sidecar is unreadable.") from exc
    try:
        return normalize_edit(data)
    except EditError as exc:
        if isinstance(exc, EditCorrupt):
            raise
        raise EditCorrupt(str(exc)) from exc


def list_edits(job_dir: Path | str, *, key: str | None = None) -> list[dict]:
    """Return Edit summaries, newest first, optionally for one story key."""
    directory = edits_dir(job_dir)
    if not directory.is_dir():
        return []
    rows: list[dict] = []
    for path in sorted(directory.glob("ed_*.json")):
        try:
            edit = load_edit(job_dir, path.stem)
        except EditError:
            continue
        if edit is None:
            continue
        row_key = story_key(
            edit["story_ref"]["set_id"],
            edit["story_ref"]["story_id"],
            edit["aspect"],
        )
        if key is not None and row_key != key:
            continue
        rows.append({
            "id": edit["id"],
            "version": edit["version"],
            "parent": edit["parent"],
            "hash": edit["hash"],
            "created": edit["created"],
            "aspect": edit["aspect"],
            "story_ref": edit["story_ref"],
            "key": row_key,
            "layer_counts": layer_counts(edit),
        })
    rows.sort(
        key=lambda row: (
            float(row.get("created") or 0.0),
            int(row.get("version") or 0),
            str(row.get("id") or ""),
        ),
        reverse=True,
    )
    return rows


def layer_counts(edit: dict) -> dict:
    return {
        "clean": len(edit.get("clean") or []),
        "motion": len(edit.get("motion") or []),
        "graphics": len(edit.get("graphics") or []),
        "captions": 1 if (edit.get("captions") or {}).get("track_id") else 0,
    }


def version_chain(job_dir: Path | str, head_id: str) -> list[dict]:
    """Return the parent chain oldest-first, stopping safely on gaps/cycles."""
    chain: list[dict] = []
    seen: set[str] = set()
    current = load_edit(job_dir, head_id)
    while current is not None and current["id"] not in seen:
        seen.add(current["id"])
        chain.append(current)
        parent = current.get("parent")
        current = load_edit(job_dir, parent) if parent else None
    chain.reverse()
    return chain


def delete_version(job_dir: Path | str, edit_id_value: str) -> bool:
    try:
        path = edit_path(job_dir, edit_id_value)
    except EditNotFound:
        return False
    try:
        path.unlink()
        return True
    except OSError:
        return False


# ---------------------------------------------------------------- job pointer


def pointer_table(job: dict) -> dict:
    table = job.get("story_edits") if isinstance(job, dict) else None
    return table if isinstance(table, dict) else {}


def pointer_edit_id(job: dict, key: str) -> str | None:
    value = pointer_table(job).get(key)
    return str(value) if value else None


def set_pointer(job: dict, edit: dict) -> str:
    key = story_key(
        edit["story_ref"]["set_id"],
        edit["story_ref"]["story_id"],
        edit["aspect"],
    )
    table = job.get("story_edits")
    if not isinstance(table, dict):
        table = {}
    table[key] = edit["id"]
    job["story_edits"] = table
    return key


def clear_pointer(job: dict, key: str) -> bool:
    table = job.get("story_edits")
    if not isinstance(table, dict):
        return False
    if key not in table:
        return False
    table.pop(key, None)
    job["story_edits"] = table
    return True


# ---------------------------------------------------------------- history


def history_entry(edit: dict) -> dict:
    key = story_key(
        edit["story_ref"]["set_id"],
        edit["story_ref"]["story_id"],
        edit["aspect"],
    )
    return {
        "id": edit["id"],
        "type": "edit",
        "created": edit["created"],
        "status": "ok",
        "record_key": key,
        "aspect": edit["aspect"],
        "clip_hash": edit["story_ref"]["clip_hash"],
        "name": f"Edit v{edit['version']}",
        "duration": edit["story_ref"].get("duration") or None,
    }


def append_history(job_dir: Path | str, edit: dict) -> dict | None:
    """Best-effort history append; the sidecar stays the source of truth."""
    import history_store

    try:
        return history_store.append(
            job_dir,
            history_entry(edit),
            {"edit": edit},
        )
    except Exception:  # noqa: BLE001 - history must not break an edit write
        return None


# ---------------------------------------------------------------- view helpers


def public_edit(edit: dict) -> dict:
    """Return the stored payload plus derived pointers for API responses."""
    value = dict(edit)
    value["key"] = story_key(
        edit["story_ref"]["set_id"],
        edit["story_ref"]["story_id"],
        edit["aspect"],
    )
    value["layer_counts"] = layer_counts(edit)
    return value
