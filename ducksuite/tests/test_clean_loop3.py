from __future__ import annotations

from duckcore.engine import pipeline
from duckcore.render import _blur_filter


META = {"width": 1000, "height": 1000, "fps": 24.0, "size": 100, "fingerprint": "test"}


def test_blur_filter_generates_gblur() -> None:
    edit = {
        "clean": [
            {
                "id": "cl_blur",
                "kind": "blur",
                "enabled": True,
                "box": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.1},
                "ranges": [{"start": 1.0, "end": 2.0}],
            }
        ]
    }
    value = _blur_filter(edit, META, clip_start=0.5, target_fps=24)
    assert "gblur" in value
    assert "overlay" in value
    assert "scale=" in value


def _blur_edit(*ranges):
    return {"clean": [{
        "id": "cl_blur", "kind": "blur", "enabled": True,
        "box": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.1},
        "ranges": [{"start": lo, "end": hi} for lo, hi in ranges],
    }]}


def test_blur_range_behind_the_clip_does_not_touch_its_first_frame() -> None:
    value = _blur_filter(_blur_edit((1.0, 2.0)), META, clip_start=8.0, target_fps=24)
    assert "gblur" not in value
    assert "between(t,0.000,0.000)" not in value
    assert _blur_filter(_blur_edit((1.0, 2.0)), META, clip_start=8.0, target_fps=24, at=8.0) == value


def test_blur_keeps_only_ranges_that_reach_the_clip() -> None:
    value = _blur_filter(_blur_edit((1.0, 2.0), (7.0, 9.0)), META, clip_start=8.0, target_fps=24)
    assert "between(t,0.000,1.000)" in value
    assert value.count("between(") == 1


def test_blur_filter_skips_fill_only() -> None:
    edit = {
        "clean": [
            {
                "id": "cl_fill",
                "kind": "fill",
                "enabled": True,
                "box": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.1},
            }
        ]
    }
    value = _blur_filter(edit, META, clip_start=0.0, target_fps=24)
    assert "gblur" not in value


def test_edge_text_line_maps_to_full_frame() -> None:
    record = {"text": []}
    line = {
        "text": "room",
        "confidence": 1.0,
        "box": {"x": 0.15, "y": 0.6, "w": 0.38, "h": 0.3},
    }
    pipeline._merge_ocr_line(record, line, crop_y0=0.5, crop_h=0.5)
    assert record["text"][0]["text"] == "room"
    assert record["text"][0]["box"]["y"] == 0.8
    assert record["text"][0]["box"]["h"] == 0.15


def test_edge_text_line_deduplicates() -> None:
    record = {
        "text": [
            {
                "text": "room",
                "confidence": 1.0,
                "box": {"x": 0.15, "y": 0.8, "w": 0.38, "h": 0.15},
            }
        ]
    }
    line = {
        "text": "room",
        "confidence": 1.0,
        "box": {"x": 0.15, "y": 0.6, "w": 0.38, "h": 0.3},
    }
    pipeline._merge_ocr_line(record, line, crop_y0=0.5, crop_h=0.5)
    assert len(record["text"]) == 1
