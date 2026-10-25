"""URL ingest for VibeCut.

One URL bar feeds the native downloader first, with optional separate sidecars:

* ``ytdlp`` for general video sites (in-process Python API, default)
* ``cobalt`` as an optional external fallback for general sites
* ``xhs`` for RedNote / Xiaohongshu notes via an optional sidecar

Provider modules are imported only when a provider is constructed or its
status is checked. Importing this package is always safe; Cobalt and xhs_get
code are never imported into VibeCut.
"""

from __future__ import annotations

from .base import (
    IngestError,
    IngestOptions,
    IngestResult,
    Progress,
    ProgressCallback,
    Provider,
)
from .registry import (
    AUTO,
    COBALT,
    DEFAULT_INGEST_SETTINGS,
    INGEST_DEFAULTS,
    PROVIDER_IDS,
    XHS,
    XHS_DOMAINS,
    YTDLP,
    detect,
    ingest_options,
    normalize_ingest_settings,
    normalize_provider_id,
    normalize_settings,
    options_from_settings,
    provider,
    safe_filename,
    sanitize_filename,
    status,
    validate_ingest_url,
    validate_url,
)

__all__ = [
    "AUTO",
    "COBALT",
    "DEFAULT_INGEST_SETTINGS",
    "INGEST_DEFAULTS",
    "PROVIDER_IDS",
    "XHS",
    "XHS_DOMAINS",
    "YTDLP",
    "IngestError",
    "IngestOptions",
    "IngestResult",
    "Progress",
    "ProgressCallback",
    "Provider",
    "detect",
    "ingest_options",
    "normalize_ingest_settings",
    "normalize_provider_id",
    "normalize_settings",
    "options_from_settings",
    "provider",
    "safe_filename",
    "sanitize_filename",
    "status",
    "validate_ingest_url",
    "validate_url",
]
