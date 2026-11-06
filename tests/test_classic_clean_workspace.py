"""Classic Clean workspace revision: pure timeline rules and static wiring.

No browser, no media and no server. The timeline/merge rules run in Node; the
rest checks the shipped page, script and stylesheet.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSIC = ROOT / "static" / "classic"
APP = CLASSIC / "app.js"
PAGE = CLASSIC / "index.html"
CSS = CLASSIC / "style.css"
I18N = CLASSIC / "i18n.js"
TIMELINE = CLASSIC / "clean-timeline.js"


def between(text: str, start: str, end: str) -> str:
    assert start in text, start
    body = text[text.index(start):]
    assert end in body, end
    return body[:body.index(end)]


def run_node(assertions: str, module: Path = TIMELINE) -> None:
    script = f"""
const assert = require("node:assert/strict");
const timeline = require(process.argv[1]);
const merge = require(process.argv[2]);
{assertions}
"""
    result = subprocess.run(
        ["node", "-e", script, str(module), str(CLASSIC / "clean-merge.js")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_one_bar_per_tight_member_and_a_fallback_label():
    run_node(
        """
assert.equal(timeline.barLabel("  Hello   world  ", 0, 8), "Hello w…");
assert.equal(timeline.barLabel("", 2), "Remove Box 3");
const rows = [{
  identity: "scan:a+b", lane: 0,
  entryRows: [
    { tracklet_id: "a", text: "first line", box: { x: 0, y: 0, w: 0.2, h: 0.1 },
      ranges: [{ start: 1, end: 2 }] },
    { tracklet_id: "b", text: "second line", box: { x: 0.1, y: 0.2, w: 0.3, h: 0.1 },
      ranges: [{ start: 3, end: 4 }] },
  ],
}];
const bars = timeline.buildBars(rows, { total: 10, identity: (row) => row.identity });
assert.equal(bars.length, 2);
assert.deepEqual(bars.map((bar) => bar.memberId), ["a", "b"]);
assert.deepEqual(bars.map((bar) => bar.label), ["first line", "second line"]);
assert.deepEqual(bars.map((bar) => [bar.start, bar.end]), [[1, 2], [3, 4]]);
assert.equal(bars[0].rowIdentity, "scan:a+b");
assert.equal(bars[0].lane, 0);
assert.ok(Math.abs(bars[0].left - 10) < 1e-9);
assert.ok(Math.abs(bars[0].width - 10) < 1e-9);
"""
    )


def test_cut_time_mapping_and_outside_cut_rows():
    run_node(
        """
const rows = [{
  identity: "scan:a", lane: 0,
  entryRows: [{ tracklet_id: "a", text: "line", box: { x: 0, y: 0, w: 0.2, h: 0.1 },
    ranges: [{ start: 5, end: 6 }] }],
}];
// One cut clip takes source 4..10 and lands at cut 0..6.
const cut = timeline.buildBars(rows, {
  total: 6,
  identity: (row) => row.identity,
  mapRanges: (ranges) => ranges
    .map((range) => ({ start: range.start - 4, end: range.end - 4 }))
    .filter((range) => range.start >= 0 && range.end > range.start),
});
assert.equal(cut.length, 1);
assert.deepEqual([cut[0].start, cut[0].end], [1, 2]);
const outside = timeline.buildBars(rows, {
  total: 2,
  identity: (row) => row.identity,
  mapRanges: () => [],
});
assert.equal(outside.length, 0);
"""
    )


def test_scan_only_range_override_is_used_for_bars_and_apply():
    run_node(
        """
const rows = [{
  identity: "scan:a", lane: 0,
  entryRows: [{ tracklet_id: "a", text: "line", box: { x: 0, y: 0, w: 0.2, h: 0.1 },
    ranges: [{ start: 1, end: 2 }] }],
}];
const overrides = { "scan:a|a": [{ start: 4, end: 5 }] };
const bars = timeline.buildBars(rows, {
  total: 10,
  identity: (row) => row.identity,
  overrideFor: (row, member, key) => overrides[key] || null,
});
assert.deepEqual([bars[0].start, bars[0].end], [4, 5]);
assert.equal(bars[0].overrideKey, "scan:a|a");
assert.deepEqual(timeline.rangesFor(rows[0], rows[0].entryRows[0], [{ start: 4, end: 5 }]), [{ start: 4, end: 5 }]);
// No override falls back to the scan range.
assert.deepEqual(timeline.rangesFor(rows[0], rows[0].entryRows[0], null), [{ start: 1, end: 2 }]);
"""
    )


def test_move_and_trim_clamp_inside_the_timeline():
    run_node(
        """
