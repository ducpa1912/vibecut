#!/usr/bin/env python3
"""Pin the shared backend this lane runs on.

Voice Room keeps its own copy of every shared module, in place on the
``voice-room`` branch. ``voice_runtime_manifest.json`` records each file's
sha256, and ``tests/test_voice_runtime_pin.py`` fails on any change that was
not marked here. A Studio change reaches this lane only as a deliberate port.

    python3 scripts/voice_runtime_pin.py --check
    python3 scripts/voice_runtime_pin.py --mark audio.py --note "Port the X fix from Studio"
    python3 scripts/voice_runtime_pin.py --add new_module.py --note "Needed by the Y route"
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "voice_runtime_manifest.json"
#: Where the import walk starts: the server and the lane's own check script.
ENTRY_POINTS = ("app.py", "scripts/voice_live_check.py")
#: Calls that import by name; a string literal argument counts as an import.
DYNAMIC_IMPORTS = frozenset({"__import__", "import_module"})
#: Written for this lane, so they change freely and are never pinned.
OWNED_MODULES = frozenset({
    "routes_voice_clone.py",
    "voice_audio.py",
    "voice_errors.py",
    "voice_persona.py",
    "voice_readiness.py",
    "voice_reference.py",
    "voice_takes.py",
})
#: Shared files that are not Python imports but that the lane cannot run without.
PINNED_FILES = (
    "requirements.txt",
    "scripts/lane-env.sh",
    "scripts/ship-lane.sh",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _imported_names(path: Path) -> set[str]:
    """Every absolute import in a file, including those inside functions."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_bytes(), filename=str(path))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
        elif (
            isinstance(node, ast.Call)
            and getattr(node.func, "id", getattr(node.func, "attr", "")) in DYNAMIC_IMPORTS
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            names.add(node.args[0].value)
    return names


def _local_file(name: str) -> str | None:
    """The repo file behind an import name, or None for a third-party module."""
    base = ROOT.joinpath(*name.split("."))
    if base.with_suffix(".py").is_file():
        return base.with_suffix(".py").relative_to(ROOT).as_posix()
    if (base / "__init__.py").is_file():
        return (base / "__init__.py").relative_to(ROOT).as_posix()
    return None


def runtime_modules() -> set[str]:
    """Repo Python files reachable from the entry points, entry points included."""
    seen: set[str] = set()
    todo = list(ENTRY_POINTS)
    while todo:
        relative = todo.pop()
        if relative in seen:
            continue
        seen.add(relative)
        for name in _imported_names(ROOT / relative):
            local = _local_file(name)
            if local and local not in seen:
                todo.append(local)
    return seen


def _head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True,
    ).strip()


def load() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def save(manifest: dict) -> None:
    manifest["copies"].sort(key=lambda entry: entry["path"])
    MANIFEST.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )


def _entry(relative: str, baseline: str) -> dict:
    return {
        "path": relative,
        "baseline": baseline,
        "sha256": sha256(ROOT / relative),
        "lane_version": "1.0.0",
        "changes": [],
    }


def problems(manifest: dict) -> list[str]:
    """Each file that changed unmarked, went missing, or is not pinned at all."""
    found: list[str] = []
    pinned = {entry["path"]: entry for entry in manifest["copies"]}
    for relative, entry in sorted(pinned.items()):
        path = ROOT / relative
        if not path.is_file():
            found.append(f"{relative}: missing. Restore the copy.")
        elif sha256(path) != entry["sha256"]:
            found.append(
                f"{relative}: changed without a mark. Resync the copy, or run "
                f'scripts/voice_runtime_pin.py --mark {relative} --note "why".'
            )
    for relative in sorted(runtime_modules() - set(pinned) - OWNED_MODULES):
        found.append(
            f"{relative}: runs in this lane but is not pinned. Run "
            f'scripts/voice_runtime_pin.py --add {relative} --note "why".'
        )
    return found


def _bump(version: str) -> str:
    major, minor, patch = (int(part) for part in version.split("."))
    return f"{major}.{minor}.{patch + 1}"


def mark(manifest: dict, relative: str, note: str) -> None:
    for entry in manifest["copies"]:
        if entry["path"] == relative:
            entry["sha256"] = sha256(ROOT / relative)
            entry["lane_version"] = _bump(entry["lane_version"])
            entry["changes"].append({
                "date": date.today().isoformat(),
                "from_commit": _head(),
                "note": note,
            })
            return
    raise SystemExit(f"{relative} is not pinned. Use --add.")


def init() -> dict:
    baseline = _head()
    paths = (runtime_modules() - OWNED_MODULES) | set(PINNED_FILES)
    return {
        "version": 1,
        "rule": (
            "Voice Room's own copy of the shared backend. Change a file here only as "
            "a deliberate port with Voice Room tests, then mark it with "
            "scripts/voice_runtime_pin.py. Never import Studio's features or core."
        ),
        "baseline_commit": baseline,
        "owned": sorted(OWNED_MODULES),
        "copies": [_entry(path, baseline) for path in sorted(paths)],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--init", action="store_true", help="Write the first baseline.")
    parser.add_argument("--mark", metavar="PATH")
    parser.add_argument("--add", metavar="PATH")
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    if args.init:
        if MANIFEST.exists():
            raise SystemExit("The baseline already exists. Use --mark or --add.")
        save(init())
    elif args.mark or args.add:
        if not args.note.strip():
            raise SystemExit("Say why with --note.")
        manifest = load()
        if args.add:
            entry = _entry(args.add, _head())
            entry["changes"].append({
                "date": date.today().isoformat(),
                "from_commit": _head(),
                "note": args.note.strip(),
            })
            manifest["copies"].append(entry)
        else:
            mark(manifest, args.mark, args.note.strip())
        save(manifest)
    found = problems(load())
    for line in found:
        print(line, file=sys.stderr)
    if not found:
        print(f"{len(load()['copies'])} files match the manifest.")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
