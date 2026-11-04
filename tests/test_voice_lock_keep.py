"""Lock identity and Keep take: one reference, one set of settings.

The speech call is faked and the reference is a short WAV written by the test.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
import real_media
from fastapi.testclient import TestClient

import audio
import settings_store
import voice_clone

ROOT = Path(__file__).resolve().parents[1]
VOICE = ROOT / "static" / "voice"


def tone(path: Path, seconds: float = 0.5, rate: int = 16000) -> Path:
    return real_media.clip("speech.wav", path, seconds, rate=rate)


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_store, "DATA", tmp_path)
    monkeypatch.setattr(settings_store, "get_secret", lambda name: "sk-test" if name == "openrouter" else "")
    monkeypatch.setattr(audio, "openrouter_available", lambda: True)
    monkeypatch.setattr(audio, "openrouter_blocked", lambda: False)
    monkeypatch.setattr(audio, "openrouter_media_available", lambda: True)
    yield tmp_path


@pytest.fixture
def api(monkeypatch, tmp_path):
    import app

    def fake_sample(engine, voice, text, cache, rate=1.0, **extra):
        out = Path(cache) / f"out-{abs(hash((voice, text, rate))) % 10 ** 10}.wav"
        return tone(out, 0.4)

    monkeypatch.setattr(audio, "voice_sample", fake_sample)
    return TestClient(app.app)


def clone(tmp_path: Path, name: str = "Me", language: str = "en") -> dict:
    sample = tone(tmp_path / f"{name}.wav", 9.0)
    return voice_clone.create_clone(
        sample, name=name, source="me", consent=True, language=language, seconds=9.0,
    )


def test_lock_freezes_the_reference_and_refuses_a_changed_one(api, tmp_path):
    record = clone(tmp_path)
    url = f"/api/voices/clones/{record['voice_id']}"
    locked = api.post(f"{url}/lock", json={"locked": True})
    assert locked.status_code == 200, locked.text
    body = locked.json()
    assert len(body["locked"]["sha256"]) == 64
    assert body["locked"]["language"] == "en"
    mode = os.stat(voice_clone.sample_path(record["voice_id"])).st_mode & 0o777
    assert mode == 0o444

    first = api.post(f"{url}/sample", json={"text": "one"})
    assert first.status_code == 200

    sample = voice_clone.sample_path(record["voice_id"])
    os.chmod(sample, 0o644)
    sample.write_bytes(b"ID3" + b"\x00" * 400)
    changed = api.post(f"{url}/sample", json={"text": "two"})
    assert changed.status_code == 409
    assert "changed after it was locked" in changed.json()["detail"]
    assert "Unlock" in changed.json()["detail"]

    unlocked = api.post(f"{url}/lock", json={"locked": False})
    assert unlocked.status_code == 200
    assert "locked" not in unlocked.json()
    assert "unlock_warning" in unlocked.json()
    assert "later takes may sound different" in unlocked.json()["unlock_warning"].lower()
    mode = os.stat(sample).st_mode & 0o777
    assert mode == 0o644
    assert api.post(f"{url}/sample", json={"text": "three"}).status_code == 200


def test_a_locked_voice_keeps_its_language(api, tmp_path, monkeypatch):
    record = clone(tmp_path, language="vi")
    url = f"/api/voices/clones/{record['voice_id']}"
    assert api.post(f"{url}/lock", json={"locked": True}).status_code == 200
    # Even if the stored row says something else later, the lock wins.
    rows = voice_clone._read()
    for row in rows:
        if row["voice_id"] == record["voice_id"]:
            row["language"] = "en"
    voice_clone._write(rows)
    seen = []

    def fake_sample(engine, voice, text, cache, rate=1.0, language="", **extra):
        seen.append(language)
        out = Path(cache) / "lang.wav"
        return tone(out, 0.4)

    monkeypatch.setattr(audio, "voice_sample", fake_sample)
    assert api.post(f"{url}/sample", json={"text": "xin chào"}).status_code == 200
    assert seen == ["vi"]


def test_keep_take_pins_the_take_settings(api, tmp_path):
    record = clone(tmp_path)
    url = f"/api/voices/clones/{record['voice_id']}"
    assert api.post(f"{url}/sample", json={"text": "Good line.", "rate": 1.15}).status_code == 200
    take = api.get("/api/voices/takes").json()["takes"][0]
    kept = api.post(f"{url}/keep", json={"take_id": take["id"]})
    assert kept.status_code == 200, kept.text
    body = kept.json()
    assert body["keep"]["take_id"] == take["id"]
    assert body["keep"]["text"] == "Good line."
    assert body["keep"]["rate"] == 1.15
    assert body["keep"]["language"] == "en"
    # It survives a reload.
    assert api.get(url).json()["keep"]["rate"] == 1.15

    cleared = api.post(f"{url}/keep", json={"take_id": ""})
    assert cleared.status_code == 200
    assert "keep" not in cleared.json()


def test_keep_refuses_another_voices_take_and_a_missing_take(api, tmp_path):
    one = clone(tmp_path, "One")
    two = clone(tmp_path, "Two")
    api.post(f"/api/voices/clones/{one['voice_id']}/sample", json={"text": "Mine"})
    take = api.get("/api/voices/takes").json()["takes"][0]
    wrong = api.post(f"/api/voices/clones/{two['voice_id']}/keep", json={"take_id": take["id"]})
    assert wrong.status_code == 400
    assert "another voice" in wrong.json()["detail"]
    missing = api.post(f"/api/voices/clones/{two['voice_id']}/keep", json={"take_id": "take_000000000000000000000000"})
    assert missing.status_code == 404
    assert "Reload" in missing.json()["detail"]


def test_a_locked_voice_can_still_be_deleted(api, tmp_path):
    record = clone(tmp_path)
    assert api.post(f"/api/voices/clones/{record['voice_id']}/lock", json={"locked": True}).status_code == 200
    assert api.delete(f"/api/voices/clones/{record['voice_id']}").status_code == 200
    assert api.get(f"/api/voices/clones/{record['voice_id']}").status_code == 404


def test_both_pages_offer_lock_and_the_takes_list_offers_keep():
    next_js = (VOICE / "next.js").read_text(encoding="utf-8")
    old_js = (VOICE / "voiceroom.js").read_text(encoding="utf-8")
    takes = (VOICE / "takes.js").read_text(encoding="utf-8")
    clone = (VOICE / "voiceclone.js").read_text(encoding="utf-8")
    for text in (next_js, old_js):
        assert "Lock identity" in text and "Unlock identity" in text
        assert "toggleLock" in text
    assert "export function lockClone" in clone
    assert "export function keepTakeOnVoice" in clone
    assert "Keep take" in takes
    assert "onKeepTake" in next_js
    assert "Use kept settings" in next_js
