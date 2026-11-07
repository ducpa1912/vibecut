"""Small local settings store for DuckSuite.

No cloud provider keys are required for the local app. Secrets are read from the
environment only; the final Mac app keeps any future secret in Keychain through
the Swift shell.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DATA = Path(
    os.environ.get(
        "DUCK_DATA",
        Path.home() / "Library" / "Application Support" / "DuckSuite",
    )
).expanduser()

_SECRET_ENV = {
    "openrouter": "OPENROUTER_API_KEY",
    "groq": "GROQ_API_KEY",
    "deepgram": "DEEPGRAM_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "elevenlabs": "ELEVENLABS_API_KEY",
}


def settings_path() -> Path:
    return DATA / "settings.json"


def load_settings() -> dict[str, Any]:
    try:
        value = json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def save_settings(value: dict[str, Any]) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def get_secret(name: str) -> str:
    env_name = _SECRET_ENV.get(str(name or "").strip().lower())
    return os.environ.get(env_name, "") if env_name else ""
