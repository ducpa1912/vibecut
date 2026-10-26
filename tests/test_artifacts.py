"""Immutable artifact identity, manifests, queue reuse and pruning."""

from __future__ import annotations

import copy
import json
import os
import re
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app
import artifacts
import audio
import render
import shares


def scene(index: int, start: float, dur: float, speech: str = "") -> dict:
    return {
        "id": index,
        "start": float(start),
        "end": float(start + dur),
        "dur": float(dur),
        "mid": float(start + dur / 2),
        "hook": 60.0,
        "score": 60.0,
        "deep": True,
        "visual_score": 60.0,
        "motion_score": 60.0,
        "audio_score": 60.0,
        "text_score": 0.0,
        "ocr": "",
        "speech": speech,
        "tags": [],
        "crop": {"cx": 0.5, "cy": 0.5},
        "crop_mode": "center",
    }


def job_record(job_id: str = "job1", root: Path | None = None) -> dict:
    root = root or Path("/tmp")
    return {
        "id": job_id,
        "created": 1.0,
        "updated": 1.0,
        "status": "ready",
        "progress": 1.0,
        "message": "Ready",
        "error": None,
        "source": {
            "path": str(root / "source.mp4"),
            "name": "source.mp4",
            "duration": 60.0,
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "size": 1234,
            "has_audio": True,
            "fingerprint": "source-fingerprint",
        },
        "options": {},
        "analysis": {
            "scene_count": 5,
            "hook_scene": 0,
            "deep_count": 5,
            "deep_scene_ids": [0, 1, 2, 3, 4],
            "engine": {"transcript_language": "en"},
            "scenes": [
                scene(0, 0.0, 4.0, "hello world"),
                scene(1, 4.0, 4.0, "second beat"),
                scene(2, 8.0, 4.0, "third beat"),
                scene(3, 12.0, 4.0, "payoff"),
                scene(4, 16.0, 4.0, "extra"),
            ],
        },
        "renders": {},
    }


def plan_for(hook: int = 0, target: int = 15, auto: bool = False) -> dict:
    return {
        "target": target,
        "total": 4.0,
        "hook_scene": hook,
        "auto": auto,
        "clip_count": 1,
        "clips": [{
            "scene": hook,
            "start": 0.0,
            "end": 4.0,
            "dur": 4.0,
            "role": "hook",
        }],
        "_source_lang": "en",
    }


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
    job = job_record("job1", tmp_path)
    directory = jobs / job["id"]
    directory.mkdir()
    (directory / "job.json").write_text(json.dumps(job), encoding="utf-8")
    return SimpleNamespace(
        tmp_path=tmp_path,
        data=data,
        jobs=jobs,
        directory=directory,
        job=job,
        job_id=job["id"],
    )


def base_spec(**overrides) -> artifacts.ArtifactSpec:
    payload = {
        "schema_version": artifacts.SCHEMA_VERSION,
        "render_version": artifacts.RENDER_VERSION,
        "source_fingerprint": "src1",
        "clips": [
            {"scene": 0, "start": 0.0, "end": 2.5, "dur": 2.5, "role": "hook"},
            {"scene": 1, "start": 5.0, "end": 8.5, "dur": 3.5, "role": "payoff"},
        ],
        "order": "source",
        "hook_scene": 0,
        "hook_override": True,
        "caption": {
            "enabled": True,
            "style_hash": "style1",
            "cue_hash": "cues1",
            "text_hash": "text1",
            "margin": 0.075,
        },
        "audio_sig": "aud1",
        "quality": "final",
        "aspect": "9:16",
        "resolved_encoder": "libx264",
        "story_id": "story1",
        "target": 15,
    }
    payload.update(overrides)
    return artifacts.ArtifactSpec.from_payload(payload)


def make_artifact(
    env,
    spec: artifacts.ArtifactSpec,
    *,
    pinned: bool = False,
    record_key: str = "15",
    created: float | None = None,
    srt: str = "1\n00:00:00,000 --> 00:00:02,000\nsaved cue\n",
) -> dict:
    job_dir = env.directory
    manifest = artifacts.make_manifest(
        env.job_id, spec, status="ready", record_key=record_key, created=created,
    )
    manifest = artifacts.save_manifest(job_dir, manifest)
    artifact_id = manifest["artifact_id"]
    directory = artifacts.artifact_dir(job_dir, artifact_id)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "reel.mp4").write_bytes(b"fake-mp4-" + artifact_id.encode())
    (directory / "poster.jpg").write_bytes(b"fake-jpg")
    artifacts.write_captions(job_dir, artifact_id, srt, "WEBVTT\n\n")
    if pinned:
        manifest = artifacts.pin_artifact(job_dir, artifact_id, True) or manifest
    return manifest


def record_for(manifest: dict, updated: float, record_key: str) -> dict:
    spec = manifest.get("spec") or {}
    caption = spec.get("caption") or {}
    return {
        "status": "ready",
        "quality": spec.get("quality"),
        "target": spec.get("target"),
        "aspect": spec.get("aspect"),
        "captions": bool(caption.get("enabled")),
        "audio_sig": spec.get("audio_sig") or "",
        "hook": spec.get("hook_scene"),
        "updated": updated,
        "path": f"artifacts/{manifest['artifact_id']}/reel.mp4",
        "poster": f"artifacts/{manifest['artifact_id']}/poster.jpg",
        "artifact_id": manifest["artifact_id"],
        "record_key": record_key,
    }


# ---------------------------------------------------------------- identity


def test_artifact_id_is_stable_and_sensitive_to_every_input():
    spec = base_spec()
    first = artifacts.artifact_id(spec)
    assert first.startswith("art_")
    assert len(first) == 4 + 24
    assert first == artifacts.artifact_id(base_spec())

    changes = {
        "schema_version": 2,
        "render_version": "v2",
        "source_fingerprint": "src2",
        "order": "arc",
        "hook_scene": 2,
        "hook_override": False,
        "audio_sig": "aud2",
        "quality": "draft",
        "aspect": "4:5",
        "resolved_encoder": "videotoolbox",
        "story_id": "story2",
        "target": 30,
        "generation": 1,
    }
    for key, value in changes.items():
        assert artifacts.artifact_id(base_spec(**{key: value})) != first, key

    for field, value in {
        "scene": 9,
        "start": 0.5,
        "end": 2.6,
        "dur": 2.0,
        "role": "beat",
    }.items():
        clips = copy.deepcopy(spec.clips)
        clips[0][field] = value
        assert artifacts.artifact_id(base_spec(clips=clips)) != first, field

    for field, value in {
        "enabled": False,
        "style_hash": "style2",
        "cue_hash": "cues2",
        "text_hash": "text2",
        "cue_count": 2,
        "margin": 0.12,
    }.items():
        caption = copy.deepcopy(spec.caption)
        caption[field] = value
        assert artifacts.artifact_id(base_spec(caption=caption)) != first, field


