"""The Setup readiness checklist: key, clone engine, local Whisper.

Every check is local and read-only; no network call is made.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import audio
import settings_store
import stt
import voice_readiness

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    secrets: dict[str, str] = {}
    monkeypatch.setattr(settings_store, "get_secret", lambda name: secrets.get(name, ""))
    monkeypatch.setattr(audio, "openrouter_blocked", lambda: False)
    monkeypatch.setattr(audio, "openrouter_blocked_seconds", lambda: 0)
    monkeypatch.setattr(audio, "openrouter_media_available", lambda: False)
    monkeypatch.setattr(stt, "_whisper_command", lambda: None)
    monkeypatch.setattr(stt, "whisper_models", lambda: [])
    monkeypatch.setattr(
        audio, "_openrouter_text",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("the checklist must not spend a request")),
    )
    return secrets


def by_id(report: dict) -> dict[str, dict]:
    return {item["id"]: item for item in report["items"]}


def test_everything_missing_says_what_to_do(clean):
    report = voice_readiness.checklist()
    items = by_id(report)
    assert [item["id"] for item in report["items"]] == ["openrouter", "clone", "whisper"]
    for item in report["items"]:
        assert item["state"] == "failed"
        assert item["detail"]
        assert item["action"]["label"]
        assert item["action"]["kind"] in {"test_key", "check_clone", "check_whisper"}
    assert "OpenRouter key" in items["openrouter"]["detail"]
    assert "install" in items["whisper"]["detail"].lower()
    assert "brew install openai-whisper" in items["whisper"]["detail"]


def test_everything_ready(clean, monkeypatch):
    clean["openrouter"] = "sk-test"
    monkeypatch.setattr(audio, "openrouter_media_available", lambda: True)
    monkeypatch.setattr(stt, "_whisper_command", lambda: ["whisper"])
    monkeypatch.setattr(stt, "whisper_models", lambda: [{
        "id": "large-v3-turbo", "current": True, "cached": False,
    }])
    report = voice_readiness.checklist()
    for item in report["items"]:
        assert item["state"] == "ready", item
        assert item["action"]["label"]
    whisper = by_id(report)["whisper"]
    assert "first use" in whisper["detail"]


def test_a_blocked_key_names_the_retry(clean, monkeypatch):
    clean["openrouter"] = "sk-test"
    monkeypatch.setattr(audio, "openrouter_blocked", lambda: True)
    monkeypatch.setattr(audio, "openrouter_blocked_seconds", lambda: 42)
    items = by_id(voice_readiness.checklist())
    assert items["openrouter"]["state"] == "failed"
    assert "Retry in 42 s" in items["openrouter"]["detail"]


def test_the_route_returns_the_checklist_and_hides_with_the_feature(monkeypatch):
    import app

    api = TestClient(app.app)
    monkeypatch.setenv("VIBECUT_FEATURES", "voice_room")
    reply = api.get("/api/voices/readiness")
    assert reply.status_code == 200
    body = reply.json()
    assert len(body["items"]) == 3
    assert body["checked"] > 0
    monkeypatch.setenv("VIBECUT_FEATURES", "")
    assert api.get("/api/voices/readiness").status_code == 404


def test_setup_has_one_key_list_and_the_whisper_status():
    text = (ROOT / "static" / "voice" / "setup.js").read_text(encoding="utf-8")
    # One Setup copied from the original layout, not a second readiness screen.
    assert "Before you start" not in text
    assert "runReadiness" not in text
    for title in ("Keys", "OpenRouter", "MiniMax", "ElevenLabs", "Voices", "Local Whisper"):
        assert title in text, title
    assert "Save key" in text and "Remove saved key" in text
    assert "/api/voices/readiness" in text  # Whisper is the one live check
    assert "Check again" in text
    assert "One key; no per-model setup" in text
    css = (ROOT / "static" / "voice" / "voice.css").read_text(encoding="utf-8")
    for name in ("vr-key", "vr-key-form", "vr-setup-engine"):
        assert name in css, name
