"""Audio replacement: voice over, dub, music beds, separation and mixing.

The module is deliberately opt-in: `keep` mode returns None and the renderer
falls back to the original audio bed. Every engine is detected at runtime, so
the UI can grey out what is not installed and show an install hint.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import settings_store

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
MUSIC_DIRS = {
    "library": ASSETS / "music" / "library",
    "cc0": ASSETS / "music" / "cc0",
    "generated": ASSETS / "music" / "generated",
}
VOICE_DIRS = {
    "piper": ROOT / "data" / "voices" / "piper",
    "kokoro": ROOT / "data" / "models" / "kokoro",
}
CACHE = ROOT / "data" / "cache"

MOOD_WORDS = (
    "calm", "warm", "upbeat", "energetic", "cinematic", "dramatic",
    "lofi", "lo-fi", "ambient", "nature", "tense", "happy", "sad",
    "epic", "soft", "chill", "groove", "piano", "guitar", "synth",
)

LANGUAGE_NAMES = {
    "en": "English", "vi": "Vietnamese", "zh": "Chinese", "ja": "Japanese",
    "ko": "Korean", "es": "Spanish", "fr": "French", "de": "German",
    "pt": "Portuguese", "it": "Italian", "ru": "Russian", "hi": "Hindi",
    "th": "Thai", "id": "Indonesian", "tr": "Turkish", "ar": "Arabic",
    "nl": "Dutch", "pl": "Polish", "sv": "Swedish", "da": "Danish",
    "no": "Norwegian", "fi": "Finnish", "uk": "Ukrainian", "cs": "Czech",
}


class AudioError(RuntimeError):
    pass


# ---------------------------------------------------------------- process


def _run(
    cmd: list[str],
    timeout: int | None = 900,
    input_text: str | None = None,
    cancel_event: threading.Event | None = None,
) -> subprocess.CompletedProcess:
    process = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, start_new_session=True,
    )
    if cancel_event is not None:
        def watch() -> None:
            while process.poll() is None:
                if cancel_event.wait(0.2):
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except OSError:
                        pass
                    return

        threading.Thread(target=watch, daemon=True).start()
    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except OSError:
            pass
        process.wait(timeout=5)
        raise AudioError("Audio command timed out.") from None
    if cancel_event is not None and cancel_event.is_set():
        raise AudioError("Audio build cancelled.")
    if process.returncode != 0:
        tail = (stderr or stdout or "")[-1400:]
        raise AudioError(f"Audio command failed.\n{tail}")
    return subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise AudioError("ffmpeg is not installed or not on PATH.")
    return path


def _convert(source: Path, output: Path, extra: list[str] | None = None) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    _run([
        _ffmpeg(), "-y", "-v", "error", "-i", str(source),
        "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le",
        *(extra or []), str(output),
    ])
    return output


# ---------------------------------------------------------------- detection


def _module(name: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def fnv1a(text: str) -> str:
    value = 0x811C9DC5
    for byte in text.encode("utf-8"):
        value ^= byte
        value = (value * 0x01000193) & 0xFFFFFFFF
    return f"{value:08x}"


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def signature(audio_plan: dict | None) -> str:
    """Short stable id for an audio plan; matches the browser's FNV-1a."""
    if not audio_plan or str(audio_plan.get("mode") or "keep") == "keep":
        return ""
    return fnv1a(canonical_json(audio_plan))


def say_available() -> bool:
    return sys.platform == "darwin" and bool(shutil.which("say"))


def piper_available() -> bool:
    if shutil.which("piper"):
        return True
    return _module("piper")


def kokoro_available() -> bool:
    if not _module("kokoro_onnx"):
        return False
    return any(VOICE_DIRS["kokoro"].glob("*.onnx"))


def elevenlabs_key() -> str:
    return settings_store.get_secret("elevenlabs")


def openai_key() -> str:
    return settings_store.get_secret("openai")


def groq_key() -> str:
    return settings_store.get_secret("groq")


def deepgram_key() -> str:
    return settings_store.get_secret("deepgram")


def cartesia_key() -> str:
    return settings_store.get_secret("cartesia")


def demucs_available() -> bool:
    if shutil.which("demucs"):
        return True
    return _module("demucs")


def mlx_lm_available() -> bool:
    return _module("mlx_lm")


def rewrite_models() -> list[dict]:
    """Small local models that fit an M1 and a short rewrite prompt."""
    current = os.environ.get("VIBECUT_LLM_MODEL", "qwen2.5:3b")
    return [
        {"id": "mlx", "name": "MLX local (no server)",
         "model": os.environ.get("VIBECUT_MLX_REWRITE_MODEL", "mlx-community/Qwen2.5-3B-Instruct-4bit"),
         "available": mlx_lm_available(), "size_mb": 1800,
         "install": "pip install mlx-lm (first run downloads ~1.8 GB)"},
        {"id": "ollama", "name": "Ollama",
         "model": current,
         "available": bool(os.environ.get("VIBECUT_LLM_URL")), "size_mb": 2000,
         "install": "install Ollama, then: ollama pull qwen2.5:3b"},
        {"id": "apple", "name": "Apple Foundation Models",
         "model": "on-device 3B",
         "available": sys.platform == "darwin", "size_mb": 0,
         "install": "enable Apple Intelligence on macOS 26"},
        {"id": "opencode", "name": "OpenCode Go · DeepSeek V4.1 Flash",
         "model": opencode_model() if opencode_available() else "deepseek-v4.1-flash",
         "available": opencode_available(), "size_mb": 0,
         "install": "Install OpenCode and sign in to OpenCode Go. Uses the local login; low reasoning."},
    ]


def stable_audio_available() -> bool:
    return _module("stable_audio_tools")


def translate_providers() -> list[dict]:
    providers = []
    providers.append({
        "id": "opencode",
        "name": "OpenCode Go · DeepSeek V4.1 Flash",
        "available": opencode_available(),
        "install": "Sign in to OpenCode Go. Uses the local OpenCode login; low reasoning.",
        "size_mb": 0,
    })
    providers.append({
        "id": "apple_fm",
        "name": "Apple Translation (on-device)",
        "available": sys.platform == "darwin" and bool(
            shutil.which("swiftc") or (ROOT / "bin" / "translate_apple").is_file()
        ),
        "install": "Built-in on macOS 26. Install language packs in System Settings → General → Language & Region.",
        "size_mb": 0,
    })
    providers.append({
        "id": "ollama",
        "name": "Ollama / local LLM",
        "available": bool(os.environ.get("VIBECUT_LLM_URL")),
        "install": "Set VIBECUT_LLM_URL to an Ollama /api/generate endpoint.",
        "size_mb": 3000,
    })
    providers.append({
        "id": "marian",
        "name": "Marian / opus-mt (on device, ~300 MB per pair)",
        "available": _module("transformers") and _module("torch"),
        "install": "pip install transformers torch. Downloads the opus-mt pair on first use.",
        "size_mb": 300,
    })
    providers.append({
        "id": "argos",
        "name": "Argos Translate (offline)",
        "available": _module("argostranslate"),
        "install": "pip install argostranslate && install the language pair.",
        "size_mb": 250,
    })
    return providers


def engine_status() -> dict:
    piper_bin = shutil.which("piper") or ("module" if _module("piper") else None)
    kokoro_model = next(VOICE_DIRS["kokoro"].glob("*.onnx"), None)
    voices = {
        "say": {"available": say_available(), "size_mb": 184,
                "install": "Built-in. Download a Premium voice in System Settings → Spoken Content."},
        "piper": {"available": piper_available(), "size_mb": 170,
                  "install": "pip install piper-tts piper-phonemize-cross, then download a voice."},
        "kokoro": {"available": kokoro_available(), "size_mb": 220,
                   "install": "pip install kokoro-onnx soundfile espeak-ng, put kokoro*.onnx + voices*.bin in data/models/kokoro."},
        "elevenlabs": {"available": bool(elevenlabs_key()), "size_mb": 0,
                       "install": "Set ELEVENLABS_API_KEY or add it in Setup. Cloud, paid."},
        "openai": {"available": bool(openai_key()), "size_mb": 0,
                   "install": "Set OPENAI_API_KEY or add it in Setup. gpt-4o-mini-tts, cloud."},
        "groq": {"available": bool(groq_key()), "size_mb": 0,
                 "install": "Set GROQ_API_KEY or add it in Setup. Orpheus English, cloud."},
        "deepgram": {"available": bool(deepgram_key()), "size_mb": 0,
                     "install": "Set DEEPGRAM_API_KEY or add it in Setup. Aura, cloud."},
    }
    music = {
        "library": {"available": True, "size_mb": 0,
                    "install": "Drop your own tracks in assets/music/library."},
        "cc0": {"available": True, "size_mb": 0,
                "install": "Drop CC0 tracks in assets/music/cc0. Check each track license."},
        "stable-small": {"available": stable_audio_available(), "size_mb": 2048,
                         "install": "pip install stable-audio-tools. Downloads ~2 GB on first use."},
        "stable-1.0": {"available": stable_audio_available(), "size_mb": 6192,
                       "install": "pip install stable-audio-tools. Downloads ~6 GB on first use. CC-BY-NC weights."},
    }
    return {
        "voices": voices,
        "music": music,
        "rewrite_models": rewrite_models(),
        "mlx_lm": mlx_lm_available(),
        "translation": translate_providers(),
        "separation": {
            "demucs": {"available": demucs_available(), "size_mb": 700,
                       "install": "pip install demucs. torch is already present."},
        },
        "piper_bin": piper_bin,
        "kokoro_model": str(kokoro_model) if kokoro_model else None,
        "assets": {
            "library": len(list(MUSIC_DIRS["library"].glob("*"))) if MUSIC_DIRS["library"].is_dir() else 0,
            "cc0": len(list(MUSIC_DIRS["cc0"].glob("*"))) if MUSIC_DIRS["cc0"].is_dir() else 0,
        },
    }


# ---------------------------------------------------------------- voices


_SAY_VOICE_RE = re.compile(r"^(?P<name>.+?)\s{2,}(?P<lang>[a-zA-Z_-]+)\s*(?:#.*)?$")


def list_voices(engine: str) -> list[dict]:
    if engine == "say":
        if not say_available():
            return []
        result = _run(["say", "-v", "?"], timeout=30)
        voices: list[dict] = []
        for line in (result.stdout or "").splitlines():
            match = _SAY_VOICE_RE.match(line.strip())
            if not match:
                continue
            name = match.group("name").strip()
            lang = match.group("lang").strip()
            voices.append({"id": name, "name": name, "lang": lang})
        voices.sort(key=lambda item: (item["lang"], item["name"]))
        return voices

    if engine == "piper":
        voices = []
        for directory in (VOICE_DIRS["piper"], Path.home() / ".local/share/piper"):
            if not directory.is_dir():
                continue
            for model in sorted(directory.glob("**/*.onnx")):
                voices.append({
                    "id": str(model),
                    "name": model.stem,
                    "lang": model.stem.split("-")[0] if "-" in model.stem else "",
                })
        return voices

    if engine == "kokoro":
        directory = VOICE_DIRS["kokoro"]
        names: list[str] = []
        meta = directory / "voices.json"
        if meta.is_file():
            try:
                data = json.loads(meta.read_text())
                names = sorted(data.keys()) if isinstance(data, dict) else []
            except (OSError, json.JSONDecodeError):
                names = []
        if not names:
            names = [
                "af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky",
                "am_adam", "am_michael", "bf_emma", "bf_isabella",
                "bm_george", "bm_lewis",
            ]
        return [{"id": name, "name": name, "lang": "en"} for name in names]

    if engine == "openai":
        if not openai_key():
            return []
        names = ["alloy", "ash", "ballad", "coral", "echo", "fable",
                 "nova", "onyx", "sage", "shimmer", "verse"]
        return [{"id": name, "name": name, "lang": "multi"} for name in names]

    if engine == "groq":
        if not groq_key():
            return []
        names = ["autumn", "diana", "hannah", "austin", "daniel", "troy"]
        return [{"id": name, "name": name, "lang": "en"} for name in names]

    if engine == "deepgram":
        if not deepgram_key():
            return []
        names = [
            "aura-2-thalia-en", "aura-2-andromeda-en", "aura-2-helena-en",
            "aura-2-apollo-en", "aura-2-arcas-en", "aura-2-aries-en",
            "aura-2-amalthea-en", "aura-2-atlas-en", "aura-2-aurora-en",
            "aura-2-callista-en", "aura-2-cora-en", "aura-2-cordelia-en",
            "aura-2-delia-en", "aura-2-draco-en", "aura-2-electra-en",
            "aura-2-harmonia-en", "aura-2-hera-en", "aura-2-hyperion-en",
            "aura-2-iris-en", "aura-2-janus-en",
            "aura-2-juno-en", "aura-2-jupiter-en", "aura-2-luna-en",
            "aura-2-mars-en", "aura-2-minerva-en", "aura-2-neptune-en",
            "aura-2-odysseus-en", "aura-2-ophelia-en", "aura-2-orion-en",
            "aura-2-perseus-en", "aura-2-phoebe-en", "aura-2-pluto-en",
            "aura-2-saturn-en", "aura-2-selene-en", "aura-2-theia-en",
            "aura-2-vesta-en", "aura-2-zeus-en",
        ]
        return [{"id": name, "name": name, "lang": "en"} for name in names]

    if engine == "elevenlabs":
        key = elevenlabs_key()
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
            raise AudioError(f"ElevenLabs voices failed: {exc}") from exc
        voices = []
        for item in data.get("voices", []):
            voices.append({
                "id": item.get("voice_id"),
                "name": item.get("name") or item.get("voice_id"),
                "lang": ",".join((item.get("labels") or {}).get("language", "").split()) or "multi",
            })
        return voices

    return []


