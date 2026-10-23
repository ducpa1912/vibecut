#!/usr/bin/env python3
"""Stable Audio music worker.

Downloads weights on first run (~2 GB for Small, ~6 GB for 1.0), then writes a
48 kHz stereo wav. Voice-free by design: the prompt always asks for an
instrumental bed.
"""

from __future__ import annotations

import argparse
import sys

MODELS = {
    "stable-small": "stabilityai/stable-audio-open-small",
    "stable-1.0": "stabilityai/stable-audio-open-1.0",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, choices=sorted(MODELS))
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--out", required=True)
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--seed", type=int, default=-1)
    args = parser.parse_args()

    try:
        import torch
        import torchaudio
        from stable_audio_tools import get_pretrained_model
        from stable_audio_tools.inference.generation import generate_diffusion_cond
    except Exception as exc:  # noqa: BLE001
        print(f"stable-audio-tools not usable: {exc}", file=sys.stderr)
        return 2

    repo = MODELS[args.model]
    device = "mps" if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available() else "cpu"
    try:
        model, config = get_pretrained_model(repo)
        model = model.to(device).eval()
        sample_rate = int(config["sample_rate"])
        seconds = max(4.0, min(47.0, float(args.seconds)))
        if args.seed >= 0:
            torch.manual_seed(args.seed)
        conditioning = [{
            "prompt": args.prompt,
            "seconds_start": 0,
            "seconds_total": seconds,
        }]
        audio = generate_diffusion_cond(
            model,
            steps=args.steps,
            cfg_scale=7.0,
            conditioning=conditioning,
            sample_size=int(sample_rate * seconds),
            device=device,
        )
        audio = audio.detach().to("cpu").float()
        if audio.dim() == 3:
            audio = audio[0]
        if audio.shape[0] == 1:
            audio = audio.repeat(2, 1)
        torchaudio.save(args.out, audio.clamp(-1.0, 1.0), sample_rate)
    except Exception as exc:  # noqa: BLE001
        print(f"music generation failed: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
