"""Pure Edit compiler: golden filter strings, coordinates and determinism."""

from __future__ import annotations

import json
import os
import subprocess

import pytest

import compose_render
import edits

STORY_REF = {
    "set_id": "cs_1",
    "story_id": "s1",
    "clip_hash": "a" * 16,
    "title": "Story one",
    "duration": 6.0,
    "clip_count": 2,
}
CLIPS = [
    {"scene": 0, "start": 0.0, "end": 4.0, "dur": 4.0, "role": "hook"},
    {"scene": 1, "start": 10.0, "end": 12.0, "dur": 2.0, "role": "payoff"},
]
SOURCE = {"width": 1920, "height": 1080}


def _edit(**overrides) -> dict:
    value = {"story_ref": dict(STORY_REF), "aspect": "9:16", "created": 1.0}
    value.update(overrides)
    return edits.build_edit(**value)


def _compile(edit: dict, **overrides) -> dict:
    value = {"clips": CLIPS, "source": SOURCE}
    value.update(overrides)
    return compose_render.compile_edit(edit, **value)


def test_plate_filter_golden():
    edit = _edit(clean=[{
        "kind": "plate", "box": {"x": 0.1, "y": 0.7, "w": 0.5, "h": 0.1},
    }])
    segment = _compile(edit)["segments"][0]
    assert segment["pre_filter"] == (
        "drawbox=x=192:y=756:w=960:h=108:color=0x000000@1.000:t=fill"
    )
    assert segment["filter"] == (
        "drawbox=x=192:y=756:w=960:h=108:color=0x000000@1.000:t=fill,"
        "crop=608:1080:656:0,scale=1080:1920:flags=lanczos,"
        "setsar=1,fps=30,format=yuv420p"
    )


def test_blur_filter_golden():
    edit = _edit(clean=[{
        "kind": "blur", "box": {"x": 0.2, "y": 0.2, "w": 0.2, "h": 0.2},
        "radius": 24,
    }])
    segment = _compile(edit)["segments"][0]
    assert segment["pre_filter"] == (
        "split=2[cl0a][cl0b];"
        "[cl0b]crop=384:216:384:216,boxblur=luma_radius=24:luma_power=2:chroma_radius=24:chroma_power=2[cl0c];"
        "[cl0a][cl0c]overlay=384:216"
    )
    assert segment["filter"] == (
        "split=2[cl0a][cl0b];"
        "[cl0b]crop=384:216:384:216,boxblur=luma_radius=24:luma_power=2:chroma_radius=24:chroma_power=2[cl0c];"
        "[cl0a][cl0c]overlay=384:216,"
        "crop=608:1080:656:0,scale=1080:1920:flags=lanczos,"
        "setsar=1,fps=30,format=yuv420p"
    )


def test_clean_motion_and_color_filter_golden():
    edit = _edit(
        clean=[
            {"kind": "plate", "box": {"x": 0.1, "y": 0.7, "w": 0.5, "h": 0.1}},
            {"kind": "blur", "box": {"x": 0.2, "y": 0.2, "w": 0.2, "h": 0.2}},
        ],
        motion=[{
            "kind": "punch_in", "start": 1.0, "end": 3.0,
            "amount": 0.08, "ramp": 0.4,
        }],
        color={"preset": "warm_film"},
    )
    segment = _compile(edit)["segments"][0]
    assert segment["post_filter"] == (
        "zoompan=z='if(lt(on,30),1.000,1.000+0.080*min(1,(on-30)/12))':"
        "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        "d=1:s=1080x1920:fps=30,"
        "eq=brightness=0.020:contrast=1.080:saturation=0.950,"
        "colortemperature=temperature=5950,vignette=angle=0.1414,"
        "noise=alls=5:allf=t+u,unsharp=5:5:0.075"
    )
    assert segment["filter"] == (
        "drawbox=x=192:y=756:w=960:h=108:color=0x000000@1.000:t=fill,"
        "split=2[cl1a][cl1b];"
        "[cl1b]crop=384:216:384:216,boxblur=luma_radius=24:luma_power=2:chroma_radius=24:chroma_power=2[cl1c];"
        "[cl1a][cl1c]overlay=384:216,"
        "crop=608:1080:656:0,scale=1080:1920:flags=lanczos,"
        "setsar=1,fps=30,format=yuv420p,"
        "zoompan=z='if(lt(on,30),1.000,1.000+0.080*min(1,(on-30)/12))':"
        "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        "d=1:s=1080x1920:fps=30,"
        "eq=brightness=0.020:contrast=1.080:saturation=0.950,"
        "colortemperature=temperature=5950,vignette=angle=0.1414,"
        "noise=alls=5:allf=t+u,unsharp=5:5:0.075"
    )


