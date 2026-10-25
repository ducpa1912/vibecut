"""Catalog kind, cache, and corruption regressions."""

from __future__ import annotations

import json
import threading

import pytest

import admin.catalog as catalog
import settings_store
from admin import store


@pytest.fixture
def catalog_data(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(settings_store, "DATA", data)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", data / "settings.json")
    monkeypatch.setattr(settings_store, "SECRETS_PATH", data / "secrets.json")
    return data


def test_openrouter_kinds_follow_output_modalities(tmp_path, monkeypatch, catalog_data):
    payload = {
        "data": [
            {"id": "text/model", "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]}},
            {"id": "voice/model", "architecture": {"input_modalities": ["text"], "output_modalities": ["audio"]}},
            {"id": "google/lyria-3-pro-preview", "architecture": {"input_modalities": ["text"], "output_modalities": ["audio"]}},
            {"id": "image/model", "architecture": {"input_modalities": ["text"], "output_modalities": ["image"]}},
        ]
    }
    monkeypatch.setattr(catalog, "_fetch_json", lambda *args, **kwargs: payload)
    models = catalog._fetch_openrouter()
    kinds = {item["id"]: item["kind"] for item in models}
    assert kinds["text/model"] == "text"
    assert kinds["voice/model"] == "tts"
    assert kinds["google/lyria-3-pro-preview"] == "music"
    assert "image/model" not in kinds


def test_catalog_merges_static_metadata_without_retagging_kind(monkeypatch, catalog_data):
    fetched = [
        {"id": "google/lyria-3-pro-preview", "name": "Lyria fetched", "reasoning": False, "kind": "text"},
        {"id": "text/model", "name": "Text", "reasoning": True, "kind": "text"},
    ]
    monkeypatch.setattr(catalog, "_fetch", lambda provider: (fetched, "test fetch"))
    result = catalog.catalog("openrouter", refresh=True)
    by_id = {item["id"]: item for item in result["models"]}
    assert by_id["google/lyria-3-pro-preview"]["kind"] == "music"
    assert by_id["google/lyria-3-pro-preview"]["name"] == "Lyria fetched"
    assert by_id["text/model"]["kind"] == "text"
    assert any(item["id"] == "fish-audio/s2.1-pro-free:free" and item["kind"] == "tts"
               for item in result["models"])


def test_corrupt_cache_falls_back_to_static(monkeypatch, catalog_data):
    path = catalog._cache_path()
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(catalog, "_fetch", lambda provider: (_ for _ in ()).throw(RuntimeError("offline")))
    result = catalog.catalog("openrouter")
    assert result["models"]
    assert all(item["kind"] in {"text", "tts", "music", "stt"} for item in result["models"])
    assert "error" in result


def test_malformed_cache_entries_are_ignored(monkeypatch, catalog_data):
    path = catalog._cache_path()
    path.write_text(json.dumps({
        "openrouter": {"models": "nope", "fetched_at": 9999999999},
        "minimax": {"models": [{"id": ""}, {"bad": True}], "fetched_at": 9999999999},
    }), encoding="utf-8")
    monkeypatch.setattr(catalog, "_fetch", lambda provider: (_ for _ in ()).throw(RuntimeError("offline")))
    result = catalog.catalog("minimax")
    assert result["models"]
    assert all(item["id"] for item in result["models"])


def test_catalog_cache_writes_are_atomic_under_threads(monkeypatch, catalog_data):
    monkeypatch.setattr(catalog, "_fetch", lambda provider: ([
        {"id": f"{provider}/model-{index}", "kind": "text"} for index in range(10)
    ], "test"))
    errors = []

    def work(provider):
        try:
            catalog.catalog(provider, refresh=True)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [
        threading.Thread(target=work, args=(provider,))
        for provider in ("opencode-go", "openrouter", "minimax", "local") * 4
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    assert json.loads(catalog._cache_path().read_text())
    assert catalog._cache_path().stat().st_mode & 0o777 == 0o600


def test_catalog_truncates_oversized_model_lists(monkeypatch, catalog_data):
    monkeypatch.setattr(catalog, "_fetch", lambda provider: ([
        {"id": f"model-{index}", "kind": "text"}
        for index in range(catalog.MAX_MODELS + 50)
    ], "test"))
    result = catalog.catalog("opencode-go", refresh=True)
    assert len(result["models"]) == catalog.MAX_MODELS


def test_failed_refresh_keeps_last_good_catalog(monkeypatch, catalog_data):
    monkeypatch.setattr(catalog, "_fetch", lambda provider: ([
        {"id": "cached/model", "kind": "text"},
    ], "test"))
    catalog.catalog("opencode-go", refresh=True)
    entry = catalog._read_cache()["opencode-go"]
    entry["fetched_at"] = 0
    cache = catalog._read_cache()
    cache["opencode-go"] = entry
    catalog._write_cache(cache)
    monkeypatch.setattr(catalog, "_fetch", lambda provider: (_ for _ in ()).throw(RuntimeError("offline")))
    result = catalog.catalog("opencode-go")
    assert result["stale"] is True
    assert "cached/model" in {item["id"] for item in result["models"]}


def test_apple_static_catalog_is_stt(monkeypatch, catalog_data):
    monkeypatch.setattr(catalog, "_fetch", lambda provider: ([], "built-in catalog"))
    result = catalog.catalog("apple", refresh=True)
    assert result["models"][0]["id"] == "on-device-3b"
    assert result["models"][0]["kind"] == "stt"
