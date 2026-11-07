"""Small media helpers for DuckSuite preview and render."""

from __future__ import annotations

import io
import os
import shutil
import subprocess
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
        "-i", str(source), "-frames:v", "1",
        "-f", "image2pipe", "-vcodec", "png", "pipe:1",
    ]
    result = subprocess.run(command, capture_output=True, timeout=120)
    if result.returncode != 0 or not result.stdout:
        raise MediaError("Could not read a frame from this source.")
    return Image.open(io.BytesIO(result.stdout)).convert("RGB")
