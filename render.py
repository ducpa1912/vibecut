"""Turn a cut plan into a vertical H.264 reel.

The renderer is deliberately boring: every beat is cut as its own segment,
then the segments are joined with the concat demuxer. That keeps frame
boundaries exact and lets us cache and parallelize the expensive part.
"""

from __future__ import annotations

import bisect
import hashlib
import json
import logging
import math
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFont

import audio
import captions as caption_engine
import compose_render
import edits
import fx
import textfill
from compose_render import path_expression as _path_expression
from compose_render import path_value as _path_value
from pipeline import PipelineError, crop_center, probe

LOGGER = logging.getLogger(__name__)

TARGET_AR = 9 / 16
OUT_W = 1080
OUT_H = 1920
OUT_FPS = 30
# v2: weighted fonts, colour emoji and caption stroke widths (QA #12).
LAYER_CACHE_VERSION = "layers-v2"
# Captions are bold by default; text layers carry their own style.weight.
CAPTION_WEIGHT = 700

PRESETS = {
    "tiktok": {"aspect": "9:16", "captions": True, "caption_margin": 0.12},
    "reels": {"aspect": "9:16", "captions": True, "caption_margin": 0.10},
    "shorts": {"aspect": "9:16", "captions": True, "caption_margin": 0.09},
    "square": {"aspect": "1:1", "captions": True, "caption_margin": 0.08},
    "landscape": {"aspect": "16:9", "captions": False, "caption_margin": 0.07},
}

# AV1 has no VideoToolbox decoder on M1/M2, so the software dav1d decoder is
# the correct default. A build with AV1 hardware decode can opt in with
# VIBECUT_DECODER=videotoolbox.
SOFTWARE_AV1 = {"av1", "av01"}
# From this many caption cues on, one timed overlay replaces one overlay per
# cue. The per-cue chain is quadratic in practice: 60 overlays cost minutes.
CAPTION_TRACK_MIN = 8

ASPECTS = {
    "9:16": ((1080, 1920), (540, 960)),
    "4:5": ((1080, 1350), (540, 676)),
    "1:1": ((1080, 1080), (540, 540)),
    "16:9": ((1920, 1080), (960, 540)),
    "16:10": ((1920, 1200), (960, 600)),
}

# Final, 720p and draft sizes keyed by quality. 720p is the middle choice
# Studio offers between a 1080 final and a 540 draft.
SIZES = {
    "9:16": {"final": (1080, 1920), "720": (720, 1280), "draft": (540, 960)},
    "4:5": {"final": (1080, 1350), "720": (720, 900), "draft": (540, 676)},
    "1:1": {"final": (1080, 1080), "720": (720, 720), "draft": (540, 540)},
    "16:9": {"final": (1920, 1080), "720": (1280, 720), "draft": (960, 540)},
    "16:10": {"final": (1920, 1200), "720": (1280, 800), "draft": (960, 600)},
}


class RenderCancelled(RuntimeError):
    pass


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise PipelineError("ffmpeg is not installed or not on PATH.")
    return path


def _run(
    cmd: list[str],
    timeout: int | None = None,
    cwd: Path | None = None,
    cancel_event: threading.Event | None = None,
) -> subprocess.CompletedProcess:
    """Run ffmpeg and kill the whole process group when a render is cancelled."""
    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, cwd=cwd, start_new_session=True,
    )
    if cancel_event is not None:
        def watch() -> None:
            while process.poll() is None:
                if cancel_event.wait(0.2):
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except OSError:
                        pass
                    return
        threading.Thread(target=watch, daemon=True).start()
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except OSError:
            pass
        process.wait(timeout=5)
        raise PipelineError("ffmpeg render timed out.") from None
    if cancel_event is not None and cancel_event.is_set():
        raise RenderCancelled("Render cancelled.")
    if process.returncode != 0:
        tail = (stderr or stdout or "")[-1600:]
        raise PipelineError(f"ffmpeg render failed.\n{tail}")
    return subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)


def _dims(aspect: str, quality: str) -> tuple[int, int]:
    sizes = SIZES.get(aspect, SIZES["9:16"])
    return sizes.get(quality, sizes["final"])


@contextmanager
def _stage(timings: dict[str, float], name: str):
    """Record wall time for one render stage. No effect on the output."""
    started = time.monotonic()
    try:
        yield
    finally:
        timings[name] = round(time.monotonic() - started, 3)


def _choose_encoder(requested: str | None = None) -> str:
    value = (requested or os.environ.get("VIBECUT_ENCODER") or "auto").lower()
    if value in ("libx264", "x264"):
        return "libx264"
    if value in ("videotoolbox", "vt"):
        return "videotoolbox"
    if value == "auto":
        return "videotoolbox" if sys.platform == "darwin" else "libx264"
    return "libx264"


def _decoder_args(meta: dict, threads: int | None = None) -> list[str]:
    """Input decoder options. Input seek stays before ``-i`` in ``_segment``.

    ``auto`` uses libdav1d for AV1: that is the only AV1 decoder in the
    Homebrew ffmpeg build, and VideoToolbox AV1 decode is absent on M1/M2.
    ``VIBECUT_DECODER=videotoolbox`` forces the hardware path for machines
    whose ffmpeg supports it; ``software`` forces dav1d.
    """
    mode = (os.environ.get("VIBECUT_DECODER") or "auto").strip().lower()
    codec = str(meta.get("codec") or "").strip().lower()
    if mode in ("vt", "videotoolbox"):
        return ["-hwaccel", "videotoolbox"]
    if codec not in SOFTWARE_AV1:
        return []
    # ffmpeg already picks libdav1d for AV1. Naming it would break a build
    # that ships a different AV1 decoder, so only the thread budget is set.
    args: list[str] = []
    if threads:
        # The beat pool runs several ffmpeg processes. Handing each one a
        # slice of the cores avoids every decoder spawning a full thread set.
        args += ["-threads", str(max(1, int(threads)))]
    return args


def _encoder_args(encoder: str, quality: str) -> list[str]:
    if encoder == "videotoolbox":
        bitrate = "10M" if quality == "final" else "6M" if quality == "720" else "3M"
        return [
            "-c:v", "h264_videotoolbox",
            "-b:v", bitrate,
            "-maxrate", bitrate,
            "-bufsize", bitrate,
            "-allow_sw", "1",
            "-profile:v", "high", "-level", "4.2",
            "-pix_fmt", "yuv420p",
            "-bf", "0",
        ]
    return [
        "-c:v", "libx264",
        "-preset", "veryfast" if quality in ("final", "720") else "ultrafast",
        "-crf", "18" if quality == "final" else "20" if quality == "720" else "23",
        "-profile:v", "high", "-level", "4.2",
        "-pix_fmt", "yuv420p",
        # No B-frames keeps every segment starting at PTS 0. That lets the
        # concat demuxer copy video without gaps at the cut boundaries.
        "-bf", "0",
    ]


def _crop_filter(
    meta: dict, crop: dict, out_w: int, out_h: int,
    crop_path: list[dict] | None = None, duration: float = 0.0,
) -> str:
    width, height = int(meta["width"]), int(meta["height"])
    source_ar = width / max(1, height)
    target_ar = out_w / out_h
    filters: list[str] = []

    if all(key in crop for key in ("x", "y", "w", "h")):
        # A compiled Edit crop is already an exact source-pixel rectangle.
        crop_w = max(2, min(width, int(crop["w"])))
        crop_h = max(2, min(height, int(crop["h"])))
        crop_w -= crop_w % 2
        crop_h -= crop_h % 2
        x = max(0, min(width - crop_w, int(crop["x"])))
        y = max(0, min(height - crop_h, int(crop["y"])))
        x -= x % 2
        y -= y % 2
        filters.append(f"crop={crop_w}:{crop_h}:{x}:{y}")
    else:
        cx = float(crop.get("cx", 0.5))
        cy = float(crop.get("cy", 0.5))
        if abs(source_ar - target_ar) > 0.01:
            if source_ar > target_ar:
                crop_h = height - (height % 2)
                crop_w = int(round(crop_h * target_ar))
                crop_w -= crop_w % 2
                crop_w = min(width, max(2, crop_w))
                x = int(round(cx * width - crop_w / 2))
                x = max(0, min(width - crop_w, x))
                y = 0
                dynamic = []
                for point in crop_path or []:
                    value = max(0.0, min(
                        float(width - crop_w),
                        float(point.get("cx", 0.5)) * width - crop_w / 2,
                    ))
                    dynamic.append((max(0.0, min(duration, float(point.get("t") or 0.0))), value))
                if len(dynamic) >= 2 and duration > 0.1:
                    filters.append(
                        f"crop={crop_w}:{crop_h}:x='{_path_expression(dynamic)}':y=0"
                    )
                else:
                    filters.append(f"crop={crop_w}:{crop_h}:{x}:{y}")
            else:
                crop_w = width - (width % 2)
                crop_h = int(round(crop_w / target_ar))
                crop_h -= crop_h % 2
                crop_h = min(height, max(2, crop_h))
                x = 0
                y = int(round(cy * height - crop_h / 2))
                y = max(0, min(height - crop_h, y))
                dynamic = []
                for point in crop_path or []:
                    value = max(0.0, min(
                        float(height - crop_h),
                        float(point.get("cy", 0.5)) * height - crop_h / 2,
                    ))
                    dynamic.append((max(0.0, min(duration, float(point.get("t") or 0.0))), value))
                if len(dynamic) >= 2 and duration > 0.1:
                    filters.append(
                        f"crop={crop_w}:{crop_h}:x=0:y='{_path_expression(dynamic)}'"
                    )
                else:
                    filters.append(f"crop={crop_w}:{crop_h}:{x}:{y}")

    # Drop frames before scaling when the source is faster than the output.
    # Scaling 60 fps AV1 frames only to discard half of them doubles the
    # cost; the selected frames are identical either way.
    try:
        source_fps = float(meta.get("fps") or 0)
    except (TypeError, ValueError):
        source_fps = 0.0
    scale = compose_render.placed_scale_filter(crop.get("place"), out_w, out_h)
    if source_fps > OUT_FPS + 0.01:
        filters.append(f"fps={OUT_FPS}")
        filters.append(scale)
    else:
        filters.append(scale)
        filters.append(f"fps={OUT_FPS}")
    filters.extend(["setsar=1", "format=yuv420p"])
    return ",".join(filters)


def _scene_crop(scene: dict, aspect: str, meta: dict, out_w: int, out_h: int) -> dict:
    crop = (scene.get("crops") or {}).get(aspect)
    if crop:
        return crop
    if scene.get("attention"):
        cx, cy = crop_center(
            scene, int(meta["width"]), int(meta["height"]), out_w / max(1, out_h),
        )
        return {"cx": round(cx, 4), "cy": round(cy, 4)}
    if aspect != "9:16":
        return {"cx": 0.5, "cy": 0.5}
    return scene.get("crop") or {"cx": 0.5, "cy": 0.5}


def _crop_path_for(scene: dict, aspect: str, clip: dict) -> list[dict] | None:
    points = (scene.get("crop_paths") or {}).get(aspect) or []
    if len(points) < 2:
        return None
    scene_start = float(scene.get("start") or clip.get("start") or 0.0)
    offset = float(clip.get("start") or scene_start) - scene_start
    duration = float(clip.get("duration") or clip.get("dur") or 0.0)
    if duration <= 0.1:
        return None
    scene_points = [
        (float(point.get("t") or 0.0), float(point.get("cx", 0.5)), float(point.get("cy", 0.5)))
        for point in points
    ]
    cx_points = [(point[0], point[1]) for point in scene_points]
    cy_points = [(point[0], point[2]) for point in scene_points]
    values = [
        (0.0, _path_value(cx_points, offset), _path_value(cy_points, offset)),
        (duration, _path_value(cx_points, offset + duration), _path_value(cy_points, offset + duration)),
    ]
    for t, cx, cy in scene_points:
        relative = t - offset
        if 0.0 < relative < duration:
            values.append((relative, cx, cy))
    values.sort(key=lambda item: item[0])
    deduped = []
    for item in values:
        if deduped and abs(item[0] - deduped[-1][0]) < 0.01:
            deduped[-1] = item
        else:
            deduped.append(item)
    return [{"t": round(t, 3), "cx": round(cx, 4), "cy": round(cy, 4)} for t, cx, cy in deduped]


def _frames_for(start: float, duration: float, source_duration: float) -> int:
    frames = max(1, int(round(duration * OUT_FPS)))
    if source_duration > 0:
        room = max(1, int((source_duration - start) * OUT_FPS + 1e-6))
        frames = min(frames, room)
    return frames


