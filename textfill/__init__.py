"""AI text fill for Edit Clean layers of kind ``fill``.

The render calls :func:`prepare_span` once per beat that has an active fill
layer. It decodes that span of the source, fills the masked text with LaMa on
key frames, blends between them, and writes a cached clip at the source size and
frame rate. The beat then reads that clip instead of the
source; every other Clean layer, the crop and the motion apply on top as
before.

Models live in ``<data>/models/fill`` (or ``VIBECUT_FILL_MODELS``). They are
never downloaded here: a missing model is a clear error.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Iterable

import numpy as np

from . import mask as masks

METHODS = ("lama",)
DEFAULT_METHOD = "lama"
# Classic fills with LaMa only. A layer saved earlier may still name these, and
# it must open and render, as LaMa.
RETIRED_METHODS = ("sttn",)
VERSION = 3
MODEL_FILES = {"lama": "lama_fp32.onnx"}
MODEL_PACKAGES = {"lama": "onnxruntime"}
METHOD_COPY = {"lama": "LaMa (per frame)"}
# Share of the previous frame's fill kept on LaMa output, to calm flicker.
LAMA_CARRY = 0.3
# LaMa fills about this many frames a second of video. The frames between blend
# two fills, since text sits still over a slow background. 0 fills every frame.
LAMA_KEYS_PER_SECOND = 3.0
# Mean change around the text (0..255) that stops a blend: the picture moved.
LAMA_MOTION_LIMIT = 6.0
# Fills a second a box with no scan plan needs at most, however much the picture
# moves. Without this floor, a moving shot ran the model on nearly every frame.
LAMA_UNPLANNED_KEYS = 6.0
# Bump when the run rule changes what a fill looks like, so a cut made under the
# old rule is not reused.
LAMA_RUN_RULE = 2
# A line planned by the scan needs no motion check, only a stop at a sudden change.
LAMA_CUT_LIMIT = 30.0
# Pixels around the text that the motion check reads.
LAMA_RING_PX = 24
# Cost of one LaMa run per pixel it reads, as a share of a 512 square, and of
# reading, pasting and writing one frame.
LAMA_FRAME_UNITS = 0.02
# LaMa has no time per unit until a render finishes on this Mac. A unit is one run
# on a full 512 square, so the figure does not depend on how much a video moves.
SEED_RATES: dict[str, float] = {}
# Earlier figures were per frame, under another key, and stay out of estimates.
RATE_KEY = "lama_run"
RATE_MIN_FRAMES = 60
RATES_FILE = "fill_rates.json"

Progress = Callable[[float, str], None]
LOGGER = logging.getLogger(__name__)

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


def known_method(method: str | None) -> str:
    """The engine to run for a stored name; a retired engine runs as LaMa."""
    name = str(method or DEFAULT_METHOD).strip().lower()
    if name in RETIRED_METHODS:
        return DEFAULT_METHOD
    if name not in METHODS:
        raise FillError(f"Unknown fill method: {method}.")
    return name


def model_path(method: str, directory: Path) -> Path:
    return Path(directory) / MODEL_FILES[known_method(method)]


def missing_model(method: str, directory: Path) -> str | None:
    """A plain message when the method's model file is absent, else None."""
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
    package = MODEL_PACKAGES[known_method(method)]
    if importlib.util.find_spec(package) is None:
        return f"{METHOD_COPY[known_method(method)]} fill needs the {package} package on this Mac."
    return None


def text_mask_enabled() -> bool:
    """Narrow scan layers to the text itself. Set off to fill the whole box."""
    value = os.environ.get("VIBECUT_FILL_TEXT_MASK", "on").strip().lower()
    return value not in {"0", "off", "false", "no"}


