"""Speech-to-text for DuckSuite: local Apple Speech and local Whisper only.

Wave 2 track T2 owns this module.  It replaces the transcription block that
used to live in ``pipeline.py`` and adds the Transcript v2 contract from
``ROADMAP.md`` "Product contracts still in force" — Transcript v2:

* Apple SpeechAnalyzer is the default local engine and emits word timings from
  each attributed run's ``audioTimeRange``.
* Whisper runs through the bundled whisper-cli with full token timing JSON and
  ``large-v3-turbo`` as the default model.
* Long sources are cut into 10 minute chunks with 5 s overlap.  Each finished
  chunk is cached by ``audio_hash + engine + model + chunk index`` so a crash
  resumes at the last finished chunk.
* Speech never leaves the Mac.  Apple Speech and the bundled Whisper pack are
  the only engines, and no route, saved list or environment variable can add a
  cloud one.

Nothing here runs at import time.  Tests fake every engine.
"""

from __future__ import annotations

import difflib
import hashlib
import inspect
import json
import locale
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
import uuid
import wave
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from duckcore import media, model_slots, packs as model_packs
from . import settings_store
from . import vision

ROOT = Path(__file__).resolve().parents[2]
TOOLS = Path(os.environ.get("DUCK_SWIFT_DIR", ROOT / "tools")).expanduser()
HELPERS = Path(os.environ.get("DUCK_HELPER_DIR", ROOT / "bin")).expanduser()

SCHEMA_VERSION = 2
CHUNK_SECONDS = 600.0
OVERLAP_SECONDS = 5.0
LOW_CONFIDENCE = 0.5
DEFAULT_WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"
# Speech stays on this Mac: Apple SpeechAnalyzer and the bundled Whisper pack.
# There is no cloud ladder, and no engine list can add one.
LOCAL_STT_ENGINES = ("apple", "whisper")
STT_ENGINES = LOCAL_STT_ENGINES
WHISPER_MODELS = (
    {
        "id": DEFAULT_WHISPER_MODEL,
        "name": "Best · accurate",
        "size_mb": 1600,
    },
)
LEGACY_WHISPER_MODELS = {
    "mlx-community/whisper-small-mlx": DEFAULT_WHISPER_MODEL,
    "mlx-community/whisper-medium-mlx-q4": DEFAULT_WHISPER_MODEL,
    "mlx-community/whisper-large-v3-turbo-q4": DEFAULT_WHISPER_MODEL,
    "whisper-1": DEFAULT_WHISPER_MODEL,
    "whisper-large-v3": DEFAULT_WHISPER_MODEL,
}
SPEECH_LOCALES = {
    "zh": "zh-CN", "en": "en-US", "ja": "ja-JP", "ko": "ko-KR",
    "es": "es-ES", "fr": "fr-FR", "de": "de-DE", "pt": "pt-BR",
    "it": "it-IT", "ru": "ru-RU", "vi": "vi-VN", "th": "th-TH",
    "id": "id-ID", "tr": "tr-TR", "hi": "hi-IN", "ar": "ar-SA",
}
DEFAULT_ROUTES = (
    {"provider": "apple", "model": "on-device-3b"},
    {"provider": "whisper", "model": DEFAULT_WHISPER_MODEL},
)
_UNSET = object()


class SttError(RuntimeError):
    """A local transcription helper failed."""


# ---------------------------------------------------------------- helpers


def _which(name: str) -> str | None:
    return shutil.which(name)


def _ffmpeg() -> str:
    try:
        return media.ffmpeg()
    except media.MediaError as exc:
        raise SttError(str(exc)) from exc


def _run(cmd: list[str], timeout: int | float | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "")[-1600:]
        raise SttError(f"command failed: {Path(cmd[0]).name}\n{tail}")
    return result


def _float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _confidence(value: Any, default: float = LOW_CONFIDENCE) -> float:
    number = _float(value, default)
    return round(min(1.0, max(0.0, number)), 4)


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        value = str(value or "")
    return unicodedata.normalize("NFKC", value).replace("\u200b", "").strip()


def _hash_json(value: Any) -> str:
    raw = json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _base_language(value: Any, default: str = "en") -> str:
    text = str(value or "").strip().lower()
    if not text or text == "auto":
        return default
    return text.split("-")[0]


def _speech_locale(language: str) -> str:
    return SPEECH_LOCALES.get(_base_language(language), "en-US")


def _system_speech_language(default: str = "en") -> str:
    """Apple Speech needs a locale; use the Mac language when nothing is known."""
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            code = locale.getdefaultlocale()[0]
    except Exception:
        code = ""
    return _base_language(code, default)


# ---------------------------------------------------------------- whisper models


def normalize_whisper_model(model: str | None) -> str:
    value = str(model or "").strip()
    if not value:
        return DEFAULT_WHISPER_MODEL
    return LEGACY_WHISPER_MODELS.get(value, value)


def whisper_models() -> list[dict]:
    """Model rows for Setup, with the turbo pack as the default."""
    configured = (
        os.environ.get("VIBECUT_WHISPER_MODEL")
        or (settings_store.load_settings().get("stt") or {}).get("model")
        or DEFAULT_WHISPER_MODEL
    )
    current = normalize_whisper_model(configured)
    pack_ready = False
    data_root = os.environ.get("DUCK_DATA_ROOT")
    if data_root:
        pack_ready = model_packs.installed_path(
            Path(data_root), "speech-whisper",
        ) is not None
    rows = []
    for item in WHISPER_MODELS:
        cached = pack_ready and item["id"] == DEFAULT_WHISPER_MODEL
        rows.append({**item, "cached": cached, "current": item["id"] == current})
    return rows


class SttCancelled(RuntimeError):
    """The read was cancelled while a speech engine was running."""


_CANCEL = threading.local()


def set_cancel_event(event: threading.Event | None) -> None:
    """Bind a cancel event to this thread's speech-to-text children.

    Analysis runs one job per worker thread, so a thread-local is enough to
    let "Cancel reading" stop a Whisper child that is mid-file instead of
    waiting for it to return to a progress checkpoint.
    """
    _CANCEL.event = event


def cancel_event() -> threading.Event | None:
    return getattr(_CANCEL, "event", None)


def has_cancel_event() -> bool:
    return cancel_event() is not None


def cancel_requested() -> bool:
    event = cancel_event()
    return bool(event is not None and event.is_set())


def _child_run(
    cmd: list[str], *, stdout, stderr, timeout: float, env=None,
    tick: Callable[[float], None] | None = None,
    tick_interval: float = 2.5,
):
    """``subprocess.run`` that also stops when the thread's cancel event fires.

    ``tick`` runs at most every ``tick_interval`` seconds with the elapsed
    child time, so a long Whisper or Apple read can show a heartbeat instead of
    one frozen line.
    """
    event = getattr(_CANCEL, "event", None)
    if event is None:
        return subprocess.run(cmd, stdout=stdout, stderr=stderr, timeout=timeout, env=env)
    process = subprocess.Popen(
        cmd, stdout=stdout, stderr=stderr, env=env, start_new_session=True,
    )
    deadline = time.monotonic() + float(timeout)
    started = time.monotonic()
    next_tick = started + max(0.1, float(tick_interval))
    try:
        while True:
            try:
                process.wait(timeout=0.25)
                return subprocess.CompletedProcess(cmd, process.returncode)
            except subprocess.TimeoutExpired:
                pass
            if event.is_set():
                raise SttCancelled("Speech-to-text cancelled.")
            now = time.monotonic()
            if tick is not None and now >= next_tick:
                next_tick = now + max(0.1, float(tick_interval))
                try:
                    tick(now - started)
                except Exception:  # noqa: BLE001 - a display tick never fails a read
                    pass
            if now >= deadline:
                raise subprocess.TimeoutExpired(cmd, timeout)
    finally:
        if process.poll() is None:
            try:
                os.killpg(os.getpgid(process.pid), 15)
            except (OSError, ProcessLookupError):
                try:
                    process.kill()
                except OSError:
                    pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except OSError:
                    pass


