"""Auto Clean: Check tracklets to Edit Clean layers, never saved server-side."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app
import detect
import edits
import settings_store

JOB_ID = "auto-clean-job"
OTHER_JOB_ID = "auto-clean-other-job"
SET_ID = "cs_auto"
STORY_ID = "st_auto"
CLIPS = [{"scene": 0, "start": 0.0, "end": 8.0, "dur": 8.0, "role": "hook"}]
STORY_REF = {
    "set_id": SET_ID,
    "story_id": STORY_ID,
    "clip_hash": edits.clip_snapshot_hash(CLIPS),
    "title": "Auto clean story",
    "duration": 8.0,
    "clip_count": 1,
}


def _job_record(job_id: str = JOB_ID) -> dict:
    return {
        "id": job_id,
        "created": 1.0,
        "updated": 1.0,
        "status": "ready",
        "progress": 1.0,
        "message": "Ready",
        "error": None,
        "source": {
            "path": "/tmp/auto-clean-source.mp4",
            "name": "auto-clean-source.mp4",
            "duration": 8.0,
            "width": 1080,
            "height": 1920,
            "fps": 30.0,
            "size": 1234,
            "has_audio": True,
            "fingerprint": "auto-clean-source-fingerprint",
        },
        "options": {},
        "analysis": {
            "scene_count": 1,
            "scenes": [{
                "id": 0,
                "start": 0.0,
                "end": 8.0,
                "dur": 8.0,
                "ocr": "",
                "faces": [],
                "tags": [],
            }],
        },
        "clip_sets": [{
            "id": SET_ID,
            "job_id": job_id,
            "stories": [{
                "id": STORY_ID,
                "title": "Auto clean story",
                "start": 0.0,
                "end": 8.0,
                "dur": 8.0,
                "clips": [dict(item) for item in CLIPS],
            }],
        }],
        "renders": {},
    }


def _write_job(jobs: Path, job: dict) -> Path:
    directory = jobs / job["id"]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "job.json").write_text(json.dumps(job), encoding="utf-8")
    return directory


def _save_edit(
    directory: Path,
    *,
    clean: list[dict] | None = None,
    version: int = 1,
    parent: str | None = None,
) -> dict:
    edit = edits.build_edit(
        story_ref=STORY_REF,
        aspect="9:16",
        clean=clean or [],
        version=version,
        parent=parent,
        created=float(version),
    )
    return edits.save_edit(directory, edit)


def _tracklet(
    tracklet_id: str,
    kind: str,
    box: dict,
    *,
    ranges: list[dict] | None = None,
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


def _report(tracklets: list[dict]) -> dict:
    return {
        "schema": 1,
        "status": "ready",
        "complete": True,
        "job_id": JOB_ID,
        "created": 1.0,
        "tracklets": tracklets,
    }


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
    settings_store.save_settings({"rights": {"lock": False}})
    monkeypatch.delenv("VIBECUT_TOKEN", raising=False)
    job = _job_record()
    directory = _write_job(jobs, job)
    edit = _save_edit(directory)
    return SimpleNamespace(
        tmp_path=tmp_path,
        data=data,
        jobs=jobs,
        directory=directory,
        job=job,
        edit=edit,
        client=TestClient(app.app),
    )


def _call(env, edit_id: str | None = None, **body):
    identifier = edit_id or env.edit["id"]
    return env.client.post(
        f"/api/jobs/{JOB_ID}/edits/{identifier}/auto-clean",
        json=body,
    )


def test_report_regions_become_delogo_layers_without_saving_the_edit(env):
    detect.write_report(env.directory, _report([
        _tracklet("trk_sub", "subtitle", {"x": 0.1, "y": 0.76, "w": 0.8, "h": 0.09}),
        _tracklet("trk_title", "title", {"x": 0.1, "y": 0.2, "w": 0.8, "h": 0.18}),
        _tracklet("trk_credit", "credit", {"x": 0.4, "y": 0.9, "w": 0.2, "h": 0.03}),
    ]))
    before = edits.edit_path(env.directory, env.edit["id"]).read_bytes()

    response = _call(env)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"layers", "added", "skipped", "warnings"}
    assert body["added"] == 3
    assert [layer["kind"] for layer in body["layers"]] == ["delogo"] * 3
    assert {layer["tracklet_id"] for layer in body["layers"]} == {
        "trk_sub", "trk_title", "trk_credit",
    }
    assert body["skipped"] == []
    assert edits.normalize_clean(body["layers"]) == body["layers"]
    assert edits.edit_path(env.directory, env.edit["id"]).read_bytes() == before


def test_second_call_against_an_edit_with_the_tracklets_adds_nothing(env):
    detect.write_report(env.directory, _report([
        _tracklet("trk_sub", "subtitle", {"x": 0.1, "y": 0.76, "w": 0.8, "h": 0.09}),
        _tracklet("trk_credit", "credit", {"x": 0.4, "y": 0.9, "w": 0.2, "h": 0.03}),
    ]))
    first = _call(env)
    assert first.status_code == 200, first.text
    applied = _save_edit(
        env.directory,
        clean=first.json()["layers"],
        version=2,
        parent=env.edit["id"],
    )
    before = edits.edit_path(env.directory, applied["id"]).read_bytes()

    response = _call(env, applied["id"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["added"] == 0
    assert body["layers"] == []
    assert {item["tracklet_id"] for item in body["skipped"]} == {
        "trk_sub", "trk_credit",
    }
    assert all("already" in item["reason"].lower() for item in body["skipped"])
    assert edits.edit_path(env.directory, applied["id"]).read_bytes() == before


def test_a_saved_region_without_a_tracklet_id_is_not_added_again(env):
    detect.write_report(env.directory, _report([
        _tracklet("trk_sub", "subtitle", {"x": 0.1, "y": 0.76, "w": 0.8, "h": 0.09}),
        _tracklet("trk_title", "title", {"x": 0.1, "y": 0.2, "w": 0.8, "h": 0.18}),
    ]))
    first = _call(env)
    assert first.status_code == 200, first.text
    manual = [
        {
            key: value for key, value in layer.items()
            if key not in {"tracklet_id", "tracklet_kind"}
        }
        for layer in first.json()["layers"]
    ]
    applied = _save_edit(
        env.directory, clean=manual, version=2, parent=env.edit["id"],
    )

    response = _call(env, applied["id"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["added"] == 0
    assert body["layers"] == []
    assert all(
        "identical" in item["reason"].lower() for item in body["skipped"]
    )


def test_watermark_and_screen_text_are_skipped_not_returned(env):
    detect.write_report(env.directory, _report([
        _tracklet(
            "trk_water", "watermark",
            {"x": 0.84, "y": 0.05, "w": 0.13, "h": 0.05}, text="TikTok",
        ),
        _tracklet(
            "trk_ui", "screen_text",
            {"x": 0.05, "y": 0.03, "w": 0.2, "h": 0.05}, text="Search",
        ),
        _tracklet("trk_sub", "subtitle", {"x": 0.1, "y": 0.76, "w": 0.8, "h": 0.09}),
    ]))

    response = _call(env)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["added"] == 1
    assert [layer["tracklet_id"] for layer in body["layers"]] == ["trk_sub"]
    skipped = {item["tracklet_id"]: item for item in body["skipped"]}
    assert set(skipped) == {"trk_water", "trk_ui"}
    assert skipped["trk_water"]["reason"] == detect.WATERMARK_MESSAGE
    assert skipped["trk_ui"]["reason"] == detect.SCREEN_TEXT_MESSAGE
    assert skipped["trk_water"]["kind"] == "watermark"
    assert skipped["trk_ui"]["kind"] == "screen_text"


def test_handles_need_the_opt_in(env):
    detect.write_report(env.directory, _report([
        _tracklet(
            "trk_handle", "handle_or_logo",
            {"x": 0.02, "y": 0.03, "w": 0.15, "h": 0.05}, text="@me",
        ),
    ]))
    default = _call(env)
    assert default.status_code == 200, default.text
    assert default.json()["added"] == 0
    assert default.json()["skipped"][0]["tracklet_id"] == "trk_handle"

    opt_in = _call(env, include_handles=True)
    assert opt_in.status_code == 200, opt_in.text
    assert opt_in.json()["added"] == 1
    assert opt_in.json()["layers"][0]["kind"] == "crop_guard"


def test_missing_report_is_a_404(env):
    response = _call(env)

    assert response.status_code == 404
    assert response.json()["detail"] == "Run Scan footage first."


def test_report_without_usable_tracklets_is_a_warning_not_an_error(env):
    detect.write_report(env.directory, _report([]))

    response = _call(env)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["added"] == 0
    assert body["layers"] == []
    assert any(
        "no usable text overlays" in warning.lower()
        for warning in body["warnings"]
    )


def test_edit_from_another_job_is_rejected(env):
    other = _write_job(env.jobs, _job_record(OTHER_JOB_ID))

    response = env.client.post(
        f"/api/jobs/{OTHER_JOB_ID}/edits/{env.edit['id']}/auto-clean", json={},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Edit not found."
    assert not (other / "edits").exists()


def test_edit_whose_story_disappeared_is_rejected(env):
    job = _job_record()
    job["clip_sets"] = []
    (env.directory / "job.json").write_text(json.dumps(job), encoding="utf-8")

    response = _call(env)

    assert response.status_code == 404
    assert "story" in response.json()["detail"].lower()


def test_cross_site_writes_are_blocked(env):
    detect.write_report(env.directory, _report([]))

    response = env.client.post(
        f"/api/jobs/{JOB_ID}/edits/{env.edit['id']}/auto-clean",
        json={},
        headers={"origin": "https://evil.example"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Cross-site writes are blocked."


def test_only_text_on_screen_during_the_moment_is_added(env):
    job = _job_record()
    job["source"]["duration"] = 30.0
    job["clip_sets"][0]["stories"][0].update(start=2.0, end=8.0)
    _write_job(env.jobs, job)
    detect.write_report(env.directory, _report([
        _tracklet("trk_in", "subtitle", {"x": 0.1, "y": 0.76, "w": 0.8, "h": 0.09},
                  ranges=[{"start": 0.0, "end": 5.0}, {"start": 7.0, "end": 12.0}]),
        _tracklet("trk_out", "title", {"x": 0.1, "y": 0.2, "w": 0.8, "h": 0.18},
                  ranges=[{"start": 20.0, "end": 25.0}]),
    ]))

    body = _call(env).json()

    assert [layer["tracklet_id"] for layer in body["layers"]] == ["trk_in"]
    assert body["layers"][0]["ranges"] == [{"start": 2.0, "end": 5.0}, {"start": 7.0, "end": 8.0}]
    assert {"tracklet_id": "trk_out", "kind": "title",
            "reason": "This text is not on screen during this moment."} in body["skipped"]
