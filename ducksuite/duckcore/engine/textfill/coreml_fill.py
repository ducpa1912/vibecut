"""LaMa through Apple Core ML on the GPU (REQ-20261116-01).

The same big-lama weights as ``big-lama.pt``, converted by
``scripts/coreml/convert_lama.py`` to ``lama_fill.mlpackage``. Core ML cannot run
LaMa's Fourier layers at a free size, so the package holds one function per
size in :data:`BUCKETS` that shares one copy of the weights. A run is padded up to
the smallest bucket that holds it, the same way the CPU and PyTorch engines pad up
to a multiple of 16.

Measured on an M1 8 GB Mac at 512x512: 406 ms a run against 550 ms for PyTorch on
the GPU, pixels within 3 of 255 (``docs/teams/coreml-lama-test/review.md``). The
Neural Engine is not asked for: Apple's compiler rejects LaMa there and the first
load then takes minutes.

The package is compiled once into app data (``<models>/cache``) so later loads
skip the compile.
"""

from __future__ import annotations

import importlib.util
import hashlib
import logging
import os
import platform
import shutil
import threading
from pathlib import Path

import numpy as np

from . import lama as _lama

LOGGER = logging.getLogger(__name__)

PACKAGE_FILE = "lama_fill.mlpackage"
CACHE_DIR = "cache"
# The long side of a LaMa run is always 512 (``lama.fit``); the short side is
# padded up to one of these. Both ways round.
SHORT_SIDES = (64, 128, 192, 256, 384, 512)
BUCKETS = tuple(sorted({(512, s) for s in SHORT_SIDES} | {(s, 512) for s in SHORT_SIDES}))

_COMPILE_LOCK = threading.Lock()


def function_name(height: int, width: int) -> str:
    return f"h{height}w{width}"


def bucket(height: int, width: int) -> tuple[int, int]:
    """The smallest bucket that holds a run of this size."""
    fits = [b for b in BUCKETS if b[0] >= height and b[1] >= width]
    if not fits:
        return SIZE_FULL
    return min(fits, key=lambda b: (b[0] * b[1], b))


SIZE_FULL = (512, 512)


def possible() -> bool:
    """Whether this Mac could run Core ML here, without loading it to ask."""
    return (
        platform.system() == "Darwin"
        and platform.machine() == "arm64"
        and importlib.util.find_spec("coremltools") is not None
    )


def package_stamp(path: Path) -> str:
    """File metadata identity, including paths, for compiled/render caches."""
    total = newest = 0
    identity = hashlib.sha256()
    for item in sorted(Path(path).rglob("*")):
        if item.is_file():
            stat = item.stat()
            total += stat.st_size
            newest = max(newest, stat.st_mtime_ns)
            identity.update(f'{item.relative_to(path)}:{stat.st_size}:{stat.st_mtime_ns}'.encode())
    return f"{Path(path).name}:{total}:{newest}:{identity.hexdigest()[:16]}"


def package_digest(path: Path) -> str:
    """Content identity used when installing a replacement package."""
    digest = hashlib.sha256()
    root = Path(path)
    for item in sorted(root.rglob('*')):
        if item.is_file():
            digest.update(str(item.relative_to(root)).encode())
            digest.update(b'\0')
            with item.open('rb') as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                    digest.update(chunk)
    return digest.hexdigest()


def _compiled(package: Path, cache: Path) -> Path:
    """The compiled model in app data, compiled once per package stamp."""
    import coremltools as ct

    stamp = package_stamp(package).replace(":", "-")
    target = cache / f"lama_fill-{stamp}.mlmodelc"
    with _COMPILE_LOCK:
        if target.is_dir():
            return target
        cache.mkdir(parents=True, exist_ok=True)
        part = cache / f".{target.stem}.part.mlmodelc"
        shutil.rmtree(part, ignore_errors=True)
        try:
            built = Path(ct.models.utils.compile_model(str(package), str(part)))
            os.replace(built, target)
        finally:
            shutil.rmtree(part, ignore_errors=True)
        for old in cache.glob("lama_fill-*.mlmodelc"):
            if old != target:
                shutil.rmtree(old, ignore_errors=True)
        return target


class LamaCoreMLFiller:
    """LaMa on the Apple GPU through Core ML. One loaded function per bucket."""

    def __init__(self, package: Path, cache: Path | None = None):
        import coremltools as ct

        self.provider = "coreml-gpu"
        self.device = "gpu"
        package = Path(package)
        self._units = ct.ComputeUnit.CPU_AND_GPU
        self._models: dict[tuple[int, int], object] = {}
        self._lock = threading.Lock()
        try:
            self._compiled = _compiled(package, Path(cache) if cache else package.parent / CACHE_DIR)
            self._model(*SIZE_FULL)  # fail here, not mid-render, when the file is bad
        except Exception as exc:  # noqa: BLE001 - the caller moves to the next engine
            raise RuntimeError(f"Core ML could not load the fill model: {exc}") from exc

    def _model(self, height: int, width: int):
        import coremltools as ct

        key = (height, width)
        with self._lock:
            model = self._models.get(key)
            if model is None:
                model = ct.models.CompiledMLModel(
                    str(self._compiled), compute_units=self._units,
                    function_name=function_name(height, width),
                )
                self._models[key] = model
            return model

    def fits(self, height: int, width: int) -> bool:
        """Whether a work area of this size has its own exact Core ML function."""
        fit_h, fit_w = _lama.fit(int(height), int(width))
        return bucket(fit_h, fit_w) == _lama.input_size(fit_h, fit_w, True)

    def fill(self, area: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """Fill ``mask`` (H, W bool) in ``area`` (H, W, 3 uint8). Same size out."""
        height, width = mask.shape
        image, small, fit_h, fit_w = _lama.fit_images(area, mask)
        run_h, run_w = bucket(fit_h, fit_w)
        native = _lama.input_size(fit_h, fit_w, True)
        if (run_h, run_w) != native:
            raise RuntimeError(
                f"Core ML has no exact {native[0]}x{native[1]} function; using the GPU fallback to preserve padding."
            )
        pad = ((0, run_h - fit_h), (0, run_w - fit_w))
        image = np.pad(image, pad + ((0, 0),), mode="edge")
        small = np.pad(small, pad, mode="constant")
        feed = {
            "image": (image.astype(np.float32) / 255.0).transpose(2, 0, 1)[None],
            "mask": small.astype(np.float32)[None, None],
        }
        try:
            result = self._model(run_h, run_w).predict(feed)["output"]
        except Exception as exc:  # noqa: BLE001 - the caller moves to the next engine
            raise RuntimeError(f"Core ML fill failed: {exc}") from exc
        pixels = np.clip(result[0].transpose(1, 2, 0), 0.0, 1.0) * 255.0
        return _lama.restore(pixels.astype(np.uint8), fit_h, fit_w, height, width)
