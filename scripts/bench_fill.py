#!/usr/bin/env python3
"""Measure AI text fill against ground truth, instead of eyeballing it.

For each sampled frame this tool takes a *clean* source frame (a time no
tracklet covers), paints a caption that looks like the real burn-in, runs the
fill path the render uses, and compares the result with the untouched frame.
That gives a number, so a change to the mask, the context or the model input
can be accepted or rejected on evidence.

Usage::

    python3 scripts/bench_fill.py --project prj_... --frames 10
    python3 scripts/bench_fill.py --project prj_... --variants baseline,wide,upscale
    python3 scripts/bench_fill.py --project prj_... --device coreml
    python3 scripts/bench_fill.py --project prj_... --device gpu --model ~/models/big-lama.pt

``--device`` picks where LaMa runs: ``cpu`` (ONNX Runtime, the shipped path),
``coreml`` (ONNX Runtime CoreML provider, same file) or ``gpu`` (PyTorch on MPS,
needs torch and ``big-lama.pt``). Run one device per process so load time and
peak memory are that device's own. The first fill is a warm-up and is timed
apart from the rest.

Nothing is written under the project; output goes to ``--out``.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from skimage.metrics import structural_similarity

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from duckcore import ink as ink_mod  # noqa: E402
from duckcore.engine.textfill import lama as lama_mod  # noqa: E402
from duckcore.engine.textfill import mask as masks  # noqa: E402
from duckcore.engine.textfill.lama import LamaFiller  # noqa: E402

FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"
DEFAULT_DATA = (
    Path.home()
    / "Library/Containers/com.ducksuite.app/Data/Library/Application Support/DuckSuite"
)


def _ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    bundled = ROOT / "build/DuckSuite-Xcode.app/Contents/Helpers/ffmpeg"
    return str(bundled)


DEVICES = ("cpu", "coreml", "gpu")


def _make_filler(device: str, model: Path):
    """The filler for a device. Each has the same ``fill(area, mask)``."""
    if device == "gpu":
        from duckcore.engine.textfill.torch_fill import LamaGpuFiller

        return LamaGpuFiller(model)
    # lama._providers reads this when the session is made.
    os.environ["VIBECUT_FILL_LAMA_PROVIDER"] = "coreml" if device == "coreml" else "cpu"
    return LamaFiller(model)


def _peak_mb() -> float:
    import resource

    # macOS reports bytes. Memory the GPU holds outside the process is not in it.
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 ** 2, 1)


def _model_path(data_root: Path, device: str = "cpu") -> Path:
    name = "big-lama.pt" if device == "gpu" else "lama_fp32.onnx"
    override = os.environ.get("DUCK_FILL_MODELS")
    if override:
        return Path(override) / name
    if device == "gpu":
        return data_root / "models/fill" / name
    bundled = ROOT / "build/DuckSuite-Xcode.app/Contents/Resources/base-models/lama_fp32.onnx"
    if bundled.is_file():
        return bundled
    return data_root / "models/fill/lama_fp32.onnx"


def _free_times(report: dict, duration: float, count: int,
                windows: list[tuple[float, float]] | None = None) -> list[float]:
    """Times where no tracklet is on screen, spread over the video or the windows."""
    spans = []
    for tracklet in report.get("tracklets") or []:
        for item in tracklet.get("ranges") or []:
            spans.append((float(item["start"]), float(item["end"])))
    spans.sort()
    margin = 0.6
    windows = [(max(0.0, a), min(duration, b)) for a, b in (windows or []) if b > a]
    if not windows:
        windows = [(margin + 1.0, duration - margin)]
    candidates = []
    step = max(0.5, duration / 400.0)
    for window_start, window_end in windows:
        at = window_start + margin / 2
        while at < window_end - margin / 2:
            blocked = any(start - margin < at < end + margin for start, end in spans)
            if not blocked:
                candidates.append(round(at, 3))
            at += step
    if not candidates:
        return []
    if len(candidates) <= count:
        return candidates
    # Spread the picks over the list, one pass, so every window contributes.
    picks = np.linspace(0, len(candidates) - 1, count).round().astype(int)
    return [candidates[index] for index in sorted(set(picks.tolist()))]


def _grab(video: str, at: float, out: Path) -> Image.Image:
    subprocess.run(
        [_ffmpeg(), "-y", "-v", "error", "-ss", f"{at:.3f}", "-i", video,
         "-frames:v", "1", "-q:v", "2", str(out)],
        check=True, capture_output=True,
    )
    return Image.open(out).convert("RGB")


def _paint(image: Image.Image, box: dict, text: str, stroke_ratio: float = 0.055) -> Image.Image:
    """Draw a caption in the style of the source burn-in, inside ``box``.

    The line is shrunk until it fits the box, because a real caption is sized
    to its box. A line wider than the mask would leak into the benchmark as
    residue the product never produces.
    """
    width, height = image.size
    x = float(box["x"]) * width
    y = float(box["y"]) * height
    w = float(box["w"]) * width
    h = float(box["h"]) * height
    draw = ImageDraw.Draw(image)
    limit = w * 0.98
    size = max(8, int(round(h * 0.80)))
    stroke = max(1, int(round(h * stroke_ratio)))
    for _attempt in range(24):
        font = ImageFont.truetype(FONT, size)
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
        tw, th = right - left, bottom - top
        if tw <= limit or size <= 8:
            break
        size = max(8, int(size * 0.94))
    cx, cy = x + w / 2.0, y + h / 2.0
    draw.text(
        (cx - tw / 2.0 - left, cy - th / 2.0 - top),
        text, font=font, fill=(255, 255, 255), stroke_width=stroke,
        stroke_fill=(0, 0, 0),
    )
    return image


def _fill(filler: LamaFiller, work: np.ndarray, hole: np.ndarray, upscale: float) -> np.ndarray:
    """Fill ``hole`` in ``work``, optionally running the model at a larger size."""
    if upscale <= 1.0:
        filled = filler.fill(work, hole)
        out = work.copy()
        out[hole] = filled[hole]
        return out
    height, width = work.shape[:2]
    big_w, big_h = int(width * upscale), int(height * upscale)
    big_image = np.asarray(
        Image.fromarray(work).resize((big_w, big_h), Image.LANCZOS)
    )
    big_mask = np.asarray(
        Image.fromarray(hole.astype(np.uint8) * 255).resize((big_w, big_h), Image.NEAREST)
    ) > 127
    big_filled = filler.fill(big_image, big_mask)
    back = np.asarray(
        Image.fromarray(big_filled).resize((width, height), Image.LANCZOS)
    )
    out = work.copy()
    out[hole] = back[hole]
    return out


def _metrics(region_truth: np.ndarray, region_got: np.ndarray, hole_px: int) -> dict:
    diff = region_truth.astype(np.float32) - region_got.astype(np.float32)
    mse = float(np.mean(diff ** 2)) if diff.size else 0.0
    psnr = 99.0 if mse <= 1e-9 else 10.0 * math.log10(255.0 ** 2 / mse)
    try:
        ssim = float(structural_similarity(
            region_truth, region_got, channel_axis=2, data_range=255,
        ))
    except ValueError:
        ssim = float("nan")
    return {
        "psnr": round(psnr, 2),
        "ssim": round(ssim, 4),
        "mae": round(float(np.mean(np.abs(diff))), 2),
        "hole_px": int(hole_px),
    }


VARIANTS: dict[str, dict] = {
    # The shipped defaults: a fill hole tight on the outline, normal context.
    "baseline": {},
    # What the app shipped before the benchmark: a 0.06 pad and a 0.18 shadow.
    "oldpads": {"FILL_PAD_RATIO": 0.06, "FILL_SHADOW_RATIO": 0.18},
    # Rejected in the sweep: a smaller or larger work area around the line.
    "tight": {"CONTEXT_MIN_PX": 48, "CONTEXT_RATIO": 0.25},
    "wide": {"CONTEXT_MIN_PX": 192, "CONTEXT_RATIO": 1.0},
    # Loop 7's hole: the painted caption's own strokes, grown 6 px, not its box.
    "ink": {"INK": True},
    # Rejected: resampling the model input up before the fill.
    "upscale": {"UPSCALE": 1.5},
    "upscale2": {"UPSCALE": 2.0},
}


def _apply(masks_module, variant: dict) -> None:
    masks_module.CONTEXT_MIN_PX = int(variant.get("CONTEXT_MIN_PX", 96))
    masks_module.CONTEXT_RATIO = float(variant.get("CONTEXT_RATIO", 0.5))
    masks_module.FILL_PAD_RATIO = float(variant.get("FILL_PAD_RATIO", 0.04))
    masks_module.FILL_SHADOW_RATIO = float(variant.get("FILL_SHADOW_RATIO", 0.10))


def run(
    data_root: Path, project: str, count: int, variants: list[str], out: Path,
    stroke: float = 0.055, device: str = "cpu", model: Path | None = None,
    windows: list[tuple[float, float]] | None = None,
) -> dict:
    project_dir = data_root / "projects" / project
    check = json.loads((project_dir / "check.json").read_text())
    report = check["report"]
    source = check["source"]["path"]
    duration = float(check["source"]["duration"])
    width, height = int(check["source"]["width"]), int(check["source"]["height"])

    captions = [
        item for item in report.get("tracklets") or []
        if item.get("kind") in {"subtitle", "title"} and item.get("text_sample")
    ]
    if not captions:
        raise SystemExit("No caption tracklets to borrow text and boxes from.")
    times = _free_times(report, duration, count, windows=windows)
    if not times:
        raise SystemExit("No text-free frames found.")

    model = Path(model).expanduser() if model else _model_path(data_root, device)
    if not model.is_file():
        raise SystemExit(f"Model file not found: {model}")
    started_load = time.perf_counter()
    filler = _make_filler(device, model)
    load_seconds = round(time.perf_counter() - started_load, 2)
    first_seconds = None
    temp = Path(tempfile.mkdtemp(prefix="fillbench-"))
    out.mkdir(parents=True, exist_ok=True)
    results: dict[str, list[dict]] = {name: [] for name in variants}
    sheets: dict[str, list] = {name: [] for name in variants}

    for index, at in enumerate(times):
        frame = _grab(source, at, temp / f"f{index}.jpg")
        caption = captions[index % len(captions)]
        box = caption["box"]
        test = _paint(frame.copy(), box, str(caption["text_sample"])[:14], stroke)
        truth = np.asarray(frame)
        dirty = np.asarray(test)

        layer = {
            "box": box,
            "tracklet_id": "bench",
            "large": bool(caption.get("large")),
        }
        truth_full = np.asarray(frame)
        dirty_full = np.asarray(test)
        _apply(masks, {})
        rect_ref = masks.layer_rect(layer, width, height)
        ry0, ry1 = max(0, rect_ref[1]), min(height, rect_ref[3])
        rx0, rx1 = max(0, rect_ref[0]), min(width, rect_ref[2])

        for name in variants:
            variant = VARIANTS[name]
            _apply(masks, variant)
            rect_n = masks.layer_rect(layer, width, height)
            if variant.get("INK"):
                # The caption's own pixels, the way loop 7 builds a line's hole.
                painted = np.any(
                    np.abs(dirty_full.astype(np.int16) - truth_full.astype(np.int16)) > 8,
                    axis=2,
                )
                inside = np.zeros_like(painted)
                inside[rect_n[1]:rect_n[3], rect_n[0]:rect_n[2]] = True
                hole = ink_mod.dilate(painted & inside, 6)
                rows_y, cols_x = np.where(hole)
                if not len(cols_x):
                    continue
                rect_n = (
                    int(cols_x.min()), int(rows_y.min()),
                    int(cols_x.max()) + 1, int(rows_y.max()) + 1,
                )
            area_n = masks.lama_area([rect_n], width, height)
            x0, y0, x1, y1 = area_n
            work = dirty_full[y0:y1, x0:x1]
            local_n = (
                hole[y0:y1, x0:x1] if variant.get("INK") else masks.rasterize(
                    [(rect_n[0] - x0, rect_n[1] - y0, rect_n[2] - x0, rect_n[3] - y0)],
                    x1 - x0, y1 - y0,
                )
            )
            started = time.perf_counter()
            filled = _fill(filler, work, local_n, float(variant.get("UPSCALE", 1.0)))
            elapsed = time.perf_counter() - started
            if first_seconds is None:
                first_seconds = round(elapsed, 2)
            frame_out = dirty_full.copy()
            frame_out[y0:y1, x0:x1][local_n] = filled[local_n]
            # Score one fixed region for every variant: the baseline hole. A
            # smaller hole that leaves an outline behind scores worse here,
            # which a hole-only score would hide.
            item = _metrics(
                truth_full[ry0:ry1, rx0:rx1],
                frame_out[ry0:ry1, rx0:rx1],
                int(local_n.sum()),
            )
            item.update({"t": at, "seconds": round(elapsed, 2), "variant": name})
            results[name].append(item)
            sheets[name].append((at, truth_full[y0:y1, x0:x1], work, filled, local_n))

    _apply(masks, {})
    shutil.rmtree(temp, ignore_errors=True)

    summary = {}
    for name, rows in results.items():
        summary[name] = {
            "psnr": round(float(np.mean([r["psnr"] for r in rows])), 2),
            "ssim": round(float(np.mean([r["ssim"] for r in rows])), 4),
            "mae": round(float(np.mean([r["mae"] for r in rows])), 2),
            "seconds": round(float(np.mean([r["seconds"] for r in rows])), 2),
            "frames": len(rows),
        }
    # The very first fill pays for warm-up; the rest say what a render pays.
    steady = [r["seconds"] for rows in results.values() for r in rows][1:]
    summary["_run"] = {
        "device": device,
        "provider": getattr(filler, "provider", device),
        "model": model.name,
        "load_seconds": load_seconds,
        "first_fill_seconds": first_seconds,
        "steady_fill_seconds": round(float(np.mean(steady)), 2) if steady else None,
        "peak_rss_mb": _peak_mb(),
    }
    (out / "results.json").write_text(json.dumps({"summary": summary, "rows": results}, indent=1))
    for name, rows in sheets.items():
        _sheet(rows, out / f"sheet-{name}-{device}.jpg")
    return summary


def _sheet(rows, path: Path) -> None:
    if not rows:
        return
    tiles = []
    for at, truth, dirty, filled, hole in rows:
        for label, image in (("truth", truth), ("text", dirty), ("fill", filled)):
            tiles.append((f"{at:.1f}s {label}", image))
    width = max(image.shape[1] for _label, image in tiles)
    height = max(image.shape[0] for _label, image in tiles)
    scale = max(1, int(math.ceil(width / 700)))
    tw, th = width // scale, height // scale
    columns = 3
    lines = math.ceil(len(tiles) / columns)
    sheet = Image.new("RGB", (columns * tw, lines * (th + 16)), "white")
    draw = ImageDraw.Draw(sheet)
    for index, (label, image) in enumerate(tiles):
        tile = Image.fromarray(image).resize((tw, th), Image.LANCZOS)
        x, y = (index % columns) * tw, (index // columns) * (th + 16)
        sheet.paste(tile, (x, y + 16))
        draw.text((x + 4, y + 3), label, fill="black")
    sheet.save(path, quality=90)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--project", required=True)
    parser.add_argument("--frames", type=int, default=10)
    parser.add_argument("--variants", default="baseline")
    parser.add_argument("--out", type=Path, default=Path("/tmp/fillbench"))
    parser.add_argument("--stroke", type=float, default=0.055,
                        help="synthetic outline width as a share of box height")
    parser.add_argument("--device", choices=DEVICES, default="cpu",
                        help="where LaMa runs; one device per process")
    parser.add_argument("--spans", default="",
                        help="t0:t1,t2:t3 windows to sample inside (moving spans)")
    parser.add_argument("--model", type=Path, default=None,
                        help="model file; default is the shipped one for the device")
    args = parser.parse_args()
    variants = [name.strip() for name in args.variants.split(",") if name.strip()]
    unknown = [name for name in variants if name not in VARIANTS]
    if unknown:
        raise SystemExit(f"Unknown variants: {', '.join(unknown)}")
    windows = []
    for part in str(args.spans or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            first, last = part.split(":")
            windows.append((float(first), float(last)))
        except ValueError:
            raise SystemExit(f"Bad span {part!r}; use t0:t1,t2:t3")
    summary = run(
        args.data_root, args.project, args.frames, variants, args.out, args.stroke,
        args.device, args.model, windows=windows,
    )
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
