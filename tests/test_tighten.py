"""Tighten transform: new plan, no source mutation, hard cuts only."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app
import tighten


def _plan() -> dict:
    return {
        "target": 30,
        "total": 13.0,
        "hook_scene": 0,
        "clip_count": 3,
        "clips": [
            {"scene": 0, "start": 0.0, "end": 3.0, "dur": 3.0, "role": "hook"},
            {"scene": 1, "start": 0.0, "end": 7.0, "dur": 7.0, "role": "beat"},
            {"scene": 2, "start": 7.0, "end": 10.0, "dur": 3.0, "role": "payoff"},
        ],
    }


def _scenes() -> list[dict]:
    words = [
        {"text": "So", "start": 0.0, "end": 0.4},
        {"text": "um", "start": 0.4, "end": 1.0},
        {"text": "today", "start": 1.0, "end": 1.6},
        {"text": "we", "start": 1.6, "end": 2.0},
        {"text": "build", "start": 2.0, "end": 2.5},
        {"text": "this", "start": 5.5, "end": 6.0},
        {"text": "thing.", "start": 6.0, "end": 6.8},
    ]
    return [
        {"id": 0, "start": 0.0, "end": 3.0, "dur": 3.0, "speech": "Hook here."},
        {"id": 1, "start": 0.0, "end": 7.0, "dur": 7.0, "words": words,
         "crop": {"cx": 0.4, "cy": 0.6}},
        {"id": 2, "start": 7.0, "end": 10.0, "dur": 3.0, "speech": "Payoff."},
    ]


def test_tighten_removes_filler_and_silence_without_mutating_source():
    plan = _plan()
    scenes = _scenes()
    before = copy.deepcopy(plan)
    before_scenes = copy.deepcopy(scenes)

    result = tighten.tighten_plan(
        plan, scenes, options={"min_silence": 0.6, "punch_ins": True},
    )

    assert result is not plan
    assert plan == before
    assert scenes == before_scenes
    assert result["tightened"] is True
    assert result["total"] < plan["total"]
    assert result["tighten"]["removed_seconds"] > 0
    assert result["tighten"]["filler_removed_seconds"] > 0
    assert result["tighten"]["silence_removed_seconds"] > 0
    assert result["clips"][0]["scene"] == 0
    assert result["clips"][0]["role"] == "hook"
    assert result["clips"][-1]["scene"] == 2
    assert result["clips"][-1]["role"] == "payoff"
    assert not any(
        clip["start"] < 0.4 and clip["end"] > 1.0
        for clip in result["clips"] if clip["scene"] == 1
    )
    assert not any(
        clip["start"] < 2.6 and clip["end"] > 5.4
        for clip in result["clips"] if clip["scene"] == 1
    )


def test_tighten_keeps_every_piece_inside_original_boundaries_and_hard_cuts():
    plan = _plan()
    result = tighten.tighten_plan(plan, _scenes())

    boundaries = {clip["scene"]: (clip["start"], clip["end"]) for clip in plan["clips"]}
    for clip in result["clips"]:
        start, end = boundaries[clip["scene"]]
        assert clip["start"] >= start - 0.001
        assert clip["end"] <= end + 0.001
        assert clip["end"] > clip["start"]
        assert "transition" not in clip
        assert "j_cut" not in clip
    assert result["tighten"]["cuts"] == "hard"
    assert result["tighten"]["j_l_cuts"] is False
    assert result["tighten"]["sfx"] is False
    assert result["tighten"]["broll"] is False
    assert result["tighten"]["preserved_roles"] == ["hook", "payoff"]


def test_tighten_keeps_meaningful_like():
    plan = {
        "target": 15,
        "total": 2.0,
        "hook_scene": 0,
        "clips": [{"scene": 0, "start": 0.0, "end": 2.0, "dur": 2.0, "role": "hook"}],
    }
    words = [
        {"text": "I", "start": 0.1, "end": 0.3},
        {"text": "like", "start": 0.3, "end": 0.6},
        {"text": "this", "start": 0.6, "end": 0.9},
        {"text": "product.", "start": 0.9, "end": 1.5},
    ]
    scenes = [{"id": 0, "start": 0.0, "end": 2.0, "dur": 2.0, "words": words}]

    result = tighten.tighten_plan(plan, scenes)

    assert result["tighten"]["filler_removed_seconds"] == 0.0
    assert result["tighten"]["removed_seconds"] == 0.0
    assert len(result["clips"]) == 1
    assert result["total"] == pytest.approx(2.0)


def test_tighten_removes_contextual_like_near_filler():
    plan = {
        "target": 15,
        "total": 2.0,
        "hook_scene": 0,
        "clips": [{"scene": 0, "start": 0.0, "end": 2.0, "dur": 2.0, "role": "hook"}],
    }
    words = [
        {"text": "um", "start": 0.1, "end": 0.3},
        {"text": "like", "start": 0.3, "end": 0.6},
        {"text": "this", "start": 0.6, "end": 0.9},
    ]
    scenes = [{"id": 0, "start": 0.0, "end": 2.0, "dur": 2.0, "words": words}]

    result = tighten.tighten_plan(plan, scenes)

    assert result["tighten"]["filler_removed_seconds"] > 0


def test_tighten_removal_accounting_is_disjoint():
    result = tighten.tighten_plan(
        _plan(), _scenes(), options={"min_silence": 0.6, "punch_ins": True},
    )
    report = result["tighten"]

    parts = (
        report["filler_removed_seconds"]
        + report["silence_removed_seconds"]
        + report["overlap_removed_seconds"]
        + report["other_removed_seconds"]
    )
    assert parts == pytest.approx(report["removed_seconds"], abs=0.01)


def test_tighten_adds_simple_punch_ins_to_beat_clips():
    plan = {
        "target": 30,
        "total": 8.0,
        "hook_scene": 0,
        "clips": [
            {"scene": 0, "start": 0.0, "end": 2.0, "dur": 2.0, "role": "hook"},
            {"scene": 1, "start": 2.0, "end": 8.0, "dur": 6.0, "role": "beat"},
        ],
    }
    scenes = [
        {"id": 0, "start": 0.0, "end": 2.0, "dur": 2.0, "speech": "Hook."},
        {"id": 1, "start": 2.0, "end": 8.0, "dur": 6.0, "speech": "A long beat.",
         "crop": {"cx": 0.35, "cy": 0.65}},
    ]

    result = tighten.tighten_plan(plan, scenes)

    beat = next(clip for clip in result["clips"] if clip["role"] == "beat")
    assert beat["punch"]["scale"] == pytest.approx(1.06)
    assert beat["punch"]["cx"] == pytest.approx(0.35)
    assert beat["punch"]["cy"] == pytest.approx(0.65)
    assert result["tighten"]["punch_ins"] == 1


def test_tighten_options_can_disable_filler_and_punch():
    plan = _plan()
    result = tighten.tighten_plan(
        plan, _scenes(),
        options={"filler": False, "silence": False, "punch_ins": False},
    )

    assert result["tighten"]["filler_removed_seconds"] == 0.0
    assert result["tighten"]["silence_removed_seconds"] == 0.0
    assert result["tighten"]["punch_ins"] == 0
    assert all("punch" not in clip for clip in result["clips"])
    assert result["total"] == pytest.approx(plan["total"])


def test_tighten_plan_with_no_changes_is_still_a_new_plan():
    plan = {
        "target": 15,
        "total": 2.0,
        "hook_scene": 0,
        "clips": [{"scene": 0, "start": 0.0, "end": 2.0, "dur": 2.0, "role": "hook"}],
    }
    scenes = [{"id": 0, "start": 0.0, "end": 2.0, "dur": 2.0, "speech": "Hello."}]
    result = tighten.tighten_plan(plan, scenes)

    assert result is not plan
    assert result["clips"] is not plan["clips"]
    assert result["clips"][0] is not plan["clips"][0]
    assert result["total"] == 2.0
    assert result["tightened"] is True


def test_detect_silences_parses_ffmpeg_stderr(monkeypatch, tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fake")

    class Result:
        returncode = 0
        stderr = (
            "[silencedetect @ 0x1] silence_start: 1.2\n"
            "[silencedetect @ 0x1] silence_end: 2.7 | silence_duration: 1.5\n"
            "[silencedetect @ 0x1] silence_start: 4.0\n"
            "[silencedetect @ 0x1] silence_end: 4.8 | silence_duration: 0.8\n"
        )

    monkeypatch.setattr(tighten.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(tighten.subprocess, "run", lambda *args, **kwargs: Result())

    assert tighten.detect_silences(source) == [
        {"start": 1.2, "end": 2.7},
        {"start": 4.0, "end": 4.8},
    ]


@pytest.fixture
def api(tmp_path, monkeypatch):
    jobs = tmp_path / "data" / "jobs"
    jobs.mkdir(parents=True)
    monkeypatch.setattr(app, "DATA", tmp_path / "data")
    monkeypatch.setattr(app, "JOBS", jobs)
    client = TestClient(app.app)
    client.jobs_dir = jobs  # type: ignore[attr-defined]
    return client


def test_tighten_api_returns_new_plan_and_leaves_job_unchanged(api):
    job = {
        "id": "job1",
        "status": "ready",
        "source": {"name": "source.mp4", "duration": 10.0},
        "analysis": {"scenes": _scenes(), "plans": {"30": _plan()}},
        "renders": {},
    }
    directory = api.jobs_dir / "job1"
    directory.mkdir()
    path = directory / "job.json"
    path.write_text(json.dumps(job), encoding="utf-8")
    before = path.read_bytes()

    response = api.post("/api/jobs/job1/tighten", json={
        "target": 30,
        "plan": _plan(),
        "options": {"min_silence": 0.6},
    })

    assert response.status_code == 200, response.text
    plan = response.json()["plan"]
    assert plan["tightened"] is True
    assert plan["total"] < 13.0
    assert path.read_bytes() == before
    assert not (directory / "renders").exists()


def test_tighten_api_rejects_malformed_plan_numbers(api):
    job = {
        "id": "job1",
        "status": "ready",
        "source": {"name": "source.mp4", "duration": 10.0},
        "analysis": {"scenes": _scenes(), "plans": {"30": _plan()}},
        "renders": {},
    }
    directory = api.jobs_dir / "job1"
    directory.mkdir()
    (directory / "job.json").write_text(json.dumps(job), encoding="utf-8")

    response = api.post("/api/jobs/job1/tighten", json={
        "plan": {
            "target": 30,
            "clips": [{"scene": 0, "start": "abc", "end": 2.0, "dur": "abc"}],
        },
    })

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "clip_invalid"


def test_tighten_option_boolean_coercion():
    options = tighten.normalize_options({
        "filler": 0,
        "silence": "off",
        "punch": 1,
    })
    assert options.remove_filler is False
    assert options.remove_silence is False
    assert options.punch_ins is True
