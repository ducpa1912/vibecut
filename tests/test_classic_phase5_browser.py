"""Phase 5 polish gate, driven by Node Playwright on stubbed routes.

No media file and no long-lived server: uvicorn is the harness's private
ephemeral process. The spec checks 1440/1280 desktop, the 1050/900 bottom
sheet, reduced motion, focus rings, the 11 px floor, Clean's entry frame and
clean-console normal flows for Source Clean and Cut Clean.
"""

from __future__ import annotations

from pathlib import Path

from classic_browser_harness import requirements, run_spec  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "tests" / "browser" / "classic_phase5.spec.mjs"


def test_phase5_polish_on_stubbed_routes(tmp_path):
    requirements(need_ffmpeg=False)
    data = tmp_path / "data"
    (data / "jobs").mkdir(parents=True)
    output = run_spec(SPEC, data, "j1", tmp_path, timeout=360, need_ffmpeg=False)
    for expected in (
        "ok phase5 source 1440×900",
        "ok phase5 source 1280×800",
        "ok phase5 source 1050×800",
        "ok phase5 source 900×800",
        "ok phase5 cut 1440×900",
        "ok phase5 cut 1280×800",
        "ok phase5 cut 1050×800",
        "ok phase5 cut 900×800",
    ):
        assert expected in output, output
