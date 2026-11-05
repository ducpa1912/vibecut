"""Full-source Clean renderer for Classic.

Source Clean removes text from the whole source, at the source's own size,
frame rate and audio. It is a separate renderer from the cut: there is no
crop, no 9:16 canvas and no beat trimming.

The worker is small on purpose. It validates nothing itself; ``routes_classic``
normalizes the boxes with the same Edit validator the cut uses. This module
owns the cache key, the fill pre-pass, the encode and the audio mux, so the
route stays a thin HTTP shell.

AI fill is LaMa only. Blur uses ``compose_render._clean_filters`` so a box
blurs the same pixels here as on a cut. Crop guard is refused by the route:
cropping the whole source would silently change the deliverable.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable

import compose_render
import job_queue
import render
import textfill

VERSION = 1
RECORD_KEY = "source_clean"
ACTIVE = {"queued", "running"}

#: One worker: a fill already uses the one model lock, and two source renders
#: at once would fight for the same memory on an 8 GB Mac.
POOL = job_queue.Scheduler(
    "source-clean", max_workers=1, thread_name_prefix="vibecut-source-clean",
)

#: Serializes the start reservation, so two requests cannot both see an idle
#: record and then submit different cache keys for the same job.
_START_LOCK = threading.Lock()

#: One cancel event per job's current render. A new start replaces it.
CANCELS: dict[str, threading.Event] = {}
_CANCEL_LOCK = threading.Lock()


class SourceCleanCancelled(RuntimeError):
    """The founder pressed Cancel while the source render was running."""


class SourceCleanError(RuntimeError):
    """The render could not produce a complete file."""


def source_clip(duration: float) -> dict:
    """The full-source clip every Source Clean body uses.

    It matches the shape the browser will send later (``classicPlanClips``):
    one clip, scene 0, source time starting at zero.
    """
    total = max(0.0, round(float(duration or 0.0), 3))
    return {
        "scene": 0,
        "start": 0.0,
        "end": total,
        "dur": total,
        "role": "source",
    }


def _app():
    import app

    return app


def _record(job: dict) -> dict:
    value = job.get(RECORD_KEY)
    return dict(value) if isinstance(value, dict) else {}


def _set(job_id: str, **values) -> dict:
    app = _app()

    def mutate(job: dict) -> None:
        record = dict(job.get(RECORD_KEY) or {})
        record.update(values)
        record["updated"] = round(time.time(), 3)
        job[RECORD_KEY] = record

    return _record(app.update_job(job_id, mutate))


def _idle() -> dict:
    return {
        "status": "idle",
        "progress": 0.0,
        "message": "No Source Clean render has run.",
        "error": None,
        "cached": False,
    }


def _live_task(record: dict):
    task_id = str(record.get("task_id") or "")
    if not task_id:
        return None
    task = POOL.get(task_id)
    if task is None or task.terminal:
        return None
    return task


def get(job_id: str) -> dict:
    """The current Source Clean record, with a stale run reported honestly."""
    app = _app()
    job = app.load_job(job_id)
    record = _record(job)
    if not record:
        return _idle()
    if (
        record.get("status") in ACTIVE
        and record.get("task_id")
        and _live_task(record) is None
    ):
        key = str(record.get("key") or "")
        _clean_parts(app._job_dir(job_id), key)
        return _set(
            job_id,
            status="failed",
            progress=1.0,
            message="Clean stopped",
            error=(
                "The Source Clean render stopped before it finished. "
                "Start it again."
            ),
            path=None,
            url=None,
            cached=False,
        )
    return record


def _visible_layers(layers: Iterable[dict]) -> list[dict]:
    return [
        dict(layer) for layer in layers or []
        if isinstance(layer, dict) and not layer.get("hidden")
    ]


def _fill_layers(layers: list[dict]) -> list[dict]:
    return [layer for layer in layers if layer.get("kind") == "fill"]


def _engine(layers: list[dict]) -> str | None:
    engines = {
        textfill.known_method(layer.get("method") or layer.get("engine") or "lama")
        for layer in _fill_layers(layers)
    }
    if not engines:
        return None
    # Classic stores one engine per box, and only LaMa is supported. A mixed
    # list still runs as the one engine, exactly like the cut renderer.
    return "lama" if "lama" in engines else sorted(engines)[0]


def _source_values(job: dict) -> tuple[dict, float, int, int, float, float]:
    source = job.get("source") or {}
    duration = float(source.get("duration") or 0.0)
    width = int(source.get("width") or 0)
    height = int(source.get("height") or 0)
    fps = float(source.get("fps") or 0.0)
    rotation = float(source.get("rotation") or 0.0)
    return source, duration, width, height, fps, rotation


def _cache_layer(layer: dict) -> dict:
    """Only the layer fields that can change the rendered pixels.

    ``fill_keys`` already lives in the fill pre-pass key, but the final file
    cache must include it too: a different key rate writes different pixels.
    Labels, scan provenance and text identity are deliberately absent: a
    re-scan or relabel of the same box must reuse the same file.
    """
    keys = (
        "kind", "method", "engine", "box", "ranges", "color", "opacity",
        "radius", "z", "mask", "tracklet_id", "fill_keys", "hidden",
    )
    return {key: layer.get(key) for key in keys if key in layer}


def _cache_key(
    job: dict,
    layers: list[dict],
    duration: float,
    engine: str | None,
    model_stamp: str,
) -> str:
    source = job.get("source") or {}
    payload = {
        "version": VERSION,
        "fingerprint": (
            source.get("fingerprint")
            or f"{source.get('size')}:{source.get('duration')}"
        ),
        "duration": round(float(duration), 6),
        "size": [int(source.get("width") or 0), int(source.get("height") or 0)],
        "fps": round(float(source.get("fps") or 0.0), 6),
        "rotation": float(source.get("rotation") or 0.0),
        "layers": [_cache_layer(layer) for layer in layers],
        "methods": [engine] if engine else ["blur"],
        "models": {engine: model_stamp} if engine else {},
        "text_mask": textfill.text_mask_enabled(),
        "renderer": compose_render.SCHEMA_VERSION,
        "encoder": "h264/yuv420p",
        "chunk_seconds": CHUNK_SECONDS,
        "max_chunk_rects": MAX_CHUNK_RECTS,
    }
    return hashlib.sha1(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8"),
    ).hexdigest()[:24]


def _dirs(job_id: str) -> tuple[Path, Path, Path]:
    app = _app()
    job_dir = app._job_dir(job_id)
    return job_dir, job_dir / "clean" / "source", job_dir / "fill" / "source"


def _clean_parts(job_dir: Path, key: str = "") -> None:
    """Remove a cancel's partial file. Never touches a finished result."""
    cache = job_dir / "clean" / "source"
    if key:
        (cache / f".{key}.part.mp4").unlink(missing_ok=True)
    for path in cache.glob(".*.part.mp4"):
        path.unlink(missing_ok=True)


