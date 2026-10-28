"""A stale Edit fails closed: render, Finish queue, packet and Edit payload.

Every test uses a scratch ``VIBECUT_DATA`` tree through the app fixture. The
render pool is stubbed, so no ffmpeg, network or model pack is touched.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app
import caption_reflow
import captions as caption_engine
import edits
import exports
import overlays
import packet
import routes_edits


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
    monkeypatch.setattr(caption_engine, "DATA", data)
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


def write_transcript(directory: Path) -> None:
    folder = directory / "transcript"
    folder.mkdir(parents=True, exist_ok=True)
    segments = [
        {"start": index * 4.0 + 0.2, "end": index * 4.0 + 3.6,
         "text": f"This is sentence {index} about the build."}
        for index in range(40)
    ]
    (folder / "transcript.json").write_text(json.dumps({"segments": segments}))


def story(api) -> tuple[dict, dict]:
    record = api.post("/api/jobs/j1/clip-sets", json={"count": 3}).json()["clip_set"]
    return record, record["stories"][0]


def make_edit(api, record: dict, story_value: dict) -> dict:
    text = overlays.edit_text_layer({
        "kind": "hook", "text": "Make it count", "start": 0.0,
        "end": min(2.0, float(story_value["dur"])),
    })
    response = api.post("/api/jobs/j1/edits", json={
        "set_id": record["id"],
        "story_id": story_value["id"],
        "aspect": "9:16",
        "graphics": [text],
    })
    assert response.status_code == 200, response.text
    return edits.load_edit(app._job_dir("j1"), response.json()["id"])


def stale_the_story(jobs: Path, record: dict) -> dict:
    path = jobs / "j1" / "job.json"
    data = json.loads(path.read_text())
    data["clip_sets"][record["id"]]["stories"][0]["clips"][0]["start"] += 0.5
    path.write_text(json.dumps(data))
    return app.load_job("j1")


def stub_submit(monkeypatch) -> list[tuple]:
    submitted: list[tuple] = []
    monkeypatch.setattr(
        app.render_pool,
        "submit",
        lambda *args, **kwargs: submitted.append((args, kwargs)),
    )
    return submitted


def test_stale_edit_raises_409_with_the_repair_message(api):
    write_job(api.jobs_dir)
    record, story_value = story(api)
    make_edit(api, record, story_value)
    job = stale_the_story(api.jobs_dir, record)
    current = next(
        item for item in job["clip_sets"][record["id"]]["stories"]
        if item["id"] == story_value["id"]
    )

    with pytest.raises(app.HTTPException) as raised:
        app._story_edit_for_render(job, current, record["id"], "9:16")

    assert raised.value.status_code == 409
    assert raised.value.detail == {
        "code": "edit_stale",
        "message": (
            "This story changed after its Edit was made. "
            "Open it in Edit and press Repair."
        ),
    }


def test_unreadable_edit_pointer_raises_409(api):
    write_job(api.jobs_dir)
    record, story_value = story(api)
    make_edit(api, record, story_value)
    key = edits.story_key(record["id"], story_value["id"], "9:16")

    def mutate(job: dict) -> None:
        job["story_edits"][key] = "ed_missing"

    app.update_job("j1", mutate)
    job = app.load_job("j1")
    current = next(
        item for item in job["clip_sets"][record["id"]]["stories"]
        if item["id"] == story_value["id"]
    )

    with pytest.raises(app.HTTPException) as raised:
        app._story_edit_for_render(job, current, record["id"], "9:16")
    assert raised.value.detail["code"] == "edit_stale"


def test_story_render_fails_closed_and_queues_nothing(api, monkeypatch):
    write_job(api.jobs_dir)
    record, story_value = story(api)
    make_edit(api, record, story_value)
    stale_the_story(api.jobs_dir, record)
    submitted = stub_submit(monkeypatch)

    response = api.post(
        f"/api/jobs/j1/clip-sets/{record['id']}/stories/{story_value['id']}/render",
        json={"quality": "final", "aspect": "9:16"},
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "edit_stale"
    assert submitted == []


def test_no_pointer_still_uses_the_legacy_plan_path(api, monkeypatch):
    write_job(api.jobs_dir)
    record, story_value = story(api)
    submitted = stub_submit(monkeypatch)

    response = api.post(
        f"/api/jobs/j1/clip-sets/{record['id']}/stories/{story_value['id']}/render",
        json={"quality": "final", "aspect": "9:16"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["edit_id"] is None
    assert submitted and submitted[-1][1]["edit"] is None


def test_finish_queue_refuses_a_stale_edit_before_it_starts(api):
    write_job(api.jobs_dir)
    record, story_value = story(api)
    make_edit(api, record, story_value)
    stale_the_story(api.jobs_dir, record)

    response = api.post("/api/story-queues", json={"items": [{
        "job_id": "j1",
        "set_id": record["id"],
        "story_id": story_value["id"],
        "aspect": "9:16",
        "quality": "final",
    }]})

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "edit_stale"


def test_packet_refuses_a_stale_edit(api):
    write_job(api.jobs_dir)
    record, story_value = story(api)
    make_edit(api, record, story_value)
    stale_the_story(api.jobs_dir, record)
    job = app.load_job("j1")

    with pytest.raises(packet.PacketError) as raised:
        packet.build_packet(
            job, app._job_dir("j1"),
            packet.PacketRequest(
                story_id=story_value["id"],
                titles=["One", "Two", "Three"],
                description="x" * 125,
            ),
        )

    assert raised.value.status == 409
    assert raised.value.code == "edit_stale"
    assert raised.value.message == (
        "This story changed after its Edit was made. "
        "Open it in Edit and press Repair."
    )


def test_edit_payload_marks_a_stale_edit(api):
    write_job(api.jobs_dir)
    record, story_value = story(api)
    edit = make_edit(api, record, story_value)

    fresh = routes_edits._payload(edit, job=app.load_job("j1"))
    assert fresh["stale"] is False
    assert fresh["edit"]["stale"] is False

    job = stale_the_story(api.jobs_dir, record)
    stale = routes_edits._payload(edit, job=job)
    assert stale["stale"] is True
    assert stale["edit"]["stale"] is True


def _track(
    job: dict,
    record: dict,
    story_value: dict,
    clip_hash: str,
    track_id: str,
) -> caption_engine.CaptionTrack:
    return caption_engine.CaptionTrack(
        id=track_id,
        job_id="j1",
        version=1,
        target=int(round(story_value["dur"])),
        cues=[caption_engine.CaptionCue.from_value({
            "id": "c001", "start": 0.2, "end": 1.6,
            "text": "Hello there", "clip_index": 0,
        })],
        style=caption_engine.normalize_style({}, style_id="clean"),
        style_id="clean",
        clip_hash=clip_hash,
    )


def test_edit_caption_track_rejects_a_mismatched_hash(api, monkeypatch):
    write_job(api.jobs_dir)
    record, story_value = story(api)
    edit = make_edit(api, record, story_value)
    job = app.load_job("j1")
    bad = _track(
        job, record, story_value, "cap_old_cut", "cap_bad",
    )
    caption_engine.save_track(app._job_dir("j1"), bad)
    patched = api.patch(f"/api/jobs/j1/edits/{edit['id']}", json={
        "captions": {"track_id": bad.id, "enabled": True},
    })
    assert patched.status_code == 200, patched.text
    edit = edits.load_edit(app._job_dir("j1"), patched.json()["id"])
    monkeypatch.setattr(
        app, "_caption_track_by_id", lambda job_id, track_id: bad,
    )

    with pytest.raises(app.HTTPException) as raised:
        app._edit_caption_track("j1", edit)
    assert raised.value.status_code == 409

    good = _track(
        job, record, story_value,
        edits.clip_snapshot_hash(story_value["clips"]),
        "cap_good",
    )
    monkeypatch.setattr(
        app, "_caption_track_by_id", lambda job_id, track_id: good,
    )
    enabled, resolved = app._edit_caption_track("j1", edit)
    assert enabled is True and resolved is good


def test_default_story_track_rebuilds_when_the_cached_track_is_from_an_old_cut(api):
    write_transcript(write_job(api.jobs_dir))
    record, story_value = story(api)

    first = app.default_story_caption_track("j1", record["id"], story_value["id"])
    assert first is not None and first.cues

    job = stale_the_story(api.jobs_dir, record)
    current = next(
        item for item in job["clip_sets"][record["id"]]["stories"]
        if item["id"] == story_value["id"]
    )

    second = app.default_story_caption_track("j1", record["id"], story_value["id"])

    assert second is not None and second.cues
    assert second.id != first.id
    prepared = app._story_track_plan(
        job, app._story_plan(job, record, current, record["id"]),
    )
    assert second.clip_hash in {
        edits.clip_snapshot_hash(current["clips"]),
        caption_engine.clip_hash(prepared["clips"]),
    }


def test_burn_srt_and_packet_share_one_track(api, tmp_path):
    write_transcript(write_job(api.jobs_dir))
    record, story_value = story(api)
    job = app.load_job("j1")
    plan = app._story_plan(job, record, story_value, record["id"])
    track_plan = app._story_track_plan(job, plan)
    track = caption_engine.build_track(
        job, track_plan, caption_engine.normalize_style({}, style_id="clean"),
        job_dir=None,
    )
    caption_engine.save_track(app._job_dir("j1"), track)

    burning = dict(plan)
    app._attach_caption_track(burning, track)
    burnt_cues = [cue.to_dict() for cue in track.cues]
    assert burning["_caption_cues"] == burnt_cues

    srt_cues = exports.plan_cues(burning, plan["clips"], job["analysis"]["scenes"])
    srt_text = app.cuts.srt(srt_cues)
    assert srt_cues == burnt_cues
    assert track.cues[0].text.replace("\n", " ").split()[0].lower() in srt_text.lower()

    # The packet reads the artifact SRT written from the same cues.
    text, source = packet._captions_from_record(
        job, app._job_dir("j1"),
        {"captions_srt": srt_text}, plan,
    )
    assert source == "artifact"
    assert text == srt_text


def test_caption_reflow_track_hash_is_the_new_story_hash(api):
    write_transcript(write_job(api.jobs_dir))
    record, story_value = story(api)
    job = app.load_job("j1")
    old_plan = app._story_track_plan(
        job, app._story_plan(job, record, story_value, record["id"]),
    )
    old_track = caption_engine.build_track(
        job, old_plan, caption_engine.normalize_style({}, style_id="clean"),
        job_dir=None,
    )
    caption_engine.save_track(app._job_dir("j1"), old_track)
    new_story = dict(story_value)
    new_story["clips"] = [
        {**clip, "start": clip["start"] + 4.0, "end": clip["end"] + 4.0}
        for clip in story_value["clips"]
    ]

    result = caption_reflow.rebuild_for_story(
        "j1", job, record["id"], story_value, new_story, old_track.id,
    )

    assert result.track.clip_hash == caption_engine.clip_hash(new_story["clips"])
    assert result.track.job_id == "j1"
    assert result.track.version == old_track.version + 1
