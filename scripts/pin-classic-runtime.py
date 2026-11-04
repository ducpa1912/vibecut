#!/usr/bin/env python3
"""Keep classic_runtime/manifest.json in step with Classic's copy of shared code.

Classic runs on its own copy of the shared backend. A change to one of these
files is deliberate: it is recorded here, in the same commit, with where it
came from. tests/test_classic_runtime_pin.py fails on anything else.

  scripts/pin-classic-runtime.py --source "studio abc1234: why" render.py audio.py
  scripts/pin-classic-runtime.py --source "new module: why" new_module.py
  scripts/pin-classic-runtime.py --init COMMIT    # rebuild the whole baseline
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "classic_runtime" / "manifest.json"
PACKAGES = ("admin", "textfill", "url_ingest", "tools")
EXTRA = ("requirements.txt", "requirements-optional.txt")
# Classic's own: changing it is ordinary lane work, not a port.
OWNED = {"routes_classic.py"}
SOURCES = {"textfill": "studio 7ce8dcf, verbatim"}


def pinned_paths() -> list[str]:
    paths = {path.name for path in ROOT.glob("*.py")} - OWNED
    for package in PACKAGES:
        for path in (ROOT / package).rglob("*"):
            if path.is_file() and path.suffix in {".py", ".swift"}:
                paths.add(path.relative_to(ROOT).as_posix())
    paths.update(name for name in EXTRA if (ROOT / name).is_file())
    return sorted(paths)


def digest(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def _bump(version: str) -> str:
    major, minor, patch = version.split(".")
    return f"{major}.{minor}.{int(patch) + 1}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--init", metavar="COMMIT")
    parser.add_argument("--source", default="")
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()

    if args.init:
        copies = [
            {
                "path": path,
                "source": SOURCES.get(path.split("/")[0], f"classic {args.init}"),
                "sha256": digest(path),
                "feature_version": "1.0.0",
            }
            for path in pinned_paths()
        ]
        data = {"baseline_commit": args.init, "copies": copies}
    else:
        if not args.source or not args.paths:
            parser.error("name the files and say where the change came from with --source")
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        rows = {row["path"]: row for row in data["copies"]}
        for path in args.paths:
            if path in rows:
                rows[path].update(
                    source=args.source,
                    sha256=digest(path),
                    feature_version=_bump(rows[path]["feature_version"]),
                )
            elif path in pinned_paths():
                rows[path] = {
                    "path": path, "source": args.source,
                    "sha256": digest(path), "feature_version": "1.0.0",
                }
            else:
                parser.error(f"{path} is not shared runtime code")
        data["copies"] = [rows[key] for key in sorted(rows)]
    MANIFEST.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    print(f"{len(data['copies'])} files pinned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
