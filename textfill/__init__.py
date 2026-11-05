"""AI text fill for Edit Clean layers of kind ``fill``.

The render calls :func:`prepare_span` once per beat that has an active fill
layer. It decodes that span of the source, fills the masked text with STTN
(video, subtitle-tuned) or LaMa (per frame), and writes a cached clip at the
source size and frame rate. The beat then reads that clip instead of the
source; every other Clean layer, the crop and the motion apply on top as
before.

Models live in ``<data>/models/fill`` (or ``VIBECUT_FILL_MODELS``). They are
never downloaded here: a missing model is a clear error.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Iterable

import numpy as np

from . import mask as masks

METHODS = ("lama", "sttn", "telea", "ns")
# No model file: OpenCV spreads the colours around the hole into it.
CLASSIC_METHODS = ("telea", "ns")
DEFAULT_METHOD = "lama"
VERSION = 3
MODEL_FILES = {"sttn": "sttn_infer_model.pth", "lama": "lama_fp32.onnx"}
MODEL_PACKAGES = {"sttn": "torch", "lama": "onnxruntime", "telea": "cv2", "ns": "cv2"}
METHOD_COPY = {
    "sttn": "STTN (video)",
    "lama": "LaMa (per frame)",
    "telea": "Telea (OpenCV)",
    "ns": "Navier-Stokes (OpenCV)",
}
# Share of the previous frame's fill kept on LaMa output, to calm flicker.
LAMA_CARRY = 0.3
# LaMa fills about this many frames a second of video. The frames between blend
# two fills, since text sits still over a slow background. 0 fills every frame.
LAMA_KEYS_PER_SECOND = 3.0
# Mean change around the text (0..255) that stops a blend: the picture moved.
LAMA_MOTION_LIMIT = 6.0
# Tighter: one fill can last a whole line only while the shot barely changes.
LAMA_STILL_LIMIT = 2.5
# Seconds per unit before this machine has its own reading. A unit is one
# strip of one frame for STTN and one frame for LaMa. STTN's figure is a real
# render on an M1 8 GB Mac under swap, the OpenCV figures are real frames on that
# Mac during a render, and LaMa's is the first estimate of the founder's render.
SEED_RATES = {"sttn": 4.6, "lama": 1.2, "telea": 0.2, "ns": 0.2}
# LaMa's saved figure from before key frames and tight areas is several times too
# high, so the new code keeps its own. This holds the old figure out of estimates.
RATE_KEYS = {"lama": "lama_keyed"}
RATE_MIN_FRAMES = 60
RATES_FILE = "fill_rates.json"

Progress = Callable[[float, str], None]

_LOCK = threading.Lock()
_FILLERS_LOCK = threading.Lock()
_FILLERS: dict[tuple[str, str], object] = {}


class FillError(RuntimeError):
    """A fill cannot run (missing model, bad source, ffmpeg failure)."""


class FillCancelled(FillError):
    pass


def models_dir(data_root: Path | str) -> Path:
    override = os.environ.get("VIBECUT_FILL_MODELS")
    if override:
        return Path(override).expanduser()
    return Path(data_root) / "models" / "fill"


def model_path(method: str, directory: Path) -> Path:
    if method not in METHODS:
        raise FillError(f"Unknown fill method: {method}.")
    return Path(directory) / MODEL_FILES.get(method, "opencv")


def missing_model(method: str, directory: Path) -> str | None:
    """A plain message when the method's model file is absent, else None."""
    if method in CLASSIC_METHODS:
        return None
    path = model_path(method, directory)
    if path.is_file() and path.stat().st_size > 0:
        return None
    return (
        f"The {METHOD_COPY.get(method, method)} fill model is missing. "
        f"Put {MODEL_FILES[method]} in {directory}."
    )


def method_problem(method: str, directory: Path) -> str | None:
    """Why an engine cannot run here, or None. Ready needs model and package."""
    problem = missing_model(method, directory)
    if problem:
        return problem
    package = MODEL_PACKAGES[method]
    if importlib.util.find_spec(package) is None:
        return f"{METHOD_COPY.get(method, method)} fill needs the {package} package on this Mac."
    return None


def text_mask_enabled() -> bool:
    """Narrow scan layers to the text itself. Set off to fill the whole box."""
    value = os.environ.get("VIBECUT_FILL_TEXT_MASK", "on").strip().lower()
    return value not in {"0", "off", "false", "no"}


