"""Flow 1 deterministic Cleanup Kit: feature gate, plans, and limits."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app
import artifacts

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
    monkeypatch.delenv("VIBECUT_ENABLE_CLEANUP", raising=False)
    response = _plan(env)
    assert response.status_code == 404
    no_body = env.client.post(f"/api/jobs/{JOB_ID}/cleanup/plan")
    assert no_body.status_code == 404
    assert env.client.get(f"/api/jobs/{JOB_ID}").status_code == 200


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