def test_extra_clip_metadata_does_not_change_identity():
    spec = base_spec()
    clips = copy.deepcopy(spec.clips)
    clips[0]["why"] = "explanation only"
    assert artifacts.artifact_id(base_spec(clips=clips)) == artifacts.artifact_id(spec)


def test_build_spec_resolves_encoder_and_hook_override(env):
    job = env.job
    spec = artifacts.build_spec(job, plan_for(), encoder="auto", captions=True)
    assert spec.resolved_encoder in {"videotoolbox", "libx264"}
    assert spec.resolved_encoder != "auto"
    assert spec.hook_override is True
    assert spec.story_id == env.job_id
    assert spec.caption["enabled"] is True
    assert spec.caption["cue_hash"]
    assert spec.caption["text_hash"]

    forced = artifacts.build_spec(job, plan_for(), encoder="videotoolbox")
    assert forced.resolved_encoder == "videotoolbox"
    assert artifacts.artifact_id(forced) != artifacts.artifact_id(spec)


def test_manifest_round_trip_index_and_safe_ids(tmp_path):
    job_dir = tmp_path / "job"
    manifest = artifacts.make_manifest("job1", base_spec(), record_key="15")
    saved = artifacts.save_manifest(job_dir, manifest)
    artifact_id = saved["artifact_id"]

    path = artifacts.manifest_path(job_dir, artifact_id)
    assert path == job_dir / "artifacts" / artifact_id / "manifest.json"
    loaded = artifacts.load_manifest(job_dir, artifact_id)
    assert loaded and loaded["artifact_id"] == artifact_id
    assert loaded["spec"]["resolved_encoder"] == "libx264"

    index = artifacts.load_index(job_dir)
    assert index["artifact_ids"] == [artifact_id]
    assert index["artifacts"][artifact_id]["target"] == 15

    with pytest.raises(artifacts.ArtifactError):
        artifacts.manifest_path(job_dir, "../../escape")
    assert artifacts.load_manifest(job_dir, "../../escape") is None
    assert artifacts.is_safe_artifact_id(artifact_id)

    assert artifacts.delete_artifact(job_dir, artifact_id)
    assert not artifacts.artifact_dir(job_dir, artifact_id).exists()
    assert artifacts.load_index(job_dir)["artifact_ids"] == []


# ---------------------------------------------------------------- render queue


def test_queue_reuses_artifact_and_ready_render_keeps_projection(env, monkeypatch):
    submitted = []
    monkeypatch.setattr(
        app.render_pool, "submit",
        lambda *args, **kwargs: submitted.append((args, kwargs)),
    )
    job = app.load_job(env.job_id)
    plan = plan_for()
    first = app._queue_render(
        env.job_id, job, plan, "final", "9:16", None, False, None, False,
    )
    artifact_id = first["artifact_id"]
    assert artifacts.is_safe_artifact_id(artifact_id)
    assert len(submitted) == 1
    manifest = artifacts.load_manifest(env.directory, artifact_id)
    assert manifest and manifest["status"] == "queued"

    again = app._queue_render(
        env.job_id, app.load_job(env.job_id), plan, "final", "9:16",
        None, False, None, False,
    )
    assert again["artifact_id"] == artifact_id
    assert len(submitted) == 1

    def fake_render_reel(source, meta, job_dir, plan, title, progress, **kwargs):
        renders = job_dir / "renders"
        renders.mkdir(parents=True, exist_ok=True)
        (renders / "reel_15.mp4").write_bytes(b"fake-mp4")
        (renders / "reel_15.jpg").write_bytes(b"fake-jpg")
        progress(1.0, "Reel ready")
        return {
            "path": "reel_15.mp4",
            "poster": "reel_15.jpg",
            "duration": 4.0,
            "width": 1080,
            "height": 1920,
            "size": 9,
            "has_audio": True,
            "clip_count": 1,
            "quality": "final",
            "aspect": "9:16",
            "encoder": "libx264",
            "captions": False,
            "caption_count": 0,
            "cached": 0,
            "used_assets": [],
        }

    monkeypatch.setattr(render, "render_reel", fake_render_reel)
    app.run_render(
        env.job_id, 15, plan, first["key"], quality="final", aspect="9:16",
        artifact_id=artifact_id,
    )
    stored = app.load_job(env.job_id)
    assert stored["renders"]["15:h0"]["status"] == "ready"
    assert stored["renders"]["15:h0"]["artifact_id"] == artifact_id
    manifest = artifacts.load_manifest(env.directory, artifact_id)
    assert manifest["status"] == "ready"
    assert artifacts.has_media(env.directory, artifact_id, "reel.mp4")
    assert "saved cue" not in artifacts.media_path(
        env.directory, artifact_id, "captions.srt",
    ).read_text(encoding="utf-8")
    assert "hello world" in artifacts.media_path(
        env.directory, artifact_id, "captions.srt",
    ).read_text(encoding="utf-8")
    assert artifacts.media_path(
        env.directory, artifact_id, "captions.vtt",
    ).read_text(encoding="utf-8").startswith("WEBVTT")

    ready_again = app._queue_render(
        env.job_id, app.load_job(env.job_id), plan, "final", "9:16",
        None, False, None, False,
    )
    assert ready_again["artifact_id"] == artifact_id
    assert len(submitted) == 1

    changed = plan_for()
    changed["clips"][0]["end"] = 3.0
    changed["clips"][0]["dur"] = 3.0
    changed["total"] = 3.0
    newer = app._queue_render(
        env.job_id, app.load_job(env.job_id), changed, "final", "9:16",
        None, False, None, False,
    )
    assert newer["artifact_id"] != artifact_id
    assert len(submitted) == 2


def test_queue_adopts_legacy_ready_render_without_rerendering(env, monkeypatch):
    submitted = []
    monkeypatch.setattr(
        app.render_pool, "submit",
        lambda *args, **kwargs: submitted.append((args, kwargs)),
    )
    job = app.load_job(env.job_id)
    plan = plan_for()
    job["analysis"]["plans"] = {"15": plan}
    renders = env.directory / "renders"
    renders.mkdir()
    (renders / "reel_15.mp4").write_bytes(b"legacy-mp4")
    (renders / "reel_15.jpg").write_bytes(b"legacy-jpg")
    job["renders"] = {
        "15:h0": {
            "status": "ready",
            "quality": "final",
            "target": 15,
            "aspect": "9:16",
            "captions": False,
            "audio_sig": "",
            "hook": 0,
            "updated": 1.0,
            "path": "reel_15.mp4",
            "poster": "reel_15.jpg",
            "record_key": "15:h0",
            "key": "legacy",
        },
    }
    app.save_job(job)

    reused = app._queue_render(
        env.job_id, app.load_job(env.job_id), plan, "final", "9:16",
        None, False, None, False,
    )
    assert reused["status"] == "ready"
    assert artifacts.is_safe_artifact_id(reused["artifact_id"])
    assert submitted == []
    manifest = artifacts.load_manifest(env.directory, reused["artifact_id"])
    assert manifest and manifest["status"] == "ready"
    assert app.load_job(env.job_id)["renders"]["15:h0"]["artifact_id"] == (
        reused["artifact_id"]
    )


