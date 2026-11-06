"""The Render step's AI fill choices: GPU, MI-GAN, following the camera, saved fills."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

import artifacts
import edits
import story_queue
import textfill
from textfill import mask as masks

ROOT = Path(__file__).resolve().parents[1]
FINISH = (ROOT / "static/studio/finish.js").read_text(encoding="utf-8")
CLEAN = (ROOT / "static/studio/edit/layers/clean.js").read_text(encoding="utf-8")


class _Counting:
    def __init__(self, truth=None):
        self.calls = 0
        self.truth = truth

    def fill(self, area, mask):
        self.calls += 1
        out = area.copy()
        out[mask] = 128
        return out


def _picture(height=200, width=320, seed=3):
    rng = np.random.default_rng(seed)
    coarse = rng.integers(0, 255, (height // 8 + 2, width // 8 + 2, 3), dtype=np.uint8)
    return np.repeat(np.repeat(coarse, 8, axis=0), 8, axis=1)[:height, :width].copy()


def _panned(count, step=2):
    base = _picture(240, 400)
    return [base[20:220, 20 + index * step:340 + index * step].copy() for index in range(count)]


RECT = [(60, 80, 260, 120)]


def _rects(_index):
    return RECT


# --- engines and chips ------------------------------------------------------


def test_mi_gan_is_an_engine_and_lama_stays_the_default():
    assert "migan" in textfill.METHODS and "migan" in edits.FILL_METHODS
    assert textfill.DEFAULT_METHOD == "lama"
    assert textfill.MODEL_FILES["migan"] == "migan_traced.pt"
    assert '["migan", "MI-GAN' in CLEAN


def test_the_gpu_is_only_used_when_its_model_is_here(tmp_path, monkeypatch):
    import textfill.torch_fill as torch_fill

    monkeypatch.setattr(torch_fill, "gpu_possible", lambda: True)
    assert textfill.chosen_device("lama", "gpu", tmp_path) == "cpu"
    assert "big-lama.pt" in textfill.gpu_problem("lama", tmp_path)
    (tmp_path / "big-lama.pt").write_bytes(b"x")
    assert textfill.chosen_device("lama", "gpu", tmp_path) == "gpu"
    assert textfill.chosen_device("lama", "cpu", tmp_path) == "cpu"
    assert textfill.chosen_device("telea", "gpu", tmp_path) == "cpu"
    options = textfill.render_options(tmp_path)
    assert options["gpu"]["lama"]["ready"] is True
    assert options["gpu"]["migan"]["ready"] is False


def test_a_gpu_or_motion_clip_never_replaces_the_plain_one(tmp_path):
    (tmp_path / "big-lama.pt").write_bytes(b"gpu")
    (tmp_path / "lama_fp32.onnx").write_bytes(b"cpu")
    args = dict(
        meta={"fingerprint": "f", "width": 100, "height": 100, "fps": 25.0},
        start=0.0, duration=1.0, method="lama",
        layers=[{"box": {"x": 0, "y": 0, "w": 1, "h": 1}, "ranges": [], "fill_keys": 3.0}],
    )
    plain = textfill.span_key(model_stamp=textfill.method_stamp("lama", tmp_path), **args)
    gpu = textfill.span_key(model_stamp=textfill.method_stamp("lama", tmp_path, "gpu"), **args)
    follow = textfill.span_key(model_stamp=textfill.method_stamp("lama", tmp_path), follow_motion=True, **args)
    assert len({plain, gpu, follow}) == 3
    assert plain == textfill.span_key(
        model_stamp=textfill.method_stamp("lama", tmp_path), follow_motion=False, **args,
    )


def test_a_gpu_that_fails_hands_the_render_to_the_cpu():
    class Bad:
        def fill(self, area, mask):
            raise RuntimeError("MPS backend out of memory")

    cpu = _Counting()
    chosen = textfill._GpuOrCpu(lambda: Bad(), lambda: cpu)
    area = _picture(40, 40)
    mask = np.ones((40, 40), dtype=bool)
    assert chosen.fill(area, mask).shape == area.shape
    assert chosen.on_gpu is False and cpu.calls == 1
    chosen.fill(area, mask)
    assert cpu.calls == 2


def test_a_gpu_that_cannot_load_starts_on_the_cpu():
    def broken():
        raise RuntimeError("no MPS device")

    cpu = _Counting()
    chosen = textfill._GpuOrCpu(broken, lambda: cpu)
    assert chosen.on_gpu is False
    chosen.fill(_picture(40, 40), np.ones((40, 40), dtype=bool))
    assert cpu.calls == 1


def test_lama_on_the_gpu_returns_the_work_area_size(monkeypatch):
    torch = pytest.importorskip("torch")
    import textfill.torch_fill as torch_fill

    seen = {}

    def model(image, mask):
        seen["image"], seen["mask"] = image, mask
        return torch.full_like(image, 0.5)

    monkeypatch.setattr(torch_fill, "_load", lambda _path, _device: model)
    filler = torch_fill.LamaGpuFiller(Path("big-lama.pt"))
    filler.device = "cpu"
    out = filler.fill(_picture(100, 300), np.ones((100, 300), dtype=bool))
    assert out.shape == (100, 300, 3)
    assert int(out[50, 150, 0]) in (126, 127, 128)
    assert seen["image"].shape[2] % 8 == 0 and seen["image"].shape[3] % 8 == 0
    assert float(seen["image"].max()) <= 1.0


def test_mi_gan_reads_a_square_with_its_hole_marked(monkeypatch):
    torch = pytest.importorskip("torch")
    import textfill.torch_fill as torch_fill

    seen = {}

    def model(feed):
        seen["feed"] = feed
        return torch.zeros((1, 3, 512, 512))

    monkeypatch.setattr(torch_fill, "_load", lambda _path, _device: model)
    filler = torch_fill.MiganFiller(Path("migan_traced.pt"), "cpu")
    mask = np.zeros((100, 300), dtype=bool)
    mask[40:60, 50:250] = True
    out = filler.fill(_picture(100, 300), mask)
    assert out.shape == (100, 300, 3)
    assert seen["feed"].shape == (1, 4, 512, 512)
    # The first channel is 0.5 - hole; the picture channels are empty in the hole.
    assert float(seen["feed"][0, 0].min()) == pytest.approx(-0.5)
    assert float(seen["feed"][0, 0].max()) == pytest.approx(0.5)
    assert int(out[50, 150, 0]) in (127, 128)


def test_each_chip_keeps_its_own_speed(tmp_path):
    textfill.record_rate(tmp_path, "lama", 10, 40.0)
    textfill.record_rate(tmp_path, "lama", 10, 8.0, "gpu")
    assert textfill.fill_rate(tmp_path, "lama")["seconds"] == pytest.approx(4.0)
    assert textfill.fill_rate(tmp_path, "lama", "gpu")["seconds"] == pytest.approx(0.8)
    assert textfill.fill_rate(tmp_path, "migan", "gpu") == {"seconds": 0.25, "measured": False}


def test_the_estimate_uses_the_chosen_chip(tmp_path):
    base = {"method": "lama", "frames": 100, "units": 10.0, "cached": False}
    cpu = textfill.estimate_summary([{**base, "device": "cpu"}], tmp_path)
    gpu = textfill.estimate_summary([{**base, "device": "gpu"}], tmp_path)
    assert gpu["seconds"] < cpu["seconds"] / 3


def test_mi_gan_counts_one_full_run_whatever_the_crop():
    assert textfill._run_units("migan", 100, 300) == 1.0
    assert textfill._run_units("lama", 144, 512) < 0.3


# --- render options reach the file ---------------------------------------------


def test_queue_items_keep_the_render_choices():
    item = {"job_id": "j1", "set_id": "s1", "story_id": "a", "aspect": "9:16", "quality": "final"}
    rows = story_queue.normalize_items([
        item,
        {**item, "fill_device": "gpu"},
        {**item, "fill_follow": True},
    ])
    assert [row["fill_device"] for row in rows] == ["", "gpu", ""]
    assert [row["fill_follow"] for row in rows] == [False, False, True]
    assert story_queue.normalize_items([{**item, "fill_device": "nonsense"}])[0]["fill_device"] == ""


def test_only_a_chosen_option_changes_a_renders_identity():
    from dataclasses import fields, replace

    names = {field.name for field in fields(artifacts.ArtifactSpec)}
    assert {"fill_device", "fill_follow"} <= names
    spec = artifacts.ArtifactSpec.from_payload({"target": 30, "story_id": "s"})
    plain = artifacts.artifact_id(spec)
    assert artifacts.artifact_id(replace(spec, fill_device="")) == plain
    assert artifacts.artifact_id(replace(spec, fill_device="gpu")) != plain
    assert artifacts.artifact_id(replace(spec, fill_follow=True)) != plain
    chosen = replace(spec, fill_device="gpu", fill_follow=True)
    back = artifacts.ArtifactSpec.from_payload(chosen.canonical() if hasattr(chosen, "canonical") else {"fill_device": "gpu", "fill_follow": True})
    assert back.fill_device == "gpu" and back.fill_follow is True


def test_the_render_step_offers_the_choices():
    assert 'segmented(\n      "AI fill on"' in FINISH
    assert "Follow camera motion" in FINISH
    assert 'fill_device: fillDeviceNow() === "gpu" ? "gpu" : ""' in FINISH
    assert "fill_follow:" in FINISH


# --- following the camera --------------------------------------------------------


def test_one_fill_follows_a_camera_pan():
    pytest.importorskip("cv2")
    frames = _panned(16)
    model = _Counting()
    out = list(textfill.fill_frames_lama(
        iter(frames), _rects, model, None, step=5, follow=True,
    ))
    assert len(out) == len(frames)
    assert model.calls == 1


def test_without_following_the_same_pan_needs_more_fills():
    frames = _panned(16)
    model = _Counting()
    plan = lambda _index: (5, textfill.LAMA_MOTION_LIMIT, False, 3)
    list(textfill.fill_frames_lama(iter(frames), _rects, model, None, step=5, plan_for=plan))
    assert model.calls >= 4


def test_a_followed_fill_moves_with_the_picture():
    pytest.importorskip("cv2")
    from textfill.follow import FollowedFill

    frames = _panned(8, step=3)
    hole = masks.rasterize(RECT, 320, 200)
    keep = textfill._ring_around(RECT, (0, 0, 320, 200))
    # The model here is perfect: it returns the real picture for the key frame.
    follower = FollowedFill(frames[0], frames[0].copy(), hole, keep)
    moved = follower.fill_for(frames[7], hole)
    assert moved is not None
    error = np.abs(moved[hole].astype(np.int16) - frames[7][hole].astype(np.int16)).mean()
    still = np.abs(frames[0][hole].astype(np.int16) - frames[7][hole].astype(np.int16)).mean()
    assert error < still / 3


def test_revealed_pixels_replace_the_models_guess():
    pytest.importorskip("cv2")
    from textfill.follow import FollowedFill

    base = _picture(300, 320)
    frames = [base[40 + index * 6:240 + index * 6].copy() for index in range(9)]
    hole = masks.rasterize(RECT, 320, 200)
    keep = textfill._ring_around(RECT, (0, 0, 320, 200))
    guess = frames[0].copy()
    guess[hole] = 128
    follower = FollowedFill(frames[0], guess, hole, keep)
    before = int(follower.guessed.sum())
    for frame in frames[1:]:
        assert follower.fill_for(frame, hole) is not None
    assert int(follower.guessed.sum()) < before / 2
    assert np.abs(follower.plate[hole].astype(np.int16) - frames[0][hole].astype(np.int16)).mean() < 40


def test_a_cut_ends_a_followed_fill_and_makes_a_new_one():
    pytest.importorskip("cv2")
    first = _picture(200, 320, seed=3)
    second = _picture(200, 320, seed=9)
    frames = [first.copy() for _ in range(6)] + [second.copy() for _ in range(6)]
    model = _Counting()
    list(textfill.fill_frames_lama(iter(frames), _rects, model, None, step=5, follow=True))
    assert 2 <= model.calls <= 4


def test_following_matches_the_light_around_the_text():
    pytest.importorskip("cv2")
    from textfill.follow import FollowedFill

    frame = _picture(200, 320)
    hole = masks.rasterize(RECT, 320, 200)
    keep = textfill._ring_around(RECT, (0, 0, 320, 200))
    follower = FollowedFill(frame, frame.copy(), hole, keep)
    brighter = np.clip(frame.astype(np.int16) + 12, 0, 255).astype(np.uint8)
    moved = follower.fill_for(brighter, hole)
    assert moved is not None
    assert np.abs(moved[hole].astype(np.int16) - brighter[hole].astype(np.int16)).mean() < 6


def test_a_fill_that_cannot_reach_the_text_ends():
    pytest.importorskip("cv2")
    from textfill.follow import FollowedFill

    frame = _picture(200, 320)
    hole = masks.rasterize([(10, 80, 310, 120)], 320, 200)
    keep = textfill._ring_around([(10, 80, 310, 120)], (0, 0, 320, 200))
    follower = FollowedFill(frame, frame.copy(), hole, keep)
    follower._matrix = lambda _crop: np.array([[1.0, 0.0, 60.0], [0.0, 1.0, 0.0]])
    assert follower.fill_for(frame, hole) is None


def test_a_shot_that_keeps_breaking_it_is_tried_less_often():
    pytest.importorskip("cv2")
    base = _picture(200, 320)
    rng = np.random.default_rng(5)
    # Busy enough to break a followed fill, and not so much that every frame is a cut.
    frames = [
        np.clip(base.astype(np.int16) + rng.normal(0, 18, base.shape), 0, 255).astype(np.uint8)
        for _ in range(60)
    ]
    layer = {"box": {"x": 0.1, "y": 0.3, "w": 0.8, "h": 0.2}, "ranges": []}
    plan = textfill.lama_plan([layer], start=0.0, fps=25.0, frames=len(frames))
    normal = _Counting()
    list(textfill.fill_frames_lama(iter(frames), _rects, normal, None, step=8, plan_for=plan))
    following = _Counting()
    out = list(textfill.fill_frames_lama(iter(frames), _rects, following, None, step=8, plan_for=plan, follow=True))
    assert len(out) == 60
    assert following.calls <= normal.calls * 1.5


def test_a_plain_background_is_held_without_tracking():
    pytest.importorskip("cv2")
    frames = [np.full((200, 320, 3), 90, dtype=np.uint8) for _ in range(12)]
    model = _Counting()
    list(textfill.fill_frames_lama(iter(frames), _rects, model, None, step=5, follow=True))
    assert model.calls == 1


# --- saved fills and per-frame costs ----------------------------------------------


def test_saved_fills_outlive_the_clip_and_the_cap_covers_every_video(tmp_path, monkeypatch):
    one = tmp_path / "jobs" / "a" / "fill" / "saved"
    two = tmp_path / "jobs" / "b" / "fill" / "saved"
    one.mkdir(parents=True)
    two.mkdir(parents=True)
    import os

    now = 2_000_000_000.0
    for index, folder in enumerate((one, two, one)):
        path = folder / f"{index}.npy"
        path.write_bytes(b"x" * 10)
        os.utime(path, (now - 100 + index, now - 100 + index))
    monkeypatch.setattr(textfill, "SAVED_MAX_BYTES", 15)
    monkeypatch.setattr(textfill, "_free_disk", lambda _path: 10 ** 15)
    folders = textfill._saved_folders(tmp_path)
    assert set(folders) == {one, two}
    textfill._prune_saved(folders, now=now)
    assert [path.name for path in one.iterdir()] == ["2.npy"]
    assert list(two.iterdir()) == []


def test_saved_fills_give_way_when_the_disk_is_short(tmp_path, monkeypatch):
    import os

    now = 2_000_000_000.0
    for index in range(4):
        path = tmp_path / f"{index}.npy"
        path.write_bytes(b"x" * 10)
        os.utime(path, (now - 10 + index, now - 10 + index))
    monkeypatch.setattr(textfill, "SAVED_MIN_FREE", 100)
    monkeypatch.setattr(textfill, "_free_disk", lambda _path: 85)
    textfill._prune_saved(tmp_path, now=now)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["2.npy", "3.npy"]


def test_no_fill_is_saved_when_the_disk_is_short(tmp_path, monkeypatch):
    monkeypatch.setattr(textfill, "_free_disk", lambda _path: 0)
    model = _Counting()
    saved = textfill._SavedFills(model, tmp_path / "saved", "m")
    saved.fill(_picture(40, 40), np.ones((40, 40), dtype=bool))
    assert model.calls == 1
    assert not (tmp_path / "saved").exists()


def test_a_box_with_the_same_hole_is_feathered_once(monkeypatch):
    calls = []
    real = masks.feather

    def counted(hole, *args, **kwargs):
        calls.append(1)
        return real(hole, *args, **kwargs)

    monkeypatch.setattr(masks, "feather", counted)
    frames = [_picture() for _ in range(10)]
    list(textfill.fill_frames_lama(
        iter(frames), _rects, _Counting(), None, step=5,
        plan_for=lambda _index: (5, textfill.LAMA_MOTION_LIMIT, False, 3),
    ))
    assert len(calls) == 1


def test_paste_touches_only_the_hole_and_matches_a_full_blend():
    rng = np.random.default_rng(1)
    original = rng.integers(0, 255, (60, 80, 3), dtype=np.uint8)
    filled = rng.integers(0, 255, (60, 80, 3), dtype=np.uint8)
    hole = np.zeros((60, 80), dtype=bool)
    hole[20:30, 30:50] = True
    alpha = masks.feather(hole)
    weight = alpha[..., None]
    full = np.clip(np.rint(original.astype(np.float32) * (1 - weight) + filled.astype(np.float32) * weight), 0, 255).astype(np.uint8)
    full[alpha <= 0] = original[alpha <= 0]
    assert np.array_equal(masks.paste(original, filled, alpha), full)
    assert np.array_equal(masks.paste(original, filled, np.zeros((60, 80), dtype=np.float32)), original)


# --- a wide box becomes the lines inside it ------------------------------------------


def _node(script: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    url = (ROOT / "static/studio/edit/layers/clean.js").as_uri()
    done = subprocess.run(
        [node, "--input-type=module", "-e", (
            "globalThis.document = undefined;\n"
            f"const m = await import({json.dumps(url)});\n{script}"
        )],
        capture_output=True, text=True, timeout=60, check=True,
    )
    return json.loads(done.stdout)


def test_a_box_finds_the_lines_inside_it_at_its_time():
    layer = {"box": {"x": 0.0, "y": 0.6, "w": 1.0, "h": 0.25}, "ranges": [{"start": 0, "end": 10}]}
    tracklets = [
        {"id": "in", "box": {"x": 0.1, "y": 0.65, "w": 0.8, "h": 0.05}, "ranges": [{"start": 1, "end": 2}]},
        {"id": "late", "box": {"x": 0.1, "y": 0.65, "w": 0.8, "h": 0.05}, "ranges": [{"start": 20, "end": 22}]},
        {"id": "above", "box": {"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.05}, "ranges": [{"start": 1, "end": 2}]},
        {"id": "edge", "box": {"x": 0.1, "y": 0.56, "w": 0.8, "h": 0.05}, "ranges": [{"start": 1, "end": 2}]},
        {"id": "logo", "minor": True, "box": {"x": 0.1, "y": 0.65, "w": 0.2, "h": 0.05}, "ranges": [{"start": 1, "end": 2}]},
    ]
    found = _node(
        f"console.log(JSON.stringify(m.linesInsideBox({json.dumps(layer)}, {json.dumps(tracklets)}).map((row) => row.id)));"
    )
    assert found == ["in"]


def test_a_lines_time_stays_inside_the_boxs_time():
    out = _node(
        "console.log(JSON.stringify([m.rangesWithin([{start: 1, end: 9}], [{start: 3, end: 5}]),"
        " m.rangesWithin([{start: 1, end: 9}], [])]));"
    )
    assert out == [[{"start": 3, "end": 5}], [{"start": 1, "end": 9}]]


def test_the_panel_offers_the_swap_and_says_what_a_box_costs():
    assert "Clean only the ${formatLines(lines.length)} inside" in CLEAN
    assert "This box repaints ${share}% of the picture" in CLEAN
    assert "async function snapToLines" in CLEAN
