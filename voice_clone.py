"""Cloned voices for HeyGen Voice Turbo on OpenRouter.

Two ways in, one store:

* **My voice** (Setup): the creator records or uploads their own voice.
* **Video voice** (Edit): the speech of the open video's source is cut out, so
  Voice-over and Dub can keep the original speaker.

OpenRouter clones statelessly: every ``/audio/speech`` request to
``heygen/heygen-voice-1-turbo:free`` carries the reference recording in
``input_references`` and leaves ``voice`` out. There is no HeyGen account, key
or voice id. A "clone" here is a short reference sample kept on this Mac with
a name; it only needs the OpenRouter key.

Nothing is cloned without an explicit consent flag from the creator. The
sample is stored under ``data/voices/`` and deleted with the voice.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Sequence

import settings_store
import voice_errors

#: HeyGen uses only the first three minutes of a reference recording.
MAX_SAMPLE_SECONDS = 180.0
MIN_SAMPLE_SECONDS = 8.0
#: The sample travels with every speech request, so keep it small: 64 kbps
#: mono MP3 is ~1.4 MB for three minutes. OpenRouter caps a reference at 15 MiB.
SAMPLE_BITRATE = "64k"
SAMPLE_RATE = 44100
MAX_REFERENCE_BYTES = 15 * 1024 * 1024
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
SOURCES = ("me", "video")
LANGUAGES = frozenset({
    "ar", "be", "bg", "ca", "cs", "da", "de", "el", "en", "es", "fa", "fi",
    "fr", "he", "hi", "hr", "hu", "id", "it", "ja", "ko", "mk", "ms", "nl",
    "pl", "pt", "ro", "ru", "sk", "sl", "sr", "sv", "ta", "th", "tl", "tr",
    "uk", "vi", "zh",
})
_VOICE_ID_RE = re.compile(r"^clone_[a-f0-9]{24}$")
LOCK = threading.Lock()


class CloneError(Exception):
    """A voice clone step failed; the message is safe to show the creator."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------- store


def voices_dir() -> Path:
    return settings_store.DATA / "voices"


def store_path() -> Path:
    return voices_dir() / "clones.json"


def available() -> bool:
    """Cloning needs the OpenRouter speech HeyGen Voice Turbo already uses.

    The same test as speech itself: a stored key, OpenRouter enabled and no
    auth quarantine. Offering a clone that cannot speak only fails later.
    """
    if not settings_store.get_secret("openrouter"):
        return False
    import audio

    return audio.openrouter_media_available()


def is_voice_id(value: str) -> bool:
    return bool(_VOICE_ID_RE.match(str(value or "")))


def sample_path(voice_id: str) -> Path:
    return voices_dir() / f"{voice_id}.mp3"