# ---------------------------------------------------------------- pruning


def test_prune_preserves_hooks_pins_and_shares(env, monkeypatch):
    monkeypatch.setenv("VIBECUT_KEEP_RENDERS", "1")
    monkeypatch.setenv("VIBECUT_KEEP_DRAFTS", "0")
    job = env.job

    def variant(hook: int, speech: str) -> artifacts.ArtifactSpec:
        local = copy.deepcopy(job)
        local["analysis"]["scenes"][hook]["speech"] = speech
        return artifacts.build_spec(local, plan_for(hook=hook), captions=False)

    new_hook0 = make_artifact(env, variant(0, "new hook"), record_key="new0")
    pinned_hook0 = make_artifact(
        env, variant(0, "pinned hook"), pinned=True, record_key="pin0",
    )
    hook1 = make_artifact(env, variant(1, "hook one"), record_key="h1")
    shared = make_artifact(env, variant(2, "shared hook"), record_key="shared")
    loser_new = make_artifact(env, variant(3, "new loser"), record_key="loser-new")
    loser_old = make_artifact(env, variant(3, "old loser"), record_key="loser-old")

    shares.create("job1", shared["artifact_id"], path=app.SHARES)
    job["renders"] = {
        "new0": record_for(new_hook0, 10.0, "new0"),
        "pin0": record_for(pinned_hook0, 1.0, "pin0"),
        "h1": record_for(hook1, 2.0, "h1"),
        "shared": record_for(shared, 1.0, "shared"),
        "loser-new": record_for(loser_new, 10.0, "loser-new"),
        "loser-old": record_for(loser_old, 1.0, "loser-old"),
    }
    removed = app._prune_renders(job)

    assert set(job["renders"]) == {"new0", "pin0", "h1", "shared", "loser-new"}
    assert "loser-old" not in job["renders"]
    assert artifacts.artifact_dir(env.directory, new_hook0["artifact_id"]).is_dir()
    assert artifacts.artifact_dir(env.directory, pinned_hook0["artifact_id"]).is_dir()
    assert artifacts.artifact_dir(env.directory, hook1["artifact_id"]).is_dir()
    assert artifacts.artifact_dir(env.directory, shared["artifact_id"]).is_dir()
    assert not artifacts.artifact_dir(env.directory, loser_old["artifact_id"]).exists()
    assert removed
    assert set(job["artifact_ids"]) == {
        new_hook0["artifact_id"], pinned_hook0["artifact_id"],
        hook1["artifact_id"], shared["artifact_id"], loser_new["artifact_id"],
    }


def test_clean_keeps_pinned_shared_and_packet_artifacts(env):
    job = env.job
    pinned = make_artifact(env, artifacts.build_spec(job, plan_for(0)), pinned=True)
    shared = make_artifact(env, artifacts.build_spec(job, plan_for(1)))
    packet = make_artifact(env, artifacts.build_spec(job, plan_for(2)))
    loose = make_artifact(env, artifacts.build_spec(job, plan_for(3)))
    shares.create("job1", shared["artifact_id"], path=app.SHARES)
    job["packet"] = {"artifact_id": packet["artifact_id"]}
    job["renders"] = {
        key: record_for(manifest, 1.0, key)
        for key, manifest in (
            ("pin", pinned), ("shared", shared), ("packet", packet), ("loose", loose),
        )
    }
    (env.directory / "renders").mkdir(exist_ok=True)

    removed = app.clean_job_files(job, "renders")

    assert "artifacts" in removed
    assert "renders" in removed
    for manifest in (pinned, shared, packet):
        assert artifacts.artifact_dir(env.directory, manifest["artifact_id"]).is_dir()
    assert not artifacts.artifact_dir(env.directory, loose["artifact_id"]).exists()
    assert set(job["artifact_ids"]) == {
        pinned["artifact_id"], shared["artifact_id"], packet["artifact_id"],
    }
    assert len(job["renders"]) == 3
    assert {
        record["artifact_id"] for record in job["renders"].values()
    } == {pinned["artifact_id"], shared["artifact_id"], packet["artifact_id"]}


# ---------------------------------------------------------------- legacy


def test_legacy_v013_job_load_adds_schema_without_breaking(env):
    legacy = {
        "id": env.job_id,
        "status": "ready",
        "source": {"name": "old.mp4", "duration": 12.0},
        "analysis": {"scenes": [], "hook_scene": None},
        "renders": {"15": {"status": "ready", "path": "reel_15.mp4", "updated": 1}},
    }
    (env.directory / "job.json").write_text(json.dumps(legacy), encoding="utf-8")

    loaded = app.load_job(env.job_id)
    assert loaded["schema_version"] == artifacts.SCHEMA_VERSION
    assert loaded["render_version"] == artifacts.RENDER_VERSION
    assert loaded["story_id"] == env.job_id
    assert loaded["artifacts"] == {}
    assert loaded["artifact_ids"] == []
    assert loaded["renders"]["15"]["path"] == "reel_15.mp4"

    status = app.public_status(loaded)
    assert status["artifact_ids"] == []
    assert status["renders"]["15"]["status"] == "ready"


def test_legacy_renders_projection_stays_in_public_job(env):
    legacy = app.load_job(env.job_id)
    legacy["renders"] = {
        "15": {
            "status": "ready", "path": "reel_15.mp4", "poster": "reel_15.jpg",
            "updated": 1.0, "key": "legacy",
        },
    }
    app.save_job(legacy)

    public = app.public_job(app.load_job(env.job_id))
    assert public["artifact_ids"] == []
    assert public["artifacts"] == {}
    assert public["renders"]["15"]["status"] == "ready"
    assert public["renders"]["15"]["path"] == "reel_15.mp4"
    assert public["renders"]["15"]["url"].startswith(
        f"/api/jobs/{env.job_id}/media/reel_15.mp4"
    )


# ---------------------------------------------------------------- QA round 1


