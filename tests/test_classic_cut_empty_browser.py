"""Empty confirmed Check report renders from the first click."""

from __future__ import annotations

from pathlib import Path

from classic_browser_harness import requirements, run_spec  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "tests" / "browser" / "classic_cut_empty.spec.mjs"


def test_empty_confirmed_report_renders_on_first_click(tmp_path):
    requirements(need_ffmpeg=False)
    data = tmp_path / "data"
    (data / "jobs").mkdir(parents=True)
    output = run_spec(
        SPEC, data, "j1", tmp_path, timeout=200, need_ffmpeg=False,
    )
    assert "ok cut-empty 1440×900" in output
    assert "ok cut-empty 1280×800" in output
