"""Moments expands to a vertical list, and dropdown text is readable.

The founder pass showed Expand opened a second thumbnail gallery, and the
Language / Voice list popups rendered at 11 px. Expand now replaces the rail
with a vertical list of moments; selects inherit the page font at 13 px.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_expand_opens_a_vertical_moment_list():
    page = (ROOT / "static" / "classic" / "index.html").read_text(encoding="utf-8")
    assert 'id="moments-list"' in page
    assert 'id="moments-list" class="moments-list"' in page

    script = (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    assert "function renderMomentList()" in script
    assert "dom.momentsList.innerHTML = scenes.map" in script
    start = script.index('dom.momentsExpand.addEventListener("click"')
    body = script[start:script.index("dom.recent.addEventListener", start)]
    assert "dom.momentsRail.hidden = state.momentsExpanded" in body
    assert "renderMomentList();" in body
    assert "renderScenes();" not in body


def test_expand_is_a_vertically_scrolling_collage():
    script = (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    assert 'class="moment-card ' in script
    assert "moment-wide-copy" not in script
    assert "moment-card-wide" not in script
    assert "scene.ocr || scene.speech" in script
    css = (ROOT / "static" / "classic" / "style.css").read_text(encoding="utf-8")
    block = css[css.index(".moments-list {"):]
    block = block[:block.index(".moments-list .moment-card")]
    assert "display: grid" in block
    assert "repeat(auto-fill, minmax(132px, 1fr))" in block
    assert "overflow-y: auto" in block


def test_dropdown_text_is_not_eleven_pixels():
    css = (ROOT / "static" / "classic" / "style.css").read_text(encoding="utf-8")
    assert "button, input, select { font: inherit; }" in css
    block = css[css.index(".audio-field select,"):]
    block = block[:block.index("}")]
    size = re.search(r"font-size:\s*([0-9.]+)px", block)
    assert size and float(size.group(1)) >= 12.5, block

    row = css[css.index(".render-row select {"):]
    row = row[:row.index("}")]
    size = re.search(r"font-size:\s*([0-9.]+)px", row)
    assert size and float(size.group(1)) >= 13, row


def test_a_moment_has_a_quick_select_toggle():
    page = (ROOT / "static" / "classic" / "index.html").read_text(encoding="utf-8")
    assert 'id="moments-scrub"' not in page
    script = (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    assert "function momentCheck(scene, checked)" in script
    assert "data-moment-toggle" in script
    assert "function toggleSceneInPlan(sceneId)" in script
    assert "function removeSceneFromPlan(sceneId)" in script
    assert "Remove from Smart Cut" in script


def test_a_clip_role_opens_a_hook_beat_payoff_menu():
    page = (ROOT / "static" / "classic" / "index.html").read_text(encoding="utf-8")
    assert 'id="clip-menu"' in page
    script = (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    assert "function setClipRole(index, role)" in script
    assert 'data-clip-role="${role}"' in script
    assert "contextmenu" in script
