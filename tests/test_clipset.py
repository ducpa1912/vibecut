"""Clip sets, selection v2 and the hook/cover matrix."""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app
import artifacts
import clipset
import matrix
import render
import selection


def make_scene(index: int, start: float, dur: float, **extra) -> dict:
    scene = {
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
        "speech": (
            f"This is sentence {index} about the build. "
            "It explains the result."
        ),
        "tags": [],
        "crop": {"cx": 0.5, "cy": 0.5},
        "crop_mode": "center",
        "face": index % 2 == 0,
    }
    scene.update(extra)
    return scene


def make_scenes(count: int = 150, dur: float = 4.0, rich: bool = False) -> list[dict]:
    scenes = [make_scene(index, index * dur, dur) for index in range(count)]
    if rich:
        # Three distinct sentences give every story three hook variants even
        # when spread selection lands on a late scene.
        for scene in scenes:
            scene["speech"] += f" Step {scene['id']} closes the loop."
    return scenes


def transcript_for(scenes: list[dict]) -> list[dict]:
    return [
        {
            "start": scene["start"],
            "end": scene["end"],
            "text": scene["speech"],
        }
        for scene in scenes
    ]


def test_clipset_count_variance_and_sentence_boundaries():
    scenes = make_scenes(150)
    transcript = transcript_for(scenes)
    starts = {
        round(sentence["start"], 3)
        for sentence in clipset.source_sentences(scenes, transcript)
    }

    three = clipset.build_clipset(
        scenes, transcript, 600.0, count=3,
    )
    six = clipset.build_clipset(
        scenes, transcript, 600.0, count=6,
    )

    assert three["available"] == 3
    assert 3 <= six["available"] <= 6
    assert len(three["stories"]) <= 3
    for document in (three, six):
        assert document["source"]["fallback"] == "transcript"
        for story in document["stories"]:
            assert 20.0 - 0.01 <= story["dur"] <= 75.0 + 0.01
            assert story["hook"]["id"] == story["sentences"][0]["id"]
            assert story["payoff"]["id"] == story["sentences"][-1]["id"]
            assert round(story["hook"]["start"], 3) in starts
            assert clipset._terminal_text(story["payoff"]["text"])
            assert story["clips"][0]["role"] == "hook"
            assert story["clips"][-1]["role"] == "payoff"
            assert story["score_breakdown"].keys() == {
                "hook_score", "speech_coherence", "audio_energy",
                "visual_quality", "payoff_position", "novelty",
            }
            types = {item["type"] for item in story["evidence"]}
            assert types == {"transcript", "visual", "audio", "structure"}
            assert "(transcript)" in story["evidence"][0]["text"]
            assert all(set(item) == {"type", "text", "scene", "time"} for item in story["evidence"])
            assert "virality" not in json.dumps(story).lower()
    ordered = sorted(six["stories"], key=lambda story: story["start"])
    for left, right in zip(ordered, ordered[1:]):
        assert left["end"] <= right["start"] + 0.001


def test_clipset_does_not_fabricate_count_and_handles_short_source():
    scenes = make_scenes(14)  # 56 seconds
    document = clipset.build_clipset(scenes, None, 56.0, count=6)
    assert 0 <= document["available"] <= 2
    assert document["available"] == len(document["stories"])
    assert document["note"]

    short = clipset.build_clipset(scenes[:4], None, 16.0, count=3)
    assert short["stories"] == []
    assert short["available"] == 0
    assert "at least 20s" in short["note"]


def test_clipset_scene_text_fallback():
    scenes = make_scenes(30)
    document = clipset.build_clipset(scenes, None, 120.0, count=3)
    assert document["available"] >= 1
    assert document["source"]["transcript"] is False
    assert document["source"]["scene_text"] is True
    assert document["source"]["fallback"] == "scene_text"
    assert "(scene)" in document["stories"][0]["evidence"][0]["text"]
    assert document["stories"][0]["evidence"][0]["type"] == "scene"

    silent = [make_scene(index, index * 4.0, 4.0, speech="", ocr="") for index in range(30)]
    empty = clipset.build_clipset(silent, None, 120.0, count=3)
    assert empty["stories"] == []
    assert "No transcript or scene text" in empty["note"]


def test_clipset_locks_and_bans_ban_wins():
    scenes = make_scenes(150)
    locked = clipset.build_clipset(
        scenes, None, 600.0, count=3, locks=[20],
    )
    assert locked["locks"] == [20]
    assert any(20 in story["scenes"] for story in locked["stories"])

    banned = clipset.build_clipset(
        scenes, None, 600.0, count=3, locks=[20], ban_scenes=[20],
    )
    assert banned["locks"] == []
    assert banned["ban_scenes"] == [20]
    assert all(20 not in story["scenes"] for story in banned["stories"])


def test_clipset_edits_persist_exclude_reorder_lock_and_ban():
    scenes = make_scenes(150)
    document = clipset.build_clipset(scenes, None, 600.0, count=3)
    sentences = clipset.source_sentences(scenes)
    first, second, third = document["stories"][:3]
    first_ids = [sentence["id"] for sentence in first["sentences"]]
    excluded_id = third["sentences"][0]["id"]
    ban_scene = second["scenes"][0]
    lock_scene = first["scenes"][-1]

    edited = clipset.apply_edits(
        document,
        sentences,
        scenes,
        600.0,
        excluded_sentences=[excluded_id],
        locks=[lock_scene, ban_scene],
        ban_scenes=[ban_scene],
        story_patches=[{
            "id": first["id"],
            "sentences": list(reversed(first_ids)),
        }],
    )

    assert edited["excluded_sentences"] == sorted([excluded_id])
    assert ban_scene in edited["ban_scenes"]
    assert ban_scene not in edited["locks"]
    assert edited["locks"] == [lock_scene]
    assert excluded_id not in {
        sentence["id"]
        for story in edited["stories"]
        for sentence in story["sentences"]
    }
    rewritten = next(story for story in edited["stories"] if story["id"] == first["id"])
    assert [sentence["id"] for sentence in rewritten["sentences"]] == list(reversed(first_ids))
    assert rewritten["edited"] is True
    assert all(ban_scene not in story["scenes"] for story in edited["stories"])

    plan = clipset.story_to_plan(rewritten, scenes)
    assert plan["auto"] is False
    assert plan["clip_count"] == len(plan["clips"])
    assert plan["clips"][0]["role"] == "hook"
    assert plan["clips"][-1]["role"] == "payoff"
    assert plan["clips"][0]["scene"] == rewritten["sentences"][0]["scene"]
    assert plan["story_id"] == first["id"]


