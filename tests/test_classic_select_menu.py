"""The four audio dropdowns open a readable custom list.

Native select popups on macOS render at the system menu size no matter what
the page asks for. Language, Script style, Voice list and Voice now use one
15px listbox.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_the_audio_selects_use_the_custom_menu():
    script = (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    assert "function enhanceAudioSelects()" in script
    assert "[dom.audioLang, dom.audioStyle, dom.audioEngine, dom.audioVoice]" in script
    assert "function openSelectMenu(select)" in script
    assert "enhanceAudioSelects();" in script


def test_the_menu_is_fifteen_pixels_and_keeps_the_choice():
    css = (ROOT / "static" / "classic" / "style.css").read_text(encoding="utf-8")
    block = css[css.index(".select-menu {"):]
    block = block[:block.index(".select-menu button.active::after")]
    assert "font-size: 15px" in block
    script = (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    assert "menuSelect.value = option.value" in script
    assert 'new Event("change", { bubbles: true })' in script