def test_artifacts_endpoint_adopts_ready_legacy_render_once(env):
    job = app.load_job(env.job_id)
    job["analysis"]["plans"] = {"15": plan_for()}
    renders = env.directory / "renders"
    renders.mkdir()
    (renders / "reel_15.mp4").write_bytes(b"legacy-mp4")
    (renders / "reel_15.jpg").write_bytes(b"legacy-jpg")
    job["renders"] = {
        "15:h0": {
            "status": "ready",
            "quality": "final",
            "target": 15,
            "aspect": "9:16",
            "captions": False,
            "audio_sig": "",
            "hook": 0,
            "updated": 1.0,
            "path": "reel_15.mp4",
            "poster": "reel_15.jpg",
            "record_key": "15:h0",
            "key": "legacy",
        },
    }
    app.save_job(job)

    client = TestClient(app.app)
    first = client.get(f"/api/jobs/{env.job_id}/artifacts")
    assert first.status_code == 200
    body = first.json()
    assert len(body["adopted"]) == 1
    adopted = body["adopted"][0]
    artifact_id = adopted["artifact_id"]
    assert body["adopted_ids"] == [artifact_id]
    assert body["artifact_ids"] == [artifact_id]
    assert body["artifacts"][0]["source_fingerprint"]

    manifest = artifacts.load_manifest(env.directory, artifact_id)
    assert manifest is not None
    assert manifest["status"] == "ready"
    assert manifest["spec"]["target"] == 15
    assert artifacts.has_media(env.directory, artifact_id, "reel.mp4")
    stored = app.load_job(env.job_id)
    assert stored["renders"]["15:h0"]["artifact_id"] == artifact_id
    assert stored["artifacts"][artifact_id]["status"] == "ready"

    second = client.get(f"/api/jobs/{env.job_id}/artifacts")
    assert second.status_code == 200
    again = second.json()
    assert again["adopted"] == []
    assert again["adopted_ids"] == []
    assert again["artifact_ids"] == [artifact_id]
    assert len(artifacts.list_manifests(env.directory)) == 1
    assert app.load_job(env.job_id)["renders"]["15:h0"]["artifact_id"] == (
        artifact_id
    )


def test_artifacts_endpoint_ignores_unready_and_failed_legacy_renders(env):
    job = app.load_job(env.job_id)
    job["analysis"]["plans"] = {
        "30": plan_for(target=30),
        "60": plan_for(target=60),
    }
    renders = env.directory / "renders"
    renders.mkdir()
    (renders / "reel_30.mp4").write_bytes(b"unfinished")
    (renders / "reel_60.mp4").write_bytes(b"failed")
    job["renders"] = {
        "30:h0": {
            "status": "rendering",
            "quality": "final",
            "target": 30,
            "aspect": "9:16",
            "hook": 0,
            "path": "reel_30.mp4",
            "record_key": "30:h0",
        },
        "60:h0": {
            "status": "failed",
            "quality": "final",
            "target": 60,
            "aspect": "9:16",
            "hook": 0,
            "path": "reel_60.mp4",
            "record_key": "60:h0",
            "error": "ffmpeg failed",
        },
        "15:h0": {
            "status": "ready",
            "quality": "final",
            "target": 15,
            "aspect": "9:16",
            "hook": 0,
            "path": "missing.mp4",
            "record_key": "15:h0",
        },
    }
    before = copy.deepcopy(job["renders"])
    app.save_job(job)

    response = TestClient(app.app).get(f"/api/jobs/{env.job_id}/artifacts")
    assert response.status_code == 200
    body = response.json()
    assert body["adopted"] == []
    assert body["artifact_ids"] == []
    assert body["artifacts"] == []
    assert artifacts.list_manifests(env.directory) == []
    assert app.load_job(env.job_id)["renders"] == before


def test_adoption_does_not_overwrite_existing_pinned_manifest(env):
    job = app.load_job(env.job_id)
    plan = plan_for()
    job["analysis"]["plans"] = {"15": plan}
    renders = env.directory / "renders"
    renders.mkdir()
    (renders / "reel_15.mp4").write_bytes(b"legacy-mp4")
    (renders / "reel_15.jpg").write_bytes(b"legacy-jpg")
    record = {
        "status": "ready",
        "quality": "final",
        "target": 15,
        "aspect": "9:16",
        "captions": False,
        "audio_sig": "",
        "hook": 0,
        "updated": 1.0,
        "path": "reel_15.mp4",
        "poster": "reel_15.jpg",
    }
    spec = artifacts.build_spec(
        job, plan, quality="final", aspect="9:16", captions=False,
    )
    manifest = artifacts.make_manifest(
        env.job_id, spec, status="ready", record_key="15",
        title="pinned-original", created=1.0,
    )
    manifest = artifacts.save_manifest(env.directory, manifest)
    manifest = artifacts.pin_artifact(
        env.directory, manifest["artifact_id"], True,
    )
    before = artifacts.load_manifest(env.directory, manifest["artifact_id"])

    adopted = app._adopt_render_artifact(job, record, 15, "9:16")

    after = artifacts.load_manifest(env.directory, manifest["artifact_id"])
    assert adopted and adopted["artifact_id"] == manifest["artifact_id"]
    assert after["pinned"] is True
    assert after["title"] == "pinned-original"
    assert after["created"] == before["created"]
    assert after["updated"] == before["updated"]
    assert record["artifact_id"] == manifest["artifact_id"]


def test_public_render_falls_back_when_artifact_media_missing(env):
    job = app.load_job(env.job_id)
    spec = artifacts.build_spec(job, plan_for(), captions=False)
    manifest = artifacts.make_manifest(
        env.job_id, spec, status="ready", record_key="15",
    )
    manifest = artifacts.save_manifest(env.directory, manifest)
    record = record_for(manifest, 1.0, "15")
    record["path"] = "reel_15.mp4"
    record["poster"] = "reel_15.jpg"
    record["key"] = "legacy"

    public = app._public_render(env.job_id, record)
    assert public["url"] == (
        f"/api/jobs/{env.job_id}/media/reel_15.mp4?v=legacy"
    )
    assert public["poster_url"] == (
        f"/api/jobs/{env.job_id}/media/reel_15.jpg?v=legacy"
    )
    prefixed = {
        **record,
        "path": "renders/reel_15.mp4",
        "poster": "renders/reel_15.jpg",
    }
    assert app._public_render(env.job_id, prefixed)["url"] == (
        f"/api/jobs/{env.job_id}/media/reel_15.mp4?v=legacy"
    )

    artifact_dir = artifacts.artifact_dir(env.directory, manifest["artifact_id"])
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "reel.mp4").write_bytes(b"artifact-mp4")
    ready = app._public_render(env.job_id, record)
    assert ready["url"].startswith(
        f"/api/jobs/{env.job_id}/artifacts/{manifest['artifact_id']}/media/reel.mp4"
    )


