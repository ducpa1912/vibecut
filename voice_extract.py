"""Clean voice reference extraction for later voice cloning.

Takes a video or audio file and returns clean mono WAVs: either one reference
clip (``extract_clean_voice``) or 3-5 one-minute candidates for the user to
choose (``find_voice_candidates``). Pipeline: separation (RoFormer / Demucs),
denoise, VAD trim, optional speaker filter, loudness normalise. Voice cloning
itself is out of scope.

Every heavy engine is optional. With only ffmpeg installed the pipeline still
runs, using `afftdn` and energy VAD, and the report says which models were
missing. Cache layout mirrors the Demucs stems cache in ``audio.py``.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import threading
import uuid
import wave
from pathlib import Path
from typing import Sequence

import audio
import packs
import settings_store

VERSION = 2
REFERENCE_RATE = 44100
DEFAULT_TARGET_SECONDS = 30.0
CANDIDATE_CLIP_SECONDS = 60.0
CANDIDATE_COUNT = 4
MIN_CLIP_SECONDS = 2.0
SHORT_CLIP_SECONDS = 5.0
MAX_CLIP_SECONDS = 300.0
TARGET_LUFS = -16.0
TRUE_PEAK_DBTP = -1.5
PAD_SECONDS = 0.12
JOIN_FADE_SECONDS = 0.015
SNR_OK_DB = 12.0
SEPARATION_CHOICES = ("best", "htdemucs", "htdemucs_ft", "roformer")
SEPARATION_ORDER = ("roformer", "htdemucs_ft", "htdemucs")
DENOISE_FALLBACK = "afftdn"
DENOISE_FILTER = "highpass=f=60,afftdn=nr=12:nf=-50:tn=1,lowpass=f=16000"
WORK_RATE = 48000


# ---------------------------------------------------------------- engines


def _deepfilter() -> str | None:
    """DeepFilterNet 3 command, if installed (MIT/Apache, 48 kHz)."""
    packed = packs.find_command("voice", "deep-filter")
    if packed is not None:
        return str(packed)
    return shutil.which("deep-filter")


def _audio_separator() -> str | None:
    """audio-separator CLI, the supported route for Mel-Band RoFormer."""
    packed = packs.find_command("separation", "audio-separator")
    if packed is not None:
        return str(packed)
    return shutil.which("audio-separator")


def _roformer_model() -> Path | None:
    """Mel-Band RoFormer checkpoint, from a pack or an explicit env path."""
    env = os.environ.get("VIBECUT_ROFORMER_MODEL")
    if env:
        path = Path(env).expanduser()
        return path if path.is_file() else None
    models = packs.find_dir("separation", "models/roformer")
    if models is None:
        return None
    for pattern in ("*.onnx", "*.safetensors", "*.ckpt", "*.th"):
        found = sorted(models.glob(pattern))
        if found:
            return found[0]
    return None


def _silero() -> bool:
    return audio._module("silero_vad")


def _pyannote() -> bool:
    return audio._module("pyannote.audio")


def available_backends() -> dict:
    """What the current machine can run, without importing a model."""
    ffmpeg = shutil.which("ffmpeg")
    demucs = audio.demucs_available()
    roformer = bool(_audio_separator() and _roformer_model())
    if roformer:
        separation = "roformer"
    elif demucs:
        separation = "htdemucs_ft"
    else:
        separation = None
    return {
        "separation": separation,
        "separations": {
            "htdemucs": demucs,
            "htdemucs_ft": demucs,
            "roformer": roformer,
        },
        "denoise": "deepfilternet3" if _deepfilter() else (DENOISE_FALLBACK if ffmpeg else None),
        "vad": "silero" if _silero() else "energy",
        "diarization": "pyannote" if _pyannote() else None,
    }


def _pick_separation(requested: bool | str, backends: dict) -> str | None:
    """Resolve ``best`` / explicit engine against what is installed."""
    if requested is False:
        return None
    wanted = "best" if requested is True else str(requested)
    if wanted == "best":
        for engine in SEPARATION_ORDER:
            if backends["separations"].get(engine):
                return engine
        return None
    if wanted not in SEPARATION_CHOICES[1:]:
        raise audio.AudioError(f"Unknown separation engine: {wanted}")
    if backends["separations"].get(wanted):
        return wanted
    hints = {
        "roformer": "Mel-Band RoFormer needs audio-separator and a model file. "
                    "Set VIBECUT_ROFORMER_MODEL or install a separation pack with models/roformer.",
        "htdemucs_ft": "Demucs is not installed. pip install demucs",
        "htdemucs": "Demucs is not installed. pip install demucs",
    }
    raise audio.AudioError(hints[wanted])


# ---------------------------------------------------------------- small helpers


def _check(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise audio.AudioError("Voice extraction cancelled.")


def _stage(on_stage, name: str) -> None:
    """Best-effort progress callback; a broken listener never fails a job."""
    if on_stage is None:
        return
    try:
        on_stage(str(name))
    except Exception:  # noqa: BLE001 - progress is advisory
        pass


def cache_dir(fingerprint: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", fingerprint or "source")[:80]
    return audio.CACHE / "voice_refs" / safe


#: Files up to this size are keyed by a full content hash, so the same
#: recording uploaded twice (each time under a new temp path) hits the cache.
FULL_HASH_BYTES = 256 * 1024 * 1024


def _fingerprint(source: Path, params: dict) -> str:
    """Content-keyed cache id; long videos hash both ends plus path and mtime."""
    try:
        stat = source.stat()
        size, stamp = stat.st_size, stat.st_mtime_ns
    except OSError:
        size, stamp = 0, 0
    digest = hashlib.sha256()
    identity: dict = {"size": size}
    try:
        with source.open("rb") as handle:
            if size <= FULL_HASH_BYTES:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
            else:
                digest.update(handle.read(1024 * 1024))
                handle.seek(max(0, size - 1024 * 1024))
                digest.update(handle.read(1024 * 1024))
                identity.update(path=str(source.resolve()), mtime=stamp)
    except OSError:
        identity.update(path=str(source.resolve()), mtime=stamp)
    raw = json.dumps(
        {**identity, "params": params, "version": VERSION, "content": digest.hexdigest()},
        sort_keys=True, separators=(",", ":"), default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _merge(spans: Sequence[tuple[float, float]], gap: float = 0.05) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for start, end in sorted((float(a), float(b)) for a, b in spans if b > a):
        if merged and start <= merged[-1][1] + gap:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


# ---------------------------------------------------------------- stages


def _decode(source: Path, work: Path, cancel_event) -> Path:
    """Mono 48 kHz PCM, so every later stage sees the same layout."""
    return audio._source_audio_bed(
        str(source), work, cancel_event,
        channels=1, rate=WORK_RATE, name="source.wav",
    )


def _separate_stage(
    decoded: Path,
    fingerprint: str,
    work: Path,
    cancel_event,
    engine: str = "best",
) -> tuple[Path, str]:
    """Vocal stem as mono 48 kHz WAV. Demucs caches its own FLAC copy."""
    if engine == "roformer":
        return _separate_roformer(decoded, work, cancel_event)
    model = "htdemucs_ft" if engine == "htdemucs_ft" else "htdemucs"
    stem = audio.separate_voice(str(decoded), fingerprint, cancel_event, model=model)
    output = work / "separated.wav"
    audio._run([
        audio._ffmpeg(), "-y", "-v", "error", "-i", str(stem),
        "-ar", str(WORK_RATE), "-ac", "1", "-c:a", "pcm_s16le", str(output),
    ], timeout=900, cancel_event=cancel_event)
    return output, model


def _separate_roformer(decoded: Path, work: Path, cancel_event) -> tuple[Path, str]:
    """Mel-Band RoFormer through audio-separator, if the model is installed."""
    cli = _audio_separator()
    model = _roformer_model()
    if cli is None or model is None:
        raise audio.AudioError(
            "Mel-Band RoFormer is not installed. Add audio-separator and a "
            "model file, or set VIBECUT_ROFORMER_MODEL."
        )
    output_dir = work / "roformer"
    output_dir.mkdir(parents=True, exist_ok=True)
    audio._run([
        cli, str(decoded), "--model_filename", str(model),
        "--output_dir", str(output_dir), "--output_format", "WAV",
    ], timeout=3600, cancel_event=cancel_event)
    produced = sorted(output_dir.glob("*Vocals*.wav"))
    if not produced:
        produced = sorted(output_dir.glob("*.wav"))
    if not produced:
        raise audio.AudioError("Mel-Band RoFormer finished but no vocal stem was found.")
    output = work / "separated.wav"
    audio._run([
        audio._ffmpeg(), "-y", "-v", "error", "-i", str(produced[-1]),
        "-ar", str(WORK_RATE), "-ac", "1", "-c:a", "pcm_s16le", str(output),
    ], timeout=900, cancel_event=cancel_event)
    return output, "roformer"


def _splice(
    path: Path,
    spans: Sequence[tuple[float, float]],
    output: Path,
    cancel_event=None,
) -> tuple[list[tuple[float, float]], float]:
    """Cut the spans out of the PCM and join them with short fades.

    Reads only the selected ranges, so a two-hour source is not held in RAM.
    Returns the spans on the new timeline.
    """
    import numpy as np  # noqa: PLC0415

    pieces: list = []
    timeline: list[tuple[float, float]] = []
    cursor = 0.0
    try:
        with wave.open(str(path), "rb") as handle:
            rate = handle.getframerate()
            channels = max(1, handle.getnchannels())
            width = handle.getsampwidth()
            if width != 2:
                raise audio.AudioError("Voice extraction expects 16-bit PCM audio.")
            fade = max(1, min(int(rate * JOIN_FADE_SECONDS), int(rate * 0.05)))
            total_frames = handle.getnframes()
            for start, end in spans:
                _check(cancel_event)
                left = max(0, min(total_frames, int(float(start) * rate)))
                right = max(0, min(total_frames, int(float(end) * rate)))
                if right - left < int(rate * 0.02):
                    continue
                handle.setpos(left)
                raw = handle.readframes(right - left)
                values = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                if channels > 1:
                    values = values.reshape(-1, channels).mean(axis=1)
                if values.size < int(rate * 0.02):
                    continue
                size = min(fade, max(1, len(values) // 4))
                ramp = np.linspace(0.0, 1.0, size, dtype=np.float32)
                values[:size] *= ramp
                values[-size:] *= ramp[::-1]
                pieces.append(values)
                seconds = len(values) / rate
                timeline.append((round(cursor, 3), round(cursor + seconds, 3)))
                cursor += seconds
            output_rate = rate
    except (OSError, EOFError, wave.Error) as exc:
        raise audio.AudioError("Could not read the extracted audio.") from exc
    if not pieces:
        raise audio.AudioError("No speech was found in this file.")
    joined = np.concatenate(pieces)
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(output_rate)
        handle.writeframes(
            (np.clip(joined, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
        )
    return timeline, len(joined) / output_rate


def _denoise_stage(
    path: Path,
    work: Path,
    cancel_event,
    mode: str = "auto",
) -> tuple[Path, str, list[str]]:
    """DeepFilterNet 3 when installed, otherwise a light ffmpeg spectral gate.

    ``mode`` is ``auto``, ``afftdn`` or ``deepfilternet``. ``compare`` is
    handled by ``_denoise_compare`` so both variants can be measured.
    """
    work.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    binary = _deepfilter() if mode != "afftdn" else None
    if mode == "deepfilternet" and not binary:
        raise audio.AudioError("DeepFilterNet is not installed. Add the voice pack or install deep-filter.")
    if binary:
        output_dir = work / "dfn"
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            audio._run(
                [binary, "--log-level", "error", "-o", str(output_dir), str(path)],
                timeout=1800, cancel_event=cancel_event,
            )
            produced = sorted(output_dir.glob("*.wav"), key=lambda item: item.stat().st_mtime)
            if produced:
                return produced[-1], "deepfilternet3", warnings
            warnings.append("DeepFilterNet produced no file; used ffmpeg denoise.")
        except audio.AudioError as exc:
            if cancel_event is not None and cancel_event.is_set():
                raise
            warnings.append(f"DeepFilterNet failed ({str(exc).splitlines()[0]}); used ffmpeg denoise.")
    output = work / "denoised.wav"
    audio._run([
        audio._ffmpeg(), "-y", "-v", "error", "-i", str(path),
        "-af", DENOISE_FILTER, "-ar", str(WORK_RATE), "-ac", "1",
        "-c:a", "pcm_s16le", str(output),
    ], timeout=1800, cancel_event=cancel_event)
    return output, DENOISE_FALLBACK, warnings


def _denoise_compare(path: Path, work: Path, cancel_event) -> tuple[Path, str, list[str], list[dict]]:
    """Run ffmpeg and DeepFilterNet, measure both, keep the better one.

    Alpha test mode: the report carries both trials so users can hear a forced
    variant by rerunning with ``denoise='afftdn'`` or ``'deepfilternet'``.
    """
    warnings: list[str] = []
    trials: list[dict] = []
    variants: list[tuple[Path, str, list[str]]] = []
    ffmpeg_dir = work / "denoise-afftdn"
    ffmpeg_dir.mkdir(parents=True, exist_ok=True)
    variants.append(_denoise_stage(path, ffmpeg_dir, cancel_event, mode="afftdn"))
    if _deepfilter():
        dfn_dir = work / "denoise-deepfilternet"
        dfn_dir.mkdir(parents=True, exist_ok=True)
        try:
            variants.append(_denoise_stage(path, dfn_dir, cancel_event, mode="deepfilternet"))
        except audio.AudioError as exc:
            if cancel_event is not None and cancel_event.is_set():
                raise
            warnings.append(
                f"DeepFilterNet failed ({str(exc).splitlines()[0]}); only ffmpeg denoise was tested."
            )
    seen: set[str] = set()
    unique: list[tuple[Path, str, list[str]]] = []
    for variant_path, label, stage_warnings in variants:
        warnings.extend(stage_warnings)
        if label in seen:
            continue
        seen.add(label)
        unique.append((variant_path, label, stage_warnings))
    scored: list[tuple[float, Path, str]] = []
    for variant_path, label, _stage_warnings in unique:
        _check(cancel_event)
        spans = audio.speech_spans(
            variant_path, threshold_db=-38.0, min_speech=0.2, min_silence=0.3,
        )
        metrics = _quality_report(
            variant_path, analysis=variant_path, analysis_spans=spans,
            source_clipping=None, loudness=None,
        )
        snr = metrics.get("snr_db")
        residual = metrics.get("music_noise_residual_db")
        score = float(snr or 0.0) + min(0.0, float(residual or 0.0)) * 0.1
        trials.append({
            "engine": label,
            "snr_db": snr,
            "music_noise_residual_db": residual,
            "score": round(score, 2),
            "kept": False,
        })
        scored.append((score, variant_path, label))
    scored.sort(key=lambda item: -item[0])
    _score, chosen_path, chosen_label = scored[0]
    for trial in trials:
        trial["kept"] = trial["engine"] == chosen_label
    if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.5:
        warnings.append(
            "DeepFilterNet and ffmpeg denoise scored within 0.5 dB; listen before trusting the pick."
        )
    return chosen_path, chosen_label, warnings, trials


def _vad_stage(path: Path, cancel_event) -> tuple[list[tuple[float, float]], str, list[str]]:
    """Speech spans from Silero VAD, else the energy gate already in audio.py."""
    warnings: list[str] = []
    if _silero():
        try:
            from silero_vad import (  # noqa: PLC0415 - optional dependency
                get_speech_timestamps, load_silero_vad, read_audio,
            )

            model = load_silero_vad()
            wav = read_audio(str(path), sampling_rate=16000)
            stamps = get_speech_timestamps(
                wav, model, sampling_rate=16000, return_seconds=True,
                min_speech_duration_ms=250, min_silence_duration_ms=300,
                speech_pad_ms=60,
            )
            spans = _merge(
                [(float(item["start"]), float(item["end"])) for item in stamps],
                gap=0.0,
            )
            return spans, "silero", warnings
        except audio.AudioError:
            raise
        except Exception as exc:  # model missing or download failed
            warnings.append(
                f"Silero VAD failed ({str(exc).splitlines()[0][:120]}); used energy VAD."
            )
    _check(cancel_event)
    spans = audio.speech_spans(
        path, threshold_db=-38.0, min_speech=0.2, min_silence=0.3,
    )
    return spans, "energy", warnings


def _speaker_spans(
    path: Path,
    spans: Sequence[tuple[float, float]],
    speaker: int | str,
    cancel_event,
) -> tuple[list[tuple[float, float]], str, list[str]]:
    """Keep only the chosen speaker's turns. 1-based rank or a diarizer label."""
    if not _pyannote():
        raise audio.AudioError(
            "Speaker filtering needs pyannote.audio. "
            "pip install pyannote.audio and accept the pyannote/speaker-diarization-3.1 terms."
        )
    token = (
        os.environ.get("HF_TOKEN")
        or os.environ.get("HUGGINGFACE_TOKEN")
        or settings_store.get_secret("huggingface")
    )
    if not token:
        raise audio.AudioError(
            "Speaker filtering needs a Hugging Face token. Set HF_TOKEN or huggingface in Setup."
        )
    _check(cancel_event)
    try:
        import torch  # noqa: PLC0415
        from pyannote.audio import Pipeline  # noqa: PLC0415

        try:
            pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1", token=token,
            )
        except TypeError:  # pyannote.audio 3.x used use_auth_token
            pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1", use_auth_token=token,
            )
        device = (
            "mps"
            if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()
            else "cpu"
        )
        try:
            pipeline.to(torch.device(device))
            diarization = pipeline(str(path))
        except Exception:
            if device != "mps":
                raise
            pipeline.to(torch.device("cpu"))
            diarization = pipeline(str(path))
        annotation = getattr(diarization, "speaker_diarization", diarization)
        turns = [
            (float(turn.start), float(turn.end), str(label))
            for turn, _, label in annotation.itertracks(yield_label=True)
        ]
    except audio.AudioError:
        raise
    except Exception as exc:
        raise audio.AudioError(
            "Speaker diarization failed. Check the pyannote terms and HF_TOKEN. "
            + str(exc).splitlines()[0][:200]
        ) from None
    _check(cancel_event)
    if not turns:
        raise audio.AudioError("Speaker diarization found no speakers.")
    talk: dict[str, float] = {}
    for start, end, label in turns:
        talk[label] = talk.get(label, 0.0) + max(0.0, end - start)
    overlap_seconds = 0.0
    for index, (start, end, label) in enumerate(turns):
        for other_start, other_end, other_label in turns[index + 1:]:
            if label == other_label:
                continue
            overlap_seconds += max(0.0, min(end, other_end) - max(start, other_start))
    warnings: list[str] = []
    if overlap_seconds >= 0.2:
        warnings.append(
            f"Overlapping speech found ({overlap_seconds:.1f} s); "
            "a clone may learn more than one voice."
        )
    labels = [label for label, _ in sorted(talk.items(), key=lambda item: -item[1])]
    if isinstance(speaker, int):
        if speaker < 1 or speaker > len(labels):
            raise audio.AudioError(
                f"Speaker {speaker} was not found. This file has {len(labels)} speaker(s)."
            )
        chosen = labels[speaker - 1]
    else:
        chosen = str(speaker)
        if chosen not in talk:
            raise audio.AudioError(
                f"Speaker {chosen} was not found. Available: {', '.join(labels)}."
            )
    kept: list[tuple[float, float]] = []
    for start, end in spans:
        for turn_start, turn_end, label in turns:
            if label != chosen:
                continue
            left, right = max(start, turn_start), min(end, turn_end)
            if right - left >= 0.05:
                kept.append((left, right))
    kept = _merge(kept)
    if not kept:
        raise audio.AudioError(f"Speaker {chosen} has no speech in this file.")
    return kept, f"pyannote:{chosen}", warnings


