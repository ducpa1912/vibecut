"""Wave 3 compose layers: text bridge, FX, colour LUTs and beat snap."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import color
import compose_render
import edits
import fx
import overlays

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


# ---------------------------------------------------------------- text layers


def test_overlay_text_layer_validates_and_maps_kinds():
    hook = overlays.edit_text_layer({
        "kind": "hook",
        "text": "  Stop   scrolling ",
        "start": 0.0,
        "end": 2.0,
        "anchor": "top-center",
        "box": {"w": 0.76, "h": 0.16},
    })
    assert hook["type"] == "text"
    assert hook["kind"] == "hook"
    assert hook["text"] == "Stop scrolling"
    assert hook["id"] == "ov01"
    assert hook["box"] == {"w": 0.76, "h": 0.16}
    assert hook["anchor"] == "top-center"

    caption = overlays.edit_text_layer({
        "kind": "caption", "text": "mid line", "start": 1.0, "end": 3.0,
    })
    assert caption["kind"] == "emphasis"
    assert caption["anchor"] == "bottom-center"


def test_overlay_text_layer_uses_the_shared_validators():
    with pytest.raises(overlays.OverlayError):
        overlays.edit_text_layer({"kind": "hook", "text": "", "start": 0, "end": 1})
    with pytest.raises(overlays.OverlayError):
        overlays.edit_text_layer({
            "kind": "hook", "text": "x", "start": 0, "end": 1,
            "style": {"size": 400},
        })
    with pytest.raises(overlays.OverlayError):
        overlays.edit_text_layer({
            "kind": "hook", "text": "x", "start": 0, "end": 4.0,
        }, max_end=3.0)


def test_overlay_plan_converts_to_edit_graphics():
    plan = overlays.build_plan(
        {"id": "j1", "source": {"duration": 6.0}},
        "9:16",
        [
            {"kind": "hook", "text": "Hook", "start": 0.0, "end": 2.0},
            {"kind": "cta", "text": "Follow", "start": 2.0, "end": 4.0},
        ],
    )
    layers = overlays.plan_text_layers(plan)
    assert [layer["kind"] for layer in layers] == ["hook", "cta"]
    built = edits.build_edit(
        story_ref=STORY_REF, aspect="9:16", graphics=layers,
    )
    assert [item["type"] for item in built["graphics"]] == ["text", "text"]
    assert [item["text"] for item in built["graphics"]] == ["Hook", "Follow"]


def test_compiled_overlay_text_keeps_output_coordinates():
    text = overlays.edit_text_layer({
        "kind": "caption", "text": "Beat", "start": 0.0, "end": 2.0,
    })
    result = _compile(_edit(graphics=[text]))
    layer = result["overlays"][0]
    assert layer["type"] == "text"
    assert layer["kind"] == "emphasis"
    assert layer["raster"]["mode"] == "static"


# ---------------------------------------------------------------- motion FX


@pytest.mark.parametrize("builder", [fx.punch_in, fx.snap_zoom, fx.push, fx.shake])
def test_motion_builders_are_valid_edit_layers(builder):
    layer = builder(0.5, 1.5)
    built = edits.build_edit(story_ref=STORY_REF, aspect="9:16", motion=[layer])
    assert built["motion"][0]["kind"] == builder.__name__
    assert built["motion"][0]["start"] == 0.5
    assert layer["kind"] == builder.__name__
    assert layer["end"] > layer["start"]


def test_motion_builder_overrides_normalize():
    layer = fx.punch_in(0.0, 1.0, amount=0.2, ramp=0.5, layer_id="punch")
    assert layer["id"] == "punch"
    assert layer["amount"] == 0.2
    assert layer["ramp"] == 0.5


def test_motion_builder_rejects_unknown_kind():
    with pytest.raises(fx.FxError):
        fx.motion("wobble", 0.0, 1.0)


# ---------------------------------------------------------------- graphic FX


def test_graphic_builders_are_valid_edit_layers():
    for builder in (fx.arrow, fx.circle, fx.underline, fx.progress_bar):
        layer = builder(0.0, 2.0)
        built = edits.build_edit(story_ref=STORY_REF, aspect="9:16", graphics=[layer])
        assert built["graphics"][0]["kind"] == layer["kind"]
        assert layer["type"] == "fx"


def test_sticker_asset_hash_matches_the_bundled_png():
    asset = fx.sticker_asset("star")
    assert asset["id"] == "star"
    assert len(asset["hash"]) == 32
    assert asset["hash"] == fx.sticker_file_hash("star")


@pytest.mark.parametrize(
    "value,expected",
    [("🔥", "fire"), ("❤️", "heart"), ("✅", "check"), ("wow", "wow")],
)
def test_emoji_resolves_to_a_bundled_sticker(value, expected):
    assert fx.sticker_id(value) == expected


def test_sticker_and_emoji_build_sticker_layers():
    layer = fx.sticker("✨", 1.0, 3.0)
    assert layer["kind"] == "sticker"
    assert layer["asset"]["id"] == "sparkle"
    emoji_layer = fx.emoji("🔥", 1.0, 3.0, box={"w": 0.2, "h": 0.2})
    assert emoji_layer["asset"]["id"] == "fire"


def test_unknown_sticker_is_rejected():
    with pytest.raises(fx.FxError):
        fx.sticker_asset("not-a-sticker")
    with pytest.raises(fx.FxError):
        fx.sticker("🦄", 0.0, 1.0)


def test_sticker_compiles_with_a_resolved_asset_path():
    layer = fx.sticker("star", 1.0, 3.0)
    result = _compile(_edit(graphics=[layer]))
    compiled = result["overlays"][0]
    assert compiled["asset"] == fx.sticker_asset("star")
    assert compiled["asset_path"] == str(fx.sticker_path("star"))
    assert compiled["raster"]["mode"] == "static"
    assert result["warnings"] == []


def test_sticker_with_a_stale_hash_is_skipped_with_a_warning():
    asset = fx.sticker_asset("star")
    layer = fx.sticker("star", 0.0, 2.0, asset={**asset, "hash": "b" * 32})
    result = _compile(_edit(graphics=[layer]))
    assert [item for item in result["overlays"] if item["type"] == "fx"] == []
    assert result["warnings"] == [{
        "code": "sticker_hash_mismatch",
        "message": (
            "Sticker star no longer matches the Edit's asset hash; layer skipped."
        ),
        "layer_id": "fx01",
    }]


def test_sticker_unknown_asset_cannot_be_built_by_the_editor():
    # The editor cannot save an unbundled sticker id, so the warning path is
    # only reachable for an Edit from another install.
    with pytest.raises(fx.FxError):
        fx.sticker("ghost", 0.0, 1.0)


def test_progress_bar_raster_is_animated():
    layer = fx.progress_bar(0.0, 2.0)
    result = _compile(_edit(graphics=[layer]))
    raster = result["overlays"][0]["raster"]
    assert raster["mode"] == "sequence"
    assert raster["frames"] == 60


# ---------------------------------------------------------------- beat snap


def test_beat_times_accepts_grids_lists_and_dicts():
    assert fx.beat_times({"bpm": 120, "beats": [2.0, 0.5]}) == [0.5, 2.0]
    assert fx.beat_times([{"t": 1.0}, {"start": 2.0}, 3.0]) == [1.0, 2.0, 3.0]
    assert fx.beat_times(None) == []


def test_beat_snap_moves_inside_the_window_only():
    beats = [1.0, 2.0]
    assert fx.beat_snap(1.08, beats) == 1.0
    assert fx.beat_snap(1.13, beats) == 1.13
    assert fx.beat_snap(2.119, beats) == 2.0
    assert fx.beat_snap(2.121, beats) == 2.121
    assert fx.beat_snap(1.08, None) == 1.08


def test_snap_span_keeps_a_usable_duration():
    start, end = fx.snap_span(0.95, 1.02, [1.0], minimum=0.2)
    assert start == 1.0
    assert end == 1.2


def test_snap_motion_and_graphics_preserve_unrelated_fields():
    motion = [fx.punch_in(1.05, 2.02, amount=0.2)]
    snapped = fx.snap_motion(motion, [1.0, 2.0])[0]
    assert (snapped["start"], snapped["end"]) == (1.0, 2.0)
    assert snapped["amount"] == 0.2

    graphic = fx.arrow(1.04, 2.03)
    snapped_graphic = fx.snap_graphics([graphic], [1.0, 2.0])[0]
    assert (snapped_graphic["start"], snapped_graphic["end"]) == (1.0, 2.0)
    assert snapped_graphic["kind"] == "arrow"


def test_compile_snaps_motion_and_graphics_to_beats():
    edit = _edit(
        motion=[{"kind": "punch_in", "start": 1.03, "end": 2.0, "amount": 0.08}],
        graphics=[{"type": "text", "kind": "hook", "text": "Beat",
                   "start": 1.04, "end": 2.0}],
    )
    result = _compile(
        edit,
        beats={"bpm": 120, "beats": [1.0, 2.0]},
        motion_engine="perspective",
    )
    assert result["beat_snap"] == {"enabled": True, "beats": 2, "window": 0.120}
    assert [item["start"] for item in result["overlays"]] == [1.0]
    assert result["segments"][0]["motion_engine"] == "perspective"
    assert "if(lt((on/30),1.000)" in result["segments"][0]["post_filter"]


def test_compile_without_beats_keeps_layer_times():
    edit = _edit(graphics=[{
        "type": "text", "kind": "hook", "text": "No snap", "start": 1.04, "end": 2.0,
    }])
    result = _compile(edit)
    assert result["beat_snap"] == {"enabled": False, "beats": 0, "window": 0.120}
    assert result["overlays"][0]["start"] == 1.04


# ---------------------------------------------------------------- colour


def test_eight_lut_presets_exist_and_match_the_generator():
    assert color.preset_names() == (
        "warm_film", "cool_fade", "vivid_pop", "soft_matte",
        "golden_hour", "teal_orange", "mono_contrast", "clean_bright",
    )
    for name in color.preset_names():
        path = color.lut_path(name)
        assert path.is_file(), path
        assert path.read_bytes() == color.lut_bytes(name)
        asset = color.lut_asset(name)
        assert asset["path"] == str(path)
        assert asset["hash"] == color.lut_hash(name)


def test_cube_file_has_a_valid_header_and_grid():
    text = color.lut_text("warm_film")
    lines = text.splitlines()
    assert lines[0] == 'TITLE "warm_film"'
    assert lines[1] == f"LUT_3D_SIZE {color.LUT_SIZE}"
    assert len(lines) == 4 + color.LUT_SIZE ** 3
    assert lines[4] == "0.000000 0.000000 0.000000"
    assert len(lines[-1].split()) == 3


def test_ensure_luts_rewrites_only_missing_files(tmp_path):
    written = color.ensure_luts(tmp_path)
    assert len(written) == 8
    assert color.ensure_luts(tmp_path) == []
    stale = tmp_path / "warm_film.cube"
    stale.write_text("broken")
    assert color.ensure_luts(tmp_path) == [stale]
    assert stale.read_bytes() == color.lut_bytes("warm_film")


def test_preset_plan_slider_mode_matches_the_edit_presets():
    plan = color.preset_plan("warm_film")
    assert plan["preset"] == "warm_film"
    assert plan["lut"] is None
    assert plan["exposure"] == edits.COLOR_PRESETS["warm_film"]["exposure"]


def test_preset_plan_lut_mode_moves_tonal_values_into_the_lut():
    plan = color.preset_plan("teal_orange", use_lut=True)
    assert plan["lut"] == color.lut_asset("teal_orange")
    assert all(plan[key] == 0.0 for key in color.TONAL_KEYS)
    assert plan["vignette"] == edits.COLOR_PRESETS["teal_orange"]["vignette"]


def test_preset_plan_lut_mode_keeps_explicit_overrides():
    plan = color.preset_plan(
        "vivid_pop", use_lut=True,
        overrides={"saturation": -0.5, "vignette": 0.3},
    )
    assert plan["saturation"] == -0.5
    assert plan["vignette"] == 0.3
    assert plan["lut"]["path"].endswith("vivid_pop.cube")


def test_lut_plan_compiles_to_a_lut3d_filter():
    edit = _edit(color=color.preset_plan("warm_film", use_lut=True))
    segment = _compile(edit)["segments"][0]
    assert segment["post_filter"].startswith(
        f"lut3d=file='{color.lut_path('warm_film')}'"
    )
    assert "eq=" not in segment["post_filter"]


def test_as_lut_preserves_spatial_sliders_only():
    stored = edits.normalize_color({"preset": "golden_hour", "grain": 0.4})
    plan = color.as_lut(stored)
    assert plan["lut"] == color.lut_asset("golden_hour")
    assert plan["grain"] == 0.4
    assert plan["exposure"] == 0.0


def test_unknown_colour_preset_is_rejected():
    with pytest.raises(color.ColorError):
        color.preset_plan("sepia")
    with pytest.raises(color.ColorError):
        color.lut_asset("none")


# ---------------------------------------------------------------- artifacts


def test_artifact_id_changes_with_the_edit_hash(tmp_path):
    import artifacts

    job = {
        "id": "j1",
        "source": {"name": "clip.mp4", "duration": 4.0, "width": 1080, "height": 1920},
        "analysis": {"scenes": []},
    }
    plan = {"target": 2, "clips": [{"scene": 0, "start": 0.0, "end": 2.0}]}
    legacy = artifacts.build_spec(job, plan, story_id="s1")
    assert "edit_hash" not in legacy.payload()
    first = artifacts.build_spec(job, plan, story_id="s1", edit_hash="edh_" + "a" * 32)
    second = artifacts.build_spec(job, plan, story_id="s1", edit_hash="edh_" + "b" * 32)
    assert first.payload()["edit_hash"].startswith("edh_")
    assert artifacts.artifact_id(first) != artifacts.artifact_id(second)
    assert artifacts.artifact_id(legacy) != artifacts.artifact_id(first)
    restored = artifacts.ArtifactSpec.from_payload(first.payload())
    assert restored.edit_hash == first.edit_hash
    assert json.dumps(first.payload(), sort_keys=True) == json.dumps(
        restored.payload(), sort_keys=True,
    )


def test_sticker_pngs_are_committed_and_small():
    root = Path(fx.ASSET_DIR)
    for name, filename in fx.STICKERS.items():
        path = root / filename
        assert path.is_file(), path
        assert path.stat().st_size > 1000
        assert path.read_bytes().startswith(b"\x89PNG")
