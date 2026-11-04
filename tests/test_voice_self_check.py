"""Self-check by re-transcribing: local Whisper reads our own voiceover back.

The speech and the transcript are faked; the take and its audio are real.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import real_media
from fastapi.testclient import TestClient

import audio
import settings_store
import stt
import tts
import voice_takes

ROOT = Path(__file__).resolve().parents[1]
needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is not installed")


def tone(path: Path, seconds: float = 0.5, rate: int = 16000) -> Path:
    return real_media.clip("speech.wav", path, seconds, rate=rate)


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_store, "DATA", tmp_path)
    monkeypatch.setattr(settings_store, "get_secret", lambda name: "sk-test" if name == "openrouter" else "")
    monkeypatch.setattr(audio, "openrouter_available", lambda: True)
    monkeypatch.setattr(audio, "openrouter_blocked", lambda: False)
    monkeypatch.setattr(audio, "openrouter_media_available", lambda: True)

    def fake_sample(engine, voice, text, cache, rate=1.0, **extra):
        return tone(Path(cache) / f"line-{abs(hash(text)) % 10 ** 8}.wav", 0.5)

    monkeypatch.setattr(tts, "voice_sample", fake_sample)
    yield tmp_path


@pytest.fixture
def api(monkeypatch):
    import app

    monkeypatch.setattr(stt, "_whisper_command", lambda: ["whisper"])
    return TestClient(app.app)


def line_number(job_dir: Path) -> int:
    name = Path(job_dir).name
    tail = name.rsplit("-", 1)[-1]
    return int(tail) if tail.isdigit() else 0


@needs_ffmpeg
@real_media.needs("speech.wav")
def test_one_drifted_line_is_flagged_with_what_whisper_heard(api, monkeypatch):
    heard = {
        1: "First line here.",
        2: "Something completely different.",
        3: "Third line here.",
    }
    seen = []

    def fake_transcribe(wav, job_dir, seconds, progress, language=""):
        index = line_number(job_dir)
        seen.append((index, round(float(seconds), 1), language))
        return {"text": heard.get(index, ""), "language": "en", "segments": []}

    monkeypatch.setattr(stt, "transcribe", fake_transcribe)
    reply = api.post("/api/voices/voiceovers", json={
        "engine": "say", "voice": "Samantha", "language": "en",
        "text": "First line here. Second line here. Third line here.",
        "rate": 1.0,
    })
    assert reply.status_code == 200, reply.text
    take = reply.json()
    check = take["selfcheck"]
    assert check["status"] == "checked"
    assert check["threshold"] == voice_takes.SELF_CHECK_THRESHOLD
    assert check["flagged"] == 1
    assert len(check["lines"]) == len(take["chunks"]) == 3
    flagged = [line for line in check["lines"] if line["drift"]]
    assert len(flagged) == 1
    assert flagged[0]["index"] == 2
    assert "different" in flagged[0]["heard"]
    assert flagged[0]["ratio"] < voice_takes.SELF_CHECK_THRESHOLD
    assert check["lines"][0]["drift"] is False
    assert "1 line may have drifted" in check["note"]
    assert [row[0] for row in seen] == [1, 2, 3]
    # The flagged take is still kept and playable; the check is advice.
    assert api.get(take["audio_url"]).status_code == 200
    stored = api.get(f"/api/voices/takes/{take['id']}").json()
    assert stored["selfcheck"]["flagged"] == 1


@needs_ffmpeg
@real_media.needs("speech.wav")
def test_matching_lines_report_all_clear(api, monkeypatch):
    monkeypatch.setattr(
        stt, "transcribe",
        lambda wav, job_dir, seconds, progress, language="": {
            "text": ["First line here.", "Second line here.", "Third line here."][line_number(job_dir) - 1],
            "language": "en", "segments": [],
        },
    )
    reply = api.post("/api/voices/voiceovers", json={
        "engine": "say", "voice": "Samantha",
        "text": "First line here. Second line here. Third line here.",
    })
    assert reply.status_code == 200, reply.text
    check = reply.json()["selfcheck"]
    assert check["flagged"] == 0
    assert "matched the script" in check["note"]


@needs_ffmpeg
@real_media.needs("speech.wav")
def test_whisper_hearing_nothing_flags_every_line(api, monkeypatch):
    monkeypatch.setattr(
        stt, "transcribe",
        lambda *a, **k: {"text": "", "language": "en", "segments": []},
    )
    reply = api.post("/api/voices/voiceovers", json={
        "engine": "say", "voice": "Samantha",
        "text": "First line here. Second line here.",
    })
    assert reply.status_code == 200, reply.text
    check = reply.json()["selfcheck"]
    assert check["status"] == "checked"
    assert check["flagged"] == len(check["lines"])
    assert all(line["heard"] == "" for line in check["lines"])


def test_drift_needs_a_real_word_difference():
    assert voice_takes.compare_line("Hello there, this is my voice.", "Hello there this is my voice") > 0.95
    assert voice_takes.compare_line("Hello there, this is my voice.", "Goodbye now, nothing like it") < 0.4
    assert voice_takes.compare_line("", "anything") == 0.0


def test_the_takes_list_shows_flagged_lines_and_their_match():
    takes = (ROOT / "static" / "voice" / "takes.js").read_text(encoding="utf-8")
    next_js = (ROOT / "static" / "voice" / "next.js").read_text(encoding="utf-8")
    assert "may differ" in takes
    assert "Lines match the script" in takes
    assert "match ${Math.round" in takes
    assert "heard:" in takes
    assert "selfcheck" in next_js
    assert "check.note" in next_js
