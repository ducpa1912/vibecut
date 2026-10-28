"""Cloned voices: store, consent, HeyGen calls and the OpenRouter route."""

import json
import urllib.error

import pytest
from fastapi.testclient import TestClient

import audio
import settings_store
import tts
import voice_clone


@pytest.fixture(autouse=True)
def clone_store(monkeypatch, tmp_path):
    monkeypatch.setattr(settings_store, "DATA", tmp_path)
    monkeypatch.setattr(voice_clone, "heygen_key", lambda: "hg-test")
    yield tmp_path


class Reply:
    def __init__(self, payload):
        self.body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.body


def _sample(tmp_path):
    path = tmp_path / "sample.wav"
    path.write_bytes(b"RIFF" + b"\x00" * 9000)
    return path


def _active(voice_id="a" * 32, source="me", language="en"):
    return voice_clone._upsert({
        "voice_id": voice_id, "name": "Me", "source": source,
        "language": language, "status": "ACTIVE", "created": 1.0,
    })


def test_speech_windows_merge_and_cap():
    segments = [
        {"start": 0.0, "end": 4.0, "text": "one"},
        {"start": 4.2, "end": 9.0, "text": "two"},
        {"start": 20.0, "end": 21.0, "text": ""},
        {"start": 30.0, "end": 400.0, "text": "long"},
    ]
    windows = voice_clone.speech_windows(segments, limit=60)
    assert windows[0] == (0.0, 9.0)
    assert windows[1][0] == 30.0
    assert sum(b - a for a, b in windows) == pytest.approx(60, abs=0.01)
    ranged = voice_clone.speech_windows(segments, start=5, end=8)
    assert ranged == [(5.0, 8.0)]


def test_clone_needs_consent(tmp_path):
    with pytest.raises(voice_clone.CloneError, match="permission"):
        voice_clone.create_clone(_sample(tmp_path), name="x", source="me", consent=False)
    assert voice_clone.list_clones() == []


def test_create_clone_posts_instant_base64_and_stores_record(monkeypatch, tmp_path):
    sent = {}

    def fake_urlopen(request, timeout=0):
        sent["url"] = request.full_url
        sent["headers"] = dict(request.header_items())
        sent["body"] = json.loads(request.data.decode())
        return Reply({"data": {"voice_id": "b" * 32}})

    monkeypatch.setattr(voice_clone.urllib.request, "urlopen", fake_urlopen)
    record = voice_clone.create_clone(
        _sample(tmp_path), name="  My   voice ", source="me", consent=True, language="en-US",
    )
    assert sent["url"].endswith("/v3/models/audio/voices")
    assert sent["headers"]["X-api-key"] == "hg-test"
    body = sent["body"]
    assert body["mode"] == "instant" and body["language"] == "en"
    assert body["audio"][0]["type"] == "base64" and body["audio"][0]["media_type"] == "audio/wav"
    assert record["name"] == "My voice" and record["status"] == "PENDING"
    assert voice_clone.get_clone("b" * 32)["consent"]["confirmed"] is True


def test_refresh_updates_status_and_never_stores_preview(monkeypatch):
    _active(voice_id="c" * 32)
    voice_clone._upsert({**voice_clone.get_clone("c" * 32), "status": "PENDING"})
    monkeypatch.setattr(voice_clone.urllib.request, "urlopen", lambda request, timeout=0: Reply(
        {"data": {"status": "ACTIVE", "language": "vi", "preview_audio_url": "https://x/p.wav"}}
    ))
    record = voice_clone.refresh("c" * 32)
    assert record["status"] == "ACTIVE" and record["preview_url"] == "https://x/p.wav"
    stored = voice_clone.get_clone("c" * 32)
    assert stored["language"] == "vi" and "preview_url" not in stored


def test_heygen_voice_list_puts_active_clones_first(monkeypatch):
    _active()
    voice_clone._upsert({"voice_id": "d" * 32, "name": "P", "status": "PENDING", "created": 2.0})
    monkeypatch.setattr(audio, "openrouter_available", lambda: True)
    voices = tts.list_voices("heygen")
    assert voices[0]["id"] == "a" * 32 and voices[0]["clone"] is True
    assert "d" * 32 not in {voice["id"] for voice in voices}
    assert {voice["id"] for voice in voices[1:]} == set(tts.HEYGEN_VOICES)


