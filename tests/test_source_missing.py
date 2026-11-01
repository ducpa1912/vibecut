"""A moved or deleted source is named plainly and blocks work (QA #11)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app


@pytest.fixture
def env(tmp_path, monkeypatch):
    # Undo the suite-wide placeholder: this file tests the real check.
    monkeypatch.setattr(app, "_source_exists", lambda path: Path(path).is_file())
    data = tmp_path / "data"
    jobs = data / "jobs"
    jobs.mkdir(parents=True)
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.delenv("VIBECUT_TOKEN", raising=False)
    source = tmp_path / "no_audio.mp4"
    source.write_bytes(b"x")
    scenes = [{"id": 0, "start": 0.0, "end": 30.0, "dur": 30.0, "speech": "Hello."}]
    (jobs / "j1").mkdir()
    (jobs / "j1" / "job.json").write_text(json.dumps({
        "id": "j1", "status": "ready", "progress": 1.0, "message": "Ready",
        "error": None, "created": 1.0,
        "source": {"path": str(source), "name": source.name, "duration": 30.0},
        "options": {}, "analysis": {"scenes": scenes, "scene_count": 1},
        "renders": {}, "clip_sets": [],
    }))
    return TestClient(app.app), source


def test_present_source_is_not_flagged(env):
    client, _source = env
    status = client.get("/api/jobs/j1/status").json()
    assert status["source_missing"] is False
    assert status["source_missing_message"] is None


def test_missing_source_is_reported_on_status_and_job(env):
    client, source = env
    source.unlink()
    status = client.get("/api/jobs/j1/status").json()
    assert status["source_missing"] is True
    assert status["source_missing_path"] == str(source)
    assert status["source_missing_message"].startswith(
        f"The original file was moved or deleted: {source}",
    )
    job = client.get("/api/jobs/j1").json()
    assert job["source_missing"] is True
    rows = client.get("/api/jobs").json()
    row = next(item for item in rows.get("jobs", rows) if item["id"] == "j1")
    assert row["source_missing"] is True


def test_missing_source_blocks_check_stories_and_render(env):
    client, source = env
    source.unlink()
    check = client.post("/api/jobs/j1/check", json={})
    assert check.status_code == 409
    assert "moved or deleted" in check.json()["detail"]
    stories = client.post("/api/jobs/j1/clip-sets", json={"count": 3})
    assert stories.status_code == 409
    assert "moved or deleted" in stories.json()["detail"]
    # Every render (story, Classic, queue) goes through _queue_render.
    with pytest.raises(app.HTTPException) as caught:
        app._queue_render(
            "j1", app.load_job("j1"), {"target": 30}, "final", "9:16",
            None, False, None, False,
        )
    assert caught.value.status_code == 409
    assert "moved or deleted" in caught.value.detail


def test_a_copy_that_moved_with_the_data_folder_is_found(env, tmp_path):
    """Lane data moved from <worktree>/data to ~/vibecut-lanes/<lane>."""
    client, _source = env
    moved = app.JOBS / "j1" / "source.mp4"
    moved.write_bytes(b"x")
    job_file = app.JOBS / "j1" / "job.json"
    job = json.loads(job_file.read_text())
    job["source"]["path"] = "/old/worktree/data/jobs/j1/source.mp4"
    job_file.write_text(json.dumps(job))
    assert app.load_job("j1")["source"]["path"] == str(moved)
    assert client.get("/api/jobs/j1/status").json()["source_missing"] is False


def test_a_file_imported_in_place_still_reads_as_missing(env):
    client, source = env
    source.unlink()
    assert app.load_job("j1")["source"]["path"] == str(source)
    assert client.get("/api/jobs/j1/status").json()["source_missing"] is True


def test_the_job_list_follows_a_moved_copy_too(env):
    client, _source = env
    (app.JOBS / "j1" / "source.mp4").write_bytes(b"x")
    job_file = app.JOBS / "j1" / "job.json"
    job = json.loads(job_file.read_text())
    job["source"]["path"] = "/old/worktree/data/jobs/j1/source.mp4"
    job_file.write_text(json.dumps(job))
    row = next(item for item in client.get("/api/jobs").json()["jobs"] if item["id"] == "j1")
    assert row["source_missing"] is False
