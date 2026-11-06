"""Classic Clean flow setting: review first by default, one click optional."""

from __future__ import annotations

from fastapi.testclient import TestClient

import app
import settings_store


def _isolate(monkeypatch, tmp_path):
    data = tmp_path / "settings"
    monkeypatch.setattr(settings_store, "DATA", data)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", data / "settings.json")
    monkeypatch.setattr(settings_store, "SECRETS_PATH", data / "secrets.json")


def test_clean_flow_defaults_to_review_first():
    assert settings_store.DEFAULTS["classic_clean"] == {"flow": "review_first"}


def test_clean_flow_accepts_only_its_two_modes():
    normalize = settings_store._normalize_classic_clean
    assert normalize({"flow": "review_first"}) == {"flow": "review_first"}
    assert normalize({"flow": "one_click"}) == {"flow": "one_click"}
    assert normalize({"flow": "ONE_CLICK"}) == {"flow": "one_click"}
    for bad in ({"flow": "automatic"}, {"flow": ""}, {}, None, "one_click"):
        assert normalize(bad) == {"flow": "review_first"}


def test_clean_flow_survives_load_and_save(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    assert settings_store.load_settings()["classic_clean"] == {"flow": "review_first"}

    settings_store.save_settings({"classic_clean": {"flow": "one_click"}})
    assert settings_store.load_settings()["classic_clean"] == {"flow": "one_click"}

    settings_store.save_settings({"classic_clean": {"flow": "not-a-mode"}})
    assert settings_store.load_settings()["classic_clean"] == {"flow": "review_first"}


def test_settings_api_accepts_the_clean_flow(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(app.admin_store, "record_audit", lambda *args, **kwargs: None)
    response = TestClient(app.app).post(
        "/api/settings", json={"settings": {"classic_clean": {"flow": "one_click"}}},
    )
    assert response.status_code == 200, response.text
    assert response.json()["settings"]["classic_clean"] == {"flow": "one_click"}
