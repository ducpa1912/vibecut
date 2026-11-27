"""A retired Kokoro voice falls back to the macOS default, and says so.

REQ-20261125-03: the notice `voice._resolve_voice` returns must reach the
preview, the voice-over and the dub track, and the track must name the voice
that actually spoke.
"""

from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from duckcore import voice
from duckcore.main import create_app

TOKEN = "test-token"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def _stub_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_synthesize(text, name, aiff, data_root=None):
        aiff.write_bytes(b"")

    def fake_to_wave(source, target):
        target.write_bytes(b"")

    def fake_fit(source, target, duration):
        frames = int(round(max(0.05, float(duration)) * voice.SAMPLE_RATE))
        with wave.open(str(target), "wb") as writer:
            writer.setnchannels(voice.CHANNELS)
            writer.setsampwidth(voice.SAMPLE_WIDTH)
            writer.setframerate(voice.SAMPLE_RATE)
            writer.writeframes(b"\x00" * frames * voice.SAMPLE_WIDTH * voice.CHANNELS)

    monkeypatch.setattr(voice, "_synthesize", fake_synthesize)
    monkeypatch.setattr(voice, "_to_wave", fake_to_wave)
    monkeypatch.setattr(voice, "_fit", fake_fit)
    monkeypatch.setattr(voice, "_duration", lambda path: 2.0)


def _client(tmp_path: Path) -> TestClient:
    edit_dir = tmp_path / "projects" / "prj_voice" / "edits"
    edit_dir.mkdir(parents=True)
    edit = {
        "id": "ed_voice",
        "project_id": "prj_voice",
        "end": 2.0,
        "captions": {"cues": [{"start": 0.0, "end": 1.0, "text": "Hello"}]},
    }
    (edit_dir / "ed_voice.json").write_text(json.dumps(edit), encoding="utf-8")
    return TestClient(create_app(TOKEN, tmp_path))


def test_dub_track_names_the_voice_that_spoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_audio(monkeypatch)
    with _client(tmp_path) as client:
        response = client.post(
            "/api/projects/prj_voice/edits/ed_voice/dub",
            headers=HEADERS,
            json={"voice": "kokoro:af_heart", "language": "en"},
        )
        assert response.status_code == 200
        dub = response.json()["dub"]
        assert dub["name"] == f"Dub · {voice.DEFAULT_VOICE}"
        assert dub["voice"] == voice.DEFAULT_VOICE
        assert dub["message"] == "The saved voice pack was retired. Using the default macOS voice."


def test_preview_and_generate_carry_the_notice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_audio(monkeypatch)
    with _client(tmp_path) as client:
        preview = client.post(
            "/api/projects/prj_voice/edits/ed_voice/voice/preview",
            headers=HEADERS,
            json={"text": "Hello", "voice": "kokoro:af_heart"},
        )
        assert preview.status_code == 200
        assert preview.json()["preview"]["message"]

        generated = client.post(
            "/api/projects/prj_voice/edits/ed_voice/voice",
            headers=HEADERS,
            json={"voice": "kokoro:af_heart", "mode": "voice_over"},
        )
        assert generated.status_code == 200
        track = generated.json()["voice"]
        assert track["message"] == preview.json()["preview"]["message"]
        assert track["voice"] == voice.DEFAULT_VOICE


def test_ordinary_macos_voice_has_no_notice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_audio(monkeypatch)
    with _client(tmp_path) as client:
        preview = client.post(
            "/api/projects/prj_voice/edits/ed_voice/voice/preview",
            headers=HEADERS,
            json={"text": "Hello", "voice": "Samantha"},
        )
        assert preview.status_code == 200
        assert "message" not in preview.json()["preview"]

        generated = client.post(
            "/api/projects/prj_voice/edits/ed_voice/voice",
            headers=HEADERS,
            json={"voice": "Samantha", "mode": "voice_over"},
        )
        assert generated.status_code == 200
        assert "message" not in generated.json()["voice"]
        assert generated.json()["voice"]["voice"] == "Samantha"

        dub = client.post(
            "/api/projects/prj_voice/edits/ed_voice/dub",
            headers=HEADERS,
            json={"voice": "Samantha", "language": "en"},
        )
        assert dub.status_code == 200
        assert dub.json()["dub"]["name"] == "Dub · Samantha"
        assert "message" not in dub.json()["dub"]


def test_requirements_do_not_ship_kokoro() -> None:
    text = (Path(__file__).resolve().parent.parent / "requirements-duck.txt").read_text(encoding="utf-8")
    assert "kokoro" not in text.lower()
