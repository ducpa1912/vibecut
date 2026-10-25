"""Tests for the OCR candidate selection layer.

No Swift compilation or Apple Vision framework is required here.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import vision


def _candidate(text: str, confidence: float) -> dict[str, object]:
    return {"text": text, "confidence": confidence}


def test_custom_word_list_covers_required_overlay_brands() -> None:
    required = {
        "linktree", "linktr.ee", "instagram", "tiktok",
        "youtube", "rednote", "xiaohongshu",
    }
    assert required <= {word.casefold() for word in vision.CUSTOM_WORDS}
    assert len(vision.CUSTOM_WORDS) <= 12


def test_correct_ocr_text_normalizes_spacing_and_letter_spaced_caps() -> None:
    assert vision.correct_ocr_text("  hello   world  ") == "hello world"
    assert vision.correct_ocr_text("L I N K T R E E") == "LINKTREE"
    assert vision.correct_ocr_text("S A L E 50%") == "SALE 50%"
    assert vision.correct_ocr_text("小红书") == "小红书"


def test_choose_prefers_linktree_candidate_over_unaree() -> None:
    candidates = [
        _candidate("UNAREE", 0.54),
        _candidate("LINKTREE", 0.41),
        _candidate("LINK TREE", 0.22),
    ]
    assert vision.choose_ocr_candidate(candidates, original="UNAREE") == "LINKTREE"


def test_choose_handles_letter_spaced_brand_candidate() -> None:
    candidates = [
        _candidate("UNAREE", 0.55),
        _candidate("L I N K T R E E", 0.36),
    ]
    assert vision.choose_ocr_candidate(candidates, original="UNAREE") == "LINKTREE"


def test_choose_rejects_low_confidence_brand_candidate() -> None:
    candidates = [
        _candidate("UNAREE", 0.80),
        _candidate("LINKTREE", 0.29),
    ]
    assert vision.choose_ocr_candidate(candidates, original="UNAREE") == "UNAREE"


def test_choose_preserves_original_when_no_safe_correction_exists() -> None:
    candidates = [
        _candidate("SALE 50%", 0.86),
        _candidate("SALE 5O%", 0.42),
        _candidate("SALE SO%", 0.31),
    ]
    assert vision.choose_ocr_candidate(candidates, original="SALE 50%") == "SALE 50%"


def test_choose_never_invents_a_brand_not_in_candidates() -> None:
    candidates = [_candidate("UNAREE", 0.47)]
    assert vision.choose_ocr_candidate(candidates, original="UNAREE") == "UNAREE"


def test_choose_does_not_swap_an_existing_brand_reading() -> None:
    candidates = [
        _candidate("TikTok", 0.60),
        _candidate("LINKTREE", 0.70),
    ]
    assert vision.choose_ocr_candidate(candidates, original="TikTok") == "TikTok"


def test_choose_accepts_confident_url_candidate() -> None:
    candidates = [
        _candidate("LINKTR EE", 0.46),
        _candidate("linktr.ee", 0.34),
    ]
    assert vision.choose_ocr_candidate(candidates, original="LINKTR EE") == "linktr.ee"


def test_choose_preserves_chinese_text() -> None:
    candidates = [
        _candidate("小红书", 0.78),
        _candidate("小红书号", 0.40),
    ]
    assert vision.choose_ocr_candidate(candidates, original="小红书") == "小红书"


def test_probe_images_applies_correction_and_keeps_line_shape(tmp_path, monkeypatch) -> None:
    frame = tmp_path / "00001.jpg"
    frame.write_bytes(b"not-a-real-jpeg")

    record = {
        "file": frame.name,
        "width": 720,
        "height": 1280,
        "text": [
            {
                "text": "UNAREE",
                "confidence": 0.42,
                "y": 0.31,
                "candidates": [
                    _candidate("UNAREE", 0.42),
                    _candidate("LINKTREE", 0.38),
                ],
                "box": {"x": 0.2, "y": 0.28, "w": 0.4, "h": 0.08},
            }
        ],
        "faces": [],
        "salient": [],
    }
    completed = SimpleNamespace(returncode=0, stdout=json.dumps(record) + "\n", stderr="")

    monkeypatch.setattr(vision, "_build", lambda: True)
    monkeypatch.setattr(vision.subprocess, "run", lambda *args, **kwargs: completed)

    result = vision.probe_images(tmp_path)

    record_result = result[frame.name]
    assert set(record_result) >= {"text", "faces", "salient", "width", "height"}
    line = record_result["text"][0]
    assert set(line) >= {"text", "confidence", "y", "candidates", "box"}
    assert line["text"] == "LINKTREE"
    assert line["original_text"] == "UNAREE"
    assert line["confidence"] == 0.42
    assert line["box"] == {"x": 0.2, "y": 0.28, "w": 0.4, "h": 0.08}
    assert line["candidates"][1]["text"] == "LINKTREE"