def test_media_path_helpers_reject_escapes_and_unknown_roots(env):
    job_dir = env.directory
    (job_dir / "source.mp4").write_bytes(b"source")
    thumbs = job_dir / "thumbs"
    thumbs.mkdir()
    (thumbs / "00000.jpg").write_bytes(b"thumb")

    assert app._record_media_path(job_dir, {"path": "thumbs/00000.jpg"}) is None
    assert app._record_media_path(job_dir, {"path": "../source.mp4"}) is None
    assert app._record_media_path(
        job_dir, {"path": "artifacts/not-an-artifact/reel.mp4"},
    ) is None
    assert app._safe_unlink(job_dir, "thumbs/00000.jpg") is None
    assert app._safe_unlink(job_dir, "../source.mp4") is None
    assert (thumbs / "00000.jpg").is_file()
    assert (job_dir / "source.mp4").is_file()

    renders = job_dir / "renders"
    renders.mkdir()
    reel = renders / "reel_15.mp4"
    reel.write_bytes(b"legacy")
    assert app._record_media_path(job_dir, {"path": "reel_15.mp4"}) == reel.resolve()
    assert app._safe_unlink(job_dir, "reel_15.mp4") == "reel_15.mp4"
    assert not reel.exists()

    artifact_id = "art_" + "a" * 24
    artifact_dir = artifacts.artifact_dir(job_dir, artifact_id)
    artifact_dir.mkdir(parents=True)
    artifact_reel = artifact_dir / "reel.mp4"
    artifact_reel.write_bytes(b"artifact")
    (artifact_dir / "manifest.json").write_text("{}", encoding="utf-8")
    assert app._record_media_path(
        job_dir, {"path": f"artifacts/{artifact_id}/reel.mp4"},
    ) == artifact_reel.resolve()
    assert app._record_media_path(
        job_dir, {"path": f"artifacts/{artifact_id}/manifest.json"},
    ) is None
    assert app._record_media_path(
        job_dir, {"path": f"artifacts/{artifact_id}/other.mp4"},
    ) is None
    assert app._safe_unlink(
        job_dir, f"artifacts/{artifact_id}/manifest.json",
    ) is None
    assert (artifact_dir / "manifest.json").is_file()


def test_manifest_load_rejects_tampered_id_and_bad_utf8(tmp_path):
    job_dir = tmp_path / "job"
    manifest = artifacts.make_manifest("job1", base_spec(), record_key="15")
    artifacts.save_manifest(job_dir, manifest)
    path = artifacts.manifest_path(job_dir, manifest["artifact_id"])
    original = json.loads(path.read_text(encoding="utf-8"))

    tampered = json.loads(json.dumps(original))
    tampered["spec"]["audio_sig"] = "tampered"
    path.write_text(json.dumps(tampered), encoding="utf-8")
    assert artifacts.load_manifest(job_dir, manifest["artifact_id"]) is None

    declared = json.loads(json.dumps(original))
    declared["artifact_id"] = "art_" + "b" * 24
    path.write_text(json.dumps(declared), encoding="utf-8")
    assert artifacts.load_manifest(job_dir, manifest["artifact_id"]) is None

    path.write_bytes(b"\xff\xfe\x00")
    assert artifacts.load_manifest(job_dir, manifest["artifact_id"]) is None


def test_pin_and_delete_serialize_on_artifact_lock(env, monkeypatch):
    manifest = make_artifact(env, artifacts.build_spec(env.job, plan_for()))
    artifact_id = manifest["artifact_id"]
    original = artifacts.pin_artifact
    entered = threading.Event()
    release = threading.Event()

    def slow_pin(job_dir, wanted, pinned=True):
        entered.set()
        assert release.wait(3)
        return original(job_dir, wanted, pinned)

    monkeypatch.setattr(artifacts, "pin_artifact", slow_pin)
    outcomes: dict = {}

    def do_pin():
        try:
            outcomes["pin"] = app.pin_artifact(env.job_id, artifact_id)
        except app.HTTPException as exc:
            outcomes["pin_error"] = exc.status_code

    pin_thread = threading.Thread(target=do_pin)
    pin_thread.start()
    assert entered.wait(3)

    def do_delete():
        try:
            outcomes["delete"] = app.delete_artifact(env.job_id, artifact_id)
        except app.HTTPException as exc:
            outcomes["delete_error"] = exc.status_code

    delete_thread = threading.Thread(target=do_delete)
    delete_thread.start()
    time.sleep(0.05)
    assert delete_thread.is_alive(), "delete escaped the pin transaction"
    release.set()
    pin_thread.join(5)
    delete_thread.join(5)
    assert not pin_thread.is_alive()
    assert not delete_thread.is_alive()
    assert "pin_error" not in outcomes
    assert outcomes.get("delete_error") == 409
    stored = artifacts.load_manifest(env.directory, artifact_id)
    assert stored is not None and stored["pinned"] is True


def test_mutating_routes_never_save_a_stale_job_snapshot(env, monkeypatch):
    manifest = make_artifact(env, artifacts.build_spec(env.job, plan_for()))
    artifact_id = manifest["artifact_id"]
    client = TestClient(app.app)

    def forbidden(job):
        raise AssertionError("save_job would overwrite concurrent updates")

    monkeypatch.setattr(app, "save_job", forbidden)
    assert client.post(
        f"/api/jobs/{env.job_id}/artifacts/{artifact_id}/pin",
    ).status_code == 200
    assert client.post(
        f"/api/jobs/{env.job_id}/artifacts/{artifact_id}/pin",
        json={"pinned": False},
    ).status_code == 200
    assert client.delete(
        f"/api/jobs/{env.job_id}/artifacts/{artifact_id}"
    ).status_code == 200
    assert client.post(
        f"/api/jobs/{env.job_id}/clean", json={"profile": "renders"},
    ).status_code == 200


# ---------------------------------------------------------------- co-sign blockers


def _parse_srt(text: str) -> list[dict]:
    cues = []
    for block in text.strip().split("\n\n"):
        lines = block.splitlines()
        if len(lines) < 3:
            continue
        match = re.match(
            r"(\d\d):(\d\d):(\d\d),(\d{3}) --> (\d\d):(\d\d):(\d\d),(\d{3})",
            lines[1],
        )
        if not match:
            continue
        values = [int(value) for value in match.groups()]
        start = values[0] * 3600 + values[1] * 60 + values[2] + values[3] / 1000
        end = values[4] * 3600 + values[5] * 60 + values[6] + values[7] / 1000
        cues.append({"start": start, "end": end, "text": "\n".join(lines[2:])})
    return cues


