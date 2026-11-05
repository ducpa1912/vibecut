"""AI text fill: masks, work areas, key frames, the Edit kind and the render hook.

Ported from Studio's tests for the same code, LaMa only.

Arrays and fake fillers only. No media file is created or read.
"""

from __future__ import annotations

import io
import threading
from pathlib import Path

import numpy as np
import pytest

import compose_render
import edits
import render
import textfill
from textfill import mask as masks


def _layer(**extra):
    base = {"id": "cl01", "kind": "fill", "box": {"x": 0.1, "y": 0.8, "w": 0.8, "h": 0.1}}
    base.update(extra)
    return base


# --- masks -----------------------------------------------------------------

def test_layer_rect_pads_by_share_of_height_and_clips():
    rect = masks.layer_rect(_layer(), 100, 200)
    # h = 20 px, pad = max(3, 1.2) = 3
    assert rect == (7, 157, 93, 183)
    edge = masks.layer_rect(_layer(box={"x": 0.0, "y": 0.9, "w": 1.0, "h": 0.1}), 100, 200)
    assert edge[0] == 0 and edge[2] == 100 and edge[3] == 200


def test_detected_layers_get_a_time_margin_manual_layers_do_not():
    ranges = [{"start": 2.0, "end": 3.0}]
    manual = masks.frame_rects([_layer(ranges=ranges)], start=0.0, fps=2.0, frames=10, width=100, height=100)
    detected = masks.frame_rects(
        [_layer(ranges=ranges, tracklet_id="t1")], start=0.0, fps=2.0, frames=10, width=100, height=100,
    )
    # Frame centres: 0.25, 0.75, ... 4.75
    assert [bool(r) for r in manual] == [False, False, False, False, True, True, False, False, False, False]
    flags = [bool(r) for r in detected]
    assert flags[2] is False and flags[3] is True and flags[5] is True and flags[7] is False


def test_layer_without_ranges_is_on_for_every_frame():
    rects = masks.frame_rects([_layer()], start=5.0, fps=10.0, frames=4, width=50, height=50)
    assert all(rects)


def test_feather_keeps_mask_at_one_and_zero_beyond_radius():
    hole = np.zeros((20, 20), dtype=bool)
    hole[8:12, 8:12] = True
    alpha = masks.feather(hole, radius=3)
    assert np.all(alpha[hole] == 1.0)
    far = np.ones_like(hole)
    far[5:15, 5:15] = False
    assert np.all(alpha[far] == 0.0)
    assert alpha[7, 10] > 0.0


def test_paste_leaves_pixels_outside_alpha_bit_identical():
    rng = np.random.default_rng(1)
    original = rng.integers(0, 256, (16, 16, 3), dtype=np.uint8)
    filled = np.full_like(original, 7)
    hole = np.zeros((16, 16), dtype=bool)
    hole[4:8, 4:8] = True
    alpha = masks.feather(hole, radius=2)
    out = masks.paste(original, filled, alpha)
    assert np.array_equal(out[alpha == 0], original[alpha == 0])
    assert np.all(out[hole] == 7)


def test_lama_area_keeps_context_around_the_union():
    area = masks.lama_area([(100, 500, 300, 540), (120, 560, 280, 600)], 720, 1280)
    assert area == (50, 450, 350, 650)


# --- chunking --------------------------------------------------------------

class _LamaFake:
    def __init__(self):
        self.calls = 0

    def fill(self, area, hole):
        self.calls += 1
        return np.full_like(area, 50 if self.calls == 1 else 250)


def test_lama_stream_fills_only_masked_frames_and_carries_a_little():
    frames = [np.full((60, 60, 3), 10, dtype=np.uint8) for _ in range(4)]
    rect = (20, 20, 40, 30)
    table = {0: [rect], 1: [rect], 2: [], 3: [rect]}
    fake = _LamaFake()
    out = list(textfill.fill_frames_lama(
        iter(frames), lambda index: table[index], fake, (0, 0, 60, 60),
    ))
    assert fake.calls == 3
    assert out[0][25, 30, 0] == 50
    # Frame 1 keeps 30% of frame 0's fill.
    assert out[1][25, 30, 0] == round(250 * 0.7 + 50 * 0.3)
    assert np.array_equal(out[2], frames[2])
    # After a gap, nothing is carried.
    assert out[3][25, 30, 0] == 250
    assert np.all(out[1][:10] == 10)


