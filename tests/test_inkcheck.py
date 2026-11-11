"""Post-render check: leftover text is found glyph by glyph, wherever it is."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest

from duckcore import ink, inkcheck, media

W, H, FPS = 320, 240, 30
ROWS = slice(100, 120)
GLYPHS = 6
META = {"width": W, "height": H, "fps": FPS}


def _ffmpeg() -> str:
    try:
        return media.ffmpeg()
    except Exception:  # noqa: BLE001 - no ffmpeg on this machine
        pytest.skip("ffmpeg is not available")


def _picture(count: int, seed: int = 1) -> np.ndarray:
    """A smooth, moving grey picture: no still hard edges of its own."""
    rng = np.random.default_rng(seed)
    out = np.zeros((count, H, W), dtype=np.uint8)
    for index in range(count):
        out[index] = 60 + (index * 3) % 120 + rng.integers(0, 12, size=(H, W))
    return out


def _columns(number: int) -> slice:
    left = 60 + number * 32
    return slice(left, left + 20)


def _draw(frames: np.ndarray, glyphs=range(GLYPHS)) -> None:
    for number in glyphs:
        columns = _columns(number)
        frames[..., ROWS, columns] = 20
        frames[..., ROWS, columns.start:columns.stop:4] = 250
        frames[..., ROWS, columns.start + 1:columns.stop:4] = 250


def _write(path: Path, frames: np.ndarray) -> Path:
    command = [
        _ffmpeg(), "-y", "-v", "error", "-nostdin",
        "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{W}x{H}", "-r", str(FPS),
        "-i", "-", "-an", "-c:v", "ffv1", "-pix_fmt", "yuv420p", str(path),
    ]
    done = subprocess.run(command, input=frames.tobytes(), capture_output=True, check=False)
    assert done.returncode == 0, done.stderr.decode()[-400:]
    return path


def _edit(start: float = 1.0, end: float = 2.0, **extra) -> dict:
    return {
        "clean": [{
            "id": "cl_test", "kind": "fill", "enabled": True, "tracklet_id": "tr_1",
            "ranges": [{"start": start, "end": end}],
            "box": {"x": 60 / W, "y": 100 / H, "w": (GLYPHS * 32 - 12) / W, "h": 20 / H},
            "text_sample": "six glyphs",
        }],
        **extra,
    }


def _source(tmp_path: Path, count: int = 90, text: slice = slice(30, 60)) -> tuple[Path, np.ndarray]:
    frames = _picture(count)
    _draw(frames[text])
    return _write(tmp_path / "source.mkv", frames), frames


def test_a_clean_render_has_no_hits_and_every_line_is_checked(tmp_path) -> None:
    source, _frames = _source(tmp_path)
    output = _write(tmp_path / "output.mkv", _picture(90))
    report = inkcheck.check(output, _edit(), META, source=source)
    assert report["hits"] == []
    assert report["unchecked"] == []
    assert report["checked"] == report["layers"] == 1
    assert report["frames"] >= 55


def test_one_leaked_frame_is_reported(tmp_path) -> None:
    source, frames = _source(tmp_path)
    filled = _picture(90)
    filled[45] = frames[45]  # the fill missed this frame
    report = inkcheck.check(_write(tmp_path / "output.mkv", filled), _edit(), META, source=source)
    assert report["times"] == [1.5]
    assert report["hits"][0]["glyphs"] == GLYPHS


def test_two_glyphs_left_of_six_are_reported(tmp_path) -> None:
    """A whole-line score read this as a third of a line and said nothing."""
    source, frames = _source(tmp_path)
    filled = _picture(90)
    for number in (0, 5):
        filled[40, ROWS, _columns(number)] = frames[40, ROWS, _columns(number)]
    report = inkcheck.check(_write(tmp_path / "output.mkv", filled), _edit(), META, source=source)
    assert [(hit["time"], hit["glyphs"], hit["of"]) for hit in report["hits"]] == [(round(40 / 30, 3), 2, GLYPHS)]


def test_text_left_after_the_range_ended_is_reported(tmp_path) -> None:
    """The range stops five frames early, and so did the fill."""
    source, frames = _source(tmp_path)
    filled = _picture(90)
    filled[55:60] = frames[55:60]
    report = inkcheck.check(
        _write(tmp_path / "output.mkv", filled), _edit(1.0, 55 / 30), META, source=source,
    )
    assert report["times"] == [round(index / 30, 3) for index in range(55, 60)]
    assert report["hits"][0]["source_time"] == report["hits"][0]["time"]


def test_a_redrawn_edge_under_the_text_is_not_leftover(tmp_path) -> None:
    """The fill drew strokes of its own where the letters were: not the source's text."""
    source, _frames = _source(tmp_path)
    filled = _picture(90)
    for number in range(GLYPHS):
        columns = _columns(number)
        filled[30:60, ROWS, columns.start:columns.stop:4] += 90
    report = inkcheck.check(_write(tmp_path / "output.mkv", filled), _edit(), META, source=source)
    assert report["hits"] == []


