"""LaMa through PyTorch on the Apple GPU (MPS).

LaMa on the CPU stays on ONNX Runtime (:mod:`textfill.lama`). Core ML takes LaMa's
graph apart, but PyTorch runs it whole on the GPU, Fourier layers included.
"""

from __future__ import annotations

import importlib.util
import os
import platform
import sys
import warnings
from pathlib import Path

import numpy as np

from . import lama as _lama

# An operation MPS lacks runs on the CPU, not as an error. Read when torch loads.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")


def gpu_possible() -> bool:
    """Whether this Mac could run on its GPU, without loading PyTorch to ask."""
    return (
        platform.system() == "Darwin"
        and platform.machine() == "arm64"
        and importlib.util.find_spec("torch") is not None
    )


def release_gpu_memory() -> None:
    torch = sys.modules.get("torch")
    if torch is None:
        return
    try:
        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
    except (AttributeError, RuntimeError):
        pass


def _load(path: Path, device: str):
    import torch

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        model = torch.jit.load(str(path), map_location="cpu")
    return model.to(device).eval()


class LamaGpuFiller:
    """The same LaMa weights as the ONNX file, on the GPU."""

    def __init__(self, model_path: Path):
        self.device = "mps"
        self.provider = "mps"
        self.model = _load(model_path, self.device)

    def fill(self, area: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """Fill ``mask`` (H, W bool) in ``area`` (H, W, 3 uint8). Same size out."""
        import torch

        height, width = mask.shape
        image, small, fit_h, fit_w = _lama.prepare_feed(area, mask)
        feed_image = torch.from_numpy((image.astype(np.float32) / 255.0).transpose(2, 0, 1)[None])
        feed_mask = torch.from_numpy(small.astype(np.float32)[None, None])
        with torch.no_grad():
            result = self.model(feed_image.to(self.device), feed_mask.to(self.device))
            pixels = result[0].permute(1, 2, 0).clamp(0.0, 1.0).mul(255.0).detach().cpu().numpy()
        return _lama.restore(pixels.astype(np.uint8), fit_h, fit_w, height, width)
