"""P1: Layers list, Clean boxes on the preview, draw/move/resize/delete."""

from __future__ import annotations

from pathlib import Path

from test_studio_js import needs_node, run_module

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "static" / "studio"
INDEX = (STUDIO / "edit" / "index.js").read_text(encoding="utf-8")
PREVIEW = (STUDIO / "edit" / "preview.js").read_text(encoding="utf-8")
TIMELINE = (STUDIO / "edit" / "timeline.js").read_text(encoding="utf-8")
PANEL = (STUDIO / "edit" / "layers-panel.js").read_text(encoding="utf-8")
CSS = (STUDIO / "edit" / "edit.css").read_text(encoding="utf-8")


@needs_node
def test_crop_matches_the_renderer_centre_crop():
    out = run_module("edit/canvas-tools.js", """
        return m.cropAt({
          edit: {reframe: {mode: "manual", cx: 0.5, cy: 0.5, zoom: 1}},
          job: {source: {width: 1920, height: 1080}},
          story: null, time: 0, aspect: "9:16",
        });
    """)
    assert abs(out["x"] - 0.341796875) < 1e-6
    assert abs(out["w"] - 0.31640625) < 1e-6
    assert out["y"] == 0 and out["h"] == 1


@needs_node
def test_auto_mode_uses_the_active_scene_crop():
    out = run_module("edit/canvas-tools.js", """
        return m.cropAt({
          edit: {reframe: {mode: "auto", cx: 0.5, cy: 0.5, zoom: 1}},
          job: {source: {width: 1920, height: 1080},
            analysis: {scenes: [{id: 7, crops: {"9:16": {cx: 0.6, cy: 0.4}}}]}},
          story: {clips: [{scene: 7, start: 0, end: 4, dur: 4}]},
          time: 1, aspect: "9:16",
        });
    """)
    assert abs(out["x"] - 0.441796875) < 1e-6
    assert out["y"] == 0


@needs_node
def test_source_box_and_output_frame_round_trip():
    out = run_module("edit/canvas-tools.js", """
        const crop = {x: 0.2, y: 0.1, w: 0.5, h: 0.8};
        const box = {x: 0.3, y: 0.2, w: 0.1, h: 0.12};
        const frame = m.boxToFrame(box, crop);
        return {frame, back: m.frameToBox(frame, crop)};
    """)
    assert abs(out["frame"]["x"] - 0.2) < 1e-9
    assert abs(out["frame"]["w"] - 0.2) < 1e-9
    back = out["back"]
    assert abs(back["x"] - 0.3) < 1e-6
    assert abs(back["w"] - 0.1) < 1e-6
    assert abs(back["h"] - 0.12) < 1e-6


@needs_node
def test_move_and_resize_keep_the_box_inside_the_source():
    out = run_module("edit/canvas-tools.js", """
        return {
          moved: m.moveBox({x: 0.1, y: 0.1, w: 0.2, h: 0.2}, 0.9, 0.9),
          resized: m.resizeBox({x: 0.2, y: 0.2, w: 0.4, h: 0.4}, "se", 0.1, 0.1),
          shrunk: m.resizeBox({x: 0.2, y: 0.2, w: 0.4, h: 0.4}, "nw", 0.1, 0.1),
          tooSmall: m.resizeBox({x: 0.2, y: 0.2, w: 0.4, h: 0.4}, "e", -0.9, 0),
        };
    """)
    assert abs(out["moved"]["x"] - 0.8) < 1e-9
    assert abs(out["moved"]["y"] - 0.8) < 1e-9
    assert abs(out["resized"]["w"] - 0.5) < 1e-9
    assert abs(out["resized"]["h"] - 0.5) < 1e-9
    assert abs(out["shrunk"]["x"] - 0.3) < 1e-9
    assert abs(out["shrunk"]["w"] - 0.3) < 1e-9
    assert out["tooSmall"]["w"] >= 0.004 - 1e-9


