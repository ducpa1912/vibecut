"""Cancel for long voice work: the clip search and the clone requests.

A clone request carries a client task id; ``DELETE /api/voices/tasks/{id}``
sets its cancel switch. The request stops cleaning at its next check, answers
409 and never saves a clone, even when the cancel lands before the upload.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import audio
import voice_clone

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


@pytest.fixture(autouse=True)
def clone_store(monkeypatch, tmp_path):
    import routes_voice_clone as routes

    monkeypatch.setattr(voice_clone.settings_store, "DATA", tmp_path)
    monkeypatch.setattr(voice_clone, "available", lambda: True)
    routes.VOICE_TASK_CANCELS.clear()
    yield
    routes.VOICE_TASK_CANCELS.clear()


def _job(tmp_path, monkeypatch, job_id="job-cancel-clone"):
    import app

    jobs = tmp_path / "jobs"
    monkeypatch.setattr(app, "JOBS", jobs)
    directory = jobs / job_id
    directory.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "talk.mp4"
    source.write_bytes(b"\x00" * 2048)
    job = {"id": job_id, "source": {"path": str(source), "name": "talk.mp4"}, "status": "ready"}
    (directory / "job.json").write_text(json.dumps(job), encoding="utf-8")
    return job, directory


def _fake_prepare(source, output, **kwargs):
    output.write_bytes(b"ID3" + b"\x00" * 4000)
    return 30.0


def _slow_clean(started: threading.Event, seen: dict):
    def clean(source, out_dir, **kwargs):
        cancel = kwargs.get("cancel_event")
        seen["cancel_event"] = cancel
        started.set()
        assert cancel is not None and cancel.wait(5.0)
        raise audio.AudioError("Voice extraction cancelled.")
    return clean


def _in_thread(call):
    box = {}
    thread = threading.Thread(target=lambda: box.setdefault("response", call()))
    thread.start()
    return thread, box


def test_cancel_stops_an_upload_clone_and_saves_nothing(tmp_path, monkeypatch):
    import app
    import routes_voice_clone as routes
    import voice_extract

    started, seen = threading.Event(), {}
    monkeypatch.setattr(routes, "_upload_head", lambda raw, work, cancel_event=None: raw)
    monkeypatch.setattr(voice_extract, "extract_clean_voice", _slow_clean(started, seen))
    monkeypatch.setattr(voice_clone, "prepare_sample", _fake_prepare)
    api = TestClient(app.app)
    thread, box = _in_thread(lambda: api.post(
        "/api/voices/clones",
        files={"file": ("me.wav", b"RIFF" + b"\x00" * 128, "audio/wav")},
        data={"consent": "true", "name": "Me", "task": "vt_upload_1"},
    ))
    assert started.wait(5.0)
    assert api.delete("/api/voices/tasks/vt_upload_1").json() == {"cancelled": "vt_upload_1"}
    thread.join(10.0)
    response = box["response"]
    assert response.status_code == 409, response.text
    assert response.json()["detail"] == routes.CANCELLED
    assert voice_clone.list_clones() == []
    assert "vt_upload_1" not in routes.VOICE_TASK_CANCELS


def test_cancel_stops_a_range_clone_and_saves_nothing(tmp_path, monkeypatch):
    import app
    import voice_extract

    job, _directory = _job(tmp_path, monkeypatch)
    started, seen = threading.Event(), {}
    monkeypatch.setattr(voice_extract, "extract_clean_voice", _slow_clean(started, seen))
    monkeypatch.setattr(voice_clone, "prepare_sample", _fake_prepare)
    api = TestClient(app.app)
    thread, box = _in_thread(lambda: api.post(
        f"/api/jobs/{job['id']}/voices/clone",
        json={"consent": True, "start": 0, "end": 30, "task": "vt_range_1"},
    ))
    assert started.wait(5.0)
    api.delete("/api/voices/tasks/vt_range_1")
    thread.join(10.0)
    assert box["response"].status_code == 409, box["response"].text
    assert voice_clone.list_clones() == []


def test_a_cancel_sent_before_the_request_still_counts(tmp_path, monkeypatch):
    import app

    job, directory = _job(tmp_path, monkeypatch)
    candidates = directory / "voice-candidates"
    candidates.mkdir(parents=True)
    (candidates / "candidate-01.wav").write_bytes(b"RIFF" + b"\x00" * 256)
    monkeypatch.setattr(voice_clone, "prepare_sample", _fake_prepare)
    api = TestClient(app.app)
    api.delete("/api/voices/tasks/vt_early_1")
    response = api.post(
        f"/api/jobs/{job['id']}/voices/clone",
        json={"consent": True, "candidate": 1, "task": "vt_early_1"},
    )
    assert response.status_code == 409
    assert voice_clone.list_clones() == []
    # Without a task, or with a different one, the clone goes through.
    ok = api.post(
        f"/api/jobs/{job['id']}/voices/clone",
        json={"consent": True, "candidate": 1, "task": "vt_other_1"},
    )
    assert ok.status_code == 200, ok.text
    assert len(voice_clone.list_clones()) == 1


def test_task_ids_are_checked_and_the_table_stays_small(monkeypatch):
    import app
    import routes_voice_clone as routes

    api = TestClient(app.app)
    assert api.delete("/api/voices/tasks/bad id!").status_code in {400, 404}
    assert api.delete("/api/voices/tasks/short").status_code == 400
    for index in range(routes.VOICE_TASK_MEMORY + 10):
        api.delete(f"/api/voices/tasks/vt_cap_{index:04d}")
    assert len(routes.VOICE_TASK_CANCELS) == routes.VOICE_TASK_MEMORY


def test_cancel_needs_voice_room_and_same_origin(monkeypatch):
    import app

    api = TestClient(app.app)
    blocked = api.delete("/api/voices/tasks/vt_origin_1", headers={"Origin": "https://evil.example"})
    assert blocked.status_code == 403
    monkeypatch.setenv("VIBECUT_FEATURES", "")
    assert api.delete("/api/voices/tasks/vt_origin_1").status_code == 404


@pytest.mark.skipif(not NODE, reason="node is not installed")
def test_client_task_ids_match_the_server_and_cancels_read_plainly():
    import routes_voice_clone as routes

    url = (ROOT / "static" / "voice" / "voiceclone.js").as_uri()
    script = (
        f"const m = await import({json.dumps(url)});\n"
        "process.stdout.write(JSON.stringify({ids: [m.newVoiceTask(), m.newVoiceTask()],"
        " cancelled: [m.wasCancelled({status: 409}), m.wasCancelled({message: 'Cancelled. No voice was cloned.'}),"
        " m.wasCancelled({status: 400, message: 'Bad'})],"
        " stopped: [m.isStopped({name: 'AbortError'}), m.isStopped(new Error('x'))]}));\n"
    )
    result = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["ids"][0] != out["ids"][1]
    assert all(routes.VOICE_TASK_ID.match(item) for item in out["ids"])
    assert out["cancelled"] == [True, True, False]
    assert out["stopped"] == [True, False]


def test_pages_offer_cancel_for_search_clone_and_samples():
    voice = ROOT / "static" / "voice"
    finder = (voice / "clipfinder.js").read_text(encoding="utf-8")
    assert "cancelVoiceCandidates(forJob)" in finder
    assert '"aria-label": "Cancel the clip search"' in finder
    assert "cancelVoiceTask(cloneTask)" in finder and "body.task = cloneTask" in finder
    panel = (voice / "voiceclone.js").read_text(encoding="utf-8")
    assert 'if (task) form.append("task", task);' in panel
    assert "cancelVoiceTask(task)" in panel
    assert "if (pendingSample) pendingSample.abort();" in panel
