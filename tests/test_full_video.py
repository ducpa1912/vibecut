"""Moments can open the whole video: every scene in order, nothing picked."""

from __future__ import annotations

import clipset
import render


def _scene(scene_id, start, end):
    return {"id": scene_id, "start": start, "end": end}


def test_every_second_is_kept_in_time_order():
    scenes = [_scene(2, 20.0, 30.0), _scene(0, 1.0, 10.0), _scene(1, 12.0, 18.0)]
    document = clipset.build_full_video_set(scenes, [], 33.0)
    story = document["stories"][0]
    assert document["kind"] == "full_video"
    assert story["full_video"] is True
    assert [clip["scene"] for clip in story["clips"]] == [0, 1, 2]
    assert story["clips"][0]["start"] == 0.0, "the part before the first scene stays"
    assert story["clips"][-1]["end"] == 33.0, "the part after the last scene stays"
    for first, second in zip(story["clips"], story["clips"][1:]):
        assert first["end"] == second["start"], "no gap between scenes"
    assert story["dur"] == 33.0


def test_a_scene_too_short_for_a_clip_joins_the_one_before():
    scenes = [_scene(0, 0.0, 5.0), _scene(1, 5.0, 5.1), _scene(2, 5.1, 9.0)]
    clips = clipset.build_full_video_set(scenes, [], 9.0)["stories"][0]["clips"]
    assert [clip["scene"] for clip in clips] == [0, 2]
    assert clips[0]["end"] == clips[1]["start"]
    assert sum(clip["dur"] for clip in clips) == 9.0


def test_a_silent_video_still_opens():
    story = clipset.build_full_video_set([_scene(0, 0.0, 5.0)], [], 5.0)["stories"][0]
    assert story["sentences"] == []
    assert story["hook"]["text"] == "Full video"


def test_a_video_with_no_scenes_is_refused():
    try:
        clipset.build_full_video_set([], [], 5.0)
    except clipset.ClipSetError as exc:
        assert "no scenes" in str(exc)
    else:
        raise AssertionError("no scenes should be refused")


def test_touching_clips_read_the_audio_once():
    clips = [
        {"start": 0.0, "duration": 5.0},
        {"start": 5.0, "duration": 5.0},
        {"start": 10.0, "duration": 5.0, "reverse": True},
        {"start": 20.0, "duration": 2.0},
        {"kind": "blank", "start": 0.0, "duration": 1.0},
    ]
    joined = render._audio_inputs(clips)
    assert [item["duration"] for item in joined] == [10.0, 5.0, 2.0, 1.0]
    assert clips[0]["duration"] == 5.0, "the render's own clips are not changed"


def test_a_join_stops_before_it_drifts_from_the_video():
    clips = [{"start": 0.0, "duration": 5.0}, {"start": 5.05, "duration": 5.0}]
    assert len(render._audio_inputs(clips)) == 2


def test_long_steps_get_more_time_than_the_old_limit():
    assert render._long_step(60.0, 900) == 900
    assert render._long_step(3600.0, 900) == 28800


def test_a_full_video_alone_opens_edit_and_finish():
    root = Path(__file__).resolve().parent.parent / "static" / "studio"
    shell = (root / "shell.js").read_text(encoding="utf-8")
    stories = (root / "stories.js").read_text(encoding="utf-8")
    # Every set counts, not only the first, and the steps refresh before Edit opens.
    assert "records.reduce((total, record)" in shell
    assert "records[0]?.stories" not in shell
    opened = stories.index("await openFullVideo(job.id)")
    assert stories.index("ctx.refreshSteps?.()", opened) < stories.index('ctx.go("edit"', opened)
