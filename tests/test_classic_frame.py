"""C0: the Classic result screen is one frame, not one long page.

Preview, timeline and settings sit side by side from 1000px up; the scan card
lives in settings and drives the shared Check route instead of a Classic copy.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _result_view() -> str:
    page = (ROOT / "static" / "classic" / "index.html").read_text(encoding="utf-8")
    start = page.index('id="result-view"')
    return page[start:page.index('id="creator-view"', start)]


def test_result_view_is_preview_then_timeline_then_settings():
    view = _result_view()
    preview = view.index("editor-pane-preview")
    timeline = view.index("editor-pane-timeline")
    settings = view.index("editor-pane-settings")
    assert preview < timeline < settings
    assert view.index('id="result-ready"') > preview
    assert view.index('id="player-wrap"') > preview
    assert view.index('id="player-wrap"') < timeline


def test_timeline_keeps_moments_and_smart_cut_and_loses_edit():
    view = _result_view()
    timeline = view[view.index("editor-pane-timeline"):view.index("editor-pane-settings")]
    assert 'id="moments-section"' in timeline
    assert "smart-cut-panel" in timeline
    assert timeline.index('id="moments-section"') < timeline.index("smart-cut-panel")
    assert 'id="audio-panel"' not in timeline
    assert 'id="mixer-panel"' not in timeline


def test_settings_holds_scan_edit_mixer_and_activity():
    view = _result_view()
    settings = view[view.index("editor-pane-settings"):]
    for marker in (
        'class="edit-section-head"',
        'id="clean-panel"',
        'id="clean-scan"',
        'id="clean-scan-start"',
        'id="audio-panel"',
        'id="mixer-panel"',
        'id="history-panel"',
    ):
        assert marker in settings
    assert 'id="text-scan"' not in view
    assert 'id="text-scan-start"' not in view
    assert settings.index('id="clean-scan"') < settings.index('id="audio-panel"')
    assert settings.index('class="edit-section-head"') < settings.index('id="clean-panel"')


def test_the_frame_only_starts_at_a_thousand_pixels():
    css = (ROOT / "static" / "classic" / "style.css").read_text(encoding="utf-8")
    # Below the breakpoint the wrappers must not exist for layout purposes, so
    # the narrow screen keeps the single column it had before C0.
    assert ".editor-pane { display: contents; }" in css
    frame = css[css.index("C0 · editor frame"):]
    assert "@media (min-width: 1000px)" in frame
    assert '"preview timeline settings"' in frame
    assert "grid-template-columns" in frame
    assert "overflow-y: auto" in frame
    assert "body.editor-frame main.shell" in frame


def test_scan_card_and_frame_class_are_wired():
    script = (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    assert 'document.body.classList.toggle("editor-frame", view === "result")' in script
    # The card reads the shared Check route rather than a Classic-only scan.
    assert "/check`" in script and "/check/cancel`" in script
    assert "refreshTextScan();" in script
    assert '"queued" || status === "running"' in script
    assert "paintTextScan();" in script
    routes = (ROOT / "routes_classic.py").read_text(encoding="utf-8")
    assert "/check" not in routes
