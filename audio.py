"""Audio replacement: voice over, dub, music beds, separation and mixing.

The module is deliberately opt-in: `keep` mode returns None and the renderer
falls back to the original audio bed. Every engine is detected at runtime, so
the UI can grey out what is not installed and show an install hint.
"""

from __future__ import annotations

import base64
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
import urllib.error
import urllib.request
import uuid
import wave
from pathlib import Path
from typing import Sequence

import packs
import settings_store
import usage_store
import workflow_config

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
MUSIC_DIRS = {
    "library": ASSETS / "music" / "library",
    "generated": ASSETS / "music" / "generated",
}
VOICE_DIRS = {
    "kokoro": ROOT / "data" / "models" / "kokoro",
}
# AudioPlan modes from ROADMAP.md "Product contracts still in force". The mixer also still accepts the
# legacy ``keep``/``bed``/``voice``/``full`` names used by Classic jobs.
AUDIO_MODES = ("original", "original_bed", "voice_over", "dub", "music_only")
LEGACY_AUDIO_MODES = ("keep", "bed", "voice", "full")
DUCK_DB = -12.0
DUCK_ATTACK_MS = 150
DUCK_RELEASE_MS = 400
LOUDNESS_LUFS = -14.0
LOUDNESS_TRUE_PEAK = -1.5
LOUDNESS_LRA = 11.0
SPEECH_BAND_HZ = (300.0, 3400.0)
SPEECH_SNR_TARGET_DB = 12.0
MUSIC_BASE_GAIN_DB = -18.0
KOKORO_EN_VOICES = (
    "af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky",
    "am_adam", "am_michael", "bf_emma", "bf_isabella",
    "bm_george", "bm_lewis",
)
KOKORO_ZH_NAMED = (
    "zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi",
    "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang",
)
KOKORO_ZH_NUMERIC = (
    "zf_001", "zf_002", "zf_003", "zf_004", "zf_005", "zf_006",
    "zf_007", "zf_008", "zm_009", "zm_010", "zm_011", "zm_012",
)
CACHE = settings_store.DATA / "cache"
LAST_USAGE: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}


def _reset_last_usage() -> None:
    LAST_USAGE["input_tokens"] = 0
    LAST_USAGE["output_tokens"] = 0


def _record_last_usage(usage: dict | None) -> None:
    usage = usage or {}
    try:
        LAST_USAGE["input_tokens"] = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        LAST_USAGE["output_tokens"] = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    except (TypeError, ValueError):
        _reset_last_usage()


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


def _workflow(name: str) -> dict:
    settings = settings_store.load_settings()
    return workflow_config.effective(settings.get("workflows"), name)


def _workflow_routes(name: str) -> list[dict[str, str]]:
    return list(_workflow(name).get("routes") or [])


