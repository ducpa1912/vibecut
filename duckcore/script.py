"""On-device script tools for DuckSuite.

The caption cues are the script. Translate or rewrite their text with the
prebuilt Swift helpers; keep the untouched source text on each cue for undo.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

from duckcore import edits

HELPERS = Path(os.environ.get("DUCK_HELPER_DIR", Path(__file__).resolve().parents[1] / "bin")).expanduser()
ROOT = Path(__file__).resolve().parents[1]


def _helper(name: str) -> Path | None:
    for path in (HELPERS / name, ROOT / "bin" / name):
        if path.is_file() and os.access(path, os.X_OK):
            return path
    return None


def _cues(edit: dict) -> list[dict]:
    track = edit.get("captions")
    cues = (track or {}).get("cues") or []
    rows = [cue for cue in cues if isinstance(cue, dict) and str(cue.get("text") or "").strip()]
    if not rows:
        raise ValueError("Generate captions first; they are the script.")
    for cue in rows:
        cue.setdefault("source_text", str(cue.get("text") or ""))
    return rows


def _run(name: str, payload: dict) -> list[str]:
    helper = _helper(name)
    if helper is None:
        raise ValueError(f"{name} is missing from the app bundle.")
    try:
        result = subprocess.run(
            [str(helper)], input=json.dumps(payload), text=True,
            capture_output=True, timeout=180,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"{name} could not run: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise ValueError(detail[-500:] or f"{name} is unavailable.")
    try:
        values = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name} returned unreadable text.") from exc
    if not isinstance(values, list) or len(values) != len(payload["lines"]):
        raise ValueError(f"{name} returned the wrong line count.")
    return [str(value) for value in values]


_FILLERS = (
    r"\b(?:um|uh|erm|you know|i mean|basically|actually|literally|kind of|sort of)\b[ ,]*",
)


def _basic_rewrite(text: str, mode: str) -> str:
    import re
    value = str(text or "").strip()
    for pattern in _FILLERS:
        value = re.sub(pattern, " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value).strip(" ,")
    if mode == "short":
        parts = re.split(r"(?<=[.!?])\s+", value)
        value = parts[0] if parts and len(parts[0]) >= 12 else value
    if mode == "punchy":
        value = re.sub(r"\b(?:very|really|quite|just|simply)\b\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\bis not\b", "isn't", value, flags=re.IGNORECASE)
        value = re.sub(r"\bdo not\b", "don't", value, flags=re.IGNORECASE)
    value = value.strip()
    return (value[:1].upper() + value[1:]) if value else value


def _array_from_text(text: str) -> list[str] | None:
    start = str(text or "").find("[")
    end = str(text or "").rfind("]")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(str(text)[start:end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    return value


def _rewrite_ollama(lines: list[str], mode: str) -> tuple[list[str], str]:
    base = os.environ.get("DUCK_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    model = os.environ.get("DUCK_OLLAMA_MODEL", "qwen3:4b")
    style = {
        "short": "Make every line shorter and tighter while keeping the meaning.",
        "punchy": "Make every line punchier and more direct while keeping the meaning.",
        "clean": "Remove filler words and false starts while keeping the meaning and tone.",
    }.get(mode, "Remove filler words and false starts.")
    prompt = (
        "You rewrite subtitle lines. " + style +
        " Keep the same line count. Return a JSON array of strings only, no commentary.\n" +
        "\n".join(f"{index + 1}. {line}" for index, line in enumerate(lines))
    )
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    request = urllib.request.Request(
        base + "/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        body = json.loads(response.read().decode("utf-8"))
    values = _array_from_text(str(body.get("response") or ""))
    if values is None or len(values) != len(lines):
        raise ValueError("The local rewrite model returned the wrong line count.")
    return values, f"ollama:{model}"


def translate(edit: dict, data_root: Path, *, target: str, source: str = "en") -> dict:
    target = str(target or "").strip().lower()
    if target not in {"en", "vi", "zh"}:
        raise ValueError("Choose English, Vietnamese or Chinese.")
    cues = _cues(edit)
    lines = [str(cue.get("source_text") or cue.get("text") or "") for cue in cues]
    values = _run("translate_apple", {
        "source": str(source or "en"),
        "target": target,
        "lines": lines,
    })
    for cue, value in zip(cues, values):
        cue["text"] = value
    edit["script"] = {
        "source_language": source,
        "target_language": target,
        "mode": "translated",
        "engine": "apple-translation",
    }
    edits.save_edit(edit, data_root)
    return edit["captions"]


def rewrite(edit: dict, data_root: Path, *, mode: str = "clean") -> dict:
    mode = str(mode or "clean").strip().lower()
    if mode not in {"clean", "short", "punchy"}:
        raise ValueError("Choose clean, short or punchy.")
    cues = _cues(edit)
    lines = [str(cue.get("source_text") or cue.get("text") or "") for cue in cues]
    engine = "apple-intelligence"
    fallback = False
    try:
        values = _run("rewrite_apple", {"mode": mode, "lines": lines})
    except ValueError:
        try:
            values, engine = _rewrite_ollama(lines, mode)
            fallback = True
        except Exception:
            values = [_basic_rewrite(line, mode) for line in lines]
            engine = "basic-cleanup"
            fallback = True
    for cue, value in zip(cues, values):
        cue["text"] = value
    edit["script"] = {
        **(edit.get("script") or {}),
        "mode": "rewritten",
        "rewrite": mode,
        "fallback": fallback,
        "engine": engine,
    }
    edits.save_edit(edit, data_root)
    return edit["captions"]


def reset(edit: dict, data_root: Path) -> dict:
    cues = _cues(edit)
    for cue in cues:
        source = cue.get("source_text")
        if source:
            cue["text"] = source
    edit["script"] = {**(edit.get("script") or {}), "mode": "original", "target_language": ""}
    edits.save_edit(edit, data_root)
    return edit["captions"]
