"""Classic guard: the batch form carries the own-footage tick.

Batches with the rights lock on used to return 409 from ``POST /api/batches``
while the Classic form had no way to confirm. The page, the script and the API
must agree on the ``rights`` field.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import app
import routes_batches
import settings_store

ROOT = Path(__file__).resolve().parents[1]


def test_classic_batch_form_has_no_attestation_tick():
    html = (ROOT / "static" / "classic" / "index.html").read_text(encoding="utf-8")
    assert 'id="batch-rights"' not in html
    assert "I own these videos or have the rights to them" not in html


def test_batch_api_accepts_no_tick_in_classic(monkeypatch, tmp_path):
    # Isolate the settings file: a shared test data folder would leave the
    # lock off for later rights tests that rely on the shipped default.
    monkeypatch.setenv("VIBECUT_EDITION", "classic")
    data = tmp_path / "settings"
    monkeypatch.setattr(settings_store, "DATA", data)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", data / "settings.json")
    monkeypatch.setattr(settings_store, "SECRETS_PATH", data / "secrets.json")
    seen: dict = {}

    class FakeManager:
        def create(self, name, items, max_items, start):
            seen["name"] = name
            seen["items"] = items
            assert start is False
            return {"id": "classicbatch1", "name": name}

        def start(self, batch_id):
            seen["started"] = batch_id
            return {"id": batch_id, "status": "running", "items": seen["items"]}

    monkeypatch.setattr(routes_batches, "_manager", lambda: FakeManager())
    settings_store.save_settings({"rights": {"lock": True}})

    client = TestClient(app.app)
    accepted = client.post(
        "/api/batches",
        json={"name": "no tick", "items": [{"path": "/tmp/classic-source.mp4"}], "max": 1},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["id"] == "classicbatch1"
