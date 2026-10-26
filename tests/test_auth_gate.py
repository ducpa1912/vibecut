"""G4: default-deny creator API, no query tokens, cookie only for reads."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app

MUTATIONS = [
    ("patch", "/api/jobs/j1/clip-sets/s1", {"locks": []}),
    ("post", "/api/jobs/j1/clip-sets/s1/plans", {}),
    ("post", "/api/jobs/j1/clip-sets", {"count": 3}),
    ("post", "/api/jobs/path", {"path": "/tmp/x.mp4"}),
    ("patch", "/clip-sets/s1", {"locks": []}),
]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA", tmp_path)
    monkeypatch.setattr(app, "JOBS", tmp_path / "jobs")
    (tmp_path / "jobs").mkdir()
    monkeypatch.delenv("VIBECUT_TOKEN", raising=False)
    return TestClient(app.app)


def test_remote_bind_without_token_denies_every_mutation(client, monkeypatch):
    monkeypatch.setattr(app, "HOST", "0.0.0.0")
    for method, path, body in MUTATIONS:
        response = getattr(client, method)(path, json=body)
        assert response.status_code in (401, 403), (path, response.status_code)
    assert client.get("/api/jobs").status_code == 403
    assert client.get("/api/health").status_code == 200


def test_bare_clip_set_routes_are_gone(client, monkeypatch):
    monkeypatch.setattr(app, "HOST", "127.0.0.1")
    assert client.patch("/clip-sets/s1", json={"locks": []}).status_code in (404, 405)
    assert client.post("/clip-sets/s1/plans", json={}).status_code in (404, 405)


def test_query_token_is_rejected_and_bearer_works(client, monkeypatch):
    monkeypatch.setattr(app, "HOST", "0.0.0.0")
    monkeypatch.setenv("VIBECUT_TOKEN", "s3cret-token-value")
    assert client.get("/api/jobs?token=s3cret-token-value").status_code == 401
    ok = client.get("/api/jobs", headers={"Authorization": "Bearer s3cret-token-value"})
    assert ok.status_code == 200
    wrong = client.get("/api/jobs", headers={"Authorization": "Bearer nope"})
    assert wrong.status_code == 401


def test_cookie_authorises_reads_only(client, monkeypatch):
    monkeypatch.setattr(app, "HOST", "0.0.0.0")
    monkeypatch.setenv("VIBECUT_TOKEN", "s3cret-token-value")
    client.cookies.set("vibecut_token", "s3cret-token-value")
    assert client.get("/api/jobs").status_code == 200
    assert client.post("/api/jobs/path", json={"path": "/tmp/x.mp4"}).status_code == 401


def test_loopback_without_token_works(client, monkeypatch):
    monkeypatch.setattr(app, "HOST", "127.0.0.1")
    assert client.get("/api/jobs").status_code == 200
