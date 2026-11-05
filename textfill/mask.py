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
# The scan reads two frames a second, so a detected range edge is known to about
# a quarter second. Detected layers (with a tracklet_id) get this margin.
DETECTED_TIME_MARGIN = 0.25
# Feather width of the paste-back edge, in pixels, outside the mask.
FEATHER_PX = 3
# Context a LaMa work area keeps around the text.
CONTEXT_MIN_PX = 32
CONTEXT_RATIO = 0.5
# Finding the text inside a scanned box, per frame. Contrast is in 8-bit levels
# against the local average; shares are of the box.
TEXT_CONTRAST = 36.0
TEXT_CONTRAST_MEDIAN = 2.5
# The contrast limit reads this percentile of the box. Text can fill half of a
# tight box, so the median measures the text itself and the limit goes above it.
TEXT_QUIET_PERCENTILE = 30
TEXT_WEAK_CONTRAST = 14.0
TEXT_MIN_SHARE = 0.002
TEXT_WEAK_SHARE = 0.01
TEXT_MAX_SHARE = 0.5
TEXT_GROW_RATIO = 0.006
TEXT_GROW_MIN_PX = 3

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


def frame_keys(
    layers: Iterable[dict],
    *,
    start: float,
    fps: float,
    frames: int,
) -> list[float | None]:
    """AI fills per second the plan asks for on each frame of a span.

    The busiest line on a frame sets it. None means a layer on that frame has no
    plan, such as a drawn box, so the render uses its own default.
    """
    timed = [(layer, layer_windows(layer)) for layer in layers]
    out: list[float | None] = []
    for index in range(frames):
        at = start + (index + 0.5) / fps
        active = [
            layer for layer, windows in timed
            if windows is None or any(low <= at <= high for low, high in windows)
        ]
        plans = [layer.get("fill_keys") for layer in active]
        out.append(None if not plans or any(plan is None for plan in plans) else float(max(plans)))
    return out


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


def without_contained(rects: Iterable[Rect]) -> list[Rect]:
    """The rects, less any that sits wholly inside another one."""
    unique = list(dict.fromkeys(tuple(rect) for rect in rects))
    return [
        rect for rect in unique
        if not any(
            other != rect
            and other[0] <= rect[0] and other[1] <= rect[1]
            and other[2] >= rect[2] and other[3] >= rect[3]
            for other in unique
        )
    ]


def lama_areas(rects: Iterable[Rect], width: int, height: int) -> list[Rect]:
    """Work areas for these rects: text close together shares one, the rest apart.

    The model's time follows the pixels it reads, so a title and a caption run
    as two small areas and not as one holding all the picture between them.
    """
    areas = [lama_area([rect], width, height) for rect in without_contained(rects)]
    areas = [area for area in areas if area is not None]
    merged = True
    while merged:
        merged = False
        for index, area in enumerate(areas):
            for other_index in range(index + 1, len(areas)):
                other = areas[other_index]
                if area[0] < other[2] and other[0] < area[2] and area[1] < other[3] and other[1] < area[3]:
                    areas[index] = (
                        min(area[0], other[0]), min(area[1], other[1]),
                        max(area[2], other[2]), max(area[3], other[3]),
                    )
                    del areas[other_index]
                    merged = True
                    break
            if merged:
                break
    return sorted(areas, key=lambda area: (area[1], area[0]))


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


def uses_text_mask(layer: dict, width: int, height: int) -> bool:
    """Only a scan layer without a brush stroke narrows to the text it found.

    A drawn box means "remove this area", and a brush stroke is exact.
    """
    if not layer.get("tracklet_id"):
        return False
    return layer_rects(layer, width, height) == [layer_rect(layer, width, height)]


def _local_mean(values: np.ndarray, radius: int) -> np.ndarray:
    """Mean over a square around each pixel; edges repeat, so they stay flat."""
    padded = np.pad(values, ((radius + 1, radius), (radius + 1, radius), (0, 0)), mode="edge")
    total = padded.cumsum(axis=0).cumsum(axis=1)
    size = 2 * radius + 1
    return (
        total[size:, size:] - total[:-size, size:] - total[size:, :-size] + total[:-size, :-size]
    ) / (size * size)


