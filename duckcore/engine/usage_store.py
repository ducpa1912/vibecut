"""Process-wide usage ledger for cloud LLM, STT and TTS calls."""

from __future__ import annotations

import threading
import time

LOCK = threading.Lock()
TOTALS = {
    "calls": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "chars": 0,
    "audio_seconds": 0.0,
    "cost_usd": 0.0,
}
EVENTS: list[dict] = []

LLM_INPUT_PER_M = 0.15
LLM_OUTPUT_PER_M = 0.60
STT_PER_HOUR = {"groq": 0.04, "openai": 0.36, "deepgram": 0.258}
MUSIC_PER_CALL = {"minimax": 0.15, "lyria-clip": 0.04, "lyria-pro": 0.08}
TTS_PER_CHAR = {
    "openai": 15e-6,
    "groq": 22e-6,
    "deepgram": 30e-6,
    "elevenlabs": 40e-6,
    "cartesia": 49e-6,
    "minimax": 60e-6,
    "heygen": 0.0,
    "fish": 0.0,
    "gemini": 10e-6,
}


def record(
    kind: str,
    provider: str,
    *,
    model: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    chars: int = 0,
    audio_seconds: float = 0.0,
    calls: int = 1,
) -> dict:
    if kind == "llm":
        cost = (
            max(0, int(input_tokens)) * LLM_INPUT_PER_M / 1_000_000
            + max(0, int(output_tokens)) * LLM_OUTPUT_PER_M / 1_000_000
        )
    elif kind == "stt":
        cost = max(0.0, float(audio_seconds)) * STT_PER_HOUR.get(provider, 0.0) / 3600
    elif kind == "tts":
        cost = max(0, int(chars)) * TTS_PER_CHAR.get(provider, 0.0)
    elif kind == "music":
        cost = MUSIC_PER_CALL.get(provider, 0.0)
    else:
        cost = 0.0
    event = {
        "kind": kind,
        "provider": provider,
        "model": model,
        "calls": max(0, int(calls)),
        "input_tokens": max(0, int(input_tokens)),
        "output_tokens": max(0, int(output_tokens)),
        "chars": max(0, int(chars)),
        "audio_seconds": round(max(0.0, float(audio_seconds)), 3),
        "cost_usd": round(cost, 6),
        "at": round(time.time(), 3),
    }
    with LOCK:
        for key in ("calls", "input_tokens", "output_tokens", "chars"):
            TOTALS[key] += event[key]
        TOTALS["audio_seconds"] += event["audio_seconds"]
        TOTALS["cost_usd"] += event["cost_usd"]
        EVENTS.append(event)
        del EVENTS[:-200]
    return event


def snapshot() -> dict:
    with LOCK:
        return {
            "calls": TOTALS["calls"],
            "input_tokens": TOTALS["input_tokens"],
            "output_tokens": TOTALS["output_tokens"],
            "chars": TOTALS["chars"],
            "audio_seconds": round(TOTALS["audio_seconds"], 3),
            "cost_usd": round(TOTALS["cost_usd"], 6),
        }


def delta(before: dict) -> dict:
    after = snapshot()
    return {
        key: round(max(0.0, after.get(key, 0.0) - before.get(key, 0.0)), 6)
        for key in ("calls", "input_tokens", "output_tokens", "chars", "audio_seconds", "cost_usd")
    }