def test_motion_kind_strings_golden():
    snap = _edit(motion=[{"kind": "snap_zoom", "start": 0.0, "end": 2.0}])
    assert _compile(snap, clips=CLIPS[:1])["segments"][0]["post_filter"] == (
        "zoompan=z='if(lt(on,0),1.000,1.120)':"
        "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        "d=1:s=1080x1920:fps=30"
    )
    push = _edit(motion=[{"kind": "push", "start": 0.0, "end": 2.0}])
    assert _compile(push, clips=CLIPS[:1])["segments"][0]["post_filter"] == (
        "zoompan=z='1.000+0.060*min(1,max(0,on-0)/60)':"
        "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        "d=1:s=1080x1920:fps=30"
    )
    shake = _edit(motion=[{"kind": "shake", "start": 0.0, "end": 2.0, "seed": 7}])
    assert _compile(shake, clips=CLIPS[:1])["segments"][0]["post_filter"] == (
        "zoompan=z='1.035':"
        "x='(iw-iw/zoom)/2+11*sin(2*PI*7.000*on/30+0.122)*between(on,0,60)':"
        "y='(ih-ih/zoom)/2+19*cos(2*PI*7.000*on/30+0.122)*between(on,0,60)':"
        "d=1:s=1080x1920:fps=30"
    )


def test_motion_activates_only_inside_its_window():
    edit = _edit(motion=[{"kind": "punch_in", "start": 4.5, "end": 5.5}])
    segments = _compile(edit)["segments"]
    assert segments[0]["motion_ids"] == []
    assert segments[0]["post_filter"] == ""
    assert segments[1]["motion_ids"] == ["mo01"]
    assert segments[1]["post_filter"].startswith("zoompan=z='if(lt(on,15)")


def test_color_none_and_zero_sliders_produce_no_filter():
    segment = _compile(_edit())["segments"][0]
    assert segment["post_filter"] == ""
    assert segment["post_filters"] == []
    assert "eq=" not in segment["filter"]


def test_color_numbers_compile_deterministically():
    edit = _edit(color={
        "preset": "none", "exposure": 0.1, "contrast": -0.2,
        "saturation": 0.3, "temperature": -0.5,
    })
    assert _compile(edit)["segments"][0]["post_filter"] == (
        "eq=brightness=0.100:contrast=0.800:saturation=1.300,"
        "colortemperature=temperature=7900"
    )


def test_lut_path_is_escaped():
    edit = _edit(color={
        "preset": "none",
        "lut": {"path": "/tmp/a:b'c.cube", "hash": "c" * 64},
    })
    assert _compile(edit)["segments"][0]["post_filter"] == (
        "lut3d=file='/tmp/a\\:b\\'c.cube'"
    )


def test_crop_guard_shifts_the_crop_window():
    edit = _edit(clean=[{
        "kind": "crop_guard", "box": {"x": 0.3, "y": 0.3, "w": 0.2, "h": 0.2},
    }])
    segment = _compile(edit)["segments"][0]
    assert segment["crop"] == {"x": 960, "y": 0, "w": 608, "h": 1080}
    assert segment["crop_filter"] == "crop=608:1080:960:0"
    assert segment["filter"].startswith("crop=")
    assert _compile(edit)["warnings"] == []


def test_impossible_crop_guard_warns_without_failing():
    edit = _edit(clean=[{
        "kind": "crop_guard", "box": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
    }])
    result = _compile(edit)
    assert result["segments"][0]["crop"] == {"x": 656, "y": 0, "w": 608, "h": 1080}
    assert [item["segment"] for item in result["warnings"]] == [0, 1]
    assert result["warnings"][0] == {
        "code": "crop_guard_unmet",
        "message": (
            "Crop cannot clear clean guard cl01 and keep the 9:16 frame."
        ),
        "layer_id": "cl01",
        "segment": 0,
    }


def test_clean_ranges_emit_enable_expressions_per_segment():
    edit = _edit(clean=[{
        "kind": "plate",
        "box": {"x": 0.1, "y": 0.7, "w": 0.5, "h": 0.1},
        "ranges": [{"start": 11.0, "end": 12.0}],
    }])
    segments = _compile(edit)["segments"]
    assert segments[0]["pre_filter"] == ""
    assert segments[0]["clean_ids"] == []
    assert segments[1]["pre_filter"] == (
        "drawbox=x=192:y=756:w=960:h=108:color=0x000000@1.000:t=fill"
        ":enable='between(t,1.000,2.000)'"
    )


