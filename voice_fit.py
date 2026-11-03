"""Pitch-preserving voice fitting for VibeCut.

One shared stage for every TTS provider and every lane:

* ``preserve_pitch=True``  -> time-stretch only; pitch and tone stay put.
* ``preserve_pitch=False`` -> intentional pitch rise ("chipmunk"), capped.

The default backend is FFmpeg ``atempo`` (WSOLA-family).  Signalsmith Stretch
is used when available through the MIT ``python-stretch`` binding, with a
transparent FFmpeg fallback.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

PRESERVE_MAX_SPEED = 1.25
CHIPMUNK_MAX_SPEED = 1.80
EXTREME_MAX_SPEED = 2.50
SAMPLE_RATE = 48000
CHANNELS = 2

ENGINES = ("auto", "ffmpeg", "signalsmith")


@dataclass(frozen=True)
class FitResult:
    source: str
    output: str
    requested: float
    applied: float
    preserve_pitch: bool
    backend: str
    capped: bool
    pitch_shift: float
    warning: str

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "output": self.output,
            "requested": round(self.requested, 4),
            "applied": round(self.applied, 4),
            "preserve_pitch": self.preserve_pitch,
            "backend": self.backend,
            "capped": self.capped,
            "pitch_shift": round(self.pitch_shift, 4),
            "warning": self.warning,
        }


def _settings() -> dict:
    try:
        import settings_store  # noqa: PLC0415 - avoid an import cycle

        value = settings_store.load_settings().get("voice_fit")
        return value if isinstance(value, dict) else {}
    except Exception:  # noqa: BLE001 - fitting must still work
        return {}


def preserve_pitch_default() -> bool:
    return _settings().get("preserve_pitch", True) is not False


def max_speed_default(preserve_pitch: bool | None = None) -> float:
    settings = _settings()
    if preserve_pitch is None:
        preserve_pitch = settings.get("preserve_pitch", True) is not False
    raw = settings.get("max_speed")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = PRESERVE_MAX_SPEED if preserve_pitch else CHIPMUNK_MAX_SPEED
    if preserve_pitch:
        return max(1.0, min(PRESERVE_MAX_SPEED, value))
    ceiling = EXTREME_MAX_SPEED if settings.get("allow_extreme_speed") is True else CHIPMUNK_MAX_SPEED
    return max(1.0, min(ceiling, value))


def engine_default() -> str:
    value = str(_settings().get("engine") or "auto").strip().lower()
    return value if value in ENGINES else "auto"


def policy_fingerprint() -> str:
    """Stable cache identity for the active voice-fit policy."""
    settings = _settings()
    payload = {
        "preserve_pitch": settings.get("preserve_pitch", True) is not False,
        "max_speed": round(max_speed_default(), 3),
        "engine": engine_default(),
        "allow_extreme_speed": settings.get("allow_extreme_speed") is True,
        "signalsmith": signalsmith_available(),
        "schema": 2,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def signalsmith_available() -> bool:
    try:
        import python_stretch  # noqa: F401, PLC0415

        return True
    except Exception:  # noqa: BLE001
        return False


def _ffmpeg() -> str:
    path = os.environ.get("VIBECUT_FFMPEG") or shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg is not installed or not on PATH.")
    return path


def _run(command: list[str], *, input_bytes: bytes | None = None, timeout: float = 300) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            command,
            input=input_bytes,
            capture_output=True,
            timeout=max(10.0, float(timeout)),
        )
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg is not installed or not on PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"ffmpeg timed out after {timeout:.0f}s.") from exc
    except OSError as exc:
        raise RuntimeError(f"ffmpeg could not start: {exc}") from exc
    if result.returncode != 0:
        message = (result.stderr or result.stdout or b"").decode("utf-8", "replace").strip()
        raise RuntimeError(message[-500:] or f"ffmpeg exited {result.returncode}")
    return result


def _normalise(source: Path, output: Path, timeout: float = 300) -> None:
    _run([
        _ffmpeg(), "-y", "-v", "error", "-i", str(source),
        "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS),
        "-c:a", "pcm_s16le", str(output),
    ], timeout=timeout)


def _ffmpeg_preserve(source: Path, output: Path, rate: float, timeout: float = 300) -> None:
    filters = []
    remaining = rate
    # atempo is reliable in 0.5..2.0; chain outside that range.
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={remaining:.6f}")
    _run([
        _ffmpeg(), "-y", "-v", "error", "-i", str(source),
        "-af", ",".join(filters),
        "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS),
        "-c:a", "pcm_s16le", str(output),
    ], timeout=timeout)


def _ffmpeg_chipmunk(source: Path, output: Path, rate: float, timeout: float = 300) -> None:
    # Resampling raises pitch and speed together, intentionally.
    filters = (
        f"aresample={SAMPLE_RATE},"
        f"asetrate={SAMPLE_RATE * rate:.6f},"
        f"aresample={SAMPLE_RATE}"
    )
    _run([
        _ffmpeg(), "-y", "-v", "error", "-i", str(source),
        "-af", filters,
        "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS),
        "-c:a", "pcm_s16le", str(output),
    ], timeout=timeout)


def _signalsmith_preserve(source: Path, output: Path, rate: float, timeout: float = 300) -> None:
    import numpy as np  # noqa: PLC0415
    import python_stretch  # noqa: PLC0415

    decoded = _run([
        _ffmpeg(), "-v", "error", "-i", str(source),
        "-f", "f32le", "-acodec", "pcm_f32le",
        "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS), "pipe:1",
    ], timeout=timeout)
    samples = np.frombuffer(decoded.stdout, dtype=np.float32)
    if samples.size == 0:
        raise RuntimeError("Signalsmith: empty input audio.")
    channels = CHANNELS
    samples = samples[: samples.size - (samples.size % channels)]
    block = np.ascontiguousarray(samples.reshape(-1, channels).T)

    stretch = python_stretch.Signalsmith.Stretch()
    stretch.preset(channels, SAMPLE_RATE)
    # In python-stretch, timeFactor is the speed factor: 1.25 is 25% faster.
    stretch.timeFactor = max(0.01, float(rate))
    processed = np.asarray(stretch.process(block), dtype=np.float32)
    if processed.ndim == 1:
        processed = processed[np.newaxis, :]
    if processed.shape[0] != channels:
        processed = processed.reshape(channels, -1)
    processed = np.ascontiguousarray(processed.T).astype(np.float32, copy=False)
    payload = processed.tobytes()
    _run([
        _ffmpeg(), "-y", "-v", "error",
        "-f", "f32le", "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS), "-i", "pipe:0",
        "-c:a", "pcm_s16le", str(output),
    ], input_bytes=payload, timeout=timeout)


def fit_audio(
    source: str | Path,
    output: str | Path,
    rate: float = 1.0,
    *,
    preserve_pitch: bool | None = None,
    max_speed: float | None = None,
    engine: str | None = None,
    timeout: float = 300,
) -> FitResult:
    """Fit one voice line to ``rate`` using one pitch policy.

    ``rate`` is the playback speed: 1.25 is 25% faster.
    """
    source_path = Path(source)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not source_path.is_file():
        raise FileNotFoundError(source_path)

    requested = max(0.5, min(3.0, float(rate or 1.0)))
    if preserve_pitch is None:
        preserve_pitch = preserve_pitch_default()
    preserve_pitch = bool(preserve_pitch)
    cap = max_speed if max_speed is not None else max_speed_default(preserve_pitch)
    if preserve_pitch:
        cap = min(float(cap), PRESERVE_MAX_SPEED)
    cap = max(1.0, min(EXTREME_MAX_SPEED, float(cap)))
    applied = requested
    capped = False
    warning = ""
    if applied > cap:
        applied = cap
        capped = True
        if preserve_pitch:
            warning = (
                f"Preserve voice is on; speed is capped at {cap:.2f}x. "
                "Shorten the script for a larger fit."
            )
        else:
            warning = f"Chipmunk speed capped at {cap:.2f}x."
    if applied < 1.0:
        applied = max(0.5, applied)

    chosen = str(engine or engine_default()).strip().lower()
    if chosen not in ENGINES:
        chosen = "auto"
    if chosen == "auto":
        chosen = "signalsmith" if signalsmith_available() else "ffmpeg"

    if abs(applied - 1.0) < 0.005:
        _normalise(source_path, output_path, timeout)
        return FitResult(
            str(source_path), str(output_path), requested, 1.0,
            preserve_pitch, "copy", capped, 0.0, warning,
        )

    backend = chosen
    if preserve_pitch:
        if chosen == "signalsmith":
            try:
                _signalsmith_preserve(source_path, output_path, applied, timeout)
            except Exception as exc:  # noqa: BLE001 - always keep a voice
                _ffmpeg_preserve(source_path, output_path, applied, timeout)
                backend = "ffmpeg-fallback"
                warning = (
                    (warning + " " if warning else "")
                    + f"Signalsmith unavailable ({str(exc)[:120]}); used FFmpeg."
                )
        else:
            _ffmpeg_preserve(source_path, output_path, applied, timeout)
            backend = "ffmpeg"
        pitch_shift = 0.0
    elif applied < 1.0:
        # Slow-down keeps pitch; chipmunk is for intentional speed-up.
        _ffmpeg_preserve(source_path, output_path, applied, timeout)
        backend = "ffmpeg-slow"
        pitch_shift = 0.0
        if not warning:
            warning = "Preserve voice is off; slow-down still keeps pitch."
    else:
        _ffmpeg_chipmunk(source_path, output_path, applied, timeout)
        backend = "ffmpeg-resample"
        pitch_shift = applied
        if not warning:
            warning = "Preserve voice is off; the voice pitch rises with speed."
    return FitResult(
        str(source_path), str(output_path), requested, applied,
        preserve_pitch, backend, capped, pitch_shift, warning,
    )


def filter_graph(rate: float, *, preserve_pitch: bool = True) -> str:
    """Legacy helper for callers that still build an FFmpeg graph.

    Prefer :func:`fit_audio`; it also supports Signalsmith.
    """
    rate = max(0.5, min(2.0, float(rate or 1.0)))
    if abs(rate - 1.0) < 0.005:
        return ""
    if preserve_pitch:
        return f"atempo={rate:.6f}"
    return (
        f"aresample={SAMPLE_RATE},"
        f"asetrate={SAMPLE_RATE * rate:.6f},"
        f"aresample={SAMPLE_RATE}"
    )