def fill_rate(data_root: Path | str, method: str) -> dict:
    """Seconds per unit for an engine: this machine's own, else the seed."""
    try:
        stored = json.loads((Path(data_root) / RATES_FILE).read_text(encoding="utf-8"))
        seconds = float(stored[RATE_KEYS.get(method, method)]["seconds"])
        if seconds > 0:
            return {"seconds": seconds, "measured": True}
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return {"seconds": SEED_RATES.get(method), "measured": False}


def record_rate(data_root: Path | str, method: str, units: int, seconds: float) -> None:
    """Remember how fast a finished fill ran. Short runs are mostly model load."""
    if units <= 0 or seconds <= 0:
        return
    path = Path(data_root) / RATES_FILE
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(stored, dict):
            stored = {}
    except (OSError, ValueError):
        stored = {}
    rate = seconds / units
    method = RATE_KEYS.get(method, method)
    previous = stored.get(method) if isinstance(stored.get(method), dict) else {}
    old = previous.get("seconds")
    stored[method] = {
        "seconds": round(rate if not old else float(old) * 0.5 + rate * 0.5, 4),
        "runs": int(previous.get("runs") or 0) + 1,
    }
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(stored), encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)


def _span_units(rect_table: list, frames: int, width: int, height: int, method: str) -> tuple[int, int]:
    """(frames with something to fill, model units) for a span."""
    active = [rects for rects in rect_table[:frames] if rects]
    if method != "sttn":
        return len(active), len(active)
    every = [rect for rects in active for rect in rects]
    return len(active), len(active) * len(masks.sttn_strips(every, width, height))


def estimate_span(
    *,
    meta: dict,
    start: float,
    duration: float,
    layers: list[dict],
    method: str,
    cache_dir: Path,
    data_root: Path,
) -> dict:
    """What one beat's fill will cost, without running anything.

    This is an upper figure: frames and strips with no text skip the model.
    """
    method = method if method in METHODS else DEFAULT_METHOD
    width = int(meta.get("width") or 0)
    height = int(meta.get("height") or 0)
    fps = float(meta.get("fps") or 0.0)
    row = {"method": method, "frames": 0, "units": 0, "cached": False}
    if width < 2 or height < 2 or fps <= 0:
        return row
    expected = max(1, int(round(duration * fps)))
    table = masks.frame_rects(layers, start=start, fps=fps, frames=expected, width=width, height=height)
    row["frames"], row["units"] = _span_units(table, expected, width, height, method)
    directory = models_dir(data_root)
    if not missing_model(method, directory):
        key = span_key(
            meta=meta, start=start, duration=duration, layers=layers,
            method=method, model_stamp=method_stamp(method, directory),
        )
        output = Path(cache_dir) / f"{key}.mp4"
        row["cached"] = output.is_file() and output.stat().st_size > 1024
    return row


def duration_text(seconds: float) -> str:
    """Rough, because the figure is rough: "about 40 min"."""
    minutes = int(round(float(seconds) / 60.0))
    if minutes < 1:
        return "under a minute"
    if minutes < 60:
        return f"about {minutes} min"
    hours, rest = divmod(minutes, 60)
    return f"about {hours} h {rest} min" if rest else f"about {hours} h"


def estimate_summary(rows: list[dict], data_root: Path | str) -> dict:
    """Add up beat estimates into one honest sentence for the panel."""
    planned = [row for row in rows if row.get("frames")]
    to_run = [row for row in planned if not row.get("cached")]
    seconds = 0.0
    unknown = []
    measured = True
    for method in METHODS:
        units = sum(row["units"] for row in to_run if row["method"] == method)
        if not units:
            continue
        rate = fill_rate(data_root, method)
        if rate["seconds"] is None:
            unknown.append(METHOD_COPY[method])
            continue
        seconds += units * rate["seconds"]
        measured = measured and rate["measured"]
    frames = sum(row["frames"] for row in to_run)
    if not planned:
        text = ""
    elif not to_run:
        text = "AI fill is already done for this. It adds no time."
    else:
        parts = []
        if seconds:
            parts.append(f"AI fill adds up to {duration_text(seconds)} on this Mac ({frames} frames).")
            if not measured:
                parts.append("That is a first guess until a render finishes here.")
        if unknown:
            parts.append(f"{' and '.join(unknown)} time is not measured yet, and it may be slower.")
        text = " ".join(parts)
    return {
        "beats": len(planned),
        "beats_cached": len(planned) - len(to_run),
        "frames": frames,
        "seconds": round(seconds, 1),
        "measured": measured,
        "unmeasured": unknown,
        "text": text,
    }


