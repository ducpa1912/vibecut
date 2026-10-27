"""Speech-to-text for VibeCut: local Apple Speech, local Whisper, explicit cloud.

Wave 2 track T2 owns this module.  It replaces the transcription block that
used to live in ``pipeline.py`` and adds the Transcript v2 contract from
``REVAMP_PLAN.md`` §6.3:

* Apple SpeechAnalyzer is the default local engine and emits word timings from
  each attributed run's ``audioTimeRange``.
* Whisper runs through ``mlx_whisper`` with ``--word-timestamps True`` and
  ``large-v3-turbo`` as the default model.
* Long sources are cut into 10 minute chunks with 5 s overlap.  Each finished
  chunk is cached by ``audio_hash + engine + model + chunk index`` so a crash
  resumes at the last finished chunk.
* Cloud providers (Groq whisper-large-v3-turbo, Deepgram nova-3) run only when
  a route names them explicitly.  There is no ``auto`` cloud ladder and OpenAI
  STT is not part of the engine set.

Nothing here runs at import time.  Tests fake every engine.
"""

from __future__ import annotations

import difflib
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import uuid
import wave
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import packs
import settings_store
import usage_store
import vision
import workflow_config

ROOT = Path(__file__).resolve().parent

SCHEMA_VERSION = 2
CHUNK_SECONDS = 600.0
OVERLAP_SECONDS = 5.0
LOW_CONFIDENCE = 0.5
DEFAULT_WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"
CLOUD_STT_PROVIDERS = ("groq", "deepgram")
LOCAL_STT_ENGINES = ("apple", "whisper")
STT_ENGINES = LOCAL_STT_ENGINES + CLOUD_STT_PROVIDERS
WHISPER_MODELS = (
    {
        "id": DEFAULT_WHISPER_MODEL,
        "name": "Whisper large-v3 turbo · best",
        "size_mb": 1600,
    },
    {
        "id": "mlx-community/whisper-large-v3-turbo-q4",
        "name": "Whisper large-v3 turbo q4 · balanced",
        "size_mb": 900,
    },
)
LEGACY_WHISPER_MODELS = {
    "mlx-community/whisper-small-mlx": DEFAULT_WHISPER_MODEL,
    "mlx-community/whisper-medium-mlx-q4": DEFAULT_WHISPER_MODEL,
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


# ---------------------------------------------------------------- credentials


def cloud_stt_key(provider: str) -> str:
    """Return the stored key for one explicit cloud STT provider."""
    name = str(provider or "").strip().lower()
    # ``openai`` is kept for the legacy key API only; it is not an STT engine.
    if name not in (*CLOUD_STT_PROVIDERS, "openai"):
        return ""
    return settings_store.get_secret(name)


def openai_key() -> str:
    """Deprecated shared key getter.

    OpenAI STT was removed in Wave 2.  ``audio.py`` still imports this name for
    the settings/key surface, so it stays until Claude Code removes leftovers.
    """
    return cloud_stt_key("openai")


def groq_key() -> str:
    return cloud_stt_key("groq")


def deepgram_key() -> str:
    return cloud_stt_key("deepgram")


# ---------------------------------------------------------------- helpers


def _which(name: str) -> str | None:
    return shutil.which(name)


def _ffmpeg() -> str:
    path = _which("ffmpeg")
    if not path:
        raise SttError("ffmpeg is not installed or not on PATH.")
    return path


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


# ---------------------------------------------------------------- whisper models


def normalize_whisper_model(model: str | None) -> str:
    value = str(model or "").strip()
    if not value:
        return DEFAULT_WHISPER_MODEL
    return LEGACY_WHISPER_MODELS.get(value, value)


def whisper_models() -> list[dict]:
    """Model rows for Setup, with the turbo pack as the default."""
    hub = Path.home() / ".cache" / "huggingface" / "hub"
    configured = (
        os.environ.get("VIBECUT_WHISPER_MODEL")
        or (settings_store.load_settings().get("stt") or {}).get("model")
        or DEFAULT_WHISPER_MODEL
    )
    current = normalize_whisper_model(configured)
    rows = []
    for item in WHISPER_MODELS:
        cached = (hub / ("models--" + item["id"].replace("/", "--"))).is_dir()
        rows.append({**item, "cached": cached, "current": item["id"] == current})
    return rows


def _stt_workflow_model(provider: str, default: str) -> str:
    try:
        workflows = settings_store.load_settings().get("workflows") or {}
        for route in workflow_config.routes(workflows, "stt"):
            if str(route.get("provider") or "") == provider and route.get("model"):
                return str(route["model"])
    except Exception:  # noqa: BLE001
        pass
    return default


def _whisper_binary() -> str | None:
    """Whisper CLI: installed Speech Pack first, then today's PATH lookup."""
    packed = packs.find_command("speech", "mlx_whisper", root=os.environ.get(packs.ROOT_ENV) or None)
    if packed is not None:
        return str(packed)
    return _which("mlx_whisper")


def _whisper_command() -> list[str] | None:
    """Command prefix for Whisper: pack binary, PATH binary, then module."""
    binary = _whisper_binary()
    if binary:
        return [binary]
    try:
        available = importlib.util.find_spec("mlx_whisper") is not None
    except (ImportError, ValueError):
        available = False
    if available:
        return [sys.executable, "-m", "mlx_whisper"]
    return None


def _apple_transcribe_helper() -> Path | None:
    """Compile tools/transcribe_apple.swift once, macOS 26 only."""
    if sys.platform != "darwin":
        return None
    source = ROOT / "tools" / "transcribe_apple.swift"
    binary = ROOT / "bin" / "transcribe_apple"
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


def _whisper_payload(data: Mapping[str, Any]) -> dict:
    segments: list[dict] = []
    words: list[dict] = []
    for raw_segment in data.get("segments") or []:
        if not isinstance(raw_segment, Mapping):
            continue
        text = " ".join(_clean_text(raw_segment.get("text")).split())
        if not text:
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


def _deepgram_payload(data: Mapping[str, Any], duration: float) -> dict:
    segments: list[dict] = []
    words: list[dict] = []
    results = data.get("results") or {}
    utterances = results.get("utterances") or []
    for item in utterances:
        if not isinstance(item, Mapping):
            continue
        text = " ".join(_clean_text(item.get("transcript")).split())
        if not text:
            continue
        speaker = item.get("speaker")
        label = f"S{int(speaker) + 1}" if isinstance(speaker, (int, float)) else None
        index = len(segments)
        segment = {
            "start": round(_float(item.get("start")), 3),
            "end": round(_float(item.get("end")), 3),
            "text": text,
            "confidence": _confidence(item.get("confidence"), 0.5),
        }
        if label:
            segment["speaker"] = label
        segments.append(segment)
        for raw_word in item.get("words") or []:
            word = _normalize_word(raw_word, speaker=label)
            if word is None:
                continue
            word["segment"] = index
            words.append(word)
    alternatives = (((results.get("channels") or [{}])[0]).get("alternatives") or [])
    alternative = alternatives[0] if alternatives else {}
    if not words:
        for raw_word in alternative.get("words") or []:
            word = _normalize_word(raw_word)
            if word is None:
                continue
            words.append(word)
    if not segments:
        full_text = " ".join(_clean_text(alternative.get("transcript")).split())
        if full_text:
            segments = [{
                "start": 0.0,
                "end": round(duration, 3) or 1.0,
                "text": full_text,
                "confidence": 0.5,
            }]
    if not segments and words:
        segments = _segments_from_words(words)
    for word in words:
        word["segment"] = _segment_index_for_time(segments, word["start"])
    return {
        "language": _base_language(
            (data.get("metadata") or {}).get("language"), "en",
        ),
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
    """Build one immutable Transcript v2 document (REVAMP_PLAN §6.3)."""
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
    try:
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
    command = _whisper_command()
    if not command:
        return None
    out_dir = Path(job_dir) / "transcript"
    out_dir.mkdir(parents=True, exist_ok=True)
    chosen_model = normalize_whisper_model(model)
    log_path = out_dir / "whisper.log"
    json_path = out_dir / "transcript.json"
    try:
        json_path.unlink()
    except OSError:
        pass
    cmd = [
        *command, str(source),
        "--model", chosen_model,
        "--output-format", "json",
        "--output-name", "transcript",
        "--output-dir", str(out_dir),
        "--word-timestamps", "True",
        "--verbose", "False",
    ]
    if language and str(language).lower() != "auto":
        cmd.extend(["--language", _base_language(language)])
    terms = [str(term) for term in (vocabulary or []) if str(term).strip()]
    if terms:
        cmd.extend(["--initial-prompt", ", ".join(terms)[:800]])
    progress(0.08, "Transcribing speech · local Whisper")
    with log_path.open("w") as log:
        try:
            result = subprocess.run(
                cmd, stdout=log, stderr=log,
                timeout=max(10.0, float(timeout)) if timeout else max(
                    900, min(7200, float(duration) * 14),
                ),
            )
        except (OSError, subprocess.SubprocessError):
            return None
    if result.returncode != 0:
        return None
    if not json_path.exists():
        return None
    progress(0.82, "Reading transcript")
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    payload = _whisper_payload(data)
    if not payload["segments"]:
        return None
    return {
        "language": payload["language"],
        "text": payload["text"][:4000],
        "segments": payload["segments"],
        "words": payload["words"],
        "provider": "whisper",
        "model": chosen_model,
    }


def _multipart(
    fields: dict, file_field: str, filename: str,
    content: bytes, content_type: str,
) -> tuple[bytes, str]:
    boundary = "----vibecut" + uuid.uuid4().hex
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n".encode("utf-8")
        )
    chunks.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
        f'filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n'.encode("utf-8")
    )
    chunks.append(content)
    chunks.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _cloud_speech(
    wav_path: Path,
    job_dir: Path,
    provider: str,
    language: str,
    model: str = "",
    timeout: float = 1800,
    *,
    run: Callable[..., Any] | None = None,
    urlopen: Callable[..., Any] | None = None,
) -> dict | None:
    """One explicit cloud STT request.  No auto provider selection."""
    name = str(provider or "").strip().lower()
    if name not in CLOUD_STT_PROVIDERS:
        return None
    runner = run or _run
    opener = urlopen or urllib.request.urlopen
    out_dir = Path(job_dir) / "transcript"
    out_dir.mkdir(parents=True, exist_ok=True)
    upload = out_dir / "transcript_upload.mp3"
    runner([
        _ffmpeg(), "-y", "-v", "error", "-i", str(wav_path),
        "-ac", "1", "-ar", "16000", "-b:a", "48k", str(upload),
    ], timeout=600)
    if not upload.is_file() or upload.stat().st_size == 0:
        return None
    audio_bytes = upload.read_bytes()
    key = settings_store.get_secret(name)
    if not key:
        return None
    duration = 0.0
    try:
        with wave.open(str(wav_path), "rb") as handle:
            duration = handle.getnframes() / max(1, handle.getframerate())
    except (OSError, EOFError, wave.Error):
        pass

    if name == "groq":
        endpoint = "https://api.groq.com/openai/v1/audio/transcriptions"
        chosen_model = model or os.environ.get(
            "VIBECUT_GROQ_STT_MODEL",
        ) or _stt_workflow_model("groq", "whisper-large-v3-turbo")
        fields = {
            "model": chosen_model,
            "response_format": "verbose_json",
            "temperature": "0",
            "timestamp_granularities[]": "word",
        }
        if language and str(language).lower() != "auto":
            fields["language"] = _base_language(language)
        body, content_type = _multipart(
            fields, "file", "audio.mp3", audio_bytes, "audio/mpeg",
        )
        request = urllib.request.Request(
            endpoint, data=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": content_type},
            method="POST",
        )
        try:
            with opener(request, timeout=max(10, timeout)) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception:  # noqa: BLE001 - a cloud failure returns no transcript
            return None
        payload = _whisper_payload(data)
        if not payload["segments"]:
            return None
        return {
            "language": payload["language"],
            "text": payload["text"][:4000],
            "segments": [
                {"start": item["start"], "end": item["end"], "text": item["text"]}
                for item in payload["segments"]
            ],
            "words": payload["words"],
            "provider": "groq",
            "model": chosen_model,
            "seconds": round(duration, 3),
        }

    # Deepgram nova-3
    chosen_model = model or _stt_workflow_model("deepgram", "nova-3")
    params = {
        "model": chosen_model,
        "smart_format": "true",
        "utterances": "true",
        "punctuate": "true",
    }
    if language and str(language).lower() != "auto":
        params["language"] = _base_language(language)
    endpoint = "https://api.deepgram.com/v1/listen?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        endpoint, data=audio_bytes,
        headers={"Authorization": f"Token {key}", "Content-Type": "audio/mpeg"},
        method="POST",
    )
    try:
        with opener(request, timeout=max(10, timeout)) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - a cloud failure returns no transcript
        return None
    payload = _deepgram_payload(data, duration)
    if not payload["segments"]:
        return None
    return {
        "language": payload["language"],
        "text": payload["text"][:4000],
        "segments": [
            {"start": item["start"], "end": item["end"], "text": item["text"]}
            for item in payload["segments"]
        ],
        "words": payload["words"],
        "provider": "deepgram",
        "model": chosen_model,
        "seconds": round(duration, 3),
    }