def test_clipset_rejects_bad_parameters():
    scenes = make_scenes(30)
    for count in (2, 13):
        with pytest.raises(clipset.ClipSetError):
            clipset.build_clipset(scenes, None, 120.0, count=count)
    with pytest.raises(clipset.ClipSetError):
        clipset.build_clipset(scenes, None, 120.0, min_s=10, max_s=75)
    with pytest.raises(clipset.ClipSetError):
        clipset.build_clipset(scenes, None, 120.0, order="random")


def test_90_minute_clipset_build_is_seconds_scale(monkeypatch):
    scenes = make_scenes(1350)
    transcript = transcript_for(scenes)
    scored: list[int] = []
    original_score = clipset._score_story

    def counted_score(*args, **kwargs):
        scored.append(1)
        return original_score(*args, **kwargs)

    monkeypatch.setattr(clipset, "_score_story", counted_score)
    started = time.perf_counter()
    document = clipset.build_clipset(
        scenes, transcript, 5400.0, count=6,
    )
    elapsed = time.perf_counter() - started
    assert document["available"] >= 3
    assert document["candidate_total"] > clipset.CANDIDATE_LIMIT
    assert document["candidate_scored"] <= clipset.CANDIDATE_LIMIT
    assert len(scored) <= clipset.CANDIDATE_LIMIT + 20
    assert all(story["clips"] for story in document["stories"])
    assert elapsed < 25.0, f"90-minute clip set took {elapsed:.1f}s"


def test_zero_overlap_story_is_rejected_and_zero_clip_fails():
    scenes = [
        make_scene(0, 100.0, 4.0),
        make_scene(1, 104.0, 4.0),
    ]
    sentences = [
        {
            "id": 0,
            "start": 0.0,
            "end": 20.0,
            "text": "A sentence far outside every scene. It has no honest clip.",
            "scene": None,
            "scenes": [],
            "source": "transcript",
            "dur": 20.0,
        },
    ]
    story = clipset._story_from_sentences(
        sentences, scenes, 600.0, "st_zero_overlap",
    )
    assert story is None

    document = clipset.build_clipset(
        scenes,
        [{
            "start": 0.0,
            "end": 20.0,
            "text": "A sentence far outside every scene.",
        }],
        600.0,
        count=3,
    )
    assert document["available"] == 0
    assert all(story["clips"] for story in document["stories"])

    broken = {
        "id": "st_zero_clip",
        "clips": [],
        "sentences": sentences,
        "hook": sentences[0],
        "payoff": sentences[0],
        "dur": 20.0,
        "start": 0.0,
        "end": 20.0,
    }
    with pytest.raises(clipset.ClipSetError):
        clipset.story_to_plan(broken, scenes)
    with pytest.raises(matrix.MatrixError):
        matrix.build_matrix(broken, scenes)


def test_matrix_short_clip_is_full_or_explicit_error():
    scenes = make_scenes(75)
    document = clipset.build_clipset(scenes, None, 300.0, count=6)
    story = next(
        story for story in document["stories"]
        if len(selection.hook_candidates(story, 3)) == 3
    )
    short = copy.deepcopy(story)
    clip = short["clips"][0]
    clip["end"] = clip["start"] + 0.05
    clip["dur"] = 0.05
    short["clips"] = [clip]

    payload = matrix.build_matrix(short, scenes)
    assert len(payload["covers"]) == 3
    assert len(payload["hooks"]) == 3
    assert len(payload["jobs"]) == 9


def test_speech_coherence_accounts_for_unspoken_duration():
    stats = {
        0: {
            "dur": 10.0,
            "terminal": True,
            "hook": 0.5,
            "keywords": {"alpha"},
            "word_count": 0,
        },
        1: {
            "dur": 10.0,
            "terminal": True,
            "hook": 0.5,
            "keywords": {"beta"},
            "word_count": 10,
        },
    }
    sentences = [
        {"id": 0, "dur": 10.0, "text": ""},
        {"id": 1, "dur": 10.0, "text": "beta beta beta"},
    ]
    half_spoken = clipset._speech_coherence(
        sentences, stats, keywords={"beta"}, word_count=10,
    )
    full_spoken = clipset._speech_coherence(
        sentences, stats, keywords={"alpha", "beta"}, word_count=10,
    )
    assert half_spoken < full_spoken
    assert 0.5 <= half_spoken < 0.7


def test_matrix_partial_result_lists_per_story_errors():
    scenes = make_scenes(75)
    document = clipset.build_clipset(scenes, None, 300.0, count=3)
    valid = copy.deepcopy(document["stories"][0])
    broken = copy.deepcopy(document["stories"][1])
    broken["clips"] = []
    result = matrix.build_matrix_for_stories([valid, broken], scenes)
    assert result["complete"] is False
    assert result["count"] == 1
    assert result["job_count"] == 9
    assert result["error_count"] == 1
    assert result["errors"][0]["story_id"] == broken["id"]
    assert result["errors"][0]["complete"] is False
    assert "no materialized clips" in result["errors"][0]["error"]
    assert len(result["matrices"][0]["jobs"]) == 9


def test_arc_order_puts_strongest_hook_first_and_payoff_last():
    scenes = make_scenes(150)
    document = clipset.build_clipset(scenes, None, 600.0, count=3)
    stories = copy.deepcopy(document["stories"])
    stories[0]["score_breakdown"]["hook_score"] = 0.99
    stories[0]["score_breakdown"]["payoff_position"] = 0.10
    stories[1]["score_breakdown"]["hook_score"] = 0.10
    stories[1]["score_breakdown"]["payoff_position"] = 0.99
    stories[2]["score_breakdown"]["hook_score"] = 0.20
    stories[2]["score_breakdown"]["payoff_position"] = 0.20

    ordered = clipset._order_stories(stories, "arc")
    assert ordered[0] is stories[0]
    assert ordered[-1] is stories[1]
    assert ordered[1] is stories[2]
    assert clipset._order_stories(stories, "source") != ordered


def test_duplicate_hook_texts_are_reported_not_padded():
    scenes = make_scenes(75)
    document = clipset.build_clipset(scenes, None, 300.0, count=3)
    story = copy.deepcopy(document["stories"][0])
    sentence = dict(
        story["sentences"][0],
        text="Yes.",
        start=0.0,
        end=1.0,
        dur=1.0,
    )
    story["sentences"] = [sentence]
    story["hook"] = sentence
    story["payoff"] = sentence
    hooks = selection.hook_candidates(story, 3)
    assert len(hooks) < 3
    assert len({hook["text"] for hook in hooks}) == len(hooks)
    ranked = selection.rank_stories([story], scenes=scenes)
    assert ranked["ranked"][0]["hook_candidates_complete"] is False
    with pytest.raises(matrix.MatrixError):
        matrix.build_matrix(story, scenes)


