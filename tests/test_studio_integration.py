"""Studio embeds Classic and Voice Room: the edition-all build serves all three."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


def _client(monkeypatch, edition="all", features="voice_room"):
    monkeypatch.setenv("VIBECUT_EDITION", edition)
    monkeypatch.setenv("VIBECUT_FEATURES", features)
    import app

    return TestClient(app.app)


def test_studio_page_is_standalone_and_has_no_view_links():
    page = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert 'id="studio-root"' in page
    assert "/static/studio/shell.js" in page
    assert "/static/classic/" not in page
    assert 'href="/voices"' not in page
    assert 'data-editor="studio"' in page
    assert 'data-views="studio"' in page
    assert "VIBECUT_EDITION" not in page


def test_classic_page_keeps_its_own_edition_boot():
    page = (ROOT / "static" / "classic" / "index.html").read_text(encoding="utf-8")
    assert "<!-- vibecut:edition -->" in page
    assert "Choose the workspace before first paint" in page
    assert "/static/classic/app.js" in page
