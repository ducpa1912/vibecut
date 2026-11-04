"""Masks and work areas for AI text fill. Pure numpy: no ffmpeg, no model.

Clean layers carry source-normalized boxes and absolute source-time ranges
(the Edit Clean contract). This module turns them into per-frame pixel
rectangles, the work area each model sees, and the feathered paste-back
alpha. Pixels outside a dilated mask are never touched.
"""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np

# OCR boxes sit tight on the glyphs. Outlines, shadows and anti-aliasing reach
# past them, so every box grows by this share of its height on each side.
PAD_RATIO = 0.06
PAD_MIN_PX = 3
# Check samples OCR at 0.5 fps, so a detected range edge is only known to
# about ±2 s. Detected layers (with a tracklet_id) get this margin.
DETECTED_TIME_MARGIN = 1.0
# Feather width of the paste-back edge, in pixels, outside the mask.
FEATHER_PX = 3
# Context a LaMa work area keeps around the text.
CONTEXT_MIN_PX = 32
CONTEXT_RATIO = 0.5

Rect = tuple[int, int, int, int]  # x0, y0, x1, y1; x1 and y1 exclusive


def layer_rect(layer: dict, width: int, height: int) -> Rect:
    """Padded pixel rectangle of one layer's source box, clipped to the frame."""
    box = layer.get("box") or {}
    x = float(box.get("x", 0.0)) * width
    y = float(box.get("y", 0.0)) * height
    w = float(box.get("w", 0.0)) * width
    h = float(box.get("h", 0.0)) * height
    pad = max(PAD_MIN_PX, PAD_RATIO * h)
    x0 = max(0, int(math.floor(x - pad)))
    y0 = max(0, int(math.floor(y - pad)))
    x1 = min(width, int(math.ceil(x + w + pad)))
    y1 = min(height, int(math.ceil(y + h + pad)))
    return x0, y0, max(x0, x1), max(y0, y1)


def _round_stamp(cx: float, cy: float, radius: float) -> list[Rect]:
    """A filled circle as three overlapping rectangles."""
    stamps = []
    for across, down in ((1.0, 0.38), (0.75, 0.75), (0.38, 1.0)):
        stamps.append((
            int(math.floor(cx - radius * across)),
            int(math.floor(cy - radius * down)),
            int(math.ceil(cx + radius * across)),
            int(math.ceil(cy + radius * down)),
        ))
    return stamps


def layer_rects(layer: dict, width: int, height: int) -> list[Rect]:
    """Every pixel rectangle a layer covers on the source frame.

    A brush mask narrows the layer's box: strokes are joined, kept round and
    clipped to the box. A mask too small to be a stroke (one click) is treated
    as a slip, so the whole box is filled rather than one dot of it.
    """
    bounds = layer_rect(layer, width, height)
    mask = layer.get("mask")
    if not mask:
        return [bounds]
    if isinstance(mask, dict):
        strokes = mask.get("strokes") or []
    else:
        strokes = [{"r": 0.025, "points": mask}]
    prepared: list[tuple[float, list[tuple[float, float]]]] = []
    for stroke in strokes:
        try:
            radius = float((stroke or {}).get("r", 0.02))
        except (TypeError, ValueError):
            radius = 0.02
        points = []
        for point in (stroke or {}).get("points") or []:
            try:
                points.append((float(point.get("x", 0.0)) * width, float(point.get("y", 0.0)) * height))
            except (TypeError, ValueError):
                continue
        if points:
            prepared.append((max(2.0, radius * width), points))
    every = [point for _radius, points in prepared for point in points]
    if len(every) < 2:
        return [bounds]
    reach = max(radius for radius, _points in prepared)
    span = (max(p[0] for p in every) - min(p[0] for p in every)) + (max(p[1] for p in every) - min(p[1] for p in every))
    if span < reach:
        return [bounds]
    x0, y0, x1, y1 = bounds
    rects: list[Rect] = []
    for radius, points in prepared:
        pad = max(PAD_MIN_PX, PAD_RATIO * radius * 2)
        centres = [points[0]]
        for (ax, ay), (bx, by) in zip(points, points[1:]):
            # Fast drags leave gaps between samples; walk across them.
            steps = max(1, int(math.ceil(math.hypot(bx - ax, by - ay) / max(1.0, radius * 0.75))))
            centres.extend(
                (ax + (bx - ax) * step / steps, ay + (by - ay) * step / steps)
                for step in range(1, steps + 1)
            )
        for cx, cy in centres:
            for left, top, right, bottom in _round_stamp(cx, cy, radius + pad):
                clipped = (max(x0, left), max(y0, top), min(x1, right), min(y1, bottom))
                if clipped[2] > clipped[0] and clipped[3] > clipped[1]:
                    rects.append(clipped)
    return rects or [bounds]


