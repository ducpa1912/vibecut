"""Optional model packs: manifest, SHA-256 verification, install and remove.

VibeCut ships without model weights. The three optional packs are downloaded
from VibeCut's release host, verified against a pinned SHA-256, and installed
under Application Support:

* **Speech Pack** — ``mlx``, ``mlx-whisper`` and Whisper large-v3-turbo;
* **Voice Pack** — ``onnxruntime``, ``kokoro-onnx`` and Kokoro v1.0/v1.1-zh;
* **Separation Pack** — CPU/MPS ``torch``, ``demucs`` and HTDemucs.

Nothing here imports an engine or touches the network unless ``install_pack``
is given a pack whose manifest entry has an HTTP(S) URL. Tests use a local
archive and a temporary root.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

MANIFEST_SCHEMA = 1
INSTALL_META = ".vibecut-pack.json"
MANIFEST_ENV = "VIBECUT_PACK_MANIFEST"
ROOT_ENV = "VIBECUT_PACKS_DIR"
PACK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")

BUILTIN_MANIFEST: dict[str, Any] = {
    "schema": MANIFEST_SCHEMA,
    "packs": [
        {
            "id": "speech",
            "name": "Speech Pack",
            "version": "1.0.0",
            "size_bytes": 1_900_000_000,
            "sha256": "",
            "url": "",
            "contents": ["mlx", "mlx-whisper", "Whisper large-v3-turbo"],
        },
        {
            "id": "voice",
            "name": "Voice Pack",
            "version": "1.0.0",
            "size_bytes": 800_000_000,
            "sha256": "",
            "url": "",
            "contents": [
                "onnxruntime", "kokoro-onnx", "Kokoro v1.0", "Kokoro v1.1-zh",
                "DeepFilterNet 3 (deep-filter)",
            ],
        },
        {
            "id": "separation",
            "name": "Separation Pack",
            "version": "1.0.0",
            "size_bytes": 800_000_000,
            "sha256": "",
            "url": "",
            "contents": [
                "torch (CPU/MPS)", "demucs", "HTDemucs", "HTDemucs FT",
                "audio-separator", "Mel-Band RoFormer",
            ],
        },
    ],
}


class PackError(Exception):
    """A pack could not be read, verified, installed or removed."""


def _validate_manifest(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise PackError("Pack manifest must be a JSON object.")
    if int(raw.get("schema") or 0) != MANIFEST_SCHEMA:
        raise PackError(f"Unsupported pack manifest schema: {raw.get('schema')!r}.")
    packs = raw.get("packs")
    if not isinstance(packs, list) or not packs:
        raise PackError("Pack manifest needs a non-empty 'packs' list.")
    seen: set[str] = set()
    clean: list[dict[str, Any]] = []
    for item in packs:
        if not isinstance(item, Mapping):
            raise PackError("Every pack entry must be an object.")
        pack_id = str(item.get("id") or "").strip()
        if not PACK_ID_RE.match(pack_id):
            raise PackError(f"Invalid pack id: {pack_id!r}.")
        if pack_id in seen:
            raise PackError(f"Duplicate pack id: {pack_id}.")
        seen.add(pack_id)
        name = str(item.get("name") or "").strip()
        if not name:
            raise PackError(f"Pack {pack_id!r} needs a name.")
        version = str(item.get("version") or "").strip()
        if not version:
            raise PackError(f"Pack {pack_id!r} needs a version.")
        try:
            size = int(item.get("size_bytes") or 0)
        except (TypeError, ValueError) as exc:
            raise PackError(f"Pack {pack_id!r} has an invalid size.") from exc
        if size < 0:
            raise PackError(f"Pack {pack_id!r} has a negative size.")
        sha = str(item.get("sha256") or "").strip().lower()
        if sha and not SHA256_RE.match(sha):
            raise PackError(f"Pack {pack_id!r} has an invalid SHA-256.")
        url = str(item.get("url") or "").strip()
        contents = item.get("contents")
        if contents is not None and not isinstance(contents, list):
            raise PackError(f"Pack {pack_id!r} 'contents' must be a list.")
        clean.append({
            "id": pack_id,
            "name": name,
            "version": version,
            "size_bytes": size,
            "sha256": sha,
            "url": url,
            "contents": [str(value) for value in (contents or [])],
        })
    return {"schema": MANIFEST_SCHEMA, "packs": clean}


def manifest(path: str | Path | Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return the active pack manifest, optionally from a JSON file or mapping."""
    if isinstance(path, Mapping):
        return _validate_manifest(path)
    target = Path(path) if path is not None else None
    if target is None:
        env = os.environ.get(MANIFEST_ENV)
        target = Path(env).expanduser() if env else None
    if target is None:
        return _validate_manifest(BUILTIN_MANIFEST)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackError(f"Could not read pack manifest: {exc}") from exc
    return _validate_manifest(raw)


