"""Recent-cut API fields and deletion behavior."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app


@pytest.fixture
def api(tmp_path, monkeypatch):
    data = tmp_path / "data"
    jobs = data / "jobs"
    sources = data / "sources"
    jobs.mkdir(parents=True)
    sources.mkdir(parents=True)
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.setattr(app, "SOURCES", sources)
    client = TestClient(app.app)
    client.jobs_dir = jobs  # type: ignore[attr-defined]
    return client


def write_job(jobs, job_id: str, **overrides) -> Path:
    job = {
        "id": job_id,
        "created": time.time(),
        "updated": time.time(),
        "status": "ready",
        "progress": 1.0,
        "message": "Ready",
        "error": None,
        "source": {"name": "clip.mp4", "duration": 12.0},
        "analysis": {"scene_count": 4, "scenes": [], "hook_scene": None},
        "renders": {},
        "ingest": {},
    }
    job.update(overrides)
    directory = jobs / job_id
    directory.mkdir(parents=True)
    (directory / "job.json").write_text(json.dumps(job))
    return directory


def test_recent_jobs_expose_failure_context(api):
    write_job(
        api.jobs_dir,
        "fail1",
        status="failed",
        progress=1.0,
        message="URL ingest failed",
        error="yt-dlp: HTTP 403 Forbidden",
        ingest={
            "provider": "ytdlp",
            "label": "yt-dlp",
            "status": "failed",
            "error": "yt-dlp: HTTP 403 Forbidden",
        },
    )

    response = api.get("/api/jobs")

    assert response.status_code == 200
    job = response.json()["jobs"][0]
    assert job["status"] == "failed"
    assert job["message"] == "URL ingest failed"
    assert job["error"] == "yt-dlp: HTTP 403 Forbidden"
    assert job["provider"] == "ytdlp"
    assert job["provider_label"] == "yt-dlp"
    assert job["ingest_status"] == "failed"
    assert job["ingest_error"] == "yt-dlp: HTTP 403 Forbidden"


def test_failed_recent_cut_can_be_deleted(api):
    directory = write_job(
        api.jobs_dir,
        "fail2",
        status="failed",
        message="URL ingest failed",
        error="Download cancelled.",
    )

    response = api.delete("/api/jobs/fail2")

    assert response.status_code == 200
    assert response.json() == {"deleted": "fail2"}
    assert not directory.exists()
    assert api.get("/api/jobs").json()["jobs"] == []


def test_downloading_recent_cut_delete_is_blocked(api):
    write_job(
        api.jobs_dir,
        "live1",
        status="downloading",
        progress=0.25,
        message="Downloading video",
        ingest={"provider": "xhs", "label": "RedNote", "status": "downloading"},
    )

    response = api.delete("/api/jobs/live1")

    assert response.status_code == 409
    assert response.json()["detail"] == "This job is still working."
    assert (api.jobs_dir / "live1" / "job.json").exists()
    assert [job["id"] for job in api.get("/api/jobs").json()["jobs"]] == ["live1"]