# ---------------------------------------------------------------- trim + splice


def _select_spans(
    spans: Sequence[tuple[float, float]],
    target_seconds: float | None,
    pad: float = PAD_SECONDS,
) -> list[tuple[float, float]]:
    """Pad each span, merge the overlaps, then cap the total length.

    ``None`` keeps all speech up to ``MAX_CLIP_SECONDS``; a longer reference
    is not useful to a clone provider and would only cost memory.
    """
    padded = _merge(
        [(max(0.0, start - pad), end + pad) for start, end in spans], gap=0.05,
    )
    limit = MAX_CLIP_SECONDS if target_seconds is None else min(
        float(target_seconds), MAX_CLIP_SECONDS,
    )
    selected: list[tuple[float, float]] = []
    total = 0.0
    for start, end in padded:
        remaining = limit - total
        if remaining <= 0.05:
            break
        if end - start > remaining:
            end = start + remaining
        if end - start < 0.05:
            continue
        selected.append((start, end))
        total += end - start
    return selected


def _iter_frames(path: Path, frame_seconds: float = 0.02, blocks_per_read: int = 200):
    """Yield ``(offset_seconds, float blocks, rate)`` without loading the file.

    Each read is frame-aligned, and each yielded block is one frame, so long
    recordings cost one frame table at a time.
    """
    try:
        import numpy as np  # noqa: PLC0415
    except ImportError as exc:
        raise audio.AudioError("numpy is required for voice extraction.") from exc
    try:
        with wave.open(str(path), "rb") as handle:
            rate = handle.getframerate()
            channels = max(1, handle.getnchannels())
            width = handle.getsampwidth()
            if width != 2:
                raise audio.AudioError("Voice extraction expects 16-bit PCM audio.")
            frame = max(1, int(rate * frame_seconds))
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
                yield offset, values[:usable].reshape(-1, frame), rate
                offset += usable
    except (OSError, EOFError, wave.Error) as exc:
        raise audio.AudioError("Could not read the extracted audio.") from exc


