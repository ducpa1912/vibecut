"""A blocked render says why, in the page, not only in a toast.

The founder pass selected a voice engine with no key. Render was disabled with
no visible reason, so it looked broken until a reload reset the audio mode.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_the_page_has_a_persistent_render_block_notice():
    page = (ROOT / "static" / "classic" / "index.html").read_text(encoding="utf-8")
    assert 'id="render-block"' in page
    assert 'id="render-block-setup"' in page
    assert "Open Setup" in page


def test_the_block_reason_fills_the_notice_and_the_button_titles():
    script = (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    assert "dom.renderBlock.hidden = !blocked" in script
    assert 'dom.renderBlock.querySelector("span").textContent = blocked || ""' in script
    assert "dom.render.title = blocked || \"\"" in script
    assert "dom.renderBlockSetup.addEventListener(\"click\", openSetup)" in script


def test_the_render_buttons_stay_disabled_while_blocked():
    script = (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    start = script.index("function updateRenderPanel(")
    body = script[start:script.index("function renderAudioNote(", start)]
    blocked = body[body.index("if (blocked) {"):]
    for name in ("dom.render.disabled", "dom.renderDraft.disabled", "dom.renderAll.disabled"):
        assert name in blocked
