"""Delete asks first, then stops the video's work and queues the delete."""

from __future__ import annotations

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

import app
import routes_check
import routes_studio
import shares
import story_queue


def _wait_gone(folder, seconds=5.0):
    deadline = time.time() + seconds
    while time.time() < deadline and folder.exists():
        time.sleep(0.02)
    return not folder.exists()


@pytest.fixture
def api(tmp_path, monkeypatch):
    jobs = tmp_path / "jobs"
    folder = jobs / "j1"
    folder.mkdir(parents=True)
    (folder / "source.mp4").write_bytes(b"x")
    outside = tmp_path / "original.mp4"
    outside.write_bytes(b"keep")
    (folder / "job.json").write_text(json.dumps({
        "id": "j1", "status": "ready", "renders": {}, "source": {"path": str(outside)},
    }))
    monkeypatch.setattr(app, "HOST", "127.0.0.1")
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.setattr(app, "DATA", tmp_path)
    monkeypatch.setattr(app, "SHARES", tmp_path / "shares.json")
    monkeypatch.setattr(routes_studio, "DELETE_SWEEP_S", 0.0)
    monkeypatch.delenv("VIBECUT_TOKEN", raising=False)
    client = TestClient(app.app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))
    client.folder, client.outside = folder, outside  # type: ignore[attr-defined]
    return client


def _edit_job(api, **fields):
    path = api.folder / "job.json"
    job = json.loads(path.read_text())
    job.update(fields)
    path.write_text(json.dumps(job))


def test_the_check_names_nothing_for_an_idle_video(api):
    assert api.get("/api/jobs/j1/delete-check").json() == {"work": [], "keeps": []}


def test_the_check_runs_nothing_and_names_what_is_working(api):
    _edit_job(api, status="reading", check={"status": "running"}, renders={"r": {"status": "rendering"}})
    work = api.get("/api/jobs/j1/delete-check").json()["work"]
    assert work == ["Reading the video", "Scanning for text", "Rendering"]
    assert api.folder.exists()


def test_the_check_names_what_goes_with_it(api):
    shares.create("j1", "art_1", path=app.SHARES)
    assert api.get("/api/jobs/j1/delete-check").json()["keeps"] == ["1 review link"]


def test_delete_removes_the_folder_and_links_but_not_the_original(api):
    token, _ = shares.create("j1", "art_1", path=app.SHARES)
    other, _ = shares.create("j2", "art_2", path=app.SHARES)
    assert api.post("/api/jobs/j1/delete").status_code == 202
    assert _wait_gone(api.folder)
    assert api.outside.read_bytes() == b"keep"
    remaining = {item["job_id"] for item in shares.list_records(app.SHARES)}
    assert remaining == {"j2"}, f"{token} {other}"


def test_a_deleting_video_leaves_the_lists_at_once(api, monkeypatch):
    monkeypatch.setattr(routes_studio, "_finish_delete", lambda _job_id: None)
    assert api.post("/api/jobs/j1/delete").status_code == 202
    assert api.get("/api/jobs").json()["jobs"] == []
    assert api.folder.exists(), "the folder waits for the work to stop"


def test_working_video_is_stopped_then_removed(api, monkeypatch):
    _edit_job(api, renders={"r": {"status": "rendering"}})
    release = threading.Event()

    def worker_stops():
        assert app.RENDER_CANCELS.setdefault(("j1", "r"), threading.Event()).wait(5)
        release.wait(5)
        _edit_job(api, renders={"r": {"status": "cancelled"}})

    thread = threading.Thread(target=worker_stops)
    thread.start()
    assert api.post("/api/jobs/j1/delete").status_code == 202
    time.sleep(0.3)
    assert api.folder.exists(), "it waits while the render is stopping"
    release.set()
    thread.join()
    assert _wait_gone(api.folder)
    app.RENDER_CANCELS.pop(("j1", "r"), None)


def test_a_worker_that_never_stops_cannot_leave_it_stuck(api, monkeypatch):
    monkeypatch.setattr(routes_studio, "DELETE_WAIT_S", 0.2)
    _edit_job(api, check={"status": "running", "task_id": "gone"})
    monkeypatch.setattr(routes_check, "cancel_check", lambda *_a, **_k: {"ok": True})
    assert api.post("/api/jobs/j1/delete").status_code == 202
    assert _wait_gone(api.folder)


def test_a_restart_finishes_a_queued_delete(api):
    _edit_job(api, deleting=1.0)
    app.recover_jobs()
    assert not api.folder.exists()


def test_a_corrupt_link_store_refuses_before_anything_stops(api):
    app.SHARES.write_bytes(b"\xff\xfe\x00")
    assert api.post("/api/jobs/j1/delete").status_code >= 500
    assert api.folder.exists()
    assert "deleting" not in json.loads((api.folder / "job.json").read_text())


def test_the_queue_drops_only_that_video(tmp_path):
    cancelled = []

    class Backend:
        def cancel(self, item, artifact_id):
            cancelled.append(artifact_id)

    manager = story_queue.StoryQueueManager(tmp_path, Backend())
    queue = {
        "id": "sq_a", "status": "running", "items": [
            {"id": "1", "job_id": "j1", "state": "running", "artifact_id": "art_1"},
            {"id": "2", "job_id": "j1", "state": "queued"},
            {"id": "3", "job_id": "j2", "state": "queued"},
        ],
    }
    manager._write(queue)
    assert manager.waiting_for_job("j1") == 1
    manager.drop_job("j1")
    states = {item["id"]: item["state"] for item in manager._read("sq_a")["items"]}
    assert states == {"1": "cancelled", "2": "cancelled", "3": "queued"}
    assert cancelled == ["art_1"]
    assert manager.waiting_for_job("j1") == 0
