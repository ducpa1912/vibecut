"""Phase 2 gate states in a real browser, on stubbed routes and no media.

Covers the long-video second click, unconfirmed OCR, no text, scan cancel,
failed scan, cancelled render, ready-with-missing-file and the ready cut route.
"""

from __future__ import annotations

from pathlib import Path

from classic_browser_harness import requirements, run_spec  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "tests" / "browser" / "classic_source_clean_gates.spec.mjs"


def test_source_clean_gate_states_in_a_real_browser(tmp_path):
    requirements(need_ffmpeg=False)
    data = tmp_path / "data"
    (data / "jobs").mkdir(parents=True)
    output = run_spec(
        SPEC, data, "gates", tmp_path, timeout=240, need_ffmpeg=False,
    )
    for marker in (
        "ok gates long-video",
        "ok gates unconfirmed",
        "ok gates no-text",
        "ok gates scan-cancel",
        "ok gates failed-scan",
        "ok gates cancel-cancelling",
        "ok gates missing-media",
        "ok gates failed-clean-back",
        "ok gates back-cancel",
        "ok gates idle-envelope",
        "ok gates blur-long",
        "ok gates source-to-cut",
        "ok gates ready-cut",
    ):
        assert marker in output, output
