"""Classic guard: a Clip Set with no stories does not claim stories exist."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_empty_clip_set_toast_is_truthful():
    script = (ROOT / "static" / "creator.js").read_text(encoding="utf-8")
    assert "const storyCount = state.clipset?.stories?.length || 0;" in script
    assert "no stories fit this source" in script
    assert "else {\n          toast(\"Clip Set built. Review the stories" in script
