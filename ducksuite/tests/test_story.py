from __future__ import annotations

import re

import pytest

from duckcore import story

SCENES = [
    {"id": index, "start": index * 5.0, "end": (index + 1) * 5.0}
    for index in range(6)
]
LINES = [
    "I lost my job in March and started cooking for strangers.",
    "At first nobody came and I nearly gave up on the whole thing.",
    "Then one video about a five dollar lunch changed everything.",
    "I made a hundred meals in a week with two hands and one stove.",
    "The shop offered me a counter and I said yes before I could think.",
    "Now I feed forty people a day and the rent is paid.",
]
TRANSCRIPT = {
    "segments": [
        {"start": scene["start"], "end": scene["end"], "text": line}
        for scene, line in zip(SCENES, LINES)
    ]
}
CHECK = {"scenes": SCENES}


def all_text() -> str:
    return " ".join(LINES)


def test_context_is_one_row_per_spoken_scene_and_keeps_a_verbatim_cue() -> None:
    rows = story.scene_context(CHECK, TRANSCRIPT)
    assert [row["id"] for row in rows] == [0, 1, 2, 3, 4, 5]
    for row in rows:
        assert row["cue"] in all_text()


def test_fallback_is_traceable_and_inside_the_story_window() -> None:
    result = story.fallback_story(story.scene_context(CHECK, TRANSCRIPT), 4)
    assert result["model"] == "none"
    assert story.MIN_BEATS <= len(result["beats"]) <= story.MAX_BEATS
    assert story.MIN_RUNTIME <= result["runtime"] <= story.MAX_RUNTIME
    assert len({beat["scene_id"] for beat in result["beats"]}) == len(result["beats"])
    for beat in result["beats"]:
        assert beat["cue"] in all_text()


def test_model_order_is_kept_even_when_it_is_not_chronological() -> None:
    def model(_payload: dict) -> dict:
        return {
            "thesis": "A five dollar lunch rebuilt a life.",
            "beats": [
                {"id": 2, "reason": "the turn"},
                {"id": 0, "reason": "the setup"},
                {"id": 5, "reason": "the payoff"},
            ],
        }
    result = story.write_story(CHECK, TRANSCRIPT, model=model)
    assert result["model"] == "apple"
    assert result["scene_ids"] == [2, 0, 5]
    assert result["thesis"] == "A five dollar lunch rebuilt a life."
    for beat in result["beats"]:
        assert beat["cue"] in all_text()


def test_bad_model_answer_falls_back() -> None:
    def model(_payload: dict) -> dict:
        return {"thesis": "x", "beats": [{"id": 99}, {"id": 0}]}
    result = story.write_story(CHECK, TRANSCRIPT, model=model)
    assert result["model"] == "none"
    assert result["reason"]


def test_a_long_source_is_batched_before_the_reduce() -> None:
    scenes = [{"id": index, "start": index * 5.0, "end": (index + 1) * 5.0} for index in range(200)]
    lines = [
        f"Line number {index} about the same long day, told at length so the prompt needs a batch split."
        for index in range(200)
    ]
    transcript = {"segments": [
        {"start": scene["start"], "end": scene["end"], "text": line}
        for scene, line in zip(scenes, lines)
    ]}
    sizes: list[int] = []

    def model(payload: dict) -> dict:
        sizes.append(len(payload["scenes"]))
        if "batch" in payload:
            return {"theme": "a batch", "ids": [payload["scenes"][0]["id"]]}
        ids = [row["id"] for row in payload["scenes"][:3]]
        return {"thesis": "One long day.", "beats": [{"id": value, "reason": "pick"} for value in ids]}

    result = story.write_story({"scenes": scenes}, transcript, model=model)
    assert max(sizes) <= story.BATCH_SIZE
    assert result["model"] == "apple"
    assert result["runtime"] == pytest.approx(15.0)


def test_no_speech_is_an_error() -> None:
    with pytest.raises(story.StoryError):
        story.write_story({"scenes": SCENES}, {"segments": []})
