"""Text-to-speech voices, engine adapters and story synthesis.

Final engine set: MiniMax, ElevenLabs, OpenRouter (HeyGen + Fish + Gemini), Kokoro and
Apple ``say``. Piper, OpenAI, Groq Orpheus, Deepgram Aura and Cartesia are
removed from the registry, voice picker and synthesis paths.

A story is voiced by exactly one engine and one voice. The per-sentence cache
is keyed by engine, model, voice, text, rate and language. If any sentence
fails on the chosen engine, the whole story moves to the next configured
engine; a story never mixes voices.

Split out of `audio.py`. Shared process helpers, caches and the audio plan stay
in `audio.py`; every call back goes through the facade so existing tests and
callers can keep patching `audio.*`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import threading
import urllib.error
import urllib.request
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import packs

# Imported last: audio re-exports this module, so the facade must finish first.
import audio  # noqa: E402


_SAY_VOICE_RE = re.compile(r"^(?P<name>.+?)\s{2,}(?P<lang>[a-zA-Z_-]+)\s*(?:#.*)?$")

#: Engines offered in the voice picker. OpenRouter is one engine with three
#: model families (HeyGen, Fish and Gemini), represented by the synthesizer
#: ids below.
ENGINES = ("minimax", "elevenlabs", "openrouter", "kokoro", "say")

#: Dub slot fitting: the accepted ``atempo`` band. Outside it the line is
#: flagged for Shorten (AI rewrite) or an explicit overlap choice.
SLOT_MIN_RATE = 0.90
SLOT_MAX_RATE = 1.15
SYNTHESIZERS = ("minimax", "elevenlabs", "heygen", "fish", "gemini", "kokoro", "say")
CLOUD_ENGINES = frozenset({"minimax", "elevenlabs", "heygen", "fish", "gemini"})
LOCAL_ENGINES = frozenset({"kokoro", "say"})
OPENROUTER_ENGINES = frozenset({"heygen", "fish", "gemini"})
#: HeyGen Voice on OpenRouter: ten stock voices, raw 44.1 kHz mono s16le PCM.
HEYGEN_VOICES = (
    "nadine", "tabitha", "bram", "gareth", "noelle",
    "meredith", "sabrina", "lucian", "weston", "vincent",
)
HEYGEN_PCM_RATE = 44100
REMOVED_ENGINES = frozenset(
    {"piper", "openai", "groq", "deepgram", "cartesia"}
)
DEFAULT_VOICES = {
    "minimax": "female-shaonv",
    "elevenlabs": "21m00Tcm4TlvDq8ikWAM",  # Rachel
    "openrouter": "Kore",
    "heygen": "nadine",
    "fish": "",
    "gemini": "Kore",
    "kokoro": "af_heart",
    "say": "Samantha",
}
DEFAULT_MODELS = {
    "minimax": "speech-2.8-turbo",
    "elevenlabs": "eleven_multilingual_v2",
    "heygen": "heygen/heygen-voice-1-turbo:free",
    "fish": "fish-audio/s2.1-pro-free:free",
    "gemini": "google/gemini-3.8-flash-lite-tts",
    "kokoro": "kokoro",
    "say": "say",
}
ENGINE_LABELS = {
    "minimax": "MiniMax Speech 2.8",
    "elevenlabs": "ElevenLabs",
    "openrouter": "OpenRouter",
    "heygen": "OpenRouter · HeyGen Voice Turbo",
    "fish": "OpenRouter · Fish S2.1",
    "gemini": "OpenRouter · Gemini Flash-Lite",
    "kokoro": "Kokoro (on-device)",
    "say": "Apple say",
}


def openrouter_engine(model: str) -> str:
    """Synthesizer id for an OpenRouter speech model slug."""
    lowered = str(model or "").lower()
    if "heygen" in lowered:
        return "heygen"
    return "fish" if "fish" in lowered else "gemini"


def is_removed_engine(engine: str) -> bool:
    return str(engine or "").strip().lower() in REMOVED_ENGINES


def engine_label(engine: str) -> str:
    return ENGINE_LABELS.get(str(engine or "").strip().lower(), str(engine or ""))


def default_voice(engine: str) -> str:
    return DEFAULT_VOICES.get(str(engine or "").strip().lower(), "")


def _removed_error(engine: str) -> "audio.AudioError":
    return audio.AudioError(
        f"Voice engine {engine!r} was removed. Use MiniMax, ElevenLabs, "
        "OpenRouter, Kokoro or Apple say."
    )


def line_cache_key(
    engine: str,
    model: str,
    voice: str,
    text: str,
    rate: float = 1.0,
    language: str = "",
) -> str:
    """SHA-256 cache key for one sentence.

    Every field that changes the audio is part of the key. The text is kept
    verbatim so two sentences that only differ by punctuation never collide.
    """
    payload = {
        "engine": str(engine or "").strip().lower(),
        "model": str(model or ""),
        "voice": str(voice or ""),
        "text": str(text or ""),
        "rate": f"{float(rate or 1.0):.3f}",
        "language": str(language or "").strip().lower(),
        "schema": 1,
    }
    blob = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def line_cache_path(
    cache_dir: Path,
    engine: str,
    model: str,
    voice: str,
    text: str,
    rate: float = 1.0,
    language: str = "",
    suffix: str = ".flac",
) -> Path:
    key = line_cache_key(engine, model, voice, text, rate, language)
    return (cache_dir / f"{key}{suffix}").resolve()


def plan_slot_fit(
    native_seconds: float,
    slot_seconds: float,
    *,
    min_rate: float = SLOT_MIN_RATE,
    max_rate: float = SLOT_MAX_RATE,
) -> dict[str, Any]:
    """Decide the ``atempo`` factor for one dubbed sentence.

    ``atempo`` is the playback speed, so a line longer than its slot needs a
    factor above 1. Inside 0.90–1.15× the line simply fits. A line beyond
    1.15× is flagged "Too long by N s" and the caller can choose Shorten or an
    explicit overlap; playback is still capped at the band edge.
    """
    native = max(0.0, float(native_seconds or 0.0))
    slot = max(0.0, float(slot_seconds or 0.0))
    min_rate = max(0.1, float(min_rate or SLOT_MIN_RATE))
    max_rate = max(min_rate, float(max_rate or SLOT_MAX_RATE))
    if slot <= 0.05 or native <= 0.0:
        return {
            "fits": False,
            "tempo": 1.0,
            "action": "none",
            "overflow": 0.0,
            "slot": round(slot, 3),
            "native": round(native, 3),
        }
    ratio = native / slot
    if ratio > max_rate:
        tempo = max_rate
        action = "shorten"
        overflow = max(0.0, native - slot * max_rate)
    elif ratio < min_rate:
        tempo = min_rate
        action = "pad"
        overflow = 0.0
    else:
        tempo = ratio
        action = "fit"
        overflow = 0.0
    return {
        "fits": action == "fit",
        "tempo": round(tempo, 4),
        "action": action,
        "overflow": round(overflow, 3),
        "slot": round(slot, 3),
        "native": round(native, 3),
    }


def fit_dub_lines(
    lines: Sequence[Mapping[str, Any]],
    *,
    duration_of: Callable[[Path], float] | None = None,
    shorten: Callable[[Mapping[str, Any], float], str | None] | None = None,
) -> list[dict[str, Any]]:
    """Attach slot-fit decisions to dubbed lines and optionally call Shorten.

    ``shorten(line, overflow_seconds)`` may return rewritten text. The caller
    re-synthesises that sentence; this helper only records the decision, so it
    stays pure and testable without an engine.
    """
    from pathlib import Path as _Path

    measured = duration_of or (lambda path: audio.media_duration(path))
    out: list[dict[str, Any]] = []
    for raw in lines:
        line = dict(raw)
        slot = float(line.get("slot") or 0.0)
        path = line.get("path")
        native = float(line.get("native") or 0.0)
        if path and not native:
            try:
                native = float(measured(_Path(str(path))) or 0.0)
            except (OSError, ValueError):
                native = 0.0
        if not native:
            native = float(line.get("estimated") or 0.0)
        fit = plan_slot_fit(native, slot)
        if fit["action"] == "shorten" and shorten is not None:
            replacement = shorten(line, float(fit["overflow"]))
            if replacement and str(replacement).strip():
                line["text"] = str(replacement).strip()
                line["shortened"] = True
                line["shortened_by"] = "ai"
        line["fit"] = fit
        line["too_long_by"] = round(float(fit["overflow"]), 3) if fit["action"] == "shorten" else 0.0
        line["slot_fit"] = bool(fit["fits"])
        out.append(line)
    return out


def slot_fit_summary(lines: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Percent of lines that fit the 0.90–1.15× band without a flag."""
    total = len(lines)
    fitted = sum(1 for line in lines if (line.get("fit") or {}).get("fits"))
    return {
        "total": total,
        "fitted": fitted,
        "percent": round(100.0 * fitted / total, 1) if total else 0.0,
        "flagged": total - fitted,
    }


