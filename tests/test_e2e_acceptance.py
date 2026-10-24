"""Acceptance checks for rewrite fallbacks and provider failure handling.

These are deliberately small, end-to-end-ish tests around the public API and
the two failure modes that used to be silent: an unusable cloud reply falling
back to rules, and a failed script request replacing the last good snapshot.
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest
from fastapi.testclient import TestClient

import app
import audio
import history_store
import pipeline


def _http_error(status: int, body: str, url: str = audio.OPENROUTER_URL) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url, status, "error", {}, io.BytesIO(body.encode("utf-8")),
    )


class _Reply:
    def __init__(self, payload: dict):
        self.payload = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture(autouse=True)
def clean_cloud_state():
    audio.clear_openrouter_quarantine()
    audio.reset_provider_breaker()
    audio.OPENROUTER_LAST_ERROR = ""
    audio.OPENROUTER_LAST_STATUS = 0
    yield
    audio.clear_openrouter_quarantine()
    audio.reset_provider_breaker()


def _openrouter(monkeypatch, urlopen):
    monkeypatch.setattr(audio, "openrouter_key", lambda: "sk-acceptance-secret")
    monkeypatch.setattr(audio, "openrouter_model", lambda: "test/model:floor")
    monkeypatch.setattr(audio.urllib.request, "urlopen", urlopen)


def test_openrouter_401_quarantines_and_never_leaks_key(monkeypatch):
    body = json.dumps({
        "error": {"message": "User not found. key=sk-acceptance-secret"},
    })
    _openrouter(monkeypatch, lambda *a, **k: (_ for _ in ()).throw(_http_error(401, body)))

    assert audio._openrouter_text("hello", force=True) is None
    assert audio.OPENROUTER_LAST_STATUS == 401
    assert audio.openrouter_blocked() is True
    assert "sk-acceptance-secret" not in audio.OPENROUTER_LAST_ERROR
    assert "HTTP 401" in audio.OPENROUTER_LAST_ERROR


def test_openrouter_empty_reply_trips_breaker(monkeypatch):
    _openrouter(
        monkeypatch,
        lambda *a, **k: _Reply({"choices": [{"message": {"content": "   "}}]}),
    )

    for _ in range(audio.PROVIDER_BREAKER_FAILURES):
        assert audio._openrouter_text("hello", force=True) is None

    status = audio.provider_breaker_status("openrouter")
    assert status["open"] is True
    assert status["failures"] >= audio.PROVIDER_BREAKER_FAILURES
    assert "empty reply" in audio.OPENROUTER_LAST_ERROR.lower()


def test_openrouter_404_reports_model_and_does_not_switch(monkeypatch):
    body = json.dumps({"error": {"message": "No endpoints found for model test/model:floor"}})
    _openrouter(monkeypatch, lambda *a, **k: (_ for _ in ()).throw(_http_error(404, body)))

    assert audio._openrouter_text("hello", force=True) is None
    assert audio.OPENROUTER_LAST_STATUS == 404
    assert audio.OPENROUTER_LAST_MODEL == "test/model:floor"
    assert "test/model:floor" in audio.OPENROUTER_LAST_ERROR
    assert "not available" in audio.OPENROUTER_LAST_ERROR


def test_rules_fallback_is_marked_with_warning(monkeypatch):
    monkeypatch.setattr(audio, "_rewrite_candidates", lambda: ["opencode", "rules"])
    monkeypatch.setattr(audio, "_rewrite_opencode", lambda *a, **k: None)
    monkeypatch.setattr(audio, "_rules_rewrite", lambda script, *a, **k: [
        "Rules line." for _ in script
    ])
    monkeypatch.setattr(audio, "OPENCODE_LAST_ERROR", "quota exhausted")

    lines = audio.adapt_script(
        [{"text": "Source line.", "duration": 3.0, "rate": 1.0}],
        "en", "en", mode="smooth",
    )

    status = audio.rewrite_status()
    assert lines[0]["text"] == "Rules line."
    assert lines[0]["rewrite"] == "rules"
    assert status["fallback"] is True
    assert "rules fallback" in status["error"].lower()
    assert "quota exhausted" in status["error"]


def _make_job(job_id: str, root) -> None:
    scenes = [{
        "id": 0,
        "start": 0.0,
        "end": 4.0,
        "dur": 4.0,
        "mid": 2.0,
        "hook": 70.0,
        "score": 70.0,
        "deep": True,
        "ocr": "",
        "speech": "Hello world.",
        "tags": [],
        "crop": {"cx": 0.5, "cy": 0.5},
        "crop_mode": "center",
    }]
    job = {
        "id": job_id,
        "created": 1.0,
        "updated": 1.0,
        "status": "ready",
        "progress": 1.0,
        "message": "Ready",
        "error": None,
        "source": {
            "path": str(root / "source.mp4"),
            "name": "source.mp4",
            "duration": 60.0,
            "width": 1920,
            "height": 1080,
        },
        "options": {},
        "analysis": {
            "scenes": scenes,
            "hook_scene": 0,
            "deep_count": 1,
            "deep_scene_ids": [0],
            "engine": {"transcript_language": "en"},
        },
        "renders": {},
    }
    directory = app.JOBS / job_id
    directory.mkdir()
    (directory / "job.json").write_text(json.dumps(job), encoding="utf-8")


def _patch_script(monkeypatch, *, fail: bool = False) -> None:
    plan = {
        "target": 15,
        "total": 4.0,
        "hook_scene": 0,
        "auto": False,
        "clip_count": 1,
        "clips": [{
            "scene": 0,
            "start": 0.0,
            "end": 4.0,
            "dur": 4.0,
            "role": "hook",
        }],
        "_source_lang": "en",
    }
    monkeypatch.setattr(app, "_plan_for", lambda job, target, hook: plan)
    monkeypatch.setattr(pipeline, "read_transcript", lambda directory: [])
    if fail:
        def boom(*args, **kwargs):
            raise RuntimeError("acceptance boom")
        monkeypatch.setattr(audio, "build_script", boom)
    else:
        monkeypatch.setattr(audio, "build_script", lambda *a, **k: [{
            "scene": 0,
            "clip": 0,
            "role": "hook",
            "duration": 4.0,
            "text": "Hello world.",
            "original": "Hello world.",
            "emotion": "warm",
            "rate": 1.0,
        }])

    def good_adapt(script, *args, **kwargs):
        for line in script:
            line["literal"] = line["text"]
            line["rewrite"] = "rules"
        return script

    monkeypatch.setattr(audio, "adapt_script", good_adapt)
    monkeypatch.setattr(audio, "refit_script", lambda script: script)
    monkeypatch.setattr(audio, "translation_status", lambda: {
        "provider": "opencode", "source": "en", "target": "en", "lines": 1, "tried": [],
    })
    monkeypatch.setattr(audio, "rewrite_status", lambda: {
        "requested": True,
        "ok": True,
        "provider": "opencode",
        "used": "opencode",
        "fallback": False,
        "error": "",
        "attempts": [],
    })
    monkeypatch.setattr(audio, "scene_moods", lambda scenes, clips: ["warm"])


def test_old_job_without_history_is_compatible(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "JOBS", tmp_path / "jobs")
    app.JOBS.mkdir()
    job_id = "oldjob"
    _make_job(job_id, tmp_path)

    assert app.get_history(job_id) == {"entries": [], "count": 0}
    job = app.load_job(job_id)
    assert "history" not in app.public_job(job)
    assert "history" not in app.public_status(job)

    client = TestClient(app.app)
    assert client.get(f"/api/jobs/{job_id}/history").json() == {
        "entries": [], "count": 0,
    }


def test_failed_script_http_keeps_last_good_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "JOBS", tmp_path / "jobs")
    monkeypatch.setattr(app, "DATA", tmp_path)
    app.JOBS.mkdir()
    job_id = "acceptancejob"
    _make_job(job_id, tmp_path)
    _patch_script(monkeypatch)

    client = TestClient(app.app, raise_server_exceptions=False)
    first = client.post(
        f"/api/jobs/{job_id}/audio/script",
        json={"target": 15, "translate": "en", "mode": "smooth"},
    )
    assert first.status_code == 200
    first_id = first.json()["script_id"]
    assert first_id
    before = history_store.get_entry(app.JOBS / job_id, first_id)
    assert before["snapshot"]["final_lines"][0]["text"] == "Hello world."

    _patch_script(monkeypatch, fail=True)
    failed = client.post(
        f"/api/jobs/{job_id}/audio/script",
        json={"target": 15, "translate": "en", "mode": "smooth"},
    )
    assert failed.status_code == 500

    entries = history_store.list_entries(app.JOBS / job_id)
    assert entries[0]["status"] == "failed"
    assert "acceptance boom" in entries[0]["error"]
    assert any(item["id"] == first_id for item in entries[1:])
    after = history_store.get_entry(app.JOBS / job_id, first_id)
    assert after == before

    assert client.get(f"/api/jobs/{job_id}/history/doesnotexist").status_code == 404
    assert client.post(
        f"/api/jobs/{job_id}/history/doesnotexist/restore",
    ).status_code == 404
    assert client.get("/api/jobs/no-such-job/history").status_code == 404
