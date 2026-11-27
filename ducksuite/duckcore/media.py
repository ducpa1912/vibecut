"""Small media helpers for DuckSuite preview and render."""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import threading
from pathlib import Path

from PIL import Image


class MediaError(RuntimeError):
    pass


def _tool(name: str) -> str:
    override = os.environ.get(f"DUCK_{name.upper()}")
    if override and Path(override).is_file():
        return override
    helpers = os.environ.get("DUCK_HELPER_DIR")
    if helpers:
        candidate = Path(helpers) / name
        if candidate.is_file():
            return str(candidate)
    root = Path(__file__).resolve().parents[1]
    candidate = root / "bin" / name
    if candidate.is_file():
        return str(candidate)
    found = shutil.which(name)
    if not found:
        raise MediaError(f"{name} is not installed or bundled.")
    return found


def ffmpeg() -> str:
    return _tool("ffmpeg")


def ffprobe() -> str:
    return _tool("ffprobe")


_PREVIEW_LOCK = threading.Lock()


def preview_path(data_root: str | Path, project_id: str) -> Path:
    return Path(data_root) / "projects" / project_id / "preview.mp4"


def ensure_preview(
    source: str | Path,
    target: str | Path,
    *,
    timeout: float = 600.0,
    force: bool = False,
) -> Path | None:
    """Make a browser-playable H.264 proxy for the editor.

    WKWebView cannot reliably decode AV1/HEVC sources. The source stays the
    render master; this proxy is only the editor video element.
    """
    target = Path(target)
    if not force and target.is_file() and target.stat().st_size > 1024:
        return target
    source = Path(source)
    if not source.is_file():
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.stem}.part.mp4")
    command = [
        ffmpeg(), "-y", "-v", "error", "-hwaccel", "none", "-i", str(source),
        "-vf", "scale=1280:720:force_original_aspect_ratio=decrease:force_divisible_by=2",
        "-c:v", "h264_videotoolbox", "-q:v", "65", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
        str(temporary),
    ]
    with _PREVIEW_LOCK:
        if not force and target.is_file() and target.stat().st_size > 1024:
            return target
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.SubprocessError):
            temporary.unlink(missing_ok=True)
            return None
        if result.returncode != 0 or not temporary.is_file() or temporary.stat().st_size < 1024:
            temporary.unlink(missing_ok=True)
            return None
        temporary.replace(target)
    return target


def duration(source: str | Path) -> float:
    result = subprocess.run(
        [ffprobe(), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(source)],
        capture_output=True, text=True, timeout=30,
    )
    try:
        return max(0.0, float(result.stdout.strip()))
    except ValueError:
        return 0.0


def has_audio(source: str | Path) -> bool:
    result = subprocess.run(
        [
            ffprobe(), "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(source),
        ],
        capture_output=True, text=True, timeout=30,
    )
    return "audio" in result.stdout


def extract_frame(source: str | Path, when: float) -> Image.Image:
    command = [
        ffmpeg(), "-v", "error", "-ss", f"{max(0.0, float(when)):.3f}",
        "-hwaccel", "none", "-i", str(source), "-frames:v", "1",
        "-f", "image2pipe", "-vcodec", "png", "pipe:1",
    ]
    result = subprocess.run(command, capture_output=True, timeout=120)
    if result.returncode != 0 or not result.stdout:
        raise MediaError("Could not read a frame from this source.")
    return Image.open(io.BytesIO(result.stdout)).convert("RGB")
