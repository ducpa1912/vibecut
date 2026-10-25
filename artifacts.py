"""Immutable render artifacts.

An artifact is the canonical identity of one finished render: the source
fingerprint, ordered clips, hook choice, caption inputs, audio mix, quality,
aspect, and the encoder that actually ran. The id is a hash of that payload,
so any change to the inputs yields a different artifact instead of silently
retargeting an existing review link.

Layout::

    data/jobs/<job_id>/artifacts/
        index.json
        <artifact_id>/
            manifest.json
            reel.mp4
            poster.jpg
            captions.srt
            captions.vtt

All JSON writes are atomic and every artifact id is validated before it is
used as a path component.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import render
import captions

SCHEMA_VERSION = 1
RENDER_VERSION = "v0.14-artifact-1"
STORY_DEFAULT = ""

MEDIA_NAMES = ("reel.mp4", "poster.jpg", "captions.srt", "captions.vtt")
MEDIA_FILES = {
    "reel": "reel.mp4",
    "poster": "poster.jpg",
    "captions_srt": "captions.srt",
    "captions_vtt": "captions.vtt",
}
ARTIFACT_RE = re.compile(r"^art_[0-9a-f]{24}$")
LOCK = threading.RLock()


class ArtifactError(ValueError):
    """Raised when an artifact id or manifest is not safe to use."""


# ---------------------------------------------------------------- canonical


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clip(value: dict, fallback_scene: int = 0) -> dict:
    start = round(_number(value.get("start")), 3)
    duration = _number(value.get("dur", value.get("duration")))
    end = round(_number(value.get("end"), start + duration), 3)
    if not duration and end > start:
        duration = end - start
    return {
        "scene": _optional_int(value.get("scene")) if value.get("scene") is not None else fallback_scene,
        "start": start,
        "end": end,
        "dur": round(duration, 3),
        "role": str(value.get("role") or "beat"),
    }


def normalize_clips(clips: Iterable[dict] | None) -> list[dict]:
    result = []
    for index, clip in enumerate(clips or []):
        if isinstance(clip, dict):
            result.append(_clip(clip, index))
    return result


def cue_hashes(cues: Iterable[dict] | None) -> tuple[str, str]:
    ranges: list[list[float]] = []
    texts: list[str] = []
    for cue in cues or []:
        if not isinstance(cue, dict):
            continue
        ranges.append([
            round(_number(cue.get("start")), 3),
            round(_number(cue.get("end")), 3),
        ])
        texts.append(str(cue.get("text") or ""))
    return _sha(ranges)[:16], _sha(texts)[:16]


def style_hash(preset: str | None, margin: float) -> str:
    return _sha({
        "style_version": 1,
        "preset": str(preset or ""),
        "margin": round(_number(margin, 0.075), 4),
    })[:16]


def resolve_encoder(requested: str | None = None) -> str:
    """Return the encoder that will actually run. Never ``auto``."""
    try:
        value = render._choose_encoder(requested)
    except Exception:  # noqa: BLE001 - identity must not depend on ffmpeg presence
        raw = (requested or os.environ.get("VIBECUT_ENCODER") or "auto").lower()
        if raw in ("libx264", "x264"):
            value = "libx264"
        elif raw in ("videotoolbox", "vt"):
            value = "videotoolbox"
        elif raw == "auto":
            value = "videotoolbox" if sys.platform == "darwin" else "libx264"
        else:
            value = "libx264"
    return "videotoolbox" if value == "videotoolbox" else "libx264"


def source_fingerprint(job: dict | None) -> str:
    source = (job or {}).get("source") or {}
    value = str(source.get("fingerprint") or "").strip()
    if value:
        return value
    payload = {
        "name": str(source.get("name") or ""),
        "size": int(source.get("size") or 0),
        "duration": round(_number(source.get("duration")), 3),
        "width": int(source.get("width") or 0),
        "height": int(source.get("height") or 0),
        "fps": round(_number(source.get("fps")), 3),
        "path": str(source.get("path") or ""),
    }
    return _sha(payload)[:32]


def cues_from_plan(job: dict | None, plan: dict | None) -> list[dict]:
    """Canonical chunked cues shared by burn-in, exports, and artifacts."""
    analysis = (job or {}).get("analysis") or {}
    return captions.reel_cues(
        plan or {},
        (plan or {}).get("clips") or [],
        analysis.get("scenes") or [],
    )


@dataclass(frozen=True)
class ArtifactSpec:
    """The complete, canonical input identity of one render."""

    clips: list[dict]
    target: int = 30
    story_id: str = STORY_DEFAULT
    order: str = "source"
    hook_scene: int | None = None
    hook_override: bool = False
    caption: dict = field(default_factory=lambda: {
        "enabled": False,
        "style_hash": "",
        "cue_hash": "",
        "text_hash": "",
        "cue_count": 0,
        "margin": 0.075,
    })
    audio_sig: str = ""
    quality: str = "final"
    aspect: str = "9:16"
    resolved_encoder: str = "libx264"
    source_fingerprint: str = ""
    generation: int = 0
    schema_version: int = SCHEMA_VERSION
    render_version: str = RENDER_VERSION

    def __post_init__(self) -> None:
        # ``auto`` is never a valid artifact identity, even when a caller
        # constructs the dataclass directly.
        if self.resolved_encoder not in ("videotoolbox", "libx264"):
            object.__setattr__(
                self, "resolved_encoder", resolve_encoder(self.resolved_encoder),
            )

    def payload(self) -> dict:
        return {
            "schema_version": int(self.schema_version),
            "render_version": str(self.render_version),
            "source_fingerprint": str(self.source_fingerprint),
            "clips": normalize_clips(self.clips),
            "order": str(self.order or "source"),
            "hook_scene": _optional_int(self.hook_scene),
            "hook_override": bool(self.hook_override),
            "caption": _caption_payload(self.caption),
            "audio_sig": str(self.audio_sig or ""),
            "quality": str(self.quality or "final"),
            "aspect": str(self.aspect or "9:16"),
            "resolved_encoder": resolve_encoder(self.resolved_encoder),
            "story_id": str(self.story_id or ""),
            "target": int(self.target),
            "generation": int(self.generation or 0),
        }

    @classmethod
    def from_payload(cls, payload: dict | None) -> "ArtifactSpec":
        data = payload or {}
        if isinstance(data.get("spec"), dict):
            data = data["spec"]
        return cls(
            clips=normalize_clips(data.get("clips")),
            target=_optional_int(data.get("target")) or 0,
            story_id=str(data.get("story_id") or ""),
            order=str(data.get("order") or "source"),
            hook_scene=_optional_int(data.get("hook_scene")),
            hook_override=bool(data.get("hook_override")),
            caption=_caption_payload(data.get("caption")),
            audio_sig=str(data.get("audio_sig") or ""),
            quality=str(data.get("quality") or "final"),
            aspect=str(data.get("aspect") or "9:16"),
            resolved_encoder=resolve_encoder(str(data.get("resolved_encoder") or "libx264")),
            source_fingerprint=str(data.get("source_fingerprint") or ""),
            generation=_optional_int(data.get("generation")) or 0,
            schema_version=int(data.get("schema_version") or SCHEMA_VERSION),
            render_version=str(data.get("render_version") or RENDER_VERSION),
        )


def _caption_payload(value: dict | None) -> dict:
    data = value if isinstance(value, dict) else {}
    return {
        "enabled": bool(data.get("enabled")),
        "style_hash": str(data.get("style_hash") or ""),
        "cue_hash": str(data.get("cue_hash") or ""),
        "text_hash": str(data.get("text_hash") or ""),
        "cue_count": max(0, _optional_int(data.get("cue_count")) or 0),
        "margin": round(_number(data.get("margin"), 0.075), 4),
    }


def build_spec(
    job: dict,
    plan: dict,
    *,
    quality: str = "final",
    aspect: str = "9:16",
    encoder: str | None = None,
    captions: bool = False,
    audio_sig: str = "",
    preset: str | None = None,
    caption_margin: float = 0.075,
    story_id: str | None = None,
    cues: Iterable[dict] | None = None,
    generation: int = 0,
) -> ArtifactSpec:
    plan = plan or {}
    if cues is None:
        cues = cues_from_plan(job, plan)
    cue_list = list(cues or [])
    cue_hash, text_hash = cue_hashes(cue_list)
    source = (job or {}).get("source") or {}
    return ArtifactSpec(
        clips=normalize_clips(plan.get("clips")),
        target=int(plan.get("target") or 0),
        story_id=str(story_id or (job or {}).get("story_id") or (job or {}).get("id") or ""),
        order=str(plan.get("order") or "source"),
        hook_scene=_optional_int(plan.get("hook_scene")),
        hook_override=not bool(plan.get("auto", True)),
        caption={
            "enabled": bool(captions),
            "style_hash": style_hash(preset, caption_margin),
            "cue_hash": cue_hash,
            "text_hash": text_hash,
            "cue_count": len(cue_list),
            "margin": round(_number(caption_margin, 0.075), 4),
        },
        audio_sig=str(audio_sig or ""),
        quality=str(quality or "final"),
        aspect=str(aspect if aspect in render.ASPECTS else "9:16"),
        resolved_encoder=resolve_encoder(encoder),
        source_fingerprint=source_fingerprint(job) or str(source.get("fingerprint") or ""),
        generation=max(0, int(generation or 0)),
        schema_version=SCHEMA_VERSION,
        render_version=RENDER_VERSION,
    )


def artifact_id(spec: ArtifactSpec | dict) -> str:
    """Stable ``art_`` id derived from the canonical payload."""
    if isinstance(spec, ArtifactSpec):
        payload = spec.payload()
    elif isinstance(spec, dict):
        payload = spec.get("spec") if isinstance(spec.get("spec"), dict) else spec
    else:
        raise ArtifactError("Artifact spec must be an ArtifactSpec or dict.")
    return "art_" + _sha(payload)[:24]


compute_id = artifact_id


def _base_payload(spec: ArtifactSpec) -> dict:
    payload = spec.payload()
    payload.pop("generation", None)
    return payload


def latest_generation(job_dir: str | Path, spec: ArtifactSpec) -> int:
    """Highest stored generation for the same canonical inputs."""
    base = _base_payload(spec)
    latest = -1
    for manifest in list_manifests(job_dir):
        candidate = manifest.get("spec")
        if not isinstance(candidate, dict):
            continue
        data = dict(candidate)
        try:
            generation = int(data.pop("generation", 0) or 0)
        except (TypeError, ValueError):
            generation = 0
        if data == base:
            latest = max(latest, generation)
    return latest


def resolve_generation(
    job_dir: str | Path,
    spec: ArtifactSpec,
    *,
    force: bool = False,
) -> int:
    """Generation for this render: latest for reuse, latest + 1 for force."""
    latest = latest_generation(job_dir, spec)
    if force:
        return max(0, latest) + 1
    return max(0, latest)


def is_safe_artifact_id(value: str | None) -> bool:
    return bool(value and ARTIFACT_RE.fullmatch(str(value)))


def validate_artifact_id(value: str | None) -> str:
    text = str(value or "")
    if not is_safe_artifact_id(text):
        raise ArtifactError("Invalid artifact id.")
    return text


# ---------------------------------------------------------------- files


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            tmp.chmod(0o600)
        except OSError:
            pass
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def atomic_write_json(path: Path, value: Any) -> None:
    _atomic_write(path, json.dumps(value, ensure_ascii=False, indent=1))


def _link_atomic(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        try:
            os.link(source, tmp)
        except OSError:
            shutil.copy2(source, tmp)
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)


def artifacts_dir(job_dir: str | Path) -> Path:
    return Path(job_dir) / "artifacts"


def artifact_dir(job_dir: str | Path, artifact: str) -> Path:
    return artifacts_dir(job_dir) / validate_artifact_id(artifact)


def manifest_path(job_dir: str | Path, artifact: str) -> Path:
    return artifact_dir(job_dir, artifact) / "manifest.json"


def index_path(job_dir: str | Path) -> Path:
    return artifacts_dir(job_dir) / "index.json"


def media_path(job_dir: str | Path, artifact: str, name: str) -> Path:
    if name not in MEDIA_NAMES:
        raise ArtifactError("Unknown artifact media name.")
    return artifact_dir(job_dir, artifact) / name


def has_media(job_dir: str | Path, artifact: str, name: str = "reel.mp4") -> bool:
    try:
        return media_path(job_dir, artifact, name).is_file()
    except (OSError, ArtifactError):
        return False


# ---------------------------------------------------------------- manifest


def make_manifest(
    job_id: str,
    spec: ArtifactSpec,
    *,
    status: str = "queued",
    record_key: str | None = None,
    title: str | None = None,
    created: float | None = None,
) -> dict:
    now = round(time.time(), 3)
    created = round(float(created if created is not None else now), 3)
    payload = spec.payload()
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": artifact_id(spec),
        "job_id": str(job_id),
        "spec": payload,
        "status": str(status),
        "pinned": False,
        "pinned_at": None,
        "created": created,
        "updated": now,
        "record_key": record_key,
        "title": title,
        "target": payload.get("target"),
        "quality": payload.get("quality"),
        "aspect": payload.get("aspect"),
        "hook_scene": payload.get("hook_scene"),
        "hook_override": bool(payload.get("hook_override")),
        "captions": bool((payload.get("caption") or {}).get("enabled")),
        "caption_count": int((payload.get("caption") or {}).get("cue_count") or 0),
        "audio_sig": payload.get("audio_sig") or "",
        "story_id": payload.get("story_id") or "",
        "source_fingerprint": payload.get("source_fingerprint") or "",
        "resolved_encoder": payload.get("resolved_encoder"),
        "generation": payload.get("generation") or 0,
        "render": None,
        "media": dict(MEDIA_FILES),
        "error": None,
    }


def manifest_summary(manifest: dict) -> dict:
    spec = manifest.get("spec") or {}
    caption = spec.get("caption") or {}
    return {
        "artifact_id": manifest.get("artifact_id"),
        "job_id": manifest.get("job_id"),
        "status": manifest.get("status"),
        "pinned": bool(manifest.get("pinned")),
        "created": manifest.get("created"),
        "updated": manifest.get("updated"),
        "record_key": manifest.get("record_key"),
        "story_id": spec.get("story_id"),
        "target": spec.get("target"),
        "quality": spec.get("quality"),
        "aspect": spec.get("aspect"),
        "hook_scene": spec.get("hook_scene"),
        "hook_override": bool(spec.get("hook_override")),
        "captions": bool(caption.get("enabled")),
        "caption_count": int(caption.get("cue_count") or 0),
        "cue_count": int(caption.get("cue_count") or 0),
        "audio_sig": spec.get("audio_sig") or "",
        "resolved_encoder": spec.get("resolved_encoder"),
        "generation": int(spec.get("generation") or 0),
        "reel": (manifest.get("media") or {}).get("reel"),
    }


def save_manifest(job_dir: str | Path, manifest: dict) -> dict:
    artifact = validate_artifact_id(manifest.get("artifact_id"))
    payload = manifest.get("spec") or {}
    expected = artifact_id(payload)
    if expected != artifact:
        raise ArtifactError("Manifest id does not match its canonical payload.")
    manifest = dict(manifest)
    manifest["updated"] = round(time.time(), 3)
    manifest.setdefault("schema_version", SCHEMA_VERSION)
    with LOCK:
        atomic_write_json(manifest_path(job_dir, artifact), manifest)
        refresh_index(job_dir)
    return manifest


def load_manifest(job_dir: str | Path, artifact: str) -> dict | None:
    if not is_safe_artifact_id(artifact):
        return None
    path = manifest_path(job_dir, artifact)
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    spec = value.get("spec")
    if not isinstance(spec, dict) or artifact_id(spec) != artifact:
        return None
    if spec.get("resolved_encoder") not in ("videotoolbox", "libx264"):
        return None
    declared = str(value.get("artifact_id") or "")
    if declared and declared != artifact:
        return None
    value["artifact_id"] = artifact
    value["spec"] = spec
    value.setdefault("media", dict(MEDIA_FILES))
    return value


def list_manifests(job_dir: str | Path) -> list[dict]:
    directory = artifacts_dir(job_dir)
    if not directory.is_dir():
        return []
    result: list[dict] = []
    for child in directory.iterdir():
        if not child.is_dir() or not is_safe_artifact_id(child.name):
            continue
        manifest = load_manifest(job_dir, child.name)
        if manifest is not None:
            result.append(manifest)
    result.sort(key=lambda item: float(item.get("created") or 0), reverse=True)
    return result


def refresh_index(job_dir: str | Path) -> dict:
    """Rebuild and atomically write the per-job artifact index."""
    with LOCK:
        entries = {
            manifest["artifact_id"]: manifest_summary(manifest)
            for manifest in list_manifests(job_dir)
            if manifest.get("artifact_id")
        }
        value = {
            "schema_version": SCHEMA_VERSION,
            "updated": round(time.time(), 3),
            "artifacts": entries,
            "artifact_ids": sorted(entries),
        }
        if entries or artifacts_dir(job_dir).is_dir():
            atomic_write_json(index_path(job_dir), value)
        return value


write_index = refresh_index


def load_index(job_dir: str | Path) -> dict:
    path = index_path(job_dir)
    if path.is_file():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            value = None
        if isinstance(value, dict) and isinstance(value.get("artifacts"), dict):
            return value
    return refresh_index(job_dir)


def delete_artifact(job_dir: str | Path, artifact: str) -> bool:
    if not is_safe_artifact_id(artifact):
        return False
    path = artifact_dir(job_dir, artifact)
    if not path.is_dir():
        return False
    manifest = load_manifest(job_dir, artifact)
    if manifest is not None and manifest.get("pinned"):
        return False
    with LOCK:
        shutil.rmtree(path, ignore_errors=True)
        refresh_index(job_dir)
    return True


def pin_artifact(job_dir: str | Path, artifact: str, pinned: bool = True) -> dict | None:
    manifest = load_manifest(job_dir, artifact)
    if manifest is None:
        return None
    manifest["pinned"] = bool(pinned)
    manifest["pinned_at"] = round(time.time(), 3) if pinned else None
    return save_manifest(job_dir, manifest)


def mark_status(
    job_dir: str | Path,
    artifact: str,
    status: str,
    *,
    error: str | None = None,
) -> dict | None:
    manifest = load_manifest(job_dir, artifact)
    if manifest is None:
        return None
    # A failed forced re-render must not downgrade a previously ready copy.
    if manifest.get("status") == "ready" and status != "ready":
        return manifest
    manifest["status"] = str(status)
    manifest["error"] = error
    return save_manifest(job_dir, manifest)


# ---------------------------------------------------------------- media


def store_media(
    job_dir: str | Path,
    artifact: str,
    reel: str | Path | None,
    poster: str | Path | None = None,
) -> dict:
    directory = artifact_dir(job_dir, artifact)
    directory.mkdir(parents=True, exist_ok=True)
    if reel:
        source = Path(reel)
        target = directory / MEDIA_FILES["reel"]
        if source.is_file() and source.resolve() != target.resolve():
            _link_atomic(source, target)
    if poster:
        source = Path(poster)
        target = directory / MEDIA_FILES["poster"]
        if source.is_file() and source.resolve() != target.resolve():
            _link_atomic(source, target)
    return dict(MEDIA_FILES)


def write_captions(
    job_dir: str | Path,
    artifact: str,
    srt: str,
    vtt: str,
) -> None:
    directory = artifact_dir(job_dir, artifact)
    directory.mkdir(parents=True, exist_ok=True)
    _atomic_write(directory / MEDIA_FILES["captions_srt"], str(srt or ""))
    _atomic_write(directory / MEDIA_FILES["captions_vtt"], str(vtt or ""))


def complete_artifact(
    job_dir: str | Path,
    artifact: str,
    *,
    reel: str | Path | None = None,
    poster: str | Path | None = None,
    srt: str = "",
    vtt: str = "",
    render_info: dict | None = None,
) -> dict | None:
    manifest = load_manifest(job_dir, artifact)
    if manifest is None:
        return None
    store_media(job_dir, artifact, reel, poster)
    write_captions(job_dir, artifact, srt, vtt)
    manifest["status"] = "ready"
    manifest["error"] = None
    manifest["completed"] = round(time.time(), 3)
    if render_info is not None:
        manifest["render"] = render_info
    return save_manifest(job_dir, manifest)


# ---------------------------------------------------------------- job helpers


def summary_dict(manifest: dict) -> dict:
    return manifest_summary(manifest)


def ensure_job_schema(job: dict, job_dir: str | Path | None = None) -> dict:
    """Add artifact/schema fields to old jobs without breaking their shape."""
    job.setdefault("schema_version", SCHEMA_VERSION)
    job.setdefault("render_version", RENDER_VERSION)
    if not job.get("story_id"):
        job["story_id"] = str(job.get("id") or "")
    table = job.get("artifacts")
    if not isinstance(table, dict):
        table = {}
    if job_dir is not None and artifacts_dir(job_dir).is_dir():
        index = load_index(job_dir)
        disk = index.get("artifacts") if isinstance(index.get("artifacts"), dict) else {}
        for artifact, summary in disk.items():
            if isinstance(summary, dict):
                table[artifact] = {**table.get(artifact, {}), **summary}
        for artifact in list(table):
            if artifact not in disk:
                table.pop(artifact, None)
    for record in (job.get("renders") or {}).values():
        if not isinstance(record, dict):
            continue
        artifact = record.get("artifact_id")
        if is_safe_artifact_id(artifact) and artifact not in table:
            table[artifact] = {
                "artifact_id": artifact,
                "status": record.get("status"),
                "pinned": bool(record.get("pinned")),
                "created": record.get("created"),
                "updated": record.get("updated"),
                "record_key": record.get("record_key"),
                "target": record.get("target"),
                "quality": record.get("quality"),
                "aspect": record.get("aspect"),
                "hook_scene": record.get("hook"),
                "captions": bool(record.get("captions")),
                "audio_sig": record.get("audio_sig") or "",
                "story_id": job.get("story_id"),
            }
    job["artifacts"] = table
    job["artifact_ids"] = sorted(table)
    return job


def public_manifest(manifest: dict, job_id: str | None = None) -> dict:
    artifact = str(manifest.get("artifact_id") or "")
    spec = manifest.get("spec") or {}
    caption = spec.get("caption") or {}
    value = {
        "artifact_id": artifact,
        "job_id": manifest.get("job_id") or job_id,
        "schema_version": manifest.get("schema_version", SCHEMA_VERSION),
        "status": manifest.get("status"),
        "pinned": bool(manifest.get("pinned")),
        "pinned_at": manifest.get("pinned_at"),
        "created": manifest.get("created"),
        "updated": manifest.get("updated"),
        "completed": manifest.get("completed"),
        "record_key": manifest.get("record_key"),
        "title": manifest.get("title"),
        "target": spec.get("target"),
        "quality": spec.get("quality"),
        "aspect": spec.get("aspect"),
        "hook_scene": spec.get("hook_scene"),
        "hook_override": bool(spec.get("hook_override")),
        "captions": bool(caption.get("enabled")),
        "caption_count": int(caption.get("cue_count") or 0),
        "cue_count": int(caption.get("cue_count") or 0),
        "audio_sig": spec.get("audio_sig") or "",
        "story_id": spec.get("story_id") or "",
        "source_fingerprint": spec.get("source_fingerprint") or "",
        "resolved_encoder": spec.get("resolved_encoder"),
        "generation": int(spec.get("generation") or 0),
        "spec": spec,
        "media": dict(manifest.get("media") or MEDIA_FILES),
        "error": manifest.get("error"),
    }
    if job_id and is_safe_artifact_id(artifact):
        base = f"/api/jobs/{job_id}/artifacts/{artifact}/media"
        value["url"] = f"{base}/reel.mp4"
        value["poster_url"] = f"{base}/poster.jpg"
        value["captions_url"] = f"{base}/captions.srt"
    return value


def render_record(manifest: dict) -> dict:
    """Reconstruct a legacy ``renders`` projection entry from a manifest."""
    spec = manifest.get("spec") or {}
    caption = spec.get("caption") or {}
    artifact = str(manifest.get("artifact_id") or "")
    render_info = manifest.get("render") or {}
    clips = spec.get("clips") or []
    total = round(sum(_number(clip.get("dur")) for clip in clips), 3)
    value = {
        "status": manifest.get("status") or "ready",
        "progress": 1.0 if manifest.get("status") == "ready" else 0.0,
        "message": "Reel ready" if manifest.get("status") == "ready" else manifest.get("status"),
        "error": manifest.get("error"),
        "key": render_info.get("key") or "",
        "hook": spec.get("hook_scene"),
        "total": total,
        "target": spec.get("target"),
        "quality": spec.get("quality"),
        "aspect": spec.get("aspect"),
        "encoder": spec.get("resolved_encoder"),
        "resolved_encoder": spec.get("resolved_encoder"),
        "captions": bool(caption.get("enabled")),
        "caption_count": int(caption.get("cue_count") or 0),
        "audio_sig": spec.get("audio_sig") or "",
        "record_key": manifest.get("record_key"),
        "artifact_id": artifact,
        "pinned": bool(manifest.get("pinned")),
        "created": manifest.get("created"),
        "updated": manifest.get("updated"),
        "generation": int(spec.get("generation") or 0),
        "path": f"artifacts/{artifact}/reel.mp4",
        "poster": f"artifacts/{artifact}/poster.jpg",
        **{key: render_info.get(key) for key in (
            "duration", "width", "height", "size", "has_audio", "clip_count",
            "caption_count", "cached", "used_assets",
        ) if key in render_info},
    }
    return value


def remove_projection(job: dict, artifact: str) -> list[str]:
    """Drop legacy projection records that point at one artifact."""
    removed: list[str] = []
    renders = job.get("renders")
    if not isinstance(renders, dict):
        return removed
    for key, record in list(renders.items()):
        if isinstance(record, dict) and record.get("artifact_id") == artifact:
            renders.pop(key, None)
            removed.append(key)
    table = job.get("artifacts")
    if isinstance(table, dict):
        table.pop(artifact, None)
    job["artifact_ids"] = sorted((job.get("artifacts") or {}).keys())
    return removed
