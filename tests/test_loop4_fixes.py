"""Loop 4: queue claim, one fill default, whole-render estimate, caption file."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from duckcore import app_settings, captions, render


def _queue(tmp_path: Path) -> render.RenderQueue:
    queue = render.RenderQueue.__new__(render.RenderQueue)
    queue.data_root = tmp_path
    queue.path = tmp_path / "state.db"
    queue.lock = __import__("threading").Lock()
    queue.paused = False
    queue.cancel_events = {}
    queue._init()
    return queue


def _enqueue(queue: render.RenderQueue, item_id: str) -> None:
    now = time.time()
    with sqlite3.connect(queue.path) as connection:
        connection.execute(
            """
            INSERT INTO render_queue
                (id, project_id, edit_id, title, state, stage, progress, message,
                 output, created, updated)
            VALUES (?, ?, ?, ?, 'queued', 'Queued', 0, '', '', ?, ?)
            """,
            (item_id, "p1", "ed_one", "Test", now, now),
        )


def test_two_workers_claim_a_job_once(tmp_path: Path) -> None:
    first = _queue(tmp_path)
    second = _queue(tmp_path)
    _enqueue(first, "rq_one")
    claimed = first._claim_next()
    assert claimed is not None and claimed["id"] == "rq_one"
    assert second._claim_next() is None


def test_fill_device_has_one_default(tmp_path: Path) -> None:
    assert app_settings.fill_device(tmp_path) == "gpu"


def test_render_reads_the_same_default_as_settings(tmp_path: Path, monkeypatch) -> None:
    def fake_chosen(method, device, directory):
        return device

    from duckcore.engine import textfill

    monkeypatch.setattr(textfill, "chosen_device", fake_chosen)
    assert render._fill_device(tmp_path) == "gpu"


def test_whole_render_estimate_uses_measured_ratio(tmp_path: Path) -> None:
    render.remember_render_time(tmp_path, 160.0, 851.0)
    edit = {"project_id": "p1", "clips": [{"start": 0.0, "end": 160.0}], "clean": []}
    estimate = render.estimate_edit(edit, {"width": 1080, "height": 1920, "fps": 30}, tmp_path)
    assert estimate["total_measured"] is True
    assert abs(estimate["total_seconds"] - 851.0) < 1.0


def test_no_whole_render_estimate_without_a_sample(tmp_path: Path) -> None:
    edit = {"project_id": "p1", "clips": [{"start": 0.0, "end": 10.0}], "clean": []}
    estimate = render.estimate_edit(edit, {"width": 1080, "height": 1920, "fps": 30}, tmp_path)
    assert estimate["total_seconds"] is None
    assert estimate["total_measured"] is False


def test_caption_file_is_opt_in() -> None:
    assert captions.wants_srt(None) is False
    assert captions.wants_srt({"cues": [{"text": "x"}]}) is False
    assert captions.wants_srt({"cues": [{"text": "x"}], "srt": True}) is True