def _ready_message(width: int, height: int, duration: float, cached: bool) -> str:
    tail = " · reused" if cached else ""
    return f"Clean video ready · {width}×{height} · {duration:.1f}s{tail}"


def _started(job_id: str, layers: list[dict]) -> dict:
    app = _app()
    job = app.load_job(job_id)
    app.require_source(job)
    source, duration, width, height, fps, rotation = _source_values(job)
    if duration <= 0.0:
        raise SourceCleanError("This source has no readable duration.")
    if width < 2 or height < 2 or fps <= 0.0:
        raise SourceCleanError(
            "This source has no readable width, height and frame rate."
        )
    if width % 2 or height % 2:
        raise SourceCleanError(
            f"H.264/yuv420p needs even width and height; this source is "
            f"{width}×{height}. Pad it first or use an even-size source."
        )
    visible = _visible_layers(layers)
    if not visible:
        raise SourceCleanError("No Clean boxes to render.")
    if any(
        layer.get("kind") == "crop_guard" or layer.get("method") == "crop"
        for layer in visible
    ):
        raise SourceCleanError(
            "Crop guard would crop the whole source. Source Clean keeps the "
            "full frame; use Blur or AI fill."
        )
    engine = _engine(visible)
    model_stamp = ""
    if engine:
        directory = textfill.models_dir(app.DATA)
        problem = textfill.missing_model(engine, directory)
        if problem:
            raise SourceCleanError(problem)
        model_stamp = textfill.method_stamp(engine, directory)

    record = _record(job)
    if record.get("status") in ACTIVE and _live_task(record) is not None:
        raise SourceCleanError("A Source Clean render is already running.")

    check_started = time.monotonic()
    key = _cache_key(job, visible, duration, engine, model_stamp)
    job_dir, cache_dir, _fill_cache = _dirs(job_id)
    final = cache_dir / f"{key}.mp4"
    check_seconds = round(time.monotonic() - check_started, 3)
    base = {
        "key": key,
        "method": engine or "blur",
        "methods": [engine] if engine else ["blur"],
        "layers": len(visible),
        "width": width,
        "height": height,
        "fps": round(fps, 3),
        "rotation": round(rotation, 3),
        "duration": round(duration, 3),
        "has_audio": bool(source.get("has_audio")),
        "path": str(final),
        "url": f"/api/classic/jobs/{job_id}/clean/source/media?v={key}",
    }

    # Reserve the job under one lock. Two clicks, or two tabs, must not both
    # decide the record is idle and then submit different keys for one job.
    with _START_LOCK:
        latest = app.load_job(job_id)
        record = _record(latest)
        if record.get("status") in ACTIVE and _live_task(record) is not None:
            raise SourceCleanError("A Source Clean render is already running.")
        active = POOL.find_key("source-clean", job_id)
        if active is not None and not active.terminal:
            raise SourceCleanError(
                "A Source Clean render is still stopping. Try again in a moment."
            )
        if final.is_file() and final.stat().st_size > 1024:
            return _set(
                job_id,
                status="ready",
                progress=1.0,
                message=_ready_message(width, height, duration, True),
                error=None,
                cached=True,
                timings={
                    "check": check_seconds, "fill": 0.0, "encode": 0.0, "mux": 0.0,
                },
                **base,
            )

        cache_dir.mkdir(parents=True, exist_ok=True)
        _clean_parts(job_dir, key)
        event = threading.Event()
        with _CANCEL_LOCK:
            CANCELS[job_id] = event
        _set(
            job_id,
            status="queued",
            progress=0.0,
            message="Queued for Clean",
            error=None,
            cached=False,
            timings={
                "check": check_seconds, "fill": 0.0, "encode": 0.0, "mux": 0.0,
            },
            **base,
        )
        task = POOL.submit(
            _run_awake, job_id, visible, key, engine, check_seconds,
            task_kind="source-clean", task_key=job_id,
        )
        _set(job_id, task_id=task.id)
        return _record(app.load_job(job_id))


