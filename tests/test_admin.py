"""Admin authentication, keys, workflows, and audit tests."""

from __future__ import annotations

import hashlib
import json
import time

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
    import admin.routes as admin_routes
    import audio
    monkeypatch.setattr(audio, "CACHE", data / "cache")
    admin_routes._ATTEMPTS.clear()
    for names in settings_store.ENV_KEYS.values():
        for env_name in names:
            monkeypatch.delenv(env_name, raising=False)
    monkeypatch.delenv("VIBECUT_TOKEN", raising=False)
    api = TestClient(
        app.app, base_url="http://127.0.0.1",
        client=("127.0.0.1", 50000),
    )
    api.data_dir = data  # type: ignore[attr-defined]
    yield api
    admin_routes._ATTEMPTS.clear()


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
    assert "text model in the current" in invalid.json()["detail"]


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


# ---------------------------------------------------------------- security regressions


def test_bootstrap_requires_local_client_and_safe_headers(admin_api):
    evil_host = admin_api.get("/_ductator/api/bootstrap", headers={"Host": "evil.example"})
    assert evil_host.json() == {"needed": True, "allowed": False}
    blocked = admin_api.post(
        "/_ductator/api/bootstrap",
        json={"email": "admin@example.com", "password": "correct horse battery"},
        headers={"Host": "evil.example"},
    )
    assert blocked.status_code == 403
    proxied = admin_api.post(
        "/_ductator/api/bootstrap",
        json={"email": "admin@example.com", "password": "correct horse battery"},
        headers={"X-Forwarded-For": "203.0.113.10"},
    )
    assert proxied.status_code == 403
    evil_origin = admin_api.post(
        "/_ductator/api/bootstrap",
        json={"email": "admin@example.com", "password": "correct horse battery"},
        headers={"Origin": "https://evil.example"},
    )
    assert evil_origin.status_code == 403
    assert store.count_users() == 0


def test_bootstrap_rejects_remote_client_even_with_local_host(admin_api):
    remote = TestClient(
        app.app, base_url="https://127.0.0.1", client=("203.0.113.9", 50000),
    )
    state = remote.get("/_ductator/api/bootstrap")
    assert state.json() == {"needed": True, "allowed": False}
    response = remote.post(
        "/_ductator/api/bootstrap",
        json={"email": "admin@example.com", "password": "correct horse battery"},
    )
    assert response.status_code == 403
    remote.close()


def test_create_user_is_atomic_singleton(admin_api):
    from concurrent.futures import ThreadPoolExecutor

    def attempt(index: int):
        try:
            store.create_user(f"admin{index}@example.com", "correct horse battery")
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(attempt, range(16)))
    assert sum(results) == 1
    assert store.count_users() == 1


def test_store_and_login_reject_empty_email_and_short_password(admin_api):
    with pytest.raises(ValueError):
        store.create_user("", "correct horse battery")
    with pytest.raises(ValueError):
        store.create_user("  ", "correct horse battery")
    bootstrap(admin_api)
    with pytest.raises(ValueError, match="at least 12"):
        store.update_user("admin@example.com", "short")
    response = admin_api.post(
        "/_ductator/api/login",
        json={"email": "   ", "password": "correct horse battery"},
    )
    assert response.status_code == 401


def test_key_rotation_clears_quarantine_breakers_and_caches(admin_api):
    import audio

    data = bootstrap(admin_api)
    audio.OPENROUTER_BLOCKED_UNTIL = time.monotonic() + 300
    audio._provider_breaker_fail("openrouter", "bad key")
    cache_file = audio.CACHE / "voice" / "stale.flac"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_bytes(b"stale")
    response = admin_api.post(
        "/_ductator/api/keys/openrouter",
        json={"value": "sk-or-new-key"},
        headers={"X-VibeCut-Admin-CSRF": data["csrf"]},
    )
    assert response.status_code == 200, response.text
    assert not audio.openrouter_blocked()
    assert not audio._provider_breaker_open("openrouter")
    assert not cache_file.exists()
    assert audio.openrouter_available()