def _normalize(
    path: Path,
    output: Path,
    *,
    target_lufs: float,
    sample_rate: int,
    cancel_event=None,
) -> dict:
    """Linear gain to the reference loudness, then mono PCM export.

    Linear gain keeps the timbre intact; loudnorm's dynamic mode does not.
    """
    measured = audio.measure_loudness(path)
    gain_db = 0.0
    warning = ""
    if measured:
        gain_db = float(target_lufs) - float(measured["integrated_lufs"])
        headroom = TRUE_PEAK_DBTP - float(measured["true_peak_dbtp"])
        if gain_db > headroom:
            gain_db = headroom
        gain_db = max(-24.0, min(24.0, gain_db))
    else:
        warning = "Loudness could not be measured; the clip keeps its source level."
    audio._run([
        audio._ffmpeg(), "-y", "-v", "error", "-i", str(path),
        "-af", f"volume={gain_db:.2f}dB",
        "-ar", str(int(sample_rate)), "-ac", "1", "-c:a", "pcm_s16le", str(output),
    ], timeout=900, cancel_event=cancel_event)
    return {
        "gain_db": round(gain_db, 2),
        "measured": measured,
        "warning": warning,
    }


# ---------------------------------------------------------------- report


def _band_ratio_db(quiet, speech, rate: int, low: float = 300.0, high: float = 3400.0) -> float | None:
    import numpy as np  # noqa: PLC0415

    if len(quiet) < rate * 0.05 or len(speech) < rate * 0.05:
        return None

    def band_power(values):
        spectrum = np.fft.rfft(values)
        freqs = np.fft.rfftfreq(values.size, 1.0 / max(1, rate))
        mask = (freqs >= low) & (freqs <= high)
        if not mask.any():
            return 0.0
        return float(np.sum(np.abs(spectrum[mask]) ** 2)) / max(1, values.size)

    quiet_power = band_power(quiet)
    speech_power = band_power(speech)
    if speech_power <= 1e-18:
        return None
    return round(10.0 * math.log10(max(quiet_power, 1e-18) / speech_power), 2)