def _speech_root(job_dir: Path) -> Path:
    for directory in (job_dir, *job_dir.parents):
        if directory.name == "projects":
            return directory.parent
    return Path(os.environ.get("DUCK_DATA_ROOT", job_dir))


def _weights(root: Path) -> Path | None:
    selected = model_slots.selected(root, "transcription")
    if selected:
        return model_slots.speech_weights(selected)
    folder = model_packs.installed_path(root, "speech-whisper")
    return folder / model_packs.SPEECH_WEIGHTS if folder else None


def whisper_problem(root: Path) -> str:
    missing = []
    if not _whisper_binary(root):
        missing.append("speech helper")
    try:
        if not _weights(root):
            missing.append("speech weights")
    except (OSError, ValueError) as exc:
        return str(exc) if not missing else f"Missing speech helper. {exc}"
    return "Missing " + " and ".join(missing) + "." if missing else ""


WHISPER_TIMEOUT_MAX_S = 7200.0


def whisper_timeout(duration: float, timeout: float | None = None) -> float:
    """Whisper's time limit, relative to the audio length.

    A short clip never waits long (a 2 s silent clip used to hold the read for
    5 min). The route's ``timeout`` does not apply: its 300 s default suits a cloud
    call, but local Whisper runs near real time on a busy 8 GB Mac, so that limit
    killed every 10-minute chunk halfway through.
    """
    seconds = max(0.0, float(duration or 0.0))
    if seconds <= 0.0:
        return 30.0
    return min(WHISPER_TIMEOUT_MAX_S, 120.0 + seconds * 4.0)


# Speech gate: a window is voiced above this level, and a file needs this
# much voiced time before speech-to-text is worth running.
SPEECH_FLOOR_DBFS = -45.0
MIN_VOICED_SECONDS = 0.3


def has_speech_energy(path: Path, *, floor_dbfs: float = SPEECH_FLOOR_DBFS) -> bool | None:
    """Loudness gate before STT. False means silence; None means unreadable.

    It reads the raw (not loudness-normalised) 16-bit PCM in 30 ms windows
    and stops at the first ``MIN_VOICED_SECONDS`` of signal, so long files
    with speech return almost at once.
    """
    try:
        import numpy as np  # noqa: PLC0415 - keeps stt import light
    except Exception:  # noqa: BLE001
        return None
    try:
        with wave.open(str(path), "rb") as reader:
            if reader.getsampwidth() != 2:
                return None
            rate = reader.getframerate() or 16000
            channels = max(1, reader.getnchannels())
            window = max(1, int(rate * 0.03))
            need = max(1, int(math.ceil(MIN_VOICED_SECONDS / 0.03)))
            threshold = 32768.0 * (10.0 ** (floor_dbfs / 20.0))
            voiced = 0
            while True:
                raw = reader.readframes(window * 2000)
                if not raw:
                    return False
                samples = np.frombuffer(raw, dtype="<i2").astype(np.float64)
                if channels > 1:
                    samples = samples[: len(samples) // channels * channels]
                    samples = samples.reshape(-1, channels).mean(axis=1)
                usable = len(samples) // window * window
                if usable:
                    blocks = samples[:usable].reshape(-1, window)
                    rms = np.sqrt((blocks * blocks).mean(axis=1))
                    voiced += int((rms > threshold).sum())
                    if voiced >= need:
                        return True
    except (OSError, EOFError, wave.Error, ValueError):
        return None


def _whisper_binary(data_root: Path | None = None) -> str | None:
    forbidden = [Path(p).resolve() for p in (data_root, os.getenv("DUCK_DATA_ROOT"),
                                             os.getenv("DUCK_PACKS_ROOT")) if p]
    helpers = os.environ.get("DUCK_HELPER_DIR")
    frozen = getattr(sys, "frozen", False)
    if frozen:
        app = next((p for p in Path(sys.executable).resolve().parents if p.suffix == ".app"), None)
        if app is None:
            return None
        candidates = [app / path / "whisper-cli" for path in ("Contents/Helpers", "Contents/Resources/Helpers")]
    else:
        candidates = [Path(helpers or ROOT / "bin") / "whisper-cli"]
    if not helpers and not frozen:
        found = _which("whisper-cli")
        if found:
            candidates.append(Path(found))
    for candidate in candidates:
        if frozen and not candidate.resolve().is_relative_to(app):
            continue
        if any(candidate.absolute().is_relative_to(p) or candidate.resolve().is_relative_to(p)
               for p in forbidden):
            continue
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.resolve())
    return None


def _whisper_command() -> list[str] | None:
    binary = _whisper_binary()
    return [binary] if binary else None


def _whisper_args(binary, source, weights, output_prefix, language, vocabulary):
    language = _base_language(language) if language and language.lower() != "auto" else "auto"
    cmd = [binary, "-m", str(weights), "-f", str(source), "-l", language,
           "-ojf", "-of", str(output_prefix)]
    prompt = ", ".join(str(term).strip() for term in vocabulary or [] if str(term).strip())
    if prompt:
        cmd.extend(["--prompt", prompt[:800]])
    return cmd


def _apple_transcribe_helper() -> Path | None:
    """Compile tools/transcribe_apple.swift once, macOS 26 only."""
    if sys.platform != "darwin":
        return None
    source = TOOLS / "transcribe_apple.swift"
    binary = HELPERS / "transcribe_apple"
    if binary.is_file() and (
        not source.is_file() or binary.stat().st_mtime >= source.stat().st_mtime
    ):
        return binary
    swiftc = shutil.which("swiftc")
    if not swiftc or not source.is_file():
        return None
    binary.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [swiftc, "-O", "-parse-as-library", str(source), "-o", str(binary)],
            capture_output=True, text=True, timeout=600,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return binary if result.returncode == 0 and binary.is_file() else None


# ---------------------------------------------------------------- vocabulary


