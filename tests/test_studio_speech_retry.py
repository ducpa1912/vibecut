"""Phase B 1a: one speech-only retry, ``pipeline.retry_speech`` on the voice queue."""

import re
from pathlib import Path

from fastapi.testclient import TestClient

import pipeline
import stt

ROOT = Path(__file__).resolve().parents[1]


def _ready_job(app, job_id, tmp_path, *, name="clip.mp4"):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    job = {
        "id": job_id, "status": "ready", "created": 1.0, "options": {"speech_language": "en"},
        "source": {"path": str(source), "name": name, "duration": 30.0, "has_audio": True},
        "analysis": {
            "scenes": [{"id": 0, "start": 0.0, "end": 30.0}],
            "plans": [{"id": "keep-me"}],
            "transcript": None,
            "engine": {"vision": True},
        },
    }
    app.save_job(job)
    return job


def test_the_retry_route_lives_in_routes_studio_only():
    app_text = (ROOT / "app.py").read_text(encoding="utf-8")
    assert '"/api/jobs/{job_id}/transcribe"' not in app_text
    studio = (ROOT / "routes_studio.py").read_text(encoding="utf-8")
    assert len(re.findall(r'"/api/jobs/\{job_id\}/transcribe"', studio)) == 1
    assert "pipeline.retry_speech(" in studio


def test_retry_route_runs_pipeline_retry_speech_and_keeps_the_rest(tmp_path, monkeypatch):
    import app

    _ready_job(app, "retryspeech1", tmp_path)
    monkeypatch.setattr(stt, "_engine_ready", lambda provider, model: provider == "openrouter")
    calls = []

    def fake_retry(job, job_dir, options=None, progress=None):
        calls.append((job["id"], dict(options or {})))
        scenes = [dict(job["analysis"]["scenes"][0], speech="hello there")]
        return {
            "ok": True,
            "transcript": {"language": "en", "text": "hello there", "segments": 2, "no_speech": False},
            "scenes": scenes,
            "engine": {"whisper": True, "transcript_provider": "openrouter", "stt_language": "auto"},
            "reason": "",
        }

    monkeypatch.setattr(pipeline, "retry_speech", fake_retry)
    response = TestClient(app.app).post("/api/jobs/retryspeech1/transcribe", json={})
    assert response.status_code == 200, response.text
    assert response.json() == {"segments": 2, "language": "en", "provider": "openrouter", "no_speech": False}
    assert calls == [("retryspeech1", {})]
    saved = app.load_job("retryspeech1")
    assert saved["analysis"]["scenes"][0]["speech"] == "hello there"
    assert saved["analysis"]["transcript"]["segments"] == 2
    assert saved["analysis"]["engine"] == {
        "vision": True, "whisper": True, "transcript_provider": "openrouter", "stt_language": "auto",
    }
    assert saved["analysis"]["plans"] == [{"id": "keep-me"}]
    assert saved["options"]["transcribe"] is True


def test_retry_route_passes_a_chosen_language_as_explicit(tmp_path, monkeypatch):
    import app

    _ready_job(app, "retryspeech2", tmp_path)
    monkeypatch.setattr(stt, "_engine_ready", lambda provider, model: True)
    seen = {}

    def fake_retry(job, job_dir, options=None, progress=None):
        seen.update(options or {})
        return {"ok": False, "transcript": None, "scenes": [], "reason": "x",
                "engine": {"stt_attempted": True}}

    monkeypatch.setattr(pipeline, "retry_speech", fake_retry)
    response = TestClient(app.app).post("/api/jobs/retryspeech2/transcribe", json={"language": "VI"})
    assert seen == {"speech_language": "vi", "speech_language_explicit": "vi"}
    assert response.status_code == 502
    assert app.load_job("retryspeech2")["analysis"]["transcript"] is None


def test_retry_speech_guesses_the_language_from_the_title(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    wav = tmp_path / "audio.wav"
    wav.write_bytes(b"RIFF")
    job = {
        "id": "j2",
        "source": {"path": str(source), "name": "東京の旅.mp4", "duration": 5.0, "has_audio": True},
        "options": {"speech_language": "en"},
        "analysis": {"scenes": [{"id": 0, "start": 0.0, "end": 5.0}]},
    }
    seen = {}
    monkeypatch.setattr(pipeline, "extract_audio", lambda *args: wav)

    def fake_transcribe(*args, **kwargs):
        seen["language"] = kwargs["language"]
        return None

    monkeypatch.setattr(stt, "transcribe_source", fake_transcribe)
    pipeline.retry_speech(job, tmp_path)
    assert seen["language"] == "ja"
    job["options"]["speech_language_explicit"] = "en"
    pipeline.retry_speech(job, tmp_path)
    assert seen["language"] == "en"
