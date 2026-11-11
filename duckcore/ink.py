"""Ink: the pixels a line of text owns, and a score for whether they are still there.

Burned-in text is the only thing that sits on the same pixels while the picture
changes. This module builds a stroke map for one line from the source frames of
its range, then scores any frame by how much of that map still has a strong
edge. No OCR.

A steady shot breaks the simple rule: the plate rim and the table edge are also
still. Ink is therefore edges that are strong through the line **and** weak in
the frames just before it starts and just after it ends. Scene edges that pass
through both windows are not ink.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

EDGE = 40.0
INSIDE = 0.8
OUTSIDE = 0.25
# A frame is text when this share of the ink still has a strong edge. Every
# real leak on the review project scores 0.94+; a filled frame keeps a scene
# edge at 0.75-0.78 at most, so the line sits between them.
HIT = 0.85
# Grown around the ink for the fill hole: outline, shadow, antialiasing.
GROW_PX = 6


def _ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    root = Path(__file__).resolve().parent.parent
    return str(root / "build/DuckSuite-Xcode.app/Contents/Helpers/ffmpeg")


def gradient(frames: np.ndarray) -> np.ndarray:
    """Sum of horizontal and vertical absolute differences, in 8-bit levels."""
    # uint8 subtraction wraps (0 - 255 = 1), which hides every dark-to-light
    # edge. Widen first.
    pixels = np.asarray(frames, dtype=np.int16)
    gx = np.abs(np.diff(pixels, axis=-1))[..., :-1, :]
    gy = np.abs(np.diff(pixels, axis=-2))[..., :, :-1]
    return gx + gy


def strong(frames: np.ndarray, edge: float = EDGE) -> np.ndarray:
    return gradient(frames) > edge


def ink_from(inside: np.ndarray, outside: np.ndarray | None = None,
             *, inside_share: float = INSIDE, outside_share: float = OUTSIDE) -> np.ndarray:
    """The stroke map. ``inside``/``outside`` are boolean edge arrays (T, h, w).

    A pixel is ink when it is a strong edge on most frames of the line and not
    a steady edge in the frames around it.
    """
    steady = inside.mean(axis=0) >= inside_share if inside.size else np.zeros(inside.shape[1:], bool)
    if outside is not None and outside.size:
        plate = outside.mean(axis=0) >= outside_share
        steady = steady & ~plate
    return steady


def scores(edges: np.ndarray, ink: np.ndarray) -> np.ndarray:
    """Per-frame share of ink pixels that still have a strong edge."""
    total = int(ink.sum())
    if total <= 0 or edges.size == 0:
        return np.zeros(edges.shape[0], dtype=np.float32)
    hit = (edges & ink[None, :, :]).sum(axis=(1, 2))
    return (hit / total).astype(np.float32)


def dilate(mask: np.ndarray, px: int = GROW_PX) -> np.ndarray:
    """Square growth, so a hole covers an outline and a soft shadow."""
    if px <= 0 or not mask.any():
        return mask.copy()
    wide = mask.copy()
    for _ in range(int(px)):
        step = wide.copy()
        step[:, 1:] |= wide[:, :-1]
        step[:, :-1] |= wide[:, 1:]
        wide = step
    tall = wide.copy()
    for _ in range(int(px)):
        step = tall.copy()
        step[1:, :] |= tall[:-1, :]
        step[:-1, :] |= tall[1:, :]
        tall = step
    return tall


def bbox(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    """x0, y0, x1, y1 of the set pixels, or None."""
    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]
    if not len(rows) or not len(cols):
        return None
    return int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1


@dataclass(frozen=True)
class Ink:
    """A line's stroke map and the frame rectangle it was read from."""

    mask: np.ndarray
    rect: tuple[int, int, int, int]

    @property
    def pixels(self) -> int:
        return int(self.mask.sum())

    def hole(self, grow: int = GROW_PX) -> np.ndarray:
        return dilate(self.mask, grow)

    def box(self, width: int, height: int) -> dict | None:
        """The grown ink as a normalized box, so a layer can use it as its hole."""
        box = bbox(self.hole())
        if box is None:
            return None
        x0, y0, x1, y1 = box
        rx, ry = self.rect[0], self.rect[1]
        return {
            "x": round((rx + x0) / width, 6),
            "y": round((ry + y0) / height, 6),
            "w": round((x1 - x0) / width, 6),
            "h": round((y1 - y0) / height, 6),
        }


