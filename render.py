"""Turn a cut plan into a vertical H.264 reel.

The renderer is deliberately boring: every beat is cut as its own segment,
then the segments are joined with the concat demuxer. That keeps frame
boundaries exact and lets us cache and parallelize the expensive part.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFont

import audio
import captions as caption_engine
import compose_render
import edits
from compose_render import path_expression as _path_expression
from compose_render import path_value as _path_value
from pipeline import PipelineError, crop_center, probe

TARGET_AR = 9 / 16
OUT_W = 1080
OUT_H = 1920
OUT_FPS = 30
LAYER_CACHE_VERSION = "layers-v1"

PRESETS = {
    "tiktok": {"aspect": "9:16", "captions": True, "caption_margin": 0.12},
    "reels": {"aspect": "9:16", "captions": True, "caption_margin": 0.10},
    "shorts": {"aspect": "9:16", "captions": True, "caption_margin": 0.09},
    "square": {"aspect": "1:1", "captions": True, "caption_margin": 0.08},
    "landscape": {"aspect": "16:9", "captions": False, "caption_margin": 0.07},
}

ASPECTS = {
    "9:16": ((1080, 1920), (540, 960)),
    "4:5": ((1080, 1350), (540, 676)),
    "1:1": ((1080, 1080), (540, 540)),
    "16:9": ((1920, 1080), (960, 540)),
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
    final, draft = ASPECTS.get(aspect, ASPECTS["9:16"])
    return final if quality == "final" else draft


def _choose_encoder(requested: str | None = None) -> str:
    value = (requested or os.environ.get("VIBECUT_ENCODER") or "auto").lower()
    if value in ("libx264", "x264"):
        return "libx264"
    if value in ("videotoolbox", "vt"):
        return "videotoolbox"
    if value == "auto":
        return "videotoolbox" if sys.platform == "darwin" else "libx264"
    return "libx264"


def _encoder_args(encoder: str, quality: str) -> list[str]:
    if encoder == "videotoolbox":
        bitrate = "10M" if quality == "final" else "3M"
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
        "-preset", "veryfast" if quality == "final" else "ultrafast",
        "-crf", "18" if quality == "final" else "23",
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

    filters.extend([
        f"scale={out_w}:{out_h}:flags=lanczos",
        "setsar=1",
        f"fps={OUT_FPS}",
        "format=yuv420p",
    ])
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
    }
    pre_hash = _filters_hash(pre_filters)
    post_hash = _filters_hash(post_filters)
    if pre_hash:
        payload["pre_filters"] = pre_hash
    if post_hash:
        payload["post_filters"] = post_hash
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:20]


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
) -> bool:
    """Render one beat. Return True when the segment came from cache."""
    key = _segment_cache_key(
        meta, scene, start, frames, out_w, out_h, quality, encoder, first, last,
        crop, crop_path, pre_filters, post_filters,
    )
    cached = cache_dir / f"{key}.mp4"
    if cached.exists() and cached.stat().st_size > 0:
        _link_or_copy(cached, output)
        return True

    ffmpeg = _ffmpeg()
    parts: list[str] = []
    if pre_filters:
        parts.append(",".join(str(item) for item in pre_filters))
    parts.append(_crop_filter(
        meta, crop or scene.get("crop") or {"cx": 0.5, "cy": 0.5},
        out_w, out_h, crop_path=crop_path, duration=duration,
    ))
    if post_filters:
        parts.append(",".join(str(item) for item in post_filters))
    vf = ",".join(part for part in parts if part)

    if first and duration > 0.4:
        vf += ",fade=t=in:st=0:d=0.12"
    if last and duration > 0.6:
        vf += f",fade=t=out:st={max(0.0, duration - 0.4):.3f}:d=0.4"

    part = output.parent / f".{output.stem}.part.mp4"
    if part.exists():
        part.unlink()
    cmd = [
        ffmpeg, "-y", "-v", "error",
        "-ss", f"{start:.3f}", "-t", f"{duration:.6f}", "-i", source,
        "-frames:v", str(frames),
        "-vf", vf,
        "-an",
        *_encoder_args(encoder, quality),
        "-movflags", "+faststart",
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


def _audio_track(
    source: str,
    meta: dict,
    clips: list[dict],
    output: Path,
    total: float,
    cancel_event: threading.Event | None = None,
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

    cmd = [ffmpeg, "-y", "-v", "error"]
    for clip in clips:
        cmd += [
            "-ss", f"{float(clip['start']):.6f}",
            "-t", f"{float(clip['duration']):.6f}",
            "-i", source,
        ]

    graph: list[str] = []
    for index, clip in enumerate(clips):
        duration = float(clip["duration"])
        branch = (
            f"[{index}:a]aresample=48000,"
            f"atrim=start=0:end={duration:.6f},"
            f"asetpts=PTS-STARTPTS"
        )
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
    _run(cmd, timeout=900, cancel_event=cancel_event)


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


def _wrap_caption(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    if not text:
        return []
    lines: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = char
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
    font = _caption_font(font_size, style.get("font"))
    widest = max(
        measure.textlength(line, font=font)
        for _start, _end, lines in prepared
        for line in lines
    )
    if widest > max_width:
        fitted_size = max(12, int(font_size * max_width / max(1.0, widest)) - 1)
        if fitted_size < font_size:
            font_size = fitted_size
            font = _caption_font(font_size, style.get("font"))
            widest = max(
                measure.textlength(line, font=font)
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
            draw.text(
                (x, y), line, font=font, anchor="ma",
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
    x, y, w, h = _layer_rect(layer, out_w, out_h)
    image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    style = layer.get("style") or {}
    text = str(layer.get("text") or "")
    if style.get("uppercase"):
        text = text.upper()
    if not text.strip():
        return image
    size = _layer_font_size(style, out_h)
    font = _caption_font(size, style.get("font"))
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    lines: list[str] = []
    while size >= 10:
        lines = _wrap_caption(measure, text, font, max(8, w - 8))
        if not lines:
            break
        widest = max(measure.textlength(line, font=font) for line in lines)
        line_height = max(1, int(size * 1.18))
        if widest <= max(8, w - 8) and line_height * len(lines) <= h:
            break
        size -= 2
        font = _caption_font(size, style.get("font"))
    if not lines:
        return image

    fill = _rgba(str(style.get("color") or "#ffffff"), int(round(float(layer.get("opacity", 1.0)) * 255)))
    background = str(style.get("background") or "none")
    if background not in {"none", "", "None"}:
        plate = _rgba(background, int(round(float(layer.get("opacity", 1.0)) * 255)))
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
        stroke_fill = _rgba(str(stroke_value), int(round(float(layer.get("opacity", 1.0)) * 255)))
        stroke_width = max(1, int(round(size * 0.055)))
    line_height = max(1, int(size * 1.18))
    total_height = line_height * len(lines)
    top = max(0, (h - total_height) // 2)
    if style.get("shadow"):
        shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        offset = max(1, int(round(size * 0.06)))
        for index, line in enumerate(lines):
            anchor = {"left": "la", "right": "ra"}.get(str(style.get("align") or "center"), "ma")
            px = {"left": 4, "right": w - 4}.get(str(style.get("align") or "center"), w // 2)
            shadow_draw.text(
                (px + offset, top + index * line_height + offset),
                line, font=font, anchor=anchor,
                fill=(0, 0, 0, int(150 * float(layer.get("opacity", 1.0)))),
                stroke_width=stroke_width, stroke_fill=(0, 0, 0, 150),
            )
        image = Image.alpha_composite(image, shadow)
        draw = ImageDraw.Draw(image)
    for index, line in enumerate(lines):
        anchor = {"left": "la", "right": "ra"}.get(str(style.get("align") or "center"), "ma")
        px = {"left": 4, "right": w - 4}.get(str(style.get("align") or "center"), w // 2)
        draw.text(
            (px, top + index * line_height),
            line, font=font, anchor=anchor,
            fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill,
        )
    return image


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
    prepared: list[tuple[dict, Path]] = []
    layer_cache = cache_dir or (tmp / "layers")
    for layer in layers:
        start = float(layer.get("start") or 0.0)
        end = float(layer.get("end") or 0.0)
        if end <= start + 1e-6:
            continue
        if start >= total - 1e-6:
            continue
        if _layer_is_sequence(layer):
            prepared_sequence = _layer_sequence(layer, out_w, out_h, layer_cache, fps)
            if prepared_sequence is None:
                continue
            prepared.append((layer, prepared_sequence[0]))
        else:
            png = _layer_png(layer, out_w, out_h, layer_cache, fps=fps)
            if png is None:
                continue
            prepared.append((layer, png))
    if not prepared:
        return 0

    cmd = [_ffmpeg(), "-y", "-v", "error", "-i", str(video)]
    for layer, path in prepared:
        if _layer_is_sequence(layer):
            cmd += [
                "-framerate", str(fps), "-start_number", "1",
                "-i", str(path),
            ]
        else:
            cmd += ["-loop", "1", "-framerate", str(fps), "-i", str(path)]
    graph: list[str] = []
    last = "0:v"
    for index, (layer, _path) in enumerate(prepared, 1):
        start = max(0.0, min(total, float(layer.get("start") or 0.0)))
        end = max(start + 0.01, min(total, float(layer.get("end") or 0.0)))
        x, y, _w, _h = _layer_rect(layer, out_w, out_h)
        source = f"{index}:v"
        if _layer_is_sequence(layer):
            graph.append(
                f"[{index}:v]setpts=PTS-STARTPTS+{start:.3f}/TB[l{index}]"
            )
            source = f"l{index}"
        out = f"v{index}"
        graph.append(
            f"[{last}][{source}]overlay=x={x}:y={y}:"
            f"enable='between(t,{start:.3f},{end:.3f})':eof_action=pass[{out}]"
        )
        last = out
    cmd += [
        "-filter_complex", ";".join(graph),
        "-map", f"[{last}]", "-an",
        *_encoder_args(encoder, quality),
        "-t", f"{total:.6f}",
        "-movflags", "+faststart",
        "-map_metadata", "-1",
        str(output),
    ]
    _run(cmd, timeout=900, cancel_event=cancel_event)
    return len(prepared)


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
        if not (start <= at <= end):
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
    for _layer, png in active:
        cmd += ["-loop", "1", "-framerate", str(fps), "-i", str(png)]
    graph: list[str] = []
    last = "0:v"
    for index, (layer, _png) in enumerate(active, 1):
        x, y, _w, _h = _layer_rect(layer, out_w, out_h)
        out = f"v{index}"
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
    cmd = [_ffmpeg(), "-y", "-v", "error", "-i", str(video)]
    for png in pngs:
        cmd += ["-loop", "1", "-i", str(png)]
    graph: list[str] = []
    last = "0:v"
    for index, (start, end, _text) in enumerate(cues, 1):
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
        "-movflags", "+faststart",
        "-map_metadata", "-1",
        str(output),
    ]
    _run(cmd, timeout=900, cancel_event=cancel_event)


def _concat_video(
    tmp: Path,
    target_mp4: Path,
    segments: list[Path],
    quality: str,
    cancel_event: threading.Event | None = None,
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
        "-movflags", "+faststart",
        "-map_metadata", "-1",
        str(target_mp4),
    ]
    try:
        _run(final, timeout=600, cwd=tmp, cancel_event=cancel_event)
        return
    except RenderCancelled:
        raise
    except PipelineError:
        pass
    fallback = base + [
        "-map", "0:v:0", "-an",
        *_encoder_args("libx264", quality),
        "-movflags", "+faststart",
        "-map_metadata", "-1",
        str(target_mp4),
    ]
    _run(fallback, timeout=900, cwd=tmp, cancel_event=cancel_event)


def _mux(
    master: Path,
    audio_path: Path,
    output: Path,
    job_title: str,
    total: float,
    quality: str,
    normalize: bool,
    cancel_event: threading.Event | None = None,
) -> None:
    """Attach one audio bed to the cached video master. Video is copied."""
    base = [
        _ffmpeg(), "-y", "-v", "error",
        "-i", str(master), "-i", str(audio_path),
    ]
    audio_filters = ["-af", "loudnorm=I=-14:TP=-1.5:LRA=11"] if normalize else []
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
    try:
        _run(final, timeout=900, cancel_event=cancel_event)
        return
    except RenderCancelled:
        raise
    except PipelineError:
        pass
    fallback = base + [
        "-map", "0:v:0", "-map", "1:a:0",
        *_encoder_args("libx264", quality),
        *audio_filters,
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-t", f"{total:.6f}",
        "-movflags", "+faststart",
        "-metadata", f"title={job_title}",
        str(output),
    ]
    _run(fallback, timeout=1200, cancel_event=cancel_event)


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
) -> bytes:
    """Render one frame through the same segment and layer graph as a reel."""
    quality = "draft" if quality == "draft" else "final"
    aspect = aspect or compiled.get("aspect") or "9:16"
    aspect = aspect if aspect in ASPECTS else "9:16"
    out_w, out_h = _dims(aspect, quality)
    encoder = _choose_encoder(encoder)
    segments = list(compiled.get("segments") or [])
    total = float(segments[-1].get("out_end") or 0.0) if segments else 0.0
    last_frame = max(0, int(round(total * OUT_FPS)) - 1)
    frame = max(0, int(round(float(at) * OUT_FPS)))
    frame = min(frame, last_frame)
    time_at = frame / OUT_FPS
    index, segment = _compiled_segment_at(compiled, time_at)
    cache_dir = _frame_cache_dir(job_dir)
    key = _frame_cache_key(compiled, frame, quality, out_w, out_h, meta, encoder)
    cached = cache_dir / f"{key}.jpg"
    if cached.is_file() and cached.stat().st_size > 0:
        return cached.read_bytes()

    tmp = job_dir / "renders" / f"tmp_frame_{uuid.uuid4().hex}"
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        segment_path = tmp / "segment.mp4"
        frames = int(segment.get("frames") or 0)
        segment_frames = max(1, frames)
        _segment(
            source, meta, {},
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


def build_story_proxy(
    source: str,
    meta: dict,
    job_dir: Path,
    clips: list[dict],
    scenes: list[dict] | None = None,
    aspect: str = "9:16",
    encoder: str | None = None,
    cancel_event: threading.Event | None = None,
) -> Path:
    """Build (or reuse) the 540-wide proxy for one story range."""
    aspect = aspect if aspect in ASPECTS else "9:16"
    out_w, out_h = _dims(aspect, "draft")
    digest = edits.clip_snapshot_hash(clips)
    proxies = job_dir / "proxies"
    target = proxies / (
        f"{digest}_{aspect.replace(':', 'x')}_{out_w}x{out_h}.mp4"
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
            crop = _scene_crop(scene, aspect, meta, out_w, out_h)
            _segment(
                source, meta, scene,
                float(clip["start"]), float(clip["duration"]), int(clip["frames"]),
                segment_path, False, False,
                out_w, out_h, "draft", encoder,
                job_dir.parent.parent / "cache" / "segments",
                crop=crop,
                cancel_event=cancel_event,
            )
            segments.append(segment_path)
        master = tmp / "master.mp4"
        _concat_video(tmp, master, segments, "draft", cancel_event)
        audio_path = tmp / "audio.wav"
        _audio_track(source, meta, proxy_clips, audio_path, total, cancel_event)
        output = tmp / "proxy.mp4"
        _mux(
            master, audio_path, output, "Story proxy", total, "draft",
            False, cancel_event,
        )
        proxies.mkdir(parents=True, exist_ok=True)
        os.replace(output, target)
        return target
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


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
) -> dict:
    quality = "draft" if quality == "draft" else "final"
    aspect = aspect if aspect in ASPECTS else "9:16"
    out_w, out_h = _dims(aspect, quality)
    encoder = _choose_encoder(encoder)
    target = int(plan["target"])
    suffix = ""
    if quality != "final":
        suffix += f"_{quality}"
    if aspect != "9:16":
        suffix += f"_{aspect.replace(':', 'x')}"
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
        )
    edit_segments: list[dict] = []
    layers: list[dict] = []
    if compiled is not None:
        edit_segments = list(compiled.get("segments") or [])
        layers = list(compiled.get("overlays") or [])
        clips = [
            {
                "scene": segment.get("scene"),
                "role": segment.get("role") or "beat",
                "start": float(segment["start"]),
                "frames": int(segment["frames"]),
                "duration": int(segment["frames"]) / OUT_FPS,
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
            progress(0.01, f"Preparing {len(clips)} beats · {quality} · {encoder}")
            done = 0
            segments: list[Path] = []
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
                    futures[pool.submit(
                        _segment,
                        source, meta, scene,
                        clip["start"], clip["duration"], clip["frames"],
                        segment, index == 0, index == len(clips) - 1,
                        out_w, out_h, quality, encoder, cache_dir, crop, crop_path, cancel_event,
                        pre_filters, post_filters,
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
                        0.02 + 0.78 * (done / max(1, len(clips))),
                        f"Cutting beat {done} / {len(clips)}"
                        + (f" · {cached_count} cached" if cached_count else ""),
                    )
            progress(0.82, "Joining the cut")
            master_tmp = tmp / "master.mp4"
            _concat_video(tmp, master_tmp, segments, quality, cancel_event)
            if layers:
                progress(0.87, "Burning layers")
                layered = tmp / "layers.mp4"
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
        if bed is None:
            progress(0.90, "Building the original audio bed")
            _audio_track(source, meta, clips, audio_path, total, cancel_event)
        else:
            audio_path = bed

        progress(0.95, "Muxing audio")
        _mux(
            master, audio_path, out_tmp, job_title, total, quality,
            not (audio_plan and str(audio_plan.get("mode") or "keep") != "keep"),
            cancel_event,
        )

        info = probe(out_tmp)
        seek = min(0.25, max(0.0, info["duration"] / 2))
        _run([
            _ffmpeg(), "-y", "-v", "error", "-ss", f"{seek:.3f}", "-i", str(out_tmp),
            "-frames:v", "1", "-vf", "scale=540:-2", "-q:v", "3", str(poster_tmp),
        ], timeout=60, cancel_event=cancel_event)

        os.replace(out_tmp, out)
        os.replace(poster_tmp, poster)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    progress(1.0, "Reel ready")
    return {
        "target": target,
        "duration": info["duration"],
        "width": info["width"],
        "height": info["height"],
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
        "beat_bpm": None if not audio_plan else audio_plan.get("_beat_bpm"),
        "beat_drift": None if not audio_plan else audio_plan.get("_beat_drift"),
        "used_assets": (audio_plan or {}).get("_used_assets") or [],
        **audio_info,
    }