def _pcm_stats(path: Path) -> dict:
    """Peak and clipped-sample count, streamed a frame table at a time."""
    import numpy as np  # noqa: PLC0415

    peak = 0.0
    count = 0
    total = 0
    for _offset, blocks, _rate in _iter_frames(Path(path), frame_seconds=0.1):
        absolute = np.abs(blocks)
        peak = max(peak, float(absolute.max()) if absolute.size else 0.0)
        count += int(np.count_nonzero(absolute >= 0.999))
        total += int(absolute.size)
    return {"peak": peak, "clipped_samples": count, "samples": total}


def _clip_stats(path: Path, stats: dict | None = None) -> dict:
    stats = stats or _pcm_stats(path)
    ratio = stats["clipped_samples"] / max(1, stats["samples"])
    return {
        "clipped": ratio >= 0.001,
        "ratio": round(ratio, 6),
        "samples": stats["clipped_samples"],
    }


def _quality_report(
    clean: Path,
    *,
    analysis: Path,
    analysis_spans: Sequence[tuple[float, float]],
    source_clipping: dict | None,
    loudness: dict | None,
    warning: str = "",
) -> dict:
    """Speech/noise levels from the pre-splice clip, peaks from the export.

    The exported clip is a splice of speech spans, so it has no natural gaps
    left to measure a noise floor in. Levels and residual energy come from the
    denoised clip and its VAD spans instead; clipping and loudness come from
    the file the caller receives. Both files are streamed, never fully loaded.
    """
    import numpy as np  # noqa: PLC0415

    speech_dbs: list[float] = []
    quiet_dbs: list[float] = []
    speech_chunks: list = []
    quiet_chunks: list = []
    speech_samples = 0
    quiet_samples = 0
    sample_cap = 48000 * 8
    rate = 0
    for offset, blocks, rate in _iter_frames(Path(analysis)):
        rms = np.sqrt(np.mean(np.square(blocks), axis=1))
        dbs = 20.0 * np.log10(np.maximum(rms, 1e-9))
        frame = blocks.shape[1]
        centres = (offset + np.arange(len(blocks)) * frame + frame / 2) / rate
        in_speech = np.zeros(len(blocks), dtype=bool)
        for start, end in analysis_spans:
            in_speech |= (centres >= start) & (centres < end)
        speech_dbs.extend(dbs[in_speech].tolist())
        quiet_dbs.extend(dbs[~in_speech].tolist())
        if speech_samples < sample_cap:
            picked = blocks[in_speech].reshape(-1)[: sample_cap - speech_samples]
            if picked.size:
                speech_chunks.append(picked)
                speech_samples += picked.size
        if quiet_samples < sample_cap:
            picked = blocks[~in_speech].reshape(-1)[: sample_cap - quiet_samples]
            if picked.size:
                quiet_chunks.append(picked)
                quiet_samples += picked.size
    if not speech_dbs:
        return {"snr_db": None, "music_noise_residual_db": None}
    noise_floor = float(np.percentile(quiet_dbs, 10)) if quiet_dbs else None
    speech_level = float(np.percentile(speech_dbs, 50))
    snr = None
    if noise_floor is not None:
        snr = round(speech_level - noise_floor, 2)
    residual = None
    if rate and speech_chunks and quiet_chunks:
        residual = _band_ratio_db(
            np.concatenate(quiet_chunks), np.concatenate(speech_chunks), rate,
        )
    stats = _pcm_stats(Path(clean))
    report = {
        "snr_db": snr,
        "music_noise_residual_db": residual,
        "noise_floor_dbfs": None if noise_floor is None else round(noise_floor, 2),
        "speech_level_dbfs": round(speech_level, 2),
        "peak_dbfs": round(20.0 * math.log10(max(float(stats["peak"]), 1e-9)), 2),
        "clipping": _clip_stats(Path(clean), stats),
        "source_clipping": source_clipping or {"clipped": False, "ratio": 0.0, "samples": 0},
        "loudness": loudness,
    }
    if warning:
        report["note"] = warning
    return report


