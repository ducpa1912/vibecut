"""Share tokens, expiry, revocation, artifact pinning and legacy binding."""

from __future__ import annotations

import json
import stat
import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app
import artifacts
import shares


def scene(index: int, start: float, dur: float, speech: str = "") -> dict:
    return {
        "id": index,
        "start": float(start),
        "end": float(start + dur),
        "dur": float(dur),
        "mid": float(start + dur / 2),
        "hook": 50.0,
        "score": 50.0,
        "deep": True,
        "ocr": "",
        "speech": speech,
        "tags": [],
        "crop": {"cx": 0.5, "cy": 0.5},
        "crop_mode": "center",
    }


def job_record(job_id: str = "job1") -> dict:
    return {
        "id": job_id,
        "created": 1.0,
        "updated": 1.0,
        "status": "ready",
        "progress": 1.0,
        "message": "Ready",
        "error": None,
        "source": {"name": "clip.mp4", "duration": 20.0},
        "analysis": {
            "scenes": [scene(0, 0.0, 4.0, "saved speech")],
            "hook_scene": 0,
        },
        "renders": {},
    }


def spec(hook: int = 0, target: int = 15) -> artifacts.ArtifactSpec:
    return artifacts.ArtifactSpec.from_payload({
        "schema_version": artifacts.SCHEMA_VERSION,
        "render_version": artifacts.RENDER_VERSION,
        "source_fingerprint": "src",
        "clips": [{
            "scene": hook, "start": 0.0, "end": 4.0, "dur": 4.0, "role": "hook",
        }],
        "order": "source",
        "hook_scene": hook,
        "hook_override": True,
        "caption": {
            "enabled": False,
            "style_hash": "s",
            "cue_hash": "c",
            "text_hash": f"t{hook}",
            "margin": 0.075,
        },
        "audio_sig": "",
        "quality": "final",
        "aspect": "9:16",
        "resolved_encoder": "libx264",
        "story_id": "story",
        "target": target,
    })


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    jobs = data / "jobs"
    jobs.mkdir(parents=True)
    sources = data / "sources"
    sources.mkdir()
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.setattr(app, "SOURCES", sources)
    monkeypatch.setattr(app, "SHARES", tmp_path / "shares.json")
    job = job_record("job1")
    directory = jobs / job["id"]
    directory.mkdir()
    (directory / "job.json").write_text(json.dumps(job), encoding="utf-8")
    return SimpleNamespace(
        tmp_path=tmp_path, data=data, jobs=jobs, directory=directory,
        job=job, job_id=job["id"],
    )


def make_artifact(env, *, hook: int = 0, target: int = 15, srt: str = "SAVED") -> dict:
    manifest = artifacts.make_manifest(
        env.job_id, spec(hook, target), status="ready", record_key=f"{target}",
    )
    manifest = artifacts.save_manifest(env.directory, manifest)
    artifact_id = manifest["artifact_id"]
    directory = artifacts.artifact_dir(env.directory, artifact_id)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "reel.mp4").write_bytes(b"fake-mp4")
    (directory / "poster.jpg").write_bytes(b"fake-jpg")
    artifacts.write_captions(env.directory, artifact_id, srt, "WEBVTT\n")
    return manifest


def test_create_token_once_and_list_redacts_token(tmp_path):
    path = tmp_path / "shares.json"
    artifact_id = "art_" + "a" * 24
    token, record = shares.create(
        "job1", artifact_id, label="Client review", path=path,
        expires_in_days=7,
    )
    assert token
    assert record["job_id"] == "job1"
    assert record["artifact_id"] == artifact_id
    assert record["expires_at"] and record["expires_at"] > time.time()
    assert record["revoked_at"] is None
    assert "token" not in record or record.get("token") is None

    token2, _ = shares.create("job1", artifact_id, path=path)
    assert token2 != token

    rows = shares.list_records(path)
    assert len(rows) == 2
    assert all("token" not in row for row in rows)
    assert all(row.get("token_hint") for row in rows)
    exposed = shares.list_records(path, include_tokens=True)
    assert {row["token"] for row in exposed} == {token, token2}
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    stored = shares.load(path)
    assert set(stored) == {token, token2}
    assert shares.get(token, path)["status"] == shares.ACTIVE


