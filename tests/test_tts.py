"""Final TTS engine set, story fallback and per-sentence cache contracts."""

from __future__ import annotations

import audio
import pytest
import tts

FINAL_ENGINES = {"minimax", "elevenlabs", "openrouter", "kokoro", "say"}
SYNTHESIS_ENGINES = {"minimax", "elevenlabs", "fish", "gemini", "kokoro", "say"}
REMOVED = ("piper", "openai", "groq", "deepgram", "cartesia")


def fake_synth_factory(calls, fail=None):
    def fake(engine, voice, text, output, rate=1.0, cancel_event=None, *,
             model="", timeout=300, language=""):
        calls.append({
            "engine": engine, "voice": voice, "text": text, "model": model,
            "rate": rate, "language": language,
        })
        if fail and fail(engine, text):
            raise audio.AudioError("synthetic failure")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"RIFF" + b"0" * 2048)
        return output

    return fake


def test_final_engine_set_excludes_removed_engines():
    assert set(tts.ENGINES) == FINAL_ENGINES
    assert set(tts.SYNTHESIZERS) == SYNTHESIS_ENGINES
    assert set(tts.voice_engine_status()) == SYNTHESIS_ENGINES
    assert tts.is_removed_engine("piper") is True
    assert tts.is_removed_engine("kokoro") is False
    for engine in REMOVED:
        assert tts.list_voices(engine) == []


def test_removed_engine_synthesis_is_refused(tmp_path):
    for engine in REMOVED:
        with pytest.raises(audio.AudioError, match="removed"):
            tts.synthesize_line(engine, "voice", "hello", tmp_path / f"{engine}.wav")
    assert not list(tmp_path.iterdir())


def test_route_candidates_drop_removed_providers_and_piper(monkeypatch):
    monkeypatch.setattr(audio, "_workflow", lambda name: {
        "routes": [
            {"provider": "minimax", "model": "speech-2.8-turbo"},
            {"provider": "openai", "model": "gpt-4o-mini-tts"},
            {"provider": "local", "model": "piper"},
            {"provider": "local", "model": "kokoro"},
            {"provider": "cartesia", "model": "sonic-3.6"},
            {"provider": "elevenlabs", "model": "eleven_multilingual_v2"},
        ],
    })
    assert tts._tts_route_candidates() == [
        {"engine": "minimax", "provider": "minimax", "model": "speech-2.8-turbo"},
        {"engine": "kokoro", "provider": "local", "model": "kokoro"},
        {"engine": "elevenlabs", "provider": "elevenlabs",
         "model": "eleven_multilingual_v2"},
    ]


def test_line_cache_key_covers_engine_model_voice_text_rate_and_language():
    base = tts.line_cache_key("minimax", "speech-2.8-turbo", "female-shaonv", "hi", 1.0, "en")
    assert base == tts.line_cache_key(
        "minimax", "speech-2.8-turbo", "female-shaonv", "hi", 1.0, "en",
    )
    variants = [
        tts.line_cache_key("elevenlabs", "speech-2.8-turbo", "female-shaonv", "hi", 1.0, "en"),
        tts.line_cache_key("minimax", "other", "female-shaonv", "hi", 1.0, "en"),
        tts.line_cache_key("minimax", "speech-2.8-turbo", "other", "hi", 1.0, "en"),
        tts.line_cache_key("minimax", "speech-2.8-turbo", "female-shaonv", "hello", 1.0, "en"),
        tts.line_cache_key("minimax", "speech-2.8-turbo", "female-shaonv", "hi", 1.1, "en"),
        tts.line_cache_key("minimax", "speech-2.8-turbo", "female-shaonv", "hi", 1.0, "vi"),
    ]
    assert len(set([base, *variants])) == len(variants) + 1


