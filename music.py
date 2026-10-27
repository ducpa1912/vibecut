"""Music library, cloud generation and beat fitting.

Split out of `audio.py` without behaviour change. The mixer and `AudioPlan`
builders stay in `audio.py`; every call back goes through the facade so
existing tests and callers can keep patching `audio.*`.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

# Imported last: audio re-exports this module, so the facade must finish first.
import audio  # noqa: E402


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


def _minimax_music(
    prompt: str, seconds: float, output: Path,
    model: str = "", timeout: float = 600,
) -> None:
    key = audio.minimax_key()
    if not key:
        raise audio.AudioError("Set MINIMAX_API_KEY to use MiniMax music.")
    model = model or str((audio.settings_store.load_settings().get("minimax") or {}).get("music_model") or "music-3.0")
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
) -> Path:
    descriptor = str(model)
    provider = ""
    model_name = descriptor
    if ":" in descriptor:
        prefix, rest = descriptor.split(":", 1)
        if prefix in {"minimax", "openrouter"}:
            provider, model_name = prefix, rest
    key = audio._text_hash("music", descriptor, prompt, f"{seconds:.0f}")
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
