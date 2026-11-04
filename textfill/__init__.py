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
from pathlib import Path
from typing import Callable, Iterable

import numpy as np

from . import mask as masks

METHODS = ("sttn", "lama")
DEFAULT_METHOD = "sttn"
VERSION = 3
MODEL_FILES = {"sttn": "sttn_infer_model.pth", "lama": "lama_fp32.onnx"}
MODEL_PACKAGES = {"sttn": "torch", "lama": "onnxruntime"}
METHOD_COPY = {"sttn": "STTN (video)", "lama": "LaMa (per frame)"}
# Share of the previous frame's fill kept on LaMa output, to calm flicker.
LAMA_CARRY = 0.3

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
    return Path(directory) / MODEL_FILES[method]


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
    package = MODEL_PACKAGES[method]
    if importlib.util.find_spec(package) is None:
        return f"{METHOD_COPY.get(method, method)} fill needs the {package} package on this Mac."
    return None


def text_mask_enabled() -> bool:
    """Narrow scan layers to the text itself. Set off to fill the whole box."""
    value = os.environ.get("VIBECUT_FILL_TEXT_MASK", "on").strip().lower()
    return value not in {"0", "off", "false", "no"}


def _model_stamp(path: Path) -> str:
    stat = path.stat()
    return f"{path.name}:{stat.st_size}:{stat.st_mtime_ns}"


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
        path = model_path(method, directory)
        present = path.is_file() and path.stat().st_size > 0
        parts.append([method, _model_stamp(path) if present else "missing"])
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
    payload = {
        "version": VERSION,
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
                else:
                    from .lama import LamaFiller
                    filler = LamaFiller(path)
            except ImportError as exc:
                package = "torch" if method == "sttn" else "onnxruntime"
                raise FillError(
                    f"{METHOD_COPY[method]} fill needs the {package} package on this Mac."
                ) from exc
            _FILLERS[key] = filler
        return filler


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


def fill_frames_lama(frames, rects_for, filler, area, *, on_frame=None, cancelled=None, hole_for=None):
    """Yield filled frames. ``rects_for(index)`` gives that frame's rects.

    ``hole_for(index, x0, y0, x1, y1)`` narrows the hole; without it the hole
    is the rects themselves.
    """
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
            if previous is not None:
                filled = np.clip(
                    filled.astype(np.float32) * (1 - LAMA_CARRY)
                    + previous.astype(np.float32) * LAMA_CARRY,
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

    The single-frame preview uses LaMa: it is the per-frame engine, so one
    frame is a supported input. STTN needs neighbouring frames and is left to
    the full render.
    """
    if method != "lama":
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
        method=method, model_stamp=_model_stamp(path),
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
            finder = masks.TextMasks(
                masks.frame_rects(tight_layers, **size),
                masks.frame_rects(exact_layers, **size),
                width, height,
            )

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
    try:
        _check_cancel(cancelled)
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
            area = masks.lama_area(span_rects, width, height)
            stream = fill_frames_lama(
                source_frames, rects_for, filler, area,
                on_frame=on_frame, cancelled=cancelled, **extra,
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
