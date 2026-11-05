"""Cancel reading frees the single analysis slot (QA #10)."""

from __future__ import annotations

import json
import sys
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app
import job_queue
import stt


class FakePool:
    def __init__(self, state=None):
        self.state = state
        self.cancelled: list[str] = []
        self.submitted: list[tuple] = []

    def find_key(self, kind, key):
        return None if self.state is None else SimpleNamespace(state=self.state)

    def cancel_key(self, kind, key):
        self.cancelled.append(key)

    def submit(self, fn, *args, **kwargs):
        self.submitted.append((fn, args))


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    jobs = data / "jobs"
    jobs.mkdir(parents=True)
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.delenv("VIBECUT_TOKEN", raising=False)
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"x")

    def write(status: str, path=source) -> None:
        directory = jobs / "j1"
        directory.mkdir(exist_ok=True)
        (directory / "job.json").write_text(json.dumps({
            "id": "j1", "status": status, "progress": 0.4, "message": "Reading",
            "error": None, "source": {"path": str(path), "name": "clip.mp4"},
            "options": {}, "analysis": None, "renders": {},
        }))

    app.ANALYSIS_CANCELS.pop("j1", None)
    yield SimpleNamespace(client=TestClient(app.app), write=write, source=source)
    app.ANALYSIS_CANCELS.pop("j1", None)


def test_cancel_drops_a_queued_read_at_once(env, monkeypatch):
    pool = FakePool(job_queue.QueueState.QUEUED)
    monkeypatch.setattr(app, "analysis_pool", pool)
    env.write("queued")
    response = env.client.post("/api/jobs/j1/reading/cancel")
    assert response.status_code == 200, response.text
    assert response.json()["cancelled"] is True
    assert pool.cancelled == ["j1"]
    assert app.load_job("j1")["status"] == "cancelled"


def test_cancel_signals_a_running_read(env, monkeypatch):
    pool = FakePool(job_queue.QueueState.RUNNING)
    monkeypatch.setattr(app, "analysis_pool", pool)
    env.write("reading")
    response = env.client.post("/api/jobs/j1/reading/cancel")
    assert response.status_code == 200
    assert pool.cancelled == []
    assert app.ANALYSIS_CANCELS["j1"].is_set()
    job = app.load_job("j1")
    assert job["status"] == "reading" and job["message"] == "Stopping…"


def test_cancel_is_a_no_op_for_a_ready_video(env, monkeypatch):
    monkeypatch.setattr(app, "analysis_pool", FakePool())
    env.write("ready")
    assert env.client.post("/api/jobs/j1/reading/cancel").json()["cancelled"] is False


def test_retry_queues_a_stopped_read(env, monkeypatch):
    pool = FakePool()
    monkeypatch.setattr(app, "analysis_pool", pool)
    env.write("cancelled")
    response = env.client.post("/api/jobs/j1/reading/retry")
    assert response.status_code == 200, response.text
    assert app.load_job("j1")["status"] == "queued"
    assert pool.submitted and pool.submitted[0][1] == ("j1",)

    env.write("reading")
    assert env.client.post("/api/jobs/j1/reading/retry").status_code == 409


def test_retry_refuses_a_moved_source(env, monkeypatch):
    monkeypatch.setattr(app, "analysis_pool", FakePool())
    env.write("failed", path=env.source.parent / "gone.mp4")
    response = env.client.post("/api/jobs/j1/reading/retry")
    assert response.status_code == 409
    assert "moved or deleted" in response.json()["detail"]


def test_run_analysis_reports_a_cancelled_speech_engine(env, monkeypatch):
    env.write("queued")

    def analyze(*args, **kwargs):
        raise stt.SttCancelled("Speech-to-text cancelled.")

    monkeypatch.setattr(app.pipeline, "analyze_source", analyze)
    app.run_analysis("j1")
    job = app.load_job("j1")
    assert job["status"] == "cancelled" and job["error"] is None


def test_analysis_progress_keeps_a_concurrent_source_edit(env, monkeypatch):
    env.write("queued")
    app.update_job("j1", lambda job: job.update({
        "clean_source": {"keep": True, "stage": 0},
        "usage": [{"action": "existing"}],
    }))
    monkeypatch.setattr(
        app.usage_store, "delta",
        lambda before: {
            "calls": 1, "input_tokens": 2, "output_tokens": 3,
            "chars": 0, "audio_seconds": 0.0, "cost_usd": 0.0,
        },
    )

    def analyze(path, source, job_dir, options, progress):
        progress("scanning", 0.2, "Scanning")
        app.update_job("j1", lambda job: job.update({
            "clean_source": {"keep": True, "stage": 1},
        }))
        progress("reading", 0.5, "Reading")
        app.update_job("j1", lambda job: job.update({
            "classic_text": {"sentinel": True},
        }))
        return {"scene_count": 1, "elapsed": 0.2}

    monkeypatch.setattr(app.pipeline, "analyze_source", analyze)
    app.run_analysis("j1")

    job = app.load_job("j1")
    assert job["status"] == "ready"
    assert job["analysis"] == {"scene_count": 1, "elapsed": 0.2}
    assert job["clean_source"] == {"keep": True, "stage": 1}
    assert job["classic_text"] == {"sentinel": True}
    assert job["usage"][0] == {"action": "existing"}
    assert job["usage"][-1]["action"] == "analysis"


def test_a_cancelled_analysis_keeps_a_concurrent_source_edit(env, monkeypatch):
    env.write("queued")

    def analyze(path, source, job_dir, options, progress):
        progress("scanning", 0.2, "Scanning")
        app.update_job("j1", lambda job: job.update({
            "clean_source": {"keep": True},
        }))
        raise app.AnalysisCancelled("stop")

    monkeypatch.setattr(app.pipeline, "analyze_source", analyze)
    app.run_analysis("j1")

    job = app.load_job("j1")
    assert job["status"] == "cancelled"
    assert job["clean_source"] == {"keep": True}


def test_a_failed_analysis_keeps_a_concurrent_source_edit(env, monkeypatch):
    env.write("queued")

    def analyze(path, source, job_dir, options, progress):
        progress("scanning", 0.2, "Scanning")
        app.update_job("j1", lambda job: job.update({
            "clean_source": {"keep": True},
        }))
        raise RuntimeError("analysis broke")

    monkeypatch.setattr(app.pipeline, "analyze_source", analyze)
    app.run_analysis("j1")

    job = app.load_job("j1")
    assert job["status"] == "failed"
    assert job["clean_source"] == {"keep": True}


def test_child_run_stops_when_the_read_is_cancelled():
    event = threading.Event()
    stt.set_cancel_event(event)
    try:
        timer = threading.Timer(0.3, event.set)
        timer.start()
        started = time.monotonic()
        with pytest.raises(stt.SttCancelled):
            stt._child_run(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                stdout=None, stderr=None, timeout=60,
            )
        assert time.monotonic() - started < 5
    finally:
        stt.set_cancel_event(None)


def test_child_run_without_an_event_is_plain_subprocess_run(monkeypatch):
    calls = []
    monkeypatch.setattr(
        stt.subprocess, "run",
        lambda cmd, **kwargs: calls.append(kwargs) or SimpleNamespace(returncode=0),
    )
    stt.set_cancel_event(None)
    stt._child_run(["true"], stdout=None, stderr=None, timeout=5)
    assert calls and calls[0]["timeout"] == 5
