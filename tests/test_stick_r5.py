"""R5 spike: a Text layer sticks to the video, by mapping it to each beat."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image
from test_studio_js import needs_node, run_module

import compose_render
import edits
import render

ROOT = Path(__file__).resolve().parents[1]
TEXT_PANEL = (ROOT / "static/studio/edit/layers/text.js").read_text(encoding="utf-8")
PREVIEW = (ROOT / "static/studio/edit/preview.js").read_text(encoding="utf-8")

SOURCE = {"width": 1920, "height": 1080}
STORY_REF = {
    "set_id": "cs_1", "story_id": "s1", "clip_hash": "a" * 16, "title": "Story",
    "duration": 8.0, "clip_count": 2,
}
VIDEO = {"box": {"x": 0.3, "y": 0.5, "w": 0.2, "h": 0.1}, "crop_h": 1.0}


def _text(**extra):
    return {
        "id": "t1", "type": "text", "kind": "hook", "text": "Hello there",
        "start": 0.0, "end": 8.0, "anchor": "center", "box": {"w": 0.8, "h": 0.1},
        "z": 10, "style": {"size": 60}, "opacity": 1.0, **extra,
    }


def _edit(graphics, **extra):
    return edits.build_edit(
        story_ref=dict(STORY_REF), aspect="9:16", created=1.0, graphics=graphics,
        **{"reframe": {"mode": "center", "cx": 0.5, "cy": 0.5, "zoom": 1.0}, **extra},
    )


def _clips(*scenes):
    clips, at = [], 0.0
    for name in scenes:
        clips.append({"scene": name, "start": at, "end": at + 4.0, "role": "beat"})
        at += 4.0
    return clips


def _scenes(**centres):
    return {name: {"id": name, "crops": {"9:16": {"cx": cx, "cy": 0.5}}} for name, cx in centres.items()}


def _compile(graphics, *scenes, scene_map=None, **extra):
    return compose_render.compile_edit(
        _edit(graphics, **extra),
        clips=_clips(*(scenes or ("a",))),
        source=SOURCE,
        scenes=scene_map or _scenes(a=0.5),
        motion_engine="perspective",
    )


# ---------------------------------------------------------------- the Edit


def test_the_edit_keeps_a_video_position():
    layer = edits.normalize_graphics([_text(video=VIDEO)])[0]
    assert layer["video"] == VIDEO


def test_a_layer_without_one_has_no_new_key():
    assert "video" not in edits.normalize_graphics([_text()])[0]


@pytest.mark.parametrize("bad", [
    "x",
    {"box": {"x": 0, "y": 0, "w": 1}, "crop_h": 1},
    {"box": {"x": 0, "y": 0, "w": 1, "h": 1}},
    {"box": {"x": 0, "y": 0, "w": 1, "h": 1}, "crop_h": 0},
    {"box": {"x": 0, "y": 0, "w": 1, "h": 1, "z": 1}, "crop_h": 1},
])
def test_a_bad_video_position_is_refused(bad):
    with pytest.raises(edits.EditError):
        edits.normalize_graphics([_text(video=bad)])


def test_effects_do_not_take_one_yet():
    fx = {
        "id": "f1", "type": "fx", "kind": "underline", "start": 0, "end": 1,
        "anchor": "center", "box": {"w": 0.5, "h": 0.1}, "video": VIDEO,
    }
    with pytest.raises(edits.EditError):
        edits.normalize_graphics([fx])


# ---------------------------------------------------------------- the compile


def test_an_old_layer_compiles_exactly_as_before():
    out = _compile([_text()])
    layer = out["overlays"][0]
    assert layer["id"] == "t1"
    assert "stuck" not in layer and "video" not in layer and "motion" not in layer


def test_the_layer_follows_each_beat_crop_and_can_leave_the_frame():
    out = _compile(
        [_text(video=VIDEO)], "a", "b",
        scene_map=_scenes(a=0.4, b=0.6),
        reframe={"mode": "auto", "cx": 0.5, "cy": 0.5, "zoom": 1.0},
    )
    first, second = out["overlays"]
    assert (first["id"], second["id"]) == ("t1~1", "t1~2")
    assert first["parent_id"] == "t1" and first["stuck"] is True
    assert (first["start"], first["end"]) == (0.0, 4.0)
    assert (second["start"], second["end"]) == (4.0, 8.0)
    for piece, segment in zip((first, second), out["segments"]):
        crop = segment["crop"]
        assert piece["rect"]["x"] == pytest.approx((0.3 * 1920 - crop["x"]) / crop["w"], abs=1e-5)
        assert piece["rect"]["w"] == pytest.approx(0.2 * 1920 / crop["w"], abs=1e-5)
    assert second["rect"]["x"] < first["rect"]["x"]
    assert second["rect"]["x"] < 0


def test_beats_with_the_same_crop_share_one_piece():
    out = _compile([_text(video=VIDEO)], "a", "b", scene_map=_scenes(a=0.5, b=0.5))
    assert [(p["start"], p["end"]) for p in out["overlays"]] == [(0.0, 8.0)]


def test_text_grows_with_the_zoom():
    zoomed = _edit([], reframe={"mode": "center", "cx": 0.5, "cy": 0.5, "zoom": 2.0})
    out = _compile([_text(video=VIDEO)], reframe=zoomed["reframe"])
    piece = out["overlays"][0]
    assert piece["style"]["size"] == pytest.approx(120.0, rel=0.02)
    normal = _compile([_text(video=VIDEO)])["overlays"][0]
    assert piece["rect"]["w"] == pytest.approx(2 * normal["rect"]["w"], rel=0.02)


def test_a_layer_outside_the_crop_is_hidden_and_stays_in_the_edit():
    left = {"box": {"x": 0.0, "y": 0.5, "w": 0.1, "h": 0.1}, "crop_h": 1.0}
    out = _compile([_text(video=left)])
    assert out["overlays"] == []
    warning = next(item for item in out["warnings"] if item["code"] == "layer_hidden_by_crop")
    assert warning["layer_id"] == "t1"


def test_a_piece_carries_its_beat_motion_exactly():
    motion = [{
        "id": "m1", "kind": "push", "start": 0.0, "end": 8.0, "amount": 0.2, "ramp": 0.0,
    }]
    out = _compile([_text(video=VIDEO)], "a", "b", scene_map=_scenes(a=0.5, b=0.5), motion=motion)
    assert len(out["overlays"]) == 2
    for piece, segment in zip(out["overlays"], out["segments"]):
        filters = piece["motion"]["filters"]
        assert filters
        assert all(item in segment["post_filters"] for item in filters)
        assert piece["motion"]["start"] == segment["out_start"]
        assert piece["motion"]["frames"] == segment["frames"]


def test_a_layer_starting_inside_a_beat_counts_motion_from_the_beat():
    motion = [{"id": "m1", "kind": "push", "start": 0.0, "end": 4.0, "amount": 0.2, "ramp": 0.0}]
    out = _compile([_text(video=VIDEO, start=1.0, end=3.0)], motion=motion)
    piece = out["overlays"][0]
    assert (piece["start"], piece["end"]) == (1.0, 3.0)
    assert piece["motion"]["start"] == 0.0


def test_a_blank_card_keeps_the_layer_where_it_was():
    clips = [
        {"scene": "a", "start": 0.0, "end": 4.0, "role": "beat"},
        {"kind": "blank", "start": 0.0, "end": 4.0, "role": "beat"},
    ]
    out = compose_render.compile_edit(
        _edit([_text(video=VIDEO)]), clips=clips, source=SOURCE, scenes=_scenes(a=0.5),
        motion_engine="perspective",
    )
    pieces = out["overlays"]
    assert len(pieces) == 2
    assert pieces[1]["rect"] == compose_render._overlay_rect("center", {"w": 0.8, "h": 0.1})


# ---------------------------------------------------------------- the burn


def _piece(**extra):
    return {
        "id": "t1~1", "type": "text", "kind": "hook", "text": "Hello there",
        "start": 2.0, "end": 4.0, "stuck": True, "z": 10, "opacity": 1.0,
        "rect": {"x": -0.1, "y": 0.5, "w": 0.8, "h": 0.1}, "style": {"size": 60},
        **extra,
    }


def test_a_stuck_layer_keeps_its_size_past_the_frame():
    assert render._layer_place(_piece(), 1000, 2000) == (-100, 1000, 800, 200)
    image = render._render_text_layer(_piece(), 1000, 2000)
    assert image.size == (800, 200)


def test_an_old_layer_is_still_clipped_to_the_frame():
    layer = {key: value for key, value in _piece().items() if key != "stuck"}
    assert render._layer_place(layer, 1000, 2000) == (0, 1000, 800, 200)


@pytest.fixture
def burn(tmp_path, monkeypatch):
    """Run the burn up to its ffmpeg call and hand back the command."""
    commands = []
    monkeypatch.setattr(render, "_run", lambda cmd, **kwargs: commands.append(cmd))
    monkeypatch.setattr(render, "_ffmpeg", lambda: "ffmpeg")

    def png(layer, out_w, out_h, cache_dir, **kwargs):
        path = tmp_path / f"{layer['id']}.png"
        if not path.exists():
            Image.new("RGBA", (10, 10), (255, 255, 255, 255)).save(path)
        return path

    monkeypatch.setattr(render, "_layer_png", png)
    return commands, tmp_path


def _graph(command):
    return command[command.index("-filter_complex") + 1]


def test_burn_places_a_stuck_piece_off_the_frame_and_owns_its_frames(burn):
    commands, tmp = burn
    render._burn_layers(tmp / "in.mp4", [_piece()], tmp / "out.mp4", tmp, 1000, 2000, 8.0, "final", "libx264")
    graph = _graph(commands[0])
    assert "overlay=x=-100:y=1000" in graph
    assert "gte(t,1.991667)*lt(t,3.991667)" in graph


def test_burn_gives_a_moving_beat_the_same_filters_on_the_whole_frame(burn):
    commands, tmp = burn
    motion = {"filters": ["perspective=x0='1':y0='2':eval=frame"], "start": 2.0, "frames": 60}
    render._burn_layers(tmp / "in.mp4", [_piece(motion=motion)], tmp / "out.mp4", tmp, 1000, 2000, 8.0, "final", "libx264")
    command = commands[0]
    graph = _graph(command)
    assert "format=yuva444p,perspective=x0='1':y0='2':eval=frame,settb=1/30,setpts=PTS-STARTPTS+60[l1]" in graph
    assert "[0:v][l1]overlay=x=0:y=0" in graph
    assert command[command.index("-t") + 1] == "2.000000"
    with Image.open(tmp / "t1~1_canvas_1000x2000.png") as canvas:
        assert canvas.size == (1000, 2000)
        assert canvas.getpixel((0, 1000))[3] == 0  # the first 100 px of the layer fell off
        assert canvas.getpixel((0, 999))[3] == 0


def test_an_old_layer_keeps_its_exact_burn(burn):
    commands, tmp = burn
    layer = {key: value for key, value in _piece().items() if key != "stuck"}
    layer["rect"] = {"x": 0.1, "y": 0.5, "w": 0.8, "h": 0.1}
    render._burn_layers(tmp / "in.mp4", [layer], tmp / "out.mp4", tmp, 1000, 2000, 8.0, "final", "libx264")
    assert "overlay=x=100:y=1000:enable='between(t,2.000,4.000)':eof_action=pass" in _graph(commands[0])


def test_only_one_piece_shows_on_the_frame_at_a_cut(burn):
    commands, tmp = burn
    first = _piece(id="a", start=0.0, end=2.0)
    second = _piece(id="b", start=2.0, end=4.0)
    render._burn_frame(tmp / "f.png", [first, second], tmp / "o.jpg", 1000, 2000, 2.0, tmp)
    assert sum(1 for item in commands[0] if str(item).endswith(".png") and "f.png" not in str(item)) == 1
    assert str(tmp / "b.png") in commands[0]


def test_the_exact_frame_shows_the_beat_motion_at_that_frame(burn):
    commands, tmp = burn
    motion = {"filters": ["perspective=x0='1':eval=frame"], "start": 2.0, "frames": 60}
    render._burn_frame(tmp / "f.png", [_piece(motion=motion)], tmp / "o.jpg", 1000, 2000, 2.5, tmp)
    graph = _graph(commands[0])
    assert "perspective=x0='1':eval=frame,trim=start_frame=15,setpts=PTS-STARTPTS[l1]" in graph
    assert commands[0][commands[0].index("-t") + 1] == f"{16 / 30:.6f}"


# ---------------------------------------------------------------- the preview


@needs_node
def test_the_preview_draws_it_where_the_render_does():
    out = run_module("edit/overlay.js", """
        const edit = {graphics: [{
          id: "t1", type: "text", kind: "hook", text: "Hi", start: 0, end: 8, z: 10,
          anchor: "center", box: {w: 0.8, h: 0.1}, style: {size: 60, stroke_width: 4},
          video: {box: {x: 0.3, y: 0.5, w: 0.2, h: 0.1}, crop_h: 1},
        }]};
        const crop = {x: 0.4, y: 0.25, w: 0.2, h: 0.5};
        const on = m.overlayLayers(edit, null, 1, crop)[0];
        const off = m.overlayLayers(edit, null, 1)[0];
        return {rect: on.rect, size: on.style.size, stroke: on.style.stroke_width, offSize: off.style.size};
    """)
    assert out["rect"]["x"] == pytest.approx(-0.5)
    assert out["rect"]["y"] == pytest.approx(0.5)
    assert out["rect"]["w"] == pytest.approx(1.0)
    assert out["rect"]["h"] == pytest.approx(0.2)
    assert out["size"] == pytest.approx(120)
    assert out["stroke"] == pytest.approx(8)
    assert out["offSize"] == 60


@needs_node
def test_sticking_a_layer_keeps_it_where_it_shows():
    out = run_module("edit/canvas-tools.js", """
        const crop = {x: 0.34, y: 0, w: 0.32, h: 1};
        const rect = {x: 0.1, y: 0.45, w: 0.8, h: 0.1};
        const video = m.stuckPosition(rect, crop);
        const layer = {video, anchor: "top-left", box: {w: 0.1, h: 0.1}};
        return {video, back: m.layerFrameRect(layer, crop), scale: m.stuckScale(layer, crop)};
    """)
    assert out["video"]["crop_h"] == 1
    assert out["back"]["x"] == pytest.approx(0.1)
    assert out["back"]["y"] == pytest.approx(0.45)
    assert out["back"]["w"] == pytest.approx(0.8)
    assert out["back"]["h"] == pytest.approx(0.1)
    assert out["scale"] == pytest.approx(1)


def test_the_panel_offers_it_and_the_canvas_follows_it():
    assert 'checkbox("Stick to the video", Boolean(layer.video))' in TEXT_PANEL
    assert "stuckPosition(graphicRect(layer), ctx.getCropAt(numberOr(layer.start, 0)))" in TEXT_PANEL
    assert "state.time, width, height, currentCrop()," in PREVIEW
    assert "insideRect(layerFrameRect(layers[index], currentCrop()), frame)" in PREVIEW
    assert "rect = layerFrameRect(layer, currentCrop());" in PREVIEW