def _model_stamp(path: Path) -> str:
    stat = path.stat()
    return f"{path.name}:{stat.st_size}:{stat.st_mtime_ns}"


def method_stamp(method: str, directory: Path | str) -> str:
    """What identifies an engine's pixels: its model file, or OpenCV's version."""
    if method in CLASSIC_METHODS:
        try:
            import cv2
        except ImportError:
            return "opencv:missing"
        return f"opencv:{cv2.__version__}"
    return _model_stamp(model_path(method, Path(directory)))


def model_signature(methods: Iterable[str], directory: Path | str) -> str:
    """A stable signature of the model files a render will read.

    The render's master cache key includes this, so replacing a checkpoint
    never reuses a master cut with the old model's pixels.
    """
    directory = Path(directory)
    parts = []
    for method in sorted({str(item) for item in methods}):
        if method not in METHODS:
            continue
        if missing_model(method, directory):
            parts.append([method, "missing"])
        else:
            parts.append([method, method_stamp(method, directory)])
    payload = {"version": VERSION, "models": parts, "text_mask": text_mask_enabled()}
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def span_key(
    *,
    meta: dict,
    start: float,
    duration: float,
    layers: Iterable[dict],
    method: str,
    model_stamp: str,
    reuse_still: bool = False,
) -> str:
    payload = {
        "version": VERSION,
        "lama_keys": lama_keys_per_second() if method == "lama" else None,
        "areas": "tight" if method == "lama" or method in CLASSIC_METHODS else None,
        "reuse_still": bool(reuse_still) and method == "lama",
        "source": meta.get("fingerprint") or f"{meta.get('size')}:{meta.get('duration')}",
        "size": [int(meta.get("width") or 0), int(meta.get("height") or 0)],
        "fps": round(float(meta.get("fps") or 0.0), 6),
        "start": round(float(start), 6),
        "duration": round(float(duration), 6),
        "method": method,
        "model": model_stamp,
        "text_mask": text_mask_enabled(),
        "layers": [
            {
                "box": layer.get("box"),
                "ranges": layer.get("ranges") or [],
                "tracklet": layer.get("tracklet_id"),
                "mask": layer.get("mask"),
            }
            for layer in layers
        ],
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:20]


def _filler(method: str, path: Path):
    key = (method, str(path))
    with _FILLERS_LOCK:
        filler = _FILLERS.get(key)
        if filler is None:
            try:
                if method == "sttn":
                    from .sttn import SttnFiller
                    filler = SttnFiller(path)
                elif method in CLASSIC_METHODS:
                    from .classic import ClassicFiller
                    filler = ClassicFiller(method)
                else:
                    from .lama import LamaFiller
                    filler = LamaFiller(path)
            except ImportError as exc:
                package = MODEL_PACKAGES[method]
                raise FillError(
                    f"{METHOD_COPY[method]} fill needs the {package} package on this Mac."
                ) from exc
            _FILLERS[key] = filler
        return filler


def busy() -> bool:
    """True while a fill is running on this machine."""
    return _LOCK.locked()


def release_fillers() -> None:
    """Drop the loaded model sessions so a finished render frees their memory."""
    with _FILLERS_LOCK:
        _FILLERS.clear()


def _check_cancel(cancelled: Callable[[], bool] | None) -> None:
    if cancelled is not None and cancelled():
        raise FillCancelled("Render cancelled.")