def test_story_cache_hit_avoids_resynthesis(monkeypatch, tmp_path):
    calls: list[dict] = []
    monkeypatch.setattr(tts, "synthesize_line", fake_synth_factory(calls))
    routes = [{"provider": "minimax", "model": "speech-2.8-turbo"}]

    first = tts.synthesize_story(
        ["one", "two"], engine="auto", voice="female-yujie",
        cache_dir=tmp_path, routes=routes, language="en",
    )
    assert first.engine == "minimax"
    assert first.voice == "female-yujie"
    assert first.cache_hits == 0
    assert len(calls) == 2

    second = tts.synthesize_story(
        ["one", "two"], engine="auto", voice="female-yujie",
        cache_dir=tmp_path, routes=routes, language="en",
    )
    assert second.cache_hits == 2
    assert len(calls) == 2
    assert first.paths == second.paths


def test_story_falls_back_as_a_whole_and_never_mixes_voices(monkeypatch, tmp_path):
    calls: list[dict] = []

    def fail(engine, text):
        return engine == "minimax" and text == "second"

    monkeypatch.setattr(tts, "synthesize_line", fake_synth_factory(calls, fail))
    routes = [
        {"provider": "minimax", "model": "speech-2.8-turbo"},
        {"provider": "elevenlabs", "model": "eleven_multilingual_v2"},
    ]

    result = tts.synthesize_story(
        ["first", "second", "third"], engine="auto", voice="female-yujie",
        cache_dir=tmp_path, routes=routes,
    )

    assert result.engine == "elevenlabs"
    assert result.voice == tts.DEFAULT_VOICES["elevenlabs"]
    assert result.voice != "female-yujie"
    assert result.attempts == ("elevenlabs", "elevenlabs", "elevenlabs")
    assert len(result.paths) == 3
    assert all("elevenlabs" in path.name or path.is_file() for path in result.paths)
    # The fallback restarted at sentence one, with one voice for every line.
    fallback_calls = [call for call in calls if call["engine"] == "elevenlabs"]
    assert [call["text"] for call in fallback_calls] == ["first", "second", "third"]
    assert {call["voice"] for call in fallback_calls} == {result.voice}


def test_story_raises_when_every_engine_fails(monkeypatch, tmp_path):
    calls: list[dict] = []
    monkeypatch.setattr(
        tts, "synthesize_line", fake_synth_factory(calls, lambda engine, text: True),
    )
    routes = [
        {"provider": "minimax", "model": "speech-2.8-turbo"},
        {"provider": "local", "model": "say"},
    ]
    with pytest.raises(audio.AudioError, match="All voice engines failed"):
        tts.synthesize_story(
            ["one"], cache_dir=tmp_path, routes=routes,
        )
    assert {call["engine"] for call in calls} == {"minimax", "say"}


def test_story_rejects_removed_engine_before_synthesis(tmp_path):
    with pytest.raises(audio.AudioError, match="removed"):
        tts.synthesize_story(
            ["one"], engine="piper", cache_dir=tmp_path,
            routes=[{"provider": "local", "model": "say"}],
        )


def test_openrouter_alias_selects_fish_or_gemini(monkeypatch, tmp_path):
    captured: list[str] = []

    def fake_openrouter(text, voice, output, rate=1.0, engine="fish", model="", timeout=300):
        captured.append(engine)
        output.write_bytes(b"RIFF" + b"0" * 2048)

    monkeypatch.setattr(audio, "_openrouter_voice", fake_openrouter)
    tts.synthesize_line(
        "openrouter", "default", "hello", tmp_path / "fish.wav",
        model="fish-audio/s2.1-pro-free:free",
    )
    tts.synthesize_line(
        "openrouter", "Kore", "hello", tmp_path / "gemini.wav",
        model="google/gemini-3.8-flash-lite-tts",
    )
    assert captured == ["fish", "gemini"]


def test_voice_sample_cache_includes_model_and_language(monkeypatch, tmp_path):
    calls: list[dict] = []
    monkeypatch.setattr(tts, "synthesize_line", fake_synth_factory(calls))
    monkeypatch.setattr(audio, "synthesize_line", fake_synth_factory(calls))

    first = tts.voice_sample(
        "minimax", "female-shaonv", "hello", tmp_path,
        model="speech-2.8-turbo", language="en",
    )
    second = tts.voice_sample(
        "minimax", "female-shaonv", "hello", tmp_path,
        model="speech-2.8-turbo", language="vi",
    )
    assert first.is_file() and second.is_file()
    assert first != second
    assert len(calls) == 2
