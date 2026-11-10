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
        "extra_files": [{
            "filename": "voices-v1.0.bin",
            "size_bytes": 28_214_398,
            "url": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
        }],
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
        "extra_files": [{
            "filename": "config.json",
            "size_bytes": 268,
            "url": "https://huggingface.co/mlx-community/whisper-large-v3-turbo/resolve/main/config.json",
        }],
    },
    {
        "id": "translation-nllb",
        "name": "NLLB-200 distilled 600M int8",
        "purpose": "translation",
        "detail": "Local translation for English, Vietnamese, Chinese and Japanese. CC-BY-NC-4.0: non-commercial use only.",
        "size_bytes": 622_595_991,
        "license": "CC-BY-NC-4.0 (non-commercial)",
        "filename": "model.bin",
        "url": "https://huggingface.co/JustFrederik/nllb-200-distilled-600M-ct2-int8/resolve/main/model.bin",
        "extra_files": [
            {
                "filename": "config.json",
                "size_bytes": 159,
                "url": "https://huggingface.co/JustFrederik/nllb-200-distilled-600M-ct2-int8/resolve/main/config.json",
            },
            {
                "filename": "sentencepiece.bpe.model",
                "size_bytes": 4_852_054,
                "url": "https://huggingface.co/JustFrederik/nllb-200-distilled-600M-ct2-int8/resolve/main/sentencepiece.bpe.model",
            },
            {
                "filename": "shared_vocabulary.txt",
                "size_bytes": 2_568_098,
                "url": "https://huggingface.co/JustFrederik/nllb-200-distilled-600M-ct2-int8/resolve/main/shared_vocabulary.txt",
            },
        ],
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


def _files(pack: dict) -> list[dict]:
    files = [{
        "filename": pack["filename"],
        "size_bytes": pack["size_bytes"],
        "url": pack["url"],
    }]
    files.extend(pack.get("extra_files") or [])
    return files


def _path(data_root: Path, pack: dict, filename: str = "") -> Path:
    return _root(data_root) / pack["id"] / (filename or pack["filename"])


def installed_path(data_root: Path, pack_id: str) -> Path | None:
    """Return the pack folder only when every declared file is present."""
    try:
        pack = _entry(pack_id)
    except KeyError:
        return None
    folder = Path(data_root) / "models" / "packs" / pack["id"]
    for item in _files(pack):
        path = folder / item["filename"]
        if not path.is_file() or path.stat().st_size < item["size_bytes"] * 0.98:
            return None
    return folder


def status(data_root: Path) -> list[dict]:
    rows = []
    for pack in PACKS:
        progress = _PROGRESS.get(pack["id"]) or {}
        files = _files(pack)
        total = sum(int(item["size_bytes"]) for item in files)
        downloaded = sum(
            _path(data_root, pack, item["filename"]).stat().st_size
            for item in files
            if _path(data_root, pack, item["filename"]).is_file()
        )
        rows.append({
            **{key: pack[key] for key in ("id", "name", "purpose", "detail", "size_bytes", "license")},
            "size_bytes": total,
            "installed": installed_path(data_root, pack["id"]) is not None,
            "downloaded_bytes": downloaded or int(progress.get("bytes") or 0),
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
    folder = _root(data_root) / pack["id"]
    folder.mkdir(parents=True, exist_ok=True)
    done = 0
    total = sum(int(item["size_bytes"]) for item in _files(pack))
    try:
        for item in _files(pack):
            target = folder / item["filename"]
            temporary = target.with_suffix(target.suffix + ".part")
            with urllib.request.urlopen(item["url"], timeout=60) as response, temporary.open("wb") as writer:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    writer.write(chunk)
                    done += len(chunk)
                    _PROGRESS[pack["id"]] = {
                        "running": True, "bytes": done,
                        "total": total, "error": "",
                    }
            if temporary.stat().st_size < item["size_bytes"] * 0.98:
                raise RuntimeError(f"{item['filename']} size does not match the manifest")
            temporary.replace(target)
        _PROGRESS[pack["id"]] = {"running": False, "bytes": done, "error": ""}
    except Exception as exc:  # noqa: BLE001
        for item in _files(pack):
            (folder / item["filename"]).with_suffix(
                (folder / item["filename"]).suffix + ".part"
            ).unlink(missing_ok=True)
        _PROGRESS[pack["id"]] = {"running": False, "bytes": 0, "error": str(exc)[:300]}


def remove(data_root: Path, pack_id: str) -> list[dict]:
    pack = _entry(pack_id)
    folder = _path(data_root, pack).parent
    shutil.rmtree(folder, ignore_errors=True)
    _PROGRESS.pop(pack_id, None)
    return status(data_root)
