"""Flow 1 deterministic Cleanup Kit: feature gate, plans, and limits."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app
import artifacts
import routes_cleanup
import settings_store

JOB_ID = "cleanup-job"
STORY_ID = "st_cleanup"
SET_ID = "cs_cleanup"
FACE = {"x": 0.72, "y": 0.05, "w": 0.16, "h": 0.14, "confidence": 0.9}


def _scene(index: int, start: float, end: float, ocr: str, faces: list) -> dict:
    return {
        "id": index,
        "start": start,
        "end": end,
        "dur": end - start,
        "mid": (start + end) / 2,
        "ocr": ocr,
        "faces": faces,
        "deep": True,
        "tags": [],
        "crop": {"cx": 0.5, "cy": 0.5},
        "crop_mode": "center",
    }


def _job_record() -> dict:
    return {
        "id": JOB_ID,
        "created": 1.0,
        "updated": 1.0,
        "status": "ready",
        "progress": 1.0,
        "message": "Ready",
        "error": None,
        "source": {
            "path": "/tmp/cleanup-source.mp4",
            "name": "cleanup-source.mp4",
            "duration": 20.0,
            "width": 1080,
            "height": 1920,
            "fps": 30.0,
            "size": 1234,
            "has_audio": True,
            "fingerprint": "cleanup-source-fingerprint",
        },
        "options": {},
        "analysis": {
            "scene_count": 2,
            "hook_scene": 0,
            "deep_count": 2,
            "scenes": [
                _scene(0, 0.0, 4.0, "SALE TODAY", []),
                _scene(1, 4.0, 8.0, "Follow for more", [dict(FACE)]),
            ],
        },
        "clip_sets": [{
            "id": SET_ID,
            "job_id": JOB_ID,
            "stories": [{
                "id": STORY_ID,
                "title": "Cleanup story",
                "start": 0.0,
                "end": 8.0,
                "dur": 8.0,
                "clips": [
                    {"scene": 0, "start": 0.0, "end": 4.0, "dur": 4.0, "role": "hook"},
                    {"scene": 1, "start": 4.0, "end": 8.0, "dur": 4.0, "role": "beat"},
                ],
            }],
        }],
        "renders": {},
    }


def _artifact(job_dir: Path) -> str:
    spec = artifacts.ArtifactSpec(
        clips=[
            {"scene": 0, "start": 0.0, "end": 4.0, "dur": 4.0, "role": "hook"},
            {"scene": 1, "start": 4.0, "end": 8.0, "dur": 4.0, "role": "beat"},
        ],
        target=8,
        story_id=STORY_ID,
        aspect="9:16",
        source_fingerprint="cleanup-source-fingerprint",
        resolved_encoder="libx264",
    )
    manifest = artifacts.make_manifest(JOB_ID, spec, status="ready")
    manifest = artifacts.save_manifest(job_dir, manifest)
    artifact_id = manifest["artifact_id"]
    directory = artifacts.artifact_dir(job_dir, artifact_id)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "reel.mp4").write_bytes(b"fake-cleanup-mp4")
    return artifact_id


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    jobs = data / "jobs"
    sources = data / "sources"
    jobs.mkdir(parents=True)
    sources.mkdir(parents=True)
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.setattr(app, "SOURCES", sources)
    monkeypatch.setattr(app, "SHARES", tmp_path / "shares.json")
    monkeypatch.setattr(app, "HOST", "127.0.0.1")
    monkeypatch.setattr(settings_store, "DATA", data)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", data / "settings.json")
    monkeypatch.setattr(settings_store, "SECRETS_PATH", data / "secrets.json")
    settings_store.save_settings({"rights": {"lock": True}})
    monkeypatch.delenv("VIBECUT_TOKEN", raising=False)
    monkeypatch.setenv("VIBECUT_ENABLE_CLEANUP", "1")
    directory = jobs / JOB_ID
    directory.mkdir()
    job = _job_record()
    job_path = directory / "job.json"
    job_path.write_text(json.dumps(job), encoding="utf-8")
    artifact_id = _artifact(directory)
    client = TestClient(app.app)
    return SimpleNamespace(
        tmp_path=tmp_path,
        jobs=jobs,
        directory=directory,
        job=job,
        job_path=job_path,
        artifact_id=artifact_id,
        client=client,
    )


def _body(**overrides) -> dict:
    body = {
        "aspect": "9:16",
        "method": "cover",
        "boxes": [{"x": 0.1, "y": 0.7, "w": 0.8, "h": 0.2}],
        "attestation": True,
    }
    body.update(overrides)
    return body


def _plan(env, **overrides):
    return env.client.post(
        f"/api/jobs/{JOB_ID}/cleanup/plan", json=_body(**overrides),
    )


def test_feature_flag_off_returns_404_and_leaves_paid_job_untouched(env, monkeypatch):
    monkeypatch.setenv("VIBECUT_ENABLE_CLEANUP", "0")
    response = _plan(env)
    assert response.status_code == 404
    no_body = env.client.post(f"/api/jobs/{JOB_ID}/cleanup/plan")
    assert no_body.status_code == 404
    assert env.client.get(f"/api/jobs/{JOB_ID}").status_code == 200


@pytest.mark.parametrize(("headers", "content"), [
    ({"content-type": "application/json"}, b"{"),
    ({"content-type": "text/plain"}, b"{"),
])
def test_feature_gate_precedes_body_parsing(env, monkeypatch, headers, content):
    monkeypatch.setenv("VIBECUT_ENABLE_CLEANUP", "0")
    url = f"/api/jobs/{JOB_ID}/cleanup/plan"
    off = env.client.post(url, content=content, headers=headers)
    assert off.status_code == 404
    assert off.json()["detail"] == "Cleanup is not enabled in this build."

    monkeypatch.setenv("VIBECUT_ENABLE_CLEANUP", "1")
    on = env.client.post(url, content=content, headers=headers)
    assert on.status_code in (400, 422)


@pytest.mark.parametrize(("value", "expected"), [
    (None, True),
    ("", True),
    ("1", True),
    ("true", True),
    ("0", False),
    ("false", False),
    ("no", False),
    ("off", False),
    ("OFF", False),
])
def test_cleanup_is_on_by_default_with_an_explicit_off_switch(
    monkeypatch, value, expected,
):
    if value is None:
        monkeypatch.delenv("VIBECUT_ENABLE_CLEANUP", raising=False)
    else:
        monkeypatch.setenv("VIBECUT_ENABLE_CLEANUP", value)
    assert routes_cleanup.cleanup_enabled() is expected


def test_cleanup_routes_work_without_the_flag(env, monkeypatch):
    monkeypatch.delenv("VIBECUT_ENABLE_CLEANUP", raising=False)
    response = _plan(env)
    assert response.status_code == 200, response.text


def test_valid_crop_plan_is_deterministic_and_does_not_mutate_job(env):
    before = env.job_path.read_bytes()
    first = _plan(env, method="crop", boxes=[{"x": 0.08, "y": 0.7, "w": 0.84, "h": 0.2}])
    second = _plan(env, method="crop", boxes=[{"x": 0.08, "y": 0.7, "w": 0.84, "h": 0.2}])
    assert first.status_code == 200
    assert first.json() == second.json()
    payload = first.json()
    plan = payload["plan"]
    assert plan["kind"] == "cleanup_plan"
    assert plan["method"] == "crop"
    assert plan["aspect"] == "9:16"
    assert plan["source"]["type"] == "job"
    assert plan["crop"]["w"] > 0 and plan["crop"]["h"] > 0
    assert plan["filter_chain"][0]["filter"] == "crop"
    assert plan["filter_chain"][1]["filter"] == "scale"
    assert plan["attestation"]["required"] is True
    assert plan["attestation"]["accepted"] is True
    assert payload["quality_report"] == plan["quality_report"]
    assert payload["warnings"] == plan["warnings"]
    assert env.job_path.read_bytes() == before


def test_valid_cover_plan_returns_drawbox_chain(env):
    response = _plan(env, method="cover")
    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan["method"] == "cover"
    assert plan["detection"]["source"] == "explicit"
    assert plan["detection"]["approximate"] is False
    assert plan["boxes"][0]["source"] == "explicit"
    assert plan["filter_chain"][0]["filter"] == "drawbox"
    assert plan["filter_chain"][0]["color"] == "black"
    assert plan["filter_chain"][0]["thickness"] == "fill"
    assert plan["quality_report"]["residual_risk"] == "low"


def test_planning_does_not_write_job_or_call_render_or_network(env, monkeypatch):
    import http.client
    import socket

    def forbidden(*_args, **_kwargs):
        raise AssertionError("planning must not write, render, or use the network")

    monkeypatch.setattr(app, "save_job", forbidden)
    monkeypatch.setattr(app, "update_job", forbidden)
    monkeypatch.setattr(app.render, "render_reel", forbidden)
    monkeypatch.setattr(app.render, "_run", forbidden)
    monkeypatch.setattr(app.render_pool, "submit", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(http.client.HTTPConnection, "request", forbidden)

    before_bytes = env.job_path.read_bytes()
    before_mtime = env.job_path.stat().st_mtime_ns
    response = _plan(env, method="cover")
    assert response.status_code == 200
    assert env.job_path.read_bytes() == before_bytes
    assert env.job_path.stat().st_mtime_ns == before_mtime


def test_ambiguous_duplicate_story_id_returns_409(env):
    job = json.loads(env.job_path.read_text(encoding="utf-8"))
    story = json.loads(json.dumps(job["clip_sets"][0]["stories"][0]))
    job["clip_sets"].append({
        "id": "cs_duplicate",
        "job_id": JOB_ID,
        "stories": [story],
    })
    env.job_path.write_text(json.dumps(job), encoding="utf-8")
    response = _plan(env, story_id=STORY_ID)
    assert response.status_code == 409
    assert "ambiguous" in response.json()["detail"].lower()


def test_valid_blur_plan_uses_approximate_ocr_fallback(env):
    response = _plan(env, method="blur", boxes=None)
    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan["method"] == "blur"
    assert plan["detection"]["source"] == "approximate"
    assert plan["detection"]["approximate"] is True
    assert plan["detection"]["confidence"] < 0.5
    assert plan["boxes"][0]["source"] == "approximate"
    assert plan["filter_chain"][0]["filter"] == "region_blur"
    assert plan["quality_report"]["residual_risk"] == "high"
    assert plan["quality_report"]["review_required"] is True
    assert any("approximate" in item.lower() for item in plan["warnings"])


def test_explicit_boxes_win_over_scene_ocr(env):
    response = _plan(env, method="blur", boxes=[{"x": 0.2, "y": 0.2, "w": 0.3, "h": 0.1}])
    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan["detection"]["source"] == "explicit"
    assert plan["detection"]["ocr_scene_ids"] == []
    assert plan["boxes"][0]["source"] == "explicit"
    assert not any("approximate" in item.lower() for item in plan["warnings"])


@pytest.mark.parametrize("method", ["inpaint", "generative_fill", "remove", "watermark"])
def test_rejects_unsupported_and_forbidden_methods(env, method):
    response = _plan(env, method=method)
    assert response.status_code == 422
    assert "not supported" in response.json()["detail"].lower()


@pytest.mark.parametrize("aspect", ["3:4", "21:9", "9x16", "portrait"])
def test_rejects_unsupported_aspects(env, aspect):
    assert _plan(env, aspect=aspect).status_code == 422


def test_rejects_watermark_box_label_and_unknown_fields(env):
    labeled = _plan(env, boxes=[{"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.1, "label": "watermark"}])
    assert labeled.status_code == 422
    unknown = _plan(env, watermark=True)
    assert unknown.status_code == 422


@pytest.mark.parametrize("attestation", [None, False, "", "false"])
def test_attestation_is_required(env, attestation):
    body = _body()
    if attestation is None:
        body.pop("attestation")
    else:
        body["attestation"] = attestation
    response = env.client.post(f"/api/jobs/{JOB_ID}/cleanup/plan", json=body)
    assert response.status_code == 422
    assert "attestation" in response.json()["detail"].lower()


def test_quality_report_contains_required_fields_and_face_warning(env):
    response = _plan(
        env,
        method="cover",
        boxes=[{"x": 0.70, "y": 0.03, "w": 0.20, "h": 0.18}],
    )
    assert response.status_code == 200
    report = response.json()["quality_report"]
    assert set(report) == {
        "detection_confidence",
        "method",
        "residual_risk",
        "face_overlap_warning",
        "review_required",
        "limitations",
    }
    assert report["method"] == "cover"
    assert report["face_overlap_warning"] is True
    assert report["review_required"] is True
    assert report["residual_risk"] == "high"
    assert isinstance(report["limitations"], list) and report["limitations"]
    assert any("face" in item.lower() for item in response.json()["warnings"])


@pytest.mark.parametrize("box", [
    {"x": 0.9, "y": 0.1, "w": 0.2, "h": 0.1},
    {"x": -0.1, "y": 0.1, "w": 0.2, "h": 0.1},
    {"x": 0.1, "y": 0.1, "w": 0.0, "h": 0.1},
    {"x": True, "y": 0.1, "w": 0.2, "h": 0.1},
    {"x": "0.1", "y": 0.1, "w": 0.2, "h": 0.1},
])
def test_invalid_boxes_are_rejected(env, box):
    assert _plan(env, boxes=[box]).status_code == 422


def test_missing_job_artifact_and_story_return_404(env):
    missing_job = env.client.post(
        "/api/jobs/nope/cleanup/plan", json=_body(),
    )
    assert missing_job.status_code == 404
    missing_artifact = _plan(env, artifact_id="art_" + "0" * 24)
    assert missing_artifact.status_code == 404
    missing_story = _plan(env, story_id="st_missing")
    assert missing_story.status_code == 404


def test_artifact_source_includes_artifact_and_clips(env):
    response = _plan(
        env, artifact_id=env.artifact_id, method="cover",
        boxes=[{"x": 0.1, "y": 0.7, "w": 0.8, "h": 0.2}],
    )
    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan["source"]["type"] == "artifact"
    assert plan["source"]["artifact_id"] == env.artifact_id
    assert plan["source"]["story_id"] == STORY_ID
    assert plan["source"]["media"] == f"artifacts/{env.artifact_id}/reel.mp4"
    assert len(plan["source"]["clips"]) == 2
    assert plan["source"]["range"] == {"start": 0.0, "end": 8.0}


def test_story_source_includes_clip_set_and_range(env):
    response = _plan(env, story_id=STORY_ID, method="blur", boxes=None)
    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan["source"]["type"] == "story"
    assert plan["source"]["story_id"] == STORY_ID
    assert plan["source"]["clip_set_id"] == SET_ID
    assert plan["source"]["range"] == {"start": 0.0, "end": 8.0}


def test_story_and_artifact_are_mutually_exclusive(env):
    response = _plan(env, story_id=STORY_ID, artifact_id=env.artifact_id)
    assert response.status_code == 422


def test_range_must_stay_inside_source(env):
    assert _plan(env, range={"start": 0, "end": 99}).status_code == 422
    assert _plan(env, range={"start": 3, "end": 3}).status_code == 422
    assert _plan(env, story_id=STORY_ID, range={"start": 0, "end": 10}).status_code == 422
    assert _plan(env, range={"start": 2, "end": 6}).status_code == 200


def test_no_detection_and_no_boxes_rejects_cover_but_allows_crop(env):
    job = json.loads(env.job_path.read_text(encoding="utf-8"))
    for scene in job["analysis"]["scenes"]:
        scene["ocr"] = ""
    env.job_path.write_text(json.dumps(job), encoding="utf-8")

    no_cover = _plan(env, method="cover", boxes=None)
    assert no_cover.status_code == 422
    assert "manual boxes" in no_cover.json()["detail"].lower()

    crop = _plan(env, method="crop", boxes=None)
    assert crop.status_code == 200
    assert crop.json()["plan"]["detection"]["source"] == "none"
    assert crop.json()["plan"]["quality_report"]["residual_risk"] == "high"


def test_cover_without_boxes_and_without_analysis_returns_409(env):
    job = json.loads(env.job_path.read_text(encoding="utf-8"))
    job["status"] = "reading"
    job["analysis"] = None
    env.job_path.write_text(json.dumps(job), encoding="utf-8")
    response = _plan(env, method="cover", boxes=None)
    assert response.status_code == 409
    assert "analysis" in response.json()["detail"].lower()


# ---------------------------------------------------------------- W3 T2: clean layers

import os
import shutil
import uuid

import cleanup
import compose_render
import detect
import edits
import pipeline
import routes_cleanup


def _padded_inside(box: dict) -> bool:
    return (
        box["x"] >= 0.0 and box["y"] >= 0.0
        and box["x"] + box["w"] <= 1.0
        and box["y"] + box["h"] <= 1.0
        and box["w"] > 0 and box["h"] > 0
    )


def _tracklet(
    tracklet_id: str,
    kind: str,
    box: dict,
    *,
    ranges: list | None = None,
    text: str = "burned caption",
) -> dict:
    return {
        "id": tracklet_id,
        "kind": kind,
        "box": dict(box),
        "ranges": ranges or [{"start": 0.0, "end": 8.0}],
        "text_sample": text,
        "confidence": 0.9,
        "samples": 4,
        "duration": 8.0,
        "approximate": False,
    }


def _report(tracklets: list[dict], *, attested: bool = True) -> dict:
    return {
        "schema": 1,
        "status": "ready",
        "complete": True,
        "job_id": JOB_ID,
        "created": 1.0,
        "tracklets": tracklets,
        "policy": {
            "clean_allowed": attested,
            "rights_attested": attested,
            "watermark_refused": [
                item["id"] for item in tracklets if item["kind"] == "watermark"
            ],
            "handle_or_logo_ids": [
                item["id"] for item in tracklets if item["kind"] == "handle_or_logo"
            ],
            "screen_text_ids": [
                item["id"] for item in tracklets if item["kind"] == "screen_text"
            ],
            "requires_attestation": [],
            "refusals": [],
        },
        "rights": {"attested": attested, "source": "job"},
    }


def test_screen_text_is_not_counted_as_baked_text():
    job = _job_record()
    job["analysis"]["transcript"] = {"text": "talking"}
    for scene in job["analysis"]["scenes"]:
        scene["speech"] = "talking"
    rows = [
        {"text": "9:41", "box": {"x": 0.44, "y": 0.02, "w": 0.12, "h": 0.03}, "confidence": 0.9},
        {"text": "Search", "box": {"x": 0.05, "y": 0.05, "w": 0.20, "h": 0.05}, "confidence": 0.9},
        {"text": "Home", "box": {"x": 0.68, "y": 0.05, "w": 0.18, "h": 0.05}, "confidence": 0.9},
    ]
    observations = detect.observations_from_samples([
        {"start": index * 2.0, "end": index * 2.0 + 2.0, "text": rows}
        for index in range(6)
    ])
    report = detect.build_report(
        job,
        observations,
        sampled={"ran": True, "frames": 12, "vision": True},
    )
    kinds = {item["kind"] for item in report["tracklets"]}
    assert "screen_text" in kinds
    assert report["recommendation"] == "compose"
    assert report["recommendation"] != "clean_then_compose"
    screen = [
        item for item in report["clean_prefill"] if item["kind"] == "screen_text"
    ]
    assert screen
    assert report["policy"]["screen_text_ids"]

    attested = detect.build_report(
        job,
        observations,
        sampled={"ran": True, "frames": 12, "vision": True},
        attestation=True,
    )
    assert attested["recommendation"] == "compose"
    assert all(item["blocked"] is None for item in attested["clean_prefill"])


def test_screen_text_follows_the_rights_like_other_text():
    assert detect.cleanup_block_reason("screen_text", attested=True) is None
    assert detect.cleanup_block_reason(
        "screen_text", attested=False, settings={"rights": {"lock": True}},
    ) == "rights_not_attested"


def test_tracklet_clean_layers_map_kinds_to_edit_clean_layers():
    tracklets = [
        _tracklet("trk_0001", "subtitle", {"x": 0.1, "y": 0.76, "w": 0.8, "h": 0.09}),
        _tracklet("trk_0002", "subtitle", {"x": 0.1, "y": 0.48, "w": 0.8, "h": 0.08}),
        _tracklet("trk_0003", "title", {"x": 0.1, "y": 0.2, "w": 0.8, "h": 0.18}),
        _tracklet("trk_0004", "lower_third", {"x": 0.08, "y": 0.72, "w": 0.4, "h": 0.08}),
        _tracklet("trk_0005", "credit", {"x": 0.4, "y": 0.9, "w": 0.2, "h": 0.03}),
    ]
    built = cleanup.tracklet_clean_layers(tracklets, attested=True)
    kinds = {layer["id"]: layer["kind"] for layer in built["layers"]}
    assert kinds == {
        "cl_trk_0001": "delogo",
        "cl_trk_0002": "delogo",
        "cl_trk_0003": "delogo",
        "cl_trk_0004": "delogo",
        "cl_trk_0005": "delogo",
    }
    assert built["refused"] == []
    normalized = edits.normalize_clean(built["layers"])
    assert normalized == built["layers"]
    first = built["layers"][0]
    assert first["box"]["x"] <= 0.1 and first["box"]["y"] <= 0.76
    assert first["box"]["x"] + first["box"]["w"] >= 0.9
    assert first["box"]["y"] + first["box"]["h"] >= 0.85
    assert first["ranges"] == [{"start": 0.0, "end": 8.0}]
    assert _padded_inside(first["box"])


def test_every_kind_produces_a_clean_layer_once_attested():
    tracklets = [
        _tracklet("trk_water", "watermark", {"x": 0.84, "y": 0.05, "w": 0.13, "h": 0.05}, text="TikTok"),
        _tracklet("trk_ui", "screen_text", {"x": 0.05, "y": 0.03, "w": 0.2, "h": 0.05}, text="Search"),
        _tracklet("trk_sub", "subtitle", {"x": 0.1, "y": 0.76, "w": 0.8, "h": 0.09}),
    ]
    built = cleanup.tracklet_clean_layers(tracklets, attested=True)
    assert {layer["id"] for layer in built["layers"]} == {"cl_trk_water", "cl_trk_ui", "cl_trk_sub"}
    assert built["refused"] == []
    assert edits.normalize_clean(built["layers"]) == built["layers"]


def test_handle_needs_attestation():
    handle = _tracklet(
        "trk_handle", "handle_or_logo", {"x": 0.02, "y": 0.03, "w": 0.15, "h": 0.05},
        text="@myhandle",
    )
    locked = cleanup.tracklet_clean_layers([handle], attested=False)
    assert locked["layers"] == []
    assert locked["refused"][0]["blocked"] == "attestation_required"

    on = cleanup.tracklet_clean_layers([handle], attested=True)
    assert on["layers"][0]["kind"] == "crop_guard"
    assert edits.normalize_clean(on["layers"]) == on["layers"]


def test_rights_are_stored_server_side_not_in_the_cleanup_body(env):
    response = env.client.post(
        f"/api/jobs/{JOB_ID}/rights",
        json={"attested": True, "source": "check"},
    )
    assert response.status_code == 200, response.text
    rights = response.json()["rights"]
    assert rights["attested"] is True
    assert rights["source"] == "check"
    assert isinstance(rights["at"], float)
    stored = json.loads(env.job_path.read_text(encoding="utf-8"))["rights"]
    assert stored == rights
    got = env.client.get(f"/api/jobs/{JOB_ID}/rights")
    assert got.status_code == 200
    assert got.json()["rights"] == rights

    bad = env.client.post(
        f"/api/jobs/{JOB_ID}/rights",
        json={"attested": True, "source": "localStorage"},
    )
    assert bad.status_code == 422


def test_rights_route_works_when_the_cleanup_flag_is_off(env, monkeypatch):
    monkeypatch.setenv("VIBECUT_ENABLE_CLEANUP", "off")
    response = env.client.post(
        f"/api/jobs/{JOB_ID}/rights",
        json={"attested": False, "source": "import"},
    )
    assert response.status_code == 200
    assert response.json()["rights"]["attested"] is False


def test_cleanup_layers_route_builds_gated_layers(env):
    tracklets = [
        _tracklet("trk_sub", "subtitle", {"x": 0.1, "y": 0.76, "w": 0.8, "h": 0.09}),
        _tracklet("trk_ui", "screen_text", {"x": 0.05, "y": 0.03, "w": 0.2, "h": 0.05}, text="Search"),
        _tracklet("trk_water", "watermark", {"x": 0.84, "y": 0.05, "w": 0.13, "h": 0.05}, text="TikTok"),
        _tracklet("trk_handle", "handle_or_logo", {"x": 0.02, "y": 0.03, "w": 0.15, "h": 0.05}, text="@me"),
    ]
    detect.write_report(env.directory, _report(tracklets))
    job = json.loads(env.job_path.read_text(encoding="utf-8"))
    job["rights"] = {"attested": False, "at": 1.0, "source": "import"}
    env.job_path.write_text(json.dumps(job), encoding="utf-8")

    locked = env.client.post(f"/api/jobs/{JOB_ID}/cleanup/layers", json={})
    assert locked.status_code == 409
    assert "attestation" in locked.json()["detail"].lower()

    env.client.post(
        f"/api/jobs/{JOB_ID}/rights", json={"attested": True, "source": "check"},
    )
    built = env.client.post(f"/api/jobs/{JOB_ID}/cleanup/layers", json={})
    assert built.status_code == 200, built.text
    body = built.json()
    assert {layer["tracklet_id"] for layer in body["layers"]} == {
        "trk_sub", "trk_ui", "trk_water", "trk_handle",
    }
    assert body["refused"] == []

    unknown = env.client.post(
        f"/api/jobs/{JOB_ID}/cleanup/layers",
        json={"tracklet_ids": ["trk_missing"]},
    )
    assert unknown.status_code == 422


def test_cleanup_layers_open_without_a_tick_when_the_lock_is_off(env):
    tracklets = [
        _tracklet("trk_sub", "subtitle", {"x": 0.1, "y": 0.76, "w": 0.8, "h": 0.09}),
        _tracklet("trk_ui", "screen_text", {"x": 0.05, "y": 0.03, "w": 0.2, "h": 0.05}, text="Search"),
        _tracklet("trk_water", "watermark", {"x": 0.84, "y": 0.05, "w": 0.13, "h": 0.05}, text="TikTok"),
        _tracklet("trk_handle", "handle_or_logo", {"x": 0.02, "y": 0.03, "w": 0.15, "h": 0.05}, text="@me"),
    ]
    detect.write_report(env.directory, _report(tracklets))
    job = json.loads(env.job_path.read_text(encoding="utf-8"))
    job["rights"] = {"attested": False, "at": 1.0, "source": "import"}
    env.job_path.write_text(json.dumps(job), encoding="utf-8")
    settings_store.save_settings({"rights": {"lock": False}})

    built = env.client.post(f"/api/jobs/{JOB_ID}/cleanup/layers", json={})
    assert built.status_code == 200, built.text
    body = built.json()
    assert {layer["id"] for layer in body["layers"]} == {"cl_trk_sub", "cl_trk_ui"}
    blocked = {item["tracklet_id"]: item["blocked"] for item in body["refused"]}
    assert blocked["trk_water"] == "attestation_required"
    assert blocked["trk_handle"] == "attestation_required"


def test_edit_save_requires_server_side_rights_for_clean_layers(env):
    clean = [{
        "kind": "plate",
        "box": {"x": 0.1, "y": 0.7, "w": 0.8, "h": 0.2},
        "ranges": [{"start": 0.0, "end": 4.0}],
    }]
    body = {
        "set_id": SET_ID, "story_id": STORY_ID, "aspect": "9:16", "clean": clean,
    }
    env.client.post(
        f"/api/jobs/{JOB_ID}/rights", json={"attested": False, "source": "import"},
    )
    refused = env.client.post(f"/api/jobs/{JOB_ID}/edits", json=body)
    assert refused.status_code == 409
    assert "attestation" in refused.json()["detail"].lower()

    no_clean = env.client.post(
        f"/api/jobs/{JOB_ID}/edits",
        json={"set_id": SET_ID, "story_id": STORY_ID, "aspect": "9:16"},
    )
    assert no_clean.status_code == 200, no_clean.text

    env.client.post(
        f"/api/jobs/{JOB_ID}/rights", json={"attested": True, "source": "import"},
    )
    allowed = env.client.post(f"/api/jobs/{JOB_ID}/edits", json=body)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["edit"]["clean"][0]["kind"] == "plate"

    env.client.post(
        f"/api/jobs/{JOB_ID}/rights", json={"attested": False, "source": "check"},
    )
    edit_id = allowed.json()["id"]
    patch_clean = env.client.patch(
        f"/api/jobs/{JOB_ID}/edits/{edit_id}",
        json={"clean": [{**clean[0], "kind": "blur"}]},
    )
    assert patch_clean.status_code == 409

    patch_color = env.client.patch(
        f"/api/jobs/{JOB_ID}/edits/{edit_id}",
        json={"color": {"preset": "warm_film"}},
    )
    assert patch_color.status_code == 200, patch_color.text


def test_legacy_job_without_a_rights_record_still_saves_clean_layers(env):
    # Jobs from before the rights field existed must keep working.
    body = {
        "set_id": SET_ID, "story_id": STORY_ID, "aspect": "9:16",
        "clean": [{"kind": "blur", "box": {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.1}}],
    }
    response = env.client.post(f"/api/jobs/{JOB_ID}/edits", json=body)
    assert response.status_code == 200, response.text


def _residual_compiled() -> dict:
    return {
        "source": {"width": 1080, "height": 1920},
        "canvas": {"w": 540, "h": 960},
        "segments": [{
            "index": 0, "start": 0.0, "out_start": 0.0, "out_end": 100.0,
            "crop": {"x": 0, "y": 0, "w": 1080, "h": 1920},
        }],
    }


def test_residual_report_counts_only_text_inside_clean_regions():
    layers = [{
        "id": "cl_sub", "kind": "plate",
        "box": {"x": 0.1, "y": 0.7, "w": 0.8, "h": 0.2},
        "ranges": [{"start": 0.0, "end": 100.0}],
    }]
    inside = {"text": "SALE", "box": {"x": 0.2, "y": 0.76, "w": 0.5, "h": 0.07}}
    outside = {"text": "TOP", "box": {"x": 0.1, "y": 0.05, "w": 0.4, "h": 0.05}}
    samples = [
        {"t": float(index), "text": [inside]}
        for index in range(100)
    ]
    report = cleanup.residual_report(
        samples, layers=layers, compiled=_residual_compiled(),
    )
    assert report["frames_sampled"] == 100
    assert report["residual_frames"] == 100
    assert report["residual_pct"] == 100.0
    assert report["pass"] is False
    assert report["layers"][0]["residual_frames"] == 100

    clean = [
        {"t": float(index), "text": [outside]}
        for index in range(200)
    ]
    report = cleanup.residual_report(
        clean, layers=layers, compiled=_residual_compiled(),
    )
    assert report["residual_frames"] == 0
    assert report["residual_pct"] == 0.0
    assert report["pass"] is True


def test_residual_report_maps_source_boxes_through_the_crop():
    compiled = _residual_compiled()
    compiled["segments"][0]["crop"] = {"x": 656, "y": 0, "w": 608, "h": 1080}
    compiled["source"] = {"width": 1920, "height": 1080}
    compiled["canvas"] = {"w": 540, "h": 960}
    # Source box x=0.5..0.8 sits outside the crop x=656/1920=0.342..0.658
    # only past 0.658, so its output region is clipped to the right edge.
    layers = [{
        "id": "cl_sub", "kind": "blur",
        "box": {"x": 0.5, "y": 0.2, "w": 0.3, "h": 0.1},
        "ranges": [],
    }]
    report = cleanup.residual_report(
        [{"t": 0.0, "text": [{"text": "tail", "box": {"x": 0.9, "y": 0.2, "w": 0.08, "h": 0.1}}]}],
        layers=layers,
        compiled=compiled,
    )
    assert report["residual_frames"] == 1


def _save_story_edit(env, *, clean: list[dict], reframe: dict | None = None) -> dict:
    job = json.loads(env.job_path.read_text(encoding="utf-8"))
    record = job["clip_sets"][0]
    story = record["stories"][0]
    story_ref = edits.normalize_story_ref({
        "set_id": record["id"],
        "story_id": story["id"],
        "clip_hash": edits.clip_snapshot_hash(story["clips"]),
        "title": story.get("title") or "",
        "duration": 8.0,
        "clip_count": len(story["clips"]),
    })
    edit = edits.build_edit(
        story_ref=story_ref,
        aspect="9:16",
        clean=clean,
        reframe=reframe or {"mode": "center"},
        created=1.0,
    )
    edits.save_edit(env.directory, edit)
    return edit


def _fake_residual(monkeypatch, text_inside: bool = False):
    calls = []

    def render_frame(job, compiled, t, quality, aspect):
        calls.append({"t": t, "quality": quality})
        return b"fake-jpg"

    def probe(directory):
        records = {}
        for path in sorted(Path(directory).glob("*.jpg")):
            text = []
            if text_inside:
                text = [{
                    "text": "OLD CAPTION", "confidence": 0.9,
                    "box": {"x": 0.2, "y": 0.76, "w": 0.5, "h": 0.07},
                }]
            records[path.name] = {"text": text, "faces": []}
        return records

    monkeypatch.setattr(routes_cleanup, "_render_frame", render_frame)
    monkeypatch.setattr(routes_cleanup, "_probe_images", probe)
    return calls


def test_residual_route_measures_rendered_frames(env, monkeypatch):
    edit = _save_story_edit(env, clean=[{
        "kind": "plate",
        "box": {"x": 0.1, "y": 0.7, "w": 0.8, "h": 0.2},
        "ranges": [{"start": 0.0, "end": 8.0}],
    }])
    calls = _fake_residual(monkeypatch)
    response = env.client.post(
        f"/api/jobs/{JOB_ID}/cleanup/residual",
        json={"edit_id": edit["id"], "fps": 1.0, "max_frames": 5},
    )
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["frames_sampled"] == 5
    assert report["residual_frames"] == 0
    assert report["residual_pct"] == 0.0
    assert report["pass"] is True
    assert report["ocr_available"] is True
    assert report["faces"] == {
        "overlap": False, "count": 0, "faces_checked": 2, "hits": [],
    }
    assert calls and all(item["quality"] == "final" for item in calls)

    _fake_residual(monkeypatch, text_inside=True)
    dirty = env.client.post(
        f"/api/jobs/{JOB_ID}/cleanup/residual",
        json={"edit_id": edit["id"], "times": [0.0, 4.0]},
    )
    assert dirty.status_code == 200, dirty.text
    assert dirty.json()["residual_pct"] == 100.0
    assert dirty.json()["pass"] is False


def test_residual_route_reports_face_overlap(env, monkeypatch):
    edit = _save_story_edit(env, clean=[{
        "kind": "blur",
        "box": {"x": 0.70, "y": 0.03, "w": 0.20, "h": 0.18},
        "ranges": [{"start": 4.0, "end": 8.0}],
    }])
    _fake_residual(monkeypatch)
    response = env.client.post(
        f"/api/jobs/{JOB_ID}/cleanup/residual",
        json={"edit_id": edit["id"], "times": [5.0]},
    )
    assert response.status_code == 200, response.text
    faces = response.json()["faces"]
    assert faces["overlap"] is True
    assert faces["count"] >= 1


def test_residual_route_validates_edit_and_body(env, monkeypatch):
    _fake_residual(monkeypatch)
    no_clean = _save_story_edit(env, clean=[])
    assert env.client.post(
        f"/api/jobs/{JOB_ID}/cleanup/residual",
        json={"edit_id": no_clean["id"]},
    ).status_code == 422
    assert env.client.post(
        f"/api/jobs/{JOB_ID}/cleanup/residual",
        json={"edit_id": "ed_" + "0" * 32},
    ).status_code == 404
    assert env.client.post(
        f"/api/jobs/{JOB_ID}/cleanup/residual",
        json={"edit_id": no_clean["id"], "quality": "huge"},
    ).status_code == 422


# ---------------------------------------------------------------- live fixtures


FIXTURE_A = os.environ.get("VIBECUT_FIXTURE_A")
FIXTURE_B = os.environ.get("VIBECUT_FIXTURE_B")
FIXTURES = [
    pytest.param("A", FIXTURE_A, id="fixture-a"),
    pytest.param("B", FIXTURE_B, id="fixture-b"),
]


def _live_check(path: str, tmp_path: Path, *, attestation: bool) -> dict:
    duration = float(pipeline.probe(path)["duration"])
    job = {
        "id": "live-" + uuid.uuid4().hex[:8],
        "source": {"path": path, "duration": duration, "has_audio": True},
        "analysis": {"scenes": []},
    }
    samples = pipeline.read_text_samples(
        path, tmp_path / "live-check", duration, fps=0.5, max_frames=60,
    )
    observations = detect.observations_from_samples(samples.get("frames") or [])
    return detect.build_report(
        job,
        observations,
        sampled={
            "ran": True,
            "frames": len(samples.get("frames") or []),
            "vision": bool(samples.get("vision")),
        },
        attestation=attestation,
    )


@pytest.mark.skipif(not FIXTURE_A, reason="VIBECUT_FIXTURE_A is not set")
def test_live_fixture_a_finds_mid_frame_subtitles_and_screen_text(tmp_path):
    path = str(Path(FIXTURE_A).expanduser())
    assert Path(path).is_file(), path
    report = _live_check(path, tmp_path, attestation=False)
    assert report["text"]["confirmed"] is True
    subtitles = [item for item in report["tracklets"] if item["kind"] == "subtitle"]
    assert 1 <= len(subtitles) <= 6
    screen = [item for item in report["tracklets"] if item["kind"] == "screen_text"]
    assert screen, "screen-recording UI text was not classified as screen_text"
    screen_prefill = [
        item for item in report["clean_prefill"] if item["kind"] == "screen_text"
    ]
    assert screen_prefill
    assert all(item["action"] == "none" and not item["enabled"] for item in screen_prefill)
    # No attestation: nothing is pre-filled as enabled, including the logo.
    assert report["rights"]["attested"] is False
    assert all(not item["enabled"] for item in report["clean_prefill"])
    print(json.dumps({"fixture": "A", "tracklets": report["tracklets"]}))


@pytest.mark.skipif(not FIXTURE_B, reason="VIBECUT_FIXTURE_B is not set")
def test_live_fixture_b_finds_chinese_lower_band_subtitles(tmp_path):
    path = str(Path(FIXTURE_B).expanduser())
    assert Path(path).is_file(), path
    report = _live_check(path, tmp_path, attestation=True)
    assert report["text"]["confirmed"] is True
    subtitles = [item for item in report["tracklets"] if item["kind"] == "subtitle"]
    assert subtitles
    assert any(
        any("\u3400" <= char <= "\u9fff" for char in item["text_sample"])
        for item in subtitles
    )
    removed = [
        item for item in report["clean_prefill"]
        if item["kind"] == "subtitle" and item["action"] == "delogo"
    ]
    assert removed
    print(json.dumps({"fixture": "B", "tracklets": report["tracklets"]}))


def _live_job(tmp_path, monkeypatch, path: str) -> SimpleNamespace:
    data = tmp_path / "live-data"
    jobs = data / "jobs"
    sources = data / "sources"
    jobs.mkdir(parents=True)
    sources.mkdir(parents=True)
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.setattr(app, "SOURCES", sources)
    monkeypatch.setattr(app, "SHARES", tmp_path / "shares.json")
    monkeypatch.setattr(app, "HOST", "127.0.0.1")
    monkeypatch.setattr(settings_store, "DATA", data)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", data / "settings.json")
    monkeypatch.setattr(settings_store, "SECRETS_PATH", data / "secrets.json")
    settings_store.save_settings({"rights": {"lock": True}})
    monkeypatch.delenv("VIBECUT_TOKEN", raising=False)
    monkeypatch.setenv("VIBECUT_ENABLE_CLEANUP", "1")
    meta = pipeline.probe(path)
    duration = float(meta["duration"])
    job_id = uuid.uuid4().hex[:12]
    directory = jobs / job_id
    directory.mkdir()
    clips = [{
        "scene": 0, "start": 0.0, "end": duration,
        "dur": duration, "role": "hook",
    }]
    job = {
        "id": job_id,
        "created": 1.0,
        "updated": 1.0,
        "status": "ready",
        "progress": 1.0,
        "message": "Ready",
        "error": None,
        "source": {"path": path, "name": Path(path).name, **meta},
        "options": {},
        "analysis": {"scenes": [], "transcript": None, "engine": {}},
        "clip_sets": [{
            "id": "cs_live", "job_id": job_id,
            "stories": [{
                "id": "st_live", "title": "Live story",
                "start": 0.0, "end": duration, "dur": duration,
                "clips": clips,
            }],
        }],
        "renders": {},
        "rights": {"attested": True, "at": 1.0, "source": "import"},
    }
    (directory / "job.json").write_text(json.dumps(job), encoding="utf-8")
    return SimpleNamespace(
        directory=directory, job=job, job_id=job_id,
        client=TestClient(app.app), duration=duration,
    )


@pytest.mark.parametrize(("label", "path"), FIXTURES)
def test_live_fixture_apply_clean_and_measure_residual(
    label, path, tmp_path, monkeypatch,
):
    if not path:
        pytest.skip(f"VIBECUT_FIXTURE_{label} is not set")
    path = str(Path(path).expanduser())
    assert Path(path).is_file(), path
    report = _live_check(path, tmp_path, attestation=True)
    built = cleanup.tracklet_clean_layers(report["tracklets"], attested=True)
    assert built["layers"], "no clean layers were built from the fixture"
    env = _live_job(tmp_path, monkeypatch, path)
    job = json.loads((env.directory / "job.json").read_text(encoding="utf-8"))
    story = job["clip_sets"][0]["stories"][0]
    edit = edits.build_edit(
        story_ref={
            "set_id": "cs_live", "story_id": "st_live",
            "clip_hash": edits.clip_snapshot_hash(story["clips"]),
            "title": "Live story", "duration": env.duration,
            "clip_count": len(story["clips"]),
        },
        aspect="9:16",
        clean=built["layers"],
        reframe={"mode": "center"},
        created=1.0,
    )
    edits.save_edit(env.directory, edit)
    response = env.client.post(
        f"/api/jobs/{env.job_id}/cleanup/residual",
        json={
            "edit_id": edit["id"],
            "fps": 1.0,
            "max_frames": 60,
            "quality": "final",
        },
    )
    assert response.status_code == 200, response.text
    residual = response.json()
    print(json.dumps({
        "fixture": label,
        "layers": [{"id": layer["id"], "kind": layer["kind"], "box": layer["box"]} for layer in built["layers"]],
        "residual_pct": residual["residual_pct"],
        "frames_sampled": residual["frames_sampled"],
        "residual_frames": residual["residual_frames"],
        "faces": residual["faces"],
        "report_path": str(tmp_path / f"residual-{label}.json"),
    }, ensure_ascii=False))
    (tmp_path / f"residual-{label}.json").write_text(
        json.dumps(residual, ensure_ascii=False, indent=1), encoding="utf-8",
    )
    assert residual["ocr_available"] is True
    assert residual["residual_pct"] <= cleanup.RESIDUAL_TARGET_PCT
