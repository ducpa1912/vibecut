"""The clip search window: the first two minutes by default, the whole video on request.

The decode and the search are faked; no media is made.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

import audio


@pytest.fixture
def worker(tmp_path, monkeypatch):
    import app
    import routes_voice_clone as routes
    import voice_extract

    jobs = tmp_path / "jobs"
    monkeypatch.setattr(app, "JOBS", jobs)
    calls = {"run": [], "find": []}

    def fake_run(cmd, timeout=None, cancel_event=None, **_kwargs):
        calls["run"].append(list(cmd))
        Path(cmd[-1]).write_bytes(b"RIFF")

    def fake_find(source, out_dir, **kwargs):
        calls["find"].append((Path(source), kwargs))
        return {"candidates": [{"index": 1, "window": [4.0, 14.0], "duration": 10.0}], "models": {}}

    monkeypatch.setattr(audio, "_run", fake_run)
    monkeypatch.setattr(voice_extract, "find_voice_candidates", fake_find)

    def run(duration, **kwargs):
        job_id = f"job-{len(calls['find'])}"
        directory = jobs / job_id
        directory.mkdir(parents=True)
        source = tmp_path / f"{job_id}.mp4"
        source.write_bytes(b"\x00" * 64)
        (directory / "job.json").write_text(json.dumps({
            "id": job_id, "status": "ready",
            "source": {"path": str(source), "name": "talk.mp4", "duration": duration},
        }))
        out = directory / "voice-candidates"
        out.mkdir()
        report = routes._run_candidate_search(job_id, threading.Event(), out, **kwargs)
        return report, calls

    return run


def _window(cmd):
    return float(cmd[cmd.index("-ss") + 1]), float(cmd[cmd.index("-t") + 1])


def test_default_window_cuts_two_minutes_and_shifts_clip_times(worker):
    report, calls = worker(1024.0, start=30.0, seconds=120.0)
    assert _window(calls["run"][-1]) == (30.0, 120.0)
    assert calls["find"][-1][0].name == "search-window.wav"
    assert report["window_offset"] == 30.0


def test_unknown_length_keeps_the_full_window_not_one_second(worker):
    _report, calls = worker(0.0, start=0.0, seconds=120.0)
    assert _window(calls["run"][-1]) == (0.0, 120.0)


def test_window_is_clamped_to_the_end_of_a_known_video(worker):
    _report, calls = worker(100.0, start=90.0, seconds=120.0)
    assert _window(calls["run"][-1]) == (90.0, 10.0)


def test_fast_search_skips_separation(worker):
    _report, calls = worker(60.0, fast=True)
    kwargs = calls["find"][-1][1]
    assert kwargs["separate"] is False and kwargs["denoise"] == "afftdn"
    assert calls["run"] == []  # no window: the whole short video is searched


def test_route_searches_a_video_of_unknown_length_whole(tmp_path, monkeypatch):
    import app
    import routes_voice_clone as routes
    from fastapi.testclient import TestClient

    jobs = tmp_path / "jobs"
    monkeypatch.setattr(app, "JOBS", jobs)
    (jobs / "job-x").mkdir(parents=True)
    source = tmp_path / "x.mp4"
    source.write_bytes(b"\x00" * 64)
    (jobs / "job-x" / "job.json").write_text(json.dumps({
        "id": "job-x", "status": "ready", "source": {"path": str(source), "name": "x.mp4"},
    }))
    seen = {}

    def fake_submit(fn, *args, **kwargs):
        seen.update(kwargs)

    monkeypatch.setattr(app.voice_pool, "submit_tracked", fake_submit)
    monkeypatch.setattr(app.voice_pool, "find_key", lambda *a: None)
    TestClient(app.app).post("/api/jobs/job-x/voices/candidates")
    assert seen["seconds"] == 0.0
    routes.forget_job("job-x")
