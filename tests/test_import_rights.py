"""Import stores the own-footage note on the job (QA #25). Policy is unchanged."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app
import routes_edits


@pytest.fixture
def client(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "jobs").mkdir(parents=True)
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", data / "jobs")
    monkeypatch.delenv("VIBECUT_TOKEN", raising=False)
    monkeypatch.setattr(app.pipeline, "probe", lambda path: {
        "duration": 10.0, "width": 1920, "height": 1080, "fps": 30, "has_audio": True, "size": 1,
    })
    monkeypatch.setattr(app.analysis_pool, "submit", lambda *args, **kwargs: None)
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"x")
    return TestClient(app.app), source


def test_path_import_with_the_rights_note_records_it(client):
    api, source = client
    response = api.post("/api/jobs/path", json={"path": str(source), "rights": True})
    assert response.status_code == 200, response.text
    job = app.load_job(response.json()["id"])
    assert job["rights"]["attested"] is True and job["rights"]["source"] == "import"
    assert routes_edits._clean_rights_attested(job) is True
    rights = api.get(f"/api/jobs/{job['id']}/rights").json()["rights"]
    assert rights == {"attested": True, "at": job["rights"]["at"], "source": "import"}


def test_import_without_a_note_stores_nothing(client):
    api, source = client
    response = api.post("/api/jobs/path", json={"path": str(source)})
    job = app.load_job(response.json()["id"])
    assert "rights" not in job


def test_explicit_no_keeps_clean_locked(client):
    api, source = client
    response = api.post("/api/jobs/path", json={"path": str(source), "rights": False})
    job = app.load_job(response.json()["id"])
    assert job["rights"]["attested"] is False
    assert routes_edits._clean_rights_attested(job) is False


def test_upload_form_carries_the_note(client):
    api, _source = client
    response = api.post(
        "/api/jobs/upload",
        files={"file": ("clip.mp4", b"0" * 2048, "video/mp4")},
        data={"options": "{}", "rights": "true"},
    )
    assert response.status_code == 200, response.text
    job = app.load_job(response.json()["id"])
    assert job["rights"]["attested"] is True and job["rights"]["source"] == "import"
