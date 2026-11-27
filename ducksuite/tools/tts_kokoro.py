#!/usr/bin/env python3
"""Kokoro ONNX TTS worker: reads text from stdin, writes a wav file."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--voices", required=True)
    parser.add_argument("--voice", default="af_heart")
    parser.add_argument("--out", required=True)
    parser.add_argument("--speed", type=float, default=1.0)
    args = parser.parse_args()

    text = sys.stdin.read().strip()
    if not text:
        print("no text on stdin", file=sys.stderr)
        return 2

    from kokoro_onnx import Kokoro  # noqa: PLC0415

    engine = None
    try:
        engine = Kokoro(args.model, args.voices)
    except Exception:  # noqa: BLE001
        try:
            from kokoro_onnx import EspeakConfig  # noqa: PLC0415

            candidates = [
                ("/opt/homebrew/lib/libespeak-ng.dylib", "/opt/homebrew/share/espeak-ng-data"),
                ("/usr/lib/libespeak-ng.so", "/usr/share/espeak-ng-data"),
                ("/usr/lib/x86_64-linux-gnu/libespeak-ng.so", "/usr/lib/espeak-ng-data"),
            ]
            for lib, data in candidates:
                if Path(lib).is_file() and Path(data).is_dir():
                    engine = Kokoro(args.model, args.voices, espeak_config=EspeakConfig(
                        lib_path=lib, data_path=data,
                    ))
                    break
        except Exception as exc:  # noqa: BLE001
            print(f"kokoro init failed: {exc}", file=sys.stderr)
            return 3
    if engine is None:
        print("kokoro init failed: no usable espeak-ng data", file=sys.stderr)
        return 3

    language = "en-us"
    prefix = (args.voice or "")[:1]
    if prefix in {"e", "f", "h", "i", "j", "p", "z"}:
        language = {
            "e": "es", "f": "fr-fr", "h": "hi", "i": "it", "j": "ja",
            "p": "pt-br", "z": "cmn",
        }.get(prefix, "en-us")
    try:
        samples, sample_rate = engine.create(
            text, voice=args.voice, speed=args.speed, lang=language,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"kokoro synth failed: {exc}", file=sys.stderr)
        return 4

    import soundfile as sf  # noqa: PLC0415

    sf.write(args.out, samples, sample_rate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
