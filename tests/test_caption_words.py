"""Captions and story cuts follow measured word timings (QA #8).

QA found the first word of a sentence dropped ("Now," → "THAT DOESN'T…"),
words repeated across cue boundaries ("…HAS TO" / "TO LOOK…") and an SRT
sidecar holding speech from before the story with synthetic timing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import app
import captions
import clipset
import stt

# One Whisper segment holding two sentences. The second sentence starts on
# "Now," at 3.00 s, but a character-share split of 0–6 s guesses ~3.12 s,
# which is inside "Now," and cut it from the story.
SEGMENT_TEXT = "So I decided to build my own app. Now, that doesn't mean that."
WORDS = [
    ("So", 0.00, 0.20), ("I", 0.25, 0.35), ("decided", 0.40, 0.90),
    ("to", 0.95, 1.05), ("build", 1.10, 1.50), ("my", 1.55, 1.75),
    ("own", 1.80, 2.10), ("app.", 2.15, 2.70),
    ("Now,", 3.00, 3.30), ("that", 3.40, 3.70), ("doesn't", 3.75, 4.20),
    ("mean", 4.25, 4.60), ("that.", 4.65, 5.90),
]


def _word_rows(segment: int = 0) -> list[dict]:
    return [{"w": w, "start": s, "end": e, "segment": segment} for w, s, e in WORDS]


def _scene_index():
    return clipset._SceneIndex([{"id": 0, "start": 0.0, "end": 6.0}])


def test_sentence_edges_sit_on_word_edges():
    parts = clipset._timed_parts(
        SEGMENT_TEXT, 0.0, 6.0, 0, "transcript", _scene_index(),
        words=[{"w": w, "start": s, "end": e} for w, s, e in WORDS],
    )
    assert [part["text"] for part in parts] == [
        "So I decided to build my own app.", "Now, that doesn't mean that.",
    ]
    # The edge is just before "Now," and never inside "app.".
    assert parts[1]["start"] <= 3.0
    assert parts[1]["start"] >= 2.70
    assert parts[0]["end"] == parts[1]["start"]


def test_sentence_edges_without_words_keep_character_share():
    parts = clipset._timed_parts(SEGMENT_TEXT, 0.0, 6.0, 0, "transcript", _scene_index())
    share = 6.0 * len("So I decided to build my own app.") / (
        len("So I decided to build my own app.") + len("Now, that doesn't mean that.")
    )
    assert parts[1]["start"] == pytest.approx(round(share, 3))


def _segments() -> list[dict]:
    return [{
        "index": 0, "start": 0.0, "end": 6.0, "text": SEGMENT_TEXT,
        "words": [{"w": w, "start": s, "end": e} for w, s, e in WORDS],
    }]


def _texts(cues: list[dict]) -> list[str]:
    return " ".join(cue["text"].replace("\n", " ") for cue in cues).split()


def test_each_word_appears_once_across_adjacent_clips():
    # Two contiguous clips cut at 1.30 s, inside "build" (1.10–1.50).
    plan = {"clips": [
        {"scene": 0, "start": 0.0, "end": 1.3},
        {"scene": 0, "start": 1.3, "end": 2.8},
    ]}
    cues, source, _ = captions.build_cues(
        plan, style=captions.normalize_style({}), segments=_segments(),
    )
    assert source == "transcript"
    words = _texts(cues)
    assert words.count("build") == 1
    assert words == ["So", "I", "decided", "to", "build", "my", "own", "app."]


def test_story_starting_on_a_sentence_keeps_its_first_word():
    sentences = clipset._timed_parts(
        SEGMENT_TEXT, 0.0, 6.0, 0, "transcript", _scene_index(),
        words=[{"w": w, "start": s, "end": e} for w, s, e in WORDS],
    )
    second = sentences[1]
    plan = {"clips": [{"scene": 0, "start": second["start"], "end": second["end"]}]}
    cues, _, _ = captions.build_cues(
        plan, style=captions.normalize_style({}), segments=_segments(),
    )
    assert _texts(cues)[0] == "Now,"
    assert "app." not in _texts(cues)


def test_clip_with_no_heard_word_gets_no_guessed_text():
    plan = {"clips": [{"scene": 0, "start": 2.72, "end": 2.98}]}
    cues, _, warnings = captions.build_cues(
        plan, style=captions.normalize_style({}), segments=_segments(),
    )
    assert cues == []
    assert not any("fallback" in warning for warning in warnings)


def _write_v2(job_dir: Path) -> None:
    transcript = stt.build_transcript(
        engine="test", model="test", language="en",
        segments=[{"start": 0.0, "end": 6.0, "text": SEGMENT_TEXT}],
        words=_word_rows(), audio_duration=6.0, source_hash="x",
    )
    stt.save_transcript(job_dir, transcript)


def test_read_transcript_can_attach_words(tmp_path):
    _write_v2(tmp_path)
    plain = stt.read_transcript(tmp_path)
    assert "words" not in plain[0]
    timed = stt.read_transcript(tmp_path, words=True)
    assert [row["w"] for row in timed[0]["words"]][:2] == ["So", "I"]


def test_new_clip_sets_are_word_timed_and_old_ones_keep_text_timing(monkeypatch):
    calls = []

    def fake(job_dir, *, words=False):
        calls.append(words)
        return None

    monkeypatch.setattr(app.pipeline, "read_transcript", fake)
    job = {"id": "j1", "analysis": {"scenes": []}}
    app._clipset_sentences(job)
    app._clipset_sentences(job, {"sentence_timing": "words"})
    app._clipset_sentences(job, {"id": "cs_old"})
    assert calls == [True, True, False]


def test_build_clipset_records_its_sentence_timing():
    scenes = [{"id": 0, "start": 0.0, "end": 6.0}]
    timed = clipset.build_clipset(scenes, _segments(), 6.0)
    plain = clipset.build_clipset(
        scenes, [{"start": 0.0, "end": 6.0, "text": SEGMENT_TEXT}], 6.0,
    )
    assert timed["sentence_timing"] == "words"
    assert plain["sentence_timing"] == "text"


def test_sidecar_cues_come_from_the_cut_words(tmp_path, monkeypatch):
    jobs = tmp_path / "jobs"
    job_dir = jobs / "j1"
    job_dir.mkdir(parents=True)
    monkeypatch.setattr(app, "JOBS", jobs)
    _write_v2(job_dir)
    job = {
        "id": "j1",
        "source": {"duration": 6.0},
        "analysis": {"scenes": [
            {"id": 0, "start": 0.0, "end": 6.0, "speech": SEGMENT_TEXT},
        ]},
    }
    # The cut is the second sentence only, rendered from 0 s.
    cues = app._reel_cues(job, {"clips": [{"scene": 0, "start": 2.92, "end": 6.0}]})
    words = _texts(cues)
    assert words[0] == "Now," and "decided" not in words
    assert cues[0]["start"] >= 0.0 and cues[0]["start"] < 0.2
    assert cues[-1]["end"] <= 3.08 + 1e-6
    assert json.dumps(cues)
