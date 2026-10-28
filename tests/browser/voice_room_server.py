"""Start VibeCut for the Voice Room browser spec, with the slow parts faked.

The clean-clip search and the upload cleaning would run separation and
denoise models; here they write short tone WAVs instead, so the spec drives
the real page and the real routes in seconds. Cloning is marked available
without an OpenRouter key; nothing in the spec speaks a cloned voice, so no
request leaves this machine.

    python tests/browser/voice_room_server.py PORT

``VR_FAKE_SEARCH_SECONDS`` makes the search wait (checking its cancel switch)
before it returns, so the spec can press Cancel while it runs.
"""

from __future__ import annotations

import math
import os
import shutil
import struct
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import uvicorn  # noqa: E402

import audio  # noqa: E402
import voice_clone  # noqa: E402
import voice_extract  # noqa: E402


def tone(path: Path, seconds: float, freq: float = 220.0) -> Path:
    rate = 16000
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frames = b"".join(
            struct.pack("<h", int(8000 * math.sin(2 * math.pi * freq * n / rate)))
            for n in range(int(seconds * rate))
        )
        handle.writeframes(frames)
    return path


def fake_find(source, out_dir, cancel_event=None, on_stage=None, **_kwargs):
    wait = float(os.environ.get("VR_FAKE_SEARCH_SECONDS") or 0)
    if on_stage:
        on_stage("scoring")
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if cancel_event is not None and cancel_event.is_set():
            raise audio.AudioError("Voice extraction cancelled.")
        time.sleep(0.05)
    if on_stage:
        on_stage("exporting")
    out = Path(out_dir)
    candidates = []
    for index, (start, freq) in enumerate(((12.0, 220.0), (48.0, 260.0), (90.0, 300.0)), start=1):
        path = tone(out / f"candidate-{index:02d}.wav", 10.0, freq)
        candidates.append({
            "index": index,
            "path": str(path),
            "duration": 10.0,
            "speech_fraction": 0.9 - index * 0.05,
            "score": 120.0 - index,
            "window": [start, start + 10.0],
            "quality": {"snr_db": 22.0 - index, "music_noise_residual_db": -32.0},
            "warnings": ["Candidates may include more than one speaker."] if index == 3 else [],
        })
    return {
        "version": 2,
        "candidates": candidates,
        "models": {"separation": "fake", "denoise": "fake", "vad": "fake"},
        "warnings": [],
    }


def fake_clean(source, out_dir, **_kwargs):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    target = out / "clean.wav"
    shutil.copyfile(source, target)
    return {"path": str(target), "quality": {}, "warnings": []}


def install_fakes() -> None:
    voice_extract.find_voice_candidates = fake_find
    voice_extract.extract_clean_voice = fake_clean
    voice_clone.available = lambda: True


if __name__ == "__main__":
    install_fakes()
    port = int(sys.argv[1])
    uvicorn.run("app:app", host="127.0.0.1", port=port, log_level="warning")
