"""P0 of the Studio UI revamp: one fixed screen, one scroll per panel.

These are source-level checks for the shipped no-build Studio UI. The
browser-level layout check lives in tests/browser/edit_layout.spec.mjs.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "static" / "studio"
CSS = (STUDIO / "edit" / "edit.css").read_text(encoding="utf-8")
INDEX = (STUDIO / "edit" / "index.js").read_text(encoding="utf-8")
SHELL = (STUDIO / "shell.js").read_text(encoding="utf-8")
CLEAN = (STUDIO / "edit" / "layers" / "clean.js").read_text(encoding="utf-8")
INSPECTOR = (STUDIO / "edit" / "inspector.js").read_text(encoding="utf-8")


def rule(selector: str) -> str:
    """The first top-level ``selector { … }`` block, without comments."""
    text = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    pattern = re.compile(rf"(?:^|[}}])\s*{re.escape(selector)}\s*\{{", re.M)
    match = pattern.search(text)
    assert match, f"{selector} not found in edit.css"
    start = text.find("{", match.start())
    end = text.find("}", start)
    return text[start + 1:end]


def test_shell_marks_the_edit_step_on_main():
    assert 'dom.main.dataset.step = step.id;' in SHELL
    assert 'root.dataset.editorFrame = "fixed";' in INDEX
    assert "delete root.dataset.editorFrame;" in INDEX


def test_edit_frame_is_fixed_and_the_page_does_not_scroll():
    frame = rule('main.st-main[data-editor-frame="fixed"]')
    assert "display: flex" in frame
    assert "flex-direction: column" in frame
    assert "overflow: hidden" in frame

    stage = rule(".st-edit-stage")
    assert "min-height: 0" in stage
    assert "flex: 1 1 auto" in stage
    # Two rows: a shrinking preview and a timeline that never leaves the screen.
    assert "grid-template-rows: minmax(0, 1fr) clamp(" in stage
    assert '"preview inspector"' in stage
    assert '"timeline inspector"' in stage


def test_toolbar_is_not_sticky():
    assert "position: sticky" not in CSS
    assert "st-edit-stepnav" not in CSS
    toolbar = rule(".st-edit-toolbar")
    assert "display: flex" in toolbar
    assert "flex: 0 0 auto" in toolbar


def test_each_panel_has_its_own_stable_scroll():
    body = rule(".st-inspector-body")
    assert "overflow-y: auto" in body
    assert "scrollbar-gutter: stable" in body
    assert "max-height" not in body

    timeline = rule(".st-timeline-scroll")
    assert "overflow-y: auto" in timeline
    assert "scrollbar-gutter: stable" in timeline

    # No nested scroll container inside the inspector body.
    assert "max-height: min(660px" not in CSS
    assert "max-height: 300px" not in CSS
    assert "st-cue-list" in CSS


def test_settings_stay_on_the_right_at_1024():
    assert "@media (max-width: 1023px)" in CSS
    assert "@media (max-width: 1040px)" not in CSS
    desktop = CSS.split("@media (max-width: 1023px)")[0]
    assert "grid-template-columns: minmax(0, 1fr) clamp(300px, 24vw, 340px)" in desktop


def test_toolbar_moves_all_moments_into_the_picker():
    assert 'const ALL_MOMENTS = "__all_moments";' in INDEX
    assert 'text: "All moments…"' in INDEX
    assert 'id="st-edit-all"' not in INDEX
    assert 'dom.all' not in INDEX


def test_inspector_tabs_are_plain_and_not_truncated():
    assert '{ id: "clean", label: "Remove text" }' in INSPECTOR
    assert '{ id: "visual", label: "Text & effects" }' in INSPECTOR
    assert "Texts & Effects" not in INSPECTOR
    tab = rule(".st-inspector-tab")
    assert "font-size: 11.5px" in tab
    tabs = rule(".st-inspector-tabs")
    assert "display: flex" in tabs


def test_clean_copy_is_true_and_scan_is_a_task_in_edit():
    assert "Nothing invents missing pixels" not in CLEAN
    assert "AI fill rebuilds the background" in CLEAN
    assert "Find text on screen" in CLEAN
    assert "/check/cancel" in CLEAN
    assert "scanProgressRow" in CLEAN
    assert "scanPrompt" in CLEAN