def packs_root(root: str | Path | None = None) -> Path:
    """Application Support pack directory, or an explicit test root."""
    if root is not None:
        return Path(root).expanduser().resolve()
    env = os.environ.get(ROOT_ENV)
    if env:
        return Path(env).expanduser().resolve()
    home = Path.home()
    if os.uname().sysname == "Darwin":
        base = home / "Library" / "Application Support" / "VibeCut"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share") / "VibeCut"
    return (base / "packs").resolve()


def pack_dir(pack_id: str, root: str | Path | None = None) -> Path:
    pack_id = str(pack_id or "").strip()
    if not PACK_ID_RE.match(pack_id):
        raise PackError(f"Invalid pack id: {pack_id!r}.")
    base = packs_root(root)
    return (base / pack_id).resolve()


def installed_dir(pack_id: str, root: str | Path | None = None) -> Path | None:
    """Return an installed pack directory, or ``None`` when it is absent.

    A directory is considered installed when it exists, is not a symlink and
    is non-empty. The install metadata file is not required so a manually
    staged or development pack works the same way as an installer-created one.
    """
    directory = pack_dir(pack_id, root)
    if not directory.is_dir() or directory.is_symlink():
        return None
    try:
        next(directory.iterdir())
    except StopIteration:
        return None
    except OSError:
        return None
    return directory


def find_asset(
    pack_id: str,
    *relative: str,
    root: str | Path | None = None,
) -> Path | None:
    """Find a file inside an installed pack.

    Each candidate is tried under the pack root and under ``bin/`` and
    ``runtime/bin/`` so both flat archives and a Unix-style runtime layout work.
    """
    base = installed_dir(pack_id, root)
    if base is None:
        return None
    for candidate in relative:
        wanted = str(candidate or "").strip()
        if not wanted:
            continue
        for prefix in ("", "bin", "runtime/bin"):
            path = base / prefix / wanted if prefix else base / wanted
            if path.is_file() and not path.is_symlink():
                return path
    return None


def find_dir(
    pack_id: str,
    *relative: str,
    root: str | Path | None = None,
) -> Path | None:
    """Find a directory inside an installed pack (``""`` means its root)."""
    base = installed_dir(pack_id, root)
    if base is None:
        return None
    for candidate in relative:
        wanted = str(candidate or "").strip()
        target = base if not wanted else base / wanted
        if target.is_dir() and not target.is_symlink():
            return target
    return None


def find_command(
    pack_id: str,
    *names: str,
    root: str | Path | None = None,
) -> Path | None:
    """Find an executable inside an installed pack."""
    found = find_asset(pack_id, *names, root=root)
    if found is None:
        return None
    return found if os.access(found, os.X_OK) else None


def verify_sha256(path: str | Path, expected: str) -> str:
    """Stream a file through SHA-256 and compare it to the pinned digest."""
    target = Path(path)
    expected = str(expected or "").strip().lower()
    if not SHA256_RE.match(expected):
        raise PackError("Pack manifest has no valid SHA-256 pin.")
    digest = hashlib.sha256()
    try:
        with target.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise PackError(f"Could not read pack archive: {exc}") from exc
    actual = digest.hexdigest()
    if actual != expected:
        raise PackError(
            f"Pack checksum mismatch: expected {expected}, got {actual}."
        )
    return actual


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _spec(pack_id: str, data: Mapping[str, Any] | None) -> dict[str, Any]:
    pack_id = str(pack_id or "").strip()
    for item in (data or manifest()).get("packs") or []:
        if item["id"] == pack_id:
            return dict(item)
    raise PackError(f"Unknown pack: {pack_id!r}.")


