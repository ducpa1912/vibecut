"""P4: the shared app bar, Import/Moments touches and Finish frame."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "static" / "studio"
SHELL = (STUDIO / "shell.js").read_text(encoding="utf-8")
IMPORT = (STUDIO / "import.js").read_text(encoding="utf-8")
STORIES = (STUDIO / "stories.js").read_text(encoding="utf-8")
FINISH = (STUDIO / "finish.js").read_text(encoding="utf-8")
CSS = (STUDIO / "studio.css").read_text(encoding="utf-8")


def test_app_bar_is_compact_and_moves_video_actions_into_the_menu():
    assert 'class="st-top-actions"' in SHELL
    assert 'id="st-change-video"' in SHELL
    assert "st-menu-workspace" in SHELL
    # Studio owns its workspace: no link into the Classic or Voice Room pages.
    assert 'id="st-voice-room"' not in SHELL
    assert 'href="/voices"' not in SHELL
    assert 'href="/?classic=1"' not in SHELL
    # The top row has one action: the Menu button.
    start = SHELL.index('<div class="st-top-actions">')
    end = SHELL.index("</div>", start)
    top_actions = SHELL[start:end]
    assert "Menu" in top_actions
    assert "Change video" not in top_actions
    assert "Voice Room" not in top_actions

    top = CSS.split(".st-top {", 1)[1].split("}", 1)[0]
    assert "padding: 7px" in top
    step = CSS.split(".st-step {", 1)[1].split("}", 1)[0]
    assert "min-height: 34px" in step


def test_import_puts_rights_next_to_start_and_recent_first_when_present():
    assert 'class="st-import-start"' in IMPORT
    assert "has-recent" in IMPORT
    assert 'querySelector(".st-import-grid")' in IMPORT
    start = IMPORT.index('class="st-import-start"')
    end = IMPORT.index("</div>", start)
    start_block = IMPORT[start:end + 6]
    assert 'id="st-attest-row"' in start_block
    assert 'id="st-import"' in start_block
    assert 'id="st-import-note"' in start_block
    assert ".st-import-grid.has-recent" in CSS
    assert ".st-import-start" in CSS


def test_moments_header_shows_scan_state_and_scan_action():
    assert 'id="st-moment-actions"' in STORIES
    assert "function renderScanAction" in STORIES
    assert '"Scan for text"' in STORIES
    assert '"Scan again"' in STORIES
    assert '"Cancel scan"' in STORIES
    assert "renderScanAction();" in STORIES
    assert ".st-panel-actions" in CSS
    assert ".st-panel-head-row" in CSS


def test_finish_uses_the_same_fixed_frame_and_scrolling_body():
    assert 'id="st-finish-back"' in FINISH
    assert 'ctx.go("edit")' in FINISH
    assert 'main.st-main[data-step="finish"]' in CSS
    assert "main.st-main[data-step=\"finish\"] > .st-finish-panel" in CSS
    assert ".st-finish-body" in CSS
    finish_body = CSS.split(".st-finish-body {", 1)[1].split("}", 1)[0]
    assert "overflow-y: auto" in finish_body
    assert "scrollbar-gutter: stable" in finish_body
    assert ".st-finish-head" in CSS
