"""Clean R3: a layer list that can be read, and the Clean lane in view."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLEAN = (ROOT / "static/studio/edit/layers/clean.js").read_text(encoding="utf-8")
INDEX = (ROOT / "static/studio/edit/index.js").read_text(encoding="utf-8")
TIMELINE = (ROOT / "static/studio/edit/timeline.js").read_text(encoding="utf-8")
CSS = (ROOT / "static/studio/edit/edit.css").read_text(encoding="utf-8")
needs_node = pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")


def _groups(layers):
    script = f"""
      globalThis.localStorage = {{ getItem() {{ return null; }} }};
      const m = await import({json.dumps((ROOT / "static/studio/edit/layers/clean.js").as_uri())});
      const groups = m.cleanGroups({json.dumps(layers)});
      console.log(JSON.stringify(groups.map((group) => group.layers.map((layer) => layer.id))));
    """
    out = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True, text=True, timeout=30, check=True,
    )
    return json.loads(out.stdout.strip().splitlines()[-1])


BOX = {"x": 0.1, "y": 0.8, "w": 0.8, "h": 0.05}


def _scan(layer_id, tracklet="trk_a", label="same words", box=BOX, ranges=None):
    return {
        "id": layer_id, "kind": "fill", "tracklet_id": tracklet, "label": label,
        "box": box, "ranges": ranges or [{"start": 10, "end": 12}],
    }


@needs_node
def test_copies_of_one_text_are_one_row():
    assert _groups([_scan("a"), _scan("b"), _scan("c", tracklet="trk_b")]) == [["a", "b", "c"]]


@needs_node
def test_other_text_in_the_same_area_at_another_time_has_its_own_row():
    other = _scan("b", tracklet="trk_b", label="other words", ranges=[{"start": 30, "end": 32}])
    assert _groups([_scan("a"), other]) == [["a"], ["b"]]


@needs_node
def test_same_words_elsewhere_on_screen_have_their_own_row():
    top = _scan("b", box={"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.05})
    assert _groups([_scan("a"), top]) == [["a"], ["b"]]


@needs_node
def test_drawn_boxes_are_never_grouped():
    drawn = {"id": "a", "kind": "blur", "label": "Remove text", "box": BOX, "ranges": []}
    assert _groups([drawn, {**drawn, "id": "b"}]) == [["a"], ["b"]]


def test_the_list_folds_pieces_and_layers_outside_the_moment():
    assert "function groupRow(group, selectedId)" in CLEAN
    assert "st-clean-group-toggle" in CLEAN and "st-clean-piece" in CLEAN
    assert "outside this moment. Kept, not deleted." in CLEAN
    assert "function isOutsideStory(layer)" in INDEX


def test_a_grouped_switch_changes_every_piece():
    assert "for (const layer of layers) ctx.setCleanMethod?.(layer.id, value);" in CLEAN
    assert "methodSwitch(group.layers)" in CLEAN


def test_old_kinds_are_marked_and_new_ones_rely_on_the_switch():
    assert "This is an old ${KIND_COPY[layer.kind]" in CLEAN


def test_opening_clean_brings_its_lane_into_view():
    assert "function showLane(id)" in TIMELINE and "focusLane(id)" in TIMELINE
    assert INDEX.count('timeline?.focusLane?.("clean")') == 2


def test_a_delete_during_an_autosave_still_runs():
    assert "attempt(50);" in INDEX
    assert "if (!state.selected || saving) return;" not in INDEX


def test_the_ruler_stays_in_view():
    assert ".st-tl-ruler { position: sticky" in CSS


def test_the_timeline_resizes_and_remembers():
    assert "st-timeline-resize" in TIMELINE and "--st-timeline-h" in TIMELINE
    assert "vibecut.studio.timelineHeight" in TIMELINE
    assert "var(--st-timeline-h, 214px)" in CSS


def test_no_clean_or_timeline_rule_goes_under_11px():
    import re

    scope = re.compile(r"st-tl|st-timeline|st-clean|st-found|st-layer|st-method|st-box-method|st-fill|st-compare")
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", CSS):
        if not scope.search(selector):
            continue
        for size in re.findall(r"font-size:\s*(\d+(?:\.\d+)?)px", body):
            assert float(size) >= 11, selector.strip()