def test_caption_cue_parity_end_to_end(env, monkeypatch):
    job = app.load_job(env.job_id)
    job["analysis"]["scenes"][0]["speech"] = (
        "This is a deliberately long speech line that must split into several "
        "caption chunks before the render burns it, so the artifact and the "
        "SRT describe exactly the same cues."
    )
    app.save_job(job)
    job = app.load_job(env.job_id)
    plan = app._plan_for(job, 15, None)
    submitted = []
    monkeypatch.setattr(
        app.render_pool, "submit",
        lambda *args, **kwargs: submitted.append((args, kwargs)),
    )
    burned: list[tuple[float, float, str]] = []

    def fake_render_reel(source, meta, job_dir, plan, title, progress, **kwargs):
        burned.extend(kwargs.get("caption_cues") or [])
        renders = job_dir / "renders"
        renders.mkdir(parents=True, exist_ok=True)
        tmp = renders / ".reel-15.tmp.mp4"
        tmp.write_bytes(b"fake-mp4")
        os.replace(tmp, renders / "reel_15.mp4")
        poster = renders / ".reel-15.tmp.jpg"
        poster.write_bytes(b"fake-jpg")
        os.replace(poster, renders / "reel_15.jpg")
        progress(1.0, "Reel ready")
        return {
            "path": "reel_15.mp4",
            "poster": "reel_15.jpg",
            "duration": float(plan["total"]),
            "width": 1080,
            "height": 1920,
            "size": 9,
            "has_audio": True,
            "clip_count": len(plan["clips"]),
            "quality": "final",
            "aspect": "9:16",
            "encoder": "libx264",
            "captions": True,
            "caption_count": len(burned),
            "cached": 0,
            "used_assets": [],
        }

    monkeypatch.setattr(render, "render_reel", fake_render_reel)
    record = app._queue_render(
        env.job_id, job, plan, "final", "9:16", None, True, None, False,
    )
    app.run_render(
        env.job_id, 15, plan, record["key"], quality="final", aspect="9:16",
        captions=True, artifact_id=record["artifact_id"],
        generation=record["generation"],
    )

    artifact_id = record["artifact_id"]
    manifest = artifacts.load_manifest(env.directory, artifact_id)
    srt_text = artifacts.media_path(
        env.directory, artifact_id, "captions.srt",
    ).read_text(encoding="utf-8")
    vtt_text = artifacts.media_path(
        env.directory, artifact_id, "captions.vtt",
    ).read_text(encoding="utf-8")
    srt_cues = _parse_srt(srt_text)
    burned_cues = [
        {"start": round(start, 3), "end": round(end, 3), "text": text}
        for start, end, text in burned
    ]

    assert len(burned_cues) > 1
    assert len(srt_cues) == len(burned_cues)
    assert srt_cues == burned_cues
    assert vtt_text.count("-->") == len(burned_cues)
    spec = manifest["spec"]
    caption = spec["caption"]
    cue_hash, text_hash = artifacts.cue_hashes(burned_cues)
    assert caption["cue_count"] == len(burned_cues)
    assert caption["cue_hash"] == cue_hash
    assert caption["text_hash"] == text_hash
    assert manifest["render"]["caption_count"] == len(burned_cues)
    assert app.export_cut(env.job_id, "srt", target=15).body.decode("utf-8") == srt_text
    assert app.export_cut(
        env.job_id, "srt", artifact_id=artifact_id,
    ).body.decode("utf-8") == srt_text


def test_force_render_creates_new_artifact_and_preserves_shared_bytes(env, monkeypatch):
    job = app.load_job(env.job_id)
    plan = plan_for()
    submitted = []
    monkeypatch.setattr(
        app.render_pool, "submit",
        lambda *args, **kwargs: submitted.append((args, kwargs)),
    )
    state = {"bytes": b"original"}

    def fake_render_reel(source, meta, job_dir, plan, title, progress, **kwargs):
        renders = job_dir / "renders"
        renders.mkdir(parents=True, exist_ok=True)
        tmp = renders / ".force-tmp.mp4"
        tmp.write_bytes(state["bytes"])
        os.replace(tmp, renders / "reel_15.mp4")
        poster = renders / ".force-tmp.jpg"
        poster.write_bytes(b"poster")
        os.replace(poster, renders / "reel_15.jpg")
        progress(1.0, "Reel ready")
        return {
            "path": "reel_15.mp4",
            "poster": "reel_15.jpg",
            "duration": 4.0,
            "width": 1080,
            "height": 1920,
            "size": 9,
            "has_audio": True,
            "clip_count": 1,
            "quality": "final",
            "aspect": "9:16",
            "encoder": "libx264",
            "captions": False,
            "caption_count": len(kwargs.get("caption_cues") or []),
            "cached": 0,
            "used_assets": [],
        }

    monkeypatch.setattr(render, "render_reel", fake_render_reel)
    first = app._queue_render(
        env.job_id, job, plan, "final", "9:16", None, False, None, False,
    )
    app.run_render(
        env.job_id, 15, plan, first["key"], quality="final", aspect="9:16",
        artifact_id=first["artifact_id"], generation=first["generation"],
    )
    artifact_a = first["artifact_id"]
    manifest_a = artifacts.load_manifest(env.directory, artifact_a)
    token = app.create_share(
        env.job_id, body=app.ShareBody(artifact_id=artifact_a),
    )["token"]
    assert app.review_video(token).path.read_bytes() == b"original"

    state["bytes"] = b"forced"
    forced = app._queue_render(
        env.job_id, app.load_job(env.job_id), plan,
        "final", "9:16", None, False, None, True,
    )
    artifact_b = forced["artifact_id"]
    assert artifact_b != artifact_a
    assert forced["generation"] == 1
    pending = artifacts.load_manifest(env.directory, artifact_b)
    assert pending["status"] == "queued"
    assert not artifacts.has_media(env.directory, artifact_b)

    with pytest.raises(app.HTTPException) as blocked:
        app.create_share(
            env.job_id, body=app.ShareBody(artifact_id=artifact_b),
        )
    assert blocked.value.status_code == 409
    assert app.review_video(token).path.read_bytes() == b"original"

    app.run_render(
        env.job_id, 15, plan, forced["key"], quality="final", aspect="9:16",
        artifact_id=artifact_b,
    )

    ready_b = artifacts.load_manifest(env.directory, artifact_b)
    ready_a = artifacts.load_manifest(env.directory, artifact_a)
    assert ready_b["status"] == "ready"
    assert artifacts.media_path(
        env.directory, artifact_b, "reel.mp4",
    ).read_bytes() == b"forced"
    assert artifacts.media_path(
        env.directory, artifact_a, "reel.mp4",
    ).read_bytes() == b"original"
    assert ready_a["updated"] == manifest_a["updated"]
    found = app._share(token)
    assert found and found[0]["artifact_id"] == artifact_a
    assert app.review_video(token).path.read_bytes() == b"original"