def _pipeline_event(
    workflow: str,
    route_index: int,
    provider: str,
    model: str,
    reasoning: str,
    started: float,
    ok: bool,
    error: str = "",
    *,
    job_id: str = "",
    request_id: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    """Best-effort persistent pipeline log; never break generation."""
    try:
        from admin import store  # noqa: PLC0415
        store.record_pipeline_event(
            workflow,
            provider,
            model,
            route_index=route_index,
            job_id=job_id,
            request_id=request_id or job_id,
            reasoning=reasoning,
            status="ok" if ok else "failed",
            latency_ms=(time.time() - started) * 1000,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            fallback=route_index > 0,
            error=error,
        )
    except Exception:  # noqa: BLE001
        pass


def _workflow_route_model(workflow: str, provider: str, default: str = "") -> str:
    for route in _workflow_routes(workflow):
        if str(route.get("provider") or "") == provider:
            return str(route.get("model") or "") or default
    return default


def _workflow_text(
    workflow: str,
    prompt: str,
    *,
    json_mode: bool = False,
    max_tokens: int | None = None,
) -> str | None:
    """Run a text workflow through its ordered model routes.

    The provider-specific functions still own their auth, retry, and fallback
    details; this layer supplies the admin-selected model, reasoning, token,
    and timeout values and records each attempt for the Pipeline log.
    """
    cfg = _workflow(workflow)
    reasoning = str(cfg.get("reasoning") or "low")
    token_limit = int(max_tokens or cfg.get("max_output_tokens") or 3000)
    timeout = float(cfg.get("timeout_s") or 300)
    for index, route in enumerate(cfg.get("routes") or []):
        provider = str(route.get("provider") or "")
        model = str(route.get("model") or "")
        started = time.time()
        _reset_last_usage()
        try:
            if provider == "opencode-go":
                value = _opencode_text(
                    prompt, json_mode=json_mode, max_tokens=token_limit,
                    model=model, variant=reasoning, timeout=timeout,
                )
                error = OPENCODE_LAST_ERROR
            elif provider == "openrouter":
                value = _openrouter_text(
                    prompt, json_mode=json_mode, max_tokens=token_limit,
                    model=model, reasoning=reasoning, timeout=timeout,
                )
                error = OPENROUTER_LAST_ERROR
            else:
                value = None
                error = f"{provider} does not support text generation."
        except Exception as exc:  # noqa: BLE001
            value = None
            error = str(exc)[:300]
        _pipeline_event(
            workflow, index, provider, model, reasoning, started,
            bool(value), "" if value else error[:300],
            input_tokens=int(LAST_USAGE.get("input_tokens") or 0),
            output_tokens=int(LAST_USAGE.get("output_tokens") or 0),
        )
        if value:
            return value
    return None


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


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
    if not audio_plan or mixer_mode(str(audio_plan.get("mode") or "keep")) == "keep":
        return ""
    return fnv1a(canonical_json(audio_plan))


def audio_mode(audio_plan: dict | None) -> str:
    """Return the declared AudioPlan mode, defaulting to ``original``."""
    mode = str((audio_plan or {}).get("mode") or "original").strip().lower().replace("-", "_")
    return mode if mode in AUDIO_MODES or mode in LEGACY_AUDIO_MODES else "original"


def mixer_mode(mode: str) -> str:
    """Map an AudioPlan §8.4 mode onto the mixer's internal branch name."""
    value = str(mode or "original").strip().lower().replace("-", "_")
    return {
        "original": "keep",
        "keep": "keep",
        "original_bed": "original_bed",
        "voice_over": "full",
        "dub": "full",
        "music_only": "music_only",
        # Legacy Classic modes keep their old branches.
        "bed": "bed",
        "voice": "voice",
        "full": "full",
    }.get(value, "keep")


def loudness_settings(audio_plan: dict | None) -> dict[str, float]:
    """Final loudness target: −14 LUFS integrated, −1.5 dBTP by default."""
    raw = (audio_plan or {}).get("loudness") or {}
    if not isinstance(raw, dict):
        raw = {}

    def _number(value, fallback):
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    return {
        "lufs": max(-30.0, min(-5.0, _number(raw.get("lufs"), LOUDNESS_LUFS))),
        "true_peak": max(-9.0, min(0.0, _number(raw.get("true_peak"), LOUDNESS_TRUE_PEAK))),
        "lra": max(1.0, min(20.0, _number(raw.get("lra"), LOUDNESS_LRA))),
    }


def normalize_audio_plan(audio_plan: dict | None) -> dict:
    """Fill ducking and loudness defaults without changing the declared mode."""
    plan = dict(audio_plan or {})
    plan["mode"] = audio_mode(plan)
    try:
        duck_db = float(plan.get("duck_db", DUCK_DB))
    except (TypeError, ValueError):
        duck_db = DUCK_DB
    plan["duck_db"] = max(-60.0, min(0.0, duck_db))
    plan["duck"] = bool(plan.get("duck", True))
    plan["loudness"] = loudness_settings(plan)
    for key in ("music", "voice", "translate"):
        if plan.get(key) is None:
            plan[key] = {}
        elif not isinstance(plan[key], dict):
            plan[key] = {}
    music = dict(plan["music"])
    music.setdefault("gain_db", MUSIC_BASE_GAIN_DB)
    music.setdefault("duck", plan["duck"])
    plan["music"] = music
    return plan


def plan_from_edit(audio_section: dict | None) -> dict | None:
    """Convert an Edit's ``audio`` object into a mixer AudioPlan.

    The Edit schema validates modes and loudness already (``edits.py``). This
    adapter adds the mixing defaults and maps a locked music ``file_hash`` to
    the resolver's field name.
    """
    if not isinstance(audio_section, dict):
        return None
    source = dict(audio_section)
    mode = str(source.get("mode") or "original").strip().lower().replace("-", "_")
    if mode not in AUDIO_MODES:
        mode = "original"
    plan: dict = {
        "mode": mode,
        "duck": bool(source.get("duck", True)),
        "duck_db": source.get("duck_db", DUCK_DB),
        "loudness": source.get("loudness") or {},
    }
    music = source.get("music")
    if isinstance(music, dict):
        copied = dict(music)
        if copied.get("file_hash") and not copied.get("locked_hash"):
            copied["locked_hash"] = copied["file_hash"]
        plan["music"] = copied
    voice = source.get("voice")
    if isinstance(voice, dict):
        plan["voice"] = dict(voice)
    if isinstance(source.get("translate"), dict):
        plan["translate"] = dict(source["translate"])
    if isinstance(source.get("script_overrides"), dict):
        plan["script_overrides"] = dict(source["script_overrides"])
    return normalize_audio_plan(plan)


def say_available() -> bool:
    return sys.platform == "darwin" and bool(shutil.which("say"))


def kokoro_available() -> bool:
    if not _module("kokoro_onnx"):
        return False
    packed = packs.find_dir("voice", "models/kokoro", "kokoro", "")
    if packed is not None and any(packed.glob("*.onnx")):
        return True
    return any(VOICE_DIRS["kokoro"].glob("*.onnx"))


def elevenlabs_key() -> str:
    return settings_store.get_secret("elevenlabs")



def minimax_key() -> str:
    return settings_store.get_secret("minimax")


def demucs_available() -> bool:
    if packs.find_command("separation", "demucs") is not None:
        return True
    if shutil.which("demucs"):
        return True
    return _module("demucs")


def rewrite_models() -> list[dict]:
    """Text models that fit a short rewrite prompt, cloud and on-device."""
    return [
        {"id": "apple", "name": "Apple Foundation Models",
         "model": "on-device 3B",
         "available": sys.platform == "darwin", "size_mb": 0,
         "install": "enable Apple Intelligence on macOS 26"},
        {"id": "opencode", "name": "OpenCode Go · DeepSeek V4.1 Flash",
         "model": opencode_model() if opencode_available() else "deepseek-v4.1-flash",
         "available": opencode_available(), "size_mb": 0,
         "install": "Install OpenCode and sign in to OpenCode Go. Uses the local login; low reasoning."},
        {"id": "openrouter", "name": "OpenRouter · DeepSeek V4.1 Flash",
         "model": openrouter_model() if openrouter_available() else "deepseek/deepseek-v4.1-flash:floor",
         "available": openrouter_available(), "size_mb": 0,
         "install": "Add an OpenRouter key in Setup."},
    ]


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
        "id": "openrouter",
        "name": "OpenRouter · DeepSeek V4.1 Flash",
        "available": openrouter_available(),
        "install": "Add an OpenRouter key in Setup.",
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
    return [item for item in providers if item["id"] in {"opencode", "openrouter", "apple_fm"}]


def _roformer_available() -> bool:
    try:
        import voice_extract  # noqa: PLC0415 - voice_extract imports audio
        return bool(voice_extract.available_backends()["separations"].get("roformer"))
    except Exception:
        return False


def _extraction_status() -> dict:
    try:
        import voice_extract  # noqa: PLC0415
        return voice_extract.available_backends()
    except Exception:
        return {}


def engine_status() -> dict:
    kokoro_model = next(VOICE_DIRS["kokoro"].glob("*.onnx"), None)
    import tts  # noqa: PLC0415 - tts imports audio at load time
    voices = tts.voice_engine_status()
    music = {
        "library": {"available": True, "size_mb": 0,
                    "install": "Drop your own tracks in assets/music/library."},
        "minimax-music": {"available": bool(minimax_key()), "size_mb": 0,
                          "install": "Set MINIMAX_API_KEY. MiniMax Music, instrumental."},
        "lyria-clip": {"available": openrouter_media_available(), "size_mb": 0,
                       "install": "Add an OpenRouter key. Lyria 3 Clip/Pro."},
    }
    return {
        "voices": voices,
        "music": music,
        "rewrite_models": rewrite_models(),
        "translation": translate_providers(),
        "separation": {
            "demucs": {"available": demucs_available(), "size_mb": 700,
                       "install": "pip install demucs. torch is already present."},
            "demucs_ft": {"available": demucs_available(), "size_mb": 1300,
                          "install": "pip install demucs. Better vocals, about four times slower."},
            "roformer": {"available": _roformer_available(), "size_mb": 900,
                         "install": "Install audio-separator and a Mel-Band RoFormer model, "
                                    "or set VIBECUT_ROFORMER_MODEL."},
        },
        "extraction": _extraction_status(),
        "kokoro_model": str(kokoro_model) if kokoro_model else None,
        "assets": {
            "library": len(list(MUSIC_DIRS["library"].glob("*"))) if MUSIC_DIRS["library"].is_dir() else 0,
        },
    }


# ---------------------------------------------------------------- shared hashes


def _text_hash(*parts: str) -> str:
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()[:20]


# ---------------------------------------------------------------- translate memo

MEMO = CACHE / "translate"
TRANSLATION_STATUS = {"provider": "", "source": "", "target": "", "lines": 0, "tried": []}


def translation_status() -> dict:
    return dict(TRANSLATION_STATUS)


def clear_translation_memo(
    lines: list[str], source: str, target: str, provider: str = "auto",
) -> int:
    removed = 0
    # One request clears each memo entry once, even when beats repeat a line.
    for line in dict.fromkeys(str(item) for item in lines):
        path = _memo_file(source, target, str(line), provider or "auto")
        try:
            if path.is_file():
                path.unlink()
                removed += 1
        except OSError:
            pass
    return removed


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


def _translate_apple(
    lines: list[str], source: str, target: str, target_name: str,
) -> list[str] | None:
    binary = _apple_helper()
    if not binary:
        return None

    def translate_chunk(chunk: list[str]) -> list[str] | None:
        payload = json.dumps({
            "source": source, "target": target,
            "targetName": target_name, "lines": chunk,
        }).encode("utf-8")
        for _attempt in range(2):
            try:
                result = subprocess.run(
                    [str(binary)], input=payload, capture_output=True, timeout=600,
                )
            except (OSError, subprocess.SubprocessError):
                continue
            if result.returncode != 0:
                continue
            try:
                data = json.loads(result.stdout.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if isinstance(data, list) and len(data) == len(chunk):
                return [str(item) for item in data]
        return None

    # Apple's framework gets flaky on very large batches; split and retry.
    output: list[str] = []
    for offset in range(0, len(lines), 20):
        translated = translate_chunk(lines[offset:offset + 20])
        if translated is None:
            return None
        output.extend(translated)
    return output


def _translate_opencode(
    lines: list[str], source: str, target: str,
    model: str | None = None, variant: str | None = None,
    timeout: float = 180, max_tokens: int = 2500,
) -> list[str] | None:
    if not opencode_available():
        return None
    prompt = (
        f"Translate these {len(lines)} subtitle lines into {_language_name(target)}. "
        "Keep the same count and order. Use natural spoken language and complete "
        "sentences. Preserve every name, product, number and claim. "
        "JSON array only:\n" + json.dumps(lines, ensure_ascii=False)
    )
    raw = _opencode_json_attempts(
        prompt, max_tokens=max_tokens, model=model, variant=variant, timeout=timeout,
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
    if not isinstance(values, list) or len(values) != len(lines):
        return None
    return [str(value) for value in values]


def _translate_openrouter(
    lines: list[str], source: str, target: str,
    model: str | None = None, reasoning: str | None = None,
    timeout: float = 180, max_tokens: int = 2500,
) -> list[str] | None:
    prompt = (
        f"Translate these {len(lines)} subtitle lines into {_language_name(target)}. "
        "Keep the same count and order, natural spoken language, complete sentences. "
        "Preserve names and numbers. JSON array only:\n"
        + json.dumps(lines, ensure_ascii=False)
    )
    raw = _openrouter_text(
        prompt, json_mode=False, max_tokens=max_tokens,
        model=model, reasoning=reasoning, timeout=timeout,
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
    if not isinstance(values, list) or len(values) != len(lines):
        return None
    return [str(value) for value in values]


def _ready_providers(source: str, target: str) -> list[str]:
    ready: list[str] = []
    if apple_pair_status(source, target) == "installed":
        ready.append("apple_fm")
    return ready


def _rewrite_candidates() -> list[str]:
    """Rewrite-specific order: configured cloud model, then rules."""
    plan = _rewrite_workflow_plan()
    if plan:
        return [item["name"] for item in plan]
    order: list[str] = []
    settings = settings_store.load_settings().get("opencode") or {}
    if opencode_available() and settings.get("use_rewrite", True):
        order.append("opencode")
    openrouter_settings = settings_store.load_settings().get("openrouter") or {}
    if openrouter_available() and openrouter_settings.get("use_rewrite", True):
        order.append("openrouter")
    order.append("rules")
    return order


def _rewrite_workflow_plan() -> list[dict[str, str]]:
    """Map the admin rewrite routes onto the existing rewrite engines."""
    mapping = {
        "opencode-go": "opencode",
        "openrouter": "openrouter",
        "apple": "apple",
    }
    plan: list[dict[str, str]] = []
    for route in _workflow_routes("rewrite"):
        name = mapping.get(str(route.get("provider") or ""))
        if not name:
            continue
        item = {
            "name": name,
            "provider": str(route.get("provider") or ""),
            "model": str(route.get("model") or ""),
            "reasoning": str(_workflow("rewrite").get("reasoning") or "low"),
        }
        plan.append(item)
    plan.append({"name": "rules", "provider": "rules", "model": "", "reasoning": ""})
    return plan


def translation_mode() -> str:
    mode = str((settings_store.load_settings().get("translation") or {}).get("mode") or "auto")
    return mode if mode in {"auto", "local_first", "local_only", "online_only"} else "auto"


def _provider_order(source: str, target: str, provider: str) -> list[str]:
    if provider and provider != "auto":
        return [provider]
    mapping = {"opencode-go": "opencode", "openrouter": "openrouter"}
    online: list[str] = []
    for route in _workflow_routes("translate"):
        candidate = mapping.get(str(route.get("provider") or ""))
        if candidate and candidate not in online:
            if candidate == "opencode" and not opencode_available():
                continue
            if candidate == "openrouter" and not openrouter_available():
                continue
            online.append(candidate)
    if not online:
        settings = settings_store.load_settings().get("opencode") or {}
        if settings.get("use_translate", True) and opencode_available():
            online.append("opencode")
        openrouter_settings = settings_store.load_settings().get("openrouter") or {}
        if openrouter_settings.get("use_translate", True) and openrouter_available():
            online.append("openrouter")
    # Local mode uses Apple Translation.
    local: list[str] = ["apple_fm"]
    mode = translation_mode()
    if mode == "local_only":
        return local
    if mode == "online_only":
        return online
    if mode == "local_first":
        return [*local, *online]
    # Auto: online first, local on-device fallback.
    return [*online, *local]


def translate_lines(
    lines: list[str],
    source: str,
    target: str,
    provider: str = "auto",
) -> list[str]:
    TRANSLATION_STATUS.update({
        "provider": "", "source": source, "target": target,
        "lines": len(lines), "tried": [],
    })
    if not target or target == source:
        TRANSLATION_STATUS["provider"] = "none"
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
    if not missing:
        TRANSLATION_STATUS.update({
            "provider": "cache", "source": source_code, "target": target_code,
            "lines": len(lines), "tried": [],
        })
    if missing:
        errors: list[str] = []
        translate_cfg = _workflow("translate")
        translate_reasoning = str(translate_cfg.get("reasoning") or "low")
        translate_max_tokens = int(translate_cfg.get("max_output_tokens") or 2500)
        translate_timeout = float(translate_cfg.get("timeout_s") or 300)
        route_map = {
            {"opencode-go": "opencode", "openrouter": "openrouter"}.get(
                str(route.get("provider") or ""), ""
            ): route
            for route in translate_cfg.get("routes") or []
        }
        translation_order = _provider_order(source_code, target_code, provider)
        for route_index, candidate in enumerate(translation_order):
            route = route_map.get(candidate, {})
            route_model = str(route.get("model") or "")
            started = time.time()
            if candidate == "opencode":
                result = _translate_opencode(
                    missing, source_code, target_code, model=route_model or None,
                    variant=translate_reasoning or None,
                    max_tokens=translate_max_tokens, timeout=translate_timeout,
                )
            elif candidate == "openrouter":
                result = _translate_openrouter(
                    missing, source_code, target_code, model=route_model or None,
                    reasoning=translate_reasoning or None,
                    max_tokens=translate_max_tokens, timeout=translate_timeout,
                )
            elif candidate == "apple_fm":
                result = _translate_apple(missing, source_code, target_code, target_name)
            else:
                result = None
            _pipeline_event(
                "translate", route_index, candidate, route_model,
                translate_reasoning, started, bool(result),
            )
            if result:
                for original, translated in zip(missing, result):
                    memo[original] = translated
                    _memo_put(source_code, target_code, original, translated, requested)
                TRANSLATION_STATUS.update({
                    "provider": candidate,
                    "source": source_code,
                    "target": target_code,
                    "lines": len(missing),
                    "tried": errors,
                })
                break
            errors.append(candidate)
        else:
            hint = (
                " Check OpenCode Go, add an OpenRouter key, or install the Apple "
                "Translation language pack (System Settings → General → Language & Region)."
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
    return _separate_stem(source, fingerprint, "no_vocals", cancel_event)


def separate_voice(
    source: str,
    fingerprint: str,
    cancel_event: threading.Event | None = None,
    *,
    model: str = "htdemucs",
) -> Path:
    """Return the vocal stem as FLAC, for clean voice references.

    Same cache as ``separate_vocals``; only the kept stem and the Demucs
    checkpoint differ. ``model`` selects ``htdemucs`` or ``htdemucs_ft``.
    """
    return _separate_stem(source, fingerprint, "vocals", cancel_event, model=model)


def _separate_stem(
    source: str,
    fingerprint: str,
    stem: str,
    cancel_event: threading.Event | None = None,
    *,
    model: str = "htdemucs",
) -> Path:
    if model not in ("htdemucs", "htdemucs_ft"):
        raise AudioError(f"Unknown separation model: {model}")
    cache_stem = stem if model == "htdemucs" else f"{stem}-{model}"
    cached = stem_cache_path(fingerprint, cache_stem)
    if cached.is_file() and cached.stat().st_size > 1024:
        return cached
    if not demucs_available():
        raise AudioError("Demucs is not installed. pip install demucs")
    # One scratch folder per run: a render, a clip search and a clone upload
    # can separate at the same time without deleting each other's stems.
    output_dir = CACHE / "stems" / f"run-{uuid.uuid4().hex[:12]}"
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        return _demucs_into(source, cached, output_dir, stem, model, cancel_event)
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def _demucs_into(
    source: str,
    cached: Path,
    output_dir: Path,
    stem: str,
    model: str,
    cancel_event: threading.Event | None,
) -> Path:
    base = [
        sys.executable, "-m", "demucs", "--two-stems=vocals",
        "-n", model, "--shifts", "0", "-j", "4",
        "-o", str(output_dir), source,
    ]
    packed = packs.find_command("separation", "demucs")
    if packed is not None:
        base = [
            str(packed), "--two-stems=vocals", "-n", model,
            "--shifts", "0", "-j", "4", "-o", str(output_dir), source,
        ]
    elif not _module("demucs") and shutil.which("demucs"):
        base = [
            "demucs", "--two-stems=vocals", "-n", model,
            "--shifts", "0", "-j", "4", "-o", str(output_dir), source,
        ]
    try:
        _run([*base, "-d", "mps"], timeout=3600, cancel_event=cancel_event)
    except AudioError:
        if cancel_event is not None and cancel_event.is_set():
            raise
        _run(base, timeout=3600, cancel_event=cancel_event)
    produced = sorted(output_dir.glob(f"{model}/*/{stem}.wav"))
    if not produced:
        label = "instrumental" if stem == "no_vocals" else "vocal"
        raise AudioError(f"Demucs finished but no {label} stem was found.")
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
    return cached


# ---------------------------------------------------------------- mixer


def _music_loop(
    path: Path,
    total: float,
    gain_db: float,
    tmp: Path,
    expr: str | None = None,
    offset: float = 0.0,
) -> Path:
    output = tmp / "music_trim.wav"
    total = max(0.1, float(total or 0.1))
    plan = fit_plan(media_duration(path), total)
    start = float(offset) if offset > 0.01 else float(plan["in"])
    seek = ["-ss", f"{start:.3f}"] if start > 0.01 else []
    filters = [expr or f"volume={gain_db}dB", "aresample=48000"]
    if plan["fade_in"]:
        filters.append(f"afade=t=in:st=0:d={plan['fade_in']:.3f}")
    if plan["fade_out"]:
        filters.append(
            f"afade=t=out:st={plan['fade_out_start']:.3f}:d={plan['fade_out']:.3f}"
        )
    _run([
        _ffmpeg(), "-y", "-v", "error", *seek, "-stream_loop", "-1", "-i", str(path),
        "-t", f"{total:.6f}", "-ar", "48000", "-ac", "2",
        "-af", ",".join(filters),
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


def ensure_terminal(text: str, cjk: bool | None = None) -> str:
    """Finish a spoken line with terminal punctuation, never a dangling cut."""
    value = str(text or "").strip()
    if not value:
        return ""
    value = value.rstrip(" ,，;；:：、-")
    if value.endswith(("…", "...")) :
        value = value.rstrip("…").rstrip(".").rstrip(" ,，;；:：、-")
    if not value:
        return ""
    if value.endswith((".", "!", "?", "。", "！", "？")):
        return value
    use_cjk = CJK_RE.search(value) if cjk is None else cjk
    return value + ("。" if use_cjk else ".")


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
    if provider in {"auto", ""}:
        raw = _workflow_text("story_brief", prompt, json_mode=True)
    else:
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


def _llm_text(prompt: str, provider: str = "auto", model: str | None = None) -> str | None:
    """One JSON text call through the configured cloud route."""
    settings = settings_store.load_settings().get("opencode") or {}
    if (
        provider in {"opencode", "auto", "apple_fm", ""}
        and settings.get("use_brief", True)
        and opencode_available()
    ):
        return _opencode_text(prompt, json_mode=True)
    return None


OPENCODE_PROVIDER = "opencode-go"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_LAST_ERROR = ""
OPENROUTER_LAST_STATUS = 0
OPENROUTER_LAST_MODEL = ""
OPENROUTER_LAST_SOURCE = ""
OPENROUTER_BLOCKED_UNTIL = 0.0
OPENROUTER_QUARANTINE_SECONDS = max(
    0.0, _env_float("VIBECUT_OPENROUTER_QUARANTINE_SECONDS", 300.0),
)

PROVIDER_BREAKER_LOCK = threading.Lock()
PROVIDER_BREAKERS: dict[str, dict] = {}
PROVIDER_BREAKER_FAILURES = max(1, _env_int("VIBECUT_PROVIDER_BREAKER_FAILURES", 3))
PROVIDER_BREAKER_SECONDS = max(1.0, _env_float("VIBECUT_PROVIDER_BREAKER_SECONDS", 90.0))


def _provider_breaker_open(provider: str) -> bool:
    now = time.monotonic()
    with PROVIDER_BREAKER_LOCK:
        state = PROVIDER_BREAKERS.get(provider)
        if not state:
            return False
        until = float(state.get("until") or 0.0)
        if until and until <= now:
            PROVIDER_BREAKERS.pop(provider, None)
            return False
        return bool(until)


def _provider_breaker_fail(provider: str, detail: str) -> None:
    now = time.monotonic()
    with PROVIDER_BREAKER_LOCK:
        state = PROVIDER_BREAKERS.setdefault(
            provider, {"failures": 0, "until": 0.0, "error": ""},
        )
        state["failures"] = int(state.get("failures") or 0) + 1
        state["error"] = str(detail or "")[:240]
        if state["failures"] >= PROVIDER_BREAKER_FAILURES:
            state["until"] = now + PROVIDER_BREAKER_SECONDS


def _provider_breaker_ok(provider: str) -> None:
    with PROVIDER_BREAKER_LOCK:
        PROVIDER_BREAKERS.pop(provider, None)


def reset_provider_breaker(provider: str = "") -> None:
    with PROVIDER_BREAKER_LOCK:
        if provider:
            PROVIDER_BREAKERS.pop(provider, None)
        else:
            PROVIDER_BREAKERS.clear()


def provider_breaker_status(provider: str) -> dict:
    now = time.monotonic()
    with PROVIDER_BREAKER_LOCK:
        state = dict(PROVIDER_BREAKERS.get(provider) or {})
    until = float(state.get("until") or 0.0)
    return {
        "open": bool(until and until > now),
        "failures": int(state.get("failures") or 0),
        "retry_in": round(max(0.0, until - now), 1) if until > now else 0.0,
        "error": str(state.get("error") or ""),
    }


def _is_empty_reply_error(message: str) -> bool:
    text = str(message or "").lower()
    return "empty reply" in text or "returned no output" in text


def openrouter_key() -> str:
    return settings_store.get_secret("openrouter")


def openrouter_key_info() -> dict:
    """Best-effort metadata for the configured OpenRouter key."""
    key = openrouter_key()
    if not key:
        return {}
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/key",
        headers={"Authorization": f"Bearer {key}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    info = data.get("data") if isinstance(data, dict) else None
    return info if isinstance(info, dict) else {}


def _openrouter_configured() -> bool:
    settings = settings_store.load_settings().get("openrouter") or {}
    return bool(openrouter_key()) and bool(settings.get("enabled", True))


def openrouter_blocked() -> bool:
    return time.monotonic() < OPENROUTER_BLOCKED_UNTIL


def openrouter_blocked_seconds() -> float:
    return round(max(0.0, OPENROUTER_BLOCKED_UNTIL - time.monotonic()), 1)


def clear_openrouter_quarantine() -> None:
    global OPENROUTER_BLOCKED_UNTIL
    OPENROUTER_BLOCKED_UNTIL = 0.0


def openrouter_available() -> bool:
    return (
        _openrouter_configured()
        and not openrouter_blocked()
        and not _provider_breaker_open("openrouter")
    )


def openrouter_media_available() -> bool:
    """OpenRouter key usable for speech or music.

    Only an auth quarantine blocks media. The provider breaker counts failed
    chat replies, which say nothing about the speech or music endpoints.
    """
    return _openrouter_configured() and not openrouter_blocked()


def openrouter_model() -> str:
    settings = settings_store.load_settings().get("openrouter") or {}
    return str(settings.get("model") or "deepseek/deepseek-v4.1-flash:floor")


def _openrouter_http_error_text(exc: urllib.error.HTTPError, key: str) -> str:
    try:
        raw = exc.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        raw = ""
    message = ""
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        payload = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or error.get("code") or "")
        elif error:
            message = str(error)
    if not message:
        message = raw
    message = " ".join(str(message or "").split())
    return _redact_secret(message, key)[:240]


def _redact_secret(text: str, key: str = "") -> str:
    value = str(text or "")
    if key:
        value = value.replace(key, "***")
    return re.sub(r"sk-[A-Za-z0-9_-]{6,}", "***", value)


def _openrouter_auth_failure(status: int, message: str = "") -> None:
    global OPENROUTER_BLOCKED_UNTIL, OPENROUTER_LAST_ERROR, OPENROUTER_LAST_STATUS
    OPENROUTER_LAST_STATUS = int(status)
    detail = f"OpenRouter key rejected (HTTP {status}); check the project key."
    if message:
        detail = f"{detail} {message}"
    OPENROUTER_LAST_ERROR = detail[:400]
    OPENROUTER_BLOCKED_UNTIL = time.monotonic() + OPENROUTER_QUARANTINE_SECONDS


def _openrouter_model_error(status: int, message: str) -> bool:
    if status == 404:
        return True
    text = str(message or "").lower()
    return status in {400, 422} and any(
        token in text
        for token in (
            "no endpoints",
            "model not found",
            "model does not exist",
            "model is not available",
            "invalid model",
        )
    )


def openrouter_status() -> dict:
    return {
        "available": openrouter_available(),
        "source": settings_store.secret_source("openrouter"),
        "model": openrouter_model(),
        "status": OPENROUTER_LAST_STATUS,
        "error": OPENROUTER_LAST_ERROR,
        "blocked": openrouter_blocked(),
        "retry_in": openrouter_blocked_seconds(),
        "breaker": provider_breaker_status("openrouter"),
    }


def _openrouter_text(
    prompt: str, json_mode: bool = False, max_tokens: int = 3000,
    force: bool = False, model: str | None = None,
    reasoning: str | None = "low", timeout: float = 180,
) -> str | None:
    global OPENROUTER_LAST_ERROR, OPENROUTER_LAST_STATUS
    global OPENROUTER_LAST_MODEL, OPENROUTER_LAST_SOURCE, OPENROUTER_BLOCKED_UNTIL
    model = model or openrouter_model()
    OPENROUTER_LAST_MODEL = model
    OPENROUTER_LAST_SOURCE = settings_store.secret_source("openrouter")
    key = openrouter_key()
    if not key:
        OPENROUTER_LAST_STATUS = 0
        OPENROUTER_LAST_ERROR = "No OpenRouter key."
        return None
    if not force and openrouter_blocked():
        OPENROUTER_LAST_ERROR = (
            "OpenRouter is quarantined after an auth error; retry in "
            f"{openrouter_blocked_seconds()}s."
        )
        return None
    if not force and _provider_breaker_open("openrouter"):
        OPENROUTER_LAST_ERROR = (
            "OpenRouter circuit is open after repeated empty replies; retry in "
            f"{provider_breaker_status('openrouter')['retry_in']}s."
        )
        return None
    payload = {
        # One configured model only: a 404/model error is reported, never
        # silently switched to another model.
        "model": model,
        "messages": [
            {"role": "system", "content": "You write short vertical video voice overs. Reply with JSON when asked."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "max_tokens": max_tokens,
        "provider": {"sort": "price"},
    }
    effort = str(reasoning or "").lower()
    if effort and effort not in {"none", "off"}:
        payload["reasoning"] = {"effort": effort}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    request = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8787",
            "X-Title": "VibeCut",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=max(10, timeout)) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        status = int(getattr(exc, "code", 0) or 0)
        message = _openrouter_http_error_text(exc, key)
        OPENROUTER_LAST_STATUS = status
        if status in {401, 403}:
            _openrouter_auth_failure(status, message)
        elif _openrouter_model_error(status, message):
            detail = f"Model {model} is not available for this key (HTTP {status})."
            if message:
                detail = f"{detail} {message}"
            OPENROUTER_LAST_ERROR = detail[:400]
        else:
            reason = getattr(exc, "reason", "request failed")
            OPENROUTER_LAST_ERROR = (
                f"OpenRouter HTTP {status}: {message or reason}"
            )[:400]
        return None
    except Exception as exc:  # noqa: BLE001
        OPENROUTER_LAST_STATUS = 0
        OPENROUTER_LAST_ERROR = _redact_secret(str(exc), key)[:240]
        return None
    OPENROUTER_LAST_STATUS = 200
    usage = data.get("usage") or {}
    _record_last_usage(usage)
    usage_store.record(
        "llm", "openrouter", model=model,
        input_tokens=int(usage.get("prompt_tokens") or 0),
        output_tokens=int(usage.get("completion_tokens") or 0),
    )
    choices = data.get("choices") or []
    if not choices:
        OPENROUTER_LAST_ERROR = "OpenRouter returned no choices."
        _provider_breaker_fail("openrouter", OPENROUTER_LAST_ERROR)
        return None
    content = (choices[0].get("message") or {}).get("content")
    if isinstance(content, list):
        content = "".join(str(part.get("text") or "") for part in content if isinstance(part, dict))
    value = str(content or "").strip()
    if not value:
        OPENROUTER_LAST_ERROR = "OpenRouter returned an empty reply."
        _provider_breaker_fail("openrouter", OPENROUTER_LAST_ERROR)
        return None
    OPENROUTER_LAST_ERROR = ""
    clear_openrouter_quarantine()
    _provider_breaker_ok("openrouter")
    return value


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


def _opencode_configured() -> bool:
    settings = settings_store.load_settings().get("opencode") or {}
    return (bool(opencode_key()) or bool(opencode_bin())) and bool(settings.get("enabled", True))


def opencode_available() -> bool:
    return _opencode_configured() and not _provider_breaker_open("opencode")


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


def _opencode_http_text(
    prompt: str, max_tokens: int = 1200, json_mode: bool = False,
    record_failure: bool = True, model: str | None = None,
    variant: str | None = None, timeout: float = 180,
) -> str | None:
    """Direct OpenCode Go API using the project's own key.

    Hidden reasoning can consume the whole completion budget and return
    ``finish_reason=length`` with empty content. Never send ``reasoning_effort``
    while thinking is disabled. If an empty length-limited reply still happens,
    retry once with reasoning explicitly off and a larger output budget.
    """
    global OPENCODE_LAST_ERROR
    key = opencode_key()
    if not key:
        return None
    model = model or opencode_model()
    variant = str(variant or opencode_variant()).lower()
    attempts = (
        (False, max(64, int(max_tokens))),
        (True, max(2048, int(max_tokens) * 2)),
    )
    last_detail = ""
    for attempt, (reasoning_off, budget) in enumerate(attempts):
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You write short vertical video voice overs. Reply with JSON when asked."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.4,
            "max_tokens": budget,
            # Structured short-script work: hidden chain-of-thought on this model
            # can consume the whole token budget and return empty content.
            "thinking": {"type": "disabled"},
        }
        if variant not in {"low", "none", ""} and not reasoning_off:
            body.pop("thinking", None)
            body["reasoning_effort"] = variant
        if reasoning_off:
            body["reasoning_effort"] = "none"
        if json_mode:
            body["response_format"] = {"type": "json_object"}
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
            with urllib.request.urlopen(request, timeout=max(10, timeout)) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            OPENCODE_LAST_ERROR = (
                f"Direct API: HTTP {exc.code} {getattr(exc, 'reason', '')}"
            )[:240]
            return None
        except Exception as exc:  # noqa: BLE001
            OPENCODE_LAST_ERROR = _redact_secret(str(exc), key)[:240]
            return None
        usage = data.get("usage") or {}
        _record_last_usage(usage)
        usage_store.record(
            "llm", "opencode", model=model,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
        )
        choices = data.get("choices") or []
        if not choices:
            OPENCODE_LAST_ERROR = "Direct API returned no choices."
            return None
        choice = choices[0]
        finish_reason = str(choice.get("finish_reason") or "")
        message = choice.get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            content = "".join(str(part.get("text") or "") for part in content if isinstance(part, dict))
        value = str(content or "").strip()
        if value:
            OPENCODE_LAST_ERROR = ""
            return value
        details = usage.get("completion_tokens_details") or {}
        try:
            reasoning_tokens = int(
                details.get("reasoning_tokens")
                or usage.get("reasoning_tokens")
                or 0
            )
        except (TypeError, ValueError):
            reasoning_tokens = 0
        detail = (
            "Direct API returned an empty reply"
            f" (finish_reason={finish_reason or 'unknown'}, "
            f"reasoning_tokens={reasoning_tokens})"
        )
        last_detail = detail
        if finish_reason == "length" and attempt == 0:
            continue
        if attempt:
            detail += " after reasoning-off retry"
        OPENCODE_LAST_ERROR = detail[:300]
        return None
    OPENCODE_LAST_ERROR = last_detail or "Direct API returned an empty reply."
    return None

def _opencode_text(
    prompt: str, json_mode: bool = False, max_tokens: int = 1200,
    force: bool = False, record_failure: bool = True,
    model: str | None = None, variant: str | None = None,
    timeout: float = 180,
) -> str | None:
    """Generate text through OpenCode Go / DeepSeek V4.1 Flash at low reasoning.

    A fresh session pins the model and the ``low`` variant, then ``/generate``
    returns plain text. The session is removed afterwards. The stored OpenCode
    login is used, so no API key is copied into VibeCut.
    """
    global OPENCODE_LAST_ERROR
    model = model or opencode_model()
    variant = str(variant or opencode_variant()).lower()
    if variant not in {"low", "medium", "high", "max", "none"}:
        variant = opencode_variant()
    OPENCODE_LAST_ERROR = ""
    if not force and _provider_breaker_open("opencode"):
        retry_in = provider_breaker_status("opencode")["retry_in"]
        OPENCODE_LAST_ERROR = (
            "OpenCode circuit is open after repeated empty replies; retry in "
            f"{retry_in}s."
        )
        return None
    if not _opencode_configured():
        OPENCODE_LAST_ERROR = "OpenCode is not installed or OpenCode Go is disabled."
        return None
    direct_error = ""
    if opencode_key():
        # Prefer the project key, but do not let a direct-API empty reply or
        # auth failure disable the already-signed-in local OpenCode service.
        http_kwargs = {}
        if model != opencode_model():
            http_kwargs["model"] = model
        if variant != opencode_variant():
            http_kwargs["variant"] = variant
        if timeout != 180:
            http_kwargs["timeout"] = timeout
        value = _opencode_http_text(
            prompt, max_tokens=max_tokens, json_mode=json_mode,
            record_failure=False, **http_kwargs,
        )
        if value:
            _provider_breaker_ok("opencode")
            return value
        direct_error = OPENCODE_LAST_ERROR
        if not opencode_bin():
            if record_failure and _is_empty_reply_error(direct_error):
                _provider_breaker_fail("opencode", direct_error)
            return None
        OPENCODE_LAST_ERROR = direct_error
    created = _opencode_api(["post", "/api/session"], {
        "title": "VibeCut rewrite",
        "model": {
            "id": model,
            "providerID": OPENCODE_PROVIDER,
            "variant": variant,
        },
    })
    session_id = str(((created or {}).get("data") or {}).get("id") or "")
    if not session_id:
        if not OPENCODE_LAST_ERROR:
            OPENCODE_LAST_ERROR = "OpenCode could not create a session."
        return None
    generate_prompt = prompt
    if json_mode:
        generate_prompt = prompt.rstrip() + "\nReply with JSON only."
    try:
        generated = _opencode_api(
            ["post", f"/api/session/{session_id}/generate"],
            {"prompt": generate_prompt},
        )
    finally:
        _opencode_api(["delete", f"/api/session/{session_id}"], allow_empty=True)
    value = str(((generated or {}).get("data") or {}).get("text") or "").strip()
    if value:
        usage_store.record("llm", "opencode-local", calls=1)
        OPENCODE_LAST_ERROR = ""
        _provider_breaker_ok("opencode")
        return value
    if not OPENCODE_LAST_ERROR:
        OPENCODE_LAST_ERROR = direct_error or "OpenCode returned an empty reply."
    if record_failure and _is_empty_reply_error(OPENCODE_LAST_ERROR):
        _provider_breaker_fail("opencode", OPENCODE_LAST_ERROR)
    return None


OPENCODE_RETRY_DELAYS = (0.0, 0.4, 1.0)
OPENCODE_RETRY_JSON_MODES = (True, False, True)


def _opencode_json_attempts(
    prompt: str, max_tokens: int, model: str | None = None,
    variant: str | None = None, timeout: float = 180,
) -> str:
    """Bounded JSON/plain retries with short backoff for empty OpenCode replies."""
    for attempt, delay in enumerate(OPENCODE_RETRY_DELAYS):
        if attempt and _provider_breaker_open("opencode"):
            break
        if delay:
            time.sleep(delay)
        kwargs = {}
        if model is not None:
            kwargs["model"] = model
        if variant is not None:
            kwargs["variant"] = variant
        if timeout != 180:
            kwargs["timeout"] = timeout
        raw = _opencode_text(
            prompt,
            json_mode=OPENCODE_RETRY_JSON_MODES[attempt],
            max_tokens=max_tokens,
            record_failure=False,
            **kwargs,
        ) or ""
        if raw:
            return raw
    if _is_empty_reply_error(OPENCODE_LAST_ERROR):
        _provider_breaker_fail("opencode", OPENCODE_LAST_ERROR)
    return ""


def _target_chars_per_second(target: str) -> float:
    return 4.6 if (target or "").split("-")[0].lower() in {"zh", "ja", "ko"} else 14.0


def _rewrite_prompt(
    script: list[dict], source: str, target: str, mode: str, literal: list[str],
    context: dict | None = None,
) -> str:
    rows = []
    context_beats = (context or {}).get("beats") or []
    chars_per_second = _target_chars_per_second(target)
    for index, line in enumerate(script):
        source_line = ""
        if index < len(context_beats):
            source_line = str(context_beats[index].get("source") or "")
        duration = max(0.8, float(line.get("duration") or 0.0))
        rate = max(0.6, float(line.get("rate") or 1.0))
        rows.append({
            "beat": index,
            "role": str(line.get("role") or "beat"),
            "seconds": round(duration, 2),
            "max_chars": max(12, int((duration - 0.10) * rate * chars_per_second)),
            "max_words": max(3, int((duration - 0.10) * rate * 2.9)),
            "source_line": source_line,
            "literal": literal[index],
        })
    context_text = str(
        (context or {}).get("target_text") or (context or {}).get("full_text") or ""
    ).strip()
    aesthetic = (context or {}).get("aesthetic")
    style = {
        "smooth": "natural, flowing, conversational; connected sentences",
        "viral": "punchy short-video style: hook in the first words, one idea per beat, payoff lands",
        "fun": "playful, warm, light and witty; keep it human and shareable",
        "creative": "vivid, surprising and visual; use fresh phrasing while keeping every fact",
        "sad": "melancholic, intimate and restrained; let the emotion breathe",
        "chill": "calm, relaxed and understated; low-energy, easy delivery",
    }.get(mode, "faithful to the source")
    brief = (context or {}).get("brief")
    parts = [
        f"You are writing ONE coherent short-video voice over in "
        f"{_language_name(target)}, not separate captions.",
        f"The cut has exactly {len(rows)} beat{'s' if len(rows) != 1 else ''}.",
        "Read the FULL VOICE SCRIPT and VIDEO AESTHETIC first. Keep the same story, "
        "speaker, setting, tone, pacing and visual mood.",
        f"Style: {style}.",
        "Hard rules:",
        f"1. Exactly {len(rows)} line{'s' if len(rows) != 1 else ''}, in beat order.",
        "2. Every line is one complete, grammatical spoken sentence and ends with "
        "terminal punctuation.",
        "3. Every line must stay within both max_chars and max_words. Count them "
        "before replying. Condense or rephrase to fit; never truncate, never end "
        "on a conjunction, preposition, article or dangling word, and never output "
        "ellipses or a fragment.",
        "4. Lines must connect: use pronouns and natural transitions so the short "
        "cut reads as one story, not isolated captions.",
        "5. Keep the hook's promise and the payoff's resolution. Keep every named "
        "product, number and claim; invent nothing. Drop secondary detail before "
        "you drop the core meaning.",
        "6. Write native target-language phrasing, not a word-for-word translation.",
        f"Reply with a JSON array of exactly {len(rows)} string{'s' if len(rows) != 1 else ''} and nothing else.",
    ]
    if brief:
        parts.append("STORY BRIEF:\n" + json.dumps(brief, ensure_ascii=False))
    if aesthetic:
        parts.append("VIDEO AESTHETIC:\n" + json.dumps(aesthetic, ensure_ascii=False))
    if context_text and (context or {}).get("full_context"):
        parts.append("FULL VOICE SCRIPT:\n" + context_text[:6000])
    elif context_text:
        query = " ".join(str(row["source_line"]) or str(row["literal"]) for row in rows)
        relevant = retrieve_lines(context_text, query, limit=8)
        if relevant:
            parts.append("RELEVANT VOICE SCRIPT LINES:\n" + "\n".join(relevant))
    parts.append("BEAT SLOTS:\n" + json.dumps(rows, ensure_ascii=False))
    return "\n".join(parts)


BAD_LINE_ENDINGS = {
    "and", "or", "but", "with", "of", "to", "for", "in", "on", "at", "by",
    "from", "as", "that", "which", "who", "whom", "the", "a", "an", "my",
    "your", "his", "her", "their", "this", "these", "those", "such", "very",
    "so", "then", "because", "while", "when", "if", "into", "over", "under",
}


def _line_needs_repair(text: str, duration: float, rate: float, target: str) -> bool:
    value = str(text or "").strip()
    if not value or value.endswith(("…", "...")):
        return True
    words = re.findall(r"[A-Za-z']+", value.lower())
    if words and words[-1] in BAD_LINE_ENDINGS:
        return True
    cjk = (target or "").split("-")[0].lower() in {"zh", "ja", "ko"}
    budget = max(1.0, duration * 1.15)
    return estimate_seconds(value, rate) > budget


def _condense_opencode(
    values: list[str], script: list[dict], target: str, context: dict | None,
    indices: list[int], model: str | None = None, variant: str | None = None,
    timeout: float = 180,
) -> list[str] | None:
    """Second pass: turn overlong or broken lines into complete short sentences."""
    rows = []
    chars_per_second = _target_chars_per_second(target)
    for index in indices:
        duration = max(0.8, float(script[index].get("duration") or 0.0))
        rate = max(0.6, float(script[index].get("rate") or 1.0))
        rows.append({
            "beat": index,
            "text": values[index],
            "seconds": round(duration, 2),
            "max_chars": max(12, int((duration - 0.10) * rate * chars_per_second)),
            "max_words": max(3, int((duration - 0.10) * rate * 2.9)),
        })
    context_text = str(
        (context or {}).get("target_text") or (context or {}).get("full_text") or ""
    ).strip()
    parts = [
        f"You are tightening {len(rows)} lines of a short-video voice over in "
        f"{_language_name(target)}. Each must become one complete, grammatical sentence.",
        "Read the full voice script and aesthetic first. Keep the same meaning, "
        "speaker and story position. Invent nothing.",
        "Respect max_chars and max_words. Condense or rephrase; never truncate, "
        "never end on a conjunction, preposition, article or dangling word, and "
        "never use ellipses.",
        f"Return a JSON array of exactly {len(rows)} strings in the same order.",
    ]
    aesthetic = (context or {}).get("aesthetic")
    if aesthetic:
        parts.append("VIDEO AESTHETIC:\n" + json.dumps(aesthetic, ensure_ascii=False))
    if context_text:
        parts.append("FULL VOICE SCRIPT:\n" + context_text[:4000])
    parts.append("LINES TO TIGHTEN:\n" + json.dumps(rows, ensure_ascii=False))
    raw = _opencode_json_attempts(
        "\n".join(parts), max_tokens=1500, model=model,
        variant=variant, timeout=timeout,
    )
    if not raw:
        return None
    match = re.search(r"\[.*\]", raw, re.S)
    if not match:
        return None
    try:
        repaired = json.loads(match.group(0))
    except ValueError:
        return None
    if not isinstance(repaired, list) or len(repaired) != len(indices):
        return None
    return [str(item).strip() for item in repaired]


def _rewrite_opencode(
    script: list[dict], source: str, target: str, mode: str, literal: list[str],
    context: dict | None = None, model: str | None = None,
    variant: str | None = None, timeout: float = 180,
    max_tokens: int = 3000,
) -> list[str] | None:
    settings = settings_store.load_settings().get("opencode") or {}
    if mode == "literal" or not settings.get("use_rewrite", True) or not opencode_available():
        return None
    prompt = _rewrite_prompt(script, source, target, mode, literal, context)
    raw = _opencode_json_attempts(
        prompt, max_tokens=max_tokens, model=model, variant=variant, timeout=timeout,
    )
    if not raw:
        if not OPENCODE_LAST_ERROR:
            OPENCODE_LAST_ERROR = "OpenCode returned no usable rewrite."
        return None
    match = re.search(r"\[.*\]", raw, re.S)
    if not match:
        OPENCODE_LAST_ERROR = "OpenCode rewrite was not a JSON array."
        return None
    try:
        values = json.loads(match.group(0))
    except ValueError:
        OPENCODE_LAST_ERROR = "OpenCode rewrite JSON could not be parsed."
        return None
    if not isinstance(values, list) or len(values) != len(script):
        OPENCODE_LAST_ERROR = "OpenCode rewrite returned the wrong line count."
        return None
    cjk = (target or "").split("-")[0].lower() in {"zh", "ja", "ko"}
    broken = [
        index for index, value in enumerate(values)
        if _line_needs_repair(
            str(value), float(script[index].get("duration") or 1.0),
            float(script[index].get("rate") or 1.0), target,
        )
    ]
    if broken:
        repaired = _condense_opencode(
            values, script, target, context, broken,
            model=model, variant=variant, timeout=timeout,
        )
        if repaired:
            for offset, index in enumerate(broken):
                values[index] = repaired[offset]
    cleaned: list[str] = []
    for index, value in enumerate(values):
        text = ensure_terminal(str(value).strip(), cjk)
        rate = float(script[index].get("rate") or 1.0)
        duration = max(1.0, float(script[index].get("duration") or 1.0))
        if _line_needs_repair(text, duration, rate, target):
            # Last resort only: the repair pass failed. Keep a clause, never
            # leave an unpunctuated fragment.
            text = trim_to_seconds(text, duration * 1.10, rate)
            text = ensure_terminal(text, cjk)
        if not text:
            return None
        cleaned.append(text)
    return cleaned


def _rewrite_openrouter(
    script: list[dict], source: str, target: str, mode: str, literal: list[str],
    context: dict | None = None, model: str | None = None,
    reasoning: str | None = None, timeout: float = 180,
    max_tokens: int = 3000,
) -> list[str] | None:
    settings = settings_store.load_settings().get("openrouter") or {}
    if mode == "literal" or not settings.get("use_rewrite", True) or not openrouter_available():
        return None
    raw = _openrouter_text(
        _rewrite_prompt(script, source, target, mode, literal, context),
        json_mode=True, max_tokens=max_tokens, model=model,
        reasoning=reasoning, timeout=timeout,
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
    cjk = (target or "").split("-")[0].lower() in {"zh", "ja", "ko"}
    cleaned = []
    for index, value in enumerate(values):
        text = ensure_terminal(str(value).strip(), cjk)
        rate = float(script[index].get("rate") or 1.0)
        duration = max(1.0, float(script[index].get("duration") or 1.0))
        if estimate_seconds(text, rate) > duration * 1.35:
            text = ensure_terminal(trim_to_seconds(text, duration * 1.20, rate), cjk)
        if not text:
            return None
        cleaned.append(text)
    return cleaned


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
    total_cut = sum(float(clip.get("duration") or clip.get("dur") or 0.0) for clip in clips)
    avg_beat = total_cut / max(1, len(clips))
    tag_counts: dict[str, int] = {}
    for scene in scenes:
        for tag in scene.get("tags") or []:
            tag_counts[str(tag)] = tag_counts.get(str(tag), 0) + 1
    has_face = any((scene.get("attention") or {}).get("face") for scene in scenes)
    context = {
        "language": (source_lang or "en").split("-")[0],
        "full_text": full,
        "beats": beats,
        "aesthetic": {
            "moods": scene_moods(scenes, clips)[:4],
            "visual_tags": [
                tag for tag, _count in sorted(
                    tag_counts.items(), key=lambda item: item[1], reverse=True,
                )[:8]
            ],
            "subject": "people" if has_face else "place / object",
            "pace": "fast" if avg_beat < 2.6 else "measured",
            "avg_beat_seconds": round(avg_beat, 2),
            "roles": [str(clip.get("role") or "beat") for clip in clips],
        },
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
        # Keep the complete source sentence. Translation/rewrite condenses it;
        # pre-trimming here was producing fragments that could not be translated
        # into a meaningful line.
        complete = ensure_terminal(text)
        if not complete:
            continue
        lines.append({
            "scene": clip.get("scene"),
            "clip": clip_index,
            "role": clip.get("role") or "beat",
            "duration": round(duration, 3),
            "text": complete,
            "original": text,
            "from_ocr": used_ocr,
            "emotion": emotion,
            "rate": rate,
            "shortened": False,
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
        # The voice track can compress up to 1.35x. Keep a complete sentence
        # within that window; only trim the rare line that cannot fit.
        budget = max(0.7, duration * 1.30)
        fitted = text if estimate_seconds(text, rate) <= budget else trim_to_seconds(
            text, duration * 1.20, rate,
        )
        if not fitted:
            continue
        line["text"] = ensure_terminal(fitted)
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


def _shorten_dub_line(
    text: str,
    native: float,
    slot: float,
    target: str,
    *,
    timeout: float = 90,
) -> str:
    """Shorten one overlong dub line, AI first and a safe trim second."""
    value = str(text or "").strip()
    if not value or slot <= 0:
        return value
    language = _language_name(target or "en")
    native = max(0.05, float(native or 0.0))
    ideal = max(4, int(round(len(value) * float(slot) / native * 0.96)))
    low = max(3, int(ideal * 0.88))
    high = max(low + 2, int(ideal * 1.08))
    best: str = ""
    best_score = -1.0
    for attempt in range(2):
        feedback = ""
        if best:
            measured = estimate_seconds(best, 1.0)
            if measured < float(slot) * 0.92:
                feedback = (
                    f" The previous attempt was too short ({len(best)} characters); "
                    f"write at least {low} characters."
                )
            else:
                feedback = (
                    f" The previous attempt was too long ({len(best)} characters); "
                    f"keep it at most {high} characters."
                )
        prompt = (
            f"Rewrite this {language} subtitle line as one short, complete, "
            f"grammatical spoken sentence between {low} and {high} characters "
            f"(target {ideal}). Keep the same meaning and speaker. "
            "Do not truncate and do not explain." + feedback
            + " Return a JSON array with exactly one string:\n"
            + json.dumps([value], ensure_ascii=False)
        )
        candidate = ""
        try:
            raw = _opencode_json_attempts(
                prompt, max_tokens=300, timeout=timeout,
            )
            if raw:
                match = re.search(r"\[.*\]", raw, re.S)
                values = json.loads(match.group(0)) if match else None
                if isinstance(values, list) and values and str(values[0]).strip():
                    candidate = str(values[0]).strip()
        except Exception:  # noqa: BLE001
            candidate = ""
        if candidate and candidate != value:
            if not candidate.endswith(("。", "！", "？", ".", "!", "?")):
                candidate = ensure_terminal(candidate, bool(CJK_RE.search(candidate)))
            measured = estimate_seconds(candidate, 1.0)
            ratio = measured / max(0.1, float(slot))
            score = 1.0 - min(1.0, abs(ratio - 1.0))
            if score > best_score:
                best, best_score = candidate, score
            if 0.92 <= ratio <= 1.10:
                return candidate
    if best and best_score > 0.55:
        return best
    return shorten_text_for_slot(value, native, slot, language=target)


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
            fit = line.get("fit") if isinstance(line.get("fit"), dict) else None
            if fit is None:
                fit = plan_slot_fit(native, slot)
                line["fit"] = fit
            tempo = float(fit.get("tempo") or 1.0)
            if abs(tempo - 1.0) > 0.005:
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
        f"apad,atrim=0:{total:.6f}"
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


def duck_filter(
    duck_db: float = DUCK_DB,
    attack_ms: float = DUCK_ATTACK_MS,
    release_ms: float = DUCK_RELEASE_MS,
) -> str:
    """Sidechain compressor string for the requested duck depth.

    The threshold is fixed at −40 dBFS and the ratio is solved so a voice at
    roughly −19 dBFS RMS (≈−16 LUFS) loses about ``duck_db`` under the bed.
    """
    depth = abs(min(0.0, float(duck_db or 0.0)))
    over = 21.0
    ratio = 1.0 if depth < 0.05 else max(1.0, min(20.0, over / max(0.1, over - depth)))
    attack = max(1.0, min(2000.0, float(attack_ms or DUCK_ATTACK_MS)))
    release = max(1.0, min(9000.0, float(release_ms or DUCK_RELEASE_MS)))
    return (
        f"sidechaincompress=threshold=0.01:ratio={ratio:.3f}:"
        f"attack={attack:.0f}:release={release:.0f}:makeup=1"
    )


def _duck_and_mix(
    voice: Path | None,
    music: Path | None,
    tmp: Path,
    total: float,
    duck: bool,
    music_gain_db: float,
    voice_gain_db: float,
    cancel_event: threading.Event | None = None,
    *,
    duck_db: float = DUCK_DB,
    attack_ms: float = DUCK_ATTACK_MS,
    release_ms: float = DUCK_RELEASE_MS,
    original: Path | None = None,
    original_gain_db: float = 0.0,
) -> Path:
    output = tmp / "mix.wav"
    if voice and music and original:
        if duck:
            graph = (
                f"[0:a]aresample=48000,volume={voice_gain_db}dB,apad[vfull];"
                f"[1:a]aresample=48000,volume={music_gain_db}dB[m];"
                f"[2:a]aresample=48000,volume={original_gain_db}dB[o];"
                "[vfull]asplit=3[v][sc1][sc2];"
                f"[m][sc1]{duck_filter(duck_db, attack_ms, release_ms)}[ducked];"
                f"[o][sc2]{duck_filter(duck_db, attack_ms, release_ms)}[oducked];"
                "[ducked][oducked][v]amix=inputs=3:normalize=0:dropout_transition=0[out]"
            )
        else:
            graph = (
                f"[0:a]aresample=48000,volume={voice_gain_db}dB[v];"
                f"[1:a]aresample=48000,volume={music_gain_db}dB[m];"
                f"[2:a]aresample=48000,volume={original_gain_db}dB[o];"
                "[v][m][o]amix=inputs=3:normalize=0:dropout_transition=0[out]"
            )
        _run([
            _ffmpeg(), "-y", "-v", "error", "-i", str(voice), "-i", str(music),
            "-i", str(original),
            "-filter_complex", graph, "-map", "[out]",
            "-t", f"{total:.6f}", "-ar", "48000", "-ac", "2",
            "-c:a", "pcm_s16le", str(output),
        ], timeout=1800, cancel_event=cancel_event)
        return output
    if voice and music:
        if duck:
            graph = (
                f"[0:a]aresample=48000,volume={voice_gain_db}dB,apad[vfull];"
                f"[1:a]aresample=48000,volume={music_gain_db}dB[m];"
                "[vfull]asplit=2[v][sc];"
                f"[m][sc]{duck_filter(duck_db, attack_ms, release_ms)}[ducked];"
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


def _wav_mono(path: Path) -> tuple["list[float]", int] | None:
    """Read a PCM WAV into mono float samples for measurement helpers."""
    try:
        with wave.open(str(path), "rb") as handle:
            channels = max(1, handle.getnchannels())
            width = handle.getsampwidth()
            rate = handle.getframerate()
            raw = handle.readframes(handle.getnframes())
    except (OSError, EOFError, wave.Error):
        return None
    if width == 1:
        values = [(value - 128) / 128.0 for value in raw]
    elif width == 2:
        import array

        samples = array.array("h")
        samples.frombytes(raw)
        values = [value / 32768.0 for value in samples]
    elif width == 4:
        import array

        samples = array.array("i")
        samples.frombytes(raw)
        values = [value / 2147483648.0 for value in samples]
    else:
        return None
    if channels > 1:
        values = [
            sum(values[index:index + channels]) / channels
            for index in range(0, len(values) - channels + 1, channels)
        ]
    return values, rate


def speech_spans(
    path: Path,
    *,
    threshold_db: float = -35.0,
    min_speech: float = 0.15,
    min_silence: float = 0.15,
) -> list[tuple[float, float]]:
    """Find speech spans by short-frame RMS. Used for the SNR acceptance gate."""
    loaded = _wav_mono(Path(path))
    if not loaded:
        return []
    samples, rate = loaded
    frame = max(1, int(rate * 0.02))
    spans: list[tuple[float, float]] = []
    active_start: float | None = None
    last_active = 0.0
    for start in range(0, len(samples), frame):
        block = samples[start:start + frame]
        if not block:
            continue
        rms = (sum(value * value for value in block) / len(block)) ** 0.5
        db = 20.0 * math.log10(max(rms, 1e-9))
        at = start / rate
        if db >= threshold_db:
            if active_start is None:
                active_start = at
            last_active = at + len(block) / rate
        elif active_start is not None and at - last_active >= min_silence:
            if last_active - active_start >= min_speech:
                spans.append((round(active_start, 3), round(last_active, 3)))
            active_start = None
    if active_start is not None and last_active - active_start >= min_speech:
        spans.append((round(active_start, 3), round(last_active, 3)))
    merged: list[tuple[float, float]] = []
    for start, end in spans:
        if merged and start - merged[-1][1] < min_silence:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


def _band_energy(samples: Sequence[float], rate: int, low: float, high: float) -> float:
    try:
        import numpy as np  # noqa: PLC0415
    except ImportError:
        return 0.0
    if not samples:
        return 0.0
    values = np.asarray(samples, dtype=np.float64)
    spectrum = np.fft.rfft(values)
    freqs = np.fft.rfftfreq(values.size, 1.0 / max(1, rate))
    mask = (freqs >= low) & (freqs <= high)
    return float(np.sum(np.abs(spectrum[mask]) ** 2))


def speech_band_snr(
    voice: Path,
    music: Path,
    spans: Sequence[tuple[float, float]] | None = None,
    *,
    duck_db: float = 0.0,
    music_gain_db: float = 0.0,
    low: float = SPEECH_BAND_HZ[0],
    high: float = SPEECH_BAND_HZ[1],
) -> float | None:
    """Speech-band SNR of the voice stem over the music stem, in dB.

    Both stems are measured in 300–3400 Hz over the voice's speech spans.
    ``music_gain_db`` and ``duck_db`` are applied to the music result, so the
    number reflects the planned mix without rendering it.
    """
    voice_loaded = _wav_mono(Path(voice))
    music_loaded = _wav_mono(Path(music))
    if not voice_loaded or not music_loaded:
        return None
    voice_samples, voice_rate = voice_loaded
    music_samples, music_rate = music_loaded
    if spans is None:
        spans = speech_spans(Path(voice))
    if not spans:
        return None
    music_attenuation = 10.0 ** ((float(music_gain_db) + float(duck_db)) / 20.0)
    voice_energy = 0.0
    music_energy = 0.0
    for start, end in spans:
        left = max(0, int(float(start) * voice_rate))
        right = min(len(voice_samples), int(float(end) * voice_rate))
        if right <= left:
            continue
        voice_energy += _band_energy(voice_samples[left:right], voice_rate, low, high)
        m_left = max(0, int(float(start) * music_rate))
        m_right = min(len(music_samples), int(float(end) * music_rate))
        if m_right > m_left:
            music_energy += _band_energy(
                music_samples[m_left:m_right], music_rate, low, high,
            )
    music_energy *= music_attenuation * music_attenuation
    if music_energy <= 1e-18:
        return 120.0 if voice_energy > 0 else None
    if voice_energy <= 1e-18:
        return -120.0
    return 10.0 * math.log10(voice_energy / music_energy)


def measure_loudness(path: Path) -> dict[str, float] | None:
    """Integrated LUFS and true peak of a rendered file, for acceptance runs."""
    try:
        result = subprocess.run(
            [
                _ffmpeg(), "-hide_banner", "-nostats", "-i", str(path),
                "-af", "loudnorm=I=-14:TP=-1.5:print_format=json",
                "-f", "null", "-",
            ],
            capture_output=True, text=True, timeout=300,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", result.stderr or "", re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        return {
            "integrated_lufs": round(float(data["input_i"]), 2),
            "true_peak_dbtp": round(float(data["input_tp"]), 2),
        }
    except (ValueError, TypeError, KeyError):
        return None


def store_uploaded_music(source: Path, job_dir: Path) -> Path:
    output = job_dir / "audio" / "uploaded_music.wav"
    output.parent.mkdir(parents=True, exist_ok=True)
    _run([
        _ffmpeg(), "-y", "-v", "error", "-i", str(source), "-vn",
        "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(output),
    ], timeout=900)
    return output


def store_uploaded_voice(source: Path, job_dir: Path) -> Path:
    output = job_dir / "audio" / "uploaded_voice.wav"
    output.parent.mkdir(parents=True, exist_ok=True)
    _run([
        _ffmpeg(), "-y", "-v", "error", "-i", str(source), "-vn",
        "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(output),
    ], timeout=900)
    return output


def _has_audio_stream(source: str) -> bool:
    """False only when ffprobe positively finds no audio stream."""
    probe = shutil.which("ffprobe")
    if not probe:
        return True
    try:
        result = subprocess.run(
            [probe, "-v", "error", "-select_streams", "a", "-show_entries",
             "stream=index", "-of", "csv=p=0", str(source)],
            capture_output=True, text=True, timeout=60, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return True
    return result.returncode != 0 or bool(result.stdout.strip())


def _source_audio_bed(
    source: str,
    tmp: Path,
    cancel_event=None,
    *,
    channels: int = 2,
    rate: int = 48000,
    name: str = "original_audio.wav",
) -> Path:
    """Decode the source's first audio stream to PCM.

    The mixer wants the stereo 48 kHz bed; voice extraction asks for a mono
    file under its own name.
    """
    output = tmp / name
    if not _has_audio_stream(source):
        # A silent source (a written voice script) mixes over silence.
        seconds = max(1.0, media_duration(Path(source)) or 1.0)
        layout = "mono" if channels == 1 else "stereo"
        _run([
            _ffmpeg(), "-y", "-v", "error", "-f", "lavfi",
            "-i", f"anullsrc=channel_layout={layout}:sample_rate={rate}",
            "-t", f"{seconds:.3f}", "-c:a", "pcm_s16le", str(output),
        ], timeout=900, cancel_event=cancel_event)
        return output
    _run([
        _ffmpeg(), "-y", "-v", "error", "-i", source, "-vn", "-map", "0:a:0",
        "-ar", str(rate), "-ac", str(channels), "-c:a", "pcm_s16le", str(output),
    ], timeout=900, cancel_event=cancel_event)
    return output


def _fit_uploaded_voice(
    source: Path, total: float, tmp: Path, gain_db: float = 0.0,
    expr: str | None = None, cancel_event=None,
) -> Path:
    """Fit an uploaded recording to the cut length without changing its voice."""
    output = tmp / "uploaded_voice.wav"
    native = media_duration(source) or 0.0
    tempo = 1.0
    if native > total > 0.1:
        tempo = max(1.0, min(1.35, native / total))
    filters = ["aresample=48000"]
    if tempo > 1.001:
        filters.append(f"atempo={tempo:.4f}")
    filters.extend([
        f"atrim=0:{total:.6f}",
        "apad",
        f"atrim=0:{total:.6f}",
        f"volume={float(gain_db):.2f}dB",
    ])
    if expr:
        filters.append(expr)
    _run([
        _ffmpeg(), "-y", "-v", "error", "-i", str(source),
        "-af", ",".join(filters), "-ar", "48000", "-ac", "2",
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
    declared_mode = audio_mode(audio_plan)
    mode = mixer_mode(declared_mode)
    if mode == "keep":
        return None
    normalized = normalize_audio_plan(audio_plan)
    audio_plan.clear()
    audio_plan.update(normalized)
    tmp.mkdir(parents=True, exist_ok=True)

    voice_plan = audio_plan.get("voice") or {}
    music_plan = audio_plan.get("music") or {}
    translate_plan = audio_plan.get("translate") or {}
    if declared_mode == "dub" and not str(translate_plan.get("target") or "").strip():
        raise AudioError(
            "Dub needs a target language. Open Edit > Audio > Dub, choose a target, "
            "then save before queueing."
        )
    confirmed = str(translate_plan.get("source") or "").strip()
    if confirmed:
        source_lang = confirmed
    lines: list[dict] = []
    voice_path: Path | None = None
    needs_voice = mode in {"voice", "full", "bed"}
    music_is_original = False

    if needs_voice and voice_plan.get("source") == "upload":
        upload = str(voice_plan.get("upload") or "")
        upload_path = (job_dir / upload).resolve() if upload else None
        if not upload_path or not upload_path.is_file() or job_dir.resolve() not in upload_path.parents:
            raise AudioError("Uploaded voice audio is missing. Upload it again.")
        progress(0.86, "Fitting uploaded voice to the cut")
        automation = audio_plan.get("automation") or {}
        voice_path = _fit_uploaded_voice(
            upload_path, total, tmp,
            float(voice_plan.get("gain_db") or 0.0),
            automation_expression(automation.get("voice"), total),
            cancel_event,
        )
    elif needs_voice and voice_plan.get("engine"):
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
        translate_mode = str(translate_plan.get("mode") or "literal")
        provider = str(translate_plan.get("provider") or "auto")
        rewrite_provider = str(translate_plan.get("rewrite_provider") or "auto")
        progress(0.87, f"Adapting {len(script)} lines → {target or source_lang} ({translate_mode})")
        context = (
            transcript_context(
                segments, clips, scenes, source_lang,
                target_lang=target, translate_provider=provider,
                brief_provider=provider, rewrite_provider=rewrite_provider,
            )
            if segments else None
        )
        script = adapt_script(
            script, source_lang, target, translate_mode, provider, context, rewrite_provider,
        )
        apply_overrides(script)
        script = refit_script(script, base_rate)

        clip_mix = audio_plan.get("clip_mix") or []
        base_voice_gain = float(voice_plan.get("gain_db") or 0.0)
        cache_dir = CACHE / "voice"
        prepared: list[dict] = [None] * len(script)  # type: ignore[list-item]
        voice_name = str(voice_plan.get("voice") or "")
        tts_cfg = _workflow("tts")
        selected_engine = str(voice_plan.get("engine") or "auto").lower()
        candidates = voice_candidates(
            selected_engine, str(voice_plan.get("model") or ""),
        )
        primary_engine = candidates[0]["engine"]
        tts_timeout = float(tts_cfg.get("timeout_s") or 300)
        workers = max(1, min(4, len(script)))

        # A route that failed once is skipped for the other lines of this
        # render, so a dead provider costs one attempt, not one per line.
        failed_routes: set[int] = set()

        def synth_one(index: int, line: dict) -> tuple[int, Path]:
            last_error: Exception | None = None
            for route_index, candidate in enumerate(candidates):
                if route_index in failed_routes and route_index < len(candidates) - 1:
                    continue
                engine = candidate["engine"]
                candidate_voice = _tts_voice_for(engine, voice_name, primary_engine)
                model = candidate.get("model") or ""
                key = _text_hash(
                    engine, model, candidate_voice,
                    f"{float(line['rate']):.3f}", line["text"],
                )
                path = _voice_cache(cache_dir, key)
                started = time.time()
                if path.is_file() and path.stat().st_size > 512:
                    line["engine_used"] = engine
                    line["model_used"] = model
                    _pipeline_event(
                        "tts", route_index, candidate.get("provider") or engine,
                        model, "", started, True, "", job_id=job_dir.name,
                    )
                    return index, path
                try:
                    synthesize_line(
                        engine, candidate_voice, line["text"], path,
                        rate=float(line["rate"]),
                        cancel_event=cancel_event,
                        model=model,
                        timeout=tts_timeout,
                    )
                    line["engine_used"] = engine
                    line["model_used"] = model
                    _pipeline_event(
                        "tts", route_index, candidate.get("provider") or engine,
                        model, "", started, True, "", job_id=job_dir.name,
                    )
                    return index, path
                except AudioError as exc:
                    last_error = exc
                    if not (cancel_event is not None and cancel_event.is_set()):
                        failed_routes.add(route_index)
                    _pipeline_event(
                        "tts", route_index, candidate.get("provider") or engine,
                        model, "", started, False, str(exc)[:300],
                        job_id=job_dir.name,
                    )
                    if path.exists():
                        path.unlink()
            raise last_error or AudioError("All voice providers failed.")

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

        prepared = fit_dub_lines(prepared, duration_of=media_duration)
        if declared_mode in {"dub", "voice_over"}:
            for index, item in enumerate(prepared):
                literal = str(item.get("literal") or "").strip()
                if (
                    (item.get("fit") or {}).get("action") != "pad"
                    or not literal
                    or literal == item.get("text")
                ):
                    continue
                expanded = {**item, "text": literal}
                expanded.pop("fit", None)
                _index, path = synth_one(index, expanded)
                native = media_duration(path)
                fit = plan_slot_fit(native, float(expanded.get("slot") or 0.0))
                if fit["action"] != "pad":
                    prepared[index] = {
                        **expanded,
                        "path": path,
                        "gain_db": item.get("gain_db") or 0.0,
                        "fit": fit,
                    }
            for _attempt in range(3):
                flagged = [
                    index for index, item in enumerate(prepared)
                    if (item.get("fit") or {}).get("action") == "shorten"
                ]
                if not flagged:
                    break
                for index in flagged:
                    line = prepared[index]
                    previous = dict(line)
                    previous_fit = previous.get("fit") or {}
                    new_text = _shorten_dub_line(
                        str(line.get("text") or ""),
                        float(previous_fit.get("native") or 0.0),
                        float(line.get("slot") or 0.0),
                        target,
                    )
                    if not new_text or new_text == line.get("text"):
                        continue
                    line["text"] = new_text
                    line["shortened"] = True
                    line.pop("fit", None)
                    _index, path = synth_one(index, line)
                    native = media_duration(path)
                    fit = plan_slot_fit(native, float(line.get("slot") or 0.0))
                    if fit["action"] == "pad" and previous_fit.get("action") == "shorten":
                        # The rewrite overshot. Keep the longer take; atempo can
                        # compress a little, but it cannot invent missing words.
                        prepared[index] = previous
                        continue
                    prepared[index] = {
                        **line,
                        "path": path,
                        "gain_db": line.get("gain_db") or 0.0,
                        "fit": fit,
                    }
                prepared = fit_dub_lines(prepared, duration_of=media_duration)
        audio_plan["_slot_fit"] = slot_fit_summary(prepared)
        audio_plan["_slot_lines"] = [
            {
                "text": item.get("text"),
                "slot": item.get("slot"),
                "native": (item.get("fit") or {}).get("native"),
                "tempo": (item.get("fit") or {}).get("tempo"),
                "action": (item.get("fit") or {}).get("action"),
                "overflow": (item.get("fit") or {}).get("overflow"),
                "shortened": bool(item.get("shortened")),
            }
            for item in prepared
        ]

        automation = audio_plan.get("automation") or {}
        voice_expr = automation_expression(automation.get("voice"), total)
        voice_path = _voice_track(
            clips, prepared, tmp, total,
            float(voice_plan.get("gain_db") or 0.0),
            voice_expr,
            cancel_event,
        )

    music_path: Path | None = None
    chosen: Path | None = None
    grid: dict | None = None
    original_overlay: Path | None = None
    music_source_type = ""
    music_is_original = mode in {"bed", "voice"}
    music_brief = music_plan.get("brief") if isinstance(music_plan.get("brief"), dict) else None
    music_provider = music_plan.get("provider") if isinstance(music_plan.get("provider"), dict) else None
    music_bpm = music_plan.get("bpm")
    music_source = str(music_plan.get("source") or "none")
    music_licence = music_plan.get("licence")
    try:
        base_music_gain = float(
            music_plan.get("gain_db")
            if music_plan.get("gain_db") is not None else MUSIC_BASE_GAIN_DB
        )
    except (TypeError, ValueError):
        base_music_gain = MUSIC_BASE_GAIN_DB
    if mode == "bed":
        progress(0.90, "Keeping the original audio under the voice")
        music_path = _source_audio_bed(source, tmp, cancel_event)
    elif mode == "voice":
        progress(0.90, "Separating the original instrumental")
        music_path = separate_vocals(
            source, str(meta.get("fingerprint") or meta.get("size") or "source"),
            cancel_event,
        )
    elif declared_mode in {"voice_over", "dub"} and music_source in {"none", "original"}:
        if declared_mode == "dub" and music_plan.get("remove_original") and demucs_available():
            progress(0.90, "Separating the original voice from the dub")
            music_path = separate_vocals(
                source, str(meta.get("fingerprint") or meta.get("size") or "source"),
                cancel_event,
            )
        else:
            progress(0.90, "Ducking the original under the voice")
            music_path = _source_audio_bed(source, tmp, cancel_event)
        music_is_original = True
    elif mode in {"original_bed", "music_only", "full"} or music_source not in {"none", ""}:
        if mode == "original_bed":
            progress(0.90, "Keeping the original speech under the bed")
            voice_path = _source_audio_bed(source, tmp, cancel_event)
        progress(0.90, "Preparing music bed")
        locked_hash = str(music_plan.get("locked_hash") or music_plan.get("file_hash") or "")
        if locked_hash:
            chosen = resolve_locked_track(job_dir, locked_hash)
            entry = next(
                (item for item in locked_history(job_dir)
                 if str(item.get("file_hash") or "") == locked_hash),
                {},
            )
            if chosen is None:
                raise AudioError(
                    "The locked music track is missing from this job. Pick or generate a new bed."
                )
            music_source_type = str(entry.get("source") or "library")
            music_brief = music_brief or entry.get("brief")
            music_provider = music_provider or entry.get("provider")
            music_licence = music_licence or entry.get("licence")
            if entry.get("bpm") and music_bpm is None:
                music_bpm = entry.get("bpm")
        elif music_source == "upload":
            upload = str(music_plan.get("upload") or "")
            candidate = (job_dir / upload).resolve() if upload else None
            if not candidate or not candidate.is_file() or job_dir.resolve() not in candidate.parents:
                raise AudioError("Uploaded music is missing. Upload it again.")
            chosen = candidate
            music_source_type = "upload"
        elif music_source in MUSIC_DIRS:
            chosen = resolve_music_track(scenes, clips, music_plan)
            music_source_type = "generated" if music_source == "generated" else "library"
        if chosen is None and music_source in {"minimax-music", "lyria-clip"}:
            prompt = str(music_plan.get("prompt") or "").strip()
            if not prompt or prompt == "auto":
                prompt = music_prompt(
                    music_plan.get("moods") or scene_moods(scenes, clips),
                    min(60.0, max(15.0, total)),
                )
            music_cfg = _workflow("music")
            music_timeout = float(music_cfg.get("timeout_s") or 600)
            candidates = generation_available()
            last_error: Exception | None = None
            if not candidates:
                last_error = AudioError(
                    "No music route has a key. Add a MiniMax or OpenRouter key in Setup."
                )
            for route_index, candidate in enumerate(candidates):
                started = time.time()
                try:
                    chosen = generate_music(
                        candidate["descriptor"], prompt,
                        min(60.0, max(15.0, total)), cancel_event,
                        timeout=music_timeout,
                    )
                except AudioError as exc:
                    last_error = exc
                    _pipeline_event(
                        "music", route_index, candidate["provider"],
                        candidate["model"], "", started, False,
                        str(exc)[:300], job_id=job_dir.name,
                    )
                    continue
                _pipeline_event(
                    "music", route_index, candidate["provider"],
                    candidate["model"], "", started, True, "",
                    job_id=job_dir.name,
                )
                break
            if chosen is not None:
                music_source_type = "generated"
                if music_licence is None:
                    music_licence = {"type": "generated"}
            elif voice_path is not None or declared_mode == "original_bed":
                # The bed is optional here: keep the voice or the original
                # sound and say why the music is missing.
                detail = str(last_error or "All music providers failed.")
                audio_plan.setdefault("_warnings", []).append(
                    f"Music bed skipped: {detail[:200]}"
                )
            else:
                raise last_error or AudioError("All music providers failed.")
        if chosen and chosen.is_file():
            if declared_mode in {"voice_over", "dub"}:
                progress(0.90, "Ducking the original under the voice")
                original_overlay = _source_audio_bed(source, tmp, cancel_event)
            beat_offset = 0.0
            grid = beat_grid(chosen)
            if grid:
                if music_bpm is None:
                    music_bpm = grid.get("bpm")
                if audio_plan.get("beat_sync") and grid.get("beats"):
                    beat_offset = float(grid["beats"][0])
                    audio_plan["_beat_bpm"] = grid.get("bpm")
            automation = audio_plan.get("automation") or {}
            expr = automation_expression(automation.get("music"), total)
            if expr is None:
                expr = music_mix_expression(
                    clips, audio_plan.get("clip_mix"), base_music_gain,
                )
            audio_plan["_used_assets"] = (
                [{
                    "path": chosen.name,
                    "license": normalize_licence(music_licence),
                }]
                if music_licence is not None
                else ensure_licensed([chosen])
            )
            music_path = _music_loop(
                chosen, total, base_music_gain, tmp, expr, beat_offset,
            )
        elif declared_mode in {"voice_over", "dub"}:
            progress(0.90, "Ducking the original under the voice")
            music_path = _source_audio_bed(source, tmp, cancel_event)
            music_is_original = True
        elif music_source in MUSIC_DIRS:
            folder = MUSIC_DIRS[music_source]
            raise AudioError(
                f"No tracks in {folder}. Drop an audio file there or pick another music source."
            )
        elif mode in {"original_bed", "music_only"}:
            raise AudioError(
                "This audio mode needs a music track. Pick a library track or upload one."
            )
        elif music_source not in {"none", ""}:
            raise AudioError("Music generation produced no file.")

    ducked = bool(music_plan.get("duck", audio_plan.get("duck", True))) and mode != "music_only"
    if not needs_voice and mode != "original_bed":
        ducked = False

    if chosen and chosen.is_file() and not music_is_original:
        if music_brief is None:
            music_brief = build_brief(
                "",
                total,
                moods=music_plan.get("moods") or scene_moods(scenes, clips),
            )
        source_seconds = media_duration(chosen)
        plan = fit_plan(source_seconds, total, grid)
        payload = music_json(
            chosen,
            source_type=music_source_type or "library",
            brief=music_brief,
            provider=music_provider,
            licence=music_licence,
            bpm=float(music_bpm) if music_bpm else None,
            in_point=float(plan["in"]),
            out_point=min(source_seconds, float(plan["in"]) + float(total)),
            job_dir=job_dir,
        )
        payload.update({
            "bpm_source": "beat_grid" if grid and grid.get("bpm") else (
                "metadata" if music_bpm else "unavailable"
            ),
            "loop": bool(plan["loop"]),
            "loop_seconds": plan["loop_seconds"],
            "bar": plan["bar"],
            "fade_out": plan["fade_out"],
            "duck": {
                "enabled": ducked,
                "db": float(audio_plan.get("duck_db") or DUCK_DB),
                "attack_ms": DUCK_ATTACK_MS,
                "release_ms": DUCK_RELEASE_MS,
            },
        })
        audio_plan["_music_meta"] = payload
        try:
            music_file = job_dir / "audio" / "music.json"
            music_file.parent.mkdir(parents=True, exist_ok=True)
            music_file.write_text(
                json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8",
            )
        except OSError:
            pass

    if voice_path is None and music_path is None:
        raise AudioError("No voice or music was produced for this audio plan.")

    if voice_path and music_path and not music_is_original:
        try:
            snr = speech_band_snr(
                voice_path, music_path,
                duck_db=float(audio_plan.get("duck_db") or DUCK_DB) if ducked else 0.0,
                music_gain_db=base_music_gain,
            )
            if snr is not None:
                audio_plan["_speech_snr_db"] = round(snr, 2)
        except (OSError, ValueError, wave.Error):
            pass

    progress(0.94, "Mixing audio")
    mixed = _duck_and_mix(
        voice_path, music_path, tmp, total,
        ducked,
        base_music_gain,
        float(voice_plan.get("gain_db") or 0.0),
        cancel_event,
        duck_db=float(audio_plan.get("duck_db") or DUCK_DB),
        original=original_overlay,
    )
    final = tmp / "final_audio.wav"
    loudness = loudness_settings(audio_plan)
    audio_plan["_loudness"] = loudness
    _run([
        _ffmpeg(), "-y", "-v", "error", "-i", str(mixed),
        "-af", (
            f"loudnorm=I={loudness['lufs']:.2f}:TP={loudness['true_peak']:.2f}:"
            f"LRA={loudness['lra']:.2f}"
        ),
        "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(final),
    ], timeout=900, cancel_event=cancel_event)
    return final


# ---------------------------------------------------------------- cache hygiene


CACHE_DIRS = (
    "segments", "voice", "stems", "music", "masters", "translate",
    "voice_refs", "voice-clone",
)


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
            if name == "stems" and path.relative_to(base).parts[0].startswith("run"):
                continue  # Demucs scratch: handled below
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
    # A live Demucs run is capped at an hour; older run folders are leftovers
    # from a crash. The CLI can prune while the app runs, so keep fresh ones.
    for scratch in (CACHE / "stems").glob("run*"):
        try:
            stale = now - scratch.stat().st_mtime > 2 * 3600
        except OSError:
            continue
        if scratch.is_dir() and stale:
            shutil.rmtree(scratch, ignore_errors=True)
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
REWRITE_VERSION = 7
REWRITE_STATUS = {
    "requested": False,
    "ok": True,
    "provider": "",
    "used": "literal",
    "fallback": False,
    "error": "",
    "attempts": [],
}


def rewrite_status() -> dict:
    status = dict(REWRITE_STATUS)
    status["attempts"] = list(REWRITE_STATUS.get("attempts") or [])
    return status


def _rewrite_status_reset(requested: bool) -> None:
    REWRITE_STATUS.update({
        "requested": bool(requested),
        "ok": True,
        "provider": "",
        "used": "literal",
        "fallback": False,
        "error": "",
        "attempts": [],
    })


def _rewrite_failure_detail(attempts: list[dict]) -> str:
    errors = [
        f"{item.get('provider')}: {str(item.get('error') or 'no usable reply')[:180]}"
        for item in attempts
        if item.get("provider")
    ]
    if not errors:
        return "No rewrite provider returned usable lines."
    return ("Rewrite unavailable (" + "; ".join(errors) + ").")[:400]


def mark_rewrite_error(message: str) -> None:
    REWRITE_STATUS.update({
        "ok": False,
        "fallback": True,
        "error": str(message or "")[:400],
    })


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


def _rewrite_provider_tag(
    candidate: str, model: str | None = None, reasoning: str | None = None,
) -> str:
    """Cache namespace for the actual rewrite provider and model."""
    name = str(candidate or "").strip()
    if name == "opencode":
        return f"opencode:{model or opencode_model()}:{reasoning or opencode_variant()}"
    if name == "openrouter":
        return f"openrouter:{model or openrouter_model()}:{reasoning or ''}"
    if name == "apple":
        return "apple:on-device-3b"
    return name or "unknown"


def _rewrite_file(
    source: str, target: str, mode: str, text: str,
    context: dict | None = None, provider: str = "",
) -> Path:
    key = hashlib.sha1(
        f"v{REWRITE_VERSION}|{provider}|{source}|{target}|{mode}|"
        f"{_context_hash(context)}|{text}".encode("utf-8"),
    ).hexdigest()[:24]
    return REWRITE / key[:2] / f"{key}.txt"


def _rewrite_memo(
    source: str, target: str, mode: str, text: str,
    context: dict | None = None, provider: str = "",
) -> str | None:
    path = _rewrite_file(source, target, mode, text, context, provider)
    if not path.is_file():
        return None
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def _rewrite_put(
    source: str, target: str, mode: str, text: str, value: str,
    context: dict | None = None, provider: str = "",
) -> None:
    if not value or provider == "rules":
        return
    path = _rewrite_file(source, target, mode, text, context, provider)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
    except OSError:
        pass


def clear_rewrite_memo(
    lines: list[str], source: str, target: str, mode: str,
    provider: str = "", context: dict | None = None,
) -> int:
    """Drop rewrite cache entries for one provider/model, or all known ones."""
    tags = [provider] if provider else [
        _rewrite_provider_tag(name)
        for name in ("opencode", "openrouter", "apple")
    ]
    if provider and ":" not in provider:
        tags = [_rewrite_provider_tag(provider)]
    removed = 0
    seen: set[Path] = set()
    for line in dict.fromkeys(str(item) for item in lines):
        for tag in tags:
            path = _rewrite_file(source, target, mode, str(line), context, tag)
            if path in seen:
                continue
            seen.add(path)
            try:
                if path.is_file():
                    path.unlink()
                    removed += 1
            except OSError:
                pass
    return removed


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
    if mode in {"smooth", "fun", "creative", "sad", "chill"} and value:
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
        elif mode in {"smooth", "fun", "creative", "sad", "chill"} and index > 0:
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
    mode = mode if mode in {"literal", "smooth", "viral", "fun", "creative", "sad", "chill"} else "smooth"
    requested = mode != "literal"
    _rewrite_status_reset(requested)
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
    if requested:
        route_plan: list[dict[str, str]] = []
        route_by_name: dict[str, dict[str, str]] = {}
        if rewrite_provider and rewrite_provider not in ("auto", ""):
            order = [rewrite_provider]
        elif provider and provider not in ("auto", ""):
            order = [provider]
        else:
            route_plan = _rewrite_workflow_plan()
            order = _rewrite_candidates()
            route_by_name = {item["name"]: item for item in route_plan}
        resolved: dict[int, str] = {}
        attempts: list[dict] = []
        succeeded = False
        ai_providers = {"opencode", "openrouter", "apple"}
        rewrite_cfg = _workflow("rewrite")
        route_max_tokens = int(rewrite_cfg.get("max_output_tokens") or 3000)
        route_timeout = float(rewrite_cfg.get("timeout_s") or 300)
        for route_index, name in enumerate(order):
            route = route_by_name.get(name, {})
            route_model = str(route.get("model") or "")
            route_reasoning = str(route.get("reasoning") or "")
            pending = [index for index in range(len(lines)) if index not in resolved]
            if not pending:
                succeeded = True
                break
            tag = _rewrite_provider_tag(name, route_model, route_reasoning)
            started = time.time()
            memo_hits: dict[int, str] = {}
            missing = list(pending)
            if name != "rules":
                missing = []
                for index in pending:
                    hit = _rewrite_memo(
                        source_lang, target_lang, mode, literals[index], context, tag,
                    )
                    if hit:
                        memo_hits[index] = hit
                    else:
                        missing.append(index)
            if not missing:
                resolved.update(memo_hits)
                used = "cached"
                REWRITE_STATUS.update({
                    "ok": True,
                    "provider": name,
                    "used": "cached",
                    "fallback": False,
                    "error": "",
                    "attempts": attempts,
                })
                succeeded = True
                break
            subset = [lines[index] for index in missing]
            subset_literal = [literals[index] for index in missing]
            rewritten: list[str] | None = None
            route_kwargs = {}
            if route_model:
                route_kwargs["model"] = route_model
            if name == "opencode":
                if route_reasoning:
                    route_kwargs["variant"] = route_reasoning
                rewritten = _rewrite_opencode(
                    subset, source_lang, target_lang, mode, subset_literal, context,
                    max_tokens=route_max_tokens, timeout=route_timeout,
                    **route_kwargs,
                )
            elif name == "openrouter":
                if route_reasoning:
                    route_kwargs["reasoning"] = route_reasoning
                rewritten = _rewrite_openrouter(
                    subset, source_lang, target_lang, mode, subset_literal, context,
                    max_tokens=route_max_tokens, timeout=route_timeout,
                    **route_kwargs,
                )
            elif name == "rules":
                rewritten = _rules_rewrite(subset, source_lang, target_lang, mode, subset_literal)
            if rewritten:
                _pipeline_event(
                    "rewrite", route_index, route.get("provider") or name,
                    route_model, route_reasoning, started, True,
                )
                for offset_index, index in enumerate(missing):
                    value = rewritten[offset_index]
                    resolved[index] = value
                    if name != "rules":
                        _rewrite_put(
                            source_lang, target_lang, mode, literals[index],
                            value, context, tag,
                        )
                resolved.update(memo_hits)
                used = name
                ai_failed = any(
                    item.get("provider") in ai_providers for item in attempts
                )
                fallback = bool(name == "rules" and ai_failed)
                detail = _rewrite_failure_detail(attempts) if fallback else ""
                REWRITE_STATUS.update({
                    "ok": True,
                    "provider": name,
                    "used": used,
                    "fallback": fallback,
                    "error": (
                        f"AI rewrite failed; used rules fallback. {detail}"
                    )[:400] if fallback else "",
                    "attempts": attempts,
                })
                succeeded = True
                break
            detail = ""
            if name == "opencode":
                detail = OPENCODE_LAST_ERROR
            elif name == "openrouter":
                detail = OPENROUTER_LAST_ERROR
            _pipeline_event(
                "rewrite", route_index, route.get("provider") or name,
                route_model, route_reasoning, started,
                bool(rewritten), str(detail or "")[:240],
            )
            attempts.append({
                "provider": name,
                "error": str(detail or "")[:240],
            })
        if not succeeded:
            resolved = {index: literals[index] for index in range(len(lines))}
            used = "literal"
            REWRITE_STATUS.update({
                "ok": False,
                "provider": "",
                "used": "literal",
                "fallback": True,
                "error": _rewrite_failure_detail(attempts),
                "attempts": attempts,
            })
        literals = [resolved.get(index, literals[index]) for index in range(len(lines))]

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


# ---------------------------------------------------------------- mix helpers


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


def clear_workflow_caches() -> None:
    """Invalidate text, voice, and music caches after a model-route change."""
    for directory in (
        BRIEFS, MEMO, REWRITE, CACHE / "voice", CACHE / "music",
    ):
        shutil.rmtree(directory, ignore_errors=True)


# ---------------------------------------------------------------- split modules
# Re-exports keep every existing caller (and `audio.*` monkeypatch) working.
from stt import CLOUD_STT_PROVIDERS, cloud_stt_key, deepgram_key, groq_key, openai_key  # noqa: E402,F401
from tts import (  # noqa: E402,F401
    _SAY_VOICE_RE,
    _elevenlabs_voice,
    _kokoro_files_for,
    _kokoro_voice,
    _minimax_voice,
    _openrouter_voice,
    _say_voice,
    _to_flac,
    _tts_candidates,
    _tts_route_candidates,
    _tts_voice_for,
    _voice_cache,
    fit_dub_lines,
    kokoro_model_dir,
    list_voices,
    plan_slot_fit,
    shorten_text_for_slot,
    slot_fit_summary,
    synthesize_line,
    voice_candidates,
    voice_sample,
)
from music import (  # noqa: E402,F401
    BEATS,
    _lyria_music,
    _minimax_music,
    _music_route_candidates,
    _slug,
    asset_license,
    beat_grid,
    brief_hash,
    build_brief,
    ensure_licensed,
    fit_plan,
    generate_candidates,
    generate_music,
    generation_available,
    generation_cache_key,
    list_music,
    lock_track,
    locked_history,
    music_json,
    music_prompt,
    normalize_licence,
    pick_music,
    preview_candidate,
    resolve_locked_track,
    resolve_music_track,
    save_generated_asset,
    scene_moods,
    sha256_file,
    snap_clips,
)
