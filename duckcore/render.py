"""Minimal DuckSuite render: cut clips, fill clean layers, concat."""

from __future__ import annotations

import json
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


def _render_ratio(data_root: Path) -> float | None:
    ratios = sorted(_render_rates(data_root))
    if not ratios:
        return None
    return ratios[len(ratios) // 2]


def estimate_edit(edit: dict, meta: dict, data_root: Path) -> dict:
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
    rows = []
    if layers:
        for clip in edit.get("clips") or []:
            start = float(clip.get("start") or 0.0)
            end = float(clip.get("end") or 0.0)
            if end <= start or str(clip.get("kind")) == "media":
                continue
            rows.append(textfill.estimate_span(
                meta=meta, start=start, duration=max(0.04, end - start), layers=layers,
                method="lama", cache_dir=cache, data_root=data_root,
                device=_fill_device(data_root),
            ))
    summary = textfill.estimate_summary(rows, data_root)
    filled_frames = sum(int(row.get("frames") or 0) for row in rows)
    timeline = sum(
        max(0.0, float(clip.get("end") or 0.0) - float(clip.get("start") or 0.0))
        for clip in edit.get("clips") or []
        if str(clip.get("kind")) != "media"
    )
    ratio = _render_ratio(data_root)
    total = round(timeline * ratio, 1) if ratio and timeline > 0 else None
    return {
        **summary,
        "total_seconds": total,
        "total_measured": bool(total),
        "timeline_seconds": round(timeline, 1),
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
            connection.execute(
                """
                UPDATE render_queue
                SET state = 'queued', stage = 'Queued',
                    message = 'Resuming after restart', updated = ?
                WHERE state IN ('running', 'cancelling')
                """,
                (time.time(),),
            )

    def _row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "edit_id": row["edit_id"],
            "title": row["title"],
            "state": row["state"],
            "stage": row["stage"],
            "progress": row["progress"],
            "message": row["message"],
            "output": row["output"],
            "created": row["created"],
            "updated": row["updated"],
            "estimate_seconds": row["estimate_seconds"] if "estimate_seconds" in row.keys() else 0,
            "elapsed_seconds": row["elapsed_seconds"] if "elapsed_seconds" in row.keys() else 0,
        }

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
                    message='Starting render', updated=?
                WHERE id=? AND state='queued'
                """,
                (now, row["id"]),
            )
            if claimed.rowcount != 1:
                return None
        return self._row(row)

    def _update(self, item_id: str, **values) -> None:
        if "message" in values:
            values["message"] = _clean_message(values["message"])
        allowed = {"state", "stage", "progress", "message", "output",
                   "estimate_seconds", "elapsed_seconds"}
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
                    guess = estimate_edit(edit, meta, self.data_root)
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
                        progress=1.0, message="Render cancelled",
                    )
                else:
                    self._update(
                        item["id"], state="done", stage="Done",
                        progress=1.0, message="Render complete", output=str(output),
                        elapsed_seconds=round(time.time() - item["created"], 1),
                    )
            except Exception as exc:  # noqa: BLE001
                cancelled = event.is_set()
                self._update(
                    item["id"],
                    state="cancelled" if cancelled else "failed",
                    stage="Cancelled" if cancelled else "Failed",
                    progress=1.0,
                    message="Render cancelled" if cancelled else _clean_message(exc)[:500],
                )
            finally:
                self.cancel_events.pop(item["id"], None)