def _download(url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "VibeCut pack installer"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, \
                destination.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    except Exception as exc:  # noqa: BLE001
        raise PackError(f"Pack download failed: {exc}") from exc
    return destination


def _source_archive(
    spec: Mapping[str, Any], archive: str | Path | None, scratch: Path,
) -> tuple[Path, bool]:
    if archive is not None:
        path = Path(archive).expanduser()
        if not path.is_file():
            raise PackError(f"Pack archive not found: {path}")
        return path, False
    url = str(spec.get("url") or "").strip()
    if not url:
        raise PackError("This pack has no download URL yet.")
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme == "file":
        path = Path(urllib.request.url2pathname(parsed.path))
        if not path.is_file():
            raise PackError(f"Pack archive not found: {path}")
        return path, False
    if parsed.scheme in {"http", "https"}:
        suffix = "".join(Path(parsed.path).suffixes) or ".zip"
        return _download(url, scratch / f"download{suffix}"), True
    raise PackError(f"Unsupported pack URL: {url}")


def _safe_member(name: str) -> PurePosixPath:
    text = str(name or "").replace("\\", "/")
    path = PurePosixPath(text)
    if not text or path.is_absolute() or ".." in path.parts:
        raise PackError(f"Unsafe path in pack archive: {name!r}.")
    return path


def _extract_zip(source: Path, destination: Path) -> None:
    try:
        with zipfile.ZipFile(source) as archive:
            for info in archive.infolist():
                _safe_member(info.filename)
                mode = (info.external_attr >> 16) & 0o170000
                if mode == stat.S_IFLNK:
                    raise PackError(
                        f"Pack archive contains a symlink: {info.filename!r}."
                    )
            archive.extractall(destination)
    except zipfile.BadZipFile as exc:
        raise PackError("Pack archive is not a valid zip file.") from exc


def _extract_tar(source: Path, destination: Path) -> None:
    try:
        with tarfile.open(source) as archive:
            members: list[tarfile.TarInfo] = []
            for member in archive.getmembers():
                _safe_member(member.name)
                if member.issym() or member.islnk() or member.isdev():
                    raise PackError(
                        f"Pack archive contains a link or device: {member.name!r}."
                    )
                members.append(member)
            archive.extractall(destination, members=members)
    except tarfile.TarError as exc:
        raise PackError("Pack archive is not a valid tar file.") from exc


def _extract(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(source):
        _extract_zip(source, destination)
    elif tarfile.is_tarfile(source):
        _extract_tar(source, destination)
    else:
        raise PackError("Pack archive must be a zip or tar file.")


def _collapse_single_root(directory: Path) -> None:
    entries = list(directory.iterdir())
    if len(entries) != 1 or not entries[0].is_dir() or entries[0].is_symlink():
        return
    inner = entries[0]
    for child in list(inner.iterdir()):
        child.rename(directory / child.name)
    inner.rmdir()


def _installed_meta(directory: Path) -> dict[str, Any]:
    path = directory / INSTALL_META
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _dir_size(directory: Path) -> int:
    total = 0
    for path in directory.rglob("*"):
        try:
            if path.is_file():
                total += path.stat().st_size
        except OSError:
            continue
    return total


def status(pack_id: str, *, manifest_data: Mapping[str, Any] | None = None,
           root: str | Path | None = None) -> dict[str, Any]:
    spec = _spec(pack_id, manifest_data)
    directory = pack_dir(pack_id, root)
    meta = _installed_meta(directory)
    installed = directory.is_dir() and not directory.is_symlink()
    return {
        **spec,
        "installed": installed,
        "installed_version": str(meta.get("version") or "") if installed else "",
        "installed_at": float(meta.get("installed_at") or 0.0) if installed else 0.0,
        "installed_sha256": str(meta.get("sha256") or "") if installed else "",
        "installed_size": _dir_size(directory) if installed else 0,
        "path": str(directory),
        "download_url": str(spec.get("url") or ""),
    }


def list_packs(*, manifest_data: Mapping[str, Any] | None = None,
               root: str | Path | None = None) -> list[dict[str, Any]]:
    data = manifest_data or manifest()
    return [
        status(item["id"], manifest_data=data, root=root)
        for item in data.get("packs") or []
    ]


def install_pack(
    pack_id: str,
    *,
    archive: str | Path | None = None,
    manifest_data: Mapping[str, Any] | None = None,
    root: str | Path | None = None,
) -> dict[str, Any]:
    """Verify, extract and atomically install one pack.

    The previous install is left untouched if the download, checksum or
    extraction fails. Returns the pack status.
    """
    data = manifest_data or manifest()
    spec = _spec(pack_id, data)
    base = packs_root(root)
    base.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix=f".vibecut-pack-{spec['id']}-", dir=base))
    staging = scratch / "staging"
    backup = scratch / "previous"
    try:
        source, _downloaded = _source_archive(spec, archive, scratch)
        verify_sha256(source, str(spec.get("sha256") or ""))
        _extract(source, staging)
        _collapse_single_root(staging)
        if not any(staging.iterdir()):
            raise PackError("Pack archive is empty.")
        (staging / INSTALL_META).write_text(
            json.dumps({
                "id": spec["id"],
                "name": spec["name"],
                "version": spec["version"],
                "sha256": spec["sha256"],
                "installed_at": time.time(),
            }, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        destination = pack_dir(spec["id"], base)
        if destination.exists() or destination.is_symlink():
            if destination.is_symlink() or not destination.is_dir():
                raise PackError(f"Pack destination is not a directory: {destination}")
            destination.rename(backup)
        try:
            staging.rename(destination)
        except Exception:
            if backup.exists() and not destination.exists():
                backup.rename(destination)
            raise
        return status(spec["id"], manifest_data=data, root=base)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def remove_pack(
    pack_id: str,
    *,
    manifest_data: Mapping[str, Any] | None = None,
    root: str | Path | None = None,
) -> dict[str, Any]:
    """Remove one installed pack. Missing packs are a no-op."""
    spec = _spec(pack_id, manifest_data)
    directory = pack_dir(spec["id"], root)
    removed = False
    if directory.is_symlink():
        raise PackError(f"Refusing to remove a symlinked pack: {directory}")
    if directory.is_dir():
        shutil.rmtree(directory)
        removed = True
    elif directory.exists():
        directory.unlink()
        removed = True
    return {
        "id": spec["id"],
        "removed": removed,
        "path": str(directory),
        "installed": False,
    }


def human_size(size: int) -> str:
    value = float(max(0, int(size)))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit in {"B", "KB"} else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"
