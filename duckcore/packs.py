"""Optional local model packs.

Downloads are data only: no executable code. Each pack has a fixed URL, size,
license and destination under the app data folder. The engine that consumes a
pack is selected by feature code; a pack never runs by itself.
"""

from __future__ import annotations

import hashlib
import threading
import urllib.request
from pathlib import Path

PACKS = (
    {
        "id": "tts-kokoro",
        "name": "Extra voice pack",
        "purpose": "voice",
        "detail": "Higher-quality local voices for voice-over and dub.",
        "size_bytes": 325_532_387,
        "license": "Apache-2.0",
        "filename": "kokoro-v1.0.onnx",
        # The publisher gives no hash for this release (GitHub asset digest is
        # empty, the release notes list none; checked 2026-11-16). Exact size
        # only; never a digest made from our own download.
        "sha256": "",
        "url": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
        "extra_files": [{
            "filename": "voices-v1.0.bin",
            "size_bytes": 28_214_398,
            "sha256": "",
            "url": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
        }],
    },
    {
        "id": "fill-lama-cpu",
        "name": "CPU fill engine",
        "purpose": "fill",
        "detail": "Runs AI fill on the CPU. The GPU engine is built in, so this is optional.",
        "size_bytes": 208_044_816,
        "license": "Apache-2.0",
        "filename": "lama_fp32.onnx",
        "dest": "fill",
        "sha256": "1faef5301d78db7dda502fe59966957ec4b79dd64e16f03ed96913c7a4eb68d6",
        "url": "https://huggingface.co/Carve/LaMa-ONNX/resolve/c3c0c9e468934d62e79c329e35d82dd09ff8c444/lama_fp32.onnx",
    },
    {
        "id": "speech-whisper",
        "name": "Speech pack · non-Apple languages",
        "purpose": "speech",
        "detail": "Local speech model for languages Apple Speech does not cover.",
        "size_bytes": 1_613_977_612,
        "license": "MIT",
        "filename": "weights.safetensors",
        "sha256": "951ed3fc1203e6a62467abb2144a96ce7eafca8fa77e3704fdb8635ff3e7f8a6",
        "url": "https://huggingface.co/mlx-community/whisper-large-v3-turbo/resolve/a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb/weights.safetensors",
        "extra_files": [{
            "filename": "config.json",
            "size_bytes": 268,
            # Not an LFS file: Hugging Face publishes its git blob SHA-1 only.
            "git_sha1": "6ac9a52a28f70a2e5681c250a470eca6e9c8cc3e",
            "url": "https://huggingface.co/mlx-community/whisper-large-v3-turbo/resolve/a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb/config.json",
        }],
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
        "sha256": pack.get("sha256", ""),
        "git_sha1": pack.get("git_sha1", ""),
    }]
    files.extend(pack.get("extra_files") or [])
    return files


def _folder(data_root: Path, pack: dict) -> Path:
    """Where a pack installs: its own folder, or a feature folder it declares."""
    dest = str(pack.get("dest") or "").strip().strip("/")
    if dest:
        folder = Path(data_root) / "models" / dest
    else:
        folder = _root(data_root) / pack["id"]
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _path(data_root: Path, pack: dict, filename: str = "") -> Path:
    return _folder(data_root, pack) / (filename or pack["filename"])


def installed_path(data_root: Path, pack_id: str) -> Path | None:
    """Return the pack folder only when every declared file is present."""
    try:
        pack = _entry(pack_id)
    except KeyError:
        return None
    folder = _folder(data_root, pack)
    for item in _files(pack):
        path = folder / item["filename"]
        if not path.is_file() or not _size_matches(path.stat().st_size, item):
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


DAMAGED = "The download was damaged. Try again."
STOPPED = "The download stopped. Check the connection and try again."


def _size_matches(size: int, item: dict) -> bool:
    return size == int(item["size_bytes"])


def verify_file(path: Path, item: dict) -> bool:
    """Exact size, then the publisher's digest when one exists."""
    if not path.is_file() or not _size_matches(path.stat().st_size, item):
        return False
    sha256 = str(item.get("sha256") or "").strip().lower()
    git_sha1 = str(item.get("git_sha1") or "").strip().lower()
    if sha256:
        digest = hashlib.sha256()
    elif git_sha1:
        digest = hashlib.sha1(f"blob {path.stat().st_size}\0".encode())
    else:
        return True
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest() == (sha256 or git_sha1)


def _download(data_root: Path, pack: dict) -> None:
    folder = _folder(data_root, pack)
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
            if not verify_file(temporary, item):
                raise ValueError(DAMAGED)
            temporary.replace(target)
        _PROGRESS[pack["id"]] = {"running": False, "bytes": done, "error": ""}
    except Exception as exc:  # noqa: BLE001
        for item in _files(pack):
            (folder / item["filename"]).unlink(missing_ok=True)
            (folder / item["filename"]).with_suffix(
                (folder / item["filename"]).suffix + ".part"
            ).unlink(missing_ok=True)
        error = DAMAGED if isinstance(exc, ValueError) else STOPPED
        _PROGRESS[pack["id"]] = {"running": False, "bytes": 0, "error": error, "detail": str(exc)[:300]}


def remove(data_root: Path, pack_id: str) -> list[dict]:
    pack = _entry(pack_id)
    folder = _folder(data_root, pack)
    for item in _files(pack):
        (folder / item["filename"]).unlink(missing_ok=True)
    try:
        folder.rmdir()  # only when nothing else lives there
    except OSError:
        pass
    _PROGRESS.pop(pack_id, None)
    return status(data_root)
