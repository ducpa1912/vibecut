"""Phase B 1b: Check can be cancelled, queued or running."""

from __future__ import annotations

from concurrent.futures import Future

from fastapi.testclient import TestClient

import app
import job_queue
import pipeline
import routes_check
from test_detect import check_env, inline_check, sample_payload, subtitle_rows  # noqa: F401


def _cancelling_sampler(job_id, seen):
    def sampler(path, job_dir, duration, *, fps, max_frames, progress):
        routes_check.CHECK_CANCELS[job_id].set()
        # The worker binds the event to its thread, so the frame reader's own
        # checkpoints (pipeline._check_cancel) see it too.
        seen.append(pipeline.cancel_requested())
        progress(0.5, "Reading text · frame 5 / 10")
        return sample_payload(subtitle_rows(4))

    return sampler


def test_running_check_stops_and_saves_no_report(check_env, inline_check, monkeypatch):
    seen = []
    monkeypatch.setattr(pipeline, "read_text_samples", _cancelling_sampler(check_env.job_id, seen))
    monkeypatch.setattr(pipeline, "extract_audio", lambda *args, **kwargs: None)
    client = TestClient(app.app)

    started = client.post(f"/api/jobs/{check_env.job_id}/check", json={})
    assert started.json()["status"] == "cancelled"
    assert seen == [True]
    assert not pipeline.cancel_requested()
    assert not (check_env.directory / "check" / "source_report.json").exists()
    assert app.load_job(check_env.job_id)["check"]["status"] == "cancelled"
    fetched = client.get(f"/api/jobs/{check_env.job_id}/check")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "cancelled"
    assert fetched.json()["complete"] is False


def test_cancelled_rerun_keeps_the_last_finished_report(check_env, inline_check, monkeypatch):
    monkeypatch.setattr(pipeline, "read_text_samples", lambda *args, **kwargs: sample_payload(subtitle_rows(4)))
    monkeypatch.setattr(pipeline, "extract_audio", lambda *args, **kwargs: None)
    client = TestClient(app.app)
    first = client.post(f"/api/jobs/{check_env.job_id}/check", json={}).json()
    assert first["status"] == "ready"

    monkeypatch.setattr(pipeline, "read_text_samples", _cancelling_sampler(check_env.job_id, []))
    client.post(f"/api/jobs/{check_env.job_id}/check", json={"force": True})
    record = app.load_job(check_env.job_id)["check"]
    assert record["status"] == "ready"
    assert record["message"] == "Cancelled · showing the last Check"
    assert client.get(f"/api/jobs/{check_env.job_id}/check").json() == first


class ParkedExecutor:
    """Accept work and never run it, so the task stays queued."""

    def submit(self, fn, *args, **kwargs):
        return Future()

    def shutdown(self, *args, **kwargs):
        return None


def test_queued_check_is_dropped_at_once(check_env, monkeypatch):
    scheduler = job_queue.Scheduler("check-parked", executor=ParkedExecutor())
    monkeypatch.setattr(routes_check, "CHECK_POOL", scheduler)
    client = TestClient(app.app)

    started = client.post(f"/api/jobs/{check_env.job_id}/check", json={})
    assert started.status_code == 202
    task_id = app.load_job(check_env.job_id)["check"]["task_id"]

    cancelled = client.post(f"/api/jobs/{check_env.job_id}/check/cancel")
    assert cancelled.json() == {"ok": True, "cancelled": True, "status": "cancelled"}
    assert scheduler.get(task_id).state is job_queue.QueueState.CANCELLED
    assert client.get(f"/api/jobs/{check_env.job_id}/check").json()["status"] == "cancelled"
    # A new Run Check starts fresh instead of waiting on the dropped task.
    assert client.post(f"/api/jobs/{check_env.job_id}/check", json={}).status_code == 202
    assert not routes_check.CHECK_CANCELS[check_env.job_id].is_set()


def test_running_check_cancel_says_stopping(check_env, monkeypatch):
    class Running:
        terminal = False
        state = job_queue.QueueState.RUNNING

    monkeypatch.setattr(routes_check.CHECK_POOL, "get", lambda task_id: Running())
    routes_check._set_check(check_env.job_id, app, status="running", task_id="t1", progress=0.3)
    client = TestClient(app.app)
    reply = client.post(f"/api/jobs/{check_env.job_id}/check/cancel")
    assert reply.json() == {"ok": True, "cancelled": True, "status": "running"}
    assert app.load_job(check_env.job_id)["check"]["message"] == "Stopping…"
    assert routes_check.CHECK_CANCELS[check_env.job_id].is_set()


def test_cancel_without_a_running_check_changes_nothing(check_env):
    client = TestClient(app.app)
    reply = client.post(f"/api/jobs/{check_env.job_id}/check/cancel")
    assert reply.json()["cancelled"] is False
    refused = client.post(
        f"/api/jobs/{check_env.job_id}/check/cancel", headers={"sec-fetch-site": "cross-site"},
    )
    assert refused.status_code == 403