# ---------------------------------------------------------------- speech


def _text_hash(*parts: str) -> str:
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()[:20]


# ---------------------------------------------------------------- translate memo

MEMO = CACHE / "translate"


def _memo_file(source: str, target: str, text: str, provider: str = "auto") -> Path:
    key = hashlib.sha1(
        f"v2|{provider}|{source}|{target}|{text}".encode("utf-8")
    ).hexdigest()[:24]
    return MEMO / key[:2] / f"{key}.txt"


def _memo_get(source: str, target: str, text: str, provider: str = "auto") -> str | None:
    path = _memo_file(source, target, text, provider)
    if not path.is_file():
        return None
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def _memo_put(source: str, target: str, text: str, value: str, provider: str = "auto") -> None:
    if not value:
        return
    path = _memo_file(source, target, text, provider)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
    except OSError:
        pass


def _voice_cache(cache_dir: Path, key: str, suffix: str = ".flac") -> Path:
    return cache_dir / f"{key}{suffix}"


def _to_flac(source: Path, output: Path, mono: bool = True) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    _run([
        _ffmpeg(), "-y", "-v", "error", "-i", str(source),
        "-ar", "32000" if mono else "48000",
        "-ac", "1" if mono else "2",
        "-c:a", "flac", str(output),
    ])
    return output


def _say_voice(text: str, voice: str, rate: float, output: Path) -> None:
    words_per_minute = int(max(90, min(360, 180 * float(rate or 1.0))))
    raw = output.with_suffix(".aiff")
    _run([
        "say", "-v", voice or "Samantha", "-r", str(words_per_minute),
        "-o", str(raw), text,
    ], timeout=300)
    _convert(raw, output)
    try:
        raw.unlink()
    except OSError:
        pass


def _piper_voice(
    text: str, voice: str, output: Path, rate: float = 1.0, cancel_event=None,
) -> None:
    model = Path(voice)
    if not model.is_file():
        raise AudioError("Pick a Piper voice model (.onnx) first.")
    binary = shutil.which("piper")
    base = [binary, "-m", str(model)] if binary else [
        sys.executable, "-m", "piper", "-m", str(model),
    ]
    length_scale = max(0.65, min(1.6, 1.0 / max(0.6, float(rate or 1.0))))
    with_rate = [*base, "--length-scale", f"{length_scale:.3f}", "-f", str(output)]
    try:
        _run(with_rate, input_text=text, timeout=600, cancel_event=cancel_event)
        return
    except AudioError:
        pass
    _run([*base, "-f", str(output)], input_text=text, timeout=600, cancel_event=cancel_event)


def _kokoro_files_for(voice: str) -> tuple[Path | None, Path | None]:
    """Prefer the model whose language matches the voice, then the smallest precision."""
    files = sorted(VOICE_DIRS["kokoro"].glob("*.onnx"))
    if not files:
        return None, None
    wants_zh = (voice or "").lower().startswith("z")

    def rank(path: Path):
        name = path.name.lower()
        lang_rank = 0 if ("zh" in name) == wants_zh else 1
        if any(token in name for token in ("int8", "q8", "quant")):
            precision = 0
        elif "fp16" in name:
            precision = 1
        else:
            precision = 2
        return (lang_rank, precision, name)

    model = sorted(files, key=rank)[0]
    version = "1.1" if "1.1" in model.name else "1.0"
    voices = sorted(VOICE_DIRS["kokoro"].glob(f"voices*{version}*.bin"))
    if not voices:
        voices = sorted(VOICE_DIRS["kokoro"].glob("voices*.bin"))
    return model, (voices[0] if voices else None)


def _kokoro_voice(
    text: str, voice: str, output: Path, rate: float = 1.0, cancel_event=None,
) -> None:
    model, voices = _kokoro_files_for(voice)
    if not model or not voices:
        raise AudioError("Kokoro model files are missing from data/models/kokoro.")
    worker = ROOT / "tools" / "tts_kokoro.py"
    _run([
        sys.executable, str(worker),
        "--model", str(model), "--voices", str(voices),
        "--voice", voice or "af_heart", "--out", str(output),
        "--speed", f"{max(0.6, min(1.6, float(rate or 1.0))):.3f}",
    ], input_text=text, timeout=900, cancel_event=cancel_event)


