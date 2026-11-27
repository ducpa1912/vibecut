"""Loop 4: run sizes LaMa accepts, and the safer default mask."""

from __future__ import annotations

import os

from duckcore.engine.textfill import text_mask_enabled
from duckcore.engine.textfill.lama import STEP, input_size


def test_run_sizes_are_multiples_of_sixteen() -> None:
    for height in range(64, 513, 7):
        for width in range(64, 513, 11):
            run_h, run_w = input_size(height, width, True)
            assert run_h % STEP == 0
            assert run_w % STEP == 0
            assert run_h >= height
            assert run_w >= width


def test_narrow_area_pads_without_a_ffc_broadcast_error() -> None:
    # A 164x160 text crop fitted to 512 kept a 504-pixel width under the old
    # 8-pixel step; the FFC skip joined 62 against 63 and ONNX raised.
    assert input_size(512, 500, True) == (512, 512)
    assert input_size(512, 504, True) == (512, 512)


def test_full_line_box_is_the_default_hole(monkeypatch) -> None:
    monkeypatch.delenv("VIBECUT_FILL_TEXT_MASK", raising=False)
    assert text_mask_enabled() is False
    monkeypatch.setenv("VIBECUT_FILL_TEXT_MASK", "1")
    assert text_mask_enabled() is True
