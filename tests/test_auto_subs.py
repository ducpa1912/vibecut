"""Batch auto-subtitles: one caption track per story, with failures reported."""

from __future__ import annotations

import pytest

import app

from test_clipset import (  # noqa: F401 - fixtures and helpers
    api,
    make_scenes,
    transcript_for,
    write_job,
    write_transcript,
)

URL = "/api/jobs/j1/auto-subtitles"


def _ready_set(api) -> dict:
    scenes = make_scenes(150)
    directory = write_job(api.jobs_dir, "j1", scenes=scenes)
    write_transcript(directory, transcript_for(scenes))
    response = api.post("/api/jobs/j1/clip-sets", json={"count": 3})
    assert response.status_code == 200, response.text
    record = response.json()["clip_set"]
    assert len(record["stories"]) == 3
    return record


@pytest.fixture
def ready(api):
    return _ready_set(api)


def test_all_stories_in_the_set_get_tracks(api, ready):
    response = api.post(URL, json={
        "set_id": ready["id"],
        "aspect": "9:16",
        "style_id": "clean",
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["failed"] == []
    assert [row["story_id"] for row in body["tracks"]] == [
        story["id"] for story in ready["stories"]
    ]
    for row, story in zip(body["tracks"], ready["stories"]):
        assert row["track_id"].startswith("cap_")
        assert row["style_id"] == "clean"
        assert row["cue_count"] > 0
        track = app.caption_engine.load_track(
            app._job_dir("j1"), row["track_id"],
        )
        assert track is not None
        assert len(track.cues) == row["cue_count"]
        assert track.target == int(round(float(story["dur"])))


def test_selected_story_ids_limit_the_work(api, ready):
    first, second, third = ready["stories"]
    response = api.post(URL, json={
        "set_id": ready["id"],
        "aspect": "4:5",
        "style_id": "clean",
        "story_ids": [third["id"], first["id"]],
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["failed"] == []
    assert [row["story_id"] for row in body["tracks"]] == [
        third["id"], first["id"],
    ]
    assert all(row["cue_count"] > 0 for row in body["tracks"])
    assert second["id"] not in {row["story_id"] for row in body["tracks"]}


def test_missing_transcript_fails_clearly(api):
    write_job(api.jobs_dir, "j1")
    record = api.post("/api/jobs/j1/clip-sets", json={"count": 3}).json()["clip_set"]
    response = api.post(URL, json={
        "set_id": record["id"],
        "aspect": "9:16",
        "style_id": "clean",
    })
    assert response.status_code == 409
    assert "transcript" in response.json()["detail"].lower()


def test_not_ready_job_fails_clearly(api):
    write_job(api.jobs_dir, "j1", status="reading")
    response = api.post(URL, json={"set_id": "cs_any", "aspect": "9:16"})
    assert response.status_code == 409
    assert "not ready" in response.json()["detail"].lower()


def test_empty_clip_set_fails_clearly(api):
    scenes = make_scenes(4)
    write_job(api.jobs_dir, "j1", scenes=scenes, duration=16.0)
    record = api.post("/api/jobs/j1/clip-sets", json={"count": 3}).json()["clip_set"]
    assert record["stories"] == []
    response = api.post(URL, json={
        "set_id": record["id"],
        "aspect": "9:16",
        "style_id": "clean",
    })
    assert response.status_code == 400
    assert "no stories" in response.json()["detail"].lower()


def test_invalid_set_aspect_and_style_return_4xx(api, ready):
    missing_set = api.post(URL, json={
        "set_id": "cs_missing", "aspect": "9:16", "style_id": "clean",
    })
    assert missing_set.status_code == 404

    bad_aspect = api.post(URL, json={
        "set_id": ready["id"], "aspect": "3:2", "style_id": "clean",
    })
    assert bad_aspect.status_code == 400
    assert "aspect" in bad_aspect.json()["detail"].lower()

    bad_style = api.post(URL, json={
        "set_id": ready["id"], "aspect": "9:16", "style_id": "nope",
    })
    assert bad_style.status_code == 400
    assert "style" in bad_style.json()["detail"].lower()


def test_cue_counts_match_the_saved_tracks(api, ready):
    response = api.post(URL, json={"set_id": ready["id"], "style_id": "clean"})
    assert response.status_code == 200, response.text
    rows = response.json()["tracks"]
    assert len(rows) == len(ready["stories"])
    counts = []
    for row in rows:
        track = app.caption_engine.load_track(
            app._job_dir("j1"), row["track_id"],
        )
        assert track is not None
        assert row["cue_count"] == len(track.cues) > 0
        counts.append(row["cue_count"])
    assert sum(counts) >= len(counts)


def test_unknown_story_is_reported_and_the_rest_build(api, ready):
    first = ready["stories"][0]
    response = api.post(URL, json={
        "set_id": ready["id"],
        "style_id": "clean",
        "story_ids": [first["id"], "st_missing"],
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["story_id"] for row in body["tracks"]] == [first["id"]]
    assert body["failed"] == [{
        "story_id": "st_missing",
        "error": "Story not found in this clip set.",
    }]


def test_one_broken_story_does_not_stop_the_batch(api, ready, monkeypatch):
    real_build = app.caption_engine.build_track
    broken = ready["stories"][1]["id"]

    def flaky_build(job, plan, style=None, **kwargs):
        if plan.get("story_id") == broken:
            raise ValueError("forced caption failure")
        return real_build(job, plan, style, **kwargs)

    monkeypatch.setattr(app.caption_engine, "build_track", flaky_build)
    response = api.post(URL, json={"set_id": ready["id"], "style_id": "clean"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["tracks"]) == 2
    assert body["failed"] == [{
        "story_id": broken,
        "error": "forced caption failure",
    }]


def test_cross_site_write_is_blocked(api, ready):
    response = api.post(
        URL,
        json={"set_id": ready["id"], "style_id": "clean"},
        headers={"origin": "https://evil.example"},
    )
    assert response.status_code == 403
