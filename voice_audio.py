"""Listening to audio without changing it.

Three jobs, all local and all read-only:

* :func:`analyse` measures a file and returns plain flags: silent, too quiet,
  too loud, clipping. Voice Room shows them as advice; it never edits the
  audio because of them.
* :func:`best_window` picks a clean 10-15 s stretch of a long recording, so a
  clone reference is short and speech-only.
* :func:`cut` writes one range of a file as mono 44.1 kHz WAV, for a trimmer
  preview or a clone sample.

Nothing here calls a network service. ffmpeg decodes; numpy measures.
"""

from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Sequence

#: Everyday speech sits around -20 dBFS. These are deliberately generous: the
#: check is advice, not a gate.
SILENT_PEAK_DBFS = -50.0
QUIET_RMS_DBFS = -30.0
LOUD_RMS_DBFS = -12.0
SPEECH_FRAME_DBFS = -42.0
CLIP_RATIO = 0.001
FRAME_SECONDS = 0.02
#: A clone reference that is shorter than this cannot teach a voice much.
MIN_REFERENCE_SECONDS = 8.0
#: The spec's guard: anything longer opens the trimmer.
MAX_REFERENCE_SECONDS = 15.0
#: The window the trimmer starts on.
TARGET_WINDOW_SECONDS = 12.0

CHECK_NOTES = {
    "silent": "No speech could be heard. Record closer to the microphone and check the input level moves.",
    "too_quiet": "The recording is quiet. Move closer or raise the input level, then record again.",
    "too_loud": "The recording is loud enough to distort. Move back a little or lower the input level.",
    "clipping": "The recording clips at the loudest words. Lower the input level and record again.",
    "clean": "The levels look usable.",
}


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError(
            "ffmpeg is not installed, so the audio cannot be read. Install it with `brew install ffmpeg`."
        )
    return path


