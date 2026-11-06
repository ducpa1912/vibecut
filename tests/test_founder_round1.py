"""Fixes from the founder's first real-video test of Clean (2026-11-04)."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_studio_js import needs_node, run_module

import detect

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "static" / "studio"
CLEAN = (STUDIO / "edit/layers/clean.js").read_text(encoding="utf-8")
INDEX = (STUDIO / "edit/index.js").read_text(encoding="utf-8")
PREVIEW = (STUDIO / "edit/preview.js").read_text(encoding="utf-8")
TIMELINE = (STUDIO / "edit/timeline.js").read_text(encoding="utf-8")
FINISH = (STUDIO / "finish.js").read_text(encoding="utf-8")
STORIES = (STUDIO / "stories.js").read_text(encoding="utf-8")
ROUTES = (ROOT / "routes_studio.py").read_text(encoding="utf-8")

CLIPS = """[
  {start: 60, end: 64},
  {kind: "blank", start: 0, end: 2},
  {start: 100, end: 110},
]"""


@needs_node
def test_a_clean_bar_sits_at_story_time_not_source_time():
    out = run_module("edit/model.js", f"""
        const edit = {{clean: [
          {{id: "drawn", kind: "fill", ranges: [{{start: 61, end: 63}}]}},
          {{id: "scan", kind: "fill", tracklet_id: "trk", ranges: [{{start: 101, end: 103}}]}},
          {{id: "gone", kind: "fill", ranges: [{{start: 5, end: 6}}]}},
        ]}};
        const row = m.layerSpans(edit, null, 16, {CLIPS}).find((item) => item.kind === "clean");
        return row.items.map((item) => [item.layerId, item.start, item.end, item.drawn]);
    """)
    assert out == [["drawn", 1, 3, True], ["scan", 7, 9, False]]


@needs_node
def test_a_range_across_a_cut_makes_one_bar_per_clip():
    out = run_module("edit/model.js", f"""
        return m.storySpans({CLIPS}, 62, 104).map((span) => [span.start, span.end, span.clipIndex]);
    """)
    assert out == [[2, 4, 0], [6, 10, 2]]


@needs_node
def test_a_dragged_bar_saves_source_time():
    out = run_module("edit/model.js", f"""
        const clips = {CLIPS};
        const ranges = [{{start: 61, end: 63}}, {{start: 101, end: 103}}];
        const span = m.storySpans(clips, 101, 103)[0];
        return {{
          moved: m.movedCleanRanges(ranges, 1, span, 7.5, 8),
          whole: m.storyToSourceRanges(clips, 2, 8),
        }};
    """)
    assert out["moved"] == [{"start": 61, "end": 63}, {"start": 101.5, "end": 102}]
    assert out["whole"] == [{"start": 62, "end": 64}, {"start": 100, "end": 102}]


@needs_node
def test_shortening_a_range_that_crosses_a_cut_keeps_its_other_part():
    out = run_module("edit/model.js", """
        const clips = [{start: 10, end: 20}, {start: 20, end: 30}];
        const span = m.storySpans(clips, 15, 25)[0];
        return m.movedCleanRanges([{start: 15, end: 25}], 0, span, 5, 7);
    """)
    assert out == [{"start": 15, "end": 17}, {"start": 20, "end": 25}]


@needs_node
@pytest.mark.parametrize("kind,at,expected", [
    ("snap_zoom", 3.0, 1.5),
    ("snap_zoom", 1.0, 1.0),
    ("punch_in", 2.25, 1.25),
    ("punch_in", 3.5, 1.5),
    ("push", 3.0, 1.25),
    # A zoom holds to the beat's end, past the motion's own end.
    ("snap_zoom", 5.5, 1.5),
    ("shake", 3.0, 1.0),
])
def test_the_preview_zoom_matches_the_render_motion(kind, at, expected):
    out = run_module("edit/canvas-tools.js", f"""
        const edit = {{motion: [{{kind: "{kind}", start: 2, end: 4, amount: 0.5, ramp: 0.5}}]}};
        return m.motionZoomAt(edit, {at}, 0, 6);
    """)
    assert out == pytest.approx(expected)


@needs_node
def test_motion_in_another_beat_does_not_zoom_this_one():
    out = run_module("edit/canvas-tools.js", """
        const edit = {motion: [{kind: "snap_zoom", start: 2, end: 4, amount: 0.5}]};
        return m.motionZoomAt(edit, 7, 6, 12);
    """)
    assert out == 1


@needs_node
def test_a_zoomed_crop_keeps_its_centre():
    out = run_module("edit/canvas-tools.js", """
        return m.zoomedCrop({x: 0.2, y: 0, w: 0.4, h: 1}, 2);
    """)
    assert out == pytest.approx({"x": 0.3, "y": 0.25, "w": 0.2, "h": 0.5})


def _tracklet(tid, start, end):
    return {"id": tid, "ranges": [{"start": start, "end": end}]}


def test_a_scene_scan_keeps_text_found_elsewhere():
    previous = {
        "status": "ready",
        "tracklets": [_tracklet("far", 50, 60), _tracklet("here", 12, 14)],
        "clean_prefill": [{"tracklet_id": "far"}, {"tracklet_id": "here"}],
    }
    report = {
        "status": "ready", "scope": {"start": 10, "end": 20},
        "tracklets": [_tracklet("new", 11, 13)], "clean_prefill": [{"tracklet_id": "new"}],
    }
    detect._keep_text_outside_scope(report, previous, 10.0, 20.0)
    assert [item["id"] for item in report["tracklets"]] == ["new", "far"]
    assert [item["tracklet_id"] for item in report["clean_prefill"]] == ["new", "far"]
    assert "scope" not in report


def test_a_scene_scan_after_another_scene_stays_scoped():
    previous = {
        "status": "ready", "scope": {"start": 40, "end": 50},
        "tracklets": [_tracklet("far", 41, 44)], "clean_prefill": [],
    }
    report = {"status": "ready", "scope": {"start": 10, "end": 20}, "tracklets": [], "clean_prefill": []}
    detect._keep_text_outside_scope(report, previous, 10.0, 20.0)
    assert report["scope"] == {"start": 10, "end": 20}
    assert [item["id"] for item in report["tracklets"]] == ["far"]


def test_a_scene_scan_with_no_earlier_report_changes_nothing():
    report = {"status": "ready", "scope": {"start": 10, "end": 20}, "tracklets": []}
    detect._keep_text_outside_scope(report, None, 10.0, 20.0)
    assert report == {"status": "ready", "scope": {"start": 10, "end": 20}, "tracklets": []}


def test_this_scene_only_filters_a_whole_video_scan():
    assert "!report?.scope || reportMatchesScene(ctx.getSceneRange?.())" in CLEAN
    assert '"Scan again"' in CLEAN


def test_test_one_second_goes_to_the_layer_first():
    assert "function seekToCleanLayer(layerId)" in INDEX
    assert INDEX.count("if (!seekToCleanLayer(layerId)) return;") == 2
    assert "This layer is outside this moment" in INDEX


def test_a_refused_fill_test_says_why_in_the_log():
    assert 'LOGGER.warning("Fill test refused' in ROUTES
    assert ROUTES.count("raise _fill_refused(") == 2


def test_timeline_and_canvas_can_be_dragged():
    assert "function beginLayerDrag(event, button, item, kind, view)" in TIMELINE
    assert "onLayerTime: (change) => setLayerTime(change)" in INDEX
    assert "function beginTextDrag(layer, frame, crop, event)" in PREVIEW
    assert "onTextBox: (id, box, options) => placeTextOnVideo(id, box, options)" in INDEX
    # A plain click on text must not move it onto the video.
    assert "} else if (current.textBox) {" in PREVIEW


def test_drawn_boxes_have_their_own_colour():
    assert 'String(item.layer?.tracklet_id || "").trim() ? LAYER_COLOURS.clean : DRAWN_BOX_COLOUR' in PREVIEW
    assert 'is-drawn' in TIMELINE


def test_the_wording_does_not_say_remove():
    assert '"Delete this layer"' in CLEAN
    assert '`Clean ${ticked.length}`' in CLEAN
    assert 'text: "Remove layer"' not in CLEAN


def test_render_is_one_click_from_review():
    assert "Edit this moment" in FINISH
    assert 'text: "Queue"' in FINISH
    assert 'queueTabButton("queue", "Queue"' in FINISH


def test_finish_shape_comes_from_edit_and_quality_has_six_tiers():
    assert "Shape comes from Edit" in FINISH
    assert '"Shape",' not in FINISH
    for quality in ("360", "draft", "720", "final", "1440", "2160"):
        assert f'value: "{quality}"' in FINISH


def test_review_and_notes_share_one_panel_with_a_playable_preview():
    assert "reviewPlayer" in FINISH
    assert "clean-preview" in FINISH
    assert "Quick blur" in FINISH
    assert "Clean check · this frame" in FINISH
    assert "Review notes" not in FINISH


def test_review_preview_waits_for_a_render_and_then_shows_the_fill():
    assert "Preview waits for the render to finish" in FINISH
    held = FINISH.index("Preview waits for the render to finish")
    assert FINISH.index("if (hasActiveWork())", held - 200) < held
    assert 'reviewMode = "fill";\n        renderReviewCard();' in FINISH


def test_queue_sits_beside_render_with_queue_and_history_tabs():
    assert "st-finish-render-grid" in FINISH
    assert "st-finish-queue-card" in FINISH
    assert 'queueTabButton("queue", "Queue"' in FINISH
    assert 'queueTabButton("history", "History"' in FINISH
    assert "st-finish-drawer" not in FINISH


def test_queue_history_can_delete_an_old_queue():
    assert "async function deleteQueue" in FINISH
    assert 'method: "DELETE"' in FINISH
    assert 'text: "Delete"' in FINISH


def test_review_rebuilds_after_the_edit_loads():
    assert "renderReviewCard();" in FINISH
    assert "renderRenderCard();" in FINISH


def test_publish_calls_the_unit_a_story_and_names_full_video():
    assert "One ready story" in FINISH
    assert "No ready story yet" in FINISH
    assert "No ready cut" not in FINISH
    assert '"Full video"' in FINISH
    assert "preferredReadyArtifact" in FINISH
    assert 'artifactStoryId(item) === "st_full_video"' in FINISH
    assert "st-finish-publish-grid" in FINISH
    assert "st-finish-finished" in FINISH
    assert 'text: "Open file"' in FINISH
    assert 'text: "Download"' in FINISH


def test_moments_can_be_cleared_and_a_search_with_none_keeps_them():
    assert "Clear all moments" in STORIES and "Delete moment" in STORIES
    assert "No new moments found. Your moments are unchanged." in STORIES
    assert '"/api/jobs/{job_id}/clip-sets/{set_id}/stories/{story_id}"' in ROUTES