def test_share_publication_revalidates_after_artifact_disappears(env, monkeypatch):
    manifest = make_artifact(env, artifacts.build_spec(env.job, plan_for()))
    artifact_id = manifest["artifact_id"]
    original = app._ready_manifest
    calls = {"count": 0}

    def race(job, wanted):
        result = original(job, wanted)
        calls["count"] += 1
        if calls["count"] == 1:
            artifacts.media_path(env.directory, wanted, "reel.mp4").unlink()
        return result

    monkeypatch.setattr(app, "_ready_manifest", race)
    with pytest.raises(app.HTTPException) as blocked:
        app.create_share(
            env.job_id, body=app.ShareBody(artifact_id=artifact_id),
        )
    assert blocked.value.status_code == 409
    assert shares.load(app.SHARES, strict=False) == {}


def test_cleanup_storage_workfiles_does_not_save_snapshot(env, monkeypatch):
    job = app.load_job(env.job_id)
    job["updated"] = time.time() - 10 * 86400
    (env.directory / "job.json").write_text(json.dumps(job), encoding="utf-8")
    thumbs = env.directory / "thumbs"
    thumbs.mkdir()
    (thumbs / "00000.jpg").write_bytes(b"thumb")
    monkeypatch.setattr(audio, "CACHE", env.tmp_path / "cache")
    monkeypatch.setenv("VIBECUT_RETENTION_DAYS", "0")
    monkeypatch.setenv("VIBECUT_JOB_CLEAN_DAYS", "1")
    monkeypatch.setenv("VIBECUT_CACHE_DAYS", "0")

    def forbidden(job):
        raise AssertionError("cleanup_storage saved a stale snapshot")

    monkeypatch.setattr(app, "save_job", forbidden)
    app.cleanup_storage()
    assert not thumbs.exists()


def test_cleanup_storage_prune_merges_concurrent_update(env, monkeypatch):
    job = app.load_job(env.job_id)
    job["updated"] = time.time() - 10 * 86400
    job["renders"] = {
        "15": {"status": "ready", "path": "reel_15.mp4", "updated": 1.0},
    }
    (env.directory / "job.json").write_text(json.dumps(job), encoding="utf-8")
    monkeypatch.setattr(audio, "CACHE", env.tmp_path / "cache")
    monkeypatch.setenv("VIBECUT_RETENTION_DAYS", "0")
    monkeypatch.setenv("VIBECUT_JOB_CLEAN_DAYS", "0")
    monkeypatch.setenv("VIBECUT_CACHE_DAYS", "0")

    started = threading.Event()
    release = threading.Event()

    def fake_prune(current):
        started.set()
        assert release.wait(3)
        current["renders"].pop("15", None)
        return ["reel_15.mp4"]

    monkeypatch.setattr(app, "_prune_renders", fake_prune)

    def run_cleanup():
        app.cleanup_storage()

    cleanup_thread = threading.Thread(target=run_cleanup)
    cleanup_thread.start()
    assert started.wait(3)

    update_started = threading.Event()

    def run_update():
        update_started.set()
        app.update_job(
            env.job_id,
            lambda current: current.__setitem__("message", "concurrent"),
        )

    update_thread = threading.Thread(target=run_update)
    update_thread.start()
    assert update_started.wait(3)
    time.sleep(0.05)
    release.set()
    update_thread.join(5)
    cleanup_thread.join(5)
    assert not update_thread.is_alive()
    assert not cleanup_thread.is_alive()

    stored = app.load_job(env.job_id)
    assert stored["message"] == "concurrent"
    assert "15" not in stored["renders"]


def test_beat_sync_cues_follow_final_frame_snapped_clips(env, monkeypatch):
    job = app.load_job(env.job_id)
    job["analysis"]["scenes"][0]["speech"] = (
        "A long opening line that will be split across several caption chunks "
        "after the first clip is snapped from four seconds to three point seven five."
    )
    app.save_job(job)
    job = app.load_job(env.job_id)
    plan = {
        "target": 15,
        "total": 8.02,
        "hook_scene": 0,
        "auto": False,
        "clip_count": 2,
        "clips": [
            {"scene": 0, "start": 0.0, "end": 4.01, "dur": 4.01, "role": "hook"},
            {"scene": 1, "start": 5.0, "end": 9.01, "dur": 4.01, "role": "payoff"},
        ],
        "_source_lang": "en",
    }
    audio_plan = {
        "mode": "full",
        "beat_sync": True,
        "music": {"source": "cc0", "track": "bed"},
    }
    grid_calls = {"count": 0}
    monkeypatch.setattr(
        audio, "resolve_music_track", lambda *args, **kwargs: Path("/tmp/bed.mp3"),
    )

    def fake_grid(track):
        grid_calls["count"] += 1
        return {"bpm": 160.0, "beats": [0.0, 3.75, 7.75, 11.75]}

    monkeypatch.setattr(audio, "beat_grid", fake_grid)
    submitted = []

    def fake_submit(fn, *args, **kwargs):
        submitted.append((fn, args, kwargs))

    monkeypatch.setattr(app.render_pool, "submit", fake_submit)
    captured: dict = {}

    def fake_render_reel(source, meta, job_dir, plan, title, progress, **kwargs):
        captured["clips"] = [dict(clip) for clip in kwargs.get("render_clips") or []]
        captured["cues"] = list(kwargs.get("caption_cues") or [])
        renders = job_dir / "renders"
        renders.mkdir(parents=True, exist_ok=True)
        tmp = renders / ".beatsync-tmp.mp4"
        tmp.write_bytes(b"beat-mp4")
        os.replace(tmp, renders / "reel_15.mp4")
        poster = renders / ".beatsync-tmp.jpg"
        poster.write_bytes(b"poster")
        os.replace(poster, renders / "reel_15.jpg")
        progress(1.0, "Reel ready")
        return {
            "path": "reel_15.mp4",
            "poster": "reel_15.jpg",
            "duration": sum(clip["duration"] for clip in captured["clips"]),
            "width": 1080,
            "height": 1920,
            "size": 9,
            "has_audio": True,
            "clip_count": len(captured["clips"]),
            "quality": "final",
            "aspect": "9:16",
            "encoder": "libx264",
            "captions": True,
            "caption_count": len(captured["cues"]),
            "cached": 0,
            "used_assets": [],
        }

    monkeypatch.setattr(render, "render_reel", fake_render_reel)
    record = app._queue_render(
        env.job_id, job, plan, "final", "9:16", None, True, audio_plan, False,
    )
    assert grid_calls["count"] == 1
    assert [round(clip["duration"], 3) for clip in submitted[0][1][-2]] == [3.75, 4.0]
    fn, args, kwargs = submitted[0]
    kwargs.pop("task_kind", None)
    kwargs.pop("task_key", None)
    fn(*args, **kwargs)

    assert [round(clip["duration"], 3) for clip in captured["clips"]] == [3.75, 4.0]
    assert grid_calls["count"] == 1
    artifact_id = record["artifact_id"]
    manifest = artifacts.load_manifest(env.directory, artifact_id)
    spec = manifest["spec"]
    assert [clip["dur"] for clip in spec["clips"]] == [3.75, 4.0]
    srt_text = artifacts.media_path(
        env.directory, artifact_id, "captions.srt",
    ).read_text(encoding="utf-8")
    srt_cues = _parse_srt(srt_text)
    burned = [
        {"start": round(start, 3), "end": round(end, 3), "text": text}
        for start, end, text in captured["cues"]
    ]
    assert srt_cues == burned
    cue_hash, text_hash = artifacts.cue_hashes(burned)
    assert spec["caption"]["cue_hash"] == cue_hash
    assert spec["caption"]["text_hash"] == text_hash
    assert spec["caption"]["cue_count"] == len(burned)
    assert manifest["render"]["caption_count"] == len(burned)
    assert srt_cues[-1]["end"] <= 7.75