def _read() -> list[dict]:
    try:
        data = json.loads(store_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = data.get("voices") if isinstance(data, dict) else None
    return [row for row in rows or [] if isinstance(row, dict) and is_voice_id(row.get("voice_id"))]


def _write(rows: list[dict]) -> None:
    path = store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".clones.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps({"voices": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def list_clones() -> list[dict]:
    rows = [row for row in _read() if sample_path(row["voice_id"]).is_file()]
    return sorted(rows, key=lambda row: float(row.get("created") or 0), reverse=True)


def get_clone(voice_id: str) -> dict | None:
    if not is_voice_id(voice_id):
        return None
    row = next((row for row in _read() if row.get("voice_id") == voice_id), None)
    return row if row and sample_path(voice_id).is_file() else None


def is_clone(voice_id: str) -> bool:
    return get_clone(str(voice_id or "")) is not None


def _upsert(record: dict) -> dict:
    with LOCK:
        rows = [row for row in _read() if row.get("voice_id") != record["voice_id"]]
        rows.append(record)
        _write(rows)
    return record


def voice_options() -> list[dict]:
    """Clones in the shape of ``tts.list_voices`` rows."""
    return [
        {
            "id": row["voice_id"],
            "name": f"{row.get('name') or 'Cloned voice'} · {'my voice' if row.get('source') == 'me' else 'from video'}",
            "lang": row.get("language") or "multi",
            "clone": True,
            "source": row.get("source") or "me",
        }
        for row in list_clones()
    ]


# ---------------------------------------------------------------- samples


def _ffmpeg() -> str:
    import audio

    return audio._ffmpeg()


def _probe_seconds(path: Path) -> float:
    probe = shutil.which("ffprobe")
    if not probe:
        return 0.0
    try:
        result = subprocess.run(
            [probe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=60, check=False,
        )
        return max(0.0, float((result.stdout or "0").strip() or 0))
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0.0


def speech_windows(
    segments: Sequence[dict], *, limit: float = MAX_SAMPLE_SECONDS,
    start: float | None = None, end: float | None = None,
) -> list[tuple[float, float]]:
    """Transcript segments inside ``start..end`` up to ``limit`` seconds.

    Speech-only windows give HeyGen a clean sample without long silences or
    music stretches. Adjacent segments under 0.35 s apart are merged.
    """
    lower = max(0.0, float(start or 0.0))
    upper = float(end) if end is not None and end > lower else float("inf")
    windows: list[tuple[float, float]] = []
    total = 0.0
    for item in segments:
        try:
            a = max(lower, float(item.get("start", 0.0)))
            b = min(upper, float(item.get("end", 0.0)))
        except (TypeError, ValueError):
            continue
        if b - a < 0.3 or not str(item.get("text") or "").strip():
            continue
        if total + (b - a) > limit:
            b = a + (limit - total)
        if windows and a - windows[-1][1] < 0.35:
            total += b - windows[-1][1]
            windows[-1] = (windows[-1][0], b)
        else:
            total += b - a
            windows.append((a, b))
        if total >= limit - 0.05:
            break
    return [(round(a, 3), round(b, 3)) for a, b in windows]


def prepare_sample(
    source: Path, output: Path, *,
    windows: Sequence[tuple[float, float]] = (),
    start: float = 0.0, duration: float = MAX_SAMPLE_SECONDS,
) -> float:
    """Cut a mono MP3 reference sample and return its length in seconds."""
    if not source.is_file():
        raise CloneError(voice_errors.fix("The recording or video file is missing", "Choose the file again, then retry"), 404)
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [_ffmpeg(), "-y", "-v", "error"]
    if windows:
        expr = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in windows)
        cmd += ["-i", str(source), "-vn", "-af", f"aselect='{expr}',asetpts=N/SR/TB"]
    else:
        cmd += ["-ss", f"{max(0.0, start):.3f}", "-t",
                f"{min(MAX_SAMPLE_SECONDS, max(1.0, duration)):.3f}",
                "-i", str(source), "-vn"]
    cmd += ["-t", f"{MAX_SAMPLE_SECONDS:.0f}", "-ac", "1", "-ar", str(SAMPLE_RATE),
            "-c:a", "libmp3lame", "-b:a", SAMPLE_BITRATE,
            # Force the MP3 container: callers name the file .wav or .mp3, and
            # ffmpeg would otherwise wrap MP3 frames in a WAV header.
            "-f", "mp3", str(output)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CloneError(voice_errors.fix(f"Could not read the audio: {exc}", "Check that the file plays in another app, then choose it again")) from exc
    if result.returncode != 0 or not output.is_file():
        raise CloneError(voice_errors.UNREADABLE)
    if output.stat().st_size < 2048:
        raise CloneError(voice_errors.NO_SPEECH)
    if output.stat().st_size > MAX_REFERENCE_BYTES:
        raise CloneError("The voice sample is over 15 MB. Use a recording under 15 MB or trim it first.")
    seconds = _probe_seconds(output) or output.stat().st_size / 8000
    if seconds < MIN_SAMPLE_SECONDS:
        raise CloneError(
            f"The voice sample is only {seconds:.0f}s. Give at least "
            f"{MIN_SAMPLE_SECONDS:.0f}s of clear speech (30 s to 3 min is best)."
        )
    return round(seconds, 2)


# ---------------------------------------------------------------- identity


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def lock(voice_id: str, locked: bool = True) -> dict:
    """Freeze, or release, a voice's reference.

    A locked voice keeps the exact sample it had at that moment. Every later
    speech request checks the fingerprint first, so a replaced or corrupted
    reference is refused instead of quietly changing how the voice sounds.
    """
    record = get_clone(voice_id)
    if record is None:
        raise CloneError(voice_errors.MISSING_VOICE, 404)
    path = sample_path(voice_id)
    if not locked:
        try:
            os.chmod(path, 0o644)
        except OSError:
            pass
        record = {key: value for key, value in record.items() if key != "locked"}
        return _upsert(record)
    try:
        os.chmod(path, 0o444)
        digest = _digest(path)
        size = path.stat().st_size
    except OSError as exc:
        raise CloneError(
            voice_errors.fix(
                "The reference could not be locked", "Unlock the file in Finder, then lock the voice again",
            )
        ) from exc
    return _upsert({
        **record,
        "locked": {
            "at": round(time.time(), 3),
            "sha256": digest,
            "bytes": int(size),
            "language": str(record.get("language") or ""),
        },
    })


def verify_lock(record: dict) -> None:
    """Refuse a speech request when a locked reference no longer matches."""
    locked = record.get("locked") if isinstance(record.get("locked"), dict) else None
    if not locked:
        return
    expected = str(locked.get("sha256") or "")
    if not expected:
        return
    try:
        actual = _digest(sample_path(record["voice_id"]))
    except OSError as exc:
        raise CloneError(
            voice_errors.fix(
                "The locked reference is missing from this Mac",
                "Restore it from a library backup or unlock the voice",
            ),
            409,
        ) from exc
    if actual != expected:
        raise CloneError(
            voice_errors.fix(
                "The reference for this voice changed after it was locked",
                "Unlock the voice, or restore the original sample, then try again",
            ),
            409,
        )


def set_keep(voice_id: str, keep: dict | None) -> dict:
    """Pin, or clear, the settings of a good take on this voice."""
    record = get_clone(voice_id)
    if record is None:
        raise CloneError(voice_errors.MISSING_VOICE, 404)
    if keep is None:
        return _upsert({key: value for key, value in record.items() if key != "keep"})
    text = " ".join(str(keep.get("text") or "").split())[:4000]
    if not text:
        raise CloneError("That take has no script to keep. Make a preview or voiceover with words, then keep it.")
    try:
        rate = float(keep.get("rate") or 1.0)
    except (TypeError, ValueError):
        rate = 1.0
    return _upsert({
        **record,
        "keep": {
            "take_id": str(keep.get("take_id") or ""),
            "text": text,
            "rate": round(max(0.5, min(2.0, rate)), 3),
            "language": str(keep.get("language") or "")[:12].lower().split("-")[0],
            "at": round(time.time(), 3),
        },
    })


# ---------------------------------------------------------------- lifecycle


def create_clone(
    sample: Path, *, name: str, source: str, consent: bool,
    language: str = "", job_id: str = "", seconds: float = 0.0,
) -> dict:
    """Keep a prepared sample as a named voice. No network call."""
    if not consent:
        raise CloneError(
            "Confirm this is your voice, or that you have the speaker's "
            "permission to clone it."
        )
    if source not in SOURCES:
        raise CloneError("The clone source was not understood. Reload Voice Room, then clone the voice again.")
    if not sample.is_file():
        raise CloneError(voice_errors.fix("The voice sample is missing", "Record or upload the voice again"), 404)
    clean_name = " ".join(str(name or "").split())[:64] or (
        "My voice" if source == "me" else "Video voice"
    )
    language = str(language or "").strip().lower().split("-")[0]
    if language not in LANGUAGES:
        language = ""
    voice_id = f"clone_{uuid.uuid4().hex[:24]}"
    target = sample_path(voice_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(sample, target)
    now = round(time.time(), 3)
    return _upsert({
        "voice_id": voice_id,
        "name": clean_name,
        "source": source,
        "language": language,
        "status": "ACTIVE",
        "job_id": str(job_id or ""),
        "sample_seconds": round(float(seconds or 0.0), 2),
        "created": now,
        "consent": {"confirmed": True, "at": now},
    })


def rename(voice_id: str, name: str) -> dict:
    record = get_clone(voice_id)
    if record is None:
        raise CloneError(voice_errors.MISSING_VOICE, 404)
    clean = " ".join(str(name or "").split())[:64]
    if not clean:
        raise CloneError("Give the voice a name of up to 64 characters, then save it.")
    return _upsert({**record, "name": clean})


def delete_clone(voice_id: str) -> bool:
    if not is_voice_id(voice_id):
        raise CloneError(voice_errors.MISSING_VOICE, 404)
    with LOCK:
        rows = _read()
        kept = [row for row in rows if row.get("voice_id") != voice_id]
        found = len(kept) != len(rows)
        if found:
            _write(kept)
    try:
        sample_path(voice_id).unlink()
        found = True
    except FileNotFoundError:
        pass
    if not found:
        raise CloneError(voice_errors.MISSING_VOICE, 404)
    return True


# ---------------------------------------------------------------- speech


def speech_fields(voice_id: str) -> dict[str, Any]:
    """Body fields that make an OpenRouter HeyGen request speak in a clone.

    The caller drops ``voice``: the recording is the voice.
    """
    record = get_clone(voice_id)
    if record is None:
        raise CloneError(voice_errors.MISSING_VOICE, 404)
    raw = sample_path(voice_id).read_bytes()
    # Clones saved before the container fix hold MP3 frames in a WAV header.
    mime = "audio/wav" if raw[:4] == b"RIFF" else "audio/mpeg"
    data = base64.b64encode(raw).decode("ascii")
    fields: dict[str, Any] = {
        "input_references": [{
            "type": "input_audio",
            "input_audio": {"data": f"data:{mime};base64,{data}"},
        }],
    }
    language = str(record.get("language") or "")
    if language in LANGUAGES:
        fields["provider"] = {"options": {"heygen": {"language": language}}}
    return fields
