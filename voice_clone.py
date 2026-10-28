"""Instant voice clones on HeyGen Voice, spoken through OpenRouter.

Two ways in, one store:

* **My voice** (Setup): the creator records or uploads their own voice.
* **Video voice** (Edit): the speech of the open video's source is cut out and
  cloned, so Voice-over and Dub can keep the original speaker.

HeyGen makes the clone (``POST /v3/models/audio/voices``, ``mode: instant``)
with the creator's own HeyGen key. The clone's ``voice_id`` is then spoken by
the existing OpenRouter route ``heygen/heygen-voice-1-turbo:free``; OpenRouter
reaches a workspace clone when the same HeyGen key is added to OpenRouter as a
BYOK integration. When that call fails, the line is spoken straight on HeyGen
with the free Turbo model, so a clone keeps working without the integration.

Nothing is cloned without an explicit consent flag from the creator. The
store keeps ids, names and status only; recordings are never kept after the
clone request.
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Sequence

import settings_store

HEYGEN_API = "https://api.heygen.com/v3/models/audio"
#: Model used when a clone is spoken straight on HeyGen.
HEYGEN_DIRECT_MODEL = "heygen-voice-1-turbo-free"
#: HeyGen uses only the first three minutes of a recording.
MAX_SAMPLE_SECONDS = 180.0
MIN_SAMPLE_SECONDS = 8.0
#: Inline base64 is capped at 16 MB decoded. 180 s of 24 kHz mono s16 is 8.6 MB.
SAMPLE_RATE = 24000
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
SOURCES = ("me", "video")
STATUSES = ("PENDING", "ACTIVE", "FAILED")
LANGUAGES = frozenset({
    "ar", "be", "bg", "ca", "cs", "da", "de", "el", "en", "es", "fa", "fi",
    "fr", "he", "hi", "hr", "hu", "id", "it", "ja", "ko", "mk", "ms", "nl",
    "pl", "pt", "ro", "ru", "sk", "sl", "sr", "sv", "ta", "th", "tl", "tr",
    "uk", "vi", "zh",
})
_VOICE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
LOCK = threading.Lock()


class CloneError(Exception):
    """A voice clone step failed; the message is safe to show the creator."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------- store


def store_path() -> Path:
    return settings_store.DATA / "voices" / "clones.json"


def heygen_key() -> str:
    return settings_store.get_secret("heygen")


def available() -> bool:
    return bool(heygen_key())


def is_voice_id(value: str) -> bool:
    return bool(_VOICE_ID_RE.match(str(value or "")))


def _read() -> list[dict]:
    path = store_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = data.get("voices") if isinstance(data, dict) else None
    return [row for row in rows or [] if isinstance(row, dict) and row.get("voice_id")]


def _write(rows: list[dict]) -> None:
    path = store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".clones.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps({"voices": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def list_clones(*, active_only: bool = False) -> list[dict]:
    rows = sorted(_read(), key=lambda row: float(row.get("created") or 0), reverse=True)
    if active_only:
        rows = [row for row in rows if row.get("status") == "ACTIVE"]
    return rows


def get_clone(voice_id: str) -> dict | None:
    return next((row for row in _read() if row.get("voice_id") == voice_id), None)


def is_clone(voice_id: str) -> bool:
    return bool(voice_id) and get_clone(str(voice_id)) is not None


def _upsert(record: dict) -> dict:
    with LOCK:
        rows = [row for row in _read() if row.get("voice_id") != record["voice_id"]]
        rows.append(record)
        _write(rows)
    return record


def _remove(voice_id: str) -> bool:
    with LOCK:
        rows = _read()
        kept = [row for row in rows if row.get("voice_id") != voice_id]
        if len(kept) == len(rows):
            return False
        _write(kept)
    return True


def voice_options() -> list[dict]:
    """Active clones in the shape of ``tts.list_voices`` rows."""
    return [
        {
            "id": row["voice_id"],
            "name": f"{row.get('name') or 'Cloned voice'} · {'my voice' if row.get('source') == 'me' else 'from video'}",
            "lang": row.get("language") or "multi",
            "clone": True,
            "source": row.get("source") or "me",
        }
        for row in list_clones(active_only=True)
    ]


# ---------------------------------------------------------------- HeyGen


