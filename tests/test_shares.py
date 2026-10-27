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
import edits
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
    assert all("token_hint" not in row for row in rows)
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
    leaked = client.get("/api/shares?include_tokens=true").json()
    assert "token" not in leaked["shares"][0]
    assert token not in leaked["shares"][0].get("url", "")

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


# ---------------------------------------------------------------- QA round 1


def _prepare_legacy_render(env) -> dict:
    job = app.load_job(env.job_id)
    plan = {
        "target": 15,
        "total": 4.0,
        "hook_scene": 0,
        "auto": True,
        "clip_count": 1,
        "clips": [{
            "scene": 0, "start": 0.0, "end": 4.0, "dur": 4.0, "role": "hook",
        }],
        "_source_lang": "en",
    }
    job["analysis"]["plans"] = {"15": plan}
    renders = env.directory / "renders"
    renders.mkdir(exist_ok=True)
    (renders / "reel_15.mp4").write_bytes(b"legacy-mp4")
    (renders / "reel_15.jpg").write_bytes(b"legacy-jpg")
    job["renders"] = {
        "15": {
            "status": "ready",
            "quality": "final",
            "target": 15,
            "aspect": "9:16",
            "captions": False,
            "audio_sig": "",
            "hook": 0,
            "updated": 1.0,
            "path": "renders/reel_15.mp4",
            "poster": "renders/reel_15.jpg",
        },
    }
    app.save_job(job)
    return job


def _save_legacy_share(env, token: str = "legacy-clean-token-0123456789") -> str:
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
    return token


def test_share_listing_never_exposes_tokens_from_any_query(env):
    manifest = make_artifact(env)
    token, _ = shares.create(
        env.job_id, manifest["artifact_id"], path=app.SHARES,
    )
    client = TestClient(app.app)
    for query in (
        "",
        "?include_tokens=true",
        "?include_tokens=1",
        "?include_tokens=true&job_id=" + env.job_id,
        "?token=" + token,
    ):
        response = client.get("/api/shares" + query)
        assert response.status_code == 200
        payload = response.json()
        assert token not in response.text
        assert payload["count"] == 1
        assert "token" not in payload["shares"][0]
        assert "token_hint" not in payload["shares"][0]
        assert "url" not in payload["shares"][0]


def test_review_token_recopy_is_job_scoped_and_loopback_only(env):
    manifest = make_artifact(env)
    token, _ = shares.create(
        env.job_id, manifest["artifact_id"], label="Client", path=app.SHARES,
    )
    loopback = TestClient(app.app, client=("127.0.0.1", 51234))
    ipv6 = TestClient(app.app, client=("::1", 51235))
    remote = TestClient(app.app, client=("203.0.113.10", 51236))
    url = f"/api/jobs/{env.job_id}/share-token"

    copied = loopback.post(url, json={"token": token})
    assert copied.status_code == 200, copied.text
    body = copied.json()
    assert body["token"] == token
    assert body["url"] == f"/r/{token}"
    assert body["artifact_id"] == manifest["artifact_id"]
    assert body["label"] == "Client"
    assert ipv6.post(url, json={"token": token}).status_code == 200

    # The normal listing still redacts every token.
    listed = loopback.get("/api/shares").json()
    assert listed["count"] == 1
    assert "token" not in listed["shares"][0]

    other_token, _ = shares.create(
        "job2", manifest["artifact_id"], path=app.SHARES,
    )
    wrong_job = loopback.post(url, json={"token": other_token})
    assert wrong_job.status_code == 404
    assert other_token not in wrong_job.text

    denied = remote.post(url, json={"token": token})
    assert denied.status_code == 403
    assert token not in denied.text

    shares.patch(token, {"expires_at": time.time() - 10}, app.SHARES)
    expired = loopback.post(url, json={"token": token})
    assert expired.status_code == 410
    assert token not in expired.text

    shares.patch(
        token, {"expires_at": time.time() + 3600, "revoked": False}, app.SHARES,
    )
    assert loopback.post(url, json={"token": token}).status_code == 200
    shares.patch(token, {"revoked": True}, app.SHARES)
    revoked = loopback.post(url, json={"token": token})
    assert revoked.status_code == 410
    assert token not in revoked.text


