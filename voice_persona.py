"""Our own portable voice file: .vcutvoice

A ZIP with a small manifest, a short preview in the voice, and — only when the
creator ticks the box — the original reference recording. It is not a
VoiceStudio persona and shares no format with it.

    voice.json
    preview.wav          always: a short line made by this voice
    reference.mp3        only when "include the original recording" is ticked

The manifest carries the name, language, the consent record, a licence tag
and the fingerprint of the reference, so an import can prove the recording
was not swapped on the way.

Import rules: the file's consent record must confirm permission, the importer
must confirm again, the licence tag must be one we know, and the reference
must match its fingerprint. The preview alone cannot make a clone; ask for a
file exported with the reference included.
"""

from __future__ import annotations

import hashlib
import io
import json
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import settings_store
import voice_clone
import voice_errors

FORMAT = "vibecut-voice-persona"
VERSION = 1
MANIFEST = "voice.json"
PREVIEW = "preview.wav"
REFERENCE_NAMES = ("reference.mp3", "reference.wav", "reference.m4a")
EXTENSION = ".vcutvoice"
PREVIEW_TEXT = "Hi, this is how this voice sounds in VibeCut. It was exported as a portable voice file."
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_IMPORT_BYTES = 60 * 1024 * 1024
LICENCES = {
    "cloned-with-consent": "Made with the speaker's permission. Check that permission before using or sharing it.",
    "public-domain": "The speaker has released the recording for any use.",
}


