"""Local language detection and the new Voice Room shell behind ?ui=new.

Whisper and ffmpeg are faked; no media is made, and nothing calls a cloud.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import audio
import settings_store


@pytest.fixture
def api(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(settings_store, "DATA", tmp_path)
    monkeypatch.setattr(audio, "_run", lambda cmd, **kw: Path(cmd[-1]).write_bytes(b"RIFF"))
    return TestClient(app.app)


def _detect(api, name="me.webm", body=b"\x1a\x45\xdf\xa3" + b"\x00" * 64):
    return api.post("/api/voices/detect-language", files={"file": (name, body, "audio/webm")})


def test_detect_language_uses_local_whisper_only(api, monkeypatch):
    import stt

    calls = []

    def fake_transcribe(wav, work, seconds, progress, language=""):
        calls.append((Path(wav).name, seconds, language))
        return {"language": "VI-vn", "text": "Xin chào " * 40}

    def no_cloud(*_args, **_kwargs):
        raise AssertionError("language detection must not use a cloud engine")

    monkeypatch.setattr(stt, "transcribe", fake_transcribe)
    monkeypatch.setattr(stt, "transcribe_cloud", no_cloud)
    reply = _detect(api)
    assert reply.status_code == 200
    assert reply.json()["language"] == "vi"
    assert len(reply.json()["text"]) <= 160
    assert calls == [("detect.wav", 45.0, "")]


def test_detect_language_says_so_without_whisper(api, monkeypatch):
    import stt

    monkeypatch.setattr(stt, "transcribe", lambda *a, **k: None)
    reply = _detect(api)
    assert reply.status_code == 400
    assert "pick the language manually" in reply.json()["detail"]


def test_detect_language_refusals(api):
    assert _detect(api, name="notes.txt").status_code == 400
    assert _detect(api, body=b"").status_code == 400
    blocked = api.post(
        "/api/voices/detect-language",
        files={"file": ("me.webm", b"x", "audio/webm")},
        headers={"Origin": "https://evil.example"},
    )
    assert blocked.status_code == 403


def test_new_ui_is_served_only_on_request(api):
    old = api.get("/voices")
    new = api.get("/voices?ui=new")
    assert old.status_code == new.status_code == 200
    assert "voiceroom.js" in old.text and "voiceroom.js" not in new.text
    assert "next.js" in new.text


def test_new_ui_hides_with_the_voice_room_switch(api, monkeypatch):
    monkeypatch.setenv("VIBECUT_FEATURES", "")
    assert api.get("/voices?ui=new").status_code == 404