def transcribe_cloud(
    wav_path: Path | None,
    job_dir: Path,
    language: str = "en",
    provider: str = "",
    model: str = "",
    timeout: float = 1800,
) -> dict | None:
    """Explicit cloud transcription.  ``auto``/empty never selects a provider."""
    name = str(provider or "").strip().lower()
    if name not in CLOUD_STT_PROVIDERS:
        return None
    source = Path(wav_path) if wav_path else None
    if not source or not source.exists():
        return None
    result = _cloud_speech(
        source, job_dir, name, language, model=model, timeout=timeout,
    )
    if result:
        usage_store.record(
            "stt", name, audio_seconds=float(result.get("seconds") or 0.0),
        )
    return result


# ---------------------------------------------------------------- routes


def normalize_engine(provider: str, model: str = "") -> dict | None:
    name = str(provider or "").strip().lower()
    raw_model = str(model or "").strip()
    if name in {"auto", "local", "whisper"}:
        return {"provider": "whisper", "model": normalize_whisper_model(raw_model)}
    if name == "apple":
        return {"provider": "apple", "model": raw_model or "on-device-3b"}
    if name in CLOUD_STT_PROVIDERS:
        if name == "groq":
            return {
                "provider": "groq",
                "model": normalize_whisper_model(
                    raw_model or _stt_workflow_model("groq", "whisper-large-v3-turbo"),
                ),
            }
        return {
            "provider": "deepgram",
            "model": raw_model or _stt_workflow_model("deepgram", "nova-3"),
        }
    # OpenAI STT was removed.  It is not mapped to another cloud provider.
    return None


