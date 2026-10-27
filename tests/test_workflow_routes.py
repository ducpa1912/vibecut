"""Admin-selected workflow routes must reach the provider calls."""

from __future__ import annotations

import json

import audio
import settings_store
import workflow_config


def test_default_routes_use_only_final_engines():
    defaults = workflow_config.default_workflows()
    assert [route["provider"] for route in defaults["tts"]["routes"]] == [
        "minimax", "openrouter", "openrouter", "local", "local",
    ]
    assert "piper" not in {
        route["model"] for route in defaults["tts"]["routes"]
    }
    assert [route["provider"] for route in defaults["stt"]["routes"]] == [
        "apple", "whisper",
    ]
    assert defaults["stt"]["routes"][-1]["model"] == (
        "mlx-community/whisper-large-v3-turbo"
    )
    for name in ("story_brief", "rewrite", "translate", "hook_rank"):
        providers = [route["provider"] for route in defaults[name]["routes"]]
        assert providers == ["opencode-go", "openrouter"]
        assert "local-mlx" not in providers and "ollama" not in providers
    assert workflow_config.TTS_PROVIDERS == (
        "minimax", "openrouter", "local", "elevenlabs",
    )
    assert workflow_config.STT_PROVIDERS == (
        "apple", "whisper", "groq", "deepgram",
    )


def test_removed_providers_never_leave_a_workflow_empty():
    normalized = workflow_config.normalize_workflow("story_brief", {
        "routes": [
            {"provider": "local-mlx", "model": "mlx-community/Qwen2.5-3B-Instruct-4bit"},
            {"provider": "ollama", "model": "qwen2.5:3b"},
        ],
        "reasoning": "low",
        "max_output_tokens": 3200,
        "timeout_s": 300,
    })
    assert [route["provider"] for route in normalized["routes"]] == [
        "opencode-go", "openrouter",
    ]


def _settings(routes, reasoning="medium"):
    return {
        "workflows": {
            name: {
                "routes": routes,
                "reasoning": reasoning,
                "max_output_tokens": 1234,
                "timeout_s": 45,
            }
            for name in ("story_brief", "rewrite", "translate", "hook_rank")
        }
    }


def test_workflow_text_passes_route_model_and_falls_back(monkeypatch):
    calls = []
    monkeypatch.setattr(audio.settings_store, "load_settings", lambda: _settings([
        {"provider": "opencode-go", "model": "first-model"},
        {"provider": "openrouter", "model": "second-model"},
    ]))
    monkeypatch.setattr(audio, "_pipeline_event", lambda *args, **kwargs: None)

    def fake_opencode(prompt, **kwargs):
        calls.append(("opencode", kwargs))
        return None

    def fake_openrouter(prompt, **kwargs):
        calls.append(("openrouter", kwargs))
        return "answer"

    monkeypatch.setattr(audio, "_opencode_text", fake_opencode)
    monkeypatch.setattr(audio, "_openrouter_text", fake_openrouter)

    result = audio._workflow_text("rewrite", "prompt", json_mode=True)

    assert result == "answer"
    assert calls[0][0] == "opencode"
    assert calls[0][1]["model"] == "first-model"
    assert calls[0][1]["variant"] == "medium"
    assert calls[0][1]["max_tokens"] == 1234
    assert calls[0][1]["timeout"] == 45
    assert calls[1][0] == "openrouter"
    assert calls[1][1]["model"] == "second-model"
    assert calls[1][1]["reasoning"] == "medium"


def test_workflow_text_uses_only_configured_routes(monkeypatch):
    monkeypatch.setattr(audio.settings_store, "load_settings", lambda: _settings([
        {"provider": "openrouter", "model": "only-model"},
    ]))
    monkeypatch.setattr(audio, "_pipeline_event", lambda *args, **kwargs: None)
    called = []
    monkeypatch.setattr(audio, "_opencode_text", lambda *args, **kwargs: called.append("opencode"))
    monkeypatch.setattr(audio, "_openrouter_text", lambda *args, **kwargs: "ok")

    assert audio._workflow_text("story_brief", "prompt") == "ok"
    assert called == []


def test_rewrite_plan_maps_admin_routes_and_keeps_rules_last():
    plan = audio._rewrite_workflow_plan()
    names = [item["name"] for item in plan]
    assert names[-1] == "rules"
    assert "opencode" in names
    assert "openrouter" in names


