"""Ink: which pixels are a line's strokes, and which frames show them."""

from __future__ import annotations

import numpy as np

from duckcore import ink

H, W, FPS = 40, 200, 30.0
RECT = (0, 0, W + 1, H + 1)


def _glyph(edges: np.ndarray, frames: slice, number: int) -> None:
    """A block of stroke edges 20 px wide; glyphs sit 30 px apart."""
    left = 10 + number * 30
    edges[frames, 10:30, left:left + 20:2] = True


def _window(count: int = 90, seed: int = 0) -> np.ndarray:
    """Edge maps of a moving picture: a few edges, never twice in one place."""
    rng = np.random.default_rng(seed)
    return rng.random((count, H, W)) < 0.03


def _build(edges: np.ndarray, core: tuple[int, int], first_index: int = 100) -> ink.Ink | None:
    return ink.analyse(edges, core, first_index=first_index, rect=RECT, fps=FPS)


def test_strokes_and_edges_are_found_on_a_moving_picture() -> None:
    edges = _window()
    for number in range(4):
        _glyph(edges, slice(30, 60), number)
    # The detected range is padded by three frames each side.
    built = _build(edges, (27, 62))
    assert built is not None
    assert (built.first, built.last) == (130, 159)
    assert len(built.glyphs) == 4
    assert built.settled
    assert built.mask[10:30, 10:30:2].all()
    assert built.pixels < 4 * 20 * 10 * 1.2


def test_scenery_that_was_there_before_and_after_is_not_ink() -> None:
    edges = _window(seed=1)
    for number in range(3):
        _glyph(edges, slice(30, 60), number)
    edges[:, 35, :] = True  # a plate rim on every frame of the window
    built = _build(edges, (30, 59))
    assert built is not None
    assert not built.mask[35].any()
    assert (built.first, built.last) == (130, 159)


def test_scenery_that_drifts_is_not_ink() -> None:
    """A rim that stays for the line and half a second around it, then moves on."""
    edges = _window(seed=2)
    for number in range(3):
        _glyph(edges, slice(30, 60), number)
    edges[15:75, 36, :] = True
    built = _build(edges, (30, 59))
    assert built is not None
    assert not built.mask[36].any()


def test_a_range_that_ends_early_keeps_its_ink_and_finds_the_real_end() -> None:
    """The old rule took text past the range for scenery and erased the ink."""
    edges = _window(seed=3)
    for number in range(4):
        _glyph(edges, slice(30, 70), number)
    built = _build(edges, (30, 55))  # the range stops 14 frames before the text does
    assert built is not None
    assert (built.first, built.last) == (130, 169)
    assert len(built.glyphs) == 4


def test_the_next_lines_text_is_not_taken_for_scenery() -> None:
    edges = _window(seed=4)
    for number in range(4):
        _glyph(edges, slice(30, 60), number)
    # The next line starts on the frame this one ends and reuses two glyph places.
    _glyph(edges, slice(60, 90), 1)
    _glyph(edges, slice(60, 90), 2)
    built = _build(edges, (30, 59))
    assert built is not None
    assert len(built.glyphs) == 4
    assert built.mask[10:30, 40:60:2].all()


def test_a_glyph_shared_with_the_next_line_lives_longer_than_the_line() -> None:
    """Three lines in a row end in "+1": those pixels show text the whole time."""
    edges = _window(seed=5)
    for number in range(3):
        _glyph(edges, slice(30, 50), number)
    _glyph(edges, slice(30, 80), 3)
    built = _build(edges, (30, 49))
    assert built is not None
    assert (built.first, built.last) == (130, 149)
    assert built.spans[3] == (130, 179)
    assert built.reach == (130, 179)
    assert built.settled
    alive_late = [first <= 170 <= last for first, last, _hole in built.pieces()]
    assert alive_late == [False, False, False, True]


def test_a_glyph_still_there_at_the_end_of_the_window_is_not_settled() -> None:
    edges = _window(seed=6)
    _glyph(edges, slice(30, 50), 0)
    _glyph(edges, slice(30, 90), 1)
    built = _build(edges, (30, 49))
    assert built is not None and not built.settled


def test_too_short_to_tell_text_from_scenery() -> None:
    edges = _window(seed=7)
    _glyph(edges, slice(30, 33), 0)
    assert _build(edges, (30, 32)) is None


def test_no_strokes_no_ink() -> None:
    assert _build(_window(seed=8), (30, 59)) is None


def test_hole_covers_the_strokes_and_a_margin() -> None:
    edges = _window(seed=9)
    _glyph(edges, slice(30, 60), 0)
    built = _build(edges, (30, 59))
    hole = built.hole(4)
    assert hole.shape == (H + 1, W + 1)
    assert hole[6:35, 6:34].all()
    assert not hole[:, 60:].any()


def test_glyph_columns_join_a_dot_to_its_neighbour() -> None:
    mask = np.zeros((30, 100), dtype=bool)
    mask[2:28, 10:30] = True
    mask[13:15, 36:38] = True   # a dot: too little ink to judge alone
    mask[2:28, 60:80] = True
    assert ink.glyph_columns(mask) == [(10, 38), (60, 80)]


def test_gradient_sees_a_dark_to_light_edge() -> None:
    picture = np.zeros((4, 4), dtype=np.uint8)
    picture[:, 2:] = 255
    assert ink.strong(picture)[:, 1].all()


def test_grow_and_box() -> None:
    mask = np.zeros((20, 30), dtype=bool)
    mask[8:12, 10:20] = True
    grown = ink.dilate(mask, 2)
    assert grown[6:14, 8:22].all() and grown.sum() == 8 * 14
    assert ink.bbox(grown) == (8, 6, 22, 14)
    assert ink.bbox(np.zeros((4, 4), bool)) is None


def test_first_frame_is_the_frame_at_or_after_a_time() -> None:
    assert ink.first_frame(93.625, 30.0) == 2809
    assert ink.first_frame(1.0, 30.0) == 30
    assert ink.first_frame(0.0, 30.0) == 0


def test_a_dense_line_is_cut_into_letter_sized_parts() -> None:
    """No gap between letters: one glyph 200 px wide and 20 tall is ten letters."""
    mask = np.zeros((40, 240), dtype=bool)
    mask[10:30, 20:220] = True
    mask[12:30, 103] = False        # a thin spot near an even cut is preferred
    parts = ink.glyph_columns(mask)
    assert len(parts) == 10
    assert parts[0][0] == 20 and parts[-1][1] == 220
    assert all(later[0] == earlier[1] for earlier, later in zip(parts, parts[1:]))
    assert all(14 <= b - a <= 26 for a, b in parts)
    assert (parts[3][1], parts[4][0]) == (103, 103)
