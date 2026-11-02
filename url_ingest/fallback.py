"""Ordered provider fallback for URL ingest.

The normal URL path uses ``yt-dlp`` first. RedNote/Xiaohongshu links stay on
their dedicated provider and never fall back to another downloader.

This module is deliberately small and dependency-light: it imports only the
standard library and :mod:`url_ingest.base`. It never imports the concrete
providers, the registry, or the application. Provider factories are resolved
lazily, so an unavailable optional provider cannot break the primary path.

Download attempts use a unique temporary path. A failed attempt is cleaned up
before the next provider starts, so two providers never write to the same
destination and stale partials are not mistaken for a finished download.
"""

from __future__ import annotations

import re
import shutil
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .base import IngestError, IngestOptions, IngestResult, ProgressCallback, Provider

AUTO = "auto"
YTDLP = "ytdlp"
XHS = "xhs"

_PROVIDER_IDS = frozenset({YTDLP, XHS})
_ALIASES = {
    "": AUTO,
    AUTO: AUTO,
    YTDLP: YTDLP,
    "yt-dlp": YTDLP,
    "yt_dlp": YTDLP,
    "youtube-dl": YTDLP,
    XHS: XHS,
    "xhs-get": XHS,
    "xhs_get": XHS,
    "rednote": XHS,
    "xiaohongshu": XHS,
}
_CANCEL_WORDS = ("cancel",)


def _provider_id(value: Any) -> str:
    key = str(value or "").strip().lower()
    return _ALIASES.get(key, AUTO)


def fallback_provider_ids(
    configured: Any,
    detected: Any,
    ytdlp_available: bool,
) -> list[str]:
    """Return the ordered provider ids to try for one link.

    ``configured`` is the user's provider setting or request override.
    ``detected`` is the registry's URL detection result. Explicit providers win
    and are the only entry. In auto mode, RedNote/Xiaohongshu stays on ``xhs``;
    every other link gets yt-dlp.
    """

    requested = _provider_id(configured)
    if requested in _PROVIDER_IDS:
        return [requested]

    detected_id = _provider_id(detected)
    if detected_id == XHS:
        return [XHS]

    # Keep yt-dlp first even when the package is unavailable, so its install
    # error is the primary failure.
    return [YTDLP]


@dataclass(frozen=True)
class Attempt:
    """One provider inspect or download attempt."""

    provider: str
    stage: str
    ok: bool
    error: str = ""
    cancelled: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "stage": self.stage,
            "ok": self.ok,
            "error": self.error,
            "cancelled": self.cancelled,
        }


class ChainError(IngestError):
    """Every provider in a chain failed.

    ``str(error)`` is the first provider's error, not the fallback's. The full
    attempt list is available on :attr:`attempts` and is also suitable for job
    metadata. Cancellation is represented by ``cancelled=True`` and is final;
    no later provider is tried after it.
    """

    def __init__(
        self,
        message: str,
        *,
        attempts: Sequence[Attempt] = (),
        cancelled: bool = False,
        primary_provider: str = "",
        primary_error: str = "",
        fallback_error: str = "",
    ) -> None:
        text = " ".join(str(message or "").split()) or "URL ingest failed."
        super().__init__(text)
        self.attempts: tuple[Attempt, ...] = tuple(attempts)
        self.cancelled = bool(cancelled)
        self.primary_provider = str(primary_provider or "")
        self.primary_error = str(primary_error or text)
        self.fallback_error = str(fallback_error or "")

    def as_dict(self) -> dict[str, Any]:
        return {
            "error": str(self),
            "cancelled": self.cancelled,
            "primary_provider": self.primary_provider,
            "primary_error": self.primary_error,
            "fallback_error": self.fallback_error,
            "attempts": [attempt.as_dict() for attempt in self.attempts],
        }

    @property
    def meta(self) -> dict[str, Any]:
        """Failure metadata shaped like the successful result's meta entry."""

        return self.as_dict()


ProviderFactory = Callable[[], Provider]
ProviderSource = Provider | ProviderFactory
ProviderMap = (
    Mapping[str, ProviderSource]
    | Sequence[ProviderSource]
    | Sequence[tuple[str, ProviderSource]]
)