def resolve_routes(
    routes: Iterable[Mapping[str, Any]] | None = None,
    *,
    engine: str = "",
    model: str = "",
) -> list[dict]:
    """Turn configured routes into the final explicit engine list.

    ``auto``/``local`` are local Whisper aliases; OpenAI routes are dropped.
    Cloud engines appear only when the caller configured them by name.
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
    if provider in CLOUD_STT_PROVIDERS:
        return bool(settings_store.get_secret(provider))
    return False


# ---------------------------------------------------------------- chunked runs


def _run_engine_chunk_keyed(
    prepared: Path, job_dir: Path, chunk: dict, *, key: str,
    engine: str, model: str, language: str,
    vocabulary: Iterable[str] | None, timeout: float | None,
    helper: Any = _UNSET,
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
        )
    elif engine == "whisper":
        raw = transcribe(
            chunk_wav, work, float(chunk["end"]) - float(chunk["start"]),
            lambda _fraction, _message: None,
            model=model, timeout=timeout, language=language,
            vocabulary=vocabulary,
        )
    else:
        raw = _cloud_speech(
            chunk_wav, work, engine, language, model=model,
            timeout=float(timeout or 1800),
        )
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
    for chunk in ranges:
        key = chunk_cache_key(audio_hash, engine, model, int(chunk["index"]))
        cache_path = _chunk_cache_path(job_dir, key)
        record = None
        if cache_path.is_file():
            try:
                record = json.loads(cache_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                record = None
        if not isinstance(record, dict) or record.get("key") != key:
            record = _run_engine_chunk_keyed(
                prepared, job_dir, chunk, key=key,
                engine=engine, model=model, language=language,
                vocabulary=vocabulary, timeout=timeout, helper=helper,
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


def transcribe_source(
    wav_path: Path | None,
    job_dir: Path,
    duration: float,
    progress: Callable[[float, str], None] | None = None,
    *,
    engine: str = "",
    model: str = "",
    routes: Iterable[Mapping[str, Any]] | None = None,
    language: str = "en",
    vocabulary: Iterable[str] | None = None,
    source_hash: str = "",
    timeout: float | None = None,
    job_id: str = "",
    request_id: str = "",
    logger: Callable[..., None] | None = None,
    helper: Any = _UNSET,
    prepared: Path | None = None,
    audio_hash: str = "",
) -> dict | None:
    """Chunk, transcribe, merge and persist one Transcript v2 for a job."""
    source = Path(wav_path) if wav_path else None
    if not source or not source.exists():
        return None
    if prepared is None:
        prepared_path, prepared_hash = prepare_audio(
            source, job_dir, source_hash=source_hash,
        )
    else:
        prepared_path = Path(prepared)
        prepared_hash = audio_hash or _sha256_file(prepared_path)
    model = str(model or "")
    plan = resolve_routes(routes, engine=engine, model=model)
    if not plan:
        return None
    terms = list(vocabulary or [])
    for route_index, route in enumerate(plan):
        provider = str(route["provider"])
        route_model = str(route["model"])
        if not _engine_ready(provider, route_model):
            continue
        started = time.time()
        try:
            merged = _chunked_run(
                prepared_path, Path(job_dir), float(duration),
                audio_hash=prepared_hash,
                engine=provider, model=route_model,
                language=language, vocabulary=terms,
                timeout=timeout, progress=progress, helper=helper,
            )
        except Exception as exc:  # noqa: BLE001 - route falls through
            merged = None
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
            continue
        words, segments = apply_vocabulary(
            list(merged.get("words") or []),
            list(merged.get("segments") or []),
            terms,
        )
        transcript = build_transcript(
            engine=provider,
            model=route_model,
            language=merged.get("language") or language,
            segments=segments,
            words=words,
            audio_duration=float(duration),
            source_hash=prepared_hash,
            drift_ms_p95=float(merged.get("drift_ms_p95") or 0.0),
        )
        if not transcript["segments"]:
            continue
        path = save_transcript(Path(job_dir), transcript)
        if provider in CLOUD_STT_PROVIDERS:
            usage_store.record(
                "stt", provider, model=route_model,
                audio_seconds=float(duration),
            )
        _log_route(
            logger, route_index, provider, route_model, started, True, "",
            job_id=job_id, request_id=request_id,
        )
        return {
            **transcript,
            "provider": provider,
            "path": str(path),
        }
    return None


def transcribe_routes(
    wav_path: Path,
    job_dir: Path,
    duration: float,
    language: str,
    routes: Iterable[Mapping[str, Any]] | None,
    timeout: float,
    progress: Callable[..., None],
    *,
    job_id: str = "",
    request_id: str = "",
    engines: Mapping[str, Callable[..., Any]] | None = None,
    logger: Callable[..., None] | None = None,
    legacy: bool = False,
) -> dict | None:
    """Route dispatcher kept for the pre-v2 caller and its compatibility tests.

    ``legacy=True`` preserves the old ``pipeline._transcribe_workflow``
    semantics, including redirecting an explicit ``auto`` route to a cloud
    provider.  Production analysis uses :func:`transcribe_source`; the new path
    resolves routes with :func:`resolve_routes` and never has an auto ladder.
    """
    chosen = dict(engines or {})

    def callable_for(name: str, fallback: Callable[..., Any]) -> Callable[..., Any]:
        return chosen.get(name) or fallback

    def emit(fraction: float, message: str) -> None:
        try:
            progress("reading", fraction, message)
        except TypeError:
            progress(fraction, message)

    for route_index, route in enumerate(routes or []):
        provider = str(route.get("provider") or "").lower()
        model = str(route.get("model") or "")
        started = time.time()
        emit(0.70 + min(0.16, route_index * 0.02), f"Transcribing speech · {provider}")
        result = None
        try:
            if legacy and provider in {"auto", "whisper", "local"}:
                cloud_provider = ""
                if provider == "auto":
                    if model == "whisper-1":
                        cloud_provider = "openai"
                    elif model == "nova-3":
                        cloud_provider = "deepgram"
                    elif model == "whisper-large-v3-turbo":
                        cloud_provider = "groq"
                if cloud_provider:
                    result = callable_for("cloud", _cloud_speech)(
                        wav_path, job_dir, cloud_provider, language,
                        model=model, timeout=timeout,
                    )
                else:
                    result = callable_for("whisper", transcribe)(
                        wav_path, job_dir, duration,
                        lambda fraction, message: emit(
                            0.70 + 0.16 * fraction, message,
                        ),
                        model=model or None, timeout=timeout,
                    )
            elif provider == "apple":
                result = callable_for("apple", transcribe_apple)(
                    wav_path, job_dir, language, timeout=timeout,
                )
            elif provider in {"groq", "openai", "deepgram"}:
                result = callable_for("cloud", _cloud_speech)(
                    wav_path, job_dir, provider, language,
                    model=model, timeout=timeout,
                )
        except Exception as exc:  # noqa: BLE001
            _log_route(
                logger, route_index, provider, model, started, False,
                str(exc)[:300], job_id=job_id, request_id=request_id,
            )
            continue
        _log_route(
            logger, route_index, provider, model, started, bool(result),
            "" if result else "No transcript returned.",
            job_id=job_id, request_id=request_id,
        )
        if result:
            return result
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
