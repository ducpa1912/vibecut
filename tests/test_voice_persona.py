"""Portable .vcutvoice files: manifest, preview, optional reference, import.

The preview speech is faked with a short WAV written by the test.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import struct
import wave
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import audio
import settings_store
import tts
import voice_clone
import voice_persona

ROOT = Path(__file__).resolve().parents[1]
VOICE = ROOT / "static" / "voice"


def tone(path: Path, seconds: float = 1.0, rate: int = 16000) -> Path:
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

    def fake_sample(engine, voice, text, cache, rate=1.0, **extra):
        return tone(Path(cache) / "preview.wav", 1.0)

    monkeypatch.setattr(tts, "voice_sample", fake_sample)
    yield tmp_path


@pytest.fixture
def api():
    import app

    return TestClient(app.app)


def clone(tmp_path: Path, name: str = "Andy-VN", language: str = "vi") -> dict:
    sample = tone(tmp_path / "reference.wav", 9.0)
    return voice_clone.create_clone(
        sample, name=name, source="me", consent=True, language=language, seconds=9.0,
    )


def members(raw: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


def manifest_of(raw: bytes) -> dict:
    return json.loads(members(raw)["voice.json"])


def rebuild(raw: bytes, *, manifest: dict | None = None, reference: bytes | None = None,
            extra: tuple[str, bytes] | None = None) -> bytes:
    files = members(raw)
    if manifest is not None:
        files["voice.json"] = json.dumps(manifest).encode()
    if reference is not None:
        files["reference.mp3"] = reference
    if extra:
        files[extra[0]] = extra[1]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, body in files.items():
            archive.writestr(name, body)
    return buffer.getvalue()


def test_export_holds_the_manifest_and_preview_but_not_the_clip(api, tmp_path):
    record = clone(tmp_path)
    reply = api.get(f"/api/voices/clones/{record['voice_id']}/persona")
    assert reply.status_code == 200, reply.text
    assert reply.headers["content-type"] == "application/zip"
    assert ".vcutvoice" in reply.headers["content-disposition"]
    files = members(reply.content)
    assert set(files) == {"voice.json", "preview.wav"}
    manifest = manifest_of(reply.content)
    assert manifest["format"] == "vibecut-voice-persona"
    assert manifest["version"] == 1
    assert manifest["name"] == "Andy-VN"
    assert manifest["language"] == "vi"
    assert manifest["consent"]["confirmed"] is True
    assert manifest["licence"] == "cloned-with-consent"
    assert manifest["reference"] == {"included": False}
    assert manifest["preview"]["seconds"] > 0
    assert files["preview.wav"][:4] == b"RIFF"


def test_export_can_include_the_recording_when_ticked(api, tmp_path):
    record = clone(tmp_path)
    reply = api.get(f"/api/voices/clones/{record['voice_id']}/persona?include_reference=1")
    files = members(reply.content)
    assert "reference.mp3" in files
    manifest = manifest_of(reply.content)
    assert manifest["reference"]["included"] is True
    reference = files["reference.mp3"]
    assert len(reference) == manifest["reference"]["bytes"]
    assert hashlib.sha256(reference).hexdigest() == manifest["reference"]["sha256"]


def test_a_failed_preview_stops_the_export_with_a_fix(api, tmp_path, monkeypatch):
    record = clone(tmp_path)
    monkeypatch.setattr(tts, "voice_sample", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no key")))
    reply = api.get(f"/api/voices/clones/{record['voice_id']}/persona")
    assert reply.status_code == 400
    detail = reply.json()["detail"]
    assert "preview could not be made" in detail
    assert "export" in detail.lower()


def test_a_preview_only_file_cannot_speak_and_says_why(api, tmp_path):
    record = clone(tmp_path)
    raw = api.get(f"/api/voices/clones/{record['voice_id']}/persona").content
    reply = api.post(
        "/api/voices/personas/import",
        files={"file": ("voice.vcutvoice", raw, "application/zip")},
        data={"consent": "true"},
    )
    assert reply.status_code == 400
    detail = reply.json()["detail"]
    assert "only a preview" in detail
    assert "Include the original recording" in detail


def test_import_creates_one_voice_and_a_second_import_does_not_duplicate(api, tmp_path):
    record = clone(tmp_path)
    raw = api.get(f"/api/voices/clones/{record['voice_id']}/persona?include_reference=1").content
    # Import into a library that does not already hold that sample.
    voice_clone.delete_clone(record["voice_id"])
    first = api.post(
        "/api/voices/personas/import",
        files={"file": ("voice.vcutvoice", raw, "application/zip")},
        data={"consent": "true"},
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["imported"] is True
    assert body["voice"]["name"] == "Andy-VN"
    assert body["voice"]["language"] == "vi"
    assert body["licence"] == "cloned-with-consent"
    again = api.post(
        "/api/voices/personas/import",
        files={"file": ("voice.vcutvoice", raw, "application/zip")},
        data={"consent": "true"},
    )
    assert again.status_code == 200
    assert again.json()["imported"] is False
    assert again.json()["already"] is True
    assert len(api.get("/api/voices/clones").json()["voices"]) == 1


def test_import_refuses_a_tampered_recording(api, tmp_path):
    record = clone(tmp_path)
    raw = api.get(f"/api/voices/clones/{record['voice_id']}/persona?include_reference=1").content
    swapped = rebuild(raw, reference=b"ID3" + b"\x00" * 5000)
    reply = api.post(
        "/api/voices/personas/import",
        files={"file": ("voice.vcutvoice", swapped, "application/zip")},
        data={"consent": "true"},
    )
    assert reply.status_code == 400
    assert "does not match its fingerprint" in reply.json()["detail"]


def test_import_refuses_unknown_licences_and_unsafe_paths(api, tmp_path):
    record = clone(tmp_path)
    raw = api.get(f"/api/voices/clones/{record['voice_id']}/persona?include_reference=1").content
    manifest = manifest_of(raw)
    manifest["licence"] = "all-rights-reserved-maybe"
    bad_licence = rebuild(raw, manifest=manifest)
    reply = api.post(
        "/api/voices/personas/import",
        files={"file": ("voice.vcutvoice", bad_licence, "application/zip")},
        data={"consent": "true"},
    )
    assert reply.status_code == 400
    assert "licence tag" in reply.json()["detail"]

    unsafe = rebuild(raw, extra=("../escape.txt", b"no"))
    reply = api.post(
        "/api/voices/personas/import",
        files={"file": ("voice.vcutvoice", unsafe, "application/zip")},
        data={"consent": "true"},
    )
    assert reply.status_code == 400
    assert "unsafe file path" in reply.json()["detail"]


def test_import_needs_the_importers_consent(api, tmp_path):
    record = clone(tmp_path)
    raw = api.get(f"/api/voices/clones/{record['voice_id']}/persona?include_reference=1").content
    reply = api.post(
        "/api/voices/personas/import",
        files={"file": ("voice.vcutvoice", raw, "application/zip")},
        data={"consent": "false"},
    )
    assert reply.status_code == 400
    assert "permission" in reply.json()["detail"]


def test_a_plain_zip_is_refused_with_a_fix(api):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("hello.txt", b"hi")
    reply = api.post(
        "/api/voices/personas/import",
        files={"file": ("bad.zip", buffer.getvalue(), "application/zip")},
        data={"consent": "true"},
    )
    assert reply.status_code == 400
    assert "manifest" in reply.json()["detail"]


def test_the_ui_exports_and_imports_voice_files():
    next_js = (VOICE / "next.js").read_text(encoding="utf-8")
    old_js = (VOICE / "voiceroom.js").read_text(encoding="utf-8")
    setup = (VOICE / "setup.js").read_text(encoding="utf-8")
    clone = (VOICE / "voiceclone.js").read_text(encoding="utf-8")
    assert "Export voice file" in next_js
    assert "Include the original recording" in next_js
    assert "personaUrl" in old_js
    assert "Import a voice file" in setup
    assert "export function personaUrl" in clone
    assert "export async function importPersona" in clone


def test_another_site_cannot_start_an_export(api, tmp_path):
    record = clone(tmp_path)
    url = f"/api/voices/clones/{record['voice_id']}/persona?include_reference=1"
    blocked = api.get(url, headers={"Sec-Fetch-Site": "cross-site"})
    assert blocked.status_code == 403
    assert api.get(url, headers={"Sec-Fetch-Site": "same-origin"}).status_code == 200
