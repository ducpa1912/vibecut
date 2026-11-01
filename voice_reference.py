"""A reference upload waiting to become a clone.

A long recording should not be sent to the cloud whole. The page uploads it
once, this module decodes it, measures it and proposes the cleanest 10-15 s
window. The trimmer then asks for a range, and the clone is cut from the same
file, so nothing is uploaded twice.

Sessions live under ``DATA/cache/reference/<ref_id>`` and expire after two
hours. They hold the creator's own audio, so deleting a session removes the
raw upload, the decoded copy and the proposal.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
import uuid
from pathlib import Path

import settings_store
import voice_audio

REF_ID = re.compile(r"^ref_[a-f0-9]{24}$")
TTL_SECONDS = 2 * 60 * 60
MAX_SESSIONS = 16


class ReferenceError(Exception):
    """A reference step failed; the message is safe to show the creator."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def root() -> Path:
    return settings_store.DATA / "cache" / "reference"


def is_ref_id(value: str) -> bool:
    return bool(REF_ID.match(str(value or "")))


def _session_dir(ref_id: str) -> Path:
    if not is_ref_id(ref_id):
        raise ReferenceError("That reference is not on this Mac. Upload it again, then trim it.", 404)
    return root() / ref_id


def _prune() -> None:
    """Drop sessions past their two hours, then the oldest past the cap."""
    base = root()
    try:
        entries = sorted(
            (path for path in base.iterdir() if path.is_dir()),
            key=lambda path: path.stat().st_mtime,
        )
    except OSError:
        return
    cutoff = time.time() - TTL_SECONDS
    for path in list(entries):
        try:
            old = path.stat().st_mtime < cutoff
        except OSError:
            continue
        if old:
            shutil.rmtree(path, ignore_errors=True)
            entries.remove(path)
    for path in entries[:-MAX_SESSIONS] if MAX_SESSIONS else []:
        shutil.rmtree(path, ignore_errors=True)


def create(raw: Path, *, suffix: str, name: str = "") -> dict:
    """Keep one upload, decode it and propose its best window."""
    import voice_errors

    raw = Path(raw)
    if not raw.is_file() or raw.stat().st_size < 256:
        raise ReferenceError(voice_errors.EMPTY_FILE)
    extension = suffix if str(suffix).startswith(".") else f".{suffix}"
    _prune()
    ref_id = f"ref_{uuid.uuid4().hex[:24]}"
    folder = root() / ref_id
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / f"source{extension.lower()}"
    try:
        shutil.copyfile(raw, source)
        wav = folder / "audio.wav"
        voice_audio.to_wav(source, wav)
        check = voice_audio.analyse(wav)
        if check.get("silent"):
            raise ReferenceError(voice_errors.NO_SPEECH)
        window = voice_audio.best_window(wav)
        peaks = voice_audio.peaks(wav)
    except (RuntimeError, OSError, ValueError) as exc:
        shutil.rmtree(folder, ignore_errors=True)
        raise ReferenceError(voice_errors.clean(str(exc), voice_errors.UNREADABLE)) from exc
    except ReferenceError:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    meta = {
        "id": ref_id,
        "name": " ".join(str(name or "Recording").split())[:120],
        "created": round(time.time(), 3),
        "duration": round(float(check.get("duration") or 0.0), 3),
        "best": window,
        "check": check,
        "peaks": peaks,
    }
    (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    os.utime(folder, None)
    return _public(meta)


def _public(meta: dict) -> dict:
    return {
        "id": meta["id"],
        "name": meta.get("name") or "Recording",
        "duration": meta.get("duration") or 0.0,
        "best": meta.get("best") or {},
        "check": meta.get("check"),
        "peaks": meta.get("peaks") or [],
        "audio_url": f"/api/voices/reference/{meta['id']}/audio",
        "limits": {
            "min_seconds": voice_audio.MIN_REFERENCE_SECONDS,
            "max_seconds": voice_audio.MAX_REFERENCE_SECONDS,
            "target_seconds": voice_audio.TARGET_WINDOW_SECONDS,
        },
    }


def get(ref_id: str) -> dict | None:
    if not is_ref_id(ref_id):
        return None
    folder = root() / ref_id
    try:
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(meta, dict) or not (folder / "audio.wav").is_file():
        return None
    return _public(meta)


def audio_path(ref_id: str) -> Path:
    folder = _session_dir(ref_id)
    path = folder / "audio.wav"
    if not path.is_file():
        raise ReferenceError("That reference is not on this Mac. Upload it again, then trim it.", 404)
    return path


def source_path(ref_id: str) -> Path:
    """The decoded copy the clone is cut from."""
    return audio_path(ref_id)


def delete(ref_id: str) -> bool:
    if not is_ref_id(ref_id):
        return False
    folder = root() / ref_id
    if not folder.is_dir():
        return False
    shutil.rmtree(folder, ignore_errors=True)
    return True


def window_for(meta: dict, start: float | None, end: float | None) -> tuple[float, float]:
    """The chosen range, or the proposed window when the page sends none."""
    duration = float(meta.get("duration") or 0.0)
    if start is None and end is None:
        best = meta.get("best") or {}
        start = float(best.get("start") or 0.0)
        end = float(best.get("end") or duration)
    start = max(0.0, float(start if start is not None else 0.0))
    end = min(duration, float(end if end is not None else duration))
    if end <= start:
        raise ReferenceError("The end must come after the start. Move the end marker right, then try again.")
    return round(start, 3), round(end, 3)


def measure(ref_id: str) -> dict:
    meta = get(ref_id)
    if meta is None:
        raise ReferenceError("That reference is not on this Mac. Upload it again, then trim it.", 404)
    return meta
