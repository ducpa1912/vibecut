"""C2b AI fill, driven by Node Playwright with the model routes mocked.

The model pack is not installed on this Mac, so a browser run cannot fill a
real frame here. This spec mocks engine status and the LaMa preview and checks
the founder's path through them: tick a subtitle, remove it with AI fill, compare
one frame, and read the copy that says
the stage box is not the filled picture. The frame route stays real.
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
SPEC = ROOT / "tests" / "browser" / "classic_fill.spec.mjs"


def test_a_ready_machine_ticks_text_and_compares_one_frame(tmp_path):
    requirements()
    source = tmp_path / "source.mp4"
    write_source_video(source, 24.0, (1080, 1920))
    data = tmp_path / "data"
    (data / "jobs").mkdir(parents=True)
    job_id = build_job(data, source, "j1", (1080, 1920))
    output = run_spec(SPEC, data, job_id, tmp_path)
    assert "ok fill ready" in output, output