def _run_awake(*args, **kwargs) -> dict:
    """A whole video can fill for hours, so the Mac must not idle to sleep."""
    with render.keep_awake():
        return run(*args, **kwargs)


def start(job_id: str, layers: list[dict]) -> dict:
    """Start, or return the existing ready result, one full-source render."""
    try:
        return _started(job_id, layers)
    except SourceCleanError as exc:
        from fastapi import HTTPException

        status = 409 if (
            "already running" in str(exc).lower()
            or "still stopping" in str(exc).lower()
        ) else 422
        raise HTTPException(status, str(exc)) from exc


def cancel(job_id: str) -> dict:
    app = _app()
    job = app.load_job(job_id)
    record = _record(job)
    status = str(record.get("status") or "idle")
    if status not in ACTIVE:
        return {"ok": True, "cancelled": False, "status": status}

    with _CANCEL_LOCK:
        event = CANCELS.setdefault(job_id, threading.Event())
    event.set()

    # Re-read after setting the event. The worker may have finished while this
    # request waited; a ready result must never be overwritten as cancelled.
    current = _record(app.load_job(job_id))
    if current.get("status") not in ACTIVE:
        return {
            "ok": True,
            "cancelled": False,
            "status": str(current.get("status") or "idle"),
        }
    task = _live_task(current)
    if task is None or task.state is job_queue.QueueState.QUEUED:
        POOL.cancel_key("source-clean", job_id)
        _clean_parts(app._job_dir(job_id), str(current.get("key") or ""))

        def mark(current_job: dict) -> None:
            value = dict(current_job.get(RECORD_KEY) or {})
            if value.get("status") not in ACTIVE:
                return
            value.update(
                status="cancelled", progress=1.0, message="Cancelled", error=None,
                path=None, url=None, cached=False,
            )
            value["updated"] = round(time.time(), 3)
            current_job[RECORD_KEY] = value

    else:
        def mark(current_job: dict) -> None:
            value = dict(current_job.get(RECORD_KEY) or {})
            if value.get("status") not in ACTIVE:
                return
            value["message"] = "Stopping…"
            value["updated"] = round(time.time(), 3)
            current_job[RECORD_KEY] = value

    updated = _record(app.update_job(job_id, mark))
    final_status = str(updated.get("status") or "idle")
    # The worker may still be stopping. Do not answer "running": the UI just
    # asked to cancel. The stored record stays running until the worker settles,
    # so GET polling still reports the real state.
    response_status = "cancelling" if final_status in ACTIVE else final_status
    return {
        "ok": True,
        "cancelled": final_status in ACTIVE or final_status == "cancelled",
        "status": response_status,
    }


