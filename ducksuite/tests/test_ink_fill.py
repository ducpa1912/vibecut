"""The fill hole of a scanned line is its own strokes, on its own frames."""

from __future__ import annotations

import numpy as np

from duckcore import ink, render
from duckcore.engine import textfill
from duckcore.engine.textfill import mask as masks

W, H, FPS = 320, 240, 30.0
META = {"width": W, "height": H, "fps": FPS, "duration": 4.0}


def _ink(first: int = 30, last: int = 59, late: int | None = None) -> ink.Ink:
    """Two glyphs at x 20..40 and 60..80 of a rect at (50, 90); the second may outlive the line."""
    mask = np.zeros((29, 119), dtype=bool)
    mask[5:25, 20:40:2] = True
    mask[5:25, 60:80:2] = True
    return ink.Ink(
        mask=mask, rect=(50, 90, 170, 120), first=first, last=last, fps=FPS,
        glyphs=((20, 39), (60, 79)),
        spans=((first, last), (first, late if late is not None else last)),
    )


def _layer(**extra) -> dict:
    return {
        "id": "cl_a", "kind": "fill", "enabled": True, "tracklet_id": "tr_a",
        "box": {"x": 60 / W, "y": 92 / H, "w": 100 / W, "h": 24 / H},
        "ranges": [{"start": 1.0, "end": 1.9}],
        "track": [{"t": 1.2, "box": {"x": 0.2, "y": 0.4, "w": 0.3, "h": 0.1}}],
        **extra,
    }


def test_a_scanned_line_gets_its_strokes_as_the_hole() -> None:
    layers, strokes = render._inked_layers([_layer()], {"cl_a": {"inks": [_ink()]}}, META)
    layer = layers[0]
    rect = tuple(layer["ink_rect"])
    assert masks.layer_rect(layer, W, H) == rect
    assert masks.layer_rects_at(layer, 1.5, W, H) == [rect]   # the box no longer follows a track
    pieces = strokes[rect]
    assert len(pieces) == 2
    covered = np.logical_or.reduce([hole for _first, _last, hole in pieces])
    assert covered.shape == (rect[3] - rect[1], rect[2] - rect[0])
    assert 0.3 < covered.mean() < 1.0      # strokes and a margin, not the whole box
    assert layer["ink_key"]


def test_the_range_is_widened_to_the_ink_and_never_narrowed() -> None:
    """Check said 1.0-1.9 s; the strokes are on frames 30..59 and one glyph until 74."""
    layers, _strokes = render._inked_layers(
        [_layer()], {"cl_a": {"inks": [_ink(late=74)]}}, META,
    )
    assert layers[0]["ranges"] == [{"start": round(29 / 30, 3), "end": round(76 / 30, 3)}]
    narrow, _strokes = render._inked_layers(
        [_layer(ranges=[{"start": 0.5, "end": 3.0}])], {"cl_a": {"inks": [_ink()]}}, META,
    )
    assert narrow[0]["ranges"] == [{"start": 0.5, "end": 3.0}]


def test_a_drawn_box_and_a_brushed_layer_stay_as_the_user_made_them() -> None:
    drawn = _layer(tracklet_id=None)
    brushed = _layer(mask={"strokes": [{"r": 0.02, "points": [{"x": 0.2, "y": 0.4}, {"x": 0.4, "y": 0.42}]}]})
    inks = {"cl_a": {"inks": [_ink()]}}
    for layer in (drawn, brushed):
        out, strokes = render._inked_layers([layer], inks, META)
        assert out == [layer] and strokes == {}


def test_a_layer_with_no_ink_keeps_the_old_hole() -> None:
    layer = _layer()
    out, strokes = render._inked_layers([layer], {"cl_a": {"inks": [], "reason": "none"}}, META)
    assert out == [layer] and strokes == {}