def test_the_stream_checks_cancel_before_running_the_model():
    class Uncalled:
        def fill(self, *args):
            raise AssertionError("the model ran after cancel")

    frames = [np.zeros((40, 32, 3), dtype=np.uint8) for _ in range(4)]
    with pytest.raises(textfill.FillCancelled):
        list(textfill.fill_frames_lama(
            iter(frames), lambda index: [(8, 20, 24, 28)], Uncalled(), (0, 0, 32, 40),
            cancelled=lambda: True,
        ))


# --- prepare_span guards ---------------------------------------------------

META = {"width": 720, "height": 1280, "fps": 30.0, "fingerprint": "x:1:2"}


def _ready_model(tmp_path: Path, method: str = "lama") -> Path:
    directory = tmp_path / "models" / "fill"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / textfill.MODEL_FILES[method]).write_bytes(b"x" * 10)
    return directory


def test_prepare_span_returns_none_when_no_layer_touches_the_span(tmp_path):
    layer = _layer(ranges=[{"start": 50.0, "end": 52.0}])
    result = textfill.prepare_span(
        source="unused.mp4", meta=META, start=0.0, duration=3.0, layers=[layer],
        method="lama", cache_dir=tmp_path / "fill", data_root=tmp_path,
    )
    assert result is None


def test_prepare_span_names_the_missing_model(tmp_path, monkeypatch):
    monkeypatch.delenv("VIBECUT_FILL_MODELS", raising=False)
    with pytest.raises(textfill.FillError, match="lama_fp32.onnx"):
        textfill.prepare_span(
            source="unused.mp4", meta=META, start=0.0, duration=3.0, layers=[_layer()],
            method="lama", cache_dir=tmp_path / "fill", data_root=tmp_path,
        )


def test_prepare_span_reuses_a_cached_clip(tmp_path, monkeypatch):
    models = tmp_path / "models" / "fill"
    models.mkdir(parents=True)
    (models / "lama_fp32.onnx").write_bytes(b"x" * 10)
    monkeypatch.delenv("VIBECUT_FILL_MODELS", raising=False)
    key = textfill.span_key(
        meta=META, start=1.0, duration=2.0, layers=[_layer()], method="lama",
        model_stamp=textfill._model_stamp(models / "lama_fp32.onnx"),
    )
    cache = tmp_path / "fill"
    cache.mkdir()
    (cache / f"{key}.mp4").write_bytes(b"0" * 2048)
    result = textfill.prepare_span(
        source="unused.mp4", meta=META, start=1.0, duration=2.0, layers=[_layer()],
        method="lama", cache_dir=cache, data_root=tmp_path,
    )
    assert result == {"path": str(cache / f"{key}.mp4"), "key": key, "cached": True, "method": "lama"}


def test_prepare_span_cancels_while_waiting_for_the_fill_lock(tmp_path, monkeypatch):
    monkeypatch.delenv("VIBECUT_FILL_MODELS", raising=False)
    _ready_model(tmp_path)
    cancel = threading.Event()
    textfill._LOCK.acquire()
    timer = threading.Timer(0.05, cancel.set)
    timer.start()
    try:
        with pytest.raises(textfill.FillCancelled):
            textfill.prepare_span(
                source="unused.mp4", meta=META, start=0.0, duration=1.0,
                layers=[_layer()], method="lama", cache_dir=tmp_path / "fill",
                data_root=tmp_path, cancel_event=cancel,
            )
    finally:
        timer.cancel()
        textfill._LOCK.release()


def test_prepare_span_checks_cancel_before_loading_the_model(tmp_path, monkeypatch):
    monkeypatch.delenv("VIBECUT_FILL_MODELS", raising=False)
    _ready_model(tmp_path)
    loaded = []
    monkeypatch.setattr(textfill, "_filler", lambda *args: loaded.append(args))
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(textfill.FillCancelled):
        textfill.prepare_span(
            source="unused.mp4", meta=META, start=0.0, duration=1.0,
            layers=[_layer()], method="lama", cache_dir=tmp_path / "fill",
            data_root=tmp_path, cancel_event=cancel,
        )
    assert loaded == []


