"""Stable Clean tick identities, driven by Node Playwright on stubbed routes."""

from __future__ import annotations

from pathlib import Path

from classic_browser_harness import requirements, run_spec  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "tests" / "browser" / "classic_cut_ticks.spec.mjs"


def test_clean_ticks_stay_stable_across_manual_rows_and_reload(tmp_path):
    requirements(need_ffmpeg=False)
    data = tmp_path / "data"
    (data / "jobs").mkdir(parents=True)
    output = run_spec(
        SPEC, data, "j1", tmp_path, timeout=180, need_ffmpeg=False,
    )
    assert "ok cut-ticks 1440×900" in output
    assert "ok cut-ticks 1280×800" in output
