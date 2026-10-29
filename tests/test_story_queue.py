"""G3: ten story items run in order, survive a crash and resume on one click."""

from __future__ import annotations

import json
import threading
import time

import pytest

import story_queue as sq


class FakeBackend:
    """Deterministic artifact ids; renders finish after ``delay`` seconds."""

    def __init__(self, delay: float = 0.0, hang: set[str] | None = None, timeout: float = 30.0):
        self.delay = delay
        self.hang = hang or set()
        self.timeout = timeout
        self.lock = threading.Lock()
        self.starts: list[str] = []
        self.renders: dict[str, int] = {}
        self.ready_at: dict[str, float] = {}
        self.cancelled: list[str] = []

    def artifact(self, item: dict) -> str:
        return f"art_{item['story_id']}_{item['aspect'].replace(':', 'x')}"

    def start(self, item: dict) -> str:
        artifact = self.artifact(item)
        with self.lock:
            self.starts.append(item["story_id"])
            if artifact not in self.ready_at:
                self.renders[artifact] = self.renders.get(artifact, 0) + 1
                self.ready_at[artifact] = time.time() + self.delay
        return artifact

    def status(self, item: dict, artifact_id: str) -> str:
        if artifact_id in self.cancelled:
            return "cancelled"
        if item["story_id"] in self.hang:
            return "rendering"
        return "ready" if time.time() >= self.ready_at[artifact_id] else "rendering"

    def cancel(self, item: dict, artifact_id: str) -> None:
        self.cancelled.append(artifact_id)

    def timeout_for(self, item: dict) -> float:
        return self.timeout


def items(count: int) -> list[dict]:
    return [
        {"job_id": f"job{index % 2}", "set_id": "set1", "story_id": f"s{index}"}
        for index in range(1, count + 1)
    ]


def test_ten_story_items_run_sequentially_with_one_output_each(tmp_path):
    backend = FakeBackend()
    manager = sq.StoryQueueManager(tmp_path, backend, poll_interval=0.01)
    queue = manager.create(items(10))
    assert manager.wait(queue["id"], 5)
    done = manager.get(queue["id"])
    assert done["status"] == "done"
    assert [item["state"] for item in done["items"]] == ["done"] * 10
    assert backend.starts == [f"s{index}" for index in range(1, 11)]
    assert set(backend.renders.values()) == {1}


def test_queue_rejects_more_than_ten_items_and_bad_aspects(tmp_path):
    manager = sq.StoryQueueManager(tmp_path, FakeBackend())
    with pytest.raises(sq.QueueError, match="at most 10"):
        manager.create(items(11))
    with pytest.raises(sq.QueueError, match="16:10"):
        manager.create([{**items(1)[0], "aspect": "2:3"}])
    with pytest.raises(sq.QueueError, match="repeats"):
        manager.create(items(1) + items(1))


def test_kill_at_item_three_then_one_click_resume(tmp_path):
    """Simulate SIGKILL mid item 3 by writing the on-disk state it leaves."""
    first = FakeBackend()
    manager = sq.StoryQueueManager(tmp_path, first, poll_interval=0.01)
    queue = manager.create(items(10), start=False)
    path = tmp_path / "story_queues" / f"{queue['id']}.json"
    state = json.loads(path.read_text())
    state["status"] = "running"
    for index, item in enumerate(state["items"]):
        if index < 2:
            item["state"] = "done"
            item["artifact_id"] = first.start(item)
        elif index == 2:
            item["state"] = "running"
            item["artifact_id"] = first.start(item)
    path.write_text(json.dumps(state))

    # Restart: a new process with the same renders on disk.
    restarted = FakeBackend()
    restarted.ready_at = dict(first.ready_at)
    restarted.renders = dict(first.renders)
    manager = sq.StoryQueueManager(tmp_path, restarted, poll_interval=0.01)
    assert manager.recover() == 1
    banner = manager.interrupted()
    assert [row["id"] for row in banner] == [queue["id"]]
    paused = manager.get(queue["id"])
    assert paused["status"] == "paused"
    assert paused["items"][2]["state"] == "interrupted"
    time.sleep(0.05)
    assert restarted.starts == []  # never auto-run

    manager.resume(queue["id"])
    assert manager.wait(queue["id"], 5)
    done = manager.get(queue["id"])
    assert [item["state"] for item in done["items"]] == ["done"] * 10
    assert restarted.starts == [f"s{index}" for index in range(3, 11)]
    assert all(count == 1 for count in restarted.renders.values())
    assert len(restarted.renders) == 10


