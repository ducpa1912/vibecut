"""Local settings + secret storage for optional cloud providers.

Secrets live in ``data/secrets.json`` with mode 0600 and are never returned by
the API. Environment variables win for most providers, so containers and CI
can inject them. OpenRouter is project-first: a key saved in Setup beats an
environment variable, because a stale global ``OPENROUTER_API_KEY`` should not
shadow the project's own key.
"""

from __future__ import annotations

import json
import math
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
_MIGRATION_LOCK = threading.Lock()

# These keys belonged to engines removed in the revamp. They stay readable for
# legacy jobs, but the admin console hides them until the creator confirms
# deletion in Setup.
STALE_SECRETS = ("cartesia", "openai")

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
        "model": "mlx-community/whisper-large-v3-turbo",
    },
    "tts": {"provider": "minimax"},
    "preflight": {
        "toggles": {},
        "severity": {},
        "styles": {},
    },
    "rights": {
        "lock": True,
    },
    "voice_fit": {
        "preserve_pitch": True,
        "max_speed": 1.80,
        "engine": "auto",
        "allow_extreme_speed": False,
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


def _migrate_route(workflow: str, raw: object) -> tuple[dict | None, bool]:
    if not isinstance(raw, dict):
        return None, True
    route = dict(raw)
    raw_provider = str(route.get("provider") or "")
    provider = raw_provider.strip().lower()
    model = str(route.get("model") or "").strip()
    route_changed = provider != raw_provider
    if workflow == "tts":
        if provider in workflow_config.REMOVED_TTS_PROVIDERS:
            return {
                "provider": "minimax",
                "model": "speech-2.8-turbo",
            }, True
        if provider == "local" and model in workflow_config.REMOVED_TTS_MODELS:
            return {"provider": "local", "model": "kokoro"}, True
    elif workflow in {"story_brief", "rewrite", "translate", "hook_rank"}:
        if provider in workflow_config.REMOVED_TEXT_PROVIDERS:
            return None, True
    elif workflow == "stt":
        if provider == "auto":
            # Old "auto" routes named a local Whisper model; keep that fallback
            # as the Whisper pack instead of collapsing it into Apple.
            if "whisper" in model.lower():
                return {
                    "provider": "whisper",
                    "model": workflow_config.STT_MODEL_MIGRATIONS.get(model, model),
                }, True
            return {"provider": "apple", "model": "on-device-3b"}, True
        if provider == "openai":
            return {"provider": "groq", "model": "whisper-large-v3-turbo"}, True
        if model in workflow_config.STT_MODEL_MIGRATIONS:
            return {
                "provider": provider,
                "model": workflow_config.STT_MODEL_MIGRATIONS[model],
            }, True
    if route_changed:
        route["provider"] = provider
    return route, route_changed


def _migrate_workflows(stored: dict) -> bool:
    workflows = stored.get("workflows")
    if not isinstance(workflows, dict):
        return False
    defaults = workflow_config.default_workflows()
    changed = False
    for name, config in list(workflows.items()):
        if name not in workflow_config.WORKFLOW_PROVIDERS:
            continue
        if not isinstance(config, dict):
            continue
        routes = config.get("routes")
        if not isinstance(routes, list):
            continue
        migrated: list[dict] = []
        for raw in routes:
            route, route_changed = _migrate_route(name, raw)
            changed = changed or route_changed
            if route is None:
                continue
            if route not in migrated:
                migrated.append(route)
            else:
                changed = True
        if not migrated and defaults.get(name, {}).get("routes"):
            migrated = [dict(item) for item in defaults[name]["routes"]]
            changed = True
        config["routes"] = migrated
    return changed


def _migrate(stored: dict) -> tuple[dict, bool]:
    original = json.loads(json.dumps(stored))
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
    tts = stored.get("tts")
    if isinstance(tts, dict):
        provider = str(tts.get("provider") or "").strip().lower()
        mapped = workflow_config.TTS_ENGINE_MIGRATIONS.get(provider)
        if mapped:
            tts["provider"] = mapped
    _migrate_workflows(stored)
    return stored, stored != original


def _normalize_rights(value: object) -> dict:
    """Keep ``rights.lock`` a bool; the lock defaults to on."""
    section = dict(value) if isinstance(value, dict) else {}
    lock = section.get("lock", True)
    if isinstance(lock, str):
        folded = lock.strip().casefold()
        if folded in {"1", "true", "yes", "on"}:
            lock = True
        elif folded in {"0", "false", "no", "off", ""}:
            lock = False
        else:
            lock = True
    elif not isinstance(lock, bool):
        lock = True
    return {"lock": lock}


def _normalize_voice_fit(value: object) -> dict:
    """Keep the shared voice-fit policy valid across lanes."""
    section = dict(value) if isinstance(value, dict) else {}
    preserve = section.get("preserve_pitch", True)
    if isinstance(preserve, str):
        preserve = preserve.strip().casefold() not in {"0", "false", "no", "off", ""}
    preserve = bool(preserve)
    try:
        speed = float(section.get("max_speed", 1.80))
    except (TypeError, ValueError):
        speed = 1.80
    if not math.isfinite(speed):
        speed = 1.80
    speed = max(1.0, min(2.5, speed))
    engine = str(section.get("engine") or "auto").strip().lower()
    if engine not in {"auto", "ffmpeg", "signalsmith"}:
        engine = "auto"
    extreme = section.get("allow_extreme_speed", False)
    if isinstance(extreme, str):
        extreme = extreme.strip().casefold() in {"1", "true", "yes", "on"}
    return {
        "preserve_pitch": preserve,
        "max_speed": round(speed, 2),
        "engine": engine,
        "allow_extreme_speed": bool(extreme),
    }


def _clean_ingest(settings: dict) -> None:
    ingest = dict(settings.get("ingest") or {})
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
    settings["ingest"] = ingest


def _atomic_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    temporary = path.with_name(
        f"{path.name}.{os.getpid()}.{threading.get_ident()}.migrate.tmp"
    )
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8",
    )
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    os.replace(temporary, path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def load_settings() -> dict:
    stored, migrated = _migrate(_read(SETTINGS_PATH))
    merged = _merge(DEFAULTS, stored)
    translation = merged.get("translation") or {}
    if translation.get("mode") not in {"auto", "local_first", "local_only", "online_only"}:
        translation["mode"] = "auto"
        merged["translation"] = translation
    _clean_ingest(merged)
    merged["rights"] = _normalize_rights(merged.get("rights"))
    merged["voice_fit"] = _normalize_voice_fit(merged.get("voice_fit"))
    try:
        merged["caption_styles"] = captions.normalize_style_settings(
            merged.get("caption_styles"),
        )
    except captions.CaptionStyleError:
        merged["caption_styles"] = captions.default_style_settings()
    merged["workflows"] = workflow_config.normalize_workflows(merged.get("workflows"))
    if migrated:
        # Removed engines and text routes are rewritten once, on first load,
        # so the founder's old settings.json does not keep feeding dead routes
        # back into the app.
        with _MIGRATION_LOCK:
            current = _read(SETTINGS_PATH)
            current_migrated, current_changed = _migrate(current)
            if current_changed:
                _atomic_write(SETTINGS_PATH, merged)
    return merged


def save_settings(patch: dict) -> dict:
    with LOCK:
        current = load_settings()
        merged = _merge(current, patch)
        merged["rights"] = _normalize_rights(merged.get("rights"))
        merged["voice_fit"] = _normalize_voice_fit(merged.get("voice_fit"))
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


def stale_secret_status() -> list[dict]:
    """Keys that belonged to removed engines, pending creator confirmation."""
    secrets = _load_secrets()
    result = []
    for name in STALE_SECRETS:
        file_value = str(secrets.get(name) or "").strip()
        env_value = _env_secret(name)
        if not file_value and not env_value:
            continue
        result.append({
            "name": name,
            "source": "file" if file_value else "env",
            "removable": bool(file_value),
        })
    return result


def confirm_stale_secrets() -> dict:
    """Delete removed-engine keys after explicit confirmation.

    Environment-managed keys cannot be deleted by the app and stay listed so
    Setup can tell the creator to unset the variable.
    """
    with LOCK:
        secrets = _load_secrets()
        removed = [name for name in STALE_SECRETS if name in secrets]
        if removed:
            for name in removed:
                secrets.pop(name, None)
            DATA.mkdir(parents=True, exist_ok=True)
            SECRETS_PATH.write_text(
                json.dumps(secrets, indent=1), encoding="utf-8",
            )
            try:
                SECRETS_PATH.chmod(0o600)
            except OSError:
                pass
    return {"removed": removed, "stale": stale_secret_status()}


def public_state() -> dict:
    settings = load_settings()
    return {
        "settings": settings,
        "secrets": secret_status(),
        "sources": {name: secret_source(name) for name in SECRET_NAMES},
        "stale_secrets": stale_secret_status(),
        "paths": {
            "settings": str(SETTINGS_PATH),
            "secrets": str(SECRETS_PATH),
        },
    }
