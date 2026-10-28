"""Caption reflow after a story range change.

Pure unit tests: no network, no packs, no renders. The transcript is a small
JSON fixture and every track is a local sidecar under ``tmp_path``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import caption_reflow
import captions as caption_engine


SENTENCES = [
    (0.0, 4.0, "Sentence zero about the build."),
    (4.0, 8.0, "Sentence one about the edit."),
    (8.0, 12.0, "Sentence two about the trim."),
    (12.0, 16.0, "Sentence three about the render."),
]


def clip(scene: int, start: float, end: float, role: str = "beat") -> dict:
    return {
        "scene": scene,
        "start": float(start),
        "end": float(end),
        "dur": round(float(end) - float(start), 3),
        "role": role,
    }


def story(story_id: str, first: int, last: int) -> dict:
    """Story showing sentences ``first``..``last`` inclusive."""
    clips = [clip(index, start, end) for index, (start, end, _) in enumerate(SENTENCES)]
    chosen = clips[first:last + 1]
    if chosen:
        chosen[0] = {**chosen[0], "role": "hook"}
        chosen[-1] = {**chosen[-1], "role": "payoff"}
    total = round(sum(item["dur"] for item in chosen), 3)
    return {
        "id": story_id,
        "clips": chosen,
        "dur": total,
        "start": chosen[0]["start"] if chosen else 0.0,
        "end": chosen[-1]["end"] if chosen else 0.0,
    }


def segments() -> list[dict]:
    return [
        {"index": index, "start": start, "end": end, "text": text}
        for index, (start, end, text) in enumerate(SENTENCES)
    ]


@pytest.fixture
def job_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "jobs" / "j1"
    (directory / "transcript").mkdir(parents=True)
    (directory / "transcript" / "transcript.json").write_text(
        json.dumps({"segments": segments()}), encoding="utf-8",
    )
    return directory


def style() -> dict:
    return caption_engine.normalize_style({}, style_id="clean")


def old_track(job_dir: Path, value: dict, style_value: dict | None = None):
    plan = {"target": int(round(value["dur"])), "clips": value["clips"]}
    track = caption_engine.build_track(
        {"id": "j1", "source": {"duration": 16.0}},
        plan,
        style_value or style(),
        segments=segments(),
        job_dir=None,
    )
    caption_engine.save_track(job_dir, track)
    return track


def manual_track(job_dir: Path, track, clip_index: int, text: str):
    cues = [cue.to_dict() for cue in track.cues]
    target = next(
        cue for cue in cues if int(cue["clip_index"]) == clip_index
    )
    target["text"] = text
    edited, changed = caption_engine.edit_track(
        track,
        cues=cues,
        clips=track.clip_windows,
        total=track.target,
        job_dir=None,
    )
    assert changed
    caption_engine.save_track(job_dir, edited)
    return edited


def reflow(job_dir: Path, old_story: dict, new_story: dict, track_id: str | None):
    return caption_reflow.rebuild_for_story(
        "j1",
        {"id": "j1", "source": {"duration": 16.0}},
        "set1",
        old_story,
        new_story,
        track_id,
        job_dir=job_dir,
    )


def test_start_trim_maps_cues_and_drops_the_removed_sentence(job_dir: Path):
    old = story("st_old", 0, 2)
    new = story("st_new", 1, 2)
    track = old_track(job_dir, old)

    result = reflow(job_dir, old, new, track.id)

    assert result.counts["dropped"] >= 1
    assert result.counts["moved"] >= 1
    assert result.counts["kept"] == 0
    assert result.counts["added"] == 0
    assert result.track.clip_hash == caption_engine.clip_hash(new["clips"])
    assert result.track.parent_id == track.id
    assert result.track.version == track.version + 1
    assert all(0.0 <= cue.start < cue.end <= new["dur"] + 0.001 for cue in result.track.cues)
    text = " ".join(cue.text for cue in result.track.cues).lower()
    assert "sentence zero" not in text
    assert "sentence one" in text


def test_end_trim_drops_the_tail_and_keeps_the_opening(job_dir: Path):
    old = story("st_old", 0, 2)
    new = story("st_new", 0, 1)
    track = old_track(job_dir, old)

    result = reflow(job_dir, old, new, track.id)

    assert result.counts["kept"] >= 1
    assert result.counts["dropped"] >= 1
    assert result.counts["added"] == 0
    assert all(cue.end <= new["dur"] + 0.001 for cue in result.track.cues)
    text = " ".join(cue.text for cue in result.track.cues).lower()
    assert "sentence two" not in text


def test_extending_the_start_adds_transcript_cues(job_dir: Path):
    old = story("st_old", 1, 2)
    new = story("st_new", 0, 2)
    track = old_track(job_dir, old)

    result = reflow(job_dir, old, new, track.id)

    assert result.counts["added"] >= 1
    assert result.counts["dropped"] == 0
    text = " ".join(cue.text for cue in result.track.cues).lower()
    assert "sentence zero" in text
    assert result.track.clip_hash == caption_engine.clip_hash(new["clips"])
    first = min(result.track.cues, key=lambda cue: cue.start)
    assert first.start < 4.0


def test_a_cue_clipped_at_the_new_edge_keeps_its_text(job_dir: Path):
    old = story("st_old", 0, 1)
    new = story("st_new", 0, 1)
    new["clips"] = [clip(0, 2.0, 4.0, "hook"), clip(1, 4.0, 8.0, "payoff")]
    new["dur"] = 6.0
    track = manual_track(job_dir, old_track(job_dir, old), 0, "Manual line here")

    result = reflow(job_dir, old, new, track.id)

    clipped = [cue for cue in result.track.cues if cue.text == "Manual line here"]
    assert clipped
    assert result.counts["moved"] >= 1
    assert result.counts["dropped"] == 0
    assert clipped[0].start == 0.0
    assert clipped[0].end <= 2.0 + 0.001


def test_manual_text_survives_a_trim_and_is_counted(job_dir: Path):
    old = story("st_old", 0, 2)
    new = story("st_new", 1, 2)
    track = manual_track(
        job_dir, old_track(job_dir, old), 1, "John said the edit.",
    )

    result = reflow(job_dir, old, new, track.id)

    texts = [cue.text for cue in result.track.cues]
    assert "John said the edit." in texts
    assert result.counts["manual_kept"] == 1


def test_no_old_track_builds_the_whole_story_from_the_transcript(job_dir: Path):
    new = story("st_new", 0, 1)

    result = reflow(job_dir, {}, new, None)

    assert result.counts["added"] == len(result.track.cues) > 0
    assert result.counts["kept"] == 0
    assert result.track.parent_id is None
    assert result.track.version == 1
    assert result.track.clip_hash == caption_engine.clip_hash(new["clips"])


def test_a_missing_old_track_raises(job_dir: Path):
    old = story("st_old", 0, 2)
    new = story("st_new", 1, 2)

    with pytest.raises(caption_reflow.ReflowError):
        reflow(job_dir, old, new, "cap_missing")


def test_a_new_story_without_clips_raises(job_dir: Path):
    old = story("st_old", 0, 2)
    with pytest.raises(caption_reflow.ReflowError):
        reflow(job_dir, old, {"id": "st_new", "clips": []}, None)


def test_save_writes_the_sidecar_and_returns_the_id(job_dir: Path):
    old = story("st_old", 0, 2)
    new = story("st_new", 1, 2)
    result = reflow(job_dir, old, new, old_track(job_dir, old).id)

    saved = result.save(job_dir)

    assert saved == result.track.id == result.track_id
    loaded = caption_engine.load_track(job_dir, saved)
    assert loaded is not None
    assert loaded.cue_hash == result.track.cue_hash
    assert loaded.clip_hash == result.track.clip_hash


def test_added_cues_use_the_old_track_style(job_dir: Path):
    old = story("st_old", 1, 2)
    new = story("st_new", 0, 2)
    bold = caption_engine.normalize_style(
        {"uppercase": True, "max_chars": 22, "max_lines": 2}, style_id="bold",
    )
    track = old_track(job_dir, old, bold)

    result = reflow(job_dir, old, new, track.id)

    added = [cue for cue in result.track.cues if cue.start < 4.0]
    assert added
    assert all(cue.text == cue.text.upper() for cue in added)
    assert result.track.style_id == "bold"
    assert result.track.style["uppercase"] is True
