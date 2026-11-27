"""Review findings #4 and #5 (2026-11-13): the estimate queue and the refill retry."""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

import pytest

from duckcore import media, render


@pytest.fixture(autouse=True)
def _fresh_jobs():
    with render._ESTIMATE_LOCK:
        render._ESTIMATE_JOBS.clear()
        render._ESTIMATE_QUEUE.clear()
        render._ESTIMATE_LAST.clear()
    yield
    with render._ESTIMATE_LOCK:
        render._ESTIMATE_JOBS.clear()
        render._ESTIMATE_QUEUE.clear()
        render._ESTIMATE_LAST.clear()


META = {"width": 100, "height": 100, "fps": 30.0}


def _edit(edit_id: str = "ed_q", updated: float = 1.0) -> dict:
    return {
        "id": edit_id, "updated": updated,
        "clean": [{
            "id": "cl_one", "kind": "fill", "enabled": True,
            "box": {"x": 0.1, "y": 0.1, "w": 0.4, "h": 0.1},
            "ranges": [{"start": 0.0, "end": 1.0}],
        }],
    }


def _until(test, seconds: float = 5.0) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if test():
            return
        time.sleep(0.02)
    raise AssertionError("timed out")


def _slow(calls: list, pause: float):
    def estimate(edit, meta, data_root, progress=None):
        calls.append((edit["id"], edit["updated"]))
        time.sleep(pause)
        return {"total_seconds": float(edit["updated"])}
    return estimate


# ---- #4 estimate queue ----------------------------------------------------