def test_auto_crop_uses_the_scene_centre_and_manual_overrides_it():
    scenes = [{"id": 0, "crops": {"9:16": {"cx": 0.25, "cy": 0.5}}}]
    auto = _edit()
    assert _compile(auto, scenes=scenes)["segments"][0]["crop"]["x"] == 176
    manual = _edit(reframe={"mode": "manual", "cx": 0.75, "cy": 0.5})
    assert _compile(manual, scenes=scenes)["segments"][0]["crop"]["x"] == 1136
    override = _edit(reframe={"mode": "auto", "overrides": {"cx": 0.75}})
    assert _compile(override, scenes=scenes)["segments"][0]["crop"]["x"] == 1136


def test_4_5_zoom_crop_geometry():
    edit = _edit(
        aspect="4:5",
        reframe={"mode": "manual", "cx": 0.5, "cy": 0.5, "zoom": 2.0},
    )
    result = _compile(edit)
    segment = result["segments"][0]
    assert result["canvas"] == {"w": 1080, "h": 1350}
    assert segment["crop"] == {"x": 744, "y": 270, "w": 432, "h": 540}
    assert segment["scale_filter"] == "scale=1080:1350:flags=lanczos"


def test_4_5_auto_ignores_a_legacy_9_16_crop():
    scenes = [{"id": 0, "crop": {"cx": 0.1, "cy": 0.5}}]
    edit = _edit(aspect="4:5")
    segment = _compile(edit, scenes=scenes)["segments"][0]
    assert segment["crop"] == {"x": 528, "y": 0, "w": 864, "h": 1080}


def test_graphics_use_output_coordinates_and_are_sorted():
    edit = _edit(graphics=[
        {"type": "text", "kind": "hook", "text": "Stop", "start": 0.0, "end": 2.0},
        {"type": "fx", "kind": "arrow", "start": 0.0, "end": 1.0, "z": 20},
    ])
    overlays = _compile(edit)["overlays"]
    assert [item["id"] for item in overlays] == ["tx01", "fx02"]
    assert overlays[0]["rect"] == {"x": 0.12, "y": 0.05, "w": 0.76, "h": 0.16}
    assert overlays[0]["type"] == "text"
    assert overlays[1]["rect"] == {"x": 0.35, "y": 0.44, "w": 0.3, "h": 0.12}
    assert overlays[1]["type"] == "fx"
    assert overlays[1]["color"] == "#ffffff"


def test_caption_cues_compile_to_output_layers():
    track = {
        "track_id": "cap_test",
        "style_id": "clean",
        "style": {
            "font_size": 56,
            "color": "#FFFFFF",
            "stroke_color": "#000000",
            "stroke_width": 3,
            "background_opacity": 0.0,
            "position": "bottom",
        },
        "cues": [
            {"start": 0.0, "end": 2.0, "text": "Hello"},
            {"start": 2.5, "end": 4.0, "text": "world"},
        ],
    }
    edit = _edit(captions={"track_id": "cap_test", "style_id": "clean"})
    result = _compile(edit, caption_track=track)
    assert result["captions"] == {
        "track_id": "cap_test",
        "style_id": "clean",
        "enabled": True,
        "cue_count": 2,
        "compiled": True,
    }
    captions = [item for item in result["overlays"] if item["type"] == "caption"]
    assert [item["id"] for item in captions] == ["cap01", "cap02"]
    assert captions[0]["rect"] == {"x": 0.12, "y": 0.8, "w": 0.76, "h": 0.12}
    assert captions[0]["style"]["size"] == 56
    assert captions[0]["z"] == 50


def test_caption_reference_without_track_warns():
    edit = _edit(captions={"track_id": "cap_test", "style_id": "clean"})
    result = _compile(edit)
    assert result["captions"]["compiled"] is False
    assert result["warnings"] == [{
        "code": "caption_track_unavailable",
        "message": "Caption track is referenced but was not supplied to the compiler.",
        "track_id": "cap_test",
    }]


def test_mismatched_caption_track_is_rejected():
    edit = _edit(captions={"track_id": "cap_test", "style_id": "clean"})
    with pytest.raises(compose_render.ComposeError):
        _compile(edit, caption_track={"track_id": "cap_other", "cues": []})


def test_include_captions_false_skips_loading_and_warnings():
    edit = _edit(captions={"track_id": "cap_test", "style_id": "clean"})
    result = _compile(edit, include_captions=False)
    assert result["captions"]["compiled"] is False
    assert result["captions"]["cue_count"] == 0
    assert result["warnings"] == []