def test_prepare_span_kills_ffmpeg_and_removes_the_part_file_on_failure(tmp_path, monkeypatch):
    monkeypatch.delenv("VIBECUT_FILL_MODELS", raising=False)
    _ready_model(tmp_path)
    processes = []

    class FakeProc:
        def __init__(self):
            self.stdin = io.BytesIO()
            self.stdout = io.BytesIO()
            self.stderr = io.BytesIO()
            self.killed = False
            processes.append(self)

        def poll(self):
            return None

        def kill(self):
            self.killed = True

        def wait(self, timeout=None):
            return 1

    class FakeReader:
        def __init__(self, *args):
            self.proc = FakeProc()

        def read(self):
            raise textfill.FillCancelled("stop")

    class FakeWriter:
        def __init__(self, _ffmpeg, output, *args):
            self.proc = FakeProc()
            Path(output).write_bytes(b"partial")

    monkeypatch.setattr(textfill, "_Reader", FakeReader)
    monkeypatch.setattr(textfill, "_Writer", FakeWriter)
    monkeypatch.setattr(textfill, "_filler", lambda *args: object())

    with pytest.raises(textfill.FillCancelled):
        textfill.prepare_span(
            source="unused.mp4", meta=META, start=0.0, duration=1.0,
            layers=[_layer()], method="lama", cache_dir=tmp_path / "fill",
            data_root=tmp_path,
        )
    assert processes and all(proc.killed for proc in processes)
    assert list((tmp_path / "fill").iterdir()) == []


def test_span_key_changes_with_box_and_span():
    base = dict(meta=META, start=1.0, duration=2.0, layers=[_layer()], method="lama", model_stamp="m")
    key = textfill.span_key(**base)
    assert textfill.span_key(**{**base, "start": 1.5}) != key
    moved = _layer(box={"x": 0.1, "y": 0.7, "w": 0.8, "h": 0.1})
    assert textfill.span_key(**{**base, "layers": [moved]}) != key
    painted = _layer(mask={
        "space": "source",
        "strokes": [{"id": "st_a", "r": 0.03, "points": [{"x": 0.4, "y": 0.7}]}],
    })
    painted_key = textfill.span_key(**{**base, "layers": [painted]})
    more = _layer(mask={
        "space": "source",
        "strokes": [{"id": "st_a", "r": 0.03, "points": [
            {"x": 0.4, "y": 0.7}, {"x": 0.5, "y": 0.7},
        ]}],
    })
    assert textfill.span_key(**{**base, "layers": [more]}) != painted_key


def test_model_signature_changes_with_the_file_and_names_missing_models(tmp_path):
    directory = tmp_path / "models"
    directory.mkdir()
    missing = textfill.model_signature(["lama"], directory)
    path = directory / textfill.MODEL_FILES["lama"]
    path.write_bytes(b"a" * 10)
    first = textfill.model_signature(["lama"], directory)
    assert first != missing
    path.write_bytes(b"a" * 20)
    assert textfill.model_signature(["lama"], directory) != first
    assert textfill.model_signature([], directory) != first


def test_release_fillers_drops_loaded_sessions():
    textfill._FILLERS[("lama", "x")] = object()
    textfill._FILLERS[("lama", "y")] = object()
    textfill.release_fillers()
    assert textfill._FILLERS == {}


def test_models_dir_follows_the_lane_data_folder(tmp_path, monkeypatch):
    monkeypatch.delenv("VIBECUT_FILL_MODELS", raising=False)
    assert textfill.models_dir(tmp_path) == tmp_path / "models" / "fill"
    monkeypatch.setenv("VIBECUT_FILL_MODELS", str(tmp_path / "other"))
    assert textfill.models_dir(tmp_path) == tmp_path / "other"


# --- Edit kind -------------------------------------------------------------

def test_fill_kind_defaults_to_lama_and_checks_the_engine():
    layer = edits.normalize_clean([_layer()])[0]
    assert layer["kind"] == "fill" and layer["method"] == "lama"
    assert textfill.DEFAULT_METHOD == "lama"
    # A layer saved with STTN opens as LaMa: Classic has no other engine.
    assert edits.normalize_clean([_layer(method="sttn")])[0]["method"] == "lama"
    assert edits.normalize_clean([_layer(method="LaMa")])[0]["method"] == "lama"
    with pytest.raises(edits.EditError, match="method"):
        edits.normalize_clean([_layer(method="propainter")])


