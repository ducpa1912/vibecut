"""Provider metadata and searchable model catalogs for the admin console."""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

import settings_store
from admin import store

CATALOG_TTL = 900
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENAI_MODELS_URL = "https://api.openai.com/v1/models"
GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"
ELEVENLABS_MODELS_URL = "https://api.elevenlabs.io/v1/models"
OLLAMA_MODELS_URL = "http://127.0.0.1:11434/api/tags"

PROVIDER_META: dict[str, dict[str, Any]] = {
    "opencode-go": {"label": "OpenCode Go", "kind": "text", "secret": "opencode"},
    "openrouter": {"label": "OpenRouter", "kind": "text", "secret": "openrouter"},
    "openai": {"label": "OpenAI", "kind": "text", "secret": "openai"},
    "groq": {"label": "Groq", "kind": "text", "secret": "groq"},
    "local-mlx": {"label": "MLX local", "kind": "text"},
    "ollama": {"label": "Ollama", "kind": "text"},
    "apple": {"label": "Apple on-device", "kind": "text"},
    "minimax": {"label": "MiniMax", "kind": "speech", "secret": "minimax"},
    "local": {"label": "Local engine", "kind": "tts"},
    "deepgram": {"label": "Deepgram", "kind": "speech", "secret": "deepgram"},
    "elevenlabs": {"label": "ElevenLabs", "kind": "speech", "secret": "elevenlabs"},
    "cartesia": {"label": "Cartesia", "kind": "speech", "secret": "cartesia"},
    "auto": {"label": "Automatic local", "kind": "stt"},
    "whisper": {"label": "mlx-whisper", "kind": "stt"},
}

AI_SECRETS: dict[str, dict[str, Any]] = {
    "opencode": {"label": "OpenCode Go", "env": "VIBECUT_OPENCODE_API_KEY"},
    "openrouter": {"label": "OpenRouter", "env": "VIBECUT_OPENROUTER_API_KEY"},
    "minimax": {"label": "MiniMax", "env": "VIBECUT_MINIMAX_API_KEY"},
    "groq": {"label": "Groq", "env": "VIBECUT_GROQ_API_KEY"},
    "openai": {"label": "OpenAI", "env": "VIBECUT_OPENAI_API_KEY"},
    "deepgram": {"label": "Deepgram", "env": "VIBECUT_DEEPGRAM_API_KEY"},
    "elevenlabs": {"label": "ElevenLabs", "env": "VIBECUT_ELEVENLABS_API_KEY"},
    "cartesia": {"label": "Cartesia", "env": "VIBECUT_CARTESIA_API_KEY"},
}

