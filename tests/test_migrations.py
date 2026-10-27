"""Legacy jobs become captions-only Edits without changing the Classic path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app
import captions
import edits
import migrations

SET_ID = "cs_1"
STORY_ID = "s1"
TRACK_ID = "cap_legacy"
JOB_ID = "j1"


def _scene(index: int = 0, start: float = 0.0, end: float = 10.0) -> dict:
    return {
        "id": index,
        "start": start,
        "end": end,
        "dur": end - start,
        "mid": (start + end) / 2,
        "hook": 40,
        "score": 50,
        "deep": True,
        "visual_score": 50,
        "motion_score": 50.0,
        "audio_score": 50,
        "text_score": 0.0,
        "ocr": "",
        "speech": "This is the legacy story.",
        "tags": [],
        "crop": {"cx": 0.5, "cy": 0.5},
        "crop_mode": "center",
        "face": False,
    }


def _clip(**overrides) -> dict:
    value = {
        "scene": 0,
        "start": 0.0,
        "end": 10.0,
        "dur": 10.0,
        "role": "beat",
    }
    value.update(overrides)
    return value


def _story(**overrides) -> dict:
    value = {
        "id": STORY_ID,
        "title": "Legacy story",
        "start": 0.0,
        "end": 10.0,
        "dur": 10.0,
        "clips": [_clip()],
    }
    value.update(overrides)
    return value


def _job(**overrides) -> dict:
    value = {
        "id": JOB_ID,
        "status": "ready",
        "created": 1.0,
        "updated": 1.0,
        "source": {
            "name": "source.mp4",
            "path": "/tmp/source.mp4",
            "duration": 20.0,
            "width": 1920,
            "height": 1080,
            "fingerprint": "source-fingerprint",
        },
        "analysis": {
            "scenes": [_scene(0, 0.0, 10.0), _scene(1, 10.0, 20.0)],
        },
        "clip_sets": [{
            "id": SET_ID,
            "stories": [_story()],
        }],
        "renders": {},
    }
    value.update(overrides)
    return value


def _track(
    *,
    job_id: str = JOB_ID,
    track_id: str = TRACK_ID,
    clip_hash: str = "",
) -> captions.CaptionTrack:
    return captions.CaptionTrack(
        id=track_id,
        job_id=job_id,
        version=1,
        target=10,
        cues=[
            captions.CaptionCue(
                id="c1", start=0.0, end=2.0, text="First line", clip_index=0,
            ),
            captions.CaptionCue(
                id="c2", start=2.5, end=4.0, text="Second line", clip_index=0,
            ),
        ],
        style=captions.normalize_style({}),
        style_id="clean",
        cue_hash="cuehash",
        style_hash="stylehash",
        clip_hash=clip_hash,
        clip_windows=[{
            "index": 0,
            "scene": 0,
            "start": 0.0,
            "end": 10.0,
            "duration": 10.0,
        }],
        created=1.0,
    )


def _write_job(jobs: Path, job: dict) -> Path:
    directory = jobs / job["id"]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "job.json").write_text(json.dumps(job), encoding="utf-8")
    return directory


def _read_job(directory: Path) -> dict:
    return json.loads((directory / "job.json").read_text(encoding="utf-8"))


@pytest.fixture
def jobs(tmp_path: Path) -> Path:
    value = tmp_path / "data" / "jobs"
    value.mkdir(parents=True)
    return value


@pytest.fixture(autouse=True)
def _cleanup_env(monkeypatch):
    monkeypatch.setenv("VIBECUT_ENABLE_CLEANUP", "1")
    monkeypatch.delenv("VIBECUT_TOKEN", raising=False)


def test_legacy_caption_track_becomes_a_captions_only_edit(jobs):
    job = _job(story_captions={f"{SET_ID}:{STORY_ID}": TRACK_ID})
    directory = _write_job(jobs, job)
    captions.save_track(directory, _track())

    result = migrations.migrate_job(directory, now=123.0)

    assert result["changed"] is True
    assert len(result["migrated"]) == 1
    migrated = result["migrated"][0]
    assert migrated["key"] == f"{SET_ID}:{STORY_ID}:9:16"
    assert migrated["story_id"] == STORY_ID
    assert migrated["track_id"] == TRACK_ID
    assert migrated["version"] == 1
    assert migrated["source"] == "story_captions"
    stored = _read_job(directory)
    edit_id = stored["story_edits"][f"{SET_ID}:{STORY_ID}:9:16"]
    edit = edits.load_edit(directory, edit_id)
    assert edit["version"] == 1
    assert edit["parent"] is None
    assert edit["created"] == 123.0
    assert edit["aspect"] == "9:16"
    assert edit["captions"] == {
        "track_id": TRACK_ID,
        "style_id": "clean",
        "enabled": True,
    }
    assert edit["clean"] == []
    assert edit["motion"] == []
    assert edit["graphics"] == []
    assert edit["story_ref"] == {
        "set_id": SET_ID,
        "story_id": STORY_ID,
        "clip_hash": edits.clip_snapshot_hash(_story()["clips"]),
        "title": "Legacy story",
        "duration": 10.0,
        "clip_count": 1,
    }
    # Classic keeps the same pointers, files and timestamps.
    assert stored["story_captions"] == {f"{SET_ID}:{STORY_ID}": TRACK_ID}
    assert stored["updated"] == 1.0
    assert (directory / "caption_tracks" / f"{TRACK_ID}.json").is_file()
    assert captions.load_track(directory, TRACK_ID) is not None


def test_migration_is_idempotent(jobs):
    job = _job(story_captions={f"{SET_ID}:{STORY_ID}": TRACK_ID})
    directory = _write_job(jobs, job)
    captions.save_track(directory, _track())

    first = migrations.migrate_job(directory, now=100.0)
    second = migrations.migrate_job(directory, now=200.0)

    assert first["changed"] is True
    assert second["changed"] is False
    assert second["migrated"] == []
    assert second["skipped"] == [{
        "key": f"{SET_ID}:{STORY_ID}:9:16",
        "story_id": STORY_ID,
        "reason": "already_migrated",
    }]
    stored = _read_job(directory)
    assert len(list(edits.edits_dir(directory).glob("ed_*.json"))) == 1
    assert stored["story_edits"][f"{SET_ID}:{STORY_ID}:9:16"] == first["migrated"][0]["edit_id"]


def test_a_cleared_pointer_is_not_recreated(jobs):
    job = _job(story_captions={f"{SET_ID}:{STORY_ID}": TRACK_ID})
    directory = _write_job(jobs, job)
    captions.save_track(directory, _track())
    first = migrations.migrate_job(directory)

    stored = _read_job(directory)
    stored["story_edits"].pop(f"{SET_ID}:{STORY_ID}:9:16")
    (directory / "job.json").write_text(json.dumps(stored), encoding="utf-8")

    second = migrations.migrate_job(directory)

    assert second["changed"] is False
    assert second["skipped"][0]["reason"] == "existing_versions"
    assert f"{SET_ID}:{STORY_ID}:9:16" not in _read_job(directory)["story_edits"]
    assert len(list(edits.edits_dir(directory).glob("ed_*.json"))) == 1
    assert edits.load_edit(directory, first["migrated"][0]["edit_id"]) is not None


def test_missing_track_is_skipped_and_the_job_is_unchanged(jobs):
    job = _job(story_captions={f"{SET_ID}:{STORY_ID}": "cap_missing"})
    directory = _write_job(jobs, job)
    before = (directory / "job.json").read_bytes()

    result = migrations.migrate_job(directory)

    assert result["changed"] is False
    assert result["migrated"] == []
    assert result["skipped"][0]["reason"] == "track_missing:cap_missing"
    assert (directory / "job.json").read_bytes() == before
    assert "story_edits" not in _read_job(directory)


def test_existing_edit_is_never_overwritten(jobs):
    job = _job(story_captions={f"{SET_ID}:{STORY_ID}": TRACK_ID})
    directory = _write_job(jobs, job)
    captions.save_track(directory, _track())
    existing = edits.build_edit(
        story_ref={
            "set_id": SET_ID,
            "story_id": STORY_ID,
            "clip_hash": edits.clip_snapshot_hash(_story()["clips"]),
            "title": "Legacy story",
            "duration": 10.0,
            "clip_count": 1,
        },
        aspect="9:16",
        color={"preset": "warm_film"},
        created=10.0,
    )
    edits.save_edit(directory, existing)
    job["story_edits"] = {
        f"{SET_ID}:{STORY_ID}:9:16": existing["id"],
    }
    _write_job(jobs, job)

    result = migrations.migrate_job(directory, now=200.0)

    assert result["changed"] is False
    assert result["skipped"][0]["reason"] == "already_migrated"
    stored = _read_job(directory)
    assert stored["story_edits"][f"{SET_ID}:{STORY_ID}:9:16"] == existing["id"]
    loaded = edits.load_edit(directory, existing["id"])
    assert loaded["color"]["preset"] == "warm_film"
    assert len(list(edits.edits_dir(directory).glob("ed_*.json"))) == 1


def test_story_render_record_is_the_fallback_for_old_jobs(jobs):
    job = _job(renders={
        "10:s1": {
            "set_id": SET_ID,
            "story_id": STORY_ID,
            "caption_track_id": TRACK_ID,
            "created": 5.0,
        },
    })
    directory = _write_job(jobs, job)
    captions.save_track(directory, _track())

    result = migrations.migrate_job(directory)

    assert result["migrated"][0]["source"] == "story_render"
    assert result["migrated"][0]["track_id"] == TRACK_ID


def test_current_pointer_wins_over_an_older_render_record(jobs):
    current = "cap_current"
    rendered = "cap_rendered"
    job = _job(
        story_captions={f"{SET_ID}:{STORY_ID}": current},
        renders={
            "10:s1": {
                "set_id": SET_ID,
                "story_id": STORY_ID,
                "caption_track_id": rendered,
                "created": 9.0,
            },
        },
    )
    directory = _write_job(jobs, job)
    captions.save_track(directory, _track(track_id=current))
    captions.save_track(directory, _track(track_id=rendered))

    result = migrations.migrate_job(directory)

    assert result["migrated"][0]["track_id"] == current
    assert result["migrated"][0]["source"] == "story_captions"


def test_stale_pointer_falls_back_to_the_render_record(jobs):
    job = _job(
        story_captions={f"{SET_ID}:{STORY_ID}": "cap_deleted"},
        renders={
            "10:s1": {
                "set_id": SET_ID,
                "story_id": STORY_ID,
                "caption_track_id": TRACK_ID,
                "created": 5.0,
            },
        },
    )
    directory = _write_job(jobs, job)
    captions.save_track(directory, _track())

    result = migrations.migrate_job(directory)

    assert result["migrated"][0]["track_id"] == TRACK_ID
    assert result["migrated"][0]["source"] == "story_render"


def test_a_track_owned_by_another_job_is_skipped(jobs):
    job = _job(story_captions={f"{SET_ID}:{STORY_ID}": TRACK_ID})
    directory = _write_job(jobs, job)
    captions.save_track(directory, _track(job_id="another-job"))

    result = migrations.migrate_job(directory)

    assert result["changed"] is False
    assert result["skipped"][0]["reason"] == f"track_missing:{TRACK_ID}"
    assert "story_edits" not in _read_job(directory)


def test_story_without_clips_is_skipped(jobs):
    job = _job(story_captions={f"{SET_ID}:{STORY_ID}": TRACK_ID})
    job["clip_sets"][0]["stories"][0]["clips"] = []
    directory = _write_job(jobs, job)
    captions.save_track(directory, _track())

    result = migrations.migrate_job(directory)

    assert result["changed"] is False
    assert result["skipped"][0]["reason"].startswith("invalid_story:")
    assert "story_edits" not in _read_job(directory)


def test_migrate_all_isolates_a_broken_job(jobs):
    directory = _write_job(
        jobs,
        _job(story_captions={f"{SET_ID}:{STORY_ID}": TRACK_ID}),
    )
    captions.save_track(directory, _track())
    broken = jobs / "broken"
    broken.mkdir()
    (broken / "job.json").write_text("{not json", encoding="utf-8")

    summary = migrations.migrate_all(jobs)

    assert summary["scanned"] == 2
    assert summary["migrated"] == 1
    assert summary["failed"] == 1
    assert summary["errors"][0]["job_id"] == "broken"


def test_startup_hook_migrates_before_the_first_request(tmp_path, monkeypatch):
    data = tmp_path / "data"
    jobs = data / "jobs"
    sources = data / "sources"
    jobs.mkdir(parents=True)
    sources.mkdir(parents=True)
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.setattr(app, "SOURCES", sources)
    job = _job(story_captions={f"{SET_ID}:{STORY_ID}": TRACK_ID})
    directory = _write_job(jobs, job)
    captions.save_track(directory, _track())

    with TestClient(app.app) as client:
        stored = _read_job(directory)
        edit_id = stored["story_edits"][f"{SET_ID}:{STORY_ID}:9:16"]
        current = client.get(
            f"/api/jobs/{JOB_ID}/edits/current",
            params={"set_id": SET_ID, "story_id": STORY_ID, "aspect": "9:16"},
        )
        assert current.status_code == 200, current.text
        assert current.json()["id"] == edit_id
        assert current.json()["edit"]["captions"]["track_id"] == TRACK_ID


def test_classic_caption_reads_and_writes_still_work(tmp_path, monkeypatch):
    data = tmp_path / "data"
    jobs = data / "jobs"
    sources = data / "sources"
    jobs.mkdir(parents=True)
    sources.mkdir(parents=True)
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.setattr(app, "SOURCES", sources)
    job = _job(story_captions={f"{SET_ID}:{STORY_ID}": TRACK_ID})
    directory = _write_job(jobs, job)
    captions.save_track(directory, _track())
    migrations.migrate_job(directory)

    client = TestClient(app.app)
    read = client.get(f"/api/jobs/{JOB_ID}/captions/{TRACK_ID}")
    assert read.status_code == 200, read.text
    assert read.json()["id"] == TRACK_ID

    cues = read.json()["cues"]
    cues[0]["text"] = "Classic edit"
    written = client.patch(
        f"/api/jobs/{JOB_ID}/captions/{TRACK_ID}",
        json={"cues": cues},
    )
    assert written.status_code == 200, written.text
    edited_id = written.json()["id"]
    assert edited_id != TRACK_ID
    stored = _read_job(directory)
    assert stored["story_captions"][f"{SET_ID}:{STORY_ID}"] == edited_id
    assert client.get(
        f"/api/jobs/{JOB_ID}/captions/{edited_id}",
    ).status_code == 200


def test_migrated_story_render_uses_the_same_caption_track(tmp_path, monkeypatch):
    data = tmp_path / "data"
    jobs = data / "jobs"
    sources = data / "sources"
    jobs.mkdir(parents=True)
    sources.mkdir(parents=True)
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.setattr(app, "SOURCES", sources)
    job = _job(story_captions={f"{SET_ID}:{STORY_ID}": TRACK_ID})
    directory = _write_job(jobs, job)
    captions.save_track(directory, _track())
    migrations.migrate_job(directory)
    edit_id = _read_job(directory)["story_edits"][f"{SET_ID}:{STORY_ID}:9:16"]

    calls: list[tuple] = []

    def fake_queue(*args, **kwargs):
        calls.append((args, kwargs))
        return {"key": "10:cap:s1", "status": "queued", "artifact_id": ""}

    monkeypatch.setattr(app, "_queue_render", fake_queue)
    client = TestClient(app.app)
    response = client.post(
        f"/api/jobs/{JOB_ID}/clip-sets/{SET_ID}/stories/{STORY_ID}/render",
        json={"quality": "final", "aspect": "9:16", "captions": True},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["edit_id"] == edit_id
    assert body["caption_track_id"] == TRACK_ID
    assert calls
    args, kwargs = calls[-1]
    assert args[6] is True
    assert kwargs["caption_track"].id == TRACK_ID
    assert kwargs["edit"]["id"] == edit_id


def test_legacy_4_5_render_stays_on_the_classic_path(tmp_path, monkeypatch):
    data = tmp_path / "data"
    jobs = data / "jobs"
    sources = data / "sources"
    jobs.mkdir(parents=True)
    sources.mkdir(parents=True)
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.setattr(app, "SOURCES", sources)
    job = _job(story_captions={f"{SET_ID}:{STORY_ID}": TRACK_ID})
    directory = _write_job(jobs, job)
    captions.save_track(directory, _track())
    migrations.migrate_job(directory)

    calls: list[tuple] = []

    def fake_queue(*args, **kwargs):
        calls.append((args, kwargs))
        return {"key": "10:4x5:cap:s1", "status": "queued", "artifact_id": ""}

    monkeypatch.setattr(app, "_queue_render", fake_queue)
    client = TestClient(app.app)
    response = client.post(
        f"/api/jobs/{JOB_ID}/clip-sets/{SET_ID}/stories/{STORY_ID}/render",
        json={"quality": "final", "aspect": "4:5", "captions": True},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["edit_id"] is None
    assert body["caption_track_id"] == TRACK_ID
    assert calls
    assert calls[-1][1]["edit"] is None
