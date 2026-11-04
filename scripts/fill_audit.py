#!/usr/bin/env python3
"""Look at a finished AI fill clip: what changed, compared with its source.

Reads one clip from ``jobs/<id>/fill/`` and the source it was filled from, and
reports four things frame by frame:

- changes outside the text (smeared objects, and any change outside the boxes);
- flicker in the filled area, against how much the background really moves;
- text left behind (not filled at all, or a ghost of it);
- colour drift (the fill against its surroundings, and the whole clip's shift).

It only reads existing media. It generates nothing and writes nothing, and the
numbers support the founder's review rather than replace it. Run it only on
clips the founder names.

The clip must be a fill clip, which keeps the source's size and frame rate. A
finished render has been cropped and moved, so it cannot be compared pixel by
pixel, and this script refuses it.

Usage:
    python3 scripts/fill_audit.py CLIP SOURCE --box 0.1,0.8,0.8,0.05
    python3 scripts/fill_audit.py CLIP SOURCE --layers edit.json --start 12.5
    python3 scripts/fill_audit.py CLIP SOURCE --box 0.1,0.8,0.8,0.05 --json

``--start`` is the clip's time in the source. Without it the script finds it by
matching the picture outside the boxes.

Exit status: 0 report written, 2 the two files cannot be compared. Lines marked
"look" are worth checking by eye. They are not a pass or a fail.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable, Iterator

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pipeline  # noqa: E402
from textfill import mask as masks  # noqa: E402

# Re-encoding moves pixels a little everywhere, so a pixel counts as changed
# only past this many 8-bit levels in its worst channel.
CHANGE_LEVEL = 16
# A frame's share of changed pixels below this is encoder noise.
NOISE_SHARE = 0.001
# Text kept: 1.0 means the text is still fully there, 0.0 means nothing of its
# shape is left.
LEFTOVER_LEVEL = 0.15
# Text kept above this means the frame was not filled at all, not a weak ghost.
UNFILLED_LEVEL = 0.8
# Levels per frame the fill may move beyond what the background moves.
FLICKER_LEVEL = 6.0
# Levels of mean change outside the boxes that mean a scene cut.
SCENE_CUT_LEVEL = 30.0
# Levels between the fill and what surrounds it, or across the whole clip.
COLOUR_LEVEL = 6.0
# Width of the surroundings the fill is compared with, in pixels.
SURROUND_PX = 12
# Share of changes outside the text, and outside the boxes, worth a look.
OUTSIDE_TEXT_LOOK = 0.25
OUTSIDE_BOXES_LOOK = 0.02
# Thumbnails used to find where the clip sits in the source.
THUMB_WIDTH = 64
# Above this mean difference the clip did not come from this source.
MATCH_LEVEL = 12.0

Rect = masks.Rect
RectsFor = Callable[[int], list[Rect]]


class AuditError(RuntimeError):
    """The two files cannot be compared."""


def _grown(rects: Iterable[Rect], by: int, width: int, height: int) -> list[Rect]:
    return [
        (max(0, x0 - by), max(0, y0 - by), min(width, x1 + by), min(height, y1 + by))
        for x0, y0, x1, y1 in rects
    ]


def _text_grow(width: int) -> int:
    """The same growth the fill gives the text, so both mean the same pixels."""
    return max(masks.TEXT_GROW_MIN_PX, int(round(width * masks.TEXT_GROW_RATIO)))


def find_text(frame: np.ndarray, rects: Iterable[Rect], grow: int) -> tuple[np.ndarray, bool]:
    """Text pixels of the source frame, and whether every box could be read."""
    height, width = frame.shape[:2]
    text = np.zeros((height, width), dtype=bool)
    certain = True
    for x0, y0, x1, y1 in set(rects):
        if x1 <= x0 or y1 <= y0:
            continue
        found = masks.text_in_region(frame[y0:y1, x0:x1], grow)
        if found is None:
            certain = False
            continue
        text[y0:y1, x0:x1] |= found
    return text, certain


def text_kept(source: np.ndarray, clip: np.ndarray, text: np.ndarray) -> float | None:
    """How much of the text's shape is still in the clip, from 0 to 1.

    The slope of the clip's pixels against the source's, over the text and the
    ring around it. Text left as it was gives 1, a ghost gives its strength, and
    a clean fill gives about 0. A busy background does not raise it, because it
    measures the text's own pattern. None when the source has no contrast there.
    """
    if not text.any():
        return None
    before = source[text].astype(np.float64).ravel()
    after = clip[text].astype(np.float64).ravel()
    before -= before.mean()
    after -= after.mean()
    energy = float((before * before).sum())
    if energy < 1.0:
        return None
    return max(0.0, float((before * after).sum()) / energy)


def changed_pixels(source: np.ndarray, clip: np.ndarray) -> np.ndarray:
    gap = np.abs(source.astype(np.int16) - clip.astype(np.int16)).max(axis=2)
    return gap > CHANGE_LEVEL


def _motion(a: np.ndarray, b: np.ndarray, where: np.ndarray) -> float | None:
    if not where.any():
        return None
    return float(np.abs(a[where].astype(np.int16) - b[where].astype(np.int16)).mean())


def _time_ranges(frames: list[int], start: float, fps: float) -> list[dict]:
    """Bad frames as source-time ranges, so they can be found in the video."""
    ranges: list[dict] = []
    for index in sorted(frames):
        at = start + index / fps
        if ranges and index == ranges[-1]["last"] + 1:
            ranges[-1]["end"] = round(at + 1 / fps, 3)
            ranges[-1]["last"] = index
        else:
            ranges.append({"start": round(at, 3), "end": round(at + 1 / fps, 3), "last": index})
    return [{"start": row["start"], "end": row["end"]} for row in ranges]


def _share(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def _spread(values: list[float]) -> dict | None:
    if not values:
        return None
    return {
        "median": round(float(np.median(values)), 2),
        "p95": round(float(np.percentile(values, 95)), 2),
        "max": round(float(np.max(values)), 2),
    }


def audit(
    source_frames: Iterable[np.ndarray],
    clip_frames: Iterable[np.ndarray],
    rects_for: RectsFor,
    *,
    fps: float,
    start: float = 0.0,
) -> dict:
    """Compare two streams of same-sized RGB frames, keeping only two in memory."""
    frames = uncertain = 0
    changed_total = changed_outside_boxes = 0
    changed_in_boxes = changed_outside_text = changed_on_text = 0
    no_text_frames = no_text_changed = 0
    text_frames = 0
    left_unfilled: list[int] = []
    left_ghost: list[int] = []
    kept_values: list[float] = []
    flicker_values: list[float] = []
    flicker_frames: list[int] = []
    scene_cuts: list[int] = []
    fill_colour: list[np.ndarray] = []
    whole_colour_sum = np.zeros(3, dtype=np.float64)
    whole_colour_frames = 0
    previous: dict | None = None

    for index, (source, clip) in enumerate(zip(source_frames, clip_frames)):
        height, width = source.shape[:2]
        frames += 1
        rects = rects_for(index)
        grow = _text_grow(width)
        # The fill's feathered edge reaches past its rectangle.
        area = masks.rasterize(_grown(rects, masks.FEATHER_PX, width, height), width, height).astype(bool)
        changed = changed_pixels(source, clip)
        text, certain = find_text(source, rects, grow)

        changed_total += int(changed.sum())
        changed_outside_boxes += int((changed & ~area).sum())
        outside = ~area
        if outside.any():
            shift = clip[outside].astype(np.float64).mean(axis=0) - source[outside].astype(np.float64).mean(axis=0)
            whole_colour_sum += shift
            whole_colour_frames += 1

        if rects and certain:
            in_area = changed & area
            changed_in_boxes += int(in_area.sum())
            changed_outside_text += int((in_area & ~text).sum())
            changed_on_text += int((in_area & text).sum())
            if text.any():
                text_frames += 1
                kept = text_kept(source, clip, text)
                if kept is not None:
                    kept_values.append(kept)
                    if kept >= UNFILLED_LEVEL:
                        left_unfilled.append(index)
                    elif kept >= LEFTOVER_LEVEL:
                        left_ghost.append(index)
            else:
                no_text_frames += 1
                if in_area.sum() > NOISE_SHARE * max(1, int(area.sum())):
                    no_text_changed += 1
        elif rects:
            uncertain += 1

        filled = changed & area
        if rects and filled.sum() > NOISE_SHARE * max(1, int(area.sum())):
            surround = masks.rasterize(_grown(rects, SURROUND_PX, width, height), width, height).astype(bool)
            surround &= ~changed & ~text
            if surround.any():
                fill_colour.append(
                    clip[filled].astype(np.float64).mean(axis=0) - clip[surround].astype(np.float64).mean(axis=0)
                )

        if previous is not None:
            cut = _motion(source, previous["source"], ~(area | previous["area"]))
            if cut is not None and cut > SCENE_CUT_LEVEL:
                scene_cuts.append(index)
            else:
                moved = (changed | previous["changed"]) & (area | previous["area"])
                if moved.sum() > NOISE_SHARE * max(1, int(area.sum())):
                    background = area & previous["area"] & ~text & ~previous["text"] & ~moved
                    if background.sum() < max(1, moved.sum() // 10):
                        background = ~(area | previous["area"])
                    fill_motion = _motion(clip, previous["clip"], moved)
                    real_motion = _motion(source, previous["source"], background)
                    if fill_motion is not None:
                        excess = max(0.0, fill_motion - (real_motion or 0.0))
                        flicker_values.append(excess)
                        if excess > FLICKER_LEVEL:
                            flicker_frames.append(index)
        previous = {"source": source, "clip": clip, "area": area, "changed": changed, "text": text}

    if not frames:
        raise AuditError("No frames could be read from these files.")

    colour_rows = np.array(fill_colour) if fill_colour else np.zeros((0, 3))
    fill_rgb = [round(float(value), 2) for value in np.median(colour_rows, axis=0)] if len(colour_rows) else None
    whole_rgb = [round(float(value), 2) for value in whole_colour_sum / max(1, whole_colour_frames)]
    return {
        "frames": frames,
        "fps": fps,
        "start": round(start, 3),
        "uncertain_frames": uncertain,
        "changes": {
            "changed_pixels": changed_total,
            "outside_boxes": _share(changed_outside_boxes, changed_total),
            "outside_text": _share(changed_outside_text, changed_in_boxes),
            "frames_without_text": no_text_frames,
            "frames_without_text_changed": no_text_changed,
        },
        "flicker": {
            "levels_beyond_background": _spread(flicker_values),
            "scene_cuts_skipped": [round(start + at / fps, 3) for at in scene_cuts],
            "spikes": _time_ranges(flicker_frames, start, fps),
            "spike_frames": len(flicker_frames),
        },
        "leftover": {
            "frames_with_text": text_frames,
            "text_kept": _spread(kept_values),
            "unfilled_frames": len(left_unfilled),
            "unfilled": _time_ranges(left_unfilled, start, fps),
            "ghost_frames": len(left_ghost),
            "ghost": _time_ranges(left_ghost, start, fps),
        },
        "colour": {
            "fill_vs_surroundings_rgb": fill_rgb,
            "outside_boxes_rgb": whole_rgb,
        },
    }


def looks(report: dict) -> list[str]:
    """What is worth checking by eye. Empty means the numbers raise nothing."""
    out = []
    changes, flicker = report["changes"], report["flicker"]
    leftover, colour = report["leftover"], report["colour"]
    if (changes["outside_boxes"] or 0) > OUTSIDE_BOXES_LOOK:
        out.append("changes outside the boxes")
    if (changes["outside_text"] or 0) > OUTSIDE_TEXT_LOOK:
        out.append("changes outside the text, so objects may smear")
    if changes["frames_without_text_changed"]:
        out.append("frames with no text were changed")
    if flicker["spike_frames"]:
        out.append("flicker in the fill")
    if leftover["unfilled_frames"]:
        out.append("frames left with their text")
    if leftover["ghost_frames"]:
        out.append("ghosts of the text")
    fill_rgb = colour["fill_vs_surroundings_rgb"] or [0.0]
    if max(abs(value) for value in fill_rgb) > COLOUR_LEVEL:
        out.append("the fill's colour differs from its surroundings")
    if max(abs(value) for value in colour["outside_boxes_rgb"]) > COLOUR_LEVEL:
        out.append("the whole clip's colour shifted")
    return out


def _percent(value: float | None) -> str:
    return "not measured" if value is None else f"{value * 100:.1f}%"


def _ranges_text(rows: list[dict]) -> str:
    if not rows:
        return ""
    shown = ", ".join(f"{row['start']:.2f}-{row['end']:.2f}s" for row in rows[:8])
    more = f" and {len(rows) - 8} more" if len(rows) > 8 else ""
    return f" at {shown}{more}"


def _spread_text(values: dict | None) -> str:
    if not values:
        return "not measured"
    return f"median {values['median']}, p95 {values['p95']}, max {values['max']}"


def report_text(report: dict) -> str:
    changes, flicker = report["changes"], report["flicker"]
    leftover, colour = report["leftover"], report["colour"]
    lines = [
        f"Frames: {report['frames']} at {report['fps']} fps, from {report['start']:.3f} s in the source.",
        f"Frames skipped as too busy to read: {report['uncertain_frames']}.",
        "",
        "Changes",
        f"  Outside the boxes: {_percent(changes['outside_boxes'])} of all changed pixels.",
        f"  Outside the text, inside the boxes: {_percent(changes['outside_text'])}.",
        f"  Frames with no text that were changed: {changes['frames_without_text_changed']}"
        f" of {changes['frames_without_text']}.",
        "",
        "Flicker (levels per frame, beyond what the background moves)",
        f"  {_spread_text(flicker['levels_beyond_background'])}.",
        f"  Spikes over {FLICKER_LEVEL:g}: {flicker['spike_frames']}{_ranges_text(flicker['spikes'])}.",
        f"  Scene cuts skipped: {len(flicker['scene_cuts_skipped'])}.",
        "",
        "Leftover text (1 means still fully there, 0 means gone)",
        f"  {_spread_text(leftover['text_kept'])}, over {leftover['frames_with_text']} frames with text.",
        f"  Left unfilled: {leftover['unfilled_frames']}{_ranges_text(leftover['unfilled'])}.",
        f"  Ghost: {leftover['ghost_frames']}{_ranges_text(leftover['ghost'])}.",
        "",
        "Colour (levels, red green blue)",
        f"  Fill against its surroundings: {colour['fill_vs_surroundings_rgb'] or 'not measured'}.",
        f"  Clip against source, outside the boxes: {colour['outside_boxes_rgb']}.",
        "",
    ]
    found = looks(report)
    if found:
        lines.extend(f"look: {item}" for item in found)
    else:
        lines.append("Nothing stands out in the numbers. Still watch the clip.")
    return "\n".join(lines)


def read_frames(
    path: str,
    *,
    start: float,
    duration: float,
    fps: float,
    width: int,
    height: int,
    pix_fmt: str = "rgb24",
    ffmpeg: str = "ffmpeg",
) -> Iterator[np.ndarray]:
    """Decode frames exactly as the fill does, so frame numbers line up."""
    channels = 3 if pix_fmt == "rgb24" else 1
    size = width * height * channels
    shape = (height, width, 3) if channels == 3 else (height, width)
    proc = subprocess.Popen(
        [
            ffmpeg, "-v", "error", "-nostdin",
            "-ss", f"{start:.6f}", "-t", f"{duration:.6f}", "-i", path,
            "-an", "-sn",
            "-vf", f"fps={fps:.6f},scale={width}:{height}",
            "-f", "rawvideo", "-pix_fmt", pix_fmt, "pipe:1",
        ],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    try:
        while True:
            data = proc.stdout.read(size)
            if not data or len(data) < size:
                return
            yield np.frombuffer(data, dtype=np.uint8).reshape(shape)
    finally:
        proc.kill()
        proc.stdout.close()
        proc.wait()


def find_start(source: np.ndarray, clip: np.ndarray, keep: np.ndarray) -> tuple[int, float]:
    """The source frame the clip starts on, from gray thumbnails.

    Compares three clip frames with every position, on the pixels outside the
    boxes (``keep``), which the fill leaves alone. Returns (frame, mean gap).
    """
    total, count = len(source), len(clip)
    if count > total:
        raise AuditError("The clip is longer than this source, so it did not come from it.")
    if not keep.any():
        raise AuditError("The boxes cover the whole frame. Give the clip's time with --start.")
    positions = total - count + 1
    gaps = np.zeros(positions, dtype=np.float64)
    picks = sorted({count // 4, count // 2, (3 * count) // 4})
    for pick in picks:
        reference = clip[pick][keep].astype(np.int16)
        for offset in range(positions):
            gaps[offset] += float(np.abs(source[offset + pick][keep].astype(np.int16) - reference).mean())
    gaps /= len(picks)
    best = int(gaps.argmin())
    return best, float(gaps[best])


def parse_box(text: str) -> dict:
    try:
        x, y, w, h = (float(value) for value in text.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("A box is x,y,w,h, each from 0 to 1.") from exc
    if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1):
        raise argparse.ArgumentTypeError("A box is x,y,w,h, each from 0 to 1.")
    return {"box": {"x": x, "y": y, "w": w, "h": h}}


def load_layers(path: str) -> list[dict]:
    """AI fill layers from an Edit file, or a plain list of Clean layers."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    layers = data.get("clean") if isinstance(data, dict) else data
    if not isinstance(layers, list):
        raise AuditError("That file has no list of Clean layers.")
    return [layer for layer in layers if isinstance(layer, dict) and layer.get("kind", "fill") == "fill"]


