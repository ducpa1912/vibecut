"""Every preview and voiceover, kept beside the work.

A take is one finished piece of speech: the exact line, voice, rate and
language that made it, plus the audio. The right-hand Takes list reads this
store, so a reload keeps the list, the stars and the settings.

Two rules shape the store:

* Nothing is sent twice. A preview answered from the speech cache says
  ``cached: true`` and the list shows it.
* Old takes are only removed after a warning. Unstarred takes older than
  :data:`CLEANUP_DAYS` appear in :func:`cleanup_plan`; :func:`cleanup` needs
  ``confirm=True`` and never touches a starred take.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import time
import uuid
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, Sequence

import settings_store
import voice_audio

CLEANUP_DAYS = 30
MAX_LISTED = 200
MAX_SCRIPT_CHARS = 4000
MAX_CHUNK_CHARS = 220
SELF_CHECK_THRESHOLD = 0.60
STORE_VERSION = 1
CANCELLED = "Cancelled. No voiceover was made."
_TAKE_ID = re.compile(r"^take_[a-f0-9]{24}$")
_LOCK = threading.RLock()
_VOICEOVER = threading.Lock()
#: What a running voiceover is doing, for the honest seconds counter. Keyed by
#: the client's task id; small and in memory because it is only read while the
#: request is still open.
_PROGRESS: dict[str, dict] = {}
_PROGRESS_LOCK = threading.Lock()
_WORD = re.compile(r"[^\w']+", re.UNICODE)
_CONSENT_COPY = (
    "Confirm this is your own voice, or that you have the speaker's "
    "permission to clone it."
)


class TakeError(Exception):
    """A take step failed; the message is safe to show the creator."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def is_take_id(value: str) -> bool:
    return bool(_TAKE_ID.match(str(value or "")))


def set_progress(task_id: str, state: str, stage: str = "", fraction: float = 0.0) -> None:
    """Remember one running voiceover's stage. No task id, no entry."""
    if not task_id:
        return
    with _PROGRESS_LOCK:
        item = _PROGRESS.get(task_id) or {"started": time.time()}
        item.update({
            "state": str(state or "running"),
            "stage": str(stage or ""),
            "fraction": round(max(0.0, min(1.0, float(fraction or 0.0))), 3),
        })
        item["elapsed"] = round(time.time() - float(item.get("started") or time.time()), 1)
        _PROGRESS[task_id] = item
        while len(_PROGRESS) > 32:
            _PROGRESS.pop(next(iter(_PROGRESS)), None)


def progress(task_id: str) -> dict:
    with _PROGRESS_LOCK:
        item = _PROGRESS.get(task_id)
        if item is None:
            return {"state": "idle", "stage": "", "fraction": 0.0, "elapsed": 0.0}
        copy = dict(item)
    copy["elapsed"] = round(time.time() - float(copy.get("started") or time.time()), 1)
    return copy


def clear_progress(task_id: str) -> None:
    if not task_id:
        return
    with _PROGRESS_LOCK:
        _PROGRESS.pop(task_id, None)


def takes_dir() -> Path:
    return settings_store.DATA / "takes"


def audio_dir() -> Path:
    return takes_dir() / "audio"


def store_path() -> Path:
    return takes_dir() / "takes.json"


def _now() -> float:
    return round(time.time(), 3)


