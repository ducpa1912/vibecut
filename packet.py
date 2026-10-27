"""Build immutable Publish Packets from ready renders or artifacts.

A packet is a self-contained hand-off for one story:

    data/jobs/<job_id>/packets/<packet_id>/
      packet.json
      media/<ascii-name>.mp4
      captions/<ascii-name>.srt
      covers/<ascii-name>-cover-1.jpg
      covers/<ascii-name>-cover-2.jpg
      copy.txt                      ordered post copy: titles, description,
                                    hashtags, pin comment
      <ascii-name>-packet-<short-id>.zip

The current build reads ready render records from ``job["renders"]`` and
trust-core manifests/summaries under ``job["artifacts"]`` or
``artifacts/<id>/``. The adapter uses ``artifacts.load_manifest`` and
``media_path`` when that module is present, with a job-relative disk fallback.
Packet manifests reference the supplied artifact ID or the existing render
record key; this module never derives a second artifact identity.

Packet JSON never contains source paths, the job directory, secrets, or other
absolute paths.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import threading
import time
import unicodedata
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import exports
import history_store
import audio
import captions
import compose_render
import edits
import fx
import render

SCHEMA = "vibecut.publish_packet/2"
SCHEMA_V1 = "vibecut.publish_packet/1"
SCHEMAS = (SCHEMA_V1, SCHEMA)
AUDIO_SCHEMA = "vibecut.packet_audio/1"
MUSIC_SCHEMA = "vibecut.packet_music/1"
IDENTITY_SCHEMA = "vibecut.packet_identity/1"
PACKET_ROOT = "packets"
DESCRIPTION_LIMIT = 125
PIN_COMMENT_LIMIT = 500
COPY_FILE = "copy.txt"
TITLE_COUNT = 3
COVER_COUNT = 2
HASHTAG_MIN = 3
HASHTAG_MAX = 8
PACKET_ID_RE = re.compile(r"^[a-f0-9]{24}$")
ARTIFACT_ID_RE = re.compile(r"^art_[0-9a-f]{24}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
HASHTAG_RE = re.compile(r"^#\w{1,50}$", re.UNICODE)
CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
SAFE_STEM_RE = re.compile(r"[^a-z0-9]+")
SRT_TIME_RE = re.compile(
    r"(\d+):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*"
    r"(\d+):(\d{2}):(\d{2})[,.](\d{3})(?:\s+.*)?"
)

_BUILD_LOCK = threading.Lock()


class PacketError(Exception):
    """A packet request that cannot complete without losing information."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        suggestion: str = "",
        status: int = 409,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.suggestion = suggestion
        self.status = int(status)
        self.details = details or {}

    def as_detail(self) -> dict:
        value = {
            "code": self.code,
            "message": self.message,
            "suggestion": self.suggestion,
        }
        if self.details:
            value["details"] = self.details
        return value


@dataclass
class PacketRequest:
    story_id: str = ""
    titles: list[str] = field(default_factory=list)
    description: str = ""
    hashtags: list[str] = field(default_factory=list)
    artifact_ids: list[str] = field(default_factory=list)
    render_keys: list[str] = field(default_factory=list)
    cover_times: list[float] | None = None
    pin_comment: str = ""