def test_partial_transcript_merges_scene_text_and_warns_on_truncation():
    scenes = make_scenes(30)
    transcript = transcript_for(scenes[:10])
    stats: dict = {}
    sentences = clipset.source_sentences(scenes, transcript, stats=stats)
    assert stats["partial_scene_fallback"] > 0
    assert {sentence["source"] for sentence in sentences} == {"transcript", "scene"}

    document = clipset.build_clipset(
        scenes, transcript, 120.0, count=3,
    )
    assert document["source"]["partial_scene_fallback"] > 0
    assert document["source"]["fallback"] == "transcript"

    many = [
        {"start": index * 0.1, "end": index * 0.1 + 0.1, "text": f"T{index}."}
        for index in range(4100)
    ]
    trunc_stats: dict = {}
    clipset.source_sentences([make_scene(0, 0.0, 500.0)], many, stats=trunc_stats)
    assert trunc_stats["truncated"] is True
    assert trunc_stats["sentence_returned"] == 4000


def _ranked_story(scenes: list[dict]) -> dict:
    document = clipset.build_clipset(scenes, None, 600.0, count=3)
    return document["stories"][0]


def test_selection_v2_prompt_exclusions_and_evidence():
    assert selection.parse_exclusions("no more than 3 clips") == []
    assert selection.parse_exclusions(
        "no politics, crypto, or religion"
    ) == ["politics", "crypto", "religion"]
    assert selection.parse_exclusions(
        "not only politics but also crypto"
    ) == ["politics", "crypto"]
    assert selection.parse_exclusions(
        "no politics but make it funny"
    ) == ["politics"]
    assert selection.parse_exclusions("no show") == ["show"]
    assert selection.parse_exclusions("no use") == ["use"]
    assert selection.parse_exclusions(
        "", ["show", "tell", "use", "include"]
    ) == ["show", "tell", "use", "include"]
    assert selection.parse_exclusions("do not include intro") == ["intro"]
    scenes = make_scenes(150)
    story = _ranked_story(scenes)
    clean = copy.deepcopy(story)
    dirty = copy.deepcopy(story)
    dirty["id"] = "politics-story"
    dirty["title"] = "The politics of the build"
    dirty["hook"]["text"] = "Politics is the topic."
    dirty["sentences"][0]["text"] = "Politics is the topic."

    result = selection.rank_stories(
        [dirty, clean],
        prompt="no politics, avoid crypto",
        scenes=scenes,
        source_duration=600.0,
    )

    assert result["exclusions"] == ["politics", "crypto"]
    assert [item["id"] for item in result["excluded"]] == ["politics-story"]
    assert result["excluded"][0]["matched_exclusions"] == ["politics"]
    assert result["excluded"][0]["evidence"]
    assert all(item["id"] != "politics-story" for item in result["ranked"])
    top = result["ranked"][0]
    assert top["v2_score"] > 0
    assert set(top["v2_breakdown"]) == {
        "hook_score", "speech_coherence", "audio_energy",
        "visual_quality", "payoff_position", "novelty",
    }
    assert top["v2_evidence"]
    assert all(item["type"] in {"transcript", "scene", "visual", "audio", "structure"} for item in top["v2_evidence"])
    assert all(set(item) == {"type", "text", "scene", "time"} for item in top["v2_evidence"])
    assert len(top["hook_candidates"]) == 3
    assert top["hook_candidates"][0]["text"] == top["hook"]["text"]
    assert all(candidate["story_id"] == top["id"] for candidate in top["hook_candidates"])
    assert len({candidate["id"] for candidate in top["hook_candidates"]}) == 3
    assert top["plan"]["story_id"] == top["id"]
    assert result["default_plan_unchanged"] is True


def test_selection_v2_explicit_exclusion_list():
    scenes = make_scenes(60)
    story = _ranked_story(scenes)
    story = copy.deepcopy(story)
    story["id"] = "crypto-story"
    story["sentences"][0]["text"] = "Crypto is the whole story."
    story["title"] = "Crypto story"
    result = selection.rank_stories(
        [story], exclusions=["crypto"], scenes=scenes, source_duration=600.0,
    )
    assert result["ranked"] == []
    assert result["excluded"][0]["matched_exclusions"] == ["crypto"]
    assert "Every candidate" in result["note"]


def test_matrix_three_hooks_three_covers_nine_sequential_jobs():
    scenes = make_scenes(150)
    story = _ranked_story(scenes)
    first = matrix.build_matrix(story, scenes)
    second = matrix.build_matrix(story, scenes)

    assert len(first["hooks"]) == 3
    assert len(first["covers"]) == 3
    assert len(first["cells"]) == 9
    assert len(first["jobs"]) == 9
    assert [job["sequence"] for job in first["jobs"]] == list(range(1, 10))
    assert all(job["status"] == "planned" for job in first["jobs"])
    assert all(job["kind"] == "hook_cover" for job in first["jobs"])
    hook_ids = {hook["id"] for hook in first["hooks"]}
    cover_ids = {cover["id"] for cover in first["covers"]}
    assert all(cell["hook"] in hook_ids and cell["cover"] in cover_ids for cell in first["cells"])
    assert all(job["hook"] in hook_ids and job["cover"] in cover_ids for job in first["jobs"])
    assert first["sequential"] is True
    assert first["job_count"] == 9
    assert first["plan"]["story_id"] == story["id"]
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert "No renders" in first["note"]


# ---------------------------------------------------------------- API


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
    # Hook matrix is post-v1; these tests exercise it behind the dev flag.
    monkeypatch.setenv("VIBECUT_EXPERIMENTAL", "1")
    client = TestClient(app.app)
    client.jobs_dir = jobs  # type: ignore[attr-defined]
    return client


def write_job(jobs: Path, job_id: str, **overrides) -> Path:
    scenes = overrides.pop("scenes", make_scenes(150))
    duration = overrides.pop("duration", 600.0)
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
            "duration": duration,
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
    job.update(overrides)
    directory = jobs / job_id
    directory.mkdir(parents=True)
    (directory / "job.json").write_text(json.dumps(job))
    return directory


def write_transcript(directory: Path, segments: list[dict]) -> Path:
    path = directory / "transcript" / "transcript.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"language": "en", "segments": segments}))
    return path