const moved = timeline.moveRange({ start: 8, end: 9 }, 5, 10);
assert.deepEqual(moved, { start: 9, end: 10 });
const back = timeline.moveRange({ start: 1, end: 2 }, -3, 10);
assert.deepEqual(back, { start: 0, end: 1 });
const trimStart = timeline.trimRange({ start: 2, end: 6 }, "start", 4, 10);
assert.deepEqual(trimStart, { start: 4, end: 6 });
const trimEnd = timeline.trimRange({ start: 2, end: 6 }, "end", 9, 10);
assert.deepEqual(trimEnd, { start: 2, end: 9 });
const tiny = timeline.trimRange({ start: 2, end: 2.1 }, "end", 0, 10);
assert.ok(tiny.end > tiny.start);
"""
    )


def test_merge_only_merges_exact_layers():
    run_node(
        """
const first = { id: "a", source: "scan", tracklet_id: "t1", tracklet_kind: "subtitle",
  box: { x: 0.1, y: 0.7, w: 0.3, h: 0.1 }, ranges: [{ start: 0, end: 1 }] };
const twin = { ...first, id: "b", ranges: [{ start: 1, end: 2 }] };
const otherLine = { ...first, id: "c", tracklet_id: "t2", box: { x: 0.12, y: 0.72, w: 0.34, h: 0.1 } };
const out = merge.dedupeCleanLayers([first, twin, otherLine]);
assert.equal(out.layers.length, 2);
assert.deepEqual(out.layers[0].box, { x: 0.1, y: 0.7, w: 0.3, h: 0.1 });
assert.deepEqual(out.layers[1].box, { x: 0.12, y: 0.72, w: 0.34, h: 0.1 });
"""
    )


def test_page_uses_one_centered_workspace_with_a_timeline_below_the_frame():
    page = PAGE.read_text(encoding="utf-8")
    view = page[page.index('id="result-view"'):page.index('id="creator-view"')]
    stage = view.index('id="clean-stage"')
    panel = view.index('id="clean-timeline-panel"')
    timeline_pane = view.index("editor-pane-timeline")
    settings = view.index("editor-pane-settings")
    assert stage < panel < timeline_pane < settings
    for marker in (
        'id="clean-timeline-panel"',
        'id="clean-timeline-total"',
        'id="clean-ruler"',
        'id="clean-lanes"',
        'id="clean-playhead"',
        'id="clean-add-range"',
        'id="clean-action-bar"',
    ):
        assert marker in page, marker
    assert 'id="clean-model-chip"' in APP.read_text(encoding="utf-8")
    # The found-text list and layer list are still in the DOM for Edit/repaint,
    # but they are not part of the Clean workspace surface.
    assert 'id="clean-found"' in page
    assert 'id="clean-layers"' in page


def test_preview_is_outlines_only_and_before_after_needs_a_render():
    css = CSS.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")
    assert "backdrop-filter: blur(14px)" not in css
    assert "-webkit-backdrop-filter: blur(14px)" not in css
    assert "background: transparent;" in between(css, ".clean-review-box {", "}")
    assert "function cleanHasAfterRender()" in app
    assert "dom.cleanPreviewBefore.hidden = !hasAfter" in app
    assert "dom.cleanPreviewAfter.hidden = !hasAfter" in app
    assert "Detection check · boxes outlined · not the final clean" in app
    assert "cleanScanPartsAt" in app
    assert "member?.box" in app


def test_icon_controls_are_authored_svg_with_labels():
    page = PAGE.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")
    for control in (
        "clean-preview-play",
        "clean-preview-expand",
        "clean-preview-ai",
        "clean-preview-blur",
        "clean-preview-exclude",
        "clean-draw",
        "clean-brush",
        "clean-undo",
        "clean-redo",
        "clean-refresh",
        "clean-add-range",
    ):
        start = page.index(f'id="{control}"')
        chunk = page[start:start + 700]
        assert "<svg" in chunk, control
        assert "aria-label=" in chunk, control
        assert "title=" in chunk, control
    stage = page[page.index('id="clean-stage"'):page.index('id="result-ready"')]
    for glyph in ("clean-tool-glyph", "＋", "↶", "↷", "↻", "✕", "◉", "◌"):
        assert glyph not in stage, glyph
    assert "CLEAN_ICONS" in app
    assert "cleanIcon(" in app
    assert "cleanIcon(\"trash\")" in app
    # Only the main action keeps text.
    assert "Find text &amp; clean" in page
    assert ">Play<" not in page
    assert ">AI fill<" not in page


def test_model_ui_is_one_status_chip_engine_menu_and_options_popover():
    page = PAGE.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")
    assert 'id="setup-clean-flow-control"' in page
    assert 'id="setup-clean-flow"' in page
    assert "hidden aria-hidden=\"true\"" in page
    assert 'id="clean-fill-engine"' not in app
    assert "clean-file-list" not in between(app, "function fillMenuHtml()", "function previewFill()")
    assert "AI fill · ${ready ? \"Ready\" : \"Not ready\"}" in app
    assert 'id="clean-engine-menu"' in app
    assert "clean-engine-item" in app
    assert "aria-checked" in app
    assert "not(:disabled)" in app
    assert 'id="clean-fill-options"' in app
    assert "GPU" in app and "CPU" in app
    assert "Follow camera" in app
    assert "aria-haspopup=\"menu\"" in app
    assert "is-above" in app
    assert ".clean-engine-menu" in CSS.read_text(encoding="utf-8")
    menu_css = between(CSS.read_text(encoding="utf-8"), ".clean-engine-menu {", "}")
    assert "width: 240px" in menu_css
    assert "font-size: 13px" in menu_css
    row_css = between(CSS.read_text(encoding="utf-8"), ".clean-engine-item {", "}")
    assert "height: 36px" in row_css


def test_review_first_is_a_compact_segmented_control():
    page = PAGE.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")
    control = between(page, 'id="setup-clean-flow-control"', "</div>")
    assert ">Review first<" in control
    assert ">One click<" in control
    assert "data-clean-flow=\"review_first\"" in control
    assert "data-clean-flow=\"one_click\"" in control
    assert "Review first — scan stops" not in page
    assert "Review first is the default. It finds text" not in page
    assert "function syncCleanFlowButtons()" in app
    assert 'dom.setupCleanFlow.value = button.dataset.cleanFlow === "one_click" ? "one_click" : "review_first";' in app


def test_timeline_wiring_seek_selection_drag_trim_and_keyboard():
    app = APP.read_text(encoding="utf-8")
    assert "function paintCleanTimeline()" in app
    assert "function cleanTimelineBars(" in app
    assert "ClassicCleanTimeline" in app
    assert "CleanTimeline.buildBars(rows" in app
    assert "setCleanBarRange" in app
    assert "CleanTimeline.trimRange" in app
    assert "CleanTimeline.moveRange" in app
    assert "state.classicText.rangeOverrides[key] = ranges" in app
    assert "function startCleanAddRange()" in app
    assert "It starts at the playhead." in app
    assert "function cleanSeek(t)" in app
    assert "updateCleanPlayhead" in app
    assert 'event.key === "ArrowLeft" || event.key === "ArrowRight"' in app
    assert "state.classicText.selectedBar = \"\"" in app
    assert 'event.key === "Backspace" || event.key === "Delete"' in app


def test_apply_creates_one_layer_per_member_with_its_fill_keys():
    app = APP.read_text(encoding="utf-8")
    block = between(app, "function applyFoundTicks()", "function renderCleanLayers()")
    assert "row.entryRows" in block
    assert "for (const member of members)" in block
    assert "cleanOverrideFor(row, member)" in block
    assert "addCleanFromScan({" in block
    assert "...member" in block
    assert "box: member.box || row.box" in block
    assert "text_key: member.text_key" in block
    # No unioning in the apply path.
    assert "joinBoxes" not in block


def test_timeline_test_is_in_the_page_and_i18n_carries_the_new_copy():
    words = I18N.read_text(encoding="utf-8")
    for english, vietnamese in (
        ("Add range", "Thêm khoảng"),
        ("Fill options", "Tùy chọn lấp"),
        ("AI fill · Ready", "AI lấp · Sẵn sàng"),
        ("AI fill · Not ready", "AI lấp · Chưa sẵn sàng"),
        ("Follow camera", "Bám theo camera"),
        ("Review first", "Xem lại trước"),
        ("One click", "Một lần bấm"),
        ("Detection check · boxes outlined · not the final clean", "Kiểm tra nhận diện · khung được viền · không phải bản làm sạch cuối"),
    ):
        assert f'"{english}": "{vietnamese}"' in words, english