def test_the_hole_on_a_frame_is_the_glyphs_that_are_on_screen() -> None:
    layers, strokes = render._inked_layers(
        [_layer()], {"cl_a": {"inks": [_ink(late=74)]}}, META,
    )
    rect = tuple(layers[0]["ink_rect"])
    frame = np.zeros((H, W, 3), dtype=np.uint8)
    finder = masks.TextMasks([[rect]] * 90, [[]] * 90, W, H, strokes=strokes, base=0)
    for index in (20, 45, 70, 85):
        finder._measure(index, frame)
    assert finder.found[20] == [] and finder.found[85] == []
    both = finder.found[45][0][1]
    late = finder.found[70][0][1]
    assert both.sum() > late.sum() > 0
    middle = both.shape[1] // 2
    assert both[:, :middle].any() and not late[:, :middle].any()
    # ``base`` is the source frame of index 0: a clip that starts at frame 40.
    shifted = masks.TextMasks([[rect]] * 90, [[]] * 90, W, H, strokes=strokes, base=40)
    shifted._measure(5, frame)
    shifted._measure(40, frame)
    assert shifted.found[5][0][1].sum() == both.sum()
    assert shifted.found[40] == []


def test_the_strokes_are_part_of_the_clip_key() -> None:
    def key(layer: dict) -> str:
        return textfill.span_key(
            meta=META, start=0.0, duration=3.0, layers=[layer], method="lama", model_stamp="m",
        )

    plain = _layer()
    inked, _strokes = render._inked_layers([plain], {"cl_a": {"inks": [_ink()]}}, META)
    other, _strokes = render._inked_layers([plain], {"cl_a": {"inks": [_ink(last=58)]}}, META)
    assert len({key(plain), key(inked[0]), key(other[0])}) == 3


def test_a_hit_widens_the_layer_that_left_it() -> None:
    edit = {"clean": [_layer(), _layer(id="cl_b")]}
    hits = [{"layer": "cl_a", "time": 9.0, "source_time": 2.0}]
    wider = render._widen_edit(edit, hits, FPS)
    assert wider["clean"][0]["ranges"] == [
        {"start": 1.0, "end": 1.9}, {"start": round(2.0 - 2 / 30, 3), "end": 2.1},
    ]
    assert wider["clean"][1] == edit["clean"][1]
    assert edit["clean"][0]["ranges"] == [{"start": 1.0, "end": 1.9}]   # the saved edit is untouched
    inside = [{"layer": "cl_a", "time": 1.5, "source_time": 1.5}]
    assert render._widen_edit(edit, inside, FPS) is None


def test_something_crossing_the_text_stops_a_fill_being_reused() -> None:
    """A hand over a fifth of the picture barely moves the mean; it still ends the run."""
    hole = np.zeros((80, 240), dtype=bool)
    hole[30:50, 40:200] = True
    plate = np.full((80, 240, 3), 200, dtype=np.uint8)
    hand = plate.copy()
    hand[:, 150:200] = (120, 90, 70)
    drift = plate.copy()
    drift[:] = 205
    assert not textfill._picture_moved(plate, drift, ~hole, limit=30.0)
    assert float(np.abs(plate.astype(int) - hand.astype(int))[~hole].mean()) < 30.0
    assert textfill._picture_moved(plate, hand, ~hole, limit=30.0)


class _CountingFiller:
    """Fills the hole with the frame's own mean colour, so a stale fill shows."""

    def __init__(self) -> None:
        self.calls = 0

    def fill(self, crop: np.ndarray, hole: np.ndarray) -> np.ndarray:
        self.calls += 1
        out = crop.copy()
        out[hole] = crop[~hole].mean(axis=0).astype(np.uint8)
        return out


def test_no_fill_from_before_the_crossing_is_pasted_after_it() -> None:
    rect = (40, 30, 200, 50)
    frames = [np.full((80, 240, 3), 200, dtype=np.uint8) for _ in range(6)]
    for frame in frames[3:]:
        frame[:] = (90, 60, 40)          # the hand now covers the whole area
    filler = _CountingFiller()
    out = list(textfill.fill_frames_lama(
        iter(frames), lambda index: [rect], filler, None, step=6,
    ))
    assert len(out) == 6
    # Every frame after the crossing is filled from its own picture: nothing pale left.
    for frame in out[3:]:
        assert int(frame[30:50, 40:200].max()) < 120
    for frame in out[:3]:
        assert int(frame[30:50, 40:200].min()) > 180
