"""The advisory audio check after every generated take.

The check measures silence, quiet, loud and clipping, says what it found, and
never changes or refuses the audio. Test sounds are written locally.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest
import real_media
from fastapi.testclient import TestClient

import audio
import settings_store
import stt
import tts
import voice_audio

ROOT = Path(__file__).resolve().parents[1]
needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is not installed")


def wav(path: Path, seconds: float = 1.0, amplitude: int = 9000, rate: int = 16000,
        square: bool = False) -> Path:
    """A real file of the kind the test describes."""
    if square:
        name = "clipped-speech.wav"
    elif amplitude == 0:
        name = "silence.wav"
    elif amplitude < 1000:
        name = "quiet-speech.wav"
    elif amplitude >= 30000:
        name = "loud-speech.wav"
    else:
        name = "speech.wav"
    return real_media.clip(name, path, seconds, rate=rate)


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_store, "DATA", tmp_path)
    monkeypatch.setattr(settings_store, "get_secret", lambda name: "sk-test" if name == "openrouter" else "")
    monkeypatch.setattr(audio, "openrouter_available", lambda: True)
    monkeypatch.setattr(audio, "openrouter_blocked", lambda: False)
    monkeypatch.setattr(audio, "openrouter_media_available", lambda: True)
    monkeypatch.setattr(stt, "_whisper_command", lambda: None)
    yield tmp_path


@pytest.fixture
def api(monkeypatch, tmp_path):
    import app

    def fake_sample(engine, voice, text, cache, rate=1.0, **extra):
        return wav(Path(cache) / f"take-{abs(hash(text)) % 10 ** 8}.wav", 0.8)

    monkeypatch.setattr(audio, "voice_sample", fake_sample)
    monkeypatch.setattr(tts, "voice_sample", fake_sample)
    return TestClient(app.app)


@needs_ffmpeg
@real_media.needs("silence.wav", "quiet-speech.wav", "loud-speech.wav", "clipped-speech.wav")
def test_silence_quiet_loud_and_clipping_are_named(tmp_path):
    silent = voice_audio.analyse(wav(tmp_path / "silent.wav", 2.0, 0))
    assert silent["silent"] is True
    assert silent["peak_dbfs"] <= voice_audio.SILENT_PEAK_DBFS

    quiet = voice_audio.analyse(wav(tmp_path / "quiet.wav", 2.0, 400))
    assert quiet["silent"] is False
    assert quiet["too_quiet"] is True
    assert quiet["too_loud"] is False

    loud = voice_audio.analyse(wav(tmp_path / "loud.wav", 2.0, 30000))
    assert loud["too_loud"] is True
    assert loud["silent"] is False

    clipped = voice_audio.analyse(wav(tmp_path / "clip.wav", 1.0, 32767, square=True))
    assert clipped["clipping"] is True
    assert clipped["clip_ratio"] >= voice_audio.CLIP_RATIO


@needs_ffmpeg
def test_the_check_never_changes_the_file(tmp_path):
    source = wav(tmp_path / "take.wav", 1.0, 9000)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    report = voice_audio.analyse(source)
    assert report["duration"] > 0.9
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


@needs_ffmpeg
def test_advice_is_written_for_made_audio_not_recordings():
    silent = voice_audio.output_advice({"silent": True})
    assert "no audible speech" in silent[0]
    assert "Record closer" not in silent[0]
    quiet = voice_audio.output_advice({"too_quiet": True})
    assert "quiet" in quiet[0]
    assert "usable" in voice_audio.output_advice({"silent": False, "too_quiet": False})[0]


@needs_ffmpeg
@real_media.needs("silence.wav")
def test_a_silent_take_is_kept_and_flagged_as_advice(api, monkeypatch, tmp_path):
    import app

    def silent_sample(engine, voice, text, cache, rate=1.0, **extra):
        return wav(Path(cache) / "silent-take.wav", 0.8, 0)

    monkeypatch.setattr(audio, "voice_sample", silent_sample)
    reply = api.post("/api/voices/sample", json={
        "engine": "say", "voice": "Samantha", "text": "this is silent",
    })
    assert reply.status_code == 200
    take = api.get("/api/voices/takes").json()["takes"][0]
    assert take["check"]["silent"] is True
    assert take["check"]["advisory"] is True
    assert "no audible speech" in take["check"]["advice"][0]
    # The audio is still served, unchanged and playable.
    played = api.get(take["audio_url"])
    assert played.status_code == 200
    assert played.content[:4] == b"RIFF"


@needs_ffmpeg
@real_media.needs("speech.wav")
def test_a_voiceover_also_carries_the_check(api, monkeypatch):
    import app  # noqa: F401 - the app builds the routers

    reply = api.post("/api/voices/voiceovers", json={
        "engine": "say", "voice": "Samantha",
        "text": "First line. Second line.",
        "rate": 1.0,
    })
    assert reply.status_code == 200, reply.text
    take = reply.json()
    assert take["check"]["available"] is True
    assert take["check"]["advisory"] is True
    assert take["check"]["advice"]
    assert take["selfcheck"]["status"] == "unavailable"


def test_the_page_shows_the_flags_and_says_advice_only():
    takes = (ROOT / "static" / "voice" / "takes.js").read_text(encoding="utf-8")
    next_js = (ROOT / "static" / "voice" / "next.js").read_text(encoding="utf-8")
    assert "vg-take-flag" in takes
    assert "check.advice" in takes
    assert "Advice only" in takes
    assert "take.check?.advice" in next_js
    assert "Advice only" in next_js
