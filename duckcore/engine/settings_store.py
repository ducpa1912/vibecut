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

#: No provider has a key: every engine DuckSuite runs is on this Mac.
_SECRET_ENV: dict[str, str] = {}


def settings_path() -> Path:
    return DATA / "settings.json"


def load_settings() -> dict[str, Any]:
    try:
        value = json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


