"""LaMa image fill through ONNX Runtime.

Model: ``lama_fp32.onnx`` from Carve/LaMa-ONNX (Apache 2.0), a port of
big-lama. Inputs ``image`` [1,3,512,512] in 0..1 and ``mask`` [1,1,512,512]
(1 = fill); output ``output`` [1,3,512,512] in 0..255.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from PIL import Image

SIZE = 512
MODEL_FILE = "lama_fp32.onnx"


def _providers() -> list[str]:
    # CoreML takes only about half of this graph, in 585 pieces, so plain CPU
    # is the default. VIBECUT_FILL_LAMA_PROVIDER=coreml tries it first.
    choice = (os.environ.get("VIBECUT_FILL_LAMA_PROVIDER") or "cpu").strip().lower()
    if choice == "coreml":
        return ["CoreMLExecutionProvider", "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


def fit(height: int, width: int) -> tuple[int, int]:
    """Size (h, w) that fits inside SIZE x SIZE and keeps the aspect."""
    scale = SIZE / float(max(height, width))
    return (
        max(1, min(SIZE, int(round(height * scale)))),
        max(1, min(SIZE, int(round(width * scale)))),
    )


class LamaFiller:
    def __init__(self, model_path: Path):
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.log_severity_level = 3
        self.session = ort.InferenceSession(
            str(model_path), sess_options=options, providers=_providers(),
        )
        self.provider = self.session.get_providers()[0]

    def fill(self, area: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """Fill ``mask`` (H, W bool) in ``area`` (H, W, 3 uint8). Same size out."""
        height, width = mask.shape
        fit_h, fit_w = fit(height, width)
        image = np.asarray(
            Image.fromarray(area).resize((fit_w, fit_h), Image.BICUBIC),
            dtype=np.uint8,
        )
        small = np.asarray(
            Image.fromarray(mask.astype(np.uint8) * 255).resize((fit_w, fit_h), Image.BILINEAR),
        ) > 0
        pad = ((0, SIZE - fit_h), (0, SIZE - fit_w))
        image = np.pad(image, pad + ((0, 0),), mode="edge")
        small = np.pad(small, pad, mode="constant")
        feed_image = (image.astype(np.float32) / 255.0).transpose(2, 0, 1)[None]
        feed_mask = small.astype(np.float32)[None, None]
        result = self.session.run(None, {"image": feed_image, "mask": feed_mask})[0][0]
        result = np.clip(result.transpose(1, 2, 0), 0, 255).astype(np.uint8)
        result = result[:fit_h, :fit_w]
        return np.asarray(
            Image.fromarray(result).resize((width, height), Image.BICUBIC),
            dtype=np.uint8,
        )
