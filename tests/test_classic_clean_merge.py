"""Classic Clean merge rules and the review-first wiring.

The merge rules are pure data, so this runs them in Node against
`static/classic/clean-merge.js`. The rest are source checks: the split control,
the playable detection check and the one clean-and-render action.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MERGE = ROOT / "static" / "classic" / "clean-merge.js"
APP = ROOT / "static" / "classic" / "app.js"
PAGE = ROOT / "static" / "classic" / "index.html"
CSS = ROOT / "static" / "classic" / "style.css"
I18N = ROOT / "static" / "classic" / "i18n.js"


def between(text: str, start: str, end: str) -> str:
    assert start in text, start
    body = text[text.index(start):]
    assert end in body, end
    return body[:body.index(end)]


def run_merge(assertions: str) -> None:
    script = f"""
const assert = require("node:assert/strict");
const merge = require(process.argv[1]);
{assertions}
"""
    result = subprocess.run(
        ["node", "-e", script, str(MERGE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_same_area_uses_iou_or_the_centre_window():
    run_merge(
        """
const box = { x: 0.20, y: 0.30, w: 0.30, h: 0.18 };
assert.equal(merge.sameArea(box, { ...box, x: 0.205, y: 0.305 }), true);
assert.equal(merge.sameArea(box, { ...box, x: 0.50, y: 0.30 }), false);
assert.equal(merge.sameArea(box, { x: 0.13, y: 0.22, w: 0.05, h: 0.04 }), false);
assert.equal(
  merge.sameArea({ x: 0, y: 0, w: 0.1, h: 0.1 }, { x: 0.05, y: 0, w: 0.1, h: 0.1 }),
  true,
);
assert.equal(merge.sameArea(null, box), false);
"""
    )


def test_text_keys_and_readings_follow_the_studio_rules():
    run_merge(
        """
assert.equal(merge.foundTextKey("  Hello, WORLD!  "), "helloworld");
assert.equal(merge.foundTextKey("Xin chào 2026"), "xinchào2026");
assert.equal(merge.sameFoundText("hello", "hello"), true);
assert.equal(merge.sameFoundText("hello world", "hello"), true);
assert.equal(merge.sameFoundText("cat", "cats"), false);
assert.equal(merge.sameFoundText("abcd", "abcdef"), true);
assert.equal(merge.sameFoundText("hello", "other"), false);
"""
    )


def test_same_scan_text_needs_a_tracklet_area_and_text_or_overlap():
    run_merge(
        """
const base = {
  tracklet_id: "t1",
  box: { x: 0.2, y: 0.2, w: 0.3, h: 0.1 },
  text_key: "hello",
  ranges: [{ start: 1, end: 2 }],
};
assert.equal(merge.sameScanText(base, { ...base }), true);
assert.equal(merge.sameScanText({ ...base, text_key: "other" }, { ...base, text_key: "third" }), true);
assert.equal(merge.sameScanText(base, { ...base, text_key: "other", ranges: [{ start: 2.01, end: 3 }] }), false);
assert.equal(merge.sameScanText(base, { ...base, box: { x: 0.7, y: 0.7, w: 0.1, h: 0.1 } }), false);
assert.equal(merge.sameScanText({ ...base, tracklet_id: "" }, base), false);
"""
    )


def test_subtitles_in_one_area_merge_and_keep_every_member():
    run_merge(
        """
