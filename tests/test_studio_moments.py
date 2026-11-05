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
    assert render._dims("16:10", "720") == (1280, 800)
    assert render._dims("9:16", "final") == (1080, 1920)
    assert render._dims("9:16", "draft") == (540, 960)


def test_quality_tiers_cover_360_2k_and_4k():
    assert render.QUALITIES == ("360", "draft", "720", "final", "1440", "2160")
    assert render._dims("9:16", "360") == (360, 640)
    assert render._dims("9:16", "1440") == (1440, 2560)
    assert render._dims("9:16", "2160") == (2160, 3840)
    assert render._dims("16:9", "2160") == (3840, 2160)
    assert render._dims("1:1", "2160") == (2160, 2160)


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
    assert "addStory(job.id, activeSetId, ids" in stories
    assert "banScenes: scenes.map" in stories


def test_reveal_path_shows_a_real_file(env, tmp_path, monkeypatch):
    import app

    source = tmp_path / "clip.mp4"
    source.write_bytes(b"not a real video, only a path")
    calls = []
    monkeypatch.setattr(app.subprocess, "Popen", lambda *args, **kwargs: calls.append(args))
    monkeypatch.setattr(app.sys, "platform", "darwin")
    response = TestClient(app.app).post("/api/path/reveal", json={"path": str(source)})
    assert response.status_code == 200
    assert calls and calls[0][0][:2] == ["open", "-R"]


def test_add_story_route_appends_a_non_overlapping_story(env):
    import app
    import clipset
    from test_clipset import make_scenes

    scenes = make_scenes(12)
    job = app.load_job(env.job_id)
    job["status"] = "ready"
    job["source"]["duration"] = 48.0
    job["analysis"] = {"scenes": scenes}
    document = clipset.build_clipset(scenes, None, 48.0, count=3)
    document.update({
        "id": "cs_add_test",
        "job_id": env.job_id,
        "created": 1.0,
        "updated": 1.0,
    })
    job["clip_sets"] = [document]
    app.save_job(job)

    response = TestClient(app.app).post(
        f"/api/jobs/{env.job_id}/clip-sets/cs_add_test/stories",
        json={"scene_ids": [0, 1, 2, 3, 4], "title": "Custom opening"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["story"]["title"] == "Custom opening"
    assert len(body["clip_set"]["stories"]) == len(document["stories"]) + 1

    again = TestClient(app.app).post(
        f"/api/jobs/{env.job_id}/clip-sets/cs_add_test/stories",
        json={"scene_ids": [0, 1, 2, 3, 4]},
    )
    assert again.status_code == 409


@needs_node
def test_platform_safe_zones_and_new_shapes():
    out = run_module("edit/model.js", """
        return {
          shapes: m.ASPECTS,
          platforms: Object.keys(m.SAFE_ZONE_PRESETS),
          tiktok: m.safeZoneRects("9:16", "tiktok").safe,
          wide: m.CANVAS["16:10"],
        };
    """, prelude=NO_PAGE)
    assert "1:1" in out["shapes"] and "16:10" in out["shapes"]
    assert out["platforms"] == ["auto", "instagram", "tiktok", "rednote", "youtube", "facebook"]
    assert out["tiktok"]["x"] == 0.06 and out["tiktok"]["y"] == 0.068
    assert out["wide"] == {"width": 1920, "height": 1200, "label": "16:10 wide"}


def test_builder_collage_tiles_keep_their_height():
    """Tiles clip overflow; without max-content rows Chrome squashed them to 30 px."""
    css = (STUDIO / "studio.css").read_text(encoding="utf-8")
    collage = css[css.index(".st-moment-collage {"):]
    collage = collage[:collage.index("}")]
    assert "grid-auto-rows: max-content;" in collage
    assert ".st-moment-builder .st-dialog-body { gap: 12px; padding: 16px 20px;" in css


def test_step_numbers_follow_the_four_step_rail():
    edit = (STUDIO / "edit" / "index.js").read_text(encoding="utf-8")
    assert "Step 4 · Edit" not in edit and "Step 3 · Edit" in edit
    assert "Step 2 · Moments" in (STUDIO / "stories.js").read_text(encoding="utf-8")
    assert "Step 4 · Finish" in (STUDIO / "finish.js").read_text(encoding="utf-8")


def test_finish_clears_its_loading_line():
    finish = (STUDIO / "finish.js").read_text(encoding="utf-8")
    assert "announce(LOADING_NOTE)" in finish
    assert 'if (!notice || notice === LOADING_NOTE) announce("");' in finish


def test_moments_scan_can_be_cancelled_and_rescanned():
    """1b's Check cancel moved with Check into Moments."""
    text = (STUDIO / "stories.js").read_text(encoding="utf-8")
    assert "/check/cancel" in text and '"Cancel scan"' in text
    assert 'state === "cancelled" || state === "failed" ? null : report' in text
    assert "body: { sample_text: true, force }" in text
    refresh = text[text.index("async function refreshCheck("):]
    refresh = refresh[:refresh.index("\n  }\n")]
    assert "followCheck();" in refresh and "renderStories();" in refresh


def test_header_steps_keep_their_labels_and_the_video_name_truncates():
    """At 800 px "04 Finish" was squeezed to "4" behind the video name."""
    css = (STUDIO / "studio.css").read_text(encoding="utf-8")

    def rule(selector):
        start = css.index(selector + " {")
        return css[start:css.index("}", start)]

    assert "flex: 0 0 auto;" in rule(".st-rail-nav")
    assert "flex: 0 0 auto;" in rule(".st-step")
    assert "flex: 1 1 auto;" in rule(".st-top-right")
    status = rule(".st-top-status")
    assert "flex: 0 1 auto;" in status and "text-overflow: ellipsis;" in status