def _error_text(exc: BaseException) -> str:
    text = " ".join(str(exc).split())
    return (text or exc.__class__.__name__)[:400]


def _looks_cancelled(exc: BaseException, cancel_event: threading.Event) -> bool:
    if cancel_event.is_set():
        return True
    text = str(exc).lower()
    return any(word in text for word in _CANCEL_WORDS)


def _noop_progress(fraction: float, message: str) -> None:
    return None


def _is_factory(source: ProviderSource) -> bool:
    if isinstance(source, type):
        return True
    if not callable(source):
        return False
    return not callable(getattr(source, "download", None))


def _source_id(source: ProviderSource) -> str:
    value = getattr(source, "id", "") or getattr(type(source), "id", "")
    return str(value or type(source).__name__.lower()).strip()


def _provider_items(providers: ProviderMap) -> list[tuple[str, ProviderSource]]:
    if isinstance(providers, Mapping):
        raw_items: list[tuple[Any, ProviderSource]] = list(providers.items())
    elif isinstance(providers, (str, bytes)) or not isinstance(providers, Sequence):
        raise IngestError("An ingest provider chain needs a provider list or mapping.")
    else:
        raw_items = []
        for item in providers:
            if (
                isinstance(item, (tuple, list))
                and len(item) == 2
                and isinstance(item[0], str)
            ):
                raw_items.append((item[0], item[1]))
            else:
                raw_items.append((_source_id(item), item))

    items: list[tuple[str, ProviderSource]] = []
    seen: set[str] = set()
    for raw_id, source in raw_items:
        provider_id = str(raw_id or _source_id(source)).strip()
        if not provider_id:
            raise IngestError("An ingest provider in the chain has no id.")
        if provider_id in seen:
            continue
        seen.add(provider_id)
        items.append((provider_id, source))
    if not items:
        raise IngestError("The ingest provider chain is empty.")
    return items


def _ordered_items(
    providers: ProviderMap, order: Sequence[str] | None
) -> list[tuple[str, ProviderSource]]:
    items = _provider_items(providers)
    if order is None:
        return items

    available = {provider_id: source for provider_id, source in items}
    ordered: list[tuple[str, ProviderSource]] = []
    used: set[str] = set()
    for raw_id in order:
        provider_id = str(raw_id or "").strip()
        if provider_id not in available:
            alias = _provider_id(provider_id)
            if alias in available:
                provider_id = alias
        if provider_id not in available:
            raise IngestError(f"Unknown ingest provider {raw_id!r} in fallback chain.")
        if provider_id in used:
            continue
        used.add(provider_id)
        ordered.append((provider_id, available[provider_id]))
    if not ordered:
        raise IngestError("The ingest provider chain is empty.")
    return ordered


def _resolve_source(provider_id: str, source: ProviderSource, stage: str) -> Provider:
    try:
        provider = source() if _is_factory(source) else source
    except IngestError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise IngestError(
            f"{provider_id} provider could not be created: {_error_text(exc)}"
        ) from exc

    method = "inspect" if stage == "inspect" else "download"
    if provider is None or not callable(getattr(provider, method, None)):
        raise IngestError(f"{provider_id} provider cannot {method} links.")
    return provider


def _attempt_dest(dest: Path, provider_id: str, index: int) -> Path:
    """Return a unique sibling path so attempts cannot reuse partial files."""

    suffix = dest.suffix or ".mp4"
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", provider_id)[:32] or "provider"
    token = uuid.uuid4().hex[:10]
    return dest.with_name(
        f".{dest.stem}.{safe_id}.{index}.{token}{suffix}"
    )


def _cleanup_attempt(path: Path) -> None:
    """Remove a failed attempt's file and its provider sidecars."""

    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
            return
        if path.is_file() or path.is_symlink():
            path.unlink(missing_ok=True)
    except OSError:
        pass
    try:
        prefixes = {path.stem, path.stem.lstrip(".")}
        for prefix in prefixes:
            for item in path.parent.glob(f"{prefix}*"):
                try:
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                    else:
                        item.unlink(missing_ok=True)
                except OSError:
                    pass
    except OSError:
        pass


