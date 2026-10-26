"""FR-17: no 24-job cap; search by name, id, story title and date; fast."""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

import app


@pytest.fixture
def api(tmp_path, monkeypatch):
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    monkeypatch.setattr(app, "JOBS", jobs)
    app._JOB_INDEX.clear()
    client = TestClient(app.app)
    client.jobs = jobs  # type: ignore[attr-defined]
    return client


def write(jobs, index: int, **extra) -> None:
    job_id = f"job{index:03d}"
    directory = jobs / job_id
    directory.mkdir()
    job = {
        "id": job_id,
        "created": time.mktime((2026, 10, 1 + index % 20, 12, 0, 0, 0, 0, -1)),
        "status": "ready",
        "source": {"name": f"episode-{index:03d}.mp4", "duration": 600.0},
        "analysis": {"scene_count": 3},
        **extra,
    }
    (directory / "job.json").write_text(json.dumps(job))


def test_no_cap_and_pagination(api):
    for index in range(40):
        write(api.jobs, index)
    first = api.get("/api/jobs?limit=30").json()
    assert first["total"] == 40 and len(first["jobs"]) == 30
    second = api.get("/api/jobs?limit=30&offset=30").json()
    assert len(second["jobs"]) == 10
    ids = {row["id"] for row in first["jobs"] + second["jobs"]}
    assert len(ids) == 40


def test_search_by_name_id_story_title_and_date(api):
    write(api.jobs, 1)
    write(api.jobs, 2, clip_sets={"cs1": {"id": "cs1", "stories": [
        {"id": "s1", "title": "Why pricing beats features"},
    ]}})
    assert [row["id"] for row in api.get("/api/jobs?q=episode-001").json()["jobs"]] == ["job001"]
    assert [row["id"] for row in api.get("/api/jobs?q=job002").json()["jobs"]] == ["job002"]
    assert [row["id"] for row in api.get("/api/jobs?q=pricing beats").json()["jobs"]] == ["job002"]
    assert [row["id"] for row in api.get("/api/jobs?q=2026-10-03").json()["jobs"]] == ["job002"]
    row = api.get("/api/jobs?q=job002").json()["jobs"][0]
    assert "_search" not in row and row["story_titles"] == ["Why pricing beats features"]


def test_index_is_derived_and_follows_job_json(api):
    write(api.jobs, 1)
    assert api.get("/api/jobs?q=renamed").json()["total"] == 0
    path = api.jobs / "job001" / "job.json"
    job = json.loads(path.read_text())
    job["source"]["name"] = "renamed.mp4"
    time.sleep(0.01)
    path.write_text(json.dumps(job))
    assert api.get("/api/jobs?q=renamed").json()["total"] == 1
    (path).unlink()
    assert api.get("/api/jobs").json()["total"] == 0


def test_100_job_search_p95_under_300ms(api):
    for index in range(100):
        write(api.jobs, index)
    api.get("/api/jobs")  # warm the derived index
    timings = []
    for _ in range(20):
        started = time.perf_counter()
        api.get("/api/jobs?q=episode-05")
        timings.append(time.perf_counter() - started)
    timings.sort()
    assert timings[int(len(timings) * 0.95) - 1] < 0.3