def test_watchdog_stops_a_hung_item_and_starts_the_next(tmp_path):
    backend = FakeBackend(hang={"s1"}, timeout=0.05)
    manager = sq.StoryQueueManager(tmp_path, backend, poll_interval=0.01)
    queue = manager.create(items(2))
    assert manager.wait(queue["id"], 5)
    done = manager.get(queue["id"])
    assert done["items"][0]["state"] == "failed"
    assert "Timed out" in done["items"][0]["error"]
    assert done["items"][1]["state"] == "done"
    assert backend.cancelled == ["art_s1_9x16"]


def test_failed_start_isolated_and_cancel_stops_running_render(tmp_path):
    class Flaky(FakeBackend):
        def start(self, item):
            if item["story_id"] == "s1":
                raise RuntimeError("source missing")
            return super().start(item)

    backend = Flaky()
    manager = sq.StoryQueueManager(tmp_path, backend, poll_interval=0.01)
    queue = manager.create(items(2))
    assert manager.wait(queue["id"], 5)
    done = manager.get(queue["id"])
    assert [item["state"] for item in done["items"]] == ["failed", "done"]
    assert done["items"][0]["error"] == "source missing"

    slow = FakeBackend(hang={"s1"})
    manager = sq.StoryQueueManager(tmp_path / "b", slow, poll_interval=0.01)
    queue = manager.create(items(3))
    time.sleep(0.05)
    cancelled = manager.cancel(queue["id"])
    assert manager.wait(queue["id"], 5)
    assert cancelled["status"] == "cancelled"
    assert all(item["state"] == "cancelled" for item in cancelled["items"])
    assert slow.cancelled == ["art_s1_9x16"]


def test_pause_then_resume_waits_on_the_same_render(tmp_path):
    backend = FakeBackend(delay=0.2)
    manager = sq.StoryQueueManager(tmp_path, backend, poll_interval=0.01)
    queue = manager.create(items(2))
    time.sleep(0.05)
    paused = manager.pause(queue["id"])
    assert manager.wait(queue["id"], 5)
    assert paused["status"] == "paused"
    assert paused["items"][0]["state"] == "queued"
    manager.resume(queue["id"])
    assert manager.wait(queue["id"], 5)
    assert manager.get(queue["id"])["status"] == "done"
    assert backend.renders == {"art_s1_9x16": 1, "art_s2_9x16": 1}


def test_startup_stops_only_orphaned_encoders_under_this_data_dir(monkeypatch, tmp_path):
    import subprocess

    import app

    monkeypatch.setattr(app, "JOBS", tmp_path / "jobs")
    listing = "\n".join([
        f" 101 1 /opt/homebrew/bin/ffmpeg -i {tmp_path}/jobs/j1/renders/tmp_1/master.mp4 out.mp4",
        " 102 1 /opt/homebrew/bin/ffmpeg -i /Users/someone/Movies/other.mp4 out.mp4",
        f" 103 1 /usr/bin/python3 app.py {tmp_path}/jobs",
    ])
    monkeypatch.setattr(
        subprocess, "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, stdout=listing, stderr=""),
    )
    killed = []
    monkeypatch.setattr(app.os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(app.os, "killpg", lambda pgid, sig: killed.append(pgid))
    assert app._stop_orphan_encoders() == 1
    assert killed == [101]


def test_render_pruning_is_off_by_default(monkeypatch):
    import app

    monkeypatch.delenv("VIBECUT_PRUNE_RENDERS", raising=False)
    assert app._render_pruning_enabled() is False
    monkeypatch.setenv("VIBECUT_PRUNE_RENDERS", "1")
    assert app._render_pruning_enabled() is True
