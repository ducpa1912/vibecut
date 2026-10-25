"""SQLite-backed admin store: users, sessions, audit, and pipeline events.

The database lives under ``data/admin`` and never stores raw API keys. Audit
values are redacted before they reach the database.
"""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Any, Iterable

import settings_store

LOCK = threading.RLock()
_READY_PATHS: set[str] = set()
SESSION_HOURS = 12
IDLE_MINUTES = 30
AUDIT_KEEP_DAYS = 365
PIPELINE_KEEP_DAYS = 90
AUDIT_ANCHOR_VERSION = 1

_SENSITIVE_KEY = re.compile(
    r"(^|_)(api[_-]?key|apikey|access[_-]?token|refresh[_-]?token|private[_-]?key|"
    r"client[_-]?secret|key|token|secret|password|passwd|authorization|"
    r"cookie|credential|webhook[_-]?secret|session)(_|$)",
    re.IGNORECASE,
)
_SECRET_TEXT = re.compile(
    r"(?i)\b(xsec_token|xsec_source|access_token|api[_-]?key|apikey|secret|"
    r"password|passwd|authorization|token|auth|signature|sig|key)=([^&\s]+)"
)
_SECRET_VALUE = re.compile(
    r"(?:\bsk-[A-Za-z0-9_-]{8,}|\bgsk_[A-Za-z0-9_-]{8,}|"
    r"\bAIza[0-9A-Za-z_-]{20,}|\bBearer\s+[A-Za-z0-9._~+/=-]{8,})",
    re.IGNORECASE,
)
_URL_TEXT = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_SHORT_MASK = "••••••••"


def mask_secret(value: str) -> str:
    """Never reveal a complete secret.

    Values below a safe length become a fixed bullet string; longer values keep
    a short recognisable prefix/suffix so an operator can tell keys apart.
    """
    text = str(value or "")
    if not text:
        return ""
    if len(text) < 16:
        return _SHORT_MASK
    return f"{text[:5]}{'•' * 10}{text[-5:]}"


def _redact_url(match: re.Match[str]) -> str:
    raw = match.group(0)
    try:
        parts = urllib.parse.urlsplit(raw)
    except ValueError:
        return raw.split("#", 1)[0].split("?", 1)[0]
    host = parts.netloc.rsplit("@", 1)[-1]
    return urllib.parse.urlunsplit((parts.scheme, host, parts.path, "", ""))


def redact_text(value: Any) -> str:
    text = " ".join(str(value or "").split())
    text = _URL_TEXT.sub(_redact_url, text)
    text = _SECRET_TEXT.sub(r"\1=redacted", text)
    return _SECRET_VALUE.sub("***", text)


def _normalized_key(key: str) -> str:
    value = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(key or ""))
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _key_is_secret(key: str) -> bool:
    normalized = _normalized_key(key)
    if not normalized:
        return False
    if _SENSITIVE_KEY.search(normalized):
        return True
    return bool(set(normalized.split("_")) & {"key", "apikey", "token", "secret"})


def _masked_leaf(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        return _SHORT_MASK
    return mask_secret(str(value))


def sanitize(value: Any, key: str = "", sensitive: bool = False) -> Any:
    """Recursively mask secret-shaped values for audit storage.

    Sensitivity follows a secret-shaped key into nested objects and lists so
    ``{"api_key": {"value": "..."}}`` and camelCase/hyphenated variants cannot
    slip through as plain text.
    """
    sensitive = sensitive or _key_is_secret(key)
    if isinstance(value, dict):
        return {
            str(k): sanitize(v, str(k), sensitive)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize(item, key, sensitive) for item in value]
    if sensitive:
        if value is None:
            return None
        return _masked_leaf(value)
    if isinstance(value, str):
        return redact_text(value)
    return value


def data_dir() -> Path:
    path = Path(settings_store.DATA) / "admin"
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path


def db_path() -> Path:
    return data_dir() / "admin.sqlite3"


def _connect() -> sqlite3.Connection:
    path = db_path()
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=30000")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA foreign_keys=ON")
    for attempt in range(6):
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            break
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() and "busy" not in str(exc).lower():
                raise
            if attempt == 5:
                break
            time.sleep(0.05 * (attempt + 1))
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return connection


