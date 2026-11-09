"""Local voice-over with the macOS `say` voices.

No cloud key, no downloaded model. Captions are the script: each cue is spoken,
fitted into its cue window, and assembled into one WAV on the edit timeline.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Any

from duckcore import media

VOICE_RE = re.compile(r"^(?P<name>.+?)\s{2,}(?P<locale>[a-z]{2}_[A-Z]{2})\s*(?:#\s*(?P<sample>.*))?$")
SAMPLE_RATE = 22050
SAMPLE_WIDTH = 2
CHANNELS = 1


NOVELTY_VOICES = {
    "Bad News", "Bahh", "Bells", "Boing", "Bubbles", "Cellos", "Good News",
    "Jester", "Organ", "Superstar", "Trinoids", "Whisper", "Wobble", "Zarvox",
}


def list_voices() -> list[dict[str, str]]:
    try:
        result = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    voices = []
    for line in result.stdout.splitlines():
        match = VOICE_RE.match(line.strip())
        if not match:
            continue
        name = match.group("name").strip()
        if name in NOVELTY_VOICES:
            continue
        voices.append({
            "name": name,
            "locale": match.group("locale"),
            "sample": (match.group("sample") or "").strip(),
        })
    voices.sort(key=lambda item: (not item["locale"].startswith("en_US"), item["locale"], item["name"]))
    return voices


def _which_say() -> str:
    found = shutil.which("say")
    if not found:
        raise RuntimeError("Apple `say` is not available.")
    return found


def _duration(path: Path) -> float:
    result = subprocess.run(
        [media.ffprobe(), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    try:
        return max(0.0, float(result.stdout.strip()))
    except ValueError:
        return 0.0


def _synthesize(text: str, voice: str, aiff: Path) -> None:
    result = subprocess.run(
        [_which_say(), "-v", voice, "-o", str(aiff), text],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0 or not aiff.is_file():
        raise RuntimeError(f"Apple voice failed: {(result.stderr or '').strip()[:200]}")


def _to_wave(source: Path, target: Path) -> None:
    result = subprocess.run(
        [
            media.ffmpeg(), "-y", "-v", "error", "-i", str(source),
            "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS), "-sample_fmt", "s16",
            "-f", "wav", str(target),
        ],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0 or not target.is_file():
        raise RuntimeError(f"Could not prepare voice audio: {result.stderr[-300:]}")


def _fit(source: Path, target: Path, duration: float) -> None:
    duration = max(0.05, float(duration))
    source_duration = _duration(source)
    tempo = 1.0
    if source_duration > duration:
        tempo = min(2.0, max(0.5, source_duration / duration))
    result = subprocess.run(
        [
            media.ffmpeg(), "-y", "-v", "error", "-i", str(source),
            "-af", f"atempo={tempo:.5f},apad=whole_dur={duration:.5f},atrim=0:{duration:.5f}",
            "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS), "-sample_fmt", "s16",
            "-f", "wav", str(target),
        ],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0 or not target.is_file():
        raise RuntimeError(f"Could not fit voice cue: {result.stderr[-300:]}")


def _silence(frames: int) -> bytes:
    return b"\x00" * max(0, frames) * SAMPLE_WIDTH * CHANNELS


def build_track(
    cues: list[dict],
    *,
    voice_name: str,
    mode: str,
    project_id: str,
    data_root: Path,
    total_duration: float | None = None,
) -> dict:
    cues = [cue for cue in cues or [] if str(cue.get("text") or "").strip()]
    if not cues:
        raise ValueError("Generate captions first; they are the script.")
    if not voice_name:
        raise ValueError("Choose a local voice.")
    mode = "voice_only" if mode == "voice_only" else "voice_over"
    job_dir = Path(data_root) / "projects" / project_id / "voice"
    job_dir.mkdir(parents=True, exist_ok=True)
    token = hashlib.sha1(
        f"{voice_name}|{mode}|{[(c.get('start'), c.get('end'), c.get('text')) for c in cues]}".encode()
    ).hexdigest()[:12]
    output = job_dir / f"voice_{token}.wav"
    if not output.is_file():
        with wave.open(str(output), "wb") as writer:
            writer.setnchannels(CHANNELS)
            writer.setsampwidth(SAMPLE_WIDTH)
            writer.setframerate(SAMPLE_RATE)
            cursor = 0
            for index, cue in enumerate(sorted(cues, key=lambda item: float(item.get("start") or 0.0))):
                start = max(0.0, float(cue.get("start") or 0.0))
                end = max(start + 0.05, float(cue.get("end") or 0.0))
                start_frame = int(round(start * SAMPLE_RATE))
                if start_frame > cursor:
                    writer.writeframes(_silence(start_frame - cursor))
                    cursor = start_frame
                aiff = job_dir / f".cue_{index}.aiff"
                wav = job_dir / f".cue_{index}.wav"
                fitted = job_dir / f".cue_{index}.fit.wav"
                _synthesize(str(cue.get("text") or ""), voice_name, aiff)
                _to_wave(aiff, wav)
                _fit(wav, fitted, end - start)
                with wave.open(str(fitted), "rb") as reader:
                    frames = reader.readframes(reader.getnframes())
                writer.writeframes(frames)
                cursor += len(frames) // (SAMPLE_WIDTH * CHANNELS)
                for path in (aiff, wav, fitted):
                    path.unlink(missing_ok=True)
            total = int(round(float(total_duration or 0.0) * SAMPLE_RATE))
            if total > cursor:
                writer.writeframes(_silence(total - cursor))
    return {
        "engine": "say",
        "voice": voice_name,
        "mode": mode,
        "audio": str(output.relative_to(Path(data_root) / "projects" / project_id)),
        "duration": _duration(output),
    }


def build_voice(
    edit: dict,
    reference: dict,
    data_root: Path,
    *,
    voice: str,
    mode: str = "voice_over",
) -> dict:
    track = build_track(
        [cue for cue in (reference or {}).get("cues") or [] if isinstance(cue, dict)],
        voice_name=voice,
        mode=mode,
        project_id=str(edit["project_id"]),
        data_root=data_root,
        total_duration=float(edit.get("end") or 0.0),
    )
    track["duration"] = _duration(Path(data_root) / "projects" / str(edit["project_id"]) / track["audio"])
    track["id"] = f"at_{secrets.token_hex(5)}"
    track["kind"] = "voice"
    track["name"] = track.get("voice") or "Voice-over"
    track["start"] = 0.0
    track["volume"] = 1.0
    from duckcore import edits
    edits.ensure_audio_tracks(edit)
    edit["audio_tracks"].append(track)
    edit["voice"] = track
    edits.save_edit(edit, data_root)
    return track


def preview_line(text: str, voice_name: str, project_id: str, data_root: Path) -> dict:
    text = str(text or "").strip()
    if not text:
        raise ValueError("Choose a line to preview.")
    if not voice_name:
        raise ValueError("Choose a local voice.")
    job_dir = Path(data_root) / "projects" / project_id / "voice" / "previews"
    job_dir.mkdir(parents=True, exist_ok=True)
    token = hashlib.sha1(f"{voice_name}|{text}".encode()).hexdigest()[:16]
    output = job_dir / f"{token}.wav"
    if not output.is_file():
        aiff = job_dir / f".{token}.aiff"
        _synthesize(text, voice_name, aiff)
        _to_wave(aiff, output)
        aiff.unlink(missing_ok=True)
    return {"audio": str(output.relative_to(Path(data_root) / "projects" / project_id)), "duration": _duration(output)}