def test_expiry_revocation_and_binding_are_serialised(tmp_path):
    path = tmp_path / "shares.json"
    past = time.time() - 30
    token, _ = shares.create("job1", None, path=path, expires_at=past)
    record, status = shares.resolve(token, path)
    assert status == shares.EXPIRED
    assert record and record["artifact_id"] is None

    extended = shares.patch(token, {"expires_in_days": 1}, path)
    assert extended["status"] == shares.ACTIVE
    revoked = shares.revoke(token, path)
    assert revoked["status"] == shares.REVOKED
    assert shares.resolve(token, path)[1] == shares.REVOKED
    assert shares.unrevoke(token, path)["status"] == shares.ACTIVE

    bound = shares.bind_artifact(token, "art_" + "c" * 24, path)
    assert bound["artifact_id"] == "art_" + "c" * 24
    again = shares.bind_artifact(token, "art_" + "d" * 24, path)
    assert again["artifact_id"] == "art_" + "c" * 24

    assert shares.delete(token, path) is True
    assert shares.get(token, path) is None
    assert shares.delete(token, path) is False


def test_expired_and_revoked_review_links_are_gone(env):
    manifest = make_artifact(env)
    past = time.time() - 10
    token, _ = shares.create(
        env.job_id, manifest["artifact_id"], path=app.SHARES, expires_at=past,
    )
    with pytest.raises(HTTPException) as expired:
        app._share(token)
    assert expired.value.status_code == 410

    shares.patch(token, {"expires_in_days": 1}, app.SHARES)
    assert app._share(token) is not None
    shares.revoke(token, app.SHARES)
    with pytest.raises(HTTPException) as revoked:
        app._share(token)
    assert revoked.value.status_code == 410

    missing, _ = shares.create(
        env.job_id, "art_" + "0" * 24, path=app.SHARES,
    )
    with pytest.raises(HTTPException) as absent:
        app._share(missing)
    assert absent.value.status_code == 404
    assert app._share("no-such-token") is None


def test_legacy_share_binds_once_and_never_retargets(env):
    manifest_a = make_artifact(env, hook=0)
    manifest_b = make_artifact(env, hook=1)
    job = app.load_job(env.job_id)
    job["renders"] = {
        "15": {
            "status": "ready",
            "path": "renders/reel_15.mp4",
            "target": 15,
            "aspect": "9:16",
            "updated": 2.0,
            "artifact_id": manifest_a["artifact_id"],
        },
    }
    app.save_job(job)

    token = "legacy-token-0123456789"
    shares.save({
        token: {
            "job_id": env.job_id,
            "created": 1.0,
            "expires_at": None,
            "revoked_at": None,
            "label": "old link",
            "target": 15,
            "aspect": "9:16",
        },
    }, app.SHARES)
    assert shares.get(token, app.SHARES)["artifact_id"] is None

    first = app._share(token)
    assert first and first[0]["artifact_id"] == manifest_a["artifact_id"]
    assert shares.get(token, app.SHARES)["artifact_id"] == manifest_a["artifact_id"]

    job = app.load_job(env.job_id)
    job["renders"]["15"]["artifact_id"] = manifest_b["artifact_id"]
    job["renders"]["15"]["updated"] = 50.0
    app.save_job(job)

    second = app._share(token)
    assert second and second[0]["artifact_id"] == manifest_a["artifact_id"]
    assert second[2]["artifact_id"] == manifest_a["artifact_id"]


