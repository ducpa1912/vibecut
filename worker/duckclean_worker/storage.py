"""Pull sources and put derivatives through short-lived presigned URLs.

The worker never holds an R2 credential and never talks to Postgres. A URL in
the signed request is the whole authority, and it expires.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

MAX_SOURCE_BYTES = 5_000_000_000
CHUNK_BYTES = 1024 * 1024


def _local_path(url: str) -> Path | None:
    """Resolve a ``file://`` URL for local integration tests only.

    Production requests always carry presigned HTTP URLs. Local file URLs stay
    disabled unless the test harness sets ``DUCKCLEAN_WORKER_ALLOW_LOCAL=1``;
    a signed request must never be able to read an arbitrary local path.
    """
    if not url.startswith("file://"):
        return None
    if os.environ.get("DUCKCLEAN_WORKER_ALLOW_LOCAL") != "1":
        raise StorageError("file_urls_disabled")
    parsed = urlparse(url)
    if parsed.netloc not in ("", "localhost"):
        raise StorageError("invalid_file_url")
    return Path(unquote(parsed.path))


class StorageError(Exception):
    """A transfer that did not complete. The API retries or reports the failure."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def download(
    url: str,
    destination: Path,
    *,
    timeout_seconds: float = 900.0,
    max_bytes: int = MAX_SOURCE_BYTES,
) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    local = _local_path(url)
    if local is not None:
        if not local.is_file():
            raise StorageError("download_failed")
        size = local.stat().st_size
        if size > max_bytes:
            raise StorageError("too_large")
        shutil.copyfile(local, destination)
        return size
    total = 0
    try:
        with (
            httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client,
            client.stream("GET", url) as response,
            destination.open("wb") as handle,
        ):
            response.raise_for_status()
            for chunk in response.iter_bytes(CHUNK_BYTES):
                total += len(chunk)
                if total > max_bytes:
                    raise StorageError("too_large")
                handle.write(chunk)
    except httpx.HTTPError as exc:
        raise StorageError("download_failed") from exc
    if total == 0:
        raise StorageError("empty_source")
    return total


def _headers_for(url_method_headers: dict[str, str], content_type: str) -> dict[str, str]:
    """Signed request headers are replayed exactly; content-type is part of it."""
    headers = dict(url_method_headers)
    headers.setdefault("content-type", content_type)
    return headers


def upload(
    url: str,
    source: Path,
    *,
    content_type: str,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 900.0,
) -> int:
    if not source.exists() or source.stat().st_size == 0:
        raise StorageError("missing_output")
    size = source.stat().st_size
    local = _local_path(url)
    if local is not None:
        local.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, local)
        return size
    request_headers = _headers_for(headers or {}, content_type)
    request_headers["content-length"] = str(size)
    try:
        with (
            httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client,
            source.open("rb") as handle,
        ):
            response = client.put(url, content=handle, headers=request_headers)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise StorageError("upload_failed") from exc
    return size
