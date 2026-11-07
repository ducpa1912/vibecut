"""Request signing for the worker contract.

Header:

    X-DuckClean-Signature: t=<unix seconds>,v1=<hex hmac>
    X-DuckClean-Key-Id:    <rotation id>

Signed payload is ``b"<t>." + raw_body``. The API and the worker use the same
secret; the key id lets a rotation overlap. Clock skew over 300 seconds is
rejected, so a captured request cannot be replayed later.
"""

from __future__ import annotations

import hashlib
import hmac
import time

MAX_SKEW_SECONDS = 300
SIGNATURE_HEADER = "X-DuckClean-Signature"
KEY_ID_HEADER = "X-DuckClean-Key-Id"


class SignatureError(Exception):
    """Raised for a missing, malformed, stale or mismatched signature."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def signed_payload(timestamp: int, body: bytes) -> bytes:
    return f"{timestamp}.".encode("ascii") + body


def sign(secret: str, body: bytes, timestamp: int | None = None) -> str:
    ts = int(time.time()) if timestamp is None else int(timestamp)
    digest = hmac.new(secret.encode("utf-8"), signed_payload(ts, body), hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


def verify(
    secret: str,
    header: str | None,
    body: bytes,
    *,
    now: int | None = None,
    max_skew: int = MAX_SKEW_SECONDS,
) -> int:
    """Return the signed timestamp or raise SignatureError.

    Comparison is constant-time for the digest and the skew is checked before
    the digest, so a stale request fails fast without leaking a timing oracle.
    """
    if not header:
        raise SignatureError("missing")

    fields: dict[str, str] = {}
    for part in header.split(","):
        key, sep, value = part.strip().partition("=")
        if not sep or not key:
            raise SignatureError("malformed")
        fields[key] = value

    timestamp_raw = fields.get("t")
    provided = fields.get("v1")
    if not timestamp_raw or not provided:
        raise SignatureError("malformed")

    try:
        timestamp = int(timestamp_raw)
    except ValueError as exc:
        raise SignatureError("malformed") from exc

    current = int(time.time()) if now is None else int(now)
    if abs(current - timestamp) > max_skew:
        raise SignatureError("clock_skew")

    expected = hmac.new(
        secret.encode("utf-8"), signed_payload(timestamp, body), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, provided):
        raise SignatureError("mismatch")

    return timestamp