def _read() -> list[dict]:
    try:
        data = json.loads(store_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = data.get("takes") if isinstance(data, dict) else None
    return [row for row in rows or [] if isinstance(row, dict) and is_take_id(row.get("id"))]


def _write(rows: list[dict]) -> None:
    path = store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".takes.{uuid.uuid4().hex}.tmp")
    tmp.write_text(
        json.dumps({"version": STORE_VERSION, "takes": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _clean_row(row: dict) -> dict | None:
    """One stored take, or None when it cannot be shown or played again."""
    take_id = str(row.get("id") or "")
    if not is_take_id(take_id):
        return None
    path = audio_dir() / f"{take_id}.wav"
    if not path.is_file():
        return None
    created = row.get("created")
    if isinstance(created, bool) or not isinstance(created, (int, float)):
        return None
    settings = row.get("settings") if isinstance(row.get("settings"), dict) else {}
    return {
        **row,
        "id": take_id,
        "created": float(created),
        "starred": bool(row.get("starred")),
        "audio": f"takes/audio/{take_id}.wav",
        "audio_url": f"/api/voices/takes/{take_id}/audio",
        "settings": {
            "text": str(settings.get("text") or ""),
            "engine": str(settings.get("engine") or ""),
            "voice": str(settings.get("voice") or ""),
            "rate": float(settings.get("rate") or 1.0),
            "language": str(settings.get("language") or ""),
        },
    }


def list_takes() -> list[dict]:
    """Starred first, then newest; capped so the panel stays quick."""
    rows = [row for row in (_clean_row(item) for item in _read()) if row]
    rows.sort(key=lambda row: (bool(row.get("starred")), float(row.get("created") or 0.0)), reverse=True)
    return rows[:MAX_LISTED]


def get_take(take_id: str) -> dict | None:
    if not is_take_id(take_id):
        return None
    row = next((item for item in _read() if item.get("id") == take_id), None)
    return _clean_row(row) if row else None


def audio_path(take_id: str) -> Path:
    if not is_take_id(take_id):
        raise TakeError("No such take.", 404)
    path = audio_dir() / f"{take_id}.wav"
    if not path.is_file():
        raise TakeError("No such take.", 404)
    return path


def _remember(record: dict) -> dict:
    with _LOCK:
        rows = [row for row in _read() if row.get("id") != record["id"]]
        rows.append(record)
        _write(rows)
    stored = _clean_row(record)
    return stored or record


def _check(path: Path) -> dict | None:
    try:
        report = voice_audio.analyse(path)
    except (RuntimeError, OSError, ValueError):
        # Decoration only: a take that was made must never be lost because
        # the measurement failed.
        return None
    report["advice"] = voice_audio.output_advice(report)
    report["advisory"] = True
    return report


def record_preview(
    source: Path,
    *,
    engine: str,
    voice: str,
    text: str,
    rate: float,
    language: str = "",
    label: str = "",
    clone: str = "",
    cached: bool = False,
) -> dict | None:
    """Keep one preview. Storage trouble never fails the preview itself."""
    source = Path(source)
    if not source.is_file():
        return None
    take_id = f"take_{uuid.uuid4().hex[:24]}"
    target = audio_dir() / f"{take_id}.wav"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copyfile(source, target)
    except OSError:
        return None
    check = _check(target)
    seconds = float((check or {}).get("duration") or 0.0)
    record = {
        "id": take_id,
        "kind": "preview",
        "label": " ".join(str(label or voice or "Preview").split())[:120],
        "created": _now(),
        "starred": False,
        "clone_voice": str(clone or ""),
        "cached": bool(cached),
        "seconds": round(seconds, 3),
        "check": check,
        "settings": {
            "text": str(text or ""),
            "engine": str(engine or ""),
            "voice": str(voice or ""),
            "rate": round(float(rate or 1.0), 3),
            "language": str(language or ""),
        },
    }
    try:
        return _remember(record)
    except OSError:
        try:
            target.unlink()
        except OSError:
            pass
        return None


def star(take_id: str, starred: bool) -> dict:
    take = get_take(take_id)
    if take is None:
        raise TakeError("No such take.", 404)
    with _LOCK:
        rows = _read()
        for row in rows:
            if row.get("id") == take_id:
                row["starred"] = bool(starred)
                break
        _write(rows)
    return get_take(take_id) or take


def delete(take_id: str) -> bool:
    if not is_take_id(take_id):
        raise TakeError("No such take.", 404)
    with _LOCK:
        rows = _read()
        kept = [row for row in rows if row.get("id") != take_id]
        found = len(kept) != len(rows)
        if found:
            _write(kept)
    if not found:
        raise TakeError("No such take.", 404)
    try:
        (audio_dir() / f"{take_id}.wav").unlink()
    except OSError:
        pass
    return True


def save_as_voice(take_id: str, name: str) -> dict:
    """Make a new cloned voice from the take's own reference.

    Only a take made in one of this Mac's clones has a reference to copy.
    A stock preview has no reference of its own, so it cannot become a clone.
    """
    import voice_clone  # noqa: PLC0415 - keeps the store importable alone

    take = get_take(take_id)
    if take is None:
        raise TakeError("No such take.", 404)
    original = str(take.get("clone_voice") or "")
    record = voice_clone.get_clone(original) if original else None
    if record is None:
        raise TakeError(
            "Only a take made in one of your cloned voices can be saved as a new voice. "
            "Preview or make a voiceover in a cloned voice, then save that take.",
        )
    work = settings_store.DATA / "cache" / "takes" / uuid.uuid4().hex
    work.mkdir(parents=True, exist_ok=True)
    sample = work / "reference.mp3"
    try:
        shutil.copyfile(voice_clone.sample_path(original), sample)
        clean = " ".join(str(name or "").split())[:64] or f"{record.get('name') or 'Voice'} copy"
        return voice_clone.create_clone(
            sample,
            name=clean,
            source=str(record.get("source") or "me"),
            consent=bool((record.get("consent") or {}).get("confirmed")),
            language=str(record.get("language") or ""),
            seconds=float(record.get("sample_seconds") or 0.0),
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ------------------------------------------------------------------ cleanup


def cleanup_plan(days: int = CLEANUP_DAYS, now: float | None = None) -> dict:
    """What a cleanup would remove. Read-only; the page asks first."""
    cutoff = float(now if now is not None else time.time()) - max(1, int(days)) * 86400
    rows = [row for row in (_clean_row(item) for item in _read()) if row]
    expired = sorted(
        (
            row for row in rows
            if not row.get("starred") and float(row.get("created") or 0.0) < cutoff
        ),
        key=lambda row: float(row.get("created") or 0.0),
    )
    return {
        "days": int(days),
        "cutoff": round(cutoff, 3),
        "count": len(expired),
        "takes": [
            {"id": row["id"], "label": row.get("label") or "", "created": row.get("created")}
            for row in expired[:50]
        ],
    }


def cleanup(confirm: bool = False, days: int = CLEANUP_DAYS) -> dict:
    """Remove unstarred takes past the cutoff, only with ``confirm``."""
    plan = cleanup_plan(days=days)
    if not confirm:
        return {"deleted": 0, "kept": plan["count"], "plan": plan, "confirmed": False}
    deleted = 0
    for row in plan["takes"]:
        try:
            if delete(row["id"]):
                deleted += 1
        except TakeError:
            continue
    return {"deleted": deleted, "kept": 0, "plan": plan, "confirmed": True}


# ------------------------------------------------------------------ voiceover


def split_script(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split a script into speakable lines at sentence boundaries.

    Our own simple splitter: sentence punctuation first, then clauses, then
    spaces. It never cuts a word, and it keeps the punctuation that was
    written, so the spoken line matches the script.
    """
    clean = " ".join(str(text or "").replace("\r", "\n").split("\n")).strip()
    if not clean:
        return []
    pieces = re.split(r"(?<=[.!?…;:])\s+", clean)
    chunks: list[str] = []
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        if len(piece) <= max_chars:
            chunks.append(piece)
            continue
        # A sentence longer than one request is cut at a clause, then at a
        # space. A word is never cut in half.
        pending = ""
        for part in re.split(r"(?<=[,])\s+", piece):
            part = part.strip()
            while len(part) > max_chars:
                cut = part.rfind(" ", 0, max_chars)
                if cut < max_chars // 2:
                    cut = max_chars
                chunks.append(part[:cut].strip())
                part = part[cut:].strip()
            if not part:
                continue
            if not pending:
                pending = part
            elif len(pending) + 1 + len(part) <= max_chars:
                pending = f"{pending} {part}"
            else:
                chunks.append(pending)
                pending = part
        if pending:
            chunks.append(pending)
    return [chunk for chunk in chunks if chunk]


def _stop(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise TakeError(CANCELLED, 409)


def _probe(path: Path) -> float:
    import voice_clone  # noqa: PLC0415

    return float(voice_clone._probe_seconds(path) or 0.0)


def _concat(parts: Sequence[Path], output: Path) -> None:
    import audio  # noqa: PLC0415 - audio imports tts and settings

    if not parts:
        raise TakeError("There was no speech to join together.")
    output.parent.mkdir(parents=True, exist_ok=True)
    if len(parts) == 1:
        shutil.copyfile(parts[0], output)
        return
    work = output.parent
    listing = work / "concat.txt"
    listing.write_text(
        "".join(f"file '{part.as_posix()}'\n" for part in parts),
        encoding="utf-8",
    )
    audio._run([
        audio._ffmpeg(), "-y", "-v", "error",
        "-f", "concat", "-safe", "0", "-i", str(listing),
        "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le", str(output),
    ], timeout=900)
    try:
        listing.unlink()
    except OSError:
        pass


def _words(text: str) -> list[str]:
    return [word for word in _WORD.split(str(text or "").lower()) if word]


def compare_line(script: str, heard: str) -> float:
    """How closely a re-transcription matches the line it should have said."""
    wanted = _words(script)
    got = _words(heard)
    if not wanted or not got:
        return 0.0
    return round(SequenceMatcher(None, wanted, got).ratio(), 3)


def _self_check(
    output: Path,
    chunks: Sequence[dict],
    *,
    language: str,
    work: Path,
    cancel_event: threading.Event | None,
) -> dict:
    """Re-transcribe each line with local Whisper and report drift.

    Advisory: an unavailable Whisper is reported, not treated as a failure.
    """
    import stt  # noqa: PLC0415 - optional local install

    if not stt._whisper_command():
        return {
            "status": "unavailable",
            "threshold": SELF_CHECK_THRESHOLD,
            "lines": [],
            "note": "Local Whisper is not installed, so the lines could not be checked. Install it in Setup, then check again.",
        }
    flagged = 0
    lines: list[dict] = []
    for index, chunk in enumerate(chunks):
        _stop(cancel_event)
        segment = work / f"line-{index + 1}.wav"
        try:
            voice_audio.cut(output, segment, float(chunk["start"]), float(chunk["end"]))
        except RuntimeError:
            lines.append({
                "index": chunk["index"],
                "script": chunk["text"],
                "heard": "",
                "ratio": 0.0,
                "drift": True,
            })
            flagged += 1
            continue
        try:
            result = stt.transcribe(
                segment, work / f"check-{index + 1}", float(chunk["seconds"]),
                lambda *_: None, language=language or "",
            )
        except Exception:  # noqa: BLE001 - a check never fails the take
            result = None
        heard = str((result or {}).get("text") or "").strip()
        ratio = compare_line(chunk["text"], heard)
        drift = ratio < SELF_CHECK_THRESHOLD or not heard
        if drift:
            flagged += 1
        lines.append({
            "index": chunk["index"],
            "script": chunk["text"],
            "heard": heard[:300],
            "ratio": ratio,
            "drift": bool(drift),
        })
    return {
        "status": "checked",
        "threshold": SELF_CHECK_THRESHOLD,
        "flagged": flagged,
        "lines": lines,
        "note": (
            f"{flagged} line{'s' if flagged != 1 else ''} may have drifted from the script. "
            "Listen to the flagged lines and correct the script or re-make them."
            if flagged else "Every line matched the script closely enough."
        ),
    }


def create_voiceover(
    *,
    text: str,
    engine: str,
    voice: str,
    rate: float = 1.0,
    language: str = "",
    label: str = "",
    clone: str = "",
    selfcheck: bool = True,
    cancel_event: threading.Event | None = None,
    progress: Callable[[float, str], None] | None = None,
) -> dict:
    """Speak a script in lines, join them, and keep the take.

    One voiceover runs at a time. A second request is refused with a sentence
    it can act on, not a queue position it cannot see.
    """
    import tts  # noqa: PLC0415 - tts reads settings at call time

    script = str(text or "").strip()
    if not script:
        raise TakeError("Type the script first, then make the voiceover.")
    if len(script) > MAX_SCRIPT_CHARS:
        raise TakeError(
            f"That script is {len(script)} characters. Keep it under {MAX_SCRIPT_CHARS} characters, or split it into two voiceovers."
        )
    chunks_text = split_script(script)
    if not chunks_text:
        raise TakeError("Type the script first, then make the voiceover.")
    if not _VOICEOVER.acquire(blocking=False):
        raise TakeError(
            "A voiceover is already being made. Wait for it to finish or stop it, then start another.",
            409,
        )
    work = settings_store.DATA / "cache" / "voiceover" / uuid.uuid4().hex
    work.mkdir(parents=True, exist_ok=True)
    cache = settings_store.DATA / "cache" / "voice"
    cache.mkdir(parents=True, exist_ok=True)
    try:
        parts: list[Path] = []
        chunks: list[dict] = []
        played = 0.0
        for index, line in enumerate(chunks_text, start=1):
            _stop(cancel_event)
            if progress is not None:
                progress((index - 1) / len(chunks_text), f"Speaking line {index} of {len(chunks_text)}")
            before = tts.line_cache_path(
                cache, engine, "", voice, line, rate, language, suffix=".wav",
            )
            cached = before.is_file() and before.stat().st_size > 512
            try:
                path = Path(tts.voice_sample(
                    engine, voice, line, cache, rate=rate, language=language,
                ))
            except Exception as exc:  # noqa: BLE001 - reword, keep the cause
                raise TakeError(
                    f"Could not speak line {index} of {len(chunks_text)}: {exc}. "
                    "Check the voice is still in the library and the key in Setup, then try again."
                ) from exc
            _stop(cancel_event)
            seconds = _probe(path)
            parts.append(path)
            chunks.append({
                "index": index,
                "text": line,
                "start": round(played, 3),
                "end": round(played + seconds, 3),
                "seconds": round(seconds, 3),
                "cached": cached,
            })
            played += seconds
        _stop(cancel_event)
        if progress is not None:
            progress(0.92, "Joining the lines")
        output = work / "voiceover.wav"
        try:
            _concat(parts, output)
        except Exception as exc:  # noqa: BLE001
            raise TakeError(
                f"Could not join the spoken lines: {exc}. Try a shorter script, then make it again."
            ) from exc
        check = _check(output)
        self_check = (
            _self_check(output, chunks, language=language, work=work, cancel_event=cancel_event)
            if selfcheck else
            {"status": "skipped", "threshold": SELF_CHECK_THRESHOLD, "lines": [], "note": ""}
        )
        take_id = f"take_{uuid.uuid4().hex[:24]}"
        target = audio_dir() / f"{take_id}.wav"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(output, target)
        record = {
            "id": take_id,
            "kind": "voiceover",
            "label": " ".join(str(label or "Voiceover").split())[:120],
            "created": _now(),
            "starred": False,
            "clone_voice": str(clone or ""),
            "cached": all(chunk["cached"] for chunk in chunks),
            "seconds": round(float((check or {}).get("duration") or played), 3),
            "check": check,
            "chunks": chunks,
            "selfcheck": self_check,
            "settings": {
                "text": script,
                "engine": str(engine or ""),
                "voice": str(voice or ""),
                "rate": round(float(rate or 1.0), 3),
                "language": str(language or ""),
            },
        }
        stored = _remember(record)
        if progress is not None:
            progress(1.0, "Done")
        return stored
    finally:
        shutil.rmtree(work, ignore_errors=True)
        _VOICEOVER.release()


def fingerprint(path: Path) -> str:
    """A short hash of a reference sample, for identity locks."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
