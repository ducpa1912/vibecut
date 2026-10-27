"""Closing payoffs and picks spread across the source (QA #13)."""

from __future__ import annotations

import clipset
from test_clipset import make_scenes


def _sentence(index: int, start: float, end: float, text: str) -> dict:
    return {
        "id": index,
        "start": start,
        "end": end,
        "dur": round(end - start, 3),
        "text": text,
        "scene": index,
        "scenes": [index],
        "source": "transcript",
    }


# ---------------------------------------------------------------- closing


def test_candidate_ends_prefer_a_closing_sentence():
    sentences = [
        _sentence(0, 0.0, 10.0, "The setup keeps going,"),
        _sentence(1, 10.0, 20.0, "The setup ends."),  # no pause before 2
        _sentence(2, 20.05, 30.0, "The payoff lands."),  # pause 1.0 before 3
        _sentence(3, 31.0, 40.0, "A last tag."),
    ]
    ends = clipset._candidate_end_indices(sentences, 0, 20.0, 75.0)
    assert ends == [2, 3]


def test_candidate_ends_fall_back_when_nothing_closes():
    sentences = [
        _sentence(0, 0.0, 10.0, "The setup keeps going,"),
        _sentence(1, 10.0, 20.0, "The setup ends."),  # terminal but no pause
        _sentence(2, 20.0, 30.0, "No punctuation here"),
        _sentence(3, 30.0, 40.0, "The end"),
    ]
    ends = clipset._candidate_end_indices(sentences, 0, 20.0, 75.0)
    assert ends == [1, 2, 3]


def test_closing_needs_punctuation_and_a_350ms_pause():
    short = [
        _sentence(0, 0.0, 10.0, "A complete line."),
        _sentence(1, 10.34, 20.0, "Next line."),
    ]
    long = [
        _sentence(0, 0.0, 10.0, "A complete line."),
        _sentence(1, 10.35, 20.0, "Next line."),
    ]
    no_punctuation = [
        _sentence(0, 0.0, 10.0, "A complete line"),
        _sentence(1, 11.0, 20.0, "Next line."),
    ]
    assert clipset._closing_sentence(short, 0) is False
    assert clipset._closing_sentence(long, 0) is True
    assert clipset._closing_sentence(no_punctuation, 0) is False


def test_a_closing_payoff_scores_above_a_plain_terminal_one():
    sentence = _sentence(0, 30.0, 40.0, "The result lands.")
    stats_closing = {0: {"terminal": True, "closing": True}}
    stats_plain = {0: {"terminal": True, "closing": False}}
    closing = clipset._payoff_signal([sentence], 40.0, 100.0, stats_closing)
    plain = clipset._payoff_signal([sentence], 40.0, 100.0, stats_plain)
    assert closing > plain


def test_story_carries_its_closing_payoff_flag():
    scenes = make_scenes(75)
    document = clipset.build_clipset(scenes, None, 300.0, count=3)
    assert document["stories"]
    for story in document["stories"]:
        assert isinstance(story["payoff_closing"], bool)


# ---------------------------------------------------------------- spread


def _candidate(story_id: str, start: float, end: float, base: float) -> dict:
    return {
        "id": story_id,
        "start": start,
        "end": end,
        "dur": round(end - start, 3),
        "sentences": [],
        "scenes": [],
        "_base_total": base,
    }


def test_spread_penalty_uses_a_15_percent_band():
    selected = [_candidate("near", 0.0, 20.0, 0.7)]
    close = _candidate("close", 20.5, 40.5, 0.8)  # centre 30.5
    edge = _candidate("edge", 100.0, 120.0, 0.8)  # centre 110 >= 15% of 600
    assert clipset._spread_penalty(close, selected, 600.0) > 0
    assert clipset._spread_penalty(edge, selected, 600.0) == 0


def test_selection_takes_the_spread_option_when_one_exists():
    selected = [_candidate("first", 0.0, 20.0, 0.7)]
    close = _candidate("close", 20.5, 40.5, 0.8)
    far = _candidate("far", 400.0, 420.0, 0.7)
    pick, _ = clipset._pick_best([close, far], selected, 600.0, 20.0, count=2)
    assert pick is far


def test_spread_penalty_relaxes_when_no_other_candidate_remains():
    selected = [_candidate("first", 0.0, 20.0, 0.7)]
    close = _candidate("close", 20.5, 40.5, 0.8)
    pick, _ = clipset._pick_best([close], selected, 600.0, 20.0, count=2)
    assert pick is close


def test_a_real_build_keeps_picks_apart_when_the_pool_allows():
    scenes = make_scenes(300)
    document = clipset.build_clipset(scenes, None, 1200.0, count=4)
    centres = sorted(
        (story["start"] + story["end"]) / 2.0 for story in document["stories"]
    )
    assert document["available"] == 4
    # The 15% band is 180 s on this source.
    assert max(b - a for a, b in zip(centres, centres[1:])) >= 180.0
