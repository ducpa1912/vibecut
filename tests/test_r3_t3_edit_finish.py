"""R3 T3: Edit navigation, queue idempotency, Finish honesty, preflight, frames."""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app
import artifacts
import edits
import preflight
import render
import story_queue as sq

STUDIO = Path(__file__).resolve().parents[1] / "static" / "studio"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(not NODE, reason="node is not installed")

CLIPS = [{"scene": 0, "start": 0.0, "end": 4.0, "dur": 4.0, "role": "hook"}]
SCENES = [{
    "id": 0, "start": 0.0, "end": 8.0, "dur": 8.0,
    "speech": "I'll show you three things later and", "crops": {},
}]


def _story() -> dict:
    return {
        "id": "st_0000000_0004000",
        "title": "Story one",
        "start": 0.0,
        "end": 4.0,
        "dur": 4.0,
        "clips": copy.deepcopy(CLIPS),
        "sentences": [{"id": 0, "start": 0.0, "end": 4.0, "text": "I'll show you three things later and"}],
    }


def _job(job_id: str = "j1") -> dict:
    return {
        "id": job_id,
        "status": "ready",
        "created": 1.0,
        "updated": 1.0,
        "source": {
            "name": "source.mp4",
            "path": "",
            "duration": 8.0,
            "width": 1080,
            "height": 1920,
            "fingerprint": "fixture",
        },
        "analysis": {"scenes": copy.deepcopy(SCENES), "hook_scene": 0},
        "clip_sets": [{
            "id": "cs_1",
            "job_id": job_id,
            "created": 1.0,
            "updated": 1.0,
            "stories": [_story()],
        }],
        "renders": {},
    }


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    jobs = data / "jobs"
    sources = data / "sources"
    jobs.mkdir(parents=True)
    sources.mkdir(parents=True)
    source = sources / "source.mp4"
    source.write_bytes(b"fake-source")
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.setattr(app, "SOURCES", sources)
    monkeypatch.delenv("VIBECUT_TOKEN", raising=False)
    job = _job()
    job["source"]["path"] = str(source)
    directory = jobs / job["id"]
    directory.mkdir()
    (directory / "job.json").write_text(json.dumps(job), encoding="utf-8")
    return {
        "data": data,
        "jobs": jobs,
        "dir": directory,
        "job": job,
        "client": TestClient(app.app),
    }


# ---------------------------------------------------------------- Edit navigation


def test_edit_keeps_save_state_and_story_switch_without_the_moment_bar():
    source = (STUDIO / "edit" / "index.js").read_text(encoding="utf-8")
    preview = (STUDIO / "edit" / "preview.js").read_text(encoding="utf-8")
    assert "Back to Moments" not in source
    assert "st-edit-toolbar" not in source
    assert 'id="st-edit-moment-btn"' not in source
    assert 'id="st-preview-story-btn"' in preview
    shell = (STUDIO / "shell.js").read_text(encoding="utf-8")
    assert 'id="st-edit-ready"' in shell
    assert 'id="st-edit-shortcuts-open"' in shell
    assert "st-edit-stepnav" not in source
    assert "position: sticky" not in source
    # The app-bar step rail flushes the autosave before leaving Edit.
    assert "setLeaveGuard" in shell and "setLeaveGuard" in source
    assert "const saved = await flushSave();" in source


# ---------------------------------------------------------------- queue route


class SlowQueueBackend:
    """Renders stay running until the test releases them."""

    def __init__(self) -> None:
        self.release = threading.Event()
        self.starts: list[tuple[str, str]] = []

    def start(self, item: dict) -> str:
        self.starts.append((item["story_id"], item["aspect"]))
        return f"art_{item['story_id']}_{item['aspect'].replace(':', 'x')}"

    def status(self, item: dict, artifact_id: str) -> str:
        return "ready" if self.release.is_set() else "rendering"

    def cancel(self, item: dict, artifact_id: str) -> None:
        self.release.set()

    def timeout_for(self, item: dict) -> float:
        return 30.0


