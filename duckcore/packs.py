"""Optional local model packs.

Downloads are data only: no executable code. Each pack has a fixed URL, size,
license and destination under the app data folder. The engine that consumes a
pack is selected by feature code; a pack never runs by itself.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
import urllib.request
from pathlib import Path

PACKS = (
    {
        "id": "tts-kokoro",
        "name": "Kokoro voice pack",
        "purpose": "voice",
        "detail": "Higher-quality local voices for voice-over and dub.",
        "size_bytes": 325_532_387,
        "license": "Apache-2.0",
        "filename": "kokoro-v1.0.onnx",
        "url": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
    },
    {
        "id": "speech-whisper",
        "name": "Whisper large-v3-turbo",
        "purpose": "speech",
        "detail": "Local speech model for languages Apple Speech does not cover.",
        "size_bytes": 1_613_977_612,
        "license": "MIT",
        "filename": "weights.safetensors",
        "url": "https://huggingface.co/mlx-community/whisper-large-v3-turbo/resolve/main/weights.safetensors",
    },
    {
        "id": "rewrite-qwen3",
        "name": "Qwen3 4B rewrite pack",
        "purpose": "rewrite",
        "detail": "Local rewrite model files. Apple Intelligence is used first; local engine wiring follows.",
        "size_bytes": 2_263_022_417,
        "license": "Apache-2.0",
        "filename": "model.safetensors",
        "url": "https://huggingface.co/mlx-community/Qwen3-4B-Instruct-2507-4bit/resolve/main/model.safetensors",
    },
    {
        "id": "separation-demucs",
        "name": "Demucs separation pack",
        "purpose": "separation",
        "detail": "Instrumental bed for dub. Review the weight terms before shipping.",
        "size_bytes": 84_141_911,
        "license": "MIT code; check weight terms",
        "filename": "955717e8-8726e21a.th",
        "url": "https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/955717e8-8726e21a.th",
    },
)

_LOCK = threading.Lock()
_PROGRESS: dict[str, dict] = {}


def _root(data_root: Path) -> Path:
    path = Path(data_root) / "models" / "packs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _entry(pack_id: str) -> dict:
    for pack in PACKS:
        if pack["id"] == pack_id:
            return pack
    raise KeyError(pack_id)


def _path(data_root: Path, pack: dict) -> Path:
    return _root(data_root) / pack["id"] / pack["filename"]


def status(data_root: Path) -> list[dict]:
    rows = []
    for pack in PACKS:
        path = _path(data_root, pack)
        progress = _PROGRESS.get(pack["id"]) or {}
        installed = path.is_file() and path.stat().st_size >= pack["size_bytes"] * 0.98
        rows.append({
            **{key: pack[key] for key in ("id", "name", "purpose", "detail", "size_bytes", "license")},
            "installed": installed,
            "downloaded_bytes": path.stat().st_size if path.is_file() else int(progress.get("bytes") or 0),
            "downloading": bool(progress.get("running")),
            "error": str(progress.get("error") or ""),
        })
    return rows


def start_download(data_root: Path, pack_id: str) -> dict:
    pack = _entry(pack_id)
    with _LOCK:
        current = _PROGRESS.get(pack_id) or {}
        if current.get("running"):
            return status(data_root)
        _PROGRESS[pack_id] = {"running": True, "bytes": 0, "error": ""}
    threading.Thread(
        target=_download, args=(Path(data_root), pack), daemon=True,
        name=f"duck-pack-{pack_id}",
    ).start()
    return status(data_root)


def _download(data_root: Path, pack: dict) -> None:
    target = _path(data_root, pack)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    try:
        with urllib.request.urlopen(pack["url"], timeout=60) as response, temporary.open("wb") as writer:
            total = int(response.headers.get("content-length") or pack["size_bytes"])
            done = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                writer.write(chunk)
                done += len(chunk)
                _PROGRESS[pack["id"]] = {
                    "running": True, "bytes": done,
                    "total": total or pack["size_bytes"], "error": "",
                }
        if temporary.stat().st_size < pack["size_bytes"] * 0.98:
            raise RuntimeError("download size does not match the manifest")
        temporary.replace(target)
        _PROGRESS[pack["id"]] = {"running": False, "bytes": target.stat().st_size, "error": ""}
    except Exception as exc:  # noqa: BLE001
        temporary.unlink(missing_ok=True)
        _PROGRESS[pack["id"]] = {"running": False, "bytes": 0, "error": str(exc)[:300]}


def remove(data_root: Path, pack_id: str) -> list[dict]:
    pack = _entry(pack_id)
    folder = _path(data_root, pack).parent
    shutil.rmtree(folder, ignore_errors=True)
    _PROGRESS.pop(pack_id, None)
    return status(data_root)