const entries = [
  { tracklet_id: "t1", kind: "subtitle", box: { x: 0.1, y: 0.7, w: 0.4, h: 0.1 },
    text: "first line", text_key: "first line", confidence: 0.7, ranges: [{ start: 0, end: 1 }] },
  { tracklet_id: "t2", kind: "subtitle", box: { x: 0.12, y: 0.72, w: 0.42, h: 0.1 },
    text: "a much longer line", text_key: "a much longer line", confidence: 0.9,
    ranges: [{ start: 1.2, end: 2.4 }] },
];
const rows = merge.mergeFoundEntries(entries);
assert.equal(rows.length, 1);
assert.deepEqual(rows[0].ids, ["t1", "t2"]);
assert.equal(rows[0].tracklet_id, "t1");
assert.equal(rows[0].text, "a much longer line");
assert.equal(rows[0].lines, 2);
assert.equal(rows[0].confidence, 0.9);
assert.deepEqual(rows[0].ranges, [{ start: 0, end: 1 }, { start: 1.2, end: 2.4 }]);
assert.ok(Math.abs(rows[0].box.w - 0.44) < 1e-9);
assert.ok(Math.abs(rows[0].box.h - 0.12) < 1e-9);
assert.equal(rows[0].box.x, 0.1);
assert.equal(rows[0].box.y, 0.7);
"""
    )


def test_subtitles_and_other_kinds_stay_apart_by_area_and_kind():
    run_merge(
        """
const rows = merge.mergeFoundEntries([
  { tracklet_id: "s1", kind: "subtitle", box: { x: 0.1, y: 0.1, w: 0.3, h: 0.1 },
    text: "top", ranges: [{ start: 0, end: 1 }] },
  { tracklet_id: "s2", kind: "subtitle", box: { x: 0.1, y: 0.8, w: 0.3, h: 0.1 },
    text: "bottom", ranges: [{ start: 0, end: 1 }] },
  { tracklet_id: "x1", kind: "title", box: { x: 0.1, y: 0.1, w: 0.3, h: 0.1 },
    text: "title words", ranges: [{ start: 0, end: 1 }] },
]);
assert.equal(rows.length, 3);
"""
    )


def test_same_or_contained_title_readings_merge_only_in_one_area():
    run_merge(
        """
const rows = merge.mergeFoundEntries([
  { tracklet_id: "a", kind: "title", box: { x: 0.2, y: 0.2, w: 0.4, h: 0.1 },
    text: "Hello world", ranges: [{ start: 0, end: 1 }] },
  { tracklet_id: "b", kind: "title", box: { x: 0.21, y: 0.2, w: 0.41, h: 0.1 },
    text: "Hello worl", ranges: [{ start: 1, end: 2 }] },
  { tracklet_id: "c", kind: "title", box: { x: 0.2, y: 0.2, w: 0.4, h: 0.1 },
    text: "Different", ranges: [{ start: 3, end: 4 }] },
  { tracklet_id: "d", kind: "title", box: { x: 0.60, y: 0.60, w: 0.3, h: 0.1 },
    text: "Hello world", ranges: [{ start: 0, end: 1 }] },
]);
assert.equal(rows.length, 3);
const home = rows.find((row) => row.ids.includes("a"));
assert.deepEqual(home.ids, ["a", "b"]);
assert.equal(home.text, "Hello world");
"""
    )


def test_dedupe_merges_saved_twins_and_leaves_manual_layers_alone():
    run_merge(
        """
const layers = [
  { id: "cl01", source: "scan", tracklet_id: "t1", tracklet_kind: "subtitle",
    box: { x: 0.1, y: 0.7, w: 0.3, h: 0.1 }, ranges: [{ start: 0, end: 1 }],
    label: "subtitle", text_key: "first", hidden: true },
  { id: "cl02", source: "scan", tracklet_id: "t2", tracklet_kind: "subtitle",
    box: { x: 0.12, y: 0.72, w: 0.34, h: 0.1 }, ranges: [{ start: 1.2, end: 2.4 }],
    label: "a much longer label", text_key: "a much longer line", hidden: false },
  { id: "cl03", source: "manual", box: { x: 0.1, y: 0.7, w: 0.3, h: 0.1 },
    ranges: [{ start: 0, end: 1 }], label: "Drawn box" },
  { id: "cl04", source: "scan", tracklet_id: "t3", tracklet_kind: "title",
    box: { x: 0.1, y: 0.7, w: 0.3, h: 0.1 }, ranges: [{ start: 0, end: 1 }],
    label: "title", text_key: "other" },
];
const out = merge.dedupeCleanLayers(layers);
assert.equal(out.changed, true);
assert.deepEqual(out.layers.map((layer) => layer.id), ["cl01", "cl03", "cl04"]);
const merged = out.layers[0];
assert.equal(merged.id, "cl01");
assert.equal(merged.tracklet_id, "t1");
assert.equal(merged.label, "a much longer label");
assert.equal(merged.text_key, "a much longer line");
assert.equal(merged.hidden, false);
assert.deepEqual(merged.ranges, [{ start: 0, end: 1 }, { start: 1.2, end: 2.4 }]);
assert.equal(merged.box.x, 0.1);
assert.equal(merged.box.y, 0.7);
assert.ok(Math.abs(merged.box.w - 0.36) < 1e-9);
assert.ok(Math.abs(merged.box.h - 0.12) < 1e-9);
"""
    )


def test_dedupe_keeps_an_unbounded_twin_unbounded():
    run_merge(
        """
