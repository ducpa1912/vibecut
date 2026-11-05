"""A scene zooms and moves inside the frame, and media past the frame is cut."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

import compose_render
import edits
import render

ROOT = Path(__file__).resolve().parent.parent


def test_a_zoomed_out_scene_sits_centred_inside_the_frame():
    crop = compose_render._base_crop(
        1920, 1080, "9:16", 0.5, 0.5, 0.5, 1080, 1920, set_x=False, set_y=False,
    )
    assert (crop["w"], crop["h"]) == (1216, 1080)
    assert crop["place"] == {"x": 0.0, "y": 0.25, "w": 1.0, "h": 0.5}
    assert crop["window"]["h"] == 2160.0


def test_fit_shows_the_whole_picture():
    fit = (1080 * 1080 / 1920) / 1920
    crop = compose_render._base_crop(
        1920, 1080, "9:16", 0.2, 0.5, fit, 1080, 1920, set_x=False, set_y=False,
    )
    assert (crop["x"], crop["y"], crop["w"], crop["h"]) == (0, 0, 1920, 1080)
    assert crop["place"]["y"] == pytest.approx(0.3418, abs=0.001)


def test_auto_reframe_does_not_push_a_zoomed_out_picture_off_centre():
    auto = compose_render._base_crop(1920, 1080, "9:16", 0.2, 0.5, 0.3165, 1080, 1920, set_x=False, set_y=False)
    moved = compose_render._base_crop(1920, 1080, "9:16", 0.2, 0.5, 0.3165, 1080, 1920, set_x=True, set_y=False)
    assert auto["place"]["w"] > 0.99
    assert moved["place"]["w"] < auto["place"]["w"], "a picture moved past the frame edge is cut"


def test_zoom_at_or_above_one_never_leaves_empty_frame():
    for zoom in (1.0, 1.5, 3.0):
        crop = compose_render._base_crop(1920, 1080, "9:16", 0.0, 1.0, zoom, 1080, 1920)
        assert "place" not in crop and crop["x"] == 0
        assert crop["y"] + crop["h"] <= 1080


def test_the_filter_pads_only_a_placed_picture():
    assert compose_render.placed_scale_filter(None, 1080, 1920) == "scale=1080:1920:flags=lanczos"
    placed = compose_render.placed_scale_filter(
        {"x": 0.0, "y": 0.25, "w": 1.0, "h": 0.5}, 1080, 1920,
    )
    assert placed == "scale=1080:960:flags=lanczos,pad=1080:1920:0:480:color=black"
    meta = {"width": 1920, "height": 1080, "fps": 30}
    crop = compose_render._base_crop(1920, 1080, "9:16", 0.5, 0.5, 0.5, 1080, 1920)
    assert placed in render._crop_filter(meta, crop, 1080, 1920)


def test_a_stuck_layer_stays_on_the_video_when_zoomed_out():
    crop = compose_render._base_crop(1920, 1080, "9:16", 0.5, 0.5, 0.5, 1080, 1920)
    video = {"box": {"x": 0.5, "y": 0.5, "w": 0.1, "h": 0.1}, "crop_h": 1.0}
    rect = compose_render._stuck_rect(video, crop, 1920, 1080)
    assert rect["y"] == pytest.approx(0.5)
    assert rect["h"] == pytest.approx(0.05)


def test_scene_framing_validates():
    clean = edits.normalize_reframe({"scenes": {"3": {"zoom": 0.4, "cx": 0.2}, "asset:a1": {"cy": 0.9}}})
    assert clean["scenes"] == {"3": {"zoom": 0.4, "cx": 0.2}, "asset:a1": {"cy": 0.9}}
    for bad in ({"../x": {"zoom": 1}}, {"3": {"zoom": 0.01}}, {"3": {"zoom": 4}}, {"3": {"cx": 2}}, {"3": {"pan": 1}}):
        with pytest.raises(edits.EditError):
            edits.normalize_reframe({"scenes": bad})


def test_an_edit_without_scene_framing_keeps_its_old_shape():
    assert "scenes" not in edits.normalize_reframe({})
    assert "scenes" not in edits.normalize_reframe({"scenes": {}})


def test_scene_framing_key_matches_the_clip():
    assert compose_render.scene_framing_key({"scene": 7}) == "7"
    assert compose_render.scene_framing_key({"kind": "file", "asset_id": "a1"}) == "asset:a1"
    assert compose_render.scene_framing_key({"kind": "file", "asset": {"id": "a2"}}) == "asset:a2"


def test_whole_proxy_keeps_the_source_shape_without_upscaling():
    assert render._whole_proxy_size({"width": 3840, "height": 2160}) == (1280, 720)
    assert render._whole_proxy_size({"width": 640, "height": 360}) == (640, 360)


def test_the_preview_and_the_render_agree_on_framing(tmp_path):
    """`canvas-tools.cropAt` must draw what `_base_crop` renders."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    cases = [
        {"zoom": 1.0, "cx": 0.5, "cy": 0.5},
        {"zoom": 1.5, "cx": 0.2, "cy": 0.5},
        {"zoom": 0.6, "cx": 0.5, "cy": 0.5},
        {"zoom": 0.32, "cx": 0.1, "cy": 0.9},
        {"zoom": 0.32},
    ]
    script = tmp_path / "run.mjs"
    module = (ROOT / "static" / "studio" / "edit" / "canvas-tools.js").as_uri()
    script.write_text(
        f'import {{ cropAt }} from "{module}";\n'
        "const job = { source: { width: 1920, height: 1080 } };\n"
        'const story = { clips: [{ scene: 4, start: 0, end: 5 }] };\n'
        f"const cases = {json.dumps(cases)};\n"
        "console.log(JSON.stringify(cases.map((entry) => cropAt({\n"
        '  edit: { reframe: { mode: "center", scenes: { 4: entry } } },\n'
        '  job, story, time: 1, aspect: "9:16",\n'
        "}))));\n",
        encoding="utf-8",
    )
    done = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    windows = json.loads(done.stdout)
    for entry, shown in zip(cases, windows):
        crop = compose_render._base_crop(
            1920, 1080, "9:16", entry.get("cx", 0.5), entry.get("cy", 0.5), entry["zoom"], 1080, 1920,
            set_x="cx" in entry, set_y="cy" in entry,
        )
        expected = crop.get("window") or crop
        assert shown["x"] * 1920 == pytest.approx(expected["x"], abs=3)
        assert shown["y"] * 1080 == pytest.approx(expected["y"], abs=3)
        assert shown["w"] * 1920 == pytest.approx(expected["w"], abs=3)
        assert shown["h"] * 1080 == pytest.approx(expected["h"], abs=3)
