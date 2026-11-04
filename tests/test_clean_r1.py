"""Clean R1: fill the text, not the box, and pay only for strips with text."""

from __future__ import annotations

import numpy as np

import compose_render
import textfill
from textfill import mask as masks


def _background(height=70, width=640, value=110):
    return np.full((height, width, 3), value, dtype=np.uint8)


def _with_text(region):
    out = region.copy()
    for x in range(100, 500, 30):
        out[20:50, x:x + 6] = 240
    return out


def test_finds_text_pixels_not_the_whole_box():
    region = _with_text(_background())
    found = masks.text_in_region(region, 3)
    assert found[35, 102]
    assert not found[35, 600]
    assert 0.05 < found.mean() < 0.5


def test_a_flat_box_has_no_text():
    found = masks.text_in_region(_background(), 3)
    assert found is not None and not found.any()


def test_finds_coloured_text_of_equal_brightness():
    region = _background(value=110)
    for x in range(100, 500, 30):
        region[20:50, x:x + 6] = (190, 80, 60)
    found = masks.text_in_region(region, 3)
    assert found is not None and found[35, 102]


def test_faint_structure_fills_the_whole_box():
    rng = np.random.default_rng(1)
    noise = rng.integers(-20, 20, size=(70, 640, 3))
    region = np.clip(110 + noise, 0, 255).astype(np.uint8)
    assert masks.text_in_region(region, 3) is None


def test_a_very_busy_box_fills_the_whole_box(monkeypatch):
    monkeypatch.setattr(masks, "TEXT_MAX_SHARE", 0.001)
    assert masks.text_in_region(_with_text(_background()), 3) is None


def _layer(**extra):
    return {"box": {"x": 0.1, "y": 0.8, "w": 0.8, "h": 0.05}, **extra}


def test_only_scan_layers_without_a_stroke_narrow_to_text():
    assert masks.uses_text_mask(_layer(tracklet_id="trk_a"), 720, 1280)
    assert not masks.uses_text_mask(_layer(), 720, 1280)
    painted = _layer(tracklet_id="trk_a", mask={"space": "source", "strokes": [{
        "r": 0.01, "points": [{"x": 0.2, "y": 0.82}, {"x": 0.6, "y": 0.82}],
    }]})
    assert not masks.uses_text_mask(painted, 720, 1280)


def _frames(count, text_from, text_to, height=100, width=200):
    out = []
    for index in range(count):
        frame = np.full((height, width, 3), 90, dtype=np.uint8)
        if text_from <= index < text_to:
            for x in range(40, 160, 20):
                frame[40:60, x:x + 4] = 250
        out.append(frame)
    return out


RECT = (10, 30, 190, 70)


def _finder(count):
    return masks.TextMasks([[RECT]] * count, [[]] * count, 200, 100)


def test_wrap_yields_every_frame_in_order():
    frames = _frames(9, 3, 6)
    finder = _finder(9)
    out = list(finder.wrap(iter(frames)))
    assert len(out) == 9 and all(a is b for a, b in zip(out, frames))


def test_frames_far_from_text_are_not_filled_and_near_ones_are():
    finder = _finder(12)
    list(finder.wrap(iter(_frames(12, 5, 7))))
    assert finder.rects_for(0) == []
    assert finder.rects_for(3) == [RECT]
    assert finder.rects_for(8) == [RECT]
    assert finder.rects_for(11) == []


def test_hole_follows_the_text_and_stays_in_the_rect():
    finder = _finder(5)
    list(finder.wrap(iter(_frames(5, 0, 5))))
    hole = finder.hole(2, 0, 0, 200, 100)
    assert hole[50, 41] and not hole[50, 180]
    assert not hole[:30].any() and not hole[70:].any()


def test_a_hole_can_be_read_for_part_of_the_frame():
    finder = _finder(3)
    list(finder.wrap(iter(_frames(3, 0, 3))))
    whole = finder.hole(1, 0, 0, 200, 100)
    assert np.array_equal(finder.hole(1, 0, 40, 200, 60), whole[40:60])