def _storage_mode(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except OSError:
        pass


def _audit_key_path() -> Path:
    return data_dir() / "audit.key"


def _audit_anchor_path() -> Path:
    return data_dir() / "audit.head.json"


def _audit_lock_path() -> Path:
    return data_dir() / "audit.head.lock"


def _audit_key() -> bytes:
    path = _audit_key_path()
    try:
        if not path.is_file():
            try:
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(descriptor, "w", encoding="ascii") as handle:
                    handle.write(secrets.token_hex(32))
                    handle.flush()
                    os.fsync(handle.fileno())
        _storage_mode(path, 0o600)
        for attempt in range(20):
            value = path.read_text(encoding="ascii").strip()
            if len(value) >= 32:
                return value.encode("ascii")
            if attempt < 19:
                time.sleep(0.01)
    except OSError:
        pass
    # A missing/unreadable anchor key must not crash the app. The anchor file
    # still detects casual edits, but a filesystem attacker can replace both.
    return b"vibecut-audit-anchor-fallback"


def _anchor_signature(payload: dict[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "signature"}
    return hmac.new(
        _audit_key(),
        json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _read_anchor() -> dict[str, Any] | None:
    path = _audit_anchor_path()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(value, dict):
        return None
    if not hmac.compare_digest(str(value.get("signature") or ""), _anchor_signature(value)):
        return None
    try:
        value["first_id"] = int(value.get("first_id") or 0)
        value["last_id"] = int(value.get("last_id") or 0)
        value["count"] = int(value.get("count") or 0)
    except (TypeError, ValueError):
        return None
    return value


def _write_anchor(payload: dict[str, Any]) -> None:
    path = _audit_anchor_path()
    payload = {
        "version": AUDIT_ANCHOR_VERSION,
        **payload,
        "updated": now(),
    }
    payload["signature"] = _anchor_signature(payload)
    temporary = path.with_name(path.name + f".{os.getpid()}.{threading.get_ident()}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8",
    )
    _storage_mode(temporary, 0o600)
    os.replace(temporary, path)


def _update_anchor(first_id: int, base_prev_hash: str, count: int, last_id: int, head: str) -> None:
    """Monotonic anchor update, serialised across processes with flock."""
    data_dir()
    lock_path = _audit_lock_path()
    try:
        with lock_path.open("a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                current = _read_anchor()
                if current is None and _audit_anchor_path().is_file():
                    # Never overwrite a tampered/unreadable anchor. Leave the
                    # evidence in place so verification reports the failure.
                    return
                if current and (
                    int(current.get("count") or 0) > int(count)
                    or (
                        int(current.get("count") or 0) == int(count)
                        and int(current.get("last_id") or 0) >= int(last_id)
                    )
                ):
                    return
                _write_anchor({
                    "first_id": int(first_id),
                    "base_prev_hash": str(base_prev_hash or ""),
                    "count": int(count),
                    "last_id": int(last_id),
                    "head": str(head or ""),
                })
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    _storage_mode(lock_path, 0o600)


def _reset_anchor(first_id: int, base_prev_hash: str, count: int, last_id: int, head: str) -> None:
    data_dir()
    lock_path = _audit_lock_path()
    try:
        with lock_path.open("a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                _write_anchor({
                    "first_id": int(first_id),
                    "base_prev_hash": str(base_prev_hash or ""),
                    "count": int(count),
                    "last_id": int(last_id),
                    "head": str(head or ""),
                })
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    _storage_mode(lock_path, 0o600)


def _ensure_anchor(db: sqlite3.Connection) -> dict[str, Any] | None:
    if _audit_anchor_path().is_file():
        # A present but invalid anchor is a verification failure, not a cue to
        # silently rebuild trust from the mutable database.
        return _read_anchor()
    rows = db.execute(
        "SELECT id, prev_hash, entry_hash FROM admin_audit ORDER BY id ASC"
    ).fetchall()
    if not rows:
        _update_anchor(0, "", 0, 0, "")
        return _read_anchor()
    first = rows[0]
    last = rows[-1]
    _update_anchor(
        int(first["id"]), str(first["prev_hash"] or ""), len(rows),
        int(last["id"]), str(last["entry_hash"]),
    )
    return _read_anchor()


def init_db() -> None:
    path = str(db_path())
    with LOCK:
        if path in _READY_PATHS:
            return
        last_error: Exception | None = None
        for attempt in range(6):
            try:
                with _connect() as db:
                    db.executescript(
                        """
                        CREATE TABLE IF NOT EXISTS admin_users (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            email TEXT NOT NULL UNIQUE,
                            password_hash TEXT NOT NULL,
                            created REAL NOT NULL,
                            updated REAL NOT NULL
                        );
                        CREATE TABLE IF NOT EXISTS admin_sessions (
                            token_hash TEXT PRIMARY KEY,
                            csrf TEXT NOT NULL,
                            user_id INTEGER NOT NULL,
                            created REAL NOT NULL,
                            last_seen REAL NOT NULL,
                            expires REAL NOT NULL,
                            ip TEXT NOT NULL DEFAULT '',
                            user_agent TEXT NOT NULL DEFAULT '',
                            FOREIGN KEY(user_id) REFERENCES admin_users(id) ON DELETE CASCADE
                        );
                        CREATE TABLE IF NOT EXISTS admin_audit (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            ts REAL NOT NULL,
                            actor TEXT NOT NULL DEFAULT '',
                            action TEXT NOT NULL,
                            resource_type TEXT NOT NULL DEFAULT '',
                            resource_id TEXT NOT NULL DEFAULT '',
                            outcome TEXT NOT NULL DEFAULT 'ok',
                            ip TEXT NOT NULL DEFAULT '',
                            user_agent TEXT NOT NULL DEFAULT '',
                            request_id TEXT NOT NULL DEFAULT '',
                            latency_ms REAL NOT NULL DEFAULT 0,
                            before_json TEXT NOT NULL DEFAULT '',
                            after_json TEXT NOT NULL DEFAULT '',
                            detail TEXT NOT NULL DEFAULT '',
                            prev_hash TEXT NOT NULL DEFAULT '',
                            entry_hash TEXT NOT NULL
                        );
                        CREATE INDEX IF NOT EXISTS admin_audit_ts ON admin_audit(ts DESC);
                        CREATE INDEX IF NOT EXISTS admin_audit_actor ON admin_audit(actor);
                        CREATE INDEX IF NOT EXISTS admin_audit_action ON admin_audit(action);
                        CREATE TABLE IF NOT EXISTS pipeline_events (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            ts REAL NOT NULL,
                            request_id TEXT NOT NULL DEFAULT '',
                            job_id TEXT NOT NULL DEFAULT '',
                            workflow TEXT NOT NULL,
                            route_index INTEGER NOT NULL DEFAULT 0,
                            provider TEXT NOT NULL DEFAULT '',
                            model TEXT NOT NULL DEFAULT '',
                            reasoning TEXT NOT NULL DEFAULT '',
                            status TEXT NOT NULL DEFAULT 'ok',
                            latency_ms REAL NOT NULL DEFAULT 0,
                            input_tokens INTEGER NOT NULL DEFAULT 0,
                            output_tokens INTEGER NOT NULL DEFAULT 0,
                            fallback INTEGER NOT NULL DEFAULT 0,
                            error TEXT NOT NULL DEFAULT ''
                        );
                        CREATE INDEX IF NOT EXISTS pipeline_events_ts ON pipeline_events(ts DESC);
                        CREATE INDEX IF NOT EXISTS pipeline_events_workflow ON pipeline_events(workflow);
                        """
                    )
                _READY_PATHS.add(path)
                return
            except sqlite3.OperationalError as exc:
                last_error = exc
                if "locked" not in str(exc).lower() and "busy" not in str(exc).lower():
                    raise
                time.sleep(0.05 * (attempt + 1))
        if last_error:
            raise last_error


def now() -> float:
    return round(time.time(), 3)


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.scrypt(
        str(password).encode("utf-8"), salt=salt, n=16384, r=8, p=1,
        dklen=32, maxmem=64 * 1024 * 1024,
    )
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


def hash_password(password: str) -> str:
    return _hash_password(password)


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, n, r, p, salt_hex, digest_hex = str(stored).split("$", 5)
        if algorithm != "scrypt":
            return False
        digest = hashlib.scrypt(
            str(password).encode("utf-8"), salt=bytes.fromhex(salt_hex),
            n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(digest_hex)),
            maxmem=64 * 1024 * 1024,
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def count_users() -> int:
    init_db()
    with LOCK, _connect() as db:
        row = db.execute("SELECT COUNT(*) AS n FROM admin_users").fetchone()
        return int(row["n"] if row else 0)


def get_user(email: str | None = None, user_id: int | None = None) -> dict | None:
    init_db()
    with LOCK, _connect() as db:
        if user_id is not None:
            row = db.execute("SELECT * FROM admin_users WHERE id = ?", (int(user_id),)).fetchone()
        elif str(email or "").strip():
            row = db.execute(
                "SELECT * FROM admin_users WHERE email = ?", (str(email or "").strip().lower(),)
            ).fetchone()
        else:
            row = None
        return dict(row) if row else None


def first_user() -> dict | None:
    """Return the single admin account for local CLI management only."""
    init_db()
    with LOCK, _connect() as db:
        row = db.execute("SELECT * FROM admin_users ORDER BY id LIMIT 1").fetchone()
        return dict(row) if row else None


def create_user(email: str, password: str) -> dict:
    init_db()
    email = str(email or "").strip().lower()
    if not email or "@" not in email or len(email) > 320:
        raise ValueError("A valid admin email is required.")
    if len(str(password or "")) < 12:
        raise ValueError("Admin password must be at least 12 characters.")
    stamp = now()
    with LOCK, _connect() as db:
        try:
            # BEGIN IMMEDIATE serialises competing bootstraps. INSERT ... WHERE
            # NOT EXISTS makes the singleton check part of the write itself.
            db.execute("BEGIN IMMEDIATE")
            cursor = db.execute(
                """INSERT INTO admin_users(email, password_hash, created, updated)
                   SELECT ?, ?, ?, ?
                   WHERE NOT EXISTS (SELECT 1 FROM admin_users)""",
                (email, _hash_password(password), stamp, stamp),
            )
            if cursor.rowcount != 1:
                db.rollback()
                raise ValueError("An admin already exists; signup is disabled.")
            row = db.execute("SELECT * FROM admin_users WHERE email = ?", (email,)).fetchone()
            db.commit()
        except sqlite3.IntegrityError as exc:
            db.rollback()
            raise ValueError("An admin already exists; signup is disabled.") from exc
        return dict(row)


def update_user(email: str, password: str | None = None) -> dict:
    init_db()
    email = str(email or "").strip().lower()
    if not email or "@" not in email or len(email) > 320:
        raise ValueError("A valid admin email is required.")
    if password is not None and len(str(password)) < 12:
        raise ValueError("Admin password must be at least 12 characters.")
    with LOCK, _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        user = db.execute("SELECT * FROM admin_users LIMIT 1").fetchone()
        if not user:
            db.rollback()
            raise ValueError("No admin account exists.")
        hash_value = _hash_password(password) if password else user["password_hash"]
        try:
            db.execute(
                "UPDATE admin_users SET email = ?, password_hash = ?, updated = ? WHERE id = ?",
                (email, hash_value, now(), int(user["id"])),
            )
        except sqlite3.IntegrityError as exc:
            db.rollback()
            raise ValueError("That admin email is already in use.") from exc
        updated = db.execute("SELECT * FROM admin_users WHERE id = ?", (int(user["id"]),)).fetchone()
        db.commit()
        return dict(updated)


def create_session(email: str, ip: str = "", user_agent: str = "") -> dict:
    init_db()
    user = get_user(email)
    if not user:
        raise ValueError("Admin account not found.")
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    stamp = now()
    expires = stamp + SESSION_HOURS * 3600
    with LOCK, _connect() as db:
        db.execute(
            """INSERT INTO admin_sessions(
                token_hash, csrf, user_id, created, last_seen, expires, ip, user_agent
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                hashlib.sha256(token.encode("utf-8")).hexdigest(), csrf,
                int(user["id"]), stamp, stamp, expires, str(ip or ""),
                str(user_agent or "")[:500],
            ),
        )
    return {"token": token, "csrf": csrf, "expires": expires, "email": user["email"]}


def get_session(token: str) -> dict | None:
    if not token:
        return None
    init_db()
    token_hash = hashlib.sha256(str(token).encode("utf-8")).hexdigest()
    stamp = now()
    with LOCK, _connect() as db:
        row = db.execute(
            """SELECT s.*, u.email FROM admin_sessions s
               JOIN admin_users u ON u.id = s.user_id
               WHERE s.token_hash = ?""",
            (token_hash,),
        ).fetchone()
        if not row:
            return None
        if float(row["expires"]) <= stamp or stamp - float(row["last_seen"]) > IDLE_MINUTES * 60:
            db.execute("DELETE FROM admin_sessions WHERE token_hash = ?", (token_hash,))
            return None
        db.execute(
            "UPDATE admin_sessions SET last_seen = ? WHERE token_hash = ?",
            (stamp, token_hash),
        )
        return {
            "token_hash": token_hash,
            "email": row["email"],
            "user_id": int(row["user_id"]),
            "csrf": row["csrf"],
            "expires": float(row["expires"]),
        }


def delete_session(token: str) -> None:
    if not token:
        return
    init_db()
    token_hash = hashlib.sha256(str(token).encode("utf-8")).hexdigest()
    with LOCK, _connect() as db:
        db.execute("DELETE FROM admin_sessions WHERE token_hash = ?", (token_hash,))


def delete_other_sessions(user_id: int, keep_hash: str = "") -> None:
    init_db()
    with LOCK, _connect() as db:
        if keep_hash:
            db.execute(
                "DELETE FROM admin_sessions WHERE user_id = ? AND token_hash != ?",
                (int(user_id), keep_hash),
            )
        else:
            db.execute("DELETE FROM admin_sessions WHERE user_id = ?", (int(user_id),))


def _last_audit_hash(db: sqlite3.Connection) -> str:
    row = db.execute("SELECT entry_hash FROM admin_audit ORDER BY id DESC LIMIT 1").fetchone()
    return str(row["entry_hash"] if row else "")


def record_audit(
    actor: str,
    action: str,
    *,
    resource_type: str = "",
    resource_id: str = "",
    outcome: str = "ok",
    before: Any = None,
    after: Any = None,
    detail: Any = "",
    ip: str = "",
    user_agent: str = "",
    request_id: str = "",
    latency_ms: float = 0,
) -> None:
    init_db()
    stamp = now()
    safe_before = sanitize(before)
    safe_after = sanitize(after)
    payload = {
        "ts": stamp,
        "actor": str(actor or "")[:320],
        "action": str(action or "")[:160],
        "resource_type": str(resource_type or "")[:80],
        "resource_id": str(resource_id or "")[:320],
        "outcome": str(outcome or "ok")[:40],
        "ip": str(ip or "")[:80],
        "user_agent": str(user_agent or "")[:500],
        "request_id": str(request_id or "")[:120],
        "latency_ms": round(float(latency_ms or 0.0), 3),
        "before": safe_before,
        "after": safe_after,
        "detail": redact_text(detail)[:2000],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    for attempt in range(6):
        try:
            with LOCK, _connect() as db:
                _ensure_anchor(db)
                db.execute("BEGIN IMMEDIATE")
                prev_hash = _last_audit_hash(db)
                entry_hash = hashlib.sha256(
                    (prev_hash + encoded).encode("utf-8")
                ).hexdigest()
                cursor = db.execute(
                    """INSERT INTO admin_audit(
                        ts, actor, action, resource_type, resource_id, outcome, ip,
                        user_agent, request_id, latency_ms, before_json, after_json,
                        detail, prev_hash, entry_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        stamp, payload["actor"], payload["action"], payload["resource_type"],
                        payload["resource_id"], payload["outcome"], payload["ip"],
                        payload["user_agent"], payload["request_id"], payload["latency_ms"],
                        json.dumps(safe_before, ensure_ascii=False, sort_keys=True) if safe_before is not None else "",
                        json.dumps(safe_after, ensure_ascii=False, sort_keys=True) if safe_after is not None else "",
                        payload["detail"], prev_hash, entry_hash,
                    ),
                )
                last_id = int(cursor.lastrowid or 0)
                row = db.execute(
                    "SELECT id, prev_hash, entry_hash FROM admin_audit ORDER BY id ASC LIMIT 1"
                ).fetchone()
                count = int(db.execute("SELECT COUNT(*) AS n FROM admin_audit").fetchone()["n"])
                db.commit()
            if row:
                _update_anchor(
                    int(row["id"]), str(row["prev_hash"] or ""), count,
                    last_id, entry_hash,
                )
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() and "busy" not in str(exc).lower():
                raise
            if attempt == 5:
                raise
            time.sleep(0.05 * (attempt + 1))


def _audit_rows(rows: Iterable[sqlite3.Row]) -> list[dict]:
    result = []
    for row in rows:
        item = dict(row)
        for source, target in (("before_json", "before"), ("after_json", "after")):
            raw = item.get(source)
            try:
                item[target] = json.loads(raw) if raw else None
            except (TypeError, ValueError):
                item[target] = None
        result.append(item)
    return result


def list_audit(
    *,
    limit: int = 100,
    offset: int = 0,
    actor: str = "",
    action: str = "",
    resource_type: str = "",
    include_http: bool = False,
) -> dict:
    init_db()
    clauses: list[str] = []
    values: list[Any] = []
    if not include_http:
        clauses.append("action != 'http.request'")
    if actor:
        clauses.append("actor = ?")
        values.append(actor)
    if action:
        clauses.append("action LIKE ?")
        values.append(f"%{action}%")
    if resource_type:
        clauses.append("resource_type = ?")
        values.append(resource_type)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    limit = max(1, min(int(limit or 100), 500))
    offset = max(0, int(offset or 0))
    with LOCK, _connect() as db:
        total = int(db.execute(f"SELECT COUNT(*) AS n FROM admin_audit{where}", values).fetchone()["n"])
        rows = db.execute(
            f"SELECT * FROM admin_audit{where} ORDER BY id DESC LIMIT ? OFFSET ?",
            [*values, limit, offset],
        ).fetchall()
    return {"entries": _audit_rows(rows), "total": total, "limit": limit, "offset": offset}


def verify_audit() -> dict:
    init_db()
    with LOCK, _connect() as db:
        anchor = _ensure_anchor(db)
        if anchor is None:
            return {
                "ok": False, "entries": 0, "broken_at": None,
                "reason": "Audit anchor is missing or unreadable.",
            }
        first_id = int(anchor.get("first_id") or 0)
        rows = db.execute(
            "SELECT * FROM admin_audit WHERE id >= ? ORDER BY id ASC", (first_id,)
        ).fetchall()
    if int(anchor.get("count") or 0) == 0 and not rows:
        return {"ok": True, "entries": 0, "broken_at": None}
    if len(rows) < int(anchor.get("count") or 0):
        return {
            "ok": False, "entries": len(rows), "broken_at": rows[-1]["id"] if rows else None,
            "reason": "Audit rows were truncated: anchor count is higher than the database.",
        }
    prev = str(anchor.get("base_prev_hash") or "")
    anchored_head = None
    for index, row in enumerate(rows):
        item = dict(row)
        try:
            before = json.loads(item["before_json"]) if item["before_json"] else None
            after = json.loads(item["after_json"]) if item["after_json"] else None
        except (TypeError, ValueError):
            return {
                "ok": False, "entries": len(rows), "broken_at": item["id"],
                "reason": "Audit entry contains malformed JSON.",
            }
        payload = {
            "ts": item["ts"],
            "actor": item["actor"],
            "action": item["action"],
            "resource_type": item["resource_type"],
            "resource_id": item["resource_id"],
            "outcome": item["outcome"],
            "ip": item["ip"],
            "user_agent": item["user_agent"],
            "request_id": item["request_id"],
            "latency_ms": item["latency_ms"],
            "before": before,
            "after": after,
            "detail": item["detail"],
        }
        expected = hashlib.sha256(
            (prev + json.dumps(payload, ensure_ascii=False, sort_keys=True)).encode("utf-8")
        ).hexdigest()
        if item["prev_hash"] != prev or item["entry_hash"] != expected:
            return {
                "ok": False, "entries": len(rows), "broken_at": item["id"],
                "reason": "Audit hash chain mismatch.",
            }
        prev = item["entry_hash"]
        if index + 1 == int(anchor.get("count") or 0):
            anchored_head = prev
    expected_head = str(anchor.get("head") or "")
    if anchored_head is not None and not hmac.compare_digest(anchored_head, expected_head):
        return {
            "ok": False, "entries": len(rows), "broken_at": rows[-1]["id"] if rows else None,
            "reason": "Audit head does not match the signed anchor.",
        }
    return {"ok": True, "entries": len(rows), "broken_at": None}


def record_pipeline_event(
    workflow: str,
    provider: str,
    model: str,
    *,
    request_id: str = "",
    job_id: str = "",
    route_index: int = 0,
    reasoning: str = "",
    status: str = "ok",
    latency_ms: float = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    fallback: bool = False,
    error: Any = "",
) -> None:
    init_db()
    with LOCK, _connect() as db:
        db.execute(
            """INSERT INTO pipeline_events(
                ts, request_id, job_id, workflow, route_index, provider, model,
                reasoning, status, latency_ms, input_tokens, output_tokens,
                fallback, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                now(), str(request_id or ""), str(job_id or ""), str(workflow or ""),
                int(route_index or 0), str(provider or ""), str(model or ""),
                str(reasoning or ""), str(status or ""), round(float(latency_ms or 0), 3),
                int(input_tokens or 0), int(output_tokens or 0), 1 if fallback else 0,
                redact_text(error),
            ),
        )


def list_pipeline_events(
    *,
    limit: int = 100,
    offset: int = 0,
    workflow: str = "",
    provider: str = "",
    status: str = "",
    job_id: str = "",
) -> dict:
    init_db()
    clauses: list[str] = []
    values: list[Any] = []
    if workflow:
        clauses.append("workflow LIKE ?")
        values.append(f"%{workflow}%")
    if provider:
        clauses.append("provider = ?")
        values.append(provider)
    if status:
        clauses.append("status = ?")
        values.append(status)
    if job_id:
        clauses.append("job_id = ?")
        values.append(job_id)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    limit = max(1, min(int(limit or 100), 500))
    offset = max(0, int(offset or 0))
    with LOCK, _connect() as db:
        total = int(db.execute(f"SELECT COUNT(*) AS n FROM pipeline_events{where}", values).fetchone()["n"])
        rows = db.execute(
            f"SELECT * FROM pipeline_events{where} ORDER BY id DESC LIMIT ? OFFSET ?",
            [*values, limit, offset],
        ).fetchall()
    return {"entries": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}


def _archive_rows(rows: Iterable[sqlite3.Row]) -> Path | None:
    items = [dict(row) for row in rows]
    if not items:
        return None
    folder = data_dir() / "audit-archive"
    folder.mkdir(parents=True, exist_ok=True)
    _storage_mode(folder, 0o700)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    path = folder / f"admin-audit-{stamp}-{os.getpid()}-{secrets.token_hex(3)}.jsonl"
    body = "\n".join(
        json.dumps(item, ensure_ascii=False, sort_keys=True) for item in items
    )
    path.write_text(body + "\n", encoding="utf-8")
    _storage_mode(path, 0o600)
    return path


def prune_audit(days: int = AUDIT_KEEP_DAYS) -> int:
    """Archive and prune old audit rows without invalidating the live chain.

    The signed anchor records the new retention base, so verification starts at
    the oldest retained row instead of expecting the deleted genesis row.
    """
    init_db()
    cutoff = now() - max(1, int(days)) * 86400
    with LOCK, _connect() as db:
        _ensure_anchor(db)
        db.execute("BEGIN IMMEDIATE")
        old_rows = db.execute(
            "SELECT * FROM admin_audit WHERE ts < ? ORDER BY id ASC", (cutoff,)
        ).fetchall()
        if not old_rows:
            db.rollback()
            return 0
        _archive_rows(old_rows)
        db.execute("DELETE FROM admin_audit WHERE ts < ?", (cutoff,))
        remaining = db.execute(
            "SELECT id, prev_hash, entry_hash FROM admin_audit ORDER BY id ASC"
        ).fetchall()
        db.commit()
    if remaining:
        first = remaining[0]
        last = remaining[-1]
        _reset_anchor(
            int(first["id"]), str(first["prev_hash"] or ""), len(remaining),
            int(last["id"]), str(last["entry_hash"]),
        )
    else:
        _reset_anchor(0, "", 0, 0, "")
    return len(old_rows)


def prune_pipeline_events(days: int = PIPELINE_KEEP_DAYS) -> int:
    init_db()
    cutoff = now() - max(1, int(days)) * 86400
    with LOCK, _connect() as db:
        result = db.execute("DELETE FROM pipeline_events WHERE ts < ?", (cutoff,))
        return int(result.rowcount or 0)


def prune_sessions() -> int:
    init_db()
    stamp = now()
    idle_cutoff = stamp - IDLE_MINUTES * 60
    with LOCK, _connect() as db:
        result = db.execute(
            "DELETE FROM admin_sessions WHERE expires <= ? OR last_seen < ?",
            (stamp, idle_cutoff),
        )
        return int(result.rowcount or 0)