def test_review_captions_come_from_saved_artifact_srt(env):
    manifest = make_artifact(env, srt="1\n00:00:00,000 --> 00:00:01,000\nSAVED CUE\n")
    token, _ = shares.create(env.job_id, manifest["artifact_id"], path=app.SHARES)

    job = app.load_job(env.job_id)
    job["analysis"]["scenes"][0]["speech"] = "CHANGED SPEECH"
    app.save_job(job)

    response = app.review_captions(token)
    assert response.body.decode("utf-8") == (
        "1\n00:00:00,000 --> 00:00:01,000\nSAVED CUE\n"
    )


def test_share_api_lifecycle_and_artifact_routes(env):
    manifest = make_artifact(env)
    artifact_id = manifest["artifact_id"]
    client = TestClient(app.app)

    listing = client.get(f"/api/jobs/{env.job_id}/artifacts")
    assert listing.status_code == 200
    assert listing.json()["artifact_ids"] == [artifact_id]
    detail = client.get(f"/api/jobs/{env.job_id}/artifacts/{artifact_id}")
    assert detail.status_code == 200
    assert detail.json()["artifact"]["spec"]["resolved_encoder"] == "libx264"

    created = client.post(
        f"/api/jobs/{env.job_id}/share",
        json={"artifact_id": artifact_id, "expires_in_days": 1, "label": "Client"},
    )
    assert created.status_code == 200
    body = created.json()
    token = body["token"]
    assert body["artifact_id"] == artifact_id
    assert body["url"] == f"/r/{token}"

    rows = client.get("/api/shares").json()
    assert rows["count"] == 1
    assert rows["shares"][0]["label"] == "Client"
    assert "token" not in rows["shares"][0]
    assert client.get("/api/shares?include_tokens=true").json()["shares"][0]["token"] == token

    assert client.get(f"/r/{token}").status_code == 200
    assert client.get(f"/r/{token}/video").content == b"fake-mp4"
    assert "SAVED" in client.get(f"/r/{token}/captions.srt").text

    expired = client.patch(f"/api/shares/{token}", json={"expires_at": time.time() - 10})
    assert expired.status_code == 200
    assert client.get(f"/r/{token}").status_code == 410

    revived = client.patch(
        f"/api/shares/{token}",
        json={"expires_at": time.time() + 3600, "revoked": False},
    )
    assert revived.status_code == 200
    assert client.get(f"/r/{token}").status_code == 200
    client.patch(f"/api/shares/{token}", json={"revoked": True})
    assert client.get(f"/r/{token}").status_code == 410

    assert client.delete(f"/api/shares/{token}").status_code == 200
    assert client.get(f"/r/{token}").status_code == 404
    assert client.patch(f"/api/shares/{token}", json={}).status_code == 404
    assert client.delete(f"/api/shares/{token}").status_code == 404

    legacy = client.post(
        f"/api/jobs/{env.job_id}/share?target=15&aspect=9:16",
    )
    assert legacy.status_code == 200
    assert legacy.json()["artifact_id"] == artifact_id
    assert client.delete(f"/api/shares/{legacy.json()['token']}").status_code == 200
    missing = client.post(
        f"/api/jobs/{env.job_id}/share",
        json={"artifact_id": "art_" + "f" * 24},
    )
    assert missing.status_code == 404

    pinned = client.post(f"/api/jobs/{env.job_id}/artifacts/{artifact_id}/pin")
    assert pinned.status_code == 200
    assert pinned.json()["artifact"]["pinned"] is True
    blocked = client.delete(f"/api/jobs/{env.job_id}/artifacts/{artifact_id}")
    assert blocked.status_code == 409
    unpinned = client.post(
        f"/api/jobs/{env.job_id}/artifacts/{artifact_id}/pin",
        json={"pinned": False},
    )
    assert unpinned.status_code == 200
    assert client.delete(f"/api/jobs/{env.job_id}/artifacts/{artifact_id}").status_code == 200
    assert client.get(
        f"/api/jobs/{env.job_id}/artifacts/{artifact_id}"
    ).status_code == 404
