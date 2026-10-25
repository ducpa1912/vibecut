"""Admin authentication, keys, workflows, and audit tests."""

from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

import admin.catalog as catalog
import admin.store as store
import app
import settings_store


@pytest.fixture
def admin_api(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(settings_store, "DATA", data)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", data / "settings.json")
    monkeypatch.setattr(settings_store, "SECRETS_PATH", data / "secrets.json")
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "HOST", "127.0.0.1")
    for names in settings_store.ENV_KEYS.values():
        for env_name in names:
            monkeypatch.delenv(env_name, raising=False)
    api = TestClient(app.app)
    api.data_dir = data  # type: ignore[attr-defined]
    return api


def bootstrap(client):
    response = client.post(
        "/_ductator/api/bootstrap",
        json={"email": "admin@example.com", "password": "correct horse battery"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_admin_page_and_bootstrap(admin_api):
    page = admin_api.get("/_ductator/")
    assert page.status_code == 200
    assert "VibeCut" in page.text
    assert page.headers["x-robots-tag"] == "noindex, nofollow"
    state = admin_api.get("/_ductator/api/bootstrap").json()
    assert state == {"needed": True, "allowed": True}
    data = bootstrap(admin_api)
    assert data["email"] == "admin@example.com"
    assert data["csrf"]
    me = admin_api.get("/_ductator/api/me")
    assert me.status_code == 200
    assert me.json()["email"] == "admin@example.com"
    assert admin_api.get("/_ductator/api/bootstrap").json()["needed"] is False
    assert (admin_api.data_dir / "admin").stat().st_mode & 0o777 == 0o700
    assert (admin_api.data_dir / "admin" / "admin.sqlite3").stat().st_mode & 0o777 == 0o600


def test_admin_no_signup_or_second_bootstrap(admin_api):
    bootstrap(admin_api)
    response = admin_api.post(
        "/_ductator/api/bootstrap",
        json={"email": "other@example.com", "password": "correct horse battery"},
    )
    assert response.status_code == 409
    assert "signup" in response.json()["detail"].lower()


def test_admin_login_csrf_and_logout(admin_api):
    data = bootstrap(admin_api)
    admin_api.post("/_ductator/api/logout", headers={"X-VibeCut-Admin-CSRF": data["csrf"]})
    assert admin_api.get("/_ductator/api/me").status_code == 401
    login = admin_api.post(
        "/_ductator/api/login",
        json={"email": "admin@example.com", "password": "correct horse battery"},
    )
    assert login.status_code == 200
    csrf = login.json()["csrf"]
    bad = admin_api.post("/_ductator/api/keys/opencode", json={"value": "sk-secret"})
    assert bad.status_code == 403
    good = admin_api.post(
        "/_ductator/api/keys/opencode",
        json={"value": "sk-secret-opencode-key"},
        headers={"X-VibeCut-Admin-CSRF": csrf},
    )
    assert good.status_code == 200


def test_admin_key_masking_and_audit(admin_api):
    data = bootstrap(admin_api)
    secret = "sk-opencode-1234567890abcdef"
    response = admin_api.post(
        "/_ductator/api/keys/opencode",
        json={"value": secret},
        headers={"X-VibeCut-Admin-CSRF": data["csrf"]},
    )
    assert response.status_code == 200
    key = response.json()["key"]
    assert key["masked"] == "sk-op••••••••••bcdef"
    assert secret not in response.text
    keys = admin_api.get("/_ductator/api/keys")
    assert secret not in keys.text
    assert keys.status_code == 200
    audit = admin_api.get("/_ductator/api/audit")
    assert audit.status_code == 200
    assert any(item["action"] == "keys.update" for item in audit.json()["entries"])
    assert secret not in audit.text
    assert secret not in (admin_api.data_dir / "admin" / "admin.sqlite3").read_bytes().decode("latin1", "ignore")


def test_admin_workflow_save_and_catalog_validation(admin_api, monkeypatch):
    data = bootstrap(admin_api)
    monkeypatch.setattr(
        catalog,
        "catalog",
        lambda provider, refresh=False: {
            "provider": provider,
            "models": [
                {"id": "deepseek-v4.1-flash", "name": "DeepSeek"},
                {"id": "glm-5.3-flash", "name": "GLM"},
            ],
            "source": "test",
            "fetched_at": 1,
            "stale": False,
            "error": "",
        },
    )
    response = admin_api.post(
        "/_ductator/api/workflows/rewrite",
        json={
            "routes": [{"provider": "opencode-go", "model": "glm-5.3-flash"}],
            "reasoning": "medium",
            "max_output_tokens": 2048,
            "timeout_s": 120,
        },
        headers={"X-VibeCut-Admin-CSRF": data["csrf"]},
    )
    assert response.status_code == 200, response.text
    saved = response.json()["value"]
    assert saved["routes"] == [{"provider": "opencode-go", "model": "glm-5.3-flash"}]
    assert saved["reasoning"] == "medium"
    assert settings_store.load_settings()["workflows"]["rewrite"]["max_output_tokens"] == 2048
    invalid = admin_api.post(
        "/_ductator/api/workflows/rewrite",
        json={
            "routes": [{"provider": "opencode-go", "model": "not-in-catalog"}],
            "reasoning": "low",
            "max_output_tokens": 2048,
            "timeout_s": 120,
        },
        headers={"X-VibeCut-Admin-CSRF": data["csrf"]},
    )
    assert invalid.status_code == 400
    assert "not in the current" in invalid.json()["detail"]


def test_admin_pipeline_log(admin_api):
    bootstrap(admin_api)
    store.record_pipeline_event(
        "rewrite", "opencode-go", "deepseek-v4.1-flash",
        status="ok", latency_ms=12, input_tokens=4, output_tokens=8,
    )
    response = admin_api.get("/_ductator/api/pipeline")
    assert response.status_code == 200
    assert response.json()["entries"][0]["workflow"] == "rewrite"


def test_admin_audit_hash_chain_and_export(admin_api):
    data = bootstrap(admin_api)
    verified = admin_api.get("/_ductator/api/audit/verify")
    assert verified.status_code == 200
    assert verified.json()["ok"] is True
    exported = admin_api.get("/_ductator/api/audit/export")
    assert exported.status_code == 200
    assert "admin.bootstrap" in exported.text
    assert data["csrf"] not in exported.text


def test_admin_requires_login(admin_api):
    for path in ("/_ductator/api/keys", "/_ductator/api/workflows", "/_ductator/api/audit"):
        response = admin_api.get(path)
        assert response.status_code == 401


def test_admin_bootstrap_rejected_on_remote_bind(admin_api, monkeypatch):
    monkeypatch.setattr(app, "HOST", "0.0.0.0")
    state = admin_api.get("/_ductator/api/bootstrap").json()
    assert state == {"needed": True, "allowed": False}
    response = admin_api.post(
        "/_ductator/api/bootstrap",
        json={"email": "admin@example.com", "password": "correct horse battery"},
    )
    assert response.status_code == 403


def test_admin_account_email_and_password_change(admin_api):
    data = bootstrap(admin_api)
    response = admin_api.post(
        "/_ductator/api/account",
        json={
            "email": "owner@example.com",
            "current_password": "correct horse battery",
            "new_password": "a new long password",
        },
        headers={"X-VibeCut-Admin-CSRF": data["csrf"]},
    )
    assert response.status_code == 200
    assert response.json()["email"] == "owner@example.com"
    assert admin_api.get("/_ductator/api/me").json()["email"] == "owner@example.com"


def test_admin_audit_contains_redacted_setup_changes(admin_api):
    bootstrap(admin_api)
    response = admin_api.post(
        "/api/settings",
        json={"settings": {"stt": {"language": "vi"}}, "secrets": {"groq": "gsk-secret-value"}},
    )
    assert response.status_code == 200
    audit = admin_api.get("/_ductator/api/audit?limit=50").json()
    actions = {item["action"] for item in audit["entries"]}
    assert "settings.update" in actions
    assert "secrets.update" in actions
    assert "gsk-secret-value" not in admin_api.get("/_ductator/api/audit?limit=50").text


def test_admin_tts_route_updates_legacy_engine_settings(admin_api):
    data = bootstrap(admin_api)
    response = admin_api.post(
        "/_ductator/api/workflows/tts",
        json={
            "routes": [{"provider": "minimax", "model": "speech-2.8-turbo"}],
            "reasoning": "",
            "max_output_tokens": 0,
            "timeout_s": 120,
        },
        headers={"X-VibeCut-Admin-CSRF": data["csrf"]},
    )
    assert response.status_code == 200, response.text
    settings = settings_store.load_settings()
    assert settings["tts"]["provider"] == "minimax"
    assert settings["minimax"]["tts_model"] == "speech-2.8-turbo"
