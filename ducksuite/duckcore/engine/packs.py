"""Minimal pack lookup for DuckSuite.

Studio's pack installer downloaded wheels and executables. DuckSuite does not
download code. This module only finds an already-installed local tool.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT_ENV = "DUCK_PACKS_ROOT"


def find_command(kind: str, name: str, root: str | Path | None = None) -> Path | None:
    base = Path(root).expanduser() if root else None
    candidates = []
    if base is not None:
        candidates.extend([
            base / name,
            base / kind / name,
            base / kind / "bin" / name,
        ])
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    found = shutil.which(name)
    return Path(found) if found else None