def _wait_for(predicate, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    raise AssertionError("timed out waiting for condition")


def _queue_body(aspect: str = "9:16") -> dict:
    return {"items": [{
        "job_id": "j1",
        "set_id": "cs_1",
        "story_id": "st_0000000_0004000",
        "aspect": aspect,
        "quality": "final",
        "title": "Story one",
    }]}


def test_queue_all_twice_attaches_to_the_active_item(env, monkeypatch):
    backend = SlowQueueBackend()
    manager = sq.StoryQueueManager(env["data"], backend, poll_interval=0.01)
    monkeypatch.setattr(app, "story_queues", lambda: manager)

    first = env["client"].post("/api/story-queues", json=_queue_body())
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["attached"] is False
    queue_id = first_body["queue"]["id"]
    _wait_for(lambda: manager.get(queue_id)["items"][0]["state"] == "running")

    second = env["client"].post("/api/story-queues", json=_queue_body())
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["attached"] is True
    assert second_body["queue"]["id"] == queue_id
    assert len(manager.list()) == 1
    items = manager.get(queue_id)["items"]
    assert len(items) == 1
    assert items[0]["state"] == "running"

    backend.release.set()
    assert manager.wait(queue_id, 5)
    done = manager.get(queue_id)
    assert done["status"] == "done"
    assert [item["state"] for item in done["items"]] == ["done"]
    assert backend.starts == [("st_0000000_0004000", "9:16")]


def test_queue_second_shape_is_a_separate_identity(env, monkeypatch):
    backend = SlowQueueBackend()
    manager = sq.StoryQueueManager(env["data"], backend, poll_interval=0.01)
    monkeypatch.setattr(app, "story_queues", lambda: manager)

    first = env["client"].post("/api/story-queues", json=_queue_body("9:16"))
    assert first.status_code == 200
    second = env["client"].post("/api/story-queues", json=_queue_body("4:5"))
    assert second.status_code == 200
    assert second.json()["attached"] is False
    assert len(manager.list()) == 2

    backend.release.set()
    for queue in manager.list():
        manager.wait(queue["id"], 5)


def test_ready_story_render_is_reused_not_rebuilt(env, monkeypatch):
    submitted: list[tuple] = []
    monkeypatch.setattr(app.render_pool, "submit", lambda *args, **kwargs: submitted.append((args, kwargs)))
    monkeypatch.setattr(app.disk, "preflight", lambda *args, **kwargs: None)

    body = app.StoryRenderBody(aspect="9:16", quality="final")
    first = app._queue_story_render("j1", "cs_1", "st_0000000_0004000", body, reject_active=False)
    artifact_id = first["artifact_id"]
    assert len(submitted) == 1

    job_dir = app._job_dir("j1")
    manifest = artifacts.load_manifest(job_dir, artifact_id)
    assert manifest is not None
    media = artifacts.media_path(job_dir, artifact_id, "reel.mp4")
    media.parent.mkdir(parents=True, exist_ok=True)
    media.write_bytes(b"fake-reel")
    artifacts.mark_status(job_dir, artifact_id, "ready")
    app._set_render(
        "j1", first["render"]["record_key"], status="ready", progress=1.0,
        artifact_id=artifact_id, message="Reel ready",
    )

    again = app._queue_story_render("j1", "cs_1", "st_0000000_0004000", body, reject_active=False)
    assert again["artifact_id"] == artifact_id
    assert again["render"]["status"] == "ready"
    assert len(submitted) == 1


def test_queue_backend_reports_the_artifact_error(env):
    spec = artifacts.build_spec(
        env["job"], {"target": 4, "clips": copy.deepcopy(CLIPS), "hook_scene": 0},
        quality="final", aspect="9:16", captions=False,
    )
    manifest = artifacts.make_manifest("j1", spec, status="queued", record_key="k")
    manifest = artifacts.save_manifest(env["dir"], manifest)
    artifacts.mark_status(
        env["dir"], manifest["artifact_id"], "failed",
        error="Dub needs a target language.",
    )

    backend = app.StoryRenderBackend()
    assert backend.error({"job_id": "j1"}, manifest["artifact_id"]) == (
        "Dub needs a target language."
    )
    assert backend.error({"job_id": "j1"}, "art_missing") == ""


# ---------------------------------------------------------------- preflight


def test_preflight_resolves_a_clip_set_story_id(env):
    response = env["client"].get("/api/jobs/j1/preflight?story_id=st_0000000_0004000")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["story_id"] == "st_0000000_0004000"
    assert body["media_source"] == "source_fallback"
    assert set(body["checks"]) == set(preflight.CHECK_IDS)
    assert body["findings"] or any(
        meta["status"] in {"pass", "unavailable"} for meta in body["checks"].values()
    )


def test_preflight_still_rejects_an_unknown_story(env):
    response = env["client"].get("/api/jobs/j1/preflight?story_id=st_missing")
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["code"] == "story_not_found"


# ---------------------------------------------------------------- frame at end


def _save_edit(env) -> dict:
    edit = edits.build_edit(
        story_ref={
            "set_id": "cs_1",
            "story_id": "st_0000000_0004000",
            "clip_hash": edits.clip_snapshot_hash(CLIPS),
            "title": "Story one",
            "duration": 4.0,
            "clip_count": 1,
        },
        aspect="9:16",
        created=1.0,
    )
    edits.save_edit(env["dir"], edit)
    path = env["dir"] / "job.json"
    job = json.loads(path.read_text(encoding="utf-8"))
    edits.set_pointer(job, edit)
    path.write_text(json.dumps(job), encoding="utf-8")
    return edit


def test_frame_at_the_story_end_is_the_last_frame(env, monkeypatch):
    edit = _save_edit(env)
    calls: list[float] = []

    def fake_frame(source, meta, job_dir, compiled, at, **kwargs):
        calls.append(float(at))
        return b"\xff\xd8\xff\xe0fake-jpeg\xff\xd9"

    monkeypatch.setattr(render, "render_story_frame", fake_frame)
    response = env["client"].get(f"/api/jobs/j1/edits/{edit['id']}/frame?t=4.000")
    assert response.status_code == 200, response.text
    assert calls == [4.0]

    for query in ("t=-1", "t=9", "t=nan", "t=inf", ""):
        bad = env["client"].get(f"/api/jobs/j1/edits/{edit['id']}/frame?{query}")
        assert bad.status_code == 422, query


# ---------------------------------------------------------------- render ETA


def _eta_queue(eta, message="Rendering beats", queue_id="sq_r3_eta"):
    return {
        "id": queue_id,
        "status": "running",
        "items": [
            {
                "id": "i1", "state": "running", "job_id": "j1",
                "artifact_id": "art_1", "progress": 0.4,
            },
            {"id": "i2", "state": "queued", "job_id": "j1"},
        ],
    }


def test_queue_eta_hides_zero_and_never_rises_within_a_stage(monkeypatch):
    app._QUEUE_ETA_STATE.clear()
    record = {"artifact_id": "art_1", "progress": 0.4, "eta": None, "message": "Rendering beats"}
    monkeypatch.setattr(app, "load_job", lambda job_id: {"renders": {"k": dict(record)}})

    hidden = app._live_queue(_eta_queue(None, queue_id="sq_r3_hidden"))
    assert "eta" not in hidden["items"][0]
    assert "eta" not in hidden

    record["eta"] = 30.0
    first = app._live_queue(_eta_queue(30.0))
    assert first["items"][0]["eta"] == 30.0
    assert first["eta"] == 80.0

    record["eta"] = 45.0
    second = app._live_queue(_eta_queue(45.0))
    assert second["items"][0]["eta"] == 30.0
    assert second["eta"] <= 80.0

    record["eta"] = 45.0
    record["message"] = "Burning layers"
    third = app._live_queue(_eta_queue(45.0, message="Burning layers"))
    assert third["items"][0]["eta"] == 45.0

    record["eta"] = 0
    zero = app._live_queue(_eta_queue(0.0, message="Burning layers"))
    assert "eta" not in zero["items"][0]
    assert "eta" not in zero


# ---------------------------------------------------------------- JS helpers


def run_finish(body: str):
    url = (STUDIO / "finish.js").as_uri()
    script = (
        f"const m = await import({json.dumps(url)});\n"
        f"const out = await (async () => {{ {body} }})();\n"
        "process.stdout.write(JSON.stringify(out));\n"
    )
    result = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout or "null")