_STATIC: dict[str, list[dict[str, Any]]] = {
    "opencode-go": [
        {"id": "deepseek-v4.1-flash", "name": "DeepSeek V4.1 Flash", "reasoning": True},
        {"id": "deepseek-v4-pro", "name": "DeepSeek V4 Pro", "reasoning": True},
        {"id": "glm-5.3-flash", "name": "GLM 5.3 Flash", "reasoning": True},
    ],
    "openrouter": [
        {"id": "deepseek/deepseek-v4.1-flash", "name": "DeepSeek V4.1 Flash", "reasoning": True},
        {"id": "google/gemini-3.1-flash-lite", "name": "Gemini 3.1 Flash Lite", "reasoning": True},
        {"id": "fish-audio/s2.1-pro-free:free", "name": "Fish S2.1 Pro Free", "reasoning": False, "kind": "tts"},
        {"id": "google/gemini-3.8-flash-lite-tts", "name": "Gemini 3.8 Flash-Lite TTS", "reasoning": False, "kind": "tts"},
        {"id": "google/lyria-3-pro-preview", "name": "Lyria 3 Pro", "reasoning": False, "kind": "music"},
        {"id": "google/lyria-3-clip-preview", "name": "Lyria 3 Clip", "reasoning": False, "kind": "music"},
    ],
    "elevenlabs": [
        {"id": "eleven_multilingual_v2", "name": "Eleven Multilingual v2", "reasoning": False, "kind": "tts"},
        {"id": "eleven_turbo_v2_5", "name": "Eleven Turbo v2.5", "reasoning": False, "kind": "tts"},
    ],
    "openai": [
        {"id": "gpt-4o-mini-tts", "name": "GPT-4o mini TTS", "reasoning": False, "kind": "tts"},
        {"id": "tts-1", "name": "TTS-1", "reasoning": False, "kind": "tts"},
        {"id": "whisper-1", "name": "Whisper-1", "reasoning": False, "kind": "stt"},
        {"id": "gpt-5.6-luna", "name": "GPT-5.6 Luna", "reasoning": True, "kind": "text"},
        {"id": "gpt-6-luna", "name": "GPT-6 Luna", "reasoning": True, "kind": "text"},
    ],
    "groq": [
        {"id": "canopylabs/orpheus-v1-english", "name": "Orpheus v1 English", "reasoning": False, "kind": "tts"},
        {"id": "whisper-large-v3-turbo", "name": "Whisper Large v3 Turbo", "reasoning": False, "kind": "stt"},
        {"id": "whisper-large-v3", "name": "Whisper Large v3", "reasoning": False, "kind": "stt"},
        {"id": "openai/gpt-oss-120b", "name": "GPT-OSS 120B", "reasoning": True, "kind": "text"},
        {"id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B", "reasoning": False, "kind": "text"},
    ],
    "local": [
        {"id": "kokoro", "name": "Kokoro (local)", "reasoning": False, "kind": "tts"},
        {"id": "piper", "name": "Piper (local)", "reasoning": False, "kind": "tts"},
        {"id": "say", "name": "Apple say (local)", "reasoning": False, "kind": "tts"},
    ],
    "local-mlx": [
        {"id": "mlx-community/Qwen2.5-3B-Instruct-4bit", "name": "Qwen2.5 3B Instruct 4-bit", "reasoning": False},
        {"id": "mlx-community/Qwen2.5-7B-Instruct-4bit", "name": "Qwen2.5 7B Instruct 4-bit", "reasoning": False},
    ],
    "apple": [
        {"id": "on-device-3b", "name": "Apple Foundation Model (on-device)", "reasoning": False},
    ],
    "minimax": [
        {"id": "speech-2.8-turbo", "name": "Speech 2.8 Turbo", "reasoning": False, "kind": "tts"},
        {"id": "music-3.0", "name": "Music 3.0", "reasoning": False, "kind": "music"},
    ],
    "deepgram": [
        {"id": "nova-3", "name": "Nova-3", "reasoning": False, "kind": "stt"},
        {"id": "aura-2-thalia-en", "name": "Aura-2 Thalia", "reasoning": False, "kind": "tts"},
        {"id": "aura-2-orpheus-en", "name": "Aura-2 Orpheus", "reasoning": False, "kind": "tts"},
    ],
    "cartesia": [
        {"id": "sonic-3.6", "name": "Sonic 3.6", "reasoning": False, "kind": "tts"},
    ],
    "auto": [
        {"id": "mlx-community/whisper-small-mlx", "name": "Whisper small (local)", "reasoning": False, "kind": "stt"},
        {"id": "whisper-1", "name": "OpenAI Whisper", "reasoning": False, "kind": "stt"},
        {"id": "whisper-large-v3-turbo", "name": "Groq Whisper Large v3 Turbo", "reasoning": False, "kind": "stt"},
        {"id": "nova-3", "name": "Deepgram Nova-3", "reasoning": False, "kind": "stt"},
    ],
    "whisper": [
        {"id": "mlx-community/whisper-small-mlx", "name": "Whisper small (local)", "reasoning": False, "kind": "stt"},
        {"id": "mlx-community/whisper-large-v3-turbo", "name": "Whisper large v3 turbo (local)", "reasoning": False, "kind": "stt"},
    ],
}


def _cache_path() -> Path:
    return store.data_dir() / "model_catalog.json"


def _read_cache() -> dict[str, Any]:
    path = _cache_path()
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_cache(value: dict[str, Any]) -> None:
    path = _cache_path()
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _model(identifier: str, name: str = "", *, reasoning: bool = False, context: int | None = None, kind: str = "text") -> dict[str, Any]:
    return {
        "id": str(identifier),
        "name": str(name or identifier),
        "reasoning": bool(reasoning),
        "context_length": context,
        "kind": kind,
    }