def fill_rate(data_root: Path | str, method: str) -> dict:
    """Seconds per unit for an engine: this machine's own, else the seed."""
    try:
        stored = json.loads((Path(data_root) / RATES_FILE).read_text(encoding="utf-8"))
        seconds = float(stored[RATE_KEY]["seconds"])
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
    previous = stored.get(RATE_KEY) if isinstance(stored.get(RATE_KEY), dict) else {}
    old = previous.get("seconds")
    stored[RATE_KEY] = {
        "seconds": round(rate if not old else float(old) * 0.5 + rate * 0.5, 4),
        "runs": int(previous.get("runs") or 0) + 1,
    }
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(stored), encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)


def _span_units(rect_table: list, frames: int) -> tuple[int, int]:
    """(frames with something to fill, model units): one unit per frame."""
    active = sum(1 for rects in rect_table[:frames] if rects)
    return active, active


def _planned_units(rect_table: list, layers, *, start: float, fps: float, frames: int, width: int, height: int) -> float:
    """What the fill will cost: its planned model runs, on the areas they read."""
    from . import lama

    plan_for = lama_plan(layers, start=start, fps=fps, frames=frames)
    total = 0.0
    index = 0
    frames = min(frames, len(rect_table))
    while index < frames:
        rects = tuple(sorted(masks.without_contained(rect_table[index])))
        end = index + 1
        while end < frames and tuple(sorted(masks.without_contained(rect_table[end]))) == rects:
            end += 1
        if rects:
            run_step, _limit, still, *shortest = plan_for(index)
            # A box with no plan: the most it can need, on a moving shot.
            run_step = shortest[0] if shortest else run_step
            runs = 1 if still else (end - index) / run_step + 1
            area_cost = sum(
                lama.run_units(spot[3] - spot[1], spot[2] - spot[0])
                for spot in masks.lama_areas(rects, width, height)
            )
            total += runs * area_cost + (end - index) * LAMA_FRAME_UNITS
        index = end
    return round(total, 2)


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

    This is an upper figure: frames with no text skip the model.
    """
    method = known_method(method)
    width = int(meta.get("width") or 0)
    height = int(meta.get("height") or 0)
    fps = float(meta.get("fps") or 0.0)
    row = {"method": method, "frames": 0, "units": 0, "cached": False}
    if width < 2 or height < 2 or fps <= 0:
        return row
    expected = max(1, int(round(duration * fps)))
    table = masks.frame_rects(layers, start=start, fps=fps, frames=expected, width=width, height=height)
    row["frames"], row["units"] = _span_units(table, expected)
    row["units"] = _planned_units(table, layers, start=start, fps=fps, frames=expected, width=width, height=height)
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
    """What identifies an engine's pixels: its model file."""
    return _model_stamp(model_path(method, Path(directory)))


def model_signature(methods: Iterable[str], directory: Path | str) -> str:
    """A stable signature of the model files a render will read.

    The render's master cache key includes this, so replacing a checkpoint
    never reuses a master cut with the old model's pixels.
    """
    directory = Path(directory)
    parts = []
    named = {str(item).strip().lower() for item in methods}
    for method in sorted({DEFAULT_METHOD if item in RETIRED_METHODS else item for item in named}):
        if method not in METHODS:
            continue
        if missing_model(method, directory):
            parts.append([method, "missing"])
        else:
            parts.append([method, method_stamp(method, directory)])
            if method == "lama":
                parts.append(["runs", LAMA_RUN_RULE])
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
) -> str:
    layers = list(layers)
    payload = {
        "version": VERSION,
        "lama_keys": lama_keys_per_second(),
        "areas": "tight",
        "plan": "scan",
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
                "keys": layer.get("fill_keys"),
            }
            for layer in layers
        ],
    }
    # Only a box with no plan changed with this rule, so planned clips stay valid.
    if method == "lama" and any(layer.get("fill_keys") is None for layer in layers):
        payload["unplanned"] = LAMA_UNPLANNED_KEYS
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:20]