@dataclass
class PacketSource:
    """One selected video plus the captions and cover seed that belong to it."""

    artifact_id: str
    render_key: str | None
    video_path: Path
    poster_path: Path | None
    sha256: str
    size: int
    duration: float
    poster_sha256: str = ""
    target: int | None = None
    width: int | None = None
    height: int | None = None
    aspect: str | None = None
    quality: str | None = None
    plan: dict | None = None
    scenes: list[dict] = field(default_factory=list)
    captions_srt: str = ""
    captions_source: str = "plan"
    updated: float | None = None
    version: int | None = None
    supersedes: str | None = None
    spec: dict = field(default_factory=dict)
    edit: dict | None = None
    audio_plan: dict | None = None
    transcript_id: str = ""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_valid_mp4(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            head = handle.read(64)
    except OSError:
        return False
    return len(head) >= 12 and head[4:8] == b"ftyp"


def _validate_mp4(path: Path, artifact_id: str) -> None:
    if not _is_valid_mp4(path):
        raise PacketError(
            "artifact_invalid_media",
            f"Artifact {artifact_id!r} is not a valid MP4 container.",
            suggestion="Re-render the cut and package the final MP4.",
            status=422, details={"artifact_id": artifact_id},
        )
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise PacketError(
            "media_probe_unavailable",
            "ffprobe is not available; MP4 integrity cannot be verified.",
            suggestion="Install ffprobe or re-run the pack on a machine that has it.",
            status=503, details={"artifact_id": artifact_id},
        )
    try:
        result = subprocess.run(
            [
                ffprobe, "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=codec_type,duration",
                "-show_entries", "format=duration", "-of", "json", str(path),
            ],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PacketError(
            "artifact_invalid_media",
            f"Artifact {artifact_id!r} could not be probed: {exc}",
            suggestion="Re-render the cut and package the final MP4.",
            status=422, details={"artifact_id": artifact_id},
        ) from exc
    if result.returncode != 0:
        raise PacketError(
            "artifact_invalid_media",
            f"Artifact {artifact_id!r} is truncated or unplayable.",
            suggestion="Re-render the cut and package the final MP4.",
            status=422, details={"artifact_id": artifact_id},
        )
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise PacketError(
            "artifact_invalid_media",
            f"Artifact {artifact_id!r} returned unreadable probe data.",
            suggestion="Re-render the cut and package the final MP4.",
            status=422, details={"artifact_id": artifact_id},
        ) from exc
    streams = payload.get("streams") if isinstance(payload, dict) else None
    if not isinstance(streams, list) or not any(
        isinstance(stream, dict) and stream.get("codec_type") == "video"
        for stream in streams
    ):
        raise PacketError(
            "artifact_invalid_media",
            f"Artifact {artifact_id!r} has no playable video stream.",
            suggestion="Re-render the cut and package the final MP4.",
            status=422, details={"artifact_id": artifact_id},
        )
    duration = None
    if isinstance(payload.get("format"), dict):
        try:
            duration = float(payload["format"].get("duration"))
        except (TypeError, ValueError):
            duration = None
    if duration is None:
        for stream in streams:
            if not isinstance(stream, dict):
                continue
            try:
                duration = float(stream.get("duration"))
                break
            except (TypeError, ValueError):
                continue
    if duration is None or not math.isfinite(duration) or duration <= 0:
        raise PacketError(
            "artifact_invalid_media",
            f"Artifact {artifact_id!r} has no measurable video duration.",
            suggestion="Re-render the cut and package the final MP4.",
            status=422, details={"artifact_id": artifact_id},
        )


def _is_valid_jpeg_bytes(payload: bytes) -> bool:
    return len(payload) > 3 and payload[:2] == b"\xff\xd8" and payload[-2:] == b"\xff\xd9"


def _is_valid_jpeg(path: Path) -> bool:
    try:
        size = path.stat().st_size
        if size < 4:
            return False
        with path.open("rb") as handle:
            head = handle.read(3)
            handle.seek(-2, os.SEEK_END)
            tail = handle.read(2)
        if not head.startswith(b"\xff\xd8\xff") or tail != b"\xff\xd9":
            return False
        from PIL import Image

        with Image.open(path) as image:
            image.verify()
    except Exception:  # noqa: BLE001 - undecodable image is not a cover
        return False
    return True


def _parse_srt_cues(text: str) -> list[dict]:
    normalized = str(text or "").replace("\ufeff", "").replace("\r\n", "\n")
    cues: list[dict] = []
    for block in re.split(r"\n\s*\n", normalized):
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        match = None
        for line in lines:
            match = SRT_TIME_RE.fullmatch(line)
            if match:
                break
        if not match:
            continue
        values = [int(match.group(index)) for index in (1, 2, 3, 4, 5, 6, 7, 8)]
        start = values[0] * 3600 + values[1] * 60 + values[2] + values[3] / 1000
        end = values[4] * 3600 + values[5] * 60 + values[6] + values[7] / 1000
        try:
            text_index = lines.index(match.group(0)) + 1
        except ValueError:
            text_index = 1
        body = " ".join(lines[text_index:]).strip()
        if body and end > start:
            cues.append({"start": start, "end": end, "text": body})
    return cues


def _validate_captions(text: str, artifact_id: str) -> None:
    if not _parse_srt_cues(text):
        raise PacketError(
            "captions_invalid",
            f"Artifact {artifact_id!r} has no valid SRT cues.",
            suggestion="Write at least one timed, non-empty caption cue before packaging.",
            status=422,
            details={"artifact_id": artifact_id},
        )


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").split())


def safe_filename(value: object, fallback: str = "packet", limit: int = 48) -> str:
    """Return a deterministic lowercase ASCII stem safe for every packet file."""
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    stem = SAFE_STEM_RE.sub("-", ascii_text.lower()).strip("-")
    if not stem:
        stem = fallback
    stem = SAFE_STEM_RE.sub("-", stem).strip("-")
    return (stem[:limit].strip("-") or fallback)


def _list_of_strings(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def normalize_request(raw: PacketRequest | dict) -> PacketRequest:
    if isinstance(raw, PacketRequest):
        data = raw
    elif isinstance(raw, dict):
        data = PacketRequest(
            story_id=str(raw.get("story_id") or ""),
            titles=_list_of_strings(raw.get("titles")),
            description=str(raw.get("description") or ""),
            hashtags=_list_of_strings(raw.get("hashtags")),
            artifact_ids=_list_of_strings(raw.get("artifact_ids")),
            render_keys=_list_of_strings(raw.get("render_keys")),
            cover_times=raw.get("cover_times"),
            pin_comment=str(raw.get("pin_comment") or ""),
        )
    else:
        raise PacketError(
            "packet_request_invalid", "Packet body must be an object.",
            suggestion="Send a JSON object with story_id and render_keys.", status=400,
        )

    story_id = _clean_text(data.story_id)
    if not story_id or len(story_id) > 120 or CONTROL_RE.search(story_id):
        raise PacketError(
            "story_id_invalid", "story_id must be a short non-empty string.",
            suggestion="Use the story or render key this packet belongs to.", status=400,
        )

    titles = [_clean_text(item) for item in data.titles]
    titles = [item for item in titles if item]
    if len(titles) != TITLE_COUNT:
        raise PacketError(
            "titles_invalid", f"Packet needs exactly {TITLE_COUNT} non-empty titles.",
            suggestion="Supply three title candidates, best first.", status=400,
            details={"count": len(titles)},
        )
    for title in titles:
        if len(title) > 100 or CONTROL_RE.search(title):
            raise PacketError(
                "title_invalid", "Each title must be 1 to 100 characters on one line.",
                suggestion="Shorten the title and remove control characters.", status=400,
            )

    description = _clean_text(data.description)
    if not description:
        raise PacketError(
            "description_missing", "Packet needs a 125-character description hook.",
            suggestion="Write one sentence that earns the click.", status=400,
        )
    if len(description) > DESCRIPTION_LIMIT:
        raise PacketError(
            "description_too_long",
            f"Description is {len(description)} characters; the limit is {DESCRIPTION_LIMIT}.",
            suggestion="Cut the description to 125 characters or fewer.", status=400,
            details={"length": len(description), "limit": DESCRIPTION_LIMIT},
        )

    hashtags: list[str] = []
    seen: set[str] = set()
    for item in data.hashtags:
        tag = _clean_text(item)
        if not tag:
            continue
        if not tag.startswith("#"):
            tag = f"#{tag}"
        if not HASHTAG_RE.fullmatch(tag):
            raise PacketError(
                "hashtag_invalid", f"Hashtag {tag!r} is not valid.",
                suggestion="Use letters, numbers, or underscores after #.", status=400,
            )
        key = tag.casefold()
        if key in seen:
            continue
        seen.add(key)
        hashtags.append(tag)
    if not HASHTAG_MIN <= len(hashtags) <= HASHTAG_MAX:
        raise PacketError(
            "hashtags_invalid",
            f"Packet needs {HASHTAG_MIN} to {HASHTAG_MAX} unique hashtags.",
            suggestion="Add or remove hashtags; each starts with #.", status=400,
            details={"count": len(hashtags)},
        )

    artifact_ids = [item.strip() for item in data.artifact_ids if item and item.strip()]
    render_keys = [item.strip() for item in data.render_keys if item and item.strip()]
    if not artifact_ids and not render_keys:
        raise PacketError(
            "artifacts_missing", "Select at least one ready render or artifact.",
            suggestion="Pass render_keys from job.renders or artifact_ids.", status=400,
        )

    cover_times: list[float] | None = None
    raw_cover_times = data.cover_times
    if isinstance(raw_cover_times, (list, tuple)) and not raw_cover_times:
        raw_cover_times = None
    if raw_cover_times is not None:
        raw_times = raw_cover_times
        if isinstance(raw_times, (int, float)) and not isinstance(raw_times, bool):
            raw_times = [raw_times]
        if not isinstance(raw_times, (list, tuple)) or len(raw_times) != COVER_COUNT:
            raise PacketError(
                "cover_times_invalid", "cover_times must contain exactly two times.",
                suggestion="Pass two non-negative seconds, or omit the field.", status=400,
            )
        cover_times = []
        for value in raw_times:
            if isinstance(value, bool):
                raise PacketError(
                    "cover_times_invalid", "Cover times must be numbers.",
                    suggestion="Pass two non-negative seconds.", status=400,
                )
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise PacketError(
                    "cover_times_invalid", "Cover times must be numbers.",
                    suggestion="Pass two non-negative seconds.", status=400,
                ) from exc
            if not math.isfinite(number) or number < 0:
                raise PacketError(
                    "cover_times_invalid", "Cover times must be non-negative seconds.",
                    suggestion="Pass two non-negative seconds.", status=400,
                )
            cover_times.append(number)

    pin_comment = "\n".join(
        line.strip() for line in str(data.pin_comment or "").strip().splitlines()
    ).strip()
    if len(pin_comment) > PIN_COMMENT_LIMIT or CONTROL_RE.search(pin_comment.replace("\n", " ")):
        raise PacketError(
            "pin_comment_invalid",
            f"Pin comment must be plain text up to {PIN_COMMENT_LIMIT} characters.",
            suggestion="Shorten the pin comment and remove control characters.", status=400,
            details={"length": len(pin_comment), "limit": PIN_COMMENT_LIMIT},
        )

    return PacketRequest(
        story_id=story_id,
        titles=titles,
        description=description,
        hashtags=hashtags,
        artifact_ids=artifact_ids,
        render_keys=render_keys,
        cover_times=cover_times,
        pin_comment=pin_comment,
    )


# ------------------------------------------------------------------ adapter


def _safe_job_path(
    job_dir: Path,
    raw: object,
    *,
    subdirs: Iterable[str] = (),
) -> Path | None:
    text = str(raw or "").strip()
    if not text:
        return None
    relative = Path(text)
    root = Path(job_dir).resolve()
    if relative.is_absolute():
        try:
            resolved = relative.resolve()
        except OSError:
            return None
        if resolved != root and root not in resolved.parents:
            raise PacketError(
                "artifact_path_invalid", "Artifact path escapes the job directory.",
                suggestion="Re-render the cut so the artifact uses a job-relative path.",
            )
        return resolved if resolved.is_file() else None
    if ".." in relative.parts:
        raise PacketError(
            "artifact_path_invalid", "Artifact path must stay inside the job directory.",
            suggestion="Re-render the cut so the artifact uses a job-relative path.",
        )
    candidates = [root / relative]
    if len(relative.parts) == 1:
        candidates.extend(root / name / relative for name in subdirs)
    fallback = candidates[0]
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved != root and root not in resolved.parents:
            raise PacketError(
                "artifact_path_invalid", "Artifact path escapes the job directory.",
                suggestion="Re-render the cut so the artifact uses a job-relative path.",
            )
        if resolved.is_file():
            return resolved
    return fallback


def _artifact_entries(job: dict) -> list[dict]:
    raw = job.get("artifacts")
    rows: list[dict] = []
    if isinstance(raw, dict):
        for key, value in raw.items():
            row = dict(value) if isinstance(value, dict) else {"path": value}
            row.setdefault("id", str(key))
            rows.append(row)
    elif isinstance(raw, list):
        for index, value in enumerate(raw):
            if isinstance(value, dict):
                row = dict(value)
                if not row.get("id") and row.get("artifact_id"):
                    row["id"] = row["artifact_id"]
                if not row.get("id"):
                    continue
                rows.append(row)
    return rows


def _trust_artifacts():
    try:
        import artifacts as module
    except Exception:  # noqa: BLE001 - packet must also run on branches without trust-core
        return None
    return module if hasattr(module, "load_manifest") else None


def _artifact_is_safe(artifact_id: object) -> bool:
    module = _trust_artifacts()
    if module is not None:
        try:
            return bool(module.is_safe_artifact_id(str(artifact_id or "")))
        except Exception:  # noqa: BLE001
            pass
    return bool(ARTIFACT_ID_RE.fullmatch(str(artifact_id or "")))


def _manifest_from_disk(job_dir: Path, artifact_id: str) -> dict | None:
    path = Path(job_dir) / "artifacts" / artifact_id / "manifest.json"
    try:
        root = Path(job_dir).resolve()
        resolved = path.resolve()
    except OSError:
        return None
    if resolved != root and root not in resolved.parents:
        return None
    if not resolved.is_file():
        return None
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PacketError(
            "artifact_manifest_invalid",
            f"Artifact {artifact_id!r} has an unreadable manifest.",
            suggestion="Rebuild the artifact manifest before packaging.",
            status=422,
            details={"artifact_id": artifact_id},
        ) from exc
    if not isinstance(value, dict) or not isinstance(value.get("spec"), dict):
        raise PacketError(
            "artifact_manifest_invalid",
            f"Artifact {artifact_id!r} has an invalid manifest.",
            suggestion="Rebuild the artifact manifest before packaging.",
            status=422,
            details={"artifact_id": artifact_id},
        )
    if str(value.get("artifact_id") or artifact_id) != artifact_id:
        raise PacketError(
            "artifact_manifest_invalid",
            f"Artifact {artifact_id!r} manifest points at another artifact.",
            suggestion="Refresh the artifact index.",
            status=422,
            details={"artifact_id": artifact_id},
        )
    return value


def _artifact_plan(manifest: dict) -> dict | None:
    spec = manifest.get("spec") if isinstance(manifest.get("spec"), dict) else {}
    plan = manifest.get("plan")
    clips = plan.get("clips") if isinstance(plan, dict) else None
    if not isinstance(clips, list) or not clips:
        clips = spec.get("clips")
    if not isinstance(clips, list) or not clips:
        clips = spec.get("plan", {}).get("clips") if isinstance(spec.get("plan"), dict) else None
    if not isinstance(clips, list) or not clips:
        return None
    total = 0.0
    for clip in clips:
        if isinstance(clip, dict):
            try:
                total += float(clip.get("dur") or 0.0)
            except (TypeError, ValueError):
                pass
    target = spec.get("target")
    if target is None and isinstance(plan, dict):
        target = plan.get("target")
    hook = spec.get("hook_scene")
    if hook is None and isinstance(plan, dict):
        hook = plan.get("hook_scene")
    return {
        "target": target,
        "total": round(total, 3),
        "hook_scene": hook,
        "auto": not bool(spec.get("hook_override")),
        "clip_count": len(clips),
        "clips": clips,
    }


def _record_for_artifact(job: dict, artifact_id: str) -> dict:
    for record in (job.get("renders") or {}).values():
        if isinstance(record, dict) and str(record.get("artifact_id") or "") == artifact_id:
            return record
    return {}


def resolve_trust_artifact(
    job: dict,
    job_dir: Path | str,
    artifact_id: str,
) -> dict | None:
    """Resolve a trust-core artifact summary or manifest to packable paths.

    Uses ``artifacts.load_manifest``/``media_path`` when that module is present
    (the integrated v0.14 tree). A disk manifest reader keeps packet-only
    branches and fixtures usable, without deriving a second artifact identity.
    """
    artifact_id = str(artifact_id or "").strip()
    if not _artifact_is_safe(artifact_id):
        raise PacketError(
            "artifact_id_invalid", "Artifact id is not valid.",
            suggestion="Use an artifact id returned by the trust-core store.",
            status=400, details={"artifact_id": artifact_id},
        )
    directory = Path(job_dir)
    module = _trust_artifacts()
    manifest: dict | None = None
    if module is not None:
        try:
            manifest = module.load_manifest(directory, artifact_id)
        except Exception as exc:  # noqa: BLE001 - preserve trust-core failure class
            raise PacketError(
                "artifact_manifest_error",
                f"Artifact store could not load {artifact_id!r}: {exc}",
                suggestion="Check the artifact store, then retry.",
                status=500, details={"artifact_id": artifact_id},
            ) from exc
        manifest_file = directory / "artifacts" / artifact_id / "manifest.json"
        if manifest is None and manifest_file.is_file():
            raise PacketError(
                "artifact_manifest_invalid",
                f"Artifact {artifact_id!r} manifest failed trust-core validation.",
                suggestion="Rebuild the artifact manifest before packaging.",
                status=422, details={"artifact_id": artifact_id},
            )
    else:
        manifest = _manifest_from_disk(directory, artifact_id)

    summary = next(
        (
            row for row in _artifact_entries(job)
            if str(row.get("id") or "") == artifact_id
        ),
        {},
    )
    record = _record_for_artifact(job, artifact_id)
    if manifest is None and not summary and not record:
        return None

    spec = (manifest or {}).get("spec") if isinstance((manifest or {}).get("spec"), dict) else {}
    render_info = (manifest or {}).get("render")
    render_info = render_info if isinstance(render_info, dict) else {}
    plan = _artifact_plan(manifest or {})

    def artifact_media(name: str) -> Path | None:
        if module is not None:
            try:
                path = Path(module.media_path(directory, artifact_id, name))
                if path.is_file():
                    return path
            except Exception:  # noqa: BLE001
                pass
        path = directory / "artifacts" / artifact_id / name
        return path if path.is_file() else None

    reel = artifact_media("reel.mp4")
    if reel is None and record.get("path"):
        reel = _safe_job_path(
            directory, record.get("path"), subdirs=("renders", "artifacts", "media"),
        )
    poster = artifact_media("poster.jpg")
    if poster is None and record.get("poster"):
        poster = _safe_job_path(
            directory, record.get("poster"), subdirs=("renders", "artifacts", "media"),
        )
    captions = artifact_media("captions.srt")
    if captions is None:
        captions = _safe_job_path(
            directory,
            record.get("captions_path") or record.get("srt_path"),
            subdirs=("captions", "renders", "artifacts"),
        )

    status = (
        (manifest or {}).get("status")
        or summary.get("status")
        or record.get("status")
        or "ready"
    )
    target = spec.get("target", summary.get("target", record.get("target")))
    quality = spec.get("quality") or summary.get("quality") or record.get("quality")
    aspect = spec.get("aspect") or summary.get("aspect") or record.get("aspect")
    duration = (
        render_info.get("duration")
        or summary.get("duration")
        or record.get("duration")
        or record.get("total")
        or target
    )
    return {
        "id": artifact_id,
        "artifact_id": artifact_id,
        "status": status,
        "path": str(reel) if reel is not None else None,
        "poster": str(poster) if poster is not None else None,
        "captions_path": str(captions) if captions is not None else None,
        "cues": (
            (manifest or {}).get("cues")
            or spec.get("cues")
            or (plan.get("cues") if isinstance(plan, dict) else None)
        ),
        "plan": plan,
        "plan_strict": True,
        "spec": spec,
        "edit_id": (manifest or {}).get("edit_id"),
        "edit_hash": spec.get("edit_hash") or "",
        "transcript_id": spec.get("transcript_id") or "",
        "audio_hash": spec.get("audio_hash") or "",
        "music_hash": spec.get("music_hash") or "",
        "target": target,
        "quality": quality,
        "aspect": aspect,
        "duration": duration,
        "width": render_info.get("width") or record.get("width"),
        "height": render_info.get("height") or record.get("height"),
        "updated": (manifest or {}).get("updated") or record.get("updated"),
        "version": (manifest or {}).get("version"),
        "supersedes": (manifest or {}).get("supersedes"),
        "record_key": (
            (manifest or {}).get("record_key")
            or summary.get("record_key")
            or record.get("record_key")
        ),
    }


def _plan_from_history(job_dir: Path, record: dict) -> dict | None:
    entry_id = str(record.get("history_id") or "").strip()
    if not entry_id:
        return None
    try:
        item = history_store.get_entry(Path(job_dir), entry_id)
    except Exception:  # noqa: BLE001 - history is optional evidence
        return None
    plan = ((item or {}).get("snapshot") or {}).get("plan")
    return plan if isinstance(plan, dict) and plan.get("clips") else None


def _plan_from_analysis(job: dict, target: int | None) -> dict | None:
    analysis = job.get("analysis") or {}
    plans = analysis.get("plans") or {}
    if not isinstance(plans, dict):
        return None
    candidates = []
    if target is not None:
        candidates.append(str(int(target)))
    candidates.extend(["30", "15", "60"])
    for key in candidates:
        plan = plans.get(key)
        if isinstance(plan, dict) and plan.get("clips"):
            return plan
    return None


def _simple_plan(job: dict, target: int) -> dict | None:
    scenes = [
        scene for scene in ((job.get("analysis") or {}).get("scenes") or [])
        if isinstance(scene, dict) and not scene.get("black")
    ]
    def scene_start(scene: dict) -> float:
        try:
            return float(scene.get("start") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    scenes.sort(key=lambda scene: (scene_start(scene), scene.get("id") or 0))
    if not scenes:
        return None
    clips: list[dict] = []
    total = 0.0
    for scene in scenes:
        try:
            start = float(scene.get("start") or 0.0)
            end = float(scene.get("end") or (start + float(scene.get("dur") or 0.0)))
        except (TypeError, ValueError):
            continue
        if total >= target:
            break
        if end - start <= 0.1:
            continue
        clip_end = min(end, start + max(0.2, target - total))
        clips.append({
            "scene": scene.get("id"),
            "start": round(start, 3),
            "end": round(clip_end, 3),
            "dur": round(clip_end - start, 3),
            "role": "beat",
        })
        total += clip_end - start
    if not clips:
        return None
    clips[0]["role"] = "hook"
    if len(clips) > 1:
        clips[-1]["role"] = "payoff"
    return {
        "target": target,
        "total": round(total, 3),
        "hook_scene": clips[0].get("scene"),
        "clip_count": len(clips),
        "clips": clips,
        "note": "Fallback plan for packet captions",
    }


def _fallback_plan(job: dict, target: int | None, hook: int | None) -> dict | None:
    analysis = job.get("analysis") or {}
    scenes = analysis.get("scenes") or []
    if not scenes or target is None:
        return None
    duration = float((job.get("source") or {}).get("duration") or 0.0)
    if duration <= 0:
        try:
            duration = max(
                float(scene.get("end") or 0.0)
                for scene in scenes if isinstance(scene, dict)
            )
        except (TypeError, ValueError):
            duration = 0.0
    if duration > 0:
        try:
            import pipeline

            plan = pipeline.build_plan(
                scenes, duration, int(target), hook, analysis.get("hook_scene"),
            )
            if isinstance(plan, dict) and plan.get("clips"):
                return plan
        except Exception:  # noqa: BLE001 - captions are optional evidence, not a crash
            pass
    return _simple_plan(job, int(target))


def _plan_from_clips(record: dict) -> dict | None:
    clips = record.get("clips")
    if not isinstance(clips, list) or not clips:
        return None
    total = 0.0
    for clip in clips:
        if isinstance(clip, dict):
            try:
                total += float(clip.get("dur") or 0.0)
            except (TypeError, ValueError):
                pass
    return {
        "target": record.get("target"),
        "total": round(total, 3),
        "clip_count": len(clips),
        "hook_scene": record.get("hook_scene") or record.get("hook"),
        "clips": clips,
    }


def _resolve_plan(
    job: dict,
    job_dir: Path,
    record: dict,
    *,
    prefer: dict | None = None,
) -> dict | None:
    if isinstance(prefer, dict) and prefer.get("clips"):
        return prefer
    plan = record.get("plan")
    if isinstance(plan, dict) and plan.get("clips"):
        return plan
    plan = _plan_from_clips(record)
    if plan:
        return plan
    if record.get("plan_strict") or record.get("_artifact_plan_strict"):
        return None
    plan = _plan_from_history(Path(job_dir), record)
    if plan:
        return plan
    try:
        target = int(record.get("target") or 0) or None
    except (TypeError, ValueError):
        target = None
    plan = _plan_from_analysis(job, target)
    if plan:
        return plan
    try:
        hook = int(record.get("hook")) if record.get("hook") is not None else None
    except (TypeError, ValueError):
        hook = None
    return _fallback_plan(job, target, hook)


def _srt_for_plan(plan: dict, scenes: list[dict]) -> str:
    clips = plan.get("clips") or []
    if not clips:
        return ""
    try:
        cues = exports.plan_cues(plan, clips, scenes)
        return exports.srt(cues)
    except (TypeError, ValueError, KeyError):
        return ""


def _captions_from_record(
    job: dict,
    job_dir: Path,
    record: dict,
    plan: dict | None,
) -> tuple[str, str]:
    direct = record.get("captions_srt")
    if isinstance(direct, str):
        return direct, "artifact"
    srt_text = record.get("srt")
    if isinstance(srt_text, str):
        return srt_text, "artifact"
    path = _safe_job_path(
        job_dir,
        record.get("captions_path") or record.get("srt_path"),
        subdirs=("captions", "renders"),
    )
    if path is not None and path.is_file():
        try:
            return path.read_text(encoding="utf-8", errors="replace"), "artifact"
        except OSError:
            pass
    if plan:
        scenes = (job.get("analysis") or {}).get("scenes") or []
        return _srt_for_plan(plan, scenes), "plan"
    return "", "missing"


def _expected_digest(record: dict) -> str:
    value = (
        record.get("sha256")
        or record.get("checksum")
        or record.get("content_hash")
        or ""
    )
    return str(value).strip().lower()


def _verify_digest(path: Path, expected: str, artifact_id: str) -> str:
    digest = _sha256_file(path)
    if expected:
        if not SHA256_RE.fullmatch(expected):
            raise PacketError(
                "artifact_checksum_invalid",
                f"Artifact {artifact_id!r} has a malformed SHA-256 checksum.",
                suggestion="Refresh the artifact record with a full 64-character SHA-256.",
                status=422, details={"artifact_id": artifact_id},
            )
        if digest != expected:
            raise PacketError(
                "artifact_stale",
                f"Artifact {artifact_id!r} does not match its recorded checksum.",
                suggestion="Render the cut again, then build the packet from the fresh render.",
                details={"artifact_id": artifact_id},
            )
    return digest


class ReadyRenderAdapter:
    """Resolve render keys and optional trust-core artifact IDs for a job."""

    def __init__(self, artifact_resolver: Callable[..., dict | None] | None = None):
        self.artifact_resolver = artifact_resolver or resolve_trust_artifact

    def resolve(
        self,
        job: dict,
        job_dir: Path,
        request: PacketRequest,
    ) -> list[PacketSource]:
        sources: list[PacketSource] = []
        used: set[str] = set()
        used_paths: set[Path] = set()
        artifacts = {str(row.get("id")): row for row in _artifact_entries(job)}

        def duplicate(identifier: str) -> None:
            raise PacketError(
                "duplicate_artifact",
                f"Artifact {identifier!r} was requested more than once.",
                suggestion="Send each artifact id or render key only once.",
                details={"artifact_id": identifier},
            )

        def add_source(source: PacketSource) -> None:
            if source.artifact_id in used or source.video_path in used_paths:
                duplicate(source.artifact_id)
            used.add(source.artifact_id)
            used_paths.add(source.video_path)
            sources.append(source)

        for artifact_id in request.artifact_ids:
            if artifact_id in used:
                duplicate(artifact_id)
            summary = artifacts.get(artifact_id)
            try:
                resolved = self.artifact_resolver(job, job_dir, artifact_id)
            except PacketError:
                raise
            except Exception as exc:  # noqa: BLE001 - preserve non-packet failures
                raise PacketError(
                    "artifact_resolver_error",
                    f"Artifact resolver failed for {artifact_id!r}: {exc}",
                    suggestion="Check the artifact store, then retry.",
                    status=500,
                    details={"artifact_id": artifact_id},
                ) from exc
            if not isinstance(resolved, dict) and not isinstance(summary, dict):
                raise PacketError(
                    "artifact_missing",
                    f"Artifact {artifact_id!r} is not available for this job.",
                    suggestion="Refresh the artifact list or pass a ready render key.",
                    status=404, details={"artifact_id": artifact_id},
                )
            entry = dict(summary or {})
            if isinstance(resolved, dict):
                entry.update({
                    key: value for key, value in resolved.items()
                    if value is not None
                })
            entry.setdefault("id", artifact_id)
            add_source(self._from_artifact(job, Path(job_dir), entry))

        renders = job.get("renders") or {}
        for render_key in request.render_keys:
            if render_key in used:
                duplicate(render_key)
            record = renders.get(render_key)
            if not isinstance(record, dict):
                raise PacketError(
                    "artifact_missing",
                    f"Render {render_key!r} is not part of this job.",
                    suggestion="Choose a render key that exists in job.renders.",
                    status=404, details={"render_key": render_key},
                )
            add_source(self._from_render(job, Path(job_dir), render_key, record))

        if not sources:
            raise PacketError(
                "artifacts_missing", "No ready artifact was selected.",
                suggestion="Choose at least one ready render or artifact.",
            )
        return sources

    def _base_source(
        self,
        job: dict,
        job_dir: Path,
        record: dict,
        *,
        artifact_id: str,
        render_key: str | None,
        path_value: object,
        poster_value: object,
        plan: dict | None,
        captions: tuple[str, str] | None = None,
    ) -> PacketSource:
        if record.get("stale") is True or str(record.get("status") or "") == "stale":
            raise PacketError(
                "artifact_stale", f"Artifact {artifact_id!r} is marked stale.",
                suggestion="Re-render the cut before packaging it.",
                details={"artifact_id": artifact_id},
            )
        if record.get("status") not in (None, "ready"):
            raise PacketError(
                "artifact_not_ready",
                f"Artifact {artifact_id!r} is {record.get('status')}, not ready.",
                suggestion="Wait for the render to finish, then retry.",
                details={"artifact_id": artifact_id, "status": record.get("status")},
            )
        video = _safe_job_path(
            job_dir, path_value, subdirs=("renders", "artifacts", "media"),
        )
        if video is None or not video.is_file():
            raise PacketError(
                "artifact_missing",
                f"Artifact {artifact_id!r} has no readable video file.",
                suggestion="Re-render the cut or refresh the artifact store.",
                details={"artifact_id": artifact_id},
            )
        if video.stat().st_size <= 0:
            raise PacketError(
                "artifact_missing", f"Artifact {artifact_id!r} has an empty video file.",
                suggestion="Re-render the cut.", details={"artifact_id": artifact_id},
            )
        if video.suffix.lower() != ".mp4":
            raise PacketError(
                "artifact_not_mp4", f"Artifact {artifact_id!r} is not an MP4.",
                suggestion="Package the final MP4 render.", status=422,
                details={"artifact_id": artifact_id},
            )
        digest = _verify_digest(video, _expected_digest(record), artifact_id)
        _validate_mp4(video, artifact_id)
        poster = _safe_job_path(
            job_dir, poster_value, subdirs=("renders", "artifacts", "media", "covers"),
        )
        if poster is not None and (not poster.is_file() or not _is_valid_jpeg(poster)):
            poster = None
        poster_digest = _sha256_file(poster) if poster is not None else ""
        scenes = (job.get("analysis") or {}).get("scenes") or []
        if captions is None:
            captions = _captions_from_record(job, job_dir, record, plan)
        captions_srt, captions_source = captions
        if captions_source == "missing":
            raise PacketError(
                "captions_unavailable",
                f"Artifact {artifact_id!r} has no caption plan or SRT.",
                suggestion="Attach captions to the artifact, or render with a saved plan.",
                details={"artifact_id": artifact_id},
            )
        _validate_captions(captions_srt, artifact_id)

        def as_int(value):
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        def as_float(value):
            try:
                return round(float(value), 3)
            except (TypeError, ValueError):
                return 0.0

        source = PacketSource(
            artifact_id=artifact_id,
            render_key=render_key,
            video_path=video,
            poster_path=poster,
            sha256=digest,
            size=video.stat().st_size,
            poster_sha256=poster_digest,
            duration=as_float(
                record.get("duration")
                or record.get("total")
                or record.get("target")
            ),
            target=as_int(record.get("target")),
            width=as_int(record.get("width")),
            height=as_int(record.get("height")),
            aspect=str(record.get("aspect") or "") or None,
            quality=str(record.get("quality") or "") or None,
            version=as_int(record.get("version")),
            supersedes=str(record.get("supersedes") or "") or None,
            plan=plan,
            scenes=scenes,
            captions_srt=captions_srt,
            captions_source=captions_source,
            updated=as_float(record.get("updated")) or None,
        )
        spec = record.get("spec") if isinstance(record.get("spec"), dict) else {}
        source.spec = spec
        source.edit = _resolve_edit(job_dir, record, spec)
        source.transcript_id = _transcript_for_source(job_dir, source, spec)
        if source.edit is not None:
            source.audio_plan = audio.plan_from_edit(source.edit.get("audio"))
        elif isinstance(record.get("audio"), dict):
            source.audio_plan = record["audio"]
        return source

    def _from_render(
        self,
        job: dict,
        job_dir: Path,
        render_key: str,
        record: dict,
    ) -> PacketSource:
        requested_artifact = str(record.get("artifact_id") or "")
        artifact_id = requested_artifact or render_key
        merged = dict(record)
        if _artifact_is_safe(requested_artifact):
            try:
                entry = self.artifact_resolver(job, job_dir, requested_artifact)
            except PacketError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise PacketError(
                    "artifact_resolver_error",
                    f"Artifact resolver failed for {requested_artifact!r}: {exc}",
                    suggestion="Check the artifact store, then retry.",
                    status=500, details={"artifact_id": requested_artifact},
                ) from exc
            if isinstance(entry, dict):
                merged.update({
                    key: value for key, value in entry.items()
                    if value is not None
                })
            merged["_artifact_plan_strict"] = True
        plan = _resolve_plan(job, job_dir, merged)
        return self._base_source(
            job,
            job_dir,
            merged,
            artifact_id=artifact_id,
            render_key=render_key,
            path_value=(
                merged.get("path")
                or merged.get("artifact_path")
                or merged.get("video")
                or merged.get("file")
            ),
            poster_value=(
                merged.get("poster")
                or merged.get("poster_path")
                or merged.get("cover")
            ),
            plan=plan,
        )

    def _from_artifact(
        self,
        job: dict,
        job_dir: Path,
        entry: dict,
    ) -> PacketSource:
        artifact_id = str(entry.get("id") or "").strip()
        if not artifact_id:
            raise PacketError(
                "artifact_id_missing", "Artifact record has no id.",
                suggestion="Attach the trust-core artifact ID before packaging.",
            )
        entry["plan_strict"] = True
        plan = _resolve_plan(job, job_dir, entry, prefer=entry.get("plan"))
        replay = dict(entry)
        if entry.get("status") is None:
            replay["status"] = "ready"
        captions = None
        direct = entry.get("captions_srt")
        if not isinstance(direct, str):
            direct = entry.get("srt")
        if isinstance(direct, str):
            captions = (direct, "artifact")
        else:
            captions = _captions_from_record(job, job_dir, replay, plan)
        return self._base_source(
            job,
            job_dir,
            replay,
            artifact_id=artifact_id,
            render_key=str(entry.get("render_key") or entry.get("record_key") or "") or None,
            path_value=(
                entry.get("path")
                or entry.get("artifact_path")
                or entry.get("video")
                or entry.get("video_path")
                or entry.get("mp4")
                or entry.get("file")
            ),
            poster_value=(
                entry.get("poster")
                or entry.get("poster_path")
                or entry.get("cover")
                or entry.get("cover_path")
            ),
            plan=plan,
            captions=captions,
        )


# ------------------------------------------------------------------ manifest


def _default_cover_times(source: PacketSource) -> list[float]:
    duration = max(0.0, float(source.duration or 0.0))
    if duration <= 0.2:
        return [0.0, 0.0]
    return [round(min(0.5, duration * 0.15), 3), round(min(duration * 0.55, duration - 0.05), 3)]


def _packet_id(
    job_id: str,
    request: PacketRequest,
    sources: list[PacketSource],
    cover_times: list[float],
    source_name: str,
    identities: dict[str, dict] | None = None,
) -> str:
    identities = identities or {}
    fingerprints = []
    for source in sorted(sources, key=lambda item: item.artifact_id):
        fingerprints.append({
            "artifact_id": source.artifact_id,
            "render_key": source.render_key,
            "sha256": source.sha256,
            "poster_sha256": source.poster_sha256,
            "captions_sha256": hashlib.sha256(
                source.captions_srt.encode("utf-8")
            ).hexdigest(),
            "duration": source.duration,
            "target": source.target,
            "width": source.width,
            "height": source.height,
            "aspect": source.aspect,
            "quality": source.quality,
            "identity": (
                identities.get(source.artifact_id, {}).get("identity", {}) or {}
            ).get("hash", ""),
        })
    seed = {
        "schema": SCHEMA,
        "job_id": job_id,
        "story_id": request.story_id,
        "source_name": source_name,
        "titles": request.titles,
        "description": request.description,
        "hashtags": request.hashtags,
        "cover_times": cover_times,
        "artifacts": fingerprints,
    }
    if request.pin_comment:
        # Only present when set, so packets built before pin comments keep
        # their ids and still re-download by the same packet_id.
        seed["pin_comment"] = request.pin_comment
    canonical = json.dumps(
        seed, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def _copy_verified(source: Path, destination: Path, expected_sha: str, artifact_id: str) -> tuple[str, int]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    with source.open("rb") as reader, destination.open("wb") as writer:
        for chunk in iter(lambda: reader.read(1024 * 1024), b""):
            digest.update(chunk)
            writer.write(chunk)
            size += len(chunk)
    actual = digest.hexdigest()
    if actual != expected_sha:
        raise PacketError(
            "artifact_stale",
            f"Artifact {artifact_id!r} changed while the packet was being built.",
            suggestion="Re-render the cut and build the packet again.",
            details={"artifact_id": artifact_id},
        )
    if size <= 0:
        raise PacketError(
            "artifact_missing", f"Artifact {artifact_id!r} copied as an empty file.",
            suggestion="Re-render the cut.", details={"artifact_id": artifact_id},
        )
    return actual, size


def _extract_cover(video: Path, seconds: float, destination: Path) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [
                ffmpeg, "-y", "-v", "error", "-ss", f"{max(0.0, seconds):.3f}",
                "-i", str(video), "-frames:v", "1", "-vf", "scale=540:-2",
                "-q:v", "3", str(destination),
            ],
            capture_output=True, timeout=45,
        )
    except (OSError, subprocess.TimeoutExpired):
        destination.unlink(missing_ok=True)
        return False
    if (
        result.returncode != 0
        or not destination.is_file()
        or destination.stat().st_size <= 0
        or not _is_valid_jpeg(destination)
    ):
        destination.unlink(missing_ok=True)
        return False
    return True


def _cover_copy(poster: Path | None, destination: Path) -> str:
    if poster is None or not poster.is_file() or not _is_valid_jpeg(poster):
        return "missing"
    shutil.copyfile(poster, destination)
    return "poster" if _is_valid_jpeg(destination) else "missing"


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    os.replace(temporary, path)


def _zip_packet(directory: Path, destination: Path) -> None:
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    files = sorted(
        path for path in directory.rglob("*")
        if path.is_file() and path != destination and path != temporary
    )
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_STORED, allowZip64=True,
        ) as archive:
            for path in files:
                name = path.relative_to(directory).as_posix()
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_STORED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                with path.open("rb") as reader, archive.open(info, "w") as writer:
                    shutil.copyfileobj(reader, writer)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _manifest_files(manifest: dict) -> list[dict]:
    files = []

    def add(file: object, size: object, digest: object) -> None:
        if not file:
            return
        row = {"file": file, "bytes": size, "sha256": digest}
        if row not in files:
            files.append(row)

    for item in manifest.get("media") or []:
        add(item.get("file"), item.get("bytes"), item.get("sha256"))
        add(
            item.get("captions_file"),
            item.get("captions_bytes"),
            item.get("captions_sha256"),
        )
        for key in ("edit", "audio", "music"):
            ref = item.get(key)
            if isinstance(ref, dict):
                add(ref.get("file"), ref.get("bytes"), ref.get("sha256"))
    for key in ("edit", "audio", "music"):
        ref = manifest.get(key)
        if isinstance(ref, dict):
            add(ref.get("file"), ref.get("bytes"), ref.get("sha256"))
    for item in manifest.get("covers") or []:
        add(item.get("file"), item.get("bytes"), item.get("sha256"))
    for item in manifest.get("layer_assets") or []:
        add(item.get("file"), item.get("bytes"), item.get("sha256"))
    if manifest.get("copy_file"):
        add(manifest.get("copy_file"), manifest.get("copy_bytes"), manifest.get("copy_sha256"))
    return files


def copy_blocks(request: PacketRequest) -> list[dict]:
    """The post copy in paste order: title, description, hashtags, pin."""
    blocks = [
        {"kind": "title", "label": f"Title {index}", "text": title}
        for index, title in enumerate(request.titles, 1)
    ]
    blocks.append({"kind": "description", "label": "Description", "text": request.description})
    blocks.append({"kind": "hashtags", "label": "Hashtags", "text": " ".join(request.hashtags)})
    if request.pin_comment:
        blocks.append({"kind": "pin_comment", "label": "Pin comment", "text": request.pin_comment})
    return blocks


def _copy_text(blocks: list[dict]) -> str:
    return "\n\n".join(f"{block['label']}\n{block['text']}" for block in blocks) + "\n"


def _packet_file(directory: Path, name: object) -> Path | None:
    text = str(name or "")
    if not text or Path(text).is_absolute() or ".." in Path(text).parts:
        return None
    path = (directory / text).resolve()
    root = directory.resolve()
    if path != root and root not in path.parents:
        return None
    return path if path.is_file() else None


def _zip_end_is_clean(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            if size < 22:
                return False
            handle.seek(-22, os.SEEK_END)
            tail = handle.read(22)
    except OSError:
        return False
    if not tail.startswith(b"PK\x05\x06"):
        return False
    comment_length = int.from_bytes(tail[20:22], "little")
    return comment_length == 0


def _zip_is_intact(path: Path, manifest: dict) -> bool:
    if not path.is_file() or path.stat().st_size <= 0:
        return False
    if not _zip_end_is_clean(path):
        return False
    required = {"packet.json"}
    sizes: dict[str, int] = {}
    for item in _manifest_files(manifest):
        name = str(item["file"])
        required.add(name)
        try:
            sizes[name] = int(item["bytes"])
        except (TypeError, ValueError):
            return False
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                return False
            names = set(archive.namelist())
            if names != required:
                return False
            for name, size in sizes.items():
                if archive.getinfo(name).file_size != size:
                    return False
            zipped = json.loads(archive.read("packet.json"))
    except (OSError, KeyError, ValueError, zipfile.BadZipFile, json.JSONDecodeError):
        return False
    return (
        isinstance(zipped, dict)
        and zipped.get("schema") == manifest.get("schema")
        and zipped.get("schema") in SCHEMAS
        and zipped.get("packet_id") == manifest.get("packet_id")
        and zipped == manifest
    )


def _existing_manifest(directory: Path, packet_id: str) -> dict | None:
    path = directory / "packet.json"
    if not path.is_file():
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(manifest, dict):
        return None
    if manifest.get("schema") not in SCHEMAS or manifest.get("packet_id") != packet_id:
        return None
    if manifest.get("schema") == SCHEMA and not isinstance(
        manifest.get("identity"), dict,
    ):
        return None
    media = manifest.get("media")
    covers = manifest.get("covers")
    if not isinstance(media, list) or not media:
        return None
    if not isinstance(covers, list) or len(covers) < COVER_COUNT:
        return None
    if any(
        not isinstance(item, dict) or not item.get("captions_file")
        for item in media
    ):
        return None
    for item in _manifest_files(manifest):
        file = _packet_file(directory, item.get("file"))
        if file is None:
            return None
        try:
            size = int(item.get("bytes"))
        except (TypeError, ValueError):
            return None
        if size < 0 or file.stat().st_size != size:
            return None
        digest = str(item.get("sha256") or "")
        if not SHA256_RE.fullmatch(digest):
            return None
        if _sha256_file(file) != digest:
            return None
    zip_name = str(manifest.get("zip_file") or "")
    if not zip_name:
        return None
    zip_path = _packet_file(directory, zip_name)
    if zip_path is None or not _zip_is_intact(zip_path, manifest):
        return None
    return manifest


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _public_value(value: object) -> object:
    """Drop private runtime keys before a document enters a packet."""
    if isinstance(value, dict):
        return {
            str(key): _public_value(item)
            for key, item in value.items()
            if not str(key).startswith("_")
        }
    if isinstance(value, (list, tuple)):
        return [_public_value(item) for item in value]
    if isinstance(value, Path):
        return value.name
    return value


def _content_hash(path: Path, expected: str = "") -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    wanted = str(expected or "").strip().lower()
    if wanted and not digest.startswith(wanted):
        raise PacketError(
            "layer_asset_hash_mismatch",
            f"Layer asset {path.name!r} no longer matches the Edit.",
            suggestion="Recreate the Edit with the bundled asset, then retry.",
            status=422,
            details={"file": path.name, "expected": wanted, "actual": digest},
        )
    return digest


def _resolve_edit(
    job_dir: Path,
    record: dict,
    spec: dict,
) -> dict | None:
    """Load the exact Edit an artifact rendered, by content hash."""
    wanted = str(spec.get("edit_hash") or record.get("edit_hash") or "").strip().lower()
    if not wanted:
        return None
    edit_id = str(record.get("edit_id") or "").strip()
    if edit_id:
        try:
            edit = edits.load_edit(job_dir, edit_id)
        except edits.EditError:
            edit = None
        if edit is not None and str(edit.get("hash") or "").lower() == wanted:
            return edit
    story_id = str(spec.get("story_id") or record.get("story_id") or "")
    aspect = str(spec.get("aspect") or record.get("aspect") or "9:16")
    try:
        rows = edits.list_edits(job_dir)
    except Exception:  # noqa: BLE001 - packet v2 must fail honest, not guess
        rows = []
    matching = [
        row for row in rows
        if str(row.get("hash") or "").lower() == wanted
        and (not story_id or str((row.get("story_ref") or {}).get("story_id") or "") == story_id)
        and str(row.get("aspect") or "") == aspect
    ]
    if not matching:
        return None
    chosen = max(
        matching,
        key=lambda row: (float(row.get("created") or 0), int(row.get("version") or 0)),
    )
    try:
        return edits.load_edit(job_dir, str(chosen.get("id") or ""))
    except edits.EditError:
        return None


def _transcript_for_source(
    job_dir: Path,
    source: PacketSource,
    spec: dict,
) -> str:
    value = str(spec.get("transcript_id") or source.transcript_id or "")
    if value or source.edit is None:
        return value
    captions_section = source.edit.get("captions") or {}
    track_id = str(captions_section.get("track_id") or "")
    if not track_id:
        return ""
    try:
        track = captions.load_track(job_dir, track_id)
    except Exception:  # noqa: BLE001
        return ""
    return str(getattr(track, "transcript_id", "") or "") if track is not None else ""


def _audio_document(source: PacketSource) -> dict | None:
    section = (source.edit or {}).get("audio")
    if not isinstance(section, dict):
        section = source.audio_plan
    if not isinstance(section, dict) or not section:
        return None
    try:
        plan = (
            audio.plan_from_edit(section)
            if source.edit is not None
            else audio.normalize_audio_plan(section)
        )
    except audio.AudioError as exc:
        raise PacketError(
            "audio_invalid",
            f"The Edit audio plan cannot be adapted: {exc}",
            suggestion="Re-save the Edit audio settings, then rebuild the packet.",
            status=422,
        ) from exc
    if not isinstance(plan, dict):
        return None
    visible = _public_value(plan)
    if isinstance(visible.get("music"), dict):
        music_section = visible["music"]
        for key in ("track", "file"):
            if music_section.get(key):
                music_section[key] = _job_relative(music_section[key])
    if isinstance(visible.get("voice"), dict) and visible["voice"].get("upload"):
        visible["voice"]["upload"] = _job_relative(visible["voice"]["upload"])
    voice = visible.get("voice") if isinstance(visible.get("voice"), dict) else {}
    engine = str(voice.get("engine") or "")
    provenance = {
        "engine": engine,
        "model": str(voice.get("model") or ""),
        "voice_id": str(voice.get("voice") or voice.get("voice_id") or ""),
        "ai_voice": bool(engine) and str(voice.get("source") or "") != "upload",
    }
    payload = {
        "schema": AUDIO_SCHEMA,
        "mode": str(visible.get("mode") or "original"),
        "plan": visible,
        "translate": (
            dict(visible["translate"])
            if isinstance(visible.get("translate"), dict) else None
        ),
        "voice": voice or None,
        "provenance": provenance,
        "transcript_id": str(source.transcript_id or ""),
    }
    payload["hash"] = _canonical_hash(payload)
    return payload


def _job_relative(value: object) -> str:
    text = str(value or "").replace("\\", "/")
    return Path(text).name if "/" in text or "\\" in text else text


def _packet_edit(edit: dict, assets: list[dict], prefix: str = "") -> dict:
    """Copy an Edit for the packet without absolute machine paths.

    The original ``id``/``hash`` stay intact so the packet still names the
    exact Edit version. Path fields point at the packet's own ``assets/``
    copies; the hash identifies the stored Edit before that path rewrite.
    """
    value = json.loads(json.dumps(edit, ensure_ascii=False))
    by_hash = [item for item in assets if item.get("kind") == "lut"]
    lut = (value.get("color") or {}).get("lut")
    if isinstance(lut, dict):
        wanted = str(lut.get("hash") or "").lower()
        match = next(
            (item for item in by_hash if item["sha256"].startswith(wanted)),
            None,
        )
        if match is not None:
            lut["path"] = f"{prefix}assets/{match['kind']}/{match['file_name']}"
    audio_section = value.get("audio")
    if isinstance(audio_section, dict):
        music_section = audio_section.get("music")
        if isinstance(music_section, dict):
            for key in ("track", "file"):
                if music_section.get(key):
                    music_section[key] = _job_relative(music_section[key])
        voice_section = audio_section.get("voice")
        if isinstance(voice_section, dict) and voice_section.get("upload"):
            voice_section["upload"] = _job_relative(voice_section["upload"])
    return value


def _music_document(
    job_dir: Path,
    source: PacketSource,
    audio_document: dict | None,
) -> dict | None:
    plan = (source.audio_plan or {}) if isinstance(source.audio_plan, dict) else {}
    if source.edit is not None:
        try:
            adapted = audio.plan_from_edit(source.edit.get("audio"))
        except audio.AudioError:
            adapted = None
        if isinstance(adapted, dict):
            plan = adapted
    music_plan = plan.get("music") if isinstance(plan.get("music"), dict) else {}
    if not music_plan:
        return None
    wanted = str(
        music_plan.get("locked_hash") or music_plan.get("file_hash") or "",
    ).strip().lower()
    source_kind = str(music_plan.get("source") or "").strip().lower()
    if not (
        wanted
        or music_plan.get("track")
        or music_plan.get("file")
        or source_kind in {"library", "upload", "generated"}
    ):
        return None
    candidate: dict = {}
    job_music = job_dir / "audio" / "music.json"
    if job_music.is_file():
        try:
            value = json.loads(job_music.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            value = None
        if isinstance(value, dict) and (
            not wanted or str(value.get("file_hash") or "").lower() == wanted
        ):
            candidate = dict(value)
    if not candidate and wanted:
        try:
            history = audio.locked_history(job_dir)
        except Exception:  # noqa: BLE001
            history = []
        match = next(
            (
                item for item in reversed(history)
                if str(item.get("file_hash") or "").lower() == wanted
            ),
            None,
        )
        if isinstance(match, dict):
            candidate = dict(match)
    if not candidate:
        candidate = {
            "source": music_plan.get("source"),
            "file": music_plan.get("track") or music_plan.get("file"),
            "file_hash": wanted,
            "licence": music_plan.get("licence"),
            "provider": music_plan.get("provider"),
            "brief": music_plan.get("brief"),
            "bpm": music_plan.get("bpm"),
            "in": music_plan.get("in"),
            "out": music_plan.get("out"),
            "locked": bool(music_plan.get("locked_hash")),
        }
    file_hash = str(candidate.get("file_hash") or wanted or "").strip().lower()
    if not file_hash:
        file_value = str(candidate.get("file") or "")
        if file_value:
            path = Path(file_value)
            if not path.is_absolute():
                path = job_dir / path
            if path.is_file():
                file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    payload = {
        "schema": MUSIC_SCHEMA,
        "source_schema": candidate.get("schema"),
        "source": str(candidate.get("source") or "library"),
        "file": _job_relative(candidate.get("file")),
        "file_hash": file_hash,
        "licence": audio.normalize_licence(candidate.get("licence")),
        "provider": (
            dict(candidate["provider"])
            if isinstance(candidate.get("provider"), dict) else {}
        ),
        "brief": (
            dict(candidate["brief"])
            if isinstance(candidate.get("brief"), dict) else None
        ),
        "bpm": (
            round(float(candidate["bpm"]), 2)
            if candidate.get("bpm") is not None else None
        ),
        "in": round(float(candidate.get("in") or 0.0), 3),
        "out": round(float(candidate.get("out") or 0.0), 3),
        "duration": round(float(candidate.get("duration") or 0.0), 3),
        "locked": bool(candidate.get("locked") or music_plan.get("locked_hash")),
    }
    if audio_document is not None:
        payload["mode"] = audio_document.get("mode")
        payload["translate"] = audio_document.get("translate")
    payload["hash"] = _canonical_hash(payload)
    return payload


def _layer_assets(
    job_dir: Path,
    edit: dict | None,
) -> list[dict]:
    """Resolve every LUT, sticker and caption font an Edit draws with."""
    if not isinstance(edit, dict):
        return []
    found: dict[str, dict] = {}
    root = Path(__file__).resolve().parent

    def add(
        kind: str,
        asset_id: str,
        path: Path | None,
        expected: str = "",
    ) -> None:
        if path is None or not path.is_file():
            raise PacketError(
                "layer_asset_missing",
                f"The Edit's {kind} asset {asset_id or '?'} is not available.",
                suggestion="Re-save the Edit with a bundled asset, then retry.",
                status=422,
                details={"kind": kind, "asset_id": asset_id},
            )
        digest = _content_hash(path, expected)
        key = f"{kind}:{digest}"
        if key in found:
            return
        suffix = path.suffix.lower() or ".bin"
        name = safe_filename(asset_id or path.stem, fallback="asset", limit=40)
        found[key] = {
            "kind": kind,
            "id": asset_id or path.stem,
            "name": path.name,
            "file_name": f"{digest[:12]}-{name}{suffix}",
            "sha256": digest,
            "bytes": path.stat().st_size,
            "path": path,
        }

    color = edit.get("color") or {}
    lut = color.get("lut") if isinstance(color.get("lut"), dict) else None
    if lut:
        path = Path(str(lut.get("path") or ""))
        if not path.is_file():
            bundled = root / "assets" / "luts" / path.name
            preset = str(color.get("preset") or "")
            if not bundled.is_file() and preset and preset != "none":
                bundled = root / "assets" / "luts" / f"{preset}.cube"
            path = bundled
        add("lut", str(color.get("preset") or path.stem), path, str(lut.get("hash") or ""))

    for index, layer in enumerate(edit.get("graphics") or []):
        if not isinstance(layer, dict):
            continue
        asset = layer.get("asset")
        if not isinstance(asset, dict):
            continue
        asset_id = str(asset.get("id") or "")
        try:
            path = fx.sticker_path(asset_id) if asset_id else None
        except fx.FxError:
            path = None
        add("sticker", asset_id or f"graphic-{index}", path, str(asset.get("hash") or ""))

    track_id = str((edit.get("captions") or {}).get("track_id") or "")
    if track_id:
        try:
            track = captions.load_track(job_dir, track_id)
        except Exception:  # noqa: BLE001
            track = None
        font = str(((track.style if track is not None else {}) or {}).get("font") or "")
        if font:
            path = Path(font).expanduser()
            if path.is_file():
                add("font", path.stem, path)

    return sorted(found.values(), key=lambda item: (item["kind"], item["file_name"]))


def _edit_identity(
    source: PacketSource,
    audio_doc: dict | None,
    music_doc: dict | None,
    assets: list[dict],
) -> dict:
    edit = source.edit or {}
    spec = source.spec or {}
    expected_transcript = str(spec.get("transcript_id") or "")
    if (
        expected_transcript
        and source.transcript_id
        and expected_transcript != source.transcript_id
    ):
        raise PacketError(
            "transcript_mismatch",
            "The artifact transcript does not match the Edit's caption track.",
            suggestion="Re-render the story, then build the packet again.",
            status=422,
            details={
                "artifact_transcript": expected_transcript,
                "edit_transcript": source.transcript_id,
            },
        )
    expected_music = str(spec.get("music_hash") or "").lower()
    actual_music = str((music_doc or {}).get("file_hash") or "").lower()
    if expected_music and actual_music and expected_music != actual_music:
        raise PacketError(
            "music_mismatch",
            "The artifact music bed does not match the Edit's locked track.",
            suggestion="Re-render the story with the locked bed, then retry.",
            status=422,
            details={"artifact_music": expected_music, "edit_music": actual_music},
        )
    identity = {
        "schema": IDENTITY_SCHEMA,
        "edit": (
            {
                "id": str(edit.get("id") or ""),
                "hash": str(edit.get("hash") or ""),
                "version": int(edit.get("version") or 0),
                "aspect": str(edit.get("aspect") or ""),
            }
            if edit else None
        ),
        "transcript_id": str(source.transcript_id or ""),
        "audio_hash": str((audio_doc or {}).get("hash") or ""),
        "music_hash": str((music_doc or {}).get("file_hash") or ""),
        "layer_assets": [str(item["sha256"]) for item in assets],
    }
    identity["hash"] = _canonical_hash(identity)
    return identity


def _write_document(stage: Path, relative: str, payload: dict) -> dict:
    path = stage / relative
    _write_json(path, payload)
    data = path.read_bytes()
    return {
        "file": relative,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _frame_cover(
    job: dict,
    job_dir: Path,
    source: PacketSource,
    seconds: float,
) -> bytes | None:
    """One cover frame from the same Edit graph as the frame endpoint."""
    if source.edit is None:
        return None
    clips = (source.plan or {}).get("clips") or []
    meta = job.get("source") or {}
    if not clips or not meta.get("path"):
        return None
    caption_track = None
    captions_section = source.edit.get("captions") or {}
    track_id = str(captions_section.get("track_id") or "")
    if captions_section.get("enabled", True) and track_id:
        try:
            caption_track = captions.load_track(job_dir, track_id)
        except Exception:  # noqa: BLE001 - captions are optional on a cover
            caption_track = None
    aspect = str(source.edit.get("aspect") or source.aspect or "9:16")
    try:
        compiled = compose_render.compile_edit(
            source.edit,
            clips=clips,
            source=meta,
            scenes=(job.get("analysis") or {}).get("scenes") or [],
            caption_track=caption_track,
            size=render._dims(aspect, "final"),
            motion_engine=compose_render.EDIT_MOTION_ENGINE,
            beats=render.edit_beat_grid(job_dir, source.edit, source.audio_plan),
        )
        return render.render_story_frame(
            str(meta["path"]),
            meta,
            job_dir,
            compiled,
            max(0.0, float(seconds)),
            quality="final",
            aspect=aspect,
        )
    except Exception:  # noqa: BLE001 - fall back to the rendered media frame
        return None


def _public(manifest: dict) -> dict:
    value = dict(manifest)
    packet_id = str(manifest.get("packet_id") or "")
    job_id = str(manifest.get("job_id") or "")
    value["zip_url"] = f"/api/jobs/{job_id}/packets/{packet_id}/zip"
    value["packet_url"] = f"/api/jobs/{job_id}/packets/{packet_id}"
    return value


def build_packet(
    job: dict,
    job_dir: Path | str,
    request: PacketRequest | dict,
    *,
    adapter: ReadyRenderAdapter | None = None,
) -> dict:
    """Build or return an existing packet. Raises ``PacketError`` on block."""
    job_dir = Path(job_dir)
    normalized = normalize_request(request)
    job_id = str(job.get("id") or job_dir.name)
    if not job_id or "/" in job_id or ".." in job_id:
        raise PacketError(
            "job_invalid", "Job id is not safe for a packet path.", status=400,
        )
    resolver = adapter or ReadyRenderAdapter()
    sources = resolver.resolve(job, job_dir, normalized)
    sources = sorted(sources, key=lambda item: (item.target or 0, item.artifact_id))
    source_name = str((job.get("source") or {}).get("name") or "")
    if source_name:
        source_name = Path(source_name.replace("\\", "/")).name[:240]
    primary = sources[0]
    cover_times = normalized.cover_times or _default_cover_times(primary)
    cover_times = [
        round(
            max(0.0, min(float(value), max(0.0, primary.duration - 0.05))),
            3,
        )
        for value in cover_times
    ]
    identities: dict[str, dict] = {}
    for source in sources:
        audio_doc = _audio_document(source)
        music_doc = _music_document(job_dir, source, audio_doc)
        assets = _layer_assets(job_dir, source.edit)
        identities[source.artifact_id] = {
            "edit": source.edit,
            "audio": audio_doc,
            "music": music_doc,
            "assets": assets,
            "identity": _edit_identity(source, audio_doc, music_doc, assets),
        }
    packet_id = _packet_id(
        job_id, normalized, sources, cover_times, source_name, identities,
    )
    directory = job_dir / PACKET_ROOT / packet_id

    with _BUILD_LOCK:
        existing = _existing_manifest(directory, packet_id)
        if existing is not None:
            return _public(existing)

        stage = job_dir / PACKET_ROOT / f".{packet_id}.{uuid.uuid4().hex}.tmp"
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        stage.mkdir(parents=True)
        try:
            asset_rows: dict[str, dict] = {}
            for source in sources:
                for asset in identities[source.artifact_id]["assets"]:
                    relative = f"assets/{asset['kind']}/{asset['file_name']}"
                    if relative in asset_rows:
                        continue
                    target = stage / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(asset["path"], target)
                    digest = _content_hash(target, asset["sha256"])
                    asset_rows[relative] = {
                        "kind": asset["kind"],
                        "id": asset["id"],
                        "file": relative,
                        "bytes": target.stat().st_size,
                        "sha256": digest,
                    }
            slug = safe_filename(normalized.story_id or source_name)
            short = packet_id[:8]
            used_names: set[str] = set()
            media_rows: list[dict] = []
            primary_media: Path | None = None
            primary_documents: dict[str, dict | None] = {
                "edit": None, "audio": None, "music": None,
            }
            for index, source in enumerate(sources):
                target = source.target or index + 1
                stem = f"{slug}-{int(target)}s-{short}"
                if stem in used_names:
                    stem = f"{stem}-{index + 1}"
                used_names.add(stem)
                media_name = f"{stem}.mp4"
                captions_name = f"{stem}.srt"
                media_path = stage / "media" / media_name
                captions_path = stage / "captions" / captions_name
                digest, size = _copy_verified(
                    source.video_path, media_path, source.sha256, source.artifact_id,
                )
                if index == 0:
                    primary_media = media_path
                captions_text = source.captions_srt
                if captions_text and not captions_text.endswith("\n"):
                    captions_text += "\n"
                captions_path.parent.mkdir(parents=True, exist_ok=True)
                captions_path.write_text(captions_text, encoding="utf-8")
                captions_bytes = captions_path.stat().st_size
                captions_sha = hashlib.sha256(captions_text.encode("utf-8")).hexdigest()
                identity = identities[source.artifact_id]
                prefix = "" if index == 0 else f"sidecars/{source.artifact_id}/"
                edit_ref = None
                if identity["edit"] is not None:
                    edit_ref = _write_document(
                        stage,
                        prefix + "edit.json",
                        _packet_edit(
                            identity["edit"],
                            identity["assets"],
                            "" if index == 0 else "../../",
                        ),
                    )
                    edit_ref.update({
                        "id": str(identity["edit"].get("id") or ""),
                        "hash": str(identity["edit"].get("hash") or ""),
                        "version": int(identity["edit"].get("version") or 0),
                        "aspect": str(identity["edit"].get("aspect") or ""),
                        "paths": "packet-relative",
                    })
                audio_ref = None
                if identity["audio"] is not None:
                    audio_ref = _write_document(
                        stage, prefix + "audio.json", identity["audio"],
                    )
                    audio_ref.update({
                        "hash": str(identity["audio"].get("hash") or ""),
                        "mode": str(identity["audio"].get("mode") or ""),
                    })
                music_ref = None
                if identity["music"] is not None:
                    music_ref = _write_document(
                        stage, prefix + "music.json", identity["music"],
                    )
                    music_ref.update({
                        "hash": str(identity["music"].get("hash") or ""),
                        "file_hash": str(identity["music"].get("file_hash") or ""),
                        "source": str(identity["music"].get("source") or ""),
                    })
                if index == 0:
                    primary_documents = {
                        "edit": edit_ref,
                        "audio": audio_ref,
                        "music": music_ref,
                    }
                layer_files = sorted({
                    f"assets/{asset['kind']}/{asset['file_name']}"
                    for asset in identity["assets"]
                })
                media_rows.append({
                    "artifact_id": source.artifact_id,
                    "version": source.version,
                    "supersedes": source.supersedes,
                    "render_key": source.render_key,
                    "target": source.target,
                    "quality": source.quality,
                    "aspect": source.aspect,
                    "duration": source.duration,
                    "width": source.width,
                    "height": source.height,
                    "file": f"media/{media_name}",
                    "bytes": size,
                    "sha256": digest,
                    "captions_file": f"captions/{captions_name}",
                    "captions_bytes": captions_bytes,
                    "captions_sha256": captions_sha,
                    "captions_source": source.captions_source,
                    "identity": identity["identity"],
                    "edit": edit_ref,
                    "audio": audio_ref,
                    "music": music_ref,
                    "layer_assets": layer_files,
                })

            cover_rows: list[dict] = []
            for index, seconds in enumerate(cover_times, 1):
                cover_name = f"{slug}-cover-{index}-{short}.jpg"
                cover_path = stage / "covers" / cover_name
                cover_path.parent.mkdir(parents=True, exist_ok=True)
                frame_payload = _frame_cover(job, job_dir, primary, seconds)
                if frame_payload and _is_valid_jpeg_bytes(frame_payload):
                    cover_path.write_bytes(frame_payload)
                    source_kind = "frame"
                else:
                    source_kind = "ffmpeg" if (
                        primary_media is not None
                        and _extract_cover(primary_media, seconds, cover_path)
                    ) else _cover_copy(primary.poster_path, cover_path)
                if source_kind == "missing":
                    raise PacketError(
                        "cover_unavailable",
                        "Could not extract a cover and the render has no poster.",
                        suggestion="Keep the render poster, or install ffmpeg and retry.",
                        status=422,
                        details={"artifact_id": primary.artifact_id, "time": seconds},
                    )
                if not _is_valid_jpeg(cover_path):
                    raise PacketError(
                        "cover_invalid",
                        "The generated cover is not a valid JPEG.",
                        suggestion="Install ffmpeg or keep a valid render poster.",
                        status=422,
                        details={"artifact_id": primary.artifact_id, "time": seconds},
                    )
                cover_rows.append({
                    "index": index,
                    "file": f"covers/{cover_name}",
                    "time": seconds,
                    "source": source_kind,
                    "bytes": cover_path.stat().st_size,
                    "sha256": _sha256_file(cover_path),
                })

            blocks = copy_blocks(normalized)
            copy_path = stage / COPY_FILE
            copy_path.write_text(_copy_text(blocks), encoding="utf-8")
            zip_name = f"{slug}-packet-{short}.zip"
            primary_identity = identities[primary.artifact_id]["identity"]
            asset_refs = sorted(asset_rows.values(), key=lambda row: row["file"])
            document_refs: dict[str, dict] = {}
            for ref in primary_documents.values():
                if isinstance(ref, dict) and ref.get("file"):
                    document_refs[str(ref["file"])] = ref
            for item in media_rows:
                for ref in (item.get("edit"), item.get("audio"), item.get("music")):
                    if isinstance(ref, dict) and ref.get("file"):
                        document_refs[str(ref["file"])] = ref
            manifest = {
                "schema": SCHEMA,
                "packet_id": packet_id,
                "story_id": normalized.story_id,
                "job_id": job_id,
                "created": round(time.time(), 3),
                "source": {
                    "name": source_name,
                    "duration": round(float((job.get("source") or {}).get("duration") or 0.0), 3),
                },
                "titles": normalized.titles,
                "description": normalized.description,
                "hashtags": normalized.hashtags,
                "pin_comment": normalized.pin_comment,
                "copy_blocks": blocks,
                "copy_file": COPY_FILE,
                "copy_bytes": copy_path.stat().st_size,
                "copy_sha256": _sha256_file(copy_path),
                "identity": primary_identity,
                "edit": primary_documents["edit"],
                "audio": primary_documents["audio"],
                "music": primary_documents["music"],
                "layer_assets": asset_refs,
                "media": media_rows,
                "covers": cover_rows,
                "zip_file": zip_name,
                "total_bytes": sum(row["bytes"] for row in media_rows)
                + sum(row["captions_bytes"] for row in media_rows)
                + sum(row["bytes"] for row in cover_rows)
                + sum(row["bytes"] for row in asset_refs)
                + sum(int(ref.get("bytes") or 0) for ref in document_refs.values())
                + copy_path.stat().st_size,
            }
            _write_json(stage / "packet.json", manifest)
            zip_path = stage / zip_name
            _zip_packet(stage, zip_path)

            if directory.exists():
                shutil.rmtree(directory, ignore_errors=True)
            os.replace(stage, directory)
        finally:
            shutil.rmtree(stage, ignore_errors=True)
        final = _existing_manifest(directory, packet_id)
        if final is None:
            raise PacketError(
                "packet_write_failed",
                "The packet was written but failed integrity verification.",
                suggestion="Check disk health, then build the packet again.",
                status=500,
            )
        return _public(final)


def load_packet(job_dir: Path | str, packet_id: str) -> dict:
    packet_id = str(packet_id or "").strip()
    if not PACKET_ID_RE.fullmatch(packet_id):
        raise PacketError(
            "packet_not_found", "Packet id is not valid.", status=404,
        )
    directory = Path(job_dir) / PACKET_ROOT / packet_id
    manifest = _existing_manifest(directory, packet_id)
    if manifest is None:
        raise PacketError(
            "packet_not_found", "Packet not found.", status=404,
            suggestion="Build the packet again from its ready render.",
        )
    return _public(manifest)


def list_packets(job_dir: Path | str) -> list[dict]:
    """Every intact packet for a job, newest first. Survives relaunch."""
    root = Path(job_dir) / PACKET_ROOT
    if not root.is_dir():
        return []
    rows: list[dict] = []
    for directory in root.iterdir():
        if not directory.is_dir() or not PACKET_ID_RE.fullmatch(directory.name):
            continue
        manifest = _existing_manifest(directory, directory.name)
        if manifest is None:
            continue
        media = manifest.get("media") or []
        public = _public(manifest)
        rows.append({
            "packet_id": manifest["packet_id"],
            "story_id": manifest.get("story_id"),
            "created": manifest.get("created"),
            "title": (manifest.get("titles") or [""])[0],
            "aspects": sorted({str(item.get("aspect") or "") for item in media}),
            "versions": [item.get("version") for item in media],
            "edits": [
                {
                    "artifact_id": item.get("artifact_id"),
                    "edit_id": (item.get("edit") or {}).get("id"),
                    "edit_hash": (item.get("edit") or {}).get("hash"),
                    "edit_version": (item.get("edit") or {}).get("version"),
                }
                for item in media
                if isinstance(item.get("edit"), dict)
            ],
            "identity": (manifest.get("identity") or {}).get("hash"),
            "zip_file": manifest.get("zip_file"),
            "zip_url": public["zip_url"],
            "packet_url": public["packet_url"],
        })
    rows.sort(key=lambda item: float(item.get("created") or 0), reverse=True)
    return rows


def packet_zip_path(job_dir: Path | str, packet_id: str) -> Path:
    manifest = load_packet(job_dir, packet_id)
    zip_file = str(manifest.get("zip_file") or "")
    if not zip_file:
        raise PacketError("packet_not_found", "Packet has no ZIP.", status=404)
    root = (Path(job_dir) / PACKET_ROOT / str(packet_id)).resolve()
    path = (root / zip_file).resolve()
    if root not in path.parents or not path.is_file():
        raise PacketError("packet_not_found", "Packet ZIP not found.", status=404)
    return path


# ------------------------------------------------------------------ API


def _app():
    import app

    return app


class ArtifactPacketBody(BaseModel):
    """Publish copy for one artifact. The artifact id is in the path."""

    story_id: str = Field(default="", max_length=160)
    artifact_ids: list[str] = Field(default_factory=list)
    titles: list[str] = Field(default_factory=list)
    description: str = ""
    hashtags: list[str] = Field(default_factory=list)
    cover_times: list[float] | None = None
    pin_comment: str = ""


router = APIRouter(tags=["packet"])


@router.post("/api/jobs/{job_id}/artifacts/{artifact_id}/packet")
def build_artifact_packet(
    job_id: str,
    artifact_id: str,
    body: ArtifactPacketBody | None = None,
) -> dict:
    """Build a packet for one ready artifact. T4 Finish uses this route."""
    body = body or ArtifactPacketBody()
    if not ARTIFACT_ID_RE.fullmatch(str(artifact_id or "")):
        raise HTTPException(404, "Artifact not found.")
    if body.artifact_ids and artifact_id not in body.artifact_ids:
        raise HTTPException(
            400, "The body artifact ids must contain the path artifact id.",
        )
    application = _app()
    job = application.load_job(job_id)
    story_id = body.story_id
    if not str(story_id or "").strip():
        # The path names one artifact, so its manifest knows the story.
        module = _trust_artifacts()
        manifest = (
            module.load_manifest(application._job_dir(job_id), artifact_id)
            if module is not None else None
        ) or {}
        story_id = str(
            manifest.get("story_id") or (manifest.get("spec") or {}).get("story_id") or ""
        )
    request = PacketRequest(
        story_id=story_id,
        titles=body.titles,
        description=body.description,
        hashtags=body.hashtags,
        artifact_ids=[artifact_id],
        cover_times=body.cover_times,
        pin_comment=body.pin_comment,
    )
    try:
        manifest = build_packet(job, application._job_dir(job_id), request)
    except PacketError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.as_detail()) from exc
    try:
        application._record_packet_refs(job_id, manifest)
    except Exception:  # noqa: BLE001 - the packet is already on disk
        pass
    return manifest
