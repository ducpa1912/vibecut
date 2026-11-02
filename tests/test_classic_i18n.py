"""The Classic and Voice Room pages expose English and Vietnamese UI copy."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_classic_page_has_the_language_selector_and_translator():
    page = (ROOT / "static" / "classic" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "classic" / "i18n.js").read_text(encoding="utf-8")
    assert 'id="ui-language"' in page
    assert 'class="lang-switch"' in page
    assert 'data-lang="en"' in page and 'data-lang="vi"' in page
    assert "Tiếng Việt" in page
    assert "/static/classic/i18n.js" in page
    assert '"Preserve voice pitch & tone": "Giữ nguyên cao độ & âm sắc"' in script
    assert '"Voice Room": "Phòng giọng nói"' in script


def test_english_mode_is_not_translated_by_a_live_observer():
    script = (ROOT / "static" / "classic" / "i18n.js").read_text(encoding="utf-8")
    assert "MutationObserver" not in script
    assert 'url.searchParams.delete("lang")' in script


def test_vietnamese_copy_has_no_machine_mistranslations():
    script = (ROOT / "static" / "classic" / "i18n.js").read_text(encoding="utf-8")
    assert '"moments": "khoảnh khắc"' in script
    assert '"Moments": "Khoảnh khắc"' in script
    assert '"A payoff beat closes the cut.": "Một nhịp cao trào khép lại bản cắt."' in script
    assert '"Story arc order": "Thứ tự mạch truyện"' in script
    assert '"Copy": "Viết lại"' in script


def test_voice_room_loads_the_same_translator():
    page = (ROOT / "static" / "voices.html").read_text(encoding="utf-8")
    room = (ROOT / "static" / "voice" / "voiceroom.js").read_text(encoding="utf-8")
    assert "/static/classic/i18n.js" in page
    assert 'id: "ui-language"' in room
    assert "Tiếng Việt" in room
