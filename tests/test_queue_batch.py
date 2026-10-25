"""Queue, batch, retry and disk-preflight behaviour."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app
import batch
import disk
import queue as job_queue
import routes_batches

GIB = 1024 ** 3


class CapturePool:
    def __init__(self) -> None:
        self.calls = []

    def submit(self, fn, *args, **kwargs):
        self.calls.append((fn, args, kwargs))
        return None


def _usage(total: int, free: int):
    return (total, total - free, free)


@pytest.fixture
def data_env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    jobs = data / "jobs"
    sources = data / "sources"
    jobs.mkdir(parents=True)
    sources.mkdir(parents=True)
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.setattr(app, "SOURCES", sources)
    monkeypatch.setattr(disk, "usage", lambda path: _usage(100 * GIB, 90 * GIB))
    batch.clear_managers()
    yield data
    batch.clear_managers()


def _wait(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    raise AssertionError("timed out waiting for condition")


def write_job(jobs: Path, job_id: str, **overrides) -> Path:
    now = time.time()
    job = {
        "id": job_id,
        "created": now,
        "updated": now,
        "status": "ready",
        "progress": 1.0,
        "message": "Ready",
        "error": None,
        "source": {"path": None, "name": "clip.mp4", "duration": 12.0},
        "options": {},
        "analysis": {"scene_count": 1, "scenes": [], "hook_scene": None},
        "renders": {},
        "ingest": {},
    }
    job.update(overrides)
    directory = jobs / job_id
    directory.mkdir(parents=True)
    (directory / "job.json").write_text(json.dumps(job), encoding="utf-8")
    return directory


class FakeBackend:
    def __init__(self, *, fail_labels: set[str] | None = None) -> None:
        self.fail_labels = fail_labels or set()
        self.created: list[str] = []
        self.jobs: dict[str, dict] = {}
        self.retried: list[str] = []
        self.cancelled: list[str] = []

    def create_job(self, item: dict) -> dict:
        label = str(item.get("path") or item.get("url") or "")
        self.created.append(label)
        if label in self.fail_labels:
            raise RuntimeError("item exploded")
        job_id = f"job{len(self.jobs) + 1}"
        job = {
            "id": job_id,
            "status": "ready",
            "error": None,
            "analysis": {"scene_count": 1, "scenes": [], "hook_scene": None},
            "renders": {},
        }
        self.jobs[job_id] = job
        return dict(job)

    def load_job(self, job_id: str) -> dict:
        return dict(self.jobs[job_id])

    def retry_job(self, job_id: str) -> dict:
        self.retried.append(job_id)
        job = self.jobs[job_id]
        job["status"] = "ready"
        job["error"] = None
        return dict(job)

    def cancel_job(self, job_id: str) -> None:
        self.cancelled.append(job_id)

    def start_renders(self, job_id: str, targets: list[int], options: dict) -> list[dict]:
        job = self.jobs[job_id]
        records = []
        for target in targets:
            record = {
                "status": "ready",
                "target": target,
                "quality": options.get("quality") or "final",
                "aspect": options.get("aspect") or "9:16",
                "captions": bool(options.get("captions")),
                "path": f"reel_{target}.mp4",
                "key": f"k{target}",
                "duration": target,
            }
            job.setdefault("renders", {})[f"r{target}"] = record
            records.append(record)
        return records

    def render_states(self, job_id: str, targets: list[int], options: dict) -> dict[int, str]:
        job = self.jobs[job_id]
        return {
            target: "ready"
            for target in targets
            if any(
                int(record.get("target") or 0) == target
                for record in (job.get("renders") or {}).values()
            )
        }


# ---------------------------------------------------------------- queue


def test_scheduler_states_retry_handle_and_idempotence():
    scheduler = job_queue.Scheduler("test", max_workers=1)
    gate = threading.Event()
    first = scheduler.submit(
        lambda: gate.wait(2),
        task_kind="analysis",
        task_key="first",
    )
    second = scheduler.submit(lambda: "second")
    _wait(lambda: first.state is job_queue.QueueState.RUNNING and second.state is job_queue.QueueState.QUEUED)
    gate.set()
    assert first.wait(2)
    assert second.wait(2)
    assert first.state is job_queue.QueueState.DONE

    def boom():
        raise RuntimeError("boom")

    failed = scheduler.submit(boom, task_kind="render", task_key="boom")
    assert failed.wait(2)
    assert failed.state is job_queue.QueueState.FAILED
    assert failed.attempts == 1
    assert failed.retry_handle.available is True

    retry_one = failed.retry()
    retry_two = failed.retry()
    assert retry_one.id == retry_two.id
    assert retry_one.retry_of == failed.id
    assert retry_one.wait(2)
    assert retry_one.state is job_queue.QueueState.FAILED
    assert retry_one.attempts == 2
    assert scheduler.stats()["states"]["failed"] == 2


def test_scheduler_preserves_single_worker_order():
    scheduler = job_queue.Scheduler("order", max_workers=1)
    seen: list[int] = []
    gate = threading.Event()

    def first():
        gate.wait(2)
        seen.append(1)

    scheduler.submit(first)
    scheduler.submit(lambda: seen.append(2))
    _wait(lambda: len(seen) == 0)
    time.sleep(0.05)
    assert seen == []
    gate.set()
    _wait(lambda: len(seen) == 2)
    assert seen == [1, 2]


# ---------------------------------------------------------------- batch


def test_batch_rejects_more_than_ten_items(data_env, monkeypatch):
    backend = FakeBackend()
    monkeypatch.setattr(routes_batches, "_backend", lambda: backend)
    with TestClient(app.app) as client:
        response = client.post(
            "/api/batches",
            json={
                "name": "too many",
                "items": [{"path": f"/tmp/item-{index}.mp4"} for index in range(11)],
                "max": 10,
            },
        )
    assert response.status_code == 400
    assert "at most 10" in response.json()["detail"]


def test_batch_accepts_exactly_ten_items(data_env, monkeypatch):
    backend = FakeBackend()
    monkeypatch.setattr(routes_batches, "_backend", lambda: backend)
    with TestClient(app.app) as client:
        response = client.post(
            "/api/batches",
            json={
                "name": "ten",
                "items": [{"path": f"/tmp/item-{index}.mp4"} for index in range(10)],
                "max": 10,
            },
        )
        assert response.status_code == 200, response.text
        batch_id = response.json()["id"]
        value = _wait(
            lambda: (
                client.get(f"/api/batches/{batch_id}").json()
                if client.get(f"/api/batches/{batch_id}").json()["status"] == "done"
                else None
            )
        )
    assert len(value["items"]) == 10
    assert all(item["state"] == "done" for item in value["items"])
    assert len(backend.created) == 10


def test_batch_sequential_order_and_failure_isolation(data_env, monkeypatch):
    backend = FakeBackend(fail_labels={"/tmp/bad.mp4"})
    monkeypatch.setattr(routes_batches, "_backend", lambda: backend)
    with TestClient(app.app) as client:
        response = client.post(
            "/api/batches",
            json={
                "name": "ordered",
                "items": [
                    {"path": "/tmp/one.mp4"},
                    {"path": "/tmp/bad.mp4"},
                    {"path": "/tmp/two.mp4"},
                ],
                "max": 10,
            },
        )
        assert response.status_code == 200
        batch_id = response.json()["id"]
        value = _wait(
            lambda: (
                client.get(f"/api/batches/{batch_id}").json()
                if client.get(f"/api/batches/{batch_id}").json()["status"] == "done"
                else None
            )
        )

    assert backend.created == ["/tmp/one.mp4", "/tmp/bad.mp4", "/tmp/two.mp4"]
    assert [item["state"] for item in value["items"]] == ["done", "failed", "done"]
    assert [item["attempts"] for item in value["items"]] == [1, 1, 1]
    assert "exploded" in value["items"][1]["error"]
    assert value["counts"]["done"] == 2
    assert value["counts"]["failed"] == 1


def test_batch_api_uses_real_path_backend(data_env, monkeypatch):
    source = data_env / "real.mp4"
    source.write_bytes(b"x" * 16)
    monkeypatch.setattr(
        app.pipeline,
        "probe",
        lambda path: {
            "duration": 12.0,
            "width": 1080,
            "height": 1920,
            "fps": 30.0,
            "has_audio": True,
            "size": 16,
        },
    )

    def fake_analysis(job_id: str) -> None:
        job = app.load_job(job_id)
        job["status"] = "ready"
        job["progress"] = 1.0
        job["message"] = "Ready"
        job["analysis"] = {"scene_count": 0, "scenes": [], "hook_scene": None}
        app.save_job(job)

    monkeypatch.setattr(app, "run_analysis", fake_analysis)
    with TestClient(app.app) as client:
        response = client.post(
            "/api/batches",
            json={"name": "real", "items": [{"path": str(source)}], "max": 10},
        )
        assert response.status_code == 200, response.text
        batch_id = response.json()["id"]
        value = _wait(
            lambda: (
                client.get(f"/api/batches/{batch_id}").json()
                if client.get(f"/api/batches/{batch_id}").json()["status"] == "done"
                else None
            )
        )
        job_id = value["items"][0]["job_id"]
        job = client.get(f"/api/jobs/{job_id}").json()

    assert value["items"][0]["state"] == "done"
    assert job_id
    assert job["status"] == "ready"


def test_batch_resume_keeps_done_outputs_and_retries_interrupted(tmp_path):
    backend = FakeBackend()
    backend.jobs["existing"] = {
        "id": "existing",
        "status": "interrupted",
        "error": "restart",
        "analysis": None,
        "renders": {},
    }
    manager = batch.BatchManager(tmp_path, backend=backend, poll_interval=0.01)
    created = manager.create(
        "restart",
        [{"path": "/tmp/a.mp4"}, {"path": "/tmp/b.mp4"}],
        start=False,
    )
    manifest = manager.load(created["id"])
    manifest["status"] = "running"
    manifest["items"][0].update({
        "state": "done",
        "job_id": "donejob",
        "outputs": [{"target": 30, "path": "keep.mp4", "key": "keep"}],
    })
    manifest["items"][1].update({"state": "running", "job_id": "existing"})
    manager.save(manifest)

    assert batch.recover_batches(tmp_path) == 1
    paused = manager.load(created["id"])
    assert paused["status"] == "paused"
    assert paused["items"][0]["state"] == "done"
    assert paused["items"][0]["outputs"][0]["path"] == "keep.mp4"
    assert paused["items"][1]["state"] == "paused"

    manager.resume(created["id"])
    final = _wait(
        lambda: (
            manager.get(created["id"])
            if manager.get(created["id"])["status"] == "done"
            else None
        )
    )
    assert final["items"][0]["outputs"][0]["path"] == "keep.mp4"
    assert final["items"][1]["state"] == "done"
    assert backend.retried == ["existing"]


def test_batch_render_targets_are_preserved(tmp_path):
    backend = FakeBackend()
    manager = batch.BatchManager(tmp_path, backend=backend, poll_interval=0.01)
    created = manager.create(
        "renders",
        [{"path": "/tmp/a.mp4", "options": {"targets": [30, 15], "quality": "draft"}}],
        start=True,
    )
    final = _wait(
        lambda: (
            manager.get(created["id"])
            if manager.get(created["id"])["status"] == "done"
            else None
        )
    )
    assert final["items"][0]["targets"] == [15, 30]
    assert [item["target"] for item in final["items"][0]["outputs"]] == [15, 30]


# ---------------------------------------------------------------- restart


def test_recover_marks_analysis_and_render_interrupted_and_pauses_batch(
    data_env, monkeypatch
):
    data = data_env
    write_job(
        app.JOBS,
        "live1",
        status="scanning",
        analysis=None,
        renders={
            "30:final": {
                "status": "rendering",
                "target": 30,
                "quality": "final",
                "aspect": "9:16",
                "captions": False,
                "key": "k",
            }
        },
    )
    manager = batch.BatchManager(data)
    created = manager.create("active", [{"path": "/tmp/a.mp4"}], start=False)
    manifest = manager.load(created["id"])
    manifest["status"] = "running"
    manifest["items"][0]["state"] = "running"
    manager.save(manifest)

    app.recover_jobs()

    job = json.loads((app.JOBS / "live1" / "job.json").read_text())
    assert job["status"] == "interrupted"
    assert job["renders"]["30:final"]["status"] == "interrupted"
    recovered = manager.get(created["id"])
    assert recovered["status"] == "paused"
    assert recovered["items"][0]["state"] == "paused"


# ---------------------------------------------------------------- retry API


def test_job_retry_is_idempotent(data_env, monkeypatch):
    source = data_env / "source.mp4"
    source.write_bytes(b"not a real video")
    write_job(
        app.JOBS,
        "retryme",
        status="interrupted",
        analysis=None,
        source={"path": str(source), "name": "source.mp4"},
    )
    cap = CapturePool()
    monkeypatch.setattr(app, "analysis_pool", cap)
    with TestClient(app.app) as client:
        first = client.post("/api/jobs/retryme/retry")
        second = client.post("/api/jobs/retryme/retry")
    assert first.status_code == 200
    assert first.json()["retried"] is True
    assert first.json()["retry"]["analysis"] is True
    assert second.status_code == 200
    assert second.json()["retried"] is False
    assert len(cap.calls) == 1
    assert cap.calls[0][0] is app.run_analysis
    assert cap.calls[0][1][0] == "retryme"


def test_legacy_job_loads_without_new_fields(data_env):
    directory = app.JOBS / "legacy"
    directory.mkdir()
    (directory / "job.json").write_text(json.dumps({
        "id": "legacy",
        "created": 1,
        "updated": 1,
        "status": "ready",
        "source": {"name": "old.mp4"},
    }), encoding="utf-8")
    with TestClient(app.app) as client:
        response = client.get("/api/jobs/legacy")
    assert response.status_code == 200
    value = response.json()
    assert value["id"] == "legacy"
    assert value["renders"] == {}


# ---------------------------------------------------------------- disk


def test_disk_preflight_reserve_and_payload():
    report = disk.report(1 * GIB, "/tmp")
    assert report["reserve_bytes"] >= 5 * GIB
    with pytest.raises(disk.InsufficientSpace) as caught:
        disk.preflight(10 ** 15, "/tmp")
    payload = caught.value.as_dict()
    assert payload["code"] == "insufficient_space"
    assert payload["required_bytes"] == 10 ** 15
    assert payload["free_bytes"] > 0


def test_path_upload_batch_and_render_return_412(data_env, monkeypatch):
    monkeypatch.setattr(disk, "usage", lambda path: _usage(100 * GIB, 5 * GIB + 10 ** 7))
    source = data_env / "small.mp4"
    source.write_bytes(b"x" * 16)
    with TestClient(app.app) as client:
        path_response = client.post("/api/jobs/path", json={"path": str(source)})
        upload_response = client.post(
            "/api/jobs/upload",
            files={"file": ("small.mp4", b"x" * 16, "video/mp4")},
        )
        batch_response = client.post(
            "/api/batches",
            json={"name": "full", "items": [{"path": str(source)}], "max": 10},
        )

        write_job(app.JOBS, "render-me", source={"path": str(source), "name": "small.mp4"})
        original_plan = app._plan_for_body
        monkeypatch.setattr(
            app,
            "_plan_for_body",
            lambda job, target, body: {
                "target": target,
                "total": target,
                "hook_scene": None,
                "auto": True,
                "clips": [],
            },
        )
        render_response = client.post("/api/jobs/render-me/render", json={"target": 30})
        monkeypatch.setattr(app, "_plan_for_body", original_plan)

    for response in (path_response, upload_response, batch_response, render_response):
        assert response.status_code == 412, response.text
        body = response.json()
        assert body["code"] == "insufficient_space"
        assert body["required_bytes"] > 0
        assert body["free_bytes"] >= 0
