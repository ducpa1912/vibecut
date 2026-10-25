"""Local settings + secret storage for optional cloud providers.

Secrets live in ``data/secrets.json`` with mode 0600 and are never returned by
the API. Environment variables win for most providers, so containers and CI
can inject them. OpenRouter is project-first: a key saved in Setup beats an
environment variable, because a stale global ``OPENROUTER_API_KEY`` should not
shadow the project's own key.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import captions
import workflow_config
from url_ingest import registry as ingest_registry

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("VIBECUT_DATA", ROOT / "data")).expanduser().resolve()
SETTINGS_PATH = DATA / "settings.json"
SECRETS_PATH = DATA / "secrets.json"
LOCK = threading.Lock()

SECRET_NAMES = (
    "opencode", "openrouter", "minimax", "groq", "openai", "deepgram",
    "elevenlabs", "cartesia", "cobalt", "xhs",
)

# A saved project key beats the environment for these providers.
PROJECT_FIRST = frozenset({"openrouter"})

ENV_KEYS = {
    "opencode": ("VIBECUT_OPENCODE_API_KEY", "OPENCODE_GO_API_KEY", "OPENCODE_API_KEY"),
    "openrouter": ("VIBECUT_OPENROUTER_API_KEY", "OPENROUTER_API_KEY"),
    "minimax": ("VIBECUT_MINIMAX_API_KEY", "MINIMAX_API_KEY"),
    "groq": ("VIBECUT_GROQ_API_KEY", "GROQ_API_KEY"),
    "openai": ("VIBECUT_OPENAI_API_KEY", "OPENAI_API_KEY"),
    "deepgram": ("VIBECUT_DEEPGRAM_API_KEY", "DEEPGRAM_API_KEY"),
    "elevenlabs": ("VIBECUT_ELEVENLABS_API_KEY", "ELEVENLABS_API_KEY"),
    "cartesia": ("VIBECUT_CARTESIA_API_KEY", "CARTESIA_API_KEY"),
    "cobalt": ("VIBECUT_COBALT_API_KEY", "COBALT_API_KEY"),
    "xhs": ("VIBECUT_XHS_GET_TOKEN", "XHS_GET_TOKEN"),
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
    "translation": {
        "mode": "auto",
    },
    "openrouter": {
        "enabled": True,
        "model": "deepseek/deepseek-v4.1-flash:floor",
        "reasoning": "low",
        "use_rewrite": True,
        "use_translate": True,
        "use_tts": True,
        "use_music": True,
    },
    "minimax": {
        "enabled": True,
        "tts_model": "speech-2.8-turbo",
        "music_model": "music-3.0",
    },
    "stt": {
        "provider": "auto",
        "language": "en",
        "model": "mlx-community/whisper-small-mlx",
    },
    "tts": {"provider": "minimax"},
    "preflight": {
        "toggles": {},
        "severity": {},
        "styles": {},
    },
    "caption_styles": captions.default_style_settings(),
    "workflows": workflow_config.default_workflows(),
    "ingest": dict(ingest_registry.DEFAULT_INGEST_SETTINGS),
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
    # Old v0.7 stored an OpenRouter config before OpenCode existed. Copy it to
    # OpenCode for migration, but keep the modern OpenRouter config intact.
    legacy = stored.get("openrouter")
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
    merged = _merge(DEFAULTS, _migrate(_read(SETTINGS_PATH)))
    translation = merged.get("translation") or {}
    if translation.get("mode") not in {"auto", "local_first", "local_only", "online_only"}:
        translation["mode"] = "auto"
        merged["translation"] = translation
    ingest = dict(merged.get("ingest") or {})
    # Secrets belong in secrets.json, never in the public settings document.
    for key in (
        "cobalt_api_key",
        "cobalt_key",
        "xhs_token",
        "xhs_api_key",
        "xhs_access_token",
        "xhs_get_token",
    ):
        ingest.pop(key, None)
    merged["ingest"] = ingest
    try:
        merged["caption_styles"] = captions.normalize_style_settings(
            merged.get("caption_styles"),
        )
    except captions.CaptionStyleError:
        merged["caption_styles"] = captions.default_style_settings()
    merged["workflows"] = workflow_config.normalize_workflows(merged.get("workflows"))
    return merged


def save_settings(patch: dict) -> dict:
    with LOCK:
        current = load_settings()
        merged = _merge(current, patch)
        DATA.mkdir(parents=True, exist_ok=True)
        try:
            DATA.chmod(0o700)
        except OSError:
            pass
        temporary = SETTINGS_PATH.with_name(
            f"{SETTINGS_PATH.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        temporary.write_text(
            json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8",
        )
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        os.replace(temporary, SETTINGS_PATH)
        try:
            SETTINGS_PATH.chmod(0o600)
        except OSError:
            pass
    return merged


def _load_secrets() -> dict:
    return _read(SECRETS_PATH)


def _file_secret(name: str) -> str:
    return str(_load_secrets().get(name) or "").strip()


def _env_secret(name: str) -> str:
    for env_name in ENV_KEYS.get(name, ()):
        value = os.environ.get(env_name)
        if value and value.strip():
            return value.strip()
    return ""


def get_secret(name: str) -> str:
    file_value = _file_secret(name)
    if name in PROJECT_FIRST and file_value:
        return file_value
    return _env_secret(name) or file_value


def secret_status() -> dict:
    return {name: bool(get_secret(name)) for name in SECRET_NAMES}


def secret_source(name: str) -> str:
    file_value = _file_secret(name)
    if name in PROJECT_FIRST and file_value:
        return "file"
    if _env_secret(name):
        return "env"
    return "file" if file_value else ""


def save_secrets(updates: dict) -> None:
    clean = {
        name: value.strip()
        for name, value in updates.items()
        if name in SECRET_NAMES
        and isinstance(value, str)
        and value.strip()
        and len(value.strip()) <= 8192
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