def test_clipset_api_create_get_patch_plans(api):
    write_job(api.jobs_dir, "j1")
    created = api.post("/api/jobs/j1/clip-sets", json={"count": 3})
    assert created.status_code == 200
    record = created.json()["clip_set"]
    set_id = record["id"]
    assert record["job_id"] == "j1"
    assert record["available"] == 3
    assert len(record["stories"]) == 3
    story_ids = [story["id"] for story in record["stories"]]
    assert len(story_ids) == len(set(story_ids)) == 3
    assert record["source_fingerprint"]
    assert "_keywords" not in json.dumps(record)
    assert "_base_total" not in json.dumps(record)

    listed = api.get("/api/jobs/j1/clip-sets")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["clip_sets"][0]["id"] == set_id

    story = record["stories"][0]
    ids = [sentence["id"] for sentence in story["sentences"]]
    excluded = record["stories"][2]["sentences"][0]["id"]
    lock_scene = story["scenes"][-1]
    ban_scene = record["stories"][1]["scenes"][0]
    patched = api.patch(
        f"/api/jobs/j1/clip-sets/{set_id}",
        json={
            "stories": [{"id": story["id"], "sentences": list(reversed(ids))}],
            "excluded_sentences": [excluded],
            "locks": [lock_scene, ban_scene],
            "ban_scenes": [ban_scene],
        },
    )
    assert patched.status_code == 200
    updated = patched.json()["clip_set"]
    assert updated["excluded_sentences"] == [excluded]
    assert updated["locks"] == [lock_scene]
    assert updated["ban_scenes"] == [ban_scene]
    assert ban_scene not in updated["locks"]
    rewritten = next(item for item in updated["stories"] if item["id"] == story["id"])
    assert [sentence["id"] for sentence in rewritten["sentences"]] == list(reversed(ids))
    assert all(
        excluded not in [sentence["id"] for sentence in item["sentences"]]
        for item in updated["stories"]
    )

    persisted = api.get("/api/jobs/j1/clip-sets").json()["clip_sets"][0]
    assert persisted["locks"] == [lock_scene]
    assert persisted["ban_scenes"] == [ban_scene]
    assert persisted["excluded_sentences"] == [excluded]

    plans = api.post(f"/api/jobs/j1/clip-sets/{set_id}/plans", json={})
    assert plans.status_code == 200
    body = plans.json()
    assert body["count"] == len(updated["stories"])
    assert body["plans"][0]["plan"]["clip_count"] >= 1
    assert body["plans"][0]["plan"]["clips"][0]["role"] == "hook"


def test_clipset_api_validation_and_short_source(api):
    write_job(api.jobs_dir, "j1")
    assert api.post("/api/jobs/j1/clip-sets", json={"count": 2}).status_code == 400
    assert api.post(
        "/api/jobs/j1/clip-sets",
        json={"count": 3, "min_s": 10, "max_s": 75},
    ).status_code == 400

    write_job(
        api.jobs_dir,
        "short",
        scenes=make_scenes(4),
        duration=16.0,
    )
    response = api.post("/api/jobs/short/clip-sets", json={"count": 3})
    assert response.status_code == 200
    record = response.json()["clip_set"]
    assert record["stories"] == []
    assert record["available"] == 0
    assert "at least 20s" in record["note"]

    matrix_response = api.post("/api/jobs/short/hook-matrix", json={})
    assert matrix_response.status_code == 200
    matrix_body = matrix_response.json()
    assert matrix_body["complete"] is False
    assert matrix_body["count"] == 0
    assert matrix_body["job_count"] == 0
    assert matrix_body["errors"]
    assert "No stories" in matrix_body["errors"][0]["error"]


def test_clipset_api_bans_alias_and_plans_readiness(api):
    write_job(api.jobs_dir, "j1")
    record = api.post(
        "/api/jobs/j1/clip-sets", json={"count": 3},
    ).json()["clip_set"]
    set_id = record["id"]
    banned = record["stories"][1]["scenes"][0]
    patched = api.patch(f"/api/jobs/j1/clip-sets/{set_id}", json={"bans": [banned]})
    assert patched.status_code == 200
    updated = patched.json()["clip_set"]
    assert updated["ban_scenes"] == [banned]
    assert all(banned not in story["scenes"] for story in updated["stories"])

    job_path = api.jobs_dir / "j1" / "job.json"
    job = json.loads(job_path.read_text())
    job["status"] = "scanning"
    job_path.write_text(json.dumps(job))
    assert api.post(f"/api/jobs/j1/clip-sets/{set_id}/plans", json={}).status_code == 409


def test_clipset_api_rejects_overlapping_edits(api):
    write_job(api.jobs_dir, "j1")
    record = api.post(
        "/api/jobs/j1/clip-sets", json={"count": 3},
    ).json()["clip_set"]
    set_id = record["id"]
    first, second = record["stories"][:2]
    ids = [sentence["id"] for sentence in first["sentences"]]
    ids.append(second["sentences"][0]["id"])
    response = api.patch(
        f"/api/jobs/j1/clip-sets/{set_id}",
        json={"stories": [{"id": first["id"], "sentences": ids}]},
    )
    assert response.status_code == 400
    assert "overlap" in response.json()["detail"]


def test_clipset_api_rejects_stale_transcript_edits(api):
    scenes = make_scenes(150)
    directory = write_job(api.jobs_dir, "j1", scenes=scenes)
    transcript = write_transcript(directory, [
        {
            "start": scene["start"],
            "end": scene["end"],
            "text": f"Different transcript line {index} about the source.",
        }
        for index, scene in enumerate(scenes)
    ])
    record = api.post(
        "/api/jobs/j1/clip-sets", json={"count": 3},
    ).json()["clip_set"]
    transcript.unlink()
    for path, payload in (
        (f"/api/jobs/j1/clip-sets/{record['id']}/plans", {}),
        ("/api/jobs/j1/selection-v2", {"set_id": record["id"]}),
        ("/api/jobs/j1/hook-matrix", {"set_id": record["id"]}),
        (f"/api/jobs/j1/clip-sets/{record['id']}", {"locks": record["locks"]}),
    ):
        method = api.patch if path.split("/")[-2] == "clip-sets" else api.post
        response = method(path, json=payload)
        assert response.status_code == 409, path
        assert "source changed" in response.json()["detail"]