def _attach_attempts(
    result: IngestResult,
    attempts: Sequence[Attempt],
    primary_provider: str,
    provider_id: str,
) -> IngestResult:
    if not isinstance(result, IngestResult):
        raise IngestError(f"{provider_id} provider returned an invalid result.")
    if not result.provider:
        result.provider = provider_id
    entries = [attempt.as_dict() for attempt in attempts]
    meta = dict(result.meta or {})
    meta["attempts"] = entries
    meta["fallback"] = {
        "provider": result.provider,
        "primary": primary_provider,
        "used": len(attempts) > 1,
        "attempts": [dict(entry) for entry in entries],
    }
    result.meta = meta
    # Convenience for callers that want the attempt list without opening meta.
    # IngestResult is not slotted, and ``meta`` remains the serialized contract.
    result.attempts = tuple(attempts)
    return result


class ProviderChain:
    """Run inspect/download attempts in a fixed, pre-computed order.

    Provider values may be instances or zero-argument factories. Factories are
    resolved only when their turn comes, so an optional provider is constructed
    lazily.
    """

    def __init__(
        self,
        providers: ProviderMap,
        order: Sequence[str] | None = None,
    ) -> None:
        self._items = _ordered_items(providers, order)
        self.last_attempts: tuple[Attempt, ...] = ()
        self.attempts: tuple[Attempt, ...] = ()
        self.last_provider: Provider | None = None
        self.last_provider_id = ""

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(provider_id for provider_id, _ in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def _set_attempts(self, attempts: Sequence[Attempt]) -> None:
        self.last_attempts = tuple(attempts)
        self.attempts = self.last_attempts

    def inspect(
        self,
        url: str,
        options: IngestOptions | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        """Inspect with fallback. Cancellation never triggers another provider."""

        cancel = cancel_event if cancel_event is not None else threading.Event()
        resolved_options = options if options is not None else IngestOptions()
        attempts: list[Attempt] = []
        primary_provider = self._items[0][0]
        primary_error = ""
        primary_message = ""
        fallback_error = ""
        last_index = len(self._items) - 1

        for index, (provider_id, source) in enumerate(self._items):
            if cancel.is_set():
                self._set_attempts(attempts)
                raise ChainError(
                    "Inspection cancelled.",
                    attempts=attempts,
                    cancelled=True,
                    primary_provider=primary_provider,
                    primary_error=primary_message or "Inspection cancelled.",
                )
            try:
                provider = _resolve_source(provider_id, source, "inspect")
                self.last_provider = provider
                self.last_provider_id = provider_id
                if cancel.is_set():
                    raise IngestError("Inspection cancelled.")
                inspected = provider.inspect(url, resolved_options)
                if not isinstance(inspected, dict):
                    raise IngestError(
                        f"{provider_id} provider returned an invalid inspection result."
                    )
                if cancel.is_set():
                    raise IngestError("Inspection cancelled.")
                if inspected.get("available") is False and index < last_index:
                    error = " ".join(
                        str(
                            inspected.get("warning")
                            or inspected.get("error")
                            or "The provider could not inspect this link."
                        ).split()
                    )[:400]
                    raise IngestError(error)
            except Exception as exc:  # noqa: BLE001
                cancelled = _looks_cancelled(exc, cancel)
                message = "Inspection cancelled." if cancelled else _error_text(exc)
                attempts.append(
                    Attempt(provider_id, "inspect", False, message, cancelled)
                )
                fallback_error = message
                if not primary_error:
                    primary_error = message
                    primary_message = message
                self._set_attempts(attempts)
                if cancelled:
                    raise ChainError(
                        "Inspection cancelled.",
                        attempts=attempts,
                        cancelled=True,
                        primary_provider=primary_provider,
                        primary_error=primary_message,
                    ) from exc
                continue

            attempts.append(Attempt(provider_id, "inspect", True))
            self._set_attempts(attempts)
            return inspected

        self._set_attempts(attempts)
        raise ChainError(
            primary_error or "Could not inspect this URL.",
            attempts=attempts,
            primary_provider=primary_provider,
            primary_error=primary_message or primary_error,
            fallback_error=fallback_error,
        )

    def download(
        self,
        url: str,
        dest: Path,
        options: IngestOptions | None = None,
        progress: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> IngestResult:
        """Download with fallback and attach attempt metadata to the result.

        A failed attempt is removed before the next provider runs. If every
        provider fails, :class:`ChainError` carries the first provider's error
        verbatim plus the full attempt list.
        """

        cancel = cancel_event if cancel_event is not None else threading.Event()
        report = progress or _noop_progress
        resolved_options = options if options is not None else IngestOptions()
        destination = Path(dest)
        attempts: list[Attempt] = []
        primary_provider = self._items[0][0]
        primary_error = ""
        primary_message = ""
        fallback_error = ""

        for index, (provider_id, source) in enumerate(self._items):
            if cancel.is_set():
                self._set_attempts(attempts)
                raise ChainError(
                    "Download cancelled.",
                    attempts=attempts,
                    cancelled=True,
                    primary_provider=primary_provider,
                    primary_error=primary_message or "Download cancelled.",
                )

            attempt_dest = _attempt_dest(destination, provider_id, index)
            try:
                attempt_dest.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                message = f"Could not prepare a download path: {_error_text(exc)}"
                attempts.append(
                    Attempt(provider_id, "download", False, message)
                )
                if not primary_error:
                    primary_error = message
                    primary_message = message
                fallback_error = message
                continue

            try:
                provider = _resolve_source(provider_id, source, "download")
                self.last_provider = provider
                self.last_provider_id = provider_id
                if cancel.is_set():
                    raise IngestError("Download cancelled.")
                result = provider.download(
                    url, attempt_dest, resolved_options, report, cancel
                )
                if cancel.is_set():
                    raise IngestError("Download cancelled.")
                if not isinstance(result, IngestResult):
                    raise IngestError(
                        f"{provider_id} provider returned an invalid result."
                    )
            except Exception as exc:  # noqa: BLE001
                cancelled = _looks_cancelled(exc, cancel)
                message = "Download cancelled." if cancelled else _error_text(exc)
                attempts.append(
                    Attempt(provider_id, "download", False, message, cancelled)
                )
                fallback_error = message
                if not primary_error:
                    primary_error = message
                    primary_message = message
                self._set_attempts(attempts)
                _cleanup_attempt(attempt_dest)
                if cancelled:
                    raise ChainError(
                        "Download cancelled.",
                        attempts=attempts,
                        cancelled=True,
                        primary_provider=primary_provider,
                        primary_error=primary_message,
                    ) from exc
                continue

            attempts.append(Attempt(provider_id, "download", True))
            self._set_attempts(attempts)
            return _attach_attempts(
                result, attempts, primary_provider, provider_id
            )

        self._set_attempts(attempts)
        raise ChainError(
            primary_error or "URL ingest failed.",
            attempts=attempts,
            primary_provider=primary_provider,
            primary_error=primary_message or primary_error,
            fallback_error=fallback_error,
        )


def run_download(
    providers: ProviderMap,
    url: str,
    dest: Path,
    options: IngestOptions | None = None,
    progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
    order: Sequence[str] | None = None,
) -> IngestResult:
    """Download through an ordered provider chain.

    ``order`` optionally selects/reorders ids from ``providers``; use
    :func:`fallback_provider_ids` to build it. The successful result's ``meta``
    contains ``attempts`` and a structured ``fallback`` entry.
    """

    chain = ProviderChain(providers, order=order)
    return chain.download(
        url,
        dest,
        options if options is not None else IngestOptions(),
        progress,
        cancel_event,
    )


def run_inspect(
    providers: ProviderMap,
    url: str,
    options: IngestOptions | None = None,
    cancel_event: threading.Event | None = None,
    order: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Inspect through an ordered provider chain. Attempts are on the chain."""

    chain = ProviderChain(providers, order=order)
    return chain.inspect(
        url,
        options if options is not None else IngestOptions(),
        cancel_event,
    )


__all__ = [
    "AUTO",
    "XHS",
    "YTDLP",
    "Attempt",
    "ChainError",
    "ProviderChain",
    "fallback_provider_ids",
    "run_download",
    "run_inspect",
]