def test_other_kinds_carry_no_engine():
    layer = edits.normalize_clean([_layer(kind="blur", method="lama")])[0]
    assert "method" not in layer


# --- compose and render ----------------------------------------------------

STORY_REF = {"set_id": "cs_1", "story_id": "s1", "clip_hash": "a" * 16, "title": "Story", "duration": 4.0, "clip_count": 1}


def _edit(clean):
    return edits.build_edit(story_ref=dict(STORY_REF), aspect="9:16", created=1.0, clean=clean)


CLIPS = [{"scene": 0, "start": 0.0, "end": 4.0, "dur": 4.0, "role": "hook"}]
SOURCE = {"width": 720, "height": 1280}


def test_compile_puts_fill_on_the_segment_not_in_the_filter_chain():
    compiled = compose_render.compile_edit(
        _edit([_layer(ranges=[{"start": 1.0, "end": 2.0}])]), clips=CLIPS, source=SOURCE,
    )
    segment = compiled["segments"][0]
    assert segment["fill"]["method"] == "lama"
    assert segment["fill"]["ids"] == ["cl01"]
    assert segment["fill"]["layers"][0]["ranges"] == [{"start": 1.0, "end": 2.0}]
    assert not any("delogo" in item for item in segment["pre_filters"])
    assert segment["pre_filters"] == []


def test_compile_has_no_fill_when_the_layer_is_off_the_beat():
    compiled = compose_render.compile_edit(
        _edit([_layer(ranges=[{"start": 10.0, "end": 12.0}])]), clips=CLIPS, source=SOURCE,
    )
    assert compiled["segments"][0]["fill"] is None


def test_fill_plan_orders_layers_by_z_not_input_order():
    plan, warnings = compose_render._fill_plan([
        _layer(id="cl09", method="lama", z=9),
        _layer(id="cl01", method="lama", z=1),
    ], 0.0, 4.0)
    assert plan["method"] == "lama"
    assert plan["ids"] == ["cl01", "cl09"]
    assert warnings == []


def test_render_prepare_fills_maps_progress_and_errors(tmp_path, monkeypatch):
    job_dir = tmp_path / "jobs" / "j1"
    job_dir.mkdir(parents=True)
    calls = []

    def fake_prepare(**kwargs):
        calls.append(kwargs)
        kwargs["progress"](0.5, "half")
        return {"path": "x.mp4", "key": "k1", "cached": False, "method": kwargs["method"]}

    monkeypatch.setattr(textfill, "prepare_span", fake_prepare)
    seen = []
    segments = [
        {"start": 0.0, "frames": 30, "fill": None},
        {"start": 4.0, "frames": 60, "fill": {"method": "lama", "layers": [_layer()]}},
    ]
    results = render._prepare_fills("src.mp4", {}, job_dir, segments, lambda f, m: seen.append((f, m)), None)
    assert results[0] is None and results[1]["key"] == "k1"
    assert calls[0]["duration"] == 2.0 and calls[0]["cache_dir"] == job_dir / "fill"
    assert calls[0]["data_root"] == tmp_path
    assert 0.02 < seen[0][0] < 0.45 and "Filling text" in seen[0][1]

    def broken(**kwargs):
        raise textfill.FillError("model missing")

    monkeypatch.setattr(textfill, "prepare_span", broken)
    with pytest.raises(render.PipelineError, match="model missing"):
        render._prepare_fills("src.mp4", {}, job_dir, segments, lambda f, m: None, None)

    def cancelled(**kwargs):
        raise textfill.FillCancelled("stop")

    monkeypatch.setattr(textfill, "prepare_span", cancelled)
    with pytest.raises(render.RenderCancelled):
        render._prepare_fills("src.mp4", {}, job_dir, segments, lambda f, m: None, threading.Event())


