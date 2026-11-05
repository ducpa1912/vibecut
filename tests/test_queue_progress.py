"""Story queues show the running render's own progress and ETA (QA #18)."""

from __future__ import annotations

import app


def test_running_item_carries_render_progress_and_eta(monkeypatch):
    job = {"renders": {"k1": {"artifact_id": "art_1", "progress": 0.4, "eta": 30.0,
                              "message": "Rendering beats"}}}
    monkeypatch.setattr(app, "load_job", lambda job_id: job)
    queue = {"items": [
        {"state": "done", "job_id": "j1"},
        {"state": "running", "job_id": "j1", "artifact_id": "art_1"},
        {"state": "queued", "job_id": "j1"},
    ]}
    live = app._live_queue(queue)
    running = live["items"][1]
    assert running["progress"] == 0.4 and running["eta"] == 30.0
    assert running["message"] == "Rendering beats"
    assert live["progress"] == round((1 + 0.4) / 3, 4)
    # 30 s left on the running item plus one waiting item of 50 s.
    assert live["eta"] == 80.0


def test_queue_without_a_running_render_keeps_its_counts(monkeypatch):
    monkeypatch.setattr(app, "load_job", lambda job_id: {"renders": {}})
    queue = {"items": [{"state": "done"}, {"state": "queued"}], "progress": 0.5}
    live = app._live_queue(queue)
    assert live["progress"] == 0.5 and "eta" not in live


def test_the_header_and_its_item_show_one_estimate(monkeypatch):
    """They read 56 and 168 minutes on the same render, on 2026-11-05."""
    app._QUEUE_ETA_STATE.clear()
    record = {"artifact_id": "art_1", "progress": 0.19, "eta": 3400.0,
              "message": "Filling text, beat 8/19 · LaMa (per frame) 61/101"}
    monkeypatch.setattr(app, "load_job", lambda job_id: {"renders": {"k": dict(record)}})

    def view():
        return app._live_queue({"id": "sq_one", "status": "running", "items": [
            {"id": "i1", "state": "running", "job_id": "j1", "artifact_id": "art_1"},
        ]})

    first = view()
    assert first["eta"] == first["items"][0]["eta"] == 3400.0
    # The estimate went up; the header must not hold the old low one.
    record["eta"] = 3800.0
    record["message"] = "Filling text, beat 8/19 · LaMa (per frame) 71/101"
    second = view()
    assert second["eta"] == second["items"][0]["eta"] == 3520.0