@needs_node
def test_finish_summary_counts_every_story_and_both_shapes():
    out = run_finish("""
        const queues = [
          {id: "q1", status: "running", items: [
            {job_id: "j1", set_id: "cs1", story_id: "s1", aspect: "9:16", state: "done"},
            {job_id: "j1", set_id: "cs1", story_id: "s1", aspect: "4:5", state: "running"},
          ]},
          {id: "q2", status: "queued", items: [
            {job_id: "j1", set_id: "cs1", story_id: "s2", aspect: "9:16", state: "queued"},
            {job_id: "j1", set_id: "cs1", story_id: "s2", aspect: "4:5", state: "queued"},
          ]},
        ];
        return m.queueSummary(queues, {jobId: "j1", setId: "cs1"});
    """)
    assert out["stories"] == 2
    assert out["total"] == 4
    assert out["shapes"] == {"9:16": 2, "4:5": 2}
    assert "2 stories" in out["text"]
    assert "4 renders" in out["text"]
    assert "2 in 9:16" in out["text"] and "2 in 4:5" in out["text"]
    assert "1 running" in out["text"] and "2 waiting" in out["text"] and "1 done" in out["text"]


@needs_node
def test_finish_eta_is_hidden_until_measured_and_never_zero():
    out = run_finish("""
        return [
          m.itemProgressText({progress: 0.1, eta: 0}),
          m.itemProgressText({progress: 0.1, eta: null}),
          m.itemProgressText({progress: 0.42, eta: 80}),
          m.queueProgressText({status: "running", progress: 0.1, eta: 0}),
          m.queueProgressText({status: "running", progress: 0.1}),
          m.queueProgressText({status: "running", progress: 0.5, eta: 12}),
        ];
    """)
    assert out[:2] == ["10%", "10%"]
    assert out[2] == "42% · about 1 min 20 s left"
    assert out[3] == "10%"
    assert out[4] == "10%"
    assert out[5] == "50% · 12 s left"


@needs_node
def test_finish_404_keeps_the_server_reason():
    out = run_finish("""
        return [
          m.checksFailedNote({status: 404, message: "Story 'st_1' was not found in this job."}),
          m.checksFailedNote({status: 404}),
          m.checksFailedNote({status: 500, message: "Boom"}),
        ];
    """)
    assert "was not found" in out[0]
    assert out[1] == "Render this story first; checks run on the render."
    assert out[2] == "Checks could not run for this story: Boom"
