"""Free-space preflight for uploads, local paths, renders and batches.

The rule is deliberately simple and conservative: a write is allowed only when
it leaves ``max(5 GiB, 5% of the volume)`` free.  Nothing here deletes files.
Callers either get a report or an :class:`InsufficientSpace` exception that the
API turns into HTTP 412 with a stable payload.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable, Mapping

GIB = 1024 ** 3
MIB = 1024 ** 2
MIN_RESERVE_BYTES = 5 * GIB
RESERVE_FRACTION = 0.05
VALID_TARGETS = (15, 30, 60)


class InsufficientSpace(RuntimeError):
    """Raised when a write would eat the reserved free-space floor."""

    code = "insufficient_space"
    status_code = 412

    def __init__(
        self,
        required_bytes: int,
        free_bytes: int,
        *,
        reserve_bytes: int = 0,
        available_bytes: int | None = None,
        path: str | Path | None = None,
    ) -> None:
        self.required_bytes = max(0, int(required_bytes))
        self.free_bytes = max(0, int(free_bytes))
        self.reserve_bytes = max(0, int(reserve_bytes))
        self.available_bytes = (
            max(0, int(available_bytes))
            if available_bytes is not None
            else max(0, self.free_bytes - self.reserve_bytes)
        )
        self.path = str(path) if path is not None else None
        super().__init__(
            f"Need {self.required_bytes} bytes but only {self.available_bytes} "
            f"bytes are available above the {self.reserve_bytes}-byte reserve."
        )

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "required_bytes": self.required_bytes,
            "free_bytes": self.free_bytes,
            "reserve_bytes": self.reserve_bytes,
            "available_bytes": self.available_bytes,
            "message": str(self),
        }

    def to_dict(self) -> dict:
        return self.as_dict()

    def payload(self) -> dict:
        return self.as_dict()


def _existing_path(path: Path) -> Path:
    path = path.expanduser()
    if path.exists():
        return path
    for parent in path.parents:
        if parent.exists():
            return parent
    return Path("/")


def reserve_bytes(total_bytes: int) -> int:
    """The floor a write must leave free: 5 GiB or 5% of the volume."""
    total = max(0, int(total_bytes or 0))
    return max(MIN_RESERVE_BYTES, int(round(total * RESERVE_FRACTION)))


def usage(path: str | Path) -> shutil._ntuple_diskusage:  # type: ignore[attr-defined]
    """Return ``(total, used, free)`` for the volume holding ``path``."""
    return shutil.disk_usage(str(_existing_path(Path(path))))


def _required_and_path(
    required_bytes: int | str | Path,
    path: str | Path | int | float,
) -> tuple[int, str | Path]:
    """Accept both ``(bytes, path)`` and ``(path, bytes)`` order."""
    if isinstance(required_bytes, (str, Path)) and isinstance(path, (int, float)):
        return max(0, int(path)), required_bytes
    return max(0, int(required_bytes or 0)), path


def report(
    required_bytes: int | str | Path,
    path: str | Path | int | float = ".",
) -> dict:
    """Describe whether ``required_bytes`` fits above the reserve."""
    required, target = _required_and_path(required_bytes, path)
    total, _used, free = usage(target)
    reserve = reserve_bytes(total)
    available = max(0, free - reserve)
    ok = required <= available
    return {
        "ok": ok,
        "code": None if ok else InsufficientSpace.code,
        "required_bytes": required,
        "free_bytes": int(free),
        "reserve_bytes": int(reserve),
        "available_bytes": int(available),
        "shortfall_bytes": max(0, required - available),
        "volume_total_bytes": int(total),
        "path": str(target),
    }


def check(
    required_bytes: int | str | Path,
    path: str | Path | int | float = ".",
) -> dict:
    """Return a space report; never raises."""
    return report(required_bytes, path)


def preflight(
    required_bytes: int | str | Path,
    path: str | Path | int | float = ".",
) -> dict:
    """Raise :class:`InsufficientSpace` unless the write fits."""
    value = report(required_bytes, path)
    if not value["ok"]:
        raise InsufficientSpace(
            value["required_bytes"],
            value["free_bytes"],
            reserve_bytes=value["reserve_bytes"],
            available_bytes=value["available_bytes"],
            path=value["path"],
        )
    return value


def require(
    required_bytes: int | str | Path,
    path: str | Path | int | float = ".",
) -> dict:
    """Alias for :func:`preflight`."""
    return preflight(required_bytes, path)


# ---------------------------------------------------------------- estimates


def _size_of(path: str | Path | None) -> int:
    if not path:
        return 0
    try:
        value = Path(path).expanduser()
        return max(0, int(value.stat().st_size)) if value.is_file() else 0
    except OSError:
        return 0


def estimate_analysis(size_bytes: int, *, copy_source: bool = False) -> int:
    """Estimate analysis workfiles plus an optional source-store copy.

    A job keeps the source (a stored copy for uploads, the original for path
    jobs), thumbnails, a mono speech track, scene metadata and crop paths.  The
    speech track dominates for long sources; 18% of the source with a 64 MiB
    floor is a practical working estimate for a short clip or a long upload.
    """
    size = max(0, int(size_bytes or 0))
    source_copy = size if copy_source else 0
    workfiles = max(64 * MIB, int(size * 0.18))
    return int(source_copy + workfiles)


def estimate_upload(size_bytes: int) -> int:
    """Uploaded sources are moved into the content-addressed store."""
    return estimate_analysis(size_bytes, copy_source=True)


def estimate_path(path: str | Path) -> int:
    """A local path is analyzed in place; keep working-file headroom."""
    return estimate_analysis(_size_of(path), copy_source=False)


def estimate_render(
    target: int = 30,
    quality: str = "final",
    aspect: str = "9:16",
) -> int:
    """Estimate one reel: segment cache, master and final MP4.

    Final video is about 10 Mbit/s on VideoToolbox and roughly comparable at
    CRF 18 with libx264.  Draft is about 3 Mbit/s.  The 2.4x multiplier covers
    the cached segments, concat master and final mux; the floor covers posters
    and concat lists.
    """
    seconds = max(1.0, float(target or 30))
    bitrate = 3_000_000 if str(quality).lower() == "draft" else 10_000_000
    output = seconds * bitrate / 8.0
    return int(max(64 * MIB, output * 2.4 + 16 * MIB))


def _targets(value) -> list[int]:
    if value is None:
        return []
    if isinstance(value, (int, str)):
        value = [value]
    result: list[int] = []
    for raw in value:
        try:
            target = int(raw)
        except (TypeError, ValueError):
            continue
        if target in VALID_TARGETS and target not in result:
            result.append(target)
    return result


def estimate_batch(items: Iterable[Mapping]) -> int:
    """Estimate known bytes for a batch of paths/URLs and requested renders.

    URL sizes are unknown until download, so they contribute only explicit
    ``size_bytes``/``source_bytes`` hints.  Local paths are statted.
    """
    total = 0
    for raw in items or []:
        item = raw if isinstance(raw, Mapping) else {}
        options = item.get("options") if isinstance(item.get("options"), Mapping) else {}
        size = item.get("size_bytes")
        if size is None:
            size = options.get("size_bytes") or options.get("source_bytes")
        if size is None and item.get("path"):
            size = _size_of(item.get("path"))
        if size:
            total += estimate_analysis(int(size or 0), copy_source=False)
        targets = _targets(
            item.get("targets")
            or options.get("targets")
            or options.get("render_targets")
        )
        quality = str(options.get("quality") or "final")
        for target in targets:
            total += estimate_render(target, quality)
    return int(total)


def free_bytes(path: str | Path) -> int:
    """Convenience accessor used by health and tests."""
    return int(usage(path)[2])


# Stable aliases for callers that prefer the longer names.
check_space = check
require_space = preflight
free_space = free_bytes