# ---------------------------------------------------------------- preparation


def _prepare(
    source_path: Path,
    work: Path,
    *,
    fingerprint: str,
    speaker: int | str | None,
    separate: bool | str,
    denoise: bool | str,
    cancel_event,
    models: dict,
    warnings: list[str],
) -> dict:
    """Run decode, separation, denoise, VAD and the optional speaker filter once."""
    decoded = _decode(source_path, work, cancel_event)
    _check(cancel_event)
    source_clipping = _clip_stats(decoded)
    clip = decoded
    backends = available_backends()
    selected_engine = _pick_separation(separate, backends)
    if selected_engine:
        trail = [selected_engine]
        if selected_engine == "roformer":
            trail += [item for item in ("htdemucs_ft", "htdemucs")
                      if backends["separations"].get(item)]
        elif selected_engine == "htdemucs_ft" and backends["separations"].get("htdemucs"):
            trail.append("htdemucs")
        last_error: audio.AudioError | None = None
        for engine in trail:
            try:
                clip, model = _separate_stage(
                    decoded, fingerprint, work, cancel_event, engine=engine,
                )
                models["separation"] = model
                if engine != selected_engine:
                    warnings.append(
                        f"{selected_engine} failed; fell back to {engine}."
                    )
                break
            except audio.AudioError as exc:
                if cancel_event is not None and cancel_event.is_set():
                    raise
                last_error = exc
                warnings.append(f"{engine} separation failed; trying the next engine.")
        else:
            raise last_error or audio.AudioError("Voice separation failed.")
    elif separate is False:
        models["separation"] = "skipped"
        warnings.append("Separation was disabled; music and effects may remain.")
    else:
        warnings.append(
            "No voice separation engine is installed (Demucs / Mel-Band RoFormer); "
            "music and effects may remain. pip install demucs"
        )
    _check(cancel_event)
    mode = "auto" if denoise is True else "off" if denoise is False else str(denoise)
    if mode not in ("auto", "afftdn", "deepfilternet", "compare", "off"):
        raise audio.AudioError(f"Unknown denoise mode: {mode}")
    trials: list[dict] = []
    if mode == "compare":
        clip, models["denoise"], stage_warnings, trials = _denoise_compare(
            clip, work, cancel_event,
        )
        warnings.extend(stage_warnings)
    elif mode != "off":
        clip, models["denoise"], stage_warnings = _denoise_stage(
            clip, work, cancel_event, mode=mode,
        )
        warnings.extend(stage_warnings)
    _check(cancel_event)
    spans, models["vad"], vad_warnings = _vad_stage(clip, cancel_event)
    warnings.extend(vad_warnings)
    if speaker == "auto":
        if _pyannote():
            speaker = 1
        else:
            warnings.append(
                "Main-speaker filter needs pyannote.audio; candidates were not speaker-filtered."
            )
            speaker = None
    if speaker is not None:
        spans, models["diarization"], speaker_warnings = _speaker_spans(
            clip, spans, speaker, cancel_event,
        )
        warnings.extend(speaker_warnings)
    return {
        "decoded": decoded,
        "clip": clip,
        "spans": spans,
        "models": models,
        "warnings": warnings,
        "source_clipping": source_clipping,
        "denoise_trials": trials,
    }


