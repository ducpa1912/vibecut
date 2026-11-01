"""The Classic and Voice Room pages expose English and Vietnamese UI copy."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_classic_page_has_the_language_selector_and_translator():
    page = (ROOT / "static" / "classic" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "classic" / "i18n.js").read_text(encoding="utf-8")
    assert 'id="ui-language"' in page
    assert "Tiếng Việt" in page
    assert "/static/classic/i18n.js" in page
    assert '"Preserve voice pitch & tone": "Giữ nguyên cao độ & âm sắc"' in script
    assert '"Voice Room": "Phòng giọng nói"' in script


def test_voice_room_loads_the_same_translator():
    page = (ROOT / "static" / "voices.html").read_text(encoding="utf-8")
    room = (ROOT / "static" / "voice" / "voiceroom.js").read_text(encoding="utf-8")
    assert "/static/classic/i18n.js" in page
    assert 'id: "ui-language"' in room
    assert "Tiếng Việt" in room
