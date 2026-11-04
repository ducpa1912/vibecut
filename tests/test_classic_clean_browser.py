"""C1/C2 Clean editor, driven by Node Playwright on a fixture job.

Draws, moves, retags and deletes boxes on the real rendered frame, reloads to
prove the cut stored them, reads the found-text list (refusals included), the
locked AI-fill row, the key sheet and the Finish frame at 1280×720 and
1024×680.
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


def test_clean_boxes_are_editable_on_the_real_frame(tmp_path):
    requirements()
    source = tmp_path / "source.mp4"
    write_source_video(source, 24.0)
    data = tmp_path / "data"
    (data / "jobs").mkdir(parents=True)
    job_id = build_job(data, source, "j1")

    output = run_spec(SPEC, data, job_id, tmp_path)
    shots = sorted((tmp_path / "shots").glob("*.png"))
    assert len(shots) == 2, output
