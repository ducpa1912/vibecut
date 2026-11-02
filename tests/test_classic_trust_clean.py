"""T6: Clean says in plain words what goes and what stays."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "static" / "classic" / "index.html"
APP = ROOT / "static" / "classic" / "app.js"
TRUST = ROOT / "static" / "classic" / "trust.js"


def _node(expression: str) -> str:
    script = (
        "const t = require(process.argv[1]);"
        f"process.stdout.write(String({expression}));"
    )
    result = subprocess.run(
        ["node", "-e", script, str(TRUST)],
        check=True, capture_output=True, text=True,
    )
    return result.stdout


def test_work_files_names_the_files_and_what_stays():
    text = _node("t.cleanConfirmText('workfiles')")
    assert text.startswith("Clean work files?")
    assert "Deletes: thumbnails, the transcript, extracted audio and deep-read scores." in text
    assert "Keeps: the source video, rendered reels and job details." in text


def test_renders_names_the_render_files_and_what_stays():
    text = _node("t.cleanConfirmText('renders')")
    assert text.startswith("Clean rendered reels?")
    assert "Deletes: rendered reels, render masters and legacy render files." in text
    assert "Keeps: the source video, transcript, thumbnails and job details." in text


def test_all_but_source_says_the_source_stays():
    text = _node("t.cleanConfirmText('all')")
    assert text.startswith("Clean everything except the source?")
    assert "Keeps: the source video and job details." in text


def test_the_menu_offers_the_three_profiles():
    html = PAGE.read_text(encoding="utf-8")
    assert '<select id="clean-profile"' in html
    for value, label in (
        ("workfiles", "Work files"),
        ("renders", "Renders"),
        ("all", "All but source"),
    ):
        assert f'<option value="{value}"' in html
        assert f">{label}</option>" in html


def test_the_old_two_click_label_is_gone_and_confirm_is_used():
    source = APP.read_text(encoding="utf-8")
    assert "Click to confirm" not in source
    assert "window.confirm(localized)" in source
    assert "VibeCutI18N?.tBlock" in source
