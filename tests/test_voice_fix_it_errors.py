"""Fix-it errors: every failure names the cause and the next step.

The silent reference is a real 9 s WAV written by the test. The cleaner is
faked to fail, so the raw file reaches the silence check; no cloud is called.
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import audio
import settings_store
import voice_errors
import voice_extract


def silent(path: Path, seconds: float = 9.0, rate: int = 16000) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * int(rate * seconds))
    return path


def tone(path: Path, seconds: float = 9.0, rate: int = 16000) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frames = bytearray()
        for index in range(int(rate * seconds)):
            frames += struct.pack("<h", int(9000 * math.sin(2 * math.pi * 220 * index / rate)))
        handle.writeframes(bytes(frames))
    return path


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_store, "DATA", tmp_path)
    monkeypatch.setattr(settings_store, "get_secret", lambda name: "sk-test" if name == "openrouter" else "")
    monkeypatch.setattr(audio, "openrouter_available", lambda: True)
    monkeypatch.setattr(audio, "openrouter_blocked", lambda: False)
    monkeypatch.setattr(audio, "openrouter_media_available", lambda: True)
    monkeypatch.setattr(
        voice_extract, "extract_clean_voice",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no speech found")),
    )
    yield tmp_path


@pytest.fixture
def api():
    import app

    return TestClient(app.app)


def _upload(api, path: Path, **fields):
    data = {"name": "Me", "language": "en", "consent": "true", **fields}
    with path.open("rb") as handle:
        return api.post(
            "/api/voices/clones",
            files={"file": (path.name, handle, "audio/wav")},
            data=data,
        )


def test_a_silent_clip_says_record_closer_and_watch_the_level(api, tmp_path):
    reply = _upload(api, silent(tmp_path / "silent.wav"))
    assert reply.status_code == 400, reply.text
    detail = reply.json()["detail"]
    assert "No speech could be heard" in detail
    assert "closer to the microphone" in detail
    assert "input level moves" in detail
    assert "Traceback" not in detail and "\n" not in detail
    # Nothing was cloned from the silence.
    assert api.get("/api/voices/clones").json()["voices"] == []


def test_an_unreadable_file_says_what_to_try_next(api, tmp_path):
    broken = tmp_path / "broken.wav"
    broken.write_bytes(b"this is not audio" * 100)
    reply = _upload(api, broken)
    assert reply.status_code == 400
    detail = reply.json()["detail"]
    assert voice_errors.has_next_step(detail)
    assert "Traceback" not in detail and "\n" not in detail


def test_a_real_clip_still_clones(api, tmp_path, monkeypatch):
    import voice_clone

    monkeypatch.setattr(voice_clone, "available", lambda: True)
    reply = _upload(api, tone(tmp_path / "me.wav"))
    assert reply.status_code == 200, reply.text
    assert reply.json()["voice_id"].startswith("clone_")


def test_every_shared_error_has_a_next_step():
    for name in dir(voice_errors):
        if not name.isupper() or name in {"CLEANUP_WARNING"}:
            continue
        message = getattr(voice_errors, name)
        if not isinstance(message, str):
            continue
        assert voice_errors.has_next_step(message), name
        assert "\n" not in message and "Traceback" not in message, name
        sentences = [part for part in message.split(". ") if part.strip()]
        assert len(sentences) <= 2, name


def test_live_responses_are_short_and_actionable(api):
    checks = [
        api.post("/api/voices/sample", json={"engine": "nope", "voice": "x", "text": "hi"}),
        api.post("/api/voices/clones", files={"file": ("x.wav", b"x", "audio/wav")}, data={}),
        api.get("/api/voices/clones/clone_000000000000000000000000"),
        api.get("/api/voices/takes/take_000000000000000000000000"),
        api.post(
            "/api/voices/library/import",
            files={"file": ("bad.zip", b"not a zip", "application/zip")},
            data={"consent": "true"},
        ),
    ]
    for reply in checks:
        assert reply.status_code >= 400
        detail = reply.json()["detail"]
        assert voice_errors.has_next_step(detail), detail
        assert "Traceback" not in detail and "\n" not in detail, detail


def test_clean_removes_a_traceback_and_long_tails():
    raw = "Traceback (most recent call last):\n  File \"x.py\", line 3\nSomething"
    assert voice_errors.clean(raw) == "That step failed. Try again."
    long = "A. B. C. D. " + "x" * 500
    cleaned = voice_errors.clean(long)
    assert len(cleaned) <= 320
    assert cleaned.count(". ") <= 1
