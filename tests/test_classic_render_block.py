"""A blocked render says why once, next to the control that fixes it.

Music mode with no source used to print the same sentence in #render-block,
#render-note and the disabled button title. The music step now owns one inline
message with Use my BGM / Generate actions; other engine blocks use the Sound
status line and an Open Setup action.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_the_page_has_one_inline_music_block():
    page = (ROOT / "static" / "classic" / "index.html").read_text(encoding="utf-8")
    assert 'id="audio-music-block"' in page
    assert 'id="audio-music-block-bgm"' in page
    assert 'id="audio-music-block-generate"' in page
    assert 'id="render-block"' not in page
    assert 'id="render-block-setup"' not in page
    assert 'id="audio-status-setup"' in page


def test_the_block_reason_is_inline_and_on_the_button_title():
    script = (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    assert "dom.audioMusicBlock.hidden = !noSource" in script
    assert "dom.audioGenerateMusic.disabled = noSource" in script
    assert "dom.render.title = blocked || \"\"" in script
    assert "dom.audioStatusSetup.hidden = !needsSetup" in script
    assert "Choose a music source before rendering." in script
    # The render note carries render context, never a second copy of the block.
    assert "dom.renderNote.textContent = blocked" not in script


def test_the_render_buttons_stay_disabled_while_blocked():
    script = (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    start = script.index("function updateRenderPanel(")
    body = script[start:script.index("function renderAudioNote(", start)]
    blocked = body[body.index("if (blocked) {"):]
    for name in ("dom.render.disabled", "dom.renderDraft.disabled", "dom.renderAll.disabled"):
        assert name in blocked
