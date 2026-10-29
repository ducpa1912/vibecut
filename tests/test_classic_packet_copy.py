"""Classic guard: no-key packet copy does not cut words or use stop-word tags."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_short_title_cuts_at_a_word_boundary():
    script = (ROOT / "static" / "classic" / "creator.js").read_text(encoding="utf-8")
    assert "cut.lastIndexOf(\" \")" in script
    assert "base.trimEnd()}…" in script
    assert "text.slice(0, limit - 1).trimEnd()}…" not in script


def test_hashtags_skip_generic_stop_words():
    script = (ROOT / "static" / "classic" / "creator.js").read_text(encoding="utf-8")
    for word in ('"today"', '"want"', '"show"', '"plan"', '"week"'):
        assert word in script, word