class PersonaError(Exception):
    """A voice file step failed; the message is safe to show the creator."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def preview_path(record: dict, cache: Path) -> Path:
    """Make the short preview with this voice through OpenRouter."""
    import tts  # noqa: PLC0415 - settings are read at call time

    cache.mkdir(parents=True, exist_ok=True)
    try:
        path = tts.voice_sample(
            "heygen",
            str(record["voice_id"]),
            PREVIEW_TEXT,
            cache,
            rate=1.0,
            language=str(record.get("language") or ""),
        )
    except Exception as exc:  # noqa: BLE001 - reword with the next step
        raise PersonaError(
            voice_errors.fix(
                f"A preview could not be made: {exc}",
                "Check the voice and the OpenRouter key in Setup, then export the voice file again",
            )
        ) from exc
    return Path(path)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def build(record: dict, preview: Path, include_reference: bool) -> bytes:
    """The whole .vcutvoice file, built in memory."""
    sample = voice_clone.sample_path(record["voice_id"])
    manifest = {
        "format": FORMAT,
        "version": VERSION,
        "name": str(record.get("name") or "My voice"),
        "language": str(record.get("language") or ""),
        "source": str(record.get("source") or "me"),
        "consent": record.get("consent") or {"confirmed": False},
        "licence": "cloned-with-consent",
        "licence_note": LICENCES["cloned-with-consent"],
        "locked": bool(record.get("locked")),
        "created": record.get("created"),
        "exported": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "preview": {
            "file": PREVIEW,
            "text": PREVIEW_TEXT,
            "bytes": preview.stat().st_size,
            "seconds": round(float(voice_clone._probe_seconds(preview) or 0.0), 2),
        },
    }
    reference_bytes = b""
    if include_reference:
        if not sample.is_file():
            raise PersonaError(voice_errors.fix(
                "The reference recording is missing from this Mac",
                "Unlock the voice or restore a library backup, then export again",
            ))
        reference_bytes = sample.read_bytes()
        if len(reference_bytes) > voice_clone.MAX_REFERENCE_BYTES:
            raise PersonaError("The reference is over 15 MB. Use a shorter recording, then export the voice file.")
        manifest["reference"] = {
            "file": REFERENCE_NAMES[0],
            "included": True,
            "bytes": len(reference_bytes),
            "sha256": _sha(sample),
        }
    else:
        manifest["reference"] = {"included": False}

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=1))
        archive.writestr(PREVIEW, preview.read_bytes())
        if reference_bytes:
            archive.writestr(REFERENCE_NAMES[0], reference_bytes)
    return buffer.getvalue()


def filename(record: dict) -> str:
    stem = "".join(
        character if character.isalnum() or character in " -_" else "-"
        for character in str(record.get("name") or "voice")
    ).strip().replace(" ", "-") or "voice"
    return f"vibecut-voice-{stem[:40]}-{datetime.now(timezone.utc):%Y%m%d-%H%M}{EXTENSION}"


def _member(info: zipfile.ZipInfo) -> PurePosixPath:
    name = str(info.filename or "").replace("\\", "/")
    path = PurePosixPath(name)
    drive = bool(path.parts and len(path.parts[0]) == 2 and path.parts[0][1] == ":")
    if not name or "\x00" in name or name.startswith("/") or path.is_absolute() or ".." in path.parts or drive:
        raise PersonaError(voice_errors.fix(
            "That voice file has an unsafe file path",
            "Export a fresh voice file from VibeCut, then import that",
        ))
    return path


def _manifest(archive: zipfile.ZipFile, infos: list[zipfile.ZipInfo]) -> dict:
    found = [info for info in infos if info.filename == MANIFEST]
    if len(found) != 1:
        raise PersonaError(
            "That ZIP has no voice file manifest. Choose a file exported from VibeCut, then import it again."
        )
    if found[0].file_size > MAX_MANIFEST_BYTES:
        raise PersonaError("That voice file has an oversized manifest. Export a fresh one, then import that.")
    try:
        data = json.loads(archive.read(found[0]).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PersonaError("That voice file's manifest cannot be read. Export a fresh one, then import that.") from exc
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise PersonaError(
            "That file is not a VibeCut voice file. Choose a .vcutvoice file, then import it again."
        )
    if str(data.get("version")) != str(VERSION):
        raise PersonaError(
            "That voice file comes from another version of VibeCut. Export a fresh one here, then import that."
        )
    return data


def read(raw: bytes, *, name: str = "") -> dict:
    """Validate a file and return what an import needs.

    Raises :class:`PersonaError` with a fix-it sentence for anything that does
    not match the format, the licence list or the recorded consent.
    """
    if not raw:
        raise PersonaError(voice_errors.EMPTY_FILE)
    if len(raw) > MAX_IMPORT_BYTES:
        raise PersonaError("That voice file is over 60 MB. Export one with a shorter reference, then import it.")
    if not zipfile.is_zipfile(io.BytesIO(raw)):
        raise PersonaError(
            "That file is not a VibeCut voice file. Choose a .vcutvoice file, then import it again."
        )
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        for info in infos:
            _member(info)
        names = {info.filename for info in infos}
        manifest = _manifest(archive, infos)
        unknown = names - {MANIFEST, PREVIEW, *REFERENCE_NAMES}
        if unknown:
            raise PersonaError(
                "That voice file holds files VibeCut does not expect. Export a fresh voice file, then import that."
            )
        licence = str(manifest.get("licence") or "")
        if licence not in LICENCES:
            raise PersonaError(
                "That voice file's licence tag is not one VibeCut knows. Export a fresh voice file here, then import that."
            )
        consent = manifest.get("consent") if isinstance(manifest.get("consent"), dict) else {}
        if not consent.get("confirmed"):
            raise PersonaError(
                "That voice file has no confirmed consent record. Ask the speaker to export a voice file with consent recorded."
            )
        reference = manifest.get("reference") if isinstance(manifest.get("reference"), dict) else {}
        if not reference.get("included"):
            raise PersonaError(
                "This voice file carries only a preview, not the recording, so it cannot speak. "
                "Ask for a file exported with 'Include the original recording' ticked."
            )
        member = str(reference.get("file") or "")
        if member not in REFERENCE_NAMES or member not in names:
            raise PersonaError(
                "The recording named in that voice file is missing. Export a fresh voice file, then import that."
            )
        info = next(item for item in infos if item.filename == member)
        if info.file_size > voice_clone.MAX_REFERENCE_BYTES:
            raise PersonaError("The recording in that voice file is over 15 MB. Ask for a shorter reference, then import it.")
        blob = archive.read(info)
        expected = str(reference.get("sha256") or "")
        if expected and hashlib.sha256(blob).hexdigest() != expected:
            raise PersonaError(
                "The recording in that voice file does not match its fingerprint. Ask for a fresh export, then import that."
            )
    clean_name = " ".join(str(name or manifest.get("name") or "Imported voice").split())[:64] or "Imported voice"
    language = str(manifest.get("language") or "").strip().lower().split("-")[0]
    if language not in voice_clone.LANGUAGES:
        language = ""
    return {
        "name": clean_name,
        "language": language,
        "source": str(manifest.get("source") or "me") if manifest.get("source") in voice_clone.SOURCES else "me",
        "licence": licence,
        "consent": consent,
        "reference": blob,
        "reference_name": member,
    }


def import_voice(raw: bytes, *, consent: bool, name: str = "") -> dict:
    """Create a clone from a validated voice file. Never overwrites a voice."""
    if not consent:
        raise PersonaError(
            "Confirm you have permission to import this voice. Tick the consent box, then import the file again."
        )
    parsed = read(raw, name=name)
    work = settings_store.DATA / "cache" / "persona" / f"{int(time.time() * 1000)}-{hash(raw) & 0xffff:x}"
    work.mkdir(parents=True, exist_ok=True)
    try:
        sample = work / parsed["reference_name"]
        sample.write_bytes(parsed["reference"])
        digest = hashlib.sha256(parsed["reference"]).hexdigest()
        for row in voice_clone.list_clones():
            try:
                if _sha(voice_clone.sample_path(row["voice_id"])) == digest:
                    return {"imported": False, "already": True, "voice": row, "licence": parsed["licence"]}
            except OSError:
                continue
        seconds = float(voice_clone._probe_seconds(sample) or 0.0)
        record = voice_clone.create_clone(
            sample,
            name=parsed["name"],
            source=parsed["source"],
            consent=True,
            language=parsed["language"],
            seconds=seconds,
        )
        return {"imported": True, "already": False, "voice": record, "licence": parsed["licence"]}
    finally:
        import shutil

        shutil.rmtree(work, ignore_errors=True)