def text_in_region(region: np.ndarray, grow: int) -> np.ndarray | None:
    """Text pixels of one RGB box, or None when the whole box must be filled.

    Burned-in text stands out from what is around it in brightness or colour.
    Returns an all-False mask when the box plainly has no text on this frame.
    When it cannot tell (a very busy box, or faint structure that might be
    faint text) it returns None, because leaving text behind is the worse error.
    """
    height, width = region.shape[:2]
    if height < 3 or width < 3:
        return None
    values = region.astype(np.float32)
    radius = max(4, min(height, width) // 2)
    contrast = np.abs(values - _local_mean(values, radius)).max(axis=2)
    limit = max(
        TEXT_CONTRAST,
        TEXT_CONTRAST_MEDIAN * float(np.percentile(contrast, TEXT_QUIET_PERCENTILE)),
    )
    strong = contrast > limit
    # A lone speck is noise; a stroke has neighbours.
    strong &= _box_mean(_box_mean(strong.astype(np.float32), 1, 0), 1, 1) >= 3 / 9
    share = float(strong.mean())
    if share > TEXT_MAX_SHARE:
        return None
    if share < TEXT_MIN_SHARE:
        if float((contrast > TEXT_WEAK_CONTRAST).mean()) > TEXT_WEAK_SHARE:
            return None
        return np.zeros((height, width), dtype=bool)
    grown = _box_mean(_box_mean(strong.astype(np.float32), grow, 0), grow, 1) > 1e-6
    return grown | strong


class TextMasks:
    """Per-frame holes for a span: found text, plus painted or drawn areas.

    A hole also covers the frames just before and after, so text fading in or
    out is caught and the mask does not flicker. ``wrap`` must read the frames,
    because the masks come from them.
    """

    WINDOW = 2

    def __init__(self, tight: list[list[Rect]], exact: list[list[Rect]], width: int, height: int):
        self.tight = tight
        self.exact = exact
        self.width = width
        self.height = height
        self.grow = max(TEXT_GROW_MIN_PX, int(round(width * TEXT_GROW_RATIO)))
        self.found: dict[int, list[tuple[Rect, np.ndarray]]] = {}

    def _measure(self, index: int, frame: np.ndarray) -> None:
        rows = []
        for rect in set(self.tight[min(index, len(self.tight) - 1)]):
            x0, y0, x1, y1 = rect
            text = text_in_region(frame[y0:y1, x0:x1], self.grow)
            if text is None:
                text = np.ones((y1 - y0, x1 - x0), dtype=bool)
            if text.any():
                rows.append((rect, text))
        self.found[index] = rows

    def wrap(self, frames: Iterable[np.ndarray]):
        """Yield frames unchanged, having read ``WINDOW`` frames ahead of each."""
        pending: list[np.ndarray] = []
        index = 0
        for frame in frames:
            self._measure(index + len(pending), frame)
            pending.append(frame)
            if len(pending) > self.WINDOW:
                yield pending.pop(0)
                index += 1
        for frame in pending:
            yield frame

    def _exact_at(self, index: int) -> list[Rect]:
        return self.exact[min(index, len(self.exact) - 1)]

    def _window(self, index: int):
        for at in range(index - self.WINDOW, index + self.WINDOW + 1):
            yield from self.found.get(at, ())

    def has_fill(self, index: int) -> bool:
        return bool(self._exact_at(index)) or any(True for _ in self._window(index))

    def rects_for(self, index: int) -> list[Rect]:
        """The rects worth filling on this frame; none when it has no text."""
        tight = self.tight[min(index, len(self.tight) - 1)]
        if not self.has_fill(index):
            return []
        return [*self._exact_at(index), *tight]

    def hole(self, index: int, x0: int, y0: int, x1: int, y1: int) -> np.ndarray:
        """The hole on frame ``index`` within an area, in that area's pixels."""
        out = np.zeros((y1 - y0, x1 - x0), dtype=bool)
        for left, top, right, bottom in self._exact_at(index):
            out[max(top, y0) - y0:max(bottom - y0, 0), max(left, x0) - x0:max(right - x0, 0)] = True
        for (left, top, right, bottom), text in self._window(index):
            cx0, cy0, cx1, cy1 = max(left, x0), max(top, y0), min(right, x1), min(bottom, y1)
            if cx1 > cx0 and cy1 > cy0:
                out[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0] |= text[cy0 - top:cy1 - top, cx0 - left:cx1 - left]
        return out

    def forget_before(self, index: int) -> None:
        for at in [key for key in self.found if key < index - self.WINDOW]:
            del self.found[at]
