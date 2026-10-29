"""Classic guard: the hook-lab badge matches the server's rounded hook score."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_hook_scores_use_the_server_half_even_rounding():
    script = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    assert "function roundScoreHalfEven(value)" in script
    assert "roundScoreHalfEven(hook.hook)" in script
    assert "roundScoreHalfEven(safe)" in script
    assert "Math.round(hook.hook)" not in script
