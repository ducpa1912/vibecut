"""Pinned, expiring, revocable review share records.

Records live in ``data/shares.json`` as::

    {token: {
        "job_id": str,
        "artifact_id": str,
        "created": epoch,
        "expires_at": epoch | None,
        "revoked_at": epoch | None,
        "label": str,
    }}

The token is a capability. It is generated exactly once, returned by
:func:`create`, and never regenerated. Reads and writes are serialised with a
thread lock plus an advisory file lock, and every write is atomic.
"""

from __future__ import annotations

import fcntl
import json
import os
import secrets
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("VIBECUT_DATA", ROOT / "data")).expanduser().resolve()
SHARES_PATH = DATA / "shares.json"
LOCK = threading.RLock()
MAX_LABEL = 120
ACTIVE = "active"
EXPIRED = "expired"
REVOKED = "revoked"
MISSING = "missing"


class ShareStoreError(RuntimeError):
    """The share store exists but cannot be read with confidence."""


def _path(value: str | Path | None = None) -> Path:
    return Path(value or SHARES_PATH)


def _lock_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.lock")


@contextmanager
def _locked(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with LOCK:
        with _lock_path(path).open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _read_unlocked(path: Path, strict: bool = False) -> dict:
    if not path.exists():
        return {}
    if not path.is_file():
        if strict:
            raise ShareStoreError("The review share store is not a file.")
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        if strict:
            raise ShareStoreError("The review share store is unreadable.") from exc
        return {}
    if not isinstance(value, dict):
        if strict:
            raise ShareStoreError("The review share store is not a JSON object.")
        return {}
    records: dict = {}
    for token, record in value.items():
        if not isinstance(record, dict):
            if strict:
                raise ShareStoreError("The review share store has an invalid record.")
            continue
        records[str(token)] = record
    return records


def _atomic_save_unlocked(path: Path, records: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(records, handle, ensure_ascii=False, indent=1)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            tmp.chmod(0o600)
        except OSError:
            pass
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def load(path: str | Path | None = None, *, strict: bool = True) -> dict:
    target = _path(path)
    with _locked(target):
        return _read_unlocked(target, strict=strict)


def save(records: dict, path: str | Path | None = None) -> dict:
    target = _path(path)
    clean = {
        str(token): record
        for token, record in (records or {}).items()
        if isinstance(record, dict)
    }
    with _locked(target):
        _atomic_save_unlocked(target, clean)
    return clean


def _epoch(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def _record(record: dict | None, token: str | None = None) -> dict:
    data = record if isinstance(record, dict) else {}
    value = {
        "job_id": str(data.get("job_id") or ""),
        "artifact_id": str(data.get("artifact_id") or "") or None,
        "created": _epoch(data.get("created")) or 0.0,
        "expires_at": _epoch(data.get("expires_at")),
        "revoked_at": _epoch(data.get("revoked_at")),
        "label": str(data.get("label") or "")[:MAX_LABEL],
    }
    # Old v0.13 records carried the target/aspect instead of an artifact id.
    if data.get("target") is not None:
        try:
            value["target"] = int(data["target"])
        except (TypeError, ValueError):
            pass
    if data.get("aspect"):
        value["aspect"] = str(data["aspect"])
    value["status"] = state(value)
    return value


def describe(record: dict | None, token: str | None = None) -> dict:
    """Public, normalised view of one stored record."""
    return _record(record, token)


def state(record: dict, now: float | None = None) -> str:
    now = time.time() if now is None else float(now)
    revoked = _epoch((record or {}).get("revoked_at"))
    if revoked is not None:
        return REVOKED
    expires = _epoch((record or {}).get("expires_at"))
    if expires is not None and expires <= now:
        return EXPIRED
    return ACTIVE


def is_active(record: dict, now: float | None = None) -> bool:
    return state(record, now) == ACTIVE


def is_expired(record: dict, now: float | None = None) -> bool:
    return state(record, now) == EXPIRED


def is_revoked(record: dict, now: float | None = None) -> bool:
    return state(record, now) == REVOKED


def _new_token(existing: dict) -> str:
    for _ in range(8):
        token = secrets.token_urlsafe(24)
        if token not in existing:
            return token
    return uuid.uuid4().hex + uuid.uuid4().hex[:12]


def create(
    job_id: str,
    artifact_id: str | None,
    *,
    expires_at: float | None = None,
    expires_in_days: float | None = None,
    label: str = "",
    path: str | Path | None = None,
    now: float | None = None,
) -> tuple[str, dict]:
    """Create a share and return ``(token, record)`` exactly once."""
    now = round(time.time() if now is None else float(now), 3)
    if expires_at is None and expires_in_days is not None:
        days = float(expires_in_days)
        if days < 0:
            raise ValueError("expires_in_days cannot be negative.")
        expires_at = now + days * 86400 if days > 0 else None
    record = {
        "job_id": str(job_id),
        "artifact_id": str(artifact_id) if artifact_id else None,
        "created": now,
        "expires_at": _epoch(expires_at),
        "revoked_at": None,
        "label": str(label or "")[:MAX_LABEL],
    }
    target = _path(path)
    with _locked(target):
        records = _read_unlocked(target, strict=True)
        token = _new_token(records)
        records[token] = record
        _atomic_save_unlocked(target, records)
    return token, _record(record, token)


def get(
    token: str,
    path: str | Path | None = None,
    *,
    strict: bool = True,
) -> dict | None:
    token = str(token or "")
    if not token:
        return None
    target = _path(path)
    with _locked(target):
        record = _read_unlocked(target, strict=strict).get(token)
    if record is None:
        return None
    return _record(record, token)


def resolve(
    token: str,
    path: str | Path | None = None,
    now: float | None = None,
) -> tuple[dict | None, str]:
    record = get(token, path)
    if record is None:
        return None, MISSING
    return record, state(record, now)


def list_records(
    path: str | Path | None = None,
    *,
    include_tokens: bool = False,
    now: float | None = None,
    strict: bool = True,
) -> list[dict]:
    target = _path(path)
    with _locked(target):
        records = _read_unlocked(target, strict=strict)
    rows: list[dict] = []
    for token, record in records.items():
        item = _record(record, token)
        item["status"] = state(record, now)
        if include_tokens:
            item["token"] = token
        rows.append(item)
    rows.sort(key=lambda item: float(item.get("created") or 0), reverse=True)
    return rows


def patch(
    token: str,
    updates: dict,
    path: str | Path | None = None,
    *,
    now: float | None = None,
) -> dict | None:
    token = str(token or "")
    target = _path(path)
    now = round(time.time() if now is None else float(now), 3)
    with _locked(target):
        records = _read_unlocked(target, strict=True)
        record = records.get(token)
        if record is None:
            return None
        if "label" in updates:
            record["label"] = str(updates.get("label") or "")[:MAX_LABEL]
        if "expires_at" in updates:
            record["expires_at"] = _epoch(updates.get("expires_at"))
        if "expires_in_days" in updates:
            days = updates.get("expires_in_days")
            if days is None:
                record["expires_at"] = None
            else:
                days = float(days)
                if days < 0:
                    raise ValueError("expires_in_days cannot be negative.")
                record["expires_at"] = (
                    round(now + days * 86400, 3) if days > 0 else None
                )
        if "revoked" in updates:
            record["revoked_at"] = (
                now if bool(updates.get("revoked")) else None
            )
        if "revoked_at" in updates:
            record["revoked_at"] = _epoch(updates.get("revoked_at"))
        records[token] = record
        _atomic_save_unlocked(target, records)
    return _record(record, token)


def bind_artifact(
    token: str,
    artifact_id: str,
    path: str | Path | None = None,
) -> dict | None:
    """Bind a legacy share to one artifact. The first binding wins."""
    token = str(token or "")
    target = _path(path)
    with _locked(target):
        records = _read_unlocked(target, strict=True)
        record = records.get(token)
        if record is None:
            return None
        if not record.get("artifact_id"):
            record["artifact_id"] = str(artifact_id)
            records[token] = record
            _atomic_save_unlocked(target, records)
    return _record(record, token)


def revoke(
    token: str,
    path: str | Path | None = None,
    *,
    now: float | None = None,
) -> dict | None:
    return patch(token, {"revoked": True}, path, now=now)


def unrevoke(
    token: str,
    path: str | Path | None = None,
) -> dict | None:
    return patch(token, {"revoked": False}, path)


def delete(token: str, path: str | Path | None = None) -> bool:
    token = str(token or "")
    target = _path(path)
    with _locked(target):
        records = _read_unlocked(target, strict=True)
        if token not in records:
            return False
        records.pop(token, None)
        _atomic_save_unlocked(target, records)
    return True


def active_records(
    path: str | Path | None = None,
    *,
    job_id: str | None = None,
    now: float | None = None,
    strict: bool = True,
) -> list[dict]:
    return [
        item for item in list_records(
            path, include_tokens=True, now=now, strict=strict,
        )
        if item.get("status") == ACTIVE
        and (job_id is None or item.get("job_id") == job_id)
    ]


def active_artifact_ids(
    path: str | Path | None = None,
    *,
    job_id: str | None = None,
    now: float | None = None,
    strict: bool = True,
) -> set[str]:
    return {
        str(item["artifact_id"])
        for item in active_records(
            path, job_id=job_id, now=now, strict=strict,
        )
        if item.get("artifact_id")
    }


def active_legacy_targets(
    path: str | Path | None = None,
    *,
    job_id: str | None = None,
    now: float | None = None,
    strict: bool = True,
) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    for item in active_records(
        path, job_id=job_id, now=now, strict=strict,
    ):
        if item.get("artifact_id"):
            continue
        try:
            target = int(item.get("target"))
        except (TypeError, ValueError):
            continue
        result.append((target, str(item.get("aspect") or "9:16")))
    return result


# Friendly aliases for callers that prefer explicit names.
create_share = create
get_share = get
resolve_share = resolve
list_shares = list_records
list_all = list_records
patch_share = patch
update_share = patch
delete_share = delete
remove_share = delete
bind_share = bind_artifact
token_state = state