def test_render_prepare_fills_releases_models_after_the_pass(tmp_path, monkeypatch):
    job_dir = tmp_path / "jobs" / "j1"
    job_dir.mkdir(parents=True)
    released = []
    monkeypatch.setattr(
        textfill, "prepare_span",
        lambda **kwargs: {"path": "x.mp4", "key": "k1", "cached": False, "method": "lama"},
    )
    monkeypatch.setattr(textfill, "release_fillers", lambda: released.append(True))
    segments = [{"start": 0.0, "frames": 30, "fill": {"method": "lama", "layers": [_layer()]}}]
    render._prepare_fills("src.mp4", {}, job_dir, segments, lambda f, m: None, None)
    assert released == [True]


def test_render_master_key_includes_the_fill_model_signature():
    source = Path(render.__file__).read_text(encoding="utf-8")
    assert "textfill.model_signature(" in source
    assert '"fill_models": fill_sig' in source


def test_segment_cache_key_includes_the_fill():
    args = ({"fingerprint": "f"}, {}, 1.0, 30, 1080, 1920, "final", "x264", False, False)
    plain = render._segment_cache_key(*args)
    filled = render._segment_cache_key(*args, fill_key="k1")
    assert plain != filled
    assert render._segment_cache_key(*args, fill_key="k2") != filled


# --- network shape (needs torch, skipped in CI) ----------------------------

# --- Studio panel ----------------------------------------------------------

# --- single-frame preview --------------------------------------------------

def test_fill_frame_runs_lama_one_frame_and_leaves_the_rest_alone(tmp_path, monkeypatch):
    monkeypatch.delenv("VIBECUT_FILL_MODELS", raising=False)
    models = textfill.models_dir(tmp_path)
    models.mkdir(parents=True)
    (models / "lama_fp32.onnx").write_bytes(b"model")

    class FakeFiller:
        def fill(self, area, hole):
            out = area.copy()
            out[hole] = np.array([0, 255, 0], dtype=np.uint8)
            return out

    monkeypatch.setattr(textfill, "_filler", lambda method, path: FakeFiller())
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    rects = [(20, 70, 180, 90)]
    out = textfill.fill_frame(frame, rects, data_root=tmp_path)

    assert out.shape == frame.shape
    assert np.array_equal(out[:60], frame[:60])
    assert (out[70:90, 20:180] == np.array([0, 255, 0])).any()
    # A saved STTN box previews as LaMa.
    assert textfill.fill_frame(frame, rects, data_root=tmp_path, method="sttn").shape == frame.shape


def test_fill_frame_names_the_missing_lama_model(tmp_path, monkeypatch):
    monkeypatch.delenv("VIBECUT_FILL_MODELS", raising=False)
    frame = np.zeros((40, 40, 3), dtype=np.uint8)
    with pytest.raises(textfill.FillError, match="LaMa"):
        textfill.fill_frame(frame, [(5, 20, 30, 30)], data_root=tmp_path)


# --- LaMa key frames ------------------------------------------------------

class _CountingFiller:
    def __init__(self):
        self.calls = 0
        self.holes = []

    def fill(self, area, hole):
        self.calls += 1
        self.holes.append(hole.copy())
        return np.full(area.shape, self.calls * 10 % 256, dtype=np.uint8)


def _keyed(frames, rects, step=6):
    filler = _CountingFiller()
    rects_at = rects if callable(rects) else (lambda index: rects)
    out = list(textfill.fill_frames_lama(
        iter(frames), rects_at, filler, (0, 0, 40, 40), step=step,
    ))
    return out, filler


def test_a_still_picture_runs_the_model_on_key_frames_only():
    frames = [np.full((40, 40, 3), 100, dtype=np.uint8) for _ in range(30)]
    out, filler = _keyed(frames, [(5, 5, 20, 20)])
    assert len(out) == 30
    # One fill starts the first run, then one fill ends each run of six.
    assert filler.calls <= 6
    # Outside the hole and its feather, every pixel is the source's.
    assert all((frame[30:, 30:] == 100).all() for frame in out)


def test_a_moving_picture_runs_the_model_on_every_frame():
    frames = [np.full((40, 40, 3), (index * 40) % 256, dtype=np.uint8) for index in range(12)]
    _, filler = _keyed(frames, [(5, 5, 20, 20)])
    assert filler.calls == 12