def _filler(method: str, path: Path):
    key = (method, str(path))
    with _FILLERS_LOCK:
        filler = _FILLERS.get(key)
        if filler is None:
            try:
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


def lama_plan(layers, *, start: float, fps: float, frames: int):
    """``plan_for``: the scan's plan per frame, or the default where a layer has none.

    Setting ``VIBECUT_FILL_LAMA_KEYS`` overrides the plan, to compare results.
    A box with no plan, such as a drawn one, adapts as it runs: the default number
    of fills when the picture holds still, up to ``LAMA_UNPLANNED_KEYS`` when it
    moves, and more only at a cut. The fourth value is that shortest run.
    """
    default = (lama_step(fps), LAMA_MOTION_LIMIT, False)
    if os.environ.get("VIBECUT_FILL_LAMA_KEYS"):
        return lambda _index: default
    shortest = max(1, min(default[0], int(round(fps / LAMA_UNPLANNED_KEYS))))
    default = (*default, shortest)
    table = masks.frame_keys(layers, start=start, fps=fps, frames=frames)

    def plan_for(index: int):
        keys = table[min(index, len(table) - 1)] if table else None
        if keys is None:
            return default
        if keys <= 0:
            return (lama_step(fps), LAMA_CUT_LIMIT, True)
        return (max(1, int(round(fps / keys))), LAMA_CUT_LIMIT, False)

    return plan_for


# Model results kept on disk while a clip is unfinished, next to its .part file.
SAVED_DIR = "saved"
SAVED_MAX_AGE = 14 * 24 * 3600
SAVED_MAX_BYTES = 2 * 1024 ** 3