def test_source_dimensions_missing_uses_nominal_frame_and_warns():
    edit = _edit()
    result = _compile(edit, source={})
    assert result["source"] == {
        "width": 1080, "height": 1920, "dimensions_source": "nominal",
    }
    assert result["segments"][0]["crop"] == {"x": 0, "y": 0, "w": 1080, "h": 1920}
    assert result["warnings"] == [{
        "code": "source_dimensions_missing",
        "message": (
            "Source width and height are unavailable; clean and crop "
            "geometry uses the nominal 1080x1920 frame."
        ),
    }]


def test_compile_is_deterministic_and_reports_edit_identity():
    edit = _edit(
        clean=[{"kind": "plate", "box": {"x": 0.1, "y": 0.7, "w": 0.5, "h": 0.1}}],
        motion=[{"kind": "push", "start": 0.0, "end": 2.0}],
        color={"preset": "cool_fade"},
    )
    first = _compile(edit)
    second = _compile(edit)
    assert first == second
    assert first["edit_id"] == edit["id"]
    assert first["edit_hash"] == edit["hash"]
    assert first["renderer_version"] == edits.RENDERER_VERSION
    assert first["counts"] == {
        "segments": 2, "overlays": 0, "clean": 2, "motion": 1,
    }
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_compiler_makes_no_process_calls(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("compile_edit must not start a process")

    monkeypatch.setattr(subprocess, "run", explode)
    monkeypatch.setattr(subprocess, "Popen", explode)
    monkeypatch.setattr(os, "system", explode)
    monkeypatch.setattr(os, "popen", explode)
    result = _compile(_edit(
        clean=[{"kind": "blur", "box": {"x": 0.2, "y": 0.2, "w": 0.2, "h": 0.2}}],
        motion=[{"kind": "shake", "start": 0.0, "end": 1.0}],
        color={"preset": "warm_film"},
    ))
    assert result["segments"]


def test_missing_clips_is_an_input_error():
    with pytest.raises(compose_render.ComposeInputError):
        compose_render.compile_edit(_edit(), clips=[])
    with pytest.raises(compose_render.ComposeInputError):
        compose_render.compile_edit(_edit(), clips=[{"start": 1.0, "end": 1.0}])


def test_invalid_stored_edit_is_a_compose_error():
    edit = _edit()
    edit["hash"] = "edh_" + "0" * 32
    with pytest.raises(compose_render.ComposeError):
        _compile(edit)


def test_emphasis_sticker_and_underline_layers_golden():
    import fx

    edit = _edit(graphics=[
        {"type": "text", "kind": "emphasis", "text": "Now",
         "start": 0.0, "end": 2.0, "z": 10},
        fx.sticker("star", 0.0, 2.0, z=20),
        fx.underline(0.0, 2.0, z=21),
    ])
    layers = _compile(edit)["overlays"]
    assert [layer["id"] for layer in layers] == ["tx01", "fx02", "fx03"]
    assert layers[0] == {
        "id": "tx01", "type": "text", "kind": "emphasis", "text": "Now",
        "start": 0.0, "end": 2.0, "box": {"w": 0.6, "h": 0.12},
        "rect": {"x": 0.2, "y": 0.44, "w": 0.6, "h": 0.12},
        "z": 10,
        "style": {
            "font": "sans", "size": 44, "weight": 800, "color": "#ffffff",
            "background": "none", "stroke": "#000000", "align": "center",
            "uppercase": False, "shadow": True,
        },
        "opacity": 1.0, "safe_zone": True, "duration": 2.0,
        "raster": {
            "mode": "static", "frames": 1, "fps": 30,
            "hash": "lyh_8750944062edab20c318cbcd",
        },
    }
    sticker = layers[1]
    assert sticker["asset"] == {
        "id": "star", "hash": "214e99de162b327c3efa8083fcdcac2e",
    }
    assert sticker["asset_path"] == str(fx.sticker_path("star"))
    assert sticker["rect"] == {"x": 0.38, "y": 0.38, "w": 0.24, "h": 0.24}
    assert sticker["raster"]["hash"] == "lyh_e1ad289239b9413ae8624ec4"
    underline = layers[2]
    assert underline["rect"] == {"x": 0.3, "y": 0.47, "w": 0.4, "h": 0.06}
    assert underline["raster"]["hash"] == "lyh_0fab73d4cacdc8d8ac123da9"


def test_beat_snap_perspective_motion_filter_golden():
    edit = _edit(
        motion=[{"kind": "snap_zoom", "start": 0.98, "end": 2.0, "amount": 0.12}],
    )
    result = _compile(
        edit, beats=[1.0], motion_engine="perspective", clips=CLIPS[:1],
    )
    assert result["segments"][0]["post_filter"] == (
        "perspective="
        "x0='(((W-W/(if(lt(on,30),1.000,1.1200)))/2)+0)':"
        "y0='(((H-H/(if(lt(on,30),1.000,1.1200)))/2)+0)':"
        "x1='(W-((W-W/(if(lt(on,30),1.000,1.1200)))/2)+0)':"
        "y1='(((H-H/(if(lt(on,30),1.000,1.1200)))/2)+0)':"
        "x2='(((W-W/(if(lt(on,30),1.000,1.1200)))/2)+0)':"
        "y2='(H-((H-H/(if(lt(on,30),1.000,1.1200)))/2)+0)':"
        "x3='(W-((W-W/(if(lt(on,30),1.000,1.1200)))/2)+0)':"
        "y3='(H-((H-H/(if(lt(on,30),1.000,1.1200)))/2)+0)':"
        "interpolation=cubic:eval=frame"
    )


def test_blur_radius_is_capped_for_small_boxes():
    # A 1-line caption box is ~60x40 px; ffmpeg refuses boxblur=24 on it.
    edit = _edit(clean=[{
        "kind": "blur", "box": {"x": 0.4, "y": 0.4, "w": 0.04, "h": 0.04},
        "radius": 24,
    }])
    segment = _compile(edit)["segments"][0]
    assert "boxblur=luma_radius=20:luma_power=2:chroma_radius=9:chroma_power=2" in (
        segment["pre_filter"]
    )


def test_delogo_clean_layer_compiles_to_interpolation():
    result = _compile(_edit(
        clean=[{"kind": "delogo", "box": {"x": 0.1, "y": 0.7, "w": 0.5, "h": 0.1}}],
    ))
    assert result["segments"][0]["clean_ids"]
    assert result["segments"][0]["pre_filters"] == ["delogo=x=192:y=756:w=960:h=108"]


def test_clean_preview_blur_swaps_fill_for_a_check_view():
    edit = _edit(clean=[{
        "kind": "fill", "method": "lama",
        "box": {"x": 0.2, "y": 0.2, "w": 0.2, "h": 0.2},
    }])
    filled = _compile(edit)["segments"][0]
    assert filled["fill"]["method"] == "lama"
    blurred = _compile(edit, clean_preview="blur", include_graphics=False)["segments"][0]
    assert blurred["fill"] is None
    assert "boxblur=" in blurred["pre_filter"]


def test_opening_the_clean_preview_never_starts_an_ai_fill(monkeypatch, tmp_path):
    import routes_edits
    import textfill

    rows = {"frames": 40, "cached": False}
    monkeypatch.setattr(textfill, "estimate_span", lambda **_kwargs: dict(rows))
    compiled = {"segments": [
        {"frames": 40, "start": 0.0, "fill": {"layers": [], "method": "lama"}},
        {"frames": 10, "start": 2.0},
    ]}
    assert routes_edits._fills_missing({"source": {}}, tmp_path, compiled, 30) is True
    rows["cached"] = True
    assert routes_edits._fills_missing({"source": {}}, tmp_path, compiled, 30) is False
    rows.update(frames=0, cached=False)
    assert routes_edits._fills_missing({"source": {}}, tmp_path, compiled, 30) is False


def test_a_frame_past_the_real_end_of_a_source_uses_its_last_frame(monkeypatch, tmp_path):
    import render

    job_dir = tmp_path / "jobs" / "j"
    job_dir.mkdir(parents=True)
    commands = []

    def fake_run(cmd, timeout=None, cwd=None, cancel_event=None):
        commands.append(cmd)
        if "-sseof" in cmd:
            from pathlib import Path

            Path(cmd[-1]).write_bytes(b"png")

    def fake_burn(_png, _overlays, output, *_args, **_kwargs):
        output.write_bytes(b"jpeg")

    monkeypatch.setattr(render, "_run", fake_run)
    monkeypatch.setattr(render, "_segment", lambda *args, **kwargs: False)
    monkeypatch.setattr(render, "_burn_frame", fake_burn)
    monkeypatch.setattr(render, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(render, "_clip_media", lambda _dir, _segment, source, meta: (source, meta))
    monkeypatch.setattr(render, "_choose_encoder", lambda _encoder: "libx264")
    compiled = {
        "aspect": "9:16", "overlays": [],
        "segments": [{"frames": 30, "start": 0.0, "out_start": 0.0, "out_end": 1.0}],
    }
    payload = render.render_story_frame("s.mp4", {}, job_dir, compiled, 1.0)
    assert payload == b"jpeg"
    assert any("-sseof" in cmd for cmd in commands)