def test_blank_key_save_is_rejected_and_clear_is_explicit(admin_api):
    data = bootstrap(admin_api)
    headers = {"X-VibeCut-Admin-CSRF": data["csrf"]}
    saved = admin_api.post(
        "/_ductator/api/keys/opencode", json={"value": "sk-opencode-1234567890"},
        headers=headers,
    )
    assert saved.status_code == 200
    blank = admin_api.post(
        "/_ductator/api/keys/opencode", json={"value": ""}, headers=headers,
    )
    assert blank.status_code == 400
    assert settings_store.get_secret("opencode") == "sk-opencode-1234567890"
    cleared = admin_api.post(
        "/_ductator/api/keys/opencode",
        json={"value": "", "clear": True}, headers=headers,
    )
    assert cleared.status_code == 200
    assert settings_store.get_secret("opencode") == ""


def test_env_managed_keys_are_read_only(admin_api, monkeypatch):
    data = bootstrap(admin_api)
    monkeypatch.setenv("VIBECUT_OPENAI_API_KEY", "env-openai-secret")
    keys = admin_api.get("/_ductator/api/keys").json()["keys"]
    openai = next(item for item in keys if item["name"] == "openai")
    assert openai["source"] == "env"
    response = admin_api.post(
        "/_ductator/api/keys/openai",
        json={"value": "file-openai-secret"},
        headers={"X-VibeCut-Admin-CSRF": data["csrf"]},
    )
    assert response.status_code == 409
    assert "managed by" in response.json()["detail"]


def test_short_keys_never_return_complete_values(admin_api):
    data = bootstrap(admin_api)
    headers = {"X-VibeCut-Admin-CSRF": data["csrf"]}
    for value in ("abc", "12345", "12345678901", "123456789012345"):
        response = admin_api.post(
            "/_ductator/api/keys/minimax", json={"value": value}, headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["key"]["masked"] == "••••••••"
        assert value not in response.text
        exported = admin_api.get("/_ductator/api/audit/export")
        assert value not in admin_api.get("/_ductator/api/keys").text
        with store._connect() as db:
            rows = db.execute(
                "SELECT before_json, after_json, detail FROM admin_audit"
            ).fetchall()
        for row in rows:
            for field in ("before_json", "after_json", "detail"):
                assert value not in str(row[field] or "")
        for line in exported.text.splitlines():
            entry = json.loads(line)
            payload = json.dumps({
                "before": entry.get("before"),
                "after": entry.get("after"),
                "detail": entry.get("detail"),
            })
            assert value not in payload


def test_sanitize_masks_nested_camel_case_numeric_and_urls():
    sanitized = store.sanitize({
        "api_key": {"value": "nested-secret"},
        "accessToken": "camel-token",
        "x-api-key": "hyphen-key",
        "items": [{"password": "list-password"}],
        "numeric_secret": 987654321,
        "url": "https://example.test/path?token=SECRETVALUE#fragment",
        "cookie_file": "/Users/owner/private/cookies.txt",
    })
    text = json.dumps(sanitized)
    for secret in ("nested-secret", "camel-token", "hyphen-key", "list-password"):
        assert secret not in text
    assert "987654321" not in text
    assert "SECRETVALUE" not in text
    assert "fragment" not in text
    assert "owner/private" not in text


def test_setup_audit_redacts_url_fragment_and_settings_are_private(admin_api):
    bootstrap(admin_api)
    url = "https://www.xiaohongshu.com/explore/abc?token=SECRET#fragment"
    response = admin_api.post(
        "/api/settings",
        json={
            "settings": {
                "ingest": {
                    "xhs_url": url,
                    "ytdlp_cookies": "file",
                    "ytdlp_cookie_file": "/Users/owner/private/cookies.txt",
                },
            },
        },
    )
    assert response.status_code == 200, response.text
    settings_path = admin_api.data_dir / "settings.json"
    assert settings_path.stat().st_mode & 0o777 == 0o600
    audit = admin_api.get("/_ductator/api/audit?limit=100&include_http=1")
    assert "SECRET" not in audit.text
    assert "fragment" not in audit.text
    assert "owner/private" not in audit.text
    exported = admin_api.get("/_ductator/api/audit/export")
    assert "SECRET" not in exported.text
    assert "owner/private" not in exported.text


def test_audit_concurrent_appends_verify(admin_api):
    from concurrent.futures import ThreadPoolExecutor

    def append(index: int):
        for item in range(10):
            store.record_audit("worker", f"concurrent.{index}.{item}")

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(append, range(8)))
    assert store.verify_audit()["ok"] is True