def test_a_key_fill_covers_every_hole_in_its_run():
    frames = [np.full((40, 40, 3), 100, dtype=np.uint8) for _ in range(6)]
    filler = _CountingFiller()

    def hole_for(index, x0, y0, x1, y1):
        hole = np.zeros((y1 - y0, x1 - x0), dtype=bool)
        hole[5:10, 5:(10 if index < 3 else 20)] = True
        return hole

    list(textfill.fill_frames_lama(
        iter(frames), lambda index: [(5, 5, 20, 10)], filler, (0, 0, 40, 40),
        step=6, hole_for=hole_for,
    ))
    assert filler.holes[0][6, 18]


def test_frames_without_text_never_reach_the_model():
    frames = [np.full((40, 40, 3), 100, dtype=np.uint8) for _ in range(12)]
    out, filler = _keyed(frames, lambda index: [(5, 5, 20, 20)] if 4 <= index < 8 else [])
    assert len(out) == 12
    assert (out[0] == 100).all() and (out[11] == 100).all()
    assert filler.calls <= 2


def test_blended_frames_change_gradually_between_two_fills():
    frames = [np.full((40, 40, 3), 100, dtype=np.uint8) for _ in range(6)]
    out, _ = _keyed(frames, [(5, 5, 20, 20)])
    middle = [int(frame[10, 10, 0]) for frame in out]
    assert middle[0] != middle[-1]
    assert middle in (sorted(middle), sorted(middle, reverse=True))


def test_key_rate_follows_the_frame_rate_and_can_be_turned_off(monkeypatch):
    assert textfill.lama_step(30.0) == 10
    assert textfill.lama_step(60.0) == 20
    monkeypatch.setenv("VIBECUT_FILL_LAMA_KEYS", "0")
    assert textfill.lama_step(30.0) == 1


def test_the_key_rate_is_part_of_the_clip_key(monkeypatch):
    base = dict(meta=META, start=1.0, duration=2.0, layers=[_layer()], model_stamp="m")
    lama = textfill.span_key(method="lama", **base)
    monkeypatch.setenv("VIBECUT_FILL_LAMA_KEYS", "0")
    assert textfill.span_key(method="lama", **base) != lama


def test_no_carry_keeps_each_fill_as_it_is():
    frames = [np.full((40, 40, 3), 100, dtype=np.uint8) for _ in range(3)]
    filler = _CountingFiller()
    out = list(textfill.fill_frames_lama(
        iter(frames), lambda index: [(5, 5, 20, 20)], filler, (0, 0, 40, 40), carry=0.0,
    ))
    assert int(out[2][10, 10, 0]) == 30


# --- Tight work areas and flexible LaMa ------------------------------------

def _pb_varint(value):
    out = bytearray()
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def _pb_len(field, body):
    return _pb_varint(field << 3 | 2) + _pb_varint(len(body)) + body


def _pb_value_info(name, dims):
    shape = b"".join(_pb_len(1, _pb_varint(1 << 3) + _pb_varint(dim)) for dim in dims)
    tensor = _pb_varint(1 << 3) + _pb_varint(1) + _pb_len(2, shape)
    return _pb_len(1, name.encode()) + _pb_len(2, _pb_len(1, tensor))


def test_free_input_size_names_only_height_and_width():
    from textfill import lama

    graph = (
        _pb_len(1, b"node bytes")
        + _pb_len(11, _pb_value_info("image", [1, 3, 512, 512]))
        + _pb_len(12, _pb_value_info("output", [1, 3, 512, 512]))
        + _pb_len(13, _pb_value_info("inner", [1, 3, 256, 256]))
    )
    model = _pb_varint(1 << 3) + _pb_varint(8) + _pb_len(7, graph)
    freed = lama.free_input_size(model)
    assert b"node bytes" in freed
    assert b"image_3" in freed and b"image_4" in freed and b"output_4" in freed
    assert b"inner" not in freed
    assert lama.free_input_size(freed).count(b"image_3") == 1


def test_a_strip_of_text_runs_as_a_strip():
    from textfill import lama

    assert lama.input_size(53, 512, True) == (64, 512)
    assert lama.input_size(110, 512, True) == (112, 512)
    assert lama.input_size(53, 512, False) == (512, 512)


