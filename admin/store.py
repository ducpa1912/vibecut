"""SQLite-backed admin store: users, sessions, audit, and pipeline events.

The database lives under ``data/admin`` and never stores raw API keys. Audit
values are redacted before they reach the database.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable

import settings_store

LOCK = threading.RLock()
SESSION_HOURS = 12
IDLE_MINUTES = 30
AUDIT_KEEP_DAYS = 365

_SENSITIVE_KEY = re.compile(
    r"(^|_)(api[_-]?key|apikey|key|token|secret|password|passwd|authorization|"
    r"cookie|credential|webhook[_-]?secret)(_|$)",
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


def mask_secret(value: str) -> str:
    """Show first 5 and last 5; short values show only the last 4."""
    text = str(value or "")
    if not text:
        return ""
    if len(text) < 12:
        return ("•" * max(0, len(text) - 4)) + text[-4:]
    return f"{text[:5]}{'•' * 10}{text[-5:]}"


def redact_text(value: Any) -> str:
    text = " ".join(str(value or "").split())
    text = _SECRET_TEXT.sub(r"\1=redacted", text)
    return _SECRET_VALUE.sub("***", text)


def _key_is_secret(key: str) -> bool:
    lowered = str(key or "")
    return bool(_SENSITIVE_KEY.search(lowered)) or lowered.lower() in {
        "api_key", "apikey", "token", "secret", "password", "authorization", "cookie",
    }


def sanitize(value: Any, key: str = "") -> Any:
    """Recursively mask secret-shaped values for audit storage."""
    if isinstance(value, dict):
        return {str(k): sanitize(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(item, key) for item in value]
    if isinstance(value, str):
        text = redact_text(value)
        return mask_secret(text) if _key_is_secret(key) and text else text
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
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return connection


def init_db() -> None:
    with LOCK:
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
            row = db.execute("SELECT * FROM admin_users ORDER BY id LIMIT 1").fetchone()
        return dict(row) if row else None


def create_user(email: str, password: str) -> dict:
    init_db()
    email = str(email or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("A valid admin email is required.")
    if len(str(password or "")) < 12:
        raise ValueError("Admin password must be at least 12 characters.")
    if count_users():
        raise ValueError("An admin already exists; signup is disabled.")
    stamp = now()
    with LOCK, _connect() as db:
        db.execute(
            "INSERT INTO admin_users(email, password_hash, created, updated) VALUES (?, ?, ?, ?)",
            (email, _hash_password(password), stamp, stamp),
        )
        row = db.execute("SELECT * FROM admin_users WHERE email = ?", (email,)).fetchone()
        return dict(row)


def update_user(email: str, password: str | None = None) -> dict:
    init_db()
    email = str(email or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("A valid admin email is required.")
    with LOCK, _connect() as db:
        user = db.execute("SELECT * FROM admin_users LIMIT 1").fetchone()
        if not user:
            raise ValueError("No admin account exists.")
        hash_value = _hash_password(password) if password else user["password_hash"]
        db.execute(
            "UPDATE admin_users SET email = ?, password_hash = ?, updated = ? WHERE id = ?",
            (email, hash_value, now(), int(user["id"])),
        )
        updated = db.execute("SELECT * FROM admin_users WHERE id = ?", (int(user["id"]),)).fetchone()
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
        "actor": str(actor or ""),
        "action": str(action or ""),
        "resource_type": str(resource_type or ""),
        "resource_id": str(resource_id or ""),
        "outcome": str(outcome or "ok"),
        "ip": str(ip or ""),
        "user_agent": str(user_agent or "")[:500],
        "request_id": str(request_id or ""),
        "latency_ms": round(float(latency_ms or 0.0), 3),
        "before": safe_before,
        "after": safe_after,
        "detail": redact_text(detail),
    }
    with LOCK, _connect() as db:
        prev_hash = _last_audit_hash(db)
        entry_hash = hashlib.sha256(
            (prev_hash + json.dumps(payload, ensure_ascii=False, sort_keys=True)).encode("utf-8")
        ).hexdigest()
        db.execute(
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
) -> dict:
    init_db()
    clauses: list[str] = []
    values: list[Any] = []
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
        rows = db.execute("SELECT * FROM admin_audit ORDER BY id ASC").fetchall()
    prev = ""
    for row in rows:
        item = dict(row)
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
            "before": json.loads(item["before_json"]) if item["before_json"] else None,
            "after": json.loads(item["after_json"]) if item["after_json"] else None,
            "detail": item["detail"],
        }
        expected = hashlib.sha256(
            (prev + json.dumps(payload, ensure_ascii=False, sort_keys=True)).encode("utf-8")
        ).hexdigest()
        if item["prev_hash"] != prev or item["entry_hash"] != expected:
            return {"ok": False, "broken_at": item["id"]}
        prev = item["entry_hash"]
    return {"ok": True, "entries": len(rows)}


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
        clauses.append("workflow = ?")
        values.append(workflow)
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


def prune_audit(days: int = AUDIT_KEEP_DAYS) -> int:
    init_db()
    cutoff = now() - max(1, int(days)) * 86400
    with LOCK, _connect() as db:
        result = db.execute("DELETE FROM admin_audit WHERE ts < ?", (cutoff,))
        return int(result.rowcount or 0)
