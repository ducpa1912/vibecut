"""Workflow model-route configuration for VibeCut.

Each AI worker has an ordered fallback list. The admin UI edits this shape; the
runtime resolves it before each provider call. Defaults preserve the existing
OpenCode Go -> OpenRouter -> local/rules behavior.
"""

from __future__ import annotations

import copy
from typing import Any, Mapping

MAX_ROUTES = 6
REASONING_VALUES = ("none", "low", "medium", "high", "max")
TEXT_PROVIDERS = ("opencode-go", "openrouter", "local-mlx", "ollama")
TTS_PROVIDERS = ("minimax", "openrouter", "local")
MUSIC_PROVIDERS = ("minimax", "openrouter")
STT_PROVIDERS = ("auto", "apple", "whisper", "groq", "openai", "deepgram")

WORKFLOW_LABELS = {
    "story_brief": "Story brief",
    "rewrite": "Script rewrite",
    "translate": "Translation",
    "hook_rank": "Hook ranking",
    "tts": "Voice-over",
    "music": "Music generation",
    "stt": "Transcription",
}

WORKFLOW_KIND = {
    "story_brief": "text",
    "rewrite": "text",
    "translate": "text",
    "hook_rank": "text",
    "tts": "tts",
    "music": "music",
    "stt": "stt",
}

WORKFLOW_PROVIDERS = {
    "story_brief": TEXT_PROVIDERS,
    "rewrite": TEXT_PROVIDERS,
    "translate": ("opencode-go", "openrouter", "ollama"),
    "hook_rank": ("opencode-go", "openrouter", "ollama"),
    "tts": TTS_PROVIDERS,
    "music": MUSIC_PROVIDERS,
    "stt": STT_PROVIDERS,
}

_TEXT_ROUTES = [
    {"provider": "opencode-go", "model": "deepseek-v4.1-flash"},
    {"provider": "openrouter", "model": "deepseek/deepseek-v4.1-flash"},
    {"provider": "local-mlx", "model": "mlx-community/Qwen2.5-3B-Instruct-4bit"},
]

DEFAULT_WORKFLOWS: dict[str, dict[str, Any]] = {
    "story_brief": {
        "routes": copy.deepcopy(_TEXT_ROUTES),
        "reasoning": "low",
        "max_output_tokens": 3200,
        "timeout_s": 300,
    },
    "rewrite": {
        "routes": copy.deepcopy(_TEXT_ROUTES),
        "reasoning": "low",
        "max_output_tokens": 3200,
        "timeout_s": 300,
    },
    "translate": {
        "routes": copy.deepcopy(_TEXT_ROUTES[:2]),
        "reasoning": "low",
        "max_output_tokens": 2500,
        "timeout_s": 300,
    },
    "hook_rank": {
        "routes": copy.deepcopy(_TEXT_ROUTES[:2]),
        "reasoning": "low",
        "max_output_tokens": 1600,
        "timeout_s": 180,
    },
    "tts": {
        "routes": [{"provider": "minimax", "model": "speech-2.8-turbo"}],
        "reasoning": "",
        "max_output_tokens": 0,
        "timeout_s": 120,
    },
    "music": {
        "routes": [{"provider": "minimax", "model": "music-3.0"}],
        "reasoning": "",
        "max_output_tokens": 0,
        "timeout_s": 600,
    },
    "stt": {
        "routes": [{"provider": "auto", "model": "mlx-community/whisper-small-mlx"}],
        "reasoning": "",
        "max_output_tokens": 0,
        "timeout_s": 300,
    },
}


def default_workflows() -> dict[str, dict[str, Any]]:
    return copy.deepcopy(DEFAULT_WORKFLOWS)


def _int(value: Any, default: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _normalize_route(workflow: str, raw: Any) -> dict[str, str] | None:
    if not isinstance(raw, Mapping):
        return None
    allowed = WORKFLOW_PROVIDERS.get(workflow, ())
    provider = str(raw.get("provider") or "").strip().lower()
    model = str(raw.get("model") or "").strip()
    if provider not in allowed:
        return None
    if not model or len(model) > 240:
        return None
    return {"provider": provider, "model": model}


def normalize_workflow(workflow: str, raw: Any) -> dict[str, Any]:
    default = DEFAULT_WORKFLOWS.get(workflow, {})
    value = raw if isinstance(raw, Mapping) else {}
    kind = WORKFLOW_KIND.get(workflow, "text")
    if kind == "text":
        default_reasoning = str(default.get("reasoning") or "low")
        reasoning = str(value.get("reasoning") or default_reasoning).lower()
        if reasoning not in REASONING_VALUES:
            reasoning = default_reasoning
    else:
        reasoning = ""
    routes_raw = value.get("routes")
    if not isinstance(routes_raw, list):
        routes_raw = default.get("routes") or []
    routes = []
    for item in routes_raw[:MAX_ROUTES]:
        route = _normalize_route(workflow, item)
        if route and route not in routes:
            routes.append(route)
    if not routes and default.get("routes"):
        routes = copy.deepcopy(default["routes"])
    return {
        "routes": routes,
        "reasoning": reasoning,
        "max_output_tokens": _int(
            value.get("max_output_tokens"),
            int(default.get("max_output_tokens") or 3200),
            64 if kind == "text" else 0,
            128000,
        ),
        "timeout_s": _int(
            value.get("timeout_s"),
            int(default.get("timeout_s") or 300),
            10,
            3600,
        ),
    }


def normalize_workflows(raw: Any) -> dict[str, dict[str, Any]]:
    source = raw if isinstance(raw, Mapping) else {}
    result: dict[str, dict[str, Any]] = {}
    for name in DEFAULT_WORKFLOWS:
        result[name] = normalize_workflow(name, source.get(name))
    return result


def effective(
    workflows: Mapping[str, Any] | None,
    workflow: str,
) -> dict[str, Any]:
    normalized = normalize_workflows(workflows)
    return normalized.get(workflow) or normalize_workflow(workflow, {})


def routes(workflows: Mapping[str, Any] | None, workflow: str) -> list[dict[str, str]]:
    return list(effective(workflows, workflow).get("routes") or [])