def _elevenlabs_voice(text: str, voice: str, output: Path, rate: float) -> None:
    key = elevenlabs_key()
    if not key:
        raise AudioError("Set VIBECUT_ELEVENLABS_API_KEY to use ElevenLabs.")
    if not voice:
        raise AudioError("Pick an ElevenLabs voice first.")
    payload = json.dumps({
        "text": text,
        "model_id": "eleven_multilingual_v2",
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
        with urllib.request.urlopen(request, timeout=180) as response:
            raw.write_bytes(response.read())
    except Exception as exc:  # noqa: BLE001
        raise AudioError(f"ElevenLabs synthesis failed: {exc}") from exc
    extra = ["-filter:a", f"atempo={max(0.7, min(1.4, float(rate or 1.0)))}"] if rate and rate != 1.0 else []
    _convert(raw, output, extra)
    try:
        raw.unlink()
    except OSError:
        pass


def _openai_voice(text: str, voice: str, output: Path, rate: float = 1.0) -> None:
    key = openai_key()
    if not key:
        raise AudioError("Set OPENAI_API_KEY to use OpenAI voice.")
    payload = json.dumps({
        "model": os.environ.get("VIBECUT_OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
        "voice": voice or "alloy",
        "input": text,
        "response_format": "wav",
    }).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        data=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    raw = output.with_name(f"{output.stem}.openai.tmp.wav")
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            raw.write_bytes(response.read())
    except Exception as exc:  # noqa: BLE001
        raise AudioError(f"OpenAI voice failed: {exc}") from exc
    extra = ["-filter:a", f"atempo={max(0.7, min(1.4, float(rate or 1.0)))}"] if rate and rate != 1.0 else []
    _convert(raw, output, extra)
    try:
        raw.unlink()
    except OSError:
        pass


def _groq_voice(text: str, voice: str, output: Path, rate: float = 1.0) -> None:
    key = groq_key()
    if not key:
        raise AudioError("Set GROQ_API_KEY to use Groq voice.")
    payload = json.dumps({
        "model": os.environ.get("VIBECUT_GROQ_TTS_MODEL", "canopylabs/orpheus-v1-english"),
        "voice": voice or "troy",
        "input": text,
        "response_format": "wav",
    }).encode("utf-8")
    request = urllib.request.Request(
        "https://api.groq.com/openai/v1/audio/speech",
        data=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    raw = output.with_name(f"{output.stem}.groq.tmp.wav")
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            raw.write_bytes(response.read())
    except Exception as exc:  # noqa: BLE001
        raise AudioError(f"Groq voice failed: {exc}") from exc
    extra = ["-filter:a", f"atempo={max(0.7, min(1.4, float(rate or 1.0)))}"] if rate and rate != 1.0 else []
    _convert(raw, output, extra)
    try:
        raw.unlink()
    except OSError:
        pass


def _deepgram_voice(text: str, voice: str, output: Path, rate: float = 1.0) -> None:
    key = deepgram_key()
    if not key:
        raise AudioError("Set DEEPGRAM_API_KEY to use Deepgram voice.")
    model = voice or "aura-2-thalia-en"
    payload = json.dumps({"text": text}).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.deepgram.com/v1/speak?model={model}",
        data=payload,
        headers={"Authorization": f"Token {key}", "Content-Type": "application/json"},
        method="POST",
    )
    raw = output.with_name(f"{output.stem}.deepgram.tmp.mp3")
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            raw.write_bytes(response.read())
    except Exception as exc:  # noqa: BLE001
        raise AudioError(f"Deepgram voice failed: {exc}") from exc
    extra = ["-filter:a", f"atempo={max(0.7, min(1.4, float(rate or 1.0)))}"] if rate and rate != 1.0 else []
    _convert(raw, output, extra)
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
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    flac = output.suffix.lower() == ".flac"
    target = output.with_suffix(".wav") if flac else output
    if engine == "say":
        if not say_available():
            raise AudioError("Apple say is not available.")
        _say_voice(text, voice, rate, target)
    elif engine == "piper":
        if not piper_available():
            raise AudioError("Piper is not installed. pip install piper-tts")
        _piper_voice(text, voice, target, rate, cancel_event)
    elif engine == "kokoro":
        if not kokoro_available():
            raise AudioError("Kokoro is not installed or has no model files.")
        _kokoro_voice(text, voice, target, rate, cancel_event)
    elif engine == "elevenlabs":
        _elevenlabs_voice(text, voice, target, rate)
    elif engine == "openai":
        _openai_voice(text, voice, target, rate)
    elif engine == "groq":
        _groq_voice(text, voice, target, rate)
    elif engine == "deepgram":
        _deepgram_voice(text, voice, target, rate)
    else:
        raise AudioError(f"Unknown voice engine {engine!r}.")
    if not target.is_file() or target.stat().st_size == 0:
        raise AudioError("Voice synthesis produced no audio.")
    if flac:
        _to_flac(target, output, mono=True)
        try:
            target.unlink()
        except OSError:
            pass
        if not output.is_file() or output.stat().st_size == 0:
            raise AudioError("Voice cache conversion produced no audio.")
        return output
    return target


def voice_sample(
    engine: str,
    voice: str,
    text: str,
    cache_dir: Path,
    rate: float = 1.0,
) -> Path:
    key = _text_hash(engine, voice, f"{rate:.2f}", text)
    target = _voice_cache(cache_dir, key, ".wav")
    if target.is_file() and target.stat().st_size > 512:
        return target
    return synthesize_line(engine, voice, text, target, rate=rate)


# ---------------------------------------------------------------- translation


def _language_name(code: str) -> str:
    return LANGUAGE_NAMES.get((code or "").lower().split("-")[0], code or "")


def _apple_helper() -> Path | None:
    if sys.platform != "darwin":
        return None
    source = ROOT / "tools" / "translate_apple.swift"
    binary = ROOT / "bin" / "translate_apple"
    if binary.is_file() and (not source.is_file() or binary.stat().st_mtime >= source.stat().st_mtime):
        return binary
    swiftc = shutil.which("swiftc")
    if not swiftc or not source.is_file():
        return None
    binary.parent.mkdir(parents=True, exist_ok=True)
    try:
        _run([swiftc, "-O", str(source), "-o", str(binary)], timeout=300)
    except (AudioError, OSError, subprocess.SubprocessError):
        return None
    return binary if binary.is_file() else None


def _translate_apple(
    lines: list[str], source: str, target: str, target_name: str,
) -> list[str] | None:
    binary = _apple_helper()
    if not binary:
        return None
    payload = json.dumps({
        "source": source, "target": target,
        "targetName": target_name, "lines": lines,
    }).encode("utf-8")
    try:
        result = subprocess.run(
            [str(binary)], input=payload, capture_output=True, timeout=600,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if isinstance(data, list) and len(data) == len(lines):
        return [str(item) for item in data]
    return None


def _translate_ollama(lines: list[str], source: str, target_name: str) -> list[str] | None:
    url = os.environ.get("VIBECUT_LLM_URL")
    if not url:
        return None
    model = os.environ.get("VIBECUT_LLM_MODEL", "llama3.1")
    numbered = "\n".join(f"{index + 1}. {line}" for index, line in enumerate(lines))
    prompt = (
        f"Translate every numbered line to {target_name}. Keep the same line count "
        "and order. Reply with a JSON array of strings only.\n" + numbered
    )
    payload = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
        "options": {"temperature": 0.2},
    }).encode("utf-8")
    request = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None
    text = str(data.get("response") or data.get("message", {}).get("content") or "")
    match = re.search(r"\[.*\]", text, re.S)
    if not match:
        return None
    try:
        values = json.loads(match.group(0))
    except ValueError:
        return None
    if isinstance(values, list) and len(values) == len(lines):
        return [str(item) for item in values]
    return None


def translate_check(source: str, target: str) -> dict:
    """Report which translation path is ready for one language pair."""
    source_code = (source or "").split("-")[0]
    target_code = (target or "").split("-")[0]
    if not source_code or not target_code or source_code == target_code:
        return {"same": True, "apple": {"status": "not-needed", "framework": True},
                "argos": {"installed": True, "module": _module("argostranslate")},
                "ollama": {"available": bool(os.environ.get("VIBECUT_LLM_URL"))}}
    apple = {"status": "unavailable", "framework": False}
    binary = _apple_helper()
    if binary:
        try:
            result = subprocess.run(
                [str(binary), "--check", source_code, target_code],
                capture_output=True, timeout=60,
            )
            if result.returncode == 0:
                apple = json.loads(result.stdout.decode("utf-8"))
        except (OSError, subprocess.SubprocessError, ValueError):
            apple = {"status": "unavailable", "framework": False}
    return {
        "same": False,
        "apple": apple,
        "marian": {
            "available": _module("transformers") and _module("torch"),
            "model": f"Helsinki-NLP/opus-mt-{source_code}-{target_code}",
            "size_mb": 300,
        },
        "argos": {
            "installed": argos_pair_ready(source_code, target_code),
            "module": _module("argostranslate"),
        },
        "ollama": {"available": bool(os.environ.get("VIBECUT_LLM_URL"))},
        "order": _provider_order(source_code, target_code, "auto"),
    }


def translate_ready(check: dict) -> bool:
    if not check or check.get("same"):
        return True
    if check.get("apple", {}).get("status") == "installed":
        return True
    if check.get("marian", {}).get("available"):
        return True
    if check.get("argos", {}).get("installed"):
        return True
    if check.get("ollama", {}).get("available"):
        return True
    return False


ARGOS_STATE: dict = {"running": False, "message": "idle", "error": None}


def argos_pair_ready(source: str, target: str) -> bool:
    if not _module("argostranslate"):
        return False
    try:
        import argostranslate.package as argos_package  # noqa: PLC0415

        source_code = (source or "en").split("-")[0]
        target_code = (target or "en").split("-")[0]
        return any(
            package.from_code == source_code and package.to_code == target_code
            for package in argos_package.get_installed_packages()
        )
    except Exception:  # noqa: BLE001
        return False


def ensure_argos_pair(source: str, target: str) -> None:
    """Download and install the offline Argos language pair (~100-300 MB)."""
    import argostranslate.package as argos_package  # noqa: PLC0415

    source_code = (source or "en").split("-")[0]
    target_code = (target or "en").split("-")[0]
    if argos_pair_ready(source_code, target_code):
        return
    ARGOS_STATE.update(running=True, message=f"Fetching {source_code}→{target_code} package", error=None)
    try:
        argos_package.update_package_index()
        available = argos_package.get_available_packages()
        match = next(
            (p for p in available if p.from_code == source_code and p.to_code == target_code),
            None,
        )
        if match is None:
            raise AudioError(f"Argos has no offline package for {source_code}→{target_code}.")
        ARGOS_STATE["message"] = f"Downloading {match.package_version}"
        path = match.download()
        argos_package.install_from_path(path)
        ARGOS_STATE["message"] = f"{source_code}→{target_code} ready"
    finally:
        ARGOS_STATE["running"] = False


def install_argos() -> None:
    """pip install argostranslate, used by the UI install button."""
    ARGOS_STATE.update(running=True, message="Installing argostranslate", error=None)
    try:
        _run([sys.executable, "-m", "pip", "install", "--quiet", "argostranslate"], timeout=900)
        ARGOS_STATE["message"] = "argostranslate installed"
    except AudioError as exc:
        ARGOS_STATE.update(error=str(exc)[:400])
        raise
    finally:
        ARGOS_STATE["running"] = False


def _translate_argos(lines: list[str], source: str, target: str) -> list[str] | None:
    if not _module("argostranslate"):
        return None
    try:
        import argostranslate.translate as argos_translate  # noqa: PLC0415

        source_code = (source or "en").split("-")[0]
        target_code = (target or "en").split("-")[0]
        try:
            return [argos_translate.translate(line, source_code, target_code) for line in lines]
        except Exception:  # noqa: BLE001
            ensure_argos_pair(source_code, target_code)
            return [argos_translate.translate(line, source_code, target_code) for line in lines]
    except Exception:  # noqa: BLE001
        return None


_APPLE_STATUS_CACHE: dict[tuple[str, str], tuple[float, str]] = {}


def apple_pair_status(source: str, target: str) -> str:
    """installed | supported | unsupported | unavailable (cached 5 min)."""
    source_code = (source or "en").split("-")[0]
    target_code = (target or "en").split("-")[0]
    key = (source_code, target_code)
    cached = _APPLE_STATUS_CACHE.get(key)
    now = time.time()
    if cached and now - cached[0] < 300:
        return cached[1]
    status = "unavailable"
    binary = _apple_helper()
    if binary:
        if source_code == target_code:
            status = "installed"
        else:
            try:
                result = subprocess.run(
                    [str(binary), "--check", source_code, target_code],
                    capture_output=True, timeout=60,
                )
                if result.returncode == 0:
                    status = str(json.loads(result.stdout.decode("utf-8")).get("status") or "unavailable")
            except (OSError, subprocess.SubprocessError, ValueError):
                status = "unavailable"
    _APPLE_STATUS_CACHE[key] = (now, status)
    return status


def _translate_opencode(lines: list[str], source: str, target: str) -> list[str] | None:
    if not opencode_available():
        return None
    prompt = (
        f"Translate these {len(lines)} subtitle lines into {_language_name(target)}. "
        "Keep the same count and order, natural spoken style, JSON array only:\n"
        + json.dumps(lines, ensure_ascii=False)
    )
    raw = _opencode_text(prompt, json_mode=False, max_tokens=1600)
    if not raw:
        return None
    match = re.search(r"\[.*\]", raw, re.S)
    if not match:
        return None
    try:
        values = json.loads(match.group(0))
    except ValueError:
        return None
    if not isinstance(values, list) or len(values) != len(lines):
        return None
    return [str(value) for value in values]


def _translate_marian(lines: list[str], source: str, target: str) -> list[str] | None:
    """Small on-device seq2seq model, ~300 MB per language pair."""
    if not (_module("transformers") and _module("torch")):
        return None
    source_code = (source or "en").split("-")[0]
    target_code = (target or "en").split("-")[0]
    model_id = f"Helsinki-NLP/opus-mt-{source_code}-{target_code}"
    try:
        import torch  # noqa: PLC0415
        from transformers import pipeline  # noqa: PLC0415

        device = "mps" if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available() else "cpu"
        translator = pipeline("translation", model=model_id, device=device)
        results = translator(lines, max_length=400)
        texts = [str(item.get("translation_text") or "").strip() for item in results]
        return texts if len(texts) == len(lines) else None
    except Exception:  # noqa: BLE001
        return None


def _ready_providers(source: str, target: str) -> list[str]:
    ready: list[str] = []
    if argos_pair_ready(source, target):
        ready.append("argos")
    if apple_pair_status(source, target) == "installed":
        ready.append("apple_fm")
    if _module("transformers") and _module("torch"):
        ready.append("marian")
    if os.environ.get("VIBECUT_LLM_URL"):
        ready.append("ollama")
    return ready


def _rewrite_candidates() -> list[str]:
    """Rewrite-specific order: configured cloud model, local models, rules."""
    order: list[str] = []
    settings = settings_store.load_settings().get("opencode") or {}
    if opencode_available() and settings.get("use_rewrite", True):
        order.append("opencode")
    if mlx_lm_available():
        order.append("mlx")
    if os.environ.get("VIBECUT_LLM_URL"):
        order.append("ollama")
    order.append("rules")
    return order


def _provider_order(source: str, target: str, provider: str) -> list[str]:
    if provider and provider != "auto":
        return [provider]
    order: list[str] = []
    settings = settings_store.load_settings().get("opencode") or {}
    if settings.get("use_translate") and opencode_available():
        order.append("opencode")
    order.extend(_ready_providers(source, target))
    # Anything that might download or install goes after what already works.
    for candidate in ("argos", "marian", "apple_fm", "ollama"):
        if candidate not in order:
            order.append(candidate)
    return order


def translate_lines(
    lines: list[str],
    source: str,
    target: str,
    provider: str = "auto",
) -> list[str]:
    if not target or target == source:
        return list(lines)
    target_name = _language_name(target)
    source_code = (source or "en").split("-")[0]
    target_code = (target or "en").split("-")[0]
    memo: dict[str, str] = {}
    missing: list[str] = []
    requested = provider or "auto"
    for line in lines:
        cached = _memo_get(source_code, target_code, line, requested)
        if cached:
            memo[line] = cached
        elif line not in missing:
            missing.append(line)
    if missing:
        errors: list[str] = []
        for candidate in _provider_order(source_code, target_code, provider):
            if candidate == "opencode":
                result = _translate_opencode(missing, source_code, target_code)
            elif candidate == "apple_fm":
                result = _translate_apple(missing, source_code, target_code, target_name)
            elif candidate == "ollama":
                result = _translate_ollama(missing, source_code, target_name)
            elif candidate == "marian":
                result = _translate_marian(missing, source_code, target_code)
            elif candidate == "argos":
                result = _translate_argos(missing, source_code, target_code)
            else:
                result = None
            if result:
                for original, translated in zip(missing, result):
                    memo[original] = translated
                    _memo_put(source_code, target_code, original, translated, requested)
                break
            errors.append(candidate)
        else:
            hint = (
                " OpenCode Go is available: enable Translation in Setup → Intelligence "
                "or pick OpenCode as the Translate engine."
                if opencode_available()
                else " Keep one of: Apple Translation language pack "
                "(System Settings → General → Language & Region), argostranslate, "
                "Marian (pip install transformers torch), or Ollama (VIBECUT_LLM_URL)."
            )
            raise AudioError(
                "No translation provider worked (tried: "
                + ", ".join(errors)
                + ")." + hint
            )
    return [memo.get(line) or line for line in lines]


# ---------------------------------------------------------------- separation


def stem_cache_path(fingerprint: str, stem: str = "no_vocals") -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", fingerprint or "source")[:80]
    return CACHE / "stems" / safe / f"{stem}.flac"


def separate_vocals(
    source: str,
    fingerprint: str,
    cancel_event: threading.Event | None = None,
) -> Path:
    """Return the instrumental stem (original music + SFX, no voice).

    Stored as FLAC (~half of PCM) and the Demucs scratch folder is removed so
    every separation does not leak the vocals stem.
    """
    cached = stem_cache_path(fingerprint, "no_vocals")
    if cached.is_file() and cached.stat().st_size > 1024:
        return cached
    if not demucs_available():
        raise AudioError("Demucs is not installed. pip install demucs")
    output_dir = CACHE / "stems" / "run"
    shutil.rmtree(output_dir, ignore_errors=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    base = [
        sys.executable, "-m", "demucs", "--two-stems=vocals",
        "-n", "htdemucs", "--shifts", "0", "-j", "4",
        "-o", str(output_dir), source,
    ]
    if not _module("demucs") and shutil.which("demucs"):
        base = [
            "demucs", "--two-stems=vocals", "-n", "htdemucs",
            "--shifts", "0", "-j", "4", "-o", str(output_dir), source,
        ]
    try:
        _run([*base, "-d", "mps"], timeout=3600, cancel_event=cancel_event)
    except AudioError:
        if cancel_event is not None and cancel_event.is_set():
            raise
        _run(base, timeout=3600, cancel_event=cancel_event)
    produced = sorted(output_dir.glob("htdemucs/*/no_vocals.wav"))
    if not produced:
        raise AudioError("Demucs finished but no instrumental stem was found.")
    cached.parent.mkdir(parents=True, exist_ok=True)
    _run([
        _ffmpeg(), "-y", "-v", "error", "-i", str(produced[-1]),
        "-ar", "48000", "-ac", "2", "-c:a", "flac", str(cached),
    ], timeout=900, cancel_event=cancel_event)
    legacy = cached.with_suffix(".wav")
    if legacy.is_file():
        try:
            legacy.unlink()
        except OSError:
            pass
    shutil.rmtree(output_dir, ignore_errors=True)
    return cached


# ---------------------------------------------------------------- music


def list_music(source: str) -> list[dict]:
    directory = MUSIC_DIRS.get(source)
    tracks: list[dict] = []
    if not directory or not directory.is_dir():
        return tracks
    for path in sorted(directory.rglob("*")):
        if path.suffix.lower() not in {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}:
            continue
        name = path.stem.lower()
        moods = [word for word in MOOD_WORDS if word in name]
        tracks.append({
            "id": str(path),
            "name": path.stem,
            "moods": moods,
            "size": path.stat().st_size,
            "license": asset_license(path),
        })
    return tracks


def scene_moods(scenes: list[dict], clips: list[dict]) -> list[str]:
    """Derive simple moods from the beats that actually made the cut."""
    by_id = {scene["id"]: scene for scene in scenes}
    motion = 0
    calm = 0
    warm = 0
    for clip in clips:
        scene = by_id.get(clip.get("scene"))
        if not scene:
            continue
        tags = scene.get("tags") or []
        if "motion" in tags:
            motion += 1
        if scene.get("dur", 0) >= 3.0:
            calm += 1
        if scene.get("face") or "subject" in tags:
            warm += 1
    total = max(1, len(clips))
    moods: list[str] = []
    if motion / total >= 0.35:
        moods += ["upbeat", "energetic", "groove"]
    if calm / total >= 0.25:
        moods += ["calm", "ambient", "soft"]
    if warm / total >= 0.35:
        moods += ["warm", "cinematic", "piano"]
    if not moods:
        moods = ["ambient", "calm", "lofi"]
    return moods


def pick_music(tracks: list[dict], moods: list[str]) -> dict | None:
    if not tracks:
        return None
    for mood in moods:
        for track in tracks:
            if mood in (track.get("moods") or []):
                return track
    return tracks[0]


def resolve_music_track(scenes: list[dict], clips: list[dict], music_plan: dict) -> Path | None:
    """Pick one library/CC0/generated track without generating anything."""
    source = str(music_plan.get("source") or "none")
    if source not in MUSIC_DIRS:
        return None
    track_id = str(music_plan.get("track") or "")
    if track_id and Path(track_id).is_file():
        return Path(track_id)
    tracks = list_music(source)
    moods = music_plan.get("moods") or scene_moods(scenes, clips)
    picked = pick_music(tracks, moods)
    return Path(picked["id"]) if picked else None


def music_prompt(moods: list[str], target: float) -> str:
    primary = moods[0] if moods else "ambient"
    return (
        f"{primary} background music bed for a short vertical video, "
        f"soft, no vocals, clean loop, {int(max(8, min(47, target)))} seconds"
    )


def generate_music(
    model: str,
    prompt: str,
    seconds: float,
    cancel_event: threading.Event | None = None,
) -> Path:
    key = _text_hash("music", model, prompt, f"{seconds:.0f}")
    target = CACHE / "music" / f"{key}.wav"
    if target.is_file() and target.stat().st_size > 1024:
        return target
    if not stable_audio_available():
        raise AudioError(
            "Stable Audio is not installed. pip install stable-audio-tools "
            "(first run downloads ~2 GB for Small, ~6 GB for 1.0)."
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    worker = ROOT / "tools" / "music_generate.py"
    _run([
        sys.executable, str(worker),
        "--model", model, "--prompt", prompt,
        "--seconds", f"{seconds:.1f}", "--out", str(target),
    ], timeout=3600, cancel_event=cancel_event)
    if not target.is_file() or target.stat().st_size <= 1024:
        raise AudioError("Stable Audio produced no file.")
    save_generated_asset(target, model, prompt, seconds)
    return target


# ---------------------------------------------------------------- mix


def _music_loop(
    path: Path,
    total: float,
    gain_db: float,
    tmp: Path,
    expr: str | None = None,
    offset: float = 0.0,
) -> Path:
    output = tmp / "music_trim.wav"
    seek = ["-ss", f"{offset:.3f}"] if offset > 0.01 else []
    audio_filter = expr or f"volume={gain_db}dB"
    _run([
        _ffmpeg(), "-y", "-v", "error", *seek, "-stream_loop", "-1", "-i", str(path),
        "-t", f"{total:.6f}", "-ar", "48000", "-ac", "2",
        "-af", audio_filter,
        "-c:a", "pcm_s16le", str(output),
    ])
    return output


CJK_RE = re.compile(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]")
CJK_FILLERS = ("嗯", "呃", "额", "那个，", "那个,", "然后，", "然后,", "就是，", "就是,")
LATIN_FILLERS = ("um", "uh", "erm", "hmm", "you know", "i mean")


def clean_line(text: str) -> str:
    """Strip stage directions, timestamps, filler starts and weird separators."""
    value = str(text or "")
    value = value.replace("·", " ").replace("|", " ").replace("♪", " ")
    value = re.sub(r"\[[^\]]{0,24}\]", " ", value)
    value = re.sub(r"[（(][^）)]{0,16}[）)]", " ", value)
    value = re.sub(r"\d{1,2}:\d{2}(:\d{2})?", " ", value)
    value = " ".join(value.split())
    for filler in LATIN_FILLERS:
        while True:
            value = value.lstrip()
            lowered = value.lower()
            if lowered.startswith(filler) and (
                len(lowered) == len(filler) or not lowered[len(filler)].isalpha()
            ):
                value = value[len(filler):]
            else:
                break
    for filler in CJK_FILLERS:
        while True:
            value = value.lstrip()
            if value.startswith(filler):
                value = value[len(filler):]
            else:
                break
    return value.strip(" ,，。.!！?？;；:：、~-")


def normalize_line(text: str) -> str:
    return re.sub(r"[\W_]+", "", str(text or "").lower(), flags=re.UNICODE)


def estimate_seconds(text: str, rate: float = 1.0) -> float:
    """Rough speaking time: CJK ~4.6 chars/s, latin ~14 chars/s at rate 1."""
    value = str(text or "")
    cjk = len(CJK_RE.findall(value))
    latin = max(0, len(value) - cjk)
    rate = max(0.5, float(rate or 1.0))
    return max(0.3, cjk / (4.6 * rate) + latin / (14.0 * rate))


def _char_cut(text: str, seconds: float, rate: float) -> str:
    """Hard cut that never lands inside a word."""
    chars_per_second = 4.6 if CJK_RE.search(text) else 14.0
    limit = max(4, int(seconds * chars_per_second * rate))
    cut = text[:limit]
    if not CJK_RE.search(cut) and " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,，。.!！?？;；:：、")


def trim_to_seconds(text: str, seconds: float, rate: float = 1.0) -> str:
    """Keep whole clauses while they fit the slot, then fall back to a cut."""
    value = clean_line(text)
    if not value:
        return ""
    seconds = max(0.5, float(seconds or 0.0))
    if estimate_seconds(value, rate) <= seconds:
        return value
    parts = [part.strip() for part in re.split(r"(?<=[。！？!?;；])|(?<=[,，、])", value)]
    parts = [part for part in parts if part]
    kept: list[str] = []
    for part in parts:
        candidate = " ".join(kept + [part]).strip()
        if kept and estimate_seconds(candidate, rate) > seconds:
            break
        kept.append(part)
        if estimate_seconds(" ".join(kept), rate) > seconds:
            break
    result = " ".join(kept).strip(" ,，。.!！?？;；:：、")
    if result and estimate_seconds(result, rate) > seconds:
        result = _char_cut(result, seconds, rate)
    if not result:
        result = _char_cut(value, seconds, rate)
    return result


def scene_emotion(scene: dict, clip_duration: float, base_rate: float = 1.0) -> tuple[str, float]:
    """Pick a small emotional tint so the read matches the beat."""
    tags = set(scene.get("tags") or [])
    audio_score = float(scene.get("audio_score") or 0.0)
    if "motion" in tags or audio_score >= 72:
        label, factor = "energetic", 1.10
    elif clip_duration >= 3.4 or float(scene.get("dur") or 0.0) >= 4.0:
        label, factor = "calm", 0.94
    elif scene.get("face") or "subject" in tags:
        label, factor = "warm", 1.0
    elif "text" in tags:
        label, factor = "punchy", 1.06
    else:
        label, factor = "neutral", 1.0
    rate = max(0.6, min(1.6, float(base_rate or 1.0) * factor))
    return label, round(rate, 3)


def load_transcript_segments(job_dir: Path) -> list[dict]:
    try:
        import pipeline  # noqa: PLC0415

        return pipeline.read_transcript(job_dir) or []
    except Exception:  # noqa: BLE001
        return []


def window_text(segments: list[dict], start: float, end: float) -> str:
    """Complete sentences covering a beat, not the trimmed fragment."""
    if not segments:
        return ""
    start = float(start or 0.0)
    end = float(end or start)
    parts = [
        segment["text"] for segment in segments
        if min(segment["end"], end) - max(segment["start"], start) > 0.15
    ]
    return clean_line(" ".join(parts))


BRIEFS = CACHE / "brief"


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。！？])\s+|\n+", str(text or ""))
    return [part.strip() for part in parts if len(part.strip()) > 12]


def _tokens(text: str) -> list[str]:
    return [token for token in re.findall(r"[\w\u3400-\u9fff]{2,}", str(text or "").lower())]


def retrieve_lines(text: str, query: str, limit: int = 6) -> list[str]:
    """BM25-lite retrieval so a small model only sees the relevant transcript."""
    sentences = _sentences(text)
    if len(sentences) <= limit:
        return sentences
    import math as _math  # noqa: PLC0415

    docs = [_tokens(sentence) for sentence in sentences]
    query_tokens = set(_tokens(query))
    if not query_tokens:
        return sentences[:limit]
    df: dict[str, int] = {}
    for doc in docs:
        for token in set(doc):
            df[token] = df.get(token, 0) + 1
    total = len(docs)
    average = sum(len(doc) for doc in docs) / max(1, total)
    scored = []
    for sentence, doc in zip(sentences, docs):
        length = max(1, len(doc))
        score = 0.0
        counts: dict[str, int] = {}
        for token in doc:
            counts[token] = counts.get(token, 0) + 1
        for token in query_tokens:
            frequency = counts.get(token, 0)
            if not frequency:
                continue
            idf = _math.log(1 + (total - df.get(token, 0) + 0.5) / (df.get(token, 0) + 0.5))
            score += idf * (frequency * 2.5) / (frequency + 1.5 * (0.25 + 0.75 * length / max(1.0, average)))
        scored.append((score, sentence))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [sentence for score, sentence in scored[:limit] if score > 0] or sentences[:limit]


def _brief_path(text: str, provider: str) -> Path:
    digest = hashlib.sha1(f"v1|{provider}|{text}".encode("utf-8")).hexdigest()[:24]
    return BRIEFS / digest[:2] / f"{digest}.json"


def story_brief(text: str, target: str, provider: str = "auto") -> dict | None:
    """Small-model summary: audience, promise, proof, tone, hook and payoff ideas."""
    text = str(text or "").strip()
    if len(text) < 80:
        return None
    cached = _brief_path(text, provider)
    if cached.is_file():
        try:
            return json.loads(cached.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    prompt = (
        "Read the transcript of a short vertical video and reply with JSON only:\n"
        '{"topic": "...", "audience": "...", "promise": "...", "proof": ["..."], '
        '"tone": "...", "hook_idea": "...", "payoff_idea": "...", "key_claims": ["..."]}\n'
        f"Write the values in {_language_name(target)}.\nTRANSCRIPT:\n{text[:4000]}"
    )
    raw = _llm_text(prompt, provider)
    if not raw:
        return None
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        return None
    try:
        brief = json.loads(match.group(0))
    except ValueError:
        return None
    if not isinstance(brief, dict):
        return None
    try:
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(brief, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return brief


def _llm_text(prompt: str, provider: str = "auto") -> str | None:
    """One model call: OpenCode Go first, then MLX, then Ollama."""
    settings = settings_store.load_settings().get("opencode") or {}
    cloud_ok = (
        provider in {"opencode", "auto", "argos", "marian", "apple_fm", ""}
        and settings.get("use_brief", True)
        and opencode_available()
    )
    if cloud_ok:
        text = _opencode_text(prompt, json_mode=True)
        if text:
            return text
        if provider == "opencode":
            return None
    if provider in {"mlx", "auto"} and mlx_lm_available():
        text = _mlx_text(prompt)
        if text:
            return text
        if provider == "mlx":
            return None
    url = os.environ.get("VIBECUT_LLM_URL")
    if not url:
        return None
    model = os.environ.get("VIBECUT_LLM_MODEL", "qwen2.5:3b")
    payload = json.dumps({
        "model": model, "prompt": prompt, "stream": False, "format": "json",
        "options": {"temperature": 0.4},
    }).encode("utf-8")
    request = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None
    return str(data.get("response") or data.get("message", {}).get("content") or "") or None


def _mlx_text(prompt: str) -> str | None:
    worker = ROOT / "tools" / "rewrite_mlx.py"
    if not worker.is_file():
        return None
    model = os.environ.get(
        "VIBECUT_MLX_REWRITE_MODEL", "mlx-community/Qwen2.5-3B-Instruct-4bit",
    )
    try:
        result = subprocess.run(
            [sys.executable, str(worker), "--model", model],
            input=json.dumps({"prompt": prompt, "system": "You write short video voice overs. Reply with JSON when asked."}),
            capture_output=True, text=True, timeout=1800,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or "").strip() or None


OPENCODE_PROVIDER = "opencode-go"
OPENCODE_URL = "https://opencode.ai/inference/go/openai/v1/chat/completions"
OPENCODE_DEFAULT_MODEL = "deepseek-v4.1-flash"
OPENCODE_DEFAULT_VARIANT = "low"
OPENCODE_LAST_ERROR = ""


def opencode_bin() -> str | None:
    path = os.environ.get("VIBECUT_OPENCODE_BIN") or shutil.which("opencode")
    if path:
        return path
    candidate = Path.home() / ".opencode" / "bin" / "opencode"
    return str(candidate) if candidate.is_file() else None


def opencode_key() -> str:
    return settings_store.get_secret("opencode")


def opencode_mode() -> str:
    settings = settings_store.load_settings().get("opencode") or {}
    if not settings.get("enabled", True):
        return "off"
    if opencode_key():
        return "api"
    if opencode_bin():
        return "local"
    return "off"


def opencode_available() -> bool:
    settings = settings_store.load_settings().get("opencode") or {}
    return (bool(opencode_key()) or bool(opencode_bin())) and bool(settings.get("enabled", True))


def opencode_model() -> str:
    settings = settings_store.load_settings().get("opencode") or {}
    return str(settings.get("model") or OPENCODE_DEFAULT_MODEL)


def opencode_variant() -> str:
    settings = settings_store.load_settings().get("opencode") or {}
    variant = str(settings.get("variant") or OPENCODE_DEFAULT_VARIANT).lower()
    return variant if variant in {"low", "high", "max"} else OPENCODE_DEFAULT_VARIANT


def _opencode_api(args: list[str], body: dict | None = None, allow_empty: bool = False) -> dict | None:
    """Call the local OpenCode service with the user's own stored login."""
    global OPENCODE_LAST_ERROR
    binary = opencode_bin()
    if not binary:
        OPENCODE_LAST_ERROR = "OpenCode CLI not found. Install OpenCode and sign in to OpenCode Go."
        return None
    command = [binary, "api", *args]
    if body is not None:
        command.extend(["-d", json.dumps(body, ensure_ascii=False)])
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=240)
    except (OSError, subprocess.SubprocessError) as exc:
        OPENCODE_LAST_ERROR = str(exc)[:240]
        return None
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        OPENCODE_LAST_ERROR = (message[-240:] or f"opencode api exited {result.returncode}")
        return None
    output = (result.stdout or "").strip()
    if not output:
        if allow_empty:
            return {}
        OPENCODE_LAST_ERROR = "OpenCode returned no output."
        return None
    try:
        return json.loads(output)
    except ValueError:
        start = output.find("{")
        end = output.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(output[start:end + 1])
            except ValueError:
                pass
    OPENCODE_LAST_ERROR = f"Could not parse OpenCode output: {output[:160]}"
    return None


def _opencode_http_text(prompt: str, max_tokens: int = 1200) -> str | None:
    """Direct OpenCode Go API using the project's own key."""
    global OPENCODE_LAST_ERROR
    key = opencode_key()
    if not key:
        return None
    body = {
        "model": opencode_model(),
        "messages": [
            {"role": "system", "content": "You write short vertical video voice overs. Reply with JSON when asked."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "max_tokens": max_tokens,
        "reasoning_effort": opencode_variant(),
    }
    request = urllib.request.Request(
        OPENCODE_URL,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "VibeCut/0.8.0",
            "x-opencode-session": "vibecut-" + hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:24],
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        OPENCODE_LAST_ERROR = f"Direct API: {str(exc)[:220]}"
        return None
    choices = data.get("choices") or []
    if not choices:
        OPENCODE_LAST_ERROR = "Direct API returned no choices."
        return None
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(str(part.get("text") or "") for part in content if isinstance(part, dict))
    value = str(content or "").strip()
    if value:
        OPENCODE_LAST_ERROR = ""
        return value
    OPENCODE_LAST_ERROR = "Direct API returned an empty reply."
    return None


def _opencode_text(prompt: str, json_mode: bool = False, max_tokens: int = 1200) -> str | None:
    """Generate text through OpenCode Go / DeepSeek V4.1 Flash at low reasoning.

    A fresh session pins the model and the ``low`` variant, then ``/generate``
    returns plain text. The session is removed afterwards. The stored OpenCode
    login is used, so no API key is copied into VibeCut.
    """
    global OPENCODE_LAST_ERROR
    OPENCODE_LAST_ERROR = ""
    if not opencode_available():
        OPENCODE_LAST_ERROR = "OpenCode is not installed or OpenCode Go is disabled."
        return None
    if opencode_key():
        # A project key is exclusive: never borrow the shared local login when
        # this key is configured but fails.
        return _opencode_http_text(prompt, max_tokens=max_tokens)
    created = _opencode_api(["post", "/api/session"], {
        "title": "VibeCut rewrite",
        "model": {
            "id": opencode_model(),
            "providerID": OPENCODE_PROVIDER,
            "variant": opencode_variant(),
        },
    })
    session_id = str(((created or {}).get("data") or {}).get("id") or "")
    if not session_id:
        if not OPENCODE_LAST_ERROR:
            OPENCODE_LAST_ERROR = "OpenCode could not create a session."
        return None
    try:
        generated = _opencode_api(
            ["post", f"/api/session/{session_id}/generate"],
            {"prompt": prompt},
        )
    finally:
        _opencode_api(["delete", f"/api/session/{session_id}"], allow_empty=True)
    value = str(((generated or {}).get("data") or {}).get("text") or "").strip()
    if value:
        OPENCODE_LAST_ERROR = ""
        return value
    if not OPENCODE_LAST_ERROR:
        OPENCODE_LAST_ERROR = "OpenCode returned an empty reply."
    return None


def _rewrite_prompt(
    script: list[dict], source: str, target: str, mode: str, literal: list[str],
    context: dict | None = None,
) -> str:
    rows = []
    context_beats = (context or {}).get("beats") or []
    for index, line in enumerate(script):
        source_line = ""
        if index < len(context_beats):
            source_line = str(context_beats[index].get("source") or "")
        rows.append({
            "beat": index,
            "role": str(line.get("role") or "beat"),
            "seconds": round(float(line.get("duration") or 0.0) - 0.25, 2),
            "source_line": source_line,
            "literal": literal[index],
        })
    context_text = str(
        (context or {}).get("target_text") or (context or {}).get("full_text") or ""
    ).strip()
    style = {
        "smooth": "natural, flowing, conversational",
        "viral": "punchy: hook grabs in the first words, one idea per beat, payoff ends with a light call to action",
    }.get(mode, "faithful")
    brief = (context or {}).get("brief")
    parts = [
        f"You write a {len(rows)}-beat short vertical video voice over in {_language_name(target)}.",
        f"Style: {style}. Keep every fact and number, invent nothing.",
        "Each line must fit its seconds budget at normal pace. Reply with a JSON array of strings only.",
    ]
    if brief:
        parts.append("STORY BRIEF:\n" + json.dumps(brief, ensure_ascii=False))
    if context_text and (context or {}).get("full_context"):
        parts.append("FULL TRANSCRIPT:\n" + context_text[:4000])
    if context_text:
        query = " ".join(str(row["source_line"]) or str(row["literal"]) for row in rows)
        relevant = retrieve_lines(context_text, query, limit=8)
        if relevant:
            parts.append("RELEVANT TRANSCRIPT LINES:\n" + "\n".join(relevant))
    parts.append("SELECTED BEATS:\n" + json.dumps(rows, ensure_ascii=False))
    return "\n".join(parts)


def _rewrite_opencode(
    script: list[dict], source: str, target: str, mode: str, literal: list[str],
    context: dict | None = None,
) -> list[str] | None:
    settings = settings_store.load_settings().get("opencode") or {}
    if mode == "literal" or not settings.get("use_rewrite", True) or not opencode_available():
        return None
    raw = _opencode_text(
        _rewrite_prompt(script, source, target, mode, literal, context),
        json_mode=True,
    )
    if not raw:
        return None
    match = re.search(r"\[.*\]", raw, re.S)
    if not match:
        return None
    try:
        values = json.loads(match.group(0))
    except ValueError:
        return None
    if not isinstance(values, list) or len(values) != len(script):
        return None
    cleaned: list[str] = []
    for index, value in enumerate(values):
        text = str(value).strip()
        rate = float(script[index].get("rate") or 1.0)
        # The TTS bed can compress up to 1.35x, so a minor overshoot must not
        # cut a fact off the end of the line.
        budget = max(1.0, float(script[index].get("duration") or 1.0) + 0.25)
        if estimate_seconds(text, rate) > budget:
            text = trim_to_seconds(text, budget, rate)
        if not text:
            return None
        cleaned.append(text)
    return cleaned


def _rewrite_mlx(
    script: list[dict], source: str, target: str, mode: str, literal: list[str],
    context: dict | None = None,
) -> list[str] | None:
    """Small local model rewrite (MLX worker or Apple FM via the same JSON contract)."""
    if mode == "literal":
        return None
    if not mlx_lm_available():
        return None
    prompt = _rewrite_prompt(script, source, target, mode, literal, context)
    raw = _llm_text(prompt, provider="mlx")
    if not raw:
        return None
    match = re.search(r"\[.*\]", raw, re.S)
    if not match:
        return None
    try:
        values = json.loads(match.group(0))
    except ValueError:
        return None
    if not isinstance(values, list) or len(values) != len(script):
        return None
    fits = all(
        estimate_seconds(str(value), float(script[index].get("rate") or 1.0))
        <= max(1.0, float(script[index].get("duration") or 1.0))
        for index, value in enumerate(values)
    )
    return [str(value).strip() for value in values] if fits else None


def transcript_context(
    segments: list[dict],
    clips: list[dict],
    scenes: list[dict],
    source_lang: str,
    cap_chars: int | None = None,
    target_lang: str | None = None,
    translate_provider: str = "auto",
    brief_provider: str = "auto",
    rewrite_provider: str = "auto",
) -> dict:
    """Whole-video context plus one complete source line per selected beat."""
    if cap_chars is None:
        try:
            cap_chars = int(os.environ.get("VIBECUT_REWRITE_CONTEXT_CHARS", "6000"))
        except ValueError:
            cap_chars = 6000
    by_id = {scene["id"]: scene for scene in scenes}
    beats = []
    for clip in clips:
        scene = by_id.get(clip.get("scene")) or {}
        beat_text = window_text(segments, scene.get("start"), scene.get("end"))
        if not beat_text:
            beat_text = clean_line(scene.get("speech") or scene.get("ocr") or "")
        beats.append({
            "scene": clip.get("scene"),
            "role": clip.get("role") or "beat",
            "seconds": round(max(0.5, float(clip.get("duration") or clip.get("dur") or 0.0) - 0.25), 2),
            "source": beat_text[:400],
        })
    full = " ".join(segment["text"] for segment in segments)
    full = " ".join(full.split())
    if cap_chars > 0 and len(full) > cap_chars:
        full = full[:cap_chars] + "…"
    context = {
        "language": (source_lang or "en").split("-")[0],
        "full_text": full,
        "beats": beats,
    }
    target = str(target_lang or "").split("-")[0]
    if target and target != context["language"]:
        try:
            translated = translate_lines(
                [segment["text"] for segment in segments],
                context["language"], target, translate_provider,
            )
            target_text = " ".join(part for part in translated if part)
            target_text = " ".join(target_text.split())
            if cap_chars > 0 and len(target_text) > cap_chars:
                target_text = target_text[:cap_chars] + "…"
            context["target_text"] = target_text
            context["target_language"] = target
        except AudioError:
            context["target_text"] = None
    opencode_settings = settings_store.load_settings().get("opencode") or {}
    opencode_rewrite = (
        rewrite_provider in {"auto", "opencode", ""}
        and opencode_available()
        and bool(opencode_settings.get("use_rewrite", True))
    )
    if opencode_rewrite:
        # DeepSeek can read the whole transcript in one call; skip the extra
        # story-brief round trip.
        context["full_context"] = True
    else:
        brief = story_brief(
            context.get("target_text") or full,
            target or context["language"],
            brief_provider,
        )
        if brief:
            context["brief"] = brief
    return context


def build_script(
    scenes: list[dict],
    clips: list[dict],
    base_rate: float = 1.0,
    segments: list[dict] | None = None,
) -> list[dict]:
    """Clean, de-duplicate and time-fit one line per beat with speech/text.

    The raw Whisper attachment repeats the same sentence on overlapping beats.
    This keeps the first good copy, drops near-duplicates, prefers speech over
    on-screen text, and cuts each line to the room the cut actually has.
    """
    by_id = {scene["id"]: scene for scene in scenes}
    lines: list[dict] = []
    accepted: list[str] = []
    seen: set[str] = set()
    for clip_index, clip in enumerate(clips):
        scene = by_id.get(clip.get("scene")) or {}
        duration = float(clip.get("duration") or clip.get("dur") or 0.0)
        if duration <= 0:
            continue
        text = ""
        used_ocr = False
        if segments:
            text = window_text(segments, scene.get("start"), scene.get("end"))
        if not text:
            text = clean_line(scene.get("speech") or "")
        if not text:
            ocr = clean_line(scene.get("ocr") or "")
            if ocr and len(ocr) <= 90:
                text, used_ocr = ocr, True
        if not text:
            continue
        norm = normalize_line(text)
        if not norm or norm in seen:
            continue
        if any(difflib.SequenceMatcher(None, norm, prev).ratio() > 0.82 for prev in accepted):
            continue
        seen.add(norm)
        accepted.append(norm)
        emotion, rate = scene_emotion(scene, duration, base_rate)
        budget = max(0.7, duration - 0.25)
        fitted = trim_to_seconds(text, budget, rate)
        if not fitted:
            continue
        lines.append({
            "scene": clip.get("scene"),
            "clip": clip_index,
            "role": clip.get("role") or "beat",
            "duration": round(duration, 3),
            "text": fitted,
            "original": text,
            "from_ocr": used_ocr,
            "emotion": emotion,
            "rate": rate,
            "shortened": normalize_line(fitted) != norm,
        })
    return lines


def refit_script(lines: list[dict], base_rate: float = 1.0) -> list[dict]:
    """Re-clean and re-fit after translation; target text has a new length."""
    out: list[dict] = []
    accepted: list[str] = []
    for line in lines:
        text = clean_line(line.get("text") or "")
        if not text:
            continue
        norm = normalize_line(text)
        if not norm:
            continue
        if any(difflib.SequenceMatcher(None, norm, prev).ratio() > 0.82 for prev in accepted):
            continue
        accepted.append(norm)
        duration = float(line.get("duration") or 0.0)
        rate = float(line.get("rate") or base_rate)
        budget = max(0.7, duration)
        fitted = trim_to_seconds(text, budget, rate)
        if not fitted:
            continue
        line["text"] = fitted
        line["shortened"] = line.get("shortened") or normalize_line(fitted) != norm
        out.append(line)
    return out


def media_duration(path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 0.0
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        return max(0.0, float((result.stdout or "0").strip() or 0.0))
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0.0


def _voice_track(
    clips: list[dict],
    lines: list[dict],
    tmp: Path,
    total: float,
    gain_db: float,
    expr: str | None = None,
    cancel_event: threading.Event | None = None,
) -> Path | None:
    """Place each line in its own slot: compress a little, then trim.

    Lines never bleed into the next one, so the mix cannot overlap.
    """
    placed = [line for line in lines if line.get("path")]
    if not placed:
        return None
    inputs: list[str] = []
    filters: list[str] = []
    for index, line in enumerate(placed):
        inputs += ["-i", str(line["path"])]
        offset = max(0.0, float(line.get("offset") or 0.0))
        slot = float(line.get("slot") or 0.0)
        native = media_duration(Path(line["path"])) or estimate_seconds(
            str(line.get("text") or ""), float(line.get("rate") or 1.0),
        )
        parts = ["aresample=48000"]
        if slot > 0.2:
            usable = max(0.4, slot - 0.06)
            if native > usable * 1.02:
                tempo = max(1.0, min(1.35, native / usable))
                if tempo > 1.005:
                    parts.append(f"atempo={tempo:.4f}")
                    line["tempo"] = round(tempo, 3)
            parts.append(f"atrim=0:{usable:.3f}")
            fade = min(0.09, max(0.03, usable / 6))
            parts.append("afade=t=in:st=0:d=0.02")
            parts.append(f"afade=t=out:st={max(0.0, usable - fade):.3f}:d={fade:.3f}")
        delay = int(offset * 1000)
        parts.append(f"adelay={delay}|{delay}")
        parts.append(f"volume={float(line.get('gain_db', gain_db)):.2f}dB")
        filters.append(f"[{index}:a]{','.join(parts)}[v{index}]")
    tail = (
        "".join(f"[v{index}]" for index in range(len(placed)))
        + f"amix=inputs={len(placed)}:normalize=0:dropout_transition=0,"
        f"atrim=0:{total:.6f}"
    )
    if expr:
        tail += f",{expr}"
    filters.append(tail + "[voice]")
    output = tmp / "voice.wav"
    _run([
        _ffmpeg(), "-y", "-v", "error", *inputs,
        "-filter_complex", ";".join(filters),
        "-map", "[voice]", "-ar", "48000", "-ac", "2",
        "-c:a", "pcm_s16le", str(output),
    ], timeout=1800, cancel_event=cancel_event)
    return output


def _duck_and_mix(
    voice: Path | None,
    music: Path | None,
    tmp: Path,
    total: float,
    duck: bool,
    music_gain_db: float,
    voice_gain_db: float,
    cancel_event: threading.Event | None = None,
) -> Path:
    output = tmp / "mix.wav"
    if voice and music:
        if duck:
            graph = (
                f"[0:a]aresample=48000,volume={voice_gain_db}dB[vfull];"
                f"[1:a]aresample=48000,volume={music_gain_db}dB[m];"
                "[vfull]asplit=2[v][sc];"
                "[m][sc]sidechaincompress=threshold=0.03:ratio=8:"
                "attack=20:release=350:makeup=1[ducked];"
                "[ducked][v]amix=inputs=2:normalize=0:dropout_transition=0[out]"
            )
        else:
            graph = (
                f"[0:a]aresample=48000,volume={voice_gain_db}dB[v];"
                f"[1:a]aresample=48000,volume={music_gain_db}dB[m];"
                "[v][m]amix=inputs=2:normalize=0:dropout_transition=0[out]"
            )
        _run([
            _ffmpeg(), "-y", "-v", "error", "-i", str(voice), "-i", str(music),
            "-filter_complex", graph, "-map", "[out]",
            "-t", f"{total:.6f}", "-ar", "48000", "-ac", "2",
            "-c:a", "pcm_s16le", str(output),
        ], timeout=1800, cancel_event=cancel_event)
        return output
    source = voice or music
    if source is None:
        raise AudioError("Nothing to mix.")
    _run([
        _ffmpeg(), "-y", "-v", "error", "-i", str(source),
        "-t", f"{total:.6f}", "-ar", "48000", "-ac", "2",
        "-c:a", "pcm_s16le", str(output),
    ], timeout=900, cancel_event=cancel_event)
    return output


def build_bed(
    source: str,
    meta: dict,
    plan: dict,
    clips: list[dict],
    scenes: list[dict],
    job_dir: Path,
    audio_plan: dict,
    total: float,
    tmp: Path,
    progress,
    source_lang: str = "en",
    cancel_event: threading.Event | None = None,
) -> Path | None:
    """Return a finished audio bed, or None to keep the original audio."""
    mode = str(audio_plan.get("mode") or "keep")
    if mode == "keep":
        return None
    tmp.mkdir(parents=True, exist_ok=True)

    voice_plan = audio_plan.get("voice") or {}
    music_plan = audio_plan.get("music") or {}
    translate_plan = audio_plan.get("translate") or {}
    lines: list[dict] = []
    voice_path: Path | None = None

    if mode in {"voice", "full", "bed"} and voice_plan.get("engine"):
        progress(0.86, "Writing the voice script")
        base_rate = float(voice_plan.get("rate") or 1.0)
        source_lang = str(source_lang or "en").split("-")[0]
        target = str(translate_plan.get("target") or "").split("-")[0]
        segments = load_transcript_segments(job_dir)
        script = build_script(scenes, clips, base_rate, segments=segments)
        if not script:
            raise AudioError(
                "The cut has no speech lines to voice over. Turn on Transcribe first."
            )

        overrides = audio_plan.get("script_overrides") or {}

        def apply_overrides(lines: list[dict]) -> None:
            if not isinstance(overrides, dict):
                return
            for line in lines:
                value = overrides.get(str(line.get("scene")))
                if isinstance(value, str) and value.strip():
                    line["text"] = clean_line(value)
                    line["overridden"] = True

        apply_overrides(script)
        mode = str(translate_plan.get("mode") or "literal")
        provider = str(translate_plan.get("provider") or "auto")
        rewrite_provider = str(translate_plan.get("rewrite_provider") or "auto")
        progress(0.87, f"Adapting {len(script)} lines → {target or source_lang} ({mode})")
        context = (
            transcript_context(
                segments, clips, scenes, source_lang,
                target_lang=target, translate_provider=provider,
                brief_provider=provider, rewrite_provider=rewrite_provider,
            )
            if segments else None
        )
        script = adapt_script(
            script, source_lang, target, mode, provider, context, rewrite_provider,
        )
        apply_overrides(script)
        script = refit_script(script, base_rate)

        clip_mix = audio_plan.get("clip_mix") or []
        base_voice_gain = float(voice_plan.get("gain_db") or 0.0)
        cache_dir = CACHE / "voice"
        prepared: list[dict] = [None] * len(script)  # type: ignore[list-item]
        engine_name = str(voice_plan.get("engine"))
        voice_name = str(voice_plan.get("voice") or "")
        workers = max(1, min(4, len(script)))

        def synth_one(index: int, line: dict) -> tuple[int, Path]:
            key = _text_hash(
                engine_name, voice_name, f"{float(line['rate']):.3f}", line["text"],
            )
            path = _voice_cache(cache_dir, key)
            if not path.is_file() or path.stat().st_size <= 512:
                try:
                    synthesize_line(
                        engine_name, voice_name, line["text"], path,
                        rate=float(line["rate"]),
                        cancel_event=cancel_event,
                    )
                except AudioError:
                    if path.exists():
                        path.unlink()
                    raise
            return index, path

        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="vibecut-tts") as pool:
            futures = {
                pool.submit(synth_one, index, line): index
                for index, line in enumerate(script)
            }
            completed = 0
            try:
                for future in as_completed(futures):
                    index, path = future.result()
                    clip_index = int(script[index].get("clip") or 0)
                    entry = clip_mix[clip_index] if clip_index < len(clip_mix) and isinstance(clip_mix[clip_index], dict) else {}
                    gain = base_voice_gain + float((entry or {}).get("voice_db") or 0.0)
                    prepared[index] = {**script[index], "path": path, "gain_db": gain}
                    completed += 1
                    progress(
                        0.88 + 0.03 * (completed / max(1, len(script))),
                        f"Voice line {completed}/{len(script)} · {script[index]['emotion']}",
                    )
            except AudioError:
                for pending in futures:
                    pending.cancel()
                raise

        clip_offsets: list[float] = []
        running = 0.0
        for clip in clips:
            clip_offsets.append(running)
            running += float(clip.get("duration") or clip.get("dur") or 0.0)
        clip_offsets.append(running)

        for index, line in enumerate(prepared):
            clip_index = int(line.get("clip") or 0)
            clip_index = max(0, min(clip_index, len(clip_offsets) - 1))
            offset = clip_offsets[clip_index]
            if index + 1 < len(prepared):
                next_index = int(prepared[index + 1].get("clip") or 0)
                next_index = max(0, min(next_index, len(clip_offsets) - 1))
                slot = max(0.5, clip_offsets[next_index] - offset - 0.12)
            else:
                slot = max(0.5, float(line["duration"]) - 0.12)
            line["offset"] = round(offset, 3)
            line["slot"] = round(min(slot, float(line["duration"])), 3)

        automation = audio_plan.get("automation") or {}
        voice_expr = automation_expression(automation.get("voice"), total)
        voice_path = _voice_track(
            clips, prepared, tmp, total,
            float(voice_plan.get("gain_db") or 0.0),
            voice_expr,
            cancel_event,
        )

    music_path: Path | None = None
    if mode == "bed":
        progress(0.90, "Separating the original instrumental")
        music_path = separate_vocals(
            source, str(meta.get("fingerprint") or meta.get("size") or "source"),
            cancel_event,
        )
    elif music_plan.get("source") and music_plan.get("source") != "none":
        progress(0.90, "Preparing music bed")
        chosen: Path | None = resolve_music_track(scenes, clips, music_plan)
        if chosen is None and music_plan.get("source") in {"stable-small", "stable-1.0"}:
            model = (
                "stabilityai/stable-audio-open-small"
                if music_plan["source"] == "stable-small"
                else "stabilityai/stable-audio-open-1.0"
            )
            prompt = str(music_plan.get("prompt") or "").strip()
            if not prompt or prompt == "auto":
                prompt = music_prompt(
                    music_plan.get("moods") or scene_moods(scenes, clips), total,
                )
            chosen = generate_music(model, prompt, min(47.0, max(8.0, total)), cancel_event)
        if chosen and chosen.is_file():
            base_music_gain = float(music_plan.get("gain_db") or -18.0)
            beat_offset = 0.0
            if audio_plan.get("beat_sync"):
                grid = beat_grid(chosen)
                if grid and grid.get("beats"):
                    beat_offset = float(grid["beats"][0])
                    audio_plan["_beat_bpm"] = grid.get("bpm")
            automation = audio_plan.get("automation") or {}
            expr = automation_expression(automation.get("music"), total)
            if expr is None:
                expr = music_mix_expression(
                    clips, audio_plan.get("clip_mix"), base_music_gain,
                )
            audio_plan["_used_assets"] = ensure_licensed([chosen])
            music_path = _music_loop(
                chosen, total, base_music_gain, tmp, expr, beat_offset,
            )
        elif music_plan.get("source") in MUSIC_DIRS:
            folder = MUSIC_DIRS[str(music_plan["source"])]
            raise AudioError(
                f"No tracks in {folder}. Drop an audio file there or pick another music source."
            )
        else:
            raise AudioError("Music generation produced no file.")

    if voice_path is None and music_path is None:
        raise AudioError("No voice or music was produced for this audio plan.")

    progress(0.94, "Mixing audio")
    mixed = _duck_and_mix(
        voice_path, music_path, tmp, total,
        bool(music_plan.get("duck", True)),
        float(music_plan.get("gain_db") or -18.0),
        float(voice_plan.get("gain_db") or 0.0),
        cancel_event,
    )
    final = tmp / "final_audio.wav"
    _run([
        _ffmpeg(), "-y", "-v", "error", "-i", str(mixed),
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(final),
    ], timeout=900, cancel_event=cancel_event)
    return final


# ---------------------------------------------------------------- cache hygiene


CACHE_DIRS = ("segments", "voice", "stems", "music", "masters", "translate")


def cache_usage() -> dict:
    usage = {}
    for name in CACHE_DIRS:
        base = CACHE / name
        total = 0
        count = 0
        if base.is_dir():
            for path in base.rglob("*"):
                if path.is_file():
                    try:
                        total += path.stat().st_size
                        count += 1
                    except OSError:
                        continue
        usage[name] = {"files": count, "mb": round(total / 1e6, 1)}
    usage["total_mb"] = round(sum(item["mb"] for item in usage.values()), 1)
    return usage


def prune_cache(max_gb: float = 2.0, days: float = 14.0) -> dict:
    """Age-prune, then LRU-prune the caches down to max_gb."""
    now = time.time()
    keep: list[tuple[float, int, Path]] = []
    removed = 0
    freed = 0
    for name in CACHE_DIRS:
        base = CACHE / name
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            if days > 0 and now - stat.st_mtime > days * 86400:
                try:
                    path.unlink()
                    removed += 1
                    freed += stat.st_size
                except OSError:
                    pass
            else:
                keep.append((stat.st_mtime, stat.st_size, path))
    shutil.rmtree(CACHE / "stems" / "run", ignore_errors=True)
    if max_gb > 0:
        budget = max_gb * 1024 ** 3
        total = sum(size for _, size, _ in keep)
        for _mtime, size, path in sorted(keep):
            if total <= budget:
                break
            try:
                path.unlink()
                total -= size
                removed += 1
                freed += size
            except OSError:
                continue
    return {"removed": removed, "freed_mb": round(freed / 1e6, 1)}


# ---------------------------------------------------------------- rewrite styles

REWRITE = CACHE / "rewrite"
REWRITE_VERSION = 4

CONNECTORS = {
    "en": ["and", "but", "so", "then", "turns out"],
    "vi": ["và", "nhưng", "nên", "rồi", "hoá ra"],
    "es": ["y", "pero", "así que", "entonces"],
    "fr": ["et", "mais", "donc", "alors"],
    "de": ["und", "aber", "also", "dann"],
    "pt": ["e", "mas", "então", "aí"],
    "ja": ["そして", "でも", "だから", "すると"],
    "ko": ["그리고", "하지만", "그래서", "그러면"],
    "zh": ["然后", "但是", "所以", "结果"],
}

CTAS = {
    "en": ["Follow for more.", "Save this one.", "Try it yourself."],
    "vi": ["Theo dõi để xem thêm.", "Lưu lại nhé.", "Thử xem sao."],
    "es": ["Sígueme para más.", "Guarda esto.", "Pruébalo tú mismo."],
    "fr": ["Abonne-toi pour plus.", "Garde ça.", "Essaie toi-même."],
    "de": ["Folge für mehr.", "Speicher das.", "Probier es selbst."],
    "pt": ["Siga para mais.", "Salve este.", "Teste você mesmo."],
    "ja": ["続きはフォローで。", "保存してね。", "試してみて。"],
    "ko": ["더 보려면 팔로우.", "저장해 두세요.", "직접 해보세요."],
    "zh": ["关注看更多。", "先收藏。", "自己试试。"],
}


def _facts(texts: list[str]) -> set[str]:
    facts: set[str] = set()
    for value in texts:
        for token in re.findall(r"[0-9]+(?:[.,][0-9]+)?", str(value or "")):
            facts.add(token.strip(".,"))
    return facts


def _context_hash(context: dict | None) -> str:
    if not context:
        return ""
    return hashlib.sha1(str(context.get("full_text") or "").encode("utf-8")).hexdigest()[:8]


def _rewrite_file(
    source: str, target: str, mode: str, text: str, context: dict | None = None,
) -> Path:
    key = hashlib.sha1(
        f"v{REWRITE_VERSION}|{source}|{target}|{mode}|{_context_hash(context)}|{text}".encode("utf-8"),
    ).hexdigest()[:24]
    return REWRITE / key[:2] / f"{key}.txt"


def _rewrite_memo(
    source: str, target: str, mode: str, text: str, context: dict | None = None,
) -> str | None:
    path = _rewrite_file(source, target, mode, text, context)
    if not path.is_file():
        return None
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def _rewrite_put(
    source: str, target: str, mode: str, text: str, value: str,
    context: dict | None = None,
) -> None:
    if not value:
        return
    path = _rewrite_file(source, target, mode, text, context)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
    except OSError:
        pass


def _dedupe_lead(text: str, previous: str) -> str:
    if not previous:
        return text
    first = text.split(" ", 1)[0].lower().rstrip(",.")
    if first in {"and", "but", "so", "then"} and " " in text:
        return text.split(" ", 1)[1]
    return text


def grow(text: str, seconds: float, rate: float, mode: str, role: str, connector: str, cta: str) -> str:
    """Shape one rewritten line to the slot and the style."""
    value = clean_line(text)
    budget = max(0.6, float(seconds or 0.0) - 0.25)
    if mode == "viral" and role == "hook":
        budget *= 0.8
        for separator in ("。", ". ", "! ", "? ", "；", "; ", "，", ", "):
            if separator in value:
                value = value.split(separator)[0]
                break
        value = value.strip(" ,，。.!?！？;；:：")
    value = trim_to_seconds(value, budget, rate)
    if mode == "smooth" and value:
        stripped = value[0].lower() + value[1:] if value[:1].isupper() and not CJK_RE.search(value) else value
        value = f"{connector} {stripped}"
        value = trim_to_seconds(value, budget, rate)
    if mode == "viral":
        value = value.replace("。", ".").strip()
        lowered = value.lower()
        if role == "payoff" and cta and cta.lower() not in lowered:
            candidate = f"{value} {cta}".strip()
            if estimate_seconds(candidate, rate) <= budget:
                value = candidate
    return value


def _rules_rewrite(
    script: list[dict], source: str, target: str, mode: str, literal: list[str],
) -> list[str]:
    connector_set = CONNECTORS.get(target, CONNECTORS["en"])
    cta_set = CTAS.get(target, CTAS["en"])
    out: list[str] = []
    for index, line in enumerate(script):
        value = _dedupe_lead(literal[index], out[index - 1] if out else "")
        grow_mode = "literal"
        if mode == "viral":
            grow_mode = "viral"
        elif mode == "smooth" and index > 0:
            grow_mode = "smooth"
        value = grow(
            value,
            float(line.get("duration") or 0.0),
            float(line.get("rate") or 1.0),
            grow_mode,
            str(line.get("role") or "beat"),
            connector_set[index % len(connector_set)],
            cta_set[index % len(cta_set)],
        )
        out.append(value)
    return out


def _rewrite_ollama(
    script: list[dict], source: str, target: str, mode: str, literal: list[str],
    context: dict | None = None,
) -> list[str] | None:
    url = os.environ.get("VIBECUT_LLM_URL")
    if not url or mode == "literal":
        return None
    model = os.environ.get("VIBECUT_LLM_MODEL", "llama3.1")
    context_beats = (context or {}).get("beats") or []
    rows = []
    for index, line in enumerate(script):
        source_line = ""
        if index < len(context_beats):
            source_line = str(context_beats[index].get("source") or "")
        rows.append({
            "beat": index,
            "role": str(line.get("role") or "beat"),
            "seconds": round(float(line.get("duration") or 0.0) - 0.25, 2),
            "source_line": source_line or line.get("text") or "",
            "literal": literal[index],
        })
    style = {
        "smooth": "natural, flowing, conversational, connected sentences",
        "viral": "punchy short-video style: hook grabs in the first words, one idea per beat, payoff ends with a light call to action",
    }.get(mode, "faithful")
    full_text = str(
        (context or {}).get("target_text") or (context or {}).get("full_text") or ""
    ).strip()
    brief = (context or {}).get("brief")
    prompt = (
        f"You are editing a short vertical video. Below is the FULL TRANSCRIPT of the "
        f"source video. Read it first to understand the story, the product, the claims "
        f"and the intended audience. Then write a {len(rows)}-beat voice over in "
        f"{_language_name(target)} for the selected beats, in order.\n"
        f"Style: {style}.\n"
        "Rules: keep every fact and number from the source, invent nothing, keep the "
        "story coherent from beat to beat (setup, proof, payoff), each line must fit its "
        "seconds budget at normal speaking pace. Reply with a JSON array of strings "
        "only, same order and count.\n"
        + (f"STORY BRIEF:\n{json.dumps(brief, ensure_ascii=False)}\n\n" if brief else "")
        + (f"FULL TRANSCRIPT:\n{full_text}\n\n" if full_text else "")
        + "SELECTED BEATS:\n"
        + json.dumps(rows, ensure_ascii=False)
    )
    payload = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
        "options": {"temperature": 0.6},
    }).encode("utf-8")
    request = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None
    body = str(data.get("response") or data.get("message", {}).get("content") or "")
    match = re.search(r"\[.*\]", body, re.S)
    if not match:
        return None
    try:
        values = json.loads(match.group(0))
    except ValueError:
        return None
    if not isinstance(values, list) or len(values) != len(script):
        return None
    fits = all(
        estimate_seconds(str(value), float(script[index].get("rate") or 1.0))
        <= max(1.0, float(script[index].get("duration") or 1.0))
        for index, value in enumerate(values)
    )
    if not fits:
        return None
    return [str(value).strip() for value in values]


def adapt_script(
    script: list[dict],
    source_lang: str,
    target_lang: str,
    mode: str = "smooth",
    provider: str = "auto",
    context: dict | None = None,
    rewrite_provider: str | None = None,
) -> list[dict]:
    """Translate, then rewrite for the slot and the short-video style.

    The literal translation stays as the meaning reference; rules or an LLM
    reshape it. Numbers found in the rewrite must exist in the source, so the
    adapted script cannot invent facts.
    """
    source_lang = (source_lang or "en").split("-")[0]
    target_lang = (target_lang or source_lang).split("-")[0]
    mode = mode if mode in {"literal", "smooth", "viral"} else "smooth"
    lines = [dict(line) for line in script]
    if not lines:
        return lines
    originals = [str(line.get("text") or "") for line in lines]
    if target_lang != source_lang:
        literals = translate_lines(originals, source_lang, target_lang, provider)
    else:
        literals = list(originals)
    literal_values = list(literals)

    used = "literal"
    if mode != "literal":
        missing: list[int] = []
        cached: dict[int, str] = {}
        for index, text in enumerate(literals):
            hit = _rewrite_memo(source_lang, target_lang, mode, text, context)
            if hit:
                cached[index] = hit
            else:
                missing.append(index)
        if cached:
            used = "cached"
        if missing:
            subset = [lines[index] for index in missing]
            subset_literal = [literals[index] for index in missing]
            rewritten: list[str] | None = None
            if rewrite_provider and rewrite_provider not in ("auto", ""):
                order = [rewrite_provider]
            elif provider and provider not in ("auto", ""):
                order = [provider]
            else:
                order = _rewrite_candidates()
            for candidate in order:
                if candidate == "opencode":
                    rewritten = _rewrite_opencode(
                        subset, source_lang, target_lang, mode, subset_literal, context,
                    )
                elif candidate in {"llm", "ollama"}:
                    rewritten = _rewrite_ollama(
                        subset, source_lang, target_lang, mode, subset_literal, context,
                    )
                elif candidate in {"mlx", "apple"}:
                    rewritten = _rewrite_mlx(
                        subset, source_lang, target_lang, mode, subset_literal, context,
                    )
                elif candidate == "rules":
                    rewritten = _rules_rewrite(subset, source_lang, target_lang, mode, subset_literal)
                if rewritten:
                    used = "llm" if candidate in {"llm", "ollama"} else candidate
                    break
            fallback = not rewritten
            if fallback:
                rewritten = subset_literal
            for offset_index, index in enumerate(missing):
                value = rewritten[offset_index]
                cached[index] = value
                if not fallback:
                    _rewrite_put(source_lang, target_lang, mode, literals[index], value, context)
        literals = [cached.get(index, literals[index]) for index in range(len(lines))]

    source_facts = _facts(originals)
    for index, line in enumerate(lines):
        candidate = literals[index]
        line_facts = _facts([candidate])
        if line_facts - (source_facts | _facts([originals[index]])):
            candidate = literals[index] if mode == "literal" else trim_to_seconds(
                originals[index] if target_lang == source_lang else literals[index],
                max(0.6, float(line.get("duration") or 0.0) - 0.25),
                float(line.get("rate") or 1.0),
            )
        line["text"] = candidate
        line["literal"] = literal_values[index]
        line["mode"] = mode
        line["rewrite"] = used
    return lines


# ---------------------------------------------------------------- assets + licenses


def asset_license(path: Path) -> dict | None:
    sidecar = Path(str(path) + ".license.json")
    if sidecar.is_file():
        try:
            return json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"license": "unknown"}
    mapping = path.parent / "LICENSE.json"
    if mapping.is_file():
        try:
            data = json.loads(mapping.read_text(encoding="utf-8"))
            entry = data.get(path.name)
            if entry:
                return entry if isinstance(entry, dict) else {"license": str(entry)}
        except (OSError, json.JSONDecodeError):
            pass
    if (path.parent / "LICENSE.txt").is_file():
        return {"license": "file"}
    return None


def ensure_licensed(paths: list[Path]) -> list[dict]:
    strict = os.environ.get("VIBECUT_AUDIO_LICENSE", "").lower() == "strict"
    used: list[dict] = []
    missing: list[str] = []
    for path in paths:
        meta = asset_license(path)
        try:
            shown = str(path.relative_to(ASSETS))
        except ValueError:
            shown = path.name
        used.append({"path": shown, "license": (meta or {}).get("license") or "unknown"})
        if not meta:
            missing.append(path.name)
    if strict and missing:
        raise AudioError(
            "Strict license mode: add a .license.json for " + ", ".join(missing)
        )
    return used


def _slug(text: str, limit: int = 36) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", str(text or "")).strip("-").lower()
    return (value or "bed")[:limit]


def save_generated_asset(source: Path, model: str, prompt: str, seconds: float) -> Path:
    """Keep an AI bed as a reusable library track, not only a render cache."""
    directory = MUSIC_DIRS["generated"]
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(
        f"{model}|{prompt}|{seconds:.0f}|{source.stat().st_size}".encode("utf-8"),
    ).hexdigest()[:8]
    out = directory / f"{_slug(prompt)}-{digest}.wav"
    if not out.is_file():
        shutil.copy2(source, out)
    sidecar = Path(str(out) + ".license.json")
    if not sidecar.is_file():
        sidecar.write_text(json.dumps({
            "license": "generated",
            "model": model,
            "prompt": prompt,
            "seconds": round(float(seconds), 1),
            "created": round(time.time(), 3),
        }, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


# ---------------------------------------------------------------- beats


BEATS = CACHE / "beats"


def beat_grid(path: Path) -> dict | None:
    """BPM and beat times for a music file, cached. Uses librosa when present."""
    if not _module("librosa") or not path.is_file():
        return None
    try:
        stat = path.stat()
    except OSError:
        return None
    key = hashlib.sha1(f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode()).hexdigest()[:24]
    cached = BEATS / f"{key}.json"
    if cached.is_file():
        try:
            return json.loads(cached.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    try:
        import librosa  # noqa: PLC0415

        samples, rate = librosa.load(str(path), mono=True, sr=22050)
        tempo, beats = librosa.beat.beat_track(y=samples, sr=rate, units="time")
        bpm = float(tempo[0] if hasattr(tempo, "__len__") else tempo)
        grid = {
            "bpm": round(bpm, 2),
            "beats": [round(float(value), 3) for value in beats][:4000],
        }
    except Exception:  # noqa: BLE001
        return None
    try:
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(grid), encoding="utf-8")
    except OSError:
        pass
    return grid


def snap_clips(
    clips: list[dict],
    grid: dict | None,
    max_shift: float = 0.25,
    min_duration: float = 0.5,
    max_drift: float = 0.4,
) -> tuple[list[dict], float]:
    """Move cut points onto nearby beats by trimming the previous clip."""
    if not grid or not grid.get("beats") or len(clips) < 2:
        return clips, 0.0
    beats = grid["beats"]
    out = [dict(clip) for clip in clips]
    drift = 0.0
    boundary = 0.0
    for index in range(len(out) - 1):
        boundary += float(out[index].get("duration") or 0.0)
        target = min(beats, key=lambda beat: abs(beat - boundary))
        delta = target - boundary
        if abs(delta) > max_shift:
            continue
        new_duration = float(out[index]["duration"]) + delta
        if new_duration < min_duration:
            continue
        if abs(drift + delta) > max_drift:
            continue
        out[index]["duration"] = round(new_duration, 3)
        drift += delta
        boundary = target
    return out, round(drift, 3)


def _db_to_linear(db: float) -> str:
    return f"pow(10,({db:.2f})/20)"


def automation_expression(points, total: float) -> str | None:
    """Smooth gain automation: 100% at rest, cosine ramps peaking at each node.

    Nodes are (time, dB) pairs. Missing start/end anchors are added at 0 dB so
    the lane always begins and ends at 100%.
    """
    cleaned: list[tuple[float, float]] = []
    total = max(0.1, float(total or 0.0))
    for item in points or []:
        try:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                at, db = float(item[0]), float(item[1])
            elif isinstance(item, dict):
                at, db = float(item.get("t", 0.0)), float(item.get("db", 0.0))
            else:
                continue
        except (TypeError, ValueError):
            continue
        cleaned.append((
            max(0.0, min(total, at)),
            max(-24.0, min(6.0, db)),
        ))
    if not cleaned:
        return None
    cleaned.sort()
    if abs(cleaned[0][0]) > 0.05:
        cleaned.insert(0, (0.0, 0.0))
    if abs(cleaned[-1][0] - total) > 0.05:
        cleaned.append((total, 0.0))
    if all(abs(db) < 0.01 for _at, db in cleaned):
        return None
    if len(cleaned) == 1:
        return f"volume=volume={_db_to_linear(cleaned[0][1])}:eval=frame"

    def ramp(t0: float, d0: float, t1: float, d1: float) -> str:
        span = max(1e-6, t1 - t0)
        return (
            f"pow(10,({d0:.2f}+({d1 - d0:.2f})*"
            f"(1-cos(PI*(t-{t0:.3f})/{span:.6f}))/2)/20)"
        )

    expression = _db_to_linear(cleaned[-1][1])
    for index in range(len(cleaned) - 1, 0, -1):
        t0, d0 = cleaned[index - 1]
        t1, d1 = cleaned[index]
        expression = f"if(lt(t,{t1:.3f}),{ramp(t0, d0, t1, d1)},{expression})"
    expression = f"if(lt(t,{cleaned[0][0]:.3f}),{_db_to_linear(cleaned[0][1])},{expression})"
    return f"volume=volume='{expression}':eval=frame"


WAVEFORMS = CACHE / "waveforms"


def _envelope_file(fingerprint: str, tag: str = "mix") -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", fingerprint or "source")[:80]
    return WAVEFORMS / f"{safe}-{tag}.json"


def source_envelope(
    path: str,
    fingerprint: str,
    bucket_seconds: float = 0.25,
    tag: str = "mix",
) -> list[float]:
    """RMS dB envelope of an audio file, cached, cheap enough for the mixer UI."""
    cached = _envelope_file(fingerprint, tag)
    if cached.is_file():
        try:
            data = json.loads(cached.read_text(encoding="utf-8"))
            if data.get("bucket") == bucket_seconds and data.get("db"):
                return [float(value) for value in data["db"]]
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    sample_rate = 8000
    try:
        import numpy as np  # noqa: PLC0415

        result = subprocess.run(
            [_ffmpeg(), "-v", "error", "-i", path, "-ac", "1", "-ar", str(sample_rate),
             "-f", "s16le", "pipe:1"],
            capture_output=True, timeout=900,
        )
        if result.returncode != 0 or not result.stdout:
            return []
        samples = np.frombuffer(result.stdout, dtype=np.int16).astype(np.float32) / 32768.0
        per_bucket = max(1, int(sample_rate * bucket_seconds))
        usable = (samples.size // per_bucket) * per_bucket
        if usable <= 0:
            return []
        blocks = samples[:usable].reshape(-1, per_bucket)
        rms = np.sqrt(np.mean(blocks * blocks, axis=1))
        dbs = 20.0 * np.log10(np.maximum(rms, 1e-6))
    except Exception:  # noqa: BLE001
        return []
    values = [round(float(value), 1) for value in dbs]
    try:
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps({"bucket": bucket_seconds, "db": values}), encoding="utf-8")
    except OSError:
        pass
    return values


def reel_envelope(
    envelope: list[float],
    clips: list[dict],
    bucket_seconds: float = 0.25,
    max_points: int = 1400,
) -> list[list[float]]:
    """Slice a source envelope onto the reel timeline: [[reel_seconds, dB], ...]."""
    if not envelope:
        return []
    out: list[list[float]] = []
    offset = 0.0
    total_seconds = sum(float(c.get("duration") or c.get("dur") or 0.0) for c in clips)
    step = max(1, int(math.ceil((total_seconds / max(1, bucket_seconds)) / max_points))) if max_points else 1
    for clip in clips:
        start = float(clip.get("start") or 0.0)
        duration = float(clip.get("duration") or clip.get("dur") or 0.0)
        count = max(1, int(duration / bucket_seconds))
        for index in range(0, count, step):
            at = start + index * bucket_seconds
            bucket = int(at / bucket_seconds)
            if 0 <= bucket < len(envelope):
                out.append([round(offset + index * bucket_seconds, 2), envelope[bucket]])
        offset += duration
    return out


def music_mix_expression(
    clips: list[dict],
    mix: list[dict] | None,
    base_db: float,
) -> str | None:
    """Piecewise volume for per-clip music gain, or None when flat."""
    if not mix:
        return None
    offsets: list[float] = []
    running = 0.0
    for clip in clips:
        offsets.append(running)
        running += float(clip.get("duration") or 0.0)
    expression = f"{base_db:.2f}"
    changed = False
    for index in range(len(clips) - 1, -1, -1):
        entry = mix[index] if index < len(mix) and isinstance(mix[index], dict) else {}
        delta = float(entry.get("music_db") or 0.0)
        start = offsets[index]
        end = start + float(clips[index].get("duration") or 0.0)
        value = base_db + delta
        if abs(delta) > 0.01:
            changed = True
        expression = f"if(between(t,{start:.3f},{end:.3f}),{value:.2f},{expression})"
    if not changed:
        return None
    return f"volume=volume='{expression}':eval=frame"