def _remove_quietly(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        LOGGER.warning("could not remove %s: %s", path.name, exc)


class _SavedFills:
    """Keeps each model result on disk, so a stopped render does not lose it.

    A fill is named by what went in: the model, the crop's pixels and the hole.
    The same frames and boxes ask the same questions in the same order, so after
    a stop the run replays and only the fills still missing reach the model. A
    result that does not match is simply a miss, so nothing here can reuse a
    wrong picture. Results go when the clip they built is finished.
    """

    def __init__(self, filler, directory: Path, stamp: str):
        self.filler = filler
        self.directory = Path(directory)
        self.stamp = stamp
        # Fills from before this run. A frame that repeats in this run is no resume.
        self.hits = 0
        self.used: set[Path] = set()
        self.writable = True

    def _path(self, area: np.ndarray, mask: np.ndarray) -> Path:
        digest = hashlib.sha1(f"{VERSION}|{self.stamp}|{area.shape}".encode())
        digest.update(area.tobytes())
        digest.update(mask.tobytes())
        return self.directory / f"{digest.hexdigest()}.npy"

    def _read(self, path: Path, shape: tuple) -> np.ndarray | None:
        try:
            found = np.load(path, allow_pickle=False)
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            _remove_quietly(path)
            return None
        return found if found.shape == shape else None

    def _write(self, path: Path, result: np.ndarray) -> None:
        if not self.writable:
            return
        temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            with temporary.open("wb") as handle:
                np.save(handle, result, allow_pickle=False)
            os.replace(temporary, path)
        except OSError as exc:
            # A full disk costs the resume, never the render.
            self.writable = False
            LOGGER.warning("could not save AI fills: %s", exc)
            _remove_quietly(temporary)

    def fill(self, area: np.ndarray, mask: np.ndarray) -> np.ndarray:
        path = self._path(area, mask)
        found = self._read(path, area.shape)
        if found is not None:
            if path not in self.used:
                self.hits += 1
            self.used.add(path)
            return found
        self.used.add(path)
        result = self.filler.fill(area, mask)
        self._write(path, result)
        return result

    def forget(self) -> None:
        """The finished clip holds these now."""
        for path in self.used:
            _remove_quietly(path)
        try:
            self.directory.rmdir()
        except OSError:
            pass  # Other clips still have fills here, or it never existed.


def _prune_saved(directory: Path, *, now: float | None = None) -> None:
    """Drop what an abandoned edit left: anything old, then the oldest past the cap."""
    now = time.time() if now is None else now
    try:
        rows = [(entry.stat().st_mtime, entry.stat().st_size, Path(entry.path)) for entry in os.scandir(directory)]
    except OSError:
        return
    kept = []
    try:
        for changed, size, path in rows:
            # Only one fill runs at a time, so a .tmp here belongs to a killed one.
            if path.suffix == ".tmp" or now - changed > SAVED_MAX_AGE:
                path.unlink(missing_ok=True)
            else:
                kept.append((changed, size, path))
        total = sum(size for _changed, size, _path in kept)
        for _changed, size, path in sorted(kept, key=lambda row: row[0]):
            if total <= SAVED_MAX_BYTES:
                break
            path.unlink(missing_ok=True)
            total -= size
    except OSError as exc:
        LOGGER.warning("could not tidy saved AI fills: %s", exc)


class _CountedFiller:
    """Counts the work a filler does, in the units its speed is measured in."""

    def __init__(self, filler):
        self.filler = filler
        self.runs = 0
        self.units = 0.0

    def fill(self, area: np.ndarray, mask: np.ndarray) -> np.ndarray:
        from . import lama

        self.runs += 1
        self.units += lama.run_units(*mask.shape)
        return self.filler.fill(area, mask)


def lama_step(fps: float) -> int:
    """Frames from one LaMa fill to the next at this frame rate."""
    keys = lama_keys_per_second()
    if keys <= 0 or fps <= 0:
        return 1
    return max(1, int(round(float(fps) / keys)))


def _ring_around(rects, spot, ring: int = LAMA_RING_PX) -> np.ndarray:
    """The picture just around the text in a work area, as a mask to leave out.

    Movement far from the text does not touch the fill, so it must not stop a blend.
    """
    x0, y0, x1, y1 = spot
    keep = np.ones((y1 - y0, x1 - x0), dtype=bool)
    for left, top, right, bottom in _local(list(rects), x0, y0, x1, y1):
        keep[max(0, top - ring):bottom + ring, max(0, left - ring):right + ring] = False
    for left, top, right, bottom in _local(list(rects), x0, y0, x1, y1):
        keep[top:bottom, left:right] = True
    return keep


def _picture_moved(first: np.ndarray, second: np.ndarray, hole: np.ndarray, limit: float = LAMA_MOTION_LIMIT) -> bool:
    """Whether the picture around the text changed too much to blend across."""
    around = ~hole[::4, ::4]
    if not around.any():
        return False
    change = np.abs(first[::4, ::4].astype(np.int16) - second[::4, ::4].astype(np.int16))
    return float(change[around].mean()) > limit


def _fill_frames_by_runs(frames, rects_for, filler, area, step, *, on_frame, cancelled, hole_for, width=0, height=0, plan_for=None):
    """Run the engine on key frames, on just the areas that hold text.

    A run is frames that share the same boxes, up to the step, while the picture
    holds still. Each area of it is filled once at its last frame, with a hole
    covering the whole run, and the frames between blend two fills. The next run
    starts from that fill when it is on the same area and covers the hole, which
    saves a model call. ``area`` fixes one work area; None finds them per run.

    ``plan_for(index)`` gives the plan for a frame: (frames per fill, motion limit,
    still), and optionally a shortest run, which only a cut can end sooner. A still
    line gets one fill, made on its first frame over its whole box, so later frames
    need no look ahead, and kept unless the picture jumps. A try that ends early
    falls back to key frames for one run.
    """
    failed_still = False
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
        run_step, run_limit, still_line, *shortest = plan_for(first[0]) if plan_for else (step, LAMA_MOTION_LIMIT, False)
        shortest_run = shortest[0] if shortest else 1
        ring = {spot: _ring_around(rects, spot) for spot in spots}
        if still_line and not failed_still:
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
                        first[1][y0:y1, x0:x1], item[1][y0:y1, x0:x1], ring[(x0, y0, x1, y1)],
                        LAMA_MOTION_LIMIT,
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
            failed_still = waiting[2] == rects and shown < max(run_step, 2)
            continue
        failed_still = False
        run = [first]
        run_holes = [holes]
        while len(run) < run_step:
            item = next_frame()
            if item is None:
                break
            limit = LAMA_CUT_LIMIT if len(run) < shortest_run else run_limit
            moved = any(
                _picture_moved(
                    first[1][y0:y1, x0:x1], item[1][y0:y1, x0:x1], ring[(x0, y0, x1, y1)], limit,
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


def fill_frames_lama(frames, rects_for, filler, area, *, on_frame=None, cancelled=None, hole_for=None, step=1, carry=LAMA_CARRY, plan_for=None):
    """Yield filled frames. ``rects_for(index)`` gives that frame's rects.

    ``hole_for(index, x0, y0, x1, y1)`` narrows the hole; without it the hole
    is the rects themselves. A ``step`` above 1 runs the model on key frames, and
    an ``area`` of None finds tight work areas for each run. ``carry`` is the
    share of the last fill kept, to calm flicker.
    """
    if step > 1 or area is None:
        yield from _fill_frames_by_runs(
            frames, rects_for, filler, area, step,
            on_frame=on_frame, cancelled=cancelled, hole_for=hole_for, plan_for=plan_for,
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

    LaMa fills each frame alone, so one frame is a full preview of the engine.
    """
    method = known_method(method)
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
    on_replay: Callable[[int], None] | None = None,
) -> dict | None:
    """Write (or reuse) a filled clip of ``[start, start + duration]``.

    Returns ``{"path", "key", "cached", "method"}``, or None when no fill
    layer touches the span. ``on_replay`` gets the frames done before the model
    first ran: after a stop they came from saved fills, so they say nothing
    about how long the rest will take.
    """
    method = known_method(method)
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
        method=method, model_stamp=method_stamp(method, directory),
    )
    cache_dir = Path(cache_dir)
    output = cache_dir / f"{key}.mp4"
    if output.is_file() and output.stat().st_size > 1024:
        return {"path": str(output), "key": key, "cached": True, "method": method}
    cache_dir.mkdir(parents=True, exist_ok=True)
    part = cache_dir / f".{key}.part.mp4"
    saved = counted = None

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
        if on_replay is not None and counted is not None and counted.runs == 0:
            on_replay(index + 1)
        if progress and index % 10 == 0:
            reused = f" · {saved.hits} saved fills reused" if saved is not None and saved.hits else ""
            progress(min(1.0, (index + 1) / expected), f"{METHOD_COPY[method]} {index + 1}/{expected}{reused}")

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
        counted = _CountedFiller(filler)
        _prune_saved(cache_dir / SAVED_DIR)
        saved = filler = _SavedFills(
            counted, cache_dir / SAVED_DIR, method_stamp(method, directory),
        )
        plan_for = lama_plan(layers, start=start, fps=fps, frames=len(rect_table))
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
        stream = fill_frames_lama(
            source_frames, rects_for, filler, None,
            on_frame=on_frame, cancelled=cancelled, step=lama_step(fps),
            plan_for=plan_for, **extra,
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
        took = time.monotonic() - started
        saved.forget()
        LOGGER.info(
            "fill span start=%.2f frames=%d runs=%d units=%.1f seconds=%.1f per_frame=%.2f reused=%d",
            start, written, counted.runs, counted.units, took, took / max(1, written), saved.hits,
        )
        # A resumed clip spent little time on what it reused: not a speed to learn.
        if written >= RATE_MIN_FRAMES and not saved.hits:
            units = counted.units + written * LAMA_FRAME_UNITS
            record_rate(data_root, method, units, took)
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
