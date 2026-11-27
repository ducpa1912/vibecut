"""DuckSuite must stay local: no speech, route or model path may reach a cloud.

The review project's Check recorded ``openrouter`` speech routes, and a core
started with OPENROUTER_API_KEY would upload the audio. These tests pin the
three promises of docs/teams/local-only-stt/BRIEF.md.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import urllib.request
from pathlib import Path

import pytest

from duckcore import model_slots
from duckcore.engine import settings_store, stt, workflow_config

SECRET_ENV = (
    "OPENROUTER_API_KEY",
    "GROQ_API_KEY",
    "DEEPGRAM_API_KEY",
    "MINIMAX_API_KEY",
    "ELEVENLABS_API_KEY",
)
CLOUD = {"openrouter", "groq", "deepgram", "openai", "minimax", "elevenlabs"}
LOCAL = {"apple", "whisper"}
LOCAL_ROUTES = [
    {"provider": "apple", "model": "on-device-3b"},
    {"provider": "whisper", "model": stt.DEFAULT_WHISPER_MODEL},
]


def _speech_wav(path: Path) -> None:
    """A tiny real audio file, because the speech pass runs ffmpeg on it."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg is absent, so no real audio file can be made")
    subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=1",
         "-ac", "1", "-ar", "16000", str(path)],
        check=True, timeout=120,
    )


def test_failed_check_speech_makes_no_network_call(tmp_path, monkeypatch):
    """Check's real speech pass with every key set and every local engine down."""
    for name in SECRET_ENV:
        monkeypatch.setenv(name, "dummy-key-for-test")
    monkeypatch.setattr(settings_store, "load_settings", lambda: {})
    monkeypatch.setattr(stt, "has_speech_energy", lambda _path: True)
    # Both local engines are unavailable, as reported in the review project.
    monkeypatch.setattr(stt, "_apple_transcribe_helper", lambda: None)
    monkeypatch.setattr(stt, "_whisper_command", lambda: None)

    calls: list[str] = []

    def no_network(request, *args, **kwargs):
        url = getattr(request, "full_url", str(request))
        calls.append(url)
        raise AssertionError(f"network call attempted: {url}")

    monkeypatch.setattr(urllib.request, "urlopen", no_network)

    wav = tmp_path / "speech.wav"
    _speech_wav(wav)
    job_dir = tmp_path / "projects" / "prj_test" / "work"
    job_dir.mkdir(parents=True)
    # The route list Check really uses (duckcore/engine/pipeline.py:3030).
    routes = workflow_config.effective({}, "stt").get("routes") or []
    errors: list[dict] = []

    result = stt.transcribe_source(
        wav, job_dir, 1.0, routes=routes, language="en", errors=errors,
    )

    assert calls == [], f"speech pass reached the network: {calls}"
    assert not result or not result.get("segments")
    assert not result or not result.get("model")
    assert not result or str(result.get("provider") or "") not in CLOUD
    cloud_errors = [row for row in errors if str(row.get("provider")) in CLOUD]
    assert cloud_errors == [], f"Check tried a cloud speech route: {cloud_errors}"


@pytest.mark.parametrize("engine", ["openrouter", "groq", "deepgram", "auto", ""])
def test_route_names_never_resolve_to_a_cloud_provider(engine, monkeypatch):
    monkeypatch.setattr(settings_store, "load_settings", lambda: {})
    plan = stt.resolve_routes(list(LOCAL_ROUTES), engine=engine)
    assert plan, f"engine {engine!r} resolved to no route"
    assert {str(route["provider"]) for route in plan} <= LOCAL, plan


def test_saved_cloud_routes_still_resolve_local(monkeypatch):
    monkeypatch.setattr(settings_store, "load_settings", lambda: {})
    saved = {
        "stt": {
            "routes": [
                {"provider": "openrouter", "model": "openai/whisper-large-v3-turbo"},
                {"provider": "groq", "model": "whisper-large-v3-turbo"},
                {"provider": "deepgram", "model": "nova-3"},
            ],
        },
    }
    for routes in (workflow_config.routes(saved, "stt"),
                   workflow_config.routes({}, "stt"),
                   list(LOCAL_ROUTES)):
        for engine in ("", "auto", "openrouter", "groq", "deepgram"):
            plan = stt.resolve_routes(routes, engine=engine)
            assert plan, f"{routes} with engine {engine!r} resolved to nothing"
            assert {str(route["provider"]) for route in plan} <= LOCAL, plan


def test_model_slots_refuse_non_loopback_before_any_request(tmp_path, monkeypatch):
    opened: list[str] = []

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self._body = json.dumps(payload).encode()

        def read(self, *_args) -> bytes:
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *_exc) -> None:
            return None

    class FakeOpener:
        def open(self, request, timeout=None):
            opened.append(request.full_url)
            return FakeResponse({"data": [{"id": "local-model"}]})

    monkeypatch.setattr(
        urllib.request, "build_opener", lambda *handlers: FakeOpener(),
    )

    for bad in ("https://example.com/v1", "http://10.0.0.5:8080"):
        before = len(opened)
        with pytest.raises(ValueError):
            model_slots.model_id(bad)
        with pytest.raises(ValueError):
            model_slots.configure(tmp_path, "rewrite", bad)
        assert len(opened) == before, f"request sent for non-loopback host {bad}"
        assert not (tmp_path / "settings.json").exists()

    for good in ("http://127.0.0.1:8080", "http://localhost:1234"):
        assert model_slots.model_id(good) == "local-model"
        assert opened[-1].startswith(good)
