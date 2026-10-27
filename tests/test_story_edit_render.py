"""Story render uses the story's current Edit; no Edit keeps the legacy path."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app
import color
import edits
import fx
import overlays
import render


def make_scene(index: int, start: float, dur: float) -> dict:
    return {
        "id": index,
        "start": float(start),
        "end": float(start + dur),
        "dur": float(dur),
        "mid": float(start + dur / 2),
        "hook": 40 + index % 55,
        "score": 45 + index % 50,
        "deep": True,
        "visual_score": 40 + index % 55,
        "motion_score": 50.0,
        "audio_score": 40 + index % 55,
        "text_score": 0.0,
        "ocr": "",
        "speech": f"This is sentence {index} about the build.",
        "tags": [],
        "crop": {"cx": 0.5, "cy": 0.5},
        "crop_mode": "center",
        "face": False,
    }


@pytest.fixture
def api(tmp_path, monkeypatch):
    data = tmp_path / "data"
    jobs = data / "jobs"
    sources = data / "sources"
    jobs.mkdir(parents=True)
    sources.mkdir(parents=True)
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.setattr(app, "SOURCES", sources)
    monkeypatch.setenv("VIBECUT_EXPERIMENTAL", "1")
    client = TestClient(app.app)
    client.jobs_dir = jobs  # type: ignore[attr-defined]
    return client


def write_job(jobs: Path, job_id: str = "j1") -> Path:
    scenes = [make_scene(index, index * 4.0, 4.0) for index in range(40)]
    job = {
        "id": job_id,
        "created": time.time(),
        "updated": time.time(),
        "status": "ready",
        "progress": 1.0,
        "message": "Ready",
        "error": None,
        "source": {
            "path": "/tmp/none.mp4",
            "name": "none.mp4",
            "duration": 160.0,
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "has_audio": True,
            "size": 1,
        },
        "options": {},
        "analysis": {
            "scene_count": len(scenes),
            "scenes": scenes,
            "hook_scene": 3,
            "deep_count": len(scenes),
            "deep_scene_ids": [scene["id"] for scene in scenes],
            "plans": {"30": {"clips": [{"scene": 3}], "target": 30}},
        },
        "renders": {},
        "clip_sets": {},
    }
    directory = jobs / job_id
    directory.mkdir(parents=True)
    (directory / "job.json").write_text(json.dumps(job))
    return directory


def story(api) -> tuple[dict, dict]:
    record = api.post("/api/jobs/j1/clip-sets", json={"count": 3}).json()["clip_set"]
    return record, record["stories"][0]


def make_edit(api, record: dict, story_value: dict, *, aspect: str = "9:16") -> dict:
    text = overlays.edit_text_layer({
        "kind": "hook", "text": "Make it count", "start": 0.0,
        "end": min(2.0, float(story_value["dur"])),
    })
    response = api.post("/api/jobs/j1/edits", json={
        "set_id": record["id"],
        "story_id": story_value["id"],
        "aspect": aspect,
        "motion": [fx.punch_in(0.0, 1.0)],
        "graphics": [text, fx.sticker("fire", 0.5, 1.5)],
        "color": color.preset_plan("warm_film", use_lut=True),
    })
    assert response.status_code == 200, response.text
    return edits.load_edit(app._job_dir("j1"), response.json()["id"])


def stub_submit(monkeypatch) -> list[tuple]:
    submitted: list[tuple] = []
    monkeypatch.setattr(
        app.render_pool,
        "submit",
        lambda *args, **kwargs: submitted.append((args, kwargs)),
    )
    return submitted


def test_story_render_uses_the_current_edit(api, monkeypatch):
    write_job(api.jobs_dir)
    record, story_value = story(api)
    edit = make_edit(api, record, story_value)
    submitted = stub_submit(monkeypatch)

    response = api.post(
        f"/api/jobs/j1/clip-sets/{record['id']}/stories/{story_value['id']}/render",
        json={"quality": "final", "aspect": "9:16"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["edit_id"] == edit["id"]
    assert body["edit_hash"] == edit["hash"]
    assert submitted and submitted[-1][1]["edit"] == edit

    manifest = app.artifacts.load_manifest(app._job_dir("j1"), body["artifact_id"])
    assert manifest["spec"]["edit_hash"] == edit["hash"]
    stored = app.load_job("j1")
    queued = stored["renders"][body["render"]["record_key"]]
    assert queued["edit_id"] == edit["id"]
    assert queued["edit_hash"] == edit["hash"]


def test_story_render_without_an_edit_keeps_the_legacy_path(api, monkeypatch):
    write_job(api.jobs_dir)
    record, story_value = story(api)
    submitted = stub_submit(monkeypatch)

    response = api.post(
        f"/api/jobs/j1/clip-sets/{record['id']}/stories/{story_value['id']}/render",
        json={"quality": "final", "aspect": "9:16"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["edit_id"] is None
    assert body["edit_hash"] is None
    assert submitted and submitted[-1][1]["edit"] is None
    manifest = app.artifacts.load_manifest(app._job_dir("j1"), body["artifact_id"])
    assert "edit_hash" not in manifest["spec"]


def test_story_render_falls_back_when_the_edit_is_stale(api, monkeypatch):
    write_job(api.jobs_dir)
    record, story_value = story(api)
    make_edit(api, record, story_value)

    directory = api.jobs_dir / "j1"
    data = json.loads((directory / "job.json").read_text())
    data["clip_sets"][record["id"]]["stories"][0]["clips"][0]["start"] += 0.5
    (directory / "job.json").write_text(json.dumps(data))
    submitted = stub_submit(monkeypatch)

    response = api.post(
        f"/api/jobs/j1/clip-sets/{record['id']}/stories/{story_value['id']}/render",
        json={"quality": "final", "aspect": "9:16"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["edit_id"] is None
    assert submitted and submitted[-1][1]["edit"] is None


def test_caption_state_comes_from_the_edit(api, monkeypatch):
    write_job(api.jobs_dir)
    record, story_value = story(api)
    make_edit(api, record, story_value)
    submitted = stub_submit(monkeypatch)

    # StoryRenderBody defaults captions on; the Edit has no caption track, so
    # the render must not build or burn a legacy track behind the Edit's back.
    response = api.post(
        f"/api/jobs/j1/clip-sets/{record['id']}/stories/{story_value['id']}/render",
        json={},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["caption_track_id"] is None
    assert submitted[-1][0][8] is False  # captions flag
    manifest = app.artifacts.load_manifest(app._job_dir("j1"), body["artifact_id"])
    assert manifest["spec"]["caption"]["enabled"] is False


def test_story_queue_backend_uses_the_current_edit(api, monkeypatch):
    write_job(api.jobs_dir)
    record, story_value = story(api)
    edit = make_edit(api, record, story_value)
    submitted = stub_submit(monkeypatch)

    artifact_id = app.StoryRenderBackend().start({
        "job_id": "j1",
        "set_id": record["id"],
        "story_id": story_value["id"],
        "aspect": "9:16",
        "quality": "final",
    })
    assert app.artifacts.is_safe_artifact_id(artifact_id)
    assert submitted and submitted[-1][1]["edit"] == edit


def test_4_5_render_reads_the_4_5_edit(api, monkeypatch):
    write_job(api.jobs_dir)
    record, story_value = story(api)
    make_edit(api, record, story_value, aspect="9:16")
    edit_45 = make_edit(api, record, story_value, aspect="4:5")
    submitted = stub_submit(monkeypatch)

    response = api.post(
        f"/api/jobs/j1/clip-sets/{record['id']}/stories/{story_value['id']}/render",
        json={"aspect": "4:5"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["edit_id"] == edit_45["id"]
    assert submitted[-1][1]["edit"] == edit_45
    manifest = app.artifacts.load_manifest(
        app._job_dir("j1"), response.json()["artifact_id"],
    )
    assert manifest["spec"]["aspect"] == "4:5"
    assert manifest["spec"]["edit_hash"] == edit_45["hash"]


def test_run_render_forwards_the_edit_to_render_reel(api, monkeypatch):
    write_job(api.jobs_dir)
    record, story_value = story(api)
    edit = make_edit(api, record, story_value)
    plan = app._story_plan(
        app.load_job("j1"), record, story_value, record["id"],
    )
    clips = [
        {
            "scene": clip["scene"], "start": clip["start"],
            "dur": clip["dur"], "frames": 30,
        }
        for clip in plan["clips"][:1]
    ]
    captured: dict = {}

    def fake_render(*args, **kwargs):
        captured.update(kwargs)
        raise render.RenderCancelled("stop")

    monkeypatch.setattr(app.render, "render_reel", fake_render)
    app.run_render(
        "j1", 2, plan, "key", "final", "9:16", None, False, None, "",
        None, 0.075, None, None, 0, clips, 2.0, edit,
    )
    assert captured["edit"] == edit


def test_stale_edit_warning_is_logged(api, caplog):
    write_job(api.jobs_dir)
    record, story_value = story(api)
    make_edit(api, record, story_value)
    directory = api.jobs_dir / "j1"
    data = json.loads((directory / "job.json").read_text())
    data["clip_sets"][record["id"]]["stories"][0]["clips"][0]["start"] += 0.5
    (directory / "job.json").write_text(json.dumps(data))
    job = app.load_job("j1")
    current = next(
        item for item in job["clip_sets"][record["id"]]["stories"]
        if item["id"] == story_value["id"]
    )
    with caplog.at_level("WARNING", logger="vibecut"):
        resolved = app._story_edit_for_render(
            job, current, record["id"], "9:16",
        )
    assert resolved is None
    assert any("changed since Edit" in row.message for row in caplog.records)


def test_edit_captions_enable_the_track_for_the_edit_render(api, monkeypatch):
    import captions as caption_engine

    write_job(api.jobs_dir)
    record, story_value = story(api)
    plan = app._story_plan(
        app.load_job("j1"), record, story_value, record["id"],
    )
    prepared = render.prepare_render(plan, app.load_job("j1")["source"], None)
    track = caption_engine.CaptionTrack(
        id="cap_edit",
        job_id="j1",
        version=1,
        target=int(plan["target"]),
        cues=[caption_engine.CaptionCue.from_value({
            "id": "c1", "start": 0.0, "end": 1.0, "text": "Hello", "clip_index": 0,
        })],
        clip_hash=caption_engine.clip_hash(prepared["clips"]),
    )
    edit = edits.build_edit(
        story_ref={
            "set_id": record["id"],
            "story_id": story_value["id"],
            "clip_hash": edits.clip_snapshot_hash(story_value["clips"]),
            "title": story_value["title"],
            "duration": story_value["dur"],
            "clip_count": len(story_value["clips"]),
        },
        aspect="9:16",
        graphics=[overlays.edit_text_layer({
            "kind": "hook", "text": "Hook", "start": 0.0, "end": 2.0,
        })],
        captions={"track_id": "cap_edit", "enabled": True},
    )
    edits.save_edit(app._job_dir("j1"), edit)
    app.update_job("j1", lambda job: edits.set_pointer(job, edit))
    monkeypatch.setattr(app, "_caption_track_by_id", lambda job_id, track_id: track)
    submitted = stub_submit(monkeypatch)

    response = api.post(
        f"/api/jobs/j1/clip-sets/{record['id']}/stories/{story_value['id']}/render",
        json={},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["caption_track_id"] == "cap_edit"
    assert submitted[-1][0][8] is True
    assert submitted[-1][1]["edit"] == edit
    manifest = app.artifacts.load_manifest(app._job_dir("j1"), body["artifact_id"])
    assert manifest["spec"]["caption"]["enabled"] is True
    assert manifest["spec"]["edit_hash"] == edit["hash"]


def _submitted_audio_plan(submitted: list[tuple]) -> dict | None:
    args = submitted[-1][0]
    run_args = args[1:] if callable(args[0]) else args
    return run_args[8]  # job_id, target, plan, key, quality, aspect, encoder, captions, audio_plan


def test_story_render_mixes_the_edit_audio_layer(api, monkeypatch):
    write_job(api.jobs_dir)
    record, story_value = story(api)
    edit = make_edit(api, record, story_value)
    patched = api.patch(f"/api/jobs/j1/edits/{edit['id']}", json={
        "audio": {"mode": "original_bed", "duck_db": -10},
    })
    assert patched.status_code == 200, patched.text
    submitted = stub_submit(monkeypatch)
    response = api.post(
        f"/api/jobs/j1/clip-sets/{record['id']}/stories/{story_value['id']}/render",
        json={"quality": "final", "aspect": "9:16"},
    )
    assert response.status_code == 200, response.text
    plan = _submitted_audio_plan(submitted)
    assert plan is not None and plan["mode"] == "original_bed"


def test_captions_only_edit_keeps_the_legacy_audio_path(api, monkeypatch):
    write_job(api.jobs_dir)
    record, story_value = story(api)
    make_edit(api, record, story_value)
    submitted = stub_submit(monkeypatch)
    response = api.post(
        f"/api/jobs/j1/clip-sets/{record['id']}/stories/{story_value['id']}/render",
        json={"quality": "final", "aspect": "9:16"},
    )
    assert response.status_code == 200, response.text
    assert _submitted_audio_plan(submitted) is None


def test_classic_caption_change_becomes_a_new_edit_version(api, monkeypatch):
    write_job(api.jobs_dir)
    record, story_value = story(api)
    edit = make_edit(api, record, story_value)
    calls = []
    monkeypatch.setattr(
        app.routes_edits, "patch_edit",
        lambda job_id, edit_id, body: calls.append((edit_id, body.captions)),
    )
    key = f"{record['id']}:{story_value['id']}"
    app._set_story_track("j1", key, "cap_new")
    assert app.load_job("j1")["story_captions"][key] == "cap_new"
    assert calls == [(edit["id"], {**edit["captions"], "track_id": "cap_new"})]
