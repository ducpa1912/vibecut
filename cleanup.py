"""Deterministic Cleanup Kit for Flow 1.

Flow 1 cleans a finished video that already has baked-in text. The supported
operations are deliberately boring: crop away edge text, cover a region, or
blur a region. This kit itself does no inpainting, generative repair, temporal
reconstruction or logo repair, and nothing in VibeCut removes watermarks. AI
text fill is separate: see ``textfill/``, which Studio runs at render.

Everything here is pure data. Building a plan never invokes ffmpeg, never
writes to a job, and never calls the network. ``filter_chain`` is a declarative
description for a future renderer, not an executable command.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Iterable

import detect
import rights

SCHEMA_VERSION = 1
MAX_BOXES = 64
CROP_EDGE = 0.08
APPROXIMATE_CONFIDENCE = 0.2
EXPLICIT_CONFIDENCE = 1.0

SUPPORTED_METHODS = ("blur", "cover", "crop")
SUPPORTED_ASPECTS = ("9:16", "4:5", "1:1", "16:9", "16:10")
CLEAN_LAYER_KINDS = ("crop_guard", "blur", "plate", "mask", "delogo")
MAX_CLEAN_LAYERS = 1000
# Words edits.py refuses in a label; what a video shows can contain them.
_LABEL_FORBIDDEN_RE = re.compile(
    r"inpaint|generative|delogo|watermark|voice[\s_-]*clon|avatar|stock[\s_-]*b-?roll",
    re.IGNORECASE,
)
MAX_LAYER_RANGES = 64
RESIDUAL_TARGET_PCT = 0.5
# Hard server cap. The route rejects larger requests and the sampling helper
# clamps to the same number, so one call can never render an unbounded set.
RESIDUAL_MAX_FRAMES = 60
RESIDUAL_DEFAULT_FRAMES = 30
RESIDUAL_DEFAULT_FPS = 1.0
# One request owns at most this many seconds of render + OCR work. Each frame
# render is already bounded by render._run; this deadline stops a long source
# from holding the route open across many frames.
RESIDUAL_TIMEOUT_SECONDS = 240.0

# Keep these dimensions in sync with render.ASPECTS. Importing render would
# pull the ffmpeg renderer into a module that is meant to stay pure.
ASPECT_DIMENSIONS = {
    "9:16": (1080, 1920),
    "4:5": (1080, 1350),
    "1:1": (1080, 1080),
    "16:9": (1920, 1080),
}

LIMITATIONS = [
    "Plausible cleanup, not restoration. Removed, covered, blurred, or cropped pixels are not recovered.",
    "Remove interpolates nearby pixels; it is not generative repair and leaves no guarantee on complex backgrounds.",
    "No watermark removal and no guarantee that every text overlay is removed.",
    "No generative repair, face repair, logo repair, or temporal reconstruction.",
    "Scene OCR is advisory. When exact OCR boxes are unavailable, detection is approximate.",
    "A human must review every plan and every cleaned output before publishing.",
    "This prototype returns a plan only. It does not render, modify, or queue the source.",
]

_WATERMARK_RE = re.compile(r"water[\s_-]*mark", re.IGNORECASE)
_FORBIDDEN_METHOD_RE = re.compile(
    r"inpaint|generative|restore|remove|repair",
    re.IGNORECASE,
)
_APPROXIMATE_BOX = {
    "x": 0.08,
    "y": 0.70,
    "w": 0.84,
    "h": 0.20,
}


class CleanupError(ValueError):
    """Base class for deterministic cleanup failures."""


class CleanupValidationError(CleanupError):
    """The request is not a valid cleanup plan."""


class CleanupForbiddenError(CleanupValidationError):
    """The request asks for a feature outside Flow 1 scope."""


class CleanupStateError(CleanupError):
    """The selected source is not ready for this plan."""


# ---------------------------------------------------------------- validation


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CleanupValidationError(f"{label} must be a finite number.")
    number = float(value)
    if not math.isfinite(number):
        raise CleanupValidationError(f"{label} must be a finite number.")
    return number


def _confidence(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    number = float(value)
    if not math.isfinite(number):
        return default
    return min(1.0, max(0.0, number))


def normalize_method(value: Any) -> str:
    """Return a supported method or raise for unsupported/forbidden intent."""
    if not isinstance(value, str):
        raise CleanupValidationError("method must be crop, cover, or blur.")
    method = value.strip().lower()
    if method in SUPPORTED_METHODS:
        return method
    if _WATERMARK_RE.search(method):
        raise CleanupForbiddenError(
            "Watermark removal is not supported. Use crop, cover, or blur."
        )
    if _FORBIDDEN_METHOD_RE.search(method):
        raise CleanupForbiddenError(
            "Generative repair and object removal are not supported. "
            "Use crop, cover, or blur."
        )
    raise CleanupValidationError("method must be crop, cover, or blur.")


def normalize_aspect(value: Any) -> str:
    if not isinstance(value, str):
        raise CleanupValidationError(
            f"aspect must be one of: {', '.join(SUPPORTED_ASPECTS)}."
        )
    aspect = value.strip()
    if aspect not in SUPPORTED_ASPECTS:
        raise CleanupValidationError(
            f"aspect must be one of: {', '.join(SUPPORTED_ASPECTS)}."
        )
    return aspect


def require_attestation(value: Any) -> dict:
    """Require an explicit ownership/permission attestation."""
    accepted = value is True
    if isinstance(value, str):
        statement = value.strip()
        accepted = bool(statement) and statement.lower() not in {
            "0", "false", "no", "off",
        }
    if not accepted:
        raise CleanupValidationError(
            "Ownership attestation is required. Confirm that you own the "
            "video or have permission to edit it."
        )
    return {
        "required": True,
        "accepted": True,
        "statement": "User attested ownership or permission to edit.",
    }


def normalize_box(value: Any) -> dict:
    """Validate one normalized box with top-left origin."""
    if isinstance(value, (list, tuple)) and len(value) == 4:
        value = {"x": value[0], "y": value[1], "w": value[2], "h": value[3]}
    if not isinstance(value, dict):
        raise CleanupValidationError("Each box must be an object with x, y, w, h.")
    x = _number(value.get("x"), "box x")
    y = _number(value.get("y"), "box y")
    w = _number(value.get("w"), "box w")
    h = _number(value.get("h"), "box h")
    if w <= 0 or h <= 0:
        raise CleanupValidationError("Box w and h must be greater than zero.")
    if x < 0 or y < 0 or x > 1 or y > 1:
        raise CleanupValidationError("Box must start inside the frame.")
    tolerance = 1e-6
    if x + w > 1 + tolerance or y + h > 1 + tolerance:
        raise CleanupValidationError("Box must stay inside the frame (0 to 1).")
    label = str(value.get("label") or value.get("purpose") or value.get("kind") or "")
    label = " ".join(label.split())[:80]
    if _WATERMARK_RE.search(label):
        raise CleanupForbiddenError(
            "Boxes that target a watermark are not supported."
        )
    return {
        "x": round(x, 6),
        "y": round(y, 6),
        "w": round(w, 6),
        "h": round(h, 6),
        "label": label,
    }


def normalize_boxes(values: Any) -> list[dict]:
    if values is None:
        return []
    if not isinstance(values, (list, tuple)):
        raise CleanupValidationError("boxes must be a list.")
    if len(values) > MAX_BOXES:
        raise CleanupValidationError(f"At most {MAX_BOXES} boxes are allowed.")
    return [normalize_box(value) for value in values]


# ---------------------------------------------------------------- clean layers


_LAYER_LABELS = {
    ("subtitle", "delogo"): "Remove burned-in subtitle",
    ("subtitle", "plate"): "Burned-in subtitle in the caption zone",
    ("subtitle", "blur"): "Mid-frame burned-in caption",
    ("title", "delogo"): "Remove burned-in title",
    ("title", "mask"): "Burned-in title",
    ("lower_third", "delogo"): "Remove burned-in lower third",
    ("lower_third", "blur"): "Burned-in lower third",
    ("credit", "delogo"): "Remove burned-in credit",
    ("credit", "blur"): "Burned-in credit",
    ("handle_or_logo", "crop_guard"): "Own handle or logo, kept out of the crop",
    ("handle_or_logo", "blur"): "Own handle or logo",
}


def _padded_box(box: dict) -> dict:
    """Grow an OCR box to cover antialiasing and clipped glyph edges.

    OCR line boxes often stop at the glyph baseline or miss a descender. A
    small, bounded pad keeps the Clean layer over the whole visible word
    without covering much of the frame.
    """
    pad_x = min(0.012, max(0.004, float(box["w"]) * 0.03))
    pad_y = min(0.012, max(0.006, float(box["h"]) * 0.25))
    x = max(0.0, float(box["x"]) - pad_x)
    y = max(0.0, float(box["y"]) - pad_y)
    right = min(1.0, float(box["x"]) + float(box["w"]) + pad_x)
    bottom = min(1.0, float(box["y"]) + float(box["h"]) + pad_y)
    return {
        "x": round(x, 6),
        "y": round(y, 6),
        "w": round(right - x, 6),
        "h": round(bottom - y, 6),
    }


def _unique_layer_id(base: str, used: set[str]) -> str:
    candidate = base[:64]
    index = 2
    while candidate in used:
        suffix = f"_{index}"
        candidate = base[: 64 - len(suffix)] + suffix
        index += 1
    used.add(candidate)
    return candidate


def _tracklet_layer_id(tracklet: dict, used: set[str]) -> str:
    raw = str(tracklet.get("tracklet_id") or tracklet.get("id") or "trk").strip()
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_")[:56]
    if not safe or not safe[0].isalpha():
        safe = f"trk_{safe}" if safe else "trk"
    return _unique_layer_id(f"cl_{safe}", used)


def _separate_stacked_boxes(layers: list[dict]) -> None:
    """Meet stacked lines halfway, so padding does not lay one box over another.

    Boxes that overlap by more than their padding hold text on top of text, and
    stay as they are.
    """
    for index, first in enumerate(layers):
        for second in layers[index + 1:]:
            top, bottom = sorted((first, second), key=lambda layer: layer["box"]["y"])
            a, b = top["box"], bottom["box"]
            if min(a["x"] + a["w"], b["x"] + b["w"]) <= max(a["x"], b["x"]):
                continue
            overlap = a["y"] + a["h"] - b["y"]
            if overlap <= 0 or overlap > 0.5 * min(a["h"], b["h"]):
                continue
            if not any(
                min(x["end"], y["end"]) > max(x["start"], y["start"])
                for x in top["ranges"] for y in bottom["ranges"]
            ):
                continue
            middle = round(b["y"] + overlap / 2.0, 6)
            a["h"] = round(middle - a["y"], 6)
            b["h"] = round(b["y"] + b["h"] - middle, 6)
            b["y"] = middle


def _text_label(text: Any) -> str:
    """The words on screen name a layer, unless an Edit could not save them."""
    label = " ".join(str(text or "").split())[:80]
    if not label or _LABEL_FORBIDDEN_RE.search(label):
        return "On-screen text"
    return label


def _layer_ranges(tracklet: dict) -> list[dict]:
    ranges = []
    for item in tracklet.get("ranges") or []:
        if not isinstance(item, dict):
            continue
        try:
            start = float(item.get("start"))
            end = float(item.get("end"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(start) or not math.isfinite(end) or end <= start:
            continue
        ranges.append({"start": round(max(0.0, start), 3), "end": round(end, 3)})
    ranges.sort(key=lambda value: (value["start"], value["end"]))
    merged: list[dict] = []
    for item in ranges:
        if merged and item["start"] <= merged[-1]["end"] + 1e-6:
            merged[-1]["end"] = max(merged[-1]["end"], item["end"])
        else:
            merged.append(dict(item))
    return merged[:MAX_LAYER_RANGES]


def tracklet_clean_layers(
    tracklets: Iterable[dict] | None,
    *,
    attested: bool | None = None,
    selected: Iterable[str] | None = None,
    job: dict | None = None,
    settings: dict | None = None,
) -> dict:
    """Turn Check tracklets into Edit Clean layers, gated by detected kind.

    ``rights.clean_block_reason`` is the single gate. Watermarks, handles and
    logos need an own-footage attestation. Every other kind follows the stored
    ``rights.lock`` setting.

    Boxes are source-normalized and ranges are absolute source times, matching
    the Edit Clean coordinate contract. The returned dict carries ``layers``,
    ``refused`` and ``warnings`` for the UI.
    """
    items = []
    for item in tracklets or []:
        if not isinstance(item, dict):
            continue
        box = item.get("box")
        if not isinstance(box, dict):
            continue
        try:
            normalized = normalize_box(box)
        except CleanupValidationError:
            continue
        items.append({
            **item,
            "box": {key: normalized[key] for key in ("x", "y", "w", "h")},
            "ranges": _layer_ranges(item),
            "confidence": _confidence(item.get("confidence"), 0.0),
            "kind": str(item.get("kind") or "").strip().lower(),
        })
    wanted = None if selected is None else {str(value) for value in selected}
    effective = rights.job_attested(job) if job is not None else bool(attested)
    entries = detect.clean_prefill(
        items, attested=effective, job=job, settings=settings,
    )
    layers: list[dict] = []
    refused: list[dict] = []
    warnings: list[str] = []
    used: set[str] = set()
    z_cursor = 0
    samples = {str(item.get("id") or ""): item.get("text_sample") for item in items}
    for entry in entries:
        tracklet_id = entry["tracklet_id"]
        if wanted is not None and tracklet_id not in wanted:
            continue
        kind = entry["kind"]
        blocked = detect.cleanup_block_reason(
            kind, attested=effective, job=job, settings=settings,
        )
        action = entry.get("action")
        if blocked or action not in CLEAN_LAYER_KINDS:
            if blocked:
                reason = entry.get("reason") or detect.RIGHTS_MESSAGE
            else:
                reason = "This tracklet has no supported Clean action."
            refused.append({
                "tracklet_id": tracklet_id,
                "kind": kind,
                "action": action,
                "blocked": blocked or "unsupported",
                "reason": reason,
            })
            continue
        if len(layers) >= MAX_CLEAN_LAYERS:
            warnings.append(
                f"Only the first {MAX_CLEAN_LAYERS} Clean layers were built."
            )
            break
        ranges = _layer_ranges(entry)
        if not ranges:
            warnings.append(
                f"Tracklet {tracklet_id} has no usable time range and was skipped."
            )
            continue
        if entry.get("quality_warning"):
            warnings.append(
                f"Tracklet {tracklet_id} crosses the middle of the frame. "
                "A cover plate is added under the blur; review at 1×."
            )
        radius = 12
        base_layer = {
            "id": _tracklet_layer_id(entry, used),
            "kind": action,
            "box": _padded_box(entry["box"]),
            "ranges": ranges,
            "z": z_cursor,
            "color": "#000000",
            "opacity": 1.0,
            "radius": radius,
            # The words name the layer, in the list and on the timeline.
            "label": _text_label(samples.get(tracklet_id)),
            # Optional provenance. The layer's own ``kind`` is the cleanup
            # method, so the detected Check kind travels as ``tracklet_kind``.
            # Edit save re-checks it against the rights policy.
            "tracklet_id": tracklet_id,
            "tracklet_kind": kind,
        }
        text_key = _text_key(samples.get(tracklet_id))
        if text_key:
            base_layer["text_key"] = text_key
        layers.append(base_layer)
        z_cursor += 1
        if kind == "subtitle" and action == "blur" and entry.get("quality_warning"):
            # Mid-frame text has no clean plate already in the frame. Add an
            # opaque cover under the blur so no old glyph can survive.
            if len(layers) >= MAX_CLEAN_LAYERS:
                warnings.append(
                    f"Only the first {MAX_CLEAN_LAYERS} Clean layers were built."
                )
                continue
            companion = {
                **base_layer,
                "id": _tracklet_layer_id(
                    {"tracklet_id": f"{tracklet_id}_plate"}, used,
                ),
                "kind": "plate",
                "z": z_cursor,
                "label": "Mid-frame caption cover",
            }
            layers.append(companion)
            z_cursor += 1
    _separate_stacked_boxes(layers)
    return {
        "layers": layers,
        "refused": refused,
        "warnings": warnings,
        "attested": bool(effective),
        "tracklets": len(items),
    }


def _clean_region_key(layer: dict) -> tuple:
    """Identify one Clean region without its layer or tracklet id."""
    box = layer.get("box") if isinstance(layer.get("box"), dict) else {}
    try:
        coords = tuple(
            round(float(box.get(key) or 0.0), 6)
            for key in ("x", "y", "w", "h")
        )
    except (TypeError, ValueError):
        coords = (0.0, 0.0, 0.0, 0.0)
    return (
        str(layer.get("kind") or "").strip().lower(),
        coords,
        tuple((item["start"], item["end"]) for item in _layer_ranges(layer)),
    )


def _text_key(text: Any) -> str:
    """A short hash of what a scan read, comparable across scans."""
    words = re.sub(r"\s+", " ", str(text or "")).strip().casefold()
    return hashlib.sha1(words.encode("utf-8")).hexdigest()[:12] if words else ""


def _same_scan_text(first: dict, second: dict) -> bool:
    """The same text in the same area. Overlapping different text is allowed.

    Areas must match, and then the words match or the times overlap. Ids alone
    are not trusted: older reports numbered them, so an id can name other text.
    """
    box_a, box_b = first.get("box"), second.get("box")
    if not isinstance(box_a, dict) or not isinstance(box_b, dict):
        return False
    try:
        if detect._similar(box_a, box_b) < 0.3:
            return False
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return False
    key_a, key_b = first.get("text_key"), second.get("text_key")
    if key_a and key_b and key_a == key_b:
        return True
    ranges_a, ranges_b = _layer_ranges(first), _layer_ranges(second)
    if not ranges_a or not ranges_b:
        return True
    # Lines that follow each other can touch; only a real overlap is one text.
    return any(
        min(a["end"], b["end"]) - max(a["start"], b["start"]) > 0.05
        for a in ranges_a for b in ranges_b
    )


def _joined_ranges(first: list[dict], second: list[dict]) -> list[dict]:
    merged: list[dict] = []
    for item in sorted([*first, *second], key=lambda value: value["start"]):
        if merged and item["start"] <= merged[-1]["end"]:
            merged[-1]["end"] = max(merged[-1]["end"], item["end"])
        else:
            merged.append({"start": item["start"], "end": item["end"]})
    return merged


def merge_auto_clean_layers(
    existing: Iterable[dict] | None,
    generated: Iterable[dict] | None,
) -> dict:
    """Return generated Clean layers that an Edit does not already contain.

    Existing layers are not changed here. When new times belong to a scan
    layer already in the Edit, ``updated`` carries its id and joined ranges for
    the frontend to apply. Drawn boxes have no tracklet and are never matched,
    except an identical region. A generated id that collides with an existing
    id gets a numeric suffix, so the frontend can still save the merged Edit.
    """
    current = [item for item in existing or [] if isinstance(item, dict)]
    scanned = [dict(item) for item in current if str(item.get("tracklet_id") or "").strip()]
    regions = {_clean_region_key(item) for item in current}
    used = {
        str(item.get("id") or "")
        for item in current
        if str(item.get("id") or "")
    }
    layers: list[dict] = []
    skipped: list[dict] = []
    updated: dict[str, list[dict]] = {}
    for item in generated or []:
        if not isinstance(item, dict):
            continue
        tracklet_id = str(item.get("tracklet_id") or "").strip()
        kind = str(item.get("tracklet_kind") or item.get("kind") or "").strip().lower()
        region = _clean_region_key(item)
        match = next((row for row in [*scanned, *layers] if _same_scan_text(row, item)), None) if tracklet_id else None
        if match is not None:
            regions.add(region)
            have = _layer_ranges(match)
            incoming = _layer_ranges(item)
            if have and incoming:
                joined = _joined_ranges(have, incoming)
                if joined != have:
                    match["ranges"] = joined
                    if match in scanned:
                        updated[str(match.get("id") or "")] = joined
            skipped.append({
                "tracklet_id": tracklet_id,
                "kind": kind,
                "reason": "This text already has a Clean layer in the Edit.",
            })
            continue
        if region in regions:
            skipped.append({
                "tracklet_id": tracklet_id or None,
                "kind": kind,
                "reason": "An identical Clean region is already in the Edit.",
            })
            continue
        layer = dict(item)
        raw_id = str(layer.get("id") or "").strip()
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", raw_id).strip("_")[:64]
        if not safe or not safe[0].isalpha():
            safe = f"cl_{safe}" if safe else "cl_auto"
        layer["id"] = _unique_layer_id(safe, used)
        layers.append(layer)
        regions.add(region)
    return {
        "layers": layers,
        "skipped": skipped,
        "updated": [{"id": key, "ranges": value} for key, value in updated.items()],
    }


def normalize_range(value: Any, span: dict | None) -> dict:
    """Validate an absolute source-time range against the selected span."""
    source_start = _number((span or {}).get("start", 0.0), "source start")
    source_end = _number((span or {}).get("end", 0.0), "source end")
    if source_end <= source_start:
        raise CleanupStateError("Selected source has no usable time range.")
    if value is None:
        return {
            "start": round(source_start, 3),
            "end": round(source_end, 3),
        }
    if isinstance(value, (list, tuple)) and len(value) == 2:
        value = {"start": value[0], "end": value[1]}
    if not isinstance(value, dict):
        raise CleanupValidationError("range must be an object with start and end.")
    start = _number(value.get("start"), "range start")
    end = _number(value.get("end"), "range end")
    if start < 0 or end <= start:
        raise CleanupValidationError("range needs 0 <= start < end.")
    if start < source_start - 1e-6 or end > source_end + 1e-6:
        raise CleanupValidationError(
            "range must stay inside the selected source span "
            f"({source_start:.3f} to {source_end:.3f})."
        )
    return {"start": round(start, 3), "end": round(end, 3)}


# ---------------------------------------------------------------- detection


def _relevant_scenes(
    scenes: Iterable[dict] | None,
    clips: Iterable[dict] | None,
    time_range: dict,
) -> list[dict]:
    scene_ids = set()
    for clip in clips or []:
        if not isinstance(clip, dict):
            continue
        try:
            if clip.get("scene") is not None:
                scene_ids.add(int(clip["scene"]))
        except (TypeError, ValueError):
            continue
    result = []
    for scene in scenes or []:
        if not isinstance(scene, dict):
            continue
        if scene_ids:
            try:
                if int(scene.get("id")) not in scene_ids:
                    continue
            except (TypeError, ValueError):
                continue
        try:
            start = float(scene.get("start") or 0.0)
            end = float(scene.get("end", start + float(scene.get("dur") or 0.0)))
        except (TypeError, ValueError):
            continue
        if end <= time_range["start"] or start >= time_range["end"]:
            continue
        result.append(scene)
    return result


def _ocr_boxes(scene: dict) -> tuple[list[dict], bool]:
    """Return (exact geometry boxes, whether OCR text was present)."""
    boxes: list[dict] = []
    for field in ("ocr_boxes", "text_boxes", "ocr_regions", "text_regions", "ocr_lines"):
        items = scene.get(field)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            raw = item.get("box") if isinstance(item.get("box"), dict) else item
            try:
                box = normalize_box(raw)
            except CleanupValidationError:
                continue
            box["source"] = "ocr"
            box["confidence"] = round(
                _confidence(item.get("confidence", raw.get("confidence")), 0.55),
                3,
            )
            if scene.get("id") is not None:
                box["scene"] = scene.get("id")
            boxes.append(box)
    text_present = bool(str(scene.get("ocr") or "").strip()) or bool(boxes)
    return boxes, text_present


def detect_boxes(
    scenes: Iterable[dict] | None,
    explicit: list[dict] | None,
    *,
    clips: Iterable[dict] | None = None,
    time_range: dict | None = None,
) -> dict:
    """Resolve explicit boxes, exact OCR geometry, or an approximate region.

    Explicit boxes always win. Scene OCR is used only when it carries usable
    geometry. If OCR text exists without geometry, the result is marked
    ``approximate`` so callers can warn and require review.
    """
    time_range = time_range or {"start": 0.0, "end": 0.0}
    if explicit:
        boxes = [
            {
                **box,
                "source": "explicit",
                "confidence": EXPLICIT_CONFIDENCE,
            }
            for box in explicit
        ]
        return {
            "boxes": boxes,
            "source": "explicit",
            "approximate": False,
            "confidence": EXPLICIT_CONFIDENCE,
            "ocr_scene_ids": [],
        }

    relevant = _relevant_scenes(scenes, clips, time_range)
    geometry: list[dict] = []
    ocr_scene_ids: list[int] = []
    for scene in relevant:
        found, has_text = _ocr_boxes(scene)
        if found:
            geometry.extend(found)
        if has_text:
            try:
                ocr_scene_ids.append(int(scene.get("id")))
            except (TypeError, ValueError):
                continue
    if geometry:
        confidence = sum(box["confidence"] for box in geometry) / len(geometry)
        return {
            "boxes": geometry[:MAX_BOXES],
            "source": "ocr",
            "approximate": False,
            "confidence": round(min(1.0, max(0.0, confidence)), 3),
            "ocr_scene_ids": sorted(set(ocr_scene_ids)),
        }
    if ocr_scene_ids:
        return {
            "boxes": [{
                "x": _APPROXIMATE_BOX["x"],
                "y": _APPROXIMATE_BOX["y"],
                "w": _APPROXIMATE_BOX["w"],
                "h": _APPROXIMATE_BOX["h"],
                "label": "approximate on-screen text",
                "source": "approximate",
                "confidence": APPROXIMATE_CONFIDENCE,
            }],
            "source": "approximate",
            "approximate": True,
            "confidence": APPROXIMATE_CONFIDENCE,
            "ocr_scene_ids": sorted(set(ocr_scene_ids)),
        }
    return {
        "boxes": [],
        "source": "none",
        "approximate": False,
        "confidence": 0.0,
        "ocr_scene_ids": [],
    }


def scene_faces(scenes: Iterable[dict] | None) -> list[dict]:
    faces = []
    for scene in scenes or []:
        if not isinstance(scene, dict):
            continue
        for face in scene.get("faces") or []:
            if not isinstance(face, dict):
                continue
            try:
                box = normalize_box(face)
            except CleanupValidationError:
                continue
            box["confidence"] = round(
                _confidence(face.get("confidence"), 0.0),
                3,
            )
            if scene.get("id") is not None:
                box["scene"] = scene.get("id")
            faces.append(box)
    return faces


# ---------------------------------------------------------------- geometry


def _area(box: dict) -> float:
    return max(0.0, float(box["w"])) * max(0.0, float(box["h"]))


def _intersection(left: dict, right: dict) -> float:
    x0 = max(float(left["x"]), float(right["x"]))
    y0 = max(float(left["y"]), float(right["y"]))
    x1 = min(float(left["x"]) + float(left["w"]), float(right["x"]) + float(right["w"]))
    y1 = min(float(left["y"]) + float(left["h"]), float(right["y"]) + float(right["h"]))
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def _overlap_ratio(box: dict, other: dict) -> float:
    area = _area(box)
    if area <= 0:
        return 0.0
    return _intersection(box, other) / area


def _union(boxes: list[dict]) -> dict | None:
    if not boxes:
        return None
    x0 = min(float(box["x"]) for box in boxes)
    y0 = min(float(box["y"]) for box in boxes)
    x1 = max(float(box["x"]) + float(box["w"]) for box in boxes)
    y1 = max(float(box["y"]) + float(box["h"]) for box in boxes)
    return {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}


def _even(value: float, minimum: int = 2) -> int:
    return max(minimum, int(round(value / 2.0)) * 2)


def _dimensions(source: dict, aspect: str) -> tuple[int, int, str]:
    try:
        width = int(source.get("width") or 0)
        height = int(source.get("height") or 0)
    except (TypeError, ValueError):
        width = height = 0
    if width > 1 and height > 1:
        return width, height, "source"
    width, height = ASPECT_DIMENSIONS[aspect]
    return width, height, "nominal"


def _fit_rect(
    safe: dict,
    *,
    width: int,
    height: int,
    aspect: str,
) -> tuple[dict, dict]:
    """Fit the target aspect inside a normalized safe rect, in pixels."""
    target_ar = ASPECT_DIMENSIONS[aspect][0] / ASPECT_DIMENSIONS[aspect][1]
    safe_x = safe["x"] * width
    safe_y = safe["y"] * height
    safe_w = safe["w"] * width
    safe_h = safe["h"] * height
    if safe_w / safe_h > target_ar:
        crop_h = safe_h
        crop_w = safe_h * target_ar
    else:
        crop_w = safe_w
        crop_h = safe_w / target_ar
    crop_w_i = _even(crop_w)
    crop_h_i = _even(crop_h)
    crop_w_i = min(crop_w_i, _even(width))
    crop_h_i = min(crop_h_i, _even(height))
    x_i = _even(safe_x + (safe_w - crop_w_i) / 2.0, 0)
    y_i = _even(safe_y + (safe_h - crop_h_i) / 2.0, 0)
    x_i = max(0, min(width - crop_w_i, x_i))
    y_i = max(0, min(height - crop_h_i, y_i))
    rect = {"x": x_i, "y": y_i, "w": crop_w_i, "h": crop_h_i}
    normalized = {
        "x": round(x_i / width, 6),
        "y": round(y_i / height, 6),
        "w": round(crop_w_i / width, 6),
        "h": round(crop_h_i / height, 6),
    }
    return rect, normalized


def _crop_region(
    boxes: list[dict],
    *,
    width: int,
    height: int,
    aspect: str,
) -> tuple[dict, dict, bool, bool]:
    """Choose a deterministic crop, trimming edge text where possible."""
    safe = {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}
    edge_trimmed = False
    union = _union(boxes)
    if union is not None:
        x0, y0 = safe["x"], safe["y"]
        x1, y1 = safe["x"] + safe["w"], safe["y"] + safe["h"]
        if union["y"] <= CROP_EDGE:
            y0 = max(y0, union["y"] + union["h"])
            edge_trimmed = True
        if union["y"] + union["h"] >= 1.0 - CROP_EDGE:
            y1 = min(y1, union["y"])
            edge_trimmed = True
        if union["x"] <= CROP_EDGE:
            x0 = max(x0, union["x"] + union["w"])
            edge_trimmed = True
        if union["x"] + union["w"] >= 1.0 - CROP_EDGE:
            x1 = min(x1, union["x"])
            edge_trimmed = True
        if x1 - x0 >= 0.2 and y1 - y0 >= 0.2:
            safe = {
                "x": x0,
                "y": y0,
                "w": x1 - x0,
                "h": y1 - y0,
            }
        else:
            edge_trimmed = False

    rect, normalized = _fit_rect(
        safe, width=width, height=height, aspect=aspect,
    )
    trimmed = edge_trimmed and safe != {
        "x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0,
    }
    return rect, normalized, trimmed, bool(boxes and not trimmed)


def _box_rect(box: dict, width: int, height: int) -> dict:
    x = max(0, min(width - 1, int(round(box["x"] * width))))
    y = max(0, min(height - 1, int(round(box["y"] * height))))
    w = max(1, min(width - x, int(round(box["w"] * width))))
    h = max(1, min(height - y, int(round(box["h"] * height))))
    return {"x": x, "y": y, "w": w, "h": h}


def _crop_face_warning(crop: dict, faces: list[dict]) -> bool:
    for face in faces:
        overlap = _intersection(crop, face)
        area = _area(face)
        if overlap > 0 and (area <= 0 or overlap / area < 0.995):
            return True
    return False


def _region_face_warning(boxes: list[dict], faces: list[dict]) -> bool:
    for box in boxes:
        for face in faces:
            overlap = _intersection(box, face)
            if _area(face) and overlap / _area(face) >= 0.10:
                return True
            if (
                face["x"] + face["w"] / 2.0 >= box["x"]
                and face["x"] + face["w"] / 2.0 <= box["x"] + box["w"]
                and face["y"] + face["h"] / 2.0 >= box["y"]
                and face["y"] + face["h"] / 2.0 <= box["y"] + box["h"]
            ):
                return True
    return False


# ---------------------------------------------------------------- plan


def build_plan(
    *,
    job_id: str,
    source: dict,
    aspect: Any,
    method: Any,
    boxes: Any = None,
    time_range: Any = None,
    attestation: Any = None,
    scenes: Iterable[dict] | None = None,
    analysis_ready: bool = True,
) -> dict:
    """Build a deterministic cleanup plan. No side effects, no media access."""
    aspect = normalize_aspect(aspect)
    method = normalize_method(method)
    attestation = require_attestation(attestation)
    explicit = normalize_boxes(boxes)
    span = source.get("span") or {
        "start": 0.0,
        "end": float(source.get("duration") or 0.0),
    }
    resolved_range = normalize_range(time_range, span)
    selected_scenes = _relevant_scenes(scenes, source.get("clips"), resolved_range)
    detection = detect_boxes(
        selected_scenes,
        explicit,
        clips=source.get("clips"),
        time_range=resolved_range,
    )
    detected = detection["boxes"]
    if method in {"cover", "blur"} and not detected:
        if not analysis_ready:
            raise CleanupStateError(
                "Analysis is not ready. Pass manual boxes or wait for analysis."
            )
        raise CleanupValidationError(
            "No text boxes were supplied and no scene OCR was available. "
            "Pass manual boxes for cover or blur."
        )

    width, height, dimensions_source = _dimensions(source, aspect)
    faces = scene_faces(selected_scenes)
    warnings: list[str] = []
    if detection["source"] == "approximate":
        warnings.append(
            "No explicit boxes were supplied. OCR text was found, but exact "
            "text boxes are unavailable; detection is approximate."
        )
    elif detection["source"] == "ocr":
        warnings.append(
            "No explicit boxes were supplied; using text boxes retained by "
            "scene OCR."
        )
    elif detection["source"] == "none":
        warnings.append(
            "No text regions were detected in the selected range."
        )

    crop_rect = None
    text_remaining = 0
    face_overlap = False
    filter_chain: list[dict]
    if method == "crop":
        crop_rect, crop_norm, edge_trimmed, fallback = _crop_region(
            detected, width=width, height=height, aspect=aspect,
        )
        text_remaining = sum(
            1 for box in detected if _overlap_ratio(box, crop_norm) > 0.02
        )
        face_overlap = _crop_face_warning(crop_norm, faces)
        target_w, target_h = ASPECT_DIMENSIONS[aspect]
        filter_chain = [
            {
                "filter": "crop",
                "rect": crop_rect,
                "target_aspect": aspect,
                "description": (
                    f"crop={crop_rect['w']}:{crop_rect['h']}:"
                    f"{crop_rect['x']}:{crop_rect['y']}"
                ),
            },
            {
                "filter": "scale",
                "width": target_w,
                "height": target_h,
                "description": f"scale={target_w}:{target_h}",
            },
        ]
        if edge_trimmed:
            warnings.append(
                "Crop trims text that touches the frame edge and reframes to "
                "the target aspect."
            )
        if fallback:
            warnings.append(
                "Text does not sit on a frame edge, so crop cannot remove all "
                "of it. Use cover or blur, or supply tighter boxes."
            )
        if text_remaining:
            warnings.append(
                f"Crop leaves {text_remaining} detected text "
                f"box{'es' if text_remaining != 1 else ''} inside the frame. "
                "Review or use cover/blur."
            )
        if not detected:
            warnings.append(
                "Crop only reframes; no text region was detected."
            )
    else:
        face_overlap = _region_face_warning(detected, faces)
        filter_chain = []
        for box in detected:
            rect = _box_rect(box, width, height)
            if method == "cover":
                filter_chain.append({
                    "filter": "drawbox",
                    "box": {key: box[key] for key in ("x", "y", "w", "h")},
                    "rect": rect,
                    "color": "black",
                    "opacity": 1.0,
                    "thickness": "fill",
                    "description": (
                        f"drawbox=x={rect['x']}:y={rect['y']}:"
                        f"w={rect['w']}:h={rect['h']}:color=black@1.0:t=fill"
                    ),
                })
            else:
                filter_chain.append({
                    "filter": "region_blur",
                    "box": {key: box[key] for key in ("x", "y", "w", "h")},
                    "rect": rect,
                    "radius": 24,
                    "description": (
                        "boxblur=24:2 on an isolated region, then overlay the "
                        "blurred region"
                    ),
                })

    if face_overlap:
        warnings.append(
            "A cleanup region overlaps a detected face. Review framing and "
            "consent before publishing."
        )
    warnings.append("Plan only: no media was modified, rendered, or queued.")

    if detection["source"] == "approximate":
        residual_risk = "high"
    elif face_overlap or text_remaining:
        residual_risk = "high"
    elif detection["source"] == "ocr":
        residual_risk = "medium"
    elif detection["source"] == "none":
        residual_risk = "high"
    else:
        residual_risk = "low"

    quality_report = {
        "detection_confidence": detection["confidence"],
        "method": method,
        "residual_risk": residual_risk,
        "face_overlap_warning": face_overlap,
        "review_required": True,
        "limitations": list(LIMITATIONS),
    }

    source_out = {
        "type": str(source.get("type") or "job"),
        "job_id": str(job_id),
        "artifact_id": source.get("artifact_id"),
        "story_id": source.get("story_id"),
        "clip_set_id": source.get("clip_set_id"),
        "media": source.get("media"),
        "aspect": source.get("aspect"),
        "width": width,
        "height": height,
        "dimensions_source": dimensions_source,
        "duration": round(resolved_range["end"] - resolved_range["start"], 3),
        "range": resolved_range,
        "clips": list(source.get("clips") or []),
    }
    if dimensions_source != "source":
        warnings.append(
            "Source dimensions were unavailable; cleanup geometry uses "
            "nominal target dimensions."
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "cleanup_plan",
        "job_id": str(job_id),
        "source": source_out,
        "aspect": aspect,
        "method": method,
        "boxes": detected,
        "detection": {
            "source": detection["source"],
            "approximate": detection["approximate"],
            "confidence": detection["confidence"],
            "ocr_scene_ids": detection["ocr_scene_ids"],
        },
        "crop": crop_rect,
        "filter_chain": filter_chain,
        "quality_report": quality_report,
        "warnings": warnings,
        "limitations": list(LIMITATIONS),
        "attestation": attestation,
    }


# ---------------------------------------------------------------- residual OCR


def segment_at(compiled: dict, t: float) -> dict | None:
    """Return the compiled segment containing one output time."""
    segments = [item for item in compiled.get("segments") or [] if isinstance(item, dict)]
    if not segments:
        return None
    for segment in segments:
        start = float(segment.get("out_start") or 0.0)
        end = float(segment.get("out_end") or start)
        if start <= t < end:
            return segment
    return segments[-1] if t >= float(segments[-1].get("out_start") or 0.0) else segments[0]


def source_time_at(compiled: dict, t: float) -> float | None:
    segment = segment_at(compiled, t)
    if segment is None:
        return None
    return float(segment.get("start") or 0.0) + (
        float(t) - float(segment.get("out_start") or 0.0)
    )


def residual_times(
    compiled: dict,
    *,
    start: float | None = None,
    end: float | None = None,
    fps: float = RESIDUAL_DEFAULT_FPS,
    max_frames: int = RESIDUAL_MAX_FRAMES,
) -> list[float]:
    """Sample output times across a compiled story for the residual pass."""
    segments = [item for item in compiled.get("segments") or [] if isinstance(item, dict)]
    total = float(segments[-1].get("out_end") or 0.0) if segments else 0.0
    if total <= 0:
        raise CleanupStateError("The story has no renderable duration.")
    low = 0.0 if start is None else float(start)
    high = total if end is None else float(end)
    if not math.isfinite(low) or not math.isfinite(high):
        raise CleanupValidationError("start and end must be finite numbers.")
    low = max(0.0, min(total, low))
    high = max(0.0, min(total, high))
    if high <= low:
        raise CleanupValidationError("end must be later than start.")
    rate = float(fps)
    if not math.isfinite(rate) or rate <= 0:
        raise CleanupValidationError("fps must be a positive number.")
    limit = max(1, min(1000, int(max_frames)))
    count = max(1, min(limit, int(math.floor((high - low) * rate))))
    step = (high - low) / count
    return [round(low + index * step, 3) for index in range(count)]


def _map_region(
    box: dict,
    crop: dict,
    *,
    source_width: int,
    source_height: int,
    out_width: int,
    out_height: int,
) -> dict | None:
    """Map a source-normalized Clean box into output-normalized coordinates."""
    try:
        crop_x = float(crop["x"])
        crop_y = float(crop["y"])
        crop_w = float(crop["w"])
        crop_h = float(crop["h"])
    except (KeyError, TypeError, ValueError):
        return None
    if crop_w <= 0 or crop_h <= 0 or source_width <= 0 or source_height <= 0:
        return None
    left = (float(box["x"]) * source_width - crop_x) / crop_w
    top = (float(box["y"]) * source_height - crop_y) / crop_h
    right = ((float(box["x"]) + float(box["w"])) * source_width - crop_x) / crop_w
    bottom = ((float(box["y"]) + float(box["h"])) * source_height - crop_y) / crop_h
    left = max(0.0, min(1.0, left))
    top = max(0.0, min(1.0, top))
    right = max(0.0, min(1.0, right))
    bottom = max(0.0, min(1.0, bottom))
    if right - left <= 1e-4 or bottom - top <= 1e-4:
        return None
    return {
        "x": round(left, 6),
        "y": round(top, 6),
        "w": round(right - left, 6),
        "h": round(bottom - top, 6),
    }


def _rect_overlap(first: dict, second: dict) -> float:
    left = max(float(first["x"]), float(second["x"]))
    top = max(float(first["y"]), float(second["y"]))
    right = min(float(first["x"]) + float(first["w"]), float(second["x"]) + float(second["w"]))
    bottom = min(float(first["y"]) + float(first["h"]), float(second["y"]) + float(second["h"]))
    return max(0.0, right - left) * max(0.0, bottom - top)


def _center_inside(box: dict, region: dict) -> bool:
    cx = float(box["x"]) + float(box["w"]) / 2.0
    cy = float(box["y"]) + float(box["h"]) / 2.0
    return (
        float(region["x"]) <= cx <= float(region["x"]) + float(region["w"])
        and float(region["y"]) <= cy <= float(region["y"]) + float(region["h"])
    )


def _layer_active(layer: dict, source_t: float) -> bool:
    ranges = layer.get("ranges") or []
    if not ranges:
        return True
    return any(
        float(item["start"]) <= source_t < float(item["end"])
        for item in ranges
        if isinstance(item, dict)
    )


def _clean_regions(
    layers: Iterable[dict],
    sample: dict,
    compiled: dict,
) -> list[dict]:
    segment = segment_at(compiled, float(sample["t"]))
    if segment is None:
        return []
    source_t = float(segment.get("start") or 0.0) + (
        float(sample["t"]) - float(segment.get("out_start") or 0.0)
    )
    source = compiled.get("source") or {}
    canvas = compiled.get("canvas") or {}
    regions = []
    for layer in layers or []:
        if not isinstance(layer, dict):
            continue
        if layer.get("kind") not in {"blur", "plate", "mask", "delogo"}:
            # crop_guard removes the region from the output; it cannot leave text.
            continue
        if not _layer_active(layer, source_t):
            continue
        region = _map_region(
            layer.get("box") or {},
            segment.get("crop") or {},
            source_width=int(source.get("width") or 0),
            source_height=int(source.get("height") or 0),
            out_width=int(canvas.get("w") or 0),
            out_height=int(canvas.get("h") or 0),
        )
        if region is not None:
            regions.append({"layer": layer, "region": region, "source_t": source_t})
    return regions


def residual_report(
    samples: Iterable[dict],
    *,
    layers: Iterable[dict],
    compiled: dict,
    target_pct: float = RESIDUAL_TARGET_PCT,
) -> dict:
    """Measure OCR text left inside Clean regions on rendered output frames.

    ``samples`` are rendered output frames: ``{"t": output_time, "text":
    [{"text", "box"}]}``. OCR boxes are output-normalized. The Clean layer box
    is mapped from source coordinates through the segment crop, so the check
    measures the same pixels the renderer cleaned.
    """
    layer_list = [item for item in layers or [] if isinstance(item, dict)]
    rows = []
    per_layer: dict[str, dict] = {}
    frames_with_ocr = 0
    unlocated = 0
    for sample in samples or []:
        if not isinstance(sample, dict):
            continue
        t = float(sample.get("t") or 0.0)
        lines = [
            line for line in sample.get("text") or []
            if isinstance(line, dict) and str(line.get("text") or "").strip()
        ]
        if lines:
            frames_with_ocr += 1
        regions = _clean_regions(layer_list, {"t": t}, compiled)
        hits = []
        for line in lines:
            box = line.get("box")
            if not isinstance(box, dict):
                unlocated += 1
                continue
            for item in regions:
                region = item["region"]
                overlap = _rect_overlap(box, region)
                area = max(1e-9, float(box.get("w") or 0) * float(box.get("h") or 0))
                if overlap / area >= 0.10 or _center_inside(box, region):
                    hits.append({
                        "layer_id": item["layer"].get("id"),
                        "kind": item["layer"].get("kind"),
                        "text": str(line.get("text") or "")[:160],
                    })
                    stats = per_layer.setdefault(str(item["layer"].get("id")), {
                        "layer_id": item["layer"].get("id"),
                        "kind": item["layer"].get("kind"),
                        "frames": 0,
                        "residual_frames": 0,
                        "hits": 0,
                    })
                    stats["hits"] += 1
                    break
        if regions:
            for item in regions:
                stats = per_layer.setdefault(str(item["layer"].get("id")), {
                    "layer_id": item["layer"].get("id"),
                    "kind": item["layer"].get("kind"),
                    "frames": 0,
                    "residual_frames": 0,
                    "hits": 0,
                })
                stats["frames"] += 1
        if hits:
            for layer_id in {hit["layer_id"] for hit in hits if hit["layer_id"]}:
                per_layer[layer_id]["residual_frames"] += 1
        rows.append({
            "t": round(t, 3),
            "residual": bool(hits),
            "text": [hit["text"] for hit in hits],
            "regions": len(regions),
        })
    sampled = len(rows)
    residual_frames = sum(1 for row in rows if row["residual"])
    pct = round(100.0 * residual_frames / sampled, 3) if sampled else 0.0
    return {
        "schema": SCHEMA_VERSION,
        "kind": "residual_ocr",
        "frames_sampled": sampled,
        "frames_with_ocr": frames_with_ocr,
        "residual_frames": residual_frames,
        "residual_pct": pct,
        "target_pct": float(target_pct),
        "pass": bool(sampled) and pct <= float(target_pct),
        "unlocated_text": unlocated,
        "layers": [
            {
                **per_layer[key],
                "residual_pct": round(
                    100.0 * per_layer[key]["residual_frames"]
                    / max(1, per_layer[key]["frames"]),
                    3,
                ),
            }
            for key in sorted(per_layer)
        ],
        "samples": rows,
        "note": (
            "Rendered with Clean and reframe only; motion, colour, graphics "
            "and captions are excluded so new text cannot be counted."
        ),
    }


def face_overlap_report(
    samples: Iterable[dict],
    *,
    layers: Iterable[dict],
    compiled: dict,
    scenes: Iterable[dict] | None,
) -> dict:
    """Report Clean regions that overlap a face detected by Check."""
    scene_rows = [item for item in scenes or [] if isinstance(item, dict)]
    hits = []
    faces_checked = 0
    for sample in samples or []:
        if not isinstance(sample, dict):
            continue
        t = float(sample.get("t") or 0.0)
        source_t = source_time_at(compiled, t)
        if source_t is None:
            continue
        scene = next(
            (
                item for item in scene_rows
                if float(item.get("start") or 0.0) <= source_t < float(item.get("end") or 0.0)
            ),
            None,
        )
        if scene is None:
            continue
        faces = scene.get("faces")
        if not faces:
            attention = scene.get("attention") or {}
            face = attention.get("face")
            faces = [face] if isinstance(face, dict) else []
        faces = [item for item in faces or [] if isinstance(item, dict)]
        faces_checked += len(faces)
        for layer in layers or []:
            if not isinstance(layer, dict) or layer.get("kind") not in {"blur", "plate", "mask", "delogo"}:
                continue
            if not _layer_active(layer, source_t):
                continue
            box = layer.get("box") or {}
            for face in faces:
                overlap = _rect_overlap(box, face)
                area = max(1e-9, float(face.get("w") or 0) * float(face.get("h") or 0))
                if overlap / area >= 0.10 or _center_inside(face, box):
                    hits.append({
                        "t": round(t, 3),
                        "source_t": round(source_t, 3),
                        "scene": scene.get("id"),
                        "layer_id": layer.get("id"),
                        "face": {
                            key: face.get(key) for key in ("x", "y", "w", "h")
                        },
                    })
    return {
        "overlap": bool(hits),
        "count": len(hits),
        "faces_checked": faces_checked,
        "hits": hits,
    }