class _Reader:
    def __init__(self, ffmpeg: str, source: str, start: float, duration: float,
                 fps: float, width: int, height: int):
        self.size = width * height * 3
        self.shape = (height, width, 3)
        self.proc = subprocess.Popen(
            [
                ffmpeg, "-v", "error", "-nostdin",
                "-ss", f"{start:.6f}", "-t", f"{duration:.6f}", "-i", source,
                "-an", "-sn",
                "-vf", f"fps={fps:.6f},scale={width}:{height}",
                "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
            ],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

    def read(self) -> np.ndarray | None:
        data = self.proc.stdout.read(self.size)
        if not data or len(data) < self.size:
            return None
        return np.frombuffer(data, dtype=np.uint8).reshape(self.shape).copy()


class _Writer:
    def __init__(self, ffmpeg: str, output: Path, fps: float, width: int, height: int):
        self.proc = subprocess.Popen(
            [
                ffmpeg, "-y", "-v", "error", "-nostdin",
                "-f", "rawvideo", "-pix_fmt", "rgb24",
                "-s", f"{width}x{height}", "-r", f"{fps:.6f}", "-i", "pipe:0",
                "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "12",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                str(output),
            ],
            stdin=subprocess.PIPE, stderr=subprocess.PIPE,
        )

    def write(self, frame: np.ndarray) -> None:
        self.proc.stdin.write(np.ascontiguousarray(frame, dtype=np.uint8).tobytes())


def _stop(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    try:
        if proc.stdin and not proc.stdin.closed:
            proc.stdin.close()
    except OSError:
        pass
    if proc.poll() is None:
        proc.kill()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except OSError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
    for stream in (proc.stdout, proc.stderr):
        try:
            if stream:
                stream.close()
        except OSError:
            pass


def _local(rects: list[masks.Rect], x0: int, y0: int, x1: int, y1: int) -> list[masks.Rect]:
    out = []
    for rx0, ry0, rx1, ry1 in rects:
        cx0, cy0 = max(rx0, x0), max(ry0, y0)
        cx1, cy1 = min(rx1, x1), min(ry1, y1)
        if cx1 > cx0 and cy1 > cy0:
            out.append((cx0 - x0, cy0 - y0, cx1 - x0, cy1 - y0))
    return out


def lama_keys_per_second() -> float:
    """``VIBECUT_FILL_LAMA_KEYS`` overrides it; 0 runs the model on every frame."""
    try:
        value = float(os.environ.get("VIBECUT_FILL_LAMA_KEYS", LAMA_KEYS_PER_SECOND))
    except ValueError:
        return LAMA_KEYS_PER_SECOND
    return max(0.0, value)


def lama_step(fps: float) -> int:
    """Frames from one LaMa fill to the next at this frame rate."""
    keys = lama_keys_per_second()
    if keys <= 0 or fps <= 0:
        return 1
    return max(1, int(round(float(fps) / keys)))


def _picture_moved(first: np.ndarray, second: np.ndarray, hole: np.ndarray, limit: float = LAMA_MOTION_LIMIT) -> bool:
    """Whether the picture around the text changed too much to blend across."""
    around = ~hole[::4, ::4]
    if not around.any():
        return False
    change = np.abs(first[::4, ::4].astype(np.int16) - second[::4, ::4].astype(np.int16))
    return float(change[around].mean()) > limit


def _fill_frames_by_runs(frames, rects_for, filler, area, step, *, on_frame, cancelled, hole_for, width=0, height=0, reuse_still=False):
    """Run the engine on key frames, on just the areas that hold text.

    A run is frames that share the same boxes, up to the step, while the picture
    holds still. Each area of it is filled once at its last frame, with a hole
    covering the whole run, and the frames between blend two fills. The next run
    starts from that fill when it is on the same area and covers the hole, which
    saves a model call. ``area`` fixes one work area; None finds them per run.

    ``reuse_still`` tries one fill for a whole line first: made on the line's
    first frame over its whole box, so later frames need no look ahead, and kept
    while the shot barely changes. A try that ends early falls back to key frames
    for one run, so a moving shot is not filled on every frame.
    """
    try_still = reuse_still
    source = enumerate(frames)
    waiting = None
    last_fills: dict[tuple, tuple[np.ndarray, np.ndarray]] = {}

    def next_frame():
        nonlocal waiting
        if waiting is not None:
            item, waiting = waiting, None
            return item
        pair = next(source, None)
        if pair is None:
            return None
        index, frame = pair
        return index, frame, tuple(sorted(masks.without_contained(rects_for(index))))

    def areas_for(rects, frame):
        if area is not None:
            return [area]
        return masks.lama_areas(rects, frame.shape[1] or width, frame.shape[0] or height)

    def hole_on(index, rects, spot):
        x0, y0, x1, y1 = spot
        local = _local(list(rects), x0, y0, x1, y1)
        if not local:
            return np.zeros((y1 - y0, x1 - x0), dtype=bool)
        return (
            hole_for(index, x0, y0, x1, y1) if hole_for
            else masks.rasterize(local, x1 - x0, y1 - y0)
        )

    while True:
        _check_cancel(cancelled)
        first = next_frame()
        if first is None:
            return
        rects = first[2]
        spots = areas_for(rects, first[1]) if rects else []
        holes = {spot: hole_on(first[0], rects, spot) for spot in spots}
        if not any(hole.any() for hole in holes.values()):
            last_fills = {}
            yield first[1]
            if on_frame:
                on_frame(first[0])
            continue
        if try_still:
            whole = {
                spot: masks.rasterize(
                    _local(list(rects), *spot), spot[2] - spot[0], spot[3] - spot[1],
                )
                for spot in spots
            }
            kept = {}
            for spot in spots:
                x0, y0, x1, y1 = spot
                _check_cancel(cancelled)
                kept[spot] = filler.fill(first[1][y0:y1, x0:x1], whole[spot])
            shown = 0
            item = first
            found = holes
            while True:
                out = item[1].copy()
                for spot, fill in kept.items():
                    x0, y0, x1, y1 = spot
                    out[y0:y1, x0:x1] = masks.paste(
                        item[1][y0:y1, x0:x1], fill, masks.feather(found[spot]),
                    )
                yield out
                if on_frame:
                    on_frame(item[0])
                shown += 1
                _check_cancel(cancelled)
                item = next_frame()
                if item is None:
                    return
                still = item[2] == rects and not any(
                    _picture_moved(
                        first[1][y0:y1, x0:x1], item[1][y0:y1, x0:x1], whole[(x0, y0, x1, y1)],
                        LAMA_STILL_LIMIT,
                    )
                    for x0, y0, x1, y1 in spots
                )
                found = {spot: hole_on(item[0], rects, spot) for spot in spots} if still else {}
                if not still or not any(hole.any() for hole in found.values()):
                    waiting = item
                    break
            # The fill is not blended into the next line, so nothing carries over.
            last_fills = {}
            # Stopped by the picture moving, not by the line ending: use key frames.
            if waiting[2] == rects and shown < step:
                try_still = False
            continue
        try_still = reuse_still
        run = [first]
        run_holes = [holes]
        while len(run) < step:
            item = next_frame()
            if item is None:
                break
            moved = any(
                _picture_moved(
                    first[1][y0:y1, x0:x1], item[1][y0:y1, x0:x1], holes[(x0, y0, x1, y1)],
                )
                for x0, y0, x1, y1 in spots
            )
            if item[2] != rects or moved:
                waiting = item
                break
            found = {spot: hole_on(item[0], rects, spot) for spot in spots}
            if not any(hole.any() for hole in found.values()):
                waiting = item
                break
            run.append(item)
            run_holes.append(found)
        fills: dict[tuple, tuple] = {}
        for spot in spots:
            x0, y0, x1, y1 = spot
            union = np.logical_or.reduce([found[spot] for found in run_holes])
            if not union.any():
                continue
            _check_cancel(cancelled)
            end_fill = filler.fill(run[-1][1][y0:y1, x0:x1], union)
            earlier = last_fills.get(spot)
            covered = earlier is not None and not (union & ~earlier[1]).any()
            begin = earlier[0] if covered else None
            if begin is None and len(run) > 1:
                _check_cancel(cancelled)
                begin = filler.fill(first[1][y0:y1, x0:x1], union)
            if begin is not None and len(run) == 1 and step > 1:
                # A frame on its own has nothing to blend, so calm it with the last.
                end_fill = np.clip(
                    end_fill.astype(np.float32) * (1 - LAMA_CARRY)
                    + begin.astype(np.float32) * LAMA_CARRY,
                    0, 255,
                ).astype(np.uint8)
            fills[spot] = (begin, end_fill, covered, union)
        for position, (index, frame, _rects) in enumerate(run):
            out = frame.copy()
            for spot, (begin, end_fill, covered, _union) in fills.items():
                x0, y0, x1, y1 = spot
                if begin is None or position == len(run) - 1:
                    filled = end_fill
                else:
                    # Runs that share a fill hand over on its frame, without a jump.
                    share = (position + (1 if covered else 0)) / (len(run) - (0 if covered else 1))
                    filled = np.clip(
                        begin.astype(np.float32) * (1 - share) + end_fill.astype(np.float32) * share,
                        0, 255,
                    ).astype(np.uint8)
                out[y0:y1, x0:x1] = masks.paste(
                    frame[y0:y1, x0:x1], filled, masks.feather(run_holes[position][spot]),
                )
            yield out
            if on_frame:
                on_frame(index)
        last_fills = {spot: (fill[1], fill[3]) for spot, fill in fills.items()}


def fill_frames_lama(frames, rects_for, filler, area, *, on_frame=None, cancelled=None, hole_for=None, step=1, carry=LAMA_CARRY, reuse_still=False):
    """Yield filled frames. ``rects_for(index)`` gives that frame's rects.

    ``hole_for(index, x0, y0, x1, y1)`` narrows the hole; without it the hole
    is the rects themselves. A ``step`` above 1 runs the model on key frames, and
    an ``area`` of None finds tight work areas for each run. ``carry`` is the
    share of the last fill kept, to calm flicker.
    """
    if step > 1 or area is None:
        yield from _fill_frames_by_runs(
            frames, rects_for, filler, area, step,
            on_frame=on_frame, cancelled=cancelled, hole_for=hole_for, reuse_still=reuse_still,
        )
        return
    x0, y0, x1, y1 = area
    previous: np.ndarray | None = None
    for index, frame in enumerate(frames):
        _check_cancel(cancelled)
        local = _local(rects_for(index), x0, y0, x1, y1)
        hole = None
        if local:
            hole = (
                hole_for(index, x0, y0, x1, y1) if hole_for
                else masks.rasterize(local, x1 - x0, y1 - y0)
            )
        if hole is None or not hole.any():
            previous = None
            yield frame
        else:
            work = frame[y0:y1, x0:x1]
            _check_cancel(cancelled)
            filled = filler.fill(work, hole)
            if previous is not None and carry > 0:
                filled = np.clip(
                    filled.astype(np.float32) * (1 - carry)
                    + previous.astype(np.float32) * carry,
                    0, 255,
                ).astype(np.uint8)
            previous = filled
            out = frame.copy()
            out[y0:y1, x0:x1] = masks.paste(work, filled, masks.feather(hole))
            yield out
        if on_frame:
            on_frame(index)


def _blend_strips(old, fresh, weight: float):
    """Cross-fade strip lists; a strip with no model output keeps the other."""
    out = []
    for before, after in zip(old, fresh):
        if before is None or after is None:
            out.append(after if before is None else before)
            continue
        out.append(np.clip(
            before.astype(np.float32) * (1 - weight) + after.astype(np.float32) * weight, 0, 255,
        ).astype(np.uint8))
    return out


def fill_frames_sttn(frames, rects_for, filler, strips, *, chunk, overlap, on_frame=None, cancelled=None, hole_for=None):
    """Yield filled frames, running the model on overlapping chunks.

    Frames in an overlap get both chunks' strips, cross-faded linearly. A strip
    with no text in a chunk skips the model for that chunk. ``hole_for`` narrows
    the hole, as in :func:`fill_frames_lama`.
    """
    width = None
    iterator = iter(frames)
    buffer: list[tuple[int, np.ndarray]] = []
    carry: dict[int, list] = {}
    next_index = 0
    lookahead = next(iterator, None)
    while True:
        _check_cancel(cancelled)
        while len(buffer) < chunk and lookahead is not None:
            buffer.append((next_index, lookahead))
            next_index += 1
            lookahead = next(iterator, None)
        # Knowing the stream ended here saves a model run on a short tail.
        eof = lookahead is None
        if not buffer:
            return
        width = buffer[0][1].shape[1]
        wanted = [rects_for(index) for index, _ in buffer]
        outputs = None
        if any(wanted):
            outputs = []
            for y0, y1 in strips:
                if any(_local(rects, 0, y0, width, y1) for rects in wanted):
                    _check_cancel(cancelled)
                    outputs.append(filler.fill([frame[y0:y1] for _, frame in buffer]))
                else:
                    outputs.append(None)
        final = len(buffer) if eof else len(buffer) - overlap
        for k, (index, frame) in enumerate(buffer):
            fresh = [None if out is None else out[k] for out in outputs] if outputs else None
            old = carry.pop(index, None)
            if old is not None and fresh is not None:
                fresh = _blend_strips(old, fresh, (k + 1) / (overlap + 1))
            elif fresh is None:
                fresh = old
            if k < final:
                out = frame
                rects = rects_for(index)
                if fresh is not None and rects:
                    out = frame.copy()
                    for (y0, y1), strip in zip(strips, fresh):
                        local = _local(rects, 0, y0, width, y1)
                        if local and strip is not None:
                            hole = (
                                hole_for(index, 0, y0, width, y1) if hole_for
                                else masks.rasterize(local, width, y1 - y0)
                            )
                            out[y0:y1] = masks.paste(out[y0:y1], strip, masks.feather(hole))
                yield out
                if on_frame:
                    on_frame(index)
            elif fresh is not None:
                carry[index] = fresh
        buffer = buffer[final:]
        if eof and not buffer:
            return


def fill_frame(
    frame: np.ndarray,
    rects: Iterable[masks.Rect],
    *,
    data_root: Path | str,
    method: str = "lama",
    tight_rects: Iterable[masks.Rect] = (),
) -> np.ndarray:
    """Fill one RGB frame in place of a sequence.

    Rects also in ``tight_rects`` narrow to the text found in them, as in the
    render, so the preview shows the same hole.

    One frame is a supported input for LaMa and the OpenCV methods. STTN needs
    neighbouring frames and is left to the full render.
    """
    if method == "sttn":
        raise FillError("The single-frame fill preview uses the LaMa model.")
    directory = models_dir(data_root)
    problem = missing_model(method, directory)
    if problem:
        raise FillError(problem)
    local_rects = [rect for rect in rects if rect[2] > rect[0] and rect[3] > rect[1]]
    height, width = frame.shape[:2]
    area = masks.lama_area(local_rects, width, height)
    if area is None:
        return frame.copy()
    x0, y0, x1, y1 = area
    local = _local(local_rects, x0, y0, x1, y1)
    if not local:
        return frame.copy()
    work = frame[y0:y1, x0:x1]
    tight = [rect for rect in tight_rects if rect in local_rects] if text_mask_enabled() else []
    if tight:
        exact = [rect for rect in local_rects if rect not in tight]
        finder = masks.TextMasks([tight], [exact], width, height)
        finder._measure(0, frame)
        hole = finder.hole(0, x0, y0, x1, y1)
        if not hole.any():
            return frame.copy()
    else:
        hole = masks.rasterize(local, x1 - x0, y1 - y0)
    # One model at a time on this Mac: a preview never loads beside a render.
    if not _LOCK.acquire(blocking=False):
        raise FillError("AI fill is busy with a render. Try the preview when it finishes.")
    try:
        filled = _filler(method, model_path(method, directory)).fill(work, hole)
    finally:
        release_fillers()
        _LOCK.release()
    out = frame.copy()
    out[y0:y1, x0:x1] = masks.paste(work, filled, masks.feather(hole))
    return out


def prepare_span(
    *,
    source: str,
    meta: dict,
    start: float,
    duration: float,
    layers: list[dict],
    method: str,
    cache_dir: Path,
    data_root: Path,
    ffmpeg: str = "ffmpeg",
    progress: Progress | None = None,
    cancel_event: threading.Event | None = None,
    reuse_still: bool = False,
) -> dict | None:
    """Write (or reuse) a filled clip of ``[start, start + duration]``.

    Returns ``{"path", "key", "cached", "method"}``, or None when no fill
    layer touches the span.
    """
    method = method if method in METHODS else DEFAULT_METHOD
    width = int(meta.get("width") or 0)
    height = int(meta.get("height") or 0)
    fps = float(meta.get("fps") or 0.0)
    if width < 2 or height < 2 or fps <= 0:
        raise FillError("AI fill needs the source width, height and frame rate.")
    expected = max(1, int(round(duration * fps)))
    # A few spare frames: the decoder may return one more than the estimate.
    rect_table = masks.frame_rects(
        layers, start=start, fps=fps, frames=expected + int(fps) + 2,
        width=width, height=height,
    )
    span_rects = [rect for rects in rect_table[:expected + 1] for rect in rects]
    if not span_rects:
        return None

    directory = models_dir(data_root)
    problem = missing_model(method, directory)
    if problem:
        raise FillError(problem)
    path = model_path(method, directory)
    key = span_key(
        meta=meta, start=start, duration=duration, layers=layers,
        method=method, model_stamp=method_stamp(method, directory), reuse_still=reuse_still,
    )
    cache_dir = Path(cache_dir)
    output = cache_dir / f"{key}.mp4"
    if output.is_file() and output.stat().st_size > 1024:
        return {"path": str(output), "key": key, "cached": True, "method": method}
    cache_dir.mkdir(parents=True, exist_ok=True)
    part = cache_dir / f".{key}.part.mp4"

    finder = None
    if text_mask_enabled():
        tight_layers = [layer for layer in layers if masks.uses_text_mask(layer, width, height)]
        if tight_layers:
            exact_layers = [layer for layer in layers if layer not in tight_layers]
            size = {"start": start, "fps": fps, "frames": len(rect_table), "width": width, "height": height}
            exact_rows = masks.frame_rects(exact_layers, **size)
            # A text box wholly inside a drawn box or brush needs no second look.
            tight_rows = [
                [
                    rect for rect in masks.without_contained(row)
                    if rect in masks.without_contained([rect, *exact])
                ]
                for row, exact in zip(masks.frame_rects(tight_layers, **size), exact_rows)
            ]
            finder = masks.TextMasks(tight_rows, exact_rows, width, height)

    def rects_for(index: int) -> list[masks.Rect]:
        if finder is not None:
            return finder.rects_for(index)
        return rect_table[min(index, len(rect_table) - 1)]

    def hole_for(index: int, x0: int, y0: int, x1: int, y1: int) -> np.ndarray:
        return finder.hole(index, x0, y0, x1, y1)

    def cancelled() -> bool:
        return cancel_event is not None and cancel_event.is_set()

    def on_frame(index: int) -> None:
        _check_cancel(cancelled)
        if finder is not None:
            finder.forget_before(index)
        if progress and index % 10 == 0:
            progress(min(1.0, (index + 1) / expected), f"{METHOD_COPY[method]} {index + 1}/{expected}")

    # A cancel while another render holds the lock must not wait for it.
    _check_cancel(cancelled)
    while not _LOCK.acquire(timeout=0.2):
        _check_cancel(cancelled)
    reader = writer = None
    started = time.monotonic()
    try:
        _check_cancel(cancelled)
        # This lock is the only fill running, so any .part here was orphaned
        # by a killed server.
        for stale in cache_dir.glob(".*.part.mp4"):
            stale.unlink(missing_ok=True)
        filler = _filler(method, path)
        reader = _Reader(ffmpeg, source, start, duration, fps, width, height)
        writer = _Writer(ffmpeg, part, fps, width, height)

        def frames():
            while True:
                _check_cancel(cancelled)
                frame = reader.read()
                if frame is None:
                    return
                yield frame

        source_frames = finder.wrap(frames()) if finder is not None else frames()
        extra = {"hole_for": hole_for} if finder is not None else {}
        if method == "lama":
            stream = fill_frames_lama(
                source_frames, rects_for, filler, None,
                on_frame=on_frame, cancelled=cancelled, step=lama_step(fps),
                reuse_still=reuse_still, **extra,
            )
        elif method in CLASSIC_METHODS:
            # Cheap enough for every frame, at full size, with nothing blended in.
            stream = fill_frames_lama(
                source_frames, rects_for, filler, None,
                on_frame=on_frame, cancelled=cancelled, carry=0.0, **extra,
            )
        else:
            from .sttn import CHUNK, OVERLAP
            strips = masks.sttn_strips(span_rects, width, height)
            stream = fill_frames_sttn(
                source_frames, rects_for, filler, strips,
                chunk=CHUNK, overlap=OVERLAP,
                on_frame=on_frame, cancelled=cancelled, **extra,
            )
        written = 0
        for frame in stream:
            writer.write(frame)
            written += 1
        writer.proc.stdin.close()
        code = writer.proc.wait(timeout=300)
        reader.proc.wait(timeout=30)
        if code != 0 or written == 0:
            detail = writer.proc.stderr.read().decode("utf-8", "replace").strip()[-400:]
            raise FillError(f"AI fill could not write the clip. {detail}".strip())
        os.replace(part, output)
        if written >= RATE_MIN_FRAMES:
            _frames, units = _span_units(rect_table, expected, width, height, method)
            record_rate(data_root, method, units, time.monotonic() - started)
    except BaseException:
        _stop(reader.proc if reader is not None else None)
        _stop(writer.proc if writer is not None else None)
        part.unlink(missing_ok=True)
        raise
    finally:
        # Close both ffmpeg pipes even on the success path.
        if reader is not None:
            _stop(reader.proc)
        if writer is not None:
            _stop(writer.proc)
        _LOCK.release()
    if progress:
        progress(1.0, f"{METHOD_COPY[method]} done")
    return {"path": str(output), "key": key, "cached": False, "method": method}
