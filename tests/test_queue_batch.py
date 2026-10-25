"""Queue, batch, retry and disk-preflight behaviour."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app
import artifacts
import batch
import disk
import job_queue
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
            quality = options.get("quality") or "final"
            aspect = options.get("aspect") or "9:16"
            captions = bool(options.get("captions"))
            hook = options.get("hook_scene")
            preset = options.get("preset")
            record_key = f"{target}:{quality}:{aspect}:{int(captions)}:{hook}:{preset}"
            record = {
                "status": "ready",
                "target": target,
                "quality": quality,
                "aspect": aspect,
                "captions": captions,
                "audio_sig": "",
                "hook": hook,
                "preset": preset,
                "record_key": record_key,
                "path": f"reel_{record_key.replace(':', '_')}.mp4",
                "key": f"k{record_key}",
                "duration": target,
            }
            job.setdefault("renders", {})[record_key] = record
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


class BlockingBackend(FakeBackend):
    def __init__(self, block_label: str) -> None:
        super().__init__()
        self.block_label = block_label
        self.entered = threading.Event()
        self.release = threading.Event()

    def create_job(self, item: dict) -> dict:
        if str(item.get("path") or "") == self.block_label:
            self.entered.set()
            self.release.wait(3)
        return super().create_job(item)


class DeterministicBackend(FakeBackend):
    def __init__(self) -> None:
        super().__init__()
        self.seen_ids: list[str] = []
        self.fail_once = True

    def create_job(self, item: dict) -> dict:
        job_id = str(item.get("job_id") or "")
        self.seen_ids.append(job_id)
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("crashed before job creation")
        job = {
            "id": job_id,
            "status": "ready",
            "error": None,
            "analysis": {"scene_count": 1, "scenes": [], "hook_scene": None},
            "renders": {},
        }
        self.jobs[job_id] = job
        self.created.append(str(item.get("path") or item.get("url") or ""))
        return dict(job)


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


def test_scheduler_dedupes_active_kind_and_key():
    scheduler = job_queue.Scheduler("dedupe", max_workers=1)
    gate = threading.Event()
    first = scheduler.submit(
        lambda: gate.wait(2), task_kind="analysis", task_key="job-a",
    )
    _wait(lambda: first.state is job_queue.QueueState.RUNNING)
    second = scheduler.submit(
        lambda: "duplicate", task_kind="analysis", task_key="job-a",
    )
    assert second.id == first.id
    gate.set()
    assert first.wait(2)
    third = scheduler.submit(
        lambda: "fresh", task_kind="analysis", task_key="job-a",
    )
    assert third.id != first.id
    assert third.wait(2)


def test_scheduler_shutdown_marks_pending_work():
    scheduler = job_queue.Scheduler("shutdown", max_workers=1)
    gate = threading.Event()
    running = scheduler.submit(lambda: gate.wait(2), task_kind="render", task_key="run")
    _wait(lambda: running.state is job_queue.QueueState.RUNNING)
    queued = scheduler.submit(lambda: "never", task_kind="render", task_key="later")
    scheduler.shutdown(wait=False)
    assert running.state is job_queue.QueueState.INTERRUPTED
    assert queued.state is job_queue.QueueState.CANCELLED
    gate.set()


def test_scheduler_interrupted_task_does_not_block_same_key():
    scheduler = job_queue.Scheduler("interrupted", max_workers=1)
    gate = threading.Event()
    first = scheduler.submit(
        lambda: gate.wait(2), task_kind="analysis", task_key="job-a",
    )
    _wait(lambda: first.state is job_queue.QueueState.RUNNING)
    scheduler.interrupt_all("restart")
    assert first.state is job_queue.QueueState.INTERRUPTED
    replacement = scheduler.submit(
        lambda: "replacement", task_kind="analysis", task_key="job-a",
    )
    assert replacement.id != first.id
    assert replacement.state is job_queue.QueueState.QUEUED
    gate.set()
    assert replacement.wait(2)
    assert replacement.state is job_queue.QueueState.DONE


def test_scheduler_cancel_key_cancels_queued_work():
    scheduler = job_queue.Scheduler("cancel", max_workers=1)
    gate = threading.Event()
    running = scheduler.submit(lambda: gate.wait(2), task_kind="render", task_key="run")
    _wait(lambda: running.state is job_queue.QueueState.RUNNING)
    queued = scheduler.submit(lambda: "never", task_kind="render", task_key="queued")
    assert queued.state is job_queue.QueueState.QUEUED
    cancelled = scheduler.cancel_key("render", "queued")
    assert cancelled is queued
    assert queued.state is job_queue.QueueState.CANCELLED
    gate.set()
    assert running.wait(2)


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


def test_batch_rejects_invalid_max_values(tmp_path):
    manager = batch.BatchManager(tmp_path)
    for value in (0, 11, True, 1.5):
        with pytest.raises(batch.BatchError):
            manager.create("bad", [{"path": "/tmp/a.mp4"}], max_items=value)


def test_batch_corrupt_manifests_are_skipped(tmp_path):
    manager = batch.BatchManager(tmp_path)
    valid = manager.create("valid", [{"path": "/tmp/a.mp4"}], start=False)
    manifest = manager.load(valid["id"])
    manifest["status"] = "running"
    manifest["items"][0]["state"] = "running"
    manager.save(manifest)
    (tmp_path / "batches" / "bad.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "batches" / "invalid.json").write_text(
        json.dumps({"id": "invalid", "status": "running", "items": "nope"}),
        encoding="utf-8",
    )
    (tmp_path / "batches" / "item.json").write_text(
        json.dumps({"id": "item", "status": "running", "items": [None]}),
        encoding="utf-8",
    )

    listed = manager.list()
    assert [item["id"] for item in listed] == [valid["id"]]
    assert batch.recover_batches(tmp_path) == 1
    assert manager.get(valid["id"])["status"] == "paused"
    assert batch._counts({"items": [None]})["failed"] == 1
    with pytest.raises(batch.BatchError):
        manager.get("bad")


def test_batch_pause_stops_before_next_item(tmp_path):
    backend = BlockingBackend("/tmp/one.mp4")
    manager = batch.BatchManager(tmp_path, backend=backend, poll_interval=0.01)
    created = manager.create(
        "pause",
        [{"path": "/tmp/one.mp4"}, {"path": "/tmp/two.mp4"}],
        start=True,
    )
    assert backend.entered.wait(2)
    paused = manager.pause(created["id"])
    assert paused["status"] == "paused"
    backend.release.set()
    _wait(lambda: backend.created == ["/tmp/one.mp4"])
    time.sleep(0.1)
    assert backend.created == ["/tmp/one.mp4"]
    current = manager.get(created["id"])
    assert current["status"] == "paused"
    assert current["items"][0]["state"] == "done"
    assert current["items"][1]["state"] == "queued"
    manager.resume(created["id"])
    final = _wait(
        lambda: (
            manager.get(created["id"])
            if manager.get(created["id"])["status"] == "done"
            else None
        )
    )
    assert backend.created == ["/tmp/one.mp4", "/tmp/two.mp4"]
    assert all(item["state"] == "done" for item in final["items"])


def test_batch_pause_endpoint_stops_runner(data_env, monkeypatch):
    backend = BlockingBackend("/tmp/one.mp4")
    monkeypatch.setattr(routes_batches, "_backend", lambda: backend)
    with TestClient(app.app) as client:
        response = client.post(
            "/api/batches",
            json={
                "name": "pause api",
                "items": [{"path": "/tmp/one.mp4"}, {"path": "/tmp/two.mp4"}],
                "max": 10,
            },
        )
        assert response.status_code == 200
        batch_id = response.json()["id"]
        assert backend.entered.wait(2)
        paused = client.post(f"/api/batches/{batch_id}/pause")
        assert paused.status_code == 200
        assert paused.json()["status"] == "paused"
        backend.release.set()
        _wait(lambda: backend.created == ["/tmp/one.mp4"])
        time.sleep(0.1)
        current = client.get(f"/api/batches/{batch_id}").json()
        assert current["status"] == "paused"
        assert backend.created == ["/tmp/one.mp4"]
        resumed = client.post(f"/api/batches/{batch_id}/resume")
        assert resumed.status_code == 200
        _wait(
            lambda: (
                client.get(f"/api/batches/{batch_id}").json()["status"] == "done"
            )
        )


def test_batch_immediate_resume_after_pause_continues(data_env, monkeypatch):
    backend = BlockingBackend("/tmp/one.mp4")
    monkeypatch.setattr(routes_batches, "_backend", lambda: backend)
    with TestClient(app.app) as client:
        response = client.post(
            "/api/batches",
            json={
                "name": "pause resume race",
                "items": [{"path": "/tmp/one.mp4"}, {"path": "/tmp/two.mp4"}],
                "max": 10,
            },
        )
        assert response.status_code == 200
        batch_id = response.json()["id"]
        assert backend.entered.wait(2)
        paused = client.post(f"/api/batches/{batch_id}/pause")
        assert paused.json()["status"] == "paused"
        assert paused.json()["current"] is None
        resumed = client.post(f"/api/batches/{batch_id}/resume")
        assert resumed.status_code == 200
        assert resumed.json()["status"] in {"running", "queued"}
        backend.release.set()
        final = _wait(
            lambda: (
                client.get(f"/api/batches/{batch_id}").json()
                if client.get(f"/api/batches/{batch_id}").json()["status"] == "done"
                else None
            )
        )
    assert backend.created == ["/tmp/one.mp4", "/tmp/two.mp4"]
    assert all(item["state"] == "done" for item in final["items"])


def test_batch_deterministic_job_id_survives_create_crash(tmp_path):
    backend = DeterministicBackend()
    manager = batch.BatchManager(tmp_path, backend=backend, poll_interval=0.01)
    created = manager.create("crash", [{"path": "/tmp/a.mp4"}], start=True)
    failed = _wait(
        lambda: (
            manager.get(created["id"])
            if manager.get(created["id"])["status"] == "failed"
            else None
        )
    )
    item = failed["items"][0]
    assert item["state"] == "failed"
    first_id = item["job_id"]
    assert first_id
    manifest = manager.load(created["id"])
    manifest["items"][0]["state"] = "paused"
    manifest["status"] = "paused"
    manager.save(manifest)
    manager.resume(created["id"])
    final = _wait(
        lambda: (
            manager.get(created["id"])
            if manager.get(created["id"])["status"] == "done"
            else None
        )
    )
    assert final["items"][0]["job_id"] == first_id
    assert backend.seen_ids == [first_id, first_id]
    assert list(backend.jobs) == [first_id]


def test_batch_render_identity_prefers_requested_variant(tmp_path):
    backend = FakeBackend()
    final_key = "30:final:9:16:0:None:None"
    backend.jobs["variant"] = {
        "id": "variant",
        "status": "ready",
        "error": None,
        "analysis": {"scene_count": 1, "scenes": [], "hook_scene": None},
        "renders": {
            final_key: {
                "status": "ready",
                "target": 30,
                "quality": "final",
                "aspect": "9:16",
                "captions": False,
                "audio_sig": "",
                "hook": None,
                "preset": None,
                "record_key": final_key,
                "path": "final.mp4",
            }
        },
    }
    manager = batch.BatchManager(tmp_path, backend=backend, poll_interval=0.01)
    created = manager.create(
        "variant",
        [{"path": "/tmp/a.mp4", "options": {
            "targets": [30], "quality": "draft", "aspect": "9:16",
        }}],
        start=True,
    )
    final = _wait(
        lambda: (
            manager.get(created["id"])
            if manager.get(created["id"])["status"] == "done"
            else None
        )
    )
    outputs = final["items"][0]["outputs"]
    assert len(outputs) == 1
    assert outputs[0]["path"].startswith("reel_30_draft")


def test_batch_render_identity_prefers_requested_hook(tmp_path):
    backend = FakeBackend()
    key0 = "30:final:9:16:0:0:None"
    key1 = "30:final:9:16:0:1:None"
    base = {
        "status": "ready",
        "target": 30,
        "quality": "final",
        "aspect": "9:16",
        "captions": False,
        "audio_sig": "",
        "preset": None,
    }
    backend.jobs["hooks"] = {
        "id": "hooks",
        "status": "ready",
        "error": None,
        "analysis": {"scene_count": 2, "scenes": [], "hook_scene": 0},
        "renders": {
            key0: {**base, "hook": 0, "record_key": key0, "path": "hook0.mp4"},
            key1: {**base, "hook": 1, "record_key": key1, "path": "hook1.mp4"},
        },
    }
    manager = batch.BatchManager(tmp_path, backend=backend, poll_interval=0.01)
    created = manager.create(
        "hooks",
        [{"path": "/tmp/a.mp4", "options": {
            "targets": [30], "quality": "final", "hook_scene": 1,
        }}],
        start=True,
    )
    final = _wait(
        lambda: (
            manager.get(created["id"])
            if manager.get(created["id"])["status"] == "done"
            else None
        )
    )
    outputs = final["items"][0]["outputs"]
    assert len(outputs) == 1
    assert outputs[0]["path"] == "reel_30_final_9_16_0_1_None.mp4"
    assert outputs[0]["record_key"] == key1


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


def test_path_job_honors_requested_job_id(data_env, monkeypatch):
    source = data_env / "source.mp4"
    source.write_bytes(b"x")
    monkeypatch.setattr(
        app.pipeline, "probe",
        lambda path: {"duration": 12.0, "width": 1080, "height": 1920, "fps": 30.0},
    )
    monkeypatch.setattr(app, "analysis_pool", CapturePool())
    with TestClient(app.app) as client:
        first = client.post(
            "/api/jobs/path",
            json={"path": str(source), "job_id": "abcdef123456"},
        )
        second = client.post(
            "/api/jobs/path",
            json={"path": str(source), "job_id": "abcdef123456"},
        )
    assert first.status_code == 200
    assert first.json()["id"] == "abcdef123456"
    assert second.status_code == 409


def test_partial_deterministic_job_dir_is_reused(data_env, monkeypatch):
    source = data_env / "source.mp4"
    source.write_bytes(b"x")
    monkeypatch.setattr(
        app.pipeline, "probe",
        lambda path: {"duration": 12.0, "width": 1080, "height": 1920, "fps": 30.0},
    )
    monkeypatch.setattr(app, "analysis_pool", CapturePool())
    empty_id = "abc123abc123"
    (app.JOBS / empty_id).mkdir()
    temp_id = "def456def456"
    temp_dir = app.JOBS / temp_id
    temp_dir.mkdir()
    (temp_dir / ".job.deadbeef.tmp").write_text("{}", encoding="utf-8")
    blocked_id = "aaa111bbb222"
    blocked_dir = app.JOBS / blocked_id
    blocked_dir.mkdir()
    (blocked_dir / "unexpected.txt").write_text("keep", encoding="utf-8")
    with TestClient(app.app) as client:
        empty_response = client.post(
            "/api/jobs/path",
            json={"path": str(source), "job_id": empty_id},
        )
        temp_response = client.post(
            "/api/jobs/path",
            json={"path": str(source), "job_id": temp_id},
        )
        blocked_response = client.post(
            "/api/jobs/path",
            json={"path": str(source), "job_id": blocked_id},
        )
    assert empty_response.status_code == 200
    assert temp_response.status_code == 200
    assert blocked_response.status_code == 409
    assert (app.JOBS / empty_id / "job.json").is_file()
    assert (app.JOBS / temp_id / "job.json").is_file()
    assert not any((app.JOBS / temp_id).glob(".job.*.tmp"))
    assert (blocked_dir / "unexpected.txt").read_text() == "keep"


def test_analysis_cancel_event_stops_progress(data_env, monkeypatch):
    source = data_env / "source.mp4"
    source.write_bytes(b"x")
    write_job(
        app.JOBS,
        "analysis-cancel",
        status="scanning",
        analysis=None,
        source={"path": str(source), "name": "source.mp4"},
    )
    started = threading.Event()
    calls = {"count": 0}

    def slow_analysis(path, meta, job_dir, options, progress):
        started.set()
        for index in range(100):
            calls["count"] += 1
            progress("scanning", index / 100.0, "working")
            time.sleep(0.01)
        return {"scene_count": 0, "scenes": [], "hook_scene": None, "elapsed": 1}

    monkeypatch.setattr(app.pipeline, "analyze_source", slow_analysis)
    pool = job_queue.Scheduler("analysis-cancel", max_workers=1)
    monkeypatch.setattr(app, "analysis_pool", pool)
    task = pool.submit(app.run_analysis, "analysis-cancel")
    assert started.wait(2)
    routes_batches._AppBackend().cancel_job("analysis-cancel")
    job = _wait(
        lambda: (
            app.load_job("analysis-cancel")
            if app.load_job("analysis-cancel")["status"] == "cancelled"
            else None
        )
    )
    assert job["status"] == "cancelled"
    assert calls["count"] < 100
    _wait(lambda: "analysis-cancel" not in app.ANALYSIS_CANCELS or None)
    assert task.state is job_queue.QueueState.INTERRUPTED


def test_render_submission_is_atomic_for_same_identity(data_env, monkeypatch):
    source = data_env / "source.mp4"
    source.write_bytes(b"x")
    write_job(
        app.JOBS,
        "render-race",
        source={"path": str(source), "name": "source.mp4"},
    )
    submitted = []
    monkeypatch.setattr(
        app.render_pool, "submit",
        lambda *args, **kwargs: submitted.append((args, kwargs)),
    )
    plan = {
        "target": 30,
        "total": 30,
        "hook_scene": 0,
        "auto": True,
        "clips": [],
    }
    job = app.load_job("render-race")
    barrier = threading.Barrier(8)

    def submit():
        barrier.wait()
        return app._queue_render(
            "render-race", job, plan, "final", "9:16", None, False, None, False,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        records = list(pool.map(lambda _: submit(), range(8)))
    assert len(submitted) == 1
    assert len({record["record_key"] for record in records}) == 1


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


def test_concurrent_job_retry_submits_once(data_env, monkeypatch):
    source = data_env / "source.mp4"
    source.write_bytes(b"not a real video")
    write_job(
        app.JOBS,
        "race",
        status="interrupted",
        analysis=None,
        source={"path": str(source), "name": "source.mp4"},
    )
    cap = CapturePool()
    monkeypatch.setattr(app, "analysis_pool", cap)
    job = app.load_job("race")
    barrier = threading.Barrier(12)

    def attempt():
        barrier.wait()
        return routes_batches._retry_job(app, job)

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda _: attempt(), range(12)))
    assert len(cap.calls) == 1
    assert sum(1 for analysis, _renders in results if analysis) == 1
    assert app.load_job("race")["status"] == "queued"


def test_job_retry_handles_old_render_record(data_env, monkeypatch):
    source = data_env / "source.mp4"
    source.write_bytes(b"x")
    write_job(
        app.JOBS,
        "old-render",
        source={"path": str(source), "name": "source.mp4"},
        renders={
            "30:final": {
                "status": "failed",
                "target": 30,
                "quality": "final",
                "aspect": "9:16",
                "captions": False,
                "error": "old failure",
            }
        },
    )
    submitted = []
    monkeypatch.setattr(app.render_pool, "submit", lambda *args, **kwargs: submitted.append((args, kwargs)))
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
    job = app.load_job("old-render")
    analysis, renders = routes_batches._retry_job(app, job)
    assert analysis is False
    assert renders == 1
    assert len(submitted) == 1
    latest = app.load_job("old-render")["renders"]
    assert "30:final" not in latest
    record = latest["30"]
    assert record["status"] == "queued"
    assert record["attempts"] == 1
    assert routes_batches._retry_job(app, app.load_job("old-render")) == (False, 0)
    assert len(submitted) == 1


def test_timeout_fails_stalled_batch_item(tmp_path):
    class StalledBackend(FakeBackend):
        def create_job(self, item: dict) -> dict:
            job = super().create_job(item)
            job["status"] = "queued"
            self.jobs[job["id"]]["status"] = "queued"
            return job

    manager = batch.BatchManager(
        tmp_path, backend=StalledBackend(), poll_interval=0.01,
    )
    manager.analysis_timeout = 0.05
    created = manager.create("timeout", [{"path": "/tmp/a.mp4"}], start=True)
    final = _wait(
        lambda: (
            manager.get(created["id"])
            if manager.get(created["id"])["status"] == "failed"
            else None
        )
    )
    assert final["items"][0]["state"] == "failed"
    assert "timed out" in final["items"][0]["error"]


def test_timeout_fails_stalled_render(tmp_path):
    class StalledRenderBackend(FakeBackend):
        def start_renders(self, job_id: str, targets: list[int], options: dict) -> list[dict]:
            records = super().start_renders(job_id, targets, options)
            for record in records:
                record["status"] = "queued"
                self.jobs[job_id]["renders"][record["record_key"]]["status"] = "queued"
            return records

    manager = batch.BatchManager(
        tmp_path, backend=StalledRenderBackend(), poll_interval=0.01,
    )
    manager.render_timeout = 0.05
    created = manager.create(
        "render-timeout",
        [{"path": "/tmp/a.mp4", "options": {"targets": [30]}}],
        start=True,
    )
    final = _wait(
        lambda: (
            manager.get(created["id"])
            if manager.get(created["id"])["status"] == "failed"
            else None
        )
    )
    assert final["items"][0]["state"] == "failed"
    assert "Render timed out" in final["items"][0]["error"]


def test_cancel_job_cancels_queued_analysis_and_render(data_env, monkeypatch):
    job_id = "cancel-me"
    write_job(
        app.JOBS,
        job_id,
        status="queued",
        analysis=None,
        renders={
            "30:final": {
                "status": "queued",
                "target": 30,
                "quality": "final",
                "aspect": "9:16",
                "captions": False,
                "record_key": "30:final",
                "error": None,
            }
        },
    )
    gate = threading.Event()
    analysis_pool = job_queue.Scheduler("analysis-test", max_workers=1)
    render_pool = job_queue.Scheduler("render-test", max_workers=1)
    analysis_blocker = analysis_pool.submit(
        lambda: gate.wait(3), task_kind="analysis", task_key="blocker",
    )
    render_blocker = render_pool.submit(
        lambda: gate.wait(3), task_kind="render", task_key="blocker",
    )
    _wait(lambda: analysis_blocker.state is job_queue.QueueState.RUNNING)
    _wait(lambda: render_blocker.state is job_queue.QueueState.RUNNING)
    analysis_task = analysis_pool.submit(
        lambda: "never", task_kind="analysis", task_key=job_id,
    )
    render_task = render_pool.submit(
        lambda: "never", task_kind="render", task_key=f"render:{job_id}:30:final",
    )
    _wait(lambda: analysis_task.state is job_queue.QueueState.QUEUED)
    _wait(lambda: render_task.state is job_queue.QueueState.QUEUED)
    monkeypatch.setattr(app, "analysis_pool", analysis_pool)
    monkeypatch.setattr(app, "render_pool", render_pool)

    routes_batches._AppBackend().cancel_job(job_id)

    assert analysis_task.state is job_queue.QueueState.CANCELLED
    assert render_task.state is job_queue.QueueState.CANCELLED
    job = app.load_job(job_id)
    assert job["status"] == "cancelled"
    assert job["renders"]["30:final"]["status"] == "cancelled"
    gate.set()
    assert analysis_blocker.wait(3)
    assert render_blocker.wait(3)


def test_oversized_upload_returns_413_before_disk_412(data_env, monkeypatch):
    monkeypatch.setattr(disk, "usage", lambda path: _usage(100 * GIB, 4 * GIB))
    monkeypatch.setattr(app, "MAX_UPLOAD", 1)
    with TestClient(app.app) as client:
        response = client.post(
            "/api/jobs/upload",
            files={"file": ("big.mp4", b"too large", "video/mp4")},
        )
    assert response.status_code == 413


def test_url_preflight_and_invalid_size_hint(data_env, monkeypatch):
    monkeypatch.setattr(disk, "usage", lambda path: _usage(100 * GIB, 4 * GIB))
    with TestClient(app.app) as client:
        url_response = client.post(
            "/api/jobs/from-url", json={"url": "https://example.com/video"},
        )
        bad_size = client.post(
            "/api/batches",
            json={
                "name": "bad size",
                "items": [{"url": "https://example.com/v", "options": {
                    "size_bytes": "not-a-number",
                }}],
                "max": 10,
            },
        )
        zero_batch = client.post(
            "/api/batches",
            json={
                "name": "zero estimate",
                "items": [{"url": "https://example.com/v"}],
                "max": 10,
            },
        )
        bad_top_size = client.post(
            "/api/batches",
            json={
                "name": "bad top size",
                "items": [{
                    "url": "https://example.com/v",
                    "size_bytes": {"nested": "junk"},
                }],
                "max": 10,
            },
        )
    assert url_response.status_code == 412
    assert url_response.json()["code"] == "insufficient_space"
    assert zero_batch.status_code == 412
    assert zero_batch.json()["code"] == "insufficient_space"
    assert bad_size.status_code == 400
    assert "size_bytes" in bad_size.json()["detail"]
    assert bad_top_size.status_code == 400
    assert "size_bytes" in bad_top_size.json()["detail"]


def test_disk_exact_reserve_boundary_and_zero_estimate(monkeypatch):
    monkeypatch.setattr(disk, "usage", lambda path: _usage(100 * GIB, 5 * GIB))
    assert disk.report(0, "/tmp")["ok"] is True
    assert disk.report(1, "/tmp")["ok"] is False
    monkeypatch.setattr(disk, "usage", lambda path: _usage(100 * GIB, 4 * GIB))
    report = disk.report(0, "/tmp")
    assert report["ok"] is False
    assert report["shortfall_bytes"] > 0
    with pytest.raises(disk.InsufficientSpace) as caught:
        disk.preflight(0, "/tmp")
    payload = caught.value.as_dict()
    assert {
        "code", "required_bytes", "free_bytes", "shortfall_bytes",
        "volume_total_bytes", "path",
    } <= set(payload)
    assert payload["volume_total_bytes"] == 100 * GIB
    assert payload["path"] == "/tmp"


def test_app_imports_after_stdlib_queue(tmp_path):
    root = Path(__file__).resolve().parents[1]
    assert not (root / "queue.py").exists()
    env = dict(os.environ)
    env["VIBECUT_DATA"] = str(tmp_path / "data")
    result = subprocess.run(
        [
            sys.executable, "-c",
            "import queue; import app; print(type(app.analysis_pool).__name__)",
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "Scheduler" in result.stdout


def test_recover_marks_artifact_backed_render_interrupted(data_env):
    source = data_env / "source.mp4"
    source.write_bytes(b"x")
    write_job(
        app.JOBS,
        "art-live",
        source={"path": str(source), "name": "source.mp4", "fingerprint": "fp1"},
        analysis={"scene_count": 0, "scenes": [], "hook_scene": None},
    )
    job = app.load_job("art-live")
    plan = {
        "target": 30, "total": 0, "hook_scene": 0, "auto": True, "clips": [],
    }
    spec = artifacts.build_spec(job, plan, captions=False)
    artifact = artifacts.artifact_id(spec)
    manifest = artifacts.make_manifest(
        "art-live", spec, status="queued", record_key="30",
    )
    artifacts.save_manifest(app._job_dir("art-live"), manifest)
    orphan_plan = {**plan, "target": 60}
    orphan_spec = artifacts.build_spec(job, orphan_plan, captions=False)
    orphan = artifacts.make_manifest(
        "art-live", orphan_spec, status="queued", record_key="60",
    )
    artifacts.save_manifest(app._job_dir("art-live"), orphan)
    orphan_id = artifacts.artifact_id(orphan_spec)
    job["renders"] = {
        "30": {
            "status": "rendering",
            "target": 30,
            "quality": "final",
            "aspect": "9:16",
            "captions": False,
            "record_key": "30",
            "artifact_id": artifact,
        }
    }
    app.save_job(job)

    app.recover_jobs()

    record = app.load_job("art-live")["renders"]["30"]
    assert record["status"] == "interrupted"
    stored = artifacts.load_manifest(app._job_dir("art-live"), artifact)
    assert stored["status"] == "interrupted"
    orphan_stored = artifacts.load_manifest(app._job_dir("art-live"), orphan_id)
    assert orphan_stored["status"] == "interrupted"


def test_artifact_backed_render_retry_reuses_artifact(data_env, monkeypatch):
    source = data_env / "source.mp4"
    source.write_bytes(b"x")
    write_job(
        app.JOBS,
        "art-retry",
        source={"path": str(source), "name": "source.mp4", "fingerprint": "fp2"},
        analysis={"scene_count": 0, "scenes": [], "hook_scene": None},
    )
    job = app.load_job("art-retry")
    plan = {
        "target": 30, "total": 0, "hook_scene": 0, "auto": True, "clips": [],
    }
    spec = artifacts.build_spec(job, plan, captions=False)
    artifact = artifacts.artifact_id(spec)
    manifest = artifacts.make_manifest(
        "art-retry", spec, status="interrupted", record_key="30",
    )
    artifacts.save_manifest(app._job_dir("art-retry"), manifest)
    job["renders"] = {
        "30": {
            "status": "interrupted",
            "target": 30,
            "quality": "final",
            "aspect": "9:16",
            "captions": False,
            "record_key": "30",
            "artifact_id": artifact,
            "error": "restart",
        }
    }
    app.save_job(job)
    submitted = []
    monkeypatch.setattr(
        app.render_pool, "submit",
        lambda *args, **kwargs: submitted.append((args, kwargs)),
    )
    monkeypatch.setattr(app, "_plan_for_body", lambda job, target, body: dict(plan))

    analysis, renders = routes_batches._retry_job(app, app.load_job("art-retry"))

    assert analysis is False
    assert renders == 1
    assert len(submitted) == 1
    record = app.load_job("art-retry")["renders"]["30"]
    assert record["status"] == "queued"
    assert record["artifact_id"] == artifact
    assert record["generation"] == 0
    assert artifact in submitted[0][0]
    stored = artifacts.load_manifest(app._job_dir("art-retry"), artifact)
    assert stored["status"] == "queued"
    assert stored["spec"]["generation"] == 0


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
        assert {"shortfall_bytes", "volume_total_bytes", "path"} <= set(body)
