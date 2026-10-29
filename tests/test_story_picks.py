"""More stories, length presets and fewer housekeeping picks (QA #13)."""

from __future__ import annotations

import pytest

import clipset
from test_clipset import api, make_scenes, transcript_for, write_job  # noqa: F401


def test_a_story_range_moves_by_one_sentence_through_the_patch(api):  # noqa: F811
    """The ± start/end controls send this PATCH (QA #14)."""
    write_job(api.jobs_dir, "j1")
    record = api.post("/api/jobs/j1/clip-sets", json={"count": 3}).json()["clip_set"]
    story = record["stories"][0]
    ids = [int(item["id"]) for item in story["sentences"]]
    wider = ids + [ids[-1] + 1]
    response = api.patch(
        f"/api/jobs/j1/clip-sets/{record['id']}",
        json={"stories": [{"id": story["id"], "sentences": wider}]},
    )
    assert response.status_code == 200, response.text
    updated = next(item for item in response.json()["clip_set"]["stories"] if item["id"] == story["id"])
    assert [int(item["id"]) for item in updated["sentences"]] == wider
    assert updated["end"] > story["end"]


def test_up_to_twelve_stories_from_a_long_source():
    scenes = make_scenes(400)
    document = clipset.build_clipset(scenes, transcript_for(scenes), 1600.0, count=12)
    assert document["requested"] == 12
    assert len(document["stories"]) == 12
    with pytest.raises(clipset.ClipSetError, match="3 to 12"):
        clipset.build_clipset(scenes, None, 1600.0, count=13)


@pytest.mark.parametrize("preset", sorted(clipset.LENGTH_PRESETS))
def test_length_presets_bound_every_story(preset):
    low, high = clipset.LENGTH_PRESETS[preset]
    scenes = make_scenes(300)
    document = clipset.build_clipset(
        scenes, transcript_for(scenes), 1200.0, count=6, min_s=low, max_s=high,
    )
    assert document["stories"]
    for story in document["stories"]:
        assert low - 0.01 <= story["dur"] <= high + 0.01


def test_lengths_outside_15_to_180_are_refused():
    scenes = make_scenes(60)
    with pytest.raises(clipset.ClipSetError):
        clipset.build_clipset(scenes, None, 240.0, min_s=10, max_s=30)
    with pytest.raises(clipset.ClipSetError):
        clipset.build_clipset(scenes, None, 240.0, min_s=30, max_s=185)


def _sentences(*texts: str) -> list[dict]:
    return [{"id": index, "text": text} for index, text in enumerate(texts)]


def test_housekeeping_and_dangling_openers_score_lower():
    clean, details = clipset._story_penalty(_sentences(
        "During a security test, AI agents found ways around their controls.",
        "That changed how the team built every guardrail.",
    ))
    assert clean == 1.0 and details["housekeeping"] == 0
    cta, _ = clipset._story_penalty(_sentences(
        "Congrats to Shelly, who won a free one-year membership.",
        "Tell me in the comments what you would do.",
    ))
    opener, info = clipset._story_penalty(_sentences(
        "And that is like discovering the concept car can drive itself.",
        "Nobody planned for it.",
    ))
    assert cta < 0.5
    assert info["dangling_opener"] is True and opener < 1.0


def test_a_giveaway_story_loses_to_an_equal_plain_one():
    scenes = make_scenes(40)
    for scene in scenes[:12]:
        scene["speech"] = "Subscribe and tell me in the comments for the giveaway."
    document = clipset.build_clipset(scenes, transcript_for(scenes), 160.0, count=3, order="score")
    first = document["stories"][0]
    assert first["penalties"]["housekeeping"] == 0