@contextmanager
def _stage(timings: dict[str, float], name: str):
    started = time.monotonic()
    try:
        yield
    finally:
        timings[name] = round(time.monotonic() - started, 3)


def _progress(job_id: str, event: threading.Event, low: float, high: float):
    def report(fraction: float, message: str) -> None:
        if event.is_set():
            raise SourceCleanCancelled("Clean cancelled.")
        value = max(0.0, min(1.0, float(fraction)))
        _set(
            job_id,
            status="running",
            progress=round(low + (high - low) * value, 4),
            message=message,
            error=None,
        )

    return report


#: A fill span is split so one request's in-memory rectangle table stays
#: bounded. The cap is frames × layers, not a wall-clock promise.
CHUNK_SECONDS = 30.0
MAX_CHUNK_RECTS = 250_000


def _overlaps(layer: dict, start: float, end: float) -> bool:
    ranges = layer.get("ranges") or []
    if not ranges:
        return True
    for item in ranges:
        try:
            low = float(item["start"])
            high = float(item["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if high > start + 1e-6 and low < end - 1e-6:
            return True
    return False


def _chunk_spans(
    duration: float, fps: float, layers: list[dict],
) -> list[tuple[float, float]]:
    """Split the source into bounded fill spans.

    A short clip or a handful of boxes stays one span, so the common path is
    unchanged. Many boxes or a long source become several spans; each request
    to ``prepare_span`` then builds a bounded rectangle table.
    """
    rate = float(fps or 0.0) or 30.0
    count = max(1, len(layers))
    span = min(CHUNK_SECONDS, MAX_CHUNK_RECTS / (count * rate))
    span = max(1.0, span)
    spans: list[tuple[float, float]] = []
    cursor = 0.0
    while cursor < duration - 1e-6:
        end = min(duration, cursor + span)
        if duration - end < 0.05:
            end = duration
        spans.append((round(cursor, 6), round(end, 6)))
        cursor = end
    return spans or [(0.0, round(duration, 6))]


def _fill_master(
    job_id: str,
    source: dict,
    duration: float,
    width: int,
    height: int,
    fps: float,
    layers: list[dict],
    engine: str,
    fill_cache: Path,
    tmp: Path,
    cancel: threading.Event,
) -> tuple[Path | None, bool]:
    """One video-only fill master, chunked when the plan is large.

    Returns ``(path, chunked)``. A chunked master is re-encoded once before
    muxing so the fill clips and the unfilled source chunks share one encode
    profile even if the concat demuxer copied them.
    """
    fill_layers = _fill_layers(layers)
    if not fill_layers:
        return None, False
    spans = _chunk_spans(duration, fps, fill_layers)
    if len(spans) == 1:
        result = textfill.prepare_span(
            source=str(source.get("path") or ""),
            meta=source,
            start=0.0,
            duration=duration,
            layers=fill_layers,
            method=engine,
            cache_dir=fill_cache,
            data_root=_app().DATA,
            progress=_progress(job_id, cancel, 0.05, 0.68),
            cancel_event=cancel,
        )
        return (Path(str(result["path"])) if result else None), False

    segments: list[Path] = []
    total = len(spans)
    for index, (start, end) in enumerate(spans):
        if cancel.is_set():
            raise SourceCleanCancelled("Clean cancelled.")
        active = [layer for layer in fill_layers if _overlaps(layer, start, end)]
        output = tmp / f"chunk_{index:04d}.mp4"
        clip: Path | None = None
        if active:
            low = 0.05 + 0.63 * index / total
            high = 0.05 + 0.63 * (index + 1) / total
            result = textfill.prepare_span(
                source=str(source.get("path") or ""),
                meta=source,
                start=start,
                duration=end - start,
                layers=active,
                method=engine,
                cache_dir=fill_cache,
                data_root=_app().DATA,
                progress=_progress(job_id, cancel, low, high),
                cancel_event=cancel,
            )
            if result:
                clip = Path(str(result["path"]))
        if clip is None:
            # This span has no AI fill. Encode it video-only so the concat
            # still covers the whole source; the final pass adds blur/audio.
            _encode(
                Path(str(source.get("path") or "")),
                [], end - start, width, height, fps, output, cancel,
                start=start,
            )
            clip = output
        if clip != output:
            try:
                os.link(clip, output)
            except OSError:
                shutil.copyfile(clip, output)
        segments.append(output)

    master = tmp / "fill_master.mp4"
    render._concat_video(tmp, master, segments, "draft", cancel)
    return master, True


def _encode(
    input_path: Path,
    filters: list[str],
    duration: float,
    width: int,
    height: int,
    fps: float,
    output: Path,
    cancel: threading.Event,
    *,
    start: float = 0.0,
) -> None:
    """Encode the full source frame, with the cut renderer's blur geometry."""
    chain = [
        *filters,
        f"scale={int(width)}:{int(height)}:flags=lanczos",
        "setsar=1",
        f"fps={float(fps):.6f}",
        "format=yuv420p",
    ]
    command = [
        render._ffmpeg(), "-y", "-v", "error",
        *(["-ss", f"{float(start):.6f}"] if start > 0.0 else []),
        "-i", str(input_path),
        "-t", f"{float(duration):.6f}",
        "-map", "0:v:0", "-an",
        "-vf", ",".join(part for part in chain if part),
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output),
    ]
    render._run(command, timeout=7200, cancel_event=cancel)


def _mux_audio(
    video: Path,
    source: Path,
    output: Path,
    duration: float,
    cancel: threading.Event,
) -> str:
    """Attach the source audio to the video-only master. Returns the mode."""
    base = [
        render._ffmpeg(), "-y", "-v", "error",
        "-i", str(video), "-i", str(source),
    ]
    copy_command = base + [
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "copy",
        "-t", f"{float(duration):.6f}",
        "-movflags", "+faststart",
        str(output),
    ]
    try:
        render._run(copy_command, timeout=1800, cancel_event=cancel)
        return "copy"
    except render.RenderCancelled:
        raise
    except render.PipelineError:
        if cancel.is_set():
            raise SourceCleanCancelled("Clean cancelled.")
    # Some source audio codecs cannot live in MP4. Keep the sound instead of
    # failing the whole render, and say so in the record.
    fallback = base + [
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-t", f"{float(duration):.6f}",
        "-movflags", "+faststart",
        str(output),
    ]
    render._run(fallback, timeout=1800, cancel_event=cancel)
    return "aac"


def run(
    job_id: str,
    layers: list[dict],
    key: str,
    engine: str | None,
    check_seconds: float = 0.0,
) -> dict:
    """Worker: fill, encode and mux one full-source file. Always terminal."""
    app = _app()
    job = app.load_job(job_id)
    source, duration, width, height, fps, _rotation = _source_values(job)
    job_dir, cache_dir, fill_cache = _dirs(job_id)
    final = cache_dir / f"{key}.mp4"
    part = cache_dir / f".{key}.part.mp4"
    tmp = cache_dir / f".{key}.{uuid.uuid4().hex}.tmp"
    timings = {"check": check_seconds, "fill": 0.0, "encode": 0.0, "mux": 0.0}
    fill_layers = _fill_layers(layers)
    with _CANCEL_LOCK:
        cancel = CANCELS.setdefault(job_id, threading.Event())
    locked = False

    _set(
        job_id,
        status="running",
        progress=0.02,
        message="Checking the source",
        error=None,
        cached=False,
        timings=dict(timings),
    )
    try:
        if cancel.is_set():
            raise SourceCleanCancelled("Clean cancelled.")
        with _stage(timings, "check"):
            if final.is_file() and final.stat().st_size > 1024:
                return _set(
                    job_id,
                    status="ready",
                    progress=1.0,
                    message=_ready_message(width, height, duration, True),
                    error=None,
                    cached=True,
                    path=str(final),
                    timings=dict(timings),
                )
            tmp.mkdir(parents=True, exist_ok=True)
            _clean_parts(job_dir, key)

        if cancel.is_set():
            raise SourceCleanCancelled("Clean cancelled.")
        video: Path | None = None
        chunked = False
        with _stage(timings, "fill"):
            if engine and fill_layers:
                _set(
                    job_id, status="running", progress=0.05,
                    message="Cleaning text with AI fill", error=None,
                )
                # The cut renderer holds this lock for its fill pre-pass. A
                # preview must not release the model sessions underneath us.
                while not render.FILL_LOCK.acquire(timeout=0.2):
                    if cancel.is_set():
                        raise SourceCleanCancelled("Clean cancelled.")
                locked = True
                video, chunked = _fill_master(
                    job_id,
                    source,
                    duration,
                    width,
                    height,
                    fps,
                    layers,
                    engine,
                    fill_cache,
                    tmp,
                    cancel,
                )
        timings["fill"] = round(timings.get("fill", 0.0), 3)

        if cancel.is_set():
            raise SourceCleanCancelled("Clean cancelled.")
        filters, applied, warnings = compose_render._clean_filters(
            layers, 0.0, duration, width, height,
        )
        with _stage(timings, "encode"):
            if video is not None and not filters and not chunked:
                # The fill pre-pass already wrote H.264/yuv420p at the source
                # size and rate. It is the video master.
                pass
            else:
                _set(
                    job_id, status="running", progress=0.74,
                    message="Encoding H.264", error=None,
                )
                encoded = tmp / "video.mp4"
                _encode(
                    video or Path(str(source.get("path") or "")),
                    filters, duration, width, height, fps, encoded, cancel,
                )
                video = encoded

        if cancel.is_set():
            raise SourceCleanCancelled("Clean cancelled.")
        with _stage(timings, "mux"):
            _set(
                job_id, status="running", progress=0.94,
                message=(
                    "Adding the source audio"
                    if source.get("has_audio") else "Writing the MP4"
                ),
                error=None,
            )
            if video is None:
                raise SourceCleanError("The Clean render produced no video.")
            if source.get("has_audio"):
                audio_mode = _mux_audio(
                    video, Path(str(source.get("path") or "")), part, duration, cancel,
                )
            else:
                audio_mode = "none"
                shutil.copyfile(video, part)
            if cancel.is_set():
                raise SourceCleanCancelled("Clean cancelled.")
            if not part.is_file() or part.stat().st_size <= 1024:
                raise SourceCleanError("Clean could not write the MP4.")
            os.replace(part, final)

        return _set(
            job_id,
            status="ready",
            progress=1.0,
            message=_ready_message(width, height, duration, False),
            error=None,
            cached=False,
            path=str(final),
            audio_mode=audio_mode,
            applied=applied,
            warnings=warnings,
            timings=dict(timings),
        )
    except (SourceCleanCancelled, textfill.FillCancelled, render.RenderCancelled):
        part.unlink(missing_ok=True)
        return _set(
            job_id,
            status="cancelled",
            progress=1.0,
            message="Cancelled",
            error=None,
            cached=False,
            path=None,
            url=None,
            timings=dict(timings),
        )
    except Exception as exc:  # noqa: BLE001
        part.unlink(missing_ok=True)
        return _set(
            job_id,
            status="failed",
            progress=1.0,
            message="Clean failed",
            error=str(exc)[:2400],
            cached=False,
            path=None,
            url=None,
            timings=dict(timings),
        )
    finally:
        part.unlink(missing_ok=True)
        shutil.rmtree(tmp, ignore_errors=True)
        # A finished, failed or cancelled fill must not keep a 208 MB model
        # session alive beside the next render. A blur-only run never had one,
        # and must not evict a concurrent cut render's model.
        if locked:
            textfill.release_fillers()
            render.FILL_LOCK.release()
