"""Classic guard: first-run keys, voice engines, packs and the rights lock."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import app
import settings_store

ROOT = Path(__file__).resolve().parents[1]


def test_classic_setup_has_keys_engines_and_packs(monkeypatch):
    monkeypatch.setenv("VIBECUT_EDITION", "classic")
    monkeypatch.delenv("VIBECUT_FEATURES", raising=False)
    html = TestClient(app.app).get("/").text
    for needed in (
        'id="first-run-nudge"',
        'id="first-run-setup"',
        'id="setup-elevenlabs-key"',
        'id="setup-voice-engines"',
        'id="setup-packs"',
        'id="setup-packs-refresh"',
    ):
        assert needed in html, needed
    assert '"views":["classic"]' in html

    packs = TestClient(app.app).get("/api/classic/packs")
    assert packs.status_code == 200, packs.text
    assert [item["id"] for item in packs.json()["packs"]] == [
        "speech", "voice", "separation",
    ]


def test_setup_saves_an_elevenlabs_key_without_returning_it(monkeypatch, tmp_path):
    data = tmp_path / "settings"
    monkeypatch.setattr(settings_store, "DATA", data)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", data / "settings.json")
    monkeypatch.setattr(settings_store, "SECRETS_PATH", data / "secrets.json")
    monkeypatch.setattr(app.admin_store, "record_audit", lambda *args, **kwargs: None)
    monkeypatch.delenv("VIBECUT_ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)

    client = TestClient(app.app)
    saved = client.post(
        "/api/settings",
        json={"secrets": {"elevenlabs": "sk-classic-test-secret"}},
    )
    assert saved.status_code == 200, saved.text
    assert "sk-classic-test-secret" not in saved.text
    assert saved.json()["secrets"]["elevenlabs"] is True

    loaded = client.get("/api/settings")
    assert loaded.status_code == 200
    assert "sk-classic-test-secret" not in loaded.text
    assert loaded.json()["secrets"]["elevenlabs"] is True

    locked = client.post(
        "/api/settings",
        json={"settings": {"rights": {"lock": False}}},
    )
    assert locked.status_code == 200, locked.text
    assert locked.json()["settings"]["rights"]["lock"] is False


def test_setup_scripts_use_the_existing_routes():
    script = (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    assert '"/api/classic/packs"' in script
    assert "renderFirstRunNudge" in script
    assert "vibecut.setupSaved" in script
    assert "Optional: add keys and voices in Setup" in (
        ROOT / "static" / "classic" / "index.html"
    ).read_text(encoding="utf-8")


def test_classic_packs_count_engines_already_on_this_mac(monkeypatch):
    import audio
    import pipeline

    monkeypatch.setattr(pipeline, "whisper_models", lambda: [{"id": "w", "cached": True}])
    monkeypatch.setattr(audio, "engine_status", lambda: {
        "voices": {"kokoro": {"available": False}},
        "separation": {"demucs": {"available": True}},
    })
    packs = TestClient(app.app).get("/api/classic/packs").json()["packs"]
    usable = {item["id"]: item["usable"] for item in packs}
    assert usable == {"speech": True, "voice": False, "separation": True}
    script = (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    assert "pack.usable === true" in script
