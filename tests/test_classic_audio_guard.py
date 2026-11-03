"""Classic guard: an unavailable audio engine blocks the render with a reason."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_audio_block_reason_covers_unavailable_music_and_voice_engines():
    script = (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    assert (
        "Music generation needs a MiniMax or OpenRouter key. "
        "Add one in Setup, or choose Use my BGM."
    ) in script
    assert 'state.audioEngines?.music' in script
    assert '["minimax-music", "lyria-clip"]' in script
    assert 'state.audioEngines?.voices' in script
    assert "choose Use my recording" in script


def test_render_note_names_the_selected_audio_mode():
    script = (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    assert "function renderAudioNote()" in script
    for label in (
        "voice-over · original audio bed",
        "dubbed voice",
        "music bed",
        "new voice + music",
    ):
        assert label in script, label
    assert "${renderAudioNote()}" in script


def test_the_music_block_reaches_render_all_and_ab():
    script = (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    # One block reason feeds Render, Draft, All and A/B, so none can start an
    # unavailable engine.
    assert script.count("const blocked = audioBlockReason();") >= 1
    assert script.count("const block = audioBlockReason();") >= 3
