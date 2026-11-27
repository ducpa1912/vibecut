"""The source bed mute is a real render rule, not only a UI state."""

from __future__ import annotations

import array
import math
import shutil
import subprocess
from pathlib import Path

import pytest

from duckcore import media, render


def _tone(path: Path, ffmpeg: str) -> None:
    subprocess.run(
        [ffmpeg, "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=c=black:s=160x90:d=2",
         "-f", "lavfi", "-i", "sine=frequency=220:duration=2",
         "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", str(path)],
        check=True,
    )


def _rms(path: Path, ffmpeg: str) -> int:
    raw = subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", "8000", "-"],
        capture_output=True, check=True,
    ).stdout
    samples = array.array("h")
    samples.frombytes(raw)
    if not samples:
        return 0
    return int(math.sqrt(sum(value * value for value in samples) / len(samples)))


def test_muted_source_silences_the_render(tmp_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg is not installed")

    source = tmp_path / "base.mp4"
    _tone(source, ffmpeg)
    assert _rms(source, ffmpeg) > 200

    render._mix_audio(ffmpeg, source, {"end": 2.0, "audio_source_muted": True}, tmp_path)

    assert abs(media.duration(source) - 2.0) < 0.3
    assert _rms(source, ffmpeg) < 40, "the muted source still carries audio"


def test_source_stays_when_not_muted(tmp_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg is not installed")

    source = tmp_path / "base.mp4"
    _tone(source, ffmpeg)

    render._mix_audio(ffmpeg, source, {"end": 2.0}, tmp_path)

    assert _rms(source, ffmpeg) > 200, "an unmuted source must survive the mix"
