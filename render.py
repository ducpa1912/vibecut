"""Turn a cut plan into a vertical H.264 reel.

The renderer is deliberately boring: every beat is cut as its own segment,
then the segments are joined with the concat demuxer. That keeps frame
boundaries exact and lets us cache and parallelize the expensive part.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFont

import audio
import captions as caption_engine
from pipeline import PipelineError, crop_center, probe

TARGET_AR = 9 / 16
OUT_W = 1080
OUT_H = 1920
OUT_FPS = 30

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


def _path_value(points: list[tuple[float, float]], at: float) -> float:
    if at <= points[0][0]:
        return points[0][1]
    for index in range(len(points) - 1):
        t0, v0 = points[index]
        t1, v1 = points[index + 1]
        if at <= t1:
            span = max(1e-6, t1 - t0)
            return v0 + (v1 - v0) * max(0.0, min(1.0, (at - t0) / span))
    return points[-1][1]


def _path_expression(points: list[tuple[float, float]]) -> str:
    expression = f"{points[-1][1]:.3f}"
    for index in range(len(points) - 2, -1, -1):
        t0, v0 = points[index]
        t1, v1 = points[index + 1]
        span = max(1e-6, t1 - t0)
        segment = (
            f"{v0:.3f}+({v1 - v0:.3f})*"
            f"(1-cos(PI*(t-{t0:.3f})/{span:.6f}))/2"
        )
        expression = f"if(lt(t,{t1:.3f}),{segment},{expression})"
    return f"if(lt(t,{points[0][0]:.3f}),{points[0][1]:.3f},{expression})"


def _crop_filter(
    meta: dict, crop: dict, out_w: int, out_h: int,
    crop_path: list[dict] | None = None, duration: float = 0.0,
) -> str:
    width, height = int(meta["width"]), int(meta["height"])
    source_ar = width / max(1, height)
    target_ar = out_w / out_h
    cx = float(crop.get("cx", 0.5))
    cy = float(crop.get("cy", 0.5))
    filters: list[str] = []

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
) -> bool:
    """Render one beat. Return True when the segment came from cache."""
    key = _segment_cache_key(
        meta, scene, start, frames, out_w, out_h, quality, encoder, first, last,
        crop, crop_path,
    )
    cached = cache_dir / f"{key}.mp4"
    if cached.exists() and cached.stat().st_size > 0:
        _link_or_copy(cached, output)
        return True

    ffmpeg = _ffmpeg()
    vf = _crop_filter(
        meta, crop or scene.get("crop") or {"cx": 0.5, "cy": 0.5},
        out_w, out_h, crop_path=crop_path, duration=duration,
    )

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
    return lines[:4]


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
        lines = [line for line in lines if line][: int(style["max_lines"])]
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
            wrapped.append((start, end, rows[: int(style["max_lines"])]))
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
    if render_clips is None:
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

    if cancel_event is not None and cancel_event.is_set():
        raise RenderCancelled("Render cancelled.")

    if (
        captions
        and not plan.get("_caption_cues")
        and not plan.get("_transcript_segments")
    ):
        plan["_transcript_segments"] = caption_engine.read_transcript_segments(job_dir)
    effective_style = caption_style or plan.get("_caption_style")
    normalized_style = caption_engine.normalize_style(effective_style or {})
    caption_sig = ""
    if captions:
        track = plan.get("_caption_track") or {}
        if track.get("id"):
            caption_sig = str(track["id"])
        else:
            caption_sig = caption_engine.style_hash(normalized_style)

    master_dir = job_dir.parent.parent / "cache" / "masters" / job_dir.name
    cues = list(caption_cues) if caption_cues is not None else _caption_cues(plan, clips)
    caption_count = len(cues)
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
        "caption_margin": round(float(caption_margin), 4) if captions else 0.0,
        "encoder": encoder,
    }, sort_keys=True).encode()).hexdigest()[:16]
    master = master_dir / f"{master_key}.mp4"
    cached_count = 0
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
                    scene = scenes.get(clip["scene"])
                    if not scene:
                        raise PipelineError(f"Plan references missing scene {clip['scene']}.")
                    segment = tmp / f"{index:03d}.mp4"
                    segments.append(segment)
                    crop = _scene_crop(scene, aspect, meta, out_w, out_h)
                    crop_path = _crop_path_for(scene, aspect, clip)
                    futures[pool.submit(
                        _segment,
                        source, meta, scene,
                        clip["start"], clip["duration"], clip["frames"],
                        segment, index == 0, index == len(clips) - 1,
                        out_w, out_h, quality, encoder, cache_dir, crop, crop_path, cancel_event,
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
            if captions:
                progress(0.87, "Burning captions")
                if cues:
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
        "captions": bool(captions),
        "caption_count": caption_count,
        "cached": cached_count,
        "beat_bpm": None if not audio_plan else audio_plan.get("_beat_bpm"),
        "beat_drift": None if not audio_plan else audio_plan.get("_beat_drift"),
        "used_assets": (audio_plan or {}).get("_used_assets") or [],
        **audio_info,
    }
