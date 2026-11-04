"""AI text fill: masks, work areas, chunking, the Edit kind and the render hook.

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
from textfill import sttn


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
    assert [bool(r) for r in detected] == [False, False, True, True, True, True, True, True, False, False]


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


def test_sttn_strips_are_full_width_16_by_3_and_stay_in_frame():
    width, height = 720, 1280
    strip = round(width * 3 / 16)
    one = masks.sttn_strips([(50, 1100, 670, 1160)], width, height)
    assert len(one) == 1
    y0, y1 = one[0]
    assert y1 - y0 == strip and y0 <= 1100 and y1 >= 1160
    bottom = masks.sttn_strips([(0, 1250, 720, 1280)], width, height)
    assert bottom == [(height - strip, height)]
    tall = masks.sttn_strips([(0, 100, 720, 500)], width, height)
    assert len(tall) == 3
    assert tall[0][0] == 100 and tall[-1][1] >= 500
    assert all(y1 - y0 == strip for y0, y1 in tall)


def test_lama_area_keeps_context_around_the_union():
    area = masks.lama_area([(100, 500, 300, 540), (120, 560, 280, 600)], 720, 1280)
    assert area == (50, 450, 350, 650)


# --- chunking --------------------------------------------------------------

def test_chunk_spans_cover_every_frame_with_overlap():
    assert sttn.chunk_spans(0) == []
    assert sttn.chunk_spans(30) == [(0, 30)]
    spans = sttn.chunk_spans(130, chunk=50, overlap=10)
    assert spans[0] == (0, 50) and spans[-1][1] == 130
    for (a0, a1), (b0, b1) in zip(spans, spans[1:]):
        assert b0 <= a1 - 10
    covered = set()
    for a, b in spans:
        covered.update(range(a, b))
    assert covered == set(range(130))


class _ConstantFiller:
    """Returns strips of a fixed value; counts calls."""

    def __init__(self, values):
        self.values = list(values)
        self.calls = 0

    def fill(self, strips):
        value = self.values[min(self.calls, len(self.values) - 1)]
        self.calls += 1
        return [np.full_like(strip, value) for strip in strips]


def test_sttn_stream_keeps_count_fills_mask_and_crossfades_overlap():
    frames = [np.full((40, 32, 3), 100, dtype=np.uint8) for _ in range(25)]
    rect = (8, 20, 24, 28)
    filler = _ConstantFiller([0, 200])
    out = list(textfill.fill_frames_sttn(
        iter(frames), lambda index: [rect], filler, [(16, 32)], chunk=15, overlap=5,
    ))
    assert len(out) == 25
    assert filler.calls == 2
    # Inside the mask: chunk 1 value, then a ramp to chunk 2 over the overlap.
    assert out[0][24, 16, 0] == 0
    ramp = [int(out[i][24, 16, 0]) for i in range(10, 15)]
    assert ramp == sorted(ramp) and 0 < ramp[0] < ramp[-1] < 200
    assert out[20][24, 16, 0] == 200
    # Far outside the mask: untouched.
    for frame in out:
        assert np.all(frame[:10] == 100)


def test_sttn_stream_skips_the_model_when_no_frame_has_text():
    frames = [np.zeros((40, 32, 3), dtype=np.uint8) for _ in range(12)]
    filler = _ConstantFiller([9])
    out = list(textfill.fill_frames_sttn(
        iter(frames), lambda index: [], filler, [(0, 6)], chunk=50, overlap=10,
    ))
    assert len(out) == 12 and filler.calls == 0
    assert all(np.array_equal(a, b) for a, b in zip(out, frames))


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


def test_the_streams_check_cancel_before_running_the_model():
    class Uncalled:
        def fill(self, *args):
            raise AssertionError("the model ran after cancel")

    frames = [np.zeros((40, 32, 3), dtype=np.uint8) for _ in range(4)]
    with pytest.raises(textfill.FillCancelled):
        list(textfill.fill_frames_sttn(
            iter(frames), lambda index: [(8, 20, 24, 28)], Uncalled(), [(16, 32)],
            chunk=50, overlap=10, cancelled=lambda: True,
        ))
    with pytest.raises(textfill.FillCancelled):
        list(textfill.fill_frames_lama(
            iter(frames), lambda index: [(8, 20, 24, 28)], Uncalled(), (0, 0, 32, 40),
            cancelled=lambda: True,
        ))


# --- prepare_span guards ---------------------------------------------------

META = {"width": 720, "height": 1280, "fps": 30.0, "fingerprint": "x:1:2"}


def _ready_model(tmp_path: Path, method: str = "sttn") -> Path:
    directory = tmp_path / "models" / "fill"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / textfill.MODEL_FILES[method]).write_bytes(b"x" * 10)
    return directory


def test_prepare_span_returns_none_when_no_layer_touches_the_span(tmp_path):
    layer = _layer(ranges=[{"start": 50.0, "end": 52.0}])
    result = textfill.prepare_span(
        source="unused.mp4", meta=META, start=0.0, duration=3.0, layers=[layer],
        method="sttn", cache_dir=tmp_path / "fill", data_root=tmp_path,
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
    (models / "sttn_infer_model.pth").write_bytes(b"x" * 10)
    monkeypatch.delenv("VIBECUT_FILL_MODELS", raising=False)
    key = textfill.span_key(
        meta=META, start=1.0, duration=2.0, layers=[_layer()], method="sttn",
        model_stamp=textfill._model_stamp(models / "sttn_infer_model.pth"),
    )
    cache = tmp_path / "fill"
    cache.mkdir()
    (cache / f"{key}.mp4").write_bytes(b"0" * 2048)
    result = textfill.prepare_span(
        source="unused.mp4", meta=META, start=1.0, duration=2.0, layers=[_layer()],
        method="sttn", cache_dir=cache, data_root=tmp_path,
    )
    assert result == {"path": str(cache / f"{key}.mp4"), "key": key, "cached": True, "method": "sttn"}


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
                layers=[_layer()], method="sttn", cache_dir=tmp_path / "fill",
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
            layers=[_layer()], method="sttn", cache_dir=tmp_path / "fill",
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
            layers=[_layer()], method="sttn", cache_dir=tmp_path / "fill",
            data_root=tmp_path,
        )
    assert processes and all(proc.killed for proc in processes)
    assert list((tmp_path / "fill").iterdir()) == []


def test_span_key_changes_with_engine_box_and_span():
    base = dict(meta=META, start=1.0, duration=2.0, layers=[_layer()], method="sttn", model_stamp="m")
    key = textfill.span_key(**base)
    assert textfill.span_key(**{**base, "method": "lama"}) != key
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
    missing = textfill.model_signature(["sttn", "lama"], directory)
    path = directory / textfill.MODEL_FILES["sttn"]
    path.write_bytes(b"a" * 10)
    first = textfill.model_signature(["sttn"], directory)
    assert first != missing
    path.write_bytes(b"a" * 20)
    assert textfill.model_signature(["sttn"], directory) != first
    assert textfill.model_signature([], directory) != first


def test_release_fillers_drops_loaded_sessions():
    textfill._FILLERS[("sttn", "x")] = object()
    textfill._FILLERS[("lama", "y")] = object()
    textfill.release_fillers()
    assert textfill._FILLERS == {}


def test_models_dir_follows_the_lane_data_folder(tmp_path, monkeypatch):
    monkeypatch.delenv("VIBECUT_FILL_MODELS", raising=False)
    assert textfill.models_dir(tmp_path) == tmp_path / "models" / "fill"
    monkeypatch.setenv("VIBECUT_FILL_MODELS", str(tmp_path / "other"))
    assert textfill.models_dir(tmp_path) == tmp_path / "other"


# --- Edit kind -------------------------------------------------------------

def test_fill_kind_defaults_to_sttn_and_checks_the_engine():
    layer = edits.normalize_clean([_layer()])[0]
    assert layer["kind"] == "fill" and layer["method"] == "sttn"
    assert edits.normalize_clean([_layer(method="LaMa")])[0]["method"] == "lama"
    with pytest.raises(edits.EditError, match="method"):
        edits.normalize_clean([_layer(method="propainter")])


def test_other_kinds_carry_no_engine():
    layer = edits.normalize_clean([_layer(kind="delogo", method="lama")])[0]
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
    assert segment["fill"]["method"] == "sttn"
    assert segment["fill"]["ids"] == ["cl01"]
    assert segment["fill"]["layers"][0]["ranges"] == [{"start": 1.0, "end": 2.0}]
    assert not any("delogo" in item for item in segment["pre_filters"])
    assert segment["pre_filters"] == []


def test_compile_has_no_fill_when_the_layer_is_off_the_beat():
    compiled = compose_render.compile_edit(
        _edit([_layer(ranges=[{"start": 10.0, "end": 12.0}])]), clips=CLIPS, source=SOURCE,
    )
    assert compiled["segments"][0]["fill"] is None


def test_compile_warns_when_one_beat_mixes_engines():
    compiled = compose_render.compile_edit(
        _edit([_layer(), _layer(id="cl02", method="lama", z=1)]), clips=CLIPS, source=SOURCE,
    )
    assert compiled["segments"][0]["fill"]["method"] == "lama"
    assert any(item["code"] == "fill_method_mixed" for item in compiled["warnings"])


def test_fill_plan_orders_layers_by_z_not_input_order():
    plan, warnings = compose_render._fill_plan([
        _layer(id="cl09", method="lama", z=9),
        _layer(id="cl01", method="sttn", z=1),
    ], 0.0, 4.0)
    assert plan["method"] == "lama"
    assert plan["ids"] == ["cl01", "cl09"]
    assert any(item["code"] == "fill_method_mixed" for item in warnings)


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
        lambda **kwargs: {"path": "x.mp4", "key": "k1", "cached": False, "method": "sttn"},
    )
    monkeypatch.setattr(textfill, "release_fillers", lambda: released.append(True))
    segments = [{"start": 0.0, "frames": 30, "fill": {"method": "sttn", "layers": [_layer()]}}]
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

def test_sttn_network_matches_the_checkpoint_layout():
    pytest.importorskip("torch")
    network = sttn._build_network()
    params = sum(p.numel() for p in network.parameters())
    assert params == 16_556_163
    keys = list(network.state_dict())
    assert keys[0] == "transformer.0.attention.query_embedding.weight"
    assert len(keys) == 112


# --- Studio panel ----------------------------------------------------------

def test_studio_clean_panel_offers_ai_fill():
    root = Path(__file__).resolve().parent.parent
    clean = (root / "static/studio/edit/layers/clean.js").read_text()
    model = (root / "static/studio/edit/model.js").read_text()
    assert '"fill"' in clean.split("const KIND_ORDER", 1)[1].split("\n", 1)[0]
    assert 'fill: "AI fill"' in model
    assert '["sttn",' in clean and '["lama",' in clean
    assert "Use AI fill for all" in clean


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
    with pytest.raises(textfill.FillError):
        textfill.fill_frame(frame, rects, data_root=tmp_path, method="sttn")


def test_fill_frame_names_the_missing_lama_model(tmp_path, monkeypatch):
    monkeypatch.delenv("VIBECUT_FILL_MODELS", raising=False)
    frame = np.zeros((40, 40, 3), dtype=np.uint8)
    with pytest.raises(textfill.FillError, match="LaMa"):
        textfill.fill_frame(frame, [(5, 20, 30, 30)], data_root=tmp_path)
