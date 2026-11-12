"""Minimal DuckSuite render: cut clips, fill clean layers, concat."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from duckcore import caption_burn, captions, edits, effects, media
from duckcore.store import ProjectStore

LOGGER = logging.getLogger(__name__)


class RenderError(RuntimeError):
    pass


class RenderCancelled(RenderError):
    pass


def _target_size(meta: dict) -> tuple[int, int]:
    width = max(2, int(meta.get("width") or 0))
    height = max(2, int(meta.get("height") or 0))
    if width >= height:
        out_h = 1080
        out_w = max(2, int(round(width * out_h / height)))
    else:
        out_w = 1080
        out_h = max(2, int(round(height * out_w / width)))
    return out_w + (out_w % 2), out_h + (out_h % 2)


def _video_codec() -> list[str]:
    override = os.environ.get("DUCK_RENDER_ENCODER", "").strip().lower()
    if override in {"h264_videotoolbox", "videotoolbox"} or (
        not override and sys.platform == "darwin"
    ):
        return ["-c:v", "h264_videotoolbox", "-q:v", "65"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]


def _clean_message(value: Any) -> str:
    text = str(value or "")
    text = "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)
    return text[-1000:]


def _run(command: list[str], timeout: float = 3600) -> None:
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RenderError(_clean_message(result.stderr or result.stdout or "ffmpeg failed"))


def _fill_layers(edit: dict) -> list[dict]:
    return [
        layer for layer in edit.get("clean") or []
        if isinstance(layer, dict)
        and layer.get("enabled") is not False
        and layer.get("kind") == "fill"
    ]


def _blur_layers(edit: dict) -> list[dict]:
    return [
        layer for layer in edit.get("clean") or []
        if isinstance(layer, dict)
        and layer.get("enabled") is not False
        and layer.get("kind") == "blur"
    ]


def _blur_filter(
    edit: dict,
    meta: dict,
    *,
    clip_start: float,
    target_fps: float,
    at: float | None = None,
) -> str:
    from duckcore.engine.textfill import mask as textmask

    out_w, out_h, scale = _scale_filter(meta, target_fps)
    width = int(meta.get("width") or 0)
    height = int(meta.get("height") or 0)
    layers = _blur_layers(edit)
    if not layers or width < 2 or height < 2:
        return scale
    parts: list[str] = []
    base = "0:v"
    used = 0
    for index, layer in enumerate(layers):
        rect = textmask.layer_rect(layer, width, height)
        x0, y0, x1, y1 = rect
        if x1 <= x0 or y1 <= y0:
            continue
        ranges = [
            (max(0.0, float(item.get("start") or 0.0) - clip_start),
             max(0.0, float(item.get("end") or 0.0) - clip_start))
            for item in layer.get("ranges") or []
            if item.get("end") is not None
        ]
        if at is not None:
            active = not ranges or any(lo <= at - clip_start <= hi for lo, hi in ranges)
            if not active:
                continue
            enable = ""
        else:
            enable = ""
            if ranges:
                enable = ":enable='" + "+".join(
                    f"between(t,{lo:.3f},{hi:.3f})" for lo, hi in ranges
                ) + "'"
        label = f"blur{used}"
        base_out = f"base{used}"
        out = f"v{used}"
        parts.append(f"[{base}]split=2[{base_out}][crop{used}]")
        parts.append(
            f"[crop{used}]crop={x1-x0}:{y1-y0}:{x0}:{y0},gblur=sigma=18[{label}]"
        )
        parts.append(f"[{base_out}][{label}]overlay=x={x0}:y={y0}{enable}[{out}]")
        base = out
        used += 1
    if not used:
        return scale
    parts.append(f"[{base}]{scale}")
    return ";".join(parts)


def _scale_filter(meta: dict, target_fps: float) -> tuple[int, int, str]:
    out_w, out_h = _target_size(meta)
    return out_w, out_h, (
        f"scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,"
        f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps={target_fps}"
    )


def proof_window(start: float, duration: float, when: float, size: float = 0.6) -> tuple[float, float]:
    """Source-time window a proof fills around one frame.

    A proof needs local temporal context, not the whole scene. Keep at least
    0.2 s so a single-frame fill still has a neighbour to blend against.
    """
    start = max(0.0, float(start))
    duration = max(0.04, float(duration))
    when = max(start, min(start + duration, float(when)))
    size = max(0.2, min(duration, float(size)))
    first = max(start, min(when - size / 2, start + duration - size))
    last = min(start + duration, max(first + size, when + size / 2))
    if last - first < 0.2:
        first = max(start, last - 0.2)
    return first, last


def _check_output(output: Path, edit: dict, meta: dict, *, source: str,
                  inks: dict, fps: float, data_root: Path,
                  size: tuple[int, int] | None = None) -> dict:
    from duckcore import inkcheck

    started = time.monotonic()
    report = inkcheck.check(output, edit, meta, source=source, inks=inks, fps=fps, size=size)
    report["seconds"] = round(time.monotonic() - started, 1)
    remember_check_time(data_root, int(report.get("layers") or 0), report["seconds"])
    return report


def _merge_spans(spans: list[tuple[float, float]]) -> list[dict]:
    out: list[list[float]] = []
    for start, end in sorted(spans):
        if out and start <= out[-1][1] + 1e-6:
            out[-1][1] = max(out[-1][1], end)
        else:
            out.append([start, end])
    return [{"start": round(start, 3), "end": round(end, 3)} for start, end in out]


def _inked_layers(layers: list[dict], inks: dict, meta: dict) -> tuple[list[dict], dict]:
    """Fill layers with their strokes as the hole, and the strokes by rect.

    A scan layer whose ink is known is filled on its glyphs' own pixels, and for
    as long as each glyph is really on screen: the range is widened to the ink,
    never narrowed. A drawn box or a brush stroke means "remove this area" and
    is left as the user made it.
    """
    import hashlib

    import numpy as np

    from duckcore import inkcheck
    from duckcore.engine.textfill import mask as masks

    width = int(meta.get("width") or 0)
    height = int(meta.get("height") or 0)
    fps = float(meta.get("fps") or 30.0)
    out: list[dict] = []
    strokes: dict = {}
    for layer in layers:
        built = (inks.get(str(layer.get("id"))) or {}).get("inks") or []
        found = inkcheck.layer_strokes(built) if built and masks.uses_text_mask(layer, width, height) else None
        if found is None or not found[1]:
            out.append(layer)
            continue
        rect, pieces = found
        digest = hashlib.sha1(repr(rect).encode())
        for first, last, hole in pieces:
            digest.update(f"{first}:{last}:".encode())
            digest.update(np.packbits(hole).tobytes())
        spans = [
            (float(item.get("start") or 0.0), float(item.get("end") or 0.0))
            for item in layer.get("ranges") or []
        ]
        # One frame of guard each side: a fading frame under the threshold.
        spans += [(max(0.0, (first - 1) / fps), (last + 2) / fps) for first, last, _hole in pieces]
        strokes.setdefault(rect, []).extend(pieces)
        prepared = {
            **layer, "ink_rect": list(rect), "ink_key": digest.hexdigest()[:16],
            "ranges": _merge_spans(spans),
        }
        # The strokes do not move, so the box does not follow a track.
        prepared.pop("track", None)
        out.append(prepared)
    return out, strokes


def _widen_edit(edit: dict, hits: list[dict], fps: float) -> dict | None:
    """A copy of the edit whose layers also cover the frames that kept text."""
    by_layer: dict[str, list[float]] = {}
    for hit in hits:
        by_layer.setdefault(str(hit.get("layer")), []).append(
            float(hit.get("source_time", hit.get("time")) or 0.0)
        )
    if not by_layer:
        return None
    step = 1.0 / max(1.0, float(fps))
    clean = []
    changed = False
    for layer in edit.get("clean") or []:
        times = by_layer.get(str(layer.get("id"))) if isinstance(layer, dict) else None
        if not times:
            clean.append(layer)
            continue
        spans = [
            (float(item.get("start") or 0.0), float(item.get("end") or 0.0))
            for item in layer.get("ranges") or []
        ]
        spans += [(max(0.0, at - 2 * step), at + 3 * step) for at in times]
        ranges = _merge_spans(spans)
        changed = changed or ranges != _merge_spans(spans[:len(layer.get("ranges") or [])])
        clean.append({**layer, "ranges": ranges})
    if not changed:
        return None
    return {**edit, "clean": clean}


def render_frame(
    project: dict,
    edit: dict,
    data_root: Path,
    output: Path,
    *,
    when: float,
    progress: Callable[[float, str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> Path:
    """Extract one frame through the exact render/fill pipeline.

    The proof uses the same fill layers, masks, key plan, ``prepare_span``
    cache and scale/pad/fps filter. It fills a short window around the frame
    instead of the whole scene, so a proof does not take minutes.
    """
    from duckcore.engine import pipeline, textfill

    device = _fill_device(Path(data_root))
    source = str(project["source_path"])
    meta = pipeline.probe(source)
    fps = float(meta.get("fps") or 30.0)
    target_fps = 24 if abs(fps - 24.0) < 0.6 else 30
    clips = [
        clip for clip in edit.get("clips") or []
        if float(clip.get("end") or 0) > float(clip.get("start") or 0)
    ]
    if not clips:
        raise RenderError("This edit has no clips.")
    requested = max(0.0, float(when))
    clip = next(
        (
            item for item in clips
            if float(item.get("start") or 0.0) <= requested < float(item.get("end") or 0.0)
        ),
        clips[-1],
    )
    start = float(clip.get("start") or 0.0)
    duration = max(0.04, float(clip.get("end") or 0.0) - start)
    job_dir = Path(data_root) / "projects" / str(project["id"])
    layers = _fill_layers(edit)
    filled = None
    if layers:
        # A proof fills a short window around the requested frame, not the
        # whole scene. It uses the same fills, masks and blend rules, while a
        # 46 s video no longer spends minutes on the first proof.
        proof_start, proof_end = proof_window(start, duration, requested)
        filled = textfill.prepare_span(
            source=source,
            meta=meta,
            start=proof_start,
            duration=proof_end - proof_start,
            layers=layers,
            method="lama",
            cache_dir=job_dir / "fill",
            data_root=data_root,
            ffmpeg=media.ffmpeg(),
            device=device,
            cancel_event=cancel_event,
            progress=(
                (lambda fraction, message: progress(
                    max(0.0, min(0.95, float(fraction))), message,
                ))
                if progress is not None else None
            ),
        )
    input_path = Path(filled["path"]) if filled else Path(source)
    offset = requested - proof_start if filled else requested
    out_w, out_h, scale = _scale_filter(meta, target_fps)
    video_filter = _blur_filter(
        edit, meta, clip_start=start, target_fps=target_fps, at=requested,
    )
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        media.ffmpeg(), "-y", "-v", "error",
        "-hwaccel", "none", "-ss", f"{max(0.0, offset):.6f}", "-i", str(input_path),
        "-frames:v", "1", "-vf", video_filter,
    ]
    if output.suffix.lower() in {".jpg", ".jpeg"}:
        command += ["-q:v", "2"]
    command.append(str(output))
    _run(command)
    if not output.is_file():
        raise RenderError("The render frame could not be written.")
    if progress:
        progress(1.0, "Render frame ready")
    return output


def _fill_device(data_root: Path) -> str:
    """The chip fill uses: the setting, and only when that chip can run here."""
    from duckcore import app_settings
    from duckcore.engine import textfill

    return textfill.chosen_device(
        "lama", app_settings.fill_device(data_root), textfill.models_dir(data_root),
    )


RENDER_RATES_FILE = "render_rates.json"
RENDER_RATE_SAMPLES = 3


def _render_rates(data_root: Path) -> list[float]:
    """Seconds of whole render per second of output, measured on this Mac."""
    try:
        stored = json.loads((Path(data_root) / RENDER_RATES_FILE).read_text(encoding="utf-8"))
        return [float(value) for value in stored.get("ratios") or [] if float(value) > 0][-RENDER_RATE_SAMPLES:]
    except (OSError, ValueError, TypeError):
        return []


def remember_render_time(data_root: Path, duration: float, seconds: float) -> None:
    if duration <= 1 or seconds <= 0:
        return
    path = Path(data_root) / RENDER_RATES_FILE
    ratios = _render_rates(data_root)
    ratios = [*ratios, round(float(seconds) / float(duration), 4)][-RENDER_RATE_SAMPLES:]
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"ratios": ratios}, indent=1), encoding="utf-8")
    temporary.replace(path)


CHECK_RATE_SAMPLES = 3


def remember_check_time(data_root: Path, layers: int, seconds: float) -> None:
    if layers <= 0 or seconds <= 0:
        return
    path = Path(data_root) / RENDER_RATES_FILE
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        stored = {}
    checks = [float(value) for value in stored.get("checks") or [] if float(value) > 0]
    checks = [*checks, round(float(seconds) / float(layers), 4)][-CHECK_RATE_SAMPLES:]
    stored["checks"] = checks
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(stored, indent=1), encoding="utf-8")
    temporary.replace(path)


def _check_rate(data_root: Path) -> float | None:
    try:
        stored = json.loads((Path(data_root) / RENDER_RATES_FILE).read_text(encoding="utf-8"))
        checks = sorted(float(value) for value in stored.get("checks") or [] if float(value) > 0)
    except (OSError, ValueError, TypeError):
        return None
    if not checks:
        return None
    return checks[len(checks) // 2]


def _render_ratio(data_root: Path) -> float | None:
    ratios = sorted(_render_rates(data_root))
    if not ratios:
        return None
    return ratios[len(ratios) // 2]


_ESTIMATE_LOCK = threading.Lock()
_ESTIMATE_JOBS: dict[str, dict] = {}
_ESTIMATE_QUEUE: list[tuple] = []
_ESTIMATE_WAKE = threading.Event()
_ESTIMATE_THREAD: threading.Thread | None = None
_ESTIMATE_LAST: dict[str, dict] = {}


def _estimate_key(edit: dict, meta: dict) -> str:
    payload = {
        "edit": edit.get("id"),
        "updated": edit.get("updated"),
        "fill_device": None,
        "clean": [
            {
                "id": layer.get("id"), "kind": layer.get("kind"),
                "enabled": layer.get("enabled"), "box": layer.get("box"),
                "ranges": layer.get("ranges"), "quality": layer.get("quality"),
            }
            for layer in edit.get("clean") or [] if isinstance(layer, dict)
        ],
        "size": [meta.get("width"), meta.get("height")],
        "fps": meta.get("fps"),
        "path": meta.get("path"),
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:20]


def _ensure_estimate_worker() -> None:
    global _ESTIMATE_THREAD
    if _ESTIMATE_THREAD is None or not _ESTIMATE_THREAD.is_alive():
        _ESTIMATE_THREAD = threading.Thread(
            target=_estimate_worker, name="estimate", daemon=True,
        )
        _ESTIMATE_THREAD.start()


def _estimate_worker() -> None:
    """One worker: it takes one estimate job at a time, in order."""
    while True:
        job = None
        with _ESTIMATE_LOCK:
            if _ESTIMATE_QUEUE:
                job = _ESTIMATE_QUEUE.pop(0)
        if job is None:
            _ESTIMATE_WAKE.wait(0.5)
            _ESTIMATE_WAKE.clear()
            continue
        key, edit, meta, data_root = job
        try:
            result = estimate_edit(
                edit, meta, data_root,
                progress=(lambda fraction, message: _set_estimate_progress(key, fraction, message)),
            )
        except Exception as exc:  # noqa: BLE001 - the endpoint reports it, never crashes
            LOGGER.warning("estimate failed: %s", exc)
            with _ESTIMATE_LOCK:
                _ESTIMATE_JOBS[key].update(
                    state="ready", progress=1.0, error=str(exc)[:300],
                    message="The fill time could not be measured.",
                )
            continue
        with _ESTIMATE_LOCK:
            _ESTIMATE_JOBS[key].update(
                state="ready", progress=1.0, estimate=result,
                message="Fill time measured.", finished=time.time(),
            )
            _ESTIMATE_LAST[str(edit.get("id"))] = result


def _set_estimate_progress(key: str, fraction: float, message: str) -> None:
    with _ESTIMATE_LOCK:
        job = _ESTIMATE_JOBS.get(key)
        if job is not None and job["state"] == "working":
            job["progress"] = max(job["progress"], min(0.99, float(fraction)))
            job["message"] = message


def estimate_status(edit: dict, meta: dict, data_root: Path, *, wait: float = 0.3) -> dict:
    """Answer now. A cold estimate runs in the background; a warm one is ready.

    The request never blocks for more than ``wait`` seconds. One worker takes
    the jobs; a second request for the same edit joins the running one.
    """
    key = _estimate_key(edit, meta)
    with _ESTIMATE_LOCK:
        job = _ESTIMATE_JOBS.get(key)
        if job is None:
            previous = _ESTIMATE_LAST.get(str(edit.get("id")))
            job = {
                "state": "working", "progress": 0.0, "message": "Measuring the fill…",
                "estimate": previous, "stale": bool(previous), "error": "",
                "started": time.time(),
            }
            _ESTIMATE_JOBS[key] = job
            # Keep the map small: a project is edited all day.
            if len(_ESTIMATE_JOBS) > 16:
                for stale in list(_ESTIMATE_JOBS)[:-8]:
                    _ESTIMATE_JOBS.pop(stale, None)
            _ESTIMATE_QUEUE.append((key, edit, meta, Path(data_root)))
            _ensure_estimate_worker()
            _ESTIMATE_WAKE.set()
    if job["state"] != "ready" and wait > 0:
        deadline = time.monotonic() + float(wait)
        while time.monotonic() < deadline:
            with _ESTIMATE_LOCK:
                if _ESTIMATE_JOBS[key]["state"] == "ready":
                    break
            time.sleep(0.02)
    with _ESTIMATE_LOCK:
        job = dict(_ESTIMATE_JOBS[key])
    return {
        "state": job["state"],
        "progress": round(float(job.get("progress") or 0.0), 3),
        "message": job.get("message") or "",
        "estimate": job.get("estimate") or None,
        "stale": bool(job.get("stale")),
        "error": job.get("error") or "",
        "working_seconds": round(time.time() - float(job.get("started") or time.time()), 1)
        if job["state"] == "working" else 0.0,
    }


def wait_for_estimate(edit: dict, meta: dict, data_root: Path, *,
                      timeout: float = 900.0) -> dict:
    """A render asks the same worker for the estimate and takes its result."""
    key = _estimate_key(edit, meta)
    with _ESTIMATE_LOCK:
        job = _ESTIMATE_JOBS.get(key)
        state = job["state"] if job else None
    if state != "ready":
        estimate_status(edit, meta, data_root, wait=0.0)
        deadline = time.monotonic() + float(timeout)
        while time.monotonic() < deadline:
            with _ESTIMATE_LOCK:
                job = _ESTIMATE_JOBS.get(key)
                if job and job["state"] == "ready":
                    return job.get("estimate") or {}
            time.sleep(0.2)
        # Nothing came back: measure here rather than start the render blind.
        return estimate_edit(edit, meta, data_root)
    return (job or {}).get("estimate") or {}


def estimate_edit(edit: dict, meta: dict, data_root: Path,
                  progress: Callable[[float, str], None] | None = None) -> dict:
    """What a render of this edit will cost in AI fill, without running anything.

    Walks the same clips and fill layers as :func:`render_edit`, so the figure
    is for the spans the render will ask for, and a span already filled counts
    as done.
    """
    from duckcore.engine import textfill

    data_root = Path(data_root)
    cache = data_root / "projects" / str(edit.get("project_id") or "") / "fill"
    clean = [layer for layer in edit.get("clean") or [] if isinstance(layer, dict)]
    on = [layer for layer in clean if layer.get("enabled") is not False]
    layers = _fill_layers(edit)
    fps = float(meta.get("fps") or 0.0)
    device = _fill_device(data_root)
    source = str(meta.get("path") or "")
    strokes: dict = {}
    if layers and source:
        from duckcore import inkcheck

        inks = inkcheck.build_inks(
            edit, meta, source=source, data_root=data_root,
            progress=(lambda fraction, message: progress(
                0.4 * max(0.0, min(1.0, float(fraction))), message,
            )) if progress else None,
        )
        layers, strokes = _inked_layers(layers, inks, meta)
    store = data_root / "render_estimate_units.json"
    try:
        cached_units = json.loads(store.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cached_units = {}
    rows = []
    if layers:
        for clip in edit.get("clips") or []:
            start = float(clip.get("start") or 0.0)
            end = float(clip.get("end") or 0.0)
            if end <= start or str(clip.get("kind")) == "media":
                continue
            duration = max(0.04, end - start)
            key = textfill.units_key(meta, layers, start, duration)
            row = textfill.estimate_span(
                meta=meta, start=start, duration=duration, layers=layers,
                method="lama", cache_dir=cache, data_root=data_root,
                device=device, strokes=strokes or None, source=source,
                units_override=cached_units.get(key),
            )
            if strokes and row.get("units"):
                cached_units[key] = row["units"]
            rows.append(row)
    if strokes and cached_units:
        try:
            temporary = store.with_suffix(".tmp")
            temporary.write_text(json.dumps(cached_units, indent=1), encoding="utf-8")
            temporary.replace(store)
        except OSError:
            pass
    summary = textfill.estimate_summary(rows, data_root)
    filled_frames = sum(int(row.get("frames") or 0) for row in rows)
    timeline = sum(
        max(0.0, float(clip.get("end") or 0.0) - float(clip.get("start") or 0.0))
        for clip in edit.get("clips") or []
        if str(clip.get("kind")) != "media"
    )
    ratio = _render_ratio(data_root)
    check_layers = len([
        layer for layer in on if layer.get("kind") in {"fill", "blur"}
    ])
    check_seconds = round(check_layers * (_check_rate(data_root) or 2.2), 1)
    total = round(timeline * ratio + check_seconds, 1) if ratio and timeline > 0 else None
    if total is not None and not int(summary.get("beats_cached") or 0):
        # A cold render pays for every fill, so a warm whole-render ratio would
        # hide most of the wait. Take the fill estimate plus encoding instead.
        total = max(total, round(float(summary.get("seconds") or 0.0) + check_seconds
                                 + timeline * 0.25, 1))
    total_range = None
    spread = summary.get("rate_spread") or []
    fill_seconds = float(summary.get("seconds") or 0.0)
    if total is not None and spread and fill_seconds:
        low = sum(units * low_rate for units, low_rate, _high in spread)
        high = sum(units * high_rate for units, _low, high_rate in spread)
        overhead = total - fill_seconds
        total_range = [round(low + overhead, 1), round(high + overhead, 1)]
    return {
        **summary,
        "spans": rows,
        "total_range": total_range,
        "total_seconds": total,
        "total_measured": bool(total),
        "timeline_seconds": round(timeline, 1),
        "check_layers": check_layers,
        "check_seconds": check_seconds,
        "layers": {
            "fill": len(layers),
            "blur": sum(1 for layer in on if layer.get("kind") == "blur"),
            "off": len(clean) - len(on),
            "moving_fill": sum(1 for layer in layers if layer.get("quality") == "moving"),
        },
        # Seconds of video that carry a fill, done or not.
        "fill_seconds": round(filled_frames / fps, 1) if fps > 0 else 0.0,
        "disk": textfill.saved_fill_disk(cache),
    }


def render_edit(
    project: dict,
    edit: dict,
    data_root: Path,
    *,
    progress: Callable[[float, str], None] | None = None,
    cancel_event: threading.Event | None = None,
    check: bool = True,
    _retry: bool = True,
) -> Path:
    from duckcore.engine import pipeline, textfill

    def check_cancel() -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise RenderCancelled("Render cancelled.")

    device = _fill_device(Path(data_root))
    source = str(project["source_path"])
    meta = pipeline.probe(source)
    target_fps = 24 if abs(float(meta.get("fps") or 30.0) - 24.0) < 0.6 else 30
    out_w, out_h, scale = _scale_filter(meta, target_fps)
    started = time.monotonic()
    project_id = str(project["id"])
    job_dir = Path(data_root) / "projects" / project_id
    cache = job_dir / "fill"
    output_dir = job_dir / "renders"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    output = output_dir / f"{edit['id']}_{stamp}.mp4"
    clips = [clip for clip in edit.get("clips") or [] if float(clip.get("end") or 0) > float(clip.get("start") or 0)]
    if not clips:
        raise RenderError("This edit has no clips.")

    layers = _fill_layers(edit)
    inks: dict = {}
    strokes: dict = {}
    if check:
        # The ink is the line's own hole and the post-render check's reference.
        from duckcore import inkcheck

        if progress:
            progress(0.0, "Reading the text strokes")
        inks = inkcheck.build_inks(edit, meta, source=source, data_root=data_root)
        layers, strokes = _inked_layers(layers, inks, meta)
    segments: list[Path] = []
    ffmpeg = media.ffmpeg()
    try:
        for index, clip in enumerate(clips):
            check_cancel()
            start = float(clip.get("start") or 0.0)
            duration = max(0.04, float(clip.get("end") or 0.0) - start)
            if progress:
                progress(index / max(1, len(clips)), f"Rendering clip {index + 1}/{len(clips)}")
            if str(clip.get("kind")) == "media":
                media_path = job_dir / str(clip.get("file") or "")
                if not media_path.is_file():
                    raise RenderError("A story beat file is missing.")
                segment = output_dir / f".{edit['id']}_{index:04d}.mp4"
                offset = max(0.0, float(clip.get("offset") or 0.0))
                if str(clip.get("media")) == "image":
                    command = [
                        ffmpeg, "-y", "-v", "error",
                        "-loop", "1", "-framerate", str(target_fps), "-i", str(media_path),
                        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                        "-t", f"{duration:.6f}",
                        "-map", "0:v:0", "-map", "1:a:0",
                        "-vf", scale,
                        *_video_codec(), "-c:a", "aac", "-b:a", "192k",
                        "-shortest", str(segment),
                    ]
                else:
                    has_beat_audio = media.has_audio(media_path)
                    command = [
                        ffmpeg, "-y", "-v", "error",
                        "-ss", f"{offset:.6f}", "-t", f"{duration:.6f}", "-i", str(media_path),
                    ]
                    if not has_beat_audio:
                        command += [
                            "-f", "lavfi", "-i",
                            "anullsrc=channel_layout=stereo:sample_rate=48000",
                        ]
                    command += ["-map", "0:v:0"]
                    command += ["-map", "0:a:0" if has_beat_audio else "1:a:0"]
                    command += [
                        "-vf", scale,
                        *_video_codec(), "-c:a", "aac", "-b:a", "192k",
                        "-shortest", str(segment),
                    ]
                _run(command)
                segments.append(segment)
                continue
            filled = None
            if layers:
                filled = textfill.prepare_span(
                    source=source,
                    meta=meta,
                    start=start,
                    duration=duration,
                    layers=layers,
                    method="lama",
                    cache_dir=cache,
                    data_root=data_root,
                    ffmpeg=ffmpeg,
                    device=device,
                    strokes=strokes,
                    cancel_event=cancel_event,
                    progress=(
                        (lambda fraction, message: progress(
                            (index + max(0.0, min(1.0, float(fraction)))) / max(1, len(clips)),
                            message,
                        ))
                        if progress is not None else None
                    ),
                )
            segment = output_dir / f".{edit['id']}_{index:04d}.mp4"
            video_filter = _blur_filter(
                edit, meta, clip_start=start, target_fps=target_fps,
            )
            if filled:
                command = [
                    ffmpeg, "-y", "-v", "error",
                    "-hwaccel", "none", "-i", str(filled["path"]),
                    "-ss", f"{start:.6f}", "-t", f"{duration:.6f}", "-i", source,
                    "-map", "0:v:0", "-map", "1:a?",
                    "-vf", video_filter,
                    *_video_codec(),
                    "-c:a", "aac", "-b:a", "192k", "-shortest",
                    str(segment),
                ]
            else:
                command = [
                    ffmpeg, "-y", "-v", "error",
                    "-hwaccel", "none", "-ss", f"{start:.6f}", "-t", f"{duration:.6f}", "-i", source,
                    "-map", "0:v:0", "-map", "0:a?",
                    "-vf", video_filter,
                    *_video_codec(),
                    "-c:a", "aac", "-b:a", "192k", "-shortest",
                    str(segment),
                ]
            _run(command)
            segments.append(segment)

        if progress:
            progress(0.96, "Joining clips")
        listing = output_dir / f".{edit['id']}_concat.txt"
        listing.write_text(
            "".join(f"file '{segment.as_posix()}'\n" for segment in segments),
            encoding="utf-8",
        )
        _run([
            ffmpeg, "-y", "-v", "error",
            "-f", "concat", "-safe", "0", "-i", str(listing),
            "-c", "copy", "-movflags", "+faststart", str(output),
        ])
        listing.unlink(missing_ok=True)
        for segment in segments:
            segment.unlink(missing_ok=True)

        track = edit.get("captions")
        if captions.wants_srt(track) and track.get("cues"):
            output.with_suffix(".srt").write_text(captions.srt(track), encoding="utf-8")
            if track.get("burn"):
                if progress:
                    progress(0.97, "Burning captions")
                captioned = output.with_name(f".{output.stem}.captions.mp4")
                caption_burn.burn_captions(
                    output, track, captioned,
                    width=out_w, height=out_h, fps=float(target_fps), ffmpeg=ffmpeg,
                )
                captioned.replace(output)

        _apply_visual_effects(
            ffmpeg, output, edit, data_root, job_dir, out_w, out_h,
            target_fps=float(target_fps), progress=progress,
        )
        _mix_audio(ffmpeg, output, edit, job_dir, progress)
        _mix_sfx_audio(ffmpeg, output, edit, job_dir, progress)

        if progress:
            progress(1.0, "Render complete")
        rendered = sum(
            max(0.0, float(clip.get("end") or 0.0) - float(clip.get("start") or 0.0))
            for clip in clips
        )
        if check:
            if progress:
                progress(0.97, "Checking every cleaned line for leftover text")
            report = _check_output(
                output, edit, meta, source=source, inks=inks,
                fps=float(target_fps), data_root=Path(data_root), size=(out_w, out_h),
            )
            sidecar = output.with_suffix(".check.json")
            if report.get("hits") and _retry:
                widened = _widen_edit(edit, report["hits"], float(meta.get("fps") or 30.0))
                if widened is not None:
                    if progress:
                        progress(0.98, "Refilling the leftover text")
                    # This file is the failed first pass of this same render,
                    # not a render the user asked to keep.
                    output.unlink(missing_ok=True)
                    return render_edit(
                        project, widened, data_root,
                        progress=progress, cancel_event=cancel_event,
                        check=True, _retry=False,
                    )
            report["retried"] = not _retry
            sidecar.write_text(json.dumps(report, indent=1), encoding="utf-8")
        remember_render_time(Path(data_root), rendered, time.monotonic() - started)
        return output
    except Exception:
        for segment in segments:
            segment.unlink(missing_ok=True)
        raise

def _apply_visual_effects(
    ffmpeg: str,
    output: Path,
    edit: dict,
    data_root: Path,
    job_dir: Path,
    out_w: int,
    out_h: int,
    *,
    target_fps: float,
    progress=None,
) -> None:
    items = effects.visual_effects(edit)
    if not items:
        return
    if progress:
        progress(0.975, "Adding effects")
    total = max(0.05, float(edit.get("end") or media.duration(output)))
    inputs = ["-i", str(output)]
    filters: list[str] = []
    base = "[0:v]"
    input_index = 1
    filter_index = 1
    for effect in items:
        kind = str(effect.get("kind") or "")
        start = max(0.0, min(total, float(effect.get("start") or 0.0)))
        end = max(start + 0.05, min(total, float(effect.get("end") or total)))
        if kind == "filter":
            preset = str(effect.get("preset") or "warm")
            chain = effects.FILTERS.get(preset)
            if not chain:
                continue
            label = f"[vf{filter_index}]"
            filter_index += 1
            filters.append(f"{base}{chain}:enable='between(t,{start:.3f},{end:.3f})'{label}")
            base = label
            continue
        path = None
        if kind == "text":
            try:
                path = effects.text_png(effect, str(edit["project_id"]), data_root, out_w, out_h)
            except Exception:
                continue
            inputs += ["-loop", "1", "-framerate", str(int(target_fps)), "-i", str(path)]
        elif kind in {"image", "gif", "sticker", "layer"}:
            candidate = job_dir / str(effect.get("file") or "")
            if not candidate.is_file():
                continue
            path = candidate
            if kind == "gif" or candidate.suffix.lower() in {".gif", ".webp"}:
                inputs += ["-stream_loop", "-1", "-ignore_loop", "0", "-i", str(candidate)]
            elif kind == "layer" and candidate.suffix.lower() in {".mp4", ".mov", ".m4v"}:
                inputs += ["-stream_loop", "-1", "-i", str(candidate)]
            else:
                inputs += ["-loop", "1", "-framerate", str(int(target_fps)), "-i", str(candidate)]
        else:
            continue
        width = max(0.04, min(1.0, float(effect.get("width") or 0.35)))
        scaled = f"[{input_index}:v]scale={max(2, int(out_w * width))}:-2,format=rgba,setpts=PTS-STARTPTS[ov{input_index}]"
        filters.append(scaled)
        label = f"[vfx{input_index}]"
        x = max(0.0, min(1.0, float(effect.get("x") or 0.5)))
        y = max(0.0, min(1.0, float(effect.get("y") or 0.5)))
        filters.append(
            f"{base}[ov{input_index}]overlay=x=(W-w)*{x:.3f}:y=(H-h)*{y:.3f}:"
            f"enable='between(t,{start:.3f},{end:.3f})':shortest=1{label}"
        )
        base = label
        input_index += 1
    if base == "[0:v]":
        return
    filters.append(f"{base}format=yuv420p[vout]")
    temporary = output.with_name(f".{output.stem}.fx.mp4")
    command = [
        ffmpeg, "-y", "-v", "error", *inputs,
        "-filter_complex", ";".join(filters),
        "-map", "[vout]", "-map", "0:a?",
        "-c:v", "h264_videotoolbox", "-q:v", "65", "-pix_fmt", "yuv420p",
        "-c:a", "copy", "-t", f"{total:.3f}", "-movflags", "+faststart",
        str(temporary),
    ]
    _run(command)
    temporary.replace(output)


def _mix_sfx_audio(
    ffmpeg: str, output: Path, edit: dict, job_dir: Path, progress=None,
) -> None:
    rows, items, solo = _audible_audio(edit, job_dir)
    if not items:
        return
    if progress:
        progress(0.99, "Mixing effects")
    total = max(0.05, float(edit.get("end") or media.duration(output)))
    inputs = ["-i", str(output)]
    filters: list[str] = []
    labels: list[str] = []
    input_index = 1
    for item in items:
        path = job_dir / str(item.get("file") or "")
        inputs += ["-i", str(path)]
        delay = max(0, int(float(item.get("start") or 0.0) * 1000))
        raw_volume = item.get("volume")
        level = max(0.0, min(1.5, float(0.9 if raw_volume is None else raw_volume)))
        duration = max(0.2, float(item.get("end") or 0.0) - float(item.get("start") or 0.0))
        offset = max(0.0, float(item.get("offset") or 0.0))
        fade_in = max(0.0, min(duration / 2, float(item.get("fade_in") or 0.0)))
        fade_out = max(0.0, min(duration / 2, float(item.get("fade_out") or 0.0)))
        chain = f"atrim=start={offset:.3f}:duration={duration:.3f},asetpts=PTS-STARTPTS,volume={level:.3f}"
        if fade_in:
            chain += f",afade=t=in:st=0:d={fade_in:.3f}"
        if fade_out:
            chain += f",afade=t=out:st={max(0.0, duration - fade_out):.3f}:d={fade_out:.3f}"
        label = f"[sfx{input_index}]"
        filters.append(f"[{input_index}:a]{chain},adelay={delay}|{delay}{label}")
        labels.append(label)
        input_index += 1
    if media.has_audio(output) and (not solo or bool(rows)):
        filters.insert(0, "[0:a]volume=1.0[base]")
        labels.insert(0, "[base]")
    else:
        filters.insert(
            0,
            f"anullsrc=channel_layout=stereo:sample_rate=48000,atrim=duration={total:.3f}[base]",
        )
        labels.insert(0, "[base]")
    filters.append(
        "".join(labels) + f"amix=inputs={len(labels)}:duration=longest:normalize=0,"
        f"apad=whole_dur={total:.3f}[aout]"
    )
    temporary = output.with_name(f".{output.stem}.sfx.mp4")
    command = [
        ffmpeg, "-y", "-v", "error", *inputs,
        "-filter_complex", ";".join(filters),
        "-map", "0:v:0", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-t", f"{total:.3f}", "-movflags", "+faststart", str(temporary),
    ]
    _run(command)
    temporary.replace(output)


def _audible_audio(edit: dict, job_dir: Path) -> tuple[list[dict], list[dict], bool]:
    """Return the audio rows and sound effects that survive the global solo state."""
    all_rows = [
        row for row in edits.ensure_audio_tracks(edit)
        if not bool(row.get("muted"))
    ]
    all_items = [
        item for item in effects.sound_effects(edit)
        if not bool(item.get("muted"))
    ]
    solo_rows = [row for row in all_rows if bool(row.get("solo"))]
    solo_items = [item for item in all_items if bool(item.get("solo"))]
    solo = bool(solo_rows or solo_items)
    rows = solo_rows if solo else all_rows
    items = solo_items if solo else all_items
    rows = [row for row in rows if (job_dir / str(row.get("audio") or "")).is_file()]
    items = [item for item in items if (job_dir / str(item.get("file") or "")).is_file()]
    return rows, items, solo


def _mix_audio(ffmpeg: str, output: Path, edit: dict, job_dir: Path, progress=None) -> None:
    """Mix all voice, dub, and music rows into the rendered video."""
    rows, _unused_items, solo = _audible_audio(edit, job_dir)
    total = max(0.05, float(edit.get("end") or media.duration(output)))
    has_original = media.has_audio(output)
    if not rows and not has_original:
        return
    if progress:
        progress(0.985, "Mixing audio")
    voices = [row for row in rows if str(row.get("kind")) in {"voice", "dub"}]
    dub = any(str(row.get("kind")) == "dub" for row in rows)
    voice_only = any(
        str(row.get("kind")) == "voice" and str(row.get("mode")) == "voice_only"
        for row in rows
    )
    include_original = has_original and not dub and not voice_only and not solo
    mixed = output.with_name(f".{output.stem}.mix.mp4")
    inputs = ["-i", str(output)]
    for row in rows:
        inputs += ["-i", str(job_dir / str(row.get("audio")))]
    filters: list[str] = []
    labels: list[str] = []
    if include_original:
        level = 0.22 if voices else 1.0
        filters.append(f"[0:a]volume={level:.3f}[base]")
        labels.append("[base]")
    for index, row in enumerate(rows, 1):
        raw_volume = row.get("volume")
        default_volume = 0.25 if row.get("kind") == "music" else 1.0
        level = max(0.0, min(1.5, float(default_volume if raw_volume is None else raw_volume)))
        delay = max(0, int(float(row.get("start") or 0.0) * 1000))
        duration = max(0.2, float(row.get("duration") or 0.2))
        offset = max(0.0, float(row.get("offset") or 0.0))
        fade_in = max(0.0, min(duration / 2, float(row.get("fade_in") or 0.0)))
        fade_out = max(0.0, min(duration / 2, float(row.get("fade_out") or 0.0)))
        chain = f"atrim=start={offset:.3f}:duration={duration:.3f},asetpts=PTS-STARTPTS,volume={level:.3f}"
        if fade_in:
            chain += f",afade=t=in:st=0:d={fade_in:.3f}"
        if fade_out:
            chain += f",afade=t=out:st={max(0.0, duration - fade_out):.3f}:d={fade_out:.3f}"
        label = f"[a{index}]"
        filters.append(
            f"[{index}:a]{chain},adelay={delay}|{delay}{label}"
        )
        labels.append(label)
    if not labels:
        if not solo:
            return
        filters.append(
            f"anullsrc=channel_layout=stereo:sample_rate=48000,"
            f"atrim=duration={total:.3f}[aout]"
        )
        labels.append("[aout]")
    if len(labels) == 1 and labels[0] == "[aout]":
        pass
    elif len(labels) == 1:
        filters.append(f"{labels[0]}apad=whole_dur={total:.3f}[aout]")
    else:
        filters.append(
            "".join(labels) + f"amix=inputs={len(labels)}:duration=longest:normalize=0,"
            f"apad=whole_dur={total:.3f}[aout]"
        )
    command = [
        ffmpeg, "-y", "-v", "error", *inputs,
        "-filter_complex", ";".join(filters),
        "-map", "0:v:0", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-t", f"{total:.3f}", "-movflags", "+faststart", str(mixed),
    ]
    _run(command)
    mixed.replace(output)


def _process_alive(pid: int) -> bool:
    """Whether a render worker still owns its row. Same machine only."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class RenderQueue:
    def __init__(self, data_root: Path):
        self.data_root = Path(data_root)
        self.path = self.data_root / "state.db"
        self.lock = threading.Lock()
        self.paused = False
        self.cancel_events: dict[str, threading.Event] = {}
        self._init()
        threading.Thread(target=self._loop, daemon=True, name="duck-render-queue").start()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _init(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS render_queue (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    edit_id TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    state TEXT NOT NULL,
                    stage TEXT NOT NULL DEFAULT 'Queued',
                    progress REAL NOT NULL DEFAULT 0,
                    message TEXT NOT NULL DEFAULT '',
                    output TEXT NOT NULL DEFAULT '',
                    created REAL NOT NULL,
                    updated REAL NOT NULL
                )
                """
            )
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(render_queue)")
            }
            if "estimate_seconds" not in columns:
                connection.execute("ALTER TABLE render_queue ADD COLUMN estimate_seconds REAL DEFAULT 0")
            if "elapsed_seconds" not in columns:
                connection.execute("ALTER TABLE render_queue ADD COLUMN elapsed_seconds REAL DEFAULT 0")
            if "worker_pid" not in columns:
                connection.execute("ALTER TABLE render_queue ADD COLUMN worker_pid INTEGER DEFAULT 0")
            for name, kind in (
                ("checked_frames", "INTEGER DEFAULT 0"),
                ("check_hits", "INTEGER DEFAULT 0"),
                ("check_times", "TEXT DEFAULT ''"),
                ("check_flicker", "TEXT DEFAULT ''"),
                ("check_unchecked", "INTEGER DEFAULT 0"),
            ):
                if name not in columns:
                    connection.execute(f"ALTER TABLE render_queue ADD COLUMN {name} {kind}")
            # Requeue only work whose worker is gone. A second core starting
            # while a render runs must not put that job back in the queue.
            rows = connection.execute(
                "SELECT id, worker_pid FROM render_queue WHERE state IN ('running', 'cancelling')"
            ).fetchall()
            for row in rows:
                if _process_alive(int(row["worker_pid"] or 0)):
                    continue
                connection.execute(
                    """
                    UPDATE render_queue
                    SET state = 'queued', stage = 'Queued',
                        message = 'Resuming after restart', worker_pid = 0, updated = ?
                    WHERE id = ?
                    """,
                    (time.time(), row["id"]),
                )

    def _row(self, row: sqlite3.Row) -> dict:
        data = dict(row)
        data["estimate_seconds"] = float(data.get("estimate_seconds") or 0.0)
        data["elapsed_seconds"] = float(data.get("elapsed_seconds") or 0.0)
        return data

    def busy_for(self, project_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM render_queue
                WHERE project_id = ? AND state IN ('queued', 'running', 'cancelling')
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
        return row is not None

    def enqueue(self, project_id: str, edit_id: str, title: str) -> dict:
        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT * FROM render_queue
                WHERE project_id = ? AND edit_id = ?
                  AND state IN ('queued', 'running', 'cancelling')
                ORDER BY created DESC LIMIT 1
                """,
                (project_id, edit_id),
            ).fetchone()
            if existing is not None:
                return self._row(existing)
            item_id = f"rq_{uuid.uuid4().hex[:12]}"
            now = time.time()
            connection.execute(
                """
                INSERT INTO render_queue
                    (id, project_id, edit_id, title, state, stage, progress,
                     message, output, created, updated)
                VALUES (?, ?, ?, ?, 'queued', 'Queued', 0, ?, '', ?, ?)
                """,
                (item_id, project_id, edit_id, title, "Waiting to render", now, now),
            )
            row = connection.execute(
                "SELECT * FROM render_queue WHERE id = ?", (item_id,)
            ).fetchone()
        return self._row(row)

    def start(self, project_id: str, edit_id: str) -> dict:
        from duckcore import edits

        edit = edits.get_edit(self.data_root, project_id, edit_id)
        return self.enqueue(project_id, edit_id, str(edit.get("title") or ""))

    def status(self, project_id: str, edit_id: str) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM render_queue
                WHERE project_id = ? AND edit_id = ?
                ORDER BY created DESC LIMIT 1
                """,
                (project_id, edit_id),
            ).fetchone()
        if row is None:
            return {
                "state": "idle", "stage": "Not rendered", "progress": 0.0,
                "message": "", "output": "",
            }
        return self._row(row)

    def list(self, limit: int = 50) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT r.*, p.name AS project_name
                FROM render_queue r
                LEFT JOIN projects p ON p.id = r.project_id
                ORDER BY r.created DESC LIMIT ?
                """,
                (max(1, min(200, int(limit))),),
            ).fetchall()
        from duckcore import edits

        result = []
        for row in rows:
            item = self._row(row)
            item["project_name"] = row["project_name"] or ""
            try:
                edit = edits.get_edit(self.data_root, item["project_id"], item["edit_id"])
                source = edit.get("source") or {}
                item["duration"] = round(
                    max(0.0, float(edit.get("end") or 0.0) - float(edit.get("start") or 0.0)), 3
                )
                item["fps"] = float(source.get("fps") or 0.0)
                item["width"] = int(source.get("width") or 0)
                item["height"] = int(source.get("height") or 0)
            except (KeyError, OSError, ValueError, TypeError):
                item["duration"] = 0.0
                item["fps"] = 0.0
                item["width"] = 0
                item["height"] = 0
            result.append(item)
        return result

    def pause(self) -> dict:
        self.paused = True
        return {"paused": True}

    def resume(self) -> dict:
        self.paused = False
        return {"paused": False}

    def clear_finished(self) -> list[dict]:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM render_queue WHERE state IN ('done', 'failed', 'cancelled')"
            )
        return self.list()

    def cancel(self, project_id: str, edit_id: str) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM render_queue
                WHERE project_id = ? AND edit_id = ?
                  AND state IN ('queued', 'running', 'cancelling')
                ORDER BY created DESC LIMIT 1
                """,
                (project_id, edit_id),
            ).fetchone()
            if row is None:
                return self.status(project_id, edit_id)
            item = self._row(row)
            if item["state"] == "queued":
                connection.execute(
                    "UPDATE render_queue SET state='cancelled', stage='Cancelled', message='Cancelled', updated=? WHERE id=?",
                    (time.time(), item["id"]),
                )
            else:
                event = self.cancel_events.get(item["id"])
                if event is not None:
                    event.set()
                connection.execute(
                    "UPDATE render_queue SET state='cancelling', stage='Cancelling', message='Stopping the render', updated=? WHERE id=?",
                    (time.time(), item["id"]),
                )
        return self.status(project_id, edit_id)

    def _claim_next(self) -> dict | None:
        """Take one queued job and mark it running in the same transaction.

        A select followed by an update let two cores on one data folder run the
        same job, and a stale worker could fail it with its own model state.
        """
        now = time.time()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM render_queue WHERE state='queued' ORDER BY created ASC LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            claimed = connection.execute(
                """
                UPDATE render_queue
                SET state='running', stage='Rendering', progress=0.01,
                    message='Starting render', worker_pid=?, updated=?
                WHERE id=? AND state='queued'
                """,
                (os.getpid(), now, row["id"]),
            )
            if claimed.rowcount != 1:
                return None
        return self._row(row)

    def _update(self, item_id: str, **values) -> None:
        if "message" in values:
            values["message"] = _clean_message(values["message"])
        allowed = {"state", "stage", "progress", "message", "output",
                   "estimate_seconds", "elapsed_seconds", "worker_pid",
                   "checked_frames", "check_hits", "check_times", "check_flicker",
                   "check_unchecked"}
        fields = [key for key in values if key in allowed]
        if not fields:
            return
        values["updated"] = time.time()
        assignments = ", ".join(f"{key} = ?" for key in fields) + ", updated = ?"
        params = [values[key] for key in fields] + [values["updated"], item_id]
        with self._connect() as connection:
            connection.execute(
                f"UPDATE render_queue SET {assignments} WHERE id = ?", params,
            )

    def _loop(self) -> None:
        while True:
            if self.paused:
                time.sleep(0.5)
                continue
            item = self._claim_next()
            if item is None:
                time.sleep(0.5)
                continue
            event = threading.Event()
            self.cancel_events[item["id"]] = event
            try:
                from duckcore import edits
                from duckcore.store import ProjectStore

                store = ProjectStore(self.data_root)
                project = store.get(item["project_id"])
                edit = edits.get_edit(self.data_root, item["project_id"], item["edit_id"])

                def progress(fraction: float, message: str) -> None:
                    self._update(
                        item["id"], state="running", stage="Rendering",
                        progress=max(0.01, min(0.99, float(fraction))),
                        message=message,
                    )

                try:
                    from duckcore.engine import pipeline

                    meta = pipeline.probe(str(project["source_path"]))
                    meta["path"] = str(project["source_path"])
                    guess = wait_for_estimate(edit, meta, self.data_root)
                    seconds = guess.get("total_seconds") or guess.get("seconds") or 0
                    self._update(item["id"], estimate_seconds=float(seconds))
                except Exception:  # noqa: BLE001 - the estimate never blocks a render
                    pass
                output = render_edit(
                    project, edit, self.data_root,
                    progress=progress, cancel_event=event,
                )
                if event.is_set():
                    self._update(
                        item["id"], state="cancelled", stage="Cancelled",
                        progress=1.0, message="Render cancelled", worker_pid=0,
                    )
                else:
                    report = {}
                    try:
                        sidecar = output.with_suffix(".check.json")
                        if sidecar.is_file():
                            report = json.loads(sidecar.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        report = {}
                    self._update(
                        item["id"], state="done", stage="Done",
                        progress=1.0, message="Render complete", output=str(output),
                        elapsed_seconds=round(time.time() - item["created"], 1),
                        checked_frames=int(report.get("frames") or 0),
                        check_hits=len(report.get("times") or []),
                        check_times=json.dumps(report.get("times") or []),
                        check_flicker=json.dumps(report.get("flicker") or {}),
                        check_unchecked=len(report.get("unchecked") or []),
                        worker_pid=0,
                    )
            except Exception as exc:  # noqa: BLE001
                cancelled = event.is_set()
                self._update(
                    item["id"],
                    state="cancelled" if cancelled else "failed",
                    stage="Cancelled" if cancelled else "Failed",
                    progress=1.0, worker_pid=0,
                    message="Render cancelled" if cancelled else _clean_message(exc)[:500],
                )
            finally:
                self.cancel_events.pop(item["id"], None)
