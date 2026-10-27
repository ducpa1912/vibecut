"""Rights policy: the one server-side source for import and Clean gates.

The policy is intentionally small and pure. It reads a job record and the
stored settings; it never reads a request body or browser storage. The hard
rules hold whether the Setup lock is on or off:

* a ``watermark`` is always refused;
* ``screen_text`` is never cleaned (a quality rule, not a rights rule);
* a ``handle_or_logo`` always needs the per-video ``attested`` tick.

With ``rights.lock`` on, every other Clean kind also needs the tick and an
import must carry it. With the lock off, those open up. A job created before
the rights record existed counts as attested, matching the old migration rule.
"""

from __future__ import annotations

from typing import Any

import settings_store

DEFAULT_LOCK = True

IMPORT_CONFIRMATION = (
    "Confirm you own this footage or have the rights to it."
)

KINDS = (
    "subtitle", "title", "lower_third", "handle_or_logo", "watermark", "credit",
    "screen_text",
)

_TRUE_ATTESTATION = {
    "1", "true", "yes", "on", "own", "owned", "attested",
    "i own this footage", "own footage", "i have permission",
}


def normalize_attestation(value: Any) -> bool:
    """Read the loose shapes stored by older imports and Check records."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in _TRUE_ATTESTATION
    if isinstance(value, dict):
        return normalize_attestation(value.get("attested"))
    return False


def _normalize_lock(value: Any, default: bool = DEFAULT_LOCK) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        folded = value.strip().casefold()
        if folded in {"1", "true", "yes", "on"}:
            return True
        if folded in {"0", "false", "no", "off", ""}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def lock_enabled(settings: dict | None = None) -> bool:
    """Return ``rights.lock``; true when the setting is absent or malformed."""
    if settings is None:
        settings = settings_store.load_settings()
    if not isinstance(settings, dict):
        return DEFAULT_LOCK
    section = settings.get("rights")
    if isinstance(section, dict):
        return _normalize_lock(section.get("lock"))
    # Tolerate a bare {"lock": ...} passed by a test or an older caller.
    if "lock" in settings and "rights" not in settings:
        return _normalize_lock(settings.get("lock"))
    return DEFAULT_LOCK


def job_attested(job: dict | None) -> bool:
    """Whether this job carries the own-footage tick.

    A job with no rights evidence at all predates the record and counts as
    attested, so old Clean layers keep saving. A rights record that exists but
    is not true stays locked.
    """
    if not isinstance(job, dict):
        return False
    record = job.get("rights")
    if isinstance(record, dict) and "attested" in record:
        return normalize_attestation(record.get("attested"))
    if "attestation" in job:
        return normalize_attestation(job.get("attestation"))
    options = job.get("options")
    if isinstance(options, dict) and "attestation" in options:
        return normalize_attestation(options.get("attestation"))
    if isinstance(record, dict):
        # A rights record without an attested field is not an attestation.
        return False
    return True


def may_import(attested: bool | None) -> bool:
    """Whether an import may start. Only an explicit tick passes the lock."""
    if not lock_enabled():
        return True
    return normalize_attestation(attested)


def clean_block_reason(
    kind: str,
    *,
    job: dict | None,
    settings: dict | None = None,
) -> str | None:
    """Return why a Clean layer may not target this kind, or ``None``."""
    normalized = str(kind or "").strip().casefold()
    if normalized == "watermark":
        return "watermark"
    if normalized == "screen_text":
        return "screen_text"
    attested = job_attested(job)
    if not attested:
        if normalized == "handle_or_logo":
            return "attestation_required"
        if lock_enabled(settings):
            return "rights_not_attested"
    return None


def policy(job: dict | None = None) -> dict:
    """The frozen policy shape served to Studio."""
    settings = settings_store.load_settings()
    lock = lock_enabled(settings)
    attested = job_attested(job) if isinstance(job, dict) else False
    return {
        "lock": lock,
        "attested": attested,
        "needs_import_tick": bool(lock and not attested),
        "clean": {
            kind: clean_block_reason(kind, job=job, settings=settings)
            for kind in KINDS
        },
    }
