"""The same text shows once: in the scan report, the list and the timeline."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

import detect

ROOT = Path(__file__).resolve().parent.parent
EDIT = ROOT / "static" / "studio" / "edit"


def _tracklet(tracklet_id, *ranges, y=0.8):
    return {
        "id": tracklet_id,
        "kind": "subtitle",
        "text_sample": "Hello world",
        "box": {"x": 0.1, "y": y, "w": 0.8, "h": 0.05},
        "ranges": [{"start": low, "end": high} for low, high in ranges],
    }


def test_a_scene_scan_joins_text_it_finds_again_instead_of_listing_it_twice():
    previous = {"status": "ready", "tracklets": [_tracklet("trk_a", (0, 5), (40, 45))], "clean_prefill": []}
    report = {
        "status": "ready", "scope": {"start": 10, "end": 20},
        "tracklets": [_tracklet("trk_a", (11, 13))], "clean_prefill": [],
    }
    detect._keep_text_outside_scope(report, previous, 10.0, 20.0)
    assert [item["id"] for item in report["tracklets"]] == ["trk_a"]
    assert report["tracklets"][0]["ranges"] == [
        {"start": 0, "end": 5}, {"start": 11, "end": 13}, {"start": 40, "end": 45},
    ]


def test_scanning_the_same_scene_twice_adds_nothing():
    first = {"status": "ready", "tracklets": [_tracklet("trk_a", (0, 5))], "clean_prefill": []}
    for _ in range(2):
        report = {
            "status": "ready", "scope": {"start": 10, "end": 20},
            "tracklets": [_tracklet("trk_a", (11, 13))], "clean_prefill": [],
        }
        detect._keep_text_outside_scope(report, first, 10.0, 20.0)
        first = report
    assert [item["id"] for item in report["tracklets"]] == ["trk_a"]
    assert report["tracklets"][0]["ranges"] == [{"start": 0, "end": 5}, {"start": 11, "end": 13}]


def test_text_cut_by_the_scene_keeps_its_time_outside_it():
    previous = {"status": "ready", "tracklets": [_tracklet("trk_old", (5, 15))], "clean_prefill": []}
    report = {"status": "ready", "scope": {"start": 10, "end": 20}, "tracklets": [], "clean_prefill": []}
    detect._keep_text_outside_scope(report, previous, 10.0, 20.0)
    assert report["tracklets"][0]["ranges"] == [{"start": 5, "end": 10}]


def _node(tmp_path, body):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    script = tmp_path / "run.mjs"
    script.write_text(body, encoding="utf-8")
    done = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_one_layer_is_one_bar_across_cuts(tmp_path):
    clips = [{"start": 0, "end": 4}, {"start": 10, "end": 14}, {"start": 20, "end": 24}]
    edit = {"clean": [{"id": "c1", "label": "Sub", "tracklet_id": "t", "ranges": [{"start": 0, "end": 30}]}]}
    gap = {"clean": [{"id": "c1", "label": "Sub", "tracklet_id": "t", "ranges": [{"start": 0, "end": 1}, {"start": 3, "end": 4}]}]}
    out = _node(tmp_path, (
        f'import {{ layerSpans }} from "{(EDIT / "model.js").as_uri()}";\n'
        f"const clips = {json.dumps(clips)};\n"
        "const bars = (edit) => layerSpans(edit, null, 12, clips)[0].items;\n"
        f"console.log(JSON.stringify([bars({json.dumps(edit)}), bars({json.dumps(gap)})]));\n"
    ))
    whole, split = out
    assert len(whole) == 1
    assert (whole[0]["start"], whole[0]["end"]) == (0, 12)
    assert whole[0]["span"] is None and len(whole[0]["pieces"]) == 3
    assert [bar["repeat"] for bar in split] == [False, True], "the name shows once"
    assert split[0]["span"] is not None


def test_dragging_a_bar_across_cuts_leaves_other_bars_alone(tmp_path):
    clips = [{"start": 0, "end": 4}, {"start": 10, "end": 14}]
    ranges = [{"start": 0, "end": 14}, {"start": 50, "end": 60}]
    out = _node(tmp_path, (
        f'import {{ layerSpans, replacedCleanSpans }} from "{(EDIT / "model.js").as_uri()}";\n'
        f"const clips = {json.dumps(clips)};\nconst ranges = {json.dumps(ranges)};\n"
        'const [bar] = layerSpans({ clean: [{ id: "c", tracklet_id: "t", ranges }] }, null, 8, clips)[0].items;\n'
        "console.log(JSON.stringify(replacedCleanSpans(ranges, bar.pieces, clips, 0, 6)));\n"
    ))
    assert out == [{"start": 0, "end": 12}, {"start": 50, "end": 60}]


def test_the_found_list_shows_one_row_per_text(tmp_path):
    def row(tracklet_id, text, low, high, y=0.8):
        return {**_tracklet(tracklet_id, (low, high), y=y), "text_sample": text, "kind": "title"}

    tracklets = [
        row("a", "Hello world", 0, 5),
        row("a", "Hello world", 8, 9),
        row("b", "Hello world!", 20, 25),
        row("c", "Hello worl", 30, 31),
        row("d", "Other line", 40, 41),
        row("e", "Hello world", 50, 51, y=0.1),
    ]
    out = _node(tmp_path, (
        f'const m = await import({json.dumps((EDIT / "layers" / "clean.js").as_uri())});\n'
        f"console.log(JSON.stringify(m.mergeFoundTracklets({json.dumps(tracklets)})));\n"
    ))
    assert [item["ids"] for item in out] == [["a", "b", "c"], ["d"], ["e"]]
    assert out[0]["text_sample"] == "Hello world"
    assert out[0]["ranges"][0] == {"start": 0, "end": 5}
    assert len(out[0]["ranges"]) == 4


def test_subtitle_lines_in_one_area_are_one_row_and_one_group(tmp_path):
    lines = [
        {**_tracklet(f"s{index}", (index, index + 1)), "text_sample": text}
        for index, text in enumerate(["First line here", "Second line here", "Third line here"])
    ]
    layers = [
        {"id": f"c{index}", "tracklet_id": f"s{index}", "tracklet_kind": "subtitle",
         "label": f"Line {index}", "box": lines[0]["box"], "ranges": [{"start": index, "end": index + 1}]}
        for index in range(3)
    ]
    out = _node(tmp_path, (
        f'const m = await import({json.dumps((EDIT / "layers" / "clean.js").as_uri())});\n'
        f"const rows = m.mergeFoundTracklets({json.dumps(lines)});\n"
        f"const groups = m.cleanGroups({json.dumps(layers)});\n"
        "console.log(JSON.stringify({ rows, groups: groups.map((group) => group.layers.length) }));\n"
    ))
    assert len(out["rows"]) == 1
    assert out["rows"][0]["ids"] == ["s0", "s1", "s2"]
    assert out["rows"][0]["lines"] == 3
    assert out["groups"] == [3]


def test_saved_copies_of_a_layer_are_dropped_but_painted_ones_stay(tmp_path):
    def layer(layer_id, **extra):
        return {
            "id": layer_id, "kind": "fill", "method": "sttn", "tracklet_id": "trk_0001",
            "box": {"x": 0.06, "y": 0.8, "w": 0.87, "h": 0.05},
            "ranges": [{"start": 5.6, "end": 12.2}], **extra,
        }

    layers = [
        layer("a"), layer("b"), layer("c"),
        layer("painted", mask={"strokes": [{"r": 0.02, "points": [{"x": 0.1, "y": 0.8}]}]}),
        {**layer("d"), "tracklet_id": "trk_0002"},
    ]
    out = _node(tmp_path, (
        f'import {{ withoutRepeatedCleanLayers }} from "{(EDIT / "model.js").as_uri()}";\n'
        f"console.log(JSON.stringify(withoutRepeatedCleanLayers({json.dumps(layers)}).map((item) => item.id)));\n"
    ))
    assert out == ["a", "painted", "d"]


def test_every_clean_bar_can_change_time_on_the_timeline():
    source = (EDIT / "timeline.js").read_text(encoding="utf-8")
    assert '(kind === "clean" || kind === "text" || kind === "effects")' in source