def test_stt_workflow_honors_route_order_model_and_timeout(monkeypatch, tmp_path):
    import pipeline

    calls = []
    transcript = {
        "language": "en", "text": "hello", "segments": [{"start": 0, "end": 1, "text": "hello"}],
        "provider": "groq", "model": "whisper-large-v3-turbo", "seconds": 1,
    }

    def fake_cloud(wav, job_dir, provider, language, model="", timeout=1800):
        calls.append((provider, model, timeout))
        if provider == "openai":
            return None
        return transcript

    monkeypatch.setattr(pipeline, "_cloud_speech", fake_cloud)
    monkeypatch.setattr(pipeline, "_pipeline_log", lambda *args, **kwargs: None)
    routes = [
        {"provider": "openai", "model": "whisper-1"},
        {"provider": "groq", "model": "whisper-large-v3-turbo"},
    ]
    wav = tmp_path / "audio.wav"
    wav.write_bytes(b"wave")
    result = pipeline._transcribe_workflow(
        wav, tmp_path, 3.0, "en", routes, 45.0, lambda *args: None,
        job_id="job-1",
    )
    assert result == transcript
    assert calls == [
        ("openai", "whisper-1", 45.0),
        ("groq", "whisper-large-v3-turbo", 45.0),
    ]


def test_stt_apple_route_falls_back_to_local_whisper(monkeypatch, tmp_path):
    import pipeline

    calls = []
    transcript = {
        "language": "en", "text": "hello", "segments": [{"start": 0, "end": 1, "text": "hello"}],
        "provider": "whisper", "seconds": 1,
    }

    def fake_apple(wav, job_dir, language, timeout=None):
        calls.append(("apple", language, timeout))
        return None

    def fake_whisper(wav, job_dir, duration, progress, *, model=None, timeout=None):
        calls.append(("whisper", model, timeout))
        return transcript

    monkeypatch.setattr(pipeline, "transcribe_apple", fake_apple)
    monkeypatch.setattr(pipeline, "transcribe", fake_whisper)
    monkeypatch.setattr(pipeline, "_pipeline_log", lambda *args, **kwargs: None)
    routes = [
        {"provider": "apple", "model": "on-device-3b"},
        {"provider": "whisper", "model": "mlx-community/whisper-large-v3-turbo"},
    ]
    wav = tmp_path / "audio.wav"
    wav.write_bytes(b"wave")
    result = pipeline._transcribe_workflow(
        wav, tmp_path, 3.0, "en", routes, 45.0, lambda *args: None,
        job_id="job-1",
    )
    assert result == transcript
    assert calls == [
        ("apple", "en", 45.0),
        ("whisper", "mlx-community/whisper-large-v3-turbo", 45.0),
    ]


def test_music_routes_preserve_admin_order_and_models(monkeypatch):
    monkeypatch.setattr(audio.settings_store, "load_settings", lambda: {
        "workflows": {
            "music": {
                "routes": [
                    {"provider": "openrouter", "model": "google/lyria-3-pro-preview"},
                    {"provider": "minimax", "model": "music-3.0"},
                ],
                "timeout_s": 90,
            }
        }
    })
    assert audio._music_route_candidates() == [
        {"provider": "openrouter", "model": "google/lyria-3-pro-preview",
         "descriptor": "openrouter:google/lyria-3-pro-preview"},
        {"provider": "minimax", "model": "music-3.0",
         "descriptor": "minimax:music-3.0"},
    ]


