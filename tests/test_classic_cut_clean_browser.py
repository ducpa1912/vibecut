"""Phase 4 Cut Clean focus mode, driven by Node Playwright on stubbed routes.

No media file is generated: the spec serves the page through uvicorn, stubs a
ready cut, the Check report, the frame, the fill preview and the render record,
then proves Edit | Clean, one scan entry, auto ticks, outside-cut rows, the
one-action render and Download at 1440×900 and 1280×800.
"""

from __future__ import annotations

from pathlib import Path

from classic_browser_harness import requirements, run_spec  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "tests" / "browser" / "classic_cut_clean.spec.mjs"


def test_cut_clean_focus_mode_on_stubbed_routes(tmp_path):
    requirements(need_ffmpeg=False)
    data = tmp_path / "data"
    (data / "jobs").mkdir(parents=True)
    output = run_spec(
        SPEC, data, "j1", tmp_path, timeout=240, need_ffmpeg=False,
    )
    assert "ok cut-clean 1440×900" in output
    assert "ok cut-clean 1280×800" in output