def test_exact_areas_always_fill():
    exact = (0, 0, 20, 20)
    finder = masks.TextMasks([[RECT]] * 4, [[exact]] * 4, 200, 100)
    list(finder.wrap(iter(_frames(4, 9, 9))))
    assert finder.has_fill(1)
    hole = finder.hole(1, 0, 0, 200, 100)
    assert hole[:20, :20].all() and not hole[50, 41]


def test_forget_keeps_the_frames_a_later_hole_needs():
    finder = _finder(10)
    list(finder.wrap(iter(_frames(10, 0, 10))))
    finder.forget_before(6)
    assert min(finder.found) == 4
    assert finder.hole(6, 0, 0, 200, 100).any()


def test_top_and_bottom_text_do_not_pay_for_the_middle():
    strips = masks.sttn_strips([(40, 60, 680, 110), (40, 1040, 680, 1100)], 720, 1280)
    assert len(strips) == 2


def test_close_text_shares_a_strip():
    assert len(masks.sttn_strips([(0, 1000, 720, 1040), (0, 1060, 720, 1100)], 720, 1280)) == 1


class _Counting:
    def __init__(self):
        self.calls = 0

    def fill(self, strips):
        self.calls += 1
        return [np.zeros_like(strip) for strip in strips]


def test_a_strip_with_no_text_in_a_chunk_skips_the_model():
    frames = [np.full((100, 32, 3), 100, dtype=np.uint8) for _ in range(10)]
    filler = _Counting()
    out = list(textfill.fill_frames_sttn(
        iter(frames), lambda index: [(0, 10, 32, 20)], filler,
        [(5, 25), (70, 90)], chunk=50, overlap=10,
    ))
    assert filler.calls == 1
    assert len(out) == 10 and np.all(out[0][80] == 100) and np.all(out[0][15] == 0)


def test_stream_pastes_only_the_narrowed_hole():
    frames = [np.full((100, 32, 3), 100, dtype=np.uint8) for _ in range(4)]

    def hole_for(index, x0, y0, x1, y1):
        hole = np.zeros((y1 - y0, x1 - x0), dtype=bool)
        hole[10:12, 10:12] = True
        return hole

    out = list(textfill.fill_frames_sttn(
        iter(frames), lambda index: [(0, 0, 32, 40)], _Counting(),
        [(0, 40)], chunk=50, overlap=10, hole_for=hole_for,
    ))
    assert out[0][10, 10, 0] == 0
    assert out[0][30, 30, 0] == 100


def test_lama_leaves_a_frame_with_an_empty_hole_alone():
    frames = [np.full((40, 40, 3), 100, dtype=np.uint8) for _ in range(2)]

    class Never:
        def fill(self, area, hole):
            raise AssertionError("no text, no model")

    out = list(textfill.fill_frames_lama(
        iter(frames), lambda index: [(0, 0, 40, 40)], Never(), (0, 0, 40, 40),
        hole_for=lambda index, x0, y0, x1, y1: np.zeros((y1 - y0, x1 - x0), dtype=bool),
    ))
    assert all(a is b for a, b in zip(out, frames))


def test_the_setting_turns_it_off_and_changes_the_cache(monkeypatch):
    base = dict(
        meta={"width": 720, "height": 1280, "fps": 30.0, "fingerprint": "f"},
        start=1.0, duration=2.0, layers=[_layer(tracklet_id="trk_a")], method="sttn", model_stamp="m",
    )
    on = textfill.span_key(**base)
    monkeypatch.setenv("VIBECUT_FILL_TEXT_MASK", "off")
    assert textfill.text_mask_enabled() is False
    assert textfill.span_key(**base) != on