def prepare_render(plan: dict, meta: dict, audio_plan: dict | None = None) -> dict:
    """Final frame-rounded, beat-snapped clips used for burn and captions."""
    source_duration = float(meta.get("duration") or 0)
    clips: list[dict] = []
    for clip in plan.get("clips") or []:
        start = max(0.0, float(clip["start"]))
        duration_hint = clip.get("dur", clip.get("duration"))
        end = clip.get("end")
        if end is None:
            end = start + float(duration_hint or 0.0)
        wanted = max(0.2, float(end) - start)
        if clip.get("kind") == "blank" or clip.get("freeze"):
            frames = max(1, int(round(wanted * OUT_FPS)))
            clips.append({
                "kind": "blank",
                "scene": None,
                "color": clip.get("color") or "#000000",
                "role": clip.get("role") or "beat",
                "start": 0.0,
                "frames": frames,
                "duration": frames / OUT_FPS,
            })
            continue
        if clip.get("kind") == "file":
            frames = max(1, int(round(wanted * OUT_FPS)))
            clips.append({
                "kind": "file",
                "scene": None,
                "file": clip.get("file"),
                "asset": dict(clip.get("asset") or {}),
                "role": clip.get("role") or "beat",
                "start": start,
                "frames": frames,
                "duration": frames / OUT_FPS,
                "reverse": bool(clip.get("reverse")),
            })
            continue
        frames = _frames_for(start, wanted, source_duration)
        clips.append({
            "scene": clip["scene"],
            "role": clip.get("role") or "beat",
            "start": start,
            "frames": frames,
            "duration": frames / OUT_FPS,
        })
    total = sum(clip["duration"] for clip in clips)
    if audio_plan and audio_plan.get("beat_sync"):
        track = audio.resolve_music_track(
            plan.get("_scenes", []), clips, audio_plan.get("music") or {},
        )
        grid = audio.beat_grid(track) if track else None
        if grid:
            clips, drift = audio.snap_clips(clips, grid)
            total = sum(clip["duration"] for clip in clips)
            audio_plan["_beat_bpm"] = grid.get("bpm")
            audio_plan["_beat_drift"] = drift
    return {"clips": clips, "total": total, "audio_plan": audio_plan}


def _link_or_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def _filters_hash(filters: list[str] | None) -> str:
    if not filters:
        return ""
    return hashlib.sha1(
        json.dumps([str(item) for item in filters]).encode("utf-8"),
    ).hexdigest()[:20]


def _blank_segment(
    output: Path,
    frames: int,
    out_w: int,
    out_h: int,
    quality: str,
    encoder: str,
    color: str,
    cancel_event: threading.Event | None = None,
    fps: int = OUT_FPS,
) -> None:
    """Write a solid-colour filler clip with the same timing as a beat."""
    duration = max(1, frames) / fps
    _run([
        _ffmpeg(), "-y", "-v", "error",
        "-f", "lavfi",
        "-i", f"color=c={color}:s={out_w}x{out_h}:r={fps}:d={duration:.6f}",
        "-frames:v", str(max(1, frames)),
        *_encoder_args(encoder, quality),
        "-video_track_timescale", "90000",
        "-avoid_negative_ts", "make_zero",
        str(output),
    ], timeout=300, cancel_event=cancel_event)


def _segment_cache_key(
    meta: dict,
    scene: dict,
    start: float,
    frames: int,
    out_w: int,
    out_h: int,
    quality: str,
    encoder: str,
    first: bool,
    last: bool,
    crop: dict | None = None,
    crop_path: list[dict] | None = None,
    pre_filters: list[str] | None = None,
    post_filters: list[str] | None = None,
    fill_key: str | None = None,
    reverse: bool = False,
    freeze: bool = False,
    fps: int = OUT_FPS,
) -> str:
    payload = {
        "source": meta.get("fingerprint") or f"{meta.get('size')}:{meta.get('duration')}",
        "start": round(start, 6),
        "frames": frames,
        "crop": crop or scene.get("crop") or {"cx": 0.5, "cy": 0.5},
        "crop_path": crop_path,
        "out": [out_w, out_h],
        "quality": quality,
        "encoder": encoder,
        "first": first,
        "last": last,
        "fps": fps,
    }
    if reverse:
        payload["reverse"] = True
    if freeze:
        payload["freeze"] = True
    pre_hash = _filters_hash(pre_filters)
    post_hash = _filters_hash(post_filters)
    if pre_hash:
        payload["pre_filters"] = pre_hash
    if post_hash:
        payload["post_filters"] = post_hash
    if fill_key:
        payload["fill"] = fill_key
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:20]


def _clip_media(
    job_dir: Path,
    clip: dict | None,
    source: str,
    meta: dict,
) -> tuple[str, dict]:
    """Resolve the source file and probe metadata for one clip."""
    clip = clip or {}
    file_name = str(clip.get("file") or "")
    if not file_name:
        return source, meta
    asset = clip.get("asset") if isinstance(clip.get("asset"), dict) else {}
    path = job_dir / file_name
    if not path.is_file():
        raise PipelineError(f"Media asset is missing: {file_name}")
    resolved = {
        **asset,
        "path": str(path),
        "fingerprint": f"{file_name}:{path.stat().st_size}",
        "duration": float(asset.get("duration") or 0.0),
        "has_audio": bool(asset.get("has_audio")),
    }
    return str(path), resolved


def _segment(
    source: str,
    meta: dict,
    scene: dict,
    start: float,
    duration: float,
    frames: int,
    output: Path,
    first: bool,
    last: bool,
    out_w: int,
    out_h: int,
    quality: str,
    encoder: str,
    cache_dir: Path,
    crop: dict | None = None,
    crop_path: list[dict] | None = None,
    cancel_event: threading.Event | None = None,
    pre_filters: list[str] | None = None,
    post_filters: list[str] | None = None,
    decode_threads: int | None = None,
    fill: dict | None = None,
    reverse: bool = False,
    freeze: bool = False,
    fps: int = OUT_FPS,
) -> bool:
    """Render one beat. Return True when the segment came from cache.

    ``fill`` is a ``textfill.prepare_span`` result: the beat then reads that
    filled clip from its start instead of the source at ``start``.
    """
    key = _segment_cache_key(
        meta, scene, start, frames, out_w, out_h, quality, encoder, first, last,
        crop, crop_path, pre_filters, post_filters,
        fill_key=(fill or {}).get("key"), reverse=reverse, freeze=freeze, fps=fps,
    )
    cached = cache_dir / f"{key}.mp4"
    if cached.exists() and cached.stat().st_size > 0:
        _link_or_copy(cached, output)
        return True

    ffmpeg = _ffmpeg()
    parts: list[str] = []
    if freeze:
        parts.append(f"tpad=stop_mode=clone:stop_duration={max(0.0, duration - 0.04):.3f}")
    if pre_filters:
        parts.append(",".join(str(item) for item in pre_filters))
    parts.append(_crop_filter(
        meta, crop or scene.get("crop") or {"cx": 0.5, "cy": 0.5},
        out_w, out_h, crop_path=crop_path, duration=duration,
    ))
    if post_filters:
        parts.append(",".join(str(item) for item in post_filters))
    if reverse:
        parts.append("reverse")
    parts.append(f"fps={fps}")
    vf = ",".join(part for part in parts if part)

    if first and duration > 0.4:
        vf += ",fade=t=in:st=0:d=0.12"
    if last and duration > 0.6:
        vf += f",fade=t=out:st={max(0.0, duration - 0.4):.3f}:d=0.4"

    part = output.parent / f".{output.stem}.part.mp4"
    if part.exists():
        part.unlink()
    input_args = [
        *_decoder_args(meta, decode_threads),
        "-ss", f"{start:.3f}", "-t", f"{duration:.6f}", "-i", source,
    ]
    if fill:
        input_args = ["-t", f"{duration:.6f}", "-i", str(fill["path"])]
    cmd = [
        ffmpeg, "-y", "-v", "error",
        *input_args,
        "-frames:v", str(frames),
        "-vf", vf,
        "-an",
        *_encoder_args(encoder, quality),
        "-video_track_timescale", "90000",
        "-avoid_negative_ts", "make_zero",
        "-muxdelay", "0", "-muxpreload", "0",
        str(part),
    ]
    _run(cmd, timeout=300, cancel_event=cancel_event)
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(part, cached)
        _link_or_copy(cached, output)
    except OSError:
        os.replace(part, output)
    return False


def _audio_inputs(clips: list[dict]) -> list[dict]:
    """Join clips that run on in the source into one read of it.

    A full video is hundreds of touching clips. One input per clip can run out
    of open files, and its fade at every cut would tick all the way through. A
    join stops once it drifts a frame's fraction from the video's own cut.
    """
    joined: list[dict] = []
    for clip in clips:
        last = joined[-1] if joined else None
        if (
            last is not None
            and _plain_audio(last) and _plain_audio(clip)
            and abs(float(last["start"]) + float(last["duration"]) - float(clip["start"])) < 0.02
        ):
            last["duration"] = float(last["duration"]) + float(clip["duration"])
        else:
            joined.append(dict(clip))
    return joined


def _plain_audio(clip: dict) -> bool:
    return not (
        clip.get("kind") == "blank" or clip.get("freeze")
        or clip.get("file") or clip.get("reverse")
    )


def _long_step(total: float, floor: int) -> int:
    """Time for a step that reads the whole output, which can run for hours."""
    return max(floor, int(float(total or 0.0) * 8))


def _audio_track(
    source: str,
    meta: dict,
    clips: list[dict],
    output: Path,
    total: float,
    cancel_event: threading.Event | None = None,
    fade: dict | None = None,
    job_dir: Path | None = None,
) -> None:
    """Build one continuous PCM bed from each clip's own exact input window.

    Using one input per clip avoids cumulative seek drift and keeps the audio
    sample-exact with the video beats, including clips from the same scene.
    """
    ffmpeg = _ffmpeg()
    if not meta.get("has_audio"):
        _run([
            ffmpeg, "-y", "-v", "error",
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-t", f"{total:.6f}", "-c:a", "pcm_s16le", str(output),
        ], timeout=120, cancel_event=cancel_event)
        return

    clips = _audio_inputs(clips)
    cmd = [ffmpeg, "-y", "-v", "error"]
    for clip in clips:
        if (
            clip.get("kind") == "blank"
            or clip.get("freeze")
            or (clip.get("file") and not bool((clip.get("asset") or {}).get("has_audio")))
        ):
            cmd += [
                "-f", "lavfi",
                "-t", f"{float(clip['duration']):.6f}",
                "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
            ]
        else:
            clip_source = source
            if job_dir is not None and clip.get("file"):
                clip_source = str(job_dir / str(clip["file"]))
            cmd += [
                "-ss", f"{float(clip['start']):.6f}",
                "-t", f"{float(clip['duration']):.6f}",
                "-i", clip_source,
            ]

    graph: list[str] = []
    for index, clip in enumerate(clips):
        duration = float(clip["duration"])
        branch = (
            f"[{index}:a]aresample=48000,"
            f"atrim=start=0:end={duration:.6f},"
            f"asetpts=PTS-STARTPTS"
        )
        if clip.get("reverse"):
            branch += ",areverse"
        if duration > 0.02:
            branch += (
                f",afade=t=in:st=0:d=0.005"
                f",afade=t=out:st={duration - 0.005:.6f}:d=0.005"
            )
        graph.append(branch + f"[b{index}]")
    graph.append(
        "".join(f"[b{index}]" for index in range(len(clips))) +
        f"concat=n={len(clips)}:v=0:a=1[cat]"
    )
    fades = ["apad"]
    try:
        fade_in = max(0.0, min(10.0, float((fade or {}).get("in") or 0.0)))
        fade_out = max(0.0, min(10.0, float((fade or {}).get("out") or 0.0)))
    except (TypeError, ValueError):
        fade_in = fade_out = 0.0
    if fade_in > 0 or fade_out > 0:
        if fade_in > 0:
            fades.append(f"afade=t=in:st=0:d={min(fade_in, total):.3f}")
        if fade_out > 0:
            fades.append(
                f"afade=t=out:st={max(0.0, total - fade_out):.6f}:"
                f"d={min(fade_out, total):.3f}"
            )
    else:
        if total > 0.4:
            fades.append("afade=t=in:st=0:d=0.12")
        if total > 0.6:
            fades.append(f"afade=t=out:st={max(0.0, total - 0.5):.6f}:d=0.5")
    graph.append("[cat]" + ",".join(fades) + "[out]")

    cmd += [
        "-filter_complex", ";".join(graph),
        "-map", "[out]",
        "-t", f"{total:.6f}",
        "-ar", "48000", "-ac", "2",
        "-c:a", "pcm_s16le",
        str(output),
    ]
    _run(cmd, timeout=_long_step(total, 900), cancel_event=cancel_event)


def _caption_text(scene: dict) -> str:
    return caption_engine.caption_text(scene)


