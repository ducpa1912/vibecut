"""Music library, cloud generation and beat fitting.

Split out of `audio.py` without behaviour change. The mixer and `AudioPlan`
builders stay in `audio.py`; every call back goes through the facade so
existing tests and callers can keep patching `audio.*`.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping, Sequence

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

# Imported last: audio re-exports this module, so the facade must finish first.
import audio  # noqa: E402

MUSIC_SCHEMA = 1
MUSIC_SOURCE_TYPES = ("library", "upload", "generated", "original")
LICENCE_TYPES = ("own", "licensed", "cc", "generated", "unknown")
BRIEF_TAIL_SECONDS = 4.0
GENERATION_SEED = 7
DEFAULT_FADE_SECONDS = 1.5
DEFAULT_CROSSFADE_SECONDS = 0.25
GENERATED_TERMS_URLS = {
    "minimax": "https://www.minimax.io/terms",
    "openrouter": "https://openrouter.ai/terms",
}


def list_music(source: str) -> list[dict]:
    directory = audio.MUSIC_DIRS.get(source)
    tracks: list[dict] = []
    if not directory or not directory.is_dir():
        return tracks
    for path in sorted(directory.rglob("*")):
        if path.suffix.lower() not in {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}:
            continue
        name = path.stem.lower()
        moods = [word for word in audio.MOOD_WORDS if word in name]
        tracks.append({
            "id": str(path),
            "name": path.stem,
            "moods": moods,
            "size": path.stat().st_size,
            "license": audio.asset_license(path),
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
    if source not in audio.MUSIC_DIRS:
        return None
    track_id = str(music_plan.get("track") or "")
    if track_id and Path(track_id).is_file():
        return Path(track_id)
    tracks = audio.list_music(source)
    moods = music_plan.get("moods") or audio.scene_moods(scenes, clips)
    picked = audio.pick_music(tracks, moods)
    return Path(picked["id"]) if picked else None


def music_prompt(moods: list[str], target: float) -> str:
    primary = moods[0] if moods else "ambient"
    return (
        f"{primary} background music bed for a short vertical video, "
        f"soft, no vocals, clean loop, {int(max(8, min(47, target)))} seconds"
    )


# ---------------------------------------------------------------- brief + candidates


_BPM_BANDS = {
    "upbeat": (110.0, 128.0),
    "energetic": (110.0, 132.0),
    "groove": (105.0, 124.0),
    "calm": (68.0, 88.0),
    "ambient": (60.0, 82.0),
    "soft": (66.0, 90.0),
    "lofi": (72.0, 92.0),
    "warm": (84.0, 102.0),
    "cinematic": (78.0, 100.0),
    "piano": (74.0, 96.0),
    "tense": (88.0, 108.0),
    "dramatic": (82.0, 104.0),
}
_GENRE_HINTS = {
    "upbeat": "percussive pop",
    "energetic": "driving electronic",
    "groove": "light funk",
    "calm": "ambient piano",
    "ambient": "ambient pad",
    "soft": "soft acoustic",
    "lofi": "lo-fi hip hop",
    "warm": "warm cinematic",
    "cinematic": "cinematic strings",
    "piano": "solo piano",
    "tense": "minimal tension",
    "dramatic": "dramatic orchestral",
}


def _mood_from(text: str, moods: Sequence[str] | None) -> str:
    for mood in moods or []:
        value = str(mood or "").strip().lower()
        if value:
            return value
    lowered = str(text or "").lower()
    for word in audio.MOOD_WORDS:
        if word in lowered:
            return word
    return "cinematic"


def build_brief(
    text: str = "",
    seconds: float = 30.0,
    *,
    moods: Sequence[str] | None = None,
    genre: str = "",
    bpm_range: tuple[float, float] | Sequence[float] | None = None,
    energy: Mapping[str, Any] | None = None,
    language: str = "",
) -> dict[str, Any]:
    """Build the editable four-field music brief from a story.

    Fields are plain values: mood, energy, genre, tempo. The cloud prompt is
    derived from them and never edited directly in the UI.
    """
    mood = _mood_from(text, moods)
    low, high = _BPM_BANDS.get(mood, (90.0, 112.0))
    if bpm_range and len(bpm_range) >= 2:
        try:
            low, high = float(bpm_range[0]), float(bpm_range[1])
        except (TypeError, ValueError):
            pass
    if high < low:
        low, high = high, low
    energy_value = dict(energy) if isinstance(energy, Mapping) else {
        "shape": "hook_payoff",
        "start": 0.35,
        "peak": 0.90,
        "end": 0.55,
    }
    target = max(0.0, float(seconds or 0.0))
    brief = {
        "mood": mood,
        "energy": energy_value,
        "genre": str(genre or _GENRE_HINTS.get(mood, "cinematic ambient")),
        "tempo": {"min": round(low, 1), "max": round(high, 1)},
        "instrumental": True,
        "seconds": round(target, 3),
        "duration": round(max(8.0, target + BRIEF_TAIL_SECONDS), 3),
        "language": str(language or "").strip().lower(),
        "schema": MUSIC_SCHEMA,
    }
    brief["prompt"] = brief_prompt(brief)
    return brief


def brief_prompt(brief: Mapping[str, Any]) -> str:
    """Cloud prompt derived from the editable brief fields."""
    energy = brief.get("energy") or {}
    shape = str(energy.get("shape") or "steady").replace("_", " to ")
    tempo = brief.get("tempo") or {}
    low = int(float(tempo.get("min") or 90))
    high = int(float(tempo.get("max") or 112))
    seconds = int(round(float(brief.get("duration") or brief.get("seconds") or 30)))
    return (
        f"{brief.get('genre') or 'cinematic ambient'} instrumental bed, "
        f"{brief.get('mood') or 'cinematic'} mood, {shape} energy, "
        f"{low}-{high} BPM, no vocals, clean loop, {max(8, seconds)} seconds"
    )


def brief_hash(brief: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        audio.canonical_json(dict(brief)).encode("utf-8"),
    ).hexdigest()[:32]


def generation_cache_key(
    provider: str,
    model: str,
    brief: Mapping[str, Any] | str,
    seed: int = 0,
) -> str:
    """Cache identity for a generated bed: provider + model + brief + seed."""
    digest = brief_hash(brief) if isinstance(brief, Mapping) else str(brief)
    payload = {
        "provider": str(provider or "").strip().lower(),
        "model": str(model or ""),
        "brief": digest,
        "seed": int(seed or 0),
    }
    return hashlib.sha256(
        audio.canonical_json(payload).encode("utf-8"),
    ).hexdigest()[:32]


#: Last-resort music routes, tried after the admin routes when their provider
#: is not configured there. A single MiniMax route must not make music depend
#: on a MiniMax key when an OpenRouter key could make the bed instead.
FALLBACK_MUSIC_ROUTES = (
    {"provider": "openrouter", "model": "google/lyria-3-pro-preview"},
    {"provider": "minimax", "model": "music-3.0"},
)


def music_routes_with_fallback() -> list[dict[str, str]]:
    """Admin music routes, then a default route per unconfigured provider."""
    routes = [dict(route) for route in audio._music_route_candidates()]
    configured = {route["provider"] for route in routes}
    for fallback in FALLBACK_MUSIC_ROUTES:
        if fallback["provider"] in configured:
            continue
        routes.append({
            **fallback,
            "descriptor": f"{fallback['provider']}:{fallback['model']}",
            "fallback": "1",
        })
    return routes


def generation_available() -> list[dict[str, str]]:
    """Music routes, fallbacks included, that have a usable key right now."""
    routes: list[dict[str, str]] = []
    for route in music_routes_with_fallback():
        provider = str(route.get("provider") or "").lower()
        if provider == "minimax" and not audio.minimax_key():
            continue
        if provider == "openrouter" and (
            not audio.openrouter_key() or audio.openrouter_blocked()
        ):
            continue
        routes.append(route)
    return routes


def _candidate_provider(descriptor: str) -> tuple[str, str]:
    text = str(descriptor or "")
    if ":" in text:
        provider, model = text.split(":", 1)
        if provider in {"minimax", "openrouter"}:
            return provider, model
    return ("openrouter" if text.startswith(("google/lyria", "lyria")) else "minimax"), text


def generate_candidates(
    brief: Mapping[str, Any],
    *,
    routes: Sequence[Mapping[str, Any]] | None = None,
    count: int = 2,
    seed: int = GENERATION_SEED,
    timeout: float = 600,
    cancel_event: threading.Event | None = None,
) -> list[dict[str, Any]]:
    """Generate two candidates in parallel, each with its own seed.

    A provider failure is recorded on its candidate; the call raises only when
    every candidate failed. Library and upload paths never reach this function.
    """
    wanted = max(1, int(count or 2))
    chosen = [dict(route) for route in (routes if routes is not None else generation_available())]
    if not chosen:
        raise audio.AudioError(
            "Cloud music needs a MiniMax or OpenRouter key. Use the library or upload a track."
        )
    seconds = float(brief.get("duration") or brief.get("seconds") or 30.0)
    prompt = str(brief.get("prompt") or brief_prompt(brief))
    jobs: list[dict[str, Any]] = []
    for index in range(wanted):
        route = chosen[index % len(chosen)]
        descriptor = str(route.get("descriptor") or "")
        if not descriptor:
            descriptor = f"{route.get('provider')}:{route.get('model')}"
        provider, model = _candidate_provider(descriptor)
        candidate_seed = int(seed) + index
        jobs.append({
            "index": index,
            "provider": provider,
            "model": model,
            "descriptor": descriptor,
            "seed": candidate_seed,
            "cache_key": generation_cache_key(provider, model, brief, candidate_seed),
        })

    def run(job: dict[str, Any]) -> dict[str, Any]:
        try:
            path = generate_music(
                job["descriptor"], prompt, seconds, cancel_event,
                timeout=timeout, seed=job["seed"], brief_hash=brief_hash(brief),
            )
            return {
                **job,
                "path": str(path),
                "file": path.name,
                "brief_hash": brief_hash(brief),
                "licence": normalize_licence(asset_license(path)),
                "error": "",
            }
        except audio.AudioError as exc:
            return {**job, "path": "", "file": "", "error": str(exc)}

    results: list[dict[str, Any]] = []
    workers = max(1, min(wanted, len(jobs)))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="vibecut-music") as pool:
        futures = [pool.submit(run, job) for job in jobs]
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda item: item["index"])
    if results and all(not item.get("path") for item in results):
        detail = next((item.get("error") for item in results if item.get("error")), "")
        raise audio.AudioError(detail or "All music providers failed.")
    return results


def preview_candidate(
    candidate: Mapping[str, Any],
    voice_path: Path | None,
    total: float,
    tmp: Path,
    *,
    gain_db: float = -18.0,
) -> Path | None:
    """Duck one candidate under a narration stem for A/B preview."""
    path = Path(str(candidate.get("path") or ""))
    if not path.is_file() or total <= 0:
        return None
    tmp = Path(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    bed = audio._music_loop(path, total, float(gain_db), tmp)
    return audio._duck_and_mix(
        voice_path, bed, tmp, total, True, float(gain_db), 0.0,
    )


def _minimax_music(
    prompt: str, seconds: float, output: Path,
    model: str = "", timeout: float = 600,
) -> None:
    key = audio.minimax_key()
    if not key:
        raise audio.AudioError("Set MINIMAX_API_KEY to use MiniMax music.")
    model = model or str((audio.settings_store.load_settings().get("minimax") or {}).get("music_model") or audio.settings_store.DEFAULTS["minimax"]["music_model"])
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "is_instrumental": True,
        "output_format": "hex",
        "audio_setting": {
            "sample_rate": 44100,
            "bitrate": 256000,
            "format": "wav",
        },
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        "https://api.minimax.io/v1/music_generation",
        data=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=max(10, timeout)) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise audio.AudioError(f"MiniMax music failed: {exc}") from exc
    status = ((data.get("base_resp") or {}).get("status_code"))
    if status not in (None, 0):
        raise audio.AudioError(f"MiniMax music failed: {data.get('base_resp')}")
    audio_hex = str((data.get("data") or {}).get("audio") or "")
    if not audio_hex:
        raise audio.AudioError("MiniMax music returned no audio.")
    output.write_bytes(bytes.fromhex(audio_hex))
    audio.usage_store.record("music", "minimax")


def _lyria_music(
    prompt: str, seconds: float, output: Path,
    model: str = "", timeout: float = 600,
) -> None:
    key = audio.openrouter_key()
    if not key:
        raise audio.AudioError("Add an OpenRouter key to use Lyria music.")
    if audio.openrouter_blocked():
        raise audio.AudioError(
            "OpenRouter is quarantined after an auth error; retry in "
            f"{audio.openrouter_blocked_seconds()}s."
        )
    model = model or audio._workflow_route_model(
        "music", "openrouter",
        "google/lyria-3-pro-preview" if seconds > 32 else "google/lyria-3-clip-preview",
    )
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "modalities": ["text", "audio"],
        "audio": {"format": "mp3"},
        "stream": True,
    }
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8787",
            "X-Title": "VibeCut",
        },
        method="POST",
    )
    chunks: list[bytes] = []
    try:
        with urllib.request.urlopen(request, timeout=max(10, timeout)) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if not body or body == "[DONE]":
                    continue
                try:
                    event = json.loads(body)
                except ValueError:
                    continue
                choices = event.get("choices") or []
                if not choices:
                    continue
                audio_payload = (choices[0].get("delta") or {}).get("audio") or {}
                value = audio_payload.get("data")
                if value:
                    try:
                        chunks.append(base64.b64decode(value))
                    except (ValueError, TypeError):
                        continue
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            audio._openrouter_auth_failure(
                int(exc.code), audio._openrouter_http_error_text(exc, key),
            )
        raise audio.AudioError(f"Lyria music failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise audio.AudioError(f"Lyria music failed: {exc}") from exc
    if not chunks:
        raise audio.AudioError("Lyria returned no audio chunks.")
    raw = output.with_name(f"{output.stem}.lyria.tmp.mp3")
    raw.write_bytes(b"".join(chunks))
    audio._convert(raw, output, ["-ar", "48000"])
    audio.usage_store.record(
        "music", "lyria-pro" if model.endswith("-pro-preview") else "lyria-clip",
    )
    try:
        raw.unlink()
    except OSError:
        pass


def _music_route_candidates() -> list[dict[str, str]]:
    cfg = audio._workflow("music")
    candidates: list[dict[str, str]] = []
    for route in cfg.get("routes") or []:
        provider = str(route.get("provider") or "").lower()
        model = str(route.get("model") or "").strip()
        if provider in {"minimax", "openrouter"}:
            candidates.append({
                "provider": provider,
                "model": model,
                "descriptor": f"{provider}:{model}",
            })
    return candidates


def generate_music(
    model: str,
    prompt: str,
    seconds: float,
    cancel_event: threading.Event | None = None,
    *,
    timeout: float = 600,
    seed: int = 0,
    brief_hash: str = "",
) -> Path:
    descriptor = str(model)
    provider = ""
    model_name = descriptor
    if ":" in descriptor:
        prefix, rest = descriptor.split(":", 1)
        if prefix in {"minimax", "openrouter"}:
            provider, model_name = prefix, rest
    key = audio._text_hash(
        "music", descriptor, prompt, f"{seconds:.0f}", str(int(seed or 0)),
        str(brief_hash or ""),
    )
    target = audio.CACHE / "music" / f"{key}.wav"
    if target.is_file() and target.stat().st_size > 1024:
        return target
    is_minimax = provider == "minimax" or (
        not provider and (
            model_name.startswith("minimax") or model_name.startswith("music-")
        )
    )
    is_lyria = (
        (provider == "openrouter" and bool(model_name))
        or model_name.startswith(("google/lyria", "lyria"))
    )
    if is_lyria:
        if not audio.openrouter_key():
            raise audio.AudioError("Add an OpenRouter key to use Lyria music.")
        if audio.openrouter_blocked():
            raise audio.AudioError(
                "OpenRouter is quarantined after an auth error; retry in "
                f"{audio.openrouter_blocked_seconds()}s."
            )
    elif is_minimax:
        if not audio.minimax_key():
            raise audio.AudioError("Set MINIMAX_API_KEY to use MiniMax music.")
    else:
        raise audio.AudioError(
            f"Unsupported music source: {descriptor}. "
            "Use MiniMax or OpenRouter Lyria, the library, or an upload."
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    if is_lyria:
        audio._lyria_music(
            prompt, seconds, target,
            model=model_name if provider == "openrouter" else "", timeout=timeout,
        )
    elif is_minimax:
        audio._minimax_music(
            prompt, seconds, target,
            model=model_name if provider == "minimax" else "", timeout=timeout,
        )
    if not target.is_file() or target.stat().st_size <= 1024:
        raise audio.AudioError("Music generation produced no file.")
    audio.save_generated_asset(target, descriptor, prompt, seconds)
    return target



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
        meta = audio.asset_license(path)
        try:
            shown = str(path.relative_to(audio.ASSETS))
        except ValueError:
            shown = path.name
        used.append({"path": shown, "license": (meta or {}).get("license") or "unknown"})
        if not meta:
            missing.append(path.name)
    if strict and missing:
        raise audio.AudioError(
            "Strict license mode: add a .license.json for " + ", ".join(missing)
        )
    return used


def _slug(text: str, limit: int = 36) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", str(text or "")).strip("-").lower()
    return (value or "bed")[:limit]


def save_generated_asset(source: Path, model: str, prompt: str, seconds: float) -> Path:
    """Keep an AI bed as a reusable library track, not only a render cache."""
    directory = audio.MUSIC_DIRS["generated"]
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(
        f"{model}|{prompt}|{seconds:.0f}|{source.stat().st_size}".encode("utf-8"),
    ).hexdigest()[:8]
    out = directory / f"{audio._slug(prompt)}-{digest}.wav"
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


# ---------------------------------------------------------------- lock + metadata


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_licence(value: Any) -> dict[str, Any]:
    """Accept a licence type, an asset sidecar or a full attestation object."""
    if isinstance(value, Mapping):
        raw = {str(key): value[key] for key in value}
    elif value:
        raw = {"license": str(value)}
    else:
        raw = {}
    kind = str(
        raw.get("type") or raw.get("license") or raw.get("licence") or "unknown",
    ).strip().lower() or "unknown"
    if kind not in LICENCE_TYPES:
        kind = "licensed" if kind not in {"", "unknown"} else "unknown"
    return {
        "type": kind,
        "attestation": str(raw.get("attestation") or raw.get("attested") or ""),
        "attribution": str(raw.get("attribution") or ""),
        "terms_url": str(raw.get("terms_url") or raw.get("terms") or ""),
    }


def provider_metadata(
    provider: str = "",
    model: str = "",
    *,
    request_id: str = "",
    prompt: str = "",
    created: float | None = None,
    terms_url: str = "",
) -> dict[str, Any]:
    provider_id = str(provider or "").strip().lower()
    return {
        "id": provider_id,
        "model": str(model or ""),
        "request_id": str(request_id or ""),
        "prompt": str(prompt or ""),
        "created": round(float(created if created is not None else time.time()), 3),
        "terms_url": str(terms_url or GENERATED_TERMS_URLS.get(provider_id, "")),
    }


def music_json(
    path: Path,
    *,
    source_type: str = "library",
    brief: Mapping[str, Any] | None = None,
    provider: Mapping[str, Any] | str | None = None,
    licence: Any = None,
    bpm: float | None = None,
    in_point: float = 0.0,
    out_point: float | None = None,
    job_dir: Path | None = None,
    file_hash: str = "",
    locked: bool = False,
) -> dict[str, Any]:
    """Complete ``music.json`` payload for the packet (§8.5)."""
    path = Path(path)
    source = str(source_type or "library").strip().lower()
    if source not in MUSIC_SOURCE_TYPES:
        source = "library"
    digest = str(file_hash or "").strip().lower()
    if not digest and path.is_file():
        digest = sha256_file(path)
    if job_dir is not None:
        try:
            shown = str(path.resolve().relative_to(Path(job_dir).resolve()))
        except (OSError, ValueError):
            shown = path.name
    else:
        shown = path.name
    if isinstance(provider, Mapping):
        provider_data = provider_metadata(
            str(provider.get("id") or provider.get("provider") or ""),
            str(provider.get("model") or ""),
            request_id=str(provider.get("request_id") or ""),
            prompt=str(provider.get("prompt") or ""),
            created=provider.get("created"),
            terms_url=str(provider.get("terms_url") or ""),
        )
    elif provider:
        provider_data = provider_metadata(str(provider), str(provider))
    else:
        provider_data = provider_metadata()
    if licence is None:
        licence = asset_license(path) if path.is_file() else None
    in_value = max(0.0, float(in_point or 0.0))
    out_value = float(out_point) if out_point is not None else in_value
    return {
        "schema": MUSIC_SCHEMA,
        "source": source,
        "file": shown,
        "file_hash": digest,
        "licence": normalize_licence(licence),
        "provider": provider_data,
        "brief": dict(brief) if isinstance(brief, Mapping) else None,
        "bpm": round(float(bpm), 2) if bpm else None,
        "in": round(in_value, 3),
        "out": round(max(in_value, out_value), 3),
        "duration": round(max(0.0, out_value - in_value), 3),
        "locked": bool(locked),
    }


def _lock_manifest_path(job_dir: Path) -> Path:
    return Path(job_dir) / "audio" / "music-lock.json"


def lock_track(
    path: Path,
    job_dir: Path,
    *,
    source_type: str = "library",
    brief: Mapping[str, Any] | None = None,
    provider: Mapping[str, Any] | str | None = None,
    licence: Any = None,
    bpm: float | None = None,
    in_point: float = 0.0,
    out_point: float | None = None,
) -> dict[str, Any]:
    """Copy a chosen bed into the job and append it to the lock history.

    The copy is content-addressed, so later cache cleanup cannot remove the
    audio an Edit points at. Regenerate keeps the older entries in
    ``audio/music-lock.json``.
    """
    path = Path(path)
    if not path.is_file():
        raise audio.AudioError(f"Music track is missing: {path.name}")
    job_dir = Path(job_dir)
    digest = sha256_file(path)
    directory = job_dir / "audio" / "music"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{digest[:12]}-{_slug(path.stem)}{path.suffix.lower() or '.wav'}"
    if not target.is_file():
        shutil.copy2(path, target)
    entry = music_json(
        target,
        source_type=source_type,
        brief=brief,
        provider=provider,
        licence=licence if licence is not None else asset_license(path),
        bpm=bpm,
        in_point=in_point,
        out_point=out_point,
        job_dir=job_dir,
        file_hash=digest,
        locked=True,
    )
    manifest = _lock_manifest_path(job_dir)
    history: list[dict[str, Any]] = []
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("locked"), list):
                history = [item for item in data["locked"] if isinstance(item, dict)]
        except (OSError, json.JSONDecodeError):
            history = []
    if not any(item.get("file_hash") == digest for item in history):
        history.append({**entry, "locked_at": round(time.time(), 3), "path": entry["file"]})
    manifest.write_text(json.dumps({
        "schema": MUSIC_SCHEMA,
        "locked": history,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return entry


def locked_history(job_dir: Path) -> list[dict[str, Any]]:
    manifest = _lock_manifest_path(job_dir)
    if not manifest.is_file():
        return []
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    locked = data.get("locked") if isinstance(data, dict) else None
    return [item for item in (locked or []) if isinstance(item, dict)]


def resolve_locked_track(job_dir: Path, file_hash: str) -> Path | None:
    wanted = str(file_hash or "").strip().lower()
    if not wanted:
        return None
    for entry in reversed(locked_history(job_dir)):
        if str(entry.get("file_hash") or "").lower() != wanted:
            continue
        path = Path(job_dir) / str(entry.get("file") or entry.get("path") or "")
        if path.is_file() and sha256_file(path) == wanted:
            return path
    return None


# ---------------------------------------------------------------- fitting


def fit_plan(
    source_duration: float,
    total: float,
    grid: Mapping[str, Any] | None = None,
    *,
    fade: float = DEFAULT_FADE_SECONDS,
    crossfade: float = DEFAULT_CROSSFADE_SECONDS,
) -> dict[str, Any]:
    """Beat-aware trim/loop plan for one music bed.

    The start moves to the first downbeat when it is close enough. A source
    shorter than the story loops, preferring whole four-beat bars. The output
    always ends at the story length with a fade, and the returned ``in``/``out``
    are source points for ``music.json``.
    """
    total = max(0.0, float(total or 0.0))
    source_duration = max(0.0, float(source_duration or 0.0))
    bpm = 0.0
    beats: list[float] = []
    if isinstance(grid, Mapping):
        try:
            bpm = float(grid.get("bpm") or 0.0)
        except (TypeError, ValueError):
            bpm = 0.0
        raw_beats = grid.get("beats") or []
        if isinstance(raw_beats, Sequence):
            for value in raw_beats:
                try:
                    beats.append(float(value))
                except (TypeError, ValueError):
                    continue
        beats.sort()
    bar = (60.0 / bpm * 4.0) if bpm > 0 else 4.0
    start = 0.0
    if beats:
        first = beats[0]
        if 0.02 < first <= min(2.0, max(0.25, total * 0.15)):
            start = first
    available = max(0.0, source_duration - start)
    loop = available < total
    loop_seconds = 0.0
    if loop and available > 0:
        bars = math.floor(available / bar) if bar > 0 else 0
        loop_seconds = bars * bar if bars >= 1 else available
    fade_out = max(0.0, min(float(fade or 0.0), total))
    return {
        "in": round(start, 3),
        "out": round(start + total, 3),
        "total": round(total, 3),
        "loop": loop,
        "loop_seconds": round(loop_seconds, 3),
        "crossfade": round(
            max(0.0, min(float(crossfade or 0.0), loop_seconds / 4 if loop_seconds else 0.0)),
            3,
        ),
        "bpm": round(bpm, 2),
        "bar": round(bar, 3),
        "beats": len(beats),
        "fade_in": 0.04 if total > 0.1 else 0.0,
        "fade_out": round(fade_out, 3),
        "fade_out_start": round(max(0.0, total - fade_out), 3),
    }


# ---------------------------------------------------------------- beats


BEATS = audio.CACHE / "beats"


def beat_grid(path: Path) -> dict | None:
    """BPM and beat times for a music file, cached. Uses librosa when present."""
    if not audio._module("librosa") or not path.is_file():
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


# ---------------------------------------------------------------- routes


router = APIRouter(tags=["music"])


class BriefRequest(BaseModel):
    text: str = ""
    seconds: float | None = None
    moods: list[str] = Field(default_factory=list)
    genre: str = ""
    bpm_min: float | None = None
    bpm_max: float | None = None
    language: str = ""


class CandidatesRequest(BaseModel):
    brief: dict
    routes: list[dict] | None = None
    count: int = 2


class LockRequest(BaseModel):
    path: str
    source_type: str = "library"
    brief: dict | None = None
    provider: dict | str | None = None
    licence: dict | str | None = None
    bpm: float | None = None
    in_point: float = 0.0
    out_point: float | None = None


def _job_context(job_id: str):
    import app as app_module  # noqa: PLC0415

    job = app_module.load_job(job_id)
    return app_module, job, Path(app_module._job_dir(job_id))


def _candidates_manifest(job_dir: Path) -> Path:
    return Path(job_dir) / "audio" / "music-candidates.json"


def _safe_music_path(value: str, job_dir: Path) -> Path:
    path = Path(str(value or ""))
    if not path.is_absolute():
        path = Path(job_dir) / path
    resolved = path.resolve()
    roots = [
        Path(job_dir).resolve(),
        (audio.CACHE / "music").resolve(),
        *[Path(folder).resolve() for folder in audio.MUSIC_DIRS.values()],
    ]
    if not any(resolved == root or root in resolved.parents for root in roots):
        raise HTTPException(400, "Music path must be inside the job, cache or library.")
    if not resolved.is_file():
        raise HTTPException(404, "Music file not found.")
    return resolved


@router.get("/api/jobs/{job_id}/music/brief")
def job_music_brief(
    job_id: str,
    target: int = 30,
    hook_scene: int | None = None,
) -> dict:
    app_module, job, _job_dir = _job_context(job_id)
    plan_target = app_module._valid_target(int(target))
    plan = app_module._plan_for(job, plan_target, hook_scene)
    scenes = job["analysis"]["scenes"]
    moods = scene_moods(scenes, plan["clips"])
    by_id = {scene.get("id"): scene for scene in scenes}
    text = " ".join(
        str((by_id.get(clip.get("scene")) or {}).get("speech") or "")
        for clip in plan["clips"]
    ).strip()
    brief = build_brief(
        text, float(plan.get("total") or 0.0), moods=moods,
        language=str((job.get("analysis") or {}).get("language") or ""),
    )
    return {
        "brief": brief,
        "moods": moods,
        "prompt": brief.get("prompt") or "",
        "seconds": brief["seconds"],
    }


@router.post("/api/jobs/{job_id}/music/candidates")
def job_music_candidates(job_id: str, body: CandidatesRequest) -> dict:
    _app, _job, job_dir = _job_context(job_id)
    routes = body.routes if body.routes is not None else None
    candidates = generate_candidates(
        body.brief, routes=routes, count=max(1, min(4, int(body.count or 2))),
    )
    manifest = _candidates_manifest(job_dir)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({
        "schema": MUSIC_SCHEMA,
        "brief": body.brief,
        "candidates": candidates,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"brief": body.brief, "candidates": candidates}


@router.get("/api/jobs/{job_id}/music/candidates/{index}")
def job_music_candidate_file(job_id: str, index: int) -> FileResponse:
    _app, _job, job_dir = _job_context(job_id)
    manifest = _candidates_manifest(job_dir)
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        candidates = data.get("candidates") or []
    except (OSError, json.JSONDecodeError):
        candidates = []
    if index < 0 or index >= len(candidates):
        raise HTTPException(404, "Music candidate not found.")
    path = _safe_music_path(str(candidates[index].get("path") or ""), job_dir)
    media = "audio/mpeg" if path.suffix.lower() == ".mp3" else "audio/wav"
    return FileResponse(path, media_type=media, filename=path.name)


@router.post("/api/jobs/{job_id}/music/lock")
def job_music_lock(job_id: str, body: LockRequest) -> dict:
    _app, _job, job_dir = _job_context(job_id)
    path = _safe_music_path(body.path, job_dir)
    entry = lock_track(
        path,
        job_dir,
        source_type=body.source_type,
        brief=body.brief,
        provider=body.provider,
        licence=body.licence,
        bpm=body.bpm,
        in_point=body.in_point,
        out_point=body.out_point,
    )
    return {"locked": entry, "history": locked_history(job_dir)}


@router.get("/api/jobs/{job_id}/music/locked")
def job_music_locked(job_id: str) -> dict:
    _app, _job, job_dir = _job_context(job_id)
    return {"locked": locked_history(job_dir)}
