"""Ink: text that sits still while the picture moves, and a steady plate."""

from __future__ import annotations

import numpy as np

from duckcore import ink


def _frames(count: int, height: int = 30, width: int = 60, seed: int = 0) -> np.ndarray:
    """A moving but smooth picture: shifts, never a hard edge."""
    rng = np.random.default_rng(seed)
    return (100 + rng.integers(0, 25, size=(count, height, width))).astype(np.uint8)


def _strokes(frames: np.ndarray, top: int = 10, bottom: int = 20,
             left: int = 20, right: int = 40) -> np.ndarray:
    """Alternating columns, so every pixel of the "text" has an edge."""
    frames[:, top:bottom, left:right] = 0
    frames[:, top:bottom, left:right:2] = 255
    return frames


def test_ink_is_the_text_not_the_moving_background() -> None:
    inside = _strokes(_frames(8, seed=1))
    outside = _frames(6, seed=2)
    mask = ink.ink_from(ink.strong(inside), ink.strong(outside))
    assert mask[10:20, 20:40].mean() > 0.8
    assert mask.sum() < mask.size * 0.35


def test_a_steady_plate_edge_is_not_ink() -> None:
    inside = _strokes(_frames(8, seed=3))
    inside[:, 25:27, :] = 0  # a rim across every frame
    outside = _frames(6, seed=4)
    outside[:, 25:27, :] = 0  # the same rim outside the line
    mask = ink.ink_from(ink.strong(inside), ink.strong(outside))
    assert mask[25:27, :].sum() == 0
    assert mask[10:20, 20:40].mean() > 0.8


def test_score_is_high_on_text_and_low_after_it() -> None:
    text = _strokes(_frames(4, seed=5))
    mask = ink.ink_from(ink.strong(text), None)
    assert float(ink.scores(ink.strong(text), mask).min()) > 0.9
    blank = np.full((4, 30, 60), 128, dtype=np.uint8)
    assert float(ink.scores(ink.strong(blank), mask).max()) < 0.2


def test_grow_and_box_cover_the_stroke() -> None:
    mask = np.zeros((20, 30), dtype=bool)
    mask[8:12, 10:20] = True
    grown = ink.dilate(mask, 2)
    assert grown[6:14, 8:22].all()
    assert ink.bbox(grown) == (8, 6, 22, 14)
    assert ink.bbox(np.zeros((4, 4), bool)) is None


def test_empty_ink_scores_zero() -> None:
    assert ink.scores(np.zeros((3, 5, 5), bool), np.zeros((5, 5), bool)).tolist() == [0.0, 0.0, 0.0]
