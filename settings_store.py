"""Local settings + secret storage for optional cloud providers.

Secrets live in ``data/secrets.json`` with mode 0600 and are never returned by
the API. Environment variables always win, so containers and CI can inject them.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("VIBECUT_DATA", ROOT / "data")).expanduser().resolve()
SETTINGS_PATH = DATA / "settings.json"
SECRETS_PATH = DATA / "secrets.json"
LOCK = threading.Lock()

SECRET_NAMES = ("groq", "openai", "deepgram", "elevenlabs", "cartesia")

ENV_KEYS = {
    "groq": ("VIBECUT_GROQ_API_KEY", "GROQ_API_KEY"),
    "openai": ("VIBECUT_OPENAI_API_KEY", "OPENAI_API_KEY"),
    "deepgram": ("VIBECUT_DEEPGRAM_API_KEY", "DEEPGRAM_API_KEY"),
    "elevenlabs": ("VIBECUT_ELEVENLABS_API_KEY", "ELEVENLABS_API_KEY"),
    "cartesia": ("VIBECUT_CARTESIA_API_KEY", "CARTESIA_API_KEY"),
}

DEFAULTS = {
    "opencode": {
        "enabled": True,
        "model": "deepseek-v4.1-flash",
        "variant": "low",
        "use_rewrite": True,
        "use_brief": True,
        "use_translate": True,
    },
    "stt": {"provider": "auto", "language": "en"},
    "tts": {"provider": "auto"},
}


def _read(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _merge(base: dict, patch: dict) -> dict:
    result = {**base}
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = {**result[key], **value}
        else:
            result[key] = value
    return result


def _migrate(stored: dict) -> dict:
    legacy = stored.pop("openrouter", None)
    if isinstance(legacy, dict) and "opencode" not in stored:
        stored["opencode"] = {
            "enabled": bool(legacy.get("enabled", True)),
            "model": "deepseek-v4.1-flash",
            "variant": "low",
            "use_rewrite": bool(legacy.get("use_rewrite", True)),
            "use_brief": bool(legacy.get("use_brief", True)),
            "use_translate": True,
        }
    return stored


def load_settings() -> dict:
    return _merge(DEFAULTS, _migrate(_read(SETTINGS_PATH)))


def save_settings(patch: dict) -> dict:
    with LOCK:
        current = load_settings()
        merged = _merge(current, patch)
        DATA.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(
            json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8",
        )
    return merged


def _load_secrets() -> dict:
    return _read(SECRETS_PATH)


def get_secret(name: str) -> str:
    for env_name in ENV_KEYS.get(name, ()):
        value = os.environ.get(env_name)
        if value:
            return value.strip()
    return str(_load_secrets().get(name) or "").strip()


def secret_status() -> dict:
    return {name: bool(get_secret(name)) for name in SECRET_NAMES}


def secret_source(name: str) -> str:
    for env_name in ENV_KEYS.get(name, ()):
        if os.environ.get(env_name):
            return "env"
    if str(_load_secrets().get(name) or "").strip():
        return "file"
    return ""


def save_secrets(updates: dict) -> None:
    clean = {
        name: str(value).strip()
        for name, value in updates.items()
        if name in SECRET_NAMES and isinstance(value, str) and value.strip()
    }
    clear = {
        name for name, value in updates.items()
        if name in SECRET_NAMES and isinstance(value, str) and value == ""
    }
    if not clean and not clear:
        return
    with LOCK:
        secrets = _load_secrets()
        for name in clear:
            secrets.pop(name, None)
        secrets.update(clean)
        DATA.mkdir(parents=True, exist_ok=True)
        SECRETS_PATH.write_text(
            json.dumps(secrets, indent=1), encoding="utf-8",
        )
        try:
            SECRETS_PATH.chmod(0o600)
        except OSError:
            pass


def public_state() -> dict:
    settings = load_settings()
    return {
        "settings": settings,
        "secrets": secret_status(),
        "sources": {name: secret_source(name) for name in SECRET_NAMES},
        "paths": {
            "settings": str(SETTINGS_PATH),
            "secrets": str(SECRETS_PATH),
        },
    }
