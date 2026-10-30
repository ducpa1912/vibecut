"""Classic translation route: memo reuse, no duplicate work, real failures only."""

from __future__ import annotations

import json
import threading

import pytest
from fastapi import HTTPException


@pytest.fixture(autouse=True)
def clean_runs():
    import routes_classic as routes

    routes.TRANSLATION_RUNS.clear()
    yield
    routes.TRANSLATION_RUNS.clear()


def _flag(tmp_path, texts, status="ready"):
    import routes_classic as routes

    path = tmp_path / "vi.json"
    path.write_text(json.dumps({
        "status": status,
        "source_hash": routes._translation_hash(texts),
        "lines": len(texts),
        "batches": 1,
    }), encoding="utf-8")
    return path


def test_a_ready_translation_memo_skips_the_worker(monkeypatch, tmp_path):
    import routes_classic as routes

    texts = ["one", "two"]
    flag = _flag(tmp_path, texts)
    monkeypatch.setattr(routes, "_translation_flag", lambda job_id, target: flag)
    monkeypatch.setattr(routes, "_translation_texts", lambda job_id: texts)
    monkeypatch.setattr(routes, "_translation_source", lambda job_id: "en")

    def no_thread(*args, **kwargs):
        raise AssertionError("a ready memo must not start another translation thread")

    monkeypatch.setattr(threading, "Thread", no_thread)
    state = routes.classic_translate(
        "copy-memo", routes.TranslateBody(target="vi"),
    )

    assert state["status"] == "ready"
    assert state["total"] == 2
    assert ("copy-memo", "vi") not in routes.TRANSLATION_RUNS


def test_a_repeat_request_while_translating_returns_the_same_run(monkeypatch, tmp_path):
    import routes_classic as routes

    texts = ["one", "two"]
    routes.TRANSLATION_RUNS[("copy-repeat", "vi")] = {
        "job_id": "copy-repeat", "target": "vi", "status": "running",
        "done": 1, "total": 2, "batch": 1, "batches": 1,
        "provider": "auto", "error": None,
    }
    monkeypatch.setattr(routes, "_translation_texts", lambda job_id: texts)
    monkeypatch.setattr(routes, "_translation_source", lambda job_id: "en")
    monkeypatch.setattr(routes, "_translation_flag", lambda job_id, target: tmp_path / "missing.json")

    def no_thread(*args, **kwargs):
        raise AssertionError("a running translation must not start a second thread")

    monkeypatch.setattr(threading, "Thread", no_thread)
    state = routes.classic_translate(
        "copy-repeat", routes.TranslateBody(target="vi"),
    )

    assert state["status"] == "running"
    assert state["done"] == 1
    assert routes.TRANSLATION_RUNS[("copy-repeat", "vi")]["status"] == "running"


def test_a_stale_ready_run_does_not_hide_a_changed_transcript(monkeypatch, tmp_path):
    import routes_classic as routes

    routes.TRANSLATION_RUNS[("copy-stale", "vi")] = {
        "job_id": "copy-stale", "target": "vi", "status": "ready",
        "done": 2, "total": 2, "batch": 1, "batches": 1,
    }
    old = _flag(tmp_path, ["old line"])
    monkeypatch.setattr(routes, "_translation_flag", lambda job_id, target: old)
    monkeypatch.setattr(routes, "_translation_texts", lambda job_id: ["new line"])
    monkeypatch.setattr(routes, "_translation_source", lambda job_id: "en")

    state = routes._translation_state("copy-stale", "vi")

    assert state["status"] == "idle"
    assert state["total"] == 1


def test_a_failed_worker_reports_failed_and_writes_no_ready_flag(monkeypatch, tmp_path):
    import audio
    import routes_classic as routes

    def broken(lines, source, target, provider="auto"):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(audio, "translate_lines", broken)
    flag = tmp_path / "vi.json"
    monkeypatch.setattr(routes, "_translation_flag", lambda job_id, target: flag)

    routes._translation_worker("copy-fail", "vi", "auto", "en", ["one", "two"])

    state = routes.TRANSLATION_RUNS[("copy-fail", "vi")]
    assert state["status"] == "failed"
    assert "provider unavailable" in state["error"]
    assert not flag.exists()


def test_no_transcript_is_not_a_fake_translation_failure(monkeypatch, tmp_path):
    import routes_classic as routes

    monkeypatch.setattr(routes, "_translation_texts", lambda job_id: [])
    monkeypatch.setattr(routes, "_translation_source", lambda job_id: "en")
    monkeypatch.setattr(routes, "_translation_flag", lambda job_id, target: tmp_path / "missing.json")

    with pytest.raises(HTTPException) as caught:
        routes.classic_translate("copy-empty", routes.TranslateBody(target="vi"))

    assert caught.value.status_code == 409
    assert ("copy-empty", "vi") not in routes.TRANSLATION_RUNS
