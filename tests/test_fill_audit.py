"""scripts/fill_audit.py: does each number say what it claims?

Frames are arrays in memory. No video file is made or read, except through a
faked reader in the end-to-end checks.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("fill_audit", ROOT / "scripts" / "fill_audit.py")
fill_audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fill_audit)

HEIGHT, WIDTH = 120, 240
RECT = (20, 80, 220, 110)


def _plain(value=100):
    return np.full((HEIGHT, WIDTH, 3), value, dtype=np.uint8)


def _with_text(frame, value=245):
    out = frame.copy()
    for x in range(40, 200, 24):
        out[88:102, x:x + 5] = value
    return out


def _source(count=6):
    return [_with_text(_plain()) for _ in range(count)]


def _clean_fill(count=6, value=100):
    return [_plain(value) for _ in range(count)]


def _run(source, clip, rects=(RECT,), fps=30.0, start=0.0):
    return fill_audit.audit(source, clip, lambda _index: list(rects), fps=fps, start=start)


def test_a_clean_fill_raises_nothing():
    report = _run(_source(), _clean_fill())
    assert report["frames"] == 6
    assert report["changes"]["outside_boxes"] == 0
    assert report["changes"]["outside_text"] == 0
    assert report["leftover"]["unfilled_frames"] == 0
    assert report["leftover"]["ghost_frames"] == 0
    assert report["flicker"]["spike_frames"] == 0
    assert fill_audit.looks(report) == []


def test_identical_files_have_no_changes_and_every_text_frame_is_left():
    source = _source(4)
    report = _run(source, source)
    assert report["changes"]["changed_pixels"] == 0
    assert report["leftover"]["unfilled_frames"] == 4


def test_encoder_noise_is_not_a_change():
    source = _source()
    rng = np.random.default_rng(1)
    clip = [
        np.clip(_plain().astype(np.int16) + rng.integers(-6, 7, (HEIGHT, WIDTH, 3)), 0, 255).astype(np.uint8)
        for _ in source
    ]
    report = _run(source, clip)
    assert report["changes"]["outside_boxes"] == 0
    assert report["changes"]["outside_text"] == 0


def test_a_smear_over_the_box_counts_as_outside_the_text():
    source = _source()
    clip = []
    for _ in source:
        frame = _plain()
        frame[RECT[1]:RECT[3], RECT[0]:RECT[2]] = 160
        clip.append(frame)
    report = _run(source, clip)
    assert report["changes"]["outside_text"] > 0.5
    assert "changes outside the text, so objects may smear" in fill_audit.looks(report)


def test_a_change_outside_the_boxes_is_reported():
    source = _source()
    clip = _clean_fill()
    for frame in clip:
        frame[5:30, 5:60] = 200
    report = _run(source, clip)
    assert report["changes"]["outside_boxes"] > 0.2
    assert "changes outside the boxes" in fill_audit.looks(report)


def test_the_feathered_edge_of_the_fill_is_not_outside_the_boxes():
    source = _source()
    clip = _clean_fill()
    x0, y0, x1, y1 = RECT
    feather = fill_audit.masks.FEATHER_PX
    for frame in clip:
        frame[y0 - feather:y1 + feather, x0 - feather:x1 + feather] = 160
    assert _run(source, clip)["changes"]["outside_boxes"] == 0


def test_frames_with_no_text_that_changed_are_counted():
    source = [_plain() for _ in range(4)]
    clip = [_plain() for _ in range(4)]
    clip[2][RECT[1]:RECT[3], RECT[0]:RECT[2]] = 160
    report = _run(source, clip)
    assert report["changes"]["frames_without_text"] == 4
    assert report["changes"]["frames_without_text_changed"] == 1
    assert "frames with no text were changed" in fill_audit.looks(report)


def test_unfilled_frames_give_their_source_time():
    source = _source(10)
    clip = _clean_fill(10)
    clip[3] = source[3].copy()
    clip[4] = source[4].copy()
    clip[8] = source[8].copy()
    report = _run(source, clip, fps=10.0, start=20.0)
    assert report["leftover"]["unfilled_frames"] == 3
    assert report["leftover"]["unfilled"] == [
        {"start": 20.3, "end": 20.5},
        {"start": 20.8, "end": 20.9},
    ]


@pytest.mark.parametrize("strength,found", [(0.05, False), (0.3, True), (0.6, True)])
def test_a_ghost_of_the_text_is_measured_by_its_strength(strength, found):
    source = _source()
    clip = [
        np.round(_plain() + strength * (frame.astype(np.float32) - _plain())).astype(np.uint8)
        for frame in source
    ]
    report = _run(source, clip)
    assert report["leftover"]["text_kept"]["median"] == pytest.approx(strength, abs=0.05)
    assert (report["leftover"]["ghost_frames"] == 6) is found
    assert report["leftover"]["unfilled_frames"] == 0


def test_a_fill_on_a_textured_background_does_not_read_as_leftover():
    rows = (100 + 12 * np.sin(np.arange(HEIGHT) / 3.0)).astype(np.uint8)
    picture = np.repeat(rows[:, None, None], WIDTH, axis=1).repeat(3, axis=2)
    source = [_with_text(picture) for _ in range(4)]
    clip = [picture.copy() for _ in range(4)]
    report = _run(source, clip)
    assert report["leftover"]["ghost_frames"] == 0
    assert report["leftover"]["unfilled_frames"] == 0


def test_flicker_is_measured_against_a_still_background():
    source = _source(8)
    clip = _clean_fill(8)
    for index, frame in enumerate(clip):
        level = 150 if index % 2 else 120
        for x in range(40, 200, 24):
            frame[88:102, x:x + 5] = level
    report = _run(source, clip, fps=10.0)
    assert report["flicker"]["spike_frames"] == 7
    assert "flicker in the fill" in fill_audit.looks(report)


def test_background_motion_is_not_flicker():
    source, clip = [], []
    for index in range(8):
        level = 100 + index * 8
        source.append(_with_text(_plain(level)))
        clip.append(_plain(level))
    report = _run(source, clip)
    assert report["flicker"]["spike_frames"] == 0


def test_a_scene_cut_is_skipped_not_called_flicker():
    source = [_with_text(_plain(40 if index < 3 else 200), 250 if index >= 3 else 200) for index in range(6)]
    clip = [_plain(40 if index < 3 else 200) for index in range(6)]
    report = _run(source, clip, fps=10.0)
    assert report["flicker"]["scene_cuts_skipped"] == [0.3]
    assert report["flicker"]["spike_frames"] == 0


def test_a_fill_of_the_wrong_colour_is_reported():
    source = _source()
    clip = []
    for _ in source:
        frame = _plain()
        for x in range(40, 200, 24):
            frame[88:102, x:x + 5] = (160, 100, 100)
        clip.append(frame)
    report = _run(source, clip)
    red, green, blue = report["colour"]["fill_vs_surroundings_rgb"]
    assert red > 40 and green == 0 and blue == 0
    assert "the fill's colour differs from its surroundings" in fill_audit.looks(report)


def test_a_shift_of_the_whole_clip_is_reported():
    source = _source()
    clip = _clean_fill(value=110)
    report = _run(source, clip)
    assert report["colour"]["outside_boxes_rgb"] == [10.0, 10.0, 10.0]
    assert "the whole clip's colour shifted" in fill_audit.looks(report)


def test_a_box_too_busy_to_read_is_skipped_and_counted():
    rng = np.random.default_rng(2)
    busy = [rng.integers(0, 256, (HEIGHT, WIDTH, 3), dtype=np.uint8) for _ in range(3)]
    report = _run(busy, [frame.copy() for frame in busy])
    assert report["uncertain_frames"] == 3
    assert report["leftover"]["frames_with_text"] == 0


def test_frames_outside_a_layer_time_have_no_area():
    source = _source(4)
    clip = [frame.copy() for frame in source]
    clip[1] = _plain()
    report = fill_audit.audit(
        source, clip, lambda index: [RECT] if index == 1 else [], fps=10.0,
    )
    assert report["leftover"]["frames_with_text"] == 1
    assert report["leftover"]["unfilled_frames"] == 0


def test_no_frames_is_an_error():
    with pytest.raises(fill_audit.AuditError, match="No frames"):
        _run([], [])


def test_find_start_finds_the_clip_in_the_source():
    rng = np.random.default_rng(3)
    source = rng.integers(0, 256, (40, 16, 32), dtype=np.uint8)
    clip = source[17:29].copy()
    clip[:, 10:13] = 0
    keep = np.ones((16, 32), dtype=bool)
    keep[10:13] = False
    frame, gap = fill_audit.find_start(source, clip, keep)
    assert frame == 17
    assert gap == 0


def test_find_start_refuses_a_clip_longer_than_the_source():
    with pytest.raises(fill_audit.AuditError, match="longer"):
        fill_audit.find_start(np.zeros((3, 4, 4), np.uint8), np.zeros((5, 4, 4), np.uint8), np.ones((4, 4), bool))


def _fake_files(monkeypatch, *, clip_size=(WIDTH, HEIGHT), source_size=(WIDTH, HEIGHT)):
    metas = {
        "clip.mp4": {"width": clip_size[0], "height": clip_size[1], "fps": 10.0, "duration": 0.6},
        "source.mp4": {"width": source_size[0], "height": source_size[1], "fps": 10.0, "duration": 2.0},
    }
    monkeypatch.setattr(fill_audit.pipeline, "probe", lambda path: metas[Path(path).name])
    calls = []

    def read(path, *, start, duration, fps, width, height, pix_fmt="rgb24", ffmpeg="ffmpeg"):
        calls.append({"path": path, "start": start, "pix_fmt": pix_fmt})
        count = 6 if path == "clip.mp4" else 20
        if pix_fmt == "gray":
            gradient = np.arange(height * width, dtype=np.uint8).reshape(height, width)
            return [
                ((gradient * ((index % 20) + 1)) % 255).astype(np.uint8)
                for index in (range(4, 10) if path == "clip.mp4" else range(count))
            ]
        return _clean_fill(count) if path == "clip.mp4" else _source(count)

    monkeypatch.setattr(fill_audit, "read_frames", read)
    return calls


def test_main_prints_a_report_and_reads_both_files_from_the_right_place(monkeypatch, capsys):
    calls = _fake_files(monkeypatch)
    code = fill_audit.main(["clip.mp4", "source.mp4", "--box", "0.1,0.7,0.8,0.2", "--start", "1.5"])
    assert code == 0
    out = capsys.readouterr().out
    assert "from 1.500 s in the source" in out
    assert "Leftover text" in out
    assert {"path": "source.mp4", "start": 1.5, "pix_fmt": "rgb24"} in calls
    assert {"path": "clip.mp4", "start": 0.0, "pix_fmt": "rgb24"} in calls


def test_main_finds_the_start_from_the_picture(monkeypatch, capsys):
    _fake_files(monkeypatch)
    code = fill_audit.main(["clip.mp4", "source.mp4", "--box", "0.1,0.7,0.8,0.2", "--json"])
    assert code == 0
    assert json.loads(capsys.readouterr().out)["start"] == 0.4


def test_main_refuses_a_cropped_render(monkeypatch, capsys):
    _fake_files(monkeypatch, clip_size=(120, 120))
    code = fill_audit.main(["clip.mp4", "source.mp4", "--box", "0.1,0.7,0.8,0.2", "--start", "0"])
    assert code == 2
    assert "cannot be compared pixel by pixel" in capsys.readouterr().err


def test_main_needs_to_know_where_the_text_is(capsys):
    assert fill_audit.main(["clip.mp4", "source.mp4"]) == 2
    assert "--box or --layers" in capsys.readouterr().err


def test_layers_come_from_an_edit_and_only_ai_fill_counts(tmp_path):
    path = tmp_path / "edit.json"
    path.write_text(json.dumps({"clean": [
        {"id": "a", "kind": "fill", "box": {"x": 0, "y": 0, "w": 1, "h": 1}},
        {"id": "b", "kind": "blur", "box": {"x": 0, "y": 0, "w": 1, "h": 1}},
    ]}), encoding="utf-8")
    assert [layer["id"] for layer in fill_audit.load_layers(str(path))] == ["a"]


def test_the_script_writes_nothing():
    script = (ROOT / "scripts" / "fill_audit.py").read_text(encoding="utf-8")
    for call in (" open(", "write_text", "write_bytes", ".unlink", "mkdir", "shutil"):
        assert call not in script
    # ffmpeg only ever writes to its own output pipe.
    assert '"pipe:1"' in script and '"-y"' not in script