def _item_warnings(
    quality: dict,
    duration: float,
    warnings: Sequence[str] = (),
) -> list[str]:
    items = list(warnings)
    snr = quality.get("snr_db")
    if snr is not None and float(snr) < SNR_OK_DB:
        items.append(f"Clean clip SNR is {snr:.1f} dB; check for music, noise or crosstalk.")
    if duration < SHORT_CLIP_SECONDS:
        items.append(
            f"Clip is {duration:.1f} s; most clone providers want 10 s or more."
        )
    clipping = quality.get("source_clipping") or {}
    if clipping.get("clipped"):
        items.append("Source clips at full scale; the cleaned clip may sound distorted.")
    note = quality.get("note")
    if note:
        items.append(note)
    return list(dict.fromkeys(items))


def _cache_report(root: Path, min_files: int = 1) -> dict | None:
    report = root / "report.json"
    if not report.is_file():
        return None
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("version") != VERSION:
        return None
    files = list(root.glob("candidate-*.wav")) + list(root.glob("clean.wav"))
    if len(files) < min_files:
        return None
    return data


def _copy_cached(root: Path, out_dir: Path, names: Sequence[str]) -> list[Path]:
    copied = []
    for name in names:
        target = out_dir / name
        shutil.copyfile(root / name, target)
        copied.append(target)
    return copied


# ---------------------------------------------------------------- single clip


def extract_clean_voice(
    source: str | Path,
    out_dir: str | Path,
    *,
    speaker: int | str | None = None,
    target_seconds: float | None = DEFAULT_TARGET_SECONDS,
    cancel_event: threading.Event | None = None,
    separate: bool | str = "best",
    denoise: bool | str = "auto",
    target_lufs: float = TARGET_LUFS,
    sample_rate: int = REFERENCE_RATE,
    use_cache: bool = True,
) -> dict:
    """Return one clean, mono, loudness-normalised speech reference clip.

    ``separate`` is ``best`` (RoFormer, then htdemucs_ft, then htdemucs),
    ``htdemucs``, ``htdemucs_ft``, ``roformer`` or ``False``. ``denoise`` is
    ``auto``, ``afftdn``, ``deepfilternet``, ``compare`` or ``False``.

    ``speaker`` keeps one diarised speaker (1-based rank by talk time, or a
    pyannote label). Without pyannote the call fails with an install hint;
    other missing engines degrade and say so in the report.
    """
    source_path = Path(source).expanduser()
    if not source_path.is_file():
        raise audio.AudioError("Source file not found.")
    if target_seconds is not None and float(target_seconds) < 1.0:
        raise audio.AudioError("target_seconds must be at least 1 second.")
    try:
        audio._ffmpeg()
    except audio.AudioError:
        raise audio.AudioError("ffmpeg is not installed or not on PATH.") from None
    _check(cancel_event)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fingerprint = _fingerprint(source_path, {
        "mode": "single",
        "speaker": speaker,
        "target": target_seconds,
        "lufs": target_lufs,
        "rate": sample_rate,
        "separate": str(separate),
        "denoise": str(denoise),
        "backends": available_backends(),
    })
    root = cache_dir(fingerprint)
    if use_cache:
        cached = _cache_report(root)
        if cached and (root / "clean.wav").is_file():
            output = out_dir / "clean_voice.wav"
            shutil.copyfile(root / "clean.wav", output)
            cached = dict(cached)
            cached["path"] = str(output)
            cached["cache_path"] = str(root / "clean.wav")
            cached["cached"] = True
            return cached
    work = root / f"work-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    work.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    models: dict[str, str | None] = {
        "separation": None, "denoise": None, "vad": None, "diarization": None,
    }
    try:
        prepared = _prepare(
            source_path, work,
            fingerprint=fingerprint,
            speaker=speaker, separate=separate, denoise=denoise,
            cancel_event=cancel_event,
            models=models, warnings=warnings,
        )
        clip = prepared["clip"]
        spans = prepared["spans"]
        if not spans:
            raise audio.AudioError("No speech was found in this file.")
        selected = _select_spans(spans, target_seconds)
        if not selected:
            raise audio.AudioError("No speech was found in this file.")
        trimmed = work / "trimmed.wav"
        _timeline, duration = _splice(clip, selected, trimmed, cancel_event)
        if duration < MIN_CLIP_SECONDS:
            raise audio.AudioError(
                f"Only {duration:.1f} s of speech was found; at least "
                f"{MIN_CLIP_SECONDS:.0f} s is needed."
            )
        _check(cancel_event)
        exported = work / "clean.wav"
        gain = _normalize(
            trimmed, exported,
            target_lufs=target_lufs, sample_rate=sample_rate,
            cancel_event=cancel_event,
        )
        _check(cancel_event)
        quality = _quality_report(
            exported,
            analysis=clip,
            analysis_spans=selected,
            source_clipping=prepared["source_clipping"],
            loudness=audio.measure_loudness(exported),
            warning=gain.get("warning", ""),
        )
        report = {
            "version": VERSION,
            "source": str(source_path),
            "duration": round(duration, 3),
            "sample_rate": int(sample_rate),
            "channels": 1,
            "speech_seconds": round(duration, 3),
            "gain_db": gain.get("gain_db", 0.0),
            "models": models,
            "quality": quality,
            "denoise_trials": prepared["denoise_trials"],
            "warnings": _item_warnings(
                quality, duration, prepared["warnings"],
            ),
        }
        root.mkdir(parents=True, exist_ok=True)
        shutil.move(str(exported), str(root / "clean.wav"))
        report["path"] = str(root / "clean.wav")
        report["cache_path"] = str(root / "clean.wav")
        report["cached"] = False
        (root / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8",
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)
    output = out_dir / "clean_voice.wav"
    shutil.copyfile(root / "clean.wav", output)
    report["path"] = str(output)
    return report


