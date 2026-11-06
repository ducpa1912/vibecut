"""Classic's AI fill choices: engines, chip, camera following and the box swap."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

import app
import clean_source
import routes_classic
import textfill

ROOT = Path(__file__).resolve().parents[1]
OPTIONS = ROOT / "static/classic/clean-options.js"


def _picture(height=200, width=320, seed=3):
    rng = np.random.default_rng(seed)
    coarse = rng.integers(0, 255, (height // 8 + 2, width // 8 + 2, 3), dtype=np.uint8)
    return np.repeat(np.repeat(coarse, 8, axis=0), 8, axis=1)[:height, :width].copy()


class _Counting:
    def __init__(self):
        self.calls = 0

    def fill(self, area, mask):
        self.calls += 1
        out = area.copy()
        out[mask] = 128
        return out


def test_engines_match_the_offer_and_sttn_stays_retired():
    assert textfill.METHODS == ("lama", "migan", "telea", "ns")
    assert textfill.known_method("sttn") == "lama"
    assert routes_classic.CLASSIC_FILL_ENGINES == textfill.METHODS


def test_opencv_needs_no_model_and_mi_gan_says_what_is_missing(tmp_path):
    assert textfill.missing_model("telea", tmp_path) is None
    assert "migan_traced.pt" in textfill.missing_model("migan", tmp_path)


def test_a_cpu_choice_beats_the_gpu_default(tmp_path, monkeypatch):
    import textfill.torch_fill as torch_fill

    monkeypatch.delenv("VIBECUT_FILL_DEVICE", raising=False)
    monkeypatch.setattr(torch_fill, "gpu_possible", lambda: True)
    (tmp_path / "big-lama.pt").write_bytes(b"x")
    assert textfill.chosen_device("lama", None, tmp_path) == "gpu"
    assert textfill.chosen_device("lama", "cpu", tmp_path) == "cpu"
    assert textfill.chosen_device("telea", None, tmp_path) == "cpu"


def test_follow_changes_the_clip_and_only_for_keyed_engines():
    args = dict(
        meta={"fingerprint": "f", "width": 100, "height": 100, "fps": 25.0},
        start=0.0, duration=1.0, method="lama", model_stamp="m",
        layers=[{"box": {"x": 0, "y": 0, "w": 1, "h": 1}, "ranges": [], "fill_keys": 3.0}],
    )
    assert textfill.span_key(**args) != textfill.span_key(follow_motion=True, **args)
    assert textfill.span_key(**args) == textfill.span_key(follow_motion=False, **args)
    assert textfill._follow_on("telea", True) is False


def test_following_a_pan_needs_fewer_fills():
    pytest.importorskip("cv2")
    base = _picture(240, 400)
    frames = [base[20:220, 20 + index * 2:340 + index * 2].copy() for index in range(24)]

    def fills(follow):
        model = _Counting()
        out = list(textfill.fill_frames_lama(
            iter(frames), lambda _index: [(60, 80, 260, 120)], model, None, step=8, follow=follow,
            plan_for=lambda _index: (8, textfill.LAMA_MOTION_LIMIT, False),
        ))
        assert len(out) == len(frames)
        return model.calls

    assert fills(True) < fills(False)


def test_opencv_fills_a_hole_with_nothing_from_a_model():
    pytest.importorskip("cv2")
    from textfill.classic import ClassicFiller

    area = _picture(60, 80)
    mask = np.zeros((60, 80), dtype=bool)
    mask[20:30, 20:60] = True
    out = ClassicFiller("telea").fill(area, mask)
    assert out.shape == area.shape
    assert np.array_equal(out[~mask], area[~mask])


def test_queue_items_keep_the_choices_and_they_tell_items_apart():
    item = {"job_id": "j", "set_id": "s", "story_id": "a", "fill_device": "cpu", "fill_follow": True}
    assert app._story_queue_identity(item) != app._story_queue_identity(
        {"job_id": "j", "set_id": "s", "story_id": "a"},
    )


def test_a_choice_only_touches_a_render_with_a_keyed_fill():
    keyed = {"clean": [{"kind": "fill", "method": "lama"}]}
    opencv = {"clean": [{"kind": "fill", "method": "telea"}]}
    plan = {}
    app._apply_fill_choices(plan, keyed, "cpu", True)
    assert plan == {"_fill_device": "cpu", "_fill_follow": True}
    plan = {}
    app._apply_fill_choices(plan, opencv, "cpu", True)
    assert plan == {}
    plan = {}
    app._apply_fill_choices(plan, keyed, "", False)
    assert plan == {}


def test_only_a_chosen_option_changes_a_clean_videos_result():
    job = {"source": {"fingerprint": "f", "width": 100, "height": 100, "fps": 25.0}}
    plain = clean_source._cache_key(job, [], 1.0, "lama", "m")
    assert plain == clean_source._cache_key(job, [], 1.0, "lama", "m", False)
    assert plain != clean_source._cache_key(job, [], 1.0, "lama", "m", True)


def test_fill_status_lists_every_engine_and_what_a_render_can_offer(monkeypatch, tmp_path):
    monkeypatch.setenv("VIBECUT_FILL_MODELS", str(tmp_path))
    (tmp_path / "lama_fp32.onnx").write_bytes(b"x")
    status = routes_classic.classic_fill_status()
    assert list(status["engines"]) == ["lama", "migan", "telea", "ns"]
    assert status["engines"]["migan"]["ready"] is False
    assert status["missing"] == []
    assert "follow" in status["render_options"]
    assert "lama" in status["render_options"]["gpu"]


def _node(script: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    done = subprocess.run(
        [node, "-e", f"const m = require({json.dumps(str(OPTIONS))});\n{script}"],
        capture_output=True, text=True, timeout=60, check=True,
    )
    return json.loads(done.stdout)


def test_choices_fall_back_to_safe_defaults():
    assert _node('console.log(JSON.stringify(m.normalChoice({engine: "sttn", device: "x", follow: 1})))') == {
        "engine": "lama", "device": "", "follow": False,
    }


def test_opencv_sends_no_chip_or_camera_choice():
    assert _node('console.log(JSON.stringify(m.requestFields({engine: "telea", device: "cpu", follow: true})))') == {
        "fill_device": "", "fill_follow": False,
    }
    assert _node('console.log(JSON.stringify(m.requestFields({engine: "lama", device: "cpu", follow: true})))') == {
        "fill_device": "cpu", "fill_follow": True,
    }


def test_a_box_finds_the_lines_inside_it_at_its_time():
    script = """
      const box = {box: {x: 0, y: 0.5, w: 1, h: 0.5}, ranges: [{start: 0, end: 5}]};
      const lines = [
        {id: "in", box: {x: 0.1, y: 0.6, w: 0.5, h: 0.05}, ranges: [{start: 1, end: 2}]},
        {id: "late", box: {x: 0.1, y: 0.7, w: 0.5, h: 0.05}, ranges: [{start: 6, end: 7}]},
        {id: "out", box: {x: 0.1, y: 0.1, w: 0.5, h: 0.05}, ranges: [{start: 1, end: 2}]},
        {id: "logo", minor: true, box: {x: 0.1, y: 0.8, w: 0.1, h: 0.05}, ranges: [{start: 1, end: 2}]},
      ];
      console.log(JSON.stringify(m.linesInsideBox(box, lines).map((line) => line.id)));
    """
    assert _node(script) == ["in"]


def test_a_lines_time_stays_inside_the_boxs_time():
    script = 'console.log(JSON.stringify(m.rangesWithin([{start: 1, end: 9}], [{start: 4, end: 6}])))'
    assert _node(script) == [{"start": 4, "end": 6}]


def test_only_a_big_drawn_fill_box_warns():
    script = """
      console.log(JSON.stringify([
        m.bigBoxShare({method: "fill", box: {w: 0.5, h: 0.5}}),
        m.bigBoxShare({method: "fill", box: {w: 0.1, h: 0.1}}),
        m.bigBoxShare({method: "fill", tracklet_id: "t", box: {w: 0.5, h: 0.5}}),
        m.bigBoxShare({method: "blur", box: {w: 0.5, h: 0.5}}),
      ]));
    """
    assert _node(script) == [25, 0, 0, 0]
