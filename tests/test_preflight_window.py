"""Preflight lists only text inside the story, at story time (QA #17)."""

from __future__ import annotations

import json

import detect
import preflight


def _report(job_dir, tracklets):
    folder = job_dir / detect.REPORT_DIR
    folder.mkdir(parents=True, exist_ok=True)
    (folder / detect.REPORT_FILE).write_text(json.dumps({
        "status": "ready", "complete": True, "tracklets": tracklets,
    }))


def _tracklet(text, start, end):
    return {
        "kind": "subtitle", "text_sample": text,
        "box": {"x": 0.1, "y": 0.8, "w": 0.8, "h": 0.08},
        "ranges": [{"start": start, "end": end}],
    }


def test_only_text_inside_the_story_is_listed_at_story_time(tmp_path):
    _report(tmp_path, [
        _tracklet("PROFITABLE EXIT!", 27.0, 30.0),  # after the story
        _tracklet("Inside the cut", 12.0, 14.0),
    ])
    # The story is source 10-21 s, rendered from 0 s.
    compiled = {"segments": [{"start": 10.0, "end": 21.0, "out_start": 0.0}]}
    markers = preflight.uncovered_text_markers(tmp_path, {"clean": []}, compiled, 11.0)
    assert len(markers) == 1
    marker = markers[0]
    assert "Inside the cut" in marker["message"]
    assert abs(marker["t"] - 2.0) < 1e-6 and abs(marker["end"] - 4.0) < 1e-6
