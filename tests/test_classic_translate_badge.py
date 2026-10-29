"""Classic shows translation progress and a ready flag before Rewrite."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_the_rewrite_step_carries_a_translation_badge():
    page = (ROOT / "static" / "classic" / "index.html").read_text(encoding="utf-8")
    assert 'id="translate-badge"' in page


def test_rewrite_waits_for_the_full_translation():
    script = (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    assert "/api/classic/jobs/${state.job.id}/translate" in script
    assert "/translate/status?target=" in script
    assert "async function ensureTranslation(controller)" in script
    assert "const translatedReady = await ensureTranslation(controller);" in script
    assert "Translating batch" in script
    assert "Translation ready · " in script


def test_the_badge_is_styled_by_status():
    css = (ROOT / "static" / "classic" / "style.css").read_text(encoding="utf-8")
    for status in ("ready", "running", "failed"):
        assert f'.translate-badge[data-status="{status}"]' in css