def _caption_chunks(text: str, width: int = caption_engine.CUE_WIDTH) -> list[str]:
    return caption_engine.chunk_text(text, width)


def _caption_cues(plan: dict, clips: list[dict]) -> list[tuple[float, float, str]]:
    """Burn-in cues. Delegates to the one cue engine also used by SRT/VTT."""
    style = plan.get("_caption_style")
    rows = caption_engine.cues_for_plan(
        plan,
        plan.get("clips") or clips,
        plan.get("_scenes") or [],
        style=style,
        source_duration=plan.get("_source_duration"),
    )
    return caption_engine.cue_tuples(rows)


_FONT_NAMES = {
    "arial": "/System/Library/Fonts/Supplemental/Arial.ttf",
    "arial unicode": "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "helvetica": "/System/Library/Fonts/Helvetica.ttc",
    "hiragino": "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "hiragino sans gb": "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "sans": "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "sans-serif": "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "serif": "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    "mono": "/System/Library/Fonts/Menlo.ttc",
    "monospace": "/System/Library/Fonts/Menlo.ttc",
    "dejavu": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "dejavu sans": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "noto": "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "noto sans": "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "noto sans cjk": "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
}


def _caption_font(
    size: int,
    font_name: str | None = None,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates: list[str] = []
    requested = str(font_name or "").strip()
    if requested:
        path = Path(requested).expanduser()
        if path.is_file():
            candidates.append(str(path))
        else:
            named = _FONT_NAMES.get(requested.lower())
            if named:
                candidates.append(named)
    candidates.append(os.environ.get("VIBECUT_CAPTION_FONT_FILE") or "")
    candidates.extend([
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    ])
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if not Path(candidate).is_file():
            continue
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


# ---------------------------------------------------------------- text fonts
#
# Burned-in text used one regular-weight font (Arial Unicode) with no colour
# glyphs, so style.weight was ignored and emoji drew as tofu boxes. Text now
# draws in runs: weighted San Francisco (or Helvetica Neue) for the scripts it
# covers, the old wide-coverage chain for everything else (CJK and more), and
# Apple Color Emoji bitmaps for emoji. All are macOS system fonts; on a host
# without them the old single-font path is used unchanged.

SYSTEM_SANS = "/System/Library/Fonts/SFNS.ttf"
SYSTEM_SANS_STATIC = "/System/Library/Fonts/HelveticaNeue.ttc"
EMOJI_FONT = "/System/Library/Fonts/Apple Color Emoji.ttc"
EMOJI_STRIKE = 160  # Apple Color Emoji only rasterizes at its bitmap strikes.
# Helvetica Neue faces by CSS weight (index into HelveticaNeue.ttc).
_HELVETICA_NEUE_FACES = {100: 12, 200: 5, 300: 7, 400: 0, 500: 10, 600: 10, 700: 1, 800: 1, 900: 1}
_SANS_NAMES = {"", "sans", "sans-serif", "system", "sf", "sf pro"}
_FONT_CACHE: dict[tuple, object] = {}
_FONT_LOCK = threading.Lock()


def _cached_font(key: tuple, build: Callable[[], object]):
    with _FONT_LOCK:
        if key in _FONT_CACHE:
            return _FONT_CACHE[key]
    value = build()
    with _FONT_LOCK:
        _FONT_CACHE[key] = value
    return value


def _weighted_sans(size: int, weight: int):
    """San Francisco at ``weight`` (variable axes), else Helvetica Neue, else None."""
    weight = max(100, min(900, int(round(weight / 100.0)) * 100))

    def build():
        if Path(SYSTEM_SANS).is_file():
            try:
                font = ImageFont.truetype(SYSTEM_SANS, size)
                axes = font.get_variation_axes()
                values = []
                for axis in axes:
                    name = axis.get("name")
                    name = name.decode() if isinstance(name, bytes) else str(name)
                    if name.lower() == "weight":
                        value = weight
                    elif name.lower() == "optical size":
                        value = size
                    else:
                        value = axis.get("default")
                    values.append(max(axis["minimum"], min(axis["maximum"], value)))
                font.set_variation_by_axes(values)
                return font
            except (OSError, ValueError, KeyError, AttributeError):
                pass
        if Path(SYSTEM_SANS_STATIC).is_file():
            try:
                return ImageFont.truetype(
                    SYSTEM_SANS_STATIC, size, index=_HELVETICA_NEUE_FACES[weight],
                )
            except OSError:
                pass
        return None

    return _cached_font(("sans", size, weight), build)


def _emoji_font():
    def build():
        if not Path(EMOJI_FONT).is_file():
            return None
        try:
            return ImageFont.truetype(EMOJI_FONT, EMOJI_STRIKE)
        except OSError:
            return None

    return _cached_font(("emoji",), build)


_EMOJI_RANGES = (
    (0x1F000, 0x1FAFF),  # pictographs, emoticons, transport, flags, symbols
    (0x2600, 0x27BF),    # misc symbols and dingbats
    (0x2B00, 0x2BFF),    # arrows and stars used as emoji
    (0x2300, 0x23FF),    # watch, hourglass, media keys
)
_EMOJI_JOINERS = {"‍", "️", "⃣"}


def _is_emoji(char: str) -> bool:
    code = ord(char)
    return any(low <= code <= high for low, high in _EMOJI_RANGES)


def _cmap_ranges(path: str, index: int = 0) -> list[tuple[int, int]] | None:
    """Code point ranges a font maps, read from its ``cmap`` table.

    A tiny reader for formats 4 and 12 (all macOS system text fonts use one
    of them), so coverage is known without a font library. Returns None when
    the file can't be read; callers then fall back to a glyph comparison.
    """
    import struct  # noqa: PLC0415

    def build():
        try:
            data = Path(path).read_bytes()
            base = 0
            if data[:4] == b"ttcf":
                count = struct.unpack(">I", data[8:12])[0]
                if index >= count:
                    return None
                base = struct.unpack(">I", data[12 + 4 * index:16 + 4 * index])[0]
            tables = struct.unpack(">H", data[base + 4:base + 6])[0]
            cmap = None
            for row in range(tables):
                entry = base + 12 + 16 * row
                if data[entry:entry + 4] == b"cmap":
                    cmap = struct.unpack(">I", data[entry + 8:entry + 12])[0]
                    break
            if cmap is None:
                return None
            subtables = struct.unpack(">H", data[cmap + 2:cmap + 4])[0]
            best = None
            for row in range(subtables):
                platform, encoding, offset = struct.unpack(
                    ">HHI", data[cmap + 4 + 8 * row:cmap + 12 + 8 * row],
                )
                fmt = struct.unpack(">H", data[cmap + offset:cmap + offset + 2])[0]
                rank = {(3, 10, 12): 0, (0, 4, 12): 0, (0, 3, 4): 1, (3, 1, 4): 1}.get(
                    (platform, encoding, fmt), 2 if fmt in (4, 12) else None,
                )
                if rank is not None and (best is None or rank < best[0]):
                    best = (rank, cmap + offset, fmt)
            if best is None:
                return None
            _rank, start, fmt = best
            ranges: list[tuple[int, int]] = []
            if fmt == 12:
                groups = struct.unpack(">I", data[start + 12:start + 16])[0]
                for group in range(groups):
                    low, high, _glyph = struct.unpack(
                        ">III", data[start + 16 + 12 * group:start + 28 + 12 * group],
                    )
                    ranges.append((low, high))
            else:
                segments = struct.unpack(">H", data[start + 6:start + 8])[0] // 2
                ends = struct.unpack(f">{segments}H", data[start + 14:start + 14 + 2 * segments])
                starts_at = start + 16 + 2 * segments
                starts = struct.unpack(f">{segments}H", data[starts_at:starts_at + 2 * segments])
                ranges = [
                    (low, high) for low, high in zip(starts, ends) if low != 0xFFFF
                ]
            return sorted(ranges)
        except (OSError, struct.error, IndexError, ValueError):
            return None

    return _cached_font(("cmap", str(path), int(index)), build)


class TextFonts:
    """A primary font plus per-character fallbacks and colour emoji.

    ``runs`` splits a line into ``(text, font)`` pieces; ``font is None``
    marks an emoji run. Widths are summed per run, so wrapping and centring
    see the same geometry that is drawn.
    """

    def __init__(self, size: int, primary, fallbacks: list, emoji=None):
        self.size = int(size)
        self.primary = primary
        self.fallbacks = [font for font in fallbacks if font is not None and font is not primary]
        self.emoji = emoji
        self._covers: dict[tuple[int, str], bool] = {}
        self._notdef: dict[int, bytes] = {}
        try:
            self.ascent = int(primary.getmetrics()[0])
        except (AttributeError, TypeError):
            self.ascent = int(size * 0.8)

    def _has_glyph(self, font, char: str) -> bool:
        if char.isspace() or not self.fallbacks:
            return True
        key = (id(font), char)
        if key not in self._covers:
            ranges = _cmap_ranges(getattr(font, "path", ""), getattr(font, "index", 0) or 0)
            if ranges is not None:
                code = ord(char)
                position = bisect.bisect_right(ranges, (code, 0x10FFFF)) - 1
                self._covers[key] = position >= 0 and ranges[position][0] <= code <= ranges[position][1]
                return self._covers[key]
            try:
                if id(font) not in self._notdef:
                    self._notdef[id(font)] = font.getmask("\U0010fffd").tobytes()
                self._covers[key] = font.getmask(char).tobytes() != self._notdef[id(font)]
            except (AttributeError, OSError, ValueError):
                self._covers[key] = True
        return self._covers[key]

    def _font_for(self, char: str):
        if self.emoji is not None and (_is_emoji(char) or char in _EMOJI_JOINERS):
            return None
        if self._has_glyph(self.primary, char):
            return self.primary
        for font in self.fallbacks:
            if self._has_glyph(font, char):
                return font
        return self.primary

    def runs(self, text: str) -> list[tuple[str, object]]:
        rows: list[tuple[str, object]] = []
        for char in str(text):
            font = self._font_for(char)
            if rows and rows[-1][1] is font:
                rows[-1] = (rows[-1][0] + char, font)
            else:
                rows.append((char, font))
        return rows

    def _emoji_glyphs(self, text: str) -> list[str]:
        return [char for char in text if char not in _EMOJI_JOINERS]

    def width(self, text: str) -> float:
        total = 0.0
        for piece, font in self.runs(text):
            if font is None:
                total += len(self._emoji_glyphs(piece)) * self.size * 1.08
            else:
                total += float(font.getlength(piece))
        return total

    def _emoji_image(self, char: str, alpha: float):
        def build():
            canvas = Image.new("RGBA", (EMOJI_STRIKE + 40, EMOJI_STRIKE + 40), (0, 0, 0, 0))
            ImageDraw.Draw(canvas).text((0, 0), char, font=self.emoji, embedded_color=True)
            box = canvas.getbbox()
            return canvas.crop(box) if box else None

        glyph = _cached_font(("emoji-glyph", char), build)
        if glyph is None:
            return None
        scale = self.size / float(EMOJI_STRIKE)
        image = glyph.resize(
            (max(1, int(round(glyph.width * scale))), max(1, int(round(glyph.height * scale)))),
            Image.LANCZOS,
        )
        if alpha < 0.999:
            image.putalpha(image.getchannel("A").point(lambda value: int(value * alpha)))
        return image

    def draw_line(
        self,
        image: Image.Image,
        x: float,
        top: float,
        text: str,
        *,
        align: str = "center",
        fill=None,
        stroke_width: int = 0,
        stroke_fill=None,
        emoji: bool = True,
        alpha: float = 1.0,
    ) -> None:
        """Draw one line whose ascender top is ``top``; ``x`` is its anchor."""
        draw = ImageDraw.Draw(image)
        total = self.width(text)
        cursor = x - total / 2.0 if align == "center" else x - total if align == "right" else x
        baseline = top + self.ascent
        for piece, font in self.runs(text):
            if font is not None:
                draw.text(
                    (cursor, baseline), piece, font=font, anchor="ls",
                    fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill,
                )
                cursor += float(font.getlength(piece))
                continue
            for char in self._emoji_glyphs(piece):
                step = self.size * 1.08
                glyph = self._emoji_image(char, alpha) if emoji else None
                if glyph is not None:
                    gx = int(round(cursor + (step - glyph.width) / 2.0))
                    gy = int(round(baseline - self.size * 0.86))
                    image.alpha_composite(glyph, (max(0, gx), max(0, gy)))
                cursor += step


def _text_fonts(size: int, font_name: str | None = None, weight: int | None = 400) -> TextFonts:
    """Fonts for one text style: weighted sans first for the default family."""
    base = _caption_font(size, font_name)
    requested = str(font_name or "").strip().lower()
    primary = None
    if requested in _SANS_NAMES and not os.environ.get("VIBECUT_CAPTION_FONT_FILE"):
        primary = _weighted_sans(size, int(weight or 400))
    fallbacks = [base]
    hiragino = "/System/Library/Fonts/Hiragino Sans GB.ttc"
    if Path(hiragino).is_file():
        fallbacks.append(_cached_font(("hiragino", size), lambda: ImageFont.truetype(hiragino, size)))
    if primary is None:
        primary = base
    return TextFonts(size, primary, fallbacks if isinstance(primary, ImageFont.FreeTypeFont) else [], _emoji_font())


def _wrap_caption(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    """Wrap text to ``max_width`` pixels, keeping the author's line breaks.

    Caption cues and text layers store explicit ``\\n`` breaks, and PIL's
    ``textlength`` refuses multiline strings, so each stored line is wrapped
    on its own. Spaced scripts break between words; a word wider than the
    box, or unspaced CJK text, falls back to breaking between characters.
    """
    if not text:
        return []
    lines: list[str] = []

    def fits(value: str) -> bool:
        if isinstance(font, TextFonts):
            return font.width(value) <= max_width
        return draw.textlength(value, font=font) <= max_width

    def by_char(word: str) -> list[str]:
        rows: list[str] = []
        current = ""
        for char in word:
            if current and not fits(current + char):
                rows.append(current)
                current = char
            else:
                current += char
        if current:
            rows.append(current)
        return rows

    for paragraph in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        current = ""
        for word in paragraph.split():
            candidate = f"{current} {word}" if current else word
            if fits(candidate):
                current = candidate
                continue
            if current:
                lines.append(current)
            if fits(word):
                current = word
            else:
                pieces = by_char(word)
                lines.extend(pieces[:-1])
                current = pieces[-1] if pieces else ""
        if current:
            lines.append(current)
    return lines


def _rgba(value: str, alpha: int = 255) -> tuple[int, int, int, int]:
    text = str(value or "").strip().lstrip("#")
    if len(text) == 3:
        text = "".join(char * 2 for char in text)
    if len(text) not in (6, 8) or any(char not in "0123456789abcdefABCDEF" for char in text):
        return 255, 255, 255, alpha
    red, green, blue = (int(text[index:index + 2], 16) for index in (0, 2, 4))
    if len(text) == 8:
        alpha = int(int(text[6:8], 16) * alpha / 255)
    return red, green, blue, alpha


def _caption_pngs(
    tmp: Path,
    cues: list[tuple[float, float, str]],
    out_w: int,
    out_h: int,
    margin_fraction: float = 0.075,
    style: dict | None = None,
) -> list[Path]:
    if style is None:
        style = caption_engine.normalize_style({
            "safe_zone": {
                "top": 0.08, "right": 0.07,
                "bottom": max(0.03, min(0.3, margin_fraction)),
                "left": 0.07,
            },
        })
    else:
        style = caption_engine.normalize_style(style)
    scale = out_h / 1920.0
    font_size = max(12, int(round(float(style["font_size"]) * scale)))
    zone = style["safe_zone"]
    left = int(out_w * float(zone["left"]))
    right = int(out_w * float(zone["right"]))
    top = int(out_h * float(zone["top"]))
    bottom = int(out_h * float(zone["bottom"]))
    max_width = max(40, out_w - left - right)
    fill = _rgba(str(style["color"]))
    stroke_fill = _rgba(str(style["stroke_color"]))
    background = _rgba(
        str(style["background"]),
        int(round(float(style["background_opacity"]) * 255)),
    )

    # Keep every stored line. CJK glyphs are roughly font-size wide, so a
    # character count that fits Latin text can overflow; shrink the whole
    # track's font once instead of dropping lines or rewrapping into a
    # different cue.
    prepared: list[tuple[float, float, list[str]]] = []
    for start, end, text in cues:
        value = str(text)
        if style.get("uppercase"):
            value = value.upper()
        lines = [
            line.strip() for line in value.splitlines() if line.strip()
        ] or [value.strip()]
        lines = [line for line in lines if line]
        if lines:
            prepared.append((start, end, lines))
    if not prepared:
        return []

    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    font = _text_fonts(font_size, style.get("font"), CAPTION_WEIGHT)
    widest = max(
        font.width(line)
        for _start, _end, lines in prepared
        for line in lines
    )
    if widest > max_width:
        fitted_size = max(12, int(font_size * max_width / max(1.0, widest)) - 1)
        if fitted_size < font_size:
            font_size = fitted_size
            font = _text_fonts(font_size, style.get("font"), CAPTION_WEIGHT)
            widest = max(
                font.width(line)
                for _start, _end, lines in prepared
                for line in lines
            )
    if widest > max_width:
        # Last resort for pathological edits: wrap to the safe width.
        wrapped: list[tuple[float, float, list[str]]] = []
        for start, end, lines in prepared:
            rows: list[str] = []
            for line in lines:
                rows.extend(_wrap_caption(measure, line, font, max_width))
            wrapped.append((start, end, rows))
        prepared = wrapped
    line_height = max(1, int(font_size * 1.22))
    stroke = max(0, int(round(float(style["stroke_width"]) * scale)))
    paths: list[Path] = []
    for index, (_start, _end, lines) in enumerate(prepared):
        image = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        if style["position"] == "top":
            y = top
        elif style["position"] == "center":
            y = max(0, (out_h - line_height * len(lines)) // 2)
        else:
            y = max(0, out_h - bottom - line_height * len(lines))
        if background[3] > 0:
            padding = max(4, int(font_size * 0.18))
            draw.rounded_rectangle(
                (
                    left - padding,
                    y - padding,
                    left + max_width + padding,
                    y + line_height * len(lines) + padding,
                ),
                radius=max(2, int(font_size * 0.18)),
                fill=background,
            )
        x = left + max_width // 2
        for line in lines:
            font.draw_line(
                image, x, y, line, align="center",
                fill=fill, stroke_width=stroke, stroke_fill=stroke_fill,
            )
            y += line_height
        path = tmp / f"caption-{index:03d}.png"
        image.save(path)
        paths.append(path)
    return paths


def _layer_rect(layer: dict, out_w: int, out_h: int) -> tuple[int, int, int, int]:
    rect = layer.get("rect") or {}
    x = int(round(float(rect.get("x") or 0.0) * out_w))
    y = int(round(float(rect.get("y") or 0.0) * out_h))
    w = max(1, int(round(float(rect.get("w") or 0.0) * out_w)))
    h = max(1, int(round(float(rect.get("h") or 0.0) * out_h)))
    x = max(0, min(out_w - 1, x))
    y = max(0, min(out_h - 1, y))
    w = max(1, min(out_w - x, w))
    h = max(1, min(out_h - y, h))
    return x, y, w, h


def _layer_place(layer: dict, out_w: int, out_h: int) -> tuple[int, int, int, int]:
    """Where a layer goes. One stuck to the video keeps its size past the frame."""
    if not layer.get("stuck"):
        return _layer_rect(layer, out_w, out_h)
    rect = layer.get("rect") or {}
    return (
        int(round(float(rect.get("x") or 0.0) * out_w)),
        int(round(float(rect.get("y") or 0.0) * out_h)),
        max(1, int(round(float(rect.get("w") or 0.0) * out_w))),
        max(1, int(round(float(rect.get("h") or 0.0) * out_h))),
    )


def _layer_font_size(style: dict, out_h: int) -> int:
    try:
        size = float(style.get("size") or 44)
    except (TypeError, ValueError):
        size = 44.0
    return max(10, int(round(size * out_h / 1920.0)))


def _layer_payload(layer: dict, out_w: int, out_h: int, fps: int, frames: int) -> dict:
    return {
        "skin": LAYER_CACHE_VERSION,
        "type": layer.get("type"),
        "kind": layer.get("kind"),
        "text": layer.get("text") or "",
        "rect": layer.get("rect"),
        "style": layer.get("style") or {},
        "color": layer.get("color"),
        "thickness": layer.get("thickness"),
        "opacity": layer.get("opacity", 1.0),
        "out": [int(out_w), int(out_h)],
        "fps": int(fps),
        "frames": int(frames),
        "asset": layer.get("asset"),
    }


def _layer_cache_key(
    layer: dict, out_w: int, out_h: int, fps: int, frames: int,
) -> str:
    return hashlib.sha256(
        json.dumps(
            _layer_payload(layer, out_w, out_h, fps, frames),
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8"),
    ).hexdigest()[:24]


def _layer_frames(layer: dict, fps: int) -> int:
    raster = layer.get("raster") or {}
    frames = int(raster.get("frames") or 0)
    if frames > 0:
        return frames
    if layer.get("type") == "fx" and layer.get("kind") == "progress_bar":
        duration = max(0.0, float(layer.get("end") or 0.0) - float(layer.get("start") or 0.0))
        return max(1, int(math.ceil(duration * fps - 1e-6)))
    return 1


def _layer_is_sequence(layer: dict) -> bool:
    raster = layer.get("raster") or {}
    if raster.get("mode"):
        return raster["mode"] == "sequence"
    return layer.get("type") == "fx" and layer.get("kind") == "progress_bar"


def _render_text_layer(layer: dict, out_w: int, out_h: int) -> Image.Image:
    x, y, w, h = _layer_place(layer, out_w, out_h)
    image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    style = layer.get("style") or {}
    text = str(layer.get("text") or "")
    if style.get("uppercase"):
        text = text.upper()
    if not text.strip():
        return image
    size = _layer_font_size(style, out_h)
    weight = _style_weight(style)
    font = _text_fonts(size, style.get("font"), weight)
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    lines: list[str] = []
    while size >= 10:
        lines = _wrap_caption(measure, text, font, max(8, w - 8))
        if not lines:
            break
        widest = max(font.width(line) for line in lines)
        line_height = max(1, int(size * 1.18))
        if widest <= max(8, w - 8) and line_height * len(lines) <= h:
            break
        size -= 2
        font = _text_fonts(size, style.get("font"), weight)
    if not lines:
        return image

    opacity = max(0.0, min(1.0, float(layer.get("opacity", 1.0))))
    fill = _rgba(str(style.get("color") or "#ffffff"), int(round(opacity * 255)))
    background = str(style.get("background") or "none")
    if background not in {"none", "", "None"}:
        plate = _rgba(background, int(round(opacity * 255)))
        if plate[3] > 0:
            draw.rounded_rectangle(
                (0, 0, w - 1, h - 1),
                radius=max(2, int(size * 0.18)),
                fill=plate,
            )
    stroke_value = style.get("stroke")
    stroke_fill = None
    stroke_width = 0
    if stroke_value and str(stroke_value).lower() not in {"none", ""}:
        stroke_fill = _rgba(str(stroke_value), int(round(opacity * 255)))
        stroke_width = _stroke_px(style, size, out_h)
    line_height = max(1, int(size * 1.18))
    total_height = line_height * len(lines)
    top = max(0, (h - total_height) // 2)
    align = str(style.get("align") or "center")
    align = align if align in {"left", "right"} else "center"
    px = {"left": 4, "right": w - 4}.get(align, w // 2)
    if style.get("shadow"):
        shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        offset = max(1, int(round(size * 0.06)))
        for index, line in enumerate(lines):
            font.draw_line(
                shadow, px + offset, top + index * line_height + offset, line,
                align=align, fill=(0, 0, 0, int(150 * opacity)),
                stroke_width=stroke_width, stroke_fill=(0, 0, 0, 150), emoji=False,
            )
        image = Image.alpha_composite(image, shadow)
    for index, line in enumerate(lines):
        font.draw_line(
            image, px, top + index * line_height, line,
            align=align, fill=fill, stroke_width=stroke_width,
            stroke_fill=stroke_fill, alpha=opacity,
        )
    return image


def _style_weight(style: dict) -> int:
    try:
        return max(100, min(900, int(round(float(style.get("weight") or 400)))))
    except (TypeError, ValueError):
        return 400


def _stroke_px(style: dict, size: int, out_h: int) -> int:
    """Outline width: the style's own width (1920-tall units) or ~8% of size."""
    try:
        explicit = float(style.get("stroke_width"))
    except (TypeError, ValueError):
        explicit = None
    if explicit is not None and math.isfinite(explicit):
        return max(0, int(round(explicit * out_h / 1920.0)))
    return max(1, int(round(size * 0.08)))


def _render_fx_layer(
    layer: dict,
    out_w: int,
    out_h: int,
    frame_index: int = 0,
    frame_count: int = 1,
) -> Image.Image | None:
    x, y, w, h = _layer_rect(layer, out_w, out_h)
    image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    opacity = max(0.0, min(1.0, float(layer.get("opacity", 1.0))))
    color = _rgba(str(layer.get("color") or "#ffffff"), int(round(opacity * 255)))
    thickness = max(1, int(layer.get("thickness") or 6))
    kind = layer.get("kind")
    if kind == "progress_bar":
        fraction = (
            1.0 if frame_count <= 1
            else max(0.0, min(1.0, (frame_index + 1) / frame_count))
        )
        track = (255, 255, 255, int(60 * opacity))
        draw.rounded_rectangle((0, 0, w - 1, h - 1), radius=max(1, h // 2), fill=track)
        fill_w = max(1, int(round(w * fraction)))
        draw.rounded_rectangle(
            (0, 0, fill_w - 1, h - 1), radius=max(1, h // 2), fill=color,
        )
    elif kind == "underline":
        pad = max(1, thickness // 2)
        draw.rounded_rectangle(
            (0, h - thickness - pad, w - 1, h - pad),
            radius=max(1, thickness // 2), fill=color,
        )
    elif kind == "arrow":
        head = max(4, int(w * 0.16))
        shaft = max(2, thickness)
        mid = h // 2
        draw.line((0, mid, w - head, mid), fill=color, width=shaft)
        draw.polygon(
            [(w - 1, mid), (w - head, mid - head // 2), (w - head, mid + head // 2)],
            fill=color,
        )
    elif kind == "circle":
        pad = max(1, thickness // 2)
        draw.ellipse((pad, pad, w - pad - 1, h - pad - 1), outline=color, width=thickness)
    elif kind == "sticker":
        path = layer.get("asset_path")
        if not path:
            return None
        try:
            sticker = Image.open(path).convert("RGBA")
        except OSError:
            return None
        sticker.thumbnail((w, h), Image.LANCZOS)
        image.alpha_composite(sticker, ((w - sticker.width) // 2, (h - sticker.height) // 2))
        return image
    else:
        return None
    return image


def _render_layer_image(
    layer: dict,
    out_w: int,
    out_h: int,
    frame_index: int = 0,
    frame_count: int = 1,
) -> Image.Image | None:
    if layer.get("type") in {"text", "caption"}:
        return _render_text_layer(layer, out_w, out_h)
    return _render_fx_layer(layer, out_w, out_h, frame_index, frame_count)


def _layer_png(
    layer: dict,
    out_w: int,
    out_h: int,
    cache_dir: Path,
    frame_index: int = 0,
    frame_count: int = 1,
    fps: int = OUT_FPS,
) -> Path | None:
    """Rasterize one layer frame and cache it by layer hash."""
    sequence = _layer_is_sequence(layer)
    frames = _layer_frames(layer, fps) if sequence else 1
    key = _layer_cache_key(
        layer, out_w, out_h, fps, frames if sequence else 1,
    )
    if sequence:
        index = max(0, min(frames - 1, int(frame_index)))
        path = cache_dir / key / f"{index + 1:05d}.png"
    else:
        path = cache_dir / f"{key}.png"
    if path.is_file() and path.stat().st_size > 0:
        return path
    image = _render_layer_image(
        layer, out_w, out_h,
        frame_index=frame_index if sequence else 0,
        frame_count=frames if sequence else 1,
    )
    if image is None:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        image.save(tmp, format="PNG")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return path


def _layer_canvas_png(layer: dict, png: Path, out_w: int, out_h: int) -> Path:
    """The layer on a transparent whole frame, for a beat's motion to act on."""
    path = png.with_name(f"{png.stem}_canvas_{int(out_w)}x{int(out_h)}.png")
    if path.is_file() and path.stat().st_size > 0:
        return path
    x, y, _w, _h = _layer_place(layer, out_w, out_h)
    canvas = Image.new("RGBA", (int(out_w), int(out_h)), (0, 0, 0, 0))
    with Image.open(png) as image:
        rgba = image.convert("RGBA")
        canvas.paste(rgba, (x, y), rgba)
    tmp = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        canvas.save(tmp, format="PNG")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return path


def _stuck_enable(layer: dict, fps: int) -> str:
    """When a stuck piece shows. Pieces meet at a beat cut, so exactly one owns
    each frame: the edges sit a quarter frame early, between two frames."""
    early = 0.25 / fps
    start = float(layer.get("start") or 0.0) - early
    end = float(layer.get("end") or 0.0) - early
    return f"gte(t,{start:.6f})*lt(t,{end:.6f})"


def _layer_sequence(
    layer: dict,
    out_w: int,
    out_h: int,
    cache_dir: Path,
    fps: int = OUT_FPS,
) -> tuple[Path, int] | None:
    frames = _layer_frames(layer, fps)
    first = _layer_png(
        layer, out_w, out_h, cache_dir,
        frame_index=0, frame_count=frames, fps=fps,
    )
    if first is None:
        return None
    directory = first.parent
    for index in range(1, frames):
        _layer_png(
            layer, out_w, out_h, cache_dir,
            frame_index=index, frame_count=frames, fps=fps,
        )
    return directory / "%05d.png", frames


def _caption_runs(layers: list[dict]) -> dict[int, int]:
    """Contiguous runs of static caption layers that share a rectangle.

    Collapsing a run into a single timed overlay keeps its z position and
    only works while nothing else is stacked inside it. A graphic layer
    between cue groups splits the run; each piece still collapses.
    """
    runs: dict[int, int] = {}
    start: int | None = None
    rect = ""
    for index, layer in enumerate(layers):
        caption = (
            layer.get("type") == "caption" and not _layer_is_sequence(layer)
        )
        if caption:
            value = json.dumps(layer.get("rect") or {}, sort_keys=True)
            if start is None or value != rect:
                if start is not None and index - start >= CAPTION_TRACK_MIN:
                    runs[start] = index - 1
                start, rect = index, value
            continue
        if start is not None and index - start >= CAPTION_TRACK_MIN:
            runs[start] = index - 1
        start, rect = None, ""
    if start is not None and len(layers) - start >= CAPTION_TRACK_MIN:
        runs[start] = len(layers) - 1
    return runs


def _burn_layers(
    video: Path,
    layers: list[dict],
    output: Path,
    tmp: Path,
    out_w: int,
    out_h: int,
    total: float,
    quality: str,
    encoder: str,
    cache_dir: Path | None = None,
    cancel_event: threading.Event | None = None,
    fps: int = OUT_FPS,
) -> int:
    """Burn compiled overlay layers in one encode. Return layers burned."""
    active = [
        layer for layer in layers
        if float(layer.get("end") or 0.0) > float(layer.get("start") or 0.0) + 1e-6
        and float(layer.get("start") or 0.0) < total - 1e-6
    ]
    if not active:
        return 0
    layer_cache = cache_dir or (tmp / "layers")
    runs = _caption_runs(active)
    prepared: list[dict] = []
    index = 0
    while index < len(active):
        if index in runs:
            last_index = runs[index]
            group = active[index:last_index + 1]
            items: list[tuple[float, float, Path]] = []
            for layer in group:
                png = _layer_png(layer, out_w, out_h, layer_cache, fps=fps)
                if png is None:
                    items = []
                    break
                items.append((
                    float(layer.get("start") or 0.0),
                    float(layer.get("end") or 0.0),
                    png,
                ))
            x, y, w, h = _layer_rect(group[0], out_w, out_h)
            track = (
                _still_overlay_track(items, total, tmp, (w, h))
                if items else None
            )
            if track is not None:
                prepared.append({
                    "layer": group[0], "path": track, "track": True,
                    "sequence": False, "x": x, "y": y, "count": len(group),
                })
            else:
                for layer in group:
                    png = _layer_png(layer, out_w, out_h, layer_cache, fps=fps)
                    if png is None:
                        continue
                    prepared.append({
                        "layer": layer, "path": png, "track": False,
                        "sequence": False, "count": 1,
                    })
            index = last_index + 1
            continue
        layer = active[index]
        if _layer_is_sequence(layer):
            prepared_sequence = _layer_sequence(layer, out_w, out_h, layer_cache, fps)
            if prepared_sequence is not None:
                prepared.append({
                    "layer": layer, "path": prepared_sequence[0],
                    "track": False, "sequence": True, "count": 1,
                })
        else:
            png = _layer_png(layer, out_w, out_h, layer_cache, fps=fps)
            if png is not None:
                motion = layer.get("motion")
                prepared.append({
                    "layer": layer,
                    "path": _layer_canvas_png(layer, png, out_w, out_h) if motion else png,
                    "track": False, "sequence": False, "count": 1,
                    **({"motion": motion} if motion else {}),
                })
        index += 1
    if not prepared:
        return 0

    cmd = [_ffmpeg(), "-y", "-v", "error", "-i", str(video)]
    for entry in prepared:
        if entry["track"]:
            cmd += ["-f", "concat", "-safe", "0", "-i", str(entry["path"])]
        elif entry["sequence"]:
            cmd += [
                "-framerate", str(fps), "-start_number", "1",
                "-i", str(entry["path"]),
            ]
        elif entry.get("motion"):
            cmd += [
                "-loop", "1", "-framerate", str(fps),
                "-t", f"{int(entry['motion']['frames']) / fps:.6f}",
                "-i", str(entry["path"]),
            ]
        else:
            cmd += ["-loop", "1", "-framerate", str(fps), "-i", str(entry["path"])]
    graph: list[str] = []
    last = "0:v"
    for index, entry in enumerate(prepared, 1):
        layer = entry["layer"]
        out = f"v{index}"
        if entry["track"]:
            graph.append(
                f"[{last}][{index}:v]overlay=x={entry['x']}:y={entry['y']}:"
                f"eof_action=pass[{out}]"
            )
            last = out
            continue
        start = max(0.0, min(total, float(layer.get("start") or 0.0)))
        end = max(start + 0.01, min(total, float(layer.get("end") or 0.0)))
        x, y, _w, _h = _layer_place(layer, out_w, out_h)
        source = f"{index}:v"
        if entry["sequence"]:
            graph.append(
                f"[{index}:v]setpts=PTS-STARTPTS+{start:.3f}/TB[l{index}]"
            )
            source = f"l{index}"
        enable = f"between(t,{start:.3f},{end:.3f})"
        if layer.get("stuck"):
            enable = _stuck_enable(layer, fps)
        if entry.get("motion"):
            # The same filters as the beat, counting from the beat's first
            # frame, so the layer and the video move as one.
            motion = entry["motion"]
            first = int(round(float(motion["start"]) * fps))
            graph.append(
                f"[{index}:v]format=yuva444p,{','.join(motion['filters'])},"
                f"settb=1/{fps},setpts=PTS-STARTPTS+{first}[l{index}]"
            )
            source = f"l{index}"
            x = y = 0
        graph.append(
            f"[{last}][{source}]overlay=x={x}:y={y}:"
            f"enable='{enable}':eof_action=pass[{out}]"
        )
        last = out
    cmd += [
        "-filter_complex", ";".join(graph),
        "-map", f"[{last}]", "-an",
        *_encoder_args(encoder, quality),
        "-t", f"{total:.6f}",
        "-map_metadata", "-1",
        str(output),
    ]
    _run(cmd, timeout=_long_step(total, 900), cancel_event=cancel_event)
    return sum(int(entry["count"]) for entry in prepared)


def _burn_frame(
    frame: Path,
    layers: list[dict],
    output: Path,
    out_w: int,
    out_h: int,
    at: float,
    cache_dir: Path,
    fps: int = OUT_FPS,
    cancel_event: threading.Event | None = None,
) -> None:
    """Composite one frame's active layers and encode it as one JPEG."""
    active: list[tuple[dict, Path]] = []
    for layer in layers:
        start = float(layer.get("start") or 0.0)
        end = float(layer.get("end") or 0.0)
        if layer.get("stuck"):
            early = 0.25 / fps
            if not (start - early <= at < end - early):
                continue
        elif not (start <= at <= end):
            continue
        if _layer_is_sequence(layer):
            frames = _layer_frames(layer, fps)
            index = max(0, min(frames - 1, int((at - start) * fps)))
            png = _layer_png(
                layer, out_w, out_h, cache_dir,
                frame_index=index, frame_count=frames, fps=fps,
            )
        else:
            png = _layer_png(layer, out_w, out_h, cache_dir, fps=fps)
        if png is not None:
            active.append((layer, png))
    cmd = [_ffmpeg(), "-y", "-v", "error", "-i", str(frame)]
    graph: list[str] = []
    last = "0:v"
    for index, (layer, png) in enumerate(active, 1):
        x, y, _w, _h = _layer_place(layer, out_w, out_h)
        out = f"v{index}"
        motion = layer.get("motion")
        if motion:
            # The exact frame shows the beat's motion, so the layer must too.
            local = max(0, int(round((at - float(motion["start"])) * fps)))
            cmd += [
                "-loop", "1", "-framerate", str(fps), "-t", f"{(local + 1) / fps:.6f}",
                "-i", str(_layer_canvas_png(layer, png, out_w, out_h)),
            ]
            graph.append(
                f"[{index}:v]format=yuva444p,{','.join(motion['filters'])},"
                f"trim=start_frame={local},setpts=PTS-STARTPTS[l{index}]"
            )
            graph.append(f"[{last}][l{index}]overlay=x=0:y=0[{out}]")
        else:
            cmd += ["-loop", "1", "-framerate", str(fps), "-i", str(png)]
            graph.append(f"[{last}][{index}:v]overlay=x={x}:y={y}[{out}]")
        last = out
    if active:
        cmd += ["-filter_complex", ";".join(graph)]
    cmd += [
        "-map", f"[{last}]" if active else "0:v",
        "-frames:v", "1", "-q:v", "2",
        str(output),
    ]
    _run(cmd, timeout=120, cancel_event=cancel_event)


def _concat_file(path: Path) -> str:
    """One ``file`` line for the ffmpeg concat demuxer."""
    return str(path.resolve()).replace("'", "'\\''")


def _still_overlay_track(
    items: list[tuple[float, float, Path]],
    total: float,
    tmp: Path,
    size: tuple[int, int],
) -> Path | None:
    """One timed transparent PNG track for many static overlays.

    Every cue used to become its own looped input and its own ``overlay``
    filter. That chain composites every input into every frame, so 60 cues
    cost minutes for a 26 s story. A concat-demuxer track has one input and
    one overlay: each PNG lasts for its cue, and a transparent PNG fills the
    gaps. Returns ``None`` for overlapping cues, where one track cannot
    reproduce the stack; callers then keep the per-layer chain.
    """
    if len(items) < 2 or total <= 0:
        return None
    ordered = sorted(
        (max(0.0, float(start)), min(float(total), float(end)), path)
        for start, end, path in items
    )
    if any(end <= start + 1e-6 for start, end, _path in ordered):
        return None
    for previous, current in zip(ordered, ordered[1:]):
        if current[0] < previous[1] - 1e-6:
            return None

    blank = tmp / "overlay-blank.png"
    if not blank.is_file():
        Image.new("RGBA", size, (0, 0, 0, 0)).save(blank)
    lines: list[str] = []

    def add(path: Path, duration: float) -> None:
        if duration <= 0.0005:
            return
        lines.append(f"file '{_concat_file(path)}'")
        lines.append(f"duration {duration:.6f}")

    cursor = 0.0
    for start, end, path in ordered:
        if start > cursor + 0.0005:
            add(blank, start - cursor)
        add(path, end - start)
        cursor = max(cursor, end)
    if cursor < total - 0.0005:
        add(blank, total - cursor)
    if not lines:
        return None
    track = tmp / "overlay-track.txt"
    track.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return track


def _burn_captions(
    video: Path,
    cues: list[tuple[float, float, str]],
    output: Path,
    tmp: Path,
    out_w: int,
    out_h: int,
    total: float,
    quality: str,
    encoder: str,
    margin_fraction: float = 0.075,
    cancel_event: threading.Event | None = None,
    style: dict | None = None,
) -> None:
    pngs = _caption_pngs(tmp, cues, out_w, out_h, margin_fraction, style=style)
    if not pngs:
        return
    cmd = [_ffmpeg(), "-y", "-v", "error", "-i", str(video)]
    graph: list[str] = []
    if len(cues) >= 2:
        track = _still_overlay_track(
            [
                (float(start), float(end), png)
                for (start, end, _text), png in zip(cues, pngs)
            ],
            total, tmp, (out_w, out_h),
        )
        if track is not None:
            cmd += ["-f", "concat", "-safe", "0", "-i", str(track)]
            graph.append("[0:v][1:v]overlay=0:0:eof_action=pass[v1]")
            last = "v1"
        else:
            last = "0:v"
    else:
        last = "0:v"
    if not graph:
        for index, (start, end, _text) in enumerate(cues, 1):
            cmd += ["-loop", "1", "-i", str(pngs[index - 1])]
            out = f"v{index}"
            graph.append(
                f"[{last}][{index}:v]overlay=0:0:"
                f"enable='between(t,{start:.3f},{max(start + 0.2, end):.3f})'[{out}]"
            )
            last = out
    cmd += [
        "-filter_complex", ";".join(graph),
        "-map", f"[{last}]", "-an",
        *_encoder_args(encoder, quality),
        "-t", f"{total:.6f}",
        "-map_metadata", "-1",
        str(output),
    ]
    _run(cmd, timeout=_long_step(total, 900), cancel_event=cancel_event)


def _concat_video(
    tmp: Path,
    target_mp4: Path,
    segments: list[Path],
    quality: str,
    cancel_event: threading.Event | None = None,
    *,
    encoder: str = "libx264",
) -> None:
    """Join cached video segments without audio. Stays a copy when possible."""
    ffmpeg = _ffmpeg()
    list_path = tmp / "segments.txt"
    if not segments:
        raise PipelineError("No rendered segments to join.")
    list_path.write_text("".join(f"file '{segment.name}'\n" for segment in segments))
    base = [
        ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0",
        "-i", str(list_path),
    ]
    final = base + [
        "-map", "0:v:0", "-an", "-c:v", "copy",
        "-map_metadata", "-1",
        str(target_mp4),
    ]
    try:
        _run(final, timeout=max(600, 30 * len(segments)), cwd=tmp, cancel_event=cancel_event)
        return
    except RenderCancelled:
        raise
    except PipelineError:
        pass
    fallback = base + [
        "-map", "0:v:0", "-an",
        *_encoder_args(encoder, quality),
        "-map_metadata", "-1",
        str(target_mp4),
    ]
    _run(fallback, timeout=max(900, 120 * len(segments)), cwd=tmp, cancel_event=cancel_event)


def _mux(
    master: Path,
    audio_path: Path,
    output: Path,
    job_title: str,
    total: float,
    quality: str,
    normalize: bool,
    cancel_event: threading.Event | None = None,
    border: dict | None = None,
    *,
    encoder: str = "libx264",
) -> None:
    """Attach one audio bed to the cached video master. Video is copied
    unless a border needs a re-encode."""
    base = [
        _ffmpeg(), "-y", "-v", "error",
        "-i", str(master), "-i", str(audio_path),
    ]
    audio_filters = ["-af", "loudnorm=I=-14:TP=-1.5:LRA=11"] if normalize else []
    border_filter = ""
    if isinstance(border, dict):
        try:
            border_width = max(0, min(64, int(border.get("width") or 0)))
        except (TypeError, ValueError):
            border_width = 0
        if border_width:
            raw_color = str(border.get("color") or "#f1efe9").lstrip("#")
            color = f"0x{raw_color}" if len(raw_color) == 6 else "white"
            border_filter = (
                f"drawbox=x=0:y=0:w=iw:h=ih:"
                f"color={color}:t={border_width}"
            )
    if border_filter:
        final = []
    else:
        final = base + [
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy",
        *audio_filters,
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-t", f"{total:.6f}",
        "-movflags", "+faststart",
        "-map_metadata", "-1",
        "-metadata", f"title={job_title}",
        "-metadata", "comment=Made with VibeCut. Original vibe preserved.",
        str(output),
        ]
    if final:
        try:
            _run(final, timeout=_long_step(total, 900), cancel_event=cancel_event)
            return
        except RenderCancelled:
            raise
        except PipelineError:
            pass
    fallback = base + [
        "-map", "0:v:0", "-map", "1:a:0",
        *( ["-vf", border_filter] if border_filter else [] ),
        *_encoder_args(encoder, quality),
        *audio_filters,
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-t", f"{total:.6f}",
        "-movflags", "+faststart",
        "-metadata", f"title={job_title}",
        str(output),
    ]
    _run(fallback, timeout=_long_step(total, 1200), cancel_event=cancel_event)


def _caption_cache_signature(
    plan: dict,
    captions: bool,
    caption_style: dict | None = None,
    caption_margin: float = 0.075,
) -> str:
    """Identity for caption pixels, including style and legacy margin."""
    if not captions:
        return ""
    requested = caption_style or plan.get("_caption_style")
    if requested:
        style = caption_engine.normalize_style(requested)
    else:
        style = caption_engine.apply_margin(
            caption_engine.normalize_style({}), caption_margin,
        )
    track = plan.get("_caption_track") or {}
    if track.get("id"):
        base = str(track["id"])
    else:
        rows = caption_engine.cues_for_plan(
            plan,
            plan.get("clips") or [],
            plan.get("_scenes") or [],
            style=style,
            source_duration=plan.get("_source_duration"),
        )
        base = (
            caption_engine.cue_hash(rows)
            + ":"
            + caption_engine.style_hash(style)
        )
    return f"{base}:m{float(caption_margin):.4f}"


def _compiled_segment_at(compiled: dict, at: float) -> tuple[int, dict]:
    segments = compiled.get("segments") or []
    if not segments:
        raise PipelineError("This Edit has no segments to render.")
    for index, segment in enumerate(segments):
        start = float(segment.get("out_start") or 0.0)
        end = float(segment.get("out_end") or 0.0)
        if start <= at < end - 1e-9:
            return index, segment
    if at >= float(segments[-1].get("out_end") or 0.0) - 1e-9:
        raise PipelineError("Frame time is past the end of the story.")
    return 0, segments[0]


def _frame_cache_dir(job_dir: Path) -> Path:
    return job_dir.parent.parent / "cache" / "frames"


def _frame_cache_key(
    compiled: dict,
    frame: int,
    quality: str,
    out_w: int,
    out_h: int,
    meta: dict,
    encoder: str,
    fps: int = OUT_FPS,
) -> str:
    layers = [
        {
            "id": layer.get("id"),
            "raster": (layer.get("raster") or {}).get("hash"),
            "start": layer.get("start"),
            "end": layer.get("end"),
        }
        for layer in compiled.get("overlays") or []
    ]
    payload = {
        "edit": compiled.get("edit_hash") or compiled.get("edit_id"),
        "frame": int(frame),
        "quality": quality,
        "size": [out_w, out_h],
        "source": meta.get("fingerprint") or f"{meta.get('size')}:{meta.get('duration')}",
        "encoder": encoder,
        "layers": layers,
        "renderer": compose_render.SCHEMA_VERSION,
        "skin": LAYER_CACHE_VERSION,
    }
    return hashlib.sha1(
        json.dumps(payload, sort_keys=True).encode("utf-8"),
    ).hexdigest()[:24]


def render_story_frame(
    source: str,
    meta: dict,
    job_dir: Path,
    compiled: dict,
    at: float,
    quality: str = "draft",
    aspect: str | None = None,
    encoder: str | None = None,
    cancel_event: threading.Event | None = None,
    fps: int = OUT_FPS,
) -> bytes:
    """Render one frame through the same segment and layer graph as a reel."""
    quality = quality if quality in ("final", "720", "draft") else "final"
    aspect = aspect or compiled.get("aspect") or "9:16"
    aspect = aspect if aspect in ASPECTS else "9:16"
    out_w, out_h = _dims(aspect, quality)
    encoder = _choose_encoder(encoder)
    segments = list(compiled.get("segments") or [])
    total = float(segments[-1].get("out_end") or 0.0) if segments else 0.0
    fps = int(fps) if int(fps) in (24, 30, 60) else OUT_FPS
    last_frame = max(0, int(round(total * fps)) - 1)
    frame = max(0, int(round(float(at) * fps)))
    frame = min(frame, last_frame)
    time_at = frame / fps
    index, segment = _compiled_segment_at(compiled, time_at)
    cache_dir = _frame_cache_dir(job_dir)
    key = _frame_cache_key(compiled, frame, quality, out_w, out_h, meta, encoder, fps)
    cached = cache_dir / f"{key}.jpg"
    if cached.is_file() and cached.stat().st_size > 0:
        return cached.read_bytes()

    tmp = job_dir / "renders" / f"tmp_frame_{uuid.uuid4().hex}"
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        if segment.get("blank"):
            from PIL import ImageColor
            frame_png = tmp / "frame.png"
            Image.new(
                "RGB", (out_w, out_h),
                ImageColor.getrgb(str(segment.get("blank_color") or "#000000")),
            ).save(frame_png)
            frame_jpg = tmp / "frame.jpg"
            _burn_frame(
                frame_png,
                compiled.get("overlays") or [],
                frame_jpg,
                out_w, out_h,
                time_at,
                job_dir.parent.parent / "cache" / "layers",
                cancel_event=cancel_event,
            )
            return frame_jpg.read_bytes()
        segment_path = tmp / "segment.mp4"
        frames = int(segment.get("frames") or 0)
        segment_frames = max(1, frames)
        frame_source, frame_meta = _clip_media(job_dir, segment, source, meta)
        _segment(
            frame_source, frame_meta, {},
            float(segment.get("start") or 0.0),
            segment_frames / OUT_FPS, segment_frames,
            segment_path,
            index == 0, index == len(compiled.get("segments") or []) - 1,
            out_w, out_h, quality, encoder,
            job_dir.parent.parent / "cache" / "segments",
            crop=dict(segment.get("crop") or {}),
            crop_path=None,
            cancel_event=cancel_event,
            pre_filters=segment.get("pre_filters") or [],
            post_filters=segment.get("post_filters") or [],
            reverse=bool(segment.get("reverse")),
            freeze=bool(segment.get("freeze")),
            fps=fps,
        )
        local = max(0, min(
            segment_frames - 1,
            frame - int(round(float(segment.get("out_start") or 0.0) * OUT_FPS)),
        ))
        frame_png = tmp / "frame.png"
        _run([
            _ffmpeg(), "-y", "-v", "error",
            "-i", str(segment_path),
            "-vf", f"select=eq(n\\,{local})",
            "-frames:v", "1",
            str(frame_png),
        ], timeout=60, cancel_event=cancel_event)
        frame_jpg = tmp / "frame.jpg"
        _burn_frame(
            frame_png,
            compiled.get("overlays") or [],
            frame_jpg,
            out_w, out_h,
            time_at,
            job_dir.parent.parent / "cache" / "layers",
            cancel_event=cancel_event,
        )
        payload = frame_jpg.read_bytes()
        cache_dir.mkdir(parents=True, exist_ok=True)
        part = cache_dir / f".{key}.{uuid.uuid4().hex}.tmp"
        part.write_bytes(payload)
        os.replace(part, cached)
        return payload
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


WHOLE_PROXY_LONG_EDGE = 1280


def _whole_proxy_size(meta: dict) -> tuple[int, int]:
    """The source's own shape, even-sized, with no upscale."""
    width = max(2, int(meta.get("width") or 1920))
    height = max(2, int(meta.get("height") or 1080))
    scale = min(1.0, WHOLE_PROXY_LONG_EDGE / max(width, height))
    return (
        max(2, int(round(width * scale / 2.0)) * 2),
        max(2, int(round(height * scale / 2.0)) * 2),
    )


def build_story_proxy(
    source: str,
    meta: dict,
    job_dir: Path,
    clips: list[dict],
    scenes: list[dict] | None = None,
    aspect: str = "9:16",
    encoder: str | None = None,
    cancel_event: threading.Event | None = None,
    whole: bool = False,
) -> Path:
    """Build (or reuse) the 540-wide proxy for one story range.

    ``whole`` keeps every clip's full picture instead of the scene crop, so the
    preview can pan and zoom out without a rebuild. All clips share one size for
    the concat. The preview maps each clip back through its own fractions, so a
    file clip of another shape comes out with its true proportions.
    """
    aspect = aspect if aspect in ASPECTS else "9:16"
    out_w, out_h = _whole_proxy_size(meta) if whole else _dims(aspect, "draft")
    digest = edits.clip_snapshot_hash(clips)
    proxies = job_dir / "proxies"
    target = proxies / (
        f"{digest}_whole_{out_w}x{out_h}.mp4"
        if whole
        else f"{digest}_{aspect.replace(':', 'x')}_{out_w}x{out_h}.mp4"
    )
    if target.is_file() and target.stat().st_size > 1024:
        return target
    encoder = _choose_encoder(encoder)
    scene_map = {
        str(scene.get("id")): scene
        for scene in (scenes or [])
        if isinstance(scene, dict) and scene.get("id") is not None
    }
    prepared = prepare_render({"clips": list(clips)}, meta, None)
    proxy_clips = prepared["clips"]
    total = float(prepared["total"])
    tmp = proxies / f".tmp_{uuid.uuid4().hex}"
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        segments: list[Path] = []
        for index, clip in enumerate(proxy_clips):
            segment_path = tmp / f"{index:03d}.mp4"
            scene = scene_map.get(str(clip.get("scene"))) or {}
            clip_source, clip_meta = _clip_media(job_dir, clip, source, meta)
            crop = (
                {
                    "x": 0, "y": 0,
                    "w": int(clip_meta.get("width") or meta["width"]),
                    "h": int(clip_meta.get("height") or meta["height"]),
                }
                if whole
                else _scene_crop(scene, aspect, clip_meta, out_w, out_h)
            )
            _segment(
                clip_source, clip_meta, scene,
                float(clip["start"]), float(clip["duration"]), int(clip["frames"]),
                segment_path, False, False,
                out_w, out_h, "draft", encoder,
                job_dir.parent.parent / "cache" / "segments",
                crop=crop,
                cancel_event=cancel_event,
            )
            segments.append(segment_path)
        master = tmp / "master.mp4"
        _concat_video(tmp, master, segments, "draft", cancel_event, encoder=encoder)
        audio_path = tmp / "audio.wav"
        _audio_track(
            source, meta, proxy_clips, audio_path, total, cancel_event,
            job_dir=job_dir,
        )
        output = tmp / "proxy.mp4"
        _mux(
            master, audio_path, output, "Story proxy", total, "draft",
            False, cancel_event, encoder=encoder,
        )
        proxies.mkdir(parents=True, exist_ok=True)
        os.replace(output, target)
        return target
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def edit_beat_grid(
    job_dir: Path,
    edit: dict | None,
    audio_plan: dict | None = None,
) -> dict | None:
    """Beat grid for an Edit whose layers already sit on the locked bed.

    Only a locked (content-hashed) bed is considered. The grid is returned
    when at least one motion or graphic boundary is already within the snap
    window of a beat; unsnapped edits keep their stored times. Nothing here
    mixes audio or changes the Edit itself.
    """
    if not isinstance(edit, dict):
        return None
    layers = [
        layer
        for key in ("motion", "graphics")
        for layer in (edit.get(key) or [])
        if isinstance(layer, dict)
    ]
    if not layers:
        return None
    plan = audio_plan if isinstance(audio_plan, dict) else audio.plan_from_edit(
        edit.get("audio"),
    )
    if not isinstance(plan, dict) or audio.mixer_mode(plan.get("mode")) == "keep":
        return None
    music_plan = plan.get("music") if isinstance(plan.get("music"), dict) else {}
    locked = str(
        music_plan.get("locked_hash") or music_plan.get("file_hash") or "",
    ).strip().lower()
    track = audio.resolve_locked_track(job_dir, locked) if locked else None
    if track is None:
        track = audio.resolve_music_track([], [], music_plan)
    if track is None:
        return None
    grid = audio.beat_grid(track)
    beats = fx.beat_times(grid)
    if not beats:
        return None
    boundaries = [
        float(layer.get(key))
        for layer in layers
        for key in ("start", "end")
        if isinstance(layer.get(key), (int, float))
    ]
    if not any(
        abs(boundary - beat) <= fx.BEAT_WINDOW + 1e-6
        for boundary in boundaries
        for beat in beats
    ):
        return None
    return grid


def _prepare_fills(
    source: str,
    meta: dict,
    job_dir: Path,
    segments: list[dict],
    progress: Callable[[float, str], None],
    cancel_event: threading.Event | None,
    fps: int = OUT_FPS,
) -> list[dict | None]:
    """Run the AI text fill pre-pass: one filled clip per beat that needs it.

    Progress runs from 0.02 to 0.45. Clips are cached by source, span, layers,
    engine and model, so a draft and the final share them.
    """
    planned = [
        (index, segment) for index, segment in enumerate(segments)
        if segment.get("fill")
    ]
    results: list[dict | None] = [None] * len(segments)
    if not planned:
        return results
    data_root = job_dir.parent.parent
    started = time.monotonic()
    # Frames still to run. A beat found in the cache comes off this total.
    work_left = sum(int(segment["frames"]) for _index, segment in planned)
    work_done = 0
    try:
        for position, (index, segment) in enumerate(planned):
            plan = segment["fill"]
            low = 0.02 + 0.43 * position / len(planned)
            high = 0.02 + 0.43 * (position + 1) / len(planned)
            beat_frames = int(segment["frames"])

            def report(
                fraction: float,
                message: str,
                low=low,
                high=high,
                beat_frames=beat_frames,
            ) -> None:
                done = work_done + beat_frames * max(0.0, min(1.0, fraction))
                remaining = ""
                elapsed = time.monotonic() - started
                if done >= 10 and elapsed >= 20 and work_left > done:
                    remaining = (
                        f" · {textfill.duration_text(elapsed / done * (work_left - done))} left"
                    )
                progress(
                    low + (high - low) * max(0.0, min(1.0, fraction)),
                    f"Filling text, beat {position + 1}/{len(planned)} · {message}{remaining}",
                )

            try:
                results[index] = textfill.prepare_span(
                    source=source,
                    meta=meta,
                    start=float(segment["start"]),
                    duration=int(segment["frames"]) / fps,
                    layers=plan.get("layers") or [],
                    method=plan.get("method") or textfill.DEFAULT_METHOD,
                    cache_dir=job_dir / "fill",
                    data_root=data_root,
                    ffmpeg=_ffmpeg(),
                    progress=report,
                    cancel_event=cancel_event,
                )
            except textfill.FillCancelled as exc:
                raise RenderCancelled("Render cancelled.") from exc
            except textfill.FillError as exc:
                raise PipelineError(str(exc)) from exc
            if results[index] is None or results[index].get("cached"):
                work_left -= beat_frames
            else:
                work_done += beat_frames
    finally:
        # Model sessions are large; a finished or failed pre-pass must not
        # hold STTN or LaMa memory for the rest of the app's life.
        textfill.release_fillers()
    return results


def render_reel(
    source: str,
    meta: dict,
    job_dir: Path,
    plan: dict,
    job_title: str,
    progress: Callable[[float, str], None],
    quality: str = "final",
    aspect: str = "9:16",
    encoder: str | None = None,
    captions: bool = False,
    audio_plan: dict | None = None,
    audio_sig: str = "",
    caption_margin: float = 0.075,
    cancel_event: threading.Event | None = None,
    caption_cues: list[tuple[float, float, str]] | None = None,
    render_clips: list[dict] | None = None,
    render_total: float | None = None,
    caption_style: dict | None = None,
    edit: dict | None = None,
    compiled_edit: dict | None = None,
    output_size: tuple[int, int] | None = None,
) -> dict:
    render_started = time.monotonic()
    timings: dict[str, float] = {
        name: 0.0 for name in (
            "fill", "segments", "concat", "layers", "captions",
            "audio", "mux", "poster",
        )
    }
    quality = quality if quality in ("final", "720", "draft") else "final"
    aspect = aspect if aspect in ASPECTS else "9:16"
    out_w, out_h = _dims(aspect, quality)
    if output_size is None and isinstance(edit, dict) and isinstance(edit.get("output"), dict):
        output_size = (edit["output"].get("width"), edit["output"].get("height"))
    output_fps = 30
    if isinstance(edit, dict) and isinstance(edit.get("output"), dict):
        try:
            requested_fps = int(edit["output"].get("fps") or 30)
        except (TypeError, ValueError):
            requested_fps = 30
        if requested_fps in (24, 30, 60):
            output_fps = requested_fps
    if output_size:
        try:
            width, height = int(output_size[0]), int(output_size[1])
        except (TypeError, ValueError, IndexError):
            width = height = 0
        if width >= 240 and height >= 240 and width % 2 == 0 and height % 2 == 0:
            out_w, out_h = width, height
    encoder = _choose_encoder(encoder)
    target = int(plan["target"])
    suffix = ""
    if quality != "final":
        suffix += f"_{quality}"
    if aspect != "9:16":
        suffix += f"_{aspect.replace(':', 'x')}"
    default_w, default_h = _dims(aspect, quality)
    if (out_w, out_h) != (default_w, default_h):
        suffix += f"_{out_w}x{out_h}"
    if audio_plan and str(audio_plan.get("mode") or "keep") != "keep":
        audio_sig = audio_sig or audio.signature(audio_plan)
        if audio_sig:
            suffix += f"_{audio_sig}"

    renders_dir = job_dir / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)
    out = renders_dir / f"reel_{target}{suffix}.mp4"
    poster = renders_dir / f"reel_{target}{suffix}.jpg"
    tmp = renders_dir / f"tmp_{target}{suffix}"
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    out_tmp = tmp / f"reel_{target}{suffix}.mp4"
    poster_tmp = tmp / f"reel_{target}{suffix}.jpg"
    cache_dir = job_dir.parent.parent / "cache" / "segments"

    scenes = {scene["id"]: scene for scene in plan.get("_scenes", [])}
    scene_list = plan.get("_scenes", [])
    compiled = compiled_edit
    if compiled is None and edit is not None:
        compiled = compose_render.compile_edit(
            edit,
            clips=plan.get("clips") or [],
            source=meta,
            scenes=scene_list,
            caption_track=plan.get("_caption_track"),
            size=(out_w, out_h),
            motion_engine=compose_render.EDIT_MOTION_ENGINE,
            beats=edit_beat_grid(job_dir, edit, audio_plan),
            fps=output_fps,
        )
    edit_segments: list[dict] = []
    layers: list[dict] = []
    if compiled is not None:
        edit_segments = list(compiled.get("segments") or [])
        layers = list(compiled.get("overlays") or [])
        clips = [
            {
                "kind": segment.get("kind") or "scene",
                "scene": segment.get("scene"),
                "role": segment.get("role") or "beat",
                "start": float(segment["start"]),
                "frames": int(segment["frames"]),
                "duration": int(segment["frames"]) / output_fps,
                "reverse": bool(segment.get("reverse")),
                "freeze": bool(segment.get("freeze")),
                **({"file": segment["file"], "asset": segment.get("asset")} if segment.get("file") else {}),
            }
            for segment in edit_segments
        ]
        total = sum(float(clip["duration"]) for clip in clips)
    elif render_clips is None:
        prepared = prepare_render(plan, meta, audio_plan)
        clips = prepared["clips"]
        total = prepared["total"]
    else:
        clips = [dict(clip) for clip in render_clips]
        total = (
            float(render_total)
            if render_total is not None
            else sum(float(clip.get("duration") or 0.0) for clip in clips)
        )
    plan["_source_duration"] = float(meta.get("duration") or 0)

    if cancel_event is not None and cancel_event.is_set():
        raise RenderCancelled("Render cancelled.")

    effective_style: dict | None = None
    if compiled is not None:
        cues = []
        caption_count = sum(
            1 for layer in layers if layer.get("type") == "caption"
        )
        caption_sig = str(compiled.get("edit_hash") or "")
    else:
        if (
            captions
            and not plan.get("_caption_cues")
            and not plan.get("_transcript_segments")
        ):
            plan["_transcript_segments"] = caption_engine.read_transcript_segments(job_dir)
        requested_style = caption_style or plan.get("_caption_style")
        if requested_style:
            effective_style = caption_engine.normalize_style(requested_style)
        else:
            effective_style = caption_engine.apply_margin(
                caption_engine.normalize_style({}), caption_margin,
            )
        caption_sig = _caption_cache_signature(
            plan, captions, effective_style, caption_margin,
        )
        cues = list(caption_cues) if caption_cues is not None else _caption_cues(plan, clips)
        caption_count = len(cues)

    master_dir = job_dir.parent.parent / "cache" / "masters" / job_dir.name
    layer_sig = (
        hashlib.sha1(json.dumps([
            {
                "id": layer.get("id"),
                "hash": (layer.get("raster") or {}).get("hash"),
                "start": round(float(layer.get("start") or 0.0), 3),
                "end": round(float(layer.get("end") or 0.0), 3),
            }
            for layer in layers
        ], sort_keys=True).encode()).hexdigest()[:16]
        if layers else ""
    )
    fill_methods = sorted({
        str((segment.get("fill") or {}).get("method") or "")
        for segment in edit_segments
        if (segment.get("fill") or {}).get("method")
    })
    fill_sig = (
        textfill.model_signature(fill_methods, textfill.models_dir(job_dir.parent.parent))
        if fill_methods else ""
    )
    master_key = hashlib.sha1(json.dumps({
        "target": target,
        "clips": [
            {"scene": clip["scene"], "start": round(clip["start"], 3), "frames": clip["frames"]}
            for clip in clips
        ],
        "quality": quality,
        "aspect": aspect,
        "captions": bool(captions),
        "caption_cues": [
            [round(start, 3), round(end, 3), text]
            for start, end, text in cues
        ] if captions else [],
        "caption_sig": caption_sig,
        "caption_margin": round(float(caption_margin), 4) if captions else 0,
        "encoder": encoder,
        "edit": compiled.get("edit_hash") if compiled is not None else None,
        "layers": layer_sig,
        # Fill model files: replacing a checkpoint must not reuse a master
        # whose beats were built from the old model.
        "fill_models": fill_sig,
        # Text raster version: a font change must not reuse an old master.
        "text_skin": LAYER_CACHE_VERSION,
    }, sort_keys=True).encode()).hexdigest()[:16]
    master = master_dir / f"{master_key}.mp4"
    cached_count = 0
    layer_count = 0
    try:
        if not master.is_file() or master.stat().st_size < 1024:
            workers = max(1, min(
                int(os.environ.get("VIBECUT_RENDER_WORKERS", "4")),
                os.cpu_count() or 2,
                len(clips),
            ))
            # Software AV1 decode is frame-threaded. Give each beat worker a
            # slice of the cores; otherwise four workers spawn four full
            # thread sets and thrash.
            decode_threads = None
            if str(meta.get("codec") or "").lower() in SOFTWARE_AV1:
                mode = (os.environ.get("VIBECUT_DECODER") or "auto").lower()
                if mode not in ("vt", "videotoolbox"):
                    decode_threads = max(
                        1, (os.cpu_count() or workers) // max(1, workers),
                    )
            progress(0.01, f"Preparing {len(clips)} beats · {quality} · {encoder}")
            with _stage(timings, "fill"):
                fills = _prepare_fills(
                    source, meta, job_dir, edit_segments if compiled is not None else [],
                    progress, cancel_event,
                )
            cut_from = 0.45 if any(fills) else 0.02
            done = 0
            segments: list[Path] = []
            segments_started = time.monotonic()
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="vibecut-seg") as pool:
                futures = {}
                for index, clip in enumerate(clips):
                    scene = scenes.get(clip["scene"]) or {}
                    compiled_segment = (
                        edit_segments[index] if compiled is not None else None
                    )
                    if compiled_segment is None and not scene:
                        raise PipelineError(f"Plan references missing scene {clip['scene']}.")
                    segment = tmp / f"{index:03d}.mp4"
                    segments.append(segment)
                    if compiled_segment is not None:
                        crop = dict(compiled_segment.get("crop") or {})
                        crop_path = None
                        pre_filters = list(compiled_segment.get("pre_filters") or [])
                        post_filters = list(compiled_segment.get("post_filters") or [])
                    else:
                        crop = _scene_crop(scene, aspect, meta, out_w, out_h)
                        crop_path = _crop_path_for(scene, aspect, clip)
                        pre_filters = []
                        post_filters = []
                    clip_source, clip_meta = _clip_media(
                        job_dir, compiled_segment or clip, source, meta,
                    )
                    if compiled_segment is not None and compiled_segment.get("blank"):
                        futures[pool.submit(
                            _blank_segment,
                            segment,
                            int(compiled_segment.get("frames") or clip["frames"]),
                            out_w, out_h, quality, encoder,
                            str(compiled_segment.get("blank_color") or "#000000"),
                            cancel_event,
                            output_fps,
                        )] = index
                        continue
                    futures[pool.submit(
                        _segment,
                        clip_source, clip_meta, scene,
                        clip["start"], clip["duration"], clip["frames"],
                        segment, index == 0, index == len(clips) - 1,
                        out_w, out_h, quality, encoder, cache_dir, crop, crop_path, cancel_event,
                        pre_filters, post_filters, decode_threads,
                        fills[index] if index < len(fills) else None,
                        reverse=bool(clip.get("reverse")),
                        freeze=bool(clip.get("freeze")),
                        fps=output_fps,
                    )] = index
                for future in as_completed(futures):
                    if cancel_event is not None and cancel_event.is_set():
                        for pending in futures:
                            pending.cancel()
                        raise RenderCancelled("Render cancelled.")
                    if future.result():
                        cached_count += 1
                    done += 1
                    progress(
                        cut_from + (0.80 - cut_from) * (done / max(1, len(clips))),
                        f"Cutting beat {done} / {len(clips)}"
                        + (f" · {cached_count} cached" if cached_count else ""),
                    )
            timings["segments"] = round(time.monotonic() - segments_started, 3)
            progress(0.82, "Joining the cut")
            master_tmp = tmp / "master.mp4"
            with _stage(timings, "concat"):
                _concat_video(tmp, master_tmp, segments, quality, cancel_event, encoder=encoder)
            if layers:
                progress(0.87, "Burning layers")
                layered = tmp / "layers.mp4"
                with _stage(timings, "layers"):
                    layer_count = _burn_layers(
                        master_tmp, layers, layered, tmp, out_w, out_h, total,
                        quality, encoder,
                        cache_dir=job_dir.parent.parent / "cache" / "layers",
                        cancel_event=cancel_event,
                    )
                if layer_count:
                    os.replace(layered, master_tmp)
            elif captions and cues:
                progress(0.87, "Burning captions")
                captioned = tmp / "captioned.mp4"
                with _stage(timings, "captions"):
                    _burn_captions(
                        master_tmp, cues, captioned, tmp, out_w, out_h, total,
                        quality, encoder, caption_margin, cancel_event,
                        style=effective_style,
                    )
                os.replace(captioned, master_tmp)
            master_dir.mkdir(parents=True, exist_ok=True)
            os.replace(master_tmp, master)
        else:
            progress(0.40, "Video master cached")
            layer_count = len(layers)

        audio_path = tmp / "audio.wav"
        audio_info: dict = {"mode": "keep"}
        bed: Path | None = None
        audio_started = time.monotonic()
        if audio_plan and str(audio_plan.get("mode") or "keep") != "keep":
            progress(0.90, "Building the new audio")
            try:
                bed = audio.build_bed(
                    source, meta, plan, clips, scene_list, job_dir, audio_plan,
                    total, tmp, progress,
                    source_lang=str(plan.get("_source_lang") or "en"),
                    cancel_event=cancel_event,
                )
            except audio.AudioError as exc:
                if cancel_event is not None and cancel_event.is_set():
                    raise RenderCancelled("Render cancelled.") from exc
                raise PipelineError(str(exc)) from exc
            audio_info = {
                "mode": audio_plan.get("mode"),
                "voice_engine": (audio_plan.get("voice") or {}).get("engine"),
                "voice": (audio_plan.get("voice") or {}).get("voice"),
                "music": (audio_plan.get("music") or {}).get("source"),
                "translate": (audio_plan.get("translate") or {}).get("target"),
            }
            if audio_plan.get("_warnings"):
                audio_info["warnings"] = list(audio_plan["_warnings"])
        if bed is None:
            progress(0.90, "Building the original audio bed")
            _audio_track(
                source, meta, clips, audio_path, total, cancel_event,
                fade=(audio_plan or {}).get("fade"), job_dir=job_dir,
            )
        else:
            audio_path = bed
        timings["audio"] = round(time.monotonic() - audio_started, 3)

        progress(0.95, "Muxing audio")
        with _stage(timings, "mux"):
            _mux(
                master, audio_path, out_tmp, job_title, total, quality,
                not (audio_plan and str(audio_plan.get("mode") or "keep") != "keep"),
                cancel_event,
                border=(edit or {}).get("border"),
                encoder=encoder,
            )

        info = probe(out_tmp)
        poster_fresh = (
            poster.is_file()
            and poster.stat().st_size > 0
            and poster.stat().st_mtime >= master.stat().st_mtime
        )
        if poster_fresh:
            timings["poster"] = 0.0
        else:
            with _stage(timings, "poster"):
                seek = min(0.25, max(0.0, info["duration"] / 2))
                _run([
                    _ffmpeg(), "-y", "-v", "error", "-ss", f"{seek:.3f}", "-i", str(out_tmp),
                    "-frames:v", "1", "-vf", "scale=540:-2", "-q:v", "3", str(poster_tmp),
                ], timeout=60, cancel_event=cancel_event)
                os.replace(poster_tmp, poster)

        os.replace(out_tmp, out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    progress(1.0, "Reel ready")
    timings["total"] = round(time.monotonic() - render_started, 3)
    LOGGER.info("render timings %s", timings)
    return {
        "target": target,
        "duration": info["duration"],
        "width": info["width"],
        "height": info["height"],
        "fps": output_fps,
        "size": info["size"],
        "has_audio": info["has_audio"],
        "path": out.name,
        "poster": poster.name,
        "clip_count": len(clips),
        "quality": quality,
        "aspect": aspect,
        "encoder": encoder,
        "captions": bool(captions) or bool(caption_count),
        "caption_count": caption_count,
        "layers": len(layers),
        "layer_count": layer_count,
        "edit_hash": compiled.get("edit_hash") if compiled is not None else None,
        "cached": cached_count,
        "timings": timings,
        "beat_bpm": None if not audio_plan else audio_plan.get("_beat_bpm"),
        "beat_drift": None if not audio_plan else audio_plan.get("_beat_drift"),
        "used_assets": (audio_plan or {}).get("_used_assets") or [],
        **audio_info,
    }
