"""FR-16: explicit source delete with CAS refcount and a receipt."""

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
    for name in ("jobs", "sources"):
        (data / name).mkdir(parents=True)
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", data / "jobs")
    monkeypatch.setattr(app, "SOURCES", data / "sources")
    monkeypatch.setattr(app, "SHARES", data / "shares.json")
    client = TestClient(app.app)
    client.data = data  # type: ignore[attr-defined]
    return client


def managed_job(data: Path, job_id: str, content: bytes = b"client footage") -> Path:
    job_dir = data / "jobs" / job_id
    job_dir.mkdir(parents=True)
    incoming = data / "sources" / f".incoming-{job_id}.mp4"
    incoming.write_bytes(content)
    stored = app.store_source(incoming, ".mp4", "client.mp4")
    linked = app.link_source(stored, job_dir, ".mp4")
    write(job_dir, job_id, linked, "client.mp4")
    return stored


def write(job_dir: Path, job_id: str, source: Path, name: str) -> None:
    (job_dir / "job.json").write_text(json.dumps({
        "id": job_id, "created": time.time(), "updated": time.time(),
        "status": "ready", "progress": 1.0, "message": "Ready", "error": None,
        "source": {"path": str(source), "name": name, "duration": 10.0},
        "options": {}, "analysis": {"scenes": []}, "renders": {},
    }))


def test_delete_last_reference_removes_cas_object_and_writes_receipt(api):
    stored = managed_job(api.data, "j1")
    refs = api.get("/api/jobs/j1/source").json()
    assert refs["managed"] is True and refs["refcount"] == 1

    response = api.post("/api/jobs/j1/source/delete", json={})
    assert response.status_code == 200, response.text
    receipt = response.json()["receipt"]
    assert receipt["result"] == "deleted"
    assert receipt["refcount_before"] == 1 and receipt["refcount_after"] == 0
    assert receipt["cas_deleted"] is True and receipt["path_absent"] is True
    assert receipt["source_hash"] == stored.parent.name
    assert not stored.exists() and not stored.parent.exists()
    assert not (api.data / "jobs" / "j1" / "source.mp4").exists()
    on_disk = json.loads((api.data / "jobs" / "j1" / "deletion_receipt.json").read_text())
    assert on_disk == receipt
    assert api.get("/api/jobs/j1/source/receipt").json()["receipt"] == receipt
    assert api.post("/api/jobs/j1/source/delete", json={}).status_code == 409


def test_shared_cas_object_survives_until_its_last_job(api):
    stored = managed_job(api.data, "j1")
    managed_job(api.data, "j2")
    first = api.post("/api/jobs/j1/source/delete", json={}).json()["receipt"]
    assert first["refcount_before"] == 2 and first["refcount_after"] == 1
    assert first["cas_deleted"] is False and stored.exists()
    second = api.post("/api/jobs/j2/source/delete", json={}).json()["receipt"]
    assert second["cas_deleted"] is True and not stored.exists()


def test_referenced_source_needs_cascade_and_keeps_outputs(api, monkeypatch):
    managed_job(api.data, "j1")
    monkeypatch.setattr(app, "_source_refs", _with_artifacts(app._source_refs))
    blocked = api.post("/api/jobs/j1/source/delete", json={})
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "source_referenced"
    allowed = api.post("/api/jobs/j1/source/delete", json={"cascade": True})
    assert allowed.status_code == 200
    assert allowed.json()["receipt"]["kept"]["artifacts"] == 1


def _with_artifacts(original):
    def wrapped(job):
        refs = original(job)
        return {**refs, "artifacts": 1}
    return wrapped


def test_path_import_never_deletes_the_users_file(api, tmp_path):
    original = tmp_path / "my-original.mp4"
    original.write_bytes(b"keep me")
    job_dir = api.data / "jobs" / "j1"
    job_dir.mkdir()
    write(job_dir, "j1", original, original.name)
    receipt = api.post("/api/jobs/j1/source/delete", json={}).json()["receipt"]
    assert receipt["managed"] is False
    assert original.read_bytes() == b"keep me"
    assert "left in place" in receipt["note"]


def test_source_store_is_never_garbage_collected_by_default(api, monkeypatch):
    monkeypatch.delenv("VIBECUT_SOURCES_GC_DAYS", raising=False)
    stored = managed_job(api.data, "j1")
    (api.data / "jobs" / "j1" / "source.mp4").unlink()  # store holds the only link
    old = time.time() - 365 * 86400
    import os
    os.utime(stored.parent, (old, old))
    assert app.gc_sources() == 0
    assert stored.exists()
