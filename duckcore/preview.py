"""Clean preview for one frame of an edit."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from duckcore.media import extract_frame


def _active(layer: dict, when: float) -> bool:
    if layer.get("enabled") is False:
        return False
    ranges = layer.get("ranges") or []
    if not ranges:
        return True
    return any(
        float(item.get("start") or 0.0) <= when <= float(item.get("end") or 0.0)
        for item in ranges
        if isinstance(item, dict)
    )


def _pixel_box(layer: dict, width: int, height: int) -> tuple[int, int, int, int] | None:
    box = layer.get("box") or {}
    try:
        x = float(box.get("x") or 0.0)
        y = float(box.get("y") or 0.0)
        w = float(box.get("w") or 0.0)
        h = float(box.get("h") or 0.0)
    except (TypeError, ValueError):
        return None
    x0 = max(0, min(width, int(round(x * width))))
    y0 = max(0, min(height, int(round(y * height))))
    x1 = max(x0, min(width, int(round((x + w) * width))))
    y1 = max(y0, min(height, int(round((y + h) * height))))
    return (x0, y0, x1, y1) if x1 > x0 and y1 > y0 else None


def proof_layers(layers: list[dict], mode: str = "clean") -> list[dict]:
    """Layers a proof draws: blur mode turns every enabled layer into a blur.

    Off stays Off. The source layers are not mutated, and a blur proof never
    reaches the fill engine or writes a fill cache entry.
    """
    if str(mode or "clean").strip().lower() != "blur":
        return list(layers)
    return [
        {**layer, "kind": "blur"}
        for layer in layers
        if isinstance(layer, dict) and layer.get("enabled") is not False
    ]


def render_clean_preview(
    source: str | Path,
    edit: dict,
    data_root: Path,
    output: Path,
    *,
    when: float | None = None,
) -> tuple[Path, float, int]:
    layers = [layer for layer in edit.get("clean") or [] if isinstance(layer, dict)]
    if not layers:
        raise ValueError("This edit has no clean layers.")
    if when is None:
        first = layers[0]
        ranges = first.get("ranges") or []
        when = float(ranges[0].get("start") or 0.0) + 0.5 if ranges else 0.0
    when = max(0.0, min(float(edit.get("end") or 0.0), float(when)))

    image = extract_frame(source, when)
    frame = np.asarray(image, dtype=np.uint8)
    height, width = frame.shape[:2]
    active = [layer for layer in layers if _active(layer, when)]

    from duckcore.engine import textfill

    for layer in active:
        box = _pixel_box(layer, width, height)
        if box is None:
            continue
        if layer.get("kind") == "blur":
            x0, y0, x1, y1 = box
            region = image.crop(box).filter(ImageFilter.GaussianBlur(radius=18))
            image.paste(region, box)
            frame = np.asarray(image, dtype=np.uint8)
            continue
        if layer.get("kind") != "fill":
            continue
        frame = textfill.fill_frame(
            frame,
            [box],
            data_root=data_root,
            method="lama",
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(frame).save(output, quality=90, optimize=True)
    return output, when, len(active)
