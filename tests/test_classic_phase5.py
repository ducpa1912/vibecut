"""Phase 5 polish contract: motion, focus, type floor, copy and Clean entry.

These static checks guard the CSS and copy that the browser spec exercises; the
browser spec proves the rendered behaviour on stubbed routes.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "static" / "classic" / "style.css").read_text(encoding="utf-8")
APP = (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")
I18N = (ROOT / "static" / "classic" / "i18n.js").read_text(encoding="utf-8")


def test_clean_rail_is_a_bottom_sheet_under_1100():
    start = CSS.index("@media (max-width: 1099px)")
    block = CSS[start:CSS.index("@media (max-width: 680px)", start)]
    for rule in (
        "body.editor-frame.source-mode main.shell",
        "body.editor-frame.cut-clean-mode main.shell",
        "flex-direction: column;",
        "border-radius: 18px 18px 0 0;",
        "max-height: 44%;",
        "position: sticky;",
        "bottom: 0;",
    ):
        assert rule in block, rule
    assert "@media (min-width: 1100px)" in CSS
    assert "grid-template-columns: minmax(0, 1.45fr) minmax(0, 1fr);" in CSS


def test_reduced_motion_disables_scroll_transition_and_animation():
    start = CSS.index("@media (prefers-reduced-motion: reduce)")
    block = CSS[start:CSS.index("@media (max-width: 560px)", start)]
    assert "html { scroll-behavior: auto; }" in block
    assert "animation: none !important;" in block
    assert "transition: none !important;" in block
    assert "scroll-behavior: auto !important;" in block
    assert "function reducedMotion()" in APP
    assert "function scrollIntoViewSafe(" in APP
    assert APP.count("scrollIntoViewSafe(") >= 8


def test_focus_rings_are_declared_for_controls_rows_and_handles():
    for rule in (
        ":focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }",
        ".clean-found-tick:focus-visible",
        ".clean-box:focus-visible",
        ".clean-box:focus-visible .clean-handle",
        ".clean-row:focus-visible",
        "select:focus-visible",
        "input[type=\"range\"]:focus-visible",
        ".setup-field input:focus-visible",
    ):
        assert rule in CSS, rule
    assert "outline: none" not in CSS


def test_no_declared_font_size_is_below_eleven_pixels():
    sizes = re.findall(r"font-size:\s*([0-9.]+)px", CSS)
    assert sizes, "no font sizes found"
    below = [value for value in sizes if float(value) < 11]
    assert below == [], f"font sizes below 11 px: {below}"


def test_vietnamese_covers_new_clean_and_render_states():
    for english in (
        "No baked-in text found. Re-rendering with the existing Clean boxes.",
        "No baked-in text found. Rendering the cut without Clean boxes.",
        "Review the low-confidence rows. Tick the ones to remove, then use the Clean action again.",
        "No text row at 0:00. Scrub the frame or scan again.",
        "No render baseline on this browser. Render again to confirm this cut matches.",
        "Changed since this render. The older file is still available; render again to update it.",
        "Clean cancelled. Nothing partial is kept. Retry when ready.",
        "Render cancelled. Nothing partial is kept. Clean again when ready.",
        "The rendered file is missing. Render again; no Download is offered.",
    ):
        assert f'"{english}":' in I18N, english


def test_raw_engine_detail_stays_out_of_visible_copy():
    assert "dom.cleanFrameState.title = frame.error" not in APP
    assert "dom.progressError.title = raw" not in APP
    assert 'dom.cleanPreviewAi.title = "AI fill needs its model pack.' in APP
    assert "plainCleanError" in APP
    assert "plainRenderError" in APP
    assert "plainJobError" in APP
    assert "cleanDiagnostic(" in APP
    assert 'return `Clean failed: ${plainCleanError(raw)}`;' in APP
    assert "Clean failed: ${clipText(" not in APP


def test_clean_opens_on_the_first_timed_text_row_and_explains_zero():
    assert "function cleanFirstTextTime()" in APP
    assert "function openCleanAtFirstText()" in APP
    assert "if (first === null && any) return 0;" in APP
    assert "state.classicText.t = start;" in APP
    assert "No text row at 0:00. Scrub the frame or scan again." in APP
    assert "openCleanAtFirstText();" in APP


def test_hidden_applied_row_says_excluded_not_already_cleaned():
    assert '${row.hidden ? "Excluded" : "Already cleaned"}' in APP
    assert ': "Already cleaned"}: ${esc(row.text)}' in APP


def test_muted_and_disabled_tokens_keep_contrast():
    # Classic overrides the shared :root token on body; that override is the
    # colour every Classic screen actually uses.
    body = CSS[CSS.index("body {"):CSS.index("}", CSS.index("body {"))]
    dim = re.search(r"--dim:\s*(#[0-9a-fA-F]{6})", body).group(1)
    panel = re.search(r"--panel:\s*(#[0-9a-fA-F]{6})", CSS).group(1)

    def luminance(hex_value):
        channels = [int(hex_value[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [
            value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4
            for value in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    high, low = sorted((luminance(dim), luminance(panel)), reverse=True)
    ratio = (high + 0.05) / (low + 0.05)
    assert ratio >= 4.5, f"--dim on --panel is {ratio:.2f}:1"
    for disabled in (".primary:disabled", ".select-menu button:disabled", ".clean-row.is-off .clean-row-copy"):
        start = CSS.index(disabled)
        block = CSS[start:CSS.index("}", start)]
        match = re.search(r"opacity:\s*([0-9.]+)", block)
        assert match, f"{disabled} has no opacity"
        assert float(match.group(1)) >= 0.4, f"{disabled} is too faint ({match.group(1)})"
