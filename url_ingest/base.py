"""Shared contract for VibeCut URL ingest providers.

This module is deliberately dependency-light: standard library only. The
native ``url_ingest.ytdlp`` provider handles ordinary video sites. The optional
``url_ingest.xhs`` module is imported lazily by :mod:`url_ingest.registry`,
so importing the package and detecting a URL never require a sidecar service
to be installed or running.

Every provider implements :class:`Provider` with a settings mapping,
``inspect(url, options)`` for metadata, and
``download(url, dest, options, progress, cancel_event)`` for the file. The
options dataclass below is the shared, JSON-safe surface used by both methods;
providers may ignore options that do not apply to them.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, ClassVar, Mapping

# progress(fraction, message); fraction is 0.0 .. 1.0.
ProgressCallback = Callable[[float, str], None]
Progress = ProgressCallback


class IngestError(RuntimeError):
    """A URL ingest failure whose message is safe to show to the user."""


@dataclass
class IngestOptions:
    """Options shared by all URL ingest providers."""

    quality: str = "max"
    codec: str = "h264"
    container: str = "mp4"
    audio: str = "best"
    cookies: str = "none"
    browser: str = "safari"
    cookie_file: str = ""
    local_processing: str = "preferred"  # preferred | forced
    no_record: bool = True
    interval: float = 12.0

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-ready representation for API responses."""
        return {
            "quality": self.quality,
            "codec": self.codec,
            "container": self.container,
            "audio": self.audio,
            "cookies": self.cookies,
            "browser": self.browser,
            "local_processing": self.local_processing,
            "no_record": self.no_record,
            "interval": self.interval,
        }


@dataclass
class IngestResult:
    """A downloaded video ready to enter the normal VibeCut pipeline."""

    path: Path
    filename: str
    provider: str
    title: str = ""
    duration: float | None = None
    thumbnail: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        self.filename = str(self.filename or self.path.name)
        self.provider = str(self.provider or "")
        self.meta = dict(self.meta or {})


class Provider:
    """Base class for URL ingest providers.

    Concrete providers may override :meth:`status` to add their own local
    health checks. If they do not, the registry supplies a settings-based
    status based on ``required_settings``.
    """

    id: ClassVar[str] = ""
    label: ClassVar[str] = ""
    required_settings: ClassVar[tuple[str, ...]] = ()

    def __init__(self, settings: Mapping[str, Any] | None = None) -> None:
        self.settings: dict[str, Any] = dict(settings or {})

    def inspect(self, url: str, options: IngestOptions) -> dict[str, Any]:
        """Resolve metadata for *url* without downloading the video."""
        raise NotImplementedError

    def download(
        self,
        url: str,
        dest: Path,
        options: IngestOptions,
        progress: ProgressCallback,
        cancel_event: threading.Event,
    ) -> IngestResult:
        """Download *url* into *dest* and return the local file."""
        raise NotImplementedError

    def status(self, settings: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Return ``{id,label,configured,available,error}`` for Setup."""
        merged: dict[str, Any] = dict(getattr(self, "settings", {}) or {})
        if settings:
            merged.update(settings)
        missing = [name for name in self.required_settings if not merged.get(name)]
        configured = not missing
        error = ""
        if missing:
            error = "Missing setting: " + ", ".join(missing)
        return {
            "id": self.id,
            "label": self.label,
            "configured": configured,
            "available": configured,
            "error": error,
        }