def test_openrouter_speaks_a_clone_id_unchanged(monkeypatch, tmp_path):
    _active()
    sent = {}

    def fake_urlopen(request, timeout=0):
        sent.update(json.loads(request.data.decode()))
        return Reply(b"\x01\x00" * 4410)

    monkeypatch.setattr(audio, "openrouter_available", lambda: True)
    monkeypatch.setattr(audio, "openrouter_key", lambda: "sk-test")
    monkeypatch.setattr(audio, "openrouter_blocked", lambda: False)
    monkeypatch.setattr(tts.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(audio, "_convert", lambda s, o, e=None: o.write_bytes(b"RIFF" + b"0" * 64) or o)
    tts.synthesize_line("heygen", "a" * 32, "Hello", tmp_path / "line.wav",
                        model="heygen/heygen-voice-1-turbo:free")
    assert sent["voice"] == "a" * 32
    assert sent["model"] == "heygen/heygen-voice-1-turbo:free"


def test_clone_falls_back_to_heygen_when_openrouter_refuses(monkeypatch, tmp_path):
    _active()

    def refuse(request, timeout=0):
        raise urllib.error.HTTPError(request.full_url, 400, "bad voice", {}, None)

    direct = {}

    def fake_direct(text, voice_id, output, *, language="", timeout=300):
        direct.update(text=text, voice=voice_id, language=language)
        output.write_bytes(b"RIFF" + b"0" * 64)
        return output

    monkeypatch.setattr(audio, "openrouter_available", lambda: True)
    monkeypatch.setattr(audio, "openrouter_key", lambda: "sk-test")
    monkeypatch.setattr(audio, "openrouter_blocked", lambda: False)
    monkeypatch.setattr(tts.urllib.request, "urlopen", refuse)
    monkeypatch.setattr(voice_clone, "speak_direct", fake_direct)
    monkeypatch.setattr(audio, "_convert", lambda s, o, e=None: o.write_bytes(b"RIFF" + b"0" * 64) or o)
    out = tts.synthesize_line("heygen", "a" * 32, "Hi", tmp_path / "line.wav")
    assert out.is_file()
    assert direct == {"text": "Hi", "voice": "a" * 32, "language": "en"}
    # A clone refusal must not quarantine OpenRouter for everyone else.
    assert not audio.openrouter_blocked()


def test_stock_voice_still_raises_on_openrouter_failure(monkeypatch, tmp_path):
    def refuse(request, timeout=0):
        raise urllib.error.HTTPError(request.full_url, 500, "down", {}, None)

    monkeypatch.setattr(audio, "openrouter_available", lambda: True)
    monkeypatch.setattr(audio, "openrouter_key", lambda: "sk-test")
    monkeypatch.setattr(audio, "openrouter_blocked", lambda: False)
    monkeypatch.setattr(tts.urllib.request, "urlopen", refuse)
    with pytest.raises(audio.AudioError, match="OpenRouter heygen voice failed"):
        tts.synthesize_line("heygen", "nadine", "Hi", tmp_path / "line.wav")


def test_speak_direct_downloads_the_wav(monkeypatch, tmp_path):
    calls = []

    def fake_urlopen(request, timeout=0):
        url = request if isinstance(request, str) else request.full_url
        calls.append(url)
        if url.endswith("/tts"):
            body = json.loads(request.data.decode())
            assert body["model"] == voice_clone.HEYGEN_DIRECT_MODEL
            return Reply({"data": {"audio_url": "https://files.heygen.ai/x.wav", "duration": 1}})
        return Reply(b"RIFF" + b"1" * 200)

    monkeypatch.setattr(voice_clone.urllib.request, "urlopen", fake_urlopen)
    out = voice_clone.speak_direct("Hi", "a" * 32, tmp_path / "x.wav", language="en")
    assert out.read_bytes().startswith(b"RIFF") and len(calls) == 2


def test_routes_list_and_consent(monkeypatch):
    import app

    _active()
    api = TestClient(app.app)
    listed = api.get("/api/voices/clones").json()
    assert listed["available"] is True and listed["voices"][0]["voice_id"] == "a" * 32
    refused = api.post(
        "/api/voices/clones",
        files={"file": ("me.wav", b"RIFF" + b"0" * 100, "audio/wav")},
        data={"consent": "false"},
    )
    assert refused.status_code == 400 and "own voice" in refused.json()["detail"]
    cross = api.delete(f"/api/voices/clones/{'a' * 32}", headers={"sec-fetch-site": "cross-site"})
    assert cross.status_code == 403


def test_delete_removes_local_row_when_heygen_already_forgot(monkeypatch):
    _active()

    def gone(request, timeout=0):
        raise urllib.error.HTTPError(request.full_url, 404, "missing", {}, None)

    monkeypatch.setattr(voice_clone.urllib.request, "urlopen", gone)
    assert voice_clone.delete_clone("a" * 32) is True
    assert voice_clone.list_clones() == []