# ---------------------------------------------------------------- candidates


def _frame_table(path: Path):
    """Frame centres, levels and speech mask for candidate scoring."""
    import numpy as np  # noqa: PLC0415

    centres: list[float] = []
    levels: list[float] = []
    for offset, blocks, rate in _iter_frames(path):
        rms = np.sqrt(np.mean(np.square(blocks), axis=1))
        dbs = 20.0 * np.log10(np.maximum(rms, 1e-9))
        frame = blocks.shape[1]
        centres.extend(((offset + np.arange(len(blocks)) * frame + frame / 2) / rate).tolist())
        levels.extend(dbs.tolist())
    return np.asarray(centres), np.asarray(levels)


def _window_score(
    times, levels, speech, start: float, end: float,
) -> dict | None:
    import numpy as np  # noqa: PLC0415

    mask = (times >= start) & (times < end)
    if not mask.any():
        return None
    in_window = levels[mask]
    voiced = speech[mask]
    speech_fraction = float(voiced.mean())
    speech_levels = in_window[voiced]
    quiet_levels = in_window[~voiced]
    snr = None
    floor = None
    if speech_levels.size and quiet_levels.size:
        speech_level = float(np.percentile(speech_levels, 50))
        floor = float(np.percentile(quiet_levels, 10))
        snr = speech_level - floor
    score = speech_fraction * 100.0
    if snr is not None:
        score += min(40.0, max(0.0, snr)) * 0.5
        score -= max(0.0, floor + 45.0) * 0.8
    if speech_levels.size:
        score += max(0.0, min(10.0, (float(np.percentile(speech_levels, 50)) + 30.0) * 0.2))
    return {
        "start": round(float(start), 3),
        "end": round(float(end), 3),
        "speech_fraction": round(speech_fraction, 3),
        "snr_db": None if snr is None else round(snr, 2),
        "noise_floor_dbfs": None if floor is None else round(floor, 2),
        "score": round(score, 2),
    }


def _candidate_windows(
    spans: Sequence[tuple[float, float]],
    clip_seconds: float,
    count: int,
    times,
    levels,
) -> list[dict]:
    """Score sliding windows, then keep up to ``count`` non-overlapping ones."""
    import numpy as np  # noqa: PLC0415

    merged = _merge(spans)
    if not merged:
        return []
    speech = np.zeros(len(times), dtype=bool)
    for start, end in merged:
        speech |= (times >= start) & (times < end)
    first = max(0.0, merged[0][0] - PAD_SECONDS)
    last = merged[-1][1] + PAD_SECONDS
    step = max(5.0, clip_seconds / 4.0)
    starts = {first, max(0.0, last - clip_seconds)}
    cursor = first
    while cursor < last:
        starts.add(round(cursor, 3))
        cursor += step
    scored = []
    for start in sorted(starts):
        end = min(last, start + clip_seconds)
        if end - start < MIN_CLIP_SECONDS:
            continue
        score = _window_score(times, levels, speech, start, end)
        if score:
            scored.append(score)
    scored.sort(key=lambda item: -item["score"])
    chosen: list[dict] = []
    for candidate in scored:
        if len(chosen) >= count:
            break
        overlaps = False
        for other in chosen:
            common = min(candidate["end"], other["end"]) - max(candidate["start"], other["start"])
            if common > min(10.0, clip_seconds * 0.25):
                overlaps = True
                break
        if not overlaps:
            chosen.append(candidate)
    chosen.sort(key=lambda item: item["start"])
    return chosen


