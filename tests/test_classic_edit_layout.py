"""Classic Edit is Copy / Sound / Texts / Script with actions at the bottom."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_edit_has_three_cards_and_a_full_width_script():
    page = (ROOT / "static" / "classic" / "index.html").read_text(encoding="utf-8")
    assert 'id="audio-panel" class="audio-panel edit-panel"' in page
    assert 'id="audio-rewrite-step" class="edit-card edit-copy"' in page
    assert 'class="edit-card edit-sound"' in page
    assert 'id="text-effects-step" class="edit-card edit-text"' in page
    assert 'class="edit-card edit-script-card"' not in page
    assert '<section class="edit-script">' in page
    assert ">Story cut<" in page
    assert 'id="audio-script"' in page
    assert 'id="mixer-open"' in page
    assert 'data-sound-tab="voice"' in page
    assert 'data-sound-tab="music"' in page
    assert 'id="audio-generate-voice"' in page
    assert 'id="audio-generate-music"' in page
    assert ">Use my recording<" in page
    assert ">Use my BGM<" in page


def test_texts_and_effects_sits_below_copy():
    css = (ROOT / "static" / "classic" / "style.css").read_text(encoding="utf-8")
    assert '"copy sound"' in css and '"text sound"' in css
    assert ".edit-copy { grid-area: copy; }" in css
    assert ".edit-text { grid-area: text; }" in css


def test_render_and_draft_sit_inside_edit_at_the_bottom():
    page = (ROOT / "static" / "classic" / "index.html").read_text(encoding="utf-8")
    panel = page[page.index('id="audio-panel"'):page.index("</details>", page.index('id="audio-panel"'))]
    assert 'id="render"' in panel and 'id="render-draft"' in panel
    assert panel.index('id="render-draft"') < panel.index('id="render"')


def test_clean_has_no_profile_dropdown_and_shapes_include_16_10():
    page = (ROOT / "static" / "classic" / "index.html").read_text(encoding="utf-8")
    assert 'id="clean-profile"' not in page
    assert '<option value="16:10">16:10</option>' in page
    script = (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    assert 'profile: "workfiles"' in script


def test_mode_tags_disable_the_edit_cards():
    script = (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    assert "const setDisabled = (root, disabled)" in script
    assert "setDisabled(dom.audioRewriteStep, !rewriteMode)" in script
    assert "setDisabled(dom.audioVoiceStep, !voiceMode)" in script
    assert "setDisabled(dom.audioMusicStep, !musicMode)" in script
    assert "function showSoundTab(tab)" in script
    assert "function setMusicSource(source)" in script


def test_translation_status_is_plain_words_only():
    script = (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    assert 'dom.translateBadge.textContent = "✓ Translation ready"' in script
    assert 'dom.translateBadge.textContent = "Translating…"' in script
    assert 'dom.translateBadge.textContent = "Rewriting…"' in script
    assert "Translating batch" not in script
    assert "Preferred MiniMax" not in script


def test_unavailable_models_are_disabled_options():
    script = (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    assert "${disabled ? \" disabled\" : \"\"}" in script
    css = (ROOT / "static" / "classic" / "style.css").read_text(encoding="utf-8")
    assert ".select-menu button:disabled" in css
    assert "filter: blur(0.35px)" in css


def test_sixteen_by_ten_is_a_render_shape():
    import render

    assert "16:10" in render.ASPECTS
