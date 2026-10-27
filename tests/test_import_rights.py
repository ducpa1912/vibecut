"""Import stores the own-footage note and obeys the rights lock."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app
import rights
import routes_edits
import settings_store


@pytest.fixture
def client(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "jobs").mkdir(parents=True)
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", data / "jobs")
    monkeypatch.setattr(settings_store, "DATA", data)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", data / "settings.json")
    monkeypatch.setattr(settings_store, "SECRETS_PATH", data / "secrets.json")
    monkeypatch.delenv("VIBECUT_TOKEN", raising=False)
    monkeypatch.setattr(app.pipeline, "probe", lambda path: {
        "duration": 10.0, "width": 1920, "height": 1080, "fps": 30, "has_audio": True, "size": 1,
    })
    monkeypatch.setattr(app.analysis_pool, "submit", lambda *args, **kwargs: None)
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"x")
    settings_store.save_settings({"rights": {"lock": True}})
    return TestClient(app.app), source


def _lock(value: bool) -> None:
    settings_store.save_settings({"rights": {"lock": value}})


def test_path_import_with_the_rights_note_records_it(client):
    api, source = client
    response = api.post("/api/jobs/path", json={"path": str(source), "rights": True})
    assert response.status_code == 200, response.text
    job = app.load_job(response.json()["id"])
    assert job["rights"]["attested"] is True and job["rights"]["source"] == "import"
    assert routes_edits._clean_rights_attested(job) is True
    rights_body = api.get(f"/api/jobs/{job['id']}/rights").json()["rights"]
    assert rights_body == {
        "attested": True, "at": job["rights"]["at"], "source": "import",
    }


def test_lock_on_refuses_an_import_without_the_note(client):
    api, source = client
    response = api.post("/api/jobs/path", json={"path": str(source)})
    assert response.status_code == 409
    assert response.json()["detail"] == rights.IMPORT_CONFIRMATION


def test_lock_on_refuses_an_explicit_no(client):
    api, source = client
    response = api.post("/api/jobs/path", json={"path": str(source), "rights": False})
    assert response.status_code == 409


def test_lock_off_imports_without_a_note_and_stores_nothing(client):
    api, source = client
    _lock(False)
    response = api.post("/api/jobs/path", json={"path": str(source)})
    assert response.status_code == 200, response.text
    job = app.load_job(response.json()["id"])
    assert "rights" not in job


def test_lock_off_still_stores_a_sent_note(client):
    api, source = client
    _lock(False)
    response = api.post(
        "/api/jobs/path", json={"path": str(source), "rights": False},
    )
    assert response.status_code == 200, response.text
    job = app.load_job(response.json()["id"])
    assert job["rights"]["attested"] is False
    assert routes_edits._clean_rights_attested(job) is False

    again = api.post(
        "/api/jobs/path", json={"path": str(source), "rights": True},
    )
    assert again.status_code == 200, again.text
    assert app.load_job(again.json()["id"])["rights"]["attested"] is True


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


def test_lock_on_upload_without_the_note_is_409(client):
    api, _source = client
    response = api.post(
        "/api/jobs/upload",
        files={"file": ("clip.mp4", b"0" * 2048, "video/mp4")},
        data={"options": "{}"},
    )
    assert response.status_code == 409