def test_a_trimmed_edit_is_checked_at_its_own_times(tmp_path) -> None:
    source, frames = _source(tmp_path)
    filled = _picture(90)
    filled[45] = frames[45]
    # The edit drops the first half second: output frame 30 is source frame 45.
    output = _write(tmp_path / "output.mkv", filled[15:])
    edit = _edit(clips=[{"start": 0.5, "end": 3.0}])
    report = inkcheck.check(output, edit, META, source=source)
    assert report["times"] == [1.0]
    assert report["hits"][0]["source_time"] == 1.5


def test_a_render_at_another_size_is_checked(tmp_path) -> None:
    source, frames = _source(tmp_path)
    filled = _picture(90)
    filled[45] = frames[45]
    full = _write(tmp_path / "full.mkv", filled)
    small = tmp_path / "small.mkv"
    done = subprocess.run(
        [_ffmpeg(), "-y", "-v", "error", "-i", str(full), "-vf", "scale=240:180",
         "-c:v", "ffv1", str(small)], capture_output=True, check=False,
    )
    assert done.returncode == 0, done.stderr.decode()[-300:]
    report = inkcheck.check(small, _edit(), META, source=source, size=(240, 180))
    assert report["times"] == [1.5]


def test_a_line_too_short_to_check_is_counted_not_passed(tmp_path) -> None:
    source, _frames = _source(tmp_path, text=slice(30, 33))
    output = _write(tmp_path / "output.mkv", _picture(90))
    report = inkcheck.check(output, _edit(1.0, 1.1), META, source=source)
    assert report["checked"] == 0
    assert report["unchecked"][0]["layer"] == "cl_test"
    assert "too short" in report["unchecked"][0]["reason"]


def test_a_missing_render_is_not_a_clean_render(tmp_path) -> None:
    source, _frames = _source(tmp_path)
    report = inkcheck.check(tmp_path / "nothing.mkv", _edit(), META, source=source)
    assert report["hits"] == []
    assert report["checked"] == 0
    assert report["unchecked"][0]["reason"]


def test_layer_strokes_give_each_glyph_its_hole_and_frames(tmp_path) -> None:
    source, _frames = _source(tmp_path)
    inks, reason = inkcheck.layer_inks(_edit()["clean"][0], META, source=source)
    assert reason == "" and len(inks) == 1
    assert (inks[0].first, inks[0].last) == (30, 59)
    rect, pieces = inkcheck.layer_strokes(inks)
    assert len(pieces) == GLYPHS
    assert all((first, last) == (30, 59) for first, last, _hole in pieces)
    assert all(hole.shape == (rect[3] - rect[1], rect[2] - rect[0]) for _f, _l, hole in pieces)
    # The rect hugs the strokes and their margin; it is not the search box.
    search = inkcheck.search_rect(_edit()["clean"][0], W, H)
    assert rect[0] >= 60 - ink.GROW_PX - 1 and rect[1] >= 100 - ink.GROW_PX - 1
    assert (rect[2] - rect[0]) * (rect[3] - rect[1]) < (search[2] - search[0]) * (search[3] - search[1])
    # Each glyph's hole stays on its own glyph.
    assert not pieces[0][2][:, 40:].any()
