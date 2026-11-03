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


def test_studio_build_serves_studio_classic_and_voice_room(monkeypatch):
    api = _client(monkeypatch)
    studio = api.get("/").text
    assert 'id="studio-root"' in studio and "/static/classic/" not in studio
    for path in ("/?classic=1", "/classic"):
        page = api.get(path).text
        assert "/static/classic/app.js" in page and 'id="studio-root"' not in page, path
    assert api.get("/voices").status_code == 200
    assert api.get("/static/classic/app.js").status_code == 200
    assert api.get("/static/studio/shell.js").status_code == 200


def test_a_saved_classic_choice_leaves_the_studio_page_once():
    page = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    boot = page[page.index("Studio is the only workspace here"):page.index("</script>", page.index("Studio is the only workspace here"))]
    # Studio owns this page. It does not redirect to Classic and keeps no
    # Classic editor choice; Classic lives on its own page.
    assert 'window.location.replace("/?classic=1")' not in boot
    assert 'root.dataset.editor = "studio"' in boot
    assert 'root.dataset.views = "studio"' in boot
    assert "vibecut.editor" not in page
    assert "/static/app.js" not in page and "/static/creator.js" not in page
