"""STTN subtitle fill (inference only).

The network is the generator from STTN, "Learning Joint Spatial-Temporal
Transformations for Video Inpainting" (Zeng, Fu, Chao; ECCV 2020),
github.com/researchmm/STTN, MIT License, Copyright (c) 2016 Michael Rose
(as stated in that repository's LICENSE). The subtitle-tuned weights and the
640x120 strip, neighbour stride 5 and reference length 10 follow
YaoFANGUK/video-subtitle-remover (``backend/inpaint/sttn/auto_sttn.py`` and
``sttn_auto_inpaint.py``), Apache License 2.0. Changes here: training code,
the discriminator and OpenCV were dropped; chunks overlap and cross-fade.

The subtitle model needs no mask on input: it learned to remove text from a
strip. The mask only decides which pixels are pasted back.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
from PIL import Image

MODEL_FILE = "sttn_infer_model.pth"
WIDTH, HEIGHT = 640, 120
NEIGHBOR_STRIDE = 5
REFERENCE_LENGTH = 10
CHUNK = 50
OVERLAP = 10


def chunk_spans(frames: int, chunk: int = CHUNK, overlap: int = OVERLAP) -> list[tuple[int, int]]:
    """Frame ranges [start, end) of at most ``chunk`` frames, overlapping."""
    if frames <= 0:
        return []
    if frames <= chunk:
        return [(0, frames)]
    step = chunk - overlap
    spans = []
    start = 0
    while True:
        end = min(frames, start + chunk)
        spans.append((max(0, end - chunk), end))
        if end >= frames:
            break
        start += step
    return spans


def reference_ids(neighbor_ids: list[int], length: int, every: int = REFERENCE_LENGTH) -> list[int]:
    return [index for index in range(0, length, every) if index not in neighbor_ids]


def _build_network():
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    class Deconv(nn.Module):
        def __init__(self, cin, cout, kernel_size=3, padding=0):
            super().__init__()
            self.conv = nn.Conv2d(cin, cout, kernel_size=kernel_size, stride=1, padding=padding)

        def forward(self, x):
            x = F.interpolate(x, scale_factor=2, mode="bilinear", align_corners=True)
            return self.conv(x)

    class MultiHeadedAttention(nn.Module):
        def __init__(self, patchsize, d_model):
            super().__init__()
            self.patchsize = patchsize
            self.query_embedding = nn.Conv2d(d_model, d_model, kernel_size=1, padding=0)
            self.value_embedding = nn.Conv2d(d_model, d_model, kernel_size=1, padding=0)
            self.key_embedding = nn.Conv2d(d_model, d_model, kernel_size=1, padding=0)
            self.output_linear = nn.Sequential(
                nn.Conv2d(d_model, d_model, kernel_size=3, padding=1),
                nn.LeakyReLU(0.2, inplace=True),
            )

        def forward(self, x, b, c):
            bt, _, h, w = x.size()
            t = bt // b
            d_k = c // len(self.patchsize)
            output = []
            parts = zip(
                self.patchsize,
                torch.chunk(self.query_embedding(x), len(self.patchsize), dim=1),
                torch.chunk(self.key_embedding(x), len(self.patchsize), dim=1),
                torch.chunk(self.value_embedding(x), len(self.patchsize), dim=1),
            )
            for (width, height), query, key, value in parts:
                out_w, out_h = w // width, h // height

                def tokens(tensor):
                    tensor = tensor.view(b, t, d_k, out_h, height, out_w, width)
                    return tensor.permute(0, 1, 3, 5, 2, 4, 6).contiguous().view(
                        b, t * out_h * out_w, d_k * height * width,
                    )

                query, key, value = tokens(query), tokens(key), tokens(value)
                scores = torch.matmul(query, key.transpose(-2, -1)) / math.sqrt(query.size(-1))
                y = torch.matmul(F.softmax(scores, dim=-1), value)
                y = y.view(b, t, out_h, out_w, d_k, height, width)
                y = y.permute(0, 1, 4, 2, 5, 3, 6).contiguous().view(bt, d_k, h, w)
                output.append(y)
            return self.output_linear(torch.cat(output, 1))

    class FeedForward(nn.Module):
        def __init__(self, d_model):
            super().__init__()
            self.conv = nn.Sequential(
                nn.Conv2d(d_model, d_model, kernel_size=3, padding=2, dilation=2),
                nn.LeakyReLU(0.2, inplace=True),
                nn.Conv2d(d_model, d_model, kernel_size=3, padding=1),
                nn.LeakyReLU(0.2, inplace=True),
            )

        def forward(self, x):
            return self.conv(x)

    class TransformerBlock(nn.Module):
        def __init__(self, patchsize, hidden=128):
            super().__init__()
            self.attention = MultiHeadedAttention(patchsize, d_model=hidden)
            self.feed_forward = FeedForward(hidden)

        def forward(self, x):
            x, b, c = x["x"], x["b"], x["c"]
            x = x + self.attention(x, b, c)
            x = x + self.feed_forward(x)
            return {"x": x, "b": b, "c": c}

    class InpaintGenerator(nn.Module):
        def __init__(self):
            super().__init__()
            channel = 256
            patchsize = [(80, 15), (32, 6), (10, 5), (5, 3)]
            self.transformer = nn.Sequential(
                *[TransformerBlock(patchsize, hidden=channel) for _ in range(8)]
            )
            self.encoder = nn.Sequential(
                nn.Conv2d(3, 64, kernel_size=3, stride=2, padding=1),
                nn.LeakyReLU(0.2, inplace=True),
                nn.Conv2d(64, 64, kernel_size=3, stride=1, padding=1),
                nn.LeakyReLU(0.2, inplace=True),
                nn.Conv2d(64, 128, kernel_size=3, stride=2, padding=1),
                nn.LeakyReLU(0.2, inplace=True),
                nn.Conv2d(128, channel, kernel_size=3, stride=1, padding=1),
                nn.LeakyReLU(0.2, inplace=True),
            )
            self.decoder = nn.Sequential(
                Deconv(channel, 128, kernel_size=3, padding=1),
                nn.LeakyReLU(0.2, inplace=True),
                nn.Conv2d(128, 64, kernel_size=3, stride=1, padding=1),
                nn.LeakyReLU(0.2, inplace=True),
                Deconv(64, 64, kernel_size=3, padding=1),
                nn.LeakyReLU(0.2, inplace=True),
                nn.Conv2d(64, 3, kernel_size=3, stride=1, padding=1),
            )

        def infer(self, feat):
            _, c, _, _ = feat.size()
            return self.transformer({"x": feat, "b": 1, "c": c})["x"]

    return InpaintGenerator()


def _device(torch) -> str:
    choice = (os.environ.get("VIBECUT_FILL_DEVICE") or "auto").strip().lower()
    if choice in ("cpu", "mps"):
        return choice
    return "mps" if torch.backends.mps.is_available() else "cpu"


class SttnFiller:
    def __init__(self, model_path: Path):
        import torch

        self.torch = torch
        state = torch.load(str(model_path), map_location="cpu", weights_only=True)
        if isinstance(state, dict) and "netG" in state:
            state = state["netG"]
        self.model = _build_network()
        self.model.load_state_dict(state)
        self.model.eval()
        self.device = _device(torch)
        self.model.to(self.device)

    def _strips(self, strips: list[np.ndarray]) -> list[np.ndarray]:
        torch = self.torch
        length = len(strips)
        scaled = np.stack([
            np.asarray(Image.fromarray(strip).resize((WIDTH, HEIGHT), Image.BICUBIC), dtype=np.uint8)
            for strip in strips
        ])
        feats = torch.from_numpy(scaled).permute(0, 3, 1, 2).float().div(255.0).mul(2).sub(1)
        feats = feats.to(self.device)
        comps: list[np.ndarray | None] = [None] * length
        with torch.no_grad():
            feats = self.model.encoder(feats)
            for f in range(0, length, NEIGHBOR_STRIDE):
                neighbor_ids = list(range(max(0, f - NEIGHBOR_STRIDE), min(length, f + NEIGHBOR_STRIDE + 1)))
                ref_ids = reference_ids(neighbor_ids, length)
                pred = self.model.infer(feats[neighbor_ids + ref_ids])
                pred = torch.tanh(self.model.decoder(pred[:len(neighbor_ids)]))
                pred = ((pred + 1) / 2).clamp(0, 1).mul(255).permute(0, 2, 3, 1).cpu().numpy()
                for i, idx in enumerate(neighbor_ids):
                    if comps[idx] is None:
                        comps[idx] = pred[i]
                    else:
                        comps[idx] = comps[idx] * 0.5 + pred[i] * 0.5
        height, width = strips[0].shape[:2]
        return [
            np.asarray(
                Image.fromarray(np.clip(comp, 0, 255).astype(np.uint8)).resize((width, height), Image.BICUBIC),
                dtype=np.uint8,
            )
            for comp in comps
        ]

    def fill(self, strips: list[np.ndarray]) -> list[np.ndarray]:
        """Remove text from a run of same-size RGB strips (one per frame)."""
        try:
            return self._strips(strips)
        except RuntimeError:
            if self.device == "cpu":
                raise
            # An MPS kernel or memory failure: finish on the CPU.
            self.device = "cpu"
            self.model.to("cpu")
            return self._strips(strips)