def test_audit_detects_tamper_tail_truncation_and_malformed_json(admin_api):
    for index in range(4):
        store.record_audit("owner", f"audit.test.{index}")
    database = store.db_path()
    with store._connect() as db:
        db.execute("UPDATE admin_audit SET actor = 'attacker' WHERE id = 2")
        db.commit()
    assert store.verify_audit()["ok"] is False

    # Rebuild a clean fixture for tail truncation.
    admin_api.data_dir.joinpath("admin").exists()
    with store._connect() as db:
        db.execute("DELETE FROM admin_audit")
        db.commit()
    store.record_audit("owner", "first")
    store.record_audit("owner", "second")
    with store._connect() as db:
        db.execute("DELETE FROM admin_audit WHERE id = (SELECT MAX(id) FROM admin_audit)")
        db.commit()
    result = store.verify_audit()
    assert result["ok"] is False
    assert "truncated" in result["reason"]

    with store._connect() as db:
        db.execute("DELETE FROM admin_audit")
        db.execute(
            """INSERT INTO admin_audit(
                ts, actor, action, outcome, before_json, entry_hash
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (time.time(), "owner", "corrupt", "ok", "{bad", "abc"),
        )
        db.commit()
    (admin_api.data_dir / "admin" / "audit.head.json").unlink(missing_ok=True)
    result = store.verify_audit()
    assert result["ok"] is False
    assert "malformed" in result["reason"]


def test_audit_retention_archives_and_keeps_verification_valid(admin_api):
    store.record_audit("owner", "old")
    with store._connect() as db:
        db.execute("UPDATE admin_audit SET ts = 0")
        db.commit()
    store.record_audit("owner", "new")
    removed = store.prune_audit(days=1)
    assert removed == 1
    assert store.verify_audit()["ok"] is True
    archives = list((admin_api.data_dir / "admin" / "audit-archive").glob("*.jsonl"))
    assert archives and "old" in archives[0].read_text()


def test_login_rate_limit_buckets_are_bounded(admin_api):
    import admin.routes as admin_routes

    bootstrap(admin_api)
    statuses = []
    for index in range(40):
        response = admin_api.post(
            "/_ductator/api/login",
            json={"email": f"nobody{index}@example.com", "password": "wrong password"},
        )
        statuses.append(response.status_code)
    assert 429 in statuses
    assert len(admin_routes._ATTEMPTS) <= admin_routes.MAX_RATE_KEYS
    audit = admin_api.get("/_ductator/api/audit?limit=100").json()
    assert any(
        item["action"] == "auth.login" and item["outcome"] == "failed"
        for item in audit["entries"]
    )


def test_admin_log_hides_http_rows_and_exports_everything(admin_api):
    bootstrap(admin_api)
    default = admin_api.get("/_ductator/api/audit?limit=100").json()
    assert all(item["action"] != "http.request" for item in default["entries"])
    raw = admin_api.get("/_ductator/api/audit?limit=100&include_http=1").json()
    assert any(item["action"] == "http.request" for item in raw["entries"])
    store.record_audit("owner", "bulk.export")
    exported = admin_api.get("/_ductator/api/audit/export")
    assert "bulk.export" in exported.text
    assert "http.request" in exported.text


def test_audit_verify_failure_logs_failed_outcome(admin_api):
    bootstrap(admin_api)
    with store._connect() as db:
        db.execute("UPDATE admin_audit SET actor = 'attacker' WHERE id = 1")
        db.commit()
    result = admin_api.get("/_ductator/api/audit/verify")
    assert result.status_code == 200
    assert result.json()["ok"] is False
    audit = admin_api.get("/_ductator/api/audit?limit=50").json()
    verify_rows = [item for item in audit["entries"] if item["action"] == "audit.verify"]
    assert verify_rows and verify_rows[0]["outcome"] == "failed"


def test_pipeline_filter_is_partial_and_case_insensitive(admin_api):
    bootstrap(admin_api)
    store.record_pipeline_event("rewrite", "opencode-go", "model")
    store.record_pipeline_event("tts", "minimax", "speech-2.8-turbo")
    result = admin_api.get("/_ductator/api/pipeline?workflow=WRIT").json()
    assert [item["workflow"] for item in result["entries"]] == ["rewrite"]


def test_key_test_reports_not_tested_for_unverified_providers(admin_api):
    data = bootstrap(admin_api)
    headers = {"X-VibeCut-Admin-CSRF": data["csrf"]}
    admin_api.post("/_ductator/api/keys/minimax", json={"value": "mm-key"}, headers=headers)
    result = admin_api.post("/_ductator/api/keys/minimax/test", headers=headers)
    assert result.status_code == 200
    assert result.json()["ok"] is True
    assert result.json()["tested"] is False
    assert "not tested" in result.json()["detail"].lower()


def test_admin_security_headers_on_page_redirect_static_and_api(admin_api):
    page = admin_api.get("/_ductator/")
    redirect = admin_api.get("/_ductator", follow_redirects=False)
    static = admin_api.get("/static/admin.html")
    api = admin_api.get("/_ductator/api/keys")
    for response in (page, redirect, static, api):
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-robots-tag"] == "noindex, nofollow"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "no-referrer"


def test_remote_cleartext_admin_access_is_rejected(admin_api):
    remote = TestClient(
        app.app, base_url="http://127.0.0.1", client=("203.0.113.9", 50000),
    )
    response = remote.get("/_ductator/")
    assert response.status_code == 403
    assert "HTTPS" in response.json()["detail"]
    remote.close()


_FAKE_CATALOG = {
    "opencode-go": [("deepseek-v4.1-flash", "text"), ("glm-5.3-flash", "text")],
    "openrouter": [
        ("deepseek/deepseek-v4.1-flash", "text"),
        ("qwen/qwen-test", "text"),
        ("fish-audio/s2.1-pro-free:free", "tts"),
        ("google/gemini-3.8-flash-lite-tts", "tts"),
        ("google/lyria-3-pro-preview", "music"),
    ],
    "openai": [
        ("gpt-5.6-luna", "text"), ("whisper-1", "stt"), ("tts-1", "tts"),
    ],
    "groq": [("whisper-large-v3-turbo", "stt"), ("openai/gpt-oss-120b", "text")],
    "deepgram": [("nova-3", "stt"), ("aura-2-thalia-en", "tts")],
    "local-mlx": [("mlx-community/Qwen2.5-3B-Instruct-4bit", "text")],
    "ollama": [("qwen2.5:3b", "text")],
    "minimax": [("speech-2.8-turbo", "tts"), ("music-3.0", "music")],
    "local": [("kokoro", "tts"), ("piper", "tts"), ("say", "tts")],
    "auto": [("mlx-community/whisper-small-mlx", "stt"), ("whisper-1", "stt")],
    "whisper": [("mlx-community/whisper-small-mlx", "stt")],
    "apple": [("on-device-3b", "stt")],
    "elevenlabs": [("eleven_multilingual_v2", "tts")],
    "cartesia": [("sonic-3.6", "tts")],
}


def _install_fake_catalog(monkeypatch):
    def fake(provider, refresh=False):
        return {
            "provider": provider,
            "models": [
                {"id": model_id, "name": model_id, "kind": kind}
                for model_id, kind in _FAKE_CATALOG.get(provider, [])
            ],
            "source": "test",
            "fetched_at": 1,
            "stale": False,
            "error": "",
        }
    monkeypatch.setattr(catalog, "catalog", fake)


def _save_workflow(client, csrf, name, routes, **extra):
    body = {
        "routes": routes,
        "reasoning": extra.get("reasoning", "low"),
        "max_output_tokens": extra.get("max_output_tokens", 3200),
        "timeout_s": extra.get("timeout_s", 120),
    }
    return client.post(
        f"/_ductator/api/workflows/{name}", json=body,
        headers={"X-VibeCut-Admin-CSRF": csrf},
    )


def test_workflow_rejects_empty_and_partially_invalid_routes(admin_api, monkeypatch):
    data = bootstrap(admin_api)
    _install_fake_catalog(monkeypatch)
    empty = _save_workflow(admin_api, data["csrf"], "rewrite", [])
    assert empty.status_code == 400
    bad_provider = _save_workflow(
        admin_api, data["csrf"], "rewrite",
        [{"provider": "minimax", "model": "speech-2.8-turbo"}],
    )
    assert bad_provider.status_code == 400
    partial = _save_workflow(admin_api, data["csrf"], "rewrite", [
        {"provider": "opencode-go", "model": "glm-5.3-flash"},
        {"provider": "opencode-go", "model": "not-real"},
    ])
    assert partial.status_code == 400
    assert settings_store.load_settings()["workflows"]["rewrite"]["routes"][0]["model"] != "glm-5.3-flash"


def test_workflow_preserves_duplicate_provider_routes(admin_api, monkeypatch):
    data = bootstrap(admin_api)
    _install_fake_catalog(monkeypatch)
    response = _save_workflow(admin_api, data["csrf"], "rewrite", [
        {"provider": "openrouter", "model": "deepseek/deepseek-v4.1-flash"},
        {"provider": "openrouter", "model": "qwen/qwen-test"},
    ])
    assert response.status_code == 200, response.text
    assert response.json()["value"]["routes"] == [
        {"provider": "openrouter", "model": "deepseek/deepseek-v4.1-flash"},
        {"provider": "openrouter", "model": "qwen/qwen-test"},
    ]


def test_workflow_rejects_wrong_kind_models(admin_api, monkeypatch):
    data = bootstrap(admin_api)
    _install_fake_catalog(monkeypatch)
    tts_music = _save_workflow(admin_api, data["csrf"], "tts", [
        {"provider": "openrouter", "model": "google/lyria-3-pro-preview"},
    ])
    assert tts_music.status_code == 400
    rewrite_tts = _save_workflow(admin_api, data["csrf"], "rewrite", [
        {"provider": "openrouter", "model": "fish-audio/s2.1-pro-free:free"},
    ])
    assert rewrite_tts.status_code == 400
    stt_text = _save_workflow(admin_api, data["csrf"], "stt", [
        {"provider": "openai", "model": "gpt-5.6-luna"},
    ])
    assert stt_text.status_code == 400
    music_tts = _save_workflow(admin_api, data["csrf"], "music", [
        {"provider": "minimax", "model": "speech-2.8-turbo"},
    ])
    assert music_tts.status_code == 400
    valid = _save_workflow(admin_api, data["csrf"], "tts", [
        {"provider": "cartesia", "model": "sonic-3.6"},
        {"provider": "local", "model": "kokoro"},
    ])
    assert valid.status_code == 200, valid.text


def test_workflow_rejects_model_id_traversal_and_query_injection(admin_api, monkeypatch):
    data = bootstrap(admin_api)
    _install_fake_catalog(monkeypatch)
    for model in ("../../etc/passwd", "model?token=SECRET", "model#fragment", ""):
        response = _save_workflow(admin_api, data["csrf"], "rewrite", [
            {"provider": "local-mlx", "model": model},
        ])
        assert response.status_code == 400


def test_settings_api_cannot_write_workflow_routes(admin_api, monkeypatch):
    _install_fake_catalog(monkeypatch)
    before = settings_store.load_settings()["workflows"]["rewrite"]
    response = admin_api.post("/api/settings", json={
        "settings": {
            "stt": {"language": "vi"},
            "workflows": {
                "rewrite": {
                    "routes": [{"provider": "openrouter", "model": "evil?x=1"}],
                    "reasoning": "max",
                    "max_output_tokens": 999999,
                    "timeout_s": 1,
                },
            },
        },
    })
    assert response.status_code == 400
    assert "admin console" in response.json()["detail"]
    after = settings_store.load_settings()
    assert after["workflows"]["rewrite"] == before
    # A valid Setup save still works and cannot touch workflows.
    response = admin_api.post("/api/settings", json={"settings": {"stt": {"language": "vi"}}})
    assert response.status_code == 200
    after = settings_store.load_settings()
    assert after["workflows"]["rewrite"] == before
    assert after["stt"]["language"] == "vi"


def test_workflow_save_clears_voice_and_music_caches(admin_api, monkeypatch):
    import audio

    data = bootstrap(admin_api)
    _install_fake_catalog(monkeypatch)
    voice = audio.CACHE / "voice" / "line.flac"
    music = audio.CACHE / "music" / "track.wav"
    voice.parent.mkdir(parents=True, exist_ok=True)
    music.parent.mkdir(parents=True, exist_ok=True)
    voice.write_bytes(b"voice")
    music.write_bytes(b"music")
    response = _save_workflow(admin_api, data["csrf"], "tts", [
        {"provider": "minimax", "model": "speech-2.8-turbo"},
    ])
    assert response.status_code == 200, response.text
    assert not voice.exists()
    assert not music.exists()


def test_audit_detects_invalid_signed_anchor(admin_api):
    store.record_audit("owner", "anchored")
    anchor_path = admin_api.data_dir / "admin" / "audit.head.json"
    payload = json.loads(anchor_path.read_text())
    payload["head"] = "0" * 64
    anchor_path.write_text(json.dumps(payload))
    result = store.verify_audit()
    assert result["ok"] is False
    assert "anchor" in result["reason"].lower()


def test_admin_export_is_not_truncated_at_500(admin_api):
    bootstrap(admin_api)
    for index in range(505):
        store.record_audit("bulk", f"bulk.entry.{index}")
    exported = admin_api.get("/_ductator/api/audit/export")
    assert exported.status_code == 200
    lines = [line for line in exported.text.splitlines() if line.strip()]
    assert len(lines) >= 505
    assert any('"bulk.entry.504"' in line for line in lines)


def test_sessions_expire_idle_and_revoke(admin_api):
    user = store.create_user("owner@example.com", "correct horse battery")
    session = store.create_session(user["email"])
    assert store.get_session(session["token"]) is not None

    with store._connect() as db:
        db.execute(
            "UPDATE admin_sessions SET expires = ? WHERE token_hash = ?",
            (time.time() - 1, hashlib.sha256(session["token"].encode()).hexdigest()),
        )
        db.commit()
    assert store.get_session(session["token"]) is None

    session = store.create_session(user["email"])
    with store._connect() as db:
        db.execute(
            "UPDATE admin_sessions SET last_seen = ? WHERE token_hash = ?",
            (time.time() - (store.IDLE_MINUTES + 1) * 60,
             hashlib.sha256(session["token"].encode()).hexdigest()),
        )
        db.commit()
    assert store.get_session(session["token"]) is None

    first = store.create_session(user["email"])
    second = store.create_session(user["email"])
    store.delete_other_sessions(int(user["id"]), keep_hash=hashlib.sha256(first["token"].encode()).hexdigest())
    assert store.get_session(first["token"]) is not None
    assert store.get_session(second["token"]) is None
    store.delete_session(first["token"])
    assert store.get_session(first["token"]) is None


def test_secret_never_reaches_sqlite_or_wal_files(admin_api):
    data = bootstrap(admin_api)
    secret = "sk-opencode-UNIQUE-WAL-SECRET-987654321"
    response = admin_api.post(
        "/_ductator/api/keys/opencode", json={"value": secret},
        headers={"X-VibeCut-Admin-CSRF": data["csrf"]},
    )
    assert response.status_code == 200
    admin_dir = admin_api.data_dir / "admin"
    for path in admin_dir.glob("admin.sqlite3*"):
        assert secret not in path.read_bytes().decode("latin1", "ignore")


def _audit_process_worker(index: int) -> None:
    from admin import store as child_store

    for item in range(10):
        child_store.record_audit("process", f"process.{index}.{item}")


def test_audit_chain_survives_multiple_processes(admin_api):
    import multiprocessing

    try:
        context = multiprocessing.get_context("fork")
    except ValueError:
        pytest.skip("fork start method is unavailable")
    processes = [
        context.Process(target=_audit_process_worker, args=(index,))
        for index in range(3)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(20)
        assert process.exitcode == 0
    result = store.verify_audit()
    assert result["ok"] is True
    assert result["entries"] >= 30


def test_setup_rejects_cross_site_and_cross_origin_writes(admin_api):
    evil = admin_api.post(
        "/api/settings",
        json={"settings": {"stt": {"language": "vi"}}},
        headers={"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"},
    )
    assert evil.status_code == 403
    cross = admin_api.post(
        "/api/settings",
        json={"settings": {"stt": {"language": "vi"}}},
        headers={"Origin": "http://127.0.0.1:9999"},
    )
    assert cross.status_code == 403
    same = admin_api.post(
        "/api/settings",
        json={"settings": {"stt": {"language": "vi"}}},
        headers={"Origin": "http://127.0.0.1", "Sec-Fetch-Site": "same-origin"},
    )
    assert same.status_code == 200
