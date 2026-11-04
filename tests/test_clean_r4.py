"""Clean R4: the R0 and R1 fixes that had only source-text checks, run for real."""

from __future__ import annotations

import pytest
from test_studio_js import needs_node, run_module

import compose_render
from textfill import mask as masks

BOX = {"x": 0.1, "y": 0.8, "w": 0.8, "h": 0.05}


@needs_node
@pytest.mark.parametrize(
    "steps,expected",
    [
        ("m.setFillAvailable(true);", "fill"),
        ("m.setFillAvailable(false);", "blur"),
        ('m.setFillAvailable(true); m.rememberDrawKind("blur");', "blur"),
        ('m.setFillAvailable(true); m.rememberDrawKind("fill");', "fill"),
        # The model went away after AI fill was last used.
        ('m.setFillAvailable(true); m.rememberDrawKind("fill"); m.setFillAvailable(false);', "blur"),
        # Removed kinds are never remembered.
        ('m.setFillAvailable(true); m.rememberDrawKind("cover");', "fill"),
    ],
)
def test_a_new_box_starts_on_the_right_method(steps, expected):
    assert run_module("edit/layers/clean.js", f"{steps} return m.drawKind();") == expected


@needs_node
def test_clicking_the_brush_again_finds_the_layer_of_that_text():
    out = run_module("edit/layers/clean.js", """
        const box = {x: 0.1, y: 0.8, w: 0.8, h: 0.05};
        const found = {box, text_key: "abc", ranges: [{start: 10, end: 16}]};
        const painted = {tracklet_id: "trk_a", kind: "fill", box, text_key: "abc", ranges: [{start: 10, end: 16}]};
        const otherTime = {...painted, text_key: "def", ranges: [{start: 30, end: 36}]};
        const otherArea = {...painted, box: {...box, y: 0.1}};
        const drawn = {kind: "fill", box, ranges: [{start: 10, end: 16}]};
        return {
          again: m.sameScanText(painted, found),
          otherTime: m.sameScanText(otherTime, found),
          otherArea: m.sameScanText(otherArea, found),
          drawn: m.sameScanText(drawn, found),
        };
    """)
    assert out == {"again": True, "otherTime": False, "otherArea": False, "drawn": False}


def _filled_frames(layer, start, end, fps=30.0):
    table = masks.frame_rects(
        [layer], start=start, fps=fps, frames=int(round((end - start) * fps)), width=720, height=1280,
    )
    return sum(1 for rects in table if rects)


@pytest.mark.parametrize("tracklet", ["trk_a", None])
@pytest.mark.parametrize("beat", range(6, 18))
def test_a_beat_runs_the_fill_exactly_when_the_fill_has_frames_on_it(beat, tracklet):
    layer = {
        "id": "a", "kind": "fill", "method": "sttn", "z": 0, "box": dict(BOX),
        "ranges": [{"start": 10.0, "end": 12.0}],
    }
    if tracklet:
        layer["tracklet_id"] = tracklet
    plan, _ = compose_render._fill_plan([layer], float(beat), float(beat + 1))
    assert (plan is not None) == (_filled_frames(layer, float(beat), float(beat + 1)) > 0)