def vocabulary_terms(
    job_dir: Path | None = None,
    settings: Mapping[str, Any] | None = None,
) -> list[str]:
    """Collect per-job and global names/brands for contextual biasing."""
    raw_terms: list[Any] = []
    if settings is None:
        try:
            settings = settings_store.load_settings()
        except Exception:  # noqa: BLE001
            settings = {}
    stt_cfg = (settings or {}).get("stt") or {}
    if isinstance(stt_cfg, Mapping):
        raw_terms.extend(_vocabulary_values(stt_cfg.get("vocabulary")))
        raw_terms.extend(_vocabulary_values(stt_cfg.get("names")))
    if job_dir is not None:
        job_file = Path(job_dir) / "job.json"
        try:
            job = json.loads(job_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            job = {}
        if isinstance(job, Mapping):
            raw_terms.extend(_vocabulary_values(job.get("vocabulary")))
            raw_terms.extend(_vocabulary_values(job.get("stt_vocabulary")))
    result: list[str] = []
    seen: set[str] = set()
    for term in raw_terms:
        value = _clean_text(term)
        if not value:
            continue
        key = _word_key(value)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
        if len(result) >= 120:
            break
    return result


def _vocabulary_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part for part in re.split(r"[,;\n|]+", value) if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return []


def _word_key(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    text = re.sub(r"^[^\w\u3400-\u9fff]+|[^\w\u3400-\u9fff]+$", "", text)
    return text


def _replace_preserving_punctuation(original: str, replacement: str) -> str:
    match = re.match(r"^([^\w]*)(.*?)([^\w]*)$", original, re.UNICODE)
    if not match:
        return replacement
    return f"{match.group(1)}{replacement}{match.group(3)}"


def _correct_word(value: str, canonical: Mapping[str, str]) -> str:
    corrected = vision.correct_ocr_text(value)
    key = _word_key(corrected)
    if not key:
        return corrected
    if key in canonical:
        return _replace_preserving_punctuation(corrected, canonical[key])
    if len(key) >= 4:
        best = ""
        best_ratio = 0.0
        for candidate_key, candidate in canonical.items():
            if abs(len(candidate_key) - len(key)) > 2:
                continue
            ratio = difflib.SequenceMatcher(None, key, candidate_key).ratio()
            if ratio > best_ratio:
                best, best_ratio = candidate, ratio
        if best and best_ratio >= 0.86:
            return _replace_preserving_punctuation(corrected, best)
    return corrected


def apply_vocabulary(
    words: list[dict],
    segments: list[dict],
    terms: Iterable[str],
) -> tuple[list[dict], list[dict]]:
    """Correct engine output against the job/global vocabulary list."""
    canonical: dict[str, str] = {}
    for term in terms or []:
        key = _word_key(term)
        if key:
            canonical[key] = _clean_text(term)
    if not canonical:
        return words, segments
    for word in words:
        word["w"] = _correct_word(str(word.get("w") or ""), canonical)
    by_segment: dict[int, list[dict]] = {}
    for word in words:
        index = int(word.get("segment") or 0)
        by_segment.setdefault(index, []).append(word)
    for segments_index, segment in enumerate(segments):
        rows = by_segment.get(segments_index)
        if rows:
            segment["text"] = _join_words([str(row.get("w") or "") for row in rows])
        else:
            segment["text"] = _correct_segment_text(
                str(segment.get("text") or ""), canonical,
            )
    return words, segments


def _correct_segment_text(text: str, canonical: Mapping[str, str]) -> str:
    corrected = vision.correct_ocr_text(text)
    if not corrected:
        return corrected
    parts = corrected.split()
    return " ".join(_correct_word(part, canonical) for part in parts)


def _join_words(words: Iterable[str]) -> str:
    values = [value for value in words if value]
    if not values:
        return ""
    cjk = re.compile(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]")
    if all(cjk.search(value) for value in values):
        return "".join(values)
    return " ".join(values)


# ---------------------------------------------------------------- normalisation


def _normalize_word(raw: Any, *, speaker: str | None = None) -> dict | None:
    if not isinstance(raw, Mapping):
        return None
    text = _clean_text(raw.get("w") or raw.get("word") or raw.get("text"))
    if not text:
        return None
    start = _float(raw.get("start"), -1.0)
    end = _float(raw.get("end"), start)
    if start < 0:
        return None
    if end <= start:
        end = start + 0.04
    value: dict[str, Any] = {
        "w": text,
        "start": round(start, 3),
        "end": round(end, 3),
        "confidence": _confidence(
            raw.get("confidence", raw.get("probability")), 0.5,
        ),
        "segment": int(raw.get("segment") or 0),
    }
    label = speaker or raw.get("speaker")
    if label not in (None, ""):
        value["speaker"] = str(label)
    return value


def _normalize_segment(raw: Any, index: int) -> dict | None:
    if not isinstance(raw, Mapping):
        return None
    text = _clean_text(raw.get("text"))
    if not text:
        return None
    start = _float(raw.get("start"), -1.0)
    end = _float(raw.get("end"), start)
    if start < 0:
        return None
    if end <= start:
        end = start + 0.2
    value: dict[str, Any] = {
        "start": round(start, 3),
        "end": round(end, 3),
        "text": text,
        "confidence": _confidence(raw.get("confidence"), 0.5),
    }
    speaker = raw.get("speaker")
    if speaker not in (None, ""):
        value["speaker"] = str(speaker)
    return value


def _shift_rows(
    segments: list[dict], words: list[dict], offset: float,
) -> tuple[list[dict], list[dict]]:
    if not offset:
        return segments, words
    shifted_segments = [
        {**item, "start": round(item["start"] + offset, 3),
         "end": round(item["end"] + offset, 3)}
        for item in segments
    ]
    shifted_words = [
        {**item, "start": round(item["start"] + offset, 3),
         "end": round(item["end"] + offset, 3)}
        for item in words
    ]
    return shifted_segments, shifted_words


# ---------------------------------------------------------------- chunking


def chunk_ranges(
    duration: float,
    chunk_seconds: float = CHUNK_SECONDS,
    overlap: float = OVERLAP_SECONDS,
) -> list[dict]:
    """10 minute chunks with a 5 s overlap, rounded to milliseconds."""
    total = max(0.0, _float(duration))
    if total <= 0:
        return []
    span = max(1.0, float(chunk_seconds))
    overlap = max(0.0, min(float(overlap), span - 0.001))
    ranges: list[dict] = []
    start = 0.0
    guard = 0
    while start < total - 1e-6 and guard < 10000:
        guard += 1
        end = min(total, start + span)
        ranges.append({
            "index": len(ranges),
            "start": round(start, 3),
            "end": round(end, 3),
        })
        if end >= total - 1e-6:
            break
        start = max(start + 0.001, end - overlap)
    return ranges


def chunk_cache_key(
    audio_hash: str, engine: str, model: str, index: int,
) -> str:
    """Cache identity required by G3: audio hash, engine, model, chunk index."""
    raw = f"{audio_hash}:{str(engine).lower()}:{model}:{int(index)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _chunk_cache_path(job_dir: Path, key: str) -> Path:
    return Path(job_dir) / "transcript" / "chunks" / f"{key}.json"


def prepare_audio(
    wav_path: Path, job_dir: Path, *, source_hash: str = "",
) -> tuple[Path, str]:
    """16 kHz mono, loudness-normalised audio cached by content hash."""
    source = Path(wav_path)
    digest = source_hash or _sha256_file(source)
    out_dir = Path(job_dir) / "transcript" / "audio"
    out = out_dir / f"{digest[:16]}_16k.wav"
    if out.is_file() and out.stat().st_size > 44:
        return out, digest
    try:
        ffmpeg = _ffmpeg()
    except SttError:
        return source, digest
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        _run([
            ffmpeg, "-y", "-v", "error", "-i", str(source),
            "-ac", "1", "-ar", "16000",
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:a", "pcm_s16le", str(out),
        ], timeout=1800)
    except (OSError, SttError, subprocess.SubprocessError):
        return source, digest
    return (out if out.is_file() and out.stat().st_size > 44 else source), digest


def _extract_chunk(audio_path: Path, start: float, end: float, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    _run([
        _ffmpeg(), "-y", "-v", "error",
        "-ss", f"{max(0.0, float(start)):.3f}",
        "-t", f"{max(0.05, float(end) - float(start)):.3f}",
        "-i", str(audio_path), "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le", str(out),
    ], timeout=900)
    return out


# ---------------------------------------------------------------- payload parsing


def _apple_payload(data: Mapping[str, Any]) -> dict:
    """Normalise the Swift helper payload, including per-run word ranges."""
    segments: list[dict] = []
    words: list[dict] = []
    raw_segments = data.get("segments") if isinstance(data, Mapping) else None
    for index, item in enumerate(raw_segments or []):
        if not isinstance(item, Mapping):
            continue
        segment = _normalize_segment(item, index)
        if segment is None:
            continue
        transcript_index = len(segments)
        segment_words = []
        for raw_word in item.get("words") or []:
            word = _normalize_word(raw_word)
            if word is not None:
                word["segment"] = transcript_index
                segment_words.append(word)
        if segment_words:
            segment["confidence"] = round(
                sum(word["confidence"] for word in segment_words) / len(segment_words), 4,
            )
        segments.append(segment)
        words.extend(segment_words)
    if not words:
        for raw_word in data.get("words") or []:
            word = _normalize_word(raw_word)
            if word is None:
                continue
            word["segment"] = _segment_index_for_time(segments, word["start"])
            words.append(word)
    if not segments and words:
        segments = _segments_from_words(words)
        for word in words:
            word["segment"] = _segment_index_for_time(segments, word["start"])
    language = _clean_text(data.get("language")) or "en"
    return {
        "language": _base_language(language),
        "text": _clean_text(data.get("text")) or _join_words(
            [word["w"] for word in words],
        ),
        "segments": segments,
        "words": words,
    }


# Whole-segment lines Whisper writes over music or silence. A segment is
# dropped only when its entire text is one of these; "thank you" also has to
# repeat in the same response, since a single one may be real speech.
_HALLUCINATED_LINES = frozenset({
    "thanks for watching", "thank you for watching", "please subscribe",
    "subscribe to my channel", "like and subscribe",
    "subtitles by the amaraorg community",
    "cảm ơn các bạn đã theo dõi", "cảm ơn các bạn đã xem video",
    "hẹn gặp lại các bạn trong những video tiếp theo",
    "hãy subscribe cho kênh để ủng hộ kênh của mình nhé",
    "hãy đăng ký kênh để ủng hộ kênh của mình nhé",
    "ghiền mì gõ", "la la school",
    "字幕由amaraorg社区提供", "请不吝点赞 订阅 转发 打赏支持明镜与点点栏目",
})
#: Short lines that are real speech once but Whisper's filler when repeated
#: over silence. Dropped only from the third time on, and never when the
#: segment's own scores say it is confident speech.
_REPEATED_ONLY_LINES = frozenset({
    "thank you", "thanks", "cảm ơn", "okay", "you", "bye", "bye bye", "ta-da",
})
_REPEATED_ONLY_MIN = 3
# A made-up loop is local. Measured on the review project: copies at 90.0, 91.86
# and 94.7 s, gaps of 0 and 1.74 s, one copy 23.36 s for ten words.
_REPEAT_GAP = 2.0
_REPEAT_SLOW_SECONDS = 8.0
_REPEAT_SLOW_PER_WORD = 1.2


def _slow_copy(segment: Mapping[str, Any] | None) -> bool:
    """One copy that takes far longer than its words can say."""
    if not segment:
        return False
    seconds = max(0.0, _float(segment.get("end")) - _float(segment.get("start")))
    words = len(_clean_text(segment.get("text")).split())
    return seconds >= _REPEAT_SLOW_SECONDS and seconds / max(1, words) >= _REPEAT_SLOW_PER_WORD


def _line_key(text: str) -> str:
    stripped = re.sub(r"[.,!?。！？…'\"“”‘’]", "", str(text or "").casefold())
    return " ".join(stripped.split())


def _confident_speech(segment: Mapping[str, Any] | None) -> bool:
    """True when Whisper's own scores say this segment is real speech."""
    if not segment or segment.get("no_speech_prob") is None or segment.get("avg_logprob") is None:
        return False
    return _float(segment.get("no_speech_prob")) < 0.3 and _float(segment.get("avg_logprob")) > -0.6


def _hallucinated(
    text: str,
    counts: Mapping[str, int],
    segment: Mapping[str, Any] | None = None,
) -> bool:
    key = _line_key(text)
    if key in _HALLUCINATED_LINES:
        return True
    if key not in _REPEATED_ONLY_LINES or _confident_speech(segment):
        return False
    return counts.get(key, 0) >= _REPEATED_ONLY_MIN


def _cpp_payload(data: Mapping[str, Any]) -> dict:
    segments = []
    for row in data.get("transcription", []):
        bounds = row["offsets"]
        words = []
        scores = []
        for token in row.get("tokens", []):
            piece = token["text"]
            if not piece.strip() or (piece.startswith("[_") and piece.endswith("]")):
                continue
            timing = token.get("offsets") or {}
            # Scripts without spaces retain timed token boundaries. Byte fragments
            # stay with the preceding token until they form a complete character.
            begins = piece[0].isspace() or not words or bool(re.match(r"[ぁ-ヿ㐀-鿿]", piece))
            if begins:
                words.append({"word": "", "start": timing.get("from", bounds["from"]) / 1000,
                              "end": timing.get("to", bounds["to"]) / 1000, "scores": []})
            word = words[-1]
            word["word"] += piece.strip()
            if "to" in timing:
                word["end"] = timing["to"] / 1000
            prob = _confidence(token.get("p"))
            word["scores"].append(prob)
            scores.append(math.log(max(prob, 1e-10)))
        for word in words:
            # UTF-8 BPE tokens can split a Vietnamese character across JSON strings.
            word["word"] = word["word"].encode("utf-8", "surrogateescape").decode("utf-8", "replace")
            probabilities = word.pop("scores")
            word["probability"] = sum(probabilities) / len(probabilities)
        segments.append({"text": row["text"], "start": bounds["from"] / 1000,
                         "end": bounds["to"] / 1000, "words": words,
                         "avg_logprob": sum(scores) / len(scores) if scores else 0})
    return _whisper_payload({"language": data["result"]["language"], "segments": segments})


def _whisper_payload(data: Mapping[str, Any]) -> dict:
    segments: list[dict] = []
    words: list[dict] = []
    raw_segments = [item for item in data.get("segments") or [] if isinstance(item, Mapping)]
    line_counts: dict[str, int] = {}
    keys: list[str] = []
    for item in raw_segments:
        key = _line_key(_clean_text(item.get("text")))
        keys.append(key)
        line_counts[key] = line_counts.get(key, 0) + 1
    # Whisper fills music or room noise with a line it knows, and the copies sit
    # together. Measured on the review project: 90.0, 91.86 and 94.7 s (gaps 0
    # and 1.74 s), one copy 23.36 s for ten words. A real repeat a minute later
    # is not a loop, so only one run of back-to-back copies is dropped.
    runs: list[list[int]] = []
    for index, key in enumerate(keys):
        if (
            runs
            and keys[runs[-1][-1]] == key
            and _float(raw_segments[index].get("start")) - _float(raw_segments[runs[-1][-1]].get("end")) <= _REPEAT_GAP
        ):
            runs[-1].append(index)
        else:
            runs.append([index])
    looped: set[int] = set()
    for run in runs:
        if len(run) < 2:
            continue
        if any(_slow_copy(raw_segments[index]) for index in run):
            looped.update(run)
    for index, raw_segment in enumerate(raw_segments):
        text = " ".join(_clean_text(raw_segment.get("text")).split())
        if not text:
            continue
        if index in looped:
            continue
        if _hallucinated(text, line_counts, raw_segment):
            continue
        compression = _float(raw_segment.get("compression_ratio"))
        no_speech = _float(raw_segment.get("no_speech_prob"))
        logprob = _float(raw_segment.get("avg_logprob"))
        if compression > 2.4 or no_speech > 0.82 or logprob < -1.2:
            continue
        tokens = text.split()
        if len(tokens) >= 8 and len(set(tokens)) / len(tokens) < 0.18:
            continue
        if len(text) > 60 and len(set(text)) < 7:
            continue
        index = len(segments)
        segment_words = []
        for raw_word in raw_segment.get("words") or []:
            word = _normalize_word(raw_word)
            if word is not None:
                word["segment"] = index
                segment_words.append(word)
        if not segment_words:
            for raw_word in data.get("words") or []:
                word = _normalize_word(raw_word)
                if word is None:
                    continue
                if float(raw_segment.get("start") or 0) - 0.05 <= word["start"] <= (
                    float(raw_segment.get("end") or 0) + 0.05
                ):
                    word["segment"] = index
                    segment_words.append(word)
        confidence = (
            sum(word["confidence"] for word in segment_words) / len(segment_words)
            if segment_words else 0.5
        )
        segments.append({
            "start": round(_float(raw_segment.get("start")), 3),
            "end": round(_float(raw_segment.get("end")), 3),
            "text": text,
            "confidence": round(confidence, 4),
        })
        words.extend(segment_words)
    if not segments:
        return {"language": "en", "text": "", "segments": [], "words": []}
    if not words:
        for raw_word in data.get("words") or []:
            word = _normalize_word(raw_word)
            if word is None:
                continue
            word["segment"] = _segment_index_for_time(segments, word["start"])
            words.append(word)
    return {
        "language": _base_language(data.get("language"), "en"),
        "text": _join_words(segment["text"] for segment in segments),
        "segments": segments,
        "words": words,
    }


def _segments_from_words(words: list[dict]) -> list[dict]:
    if not words:
        return []
    groups: list[list[dict]] = []
    current: list[dict] = []
    for word in sorted(words, key=lambda item: item["start"]):
        if current and float(word["start"]) - float(current[-1]["end"]) > 0.8:
            groups.append(current)
            current = []
        current.append(word)
    if current:
        groups.append(current)
    return [{
        "start": round(float(group[0]["start"]), 3),
        "end": round(float(group[-1]["end"]), 3),
        "text": _join_words(word["w"] for word in group),
        "confidence": round(
            sum(word["confidence"] for word in group) / len(group), 4,
        ),
    } for group in groups]


def _segment_index_for_time(segments: list[dict], when: float) -> int:
    if not segments:
        return 0
    for index, segment in enumerate(segments):
        if float(segment["start"]) - 0.001 <= when <= float(segment["end"]) + 0.001:
            return index
    previous = 0
    for index, segment in enumerate(segments):
        if float(segment["start"]) <= when:
            previous = index
    return previous


# ---------------------------------------------------------------- quality


def _coverage(intervals: Iterable[tuple[float, float]], duration: float) -> float:
    if duration <= 0:
        return 0.0
    ordered = sorted(
        (max(0.0, float(start)), min(duration, float(end)))
        for start, end in intervals
        if float(end) > float(start)
    )
    total = 0.0
    cursor = 0.0
    for start, end in ordered:
        start = max(start, cursor)
        if end <= start:
            continue
        total += end - start
        cursor = end
    return round(min(1.0, total / duration), 4)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))
    return round(ordered[index], 1)


# ---------------------------------------------------------------- transcript v2


def build_transcript(
    *,
    engine: str,
    model: str,
    language: str,
    segments: list[dict],
    words: list[dict],
    audio_duration: float,
    source_hash: str,
    drift_ms_p95: float = 0.0,
    created: float | None = None,
) -> dict:
    """Build one immutable Transcript v2 document (ROADMAP.md, Transcript v2)."""
    clean_segments: list[dict] = []
    for index, item in enumerate(segments):
        segment = _normalize_segment(item, index)
        if segment is None:
            continue
        clean_segments.append(segment)
    clean_words: list[dict] = []
    for raw in words:
        word = _normalize_word(raw)
        if word is None:
            continue
        if audio_duration > 0:
            word["start"] = round(min(max(0.0, word["start"]), audio_duration), 3)
            word["end"] = round(min(max(word["start"] + 0.001, word["end"]), audio_duration), 3)
        if word["end"] <= word["start"]:
            continue
        word["segment"] = _segment_index_for_time(clean_segments, word["start"])
        clean_words.append(word)
    clean_words.sort(key=lambda item: (item["start"], item["end"]))
    for index, word in enumerate(clean_words):
        word["segment"] = min(max(0, word["segment"]), max(0, len(clean_segments) - 1))
    if not clean_segments and clean_words:
        clean_segments = _segments_from_words(clean_words)
        for word in clean_words:
            word["segment"] = _segment_index_for_time(clean_segments, word["start"])
    if clean_segments:
        for index, segment in enumerate(clean_segments):
            rows = [word for word in clean_words if word["segment"] == index]
            if rows:
                segment["confidence"] = round(
                    sum(word["confidence"] for word in rows) / len(rows), 4,
                )
    confidences = [word["confidence"] for word in clean_words] or [
        segment["confidence"] for segment in clean_segments
    ]
    mean_confidence = round(sum(confidences) / len(confidences), 4) if confidences else 0.0
    coverage_intervals = (
        [(word["start"], word["end"]) for word in clean_words]
        if clean_words
        else [(segment["start"], segment["end"]) for segment in clean_segments]
    )
    payload = {
        "schema": SCHEMA_VERSION,
        "source_hash": str(source_hash or ""),
        "engine": str(engine or ""),
        "model": str(model or ""),
        "language": _base_language(language, "en"),
        "segments": clean_segments,
        "words": clean_words,
        "quality": {
            "coverage": _coverage(coverage_intervals, float(audio_duration or 0.0)),
            "mean_confidence": mean_confidence,
            "low_conf_words": sum(
                1 for word in clean_words if float(word["confidence"]) < LOW_CONFIDENCE
            ),
            "drift_ms_p95": round(max(0.0, float(drift_ms_p95 or 0.0)), 1),
        },
    }
    digest = _hash_json(payload)
    stamp = round(float(created if created is not None else time.time()), 3)
    transcript_id = f"tr_{int(stamp * 1000)}_{uuid.uuid4().hex[:8]}"
    return {
        "id": transcript_id,
        **payload,
        "created": stamp,
        "hash": digest,
        "text": _join_words(segment["text"] for segment in clean_segments),
    }


def transcript_paths(job_dir: Path) -> list[Path]:
    directory = Path(job_dir) / "transcript"
    if not directory.is_dir():
        return []
    return sorted(
        path for path in directory.glob("transcript_v2*.json")
        if path.is_file() and not path.name.startswith(".")
    )


def load_latest_transcript(job_dir: Path) -> dict | None:
    """Newest immutable v2 transcript for a job, or ``None``."""
    best: dict | None = None
    for path in transcript_paths(job_dir):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(value, dict) or not value.get("id"):
            continue
        if best is None or (
            float(value.get("created") or 0.0), str(value.get("id") or "")
        ) > (
            float(best.get("created") or 0.0), str(best.get("id") or "")
        ):
            best = value
    return best


def save_transcript(job_dir: Path, transcript: dict) -> Path:
    """Persist a v2 transcript.  Canonical files are never overwritten."""
    directory = Path(job_dir) / "transcript"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"transcript_v2_{transcript['id']}.json"
    if not path.is_file():
        _atomic_write(path, transcript)
    # Legacy mirror: the existing transcript endpoint and older readers only
    # know transcript.json.  The canonical, immutable record is the v2 file.
    _atomic_write(directory / "transcript.json", {
        **transcript,
        "provider": transcript.get("engine"),
    })
    return path


# ---------------------------------------------------------------- engines


def transcribe_apple(
    wav_path: Path | None,
    job_dir: Path,
    language: str = "en",
    timeout: float | None = None,
    *,
    helper: Any = _UNSET,
    vocabulary: Iterable[str] | None = None,
    progress: Callable[[float, str], None] | None = None,
) -> dict | None:
    """Transcribe one file with Apple SpeechAnalyzer (single file, no chunking)."""
    source = Path(wav_path) if wav_path else None
    if not source or not source.exists():
        return None
    chosen_helper = (
        _apple_transcribe_helper() if helper is _UNSET else helper
    )
    if not chosen_helper:
        return None
    out_dir = Path(job_dir) / "transcript"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "transcript_apple.json"
    try:
        out_path.unlink()
    except OSError:
        pass
    cmd = [
        str(chosen_helper),
        "--audio", str(source),
        "--locale", _speech_locale(language),
        "--out", str(out_path),
    ]
    terms = [str(term) for term in (vocabulary or []) if str(term).strip()]
    if terms:
        cmd.extend(["--vocabulary", json.dumps(terms, ensure_ascii=False)])

    def heartbeat(elapsed: float) -> None:
        if progress is not None:
            progress(
                0.5,
                f"Transcribing speech · Apple speech · {max(1, int(elapsed))} s",
            )

    try:
        if has_cancel_event():
            # Only the return code and the output file are read; unread
            # pipes could fill and stall the helper until the timeout.
            result = _child_run(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=max(10.0, float(timeout or 3600)),
                tick=heartbeat,
            )
        else:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=max(10.0, float(timeout or 3600)),
            )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0 or not out_path.is_file():
        return None
    try:
        data = json.loads(out_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    payload = _apple_payload(data)
    if not payload["segments"]:
        return None
    return {
        "language": payload["language"],
        "text": payload["text"][:4000],
        "segments": payload["segments"],
        "words": payload["words"],
        "provider": "apple",
        "model": "on-device-3b",
    }


def transcribe(
    wav_path: Path | None,
    job_dir: Path,
    duration: float,
    progress: Callable[[float, str], None],
    *,
    model: str | None = None,
    timeout: float | None = None,
    language: str = "",
    vocabulary: Iterable[str] | None = None,
) -> dict | None:
    """Transcribe one file with local Whisper (single file, no chunking)."""
    source = Path(wav_path) if wav_path else None
    if not source or not source.exists():
        return None
    root = _speech_root(Path(job_dir))
    binary = _whisper_binary(root)
    # The chunk dispatcher pins one weights path for the entire read.
    chosen_model = Path(model) if model and Path(model).is_absolute() else _weights(root)
    if not binary or chosen_model is None or not chosen_model.is_file():
        return None
    model_name = normalize_whisper_model(model)
    out_dir = Path(job_dir) / "transcript"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "whisper.log"
    json_path = out_dir / "transcript.json"
    json_path.unlink(missing_ok=True)
    cmd = _whisper_args(binary, source, chosen_model, json_path.with_suffix(""), language, vocabulary)
    progress(0.08, "Transcribing speech · local Whisper")
    budget = whisper_timeout(duration, timeout)

    def heartbeat(elapsed: float) -> None:
        # Time-based only: Whisper gives no per-token progress, so the line
        # must move on elapsed time and stay short of the stage end.
        share = min(0.72, 0.70 * (float(elapsed) / max(1.0, budget)))
        progress(
            min(0.78, 0.08 + share),
            f"Transcribing speech · local Whisper · {max(1, int(elapsed))} s",
        )

    with log_path.open("w") as log:
        try:
            result = _child_run(
                cmd, stdout=log, stderr=log,
                timeout=budget,
                tick=heartbeat,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Whisper ran out of time after {int(budget)} s on {int(duration)} s of audio."
            ) from exc
        except (OSError, subprocess.SubprocessError):
            return None
    if result.returncode != 0:
        return None
    if not json_path.exists():
        return None
    progress(0.82, "Reading transcript")
    try:
        data = json.loads(json_path.read_text(encoding="utf-8", errors="surrogateescape"), strict=False)
    except (OSError, json.JSONDecodeError):
        return None
    payload = _cpp_payload(data)
    if not payload["segments"]:
        return None
    return {
        "language": payload["language"],
        "text": payload["text"][:4000],
        "segments": payload["segments"],
        "words": payload["words"],
        "provider": "whisper",
        "model": model_name,
        "model_path": str(chosen_model),
    }


# ---------------------------------------------------------------- routes


def normalize_engine(provider: str, model: str = "") -> dict | None:
    name = str(provider or "").strip().lower()
    raw_model = str(model or "").strip()
    if name in {"", "auto", "local", "whisper"}:
        return {"provider": "whisper", "model": normalize_whisper_model(raw_model)}
    if name == "apple":
        return {"provider": "apple", "model": raw_model or "on-device-3b"}
    # Every other name, including a saved cloud route, is not an engine:
    # speech never leaves the Mac.
    return None


def resolve_routes(
    routes: Iterable[Mapping[str, Any]] | None = None,
    *,
    engine: str = "",
    model: str = "",
) -> list[dict]:
    """Turn configured routes into the final explicit engine list.

    ``auto``/``local``/``whisper`` are local Whisper aliases.  Every other name,
    including a saved cloud route, is dropped; the result is always Apple or
    Whisper from :data:`DEFAULT_ROUTES`.
    """
    requested = str(engine or "").strip().lower()
    if requested and requested != "auto":
        chosen = normalize_engine(requested, model)
        if chosen:
            return [chosen]
        # Removed/unknown explicit engine: fall through to the configured local
        # routes instead of failing transcription outright.
    resolved: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for route in routes or []:
        if not isinstance(route, Mapping):
            continue
        chosen = normalize_engine(
            str(route.get("provider") or ""), str(route.get("model") or ""),
        )
        if not chosen:
            continue
        key = (chosen["provider"], chosen["model"])
        if key in seen:
            continue
        seen.add(key)
        resolved.append(chosen)
    if not resolved:
        resolved = [dict(route) for route in DEFAULT_ROUTES]
    return resolved


def _engine_ready(provider: str, model: str) -> bool:
    if provider == "apple":
        return _apple_transcribe_helper() is not None
    if provider == "whisper":
        return _whisper_command() is not None
    return False


# ---------------------------------------------------------------- chunked runs


def _run_engine_chunk_keyed(
    prepared: Path, job_dir: Path, chunk: dict, *, key: str,
    engine: str, model: str, language: str,
    vocabulary: Iterable[str] | None, timeout: float | None,
    helper: Any = _UNSET,
    progress: Callable[[float, str], None] | None = None,
) -> dict | None:
    work = Path(job_dir) / "transcript" / "chunks" / "work" / key
    work.mkdir(parents=True, exist_ok=True)
    chunk_wav = work / "chunk.wav"
    _extract_chunk(prepared, float(chunk["start"]), float(chunk["end"]), chunk_wav)
    offset = float(chunk["start"])
    if engine == "apple":
        raw = transcribe_apple(
            chunk_wav, work, language, timeout=timeout,
            helper=_apple_transcribe_helper() if helper is _UNSET else helper,
            vocabulary=vocabulary,
            progress=progress,
        )
    elif engine == "whisper":
        raw = transcribe(
            chunk_wav, work, float(chunk["end"]) - float(chunk["start"]),
            (
                (lambda fraction, message: progress(fraction, message))
                if progress is not None else (lambda _fraction, _message: None)
            ),
            model=model, timeout=timeout, language=language,
            vocabulary=vocabulary,
        )
    else:
        # Only Apple and Whisper exist; an unknown engine name returns nothing
        # rather than reaching a service.
        return None
    if not raw:
        return None
    segments, words = _shift_rows(
        list(raw.get("segments") or []), list(raw.get("words") or []), offset,
    )
    return {
        "index": int(chunk["index"]),
        "start": float(chunk["start"]),
        "end": float(chunk["end"]),
        "language": raw.get("language") or language,
        "segments": segments,
        "words": words,
    }


def _merge_chunks(chunks: list[dict], duration: float) -> dict:
    """Merge chunks in order, de-duplicating the 5 s overlaps by time."""
    ordered = sorted(chunks, key=lambda item: int(item["index"]))
    words: list[dict] = []
    drifts: list[float] = []
    for chunk in ordered:
        chunk_index = int(chunk["index"])
        overlap_limit = float(chunk["start"]) + OVERLAP_SECONDS + 0.5
        for raw in chunk.get("words") or []:
            word = _normalize_word(raw)
            if word is None:
                continue
            duplicate = None
            if chunk_index == 0 or word["start"] <= overlap_limit:
                for existing in reversed(words[-60:]):
                    if abs(float(existing["start"]) - word["start"]) <= 0.6 and (
                        _word_key(existing["w"]) == _word_key(word["w"])
                    ):
                        duplicate = existing
                        break
            if duplicate is not None:
                drifts.append(abs(float(duplicate["start"]) - word["start"]) * 1000.0)
                duplicate["start"] = round(
                    min(float(duplicate["start"]), word["start"]), 3,
                )
                duplicate["end"] = round(
                    max(float(duplicate["end"]), word["end"]), 3,
                )
                duplicate["confidence"] = max(
                    float(duplicate["confidence"]), float(word["confidence"]),
                )
                continue
            words.append(word)
    words.sort(key=lambda item: (item["start"], item["end"]))

    segments: list[dict] = []
    for chunk in ordered:
        for raw in chunk.get("segments") or []:
            segment = _normalize_segment(raw, len(segments))
            if segment is None:
                continue
            duplicate = None
            for existing in reversed(segments[-8:]):
                if abs(float(existing["start"]) - segment["start"]) <= 0.75 and (
                    _word_key(existing["text"]) == _word_key(segment["text"])
                ):
                    duplicate = existing
                    break
            if duplicate is not None:
                duplicate["end"] = round(
                    max(float(duplicate["end"]), segment["end"]), 3,
                )
                continue
            segments.append(segment)

    limit = max(0.0, float(duration or 0.0))
    cleaned_words: list[dict] = []
    for word in words:
        start = max(0.0, float(word["start"]))
        end = max(start + 0.001, float(word["end"]))
        if limit:
            start = min(start, limit)
            end = min(end, limit)
        if end <= start:
            continue
        word["start"] = round(start, 3)
        word["end"] = round(end, 3)
        cleaned_words.append(word)
    cleaned_segments: list[dict] = []
    for segment in segments:
        start = max(0.0, float(segment["start"]))
        end = max(start + 0.001, float(segment["end"]))
        if limit:
            start = min(start, limit)
            end = min(end, limit)
        if end <= start:
            continue
        segment["start"] = round(start, 3)
        segment["end"] = round(end, 3)
        cleaned_segments.append(segment)
    if not cleaned_segments and cleaned_words:
        cleaned_segments = _segments_from_words(cleaned_words)
    for word in cleaned_words:
        word["segment"] = _segment_index_for_time(cleaned_segments, word["start"])
    language = next(
        (str(chunk.get("language")) for chunk in ordered if chunk.get("language")),
        "en",
    )
    return {
        "language": _base_language(language, "en"),
        "segments": cleaned_segments,
        "words": cleaned_words,
        "drift_ms_p95": _p95(drifts),
    }


def _accepts_progress_kw(function: Callable[..., Any]) -> bool:
    try:
        parameters = inspect.signature(function).parameters
    except (TypeError, ValueError):
        return True
    return "progress" in parameters or any(
        item.kind is inspect.Parameter.VAR_KEYWORD
        for item in parameters.values()
    )


def _chunked_run(
    prepared: Path,
    job_dir: Path,
    duration: float,
    *,
    audio_hash: str,
    engine: str,
    model: str,
    language: str,
    vocabulary: Iterable[str] | None,
    timeout: float | None,
    progress: Callable[[float, str], None] | None,
    helper: Any = _UNSET,
) -> dict | None:
    ranges = chunk_ranges(duration)
    if not ranges:
        return None
    results: list[dict] = []
    cache_model = model
    if engine == "whisper":
        vocabulary = tuple(vocabulary or ())
        cache_model = _hash_json(["whisper.cpp-v1.8.2", model, language, vocabulary])
    for chunk in ranges:
        key = chunk_cache_key(audio_hash, engine, cache_model, int(chunk["index"]))
        cache_path = _chunk_cache_path(job_dir, key)
        record = None
        if cache_path.is_file():
            try:
                record = json.loads(cache_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                record = None
        if not isinstance(record, dict) or record.get("key") != key:
            chunk_kwargs = {
                "key": key,
                "engine": engine,
                "model": model,
                "language": language,
                "vocabulary": vocabulary,
                "timeout": timeout,
                "helper": helper,
            }
            if _accepts_progress_kw(_run_engine_chunk_keyed):
                chunk_kwargs["progress"] = progress
            record = _run_engine_chunk_keyed(
                prepared, job_dir, chunk, **chunk_kwargs,
            )
            if record is None:
                return None
            record["key"] = key
            _atomic_write(cache_path, record)
        results.append(record)
        if progress is not None:
            fraction = 0.10 + 0.80 * (len(results) / max(1, len(ranges)))
            progress(
                fraction,
                f"Transcribing speech · {engine} · chunk {len(results)}/{len(ranges)}",
            )
    return _merge_chunks(results, duration)


def _log_route(
    logger: Callable[..., None] | None,
    route_index: int,
    provider: str,
    model: str,
    started: float,
    ok: bool,
    error: str,
    *,
    job_id: str = "",
    request_id: str = "",
) -> None:
    if logger is not None:
        logger(
            "stt", route_index, provider, model, started, ok, error,
            job_id=job_id, request_id=request_id,
        )
        return
    try:
        from admin import store  # noqa: PLC0415

        store.record_pipeline_event(
            "stt", provider, model,
            route_index=route_index,
            job_id=job_id,
            request_id=request_id or job_id,
            status="ok" if ok else "failed",
            latency_ms=(time.time() - started) * 1000,
            fallback=route_index > 0,
            error=error,
        )
    except Exception:  # noqa: BLE001
        pass


ENGINE_LABELS = {
    "apple": "Apple speech",
    "whisper": "local Whisper",
}


_VI_LETTERS = re.compile(
    r"[ăắằẳẵặâấầẩẫậđêếềểễệôốồổỗộơớờởỡợưứừửữựạảãẹẻẽịỉĩọỏõụủũỵỷỹ]",
    re.IGNORECASE,
)


def guess_language(*texts: str) -> str:
    """A base language code from a title's script, or "" when unclear.

    Used before transcription so a Vietnamese or Japanese video is not read
    as English just because the Setup default is "en". Latin titles without
    Vietnamese letters stay "" (the configured language applies).
    """
    text = " ".join(str(item or "") for item in texts)
    if not text.strip():
        return ""
    # A file name often carries the language before the first dash:
    # cn-1min29s..., vi-episode-12..., en-17mins... . Only trust a known
    # two-letter prefix at the start of a name or path segment.
    prefix = re.search(
        r"(?:^|/)(cn|zh|vi|ja|ko|en|es|fr|de|pt|it|hi|ar|th|ru)[-_]",
        text.lower(),
    )
    if prefix:
        return "zh" if prefix.group(1) == "cn" else prefix.group(1)
    if re.search(r"[\u3040-\u30ff]", text):
        return "ja"
    if len(re.findall(r"[\uac00-\ud7af]", text)) >= 2:
        return "ko"
    if len(re.findall(r"[\u3400-\u9fff]", text)) >= 2:
        return "zh"
    if len(re.findall(r"[\u0e00-\u0e7f]", text)) >= 2:
        return "th"
    if len(re.findall(r"[\u0400-\u04ff]", text)) >= 3:
        return "ru"
    if len(_VI_LETTERS.findall(text)) >= 2:
        return "vi"
    return ""


def no_speech_transcript(language: str = "") -> dict:
    """What a read returns when the loudness gate finds no speech.

    Not persisted: there is nothing to cache, and a later read with speech
    must not be shadowed. ``no_speech`` lets callers say "No speech found"
    instead of "transcription did not run".
    """
    return {
        "language": _base_language(language, ""),
        "text": "",
        "segments": [],
        "words": [],
        "provider": "none",
        "no_speech": True,
    }


from duckcore.providers import local_step


@local_step('transcription')
def transcribe_source(
    wav_path: Path | None,
    job_dir: Path,
    duration: float,
    progress: Callable[[float, str], None] | None = None,
    *,
    engine: str = "",
    model: str = "",
    routes: Iterable[Mapping[str, Any]] | None = None,
    language: str = "",
    vocabulary: Iterable[str] | None = None,
    source_hash: str = "",
    timeout: float | None = None,
    job_id: str = "",
    request_id: str = "",
    logger: Callable[..., None] | None = None,
    helper: Any = _UNSET,
    prepared: Path | None = None,
    audio_hash: str = "",
    errors: list[dict] | None = None,
) -> dict | None:
    """Chunk, transcribe, merge and persist one Transcript v2 for a job.

    An empty ``language`` means auto: Whisper detects the language and
    reports what it detected.  Apple Speech cannot detect a language, so it is
    skipped unless the caller selected it explicitly or supplied a language;
    otherwise a Chinese source would be forced through an English locale and
    return nothing.
    """
    requested_language = str(language or "").strip().lower()
    root = _speech_root(Path(job_dir))
    user_path = model_slots.selected(root, 'transcription')
    if requested_language in {"auto", "none", "und"}:
        requested_language = ""
    if errors is None:
        errors = []

    def fail(provider: str, model_name: str, message: str) -> None:
        errors.append({
            "provider": provider,
            "model": model_name,
            "error": str(message)[:300],
        })

    source = Path(wav_path) if wav_path else None
    if not source or not source.exists():
        fail("stt", "", "No extracted audio to transcribe.")
        return None
    # Gate on the raw audio: loudness normalisation would lift room noise.
    if has_speech_energy(source) is False:
        if progress is not None:
            progress(1.0, "No speech found")
        return no_speech_transcript(requested_language)
    if prepared is None:
        prepared_path, prepared_hash = prepare_audio(
            source, job_dir, source_hash=source_hash,
        )
    else:
        prepared_path = Path(prepared)
        prepared_hash = audio_hash or _sha256_file(prepared_path)
    model = str(model or "")
    plan = resolve_routes(routes, engine=engine, model=model)
    if user_path:
        plan = [{"provider": "whisper", "model": user_path}]
    if not plan:
        fail("stt", "", "No speech engine is configured.")
        return None
    terms = list(vocabulary or [])
    ready_routes = {
        index: (_engine_ready(str(route["provider"]), str(route["model"]))
                and (route["provider"] != "whisper" or not whisper_problem(root)))
        for index, route in enumerate(plan)
    }
    ready_auto = any(
        str(route.get("provider") or "").lower() in {"whisper"}
        and ready_routes[index]
        for index, route in enumerate(plan)
        if isinstance(route, Mapping)
    )
    for route_index, route in enumerate(plan):
        provider = str(route["provider"])
        route_model = str(route["model"])
        if (
            provider == "apple"
            and not requested_language
            and ready_auto
            and str(engine).lower() != "apple"
        ):
            # Apple needs a concrete locale.  Do not silently run a Chinese
            # clip through en-US when an available auto engine can report it.
            fail("apple", route_model, "Apple speech needs a known language.")
            continue
        if not ready_routes[route_index]:
            fail(provider, route_model, (whisper_problem(root) if provider == "whisper" else "") or "Speech engine is not available.")
            continue
        route_language = requested_language
        if provider == "apple" and not route_language:
            # Apple is the only ready local engine. Use the Mac language
            # rather than dropping the transcript entirely.
            route_language = _system_speech_language()
        started = time.time()
        if progress is not None:
            # Said before the first chunk, or the previous stage's text stays up.
            progress(0.0, f"Transcribing speech · {ENGINE_LABELS.get(provider, provider)}")
        try:
            run_model = route_model
            if provider == "whisper":
                weights = _weights(root)
                if weights is None:
                    fail(provider, route_model, "Missing speech weights.")
                    continue
                run_model = str(weights.resolve())
            merged = _chunked_run(
                prepared_path, Path(job_dir), float(duration),
                audio_hash=prepared_hash,
                engine=provider, model=run_model,
                language=route_language, vocabulary=terms,
                timeout=timeout, progress=progress, helper=helper,
            )
        except SttCancelled:
            raise
        except Exception as exc:  # noqa: BLE001 - route falls through
            merged = None
            fail(provider, route_model, str(exc))
            _log_route(
                logger, route_index, provider, route_model, started, False,
                str(exc)[:300], job_id=job_id, request_id=request_id,
            )
        if not merged:
            if merged is None:
                _log_route(
                    logger, route_index, provider, route_model, started, False,
                    "No transcript returned.", job_id=job_id, request_id=request_id,
                )
            fail(provider, route_model, "No transcript returned.")
            continue
        words, segments = apply_vocabulary(
            list(merged.get("words") or []),
            list(merged.get("segments") or []),
            terms,
        )
        transcript = build_transcript(
            engine=provider,
            model=route_model,
            language=merged.get("language") or route_language or requested_language,
            segments=segments,
            words=words,
            audio_duration=float(duration),
            source_hash=prepared_hash,
            drift_ms_p95=float(merged.get("drift_ms_p95") or 0.0),
        )
        if not transcript["segments"]:
            fail(provider, route_model, "The engine returned an empty transcript.")
            continue
        path = save_transcript(Path(job_dir), transcript)
        _log_route(
            logger, route_index, provider, route_model, started, True, "",
            job_id=job_id, request_id=request_id,
        )
        return {
            **transcript,
            "provider": "user-local" if user_path else provider,
            "path": str(path),
        }
    return None


# ---------------------------------------------------------------- readers


def read_transcript(job_dir: Path, *, words: bool = False) -> list[dict] | None:
    """Load transcript segments for speech/script callers.

    Transcript v2 wins; legacy ``transcript.json`` / ``transcript_apple.json``
    remain readable for old jobs. With ``words=True`` each v2 segment also
    carries its measured ``words`` (``{"w", "start", "end"}``), so callers
    that cut on sentence edges can place them on real word boundaries.
    """
    latest = load_latest_transcript(job_dir)
    if latest:
        by_segment: dict[int, list[dict]] = {}
        if words:
            for raw in latest.get("words") or []:
                if not isinstance(raw, Mapping):
                    continue
                text = _clean_text(raw.get("w") or raw.get("word")).strip()
                start = _float(raw.get("start"))
                end = _float(raw.get("end"), start)
                if not text or end <= start:
                    continue
                try:
                    index = int(raw.get("segment") or 0)
                except (TypeError, ValueError):
                    index = 0
                by_segment.setdefault(index, []).append(
                    {"w": text, "start": start, "end": end},
                )
        segments = []
        for position, item in enumerate(latest.get("segments") or []):
            if not isinstance(item, Mapping):
                continue
            value = " ".join(_clean_text(item.get("text")).split())
            if not value:
                continue
            segment = {
                "start": _float(item.get("start")),
                "end": _float(item.get("end")),
                "text": value,
            }
            if by_segment.get(position):
                segment["words"] = sorted(
                    by_segment[position], key=lambda row: (row["start"], row["end"]),
                )
            segments.append(segment)
        if segments:
            return segments
    directory = Path(job_dir) / "transcript"
    for name in ("transcript.json", "transcript_apple.json"):
        path = directory / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        segments = []
        for item in data.get("segments") or []:
            value = " ".join(_clean_text(item.get("text")).split())
            if not value:
                continue
            try:
                start = float(item.get("start", 0.0))
                end = float(item.get("end", start))
            except (TypeError, ValueError):
                continue
            segments.append({"start": start, "end": end, "text": value})
        if segments:
            return segments
    return None


def attach_speech(scenes: list[dict], transcript: Mapping[str, Any] | None) -> None:
    for scene in scenes:
        scene.setdefault("speech", "")
    if not transcript:
        return
    for event in transcript.get("segments") or []:
        for scene in scenes:
            overlap = min(scene["end"], event["end"]) - max(scene["start"], event["start"])
            if overlap > 0.18:
                existing = scene.get("speech") or ""
                if event["text"] not in existing:
                    joined = (existing + " " + event["text"]).strip()
                    scene["speech"] = joined[:260]
