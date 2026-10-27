"""Final TTS engine set, story fallback and per-sentence cache contracts."""

from __future__ import annotations

import audio
import pytest
import tts

FINAL_ENGINES = {"minimax", "elevenlabs", "openrouter", "kokoro", "say"}
SYNTHESIS_ENGINES = {"minimax", "elevenlabs", "heygen", "fish", "gemini", "kokoro", "say"}
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


def test_explicit_engine_without_route_uses_its_real_default_model(monkeypatch, tmp_path):
    calls: list[dict] = []
    monkeypatch.setattr(tts, "synthesize_line", fake_synth_factory(calls))
    result = tts.synthesize_story(
        ["one"], engine="elevenlabs", cache_dir=tmp_path, routes=[],
    )
    assert result.model == "eleven_multilingual_v2"
    assert calls[0]["model"] == "eleven_multilingual_v2"


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


def test_heygen_free_is_the_first_default_voice_route():
    import workflow_config

    first = workflow_config.DEFAULT_WORKFLOWS["tts"]["routes"][0]
    assert first == {"provider": "openrouter", "model": "heygen/heygen-voice-1-turbo:free"}
    assert tts._candidate(first["provider"], first["model"])["engine"] == "heygen"
    assert tts.openrouter_engine("fish-audio/s2.1-pro-free:free") == "fish"
    assert tts.openrouter_engine("google/gemini-3.8-flash-lite-tts") == "gemini"


def test_heygen_requests_pcm_and_wraps_it_as_wav(monkeypatch, tmp_path):
    import json
    import wave

    sent = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"\x01\x00" * 4410 + b"\x07"  # 0.1 s plus a stray odd byte

    def fake_urlopen(request, timeout=0):
        sent.update(json.loads(request.data.decode("utf-8")))
        return Response()

    converted = {}

    def fake_convert(source, output, extra=None):
        with wave.open(str(source), "rb") as handle:
            converted.update(rate=handle.getframerate(), frames=handle.getnframes())
        output.write_bytes(b"RIFF" + b"0" * 64)
        return output

    monkeypatch.setattr(audio, "openrouter_key", lambda: "sk-test")
    monkeypatch.setattr(audio, "openrouter_blocked", lambda: False)
    monkeypatch.setattr(tts.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(audio, "_convert", fake_convert)
    out = tts.synthesize_line(
        "openrouter", "default", "Hello", tmp_path / "line.wav",
        model="heygen/heygen-voice-1-turbo:free",
    )
    assert out.is_file()
    assert sent["response_format"] == "pcm"
    assert sent["voice"] == "nadine"
    assert converted == {"rate": 44100, "frames": 4410}


def test_openrouter_model_comes_from_the_matching_engine_route(monkeypatch, tmp_path):
    monkeypatch.setattr(audio, "_workflow_routes", lambda name: [
        {"provider": "openrouter", "model": "heygen/heygen-voice-1-turbo:free"},
        {"provider": "openrouter", "model": "fish-audio/s2.1-pro-free:free"},
    ])
    sent = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"ID3"

    def fake_urlopen(request, timeout=0):
        import json

        sent.append(json.loads(request.data.decode("utf-8"))["model"])
        return Response()

    monkeypatch.setattr(audio, "openrouter_key", lambda: "sk-test")
    monkeypatch.setattr(audio, "openrouter_blocked", lambda: False)
    monkeypatch.setattr(tts.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(audio, "_convert", lambda source, output, extra=None: output)
    for engine in ("fish", "gemini"):
        tts._openrouter_voice("hi", "", tmp_path / f"{engine}.wav", 1.0, engine)
    assert sent == ["fish-audio/s2.1-pro-free:free", "google/gemini-3.8-flash-lite-tts"]