def _start_from_picture(clip: str, source: str, meta: dict, layers: list[dict], duration: float, ffmpeg: str) -> float:
    fps, width, height = meta["fps"], meta["width"], meta["height"]
    thumb_w = THUMB_WIDTH
    thumb_h = max(2, int(round(thumb_w * height / width)))
    size = {"fps": fps, "width": thumb_w, "height": thumb_h, "pix_fmt": "gray", "ffmpeg": ffmpeg}
    source_rows = np.stack(list(read_frames(source, start=0.0, duration=float(meta["duration"]) + 1.0, **size)))
    clip_rows = np.stack(list(read_frames(clip, start=0.0, duration=duration + 1.0, **size)))
    rects = [masks.layer_rect(layer, thumb_w, thumb_h) for layer in layers]
    keep = ~masks.rasterize(_grown(rects, 1, thumb_w, thumb_h), thumb_w, thumb_h).astype(bool)
    frame, gap = find_start(source_rows, clip_rows, keep)
    if gap > MATCH_LEVEL:
        raise AuditError("This clip does not match the source. Check the files, or give --start.")
    return frame / fps


def run(
    clip: str,
    source: str,
    layers: list[dict],
    *,
    start: float | None = None,
    ffmpeg: str = "ffmpeg",
) -> dict:
    clip_meta = pipeline.probe(clip)
    source_meta = pipeline.probe(source)
    width, height = int(clip_meta["width"]), int(clip_meta["height"])
    if (width, height) != (int(source_meta["width"]), int(source_meta["height"])):
        raise AuditError(
            f"The clip is {width}x{height} and the source is "
            f"{source_meta['width']}x{source_meta['height']}. This script reads AI fill "
            "clips from jobs/<id>/fill/, which keep the source's size. A finished render "
            "has been cropped, so it cannot be compared pixel by pixel."
        )
    fps = float(clip_meta["fps"])
    duration = float(clip_meta["duration"])
    if start is None:
        start = _start_from_picture(clip, source, {**source_meta, "fps": fps}, layers, duration, ffmpeg)
    frames = int(round(duration * fps))
    table = masks.frame_rects(
        layers, start=start, fps=fps, frames=frames + int(fps) + 2, width=width, height=height,
    )
    size = {"fps": fps, "width": width, "height": height, "ffmpeg": ffmpeg}
    report = audit(
        read_frames(source, start=start, duration=duration, **size),
        read_frames(clip, start=0.0, duration=duration, **size),
        lambda index: table[min(index, len(table) - 1)],
        fps=fps,
        start=start,
    )
    report["clip"] = str(clip)
    report["source"] = str(source)
    report["look"] = looks(report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Look at a finished AI fill clip against its source.")
    parser.add_argument("clip", help="a fill clip from jobs/<id>/fill/")
    parser.add_argument("source", help="the video it was filled from")
    parser.add_argument("--box", action="append", type=parse_box, default=[], help="x,y,w,h from 0 to 1; repeat for more")
    parser.add_argument("--layers", help="an Edit file or a list of Clean layers, for their boxes, strokes and times")
    parser.add_argument("--start", type=float, help="the clip's time in the source, in seconds")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)
    try:
        layers = [*args.box, *(load_layers(args.layers) if args.layers else [])]
        if not layers:
            raise AuditError("Say where the text is, with --box or --layers.")
        report = run(args.clip, args.source, layers, start=args.start)
    except (AuditError, pipeline.PipelineError, OSError, ValueError) as exc:
        print(f"Cannot compare: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2) if args.json else report_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
