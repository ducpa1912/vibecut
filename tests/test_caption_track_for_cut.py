"""A story's own caption track survives the frame-rounded render cut."""

from __future__ import annotations

from pathlib import Path

import app
import captions as caption_engine


def _track(clips: list[dict]) -> caption_engine.CaptionTrack:
    return caption_engine.CaptionTrack.from_dict({
        "id": "cap_manualfix0001",
        "job_id": "j1",
        "version": 2,
        "target": 20,
        "clip_hash": caption_engine.clip_hash(clips),
        "cues": [
            {"id": "c1", "start": 0.5, "end": 2.0, "text": "Meet Nguyễn Thảo", "clip_index": 0},
            {"id": "c2", "start": 10.2, "end": 12.0, "text": "Second clip line", "clip_index": 1},
        ],
    })


def test_manual_text_is_kept_and_retimed_onto_the_rounded_cut(monkeypatch):
    raw = [
        {"start": 10.0, "end": 20.0, "duration": 10.0},
        {"start": 30.0, "end": 40.0, "duration": 10.0},
    ]
    # prepare_render rounds the first clip end to a frame boundary.
    prepared = [
        {"start": 10.0, "end": 19.967, "duration": 9.967},
        {"start": 30.0, "end": 40.0, "duration": 10.0},
    ]
    rebuilt = []
    monkeypatch.setattr(
        caption_engine, "build_track",
        lambda *args, **kwargs: rebuilt.append(True),
    )
    track = _track(raw)
    result = app._caption_track_for_cut(
        {"id": "j1"}, Path("."), track, raw,
        {"clips": prepared, "total": 19.967},
    )

    assert rebuilt == []
    assert [cue.text for cue in result.cues] == ["Meet Nguyễn Thảo", "Second clip line"]
    assert result.clip_hash == caption_engine.clip_hash(prepared)
    assert result.parent_id == track.id
    assert result.id != track.id
    assert abs(result.cues[1].start - (10.2 - 0.033)) < 0.01
