#!/usr/bin/env python3
"""Release gate for the proprietary VibeCut build.

Checks, using only the standard library:

1. Direct Python requirements are not GPL/AGPL packages.
2. Installed metadata for each direct requirement reports no GPL/AGPL license.
3. Source files do not import xhs_get as a Python module.
4. The repo root does not contain vendored sidecar code or node_modules.
5. yt-dlp is a declared requirement and, when installed, meets the floor.

LGPL is reported as a warning because the linking question depends on the
distribution model; strong copyleft (GPL/AGPL) is a hard failure.

Usage:
    python3 scripts/check_proprietary_deps.py
    python3 scripts/check_proprietary_deps.py --all

Exit status: 0 clean, 1 findings. This is not legal advice.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENT_FILES = ("requirements.txt", "requirements-music.txt")
MIN_YTDLP = (2025, 10, 22)
SIDECAR_IMPORT_ROOTS = frozenset({"xhs_get", "xhsget"})
SIDECAR_PACKAGES = frozenset({"xhs-get", "xhsget", "xhs-get-api"})
SIDECAR_DIRS = ("xhs_get", "xhsget", "node_modules")
SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "data",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        "build",
        "dist",
        ".mypy_cache",
        ".ruff_cache",
    }
)

REQUIREMENT_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")
INLINE_COMMENT = re.compile(r"\s+#.*$")


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.warnings: list[str] = []
        self.notes: list[str] = []

    def fail(self, message: str) -> None:
        self.failures.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def note(self, message: str) -> None:
        self.notes.append(message)


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def parse_requirements(path: Path) -> list[tuple[str, int]]:
    """Return (distribution name, line number) for direct requirements."""
    entries: list[tuple[str, int]] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = INLINE_COMMENT.sub("", raw).strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        match = REQUIREMENT_NAME.match(line)
        if match:
            entries.append((match.group(1), number))
    return entries


def license_markers(dist: metadata.Distribution) -> list[str]:
    md = dist.metadata
    values: list[str] = []
    expression = md.get("License-Expression")
    if expression:
        values.append(expression)
    license_field = md.get("License")
    if license_field:
        values.append(license_field[:500])
    values.extend(
        item
        for item in (md.get_all("Classifier") or [])
        if item.startswith("License ::")
    )
    return values


def classify(values: list[str]) -> str:
    """Return AGPL, GPL, LGPL, OK, or UNKNOWN for license metadata."""
    text = " ".join(value for value in values if value).strip()
    lowered = text.lower()
    if not lowered or lowered in {"unknown", "none", "other/proprietary"}:
        return "UNKNOWN"
    if "affero" in lowered or re.search(r"(?<![a-z])agpl", lowered):
        return "AGPL"
    if "lgpl" in lowered or "lesser general public" in lowered:
        return "LGPL"
    if re.search(r"(?<![a-z])gpl", lowered) or "gnu general public license" in lowered:
        return "GPL"
    return "OK"


def short_license(values: list[str]) -> str:
    if not values:
        return "unknown"
    text = " ".join(" ".join(values).split())
    return text[:90]


def installed(name: str) -> metadata.Distribution | None:
    try:
        return metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return None


def version_tuple(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in re.split(r"[.\-+]", value):
        match = re.match(r"\d+", piece)
        if not match:
            break
        parts.append(int(match.group()))
    return tuple(parts)


def check_requirements(report: Report) -> set[str]:
    direct: set[str] = set()
    found_files = 0
    for filename in REQUIREMENT_FILES:
        path = ROOT / filename
        if not path.is_file():
            continue
        found_files += 1
        for name, line in parse_requirements(path):
            key = canonical(name)
            direct.add(key)
            if key in SIDECAR_PACKAGES:
                report.fail(
                    f"{filename}:{line}: sidecar package {name!r} must not be a VibeCut dependency."
                )
            dist = installed(name)
            if dist is None:
                report.warn(
                    f"{filename}:{line}: {name} is not installed; run pip install -r {filename}."
                )
                continue
            kind = classify(license_markers(dist))
            label = short_license(license_markers(dist))
            if kind in {"GPL", "AGPL"}:
                report.fail(
                    f"{filename}:{line}: {name} {dist.version} reports {kind} ({label})."
                )
            elif kind == "LGPL":
                report.warn(
                    f"{filename}:{line}: {name} {dist.version} reports LGPL ({label}); "
                    "review linking and notice duties before distribution."
                )
            elif kind == "UNKNOWN":
                report.warn(
                    f"{filename}:{line}: {name} {dist.version} has no usable license metadata."
                )
            else:
                report.note(f"{name} {dist.version}: {label}")
    if not found_files:
        report.fail("No requirements file found.")
    return direct


def check_ytdlp(report: Report, direct: set[str]) -> None:
    if "yt-dlp" not in direct:
        report.fail("requirements.txt does not declare yt-dlp.")
        return
    dist = installed("yt-dlp")
    if dist is None:
        return
    if version_tuple(dist.version) < MIN_YTDLP:
        report.fail(
            f"yt-dlp {dist.version} is below the documented floor "
            f"{'.'.join(str(part) for part in MIN_YTDLP)}; upgrade before release."
        )


def check_imports(report: Report) -> int:
    scanned = 0
    for path in ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        scanned += 1
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as exc:
            report.warn(f"{path.relative_to(ROOT)}: could not parse ({exc.msg}).")
            continue
        for node in ast.walk(tree):
            roots: list[str] = []
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue
                roots = [(node.module or "").split(".")[0]]
            for root in roots:
                if root in SIDECAR_IMPORT_ROOTS:
                    report.fail(
                        f"{path.relative_to(ROOT)}:{getattr(node, 'lineno', '?')}: "
                        f"imports sidecar module {root!r}."
                    )
    return scanned


def check_vendored(report: Report) -> None:
    for name in SIDECAR_DIRS:
        if (ROOT / name).exists():
            report.fail(f"Repo root contains vendored path {name!r}; keep sidecars out of the build.")
    for path in ROOT.rglob("node_modules"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        report.fail(f"Vendored Node directory found: {path.relative_to(ROOT)}.")


def check_all_installed(report: Report) -> None:
    seen: set[str] = set()
    for dist in metadata.distributions():
        name = dist.metadata.get("Name")
        if not name:
            continue
        key = canonical(name)
        if key in seen:
            continue
        seen.add(key)
        kind = classify(license_markers(dist))
        if kind in {"GPL", "AGPL"}:
            report.fail(f"Installed environment: {name} {dist.version} reports {kind}.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--all",
        action="store_true",
        help="also fail on any GPL/AGPL distribution in the installed environment",
    )
    args = parser.parse_args()

    report = Report()
    direct = check_requirements(report)
    check_ytdlp(report, direct)
    scanned = check_imports(report)
    check_vendored(report)
    if args.all:
        check_all_installed(report)

    print("VibeCut proprietary dependency audit")
    print(f"  repo: {ROOT}")
    print(f"  direct requirements: {len(direct)}")
    print(f"  Python files scanned for sidecar imports: {scanned}")
    for note in report.notes:
        print(f"  [ok]   {note}")
    for warning in report.warnings:
        print(f"  [warn] {warning}")
    for failure in report.failures:
        print(f"  [FAIL] {failure}")
    if report.failures:
        print("result: FAIL")
        return 1
    print(f"result: PASS ({len(report.warnings)} warning(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
