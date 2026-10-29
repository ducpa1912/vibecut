"""A quick-scan hook has no still, so the index must not advertise one."""

from __future__ import annotations

import app


def test_a_quick_scan_hook_has_no_hook_thumb():
    job = {
        "id": "job1",
        "source": {"name": "a.mp4", "duration": 10},
        "analysis": {
            "hook_scene": 2,
            "scene_count": 3,
            "scenes": [
                {"id": 0, "deep": True},
                {"id": 1, "deep": True},
                {"id": 2, "deep": False},
            ],
        },
    }

    row = app._job_index_row(job)

    assert row["hook_thumb"] is None


def test_a_deep_hook_keeps_its_hook_thumb():
    job = {
        "id": "job2",
        "source": {"name": "a.mp4", "duration": 10},
        "analysis": {
            "hook_scene": 1,
            "scene_count": 2,
            "scenes": [{"id": 0, "deep": True}, {"id": 1, "deep": True}],
        },
    }

    row = app._job_index_row(job)

    assert row["hook_thumb"] == "/api/jobs/job2/thumb/1"
