"""Setup keys: one panel each for OpenRouter, MiniMax and ElevenLabs.

The key values are saved through the real settings route and must never come
back in the response.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
VOICE = ROOT / "static" / "voice"


def test_setup_saves_the_three_cloud_keys_without_returning_them():
    import app

    api = TestClient(app.app)
    for name in ("openrouter", "minimax", "elevenlabs"):
        saved = api.post("/api/settings", json={"secrets": {name: f"test-{name}-key"}})
        assert saved.status_code == 200, saved.text
        assert f"test-{name}-key" not in saved.text
    state = api.get("/api/settings").json()
    assert state["secrets"]["openrouter"] is True
    assert state["secrets"]["minimax"] is True
    assert state["secrets"]["elevenlabs"] is True
    assert "test-openrouter-key" not in str(state)
    assert state["sources"]["openrouter"] == "file"


def test_setup_has_three_key_panels_and_one_openrouter_row():
    text = (VOICE / "setup.js").read_text(encoding="utf-8")
    for name in ("openrouter", "minimax", "elevenlabs"):
        assert f'id: "{name}"' in text, name
    assert "One key; no per-model setup." in text
    # The OpenRouter voices are one row, not three setup rows.
    assert 'el("strong", { text: "OpenRouter voices" })' in text
    assert 'ENGINE_LABELS[id]' in text
    for label in ("Apple voices", "Kokoro", "MiniMax Speech", "ElevenLabs"):
        assert label in text, label


def test_setup_is_not_the_classic_setup_and_has_no_duplicate_model_picker():
    text = (VOICE / "setup.js").read_text(encoding="utf-8")
    assert "OpenRouter text model" not in text
    assert "OPENROUTER_TEXT_MODELS" not in text
    assert "OpenCode" not in text
    assert "readinessCard" not in text
    assert "This app's config" not in text
    # The library remains one place.
    assert "Download backup" in text
    assert "Restore backup" in text
    assert "Voice file" in text