def _heygen(method: str, path: str, body: dict | None = None, *,
            timeout: float = 60, idempotency: str = "") -> dict:
    key = heygen_key()
    if not key:
        raise CloneError("Add a HeyGen API key in Setup to clone a voice.")
    headers = {"X-Api-Key": key, "Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    if idempotency:
        headers["Idempotency-Key"] = idempotency
    request = urllib.request.Request(
        f"{HEYGEN_API}{path}", data=data, headers=headers, method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            payload = json.loads(exc.read().decode("utf-8", "replace"))
            error = payload.get("error") if isinstance(payload, dict) else None
            if isinstance(error, dict):
                detail = str(error.get("message") or error.get("code") or "")
            elif error:
                detail = str(error)
        except Exception:  # noqa: BLE001
            detail = ""
        if exc.code in {401, 403}:
            raise CloneError(
                "HeyGen refused the key. Check the HeyGen API key in Setup"
                + (f" ({detail})." if detail else "."),
                exc.code,
            ) from exc
        if exc.code == 404:
            raise CloneError("HeyGen has no such voice.", 404) from exc
        if exc.code == 429:
            raise CloneError("HeyGen is busy (rate limit). Try again in a minute.", 429) from exc
        raise CloneError(
            f"HeyGen request failed ({exc.code})" + (f": {detail}" if detail else "."),
            502,
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise CloneError(f"Could not reach HeyGen: {exc}", 502) from exc
    if not raw:
        return {}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise CloneError("HeyGen returned an unreadable reply.", 502) from exc
    return payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else {}


# ---------------------------------------------------------------- samples


def _ffmpeg() -> str:
    import audio

    return audio._ffmpeg()


def _probe_seconds(path: Path) -> float:
    import shutil

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
    """Cut a mono 24 kHz WAV for cloning and return its length in seconds."""
    if not source.is_file():
        raise CloneError("The recording or video file is missing.", 404)
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
            "-c:a", "pcm_s16le", str(output)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CloneError(f"Could not read the audio: {exc}") from exc
    if result.returncode != 0 or not output.is_file() or output.stat().st_size < 4096:
        raise CloneError("Could not cut a voice sample from that file. Is there any sound in it?")
    seconds = _probe_seconds(output) or (output.stat().st_size - 44) / (SAMPLE_RATE * 2)
    if seconds < MIN_SAMPLE_SECONDS:
        raise CloneError(
            f"The voice sample is only {seconds:.0f}s. Give at least "
            f"{MIN_SAMPLE_SECONDS:.0f}s of clear speech (30 s to 3 min is best)."
        )
    return round(seconds, 2)


# ---------------------------------------------------------------- lifecycle


def create_clone(
    sample: Path, *, name: str, source: str, consent: bool,
    language: str = "", job_id: str = "", seconds: float = 0.0,
    remove_noise: bool = True,
) -> dict:
    if not consent:
        raise CloneError(
            "Confirm this is your voice, or that you have the speaker's "
            "permission to clone it."
        )
    if source not in SOURCES:
        raise CloneError("Unknown clone source.")
    clean_name = " ".join(str(name or "").split())[:64] or (
        "My voice" if source == "me" else "Video voice"
    )
    language = str(language or "").strip().lower().split("-")[0]
    if language and language not in LANGUAGES:
        language = ""
    data = sample.read_bytes()
    if len(data) > 16 * 1024 * 1024:
        raise CloneError("The voice sample is over 16 MB. Use a shorter recording.")
    body: dict[str, Any] = {
        "mode": "instant",
        "name": clean_name,
        "similarity": "max",
        "remove_background_noise": bool(remove_noise),
        "audio": [{
            "type": "base64",
            "media_type": "audio/wav",
            "data": base64.b64encode(data).decode("ascii"),
        }],
    }
    if language:
        body["language"] = language
    reply = _heygen("POST", "/voices", body, timeout=180, idempotency=uuid.uuid4().hex)
    voice_id = str(reply.get("voice_id") or "")
    if not is_voice_id(voice_id):
        raise CloneError("HeyGen did not return a voice id.", 502)
    record = {
        "voice_id": voice_id,
        "name": clean_name,
        "source": source,
        "language": language,
        "status": "PENDING",
        "failure_reason": "",
        "job_id": str(job_id or ""),
        "sample_seconds": round(float(seconds or 0.0), 2),
        "created": round(time.time(), 3),
        "consent": {"confirmed": True, "at": round(time.time(), 3)},
    }
    return _upsert(record)


def refresh(voice_id: str) -> dict:
    record = get_clone(voice_id)
    if record is None:
        raise CloneError("No such cloned voice.", 404)
    reply = _heygen("GET", f"/voices/{voice_id}", timeout=30)
    status = str(reply.get("status") or record.get("status") or "PENDING").upper()
    if status not in STATUSES:
        status = "PENDING"
    record = {
        **record,
        "status": status,
        "failure_reason": str(reply.get("failure_reason") or ""),
        "language": str(reply.get("language") or record.get("language") or ""),
    }
    _upsert(record)
    # The preview URL expires; hand it out, never store it.
    return {**record, "preview_url": str(reply.get("preview_audio_url") or "")}


def wait_active(voice_id: str, *, timeout: float = 45.0, interval: float = 1.5) -> dict:
    deadline = time.monotonic() + timeout
    record = refresh(voice_id)
    while record.get("status") == "PENDING" and time.monotonic() < deadline:
        time.sleep(interval)
        record = refresh(voice_id)
    return record


def rename(voice_id: str, name: str) -> dict:
    record = get_clone(voice_id)
    if record is None:
        raise CloneError("No such cloned voice.", 404)
    clean = " ".join(str(name or "").split())[:64]
    if not clean:
        raise CloneError("Give the voice a name.")
    return _upsert({**record, "name": clean})


def delete_clone(voice_id: str) -> bool:
    if get_clone(voice_id) is None:
        raise CloneError("No such cloned voice.", 404)
    try:
        _heygen("DELETE", f"/voices/{voice_id}", timeout=30)
    except CloneError as exc:
        # Already gone on HeyGen is fine; anything else keeps the local row.
        if exc.status_code != 404:
            raise
    return _remove(voice_id)


# ---------------------------------------------------------------- speech


def speak_direct(text: str, voice_id: str, output: Path, *,
                 language: str = "", timeout: float = 300) -> Path:
    """Speak a clone straight on HeyGen Turbo Free; write a WAV to ``output``."""
    body: dict[str, Any] = {
        "model": HEYGEN_DIRECT_MODEL,
        "voice_id": voice_id,
        "text": text,
    }
    language = str(language or "").strip().lower().split("-")[0]
    if language in LANGUAGES:
        body["language"] = language
    reply = _heygen("POST", "/tts", body, timeout=max(30, timeout))
    url = str(reply.get("audio_url") or "")
    if not url.startswith("https://"):
        raise CloneError("HeyGen returned no audio.", 502)
    try:
        with urllib.request.urlopen(url, timeout=max(30, timeout)) as response:
            content = response.read()
    except Exception as exc:  # noqa: BLE001
        raise CloneError(f"Could not download the HeyGen audio: {exc}", 502) from exc
    if len(content) < 64:
        raise CloneError("HeyGen returned empty audio.", 502)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(content)
    return output
