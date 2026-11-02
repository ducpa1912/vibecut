"""The Classic voice sample says whether it reused the cache."""

from __future__ import annotations

from fastapi.testclient import TestClient

import app
import audio


def test_voice_sample_reports_a_cache_hit(monkeypatch, tmp_path):
    target = tmp_path / "voice.wav"
    target.write_bytes(b"x" * 1024)
    monkeypatch.setattr(app, "load_job", lambda job_id: {})
    monkeypatch.setattr(audio, "voice_sample_target", lambda *args, **kwargs: target)
    monkeypatch.setattr(audio, "voice_sample", lambda *args, **kwargs: target)

    response = TestClient(app.app).post(
        "/api/jobs/j1/voice/sample",
        json={"engine": "say", "voice": "Samantha", "text": "hello"},
    )

    assert response.status_code == 200
    assert response.headers["X-VibeCut-Preview"] == "cached"


def test_voice_sample_reports_a_new_call(monkeypatch, tmp_path):
    target = tmp_path / "missing.wav"
    target.write_bytes(b"x")
    monkeypatch.setattr(app, "load_job", lambda job_id: {})
    monkeypatch.setattr(audio, "voice_sample_target", lambda *args, **kwargs: target)
    monkeypatch.setattr(audio, "voice_sample", lambda *args, **kwargs: target)

    response = TestClient(app.app).post(
        "/api/jobs/j1/voice/sample",
        json={"engine": "say", "voice": "Samantha", "text": "hello"},
    )

    assert response.status_code == 200
    assert response.headers["X-VibeCut-Preview"] == "new"
