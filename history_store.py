"""Persistent per-job history index and snapshots.

Layout inside a job directory::

    <job>/history/index.json        # newest-first summaries, capped
    <job>/history/<entry_id>.json   # full snapshot for one entry

The job's ``job.json`` stays small: history summaries and snapshots never go
into it. Both files are written atomically (temp file + ``os.replace``) and a
process-wide lock serialises index updates. Old jobs without a ``history``
directory simply report an empty history.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

VERSION = 1
DEFAULT_MAX_ENTRIES = 50
HARD_MAX_ENTRIES = 200

LOCK = threading.RLock()

# Fields kept in index.json. Everything else stays in the snapshot file.
SUMMARY_FIELDS = (
    "id",
    "type",
    "created",
    "status",
    "target",
    "style",
    "source_lang",
    "target_lang",
    "provider",
    "fallback",
    "tried",
    "model",
    "latency_ms",
    "usage",
    "warning",
    "error",
    "path",
    "script_id",
    "clip_hash",
    # Render/upload extras are cheap and useful in the list view.
    "kind",
    "quality",
    "aspect",
    "audio_sig",
    "record_key",
    "name",
    "duration",
)

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SECRET_KEY = re.compile(
    r"(?:api[_-]?key|apikey|authorization|password|credential|secret|bearer)",
    re.IGNORECASE,
)
_USAGE_KEYS = frozenset({
    "calls", "input_tokens", "output_tokens", "chars", "audio_seconds", "cost_usd",
})
_SECRET_VALUE = re.compile(
    r"(?:"
    r"\bsk-[A-Za-z0-9_-]{8,}"
    r"|\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"
    r"|\bghp_[A-Za-z0-9]{20,}"
    r"|\bxox[baprs]-[A-Za-z0-9-]{10,}"
    r"|\bAIza[0-9A-Za-z_-]{20,}"
    r")",
    re.IGNORECASE,
)


def _max_entries(limit: int | None = None) -> int:
    if limit is None:
        raw = os.environ.get("VIBECUT_HISTORY_MAX", str(DEFAULT_MAX_ENTRIES))
        try:
            limit = int(raw)
        except (TypeError, ValueError):
            limit = DEFAULT_MAX_ENTRIES
    try:
        value = int(limit)
    except (TypeError, ValueError):
        value = DEFAULT_MAX_ENTRIES
    return max(1, min(value, HARD_MAX_ENTRIES))


def _history_dir(job_dir: Path | str) -> Path:
    return Path(job_dir) / "history"


def _index_path(directory: Path) -> Path:
    return directory / "index.json"


def _snapshot_path(directory: Path, entry_id: str) -> Path:
    return directory / f"{entry_id}.json"


def _is_secret_key(name: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")
    if normalized in _USAGE_KEYS:
        return False
    return bool(_SECRET_KEY.search(name)) or "token" in normalized


def _redact(value, depth: int = 0):
    """Drop secret-shaped keys/values. History must never store credentials."""
    if depth > 16:
        return "[truncated]"
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            name = str(key)
            if _is_secret_key(name):
                continue
            result[name] = _redact(item, depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [_redact(item, depth + 1) for item in value[:4000]]
    if isinstance(value, str):
        return _SECRET_VALUE.sub("[redacted]", value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


def _atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        try:
            tmp.chmod(0o600)
        except OSError:
            pass
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def _read_index(directory: Path) -> list[dict]:
    path = _index_path(directory)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = data.get("entries") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return []
    return [
        row for row in rows
        if isinstance(row, dict) and _SAFE_ID.match(str(row.get("id") or ""))
    ]


def _summary(entry: dict) -> dict:
    row = {key: entry.get(key) for key in SUMMARY_FIELDS}
    row["id"] = str(entry["id"])
    row["type"] = str(entry.get("type") or "test")
    try:
        row["created"] = round(float(entry.get("created") or time.time()), 3)
    except (TypeError, ValueError):
        row["created"] = round(time.time(), 3)
    row["status"] = str(entry.get("status") or "ok")
    row["fallback"] = bool(entry.get("fallback"))
    tried = entry.get("tried") or []
    row["tried"] = [str(item) for item in tried][:24] if isinstance(tried, list) else []
    usage = entry.get("usage")
    row["usage"] = usage if isinstance(usage, dict) else {}
    try:
        row["latency_ms"] = max(0, int(entry.get("latency_ms") or 0))
    except (TypeError, ValueError):
        row["latency_ms"] = 0
    for key in ("warning", "error", "path", "script_id", "clip_hash", "model",
                "source_lang", "target_lang", "provider", "style", "kind",
                "quality", "aspect", "audio_sig", "record_key", "name"):
        if row.get(key) is not None:
            row[key] = str(row[key])[:2400]
    if row.get("target") is not None:
        try:
            row["target"] = int(row["target"])
        except (TypeError, ValueError):
            row["target"] = None
    if row.get("duration") is not None:
        try:
            row["duration"] = round(float(row["duration"]), 3)
        except (TypeError, ValueError):
            row["duration"] = None
    return row


def append(
    job_dir: Path | str,
    entry: dict,
    snapshot: dict | None = None,
    limit: int | None = None,
) -> dict:
    """Append one entry and its snapshot. Returns the stored summary.

    Entries are newest-first in ``index.json``. When the cap is exceeded the
    oldest summaries and their snapshot files are removed.
    """
    directory = _history_dir(job_dir)
    entry = dict(entry)
    entry_id = str(entry.get("id") or uuid.uuid4().hex[:12])
    if not _SAFE_ID.match(entry_id):
        entry_id = uuid.uuid4().hex[:12]
    entry["id"] = entry_id
    entry = _redact(entry)
    entry["id"] = entry_id
    row = _summary(entry)
    payload = _redact(snapshot or {})

    with LOCK:
        entries = [item for item in _read_index(directory) if item.get("id") != entry_id]
        entries.insert(0, row)
        cap = _max_entries(limit)
        doomed = entries[cap:]
        entries = entries[:cap]

        _atomic_json(
            _snapshot_path(directory, entry_id),
            {"version": VERSION, "entry": row, "snapshot": payload},
        )
        _atomic_json(
            _index_path(directory),
            {"version": VERSION, "updated": round(time.time(), 3), "entries": entries},
        )
        for old in doomed:
            try:
                _snapshot_path(directory, str(old.get("id") or "")).unlink()
            except OSError:
                continue
    return row


def list_entries(job_dir: Path | str, limit: int | None = None) -> list[dict]:
    """Return summaries newest first. Missing history is an empty list."""
    with LOCK:
        entries = _read_index(_history_dir(job_dir))
    if limit is not None:
        entries = entries[: max(1, min(int(limit), HARD_MAX_ENTRIES))]
    return [dict(item) for item in entries]


def get_entry(job_dir: Path | str, entry_id: str) -> dict | None:
    """Return ``{"entry": summary, "snapshot": payload}`` or ``None``."""
    entry_id = str(entry_id or "")
    if not _SAFE_ID.match(entry_id):
        return None
    directory = _history_dir(job_dir)
    with LOCK:
        row = next(
            (item for item in _read_index(directory) if item.get("id") == entry_id),
            None,
        )
        if not row:
            return None
        path = _snapshot_path(directory, entry_id)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        payload = data.get("snapshot") if isinstance(data, dict) else None
    return {"entry": dict(row), "snapshot": payload if isinstance(payload, dict) else {}}


def delete_entry(job_dir: Path | str, entry_id: str) -> bool:
    """Remove one summary + snapshot. Returns True when the entry existed."""
    entry_id = str(entry_id or "")
    if not _SAFE_ID.match(entry_id):
        return False
    directory = _history_dir(job_dir)
    with LOCK:
        entries = _read_index(directory)
        kept = [item for item in entries if item.get("id") != entry_id]
        if len(kept) == len(entries):
            return False
        _atomic_json(
            _index_path(directory),
            {"version": VERSION, "updated": round(time.time(), 3), "entries": kept},
        )
        try:
            _snapshot_path(directory, entry_id).unlink()
        except OSError:
            pass
    return True