def layer_windows(layer: dict) -> list[tuple[float, float]] | None:
    """Active source-time windows, or None when the layer is always on."""
    ranges = layer.get("ranges") or []
    if not ranges:
        return None
    margin = DETECTED_TIME_MARGIN if layer.get("tracklet_id") else 0.0
    return [
        (float(item["start"]) - margin, float(item["end"]) + margin)
        for item in ranges
    ]


def frame_rects(
    layers: Iterable[dict],
    *,
    start: float,
    fps: float,
    frames: int,
    width: int,
    height: int,
) -> list[list[Rect]]:
    """Rectangles to fill on each frame of a span that starts at ``start``."""
    prepared = []
    for layer in layers:
        rects = layer_rects(layer, width, height)
        if not rects:
            continue
        prepared.append((rects, layer_windows(layer)))
    out: list[list[Rect]] = []
    step = 1.0 / float(fps)
    for index in range(int(frames)):
        # Frame centre time, so a window edge between frames is not ambiguous.
        at = float(start) + (index + 0.5) * step
        rects = [
            rect for group, windows in prepared
            if windows is None or any(lo <= at < hi for lo, hi in windows)
            for rect in group
        ]
        out.append(rects)
    return out


def union(rects: Iterable[Rect]) -> Rect | None:
    items = list(rects)
    if not items:
        return None
    return (
        min(item[0] for item in items),
        min(item[1] for item in items),
        max(item[2] for item in items),
        max(item[3] for item in items),
    )


def lama_area(rects: Iterable[Rect], width: int, height: int) -> Rect | None:
    """One fixed work area for the whole span: the text union plus context.

    A fixed area keeps the fill steady from frame to frame.
    """
    box = union(rects)
    if box is None:
        return None
    x0, y0, x1, y1 = box
    context = max(CONTEXT_MIN_PX, int(round(CONTEXT_RATIO * (y1 - y0))))
    return (
        max(0, x0 - context),
        max(0, y0 - context),
        min(width, x1 + context),
        min(height, y1 + context),
    )


def sttn_strips(
    rects: Iterable[Rect], width: int, height: int, ratio: float = 3 / 16,
) -> list[tuple[int, int]]:
    """Full-width horizontal strips (y0, y1) that cover the text union.

    The STTN subtitle model reads a 16:3 strip, so each strip is
    ``width * ratio`` tall. Taller text gets more strips; the last one is
    pulled up so no strip leaves the frame.
    """
    box = union(rects)
    if box is None:
        return []
    strip = min(height, max(2, int(round(width * ratio))))
    top, bottom = box[1], box[3]
    if bottom - top <= strip:
        middle = (top + bottom) // 2
        y0 = min(max(0, middle - strip // 2), height - strip)
        return [(y0, y0 + strip)]
    strips = []
    y0 = top
    while y0 < bottom:
        start = min(y0, height - strip)
        strips.append((start, start + strip))
        y0 += strip
    return strips


def rasterize(rects: Iterable[Rect], width: int, height: int) -> np.ndarray:
    """Boolean mask (height, width) with every rectangle set."""
    mask = np.zeros((height, width), dtype=bool)
    for x0, y0, x1, y1 in rects:
        mask[y0:y1, x0:x1] = True
    return mask


def _box_mean(values: np.ndarray, radius: int, axis: int) -> np.ndarray:
    if radius <= 0:
        return values
    pad = [(0, 0)] * values.ndim
    pad[axis] = (radius + 1, radius)
    padded = np.pad(values, pad, mode="constant")
    total = np.cumsum(padded, axis=axis)
    size = 2 * radius + 1
    upper = np.take(total, np.arange(size, total.shape[axis]), axis=axis)
    lower = np.take(total, np.arange(0, total.shape[axis] - size), axis=axis)
    return (upper - lower) / size


def feather(mask: np.ndarray, radius: int = FEATHER_PX) -> np.ndarray:
    """Paste-back alpha in [0, 1]: 1 on the mask, easing to 0 just outside.

    Every masked pixel stays at 1, and alpha is 0 beyond ``radius`` pixels
    from the mask, so pixels there keep their original values exactly.
    """
    base = mask.astype(np.float32)
    if radius <= 0 or not mask.any():
        return base
    soft = _box_mean(_box_mean(base, radius, 0), radius, 1)
    soft = np.clip(soft * 2.0, 0.0, 1.0)
    return np.maximum(base, soft)


def paste(original: np.ndarray, filled: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """Blend ``filled`` over ``original`` with ``alpha`` (H, W). uint8 out."""
    if not alpha.any():
        return original.copy()
    weight = alpha[..., None]
    blended = original.astype(np.float32) * (1.0 - weight) + filled.astype(np.float32) * weight
    out = np.clip(np.rint(blended), 0, 255).astype(np.uint8)
    keep = alpha <= 0.0
    out[keep] = original[keep]
    return out
