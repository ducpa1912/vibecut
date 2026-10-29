"""Moments: longer picks, 720p, and the combined Check + Stories screen."""

from __future__ import annotations

import clipset
import render
from fastapi.testclient import TestClient
from test_artifacts import env  # noqa: F401
from test_r3_t2_library_static import STUDIO, needs_node
from test_studio_js import NO_PAGE, run_module


def test_extended_and_custom_lengths_reach_three_minutes():
    assert clipset.LENGTH_CEIL_S == 180.0
    assert clipset.LENGTH_PRESETS["extended"] == (90.0, 180.0)
    assert clipset.LENGTH_PRESETS["long"] == (45.0, 90.0)


def test_720p_is_offered_between_final_and_draft():
    assert render._dims("9:16", "720") == (720, 1280)
    assert render._dims("4:5", "720") == (720, 900)
    assert render._dims("9:16", "final") == (1080, 1920)
    assert render._dims("9:16", "draft") == (540, 960)


def test_delete_clip_set_removes_one_moment_set(env):
    import app

    job = app.load_job(env.job_id)
    job["clip_sets"] = [
        {"id": "cs_keep", "stories": [{"id": "st_keep"}]},
        {"id": "cs_drop", "stories": []},
    ]
    app.save_job(job)

    response = TestClient(app.app).delete(
        f"/api/jobs/{env.job_id}/clip-sets/cs_drop",
    )
    assert response.status_code == 200
    assert response.json()["id"] == "cs_drop"
    stored = app.load_job(env.job_id)
    assert [item["id"] for item in stored["clip_sets"]] == ["cs_keep"]


@needs_node
def test_moments_length_presets_match_the_server():
    out = run_module("stories.js", """
        return {
          extended: m.LENGTH_PRESETS.extended,
          custom: m.LENGTH_PRESETS.custom,
          values: Object.keys(m.LENGTH_PRESETS),
        };
    """, prelude=NO_PAGE)
    assert out["extended"] == {"label": "Extended · 90–180 s", "min": 90, "max": 180}
    assert out["custom"] == {"label": "Custom range", "min": 15, "max": 180}
    assert "extended" in out["values"] and "custom" in out["values"]


def test_shell_has_one_moments_step_and_no_separate_check_step():
    shell = (STUDIO / "shell.js").read_text(encoding="utf-8")
    assert 'id: "moments"' in shell
    assert 'id: "check"' not in shell
    assert 'id: "stories"' not in shell
    assert 'value === "check" || value === "stories" ? "moments"' in shell


def test_moment_cards_carry_a_frame_boxes_and_the_builder():
    stories = (STUDIO / "stories.js").read_text(encoding="utf-8")
    assert "function momentFrame(" in stories
    assert '"st-moment-box"' in stories
    assert "function openBuilder(" in stories
    assert "banScenes: banned" in stories