def test_legacy_clip_set_without_fingerprint_warns_and_edits_are_rejected(api):
    write_job(api.jobs_dir, "j1")
    record = api.post(
        "/api/jobs/j1/clip-sets", json={"count": 3},
    ).json()["clip_set"]
    set_id = record["id"]
    job_path = api.jobs_dir / "j1" / "job.json"
    job = json.loads(job_path.read_text())
    legacy = job["clip_sets"][set_id]
    legacy.pop("source_fingerprint", None)
    job_path.write_text(json.dumps(job))

    plans = api.post(f"/api/jobs/j1/clip-sets/{set_id}/plans", json={})
    assert plans.status_code == 200
    assert plans.json()["stale_check"] == "unverified"
    assert plans.json()["warnings"]
    assert 20 <= plans.json()["plans"][0]["plan"]["target"] <= 75

    ranked = api.post(
        "/api/jobs/j1/selection-v2", json={"set_id": set_id},
    )
    assert ranked.status_code == 200
    assert ranked.json()["stale_check"] == "unverified"
    assert ranked.json()["warnings"]

    hook_matrix = api.post(
        "/api/jobs/j1/hook-matrix", json={"set_id": set_id},
    )
    assert hook_matrix.status_code == 200
    assert hook_matrix.json()["stale_check"] == "unverified"
    assert hook_matrix.json()["warnings"]

    patched = api.patch(f"/api/jobs/j1/clip-sets/{set_id}", json={"locks": []})
    assert patched.status_code == 409
    assert "no source fingerprint" in patched.json()["detail"]


def test_new_pydantic_models_do_not_share_list_defaults():
    first = app.ClipSetCreateBody()
    second = app.ClipSetCreateBody()
    first.locks.append(1)
    first.ban_scenes.append(2)
    assert second.locks == []
    assert second.ban_scenes == []
    assert app.SelectionV2Body().exclusions == []
    assert app.HookMatrixBody().exclusions == []


def test_clip_set_plan_maps_to_artifact_render_request_for_v013_job(api, monkeypatch):
    directory = write_job(api.jobs_dir, "j1")
    legacy = json.loads((directory / "job.json").read_text())
    assert "artifact_ids" not in legacy
    assert "source_fingerprint" not in legacy["source"]

    submitted = []
    monkeypatch.setattr(
        app.render_pool,
        "submit",
        lambda *args, **kwargs: submitted.append((args, kwargs)),
    )
    created = api.post(
        "/api/jobs/j1/clip-sets", json={"count": 3},
    ).json()["clip_set"]
    payload = api.post(
        f"/api/jobs/j1/clip-sets/{created['id']}/plans", json={},
    ).json()
    plan = payload["plans"][0]["plan"]
    assert 20 <= plan["target"] <= 75
    assert plan["story_id"]
    assert plan["clips"]

    record = app._queue_render(
        "j1", app.load_job("j1"), plan, "final", "9:16", None, False, None, False,
    )
    assert submitted, "artifact-backed render request was not queued"
    artifact_id = record["artifact_id"]
    assert artifacts.is_safe_artifact_id(artifact_id)
    manifest = artifacts.load_manifest(app._job_dir("j1"), artifact_id)
    assert manifest is not None
    spec = manifest["spec"]
    stored_job = app.load_job("j1")
    prepared = render.prepare_render(
        plan, stored_job.get("source") or {}, None,
    )
    assert spec["clips"] == artifacts.normalize_clips(prepared["clips"])
    assert spec["target"] == plan["target"]
    assert spec["hook_scene"] == plan["hook_scene"]
    assert spec["story_id"] == plan["story_id"]
    assert spec["source_fingerprint"]

    stored = app.load_job("j1")
    assert stored["artifact_ids"] == [artifact_id]
    assert stored["renders"][record["record_key"]]["artifact_id"] == artifact_id
    assert stored["renders"][record["record_key"]]["status"] == "queued"


def test_story_render_queues_artifact_and_returns_plan(api, monkeypatch):
    write_job(api.jobs_dir, "j1")
    record = api.post(
        "/api/jobs/j1/clip-sets", json={"count": 3},
    ).json()["clip_set"]
    story = record["stories"][0]
    submitted = []
    monkeypatch.setattr(
        app.render_pool,
        "submit",
        lambda *args, **kwargs: submitted.append((args, kwargs)),
    )

    response = api.post(
        f"/api/jobs/j1/clip-sets/{record['id']}/stories/{story['id']}/render",
        json={"quality": "final", "aspect": "9:16", "captions": False},
    )
    assert response.status_code == 200
    body = response.json()
    stored = int(round(story["dur"]))
    assert body["plan"]["story_id"] == story["id"]
    assert body["plan"]["target"] == stored
    assert body["plan"]["clips"][0]["role"] == "hook"
    assert "_scenes" not in body["plan"]
    assert artifacts.is_safe_artifact_id(body["artifact_id"])
    assert body["render"]["artifact_id"] == body["artifact_id"]
    assert body["render"]["status"] == "queued"
    assert submitted

    manifest = artifacts.load_manifest(app._job_dir("j1"), body["artifact_id"])
    assert manifest is not None
    assert manifest["status"] == "queued"
    assert manifest["spec"]["story_id"] == story["id"]
    assert manifest["spec"]["target"] == stored
    assert manifest["record_key"] == body["render"]["record_key"]
    assert body["render"]["record_key"].endswith(f":s{story['id']}")

    stored = app.load_job("j1")
    assert stored["artifact_ids"] == [body["artifact_id"]]
    assert stored["renders"][body["render"]["record_key"]]["artifact_id"] == (
        body["artifact_id"]
    )


