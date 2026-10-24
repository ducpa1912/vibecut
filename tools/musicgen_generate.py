#!/usr/bin/env python3
"""Ungated local music fallback: facebook/musicgen-small via transformers."""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="facebook/musicgen-small")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--seconds", type=float, default=8.0)
    parser.add_argument("--out", required=True)
    parser.add_argument("--steps", type=int, default=0, help="ignored; MusicGen uses tokens")
    args = parser.parse_args()

    try:
        import numpy as np
        import soundfile as sf
        import torch
        from transformers import AutoProcessor, MusicgenForConditionalGeneration
    except Exception as exc:  # noqa: BLE001
        print(f"MusicGen dependencies unavailable: {exc}", file=sys.stderr)
        return 2

    device = "mps" if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available() else "cpu"
    try:
        processor = AutoProcessor.from_pretrained(args.model)
        model = MusicgenForConditionalGeneration.from_pretrained(args.model).to(device).eval()
        inputs = processor(text=[args.prompt], padding=True, return_tensors="pt")
        inputs = {key: value.to(device) for key, value in inputs.items()}
        # Keep the untuned fallback bounded: the renderer loops the bed.
        seconds = max(4.0, min(8.0, float(args.seconds)))
        with torch.inference_mode():
            audio = model.generate(
                **inputs,
                max_new_tokens=int(seconds * 50),
                do_sample=True,
                guidance_scale=3.0,
            )
        values = audio[0].detach().cpu().float().numpy()
        if values.ndim == 2 and values.shape[0] == 1:
            values = np.repeat(values, 2, axis=0)
        if values.ndim == 2:
            values = values.T
        sf.write(args.out, values, int(model.config.audio_encoder.sampling_rate))
    except Exception as exc:  # noqa: BLE001
        print(f"MusicGen generation failed: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
