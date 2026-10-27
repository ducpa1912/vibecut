"""Text-to-speech voices, engine adapters and per-line synthesis.

Split out of `audio.py` without behaviour change. Shared process helpers,
caches and the audio plan stay in `audio.py`; every call back goes through the
facade so existing tests and callers can keep patching `audio.*`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

# Imported last: audio re-exports this module, so the facade must finish first.
import audio  # noqa: E402


_SAY_VOICE_RE = re.compile(r"^(?P<name>.+?)\s{2,}(?P<lang>[a-zA-Z_-]+)\s*(?:#.*)?$")


def list_voices(engine: str) -> list[dict]:
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
            lang = match.group("lang").strip()
            voices.append({"id": name, "name": name, "lang": lang})
        voices.sort(key=lambda item: (item["lang"], item["name"]))
        return voices

    if engine == "piper":
        voices = []
        for directory in (audio.VOICE_DIRS["piper"], Path.home() / ".local/share/piper"):
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
        directory = audio.VOICE_DIRS["kokoro"]
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

    if engine == "fish":
        if not audio.openrouter_available():
            return []
        return [{"id": "default", "name": "Fish default", "lang": "multi"}]

    if engine == "gemini":
        if not audio.openrouter_available():
            return []
        names = ["Kore", "Zephyr", "Puck", "Charon", "Leda", "Aoede", "Fenrir"]
        return [{"id": name, "name": name, "lang": "multi"} for name in names]

    if engine == "openai":
        if not audio.openai_key():
            return []
        names = ["alloy", "ash", "ballad", "coral", "echo", "fable",
                 "nova", "onyx", "sage", "shimmer", "verse"]
        return [{"id": name, "name": name, "lang": "multi"} for name in names]

    if engine == "groq":
        if not audio.groq_key():
            return []
        names = ["autumn", "diana", "hannah", "austin", "daniel", "troy"]
        return [{"id": name, "name": name, "lang": "en"} for name in names]

    if engine == "deepgram":
        if not audio.deepgram_key():
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

    if engine == "cartesia":
        key = audio.cartesia_key()
        if not key:
            return []
        request = urllib.request.Request(
            "https://api.cartesia.ai/voices?limit=100",
            headers={
                "X-API-Key": key,
                "Cartesia-Version": "2026-08-14",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise audio.AudioError(f"Cartesia voices failed: {exc}") from exc
        items = data.get("data") if isinstance(data, dict) else data
        voices = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            voice_id = item.get("id")
            if not voice_id:
                continue
            voices.append({
                "id": voice_id,
                "name": item.get("name") or voice_id,
                "lang": str(item.get("language") or "multi"),
            })
        return voices

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

    return []


def _tts_route_candidates() -> list[dict[str, str]]:
    """Ordered TTS candidates from the admin workflow, model included."""
    cfg = audio._workflow("tts")
    candidates: list[dict[str, str]] = []
    for route in cfg.get("routes") or []:
        provider = str(route.get("provider") or "").lower()
        model = str(route.get("model") or "").strip()
        if provider == "minimax":
            candidates.append({
                "engine": "minimax", "provider": provider, "model": model,
            })
        elif provider == "openrouter":
            engine = "fish" if "fish" in model.lower() else "gemini"
            candidates.append({
                "engine": engine, "provider": provider, "model": model,
            })
        elif provider == "local":
            engine = model if model in {"kokoro", "piper", "say"} else "kokoro"
            candidates.append({
                "engine": engine, "provider": provider, "model": model or engine,
            })
        elif provider in {"elevenlabs", "openai", "groq", "deepgram", "cartesia"}:
            candidates.append({
                "engine": provider, "provider": provider, "model": model,
            })
    return candidates


def _tts_candidates(engine_name: str = "auto") -> list[str]:
    """Compatibility helper: ordered engine names from configured routes."""
    return [item["engine"] for item in audio._tts_route_candidates()]


def _tts_voice_for(candidate: str, preferred: str, primary: str) -> str:
    preferred = str(preferred or "")
    if candidate == "fish":
        if candidate == primary and preferred not in {"", "default"}:
            return preferred
        return ""
    if candidate in {"elevenlabs", "cartesia"}:
        return preferred if candidate == primary and preferred not in {"", "default"} else ""
    if candidate == primary and preferred not in {"", "default"}:
        return preferred
    if candidate == "gemini":
        return "Kore"
    if candidate == "kokoro":
        return "af_heart"
    if candidate == "say":
        return "Samantha"
    if candidate == "piper":
        voices = audio.list_voices("piper")
        return voices[0]["id"] if voices else ""
    if candidate == "minimax":
        return "female-shaonv"
    if candidate == "openai":
        return "alloy"
    if candidate == "groq":
        return "troy"
    if candidate == "deepgram":
        return "aura-2-thalia-en"
    return preferred


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


def _piper_voice(
    text: str, voice: str, output: Path, rate: float = 1.0, cancel_event=None,
) -> None:
    model = Path(voice)
    if not model.is_file():
        raise audio.AudioError("Pick a Piper voice model (.onnx) first.")
    binary = shutil.which("piper")
    base = [binary, "-m", str(model)] if binary else [
        sys.executable, "-m", "piper", "-m", str(model),
    ]
    length_scale = max(0.65, min(1.6, 1.0 / max(0.6, float(rate or 1.0))))
    with_rate = [*base, "--length-scale", f"{length_scale:.3f}", "-f", str(output)]
    try:
        audio._run(with_rate, input_text=text, timeout=600, cancel_event=cancel_event)
        return
    except audio.AudioError:
        pass
    audio._run([*base, "-f", str(output)], input_text=text, timeout=600, cancel_event=cancel_event)


def _kokoro_files_for(voice: str) -> tuple[Path | None, Path | None]:
    """Prefer the model whose language matches the voice, then the smallest precision."""
    files = sorted(audio.VOICE_DIRS["kokoro"].glob("*.onnx"))
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
    voices = sorted(audio.VOICE_DIRS["kokoro"].glob(f"voices*{version}*.bin"))
    if not voices:
        voices = sorted(audio.VOICE_DIRS["kokoro"].glob("voices*.bin"))
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


def _openai_voice(
    text: str, voice: str, output: Path, rate: float = 1.0,
    model: str = "", timeout: float = 300,
) -> None:
    key = audio.openai_key()
    if not key:
        raise audio.AudioError("Set OPENAI_API_KEY to use OpenAI voice.")
    payload = json.dumps({
        "model": model or os.environ.get("VIBECUT_OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
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
        with urllib.request.urlopen(request, timeout=max(10, timeout)) as response:
            raw.write_bytes(response.read())
    except Exception as exc:  # noqa: BLE001
        raise audio.AudioError(f"OpenAI voice failed: {exc}") from exc
    extra = ["-filter:a", f"atempo={max(0.7, min(1.4, float(rate or 1.0)))}"] if rate and rate != 1.0 else []
    audio._convert(raw, output, extra)
    try:
        raw.unlink()
    except OSError:
        pass


def _groq_voice(
    text: str, voice: str, output: Path, rate: float = 1.0,
    model: str = "", timeout: float = 300,
) -> None:
    key = audio.groq_key()
    if not key:
        raise audio.AudioError("Set GROQ_API_KEY to use Groq voice.")
    payload = json.dumps({
        "model": model or os.environ.get("VIBECUT_GROQ_TTS_MODEL", "canopylabs/orpheus-v1-english"),
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
        with urllib.request.urlopen(request, timeout=max(10, timeout)) as response:
            raw.write_bytes(response.read())
    except Exception as exc:  # noqa: BLE001
        raise audio.AudioError(f"Groq voice failed: {exc}") from exc
    extra = ["-filter:a", f"atempo={max(0.7, min(1.4, float(rate or 1.0)))}"] if rate and rate != 1.0 else []
    audio._convert(raw, output, extra)
    try:
        raw.unlink()
    except OSError:
        pass


def _deepgram_voice(
    text: str, voice: str, output: Path, rate: float = 1.0,
    model: str = "", timeout: float = 300,
) -> None:
    key = audio.deepgram_key()
    if not key:
        raise audio.AudioError("Set DEEPGRAM_API_KEY to use Deepgram voice.")
    model = model or voice or "aura-2-thalia-en"
    payload = json.dumps({"text": text}).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.deepgram.com/v1/speak?model={model}",
        data=payload,
        headers={"Authorization": f"Token {key}", "Content-Type": "application/json"},
        method="POST",
    )
    raw = output.with_name(f"{output.stem}.deepgram.tmp.mp3")
    try:
        with urllib.request.urlopen(request, timeout=max(10, timeout)) as response:
            raw.write_bytes(response.read())
    except Exception as exc:  # noqa: BLE001
        raise audio.AudioError(f"Deepgram voice failed: {exc}") from exc
    extra = ["-filter:a", f"atempo={max(0.7, min(1.4, float(rate or 1.0)))}"] if rate and rate != 1.0 else []
    audio._convert(raw, output, extra)
    try:
        raw.unlink()
    except OSError:
        pass


def _cartesia_voice(
    text: str, voice: str, output: Path, rate: float = 1.0,
    model: str = "sonic-3.6", timeout: float = 300,
) -> None:
    key = audio.cartesia_key()
    if not key:
        raise audio.AudioError("Set CARTESIA_API_KEY to use Cartesia voice.")
    if not voice:
        raise audio.AudioError("Pick a Cartesia voice first.")
    payload = json.dumps({
        "model_id": model or "sonic-3.6",
        "transcript": text,
        "voice": voice,
        "output_format": {
            "container": "wav",
            "encoding": "pcm_s16le",
            "sample_rate": 44100,
        },
        "generation_config": {"speed": 1.0, "volume": 1.0},
    }).encode("utf-8")
    request = urllib.request.Request(
        "https://api.cartesia.ai/tts/bytes",
        data=payload,
        headers={
            "X-API-Key": key,
            "Cartesia-Version": "2026-08-14",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    raw = output.with_name(f"{output.stem}.cartesia.tmp.wav")
    try:
        with urllib.request.urlopen(request, timeout=max(10, timeout)) as response:
            raw.write_bytes(response.read())
    except Exception as exc:  # noqa: BLE001
        raise audio.AudioError(f"Cartesia voice failed: {exc}") from exc
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
    model = model or audio._workflow_route_model(
        "tts", "openrouter",
        "fish-audio/s2.1-pro-free:free" if engine == "fish" else "google/gemini-3.8-flash-lite-tts",
    )
    default_voice = "" if engine == "fish" else "Kore"
    voice_value = default_voice if voice in {"", "default"} else voice
    body = {
        "model": model,
        "input": text,
        "voice": voice_value,
        # OpenRouter speech returns MP3 or PCM, not WAV. Convert afterwards.
        "response_format": "mp3",
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
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    flac = output.suffix.lower() == ".flac"
    target = output.with_suffix(".wav") if flac else output
    if engine == "say":
        if not audio.say_available():
            raise audio.AudioError("Apple say is not available.")
        audio._say_voice(text, voice, rate, target)
    elif engine == "piper":
        if not audio.piper_available():
            raise audio.AudioError("Piper is not installed. pip install piper-tts")
        audio._piper_voice(text, voice, target, rate, cancel_event)
    elif engine == "kokoro":
        if not audio.kokoro_available():
            raise audio.AudioError("Kokoro is not installed or has no model files.")
        audio._kokoro_voice(text, voice, target, rate, cancel_event)
    elif engine == "elevenlabs":
        audio._elevenlabs_voice(text, voice, target, rate, model=model, timeout=timeout)
    elif engine == "openai":
        audio._openai_voice(text, voice, target, rate, model=model, timeout=timeout)
    elif engine == "groq":
        audio._groq_voice(text, voice, target, rate, model=model, timeout=timeout)
    elif engine == "deepgram":
        audio._deepgram_voice(text, voice, target, rate, model=model, timeout=timeout)
    elif engine == "cartesia":
        audio._cartesia_voice(text, voice, target, rate, model=model, timeout=timeout)
    elif engine == "minimax":
        audio._minimax_voice(text, voice, target, rate, model=model, timeout=timeout)
    elif engine in {"fish", "gemini"}:
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


def voice_sample(
    engine: str,
    voice: str,
    text: str,
    cache_dir: Path,
    rate: float = 1.0,
) -> Path:
    key = audio._text_hash(engine, voice, f"{rate:.2f}", text)
    target = audio._voice_cache(cache_dir, key, ".wav")
    if target.is_file() and target.stat().st_size > 512:
        return target
    return audio.synthesize_line(engine, voice, text, target, rate=rate)
