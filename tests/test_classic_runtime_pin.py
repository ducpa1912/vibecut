"""Classic runs on its own copy of the shared backend, changed only on purpose.

Studio moves its code on its own branch. A Studio change reaches Classic only
as a deliberate port: the file changes here with Classic tests, and the manifest
records it in the same commit (scripts/pin-classic-runtime.py).
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "classic_runtime" / "manifest.json").read_text("utf-8"))
ROWS = {row["path"]: row for row in MANIFEST["copies"]}
PACKAGES = ("admin", "textfill", "url_ingest", "tools")
HOW = "resync copy or bump version: scripts/pin-classic-runtime.py --source '<why>' <file>"


def _runtime_files() -> set[str]:
    found = {path.name for path in ROOT.glob("*.py")} - {"routes_classic.py"}
    for package in PACKAGES:
        found.update(
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / package).rglob("*")
            if path.is_file() and path.suffix in {".py", ".swift"}
        )
    found.update(name for name in ("requirements.txt", "requirements-optional.txt")
                 if (ROOT / name).is_file())
    return found


def test_every_pinned_file_matches_its_hash():
    changed = [
        path for path, row in ROWS.items()
        if not (ROOT / path).is_file()
        or hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != row["sha256"]
    ]
    assert not changed, f"{changed}: {HOW}"


def test_no_runtime_file_is_unpinned():
    unpinned = sorted(_runtime_files() - set(ROWS))
    assert not unpinned, f"{unpinned}: {HOW}"


def test_every_row_says_where_it_came_from():
    for row in MANIFEST["copies"]:
        assert row["source"], row["path"]
        assert row["feature_version"], row["path"]


def test_the_core_modules_are_in_the_baseline():
    for path in (
        "render.py", "compose_render.py", "audio.py", "tts.py", "music.py", "stt.py",
        "pipeline.py", "captions.py", "detect.py", "cleanup.py", "edits.py",
        "settings_store.py", "job_queue.py", "artifacts.py", "rights.py",
        "textfill/__init__.py", "app.py",
    ):
        assert path in ROWS, path


def test_no_hidden_reach_outside_this_tree():
    """Copies are allowed; imports of Studio's packages and other checkouts are not."""
    files = [path for path in _runtime_files() | {"routes_classic.py"} if path.endswith(".py")]
    for path in files:
        text = (ROOT / path).read_text("utf-8")
        for needle in ("drop_eval/", "vibecut-studio", "vibecut-voice-room", "lanes/studio", "lanes/voice"):
            assert needle not in text, f"{path} points at another lane: {needle}"
        for node in ast.walk(ast.parse(text)):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and not node.level:
                names = [node.module or ""]
            for name in names:
                assert name.split(".")[0] not in {"features", "core"}, f"{path} imports {name}"


def test_rights_flow_is_still_here():
    import rights

    assert callable(rights.may_import)