def find_voice_candidates(
    source: str | Path,
    out_dir: str | Path,
    *,
    count: int = CANDIDATE_COUNT,
    clip_seconds: float = CANDIDATE_CLIP_SECONDS,
    speaker: int | str | None = "auto",
    cancel_event: threading.Event | None = None,
    separate: bool | str = "best",
    denoise: bool | str = "auto",
    target_lufs: float = TARGET_LUFS,
    sample_rate: int = REFERENCE_RATE,
    use_cache: bool = True,
    on_stage=None,
) -> dict:
    """Find 3-5 clean speech batches and let the user choose one.

    Each candidate is up to ``clip_seconds`` long. Ranking prefers speech
    coverage, then a low noise floor and a clean residual. ``speaker="auto"``
    keeps the main diarised speaker when pyannote is installed. Without it the
    candidates may contain more than one voice; the report warns about that
    and about overlapping speech when pyannote runs.

    ``on_stage`` receives short status names (``preparing``, ``scoring``,
    ``exporting``) for a progress line. It is optional and never required.
    """
    _stage(on_stage, "starting")
    source_path = Path(source).expanduser()
    if not source_path.is_file():
        raise audio.AudioError("Source file not found.")
    if not 1 <= int(count) <= 5:
        raise audio.AudioError("count must be between 1 and 5 candidates.")
    clip_seconds = float(clip_seconds)
    if clip_seconds < MIN_CLIP_SECONDS:
        raise audio.AudioError(f"clip_seconds must be at least {MIN_CLIP_SECONDS:.0f} seconds.")
    clip_seconds = min(clip_seconds, MAX_CLIP_SECONDS)
    try:
        audio._ffmpeg()
    except audio.AudioError:
        raise audio.AudioError("ffmpeg is not installed or not on PATH.") from None
    _check(cancel_event)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fingerprint = _fingerprint(source_path, {
        "mode": "candidates",
        "count": int(count),
        "clip": clip_seconds,
        "speaker": speaker,
        "lufs": target_lufs,
        "rate": sample_rate,
        "separate": str(separate),
        "denoise": str(denoise),
        "backends": available_backends(),
    })
    root = cache_dir(fingerprint)
    if use_cache:
        cached = _cache_report(root, min_files=1)
        if cached and cached.get("candidates"):
            # A skipped window leaves a gap (01, 03); name files by each index.
            names = [f"candidate-{int(item['index']):02d}.wav" for item in cached["candidates"]]
            if all((root / name).is_file() for name in names):
                copied = _copy_cached(root, out_dir, names)
                data = dict(cached)
                data["candidates"] = [
                    {**item, "path": str(path)}
                    for item, path in zip(cached["candidates"], copied)
                ]
                data["cache_path"] = str(root)
                data["cached"] = True
                return data
    work = root / f"work-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    work.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    models: dict[str, str | None] = {
        "separation": None, "denoise": None, "vad": None, "diarization": None,
    }
    try:
        _stage(on_stage, "preparing")
        prepared = _prepare(
            source_path, work,
            fingerprint=fingerprint,
            speaker=speaker, separate=separate, denoise=denoise,
            cancel_event=cancel_event,
            models=models, warnings=warnings,
        )
        clip = prepared["clip"]
        spans = prepared["spans"]
        if models["diarization"] is None:
            warnings.append(
                "Candidates may include more than one speaker. "
                "Install pyannote.audio or pass speaker=1 to keep the main speaker."
            )
        if not spans:
            raise audio.AudioError("No speech was found in this file.")
        _stage(on_stage, "scoring")
        times, levels = _frame_table(clip)
        windows = _candidate_windows(spans, clip_seconds, int(count), times, levels)
        if not windows:
            raise audio.AudioError("No speech windows were found in this file.")
        _stage(on_stage, "exporting")
        candidates: list[dict] = []
        for index, window in enumerate(windows, start=1):
            selected = _select_spans(
                [(max(start, window["start"]), min(end, window["end"])) for start, end in spans],
                clip_seconds,
            )
            selected = [span for span in selected if span[1] > span[0]]
            if not selected:
                continue
            trimmed = work / f"trimmed-{index}.wav"
            _timeline, duration = _splice(clip, selected, trimmed, cancel_event)
            if duration < MIN_CLIP_SECONDS:
                continue
            exported = work / f"candidate-{index:02d}.wav"
            gain = _normalize(
                trimmed, exported,
                target_lufs=target_lufs, sample_rate=sample_rate,
                cancel_event=cancel_event,
            )
            quality = _quality_report(
                exported,
                analysis=clip,
                analysis_spans=selected,
                source_clipping=prepared["source_clipping"],
                loudness=audio.measure_loudness(exported),
                warning=gain.get("warning", ""),
            )
            candidates.append({
                "index": index,
                "path": str(exported),
                "duration": round(duration, 3),
                "speech_seconds": round(duration, 3),
                "speech_fraction": window["speech_fraction"],
                "score": window["score"],
                "window": [window["start"], window["end"]],
                "gain_db": gain.get("gain_db", 0.0),
                "quality": quality,
                "warnings": _item_warnings(
                    quality, duration, prepared["warnings"],
                ),
            })
        if not candidates:
            raise audio.AudioError("No usable speech candidates were found in this file.")
        if len(candidates) < 3:
            warnings.append(
                f"Only {len(candidates)} candidate(s) were found; the source may be short or quiet."
            )
        root.mkdir(parents=True, exist_ok=True)
        for item in candidates:
            name = f"candidate-{item['index']:02d}.wav"
            shutil.move(item["path"], root / name)
            item["path"] = str(root / name)
        report = {
            "version": VERSION,
            "source": str(source_path),
            "clip_seconds": clip_seconds,
            "models": models,
            "denoise_trials": prepared["denoise_trials"],
            "candidates": candidates,
            "warnings": warnings,
            "cached": False,
        }
        (root / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8",
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)
    copied = _copy_cached(
        root, out_dir,
        [f"candidate-{item['index']:02d}.wav" for item in report["candidates"]],
    )
    for item, path in zip(report["candidates"], copied):
        item["path"] = str(path)
    report["cache_path"] = str(root)
    return report
