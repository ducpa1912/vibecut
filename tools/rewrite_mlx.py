#!/usr/bin/env python3
"""Local small-model rewrite worker (MLX, Apple silicon).

Reads a JSON payload on stdin: {prompt, system, max_tokens}
Writes the model text on stdout. Falls back with exit 3 when mlx-lm is missing.
"""

from __future__ import annotations

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="mlx-community/Qwen2.5-3B-Instruct-4bit")
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--temp", type=float, default=0.6)
    args = parser.parse_args()

    try:
        from mlx_lm import generate, load  # noqa: PLC0415
        from mlx_lm.sample_utils import make_sampler  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        print(f"mlx_lm not usable: {exc}", file=sys.stderr)
        return 3

    payload = json.loads(sys.stdin.read() or "{}")
    system = str(payload.get("system") or "You write short video voice overs.")
    prompt = str(payload.get("prompt") or "")
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    try:
        model, tokenizer = load(args.model)
        text = tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, tokenize=False,
        )
        sampler = make_sampler(temp=args.temp)
        out = generate(
            model, tokenizer, prompt=text,
            max_tokens=args.max_tokens, sampler=sampler, verbose=False,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"mlx generation failed: {exc}", file=sys.stderr)
        return 4
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
