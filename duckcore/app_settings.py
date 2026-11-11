"""Local DuckSuite settings, storage report and model verification."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

from duckcore import __version__

MODEL_HASHES = {
    "lama": "1faef5301d78db7dda502fe59966957ec4b79dd64e16f03ed96913c7a4eb68d6",
}


def settings_path(data_root: Path | str) -> Path:
    return Path(data_root) / "settings.json"


def load(data_root: Path | str) -> dict[str, Any]:
    try:
        value = json.loads(settings_path(data_root).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        value = {}
    if not isinstance(value, dict):
        value = {}
    value.setdefault("language", "auto")
    # Removed in loop 9: an old file may still hold them, and they are dropped
    # on the next save rather than failing the load.
    value.pop("online_enabled", None)
    value.pop("online_endpoint", None)
    return value


def save(data_root: Path | str, value: dict[str, Any]) -> dict[str, Any]:
    path = settings_path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)
    return value


def _tree_bytes(path: Path) -> int:
    total = 0
    try:
        for root, _dirs, files in os.walk(path):
            for name in files:
                try:
                    total += (Path(root) / name).stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def fill_model_status(data_root: Path | str) -> dict[str, Any]:
    """The user's fill model folder: ready, or a plain reason it is not."""
    from duckcore.engine.textfill import custom

    folder = str(load(data_root).get("fill_model_path") or "").strip()
    if not folder:
        return {"path": "", "file": "", "ready": False, "problem": ""}
    reason = custom.problem(folder)
    path = custom.find_model(folder)
    return {
        "path": folder,
        "file": path.name if path is not None else "",
        "ready": reason is None,
        "problem": reason or "",
    }


def fill_device(data_root: Path | str) -> str:
    """The fill chip the user chose. One default: GPU. The render reads this."""
    stored = str(load(data_root).get("fill_device") or "gpu").strip().lower()
    return "cpu" if stored == "cpu" else "gpu"


def snapshot(data_root: Path | str) -> dict[str, Any]:
    root = Path(data_root)
    settings = load(root)
    usage = shutil.disk_usage(root)
    return {
        "version": __version__,
        "language": "auto",
        "translation": {
            "engine": str(settings.get("translation_engine") or "auto"),
            "custom_path": str(settings.get("translation_model_path") or ""),
        },
        "fill": {
            "device": fill_device(root),
            "model": fill_model_status(root),
        },
        "storage": {
            "data_root": str(root),
            "projects_bytes": _tree_bytes(root / "projects"),
            "models_bytes": _tree_bytes(root / "models"),
            "free_bytes": usage.free,
            "total_bytes": usage.total,
        },
    }


def update(data_root: Path | str, payload: dict[str, Any]) -> dict[str, Any]:
    current = load(data_root)
    if "translation_engine" in payload:
        engine = str(payload["translation_engine"] or "auto").strip().lower()
        if engine == "nllb":  # legacy setting from the removed pack
            engine = "auto"
        if engine not in {"auto", "custom"}:
            raise ValueError("Translation engine must be auto or custom.")
        current["translation_engine"] = engine
    if "fill_device" in payload:
        device = str(payload["fill_device"] or "cpu").strip().lower()
        if device not in {"cpu", "gpu"}:
            raise ValueError("Fill device must be cpu or gpu.")
        current["fill_device"] = device
    if "translation_model_path" in payload:
        current["translation_model_path"] = str(payload["translation_model_path"] or "").strip()[:2000]
    if "fill_model_path" in payload:
        folder = str(payload["fill_model_path"] or "").strip()[:2000]
        if folder:
            from duckcore.engine.textfill import custom

            reason = custom.problem(folder)
            if reason:
                raise ValueError(reason)
        current["fill_model_path"] = folder
    # DuckSuite always auto-detects language. Keep the field read-only.
    current["language"] = "auto"
    return save(data_root, current)


def verify_model(data_root: Path | str, model_id: str) -> dict[str, Any]:
    from duckcore.engine import textfill

    directory = textfill.models_dir(data_root)
    path = directory / textfill.MODEL_FILES.get(model_id, "")
    if not path.is_file():
        return {"ok": False, "model": model_id, "error": "Model file is missing.", "path": str(path)}
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    expected = MODEL_HASHES.get(model_id)
    return {
        "ok": expected is None or actual == expected,
        "model": model_id,
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": actual,
        "expected": expected or "",
    }
