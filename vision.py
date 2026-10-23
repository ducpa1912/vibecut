"""Local frame reader: Apple Vision OCR + face + attention saliency.

Compiles a tiny Swift helper on first use. Everything stays on this machine.
On non-macOS systems, or if Swift is unavailable, callers fall back to
center crops and no on-screen text.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

LOGGER = logging.getLogger("vibecut.vision")
ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "tools" / "vision_probe.swift"
BINARY = ROOT / "bin" / "vision_probe"
_checked = False
_ok = False
_lock = threading.Lock()


def _build() -> bool:
    global _checked, _ok
    if _checked:
        return _ok
    with _lock:
        if _checked:
            return _ok
        if sys.platform != "darwin" or not shutil.which("swiftc"):
            LOGGER.info("Apple Vision helper unavailable; using center crops.")
            _checked = True
            return False
        try:
            needs_build = (
                not BINARY.exists()
                or BINARY.stat().st_mtime < SOURCE.stat().st_mtime
            )
            if needs_build:
                BINARY.parent.mkdir(parents=True, exist_ok=True)
                LOGGER.info("Compiling Vision helper…")
                result = subprocess.run(
                    ["swiftc", "-O", "-swift-version", "5", str(SOURCE), "-o", str(BINARY)],
                    capture_output=True, text=True, timeout=180,
                )
                if result.returncode != 0:
                    LOGGER.warning("Vision helper compile failed: %s", result.stderr[-800:])
                    _checked = True
                    return False
            _ok = True
        except Exception as exc:
            LOGGER.warning("Vision helper unavailable: %s", exc)
            _ok = False
        _checked = True
        return _ok


def available() -> bool:
    return _build()


def probe_images(directory: Path, files: list[Path] | None = None) -> dict[str, dict]:
    """Return {filename: {text, faces, salient, width, height}}.

    Pass ``files`` to analyze only those stills. The helper reads a directory,
    so selected files are linked into a temporary directory first.
    """
    if not _build() or not directory.is_dir():
        return {}
    if files is None:
        jpgs = sorted(directory.glob("*.jpg"))
        target = directory
        cleanup = None
    else:
        jpgs = [path for path in files if path.is_file()]
        if not jpgs:
            return {}
        cleanup = tempfile.TemporaryDirectory(prefix=".vision-", dir=directory)
        target = Path(cleanup.name)
        for path in jpgs:
            try:
                os.link(path, target / path.name)
            except OSError:
                shutil.copy2(path, target / path.name)
    try:
        try:
            result = subprocess.run(
                [str(BINARY), str(target)],
                capture_output=True, text=True,
                timeout=max(180, len(jpgs) * 0.8),
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("Vision helper timed out on %d frames.", len(jpgs))
            return {}
        if result.returncode != 0:
            LOGGER.warning("Vision helper failed: %s", result.stderr[-800:])
            return {}
        output: dict[str, dict] = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if item.get("file"):
                output[item["file"]] = item
        if result.stderr.strip():
            LOGGER.debug("vision stderr: %s", result.stderr[-400:])
        return output
    finally:
        if cleanup:
            cleanup.cleanup()


def probe_image(path: Path) -> dict:
    return probe_images(path.parent, files=[path]).get(path.name, {})