def test_clean_adopts_live_legacy_share_before_deleting_renders(env):
    _prepare_legacy_render(env)
    token = _save_legacy_share(env)
    job = app.load_job(env.job_id)

    removed = app.clean_job_files(job, "renders")

    assert "renders" in removed
    artifact_id = job["artifact_ids"][0]
    assert artifacts.has_media(env.directory, artifact_id)
    assert shares.get(token, app.SHARES)["artifact_id"] == artifact_id
    assert "15" in job["renders"]
    assert not (env.directory / "renders" / "reel_15.mp4").exists()
    app.save_job(job)

    found = app._share(token)
    assert found and found[0]["artifact_id"] == artifact_id
    assert app.review_video(token).path.read_bytes() == b"legacy-mp4"


def test_clean_preserves_unadoptable_legacy_share_target(env, monkeypatch):
    _prepare_legacy_render(env)
    token = _save_legacy_share(env)
    monkeypatch.setattr(app, "_adopt_render_artifact", lambda *args, **kwargs: None)
    job = app.load_job(env.job_id)

    with pytest.raises(HTTPException) as blocked:
        app.clean_job_files(job, "renders")

    assert blocked.value.status_code == 409
    assert (env.directory / "renders" / "reel_15.mp4").is_file()
    assert "15" in job["renders"]
    assert shares.get(token, app.SHARES)["artifact_id"] is None
    client = TestClient(app.app)
    assert client.post(
        f"/api/jobs/{env.job_id}/clean", json={"profile": "renders"},
    ).status_code == 409


def test_corrupt_share_store_blocks_destructive_operations(env, monkeypatch):
    manifest = make_artifact(env)
    artifact_id = manifest["artifact_id"]
    token, _ = shares.create(env.job_id, artifact_id, path=app.SHARES)
    job = app.load_job(env.job_id)
    job["renders"] = {
        "15": {
            "status": "ready",
            "quality": "final",
            "target": 15,
            "aspect": "9:16",
            "captions": False,
            "audio_sig": "",
            "hook": 0,
            "updated": 1.0,
            "path": f"artifacts/{artifact_id}/reel.mp4",
            "poster": f"artifacts/{artifact_id}/poster.jpg",
            "artifact_id": artifact_id,
            "record_key": "15",
        },
    }
    app.save_job(job)
    app.SHARES.write_bytes(b"\xff\xfe\x00")

    assert shares.load(app.SHARES, strict=False) == {}
    with pytest.raises(shares.ShareStoreError):
        shares.load(app.SHARES)
    with pytest.raises(shares.ShareStoreError):
        app._prune_renders(app.load_job(env.job_id))
    assert artifacts.artifact_dir(env.directory, artifact_id).is_dir()
    with pytest.raises(shares.ShareStoreError):
        app.clean_job_files(app.load_job(env.job_id), "renders")
    assert artifacts.artifact_dir(env.directory, artifact_id).is_dir()
    with pytest.raises(shares.ShareStoreError):
        app.clean_job_files(app.load_job(env.job_id), "workfiles")
    assert artifacts.artifact_dir(env.directory, artifact_id).is_dir()

    client = TestClient(app.app)
    assert client.post(
        f"/api/jobs/{env.job_id}/clean", json={"profile": "renders"},
    ).status_code == 503
    assert client.delete(
        f"/api/jobs/{env.job_id}/artifacts/{artifact_id}"
    ).status_code == 503
    assert client.delete(f"/api/jobs/{env.job_id}").status_code == 503
    assert client.delete(f"/api/shares/{token}").status_code == 503
    assert client.get("/api/shares").status_code == 503
    assert client.patch(
        f"/api/shares/{token}", json={"label": "blocked"},
    ).status_code == 503
    assert client.post(
        f"/api/jobs/{env.job_id}/share",
        json={"artifact_id": artifact_id},
    ).status_code == 503
    assert client.get(f"/r/{token}").status_code == 503
    assert env.directory.is_dir()
    assert artifacts.artifact_dir(env.directory, artifact_id).is_dir()

    def age(job: dict) -> None:
        job["updated"] = time.time() - 10 * 86400

    app.update_job(env.job_id, age)
    monkeypatch.setenv("VIBECUT_RETENTION_DAYS", "1")
    app.cleanup_storage()
    assert env.directory.is_dir()


