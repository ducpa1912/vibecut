"""A text effect renders at the size the preview promises."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from duckcore import render


def _black(path: Path, ffmpeg: str) -> None:
    subprocess.run(
        [ffmpeg, "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=c=black:s=320x180:d=1",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )


def test_headline_renders_near_its_style_share_of_the_frame(tmp_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg is not installed")

    output = tmp_path / "base.mp4"
    _black(output, ffmpeg)
    project = tmp_path / "projects" / "prj_size"
    (project / "edits").mkdir(parents=True)
    (project / "edits" / "ed_size.json").write_text(json.dumps({}), encoding="utf-8")
    edit = {
        "id": "ed_size",
        "project_id": "prj_size",
        "end": 1.0,
        "sfx": [{
            "id": "fx_big", "kind": "text", "name": "Big line", "text": "Big line",
            "start": 0.0, "end": 1.0, "style": "headline", "color": "#ffffff",
            "x": 0.5, "y": 0.5, "opacity": 1.0,
        }],
    }

    render._apply_visual_effects(
        ffmpeg, output, edit, tmp_path, tmp_path,
        out_w=320, out_h=180, target_fps=30,
    )

    frame = tmp_path / "frame.png"
    subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(output), "-frames:v", "1", str(frame)], check=True)

    from PIL import Image

    image = Image.open(frame).convert("L")
    width, height = image.size
    pixels = image.load()
    bright = [
        (x, y) for y in range(height) for x in range(width)
        if pixels[x, y] > 60
    ]
    assert bright, "the text effect did not render"
    top = min(y for _x, y in bright)
    bottom = max(y for _x, y in bright)
    glyph_height = bottom - top + 1

    # Headline is 9.2 % of the frame height; glyph ink is a little shorter than the em box.
    share = glyph_height / height
    assert 0.055 <= share <= 0.115, f"headline ink is {share:.3f} of the frame, expected about 0.092"


def test_badge_is_not_scaled_up_by_the_overlay(tmp_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg is not installed")

    output = tmp_path / "base.mp4"
    _black(output, ffmpeg)
    project = tmp_path / "projects" / "prj_badge"
    (project / "edits").mkdir(parents=True)
    (project / "edits" / "ed_badge.json").write_text(json.dumps({}), encoding="utf-8")
    edit = {
        "id": "ed_badge",
        "project_id": "prj_badge",
        "end": 1.0,
        "sfx": [{
            "id": "fx_badge", "kind": "text", "name": "Badge", "text": "LIVE",
            "start": 0.0, "end": 1.0, "style": "badge", "color": "#ffffff",
            "x": 0.5, "y": 0.5, "opacity": 1.0,
        }],
    }

    render._apply_visual_effects(
        ffmpeg, output, edit, tmp_path, tmp_path,
        out_w=320, out_h=180, target_fps=30,
    )

    frame = tmp_path / "frame.png"
    subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(output), "-frames:v", "1", str(frame)], check=True)

    from PIL import Image

    image = Image.open(frame).convert("L")
    width, height = image.size
    pixels = image.load()
    bright = [(x, y) for y in range(height) for x in range(width) if pixels[x, y] > 60]
    assert bright, "the badge effect did not render"
    ink = max(y for _x, y in bright) - min(y for _x, y in bright) + 1
    share = ink / height
    # Badge is 4.6 % of the height with a padded pill; anything near 0.09 is the old 35 %-width blow-up.
    assert share <= 0.075, f"badge ink is {share:.3f} of the frame, expected about 0.046"