def test_older_saves_of_an_edit_are_never_measured(tmp_path, monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(render, "estimate_edit", _slow(calls, 0.4))
    meta = {**META, "path": str(tmp_path / "s.mp4")}
    render.estimate_status(_edit(updated=1.0), meta, tmp_path, wait=0.0)
    _until(lambda: calls)  # version 1 is running
    render.estimate_status(_edit(updated=2.0), meta, tmp_path, wait=0.0)
    middle = render._estimate_key(_edit(updated=2.0), meta, tmp_path)
    render.estimate_status(_edit(updated=3.0), meta, tmp_path, wait=0.0)
    with render._ESTIMATE_LOCK:
        assert render._ESTIMATE_JOBS[middle]["state"] == "ready"
        assert render._ESTIMATE_JOBS[middle].get("superseded")
    got = render.wait_for_estimate(_edit(updated=3.0), meta, tmp_path, timeout=5.0)
    assert got["total_seconds"] == 3.0
    assert [updated for _id, updated in calls] == [1.0, 3.0]


def test_a_render_does_not_wait_behind_the_queue(tmp_path, monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(render, "estimate_edit", _slow(calls, 1.0))
    meta = {**META, "path": str(tmp_path / "s.mp4")}
    render.estimate_status(_edit("ed_other"), meta, tmp_path, wait=0.0)
    _until(lambda: calls)  # another edit holds the worker for a second
    render.estimate_status(_edit("ed_mine"), meta, tmp_path, wait=0.0)
    began = time.monotonic()
    got = render.estimate_for_render(_edit("ed_mine"), meta, tmp_path)
    assert time.monotonic() - began < 0.3
    assert got == {}
    with render._ESTIMATE_LOCK:
        assert all(item[1]["id"] != "ed_mine" for item in render._ESTIMATE_QUEUE)


def test_a_render_takes_the_last_figure_when_its_estimate_is_queued(tmp_path, monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(render, "estimate_edit", _slow(calls, 1.0))
    meta = {**META, "path": str(tmp_path / "s.mp4")}
    render._ESTIMATE_LAST["ed_mine"] = {"total_seconds": 42.0}
    render.estimate_status(_edit("ed_other"), meta, tmp_path, wait=0.0)
    _until(lambda: calls)
    render.estimate_status(_edit("ed_mine", updated=9.0), meta, tmp_path, wait=0.0)
    assert render.estimate_for_render(_edit("ed_mine", updated=9.0), meta, tmp_path) == {
        "total_seconds": 42.0,
    }


def test_a_render_joins_its_own_running_estimate(tmp_path, monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(render, "estimate_edit", _slow(calls, 0.4))
    meta = {**META, "path": str(tmp_path / "s.mp4")}
    render.estimate_status(_edit("ed_run", updated=5.0), meta, tmp_path, wait=0.0)
    _until(lambda: calls)
    got = render.estimate_for_render(_edit("ed_run", updated=5.0), meta, tmp_path, timeout=5.0)
    assert got["total_seconds"] == 5.0
    assert len(calls) == 1


def test_a_ready_job_trimmed_from_the_map_still_answers(tmp_path, monkeypatch) -> None:
    """Finding #8: the answer is read from the job held, not looked up again."""
    monkeypatch.setattr(render, "estimate_edit", _slow([], 0.05))
    meta = {**META, "path": str(tmp_path / "s.mp4")}
    real_sleep = time.sleep

    def trim_while_waiting(seconds):
        with render._ESTIMATE_LOCK:
            render._ESTIMATE_JOBS.clear()
        real_sleep(seconds)

    monkeypatch.setattr(render.time, "sleep", trim_while_waiting)
    answer = render.estimate_status(_edit("ed_trim"), meta, tmp_path, wait=0.5)
    assert answer["state"] in {"working", "ready"}


# ---- #5 refill retry -------------------------------------------------------


def test_retry_clips_are_the_clips_a_hit_falls_in() -> None:
    clips = [
        {"start": 0.0, "end": 1.0},
        {"start": 2.0, "end": 3.0},
        {"start": 4.0, "end": 5.0},
        {"kind": "media", "start": 0.0, "end": 9.0},
    ]
    assert render._retry_clips(clips, [{"source_time": 2.5}], 30.0) == {1}
    # The widened span reaches 3 frames past the hit: across a clip edge.
    assert render._retry_clips(clips, [{"source_time": 1.98}], 30.0) == {1}
    assert render._retry_clips(clips, [{"source_time": 9.5}], 30.0) == set()


def _ffmpeg() -> str:
    try:
        return media.ffmpeg()
    except Exception:  # noqa: BLE001 - no ffmpeg on this machine
        pytest.skip("ffmpeg is not available")


def test_a_refill_draws_only_the_clip_that_kept_text(tmp_path, monkeypatch) -> None:
    ffmpeg = _ffmpeg()
    source = tmp_path / "source.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-v", "error",
         "-f", "lavfi", "-i", "testsrc=s=160x90:d=6:r=30",
         "-f", "lavfi", "-i", "sine=frequency=220:duration=6",
         "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source)],
        check=True,
    )
    edit = {
        "id": "ed_retry", "project_id": "prj_retry",
        "clips": [
            {"start": 0.0, "end": 1.0}, {"start": 2.0, "end": 3.0}, {"start": 4.0, "end": 5.0},
        ],
        "clean": [{
            "id": "cl_blur", "kind": "blur", "enabled": True,
            "box": {"x": 0.1, "y": 0.1, "w": 0.4, "h": 0.2},
            "ranges": [{"start": 2.2, "end": 2.4}],
        }],
    }
    checks: list[dict] = []

    def fake_check(output, edit, meta, **_kwargs):
        first = not checks
        checks.append(edit)
        hits = [{"layer": "cl_blur", "time": 1.5, "source_time": 2.5}] if first else []
        return {"frames": 30, "hits": hits, "times": [1.5] if first else [],
                "flicker": {}, "unchecked": [], "layers": 1}

    drawn: list[str] = []
    real_run = render._run

    def recording_run(command, *args, **kwargs):
        name = Path(str(command[-1])).name
        if re.fullmatch(r"\.ed_retry_\d{4}\.mp4", name):  # one clip file
            drawn.append(name)
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(render, "_check_output", fake_check)
    monkeypatch.setattr(render, "_run", recording_run)
    project = {"id": "prj_retry", "source_path": str(source)}
    output = render.render_edit(project, edit, tmp_path)
    assert output.is_file()
    assert abs(media.duration(output) - 3.0) < 0.4
    # Three clips on the first pass, then only the clip the hit is in.
    assert drawn == [
        ".ed_retry_0000.mp4", ".ed_retry_0001.mp4", ".ed_retry_0002.mp4", ".ed_retry_0001.mp4",
    ]
    assert len(checks) == 2
    report = json.loads(output.with_suffix(".check.json").read_text())
    assert report["retried"] is True and report["refilled_clips"] == 1
    # No clip file is left behind.
    assert not [path for path in output.parent.glob(".ed_retry_*.mp4")
                if re.fullmatch(r"\.ed_retry_\d{4}\.mp4", path.name)]
