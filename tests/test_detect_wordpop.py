"""Word-pop captions are cleanable subtitles; OCR junk is dropped (QA #15)."""

from __future__ import annotations

import detect


def _tracklet(text: str, box: dict, **extra) -> dict:
    return {
        "box": box, "text_sample": text, "samples": 1, "duration": 1.0,
        "_texts": [(0.0, text)], "screen_frame": False, **extra,
    }


def test_mid_frame_word_pop_is_a_subtitle_even_over_a_screen_recording():
    box = {"x": 0.38, "y": 0.55, "w": 0.24, "h": 0.05}
    for text in ("BUILD MY", "OWN", "creator"):
        kind, _rule = detect.classify(_tracklet(text, box, screen_frame=True), 53.0)
        assert kind == "subtitle", text


def test_small_ui_labels_stay_screen_text():
    kind, _ = detect.classify(_tracklet("SETTINGS", {"x": 0.4, "y": 0.55, "w": 0.12, "h": 0.02}), 53.0)
    assert kind == "screen_text"
    kind, _ = detect.classify(_tracklet("Open the File menu and pick Export", {
        "x": 0.2, "y": 0.5, "w": 0.6, "h": 0.03,
    }, screen_frame=True), 53.0)
    assert kind == "screen_text"


def test_ocr_junk_is_dropped_and_words_are_kept():
    assert detect.ocr_line_is_junk("^9UM.", 0.45)
    assert detect.ocr_line_is_junk("OII8C", 0.5)
    assert detect.ocr_line_is_junk("4HIH}", 0.55)
    assert detect.ocr_line_is_junk("anything", 0.3)
    assert not detect.ocr_line_is_junk("PROFITABLE EXIT!", 0.5)
    assert not detect.ocr_line_is_junk("my attention", 0.45)
    assert not detect.ocr_line_is_junk("进日成分", 0.5)
    assert not detect.ocr_line_is_junk("OII8C", 0.9)


def test_merge_lines_skips_junk_reads():
    lines = [
        {"text": "OII8C", "confidence": 0.5, "box": {"x": 0.1, "y": 0.1, "w": 0.1, "h": 0.03}},
        {"text": "Real words here", "confidence": 0.5, "box": {"x": 0.1, "y": 0.6, "w": 0.4, "h": 0.04}},
    ]
    blocks = detect.merge_lines(lines, start=0.0, end=1.0, source="vision")
    assert [block["text"] for block in blocks] == ["Real words here"]