const layers = [
  { id: "cl01", source: "scan", tracklet_id: "t1", tracklet_kind: "title",
    box: { x: 0.1, y: 0.1, w: 0.2, h: 0.1 }, ranges: [],
    label: "title", text_key: "same" },
  { id: "cl02", source: "scan", tracklet_id: "t2", tracklet_kind: "title",
    box: { x: 0.11, y: 0.11, w: 0.2, h: 0.1 }, ranges: [{ start: 1, end: 2 }],
    label: "title", text_key: "same" },
];
const out = merge.dedupeCleanLayers(layers);
assert.equal(out.changed, true);
assert.deepEqual(out.layers[0].ranges, []);
"""
    )


def test_dedupe_keeps_same_text_in_different_areas_apart():    run_merge(
        """
const layers = [
  { id: "cl01", source: "scan", tracklet_id: "t1", tracklet_kind: "title",
    box: { x: 0.1, y: 0.1, w: 0.2, h: 0.1 }, ranges: [{ start: 0, end: 1 }],
    label: "title", text_key: "same" },
  { id: "cl02", source: "scan", tracklet_id: "t2", tracklet_kind: "title",
    box: { x: 0.7, y: 0.7, w: 0.2, h: 0.1 }, ranges: [{ start: 0, end: 1 }],
    label: "title", text_key: "same" },
];
const out = merge.dedupeCleanLayers(layers);
assert.equal(out.changed, false);
assert.equal(out.layers.length, 2);
"""
    )


def test_review_first_setting_and_scan_only_split_are_wired():
    app = APP.read_text(encoding="utf-8")
    page = PAGE.read_text(encoding="utf-8")
    assert 'id="setup-clean-flow"' in page
    assert 'value="review_first"' in page
    assert 'value="one_click"' in page
    assert "setupCleanFlow: $(\"#setup-clean-flow\")" in app
    assert 'classic_clean: {' in app
    assert 'flow: dom.setupCleanFlow?.value === "one_click" ? "one_click" : "review_first"' in app
    assert 'cleanFlow: "review_first"' in app
    assert 'classicClean.flow === "one_click" ? "one_click" : "review_first"' in app

    source = between(app, "async function runSourceCleanSteps(options = {})", "function sourceCleanErrorText(error)")
    assert "if (scanOnly) {" in source
    assert "Review the rows, then clean." in source
    assert source.index("if (scanOnly) {") < source.index("applyFoundTicks()")
    assert source.index("if (scanOnly) {") < source.index("await persistClassicText(classicPlanClips());")
    assert source.index("if (scanOnly) {") < source.index("await startSourceCleanRender();")

    cut = between(app, "async function runCutClean(options = {})", "async function cancelCutClean()")
    assert "if (scanOnly) {" in cut
    assert "Review the rows, then clean." in cut
    scan_only = between(cut, "if (scanOnly) {", "if (!cutCleanFoundRows(rows).length) {")
    assert "applyFoundTicks()" not in scan_only
    assert "persistClassicText" not in scan_only
    assert "startRender" not in scan_only
    assert "return;" in scan_only
    assert cut.index("if (scanOnly) {") < cut.index("applyFoundTicks()")
    assert cut.index("if (scanOnly) {") < cut.index("await persistClassicText(classicPlanClips());")

    assert 'label = reviewFirst ? "Find text" : "Find text & clean";' in app
    assert "`Clean ${count} text${count === 1 ? \"\" : \"s\"} & render`" in app
    assert "needsSelection" in app
    assert "if (!reviewFirst && duration >= 180 && !confirm) {" in app
    assert 'let label = reviewFirst ? "Find text" : "Find text & clean";' in app
    assert "row.added = matching.length > 0;" in app
    assert "clean-found-selected" in app
    assert "Select ${esc(row.text)} for cleaning" in app

    change = between(app, 'dom.cleanFound?.addEventListener("change"', 'dom.cleanFound?.addEventListener("keydown"')
    assert "applyFoundTicks" not in change
    assert "startRender" not in change
    assert "persistClassicText" not in change


def test_lane_packing_uses_every_range_interval():
    app = APP.read_text(encoding="utf-8")
    lane = between(app, "function cleanRowLaneIntervals(row)", "function cleanScanRows()")
    assert "const mapped = state.cleanScope === \"cut\" && !row?.manual" in lane
    assert "return mapped;" in lane
    assert "return [{ start: 0, end: Math.max(0.1, cleanCutTotal()) }];" in lane
    packing = between(app, "function assignCleanLanes(rows)", "function cleanScanRows()")
    assert "intervals.some((item) =>" in packing
    assert "lanes[lane].some((other) =>" in packing
    assert "lanes[lane].push(...intervals);" in packing


def test_playable_detection_check_is_wired_without_a_render():
    app = APP.read_text(encoding="utf-8")
    page = PAGE.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    assert 'id="clean-review-video"' in page
    assert 'id="clean-review-blur"' in page
    assert 'id="cut-clean-play-note"' in page
    assert "Render a draft once to play this cut." in page
    assert 'id="clean-preview-play"' in page
    assert 'aria-pressed="false"' in page
    assert "source/media" in app
    assert "backdrop-filter: blur(14px)" in css
    assert "-webkit-backdrop-filter: blur(14px)" in css
    assert 'src="/static/classic/clean-merge.js' in page
    assert page.index("clean-merge.js") < page.index("app.js")

    play = between(app, "async function startCleanReviewPlayback()", "function toggleCleanReviewPlayback()")
    assert "source/media" in app
    assert "video.play()" in play
    assert "startRender" not in play
    assert "persistClassicText" not in play
    assert "applyFoundTicks" not in play
    assert "fill/preview" not in play
    assert "timeupdate" in app
    assert "requestAnimationFrame(cleanReviewTick)" in app
    assert "Render a draft once to play this cut." in app
    assert "cut-clean-play-note" in page
    assert "const showPlayNote = cutCleanActive() && !playable && !renderActive && !ready && !working;" in app
    assert "The video could not play here. Showing the still frame." in app
    assert "Detection check · all found boxes blurred · not the final clean" in app
    frame = between(app, "async function refreshCleanFrame(force = false)", "function cleanCropHeader(response)")
    assert "if (state.classicText.review.active) return;" in frame
    assert "fill/preview" not in between(
        app, "async function startCleanReviewPlayback()", "function toggleCleanReviewPlayback()",
    )
    overlay = between(app, "function paintCleanReviewBoxes(t = currentCleanTime())", "function updateCleanReviewButton()")
    assert "for (const row of cleanScanRows())" in overlay
    assert "cleanReviewCandidates" not in overlay
    assert "row.ticked" not in overlay
    assert "cleanReviewRecord" not in overlay


def test_vietnamese_carries_the_review_copy():
    words = I18N.read_text(encoding="utf-8")
    for english, vietnamese in (
        ("Find text", "Tìm chữ"),
        ("Play", "Phát"),
        ("Pause", "Tạm dừng"),
        ("Clean review", "Xem lại làm sạch"),
        ("Selected", "Đã chọn"),
        ("Render a draft once to play this cut.", "Render một bản nháp để phát bản cắt này."),
    ):
        assert f'"{english}": "{vietnamese}"' in words, english
    assert "Detection check · all found boxes blurred · not the final clean" in words
    assert "/^(\\d+) texts? found\\. Review the rows, then clean\\.$/" in words
