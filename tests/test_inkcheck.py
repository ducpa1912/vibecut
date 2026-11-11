"""Post-render ink check: a render with one leaked frame must report it."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from duckcore import ink, inkcheck

W, H, FPS = 320, 240, 30
TEXT = (slice(100, 120), slice(60, 260))


def _ffmpeg() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    root = Path(__file__).resolve().parent.parent
    bundled = root / "build/DuckSuite-Xcode.app/Contents/Helpers/ffmpeg"
    return str(bundled) if bundled.is_file() else None


def _picture(count: int, seed: int) -> np.ndarray:
    """A smooth, moving grey picture: no still hard edges of its own."""
    rng = np.random.default_rng(seed)
    out = np.zeros((count, H, W), dtype=np.uint8)
    for index in range(count):
        base = 60 + (index * 3) % 120
        out[index] = base + rng.integers(0, 12, size=(H, W))
    return out


def _draw_text(frames: np.ndarray) -> None:
    top, left = TEXT
    for column in range(left.start, left.stop, 8):
        frames[:, top, column:column + 4] = 250
        frames[:, top, column + 4:column + 8] = 20


def _write(path: Path, frames: np.ndarray, ffmpeg: str) -> None:
    command = [
        ffmpeg, "-y", "-v", "error", "-nostdin",
        "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{W}x{H}", "-r", str(FPS),
        "-i", "-", "-an", "-c:v", "ffv1", "-pix_fmt", "yuv420p", str(path),
    ]
    done = subprocess.run(command, input=frames.tobytes(), capture_output=True, check=False)
    assert done.returncode == 0, done.stderr.decode()[-400:]


def test_one_leaked_frame_is_reported(tmp_path) -> None:
    ffmpeg = _ffmpeg()
    if ffmpeg is None:
        pytest.skip("ffmpeg is not available")

    count = 60  # 2 s
    source = _picture(count, seed=1)
    _draw_text(source[15:45])
    output = _picture(count, seed=1)
    # One frame keeps the whole line: the fill missed that frame.
    output[30, TEXT[0], TEXT[1]] = source[30, TEXT[0], TEXT[1]]

    source_path, output_path = tmp_path / "source.mkv", tmp_path / "output.mkv"
    _write(source_path, source, ffmpeg)
    _write(output_path, output, ffmpeg)

    edit = {
        "clean": [{
            "id": "cl_test",
            "kind": "fill",
            "enabled": True,
            "ranges": [{"start": 0.5, "end": 1.5}],
            "box": {"x": 60 / W, "y": 100 / H, "w": 200 / W, "h": 20 / H},
            "text_sample": "test line",
        }],
    }
    meta = {"width": W, "height": H, "fps": FPS}
    report = inkcheck.check(
        output_path, edit, meta, source=source_path, fps=FPS,
    )
    assert report["layers"] == 1
    assert report["frames"] >= 60
    assert report["hits"], "the leaked frame must be a hit"
    worst = max(report["hits"], key=lambda item: item["score"])
    assert abs(worst["time"] - 1.0) <= 0.05
    assert worst["score"] >= ink.HIT