def _decode(source: Path, output: Path, *, start: float = 0.0, end: float | None = None) -> Path:
    """Decode a range as mono 16-bit 16 kHz PCM, the cheapest shape to read."""
    cmd = [_ffmpeg(), "-y", "-v", "error"]
    if start > 0:
        cmd += ["-ss", f"{max(0.0, float(start)):.3f}"]
    if end is not None and end > start:
        cmd += ["-t", f"{max(0.05, float(end) - float(start)):.3f}"]
    cmd += ["-i", str(source), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(output)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(
            f"Could not read that audio. Check the file plays, then try again ({exc})."
        ) from exc
    if result.returncode != 0 or not output.is_file():
        tail = (result.stderr or result.stdout or "").strip().splitlines()
        detail = tail[-1][:160] if tail else "ffmpeg could not decode it"
        raise RuntimeError(
            f"Could not read that audio: {detail}. Use a WAV, MP3, M4A, OGG or WebM file."
        )
    return output


def to_wav(source: Path, output: Path) -> Path:
    """Decode any supported file to mono 16 kHz PCM WAV for reading or serving."""
    return _decode(Path(source), Path(output))


def _frames(path: Path, frame_seconds: float = FRAME_SECONDS):
    """Yield ``(block_start_seconds, float array block)`` from mono PCM WAV."""
    import numpy as np  # noqa: PLC0415 - numpy is only needed for measurement

    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        channels = max(1, handle.getnchannels())
        width = handle.getsampwidth()
        if width != 2:
            raise RuntimeError("The audio reader expected 16-bit PCM.")
        frame = max(1, int(rate * frame_seconds))
        blocks_per_read = 200
        offset = 0
        while True:
            raw = handle.readframes(frame * blocks_per_read)
            if not raw:
                break
            values = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            if channels > 1:
                values = values.reshape(-1, channels).mean(axis=1)
            usable = (len(values) // frame) * frame
            if usable < frame:
                break
            for index in range(usable // frame):
                chunk = values[index * frame:(index + 1) * frame]
                yield offset / rate, chunk
                offset += frame


def _db(value: float) -> float:
    return 20.0 * math.log10(max(float(value), 1e-9))


def analyse(path: Path) -> dict:
    """Measure one file and return advice flags. Never raises for silence."""
    import numpy as np  # noqa: PLC0415

    source = Path(path)
    if not source.is_file():
        raise RuntimeError("That audio file is missing. Choose it again.")
    with tempfile.TemporaryDirectory(prefix="vibecut-voice-check-") as work:
        wav = _decode(source, Path(work) / "check.wav")
        levels: list[float] = []
        peak = 0.0
        clipped = 0
        samples = 0
        for _offset, block in _frames(wav):
            absolute = np.abs(block)
            peak = max(peak, float(absolute.max()) if absolute.size else 0.0)
            clipped += int(np.count_nonzero(absolute >= 0.999))
            samples += int(absolute.size)
            levels.append(_db(float(np.sqrt(np.mean(np.square(block))))) if block.size else -120.0)
        duration = samples / 16000.0
    if not levels or duration <= 0.02:
        return {
            "available": True,
            "duration": 0.0,
            "peak_dbfs": -120.0,
            "rms_dbfs": -120.0,
            "speech_fraction": 0.0,
            "clip_ratio": 0.0,
            "silent": True,
            "too_quiet": False,
            "too_loud": False,
            "clipping": False,
            "notes": [CHECK_NOTES["silent"]],
        }
    speech = [value for value in levels if value >= SPEECH_FRAME_DBFS]
    speech_fraction = len(speech) / len(levels)
    rms = 10.0 * math.log10(max(1e-12, sum(10.0 ** (value / 10.0) for value in levels) / len(levels)))
    peak_dbfs = _db(peak)
    clip_ratio = clipped / max(1, samples)
    silent = peak_dbfs <= SILENT_PEAK_DBFS or speech_fraction < 0.02
    too_quiet = not silent and rms <= QUIET_RMS_DBFS
    too_loud = rms >= LOUD_RMS_DBFS
    clipping = clip_ratio >= CLIP_RATIO
    notes: list[str] = []
    if silent:
        notes.append(CHECK_NOTES["silent"])
    else:
        if too_quiet:
            notes.append(CHECK_NOTES["too_quiet"])
        if too_loud:
            notes.append(CHECK_NOTES["too_loud"])
        if clipping:
            notes.append(CHECK_NOTES["clipping"])
    if not notes:
        notes.append(CHECK_NOTES["clean"])
    return {
        "available": True,
        "duration": round(duration, 3),
        "peak_dbfs": round(peak_dbfs, 2),
        "rms_dbfs": round(rms, 2),
        "speech_fraction": round(speech_fraction, 3),
        "clip_ratio": round(clip_ratio, 6),
        "silent": bool(silent),
        "too_quiet": bool(too_quiet),
        "too_loud": bool(too_loud),
        "clipping": bool(clipping),
        "notes": notes,
    }


def peaks(path: Path, count: int = 240) -> list[float]:
    """A small waveform: the loudest sample in each of ``count`` buckets, 0-1."""
    import numpy as np  # noqa: PLC0415

    count = max(24, min(600, int(count or 240)))
    values: list[float] = []
    for _offset, block in _frames(Path(path), frame_seconds=0.05):
        values.append(float(np.max(np.abs(block))) if block.size else 0.0)
    if not values:
        return [0.0] * count
    buckets: list[float] = []
    step = len(values) / count
    for index in range(count):
        left = int(index * step)
        right = max(left + 1, int((index + 1) * step))
        chunk = values[left:right]
        buckets.append(round(min(1.0, max(chunk) if chunk else 0.0), 3))
    return buckets


def _speech_mask(levels: Sequence[float]) -> tuple[list[bool], float]:
    import numpy as np  # noqa: PLC0415

    values = np.asarray(list(levels), dtype=np.float64)
    if not values.size:
        return [], -120.0
    floor = float(np.percentile(values, 10))
    threshold = max(SPEECH_FRAME_DBFS, floor + 8.0)
    return [bool(value >= threshold) for value in values], floor


def best_window(
    path: Path,
    *,
    min_seconds: float = 10.0,
    max_seconds: float = MAX_REFERENCE_SECONDS,
    target_seconds: float = TARGET_WINDOW_SECONDS,
) -> dict:
    """The cleanest speech window, never longer than ``max_seconds``.

    A short clip is returned whole. A long clip is scanned in half-second
    steps; the winner has the most speech, then the earliest start, so the
    result is repeatable. The window is padded slightly and kept inside the
    file.
    """
    source = Path(path)
    with tempfile.TemporaryDirectory(prefix="vibecut-voice-window-") as work:
        wav = _decode(source, Path(work) / "window.wav")
        levels: list[float] = []
        for _offset, block in _frames(wav):
            import numpy as np  # noqa: PLC0415

            levels.append(
                _db(float(np.sqrt(np.mean(np.square(block))))) if block.size else -120.0
            )
    duration = len(levels) * FRAME_SECONDS
    if duration <= max_seconds:
        start, end = 0.0, round(duration, 3)
    else:
        speech, _floor = _speech_mask(levels)
        length = min(max_seconds, max(min_seconds, target_seconds))
        step_frames = max(1, int(round(0.5 / FRAME_SECONDS)))
        window_frames = max(1, int(round(length / FRAME_SECONDS)))
        best = (0.0, 0.0, -1.0)
        for first in range(0, max(1, len(speech) - window_frames + 1), step_frames):
            block = speech[first:first + window_frames]
            if not block:
                break
            fraction = sum(1 for flag in block if flag) / len(block)
            if fraction > best[0] + 1e-9:
                start = first * FRAME_SECONDS
                best = (fraction, start, float(window_frames))
        start = float(best[1])
        # A little air before the first word and after the last, without
        # going outside the file or over the limit.
        if speech:
            first_word = int(start / FRAME_SECONDS)
            last = min(len(speech), first_word + int(best[2]))
            block = speech[first_word:last]
            if any(block):
                lead = next(index for index, flag in enumerate(block) if flag)
                trail = len(block) - next(
                    index for index, flag in enumerate(reversed(block)) if flag
                )
                start = max(0.0, start + lead * FRAME_SECONDS - 0.15)
                end = min(duration, start + max(min_seconds, length - lead * FRAME_SECONDS + trail * FRAME_SECONDS + 0.15))
            else:
                end = min(duration, start + length)
        else:
            end = min(duration, start + length)
        if end - start > max_seconds:
            end = start + max_seconds
        if end - start < min_seconds:
            start = max(0.0, min(start, duration - min(min_seconds, duration)))
            end = min(duration, start + min_seconds)
    return {
        "start": round(max(0.0, start), 3),
        "end": round(min(duration, max(end, start + 0.1)), 3),
        "duration": round(duration, 3),
        "ok": (end - start) >= min_seconds,
        "too_short": (end - start) < min_seconds,
        "too_long": (end - start) > max_seconds,
    }


def cut(source: Path, output: Path, start: float, end: float) -> Path:
    """Write one range as mono 44.1 kHz WAV. Used by the trimmer and clones."""
    if end <= start:
        raise RuntimeError("The end of the selection must come after its start.")
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        _ffmpeg(), "-y", "-v", "error",
        "-ss", f"{max(0.0, float(start)):.3f}",
        "-t", f"{max(0.05, float(end) - float(start)):.3f}",
        "-i", str(source), "-vn", "-ac", "1", "-ar", "44100",
        "-c:a", "pcm_s16le", str(output),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"Could not cut that part of the audio ({exc}).") from exc
    if result.returncode != 0 or not output.is_file() or output.stat().st_size < 1024:
        raise RuntimeError(
            "Could not cut that part of the audio. Check the file plays, then try again."
        )
    return output
