"""Phase 2 Source Clean UI, driven by Node Playwright on stubbed routes.

No media file is generated or committed: the spec serves the page through
uvicorn, stubs the extraction-only job, the Check report, the frame and the
Source Clean record, and proves the one-action rail at 1440×900 and 1280×800.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from classic_browser_harness import requirements, run_spec  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "tests" / "browser" / "classic_source_clean.spec.mjs"


def test_source_clean_one_action_rail_on_stubbed_routes(tmp_path):
    requirements(need_ffmpeg=False)
    data = tmp_path / "data"
    (data / "jobs").mkdir(parents=True)
    output = run_spec(
        SPEC, data, "j1", tmp_path, timeout=180, need_ffmpeg=False,
    )
    assert "ok source-clean 1440×900" in output
    assert "ok source-clean 1280×800" in output
