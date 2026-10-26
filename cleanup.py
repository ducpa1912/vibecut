"""Deterministic Cleanup Kit for Flow 1.

Flow 1 cleans a finished video that already has baked-in text. The supported
operations are deliberately boring: crop away edge text, cover a region, or
blur a region. There is no inpainting, generative repair, temporal
reconstruction, logo repair, or watermark removal.

Everything here is pure data. Building a plan never invokes ffmpeg, never
writes to a job, and never calls the network. ``filter_chain`` is a declarative
description for a future renderer, not an executable command.
"""

from __future__ import annotations

import math
import re
from typing import Any, Iterable

SCHEMA_VERSION = 1
MAX_BOXES = 64
CROP_EDGE = 0.08
APPROXIMATE_CONFIDENCE = 0.2
EXPLICIT_CONFIDENCE = 1.0

SUPPORTED_METHODS = ("blur", "cover", "crop")
SUPPORTED_ASPECTS = ("9:16", "4:5", "1:1", "16:9")

# Keep these dimensions in sync with render.ASPECTS. Importing render would
# pull the ffmpeg renderer into a module that is meant to stay pure.
ASPECT_DIMENSIONS = {
    "9:16": (1080, 1920),
    "4:5": (1080, 1350),
    "1:1": (1080, 1080),
    "16:9": (1920, 1080),
}

LIMITATIONS = [
    "Plausible cleanup, not restoration. Covered, blurred, or cropped pixels are not recovered.",
    "No watermark removal and no guarantee that every text overlay is removed.",
    "No generative repair, inpainting, face repair, logo repair, or temporal reconstruction.",
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