def test_caption_count_agrees_when_captions_disabled(env, monkeypatch):
    job = app.load_job(env.job_id)
    job["analysis"]["scenes"][0]["speech"] = (
        "This caption text is present even when burn-in is disabled, so the "
        "saved caption count must agree everywhere."
    )
    app.save_job(job)
    job = app.load_job(env.job_id)
    plan = app._plan_for(job, 15, None)
    submitted = []
    monkeypatch.setattr(
        app.render_pool, "submit",
        lambda fn, *args, **kwargs: submitted.append((fn, args, kwargs)),
    )

    def fake_render_reel(source, meta, job_dir, plan, title, progress, **kwargs):
        renders = job_dir / "renders"
        renders.mkdir(parents=True, exist_ok=True)
        tmp = renders / ".nocap-tmp.mp4"
        tmp.write_bytes(b"nocap")
        os.replace(tmp, renders / "reel_15.mp4")
        poster = renders / ".nocap-tmp.jpg"
        poster.write_bytes(b"poster")
        os.replace(poster, renders / "reel_15.jpg")
        progress(1.0, "Reel ready")
        return {
            "path": "reel_15.mp4",
            "poster": "reel_15.jpg",
            "duration": float(plan["total"]),
            "width": 1080,
            "height": 1920,
            "size": 9,
            "has_audio": True,
            "clip_count": len(kwargs.get("render_clips") or []),
            "quality": "final",
            "aspect": "9:16",
            "encoder": "libx264",
            "captions": False,
            # Deliberately wrong: the app must normalize to the cue count.
            "caption_count": 0,
            "cached": 0,
            "used_assets": [],
        }

    monkeypatch.setattr(render, "render_reel", fake_render_reel)
    record = app._queue_render(
        env.job_id, job, plan, "final", "9:16", None, False, None, False,
    )
    fn, args, kwargs = submitted[0]
    kwargs.pop("task_kind", None)
    kwargs.pop("task_key", None)
    fn(*args, **kwargs)

    loaded = app.load_job(env.job_id)
    render_record = loaded["renders"][record["record_key"]]
    manifest = artifacts.load_manifest(env.directory, record["artifact_id"])
    cue_count = manifest["spec"]["caption"]["cue_count"]
    assert cue_count > 1
    assert manifest["render"]["caption_count"] == cue_count
    assert manifest["caption_count"] == cue_count
    assert artifacts.public_manifest(manifest, env.job_id)["caption_count"] == cue_count
    assert render_record["caption_count"] == cue_count


def test_artifact_caption_preview_route(env):
    manifest = make_artifact(
        env, artifacts.build_spec(
            env.job, plan_for(), captions=True,
            cues=[{"start": 0.0, "end": 1.0, "text": "preview cue"}],
        ),
        srt="1\n00:00:00,000 --> 00:00:01,000\npreview cue\n",
    )
    payload = app.get_artifact_captions(env.job_id, manifest["artifact_id"])
    assert payload["cue_count"] == 1
    assert payload["cues"] == [
        {"start": 0.0, "end": 1.0, "text": "preview cue"},
    ]
    assert payload["srt_url"].endswith("/captions.srt")


def test_concurrent_force_requests_do_not_share_generation(env, monkeypatch):
    job = app.load_job(env.job_id)
    plan = plan_for()
    submitted = []
    monkeypatch.setattr(
        app.render_pool, "submit",
        lambda fn, *args, **kwargs: submitted.append((fn, args, kwargs)),
    )
    barrier = threading.Barrier(3)
    outcomes: list[dict] = []
    lock = threading.Lock()

    def race():
        barrier.wait(3)
        try:
            record = app._queue_render(
                env.job_id, app.load_job(env.job_id), plan,
                "final", "9:16", None, False, None, True,
            )
            with lock:
                outcomes.append({"artifact_id": record["artifact_id"]})
        except app.HTTPException as exc:
            with lock:
                outcomes.append({"error": exc.status_code})

    threads = [threading.Thread(target=race) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait(3)
    for thread in threads:
        thread.join(5)
        assert not thread.is_alive()

    assert len(outcomes) == 2
    successes = [item for item in outcomes if "artifact_id" in item]
    errors = [item for item in outcomes if "error" in item]
    assert len(successes) == 1
    assert errors and all(item["error"] == 409 for item in errors)


def test_cleanup_storage_skips_job_with_active_artifact(env, monkeypatch):
    job = app.load_job(env.job_id)
    job["updated"] = time.time() - 10 * 86400
    (env.directory / "job.json").write_text(json.dumps(job), encoding="utf-8")
    spec = artifacts.build_spec(env.job, plan_for())
    manifest = artifacts.make_manifest(
        env.job_id, spec, status="queued", record_key="15",
    )
    manifest = artifacts.save_manifest(env.directory, manifest)
    monkeypatch.setattr(audio, "CACHE", env.tmp_path / "cache")
    monkeypatch.setenv("VIBECUT_RETENTION_DAYS", "1")
    monkeypatch.setenv("VIBECUT_JOB_CLEAN_DAYS", "0")
    monkeypatch.setenv("VIBECUT_CACHE_DAYS", "0")

    app.cleanup_storage()

    assert env.directory.is_dir()
    assert artifacts.load_manifest(env.directory, manifest["artifact_id"]) is not None


def test_share_does_not_publish_without_job_record(env, monkeypatch):
    manifest = make_artifact(env, artifacts.build_spec(env.job, plan_for()))
    artifact_id = manifest["artifact_id"]
    job = app.load_job(env.job_id)
    (env.directory / "job.json").unlink()
    monkeypatch.setattr(app, "load_job", lambda job_id: job)

    with pytest.raises(app.HTTPException) as missing_job:
        app.create_share(
            env.job_id, body=app.ShareBody(artifact_id=artifact_id),
        )

    assert missing_job.value.status_code == 404
    assert shares.load(app.SHARES, strict=False) == {}