def test_text_far_apart_gets_two_work_areas_and_close_text_one():
    apart = textfill.masks.lama_areas([(100, 100, 900, 150), (100, 1700, 900, 1750)], 1080, 1920)
    assert len(apart) == 2
    close = textfill.masks.lama_areas([(100, 100, 900, 150), (100, 155, 900, 205)], 1080, 1920)
    assert len(close) == 1


def test_a_box_inside_another_is_dropped():
    assert textfill.masks.without_contained(
        [(0, 0, 100, 100), (10, 10, 20, 20), (0, 0, 100, 100), (90, 90, 120, 120)],
    ) == [(0, 0, 100, 100), (90, 90, 120, 120)]


def test_each_work_area_gets_its_own_fill_and_no_more():
    class Sizes:
        def __init__(self):
            self.shapes = []

        def fill(self, area, hole):
            self.shapes.append(area.shape[:2])
            return np.full(area.shape, 7, dtype=np.uint8)

    frames = [np.full((400, 200, 3), 100, dtype=np.uint8) for _ in range(4)]
    filler = Sizes()
    out = list(textfill.fill_frames_lama(
        iter(frames), lambda index: [(20, 20, 180, 40), (20, 360, 180, 380)], filler, None, step=4,
    ))
    assert len(out) == 4
    # Two areas, begin and end each, and neither reads the middle of the picture.
    assert len(filler.shapes) == 4
    assert all(height < 120 for height, _width in filler.shapes)
    assert (out[0][200, 100] == 100).all()


# --- One fill for a whole line ---------------------------------------------

def test_a_still_line_uses_one_fill_for_all_its_frames():
    frames = [np.full((40, 40, 3), 100, dtype=np.uint8) for _ in range(40)]
    filler = _CountingFiller()
    out = list(textfill.fill_frames_lama(
        iter(frames), lambda index: [(5, 5, 20, 20)], filler, (0, 0, 40, 40),
        step=6, reuse_still=True,
    ))
    assert len(out) == 40
    assert filler.calls == 1


def test_a_new_line_gets_its_own_fill():
    frames = [np.full((40, 40, 3), 100, dtype=np.uint8) for _ in range(20)]
    filler = _CountingFiller()
    list(textfill.fill_frames_lama(
        iter(frames),
        lambda index: [(5, 5, 20, 20)] if index < 10 else [(5, 22, 20, 35)],
        filler, (0, 0, 40, 40), step=6, reuse_still=True,
    ))
    assert filler.calls == 2


def test_a_moving_shot_falls_back_to_key_frames_with_reuse_on():
    frames = [np.full((40, 40, 3), (index * 40) % 256, dtype=np.uint8) for index in range(12)]
    filler = _CountingFiller()
    out = list(textfill.fill_frames_lama(
        iter(frames), lambda index: [(5, 5, 20, 20)], filler, (0, 0, 40, 40),
        step=6, reuse_still=True,
    ))
    assert len(out) == 12
    # No worse than a model run per frame, and every frame still comes out.
    assert filler.calls <= 12


def test_reuse_is_part_of_the_clip_key():
    base = dict(meta=META, start=1.0, duration=2.0, layers=[_layer()], model_stamp="m")
    assert textfill.span_key(method="lama", reuse_still=True, **base) != textfill.span_key(method="lama", **base)


# --- LaMa only -------------------------------------------------------------

def test_classic_offers_lama_and_nothing_else():
    assert textfill.METHODS == ("lama",)
    assert textfill.DEFAULT_METHOD == "lama"
    assert edits.FILL_METHODS == ("lama",)
    root = Path(__file__).resolve().parent.parent
    assert not (root / "textfill" / "sttn.py").exists()
    assert not (root / "textfill" / "classic.py").exists()


def test_a_saved_sttn_layer_still_renders_as_lama(tmp_path):
    assert textfill.known_method("sttn") == "lama"
    assert textfill.model_path("sttn", tmp_path).name == "lama_fp32.onnx"
    with pytest.raises(textfill.FillError):
        textfill.known_method("propainter")
    (tmp_path / "lama_fp32.onnx").write_bytes(b"x" * 10)
    assert textfill.model_signature(["sttn"], tmp_path) == textfill.model_signature(["lama"], tmp_path)
