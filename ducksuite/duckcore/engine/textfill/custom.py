"""A fill model the user supplies, loaded in place of LaMa.

DuckSuite ships LaMa and nothing else. This slot lets a user point the app at a
folder with ``model.onnx`` or ``model.pt`` (TorchScript) and run that instead.
Nothing is named in the UI, nothing is downloaded, and no weights enter the
repository or the bundle.

Contract, so any inpainting model can be adapted to it:

- input ``image``: float32 ``[1, 3, H, W]``, RGB in 0..1
- input ``mask``: float32 ``[1, 1, H, W]``, 1 where the pixels must be invented
- output: ``[1, 3, H, W]`` at the input size, RGB

The output is read as 0..1 when its maximum is at most 1.5, else as 0..255, so a
LaMa-style graph works without a conversion step. An ONNX model may declare a
fixed size; the feed is resized to it. Everything else about the pipeline — the
work area, the ink hole, the cache, the flicker number — stays the same.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from . import lama as lama_mod

ONNX_FILE = "model.onnx"
TORCH_FILE = "model.pt"
MODEL_FILES = (ONNX_FILE, TORCH_FILE)


def find_model(folder: Path | str) -> Path | None:
    """The model file in a user folder, or None."""
    root = Path(folder)
    for name in MODEL_FILES:
        path = root / name
        if path.is_file():
            return path
    return None


def problem(folder: Path | str) -> str | None:
    """A plain message when the folder cannot serve as a fill model, else None."""
    text = str(folder or "").strip()
    if not text:
        return "Choose a fill model folder first."
    root = Path(text)
    if not root.is_dir():
        return "That fill model folder is not there."
    path = find_model(root)
    if path is None:
        return f"That folder needs a {ONNX_FILE} or {TORCH_FILE} file."
    try:
        size = path.stat().st_size
    except OSError:
        return "The fill model file cannot be read."
    if size <= 1024:
        return "The fill model file is empty or truncated."
    if path.name == ONNX_FILE:
        try:
            import onnxruntime  # noqa: F401
        except ImportError:
            return "ONNX fill needs the onnxruntime package on this Mac."
    return None


def open_filler(folder: Path | str):
    """Load the user's model. Raises ``ValueError`` with a plain message."""
    message = problem(folder)
    if message:
        raise ValueError(message)
    path = find_model(folder)
    assert path is not None
    if path.name == TORCH_FILE:
        return CustomTorchFiller(path)
    return CustomOnnxFiller(path)


def _scale(result: np.ndarray) -> np.ndarray:
    """An engine's RGB frame as uint8, reading 0..1 and 0..255 output both."""
    values = np.asarray(result, dtype=np.float32)
    if values.size and float(values.max()) <= 1.5:
        values = values * 255.0
    return np.clip(values, 0, 255).astype(np.uint8)


class _Base:
    """Shared fill: prepare the strip, run the engine, restore the size."""

    flexible = True
    label = "your fill model"

    def run(self, image: np.ndarray, mask: np.ndarray) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError

    def fill(self, area: np.ndarray, mask: np.ndarray) -> np.ndarray:
        height, width = mask.shape
        image, small, fit_h, fit_w = lama_mod.prepare_feed(area, mask, self.flexible)
        result = _scale(self.run(image, small))
        if result.shape[:2] != image.shape[:2]:
            result = np.asarray(
                Image.fromarray(result).resize(
                    (image.shape[1], image.shape[0]), Image.BICUBIC,
                ),
                dtype=np.uint8,
            )
        return lama_mod.restore(result, fit_h, fit_w, height, width)


class CustomOnnxFiller(_Base):
    """A user ONNX graph with the image/mask contract."""

    def __init__(self, path: Path):
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.log_severity_level = 3
        self.session = ort.InferenceSession(
            str(path), sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self.provider = self.session.get_providers()[0]
        self.image_name, self.mask_name = self._names()
        self.fixed = self._fixed_size()

    def _names(self) -> tuple[str, str]:
        inputs = list(self.session.get_inputs())
        image = mask = None
        for item in inputs:
            shape = list(item.shape or [])
            channels = shape[1] if len(shape) == 4 and isinstance(shape[1], int) else None
            name = str(item.name).lower()
            if "mask" in name or channels == 1:
                mask = mask or item.name
            elif "image" in name or channels == 3:
                image = image or item.name
        if image is None or mask is None:
            if len(inputs) >= 2:
                image, mask = inputs[0].name, inputs[1].name
            else:
                raise ValueError(
                    "The fill model needs an image input and a mask input."
                )
        return str(image), str(mask)

    def _fixed_size(self) -> tuple[int, int] | None:
        for item in self.session.get_inputs():
            shape = list(item.shape or [])
            if len(shape) == 4 and all(isinstance(v, int) and v > 1 for v in shape[2:]):
                return int(shape[2]), int(shape[3])
        return None

    def run(self, image: np.ndarray, mask: np.ndarray) -> np.ndarray:
        if self.fixed is not None:
            run_h, run_w = self.fixed
        else:
            run_h, run_w = image.shape[:2]
        if (run_h, run_w) != image.shape[:2]:
            image = np.asarray(
                Image.fromarray(image).resize((run_w, run_h), Image.BICUBIC),
                dtype=np.uint8,
            )
            mask = np.asarray(
                Image.fromarray(mask.astype(np.uint8) * 255)
                .resize((run_w, run_h), Image.BILINEAR),
            ) > 0
        feed = {
            self.image_name: (image.astype(np.float32) / 255.0).transpose(2, 0, 1)[None],
            self.mask_name: mask.astype(np.float32)[None, None],
        }
        return self.session.run(None, feed)[0][0].transpose(1, 2, 0)


class CustomTorchFiller(_Base):
    """A user TorchScript module called as ``model(image, mask)``."""

    def __init__(self, path: Path):
        import torch

        self.torch = torch
        self.device = "cpu"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            self.device = "mps"
        self.module = torch.jit.load(str(path), map_location=self.device)
        self.module.eval()
        self.provider = "MPS" if self.device == "mps" else "CPU"
        self.flexible = True

    def run(self, image: np.ndarray, mask: np.ndarray) -> np.ndarray:
        torch = self.torch
        with torch.no_grad():
            picture = torch.from_numpy(
                (image.astype(np.float32) / 255.0).transpose(2, 0, 1)[None].copy(),
            ).to(self.device)
            hole = torch.from_numpy(
                mask.astype(np.float32)[None, None].copy(),
            ).to(self.device)
            result = self.module(picture, hole)
            if isinstance(result, (list, tuple)):
                result = result[0]
            return result[0].detach().float().cpu().numpy().transpose(1, 2, 0)
