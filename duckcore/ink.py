"""Ink: the pixels a line of text owns, when it is on screen, and whether a frame still shows it.

Burned-in text is the only thing that sits on the same pixels while the picture
changes. This module reads one window of the source around a line and works out,
from pixels alone:

* the stroke map: edges that hold still through the middle of the line;
* the line's real first and last frame: where those strokes switch on and off;
* the glyphs: the stroke map cut into columns, so two letters left behind out
  of eleven are seen as two whole letters, not as a fifth of a line.

Still scenery is also still. A plate rim is told from text by time: it is there
before the line starts **and** after it ends. The next line's text is there on
one side only, so it is never mistaken for scenery, and a range that ends too
early cannot erase its own ink: the edges are found first, and only frames past
them count as "outside".

No OCR. A one-frame flash of text cannot be told from scenery this way.
"""

from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

# A stroke edge: summed horizontal and vertical step, in 8-bit levels.
EDGE = 40.0
# Share of the middle frames an edge must hold on to be a stroke.
CORE_SHARE = 0.8
# Share of the frames on one side of the line an edge must hold on to be scenery.
PLATE_SHARE = 0.7
# The line is on a frame when this share of its strokes is there...
PRESENT = 0.5
# ...and still fading in or out down to this share.
FADE = 0.3
# Frames a line may take to fade in or out past the point it is half there.
FADE_FRAMES = 2
# Seconds read on each side of the range to find the real edges and the scenery.
REACH = 1.0
# A glyph can outlive its line (the "+1" three lines in a row share). The window
# doubles until every glyph has an end, up to this many seconds a side.
REACH_MOST = 8.0
# Seconds just before and just after the line that say what is scenery.
BESIDE = 0.2
# A range shorter than this many frames cannot show that anything holds still.
MIN_FRAMES = 5
# Fewer stroke pixels than this is noise, not a line.
MIN_PIXELS = 24
# Grown around the strokes for the fill hole: letter body, outline, soft shadow.
GROW_PX = 6
# Columns with no ink for this many pixels split two glyphs.
GLYPH_GAP = 3
# A glyph smaller than this joins its neighbour; a dot is not judged alone.
GLYPH_MIN_PIXELS = 60

Rect = tuple[int, int, int, int]  # x0, y0, x1, y1; x1 and y1 exclusive


class InkError(RuntimeError):
    """The frames could not be read, so nothing can be said about the text."""


def gradient(frames: np.ndarray) -> np.ndarray:
    """Sum of horizontal and vertical absolute differences. Shape (..., h-1, w-1)."""
    # uint8 subtraction wraps (0 - 255 = 1), which hides every dark-to-light
    # edge. Widen first.
    pixels = np.asarray(frames, dtype=np.int16)
    gx = np.abs(np.diff(pixels, axis=-1))[..., :-1, :]
    gy = np.abs(np.diff(pixels, axis=-2))[..., :, :-1]
    return gx + gy


def grey(frames: np.ndarray) -> np.ndarray:
    """Luma of RGB frames (..., h, w, 3); grey frames pass through."""
    frames = np.asarray(frames)
    if frames.ndim >= 3 and frames.shape[-1] == 3:
        weights = np.array([77, 150, 29], dtype=np.uint32)
        return ((frames.astype(np.uint32) * weights).sum(axis=-1) >> 8).astype(np.uint8)
    return frames


def strong(frames: np.ndarray, edge: float = EDGE) -> np.ndarray:
    return gradient(grey(frames)) > edge


def dilate(mask: np.ndarray, px: int = GROW_PX) -> np.ndarray:
    """Square growth by ``px`` pixels."""
    if px <= 0 or not mask.any():
        return mask.copy()
    out = mask.copy()
    for axis in (1, 0):
        grown = out.copy()
        for shift in range(1, int(px) + 1):
            if axis == 1:
                grown[:, shift:] |= out[:, :-shift]
                grown[:, :-shift] |= out[:, shift:]
            else:
                grown[shift:, :] |= out[:-shift, :]
                grown[:-shift, :] |= out[shift:, :]
        out = grown
    return out


def bbox(mask: np.ndarray) -> Rect | None:
    rows = np.flatnonzero(mask.any(axis=1))
    cols = np.flatnonzero(mask.any(axis=0))
    if not len(rows) or not len(cols):
        return None
    return int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1


def first_frame(time: float, fps: float) -> int:
    """Index of the first frame at or after ``time`` on a constant-rate grid."""
    return max(0, int(math.ceil(float(time) * float(fps) - 1e-6)))