@needs_node
def test_handle_hit_testing_and_clean_ranges():
    out = run_module("edit/canvas-tools.js", """
        const rect = {x: 0, y: 0, w: 100, h: 100};
        return {
          se: m.handleAt(rect, {x: 99, y: 99}, 3),
          middle: m.handleAt(rect, {x: 50, y: 50}, 3),
          inside: m.insideRect(rect, {x: 50, y: 50}),
          active: m.layerActive({ranges: [{start: 2, end: 4}]}, 3),
          before: m.layerActive({ranges: [{start: 2, end: 4}]}, 1),
          whole: m.layerActive({ranges: []}, 100),
          clipped: m.visibleRect({x: -0.2, y: 0.1, w: 0.4, h: 0.2}),
        };
    """)
    assert out["se"] == "se"
    assert out["middle"] == ""
    assert out["inside"] is True
    assert out["active"] is True
    assert out["before"] is False
    assert out["whole"] is True
    assert abs(out["clipped"]["x"]) < 1e-9
    assert abs(out["clipped"]["w"] - 0.2) < 1e-9


@needs_node
def test_story_output_time_maps_to_source_time():
    out = run_module("edit/canvas-tools.js", """
        const story = {clips: [
          {start: 10, end: 14, dur: 4},
          {start: 20, end: 24, dur: 4},
        ]};
        return [m.sourceTimeAt(story, 0), m.sourceTimeAt(story, 5), m.sourceTimeAt(story, 8)];
    """)
    assert out == [10, 21, 24]


def test_layers_panel_is_in_the_editor_and_grouped_in_timeline_order():
    assert 'id="st-edit-layers"' in INDEX
    assert "renderLayers()" in INDEX
    assert "renderLayersPanel" in PANEL
    assert 'kind: "clean", label: "Remove text"' in PANEL
    assert 'kind: "text", label: "Text"' in PANEL
    assert 'kind: "captions", label: "Captions"' in PANEL
    assert 'kind: "effects", label: "Effects"' in PANEL
    assert 'kind: "color", label: "Colour"' in PANEL
    assert 'kind: "audio", label: "Audio"' in PANEL
    assert "st-layers-add-menu" in PANEL
    assert "st-layer-caret" in PANEL
    assert "st-layer-eye" in PANEL
    assert "st-layer-warning" in PANEL


def test_preview_draws_clean_boxes_and_has_box_tools():
    assert "drawCleanBoxes" in PREVIEW
    assert "cleanAt(" in PREVIEW
    assert "handleAt(" in PREVIEW
    assert "moveBox(" in PREVIEW
    assert "resizeBox(" in PREVIEW
    assert "onBoxChange" in PREVIEW
    assert "onBoxCreate" in PREVIEW
    assert 'id="st-preview-tool-select"' in PREVIEW
    assert 'id="st-preview-tool-box"' in PREVIEW
    assert 'event.key === "b" || event.key === "B"' in INDEX
    assert 'preview?.setTool("box")' in INDEX


def test_delete_removes_the_selected_layer_from_all_three_places():
    assert "onLayerKeydown" in INDEX
    assert 'event.key !== "Delete" && event.key !== "Backspace"' in INDEX
    assert "removeSelectedLayer" in INDEX
    assert "removeLayer(kind, id)" in INDEX
    assert "preview?.setSelected(null)" in INDEX
    assert "timeline?.setSelected(null)" in INDEX
    assert "renderLayers()" in INDEX


def test_timeline_bars_select_layers_and_adding_lives_in_layers():
    assert "onAdd" in TIMELINE
    assert "st-tl-add" not in TIMELINE
    assert "handlers.onAdd(row.kind)" not in TIMELINE
    assert 'handlers.onSelect(kind, item.layerId || item.id)' in TIMELINE
    assert "st-layers-add-menu" in PANEL
    assert ".st-layers" in CSS
    assert ".st-preview-tool" in CSS


def test_drawn_box_uses_the_same_manual_clean_shape():
    import re

    clean = (STUDIO / "edit" / "layers" / "clean.js").read_text(encoding="utf-8")
    assert "export function manualLayer(index, box = null)" in clean
    assert "box: paddedBox(box, \"delogo\")" in clean
    assert re.search(r"manualLayer\(layers\.length, box\)", INDEX)
