"""Cloned voices: store, consent, samples and the OpenRouter HeyGen route."""

import base64
import json
import shutil
import subprocess
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
    yield tmp_path


@pytest.fixture
def openrouter(monkeypatch):
    monkeypatch.setattr(audio, "openrouter_available", lambda: True)
    monkeypatch.setattr(audio, "openrouter_key", lambda: "sk-test")
    monkeypatch.setattr(audio, "openrouter_blocked", lambda: False)
    monkeypatch.setattr(audio, "_convert", lambda s, o, e=None: o.write_bytes(b"RIFF" + b"0" * 64) or o)


class Reply:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return b"\x01\x00" * 4410


def _clone(tmp_path, *, source="me", language="en", name="Me"):
    sample = tmp_path / "sample.mp3"
    sample.write_bytes(b"ID3" + b"\x00" * 4000)
    return voice_clone.create_clone(
        sample, name=name, source=source, consent=True, language=language, seconds=42,
    )


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
    assert voice_clone.speech_windows(segments, start=5, end=8) == [(5.0, 8.0)]


def test_clone_needs_consent(tmp_path):
    sample = tmp_path / "s.mp3"
    sample.write_bytes(b"ID3" + b"\x00" * 4000)
    with pytest.raises(voice_clone.CloneError, match="permission"):
        voice_clone.create_clone(sample, name="x", source="me", consent=False)
    assert voice_clone.list_clones() == []


def test_create_clone_keeps_sample_locally_without_network(monkeypatch, tmp_path):
    def no_network(*args, **kwargs):
        raise AssertionError("cloning must not call the network")

    monkeypatch.setattr("urllib.request.urlopen", no_network)
    record = _clone(tmp_path, language="en-US", name="  My   voice ")
    assert voice_clone.is_voice_id(record["voice_id"])
    assert record["name"] == "My voice" and record["language"] == "en"
    assert record["status"] == "ACTIVE" and record["consent"]["confirmed"] is True
    assert voice_clone.sample_path(record["voice_id"]).is_file()


def test_delete_removes_record_and_sample(tmp_path):
    record = _clone(tmp_path)
    voice_clone.delete_clone(record["voice_id"])
    assert voice_clone.list_clones() == []
    assert not voice_clone.sample_path(record["voice_id"]).exists()
    with pytest.raises(voice_clone.CloneError):
        voice_clone.delete_clone(record["voice_id"])


def test_heygen_voice_list_puts_clones_first(tmp_path, openrouter):
    record = _clone(tmp_path)
    voices = tts.list_voices("heygen")
    assert voices[0]["id"] == record["voice_id"] and voices[0]["clone"] is True
    assert {voice["id"] for voice in voices[1:]} == set(tts.HEYGEN_VOICES)


def test_no_openrouter_key_means_no_heygen_voices(tmp_path, monkeypatch):
    _clone(tmp_path)
    monkeypatch.setattr(audio, "openrouter_available", lambda: False)
    assert tts.list_voices("heygen") == []


def test_clone_is_sent_as_openrouter_input_reference(monkeypatch, tmp_path, openrouter):
    record = _clone(tmp_path, language="vi")
    sent = {}

    def fake_urlopen(request, timeout=0):
        sent["url"] = request.full_url
        sent["body"] = json.loads(request.data.decode())
        return Reply()

    monkeypatch.setattr(tts.urllib.request, "urlopen", fake_urlopen)
    tts.synthesize_line("heygen", record["voice_id"], "Xin chào", tmp_path / "line.wav",
                        model="heygen/heygen-voice-1-turbo:free")
    body = sent["body"]
    assert sent["url"] == "https://openrouter.ai/api/v1/audio/speech"
    assert body["model"] == "heygen/heygen-voice-1-turbo:free"
    assert "voice" not in body
    assert body["response_format"] == "pcm"
    ref = body["input_references"][0]
    assert ref["type"] == "input_audio"
    data = ref["input_audio"]["data"]
    assert data.startswith("data:audio/mpeg;base64,")
    assert base64.b64decode(data.split(",", 1)[1]) == voice_clone.sample_path(record["voice_id"]).read_bytes()
    assert body["provider"] == {"options": {"heygen": {"language": "vi"}}}


def test_stock_voice_request_is_unchanged(monkeypatch, tmp_path, openrouter):
    sent = {}

    def fake_urlopen(request, timeout=0):
        sent.update(json.loads(request.data.decode()))
        return Reply()

    monkeypatch.setattr(tts.urllib.request, "urlopen", fake_urlopen)
    tts.synthesize_line("heygen", "bram", "Hi", tmp_path / "line.wav")
    assert sent["voice"] == "bram" and "input_references" not in sent


def test_clone_failure_raises_and_never_calls_heygen_directly(monkeypatch, tmp_path, openrouter):
    record = _clone(tmp_path)
    urls = []

    def refuse(request, timeout=0):
        urls.append(request.full_url)
        raise urllib.error.HTTPError(request.full_url, 400, "bad", {}, None)

    monkeypatch.setattr(tts.urllib.request, "urlopen", refuse)
    with pytest.raises(audio.AudioError, match="OpenRouter heygen voice failed"):
        tts.synthesize_line("heygen", record["voice_id"], "Hi", tmp_path / "line.wav")
    assert urls == ["https://openrouter.ai/api/v1/audio/speech"]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is not installed")
def test_prepare_sample_cuts_a_small_mono_mp3(tmp_path):
    source = tmp_path / "talk.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=220:duration=30",
         "-f", "lavfi", "-i", "color=c=black:s=320x240:d=30", "-shortest",
         "-c:v", "libx264", "-c:a", "aac", str(source)],
        check=True,
    )
    out = tmp_path / "sample.mp3"
    seconds = voice_clone.prepare_sample(source, out, windows=[(2.0, 12.0), (15.0, 25.0)])
    assert seconds == pytest.approx(20, abs=0.5)
    assert out.stat().st_size < 400_000
    with pytest.raises(voice_clone.CloneError, match="only"):
        voice_clone.prepare_sample(source, tmp_path / "short.mp3", windows=[(0.0, 3.0)])


def test_routes_list_consent_and_origin(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(voice_clone, "available", lambda: True)
    record = _clone(tmp_path)
    api = TestClient(app.app)
    listed = api.get("/api/voices/clones").json()
    assert listed["available"] is True and listed["voices"][0]["voice_id"] == record["voice_id"]
    assert api.get(f"/api/voices/clones/{record['voice_id']}").json()["name"] == "Me"
    refused = api.post(
        "/api/voices/clones",
        files={"file": ("me.wav", b"RIFF" + b"0" * 100, "audio/wav")},
        data={"consent": "false"},
    )
    assert refused.status_code == 400 and "own voice" in refused.json()["detail"]
    cross = api.delete(f"/api/voices/clones/{record['voice_id']}", headers={"sec-fetch-site": "cross-site"})
    assert cross.status_code == 403
    assert api.delete(f"/api/voices/clones/{record['voice_id']}").json() == {"deleted": record["voice_id"]}