def glyph_columns(mask: np.ndarray, *, gap: int = GLYPH_GAP,
                  least: int = GLYPH_MIN_PIXELS) -> list[tuple[int, int]]:
    """Column spans (x0, x1) of the glyphs in a stroke map, left to right."""
    counts = mask.sum(axis=0)
    spans: list[list[int]] = []
    empty = gap
    for x, count in enumerate(counts):
        if count:
            if empty >= gap or not spans:
                spans.append([x, x + 1])
            else:
                spans[-1][1] = x + 1
            empty = 0
        else:
            empty += 1
    # A comma or a dot has too little ink to judge alone: it joins the glyph
    # before it, or the one after when it comes first.
    def weight(span: list[int]) -> int:
        return int(counts[span[0]:span[1]].sum())

    merged: list[list[int]] = []
    for span in spans:
        if merged and (weight(span) < least or weight(merged[-1]) < least):
            merged[-1][1] = span[1]
        else:
            merged.append(span)
    # Dense script leaves no gap between letters, and a line read as one glyph
    # would hide two letters left behind among eleven. Cut anything much wider
    # than the line is tall into letter-sized parts, at the emptiest column near
    # each even cut.
    rows = np.flatnonzero(mask.any(axis=1))
    tall = int(rows[-1] - rows[0] + 1) if len(rows) else 0
    out: list[tuple[int, int]] = []
    for a, b in merged:
        parts = int(round((b - a) / tall)) if tall >= 8 else 1
        left = a
        for number in range(1, parts):
            aim = a + (b - a) * number // parts
            near = range(max(left + tall // 2, aim - tall // 4), min(b - tall // 2, aim + tall // 4) + 1)
            if not len(near):
                continue
            cut = min(near, key=lambda x: (int(counts[x]), abs(x - aim)))
            out.append((left, cut))
            left = cut
        out.append((left, b))
    return out


def _run(share: np.ndarray, low: int, high: int, level: float) -> tuple[int, int]:
    """Grow [low, high] outwards while ``share`` holds ``level``; one dip is forgiven."""
    count = len(share)
    while low > 0 and (share[low - 1] >= level or (low > 1 and share[low - 2] >= level)):
        low -= 1
    while high < count - 1 and (share[high + 1] >= level or (high < count - 2 and share[high + 2] >= level)):
        high += 1
    # A forgiven dip at the very end is not text.
    while low < high and share[low] < level:
        low += 1
    while high > low and share[high] < level:
        high -= 1
    return low, high


def _fade(share: np.ndarray, low: int, high: int, level: float, most: int = FADE_FRAMES) -> tuple[int, int]:
    """A few more frames each way while the line is still partly there."""
    for _ in range(most):
        if low > 0 and share[low - 1] >= level:
            low -= 1
    for _ in range(most):
        if high < len(share) - 1 and share[high + 1] >= level:
            high += 1
    return low, high


def _extent(share: np.ndarray, low: int, high: int) -> tuple[int, int] | None:
    """Frames that show the strokes behind ``share``, grown from inside [low, high]."""
    inside = np.flatnonzero(share[low:high + 1] >= PRESENT)
    if not len(inside):
        return None
    a, b = _run(share, low + int(inside[0]), low + int(inside[-1]), PRESENT)
    return _fade(share, a, b, FADE)


@dataclass(frozen=True)
class Ink:
    """One line: its strokes, where they sit, and the frames that show them."""

    mask: np.ndarray            # (h-1, w-1) bool, in ``rect`` coordinates
    rect: Rect                  # the frame rectangle the mask was read from
    first: int                  # first source frame that shows the line
    last: int                   # last source frame that shows the line
    fps: float
    # False when a glyph was still there at the end of the window that was read.
    settled: bool = True
    glyphs: tuple[tuple[int, int], ...] = field(default=())
    # First and last source frame of each glyph. A glyph shared with the lines
    # around it lives longer than the line.
    spans: tuple[tuple[int, int], ...] = field(default=())

    @property
    def pixels(self) -> int:
        return int(self.mask.sum())

    @property
    def start(self) -> float:
        return self.first / self.fps

    @property
    def end(self) -> float:
        """Exclusive: the time of the first frame without the line."""
        return (self.last + 1) / self.fps

    @property
    def reach(self) -> tuple[int, int]:
        """First and last source frame on which any glyph of the line shows."""
        if not self.spans:
            return self.first, self.last
        return min(a for a, _ in self.spans), max(b for _, b in self.spans)

    def hole(self, grow: int = GROW_PX) -> np.ndarray:
        """The strokes grown to cover the letter body, outline and shadow. (h, w)."""
        return self._grown(self.mask, grow)

    def pieces(self, grow: int = GROW_PX) -> list[tuple[int, int, np.ndarray]]:
        """(first frame, last frame, hole) for each glyph: what to fill, and when."""
        if not self.glyphs or len(self.spans) != len(self.glyphs):
            return [(self.first, self.last, self.hole(grow))]
        out = []
        for (x0, x1), (a, b) in zip(self.glyphs, self.spans):
            part = np.zeros_like(self.mask)
            part[:, x0:x1] = self.mask[:, x0:x1]
            out.append((a, b, self._grown(part, grow)))
        return out

    def _grown(self, mask: np.ndarray, grow: int) -> np.ndarray:
        height = self.rect[3] - self.rect[1]
        width = self.rect[2] - self.rect[0]
        full = np.zeros((height, width), dtype=bool)
        # A gradient pixel is the step from a picture pixel to the one on its
        # right and the one below: mark the whole 2 x 2.
        full[:-1, :-1] |= mask
        full[:-1, 1:] |= mask
        full[1:, :-1] |= mask
        full[1:, 1:] |= mask
        return dilate(full, grow)


def analyse(edges: np.ndarray, core: tuple[int, int], *, first_index: int, rect: Rect,
            fps: float, open_high: bool = True) -> Ink | None:
    """Ink from a window of edge maps (T, h, w); ``core`` is the range, as indexes.

    ``first_index`` is the source frame of ``edges[0]``. ``open_high`` says the
    video goes on past the end of the window; when it does not, a glyph that is
    there on the last frame really ends there.
    """
    count = int(edges.shape[0])
    low, high = max(0, int(core[0])), min(count - 1, int(core[1]))
    if count == 0 or high - low + 1 < MIN_FRAMES:
        return None
    # A detected range is padded: trust only its middle to say what the text is.
    trim = (high - low + 1) // 5
    stroke = edges[low + trim:high - trim + 1].mean(axis=0) >= CORE_SHARE
    if int(stroke.sum()) < MIN_PIXELS:
        return None

    def share_of(mask: np.ndarray) -> np.ndarray:
        return edges[:, mask].mean(axis=1) if mask.any() else np.zeros(count)

    # First pass: the strokes still hold scenery, so "there" is halfway between
    # all of them and whatever is left once the text has gone.
    share = share_of(stroke)
    outside = np.concatenate([share[:low], share[high + 1:]])
    floor = float(np.percentile(outside, 10)) if outside.size else 0.0
    ink = stroke
    if floor <= 0.8:
        a, b = _run(share, low + trim, high - trim, (1.0 + floor) / 2.0)
        beside = max(4, int(round(BESIDE * fps)))
        before = edges[max(0, a - 1 - beside):max(0, a - 1)]
        after = edges[b + 2:b + 2 + beside]
        if before.shape[0] >= 4 and after.shape[0] >= 4:
            # Scenery is there just before the line and just after it, even when
            # it drifts. Text is new on at least one side: the next line's
            # letters are on one side only, so they are never taken for scenery.
            # With one side out of the video nothing can be ruled out, and
            # everything steady is kept: a hole a little too big, never a
            # letter left behind.
            ink = stroke & ~((before.mean(axis=0) >= PLATE_SHARE) & (after.mean(axis=0) >= PLATE_SHARE))
    if int(ink.sum()) < MIN_PIXELS:
        return None
    line = _extent(share_of(ink), low, high)
    if line is None:
        return None
    glyphs = glyph_columns(ink)
    spans = []
    for x0, x1 in glyphs:
        part = np.zeros_like(ink)
        part[:, x0:x1] = ink[:, x0:x1]
        spans.append(_extent(share_of(part), low, high) or line)
    settled = not any(
        (a == 0 and first_index > 0) or (b == count - 1 and open_high) for a, b in spans
    )
    return Ink(
        mask=ink, rect=rect, first=first_index + line[0], last=first_index + line[1],
        fps=float(fps), settled=settled, glyphs=tuple(glyphs),
        spans=tuple((first_index + a, first_index + b) for a, b in spans),
    )


def read_box(path: str | Path, first: int, count: int, rect: Rect, fps: float, *,
             size: tuple[int, int] | None = None, colour: bool = False) -> np.ndarray:
    """Decode ``count`` frames of a rectangle, starting at frame ``first``.

    ``size`` (width, height) scales the picture first, so a render at another
    size is read in source pixels. Shape (T, h, w) or (T, h, w, 3), uint8. Fewer
    frames come back at the end of the file. Raises InkError when ffmpeg fails.
    """
    from duckcore import media

    x0, y0, x1, y1 = rect
    width, height = x1 - x0, y1 - y0
    channels = 3 if colour else 1
    shape = (0, height, width, 3) if colour else (0, height, width)
    if width < 2 or height < 2 or count <= 0:
        return np.zeros(shape, dtype=np.uint8)
    # Half a frame early: the first frame returned is exactly ``first``.
    seek = max(0.0, (first - 0.5) / fps)
    chain = [f"fps={fps:.6f}"]
    if size:
        chain.append(f"scale={int(size[0])}:{int(size[1])}")
    # Format first: a crop on subsampled video rounds odd offsets and sizes,
    # and the frames would come back in another shape than asked for.
    chain.append("format=rgb24" if colour else "format=gray")
    chain.append(f"crop={width}:{height}:{x0}:{y0}:exact=1")
    command = [
        media.ffmpeg(), "-v", "error", "-nostdin",
        "-ss", f"{seek:.6f}", "-i", str(path), "-an", "-sn",
        "-vf", ",".join(chain), "-frames:v", str(int(count)), "-f", "rawvideo", "-",
    ]
    try:
        done = subprocess.run(command, capture_output=True, check=False)
    except OSError as exc:
        raise InkError(f"The frames could not be read: {exc}") from exc
    step = width * height * channels
    frames = len(done.stdout) // step
    if frames <= 0:
        if done.returncode != 0:
            raise InkError(done.stderr.decode("utf-8", "replace").strip()[:200] or "ffmpeg failed")
        return np.zeros(shape, dtype=np.uint8)
    data = np.frombuffer(done.stdout[:frames * step], dtype=np.uint8)
    return data.reshape((frames, height, width, 3) if colour else (frames, height, width))


def build(source: str | Path, rect: Rect, *, start: float, end: float, fps: float,
          reach: float = REACH, size: tuple[int, int] | None = None) -> Ink | None:
    """The ink of the line that a range ``[start, end)`` of the source points at.

    ``size`` reads the source scaled to (width, height); ``rect`` is then in
    those pixels.
    """
    fps = float(fps)
    low = first_frame(start, fps)
    high = first_frame(end, fps) - 1
    if fps <= 0 or high < low:
        return None
    while True:
        margin = max(4, int(round(reach * fps)))
        first = max(0, low - margin)
        wanted = high + margin - first + 1
        frames = read_box(source, first, wanted, rect, fps, size=size)
        if frames.shape[0] <= low - first:
            return None
        found = analyse(
            strong(frames), (low - first, high - first), first_index=first, rect=rect, fps=fps,
            open_high=frames.shape[0] >= wanted,
        )
        if found is None or found.settled or reach >= REACH_MOST:
            return found
        reach *= 2.0


def presence(edges: np.ndarray, ink: Ink) -> np.ndarray:
    """Per frame and glyph, the share of stroke pixels with a strong edge. (T, G)."""
    out = np.zeros((edges.shape[0], max(1, len(ink.glyphs))), dtype=np.float32)
    spans = ink.glyphs or ((0, ink.mask.shape[1]),)
    for index, (x0, x1) in enumerate(spans):
        part = ink.mask[:, x0:x1]
        total = int(part.sum())
        if total:
            out[:, index] = edges[:, :, x0:x1][:, part].mean(axis=1)
    return out


def onset_moments(source: str | Path, *, width: int = 540, height: int = 960,
                  fps: float = 30.0, edge: float = 36.0,
                  stay: int = 4, band_min: int = 150) -> list[float]:
    """Frames where strokes appear and then stay: a candidate line start.

    A full-rate scan at 540 px. It is used to look where Check's 4 fps pass
    cannot see, not to prove text.
    """
    from duckcore import media

    command = [
        media.ffmpeg(), "-v", "error", "-nostdin", "-i", str(source),
        "-vf", f"scale={width}:{height},format=gray", "-f", "rawvideo", "-",
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE)
    size = width * height
    frames: list[np.ndarray] = []
    index = 0
    found: list[float] = []
    try:
        while True:
            data = process.stdout.read(size)
            if len(data) < size:
                break
            picture = np.frombuffer(data, dtype=np.uint8).reshape(height, width)
            frames.append(gradient(picture) > edge)
            frames = frames[-(stay + 3):]
            if len(frames) == stay + 3:
                after = np.logical_and.reduce(frames[3:])
                before = dilate(frames[0] | frames[1] | frames[2], 1)
                rows = (after & ~before).sum(axis=1)
                band = np.convolve(rows, np.ones(30), "same")
                if band.size and int(band.max()) >= band_min:
                    found.append((index - stay + 1) / fps)
            index += 1
    finally:
        process.kill()
        process.wait(timeout=5)
    # One moment per 0.2 s burst.
    moments: list[float] = []
    for time in found:
        if not moments or time - moments[-1] > 0.2:
            moments.append(round(time, 3))
    return moments