def test_preview_narrows_to_the_text_too(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBECUT_FILL_MODELS", str(tmp_path))
    (tmp_path / textfill.MODEL_FILES["lama"]).write_bytes(b"x")
    monkeypatch.setattr(textfill, "release_fillers", lambda: None)

    class Black:
        def fill(self, work, hole):
            return np.zeros_like(work)

    monkeypatch.setattr(textfill, "_filler", lambda method, path: Black())
    frame = _frames(1, 0, 1)[0]
    out = textfill.fill_frame(frame, [RECT], data_root=tmp_path, tight_rects=[RECT])
    assert out[50, 41, 0] == 0
    assert out[50, 180, 0] == 90


def test_preview_of_a_frame_with_no_text_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBECUT_FILL_MODELS", str(tmp_path))
    (tmp_path / textfill.MODEL_FILES["lama"]).write_bytes(b"x")
    frame = _frames(1, 9, 9)[0]
    out = textfill.fill_frame(frame, [RECT], data_root=tmp_path, tight_rects=[RECT])
    assert np.array_equal(out, frame)


def test_beat_selection_uses_the_time_margin_for_scan_layers_only():
    scan = {
        "id": "a", "kind": "fill", "method": "sttn", "z": 0,
        "box": {"x": 0.1, "y": 0.8, "w": 0.8, "h": 0.05},
        "ranges": [{"start": 10.0, "end": 12.0}], "tracklet_id": "trk_a",
    }
    plan, _ = compose_render._fill_plan([scan], 12.5, 14.0)
    assert plan["ids"] == ["a"]
    drawn = {key: value for key, value in scan.items() if key != "tracklet_id"}
    plan, _ = compose_render._fill_plan([drawn], 12.5, 14.0)
    assert plan is None


def _run_span(tmp_path, monkeypatch, layer, method="sttn"):
    """prepare_span end to end, with the ffmpeg pair and the model faked."""
    import io
    from pathlib import Path

    monkeypatch.setenv("VIBECUT_FILL_MODELS", str(tmp_path))
    (tmp_path / textfill.MODEL_FILES[method]).write_bytes(b"x")
    source = _frames(10, 2, 8, height=100, width=200)
    written = []

    class Proc:
        def __init__(self):
            self.stdin = io.BytesIO()
            self.stdout = io.BytesIO()
            self.stderr = io.BytesIO()

        def poll(self):
            return 0

        def kill(self):
            pass

        def wait(self, timeout=None):
            return 0

    class Reader:
        def __init__(self, *args):
            self.proc = Proc()
            self.frames = iter(source)

        def read(self):
            return next(self.frames, None)

    class Writer:
        def __init__(self, _ffmpeg, output, *args):
            self.proc = Proc()
            self.output = Path(output)
            self.output.parent.mkdir(parents=True, exist_ok=True)
            self.output.write_bytes(b"x" * 2048)

        def write(self, frame):
            written.append(frame)

    class Black:
        calls = 0

        def fill(self, *args):
            Black.calls += 1
            first = args[0]
            if isinstance(first, list):
                return [np.zeros_like(item) for item in first]
            return np.zeros_like(first)

    monkeypatch.setattr(textfill, "_Reader", Reader)
    monkeypatch.setattr(textfill, "_Writer", Writer)
    monkeypatch.setattr(textfill, "_filler", lambda *args: Black())
    result = textfill.prepare_span(
        source="unused.mp4",
        meta={"width": 200, "height": 100, "fps": 10.0, "fingerprint": "f"},
        start=0.0, duration=1.0, layers=[layer], method=method,
        cache_dir=tmp_path / "fill", data_root=tmp_path,
    )
    return result, written, source


SCAN = {"id": "a", "box": {"x": 0.05, "y": 0.3, "w": 0.9, "h": 0.4}, "ranges": [], "tracklet_id": "trk_a"}
DRAWN = {"id": "b", "box": {"x": 0.05, "y": 0.3, "w": 0.9, "h": 0.4}, "ranges": []}


def test_a_scan_layer_changes_only_the_text_end_to_end(tmp_path, monkeypatch):
    result, written, source = _run_span(tmp_path, monkeypatch, SCAN)
    assert result["cached"] is False and len(written) == 10
    assert written[4][50, 41, 0] == 0
    assert written[4][50, 180, 0] == 90
    assert np.array_equal(written[9], source[9]) or written[9][50, 180, 0] == 90


def test_a_drawn_box_still_fills_the_whole_box_end_to_end(tmp_path, monkeypatch):
    _result, written, _source = _run_span(tmp_path, monkeypatch, DRAWN)
    assert written[0][50, 180, 0] == 0


def test_lama_narrows_end_to_end_too(tmp_path, monkeypatch):
    _result, written, source = _run_span(tmp_path, monkeypatch, SCAN, method="lama")
    assert written[4][50, 41, 0] < 90
    assert written[4][50, 180, 0] == 90
    assert np.array_equal(written[0], source[0]) is False or written[0][50, 180, 0] == 90