def shorten_text_for_slot(
    text: str,
    native_seconds: float,
    slot_seconds: float,
    *,
    language: str = "",
    max_rate: float = SLOT_MAX_RATE,
    margin: float = 0.95,
) -> str:
    """Shorten a translation so a retake can fit the 0.90–1.15× band.

    The estimate uses the measured length of the previous take, not a generic
    characters-per-second guess, so one retake usually lands inside the band.
    The cut respects sentence and clause punctuation; it never returns a
    mid-word fragment.
    """
    value = str(text or "").strip()
    native = max(0.0, float(native_seconds or 0.0))
    slot = max(0.0, float(slot_seconds or 0.0))
    if not value or native <= 0 or slot <= 0:
        return value
    budget = slot * max(0.1, float(max_rate)) * max(0.5, min(1.0, float(margin)))
    if native <= budget:
        return value
    seconds_per_char = native / max(1, len(value))
    keep = max(4, int(budget / max(1e-6, seconds_per_char)))
    if keep >= len(value):
        return value
    head = value[:keep]
    clause = max(head.rfind(mark) for mark in "，,。.!！?？;；、")
    if clause >= max(3, keep // 2):
        head = head[:clause]
    else:
        space = head.rfind(" ")
        if space >= max(3, keep // 3):
            head = head[:space]
    head = head.strip(" ，,。.!！?？;；、~-")
    if not head:
        return value
    cjk = bool(re.search(r"[\u3400-\u9fff]", head))
    terminal = "。" if cjk else "."
    return head + terminal


def kokoro_model_dir() -> Path:
    """Kokoro model directory: installed Voice Pack first, then data/models."""
    packed = packs.find_dir("voice", "models/kokoro", "kokoro", "")
    if packed is not None and any(packed.glob("*.onnx")):
        return packed
    return audio.VOICE_DIRS["kokoro"]


# Apple's novelty voices (sound effects and singing) are never a voice-over.
SAY_NOVELTY = frozenset({
    "Albert", "Bad News", "Bahh", "Bells", "Boing", "Bubbles", "Cellos",
    "Good News", "Jester", "Organ", "Superstar", "Trinoids", "Whisper",
    "Wobble", "Zarvox",
})
# Older synthetic voices: kept, but listed after the natural ones.
SAY_SYNTHETIC = frozenset({
    "Fred", "Junior", "Kathy", "Ralph",
    "Eddy", "Flo", "Grandma", "Grandpa", "Reed", "Rocko", "Sandy", "Shelley",
})


def _say_base_name(name: str) -> str:
    return name.split(" (", 1)[0].strip()


def _say_voice_rank(name: str) -> int:
    """0 premium/enhanced, 1 natural, 2 older synthetic voices."""
    if "(Premium)" in name or "(Enhanced)" in name:
        return 0
    return 2 if _say_base_name(name) in SAY_SYNTHETIC else 1


def list_voices(engine: str) -> list[dict]:
    engine = str(engine or "").strip().lower()
    if engine == "say":
        if not audio.say_available():
            return []
        result = audio._run(["say", "-v", "?"], timeout=30)
        voices: list[dict] = []
        for line in (result.stdout or "").splitlines():
            match = _SAY_VOICE_RE.match(line.strip())
            if not match:
                continue
            name = match.group("name").strip()
            if _say_base_name(name) in SAY_NOVELTY:
                continue
            lang = match.group("lang").strip()
            voices.append({"id": name, "name": name, "lang": lang})
        # Natural voices first; within a rank, by language then name.
        voices.sort(key=lambda item: (_say_voice_rank(item["name"]), item["lang"], item["name"]))
        return voices

    if engine == "kokoro":
        directory = kokoro_model_dir()
        names: list[str] = []
        meta = directory / "voices.json"
        if meta.is_file():
            try:
                data = json.loads(meta.read_text())
                names = sorted(data.keys()) if isinstance(data, dict) else []
            except (OSError, json.JSONDecodeError):
                names = []
        if not names:
            names = [*audio.KOKORO_EN_VOICES, *audio.KOKORO_ZH_NAMED, *audio.KOKORO_ZH_NUMERIC]
        return [
            {"id": name, "name": name,
             "lang": "zh" if name.startswith(("zf_", "zm_")) else "en"}
            for name in names
        ]

    if engine == "minimax":
        if not audio.minimax_key():
            return []
        names = [
            "female-shaonv", "female-yujie", "female-chengshu", "female-tianmei",
            "male-qn-qingse", "male-qn-jingying", "presenter_female", "presenter_male",
        ]
        return [{"id": name, "name": name, "lang": "multi"} for name in names]

    if engine == "heygen":
        if not audio.openrouter_available():
            return []
        return [{"id": name, "name": name.title(), "lang": "multi"} for name in HEYGEN_VOICES]

    if engine == "fish":
        if not audio.openrouter_available():
            return []
        return [{"id": "default", "name": "Fish default", "lang": "multi"}]

    if engine == "gemini":
        if not audio.openrouter_available():
            return []
        names = ["Kore", "Zephyr", "Puck", "Charon", "Leda", "Aoede", "Fenrir"]
        return [{"id": name, "name": name, "lang": "multi"} for name in names]

    if engine == "openrouter":
        if not audio.openrouter_available():
            return []
        names = ["Kore", "Zephyr", "Puck", "Charon", "Leda", "Aoede", "Fenrir"]
        return (
            [{"id": "default", "name": "Fish default", "lang": "multi"}]
            + [{"id": name, "name": name, "lang": "multi"} for name in names]
        )

    if engine == "elevenlabs":
        key = audio.elevenlabs_key()
        if not key:
            return []
        request = urllib.request.Request(
            "https://api.elevenlabs.io/v1/voices",
            headers={"xi-api-key": key},
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise audio.AudioError(f"ElevenLabs voices failed: {exc}") from exc
        voices = []
        for item in data.get("voices", []):
            voices.append({
                "id": item.get("voice_id"),
                "name": item.get("name") or item.get("voice_id"),
                "lang": ",".join((item.get("labels") or {}).get("language", "").split()) or "multi",
            })
        return voices

    # Removed engines (piper/openai/groq/deepgram/cartesia) have no voices.
    return []


def _candidate(provider: str, model: str) -> dict[str, str] | None:
    provider = str(provider or "").strip().lower()
    model = str(model or "").strip()
    if provider == "minimax":
        return {
            "engine": "minimax", "provider": provider,
            "model": model or DEFAULT_MODELS["minimax"],
        }
    if provider == "elevenlabs":
        return {
            "engine": "elevenlabs", "provider": provider,
            "model": model or DEFAULT_MODELS["elevenlabs"],
        }
    if provider == "openrouter":
        engine = openrouter_engine(model)
        return {
            "engine": engine, "provider": provider,
            "model": model or DEFAULT_MODELS[engine],
        }
    if provider == "local":
        if model == "piper":
            return None
        engine = model if model in LOCAL_ENGINES else "kokoro"
        return {"engine": engine, "provider": provider, "model": model or engine}
    # Removed providers (openai/groq/deepgram/cartesia) are skipped.
    return None


def _tts_route_candidates() -> list[dict[str, str]]:
    """Ordered TTS candidates from the admin workflow, model included."""
    cfg = audio._workflow("tts")
    candidates: list[dict[str, str]] = []
    for route in cfg.get("routes") or []:
        if not isinstance(route, Mapping):
            continue
        item = _candidate(
            str(route.get("provider") or ""), str(route.get("model") or ""),
        )
        if item:
            candidates.append(item)
    return candidates


def _tts_candidates(engine_name: str = "auto") -> list[str]:
    """Compatibility helper: ordered engine names from configured routes."""
    return [item["engine"] for item in _tts_route_candidates()]


def _tts_voice_for(candidate: str, preferred: str, primary: str) -> str:
    candidate = str(candidate or "").strip().lower()
    candidate = "gemini" if candidate == "openrouter" else candidate
    preferred = str(preferred or "").strip()
    if candidate == primary and preferred not in {"", "default"}:
        return preferred
    if candidate == "fish":
        return ""
    if candidate in {"elevenlabs"}:
        return DEFAULT_VOICES["elevenlabs"]
    return DEFAULT_VOICES.get(candidate, preferred)


@dataclass(frozen=True)
class StoryVoice:
    """One voice for a whole story."""

    engine: str
    model: str
    voice: str
    language: str
    paths: tuple[Path, ...]
    cache_hits: int = 0
    attempts: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "model": self.model,
            "voice": self.voice,
            "language": self.language,
            "paths": [str(path) for path in self.paths],
            "cache_hits": self.cache_hits,
            "attempts": list(self.attempts),
        }


def _story_lines(
    lines: Sequence[Any], rate: float, language: str,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(lines):
        if isinstance(raw, str):
            text = raw
            line_rate = rate
            line_language = language
        elif isinstance(raw, Mapping):
            text = str(raw.get("text") or "")
            line_rate = float(raw.get("rate") or rate or 1.0)
            line_language = str(raw.get("language") or language or "")
        else:
            raise ValueError(f"Voice line {index} must be text or a mapping.")
        if not text.strip():
            raise ValueError(f"Voice line {index} has no text.")
        normalized.append({
            "text": text,
            "rate": line_rate,
            "language": line_language,
        })
    if not normalized:
        raise ValueError("A story needs at least one line to voice.")
    return normalized


def _candidate_order(
    engine: str, model: str, routes: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, str]]:
    configured: list[dict[str, str]] = []
    for route in routes if routes is not None else _tts_route_candidates():
        if not isinstance(route, Mapping):
            continue
        item = _candidate(
            str(route.get("provider") or ""), str(route.get("model") or ""),
        )
        if item:
            configured.append(item)

    requested = str(engine or "auto").strip().lower()
    if requested in {"", "auto"}:
        if not configured:
            raise audio.AudioError("No voice routes are configured in the admin console.")
        return configured
    if requested == "openrouter":
        requested = "fish" if "fish" in str(model or "").lower() else "gemini"
    if requested not in SYNTHESIZERS:
        raise _removed_error(requested) if is_removed_engine(requested) else audio.AudioError(
            f"Unknown voice engine {engine!r}."
        )
    if model:
        primary = {
            "engine": requested,
            "provider": "openrouter" if requested in OPENROUTER_ENGINES else (
                "local" if requested in LOCAL_ENGINES else requested
            ),
            "model": model,
        }
    elif configured:
        match = next((item for item in configured if item["engine"] == requested), None)
        primary = dict(match or {
            "engine": requested,
            "provider": "openrouter" if requested in OPENROUTER_ENGINES else (
                "local" if requested in LOCAL_ENGINES else requested
            ),
            "model": DEFAULT_MODELS.get(requested, requested),
        })
    else:
        primary = {
            "engine": requested,
            "provider": "openrouter" if requested in OPENROUTER_ENGINES else (
                "local" if requested in LOCAL_ENGINES else requested
            ),
            "model": DEFAULT_MODELS.get(requested, requested),
        }
    ordered = [primary]
    for item in configured:
        if not any(
            item["engine"] == existing["engine"]
            and item["model"] == existing["model"]
            for existing in ordered
        ):
            ordered.append(item)
    return ordered


def synthesize_story(
    lines: Sequence[Any],
    *,
    engine: str = "auto",
    voice: str = "",
    model: str = "",
    language: str = "en",
    rate: float = 1.0,
    cache_dir: Path | None = None,
    routes: Sequence[Mapping[str, Any]] | None = None,
    cancel_event: threading.Event | None = None,
    timeout: float = 300,
    progress: Callable[[int, int], None] | None = None,
) -> StoryVoice:
    """Voice a whole story with one engine and one voice.

    Each sentence is a cache unit. If any sentence fails on the current engine,
    that engine is abandoned and the whole story restarts on the next route.
    Already-written cache files are reused, but no clip from a failed attempt
    reaches the returned story.
    """
    normalized = _story_lines(lines, rate, language)
    candidates = _candidate_order(engine, model, routes)
    requested_voice = str(voice or "").strip()
    primary_engine = candidates[0]["engine"]
    cache = Path(cache_dir) if cache_dir is not None else audio.CACHE / "voice"
    cache.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    for candidate in candidates:
        candidate_engine = candidate["engine"]
        candidate_model = candidate.get("model") or candidate_engine
        candidate_voice = _tts_voice_for(
            candidate_engine, requested_voice, primary_engine,
        )
        if not candidate_voice and candidate_engine != "fish":
            candidate_voice = default_voice(candidate_engine)
        attempts: list[str] = []
        paths: list[Path] = []
        hits = 0
        try:
            for index, line in enumerate(normalized):
                path = line_cache_path(
                    cache, candidate_engine, candidate_model, candidate_voice,
                    line["text"], line["rate"], line["language"],
                )
                if path.is_file() and path.stat().st_size > 512:
                    hits += 1
                else:
                    synthesize_line(
                        candidate_engine,
                        candidate_voice,
                        line["text"],
                        path,
                        rate=line["rate"],
                        cancel_event=cancel_event,
                        model=candidate_model,
                        timeout=timeout,
                        language=line["language"],
                    )
                    if not path.is_file() or path.stat().st_size == 0:
                        raise audio.AudioError(
                            f"{engine_label(candidate_engine)} produced no audio."
                        )
                paths.append(path)
                attempts.append(candidate_engine)
                if progress:
                    progress(index + 1, len(normalized))
        except Exception as exc:  # noqa: BLE001
            if cancel_event is not None and cancel_event.is_set():
                raise audio.AudioError("Voice synthesis cancelled.") from exc
            failures.append(
                f"{engine_label(candidate_engine)}: {str(exc)[:200]}"
            )
            continue
        return StoryVoice(
            engine=candidate_engine,
            model=candidate_model,
            voice=candidate_voice,
            language=str(language or ""),
            paths=tuple(paths),
            cache_hits=hits,
            attempts=tuple(attempts),
        )

    detail = "; ".join(failures) if failures else "no configured route"
    raise audio.AudioError(f"All voice engines failed for this story: {detail}")


# ---------------------------------------------------------------- speech

def _voice_cache(cache_dir: Path, key: str, suffix: str = ".flac") -> Path:
    return cache_dir / f"{key}{suffix}"


def _to_flac(source: Path, output: Path, mono: bool = True) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    audio._run([
        audio._ffmpeg(), "-y", "-v", "error", "-i", str(source),
        "-ar", "32000" if mono else "48000",
        "-ac", "1" if mono else "2",
        "-c:a", "flac", str(output),
    ])
    return output


def _say_voice(text: str, voice: str, rate: float, output: Path) -> None:
    words_per_minute = int(max(90, min(360, 180 * float(rate or 1.0))))
    raw = output.with_suffix(".aiff")
    audio._run([
        "say", "-v", voice or "Samantha", "-r", str(words_per_minute),
        "-o", str(raw), text,
    ], timeout=300)
    audio._convert(raw, output)
    try:
        raw.unlink()
    except OSError:
        pass


def _kokoro_files_for(voice: str) -> tuple[Path | None, Path | None]:
    """Prefer the model whose language matches the voice, then the smallest precision."""
    directory = kokoro_model_dir()
    files = sorted(directory.glob("*.onnx"))
    if not files:
        return None, None
    voice_name = (voice or "").lower()
    # v1.1-zh uses numeric IDs (zf_001, zm_009). The named Chinese voices
    # (zf_xiaobei, zm_yunjian) belong to the v1.0 multilingual model.
    numeric_zh = bool(re.fullmatch(r"z[fm]_\d{3}", voice_name))
    named_zh = voice_name in audio.KOKORO_ZH_NAMED
    wants_zh = numeric_zh

    def rank(path: Path):
        name = path.name.lower()
        has_zh = "zh" in name
        if wants_zh:
            lang_rank = 0 if has_zh else 1
        elif named_zh:
            # named Chinese voices are in v1.0, not the numeric v1.1-zh file
            lang_rank = 0 if not has_zh else 1
        else:
            lang_rank = 0 if not has_zh else 1
        if any(token in name for token in ("int8", "q8", "quant")):
            precision = 0
        elif "fp16" in name:
            precision = 1
        else:
            precision = 2
        return (lang_rank, precision, name)

    model = sorted(files, key=rank)[0]
    version = "1.1" if "1.1" in model.name else "1.0"
    voices = sorted(directory.glob(f"voices*{version}*.bin"))
    if not voices:
        voices = sorted(directory.glob("voices*.bin"))
    return model, (voices[0] if voices else None)


def _kokoro_voice(
    text: str, voice: str, output: Path, rate: float = 1.0, cancel_event=None,
) -> None:
    model, voices = audio._kokoro_files_for(voice)
    if not model or not voices:
        raise audio.AudioError("Kokoro model files are missing from data/models/kokoro.")
    worker = audio.ROOT / "tools" / "tts_kokoro.py"
    audio._run([
        sys.executable, str(worker),
        "--model", str(model), "--voices", str(voices),
        "--voice", voice or "af_heart", "--out", str(output),
        "--speed", f"{max(0.6, min(1.6, float(rate or 1.0))):.3f}",
    ], input_text=text, timeout=900, cancel_event=cancel_event)


def _elevenlabs_voice(
    text: str, voice: str, output: Path, rate: float,
    model: str = "", timeout: float = 180,
) -> None:
    key = audio.elevenlabs_key()
    if not key:
        raise audio.AudioError("Set VIBECUT_ELEVENLABS_API_KEY to use ElevenLabs.")
    if not voice:
        raise audio.AudioError("Pick an ElevenLabs voice first.")
    payload = json.dumps({
        "text": text,
        "model_id": model or "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.75},
    }).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128",
        data=payload,
        headers={"xi-api-key": key, "Content-Type": "application/json"},
        method="POST",
    )
    raw = output.with_suffix(".mp3")
    try:
        with urllib.request.urlopen(request, timeout=max(10, timeout)) as response:
            raw.write_bytes(response.read())
    except Exception as exc:  # noqa: BLE001
        raise audio.AudioError(f"ElevenLabs synthesis failed: {exc}") from exc
    extra = ["-filter:a", f"atempo={max(0.7, min(1.4, float(rate or 1.0)))}"] if rate and rate != 1.0 else []
    audio._convert(raw, output, extra)
    try:
        raw.unlink()
    except OSError:
        pass


def _minimax_voice(
    text: str, voice: str, output: Path, rate: float = 1.0,
    model: str = "", timeout: float = 300,
) -> None:
    key = audio.minimax_key()
    if not key:
        raise audio.AudioError("Set MINIMAX_API_KEY to use MiniMax voice.")
    model = model or str((audio.settings_store.load_settings().get("minimax") or {}).get("tts_model") or "speech-2.8-turbo")
    payload = json.dumps({
        "model": model,
        "text": text,
        "stream": False,
        "voice_setting": {
            "voice_id": voice or "female-shaonv",
            "speed": max(0.5, min(2.0, float(rate or 1.0))),
            "vol": 1.0,
            "pitch": 0,
        },
        "audio_setting": {
            "sample_rate": 44100,
            "bitrate": 128000,
            "format": "wav",
        },
        "language_boost": "auto",
    }).encode("utf-8")
    request = urllib.request.Request(
        "https://api.minimax.io/v1/t2a_v2",
        data=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=max(10, timeout)) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise audio.AudioError(f"MiniMax voice failed: {exc}") from exc
    status = ((data.get("base_resp") or {}).get("status_code"))
    if status not in (None, 0):
        raise audio.AudioError(f"MiniMax voice failed: {data.get('base_resp')}")
    audio_hex = str((data.get("data") or {}).get("audio") or "")
    if not audio_hex:
        raise audio.AudioError("MiniMax voice returned no audio.")
    raw = output.with_name(f"{output.stem}.minimax.tmp.wav")
    raw.write_bytes(bytes.fromhex(audio_hex))
    extra = ["-filter:a", f"atempo={max(0.8, min(1.25, float(rate or 1.0)))}"] if rate and rate != 1.0 else []
    audio._convert(raw, output, extra)
    try:
        raw.unlink()
    except OSError:
        pass


def _openrouter_voice(
    text: str, voice: str, output: Path, rate: float = 1.0, engine: str = "fish",
    model: str = "", timeout: float = 300,
) -> None:
    key = audio.openrouter_key()
    if not key:
        raise audio.AudioError("Set an OpenRouter key to use this voice.")
    if audio.openrouter_blocked():
        raise audio.AudioError(
            "OpenRouter is quarantined after an auth error; retry in "
            f"{audio.openrouter_blocked_seconds()}s."
        )
    if engine not in OPENROUTER_ENGINES:
        engine = "gemini"
    if not model:
        # Several OpenRouter routes share one provider; take the configured
        # model of this engine only, never the first OpenRouter route.
        model = next((
            str(route.get("model") or "")
            for route in audio._workflow_routes("tts")
            if str(route.get("provider") or "") == "openrouter"
            and openrouter_engine(str(route.get("model") or "")) == engine
        ), "") or DEFAULT_MODELS[engine]
    voice_value = DEFAULT_VOICES[engine] if voice in {"", "default"} else voice
    if engine == "heygen" and voice_value not in HEYGEN_VOICES:
        voice_value = DEFAULT_VOICES["heygen"]
    body = {
        "model": model,
        "input": text,
        "voice": voice_value,
        # OpenRouter speech returns MP3 or PCM, not WAV. HeyGen only serves
        # PCM. Convert afterwards.
        "response_format": "pcm" if engine == "heygen" else "mp3",
    }
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/audio/speech",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=max(10, timeout)) as response:
            content = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            audio._openrouter_auth_failure(
                int(exc.code), audio._openrouter_http_error_text(exc, key),
            )
        raise audio.AudioError(f"OpenRouter {engine} voice failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise audio.AudioError(f"OpenRouter {engine} voice failed: {exc}") from exc
    if engine == "heygen":
        raw = output.with_name(f"{output.stem}.{engine}.tmp.wav")
        with wave.open(str(raw), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(HEYGEN_PCM_RATE)
            handle.writeframes(content[: len(content) - len(content) % 2])
    else:
        raw = output.with_name(f"{output.stem}.{engine}.tmp.mp3")
        raw.write_bytes(content)
    extra = ["-filter:a", f"atempo={max(0.7, min(1.4, float(rate or 1.0)))}"] if rate and rate != 1.0 else []
    audio._convert(raw, output, extra)
    try:
        raw.unlink()
    except OSError:
        pass


def synthesize_line(
    engine: str,
    voice: str,
    text: str,
    output: Path,
    rate: float = 1.0,
    cancel_event: threading.Event | None = None,
    *,
    model: str = "",
    timeout: float = 300,
    language: str = "",
) -> Path:
    engine = str(engine or "").strip().lower()
    if is_removed_engine(engine):
        raise _removed_error(engine)
    if engine == "openrouter":
        engine = openrouter_engine(model)
    output.parent.mkdir(parents=True, exist_ok=True)
    flac = output.suffix.lower() == ".flac"
    target = output.with_suffix(".wav") if flac else output
    if engine == "say":
        if not audio.say_available():
            raise audio.AudioError("Apple say is not available.")
        audio._say_voice(text, voice, rate, target)
    elif engine == "kokoro":
        if not audio.kokoro_available():
            raise audio.AudioError("Kokoro is not installed or has no model files.")
        audio._kokoro_voice(text, voice, target, rate, cancel_event)
    elif engine == "elevenlabs":
        audio._elevenlabs_voice(text, voice, target, rate, model=model, timeout=timeout)
    elif engine == "minimax":
        audio._minimax_voice(text, voice, target, rate, model=model, timeout=timeout)
    elif engine in OPENROUTER_ENGINES:
        audio._openrouter_voice(
            text, voice, target, rate, engine, model=model, timeout=timeout,
        )
    else:
        raise audio.AudioError(f"Unknown voice engine {engine!r}.")
    if engine in audio.usage_store.TTS_PER_CHAR:
        audio.usage_store.record("tts", engine, chars=len(text))
    if not target.is_file() or target.stat().st_size == 0:
        raise audio.AudioError("Voice synthesis produced no audio.")
    if flac:
        audio._to_flac(target, output, mono=True)
        try:
            target.unlink()
        except OSError:
            pass
        if not output.is_file() or output.stat().st_size == 0:
            raise audio.AudioError("Voice cache conversion produced no audio.")
        return output
    return target


def voice_engine_status() -> dict[str, dict]:
    """Readiness for the final voice engines only.

    `audio.engine_status` is the legacy facade and is cleaned up by its owner;
    new code should use this mapping so removed engines cannot reappear in a
    picker or setup screen.
    """
    return {
        "say": {
            "available": audio.say_available(), "size_mb": 184,
            "install": "Built in. Download a Premium voice in System Settings → Spoken Content.",
        },
        "kokoro": {
            "available": audio.kokoro_available(), "size_mb": 700,
            "install": "Install the Voice Pack (Kokoro v1.0/v1.1-zh).",
        },
        "elevenlabs": {
            "available": bool(audio.elevenlabs_key()), "size_mb": 0,
            "install": "Add an ElevenLabs key in Setup.",
        },
        "minimax": {
            "available": bool(audio.minimax_key()), "size_mb": 0,
            "install": "Add a MiniMax key in Setup. Speech 2.8 Turbo.",
        },
        "heygen": {
            "available": audio.openrouter_available(), "size_mb": 0,
            "install": "Add an OpenRouter key. HeyGen Voice Turbo (free).",
        },
        "fish": {
            "available": audio.openrouter_available(), "size_mb": 0,
            "install": "Add an OpenRouter key. Fish Audio S2.1.",
        },
        "gemini": {
            "available": audio.openrouter_available(), "size_mb": 0,
            "install": "Add an OpenRouter key. Gemini Flash-Lite TTS.",
        },
    }


def voice_sample(
    engine: str,
    voice: str,
    text: str,
    cache_dir: Path,
    rate: float = 1.0,
    *,
    model: str = "",
    language: str = "",
) -> Path:
    target = line_cache_path(
        cache_dir, engine, model, voice, text, rate, language, suffix=".wav",
    )
    if target.is_file() and target.stat().st_size > 512:
        return target
    extra: dict[str, Any] = {}
    if model:
        extra["model"] = model
    if language:
        extra["language"] = language
    return audio.synthesize_line(
        engine, voice, text, target, rate=rate, **extra,
    )