def read_box(path: str | Path, t0: float, duration: float,
             rect: tuple[int, int, int, int], fps: float) -> np.ndarray:
    """Decode a rectangle of grey frames at ``fps``. Shape (T, h, w) uint8."""
    x0, y0, x1, y1 = rect
    width, height = x1 - x0, y1 - y0
    if width < 2 or height < 2 or duration <= 0:
        return np.zeros((0, max(2, height), max(2, width)), dtype=np.uint8)
    frames = max(1, int(round(duration * fps)))
    command = [
        _ffmpeg(), "-v", "error", "-nostdin",
        "-ss", f"{max(0.0, t0):.6f}", "-t", f"{duration:.6f}", "-i", str(path),
        "-an", "-sn",
        "-vf", f"fps={fps:.6f},crop={width}:{height}:{x0}:{y0},format=gray",
        "-frames:v", str(frames), "-f", "rawvideo", "-",
    ]
    out = subprocess.run(command, capture_output=True, check=False).stdout
    size = width * height
    count = len(out) // size
    if count <= 0:
        return np.zeros((0, height, width), dtype=np.uint8)
    return np.frombuffer(out[:count * size], dtype=np.uint8).reshape(count, height, width)


def build(source: str | Path, rect: tuple[int, int, int, int], *,
          start: float, end: float, fps: float,
          before: float = 0.45, after: float = 0.45) -> Ink | None:
    """Build the ink for a line from the source frames of its range."""
    duration = max(0.0, end - start)
    if duration <= 0.05:
        return None
    inside = strong(read_box(source, start, duration, rect, fps))
    if inside.size == 0:
        return None
    before_frames = strong(read_box(source, max(0.0, start - before), before, rect, fps))
    after_frames = strong(read_box(source, end, after, rect, fps))
    outside = np.concatenate([before_frames, after_frames], axis=0) \
        if before_frames.size or after_frames.size else None
    mask = ink_from(inside, outside)
    if mask.sum() < 8:
        return None
    return Ink(mask=mask, rect=rect)


def score(output: str | Path, ink: Ink, *, start: float, end: float,
          fps: float, pad: float = 0.5) -> list[tuple[float, float]]:
    """Score the output in ``[start - pad, end + pad]`` and return (time, score)."""
    t0 = max(0.0, start - pad)
    duration = max(0.05, end - start + 2 * pad)
    frames = read_box(output, t0, duration, ink.rect, fps)
    if frames.size == 0:
        return []
    values = scores(strong(frames), ink.mask)
    return [(round(t0 + index / fps, 3), float(value)) for index, value in enumerate(values)]


def hits(points: Iterable[tuple[float, float]], threshold: float = HIT) -> list[float]:
    """Times where the score says the line is still there."""
    return [time for time, value in points if value >= threshold]


def onset_moments(source: str | Path, *, width: int = 540, height: int = 960,
                  fps: float = 30.0, edge: float = 36.0,
                  stay: int = 4, band_min: int = 150) -> list[float]:
    """Frames where strokes appear and then stay: a candidate line start.

    A full-rate scan at 540 px. It is used to look where Check's 4 fps pass
    cannot see, not to prove text.
    """
    command = [
        _ffmpeg(), "-v", "error", "-nostdin", "-i", str(source),
        "-vf", f"scale={width}:{height},format=gray", "-f", "rawvideo", "-",
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE)
    size = width * height
    frames: list[np.ndarray] = []
    times: list[float] = []
    index = 0
    found: list[tuple[float, int, int]] = []
    try:
        while True:
            data = process.stdout.read(size)
            if len(data) < size:
                break
            grey = np.frombuffer(data, dtype=np.uint8).reshape(height, width).astype(np.int16)
            gx = np.abs(np.diff(grey, axis=1))[:-1, :]
            gy = np.abs(np.diff(grey, axis=0))[:, :-1]
            frames.append((gx + gy) > edge)
            frames = frames[-(stay + 3):]
            if len(frames) == stay + 3:
                after = frames[3] & frames[4] & frames[5] & frames[6]
                before = dilate_small(frames[0] | frames[1] | frames[2])
                onset = after & ~before
                rows = onset.sum(axis=1)
                band = np.convolve(rows, np.ones(30), "same")
                if band.size and int(band.max()) >= band_min:
                    found.append(((index - 3) / fps, int(band.max()), int(band.argmax())))
            index += 1
    finally:
        process.kill()
        process.wait(timeout=5)
    # One moment per 0.2 s burst.
    moments: list[float] = []
    for time, _peak, _y in found:
        if not moments or time - moments[-1] > 0.2:
            moments.append(round(time, 3))
    return moments


def dilate_small(mask: np.ndarray) -> np.ndarray:
    out = mask.copy()
    out[1:, :] |= mask[:-1, :]
    out[:-1, :] |= mask[1:, :]
    out[:, 1:] |= mask[:, :-1]
    out[:, :-1] |= mask[:, 1:]
    return out
