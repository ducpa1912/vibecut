"""Plain-language import errors and speech copy (QA #23)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app
import detect
import pipeline


@pytest.fixture
def client(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "jobs").mkdir(parents=True)
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", data / "jobs")
    monkeypatch.delenv("VIBECUT_TOKEN", raising=False)
    return TestClient(app.app)


def test_folder_path_says_it_is_a_folder(client, tmp_path):
    response = client.post("/api/jobs/path", json={"path": str(tmp_path)})
    assert response.status_code == 400
    assert response.json()["detail"] == "That path is a folder; choose a video file."


def test_unreadable_file_hides_ffprobe_output(client, tmp_path, monkeypatch):
    fake = tmp_path / "fake.mp4"
    fake.write_text("not a video")

    def probe(path):
        raise pipeline.PipelineError(
            "command failed: ffprobe\n[mov,mp4 @ 0xb85] moov atom not found\nInvalid data",
        )

    monkeypatch.setattr(app.pipeline, "probe", probe)
    response = client.post("/api/jobs/path", json={"path": str(fake)})
    assert response.status_code == 400
    assert response.json()["detail"] == app.UNREADABLE_VIDEO
    plain = client.post("/api/inspect", json={"path": str(tmp_path / "missing.mp4")})
    assert plain.status_code == 404


def _codes(audio: dict) -> list[str]:
    rows = detect._report_warnings(
        [], audio=audio, quality={"issues": []}, text={"confirmed": True},
        attested=True, sampled_error=None, truncated=False,
    )
    return [item["code"] for item in rows]


def test_no_audio_and_no_speech_are_not_called_unknown():
    assert "no_audio" in _codes({"has_audio": False, "transcript": False})
    assert "no_speech" in _codes({"has_audio": True, "transcript": False, "no_speech": True})
    unknown = _codes({"has_audio": True, "transcript": False})
    assert "speech_unknown" in unknown
