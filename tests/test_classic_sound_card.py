"""Classic Sound: Voice and Music are real tabs with Generate as the action."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def page() -> str:
    return (ROOT / "static" / "classic" / "index.html").read_text(encoding="utf-8")


def script() -> str:
    return (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")


def css() -> str:
    return (ROOT / "static" / "classic" / "style.css").read_text(encoding="utf-8")


def test_voice_and_music_are_tabs_with_generate_as_the_primary_action():
    html = page()
    assert 'role="tablist"' in html
    assert 'id="sound-tab-voice"' in html and 'id="sound-tab-music"' in html
    assert 'aria-selected="true"' in html
    assert 'id="audio-generate-voice" class="primary small"' in html
    assert 'id="audio-generate-music" class="primary small"' in html
    assert html.index('id="audio-generate-voice"') < html.index('id="audio-preview"')
    assert html.index('id="audio-generate-music"') < html.index('id="audio-play-music"')


def test_the_voice_preview_is_a_generated_sample_not_a_placeholder():
    js = script()
    assert "async function generateVoicePreview()" in js
    assert "function playVoiceSample()" in js
    assert "text: previewVoiceText()" in js
    assert "Voice preview ready. Play ▶ or render to use this voice." in js
    assert "Generate a voice preview first." in js
    assert "dom.audioPreview.disabled = !voiceMode || !voiceReady" in js


def test_the_rate_control_is_compact_and_labelled():
    html = page()
    assert 'class="audio-field small rate-field"' in html
    assert 'class="rate-control"' in html
    assert 'aria-label="Voice rate"' in html
    assert ".rate-control input" in css()
    assert "width: 52px;" in css()


def test_use_my_recording_and_use_my_bgm_are_visible_actions():
    html = page()
    assert ">Use my recording<" in html
    assert ">Use my BGM<" in html
    assert 'id="audio-use-recording"' in html
    assert 'id="audio-use-bgm"' in html
    assert 'data-sound-tab="voice"' in html and 'data-sound-tab="music"' in html


def test_music_has_a_real_preview_and_no_fake_playback_copy():
    js = script()
    assert "async function generateMusicPreview()" in js
    assert "sound/music-preview" in js
    assert "sound/bgm-preview" in js
    assert "Generated music plays in the render." not in js
    assert "Press Generate for a 12s preview. The render makes the full bed." in js
    assert "musicPreviewBusy" in js


def test_unavailable_engines_are_dimmed_and_the_old_status_copy_is_gone():
    js = script()
    assert "is-unavailable" in js
    assert "pieces.push(info.install)" not in js
    assert "Preferred MiniMax" not in js
    assert ".audio-field.is-unavailable" in css()
    assert "filter: blur(0.2px)" in css()
    assert "select option:disabled" in css()


def test_mixer_opens_from_the_sound_header_even_before_a_mode():
    html = page()
    sound = html[html.index('class="edit-card edit-sound"'):html.index('id="text-effects-step"')]
    assert 'id="mixer-open"' in sound
    js = script()
    assert "async function toggleMixer()" in js
    assert "if (!state.mixer.ready) await loadMixer();" in js
    start = js.index("async function loadMixer(")
    body = js[start:js.index("function formatGain(", start)]
    assert 'state.audio.mode === "keep"' not in body