def test_generate_music_passes_admin_model_and_timeout(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr(audio, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(audio, "openrouter_key", lambda: "sk-or")
    monkeypatch.setattr(audio, "openrouter_blocked", lambda: False)
    monkeypatch.setattr(audio, "save_generated_asset", lambda *args, **kwargs: None)

    def fake_lyria(prompt, seconds, output, model="", timeout=600):
        captured.update({"model": model, "timeout": timeout})
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"x" * 2048)

    monkeypatch.setattr(audio, "_lyria_music", fake_lyria)
    result = audio.generate_music(
        "openrouter:google/lyria-3-pro-preview", "calm", 30,
        timeout=77,
    )
    assert result.is_file()
    assert captured == {"model": "google/lyria-3-pro-preview", "timeout": 77}


def test_tts_synthesize_passes_model_and_timeout_to_minimax(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr(
        audio, "usage_store",
        type("U", (), {
            "TTS_PER_CHAR": {}, "record": staticmethod(lambda *a, **k: None),
        }),
    )

    def fake_minimax(text, voice, output, rate=1.0, model="", timeout=300):
        captured.update({"model": model, "timeout": timeout})
        output.write_bytes(b"RIFF" * 100)

    monkeypatch.setattr(audio, "_minimax_voice", fake_minimax)
    output = tmp_path / "line.wav"
    audio.synthesize_line(
        "minimax", "female-shaonv", "hello", output,
        model="speech-2.8-turbo", timeout=33,
    )
    assert output.is_file()
    assert captured == {"model": "speech-2.8-turbo", "timeout": 33}


def test_removed_tts_engine_cannot_be_synthesized(tmp_path):
    import pytest

    with pytest.raises(audio.AudioError, match="removed"):
        audio.synthesize_line("cartesia", "voice-id", "hello", tmp_path / "line.wav")
    assert not (tmp_path / "line.wav").exists()


def test_deepgram_query_parameters_are_urlencoded(monkeypatch, tmp_path):
    import json
    import pipeline

    wav = tmp_path / "audio.wav"
    wav.write_bytes(b"RIFF")
    captured = {}

    def fake_run(cmd, timeout=None):
        target = __import__("pathlib").Path(cmd[-1])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"mp3")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({
                "metadata": {"language": "en"},
                "results": {"channels": [{"alternatives": [{"transcript": "hello"}]}]},
            }).encode("utf-8")

    monkeypatch.setattr(pipeline, "_run", fake_run)
    monkeypatch.setattr(pipeline.settings_store, "get_secret", lambda name: "dg-key")
    def fake_urlopen(request, timeout=0):
        captured.setdefault("url", request.full_url)
        return FakeResponse()

    monkeypatch.setattr(pipeline.urllib.request, "urlopen", fake_urlopen)
    result = pipeline._cloud_speech(
        wav, tmp_path, "deepgram", "en",
        model="nova-3&evil=1#fragment", timeout=20,
    )
    assert result is not None
    assert "model=nova-3%26evil%3D1%23fragment" in captured["url"]
    assert "evil=1#fragment" not in captured["url"]


FOUNDER_SETTINGS = {
    "tts": {"provider": "piper"},
    "stt": {"provider": "auto", "model": "mlx-community/whisper-small-mlx"},
    "workflows": {
        "story_brief": {
            "routes": [
                {"provider": "local-mlx", "model": "mlx-community/Qwen2.5-3B-Instruct-4bit"},
                {"provider": "opencode-go", "model": "deepseek-v4.1-flash"},
                {"provider": "openrouter", "model": "deepseek/deepseek-v4.1-flash"},
            ],
            "reasoning": "low",
            "max_output_tokens": 3200,
            "timeout_s": 300,
        },
        "tts": {
            "routes": [
                {"provider": "openai", "model": "gpt-4o-mini-tts"},
                {"provider": "local", "model": "piper"},
                {"provider": "local", "model": "say"},
            ],
            "reasoning": "",
            "max_output_tokens": 0,
            "timeout_s": 120,
        },
    },
}


def test_settings_migration_removes_text_routes_and_maps_tts(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    path = data / "settings.json"
    path.write_text(json.dumps(FOUNDER_SETTINGS), encoding="utf-8")
    monkeypatch.setattr(settings_store, "DATA", data)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", path)
    monkeypatch.setattr(settings_store, "SECRETS_PATH", data / "secrets.json")

    settings = settings_store.load_settings()

    brief = settings["workflows"]["story_brief"]["routes"]
    assert [route["provider"] for route in brief] == ["opencode-go", "openrouter"]
    assert settings["tts"]["provider"] == "kokoro"
    tts_routes = settings["workflows"]["tts"]["routes"]
    assert [route["provider"] for route in tts_routes] == [
        "minimax", "local", "local",
    ]
    assert [route["model"] for route in tts_routes] == [
        "speech-2.8-turbo", "kokoro", "say",
    ]
    assert all("piper" not in route["model"] for route in tts_routes)

    written = path.read_text(encoding="utf-8")
    assert "local-mlx" not in written
    assert "gpt-4o-mini-tts" not in written
    # A second load does not rewrite the file again.
    settings_store.load_settings()
    assert path.read_text(encoding="utf-8") == written


def test_settings_migration_falls_back_when_every_text_route_is_removed(
    tmp_path, monkeypatch,
):
    data = tmp_path / "data"
    data.mkdir()
    path = data / "settings.json"
    path.write_text(json.dumps({
        "workflows": {
            "rewrite": {
                "routes": [{"provider": "ollama", "model": "qwen2.5:3b"}],
            },
        },
    }), encoding="utf-8")
    monkeypatch.setattr(settings_store, "DATA", data)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", path)
    monkeypatch.setattr(settings_store, "SECRETS_PATH", data / "secrets.json")

    settings = settings_store.load_settings()

    assert [route["provider"] for route in settings["workflows"]["rewrite"]["routes"]] == [
        "opencode-go", "openrouter",
    ]
    assert "ollama" not in path.read_text(encoding="utf-8")
