"""C1/C2 Clean editor, driven by Node Playwright on a fixture job.

Draws, moves, retags and deletes boxes on the real rendered frame, reloads to
prove the cut stored them, reads the found-text list (refusals included), the
locked AI-fill row, the key sheet and the Finish frame at 1280×720 and
1024×680.

It runs twice: once on a portrait source, where the crop is the whole frame and
frame space and source space coincide, and once on a 16:9 source, where they do
not. The second run is the one that proves a box is stored in source space —
the bug that made a box drawn on the output frame render nowhere.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pipeline")
pytest.importorskip("clipset")

from classic_browser_harness import (  # noqa: E402
    build_job,
    requirements,
    run_spec,
    write_source_video,
)

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "tests" / "browser" / "classic_clean.spec.mjs"

# 1920×1080 in 9:16 keeps source x 656..1264, so a box drawn at 12% of the
# frame starts at 0.341667 + 0.12 × 0.316667 of the source.
WIDE_SRC_X = 656 / 1920 + 0.12 * (608 / 1920)
WIDE_SRC_W = 0.76 * (608 / 1920)


def _run(tmp_path: Path, size: tuple[int, int], expect: dict[str, str]) -> str:
    source = tmp_path / "source.mp4"
    write_source_video(source, 24.0, size)
    data = tmp_path / "data"
    (data / "jobs").mkdir(parents=True)
    job_id = build_job(data, source, "j1", size)
    output = run_spec(SPEC, data, job_id, tmp_path, extra_env=expect)
    shots = sorted((tmp_path / "shots").glob("*.png"))
    assert len(shots) == 2, output
    return output


def test_clean_boxes_are_editable_on_the_real_frame(tmp_path):
    requirements()
    _run(tmp_path, (1080, 1920), {
        "CLASSIC_EXPECT_SRC_X": "0.12",
        "CLASSIC_EXPECT_SRC_W": "0.76",
    })


def test_a_box_on_a_cropped_source_is_stored_in_source_coordinates(tmp_path):
    requirements()
    data = tmp_path / "wide"
    data.mkdir()
    _run(data, (1920, 1080), {
        "CLASSIC_EXPECT_SRC_X": f"{WIDE_SRC_X:.6f}",
        "CLASSIC_EXPECT_SRC_W": f"{WIDE_SRC_W:.6f}",
    })
