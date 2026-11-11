"""Score a finished render against the ink of every line it was meant to clean.

For each fill or blur layer this builds the line's ink from the source, scores
the output frames of its range plus half a second each side, and records a
flicker number. A frame whose score passes ``ink.HIT`` is leftover text.

The check reads pixels only, so a one-frame text flash and a still scene edge
cannot be told apart without OCR. It also reads the whole line: a fill that
leaves two glyphs of eleven scores about 0.2 and is not reported. Both limits
are stated in the render panel.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from duckcore import ink as inkmod
from duckcore.engine.textfill import mask as masks

PAD = 0.5
FLICKER_LIMIT = 2.2


def _rect(layer: dict, meta: dict) -> tuple[int, int, int, int] | None:
    width = int(meta.get("width") or 0)
    height = int(meta.get("height") or 0)
    if width < 2 or height < 2:
        return None
    return masks.layer_rect(layer, width, height)


def _flicker(output: str | Path, built: inkmod.Ink, *, start: float,
             end: float, fps: float) -> float | None:
    """Frame-to-frame change inside the hole against a ring around it."""
    pad = 0.25
    t0 = max(0.0, start - pad)
    duration = max(0.1, end - start + 2 * pad)
    frames = inkmod.read_box(output, t0, duration, built.rect, fps)
    if frames.shape[0] < 3:
        return None
    hole = built.mask
    ring = np.zeros_like(hole)
    grow = inkmod.dilate(np.ones_like(hole), max(6, hole.shape[0] // 4))
    ring[:] = grow
    ring[hole] = False
    if not ring.any():
        return None
    change = np.abs(np.diff(frames.astype(np.int16), axis=0))
    # The ink spans one pixel less than the rect: its gradient drops the last
    # row and column. Crop the change map to the ink's frame.
    change = change[:, :hole.shape[0], :hole.shape[1]]
    inside = float(change[:, hole].mean()) if hole.any() else 0.0
    around = float(change[:, ring].mean())
    if around <= 1e-3:
        return None
    return round(inside / around, 2)


def layer_ink(layer: dict, meta: dict, *, source: str | Path,
              fps: float = 30.0) -> inkmod.Ink | None:
    """One ink for a layer, unioned over its ranges, in the layer rect's frame."""
    rect = _rect(layer, meta)
    if rect is None:
        return None
    masks_out: list[np.ndarray] = []
    for span in layer.get("ranges") or []:
        start = float(span.get("start") or 0.0)
        end = float(span.get("end") or 0.0)
        if end <= start:
            continue
        built = inkmod.build(source, rect, start=start, end=end, fps=fps)
        if built is not None:
            masks_out.append(built.mask)
    if not masks_out:
        return None
    mask = masks_out[0]
    for extra in masks_out[1:]:
        mask = mask | extra
    return inkmod.Ink(mask=mask, rect=rect)


def check(output: str | Path, edit: dict, meta: dict, *, source: str | Path,
          fps: float = 30.0, inks: dict | None = None) -> dict:
    """Score every clean layer on the output. Returns counts, hits and flicker."""
    inks = inks if inks is not None else {}
    frames = 0
    hits: list[dict] = []
    flicker: dict[str, float] = {}
    layers = [
        layer for layer in edit.get("clean") or []
        if isinstance(layer, dict) and layer.get("enabled") is not False
        and layer.get("kind") in {"fill", "blur"}
    ]
    for layer in layers:
        layer_id = str(layer.get("id"))
        built = inks.get(layer_id)
        if built is None:
            built = layer_ink(layer, meta, source=source, fps=fps)
            if built is None:
                continue
            inks[layer_id] = built
        for span in layer.get("ranges") or []:
            start = float(span.get("start") or 0.0)
            end = float(span.get("end") or 0.0)
            if end <= start:
                continue
            points = inkmod.score(
                output, built, start=start, end=end, fps=fps, pad=PAD,
            )
            frames += len(points)
            for time, value in points:
                # The pad is there to catch a late frame of this line. Text
                # before the range belongs to the previous line, not this one.
                if time < start - 0.04 or time > end + 0.04:
                    continue
                if value >= inkmod.HIT:
                    hits.append({
                        "time": time,
                        "score": round(value, 2),
                        "layer": layer_id,
                        "text": str(layer.get("text_sample") or "")[:40],
                    })
        span = (layer.get("ranges") or [{}])[0]
        value = _flicker(
            output, built,
            start=float(span.get("start") or 0.0),
            end=float(span.get("end") or 0.0),
            fps=fps,
        )
        if value is not None:
            flicker[layer_id] = value
    return {
        "frames": int(frames),
        "hits": hits,
        "times": sorted({item["time"] for item in hits}),
        "flicker": flicker,
        "flicker_limit": FLICKER_LIMIT,
        "layers": len(layers),
    }


def build_inks(edit: dict, meta: dict, *, source: str | Path,
               fps: float = 30.0) -> dict:
    """Ink for every clean layer, keyed by layer id."""
    out: dict = {}
    for layer in edit.get("clean") or []:
        if not isinstance(layer, dict) or layer.get("enabled") is False:
            continue
        if layer.get("kind") not in {"fill", "blur"}:
            continue
        built = layer_ink(layer, meta, source=source, fps=fps)
        if built is not None:
            out[str(layer.get("id"))] = built
    return out