def _fetch_json(url: str, headers: dict[str, str] | None = None, timeout: float = 20) -> Any:
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _fetch_opencode() -> list[dict[str, Any]]:
    try:
        from audio import opencode_bin  # noqa: PLC0415
        binary = opencode_bin()
    except Exception:  # noqa: BLE001
        binary = ""
    if not binary:
        return []
    try:
        result = subprocess.run(
            [binary, "models"], capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    models = []
    for line in result.stdout.splitlines():
        value = line.strip()
        if not value.startswith("opencode-go/"):
            continue
        model = value.split("/", 1)[1].strip()
        if model:
            models.append(_model(model, model, reasoning=True))
    return models


def _fetch_openrouter() -> list[dict[str, Any]]:
    payload = _fetch_json(OPENROUTER_MODELS_URL)
    rows = payload.get("data") if isinstance(payload, dict) else payload
    models = []
    for item in rows if isinstance(rows, list) else []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        supported = [str(v) for v in (item.get("supported_parameters") or [])]
        modalities = item.get("architecture") or {}
        inputs = modalities.get("input_modalities") if isinstance(modalities, dict) else None
        kind = "text"
        if inputs and "text" not in inputs:
            continue
        models.append(_model(
            str(item["id"]), str(item.get("name") or item["id"]),
            reasoning="reasoning" in supported or "reasoning_effort" in supported,
            context=item.get("context_length"), kind=kind,
        ))
    return models


def _fetch_openai_compatible(url: str, secret: str) -> list[dict[str, Any]]:
    key = settings_store.get_secret(secret)
    if not key:
        return []
    payload = _fetch_json(url, {"Authorization": f"Bearer {key}"})
    rows = payload.get("data") if isinstance(payload, dict) else payload
    models = []
    for item in rows if isinstance(rows, list) else []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        identifier = str(item["id"])
        if any(marker in identifier for marker in ("embedding", "whisper", "tts", "dall-e", "moderation")):
            continue
        models.append(_model(identifier, identifier, reasoning=True))
    return models


def _fetch_ollama() -> list[dict[str, Any]]:
    payload = _fetch_json(OLLAMA_MODELS_URL, timeout=5)
    rows = payload.get("models") if isinstance(payload, dict) else []
    return [
        _model(str(item.get("name") or item.get("model")), str(item.get("name") or item.get("model")))
        for item in rows if isinstance(item, dict) and (item.get("name") or item.get("model"))
    ]


def _fetch_elevenlabs() -> list[dict[str, Any]]:
    key = settings_store.get_secret("elevenlabs")
    if not key:
        return []
    payload = _fetch_json(ELEVENLABS_MODELS_URL, {"xi-api-key": key})
    rows = payload if isinstance(payload, list) else []
    return [
        _model(str(item.get("model_id") or item.get("id")), str(item.get("name") or item.get("model_id")), kind="tts")
        for item in rows if isinstance(item, dict) and (item.get("model_id") or item.get("id"))
    ]


def _fetch(provider: str) -> tuple[list[dict[str, Any]], str]:
    if provider == "opencode-go":
        models = _fetch_opencode()
        return models, "opencode models"
    if provider == "openrouter":
        return _fetch_openrouter(), "openrouter /models"
    if provider == "openai":
        return _fetch_openai_compatible(OPENAI_MODELS_URL, "openai"), "openai /models"
    if provider == "groq":
        return _fetch_openai_compatible(GROQ_MODELS_URL, "groq"), "groq /models"
    if provider == "ollama":
        return _fetch_ollama(), "ollama /api/tags"
    if provider == "elevenlabs":
        return _fetch_elevenlabs(), "elevenlabs /v1/models"
    return list(_STATIC.get(provider, [])), "built-in catalog"


def catalog(provider: str, *, refresh: bool = False, stale_ok: bool = True) -> dict[str, Any]:
    provider = str(provider or "").strip()
    cache = _read_cache()
    entry = cache.get(provider) if isinstance(cache.get(provider), dict) else {}
    now = time.time()
    fetched = float(entry.get("fetched_at") or 0)
    if not refresh and entry and now - fetched < CATALOG_TTL:
        return {**entry, "stale": False, "provider": provider}
    error = ""
    models: list[dict[str, Any]] = []
    source = "built-in catalog"
    try:
        models, source = _fetch(provider)
    except Exception as exc:  # noqa: BLE001
        error = store.redact_text(str(exc))[:300]
        if entry and stale_ok:
            return {**entry, "stale": True, "error": error, "provider": provider}
    if models:
        known = {str(item.get("id")) for item in models}
        extras = [item for item in _STATIC.get(provider, []) if item.get("id") not in known]
        models = [*models, *extras]
        entry = {
            "provider": provider,
            "models": models,
            "source": source,
            "fetched_at": now,
            "stale": False,
            "error": error,
        }
        cache[provider] = entry
        try:
            _write_cache(cache)
        except OSError:
            pass
        return entry
    if entry and stale_ok:
        return {**entry, "stale": True, "error": error, "provider": provider}
    return {
        "provider": provider,
        "models": list(_STATIC.get(provider, [])),
        "source": "built-in catalog",
        "fetched_at": fetched or now,
        "stale": bool(error),
        "error": error,
    }


def clear_cache(provider: str) -> None:
    cache = _read_cache()
    if provider in cache:
        cache.pop(provider, None)
        try:
            _write_cache(cache)
        except OSError:
            pass


def model_ids(provider: str, *, refresh: bool = False) -> list[str]:
    return [str(item.get("id")) for item in catalog(provider, refresh=refresh).get("models", [])]


def provider_options() -> list[dict[str, Any]]:
    return [
        {
            "id": provider,
            **meta,
            "secret": meta.get("secret", ""),
            "configured": bool(settings_store.get_secret(meta["secret"]))
            if meta.get("secret") else True,
        }
        for provider, meta in PROVIDER_META.items()
    ]
