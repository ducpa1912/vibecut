"""Build immutable Publish Packets from ready renders or artifacts.

A packet is a self-contained hand-off for one story:

    data/jobs/<job_id>/packets/<packet_id>/
      packet.json
      media/<ascii-name>.mp4
      captions/<ascii-name>.srt
      covers/<ascii-name>-cover-1.jpg
      covers/<ascii-name>-cover-2.jpg
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

import exports
import history_store

SCHEMA = "vibecut.publish_packet/1"
PACKET_ROOT = "packets"
DESCRIPTION_LIMIT = 125
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
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*"
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})"
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

    return PacketRequest(
        story_id=story_id,
        titles=titles,
        description=description,
        hashtags=hashtags,
        artifact_ids=artifact_ids,
        render_keys=render_keys,
        cover_times=cover_times,
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
        "plan": plan,
        "plan_strict": True,
        "target": target,
        "quality": quality,
        "aspect": aspect,
        "duration": duration,
        "width": render_info.get("width") or record.get("width"),
        "height": render_info.get("height") or record.get("height"),
        "updated": (manifest or {}).get("updated") or record.get("updated"),
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
        if not _is_valid_mp4(video):
            raise PacketError(
                "artifact_invalid_media",
                f"Artifact {artifact_id!r} is not a valid MP4 container.",
                suggestion="Re-render the cut and package the final MP4.",
                status=422, details={"artifact_id": artifact_id},
            )
        digest = _verify_digest(video, _expected_digest(record), artifact_id)
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

        return PacketSource(
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
            plan=plan,
            scenes=scenes,
            captions_srt=captions_srt,
            captions_source=captions_source,
            updated=as_float(record.get("updated")) or None,
        )

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
) -> str:
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
    for item in manifest.get("media") or []:
        files.append({
            "file": item.get("file"),
            "bytes": item.get("bytes"),
            "sha256": item.get("sha256"),
        })
        files.append({
            "file": item.get("captions_file"),
            "bytes": item.get("captions_bytes"),
            "sha256": item.get("captions_sha256"),
        })
    for item in manifest.get("covers") or []:
        files.append({
            "file": item.get("file"),
            "bytes": item.get("bytes"),
            "sha256": item.get("sha256"),
        })
    return [item for item in files if item.get("file")]


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
        and zipped.get("schema") == SCHEMA
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
    if manifest.get("schema") != SCHEMA or manifest.get("packet_id") != packet_id:
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
    packet_id = _packet_id(job_id, normalized, sources, cover_times, source_name)
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
            slug = safe_filename(normalized.story_id or source_name)
            short = packet_id[:8]
            used_names: set[str] = set()
            media_rows: list[dict] = []
            primary_media: Path | None = None
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
                media_rows.append({
                    "artifact_id": source.artifact_id,
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
                })

            cover_rows: list[dict] = []
            for index, seconds in enumerate(cover_times, 1):
                cover_name = f"{slug}-cover-{index}-{short}.jpg"
                cover_path = stage / "covers" / cover_name
                cover_path.parent.mkdir(parents=True, exist_ok=True)
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

            zip_name = f"{slug}-packet-{short}.zip"
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
                "media": media_rows,
                "covers": cover_rows,
                "zip_file": zip_name,
                "total_bytes": sum(row["bytes"] for row in media_rows)
                + sum(row["captions_bytes"] for row in media_rows)
                + sum(row["bytes"] for row in cover_rows),
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