def test_create_share_merges_concurrent_job_update(env, monkeypatch):
    _prepare_legacy_render(env)
    client = TestClient(app.app)
    original = app._find_artifact_for_target

    def find_then_concurrent(*args, **kwargs):
        result = original(*args, **kwargs)
        app.update_job(
            env.job_id,
            lambda job: job.setdefault("renders", {}).__setitem__(
                "concurrent",
                {"status": "ready", "path": "reel_99.mp4", "updated": 2.0},
            ),
        )
        return result

    monkeypatch.setattr(app, "_find_artifact_for_target", find_then_concurrent)
    response = client.post(
        f"/api/jobs/{env.job_id}/share?target=15&aspect=9:16",
    )

    assert response.status_code == 200
    assert response.json()["artifact_id"]
    job = app.load_job(env.job_id)
    assert "concurrent" in job["renders"]


def test_legacy_share_create_persists_adopted_projection(env):
    _prepare_legacy_render(env)
    result = app.create_share(env.job_id, 15, "9:16")
    artifact_id = result["artifact_id"]
    job = app.load_job(env.job_id)
    record = job["renders"]["15"]
    assert record["artifact_id"] == artifact_id
    assert record["record_key"] == "15"
    assert record["resolved_encoder"] in {"videotoolbox", "libx264"}
    assert shares.get(result["token"], app.SHARES)["artifact_id"] == artifact_id


def test_review_page_shows_the_edit_version(env):
    job = app.load_job(env.job_id)
    clips = [{
        "scene": 0, "start": 0.0, "end": 4.0, "dur": 4.0, "role": "hook",
    }]
    edit = edits.build_edit(
        story_ref={
            "set_id": "cs_1",
            "story_id": "story",
            "clip_hash": edits.clip_snapshot_hash(clips),
            "duration": 4.0,
            "clip_count": 1,
        },
        aspect="9:16",
        motion=[{"kind": "punch_in", "start": 0.5, "end": 1.5}],
    )
    edits.save_edit(env.directory, edit)
    job["story_edits"] = {"cs_1:story:9:16": edit["id"]}
    (env.directory / "job.json").write_text(json.dumps(job), encoding="utf-8")

    spec = artifacts.build_spec(
        job,
        {
            "target": 15,
            "clips": clips,
            "story_id": "story",
        },
        story_id="story",
        edit_hash=edit["hash"],
    )
    manifest = artifacts.make_manifest("job1", spec, status="ready", record_key="15")
    manifest["set_id"] = "cs_1"
    manifest = artifacts.assign_version(env.directory, manifest)
    manifest = artifacts.save_manifest(env.directory, manifest)
    artifact_id = manifest["artifact_id"]
    directory = artifacts.artifact_dir(env.directory, artifact_id)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "reel.mp4").write_bytes(b"fake-mp4")
    (directory / "poster.jpg").write_bytes(b"fake-jpg")
    artifacts.write_captions(env.directory, artifact_id, "1\n00:00:00,000 --> 00:00:02,000\nHi\n", "WEBVTT\n")

    token, _ = shares.create("job1", artifact_id, path=app.SHARES)
    client = TestClient(app.app)
    response = client.get(f"/r/{token}")
    assert response.status_code == 200
    assert "Edit v1" in response.text
    assert "v1 · Edit v1 · current" in response.text
    assert manifest["edit_id"] == edit["id"]