def test_story_render_accepts_draft_aspect_and_captions(api, monkeypatch):
    write_job(api.jobs_dir, "j1")
    record = api.post(
        "/api/jobs/j1/clip-sets", json={"count": 3},
    ).json()["clip_set"]
    story = record["stories"][1]
    monkeypatch.setattr(app.render_pool, "submit", lambda *args, **kwargs: None)

    response = api.post(
        f"/api/jobs/j1/clip-sets/{record['id']}/stories/{story['id']}/render",
        json={"quality": "draft", "aspect": "4:5", "captions": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["plan"]["target"] == int(round(story["dur"]))
    manifest = artifacts.load_manifest(app._job_dir("j1"), body["artifact_id"])
    assert manifest is not None
    assert manifest["spec"]["quality"] == "draft"
    assert manifest["spec"]["aspect"] == "4:5"
    assert manifest["spec"]["caption"]["enabled"] is True
    assert manifest["spec"]["story_id"] == story["id"]


def test_story_render_validation_and_duplicate_active(api, monkeypatch):
    write_job(api.jobs_dir, "j1")
    record = api.post(
        "/api/jobs/j1/clip-sets", json={"count": 3},
    ).json()["clip_set"]
    set_id = record["id"]
    story_id = record["stories"][0]["id"]
    url = f"/api/jobs/j1/clip-sets/{set_id}/stories/{story_id}/render"
    monkeypatch.setattr(app.render_pool, "submit", lambda *args, **kwargs: None)

    assert api.post(
        f"/api/jobs/j1/clip-sets/missing/stories/{story_id}/render", json={},
    ).status_code == 404
    assert api.post(
        f"/api/jobs/j1/clip-sets/{set_id}/stories/missing/render", json={},
    ).status_code == 404
    stored = int(round(record["stories"][0]["dur"]))
    # Stored story duration is authoritative: no 1–180 override.
    assert api.post(url, json={"target": stored + 7}).status_code == 400
    assert api.post(url, json={"target": 0}).status_code == 400
    assert api.post(url, json={"quality": "cinema"}).status_code == 400
    assert api.post(url, json={"aspect": "21:9"}).status_code == 400
    assert api.post(url, json={"aspect": "1:1"}).status_code == 400
    assert api.post(url, json={"aspect": "16:9"}).status_code == 400

    first = api.post(url, json={"target": stored})
    assert first.status_code == 200
    duplicate = api.post(url, json={})
    assert duplicate.status_code == 409
    assert "already rendering" in duplicate.json()["detail"]

    job_path = api.jobs_dir / "j1" / "job.json"
    job = json.loads(job_path.read_text())
    job["status"] = "scanning"
    job_path.write_text(json.dumps(job))
    assert api.post(url, json={}).status_code == 409


def test_story_render_rejects_missing_clips(api):
    write_job(api.jobs_dir, "j1")
    record = api.post(
        "/api/jobs/j1/clip-sets", json={"count": 3},
    ).json()["clip_set"]
    set_id = record["id"]
    story_id = record["stories"][0]["id"]
    job_path = api.jobs_dir / "j1" / "job.json"
    job = json.loads(job_path.read_text())
    job["clip_sets"][set_id]["stories"][0]["clips"] = []
    job_path.write_text(json.dumps(job))

    response = api.post(
        f"/api/jobs/j1/clip-sets/{set_id}/stories/{story_id}/render",
        json={},
    )
    assert response.status_code == 422


def test_hook_matrix_api_returns_partial_errors_not_422(api):
    write_job(api.jobs_dir, "j1", scenes=make_scenes(150, rich=True))
    created = api.post(
        "/api/jobs/j1/clip-sets", json={"count": 3},
    ).json()["clip_set"]
    job_path = api.jobs_dir / "j1" / "job.json"
    job = json.loads(job_path.read_text())
    job["clip_sets"][created["id"]]["stories"][0]["clips"] = []
    job_path.write_text(json.dumps(job))

    response = api.post(
        "/api/jobs/j1/hook-matrix", json={"set_id": created["id"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["complete"] is False
    assert body["count"] == 2
    assert body["error_count"] == 1
    assert body["job_count"] == 18
    assert body["errors"][0]["story_id"] == created["stories"][0]["id"]


def test_generated_paths_for_selection_v2_and_hook_matrix(api):
    write_job(api.jobs_dir, "j1", scenes=make_scenes(150, rich=True))
    ranked = api.post("/api/jobs/j1/selection-v2", json={})
    assert ranked.status_code == 200
    assert ranked.json()["source"] == "generated"
    assert 3 <= ranked.json()["count"] <= 6
    assert all(len(story["hook_candidates"]) == 3 for story in ranked.json()["ranked"])

    payload = api.post("/api/jobs/j1/hook-matrix", json={})
    assert payload.status_code == 200
    body = payload.json()
    assert body["source"] == "generated"
    assert 3 <= body["count"] <= 6
    assert body["job_count"] == body["count"] * 9
    assert body["queued"] == 0


def test_selection_v2_api_is_explicit_and_keeps_v1_default(api):
    write_job(api.jobs_dir, "j1", scenes=make_scenes(150, rich=True))
    created = api.post("/api/jobs/j1/clip-sets", json={"count": 3}).json()["clip_set"]
    set_id = created["id"]
    before = (api.jobs_dir / "j1" / "job.json").read_text()
    before_plan = api.post("/api/jobs/j1/plan", json={"target": 30}).json()["plan"]

    response = api.post(
        "/api/jobs/j1/selection-v2",
        json={"set_id": set_id, "prompt": "no elephant", "count": 3},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["version"] == 2
    assert result["explicit"] is True
    assert result["default_plan_unchanged"] is True
    assert result["set_id"] == set_id
    assert result["source"] == "clip_set"
    assert len(result["ranked"]) == 3
    assert all(len(story["hook_candidates"]) == 3 for story in result["ranked"])
    assert all(story["v2_evidence"] for story in result["ranked"])

    after_plan = api.post("/api/jobs/j1/plan", json={"target": 30}).json()["plan"]
    after = json.loads((api.jobs_dir / "j1" / "job.json").read_text())
    assert after_plan == before_plan
    assert after["analysis"]["plans"] == json.loads(before)["analysis"]["plans"]


def test_selection_v2_api_prompt_exclusion(api):
    scenes = make_scenes(150)
    for scene in scenes:
        scene["speech"] = "Politics is the topic. " + scene["speech"]
    write_job(api.jobs_dir, "j1", scenes=scenes)
    created = api.post("/api/jobs/j1/clip-sets", json={"count": 3}).json()["clip_set"]
    result = api.post(
        "/api/jobs/j1/selection-v2",
        json={"set_id": created["id"], "prompt": "no politics"},
    ).json()
    assert result["exclusions"] == ["politics"]
    assert result["ranked"] == []
    assert result["count"] == 0
    assert result["excluded"]


def test_hook_matrix_api_shape_and_determinism(api):
    write_job(api.jobs_dir, "j1", scenes=make_scenes(150, rich=True))
    created = api.post("/api/jobs/j1/clip-sets", json={"count": 3}).json()["clip_set"]
    set_id = created["id"]
    first = api.post("/api/jobs/j1/hook-matrix", json={"set_id": set_id})
    second = api.post("/api/jobs/j1/hook-matrix", json={"set_id": set_id})
    assert first.status_code == 200
    body = first.json()
    assert body["count"] == 3
    assert body["complete"] is True
    assert body["errors"] == []
    assert body["queued"] == 0
    assert body["job_count"] == 27
    assert body["matrices"] == second.json()["matrices"]
    for payload in body["matrices"]:
        assert len(payload["hooks"]) == 3
        assert len(payload["covers"]) == 3
        assert len(payload["cells"]) == 9
        assert len(payload["jobs"]) == 9
        assert [job["sequence"] for job in payload["jobs"]] == list(range(1, 10))
        assert payload["sequential"] is True
        assert payload["plan"]["clips"]
        assert "No renders" in payload["note"]


def test_story_caption_lineage_survives_edit_into_render(api, monkeypatch):
    """G2: the edited story track is the one the story render burns."""
    write_job(api.jobs_dir, "j1")
    record = api.post("/api/jobs/j1/clip-sets", json={"count": 3}).json()["clip_set"]
    set_id = record["id"]
    story = record["stories"][0]
    monkeypatch.setattr(app.render_pool, "submit", lambda *args, **kwargs: None)

    built = api.post(
        "/api/jobs/j1/captions", json={"set_id": set_id, "story_id": story["id"]},
    )
    assert built.status_code == 200, built.text
    track = built.json()["track"]
    assert built.json()["duration"] > 0
    cues = [dict(cue) for cue in track["cues"]]
    assert cues
    cues[0]["text"] = "Edited first cue"
    edited = api.patch(f"/api/jobs/j1/captions/{track['id']}", json={"cues": cues})
    assert edited.status_code == 200, edited.text
    edited_id = edited.json()["id"]
    assert edited_id != track["id"]
    assert app.load_job("j1")["story_captions"][f"{set_id}:{story['id']}"] == edited_id

    rendered = api.post(
        f"/api/jobs/j1/clip-sets/{set_id}/stories/{story['id']}/render", json={},
    )
    assert rendered.status_code == 200, rendered.text
    assert rendered.json()["caption_track_id"] == edited_id
    manifest = artifacts.load_manifest(app._job_dir("j1"), rendered.json()["artifact_id"])
    burned = manifest["spec"]["caption"]
    assert burned["enabled"] is True
    edited_cues = edited.json()["track"]["cues"]
    assert edited_cues[0]["text"] == "Edited first cue"
    assert burned["cue_hash"] == artifacts.cue_hashes(edited_cues)[0]
    assert burned["cue_count"] == len(edited_cues)


def test_story_render_4x5_is_a_separate_artifact(api, monkeypatch):
    write_job(api.jobs_dir, "j1")
    record = api.post("/api/jobs/j1/clip-sets", json={"count": 3}).json()["clip_set"]
    story = record["stories"][0]
    monkeypatch.setattr(app.render_pool, "submit", lambda *args, **kwargs: None)
    url = f"/api/jobs/j1/clip-sets/{record['id']}/stories/{story['id']}/render"
    vertical = api.post(url, json={"aspect": "9:16"}).json()
    portrait = api.post(url, json={"aspect": "4:5"}).json()
    assert vertical["artifact_id"] != portrait["artifact_id"]
    job_dir = app._job_dir("j1")
    assert artifacts.load_manifest(job_dir, vertical["artifact_id"])["spec"]["aspect"] == "9:16"
    assert artifacts.load_manifest(job_dir, portrait["artifact_id"])["spec"]["aspect"] == "4:5"


def test_story_retry_keeps_37s_4x5_edited_track_identity(api, monkeypatch):
    """A failed story render retries the same 37s 4:5 object and edited track."""
    write_job(api.jobs_dir, "j1")
    record = api.post("/api/jobs/j1/clip-sets", json={"count": 3}).json()["clip_set"]
    set_id = record["id"]
    story = record["stories"][0]

    job_path = api.jobs_dir / "j1" / "job.json"
    job = json.loads(job_path.read_text())
    stored_story = next(
        item for item in job["clip_sets"][set_id]["stories"]
        if item["id"] == story["id"]
    )
    stored_story["dur"] = 37.0
    job_path.write_text(json.dumps(job))

    monkeypatch.setattr(app.render_pool, "submit", lambda *args, **kwargs: None)
    built = api.post(
        "/api/jobs/j1/captions",
        json={"set_id": set_id, "story_id": story["id"]},
    )
    assert built.status_code == 200, built.text
    track = built.json()["track"]
    cues = [dict(cue) for cue in track["cues"]]
    cues[0]["text"] = "Edited retry cue"
    edited = api.patch(
        f"/api/jobs/j1/captions/{track['id']}", json={"cues": cues},
    )
    assert edited.status_code == 200, edited.text
    edited_track = edited.json()["track"]
    edited_id = edited.json()["id"]

    rendered = api.post(
        f"/api/jobs/j1/clip-sets/{set_id}/stories/{story['id']}/render",
        json={"aspect": "4:5", "quality": "draft"},
    )
    assert rendered.status_code == 200, rendered.text
    artifact_id = rendered.json()["artifact_id"]

    job = app.load_job("j1")
    record_key, queued = next(
        (key, value) for key, value in job["renders"].items()
        if value.get("artifact_id") == artifact_id
    )
    assert queued["target"] == 37
    assert queued["aspect"] == "4:5"
    assert queued["caption_track_id"] == edited_id
    assert queued["plan_snapshot"]["story_id"] == story["id"]
    assert queued["plan_snapshot"]["set_id"] == set_id
    snapshot_clips = [dict(clip) for clip in queued["plan_snapshot"]["clips"]]
    track_dir = app._job_dir("j1") / "caption_tracks"
    tracks_before = len(list(track_dir.glob("*.json")))

    def fail(value: dict) -> None:
        value["renders"][record_key]["status"] = "failed"
        value["renders"][record_key]["error"] = "encoder failed"
        value["renders"][record_key]["attempts"] = 1

    app.update_job("j1", fail)
    artifacts.mark_status(
        app._job_dir("j1"), artifact_id, "interrupted", error="encoder failed",
    )

    response = api.post("/api/jobs/j1/retry")
    assert response.status_code == 200, response.text
    retried = response.json()
    assert retried["retry"]["renders"] == 1

    latest = app.load_job("j1")
    assert record_key in latest["renders"]
    retry = latest["renders"][record_key]
    assert retry["status"] == "queued"
    assert retry["target"] == 37
    assert retry["quality"] == "draft"
    assert retry["aspect"] == "4:5"
    assert retry["captions"] is True
    assert retry["story_id"] == story["id"]
    assert retry["set_id"] == set_id
    assert retry["plan_snapshot"]["story_id"] == story["id"]
    assert retry["plan_snapshot"]["set_id"] == set_id
    assert retry["plan_snapshot"]["clips"] == snapshot_clips
    assert retry["caption_track_id"] == edited_id
    assert retry["caption_style_id"] == edited_track["style_id"]
    assert retry["style_hash"] == edited_track["style_hash"]
    assert retry["cue_hash"] == edited_track["cue_hash"]
    assert retry["artifact_id"] == artifact_id
    assert retry["attempts"] == 2
    assert len(list(track_dir.glob("*.json"))) == tracks_before

    manifest = artifacts.load_manifest(app._job_dir("j1"), artifact_id)
    assert manifest["status"] == "queued"
    assert manifest["spec"]["caption"]["cue_hash"] == (
        artifacts.cue_hashes(edited_track["cues"])[0]
    )
    assert manifest["spec"]["caption"]["style_hash"] == artifacts.style_hash(
        None, 0.075, edited_track["style_hash"],
    )
    assert manifest["spec"]["target"] == 37
    assert manifest["spec"]["aspect"] == "4:5"
    assert manifest["caption_track_id"] == edited_id


def test_public_plan_and_render_cannot_forge_story_identity(api, monkeypatch):
    """Public PlanBody ignores story ids and cannot collide with a story key."""
    write_job(api.jobs_dir, "j1")
    record = api.post("/api/jobs/j1/clip-sets", json={"count": 3}).json()["clip_set"]
    set_id = record["id"]
    story = record["stories"][0]

    job_path = api.jobs_dir / "j1" / "job.json"
    job = json.loads(job_path.read_text())
    stored_story = next(
        item for item in job["clip_sets"][set_id]["stories"]
        if item["id"] == story["id"]
    )
    stored_story["dur"] = 30.0
    job_path.write_text(json.dumps(job))
    monkeypatch.setattr(app.render_pool, "submit", lambda *args, **kwargs: None)

    plan_body = {
        "target": 30,
        "clips": story["clips"],
        "story_id": story["id"],
        "set_id": set_id,
    }
    planned = api.post("/api/jobs/j1/plan", json=plan_body)
    assert planned.status_code == 200, planned.text
    assert "story_id" not in planned.json()["plan"]
    assert "clip_set_id" not in planned.json()["plan"]

    story_render = api.post(
        f"/api/jobs/j1/clip-sets/{set_id}/stories/{story['id']}/render",
        json={"aspect": "9:16", "captions": True},
    )
    assert story_render.status_code == 200, story_render.text
    story_artifact = story_render.json()["artifact_id"]
    _job = app.load_job("j1")
    story_key = next(
        key for key, value in _job["renders"].items()
        if value.get("artifact_id") == story_artifact
    )
    assert story_key.endswith(f":s{story['id']}")

    public = api.post(
        "/api/jobs/j1/render",
        json={**plan_body, "aspect": "9:16", "captions": True},
    )
    assert public.status_code == 200, public.text
    public_record = public.json()["render"]
    assert public_record["record_key"] != story_key
    assert not public_record["record_key"].endswith(f":s{story['id']}")
    assert not public_record.get("story_id")
    assert public_record["artifact_id"] != story_artifact

    latest = app.load_job("j1")
    assert story_key in latest["renders"]
    assert latest["renders"][story_key]["artifact_id"] == story_artifact
    assert latest["renders"][story_key]["story_id"] == story["id"]


def test_story_versions_are_monotonic_and_old_versions_are_labelled(api, monkeypatch):
    """FR-10: v{n} per story/aspect; old artifacts stay, labelled superseded."""
    write_job(api.jobs_dir, "j1")
    record = api.post("/api/jobs/j1/clip-sets", json={"count": 3}).json()["clip_set"]
    story = record["stories"][0]
    monkeypatch.setattr(app.render_pool, "submit", lambda *args, **kwargs: None)
    url = f"/api/jobs/j1/clip-sets/{record['id']}/stories/{story['id']}/render"
    first = api.post(url, json={"captions": False}).json()["artifact_id"]
    second = api.post(url, json={"captions": True}).json()["artifact_id"]
    other_aspect = api.post(url, json={"aspect": "4:5", "captions": False}).json()["artifact_id"]
    job_dir = app._job_dir("j1")

    one = artifacts.load_manifest(job_dir, first)
    two = artifacts.load_manifest(job_dir, second)
    portrait = artifacts.load_manifest(job_dir, other_aspect)
    assert (one["version"], two["version"], portrait["version"]) == (1, 2, 1)
    assert two["supersedes"] == first
    assert portrait["supersedes"] is None

    for manifest in (one, two):
        manifest["status"] = "ready"
        artifacts.save_manifest(job_dir, manifest)
    listed = {row["artifact_id"]: row["versions"] for row in api.get("/api/jobs/j1/artifacts").json()["artifacts"]}
    assert listed[second]["label"] == "v2 · current"
    assert listed[first]["current"] is False
    assert listed[first]["label"].startswith("v1 · superseded by v2 on ")
    assert listed[first]["superseded_by"]["artifact_id"] == second


def test_story_queue_api_queues_story_items_and_resume_banner(api, monkeypatch):
    write_job(api.jobs_dir, "j1")
    record = api.post("/api/jobs/j1/clip-sets", json={"count": 3}).json()["clip_set"]
    submitted = []
    monkeypatch.setattr(app.render_pool, "submit", lambda *args, **kwargs: submitted.append(args))
    body = {"items": [
        {"job_id": "j1", "set_id": record["id"], "story_id": story["id"], "aspect": aspect}
        for story in record["stories"][:2] for aspect in ("9:16", "4:5")
    ]}
    created = api.post("/api/story-queues", json=body)
    assert created.status_code == 200, created.text
    queue_id = created.json()["queue"]["id"]
    manager = app.story_queues()
    deadline = time.time() + 5
    while time.time() < deadline and not manager.get(queue_id)["items"][0].get("artifact_id"):
        time.sleep(0.02)
    first = manager.get(queue_id)["items"][0]
    assert first["state"] == "running" and first["artifact_id"]
    assert len(submitted) == 1  # strictly sequential: item 2 waits

    cancelled = api.post(f"/api/story-queues/{queue_id}/cancel")
    assert cancelled.status_code == 200
    assert manager.wait(queue_id, 5)
    listed = api.get("/api/story-queues").json()
    assert listed["queues"][0]["status"] == "cancelled"
    assert listed["interrupted"] == []

    missing = api.post("/api/story-queues", json={"items": [
        {"job_id": "j1", "set_id": record["id"], "story_id": "nope"},
    ]})
    assert missing.status_code == 404


def test_hook_matrix_is_off_without_the_experimental_flag(api, monkeypatch):
    write_job(api.jobs_dir, "j1")
    monkeypatch.delenv("VIBECUT_EXPERIMENTAL", raising=False)
    assert api.post("/api/jobs/j1/hook-matrix", json={}).status_code == 404
