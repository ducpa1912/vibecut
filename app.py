"""VibeCut — local, self-hosted long-video to reel cutter."""

from __future__ import annotations

import errno
import hashlib
import hmac
import html as html_lib
import ipaddress
import json
import logging
import math
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# ``studio_app.py`` sets this before importing the module. Studio's build owns
# its page and does not import Classic's router, so the Classic tree can be
# absent without breaking boot. The default keeps the shared app as it was.
STUDIO_APP = os.environ.get("VIBECUT_APP", "").strip().lower() == "studio"

import artifacts
import audio
import captions as caption_engine
import admin.routes as admin_routes
import admin.store as admin_store
import batch as batch_store
import clipset
import disk
import editions
import edits
import exports as cuts
import history_store
import job_queue
import matrix
import migrations
import music
import overlays
import packet
import pipeline
import preflight
import render
import rights
import routes_auto_subs
import routes_batches
import routes_check
if not STUDIO_APP:
    import routes_classic
import routes_cleanup
import routes_edits
import routes_library
import routes_overlays
import routes_studio
import routes_voice_clone
import selection
import settings_store
import shares
import silent_script
import story_queue
import tighten
import usage_store
import vision
import voice_fit
import workflow_config
from url_ingest import fallback as ingest_fallback
from url_ingest import registry
from url_ingest.base import IngestError, IngestOptions

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DATA = Path(os.environ.get("VIBECUT_DATA", ROOT / "data")).expanduser().resolve()
JOBS = DATA / "jobs"
HOST = os.environ.get("VIBECUT_HOST", "127.0.0.1")
PORT = int(os.environ.get("VIBECUT_PORT", "8787"))
MAX_UPLOAD = int(float(os.environ.get("VIBECUT_MAX_UPLOAD_GB", "20")) * 1024 ** 3)
ACTIVE = {"scanning", "reading", "scoring"}
LIVE = ACTIVE | {"queued", "downloading"}
LOCK = threading.RLock()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
LOGGER = logging.getLogger("vibecut")
JOBS.mkdir(parents=True, exist_ok=True)
SOURCES = DATA / "sources"

analysis_pool = job_queue.Scheduler(
    "analysis", max_workers=1, thread_name_prefix="vibecut-analyze",
)
ingest_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="vibecut-ingest")
render_pool = job_queue.Scheduler(
    "render", max_workers=1, thread_name_prefix="vibecut-render",
)
#: Speech re-reads, written scripts and voice clip searches. Kept apart from
#: analysis so a long import never queues them, and the reverse.
voice_pool = job_queue.Scheduler(
    "voice", max_workers=1, thread_name_prefix="vibecut-voice",
)
INGEST_CANCELS: dict[str, threading.Event] = {}
ANALYSIS_CANCELS: dict[str, threading.Event] = {}
RENDER_CANCELS: dict[tuple[str, str], threading.Event] = {}
QUEUE_LOCK = threading.RLock()
ACTIVE_RENDER = {"queued", "rendering", "cancelling"}
RENDER_SUBMIT_LOCK = threading.RLock()


def _fnv1a(text: str) -> str:
    return audio.fnv1a(text)


def _canonical(value) -> str:
    return audio.canonical_json(value)


def _audio_signature(audio_plan: dict | None) -> str:
    return audio.signature(audio_plan)


def _reel_cues(job: dict, plan: dict, clips: list[dict] | None = None) -> list[dict]:
    """Sidecar cues for a cut: the words spoken inside its clips.

    With a transcript the cues come from the same timed engine as caption
    tracks, so the SRT matches the cut's speech and timing. Without one the
    scene-level text contract is kept.
    """
    analysis = (job or {}).get("analysis") or {}
    job_id = str((job or {}).get("id") or "")
    segments: list[dict] = []
    if job_id and "/" not in job_id and ".." not in job_id:
        segments = caption_engine.read_transcript_segments(_job_dir(job_id))
    if segments:
        cues, _source, _warnings = caption_engine.build_cues(
            {
                **(plan or {}),
                "clips": clips if clips is not None else (plan or {}).get("clips") or [],
                "_scenes": analysis.get("scenes") or [],
            },
            segments=segments,
            source_duration=float(((job or {}).get("source") or {}).get("duration") or 0.0),
        )
        if cues:
            return [
                {
                    "start": cue["start"], "end": cue["end"],
                    "text": cue["text"], "scene": cue.get("scene"),
                }
                for cue in cues
            ]
    return caption_engine.reel_cues(
        plan or {},
        clips if clips is not None else (plan or {}).get("clips") or [],
        analysis.get("scenes") or [],
    )


def _render_key(
    target: int,
    quality: str = "final",
    aspect: str = "9:16",
    captions: bool = False,
    audio_sig: str = "",
    hook_marker: int | None = None,
    story_id: str | None = None,
) -> str:
    key = str(int(target))
    if quality != "final":
        key += f":{quality}"
    if aspect != "9:16":
        key += f":{aspect.replace(':', 'x')}"
    if captions:
        key += ":cap"
    if audio_sig:
        key += f":a{audio_sig}"
    if hook_marker is not None:
        key += f":h{hook_marker}"
    if story_id:
        key += f":s{story_id}"
    return key


def _hook_marker(plan: dict) -> int | None:
    """Overridden hooks get their own render slot instead of overwriting auto."""
    if plan.get("auto", True):
        return None
    hook = plan.get("hook_scene")
    return int(hook) if hook is not None else None


# ---------------------------------------------------------------- store


def _hash_file(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def store_source(temp_path: Path, suffix: str, original_name: str) -> Path:
    """Move a file into the content-addressed store; returns the stored path."""
    SOURCES.mkdir(parents=True, exist_ok=True)
    digest = _hash_file(temp_path)
    directory = SOURCES / digest
    directory.mkdir(parents=True, exist_ok=True)
    stored = directory / f"source{suffix}"
    if stored.is_file() and stored.stat().st_size == temp_path.stat().st_size:
        temp_path.unlink(missing_ok=True)
    else:
        os.replace(temp_path, stored)
    meta = directory / "meta.json"
    if not meta.is_file():
        meta.write_text(json.dumps({
            "name": original_name,
            "size": stored.stat().st_size,
            "created": round(time.time(), 3),
        }), encoding="utf-8")
    return stored


def link_source(stored: Path, job_dir: Path, suffix: str) -> Path:
    """Hardlink the stored source into the job dir; copy if the volume differs."""
    target = job_dir / f"source{suffix}"
    target.unlink(missing_ok=True)
    try:
        os.link(stored, target)
    except OSError:
        shutil.copy2(stored, target)
    return target


def gc_sources() -> int:
    try:
        days = float(os.environ.get("VIBECUT_SOURCES_GC_DAYS", "0") or 0)
    except ValueError:
        days = 0.0
    if days <= 0 or not SOURCES.is_dir():
        return 0
    cutoff = time.time() - days * 86400
    removed = 0
    for directory in SOURCES.iterdir():
        if not directory.is_dir():
            continue
        files = [item for item in directory.iterdir() if item.is_file() and item.name.startswith("source")]
        if not files:
            continue
        try:
            referenced = any(item.stat().st_nlink > 1 for item in files)
            stale = directory.stat().st_mtime < cutoff
        except OSError:
            continue
        if referenced or not stale:
            continue
        shutil.rmtree(directory, ignore_errors=True)
        removed += 1
    return removed


def _job_dir(job_id: str) -> Path:
    if not job_id or "/" in job_id or ".." in job_id:
        raise HTTPException(404, "Job not found.")
    return JOBS / job_id


def _job_file(job_id: str) -> Path:
    return _job_dir(job_id) / "job.json"


def _load_unlocked(job_id: str) -> dict:
    path = _job_file(job_id)
    if not path.exists():
        raise HTTPException(404, "Job not found.")
    try:
        job = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(500, "Job data is unreadable.") from exc
    if not isinstance(job, dict):
        raise HTTPException(500, "Job data is unreadable.")
    _relocate_source(job)
    return artifacts.ensure_job_schema(job, path.parent)


def _relocate_source(job: dict) -> None:
    """Follow a source copy that moved with the data folder.

    Lane data moved from ``<worktree>/data`` to ``~/vibecut-lanes/<lane>``
    (scripts/serve.sh). Uploads and link downloads keep their file inside the
    data folder, so a missing ``.../data/<rest>`` path is looked up again
    under today's ``DATA``. A path outside a data folder (a video imported in
    place) is left alone and still reads as missing.
    """
    source = job.get("source")
    if not isinstance(source, dict):
        return
    raw = str(source.get("path") or "")
    if not raw or _source_exists(raw):
        return
    parts = Path(raw).parts
    if "data" not in parts:
        return
    index = len(parts) - 1 - parts[::-1].index("data")
    rest = parts[index + 1:]
    if not rest:
        return
    candidate = DATA.joinpath(*rest)
    if _source_exists(str(candidate)):
        source["path"] = str(candidate)


def load_job(job_id: str) -> dict:
    with LOCK:
        return _load_unlocked(job_id)


def _save_unlocked(job: dict) -> None:
    job["updated"] = round(time.time(), 3)
    directory = _job_dir(job["id"])
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "job.json"
    tmp = directory / f".job.{uuid.uuid4().hex}.tmp"
    tmp.write_text(json.dumps(job, ensure_ascii=False, separators=(",", ":")))
    os.replace(tmp, path)


def save_job(job: dict) -> None:
    with LOCK:
        _save_unlocked(job)


def update_job(job_id: str, mutator) -> dict:
    with LOCK:
        job = _load_unlocked(job_id)
        mutator(job)
        _save_unlocked(job)
        return job


def clean_options(raw: dict | None) -> dict:
    raw = raw or {}
    configured = str(
        (settings_store.load_settings().get("stt") or {}).get("language") or "en"
    ).strip().lower()
    requested = str(raw.get("speech_language") or "").strip().lower()
    options = {
        "ocr": bool(raw.get("ocr", True)),
        "transcribe": bool(raw.get("transcribe", False)),
        "smart_crop": bool(raw.get("smart_crop", True)),
        "crop_tracking": bool(raw.get("crop_tracking", True)),
        "transcribe_engine": str(raw.get("transcribe_engine") or "auto"),
        "speech_language": requested or configured,
    }
    # Classic sends the Setup language on every import, so only a language
    # that differs from Setup (or one flagged explicit) is the creator's pick.
    # A pick beats the title-script guess; the Setup default does not.
    flagged = raw.get("speech_language_explicit")
    explicit = str(flagged).strip().lower() if isinstance(flagged, str) else ""
    if not explicit and requested and (flagged is True or requested != configured):
        explicit = requested
    if explicit and explicit not in {"auto", "none", "und"}:
        options["speech_language_explicit"] = explicit
    return options


def _legacy_media_name(value) -> str:
    text = str(value or "")
    if text.startswith("renders/"):
        text = text[len("renders/"):]
    if not text or "/" in text or ".." in Path(text).parts:
        return ""
    return text


def _public_render(job_id: str, record: dict | None) -> dict | None:
    if not record:
        return None
    value = dict(record)
    if record.get("status") == "ready":
        artifact = record.get("artifact_id")
        artifact_ready = False
        job_dir = _job_dir(job_id)
        if artifacts.is_safe_artifact_id(artifact):
            manifest = artifacts.load_manifest(job_dir, artifact)
            artifact_ready = bool(
                manifest
                and manifest.get("status") == "ready"
                and artifacts.has_media(job_dir, artifact)
            )
        suffix = f"?v={record.get('key', '') or artifact or ''}"
        if artifact_ready:
            base = f"/api/jobs/{job_id}/artifacts/{artifact}/media"
            value["url"] = f"{base}/reel.mp4{suffix}"
            if artifacts.has_media(job_dir, artifact, "poster.jpg"):
                value["poster_url"] = f"{base}/poster.jpg{suffix}"
            elif record.get("poster"):
                legacy_poster = _legacy_media_name(record.get("poster"))
                if legacy_poster:
                    value["poster_url"] = (
                        f"/api/jobs/{job_id}/media/{legacy_poster}{suffix}"
                    )
        elif record.get("path"):
            legacy_path = _legacy_media_name(record.get("path"))
            legacy_poster = _legacy_media_name(record.get("poster"))
            if legacy_path:
                value["url"] = f"/api/jobs/{job_id}/media/{legacy_path}{suffix}"
            if legacy_poster:
                value["poster_url"] = (
                    f"/api/jobs/{job_id}/media/{legacy_poster}{suffix}"
                )
    return value


def _source_exists(path: str) -> bool:
    try:
        return Path(path).is_file()
    except OSError:
        return False


def source_missing(job: dict) -> str | None:
    """The source path when the original file is gone, else None.

    Jobs keep a path, not a copy, so a moved or deleted file must be named
    plainly instead of Check reporting "Checked" over an ffmpeg error and
    Stories finding nothing. A URL download still in flight has no file yet.
    """
    if str(job.get("status") or "") in {"downloading", "failed"} and not job.get("analysis"):
        return None
    path = str((job.get("source") or {}).get("path") or "")
    if not path:
        return None
    return None if _source_exists(path) else path


def source_missing_message(path: str) -> str:
    return f"The original file was moved or deleted: {path}. Put it back or import it again."


def require_source(job: dict) -> None:
    """Refuse work that reads the source when the file is gone (409)."""
    missing = source_missing(job)
    if missing:
        raise HTTPException(409, source_missing_message(missing))


def _source_state(job: dict) -> dict:
    missing = source_missing(job)
    return {
        "source_missing": bool(missing),
        "source_missing_path": missing,
        "source_missing_message": source_missing_message(missing) if missing else None,
    }


def public_job(job: dict) -> dict:
    artifacts.ensure_job_schema(job)
    value = dict(job)
    value.pop("source", None)
    value.pop("history", None)
    value["renders"] = {
        key: _public_render(job["id"], record)
        for key, record in (job.get("renders") or {}).items()
    }
    value["artifact_ids"] = list(job.get("artifact_ids") or [])
    value["artifacts"] = {
        artifact: artifacts.public_manifest(manifest, job["id"])
        for artifact, manifest in (
            (key, artifacts.load_manifest(_job_dir(job["id"]), key))
            for key in value["artifact_ids"]
        )
        if manifest is not None
    }
    value["source"] = {
        key: job.get("source", {}).get(key)
        for key in ("name", "duration", "width", "height", "fps", "has_audio", "size")
    }
    value["usage"] = _usage_summary(job)
    value["rights_policy"] = rights.policy(job)
    value.update(_source_state(job))
    analysis = value.get("analysis")
    if analysis:
        for scene in analysis.get("scenes", []):
            scene["thumb_url"] = f"/api/jobs/{job['id']}/thumb/{scene['id']}"
    return value


def public_status(job: dict) -> dict:
    artifacts.ensure_job_schema(job)
    return {
        "id": job["id"],
        "status": job.get("status"),
        "progress": job.get("progress", 0),
        "message": job.get("message", ""),
        "error": job.get("error"),
        "artifact_ids": list(job.get("artifact_ids") or []),
        "renders": {
            key: _public_render(job["id"], record)
            for key, record in (job.get("renders") or {}).items()
        },
        **_source_state(job),
    }


# ---------------------------------------------------------------- workers


class AnalysisCancelled(RuntimeError):
    """Best-effort cancellation raised at analysis progress checkpoints."""


def _analysis_cancel_event(job_id: str) -> threading.Event:
    event = ANALYSIS_CANCELS.get(job_id)
    if event is None:
        event = threading.Event()
        ANALYSIS_CANCELS[job_id] = event
    return event


def run_analysis(job_id: str) -> None:
    event = _analysis_cancel_event(job_id)
    job = load_job(job_id)
    if event.is_set():
        job["status"] = "cancelled"
        job["progress"] = 1.0
        job["message"] = "Cancelled"
        job["error"] = None
        save_job(job)
        ANALYSIS_CANCELS.pop(job_id, None)
        return
    job["status"] = "scanning"
    job["progress"] = 0.01
    job["message"] = "Warming up"
    job["error"] = None
    save_job(job)

    def progress(stage: str, fraction: float, message: str) -> None:
        if event.is_set():
            raise AnalysisCancelled("Analysis cancelled.")
        job["status"] = stage if stage in ACTIVE else "scoring"
        job["progress"] = round(max(0.01, min(0.995, fraction)), 4)
        job["message"] = message
        save_job(job)

    # Lets Cancel reading stop a speech engine that is mid-file.
    pipeline.stt.set_cancel_event(event)
    try:
        before_usage = usage_store.snapshot()
        options = dict(job.get("options") or {})
        options.setdefault("job_id", job_id)
        options.setdefault("request_id", job_id)
        analysis = pipeline.analyze_source(
            job["source"]["path"],
            job["source"],
            _job_dir(job_id),
            options,
            progress,
        )
        if event.is_set():
            raise AnalysisCancelled("Analysis cancelled.")
        analysis_delta = usage_store.delta(before_usage)
        if analysis_delta["calls"] or analysis_delta["audio_seconds"] or analysis_delta["chars"]:
            job.setdefault("usage", []).append({
                "action": "analysis",
                "at": round(time.time(), 3),
                **analysis_delta,
            })
        job["analysis"] = analysis
        job["status"] = "ready"
        job["progress"] = 1.0
        count = int(analysis["scene_count"])
        job["message"] = f"{count} {'moment' if count == 1 else 'moments'} · hook found"
        job["error"] = None
        save_job(job)
        LOGGER.info("job %s ready in %.1fs", job_id, analysis["elapsed"])
    except (AnalysisCancelled, pipeline.stt.SttCancelled):
        LOGGER.info("analysis cancelled for %s", job_id)
        job["status"] = "cancelled"
        job["progress"] = 1.0
        job["message"] = "Cancelled"
        job["error"] = None
        save_job(job)
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("analysis failed for %s", job_id)
        job["status"] = "failed"
        job["progress"] = 1.0
        job["message"] = "Analysis failed"
        job["error"] = str(exc)[:2400]
        save_job(job)
    finally:
        pipeline.stt.set_cancel_event(None)
        if ANALYSIS_CANCELS.get(job_id) is event:
            ANALYSIS_CANCELS.pop(job_id, None)


def _set_render(job_id: str, record_key: str, **values) -> dict:
    def mutate(job: dict) -> None:
        job.setdefault("renders", {})
        record = job["renders"].setdefault(record_key, {})
        record.update(values)
        record["updated"] = round(time.time(), 3)

    return update_job(job_id, mutate)


def _append_usage(job_id: str, action: str, delta: dict) -> None:
    if not delta.get("calls") and not delta.get("audio_seconds") and not delta.get("chars"):
        return

    def mutate(job: dict) -> None:
        job.setdefault("usage", []).append({
            "action": action,
            "at": round(time.time(), 3),
            **delta,
        })
        job["usage"] = job["usage"][-100:]

    update_job(job_id, mutate)


def _usage_summary(job: dict) -> dict:
    entries = job.get("usage") or []
    totals = {"calls": 0, "input_tokens": 0, "output_tokens": 0,
              "chars": 0, "audio_seconds": 0.0, "cost_usd": 0.0}
    for entry in entries:
        for key in ("calls", "input_tokens", "output_tokens", "chars"):
            totals[key] += int(entry.get(key) or 0)
        totals["audio_seconds"] += float(entry.get("audio_seconds") or 0.0)
        totals["cost_usd"] += float(entry.get("cost_usd") or 0.0)
    totals["audio_seconds"] = round(totals["audio_seconds"], 3)
    totals["cost_usd"] = round(totals["cost_usd"], 6)
    return {"totals": totals, "entries": entries[-40:]}


def _history_append(job_id: str, entry: dict, snapshot: dict | None = None) -> dict | None:
    """Best-effort history write; never break the media operation itself."""
    try:
        return history_store.append(_job_dir(job_id), entry, snapshot)
    except Exception:  # noqa: BLE001
        LOGGER.exception("history append failed for %s", job_id)
        return None


# ---------------------------------------------------------------- url ingest

YTDLP_QUALITY_VALUES = frozenset({"max", "2160", "1440", "1080", "720", "480", "360"})
YTDLP_CODEC_VALUES = frozenset({"h264", "any"})
YTDLP_CONTAINER_VALUES = frozenset({"mp4", "mkv", "webm"})
YTDLP_AUDIO_VALUES = frozenset({"best", "192", "128"})
YTDLP_COOKIE_VALUES = frozenset({"none", "browser", "file"})
YTDLP_BROWSER_VALUES = frozenset(
    {"safari", "chrome", "chromium", "firefox", "edge", "brave", "opera", "vivaldi", "whale"}
)
INGEST_VIDEO_SUFFIXES = frozenset(
    {".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi", ".mpg", ".mpeg", ".ts", ".flv"}
)
_INGEST_SECRET_KEYS = frozenset(
    {
        "xhs_token",
        "xhs_api_key",
        "xhs_access_token",
        "xhs_get_token",
    }
)
_INGEST_SESSION_FIELDS = (
    "cookie_set",
    "session_ok",
    "auth_required",
    "user",
    "login_site",
    "cookie_hint",
    "service_url",
)


def _public_ingest_settings(settings: dict) -> dict:
    """Return the safe, non-secret ingest settings for API responses."""
    ingest = settings.get("ingest") if isinstance(settings, dict) else {}
    ingest = ingest if isinstance(ingest, dict) else {}
    return {
        "provider": ingest.get("provider", registry.AUTO),
        "ytdlp_quality": ingest.get("ytdlp_quality", "max"),
        "ytdlp_codec": ingest.get("ytdlp_codec", "h264"),
        "ytdlp_container": ingest.get("ytdlp_container", "mp4"),
        "ytdlp_audio": ingest.get("ytdlp_audio", "best"),
        "ytdlp_cookies": ingest.get("ytdlp_cookies", "none"),
        "ytdlp_browser": ingest.get("ytdlp_browser", "safari"),
        "ytdlp_cookie_file": ingest.get("ytdlp_cookie_file", ""),
        "xhs_url": ingest.get("xhs_url", ""),
        "xhs_no_record": ingest.get("xhs_no_record", True),
        "xhs_interval": ingest.get("xhs_interval", 12.0),
    }


def _ingest_provider_settings(
    xhs_url: str | None = None,
    xhs_token: str | None = None,
) -> dict:
    """Load ingest settings and inject provider secrets for sidecar calls."""
    normalized = registry.normalize_settings(settings_store.load_settings())
    values = {
        "provider": normalized.get("provider", registry.AUTO),
        "ytdlp_quality": normalized.get("ytdlp_quality", "max"),
        "ytdlp_codec": normalized.get("ytdlp_codec", "h264"),
        "ytdlp_container": normalized.get("ytdlp_container", "mp4"),
        "ytdlp_audio": normalized.get("ytdlp_audio", "best"),
        "ytdlp_cookies": normalized.get("ytdlp_cookies", "none"),
        "ytdlp_browser": normalized.get("ytdlp_browser", "safari"),
        "ytdlp_cookie_file": normalized.get("ytdlp_cookie_file", ""),
        "xhs_url": xhs_url if xhs_url is not None else normalized.get("xhs_url", ""),
        "xhs_token": xhs_token if xhs_token is not None else settings_store.get_secret("xhs"),
        "xhs_no_record": normalized.get("xhs_no_record", True),
        "xhs_interval": normalized.get("xhs_interval", 12.0),
    }
    return {"ingest": values}


def _is_public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return bool(address.is_global)


@lru_cache(maxsize=512)
def _resolved_addresses(host: str) -> tuple[str, ...]:
    """Resolve a host once and return all A/AAAA addresses.

    ``getaddrinfo`` also normalizes legacy IPv4 spellings such as ``127.1``,
    integer hosts, and hex hosts, so those cannot bypass the literal check.
    """
    infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return tuple(sorted({str(info[4][0]) for info in infos if info[4]}))


def _validate_remote_ingest_url(url: str) -> str:
    """Validate a user URL and block local/private/link-local targets.

    Local files should use the path input. Literal addresses, legacy IPv4
    spellings, DNS aliases and common internal names are checked before a
    provider can fetch the URL. Network egress policy remains the final guard
    against a DNS rebinding race.
    """
    value = registry.validate_url(url)
    host = (urlsplit(value).hostname or "").lower().rstrip(".")
    if (
        host in {"localhost", "localhost.localdomain"}
        or host.endswith(".localhost")
        or host.endswith(".local")
        or host.endswith(".internal")
    ):
        raise IngestError("URL ingest only accepts public internet links. Use a local path instead.")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not literal.is_global:
            raise IngestError("URL ingest only accepts public internet links. Use a local path instead.")
        return value
    try:
        addresses = _resolved_addresses(host)
    except OSError as exc:
        raise IngestError("URL ingest could not resolve this public host.") from exc
    if not addresses:
        raise IngestError("URL ingest could not resolve this public host.")
    if any(not _is_public_address(address) for address in addresses):
        raise IngestError("URL ingest only accepts public internet links. Use a local path instead.")
    return value


def _ingest_provider_order(url: str, override: str | None, settings: dict) -> list[str]:
    """Return the ordered provider ids for this link.

    Auto mode starts with yt-dlp. RedNote stays on xhs.
    """
    ingest = settings.get("ingest") if isinstance(settings, dict) else {}
    ingest = ingest if isinstance(ingest, dict) else {}
    if override is not None and str(override).strip():
        configured = registry.normalize_provider_id(override, strict=True)
    else:
        configured = registry.normalize_provider_id(ingest.get("provider"))
    try:
        from url_ingest import ytdlp as ytdlp_ingest

        ytdlp_available = ytdlp_ingest.ytdlp_available()
    except Exception:  # noqa: BLE001
        ytdlp_available = False
    return ingest_fallback.fallback_provider_ids(
        configured,
        registry.detect(url),
        ytdlp_available,
    )


def _ingest_provider_chain(settings: dict, order: list[str]):
    sources = {
        registry.YTDLP: lambda: registry.provider(registry.YTDLP, settings),
        registry.XHS: lambda: registry.provider(registry.XHS, settings),
    }
    return ingest_fallback.ProviderChain(sources, order=order)


def _provider_status_entry(provider, settings: dict, *, optimistic: bool = False) -> dict:
    """Call a provider's live status without letting it break an API route."""
    fallback = {
        "id": str(getattr(provider, "id", "") or ""),
        "label": str(getattr(provider, "label", "") or ""),
        "configured": optimistic,
        "available": optimistic,
        "error": "",
    }
    method = getattr(provider, "status", None)
    if not callable(method):
        return fallback
    try:
        entry = method(settings)
    except TypeError:
        try:
            entry = method()
        except Exception as exc:  # noqa: BLE001
            return {**fallback, "error": _short_ingest_error(exc)}
    except Exception as exc:  # noqa: BLE001
        return {**fallback, "error": _short_ingest_error(exc)}
    if not isinstance(entry, dict):
        return {**fallback, "error": "Provider status returned an invalid result."}
    result = {**fallback, **entry}
    result["available"] = bool(result.get("available"))
    result["configured"] = bool(result.get("configured", result["available"]))
    return result


_SENSITIVE_QUERY_MARKERS = (
    "xsec_source", "token", "secret", "password", "passwd", "auth",
    "signature", "sig", "api_key", "api-key", "apikey", "session",
    "cookie", "credential",
)


def _is_sensitive_query_key(key: str) -> bool:
    lowered = str(key or "").lower()
    return (
        lowered == "key"
        or any(marker in lowered for marker in _SENSITIVE_QUERY_MARKERS)
    )


def _redact_ingest_text(value: str) -> str:
    """Redact token-like query pairs from logs, errors, and metadata."""
    text = " ".join(str(value or "").split())
    return re.sub(
        r"(?i)\b([a-z0-9_.-]*(?:xsec_source|token|secret|password|passwd|auth|signature|sig|api[_-]?key|apikey|session|cookie|credential|key)[a-z0-9_.-]*)=([^&\s]+)",
        r"\1=redacted",
        text,
    )


def _short_ingest_error(exc: BaseException) -> str:
    text = _redact_ingest_text(str(exc))
    return (text or exc.__class__.__name__)[:400]


def _ingest_session(entry: dict) -> dict:
    session = entry.get("session") if isinstance(entry, dict) else None
    session = dict(session) if isinstance(session, dict) else {}
    if isinstance(entry, dict):
        for key in _INGEST_SESSION_FIELDS:
            if key not in session and key in entry:
                session[key] = entry.get(key)
    return session


def _ingest_warning(*values) -> str:
    warnings: list[str] = []
    for value in values:
        text = " ".join(str(value or "").split())
        if text and text not in warnings:
            warnings.append(text)
    return " ".join(warnings)


def _ingest_progress(job_id: str, fraction: float, message: str) -> None:
    try:
        value = max(0.0, min(0.99, float(fraction)))
    except (TypeError, ValueError):
        return
    text = " ".join(str(message or "").split())[:240] or "Downloading"

    def mutate(job: dict) -> None:
        if job.get("status") != "downloading":
            return
        job["progress"] = round(value, 4)
        job["message"] = text
        ingest = job.setdefault("ingest", {})
        ingest["progress"] = job["progress"]
        ingest["message"] = text

    try:
        update_job(job_id, mutate)
    except Exception:  # noqa: BLE001
        # Progress is advisory; a removed/unreadable job must not stop download.
        pass


def _redact_source_url(value: str) -> str:
    """Remove share/access tokens from URLs before storing or returning them."""
    raw = str(value or "")
    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw
    if not parts.scheme or not parts.netloc:
        return raw
    query = [
        (key, "redacted" if _is_sensitive_query_key(key) else val)
        for key, val in parse_qsl(parts.query, keep_blank_values=True)
    ]
    netloc = parts.netloc.rsplit("@", 1)[-1]
    return urlunsplit((
        parts.scheme, netloc, parts.path,
        urlencode(query, doseq=True), "",
    ))


def _redact_ingest_value(value):
    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            if (
                _is_sensitive_query_key(str(key))
                and isinstance(item, str)
                and item.strip()
            ):
                clean[key] = "redacted"
            else:
                clean[key] = _redact_ingest_value(item)
        return clean
    if isinstance(value, (list, tuple)):
        return [_redact_ingest_value(item) for item in value]
    if isinstance(value, str):
        redacted = _redact_ingest_text(value)
        if redacted != value:
            return redacted
        try:
            parts = urlsplit(value)
        except ValueError:
            return redacted
        if parts.scheme in {"http", "https"} and parts.netloc:
            return _redact_source_url(value)
    return value


def _redact_ingest_meta(meta: dict | None) -> dict:
    """Return provider metadata with tokens removed at every nesting level."""
    return _redact_ingest_value(dict(meta or {}))


def _attempts_payload(attempts) -> list[dict]:
    return _redact_ingest_value([
        attempt.as_dict()
        for attempt in attempts or ()
        if hasattr(attempt, "as_dict")
    ])


def _cleanup_ingest_temp(temp: Path | None) -> None:
    """Remove the app temp and any yt-dlp output that stripped its dot prefix."""
    if temp is None:
        return
    names = {temp.name, temp.name.lstrip(".")}
    for name in names:
        for path in SOURCES.glob(f"{name}*"):
            try:
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink(missing_ok=True)
            except OSError:
                pass


def _ingest_temp_path(job_id: str, source_url: str) -> Path:
    suffix = ""
    try:
        suffix = Path(urlsplit(source_url).path).suffix.lower()
    except (TypeError, ValueError):
        suffix = ""
    if suffix not in INGEST_VIDEO_SUFFIXES:
        suffix = ".mp4"
    SOURCES.mkdir(parents=True, exist_ok=True)
    return SOURCES / f".ingest-{job_id}-{uuid.uuid4().hex}{suffix}"


def _ingest_names(result, downloaded: Path) -> tuple[str, str]:
    raw = result.filename or result.title or downloaded.name or "url-video"
    display = registry.safe_filename(raw, "url-video", max_length=140)
    suffix = Path(display).suffix.lower()
    if suffix not in INGEST_VIDEO_SUFFIXES:
        actual = downloaded.suffix.lower()
        suffix = actual if actual in INGEST_VIDEO_SUFFIXES else ".mp4"
        stem = Path(display).stem or "url-video"
        display = registry.safe_filename(f"{stem}{suffix}", f"url-video{suffix}", max_length=140)
    return display, suffix


def _record_ingest_history(
    job_id: str,
    provider_id: str,
    source_url: str,
    status: str,
    *,
    title: str = "",
    path: str | None = None,
    duration: float | None = None,
    size: int | None = None,
    error: str | None = None,
    warning: str | None = None,
    meta: dict | None = None,
) -> dict | None:
    source_url = _redact_source_url(source_url)
    safe_meta = _redact_ingest_meta(meta)
    safe_title = _redact_ingest_text(title or "")
    safe_error = _redact_ingest_text(error or "") or None
    safe_warning = _redact_ingest_text(warning or "") or None
    entry = {
        "id": uuid.uuid4().hex[:12],
        "type": "ingest",
        "created": round(time.time(), 3),
        "status": status,
        "kind": provider_id,
        "style": provider_id,
        "name": safe_title or (Path(path).name if path else provider_id),
        "path": path,
        "duration": duration,
        "target": None,
        "source_lang": None,
        "target_lang": None,
        "provider": provider_id,
        "fallback": False,
        "tried": [],
        "model": None,
        "latency_ms": 0,
        "usage": {},
        "warning": safe_warning,
        "error": safe_error,
        "script_id": None,
        "size": size,
        "source_url": source_url,
        "title": safe_title,
    }
    snapshot = {
        "provider": provider_id,
        "source_url": source_url,
        "title": safe_title,
        "path": path,
        "duration": duration,
        "size": size,
        "status": status,
        "error": safe_error,
        "meta": safe_meta,
    }
    return _history_append(job_id, entry, snapshot)


def _run_url_ingest(
    job_id: str,
    chain,
    provider_id: str,
    provider_label: str,
    source_url: str,
    options: IngestOptions,
    cancel_event: threading.Event,
    analysis_options: dict,
) -> None:
    temp: Path | None = None
    destination: Path | None = None
    metadata: dict = {}
    title = ""
    try:
        if cancel_event.is_set():
            raise IngestError("Download cancelled.")
        temp = _ingest_temp_path(job_id, source_url)
        result = chain.download(
            source_url,
            temp,
            options,
            lambda fraction, message: _ingest_progress(job_id, fraction, message),
            cancel_event,
        )
        if cancel_event.is_set():
            raise IngestError("Download cancelled.")
        provider_id = str(chain.last_provider_id or result.provider or provider_id)
        provider_label = str(
            getattr(chain.last_provider, "label", "") or provider_label or provider_id
        )

        downloaded = Path(result.path).expanduser()
        if not downloaded.is_file():
            raise IngestError("The provider did not produce a video file.")
        if downloaded.stat().st_size <= 0:
            raise IngestError("The provider returned an empty video file.")
        disk.preflight(disk.estimate_upload(downloaded.stat().st_size), DATA)

        display, suffix = _ingest_names(result, downloaded)
        title = str(result.title or "").strip() or Path(display).stem
        stored = store_source(downloaded, suffix, display)
        destination = link_source(stored, _job_dir(job_id), suffix)
        if cancel_event.is_set():
            raise IngestError("Download cancelled.")
        metadata = pipeline.probe(destination)
        duration = metadata.get("duration")
        if duration is None:
            duration = result.duration
            if duration is not None:
                metadata["duration"] = duration
        if cancel_event.is_set():
            raise IngestError("Download cancelled.")

        def finish(job: dict) -> None:
            job["status"] = "queued"
            job["progress"] = 0.0
            job["message"] = "Queued for analysis"
            job["error"] = None
            job["source"] = {"path": str(destination), "name": display, **metadata}
            job["options"] = analysis_options
            ingest = job.setdefault("ingest", {})
            ingest.update({
                "provider": provider_id,
                "label": provider_label,
                "source_url": _redact_source_url(source_url),
                "title": title,
                "thumbnail": _redact_ingest_value(result.thumbnail),
                "duration": duration,
                "meta": _redact_ingest_meta(result.meta),
                "options": options.as_dict(),
                "progress": 0.0,
                "message": "Queued for analysis",
                "phase": "queued",
                "status": "queued",
                "error": None,
            })

        update_job(job_id, finish)
        _record_ingest_history(
            job_id,
            provider_id,
            source_url,
            "ok",
            title=title,
            path=str(destination),
            duration=duration,
            size=metadata.get("size"),
            meta=_redact_ingest_meta(result.meta),
        )
        try:
            analysis_pool.submit(run_analysis, job_id)
        except Exception:  # noqa: BLE001
            LOGGER.exception("could not queue analysis for %s", job_id)
    except Exception as exc:  # noqa: BLE001
        cancelled = cancel_event.is_set()
        error = (
            "Download cancelled."
            if cancelled
            else _short_ingest_error(exc)
        )
        message = "Download cancelled" if cancelled else "URL ingest failed"
        LOGGER.info("url ingest failed for %s: %s", job_id, error)
        attempts = _attempts_payload(getattr(exc, "attempts", ()))

        def fail(job: dict) -> None:
            job["status"] = "failed"
            job["progress"] = 1.0
            job["message"] = message
            job["error"] = error
            ingest = job.setdefault("ingest", {})
            ingest.update({
                "phase": "failed",
                "status": "failed",
                "progress": 1.0,
                "message": message,
                "error": error,
            })
            if attempts:
                ingest["attempts"] = attempts

        try:
            update_job(job_id, fail)
        except Exception:  # noqa: BLE001
            # A removed job still gets a history entry when possible.
            LOGGER.exception("could not mark url job %s failed", job_id)
        _record_ingest_history(
            job_id,
            provider_id,
            source_url,
            "failed",
            title=title,
            path=str(destination) if destination else None,
            duration=metadata.get("duration"),
            size=metadata.get("size"),
            error=error,
            meta={**metadata, **({"attempts": attempts} if attempts else {})},
        )
    finally:
        _cleanup_ingest_temp(temp)
        INGEST_CANCELS.pop(job_id, None)



def _clip_hash(clips: list[dict] | None) -> str:
    if not clips:
        return ""
    return hashlib.sha1(_canonical(clips).encode("utf-8")).hexdigest()[:16]


def _history_tried(translation: dict | None, rewrite: dict | None) -> list[str]:
    tried: list[str] = []
    for name in (translation or {}).get("tried") or []:
        value = str(name)
        if value and value not in tried:
            tried.append(value)
    for attempt in (rewrite or {}).get("attempts") or []:
        value = str((attempt or {}).get("provider") or "")
        if value and value not in tried:
            tried.append(value)
    return tried[:24]


def _provider_model(provider: str | None) -> str:
    name = str(provider or "")
    try:
        if name == "opencode":
            return audio.opencode_model()
        if name == "openrouter":
            return audio.openrouter_model()
    except Exception:  # noqa: BLE001
        return name
    return name


def _audio_languages(audio_plan: dict | None) -> tuple[str | None, str | None]:
    if not isinstance(audio_plan, dict):
        return None, None
    translate = audio_plan.get("translate")
    if not isinstance(translate, dict):
        return None, None
    source = str(translate.get("source") or "").split("-")[0] or None
    target = str(translate.get("target") or "").split("-")[0] or None
    return source, target


def _body_script_id(body, audio_plan: dict | None) -> str | None:
    value = getattr(body, "script_id", None)
    if not value and isinstance(audio_plan, dict):
        value = audio_plan.get("script_id")
    text = str(value or "").strip()[:64]
    return text or None


def _record_upload_history(
    job_id: str,
    kind: str,
    status: str,
    name: str,
    *,
    path: str | None = None,
    duration: float | None = None,
    size: int | None = None,
    error: str | None = None,
    latency_ms: int = 0,
) -> dict | None:
    entry = {
        "id": uuid.uuid4().hex[:12],
        "type": "upload",
        "created": round(time.time(), 3),
        "status": status,
        "kind": kind,
        "name": name,
        "path": path,
        "duration": duration,
        "target": None,
        "style": kind,
        "source_lang": None,
        "target_lang": None,
        "provider": None,
        "fallback": False,
        "tried": [],
        "model": None,
        "latency_ms": latency_ms,
        "usage": {},
        "warning": None,
        "error": error,
        "script_id": None,
        "size": size,
    }
    snapshot = {
        "kind": kind,
        "name": name,
        "path": path,
        "duration": duration,
        "size": size,
        "error": error,
        "status": status,
    }
    return _history_append(job_id, entry, snapshot)


def _record_render_history(
    job_id: str,
    record: dict,
    plan: dict,
    audio_plan: dict | None,
    status: str,
    *,
    script_id: str | None = None,
    error: str | None = None,
    warning: str | None = None,
    latency_ms: int = 0,
    entry_id: str | None = None,
) -> dict | None:
    try:
        return _append_render_history(
            job_id, record, plan, audio_plan, status,
            script_id=script_id, error=error, warning=warning,
            latency_ms=latency_ms, entry_id=entry_id,
        )
    except Exception:  # noqa: BLE001
        LOGGER.exception("render history failed for %s", job_id)
        return None


def _append_render_history(
    job_id: str,
    record: dict,
    plan: dict,
    audio_plan: dict | None,
    status: str,
    *,
    script_id: str | None = None,
    error: str | None = None,
    warning: str | None = None,
    latency_ms: int = 0,
    entry_id: str | None = None,
) -> dict | None:
    source_lang, target_lang = _audio_languages(audio_plan)
    if not source_lang:
        source_lang = str(plan.get("_source_lang") or "").split("-")[0] or None
    translate = (audio_plan or {}).get("translate") if isinstance(audio_plan, dict) else None
    if not isinstance(translate, dict):
        translate = {}
    provider = str(translate.get("provider") or "") or None
    target = record.get("target")
    quality = record.get("quality") or "final"
    aspect = record.get("aspect") or "9:16"
    audio_sig = record.get("audio_sig") or ""
    record_key = record.get("record_key") or ""
    entry = {
        "id": entry_id or uuid.uuid4().hex[:12],
        "type": "render",
        "created": round(time.time(), 3),
        "status": status,
        "target": target,
        "style": record.get("preset") or quality,
        "source_lang": source_lang,
        "target_lang": target_lang,
        "provider": provider,
        "fallback": False,
        "tried": [],
        "model": None,
        "latency_ms": latency_ms,
        "usage": record.get("usage") or {},
        "warning": warning,
        "error": error,
        "path": record.get("path"),
        "artifact_id": record.get("artifact_id"),
        "script_id": script_id,
        "clip_hash": _clip_hash(plan.get("clips")),
        "kind": "render",
        "quality": quality,
        "aspect": aspect,
        "audio_sig": audio_sig,
        "record_key": record_key,
    }
    snapshot = {
        "render": record,
        "plan": {
            "target": target,
            "hook_scene": plan.get("hook_scene"),
            "total": plan.get("total"),
            "clip_count": plan.get("clip_count"),
            "order": plan.get("order") or "source",
            "clips": plan.get("clips") or [],
        },
        "script_id": script_id,
        "error": error,
        "warning": warning,
        "status": status,
    }
    return _history_append(job_id, entry, snapshot)


def _load_shares(strict: bool = True) -> dict:
    return shares.load(SHARES, strict=strict)


SHARE_STORE_DETAIL = (
    "The review share store is unreadable; refusing to continue."
)


def _share_store_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(503, SHARE_STORE_DETAIL)


def _job_media_path(
    job_dir: Path,
    name: str | None,
    default_root: str = "renders",
) -> Path | None:
    """Resolve only job-relative render/artifact media, never arbitrary files."""
    text = str(name or "")
    if not text:
        return None
    parts = Path(text).parts
    if not parts or ".." in parts:
        return None
    if len(parts) == 1:
        candidate = job_dir / default_root / parts[0]
    elif parts[0] in ("renders", "artifacts"):
        if parts[0] == "artifacts" and (
            len(parts) != 3
            or not artifacts.is_safe_artifact_id(parts[1])
            or parts[2] not in artifacts.MEDIA_NAMES
        ):
            return None
        candidate = job_dir.joinpath(*parts)
    else:
        return None
    try:
        resolved = candidate.resolve()
        resolved.relative_to(job_dir.resolve())
    except (OSError, ValueError):
        return None
    return resolved


def _record_media_path(job_dir: Path, record: dict, field: str = "path") -> Path | None:
    return _job_media_path(job_dir, record.get(field))


def _adoption_plan(job: dict, target: int, hook: int | None) -> dict:
    analysis = job.get("analysis") or {}
    plans = analysis.get("plans") or {}
    plan = plans.get(str(target)) or plans.get(target)
    if isinstance(plan, dict):
        return plan
    return {
        "target": int(target),
        "total": 0.0,
        "hook_scene": hook,
        "auto": True,
        "clip_count": 0,
        "clips": [],
    }


def _adopt_render_artifact(
    job: dict,
    record: dict,
    target: int | None = None,
    aspect: str | None = None,
) -> dict | None:
    """Give a v0.13 ready render a manifest so old shares can pin to it."""
    job_dir = _job_dir(job["id"])
    artifact = record.get("artifact_id")
    if artifacts.is_safe_artifact_id(artifact):
        manifest = artifacts.load_manifest(job_dir, artifact)
        if manifest is not None:
            record["artifact_id"] = artifact
            record["resolved_encoder"] = (
                (manifest.get("spec") or {}).get("resolved_encoder")
                or record.get("resolved_encoder")
            )
            artifacts.ensure_job_schema(job, job_dir)
            return manifest
    reel = _record_media_path(job_dir, record, "path")
    poster = _record_media_path(job_dir, record, "poster")
    try:
        wanted_target = int(target if target is not None else record.get("target") or 0)
    except (TypeError, ValueError):
        wanted_target = 0
    plan = _adoption_plan(job, wanted_target, record.get("hook"))
    prepared = render.prepare_render(plan, job.get("source") or {}, None)
    prepared_cues = _reel_cues(job, plan, prepared["clips"])
    quality = str(record.get("quality") or "final")
    chosen_aspect = str(aspect or record.get("aspect") or "9:16")
    captions = bool(record.get("captions"))
    audio_sig = str(record.get("audio_sig") or "")
    caption_track = None
    track_id = str(record.get("caption_track_id") or "")
    if captions and track_id:
        caption_track = caption_engine.load_track(job_dir, track_id)
    caption_warning = None
    if captions and caption_track is not None:
        cues = [cue.to_dict() for cue in caption_track.cues]
        caption_style_key = caption_track.style_hash
    else:
        cues = prepared_cues
        caption_style_key = ""
        if captions:
            caption_warning = (
                "Stored caption track missing; regenerated SRT from the plan."
                if track_id
                else "Legacy render had no pinned caption track; regenerated SRT from the plan."
            )
            LOGGER.warning(
                "legacy artifact adoption for %s/%s: %s",
                job.get("id"), record.get("record_key") or wanted_target,
                caption_warning,
            )
    margin = float(record.get("caption_margin") or 0.075)
    spec = artifacts.build_spec(
        job, plan,
        quality=quality,
        aspect=chosen_aspect,
        encoder=record.get("encoder"),
        captions=captions,
        audio_sig=audio_sig,
        preset=record.get("preset"),
        caption_margin=margin,
        caption_style_key=caption_style_key,
        story_id=plan.get("story_id"),
        cues=cues,
        clips=prepared["clips"],
    )
    artifact = artifacts.artifact_id(spec)
    record_key = str(
        record.get("record_key")
        or _render_key(
            wanted_target, quality, chosen_aspect, captions, audio_sig,
            story_id=plan.get("story_id"),
        )
    )
    existing = artifacts.load_manifest(job_dir, artifact)
    if existing is not None:
        # Never rewrite a manifest that may already be pinned or shared.
        record["artifact_id"] = artifact
        record["record_key"] = record.get("record_key") or record_key
        record["resolved_encoder"] = (
            (existing.get("spec") or {}).get("resolved_encoder")
            or spec.resolved_encoder
        )
        artifacts.ensure_job_schema(job, job_dir)
        return existing
    if artifacts.manifest_path(job_dir, artifact).is_file():
        # A manifest exists but does not validate. Do not overwrite it.
        return None
    if reel is None or not reel.is_file():
        return None
    manifest = artifacts.make_manifest(
        job["id"], spec,
        status="ready",
        record_key=record_key,
        title=Path(job.get("source", {}).get("name") or "reel").stem,
        created=record.get("created") or record.get("updated"),
    )
    artifacts.assign_version(job_dir, manifest)
    manifest["caption_source"] = "track" if caption_track is not None else "plan"
    manifest["caption_track_id"] = caption_track.id if caption_track is not None else None
    manifest["caption_style_id"] = (
        caption_track.style_id if caption_track is not None else None
    )
    if caption_warning:
        manifest["caption_warning"] = caption_warning
        record["caption_warning"] = caption_warning
    manifest["render"] = {
        key: record.get(key)
        for key in (
            "duration", "width", "height", "size", "has_audio", "clip_count",
            "caption_count", "cached", "used_assets", "key",
        )
        if key in record
    }
    artifacts.store_media(job_dir, artifact, reel, poster)
    artifacts.write_captions(job_dir, artifact, cuts.srt(cues), cuts.vtt(cues))
    manifest = artifacts.save_manifest(job_dir, manifest)
    record["artifact_id"] = artifact
    record["record_key"] = record.get("record_key") or record_key
    record["resolved_encoder"] = spec.resolved_encoder
    artifacts.ensure_job_schema(job, job_dir)
    return manifest


def _adopt_ready_artifacts(job_id: str) -> tuple[dict, list[dict]]:
    """Adopt ready legacy renders before exposing the artifact list.

    A legacy render is ready when its record is ready and its media path
    resolves. Failed, queued, and rendering records are never touched, so
    adoption cannot make unfinished work look publishable. The record's
    artifact id makes a second call a read-only no-op.
    """
    job_dir = _job_dir(job_id)
    adopted: dict[str, dict] = {}
    with RENDER_SUBMIT_LOCK:
        with LOCK:
            job = _load_unlocked(job_id)
            changed = False
            for record in (job.get("renders") or {}).values():
                if not isinstance(record, dict):
                    continue
                if record.get("status") != "ready" or not record.get("path"):
                    continue
                artifact = record.get("artifact_id")
                previous = (
                    artifacts.load_manifest(job_dir, artifact)
                    if artifacts.is_safe_artifact_id(artifact)
                    else None
                )
                before = (
                    record.get("artifact_id"),
                    record.get("record_key"),
                    record.get("resolved_encoder"),
                    record.get("caption_warning"),
                )
                manifest = _adopt_render_artifact(
                    job,
                    record,
                    record.get("target"),
                    record.get("aspect"),
                )
                if manifest is None or manifest.get("status") != "ready":
                    continue
                if (
                    previous is None
                    and manifest.get("artifact_id") not in adopted
                ):
                    adopted[manifest["artifact_id"]] = manifest
                after = (
                    record.get("artifact_id"),
                    record.get("record_key"),
                    record.get("resolved_encoder"),
                    record.get("caption_warning"),
                )
                if after != before:
                    changed = True
            if changed:
                artifacts.ensure_job_schema(job, job_dir)
                _save_unlocked(job)
    return job, list(adopted.values())


def _find_artifact_for_target(
    job: dict, target: int, aspect: str, not_after: float | None = None,
) -> dict | None:
    """Resolve the artifact a legacy target/aspect link would serve today.

    ``not_after`` binds an existing legacy link: the file at the legacy path is
    what that link always served, and a manifest made after the link was
    created is never a candidate, so an old link cannot jump to a newer cut.
    """
    record = _find_share_render(job, target, aspect)
    if record:
        manifest = _adopt_render_artifact(job, record, target, aspect)
        if manifest is not None and manifest.get("status") == "ready":
            return manifest
    job_dir = _job_dir(job["id"])
    candidates = []
    for manifest in artifacts.list_manifests(job_dir):
        spec = manifest.get("spec") or {}
        if manifest.get("status") != "ready":
            continue
        if not_after is not None and float(manifest.get("created") or 0) > not_after:
            continue
        if int(spec.get("target") or 0) != int(target):
            continue
        if str(spec.get("aspect") or "9:16") != aspect:
            continue
        artifact = str(manifest.get("artifact_id") or "")
        if not artifacts.has_media(job_dir, artifact):
            continue
        candidates.append(manifest)
    candidates.sort(key=lambda item: float(item.get("created") or 0), reverse=True)
    return candidates[0] if candidates else None


def _artifact_for_legacy_share(job: dict, record: dict) -> dict | None:
    try:
        target = int(record.get("target") or 0)
    except (TypeError, ValueError):
        return None
    aspect = str(record.get("aspect") or "9:16")
    created = float(record.get("created") or 0.0)
    return _find_artifact_for_target(job, target, aspect, not_after=created)


def _share(token: str) -> tuple[dict, dict, dict] | None:
    try:
        stored = _load_shares(strict=True).get(token)
    except shares.ShareStoreError as exc:
        raise _share_store_unavailable(exc) from exc
    if not stored:
        return None
    record = shares.describe(stored, token)
    status = shares.state(record)
    if status == shares.EXPIRED:
        raise HTTPException(410, "This review link has expired.")
    if status == shares.REVOKED:
        raise HTTPException(410, "This review link was revoked.")
    try:
        job = load_job(record["job_id"])
    except HTTPException:
        return None
    if not record.get("artifact_id"):
        manifest = _artifact_for_legacy_share(job, record)
        if manifest is None:
            return None
        try:
            bound = shares.bind_artifact(token, manifest["artifact_id"], SHARES)
        except shares.ShareStoreError as exc:
            raise _share_store_unavailable(exc) from exc
        if bound:
            record = bound
    artifact = str(record.get("artifact_id") or "")
    manifest = artifacts.load_manifest(_job_dir(job["id"]), artifact)
    if manifest is None:
        raise HTTPException(404, "This review artifact no longer exists.")
    if manifest.get("status") != "ready":
        raise HTTPException(404, "This review artifact is not ready.")
    if not artifacts.has_media(_job_dir(job["id"]), artifact):
        raise HTTPException(404, "The review video is missing.")
    value = dict(record)
    spec = manifest.get("spec") or {}
    value["artifact_id"] = artifact
    value["target"] = spec.get("target")
    value["aspect"] = spec.get("aspect")
    value["job_id"] = record.get("job_id") or job["id"]
    # A link stays pinned to its artifact; the label says when it is old.
    value["versions"] = artifacts.version_info(_job_dir(job["id"]), manifest)
    return value, job, artifacts.render_record(manifest)


def _share_captions(job: dict, artifact: str) -> str:
    if not artifacts.is_safe_artifact_id(str(artifact)):
        raise HTTPException(404, "Captions are not available for this artifact.")
    path = artifacts.media_path(_job_dir(job["id"]), str(artifact), "captions.srt")
    if not path.is_file():
        raise HTTPException(404, "Captions are not available for this artifact.")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise HTTPException(404, "Captions are not available for this artifact.") from exc


#: Render file names carry their shape; a 9:16 file has no token. Every other
#: shape must be listed, or a 9:16 lookup can pick its file.
_OTHER_SHAPE_TOKENS = ("_16x9", "_16x10", "_1x1", "_4x5")


def _find_share_render(job: dict, target: int, aspect: str) -> dict | None:
    rows = []
    for record in (job.get("renders") or {}).values():
        if record.get("status") != "ready" or not record.get("path"):
            continue
        if f"reel_{int(target)}" not in str(record["path"]):
            continue
        path = str(record["path"])
        if aspect == "9:16" and any(token in path for token in _OTHER_SHAPE_TOKENS):
            continue
        if aspect != "9:16" and aspect.replace(":", "x") not in path:
            continue
        rows.append(record)
    rows.sort(key=lambda item: float(item.get("updated") or 0), reverse=True)
    if rows:
        return rows[0]
    # CLI renders are files only, so fall back to the render directory.
    directory = _job_dir(job["id"]) / "renders"
    pattern = f"reel_{int(target)}*.mp4"
    candidates = []
    for path in directory.glob(pattern):
        name = path.name
        if aspect == "9:16" and any(token in name for token in _OTHER_SHAPE_TOKENS):
            continue
        if aspect != "9:16" and aspect.replace(":", "x") not in name:
            continue
        candidates.append(path)
    candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    if not candidates:
        return None
    chosen = candidates[0]
    return {
        "status": "ready",
        "path": str(chosen.relative_to(_job_dir(job["id"]))),
        "updated": chosen.stat().st_mtime,
    }


def run_render(
    job_id: str,
    target: int,
    plan: dict,
    key: str,
    quality: str = "final",
    aspect: str = "9:16",
    encoder: str | None = None,
    captions: bool = False,
    audio_plan: dict | None = None,
    audio_sig: str = "",
    preset: str | None = None,
    caption_margin: float = 0.075,
    script_id: str | None = None,
    artifact_id: str | None = None,
    generation: int = 0,
    prepared_clips: list[dict] | None = None,
    prepared_total: float | None = None,
    edit: dict | None = None,
) -> None:
    plan["_source_lang"] = plan.get("_source_lang") or "en"
    record_key = _render_key(
        target, quality, aspect, captions, audio_sig, _hook_marker(plan),
        story_id=plan.get("story_id"),
    )
    cancel_event = RENDER_CANCELS.setdefault((job_id, record_key), threading.Event())
    started = time.time()
    try:
        job = load_job(job_id)
        job_dir = _job_dir(job_id)
        if artifacts.is_safe_artifact_id(artifact_id):
            queued = artifacts.load_manifest(job_dir, artifact_id)
            if queued is not None:
                # The artifact id is authoritative when a caller omits the
                # generation argument (for example a direct retry).
                generation = int(
                    (queued.get("spec") or {}).get("generation") or generation or 0
                )
        scenes = job["analysis"]["scenes"]
        plan["_scenes"] = scenes
        source_duration = float(
            (job.get("source") or {}).get("duration") or 0.0
        )
        plan["_source_duration"] = source_duration
        raw_clip_hash = caption_engine.clip_hash(plan.get("clips"))
        if prepared_clips is None:
            prepared = render.prepare_render(
                plan, job["source"], audio_plan,
            )
            prepared_clips = prepared["clips"]
            prepared_total = prepared["total"]
        cues: list[dict] = _reel_cues(job, plan, prepared_clips)
        if captions:
            track_plan = {
                **plan,
                "clips": prepared_clips,
                "total": (
                    prepared_total
                    if prepared_total is not None
                    else sum(float(clip.get("duration") or 0.0) for clip in prepared_clips)
                ),
            }
            current_track = None
            if plan.get("_caption_track"):
                try:
                    current_track = caption_engine.CaptionTrack.from_dict(
                        plan["_caption_track"],
                    )
                except (TypeError, ValueError):
                    current_track = None
            prepared_hash = caption_engine.clip_hash(prepared_clips)
            if current_track is None:
                caption_track = _default_caption_track(
                    job_id, job, track_plan, margin=caption_margin,
                )
            elif current_track.clip_hash == prepared_hash:
                caption_track = current_track
            elif current_track.clip_hash == raw_clip_hash:
                caption_track = _caption_track_for_cut(
                    job, job_dir, current_track, plan.get("clips"), track_plan,
                )
            else:
                raise HTTPException(
                    409, "The caption track does not match this cut. Rebuild the track.",
                )
            _attach_caption_track(plan, caption_track)
            cues = [cue.to_dict() for cue in caption_track.cues]
        spec = artifacts.build_spec(
            job, plan,
            quality=quality, aspect=aspect, encoder=encoder,
            captions=captions, audio_sig=audio_sig, preset=preset,
            caption_margin=caption_margin,
            caption_style_key=(
                (plan.get("_caption_track") or {}).get("style_hash") or ""
            ),
            cues=cues,
            clips=prepared_clips,
            story_id=plan.get("story_id"),
            generation=generation,
            edit_hash=(edit or {}).get("hash") or "",
        )
        expected_id = artifacts.artifact_id(spec)
        if not artifacts.is_safe_artifact_id(artifact_id):
            artifact_id = expected_id
        if artifact_id != expected_id:
            LOGGER.warning(
                "artifact id mismatch for %s/%s (%s != %s)",
                job_id, record_key, artifact_id, expected_id,
            )
            artifact_id = expected_id
        manifest = artifacts.load_manifest(job_dir, artifact_id)
        if (
            manifest is not None
            and manifest.get("status") == "ready"
            and artifacts.has_media(job_dir, artifact_id)
        ):
            raise RuntimeError("Artifact already exists; refusing to overwrite it.")
        if manifest is None:
            manifest = artifacts.make_manifest(
                job_id, spec, status="queued", record_key=record_key,
                title=f"{Path(job['source']['name']).stem} · {target}s cut",
            )
            artifacts.assign_version(job_dir, manifest)
            manifest["caption_track_id"] = plan.get("_caption_key")
            manifest["caption_style_id"] = (plan.get("_caption_style") or {}).get("id")
            manifest["set_id"] = plan.get("clip_set_id")
            artifacts.save_manifest(job_dir, manifest)
        history_id = str(
            ((job.get("renders") or {}).get(record_key) or {}).get("history_id") or ""
        ) or None
        source = job["source"]["path"]
        meta = job["source"]
        title = f"{Path(job['source']['name']).stem} · {target}s cut"

        def progress(fraction: float, message: str) -> None:
            fraction = max(0.0, min(0.99, fraction))
            elapsed = time.time() - started
            eta = None
            if fraction > 0.03 and elapsed > 0.5:
                eta = round(elapsed / fraction * (1.0 - fraction), 1)
            _set_render(
                job_id, record_key, status="rendering",
                progress=round(fraction, 4), message=message,
                error=None, eta=eta, elapsed=round(elapsed, 1),
            )

        if cancel_event.is_set():
            raise render.RenderCancelled("Render cancelled.")
        before_usage = usage_store.snapshot()
        result = render.render_reel(
            source, meta, _job_dir(job_id), plan, title, progress,
            quality=quality, aspect=aspect, encoder=encoder,
            captions=captions, audio_plan=audio_plan, audio_sig=audio_sig,
            caption_margin=caption_margin,
            cancel_event=cancel_event,
            caption_cues=caption_engine.cue_tuples(cues),
            render_clips=prepared_clips,
            render_total=prepared_total,
            caption_style=plan.get("_caption_style"),
            edit=edit,
            output_size=(
                tuple(edit.get("output", {}).get(k) for k in ("width", "height"))
                if edit and edit.get("output") else None
            ),
        )
        result["caption_count"] = len(cues)
        render_delta = usage_store.delta(before_usage)
        _append_usage(job_id, "render", render_delta)
        _set_render(
            job_id, record_key,
            status="ready", progress=1.0, message="Reel ready",
            error=None, key=key, hook=plan["hook_scene"],
            total=prepared_total if prepared_total is not None else plan["total"],
            eta=0, audio_sig=audio_sig,
            preset=preset, caption_margin=caption_margin,
            usage=render_delta, artifact_id=artifact_id,
            resolved_encoder=spec.resolved_encoder,
            **result,
        )
        ready_record = {
            "status": "ready",
            "progress": 1.0,
            "message": "Reel ready",
            "error": None,
            "key": key,
            "hook": plan["hook_scene"],
            "total": prepared_total if prepared_total is not None else plan["total"],
            "eta": 0,
            "audio_sig": audio_sig,
            "preset": preset,
            "caption_margin": caption_margin,
            "usage": render_delta,
            "target": target,
            "quality": quality,
            "aspect": aspect,
            "encoder": spec.resolved_encoder,
            "resolved_encoder": spec.resolved_encoder,
            "captions": bool(captions),
            "record_key": record_key,
            "artifact_id": artifact_id,
            "created": round(time.time(), 3),
            "script_id": script_id,
            "caption_track_id": plan.get("_caption_key"),
            "caption_clip_hash": (plan.get("_caption_track") or {}).get("clip_hash"),
            "caption_style_id": (plan.get("_caption_style") or {}).get("id"),
            "cue_hash": (plan.get("_caption_track") or {}).get("cue_hash"),
            "style_hash": (plan.get("_caption_track") or {}).get("style_hash"),
            **result,
        }
        _record_render_history(
            job_id, ready_record, plan, audio_plan, "ready",
            script_id=script_id,
            latency_ms=round((time.time() - started) * 1000),
            entry_id=history_id,
            warning="; ".join(result.get("warnings") or []) or None,
        )
        try:
            artifacts.complete_artifact(
                job_dir, artifact_id,
                reel=job_dir / "renders" / str(result.get("path") or ""),
                poster=job_dir / "renders" / str(result.get("poster") or ""),
                srt=cuts.srt(cues), vtt=cuts.vtt(cues),
                render_info={**ready_record, "key": key},
            )
        except Exception:  # noqa: BLE001 - the legacy render stays usable
            LOGGER.exception("artifact finalize failed for %s/%s", job_id, artifact_id)
        LOGGER.info("render %s/%s ready in %s", job_id, record_key, result["path"])
        pruned: list[str] = []
        try:
            if _render_pruning_enabled():
                update_job(job_id, lambda value: pruned.extend(_prune_renders(value)))
        except shares.ShareStoreError:
            LOGGER.error("share store is unreadable; prune skipped for %s", job_id)
        if pruned:
            LOGGER.info("pruned %d old render file(s) for %s", len(pruned), job_id)
    except render.RenderCancelled:
        LOGGER.info("render %s/%s cancelled", job_id, record_key)
        if artifacts.is_safe_artifact_id(artifact_id):
            try:
                artifacts.mark_status(_job_dir(job_id), artifact_id, "cancelled")
            except Exception:  # noqa: BLE001
                LOGGER.exception("could not mark artifact cancelled")
        _set_render(
            job_id, record_key, status="cancelled", progress=1.0,
            message="Cancelled", error=None, eta=None,
        )
        _record_render_history(
            job_id,
            {
                "status": "cancelled",
                "target": target,
                "quality": quality,
                "aspect": aspect,
                "record_key": record_key,
                "audio_sig": audio_sig,
                "preset": preset,
                "message": "Cancelled",
                "error": None,
                "script_id": script_id,
            },
            plan, audio_plan, "cancelled",
            script_id=script_id,
            latency_ms=round((time.time() - started) * 1000),
            entry_id=history_id,
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("render failed for %s/%s", job_id, record_key)
        if artifacts.is_safe_artifact_id(artifact_id):
            try:
                artifacts.mark_status(
                    _job_dir(job_id), artifact_id, "failed", error=str(exc)[:2400],
                )
            except Exception:  # noqa: BLE001
                LOGGER.exception("could not mark artifact failed")
        _set_render(
            job_id, record_key, status="failed", progress=1.0,
            message="Render failed", error=str(exc)[:2400], eta=None,
        )
        _record_render_history(
            job_id,
            {
                "status": "failed",
                "target": target,
                "quality": quality,
                "aspect": aspect,
                "record_key": record_key,
                "audio_sig": audio_sig,
                "preset": preset,
                "message": "Render failed",
                "error": str(exc)[:2400],
                "script_id": script_id,
            },
            plan, audio_plan, "failed",
            script_id=script_id,
            error=str(exc)[:2400],
            latency_ms=round((time.time() - started) * 1000),
            entry_id=history_id,
        )
    finally:
        RENDER_CANCELS.pop((job_id, record_key), None)


def _stop_orphan_encoders() -> int:
    """Stop ffmpeg/ffprobe left running by a crashed VibeCut process.

    Encoders run in their own process group so a timeout can kill the whole
    tree, which also means they outlive a SIGKILL of the server. Any encoder
    still writing under this data directory at startup is an orphan.
    """
    marker = str(JOBS)
    try:
        listing = subprocess.run(
            ["ps", "-axo", "pid=,ppid=,command="],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return 0
    stopped = 0
    for line in listing.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) < 3 or not parts[0].isdigit():
            continue
        pid, command = int(parts[0]), parts[2]
        name = Path(command.split(" ", 1)[0]).name
        if name not in {"ffmpeg", "ffprobe"} or marker not in command or pid == os.getpid():
            continue
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (OSError, ProcessLookupError):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                continue
        stopped += 1
    if stopped:
        LOGGER.warning("stopped %d orphaned encoder process(es) from a previous run", stopped)
    return stopped


def _manifest_record_key(manifest: dict, job: dict | None = None) -> str:
    """The render key a queued manifest was created under, or derive it."""
    key = str(manifest.get("record_key") or "").strip()
    if key:
        return key
    spec = manifest.get("spec") or {}
    try:
        target = int(spec.get("target") or 0)
    except (TypeError, ValueError):
        return ""
    if target <= 0:
        return ""
    caption = spec.get("caption") or {}
    hook = None
    if spec.get("hook_override") and spec.get("hook_scene") is not None:
        try:
            hook = int(spec.get("hook_scene"))
        except (TypeError, ValueError):
            hook = None
    story_id = str(spec.get("story_id") or "") or None
    ignored = {str(manifest.get("job_id") or "")}
    if job is not None:
        ignored |= {
            str(job.get("id") or ""),
            str(job.get("story_id") or ""),
        }
    ignored.discard("")
    if story_id in ignored:
        story_id = None
    return _render_key(
        target,
        str(spec.get("quality") or "final"),
        str(spec.get("aspect") or "9:16"),
        bool(caption.get("enabled")),
        str(spec.get("audio_sig") or ""),
        hook,
        story_id=story_id,
    )


def _manifest_caption_track(job_dir: Path, manifest: dict):
    """Recover the exact track a queued captioned manifest used.

    New manifests carry ``caption_track_id``. Older manifests only carry the
    style/cue/clip hashes, so an exact, unique track match is required. A
    near-match is refused: retry must not silently burn a different track.
    """
    spec = manifest.get("spec") or {}
    caption = spec.get("caption") or {}
    if not caption.get("enabled"):
        return None
    track_id = str(manifest.get("caption_track_id") or "")
    if track_id:
        track = caption_engine.load_track(job_dir, track_id)
        if track is not None:
            return track
    wanted_clip = caption_engine.clip_hash(spec.get("clips") or [])
    wanted_cue = str(caption.get("cue_hash") or "")
    wanted_style = str(caption.get("style_hash") or "")
    try:
        target = int(spec.get("target") or 0)
    except (TypeError, ValueError):
        target = 0
    try:
        margin = float(caption.get("margin") or 0.075)
    except (TypeError, ValueError):
        margin = 0.075
    presets = (None, *render.PRESETS.keys())
    matches = []
    try:
        rows = caption_engine.list_tracks(job_dir)
    except Exception:  # noqa: BLE001 - recovery must not fail on one bad track
        rows = []
    for row in rows:
        track = caption_engine.load_track(job_dir, str(row.get("id") or ""))
        if track is None or int(track.target or 0) != target:
            continue
        if track.clip_hash != wanted_clip:
            continue
        cue_hash, _text_hash = artifacts.cue_hashes(
            cue.to_dict() for cue in track.cues
        )
        if cue_hash != wanted_cue:
            continue
        if not any(
            artifacts.style_hash(preset, margin, track.style_hash) == wanted_style
            for preset in presets
        ):
            continue
        matches.append(track)
    return matches[0] if len(matches) == 1 else None


def _recovery_story_identity(
    job: dict,
    spec_story_id: object,
) -> tuple[str | None, str | None]:
    """Resolve a manifest's story id without treating a job id as a story.

    ``artifacts.build_spec`` falls back to the job id when no caller story id
    exists, so that value is not evidence of a story render. A real story id
    must also match the job's clip sets when they are present.
    """
    story_id = str(spec_story_id or "")
    ignored = {
        str(job.get("id") or ""),
        str(job.get("story_id") or ""),
    }
    ignored.discard("")
    if not story_id or story_id in ignored:
        return None, None
    rows: list[tuple[str, str]] = []
    has_clip_sets = False
    for record in _clip_set_records(job):
        has_clip_sets = True
        set_id = str(record.get("id") or "")
        for story in record.get("stories") or []:
            if not isinstance(story, dict):
                continue
            candidate = str(story.get("id") or "")
            if candidate == story_id:
                rows.append((set_id, candidate))
    if not has_clip_sets:
        return story_id, None
    if not rows:
        return None, None
    set_ids = {row[0] for row in rows}
    if len(set_ids) == 1:
        return story_id, rows[0][0]
    return story_id, None


def _recovered_manifest_record(
    manifest: dict,
    job: dict,
    job_dir: Path,
) -> dict:
    """Project an orphan queued/rendering manifest back into a retryable record."""
    spec = manifest.get("spec") or {}
    caption = spec.get("caption") or {}
    clips = [
        dict(clip) for clip in (spec.get("clips") or [])
        if isinstance(clip, dict)
    ]
    try:
        target = int(spec.get("target") or manifest.get("target") or 0)
    except (TypeError, ValueError):
        target = 0
    error = "The server restarted while this reel was rendering."
    track = _manifest_caption_track(job_dir, manifest)
    captions = bool(caption.get("enabled"))
    auto = not bool(spec.get("hook_override"))
    story_id, set_id = _recovery_story_identity(job, spec.get("story_id"))
    if story_id and not set_id:
        set_id = str(manifest.get("set_id") or "") or None
    if not story_id:
        set_id = None
    record = artifacts.render_record(manifest)
    record.update({
        "status": "interrupted",
        "progress": 0.0,
        "message": "Interrupted",
        "error": error,
        "target": target,
        "total": round(sum(
            float(clip.get("dur") or clip.get("duration") or 0.0)
            for clip in clips
        ), 3),
        "story_id": story_id or None,
        "set_id": set_id or None,
        "captions": captions,
        "caption_margin": float(caption.get("margin") or 0.075),
        "caption_track_id": track.id if track is not None else None,
        "caption_clip_hash": (
            track.clip_hash if track is not None
            else caption_engine.clip_hash(clips) if captions else None
        ),
        "caption_style_id": (
            track.style_id if track is not None
            else manifest.get("caption_style_id")
        ),
        "cue_hash": (
            track.cue_hash if track is not None
            else str(caption.get("cue_hash") or "") or None
        ),
        "style_hash": (
            track.style_hash if track is not None
            else str(caption.get("style_hash") or "") or None
        ),
        "attempts": 0,
        "plan_snapshot": {
            "target": target,
            "hook_scene": spec.get("hook_scene"),
            "order": str(spec.get("order") or "source"),
            "auto": auto,
            "clips": clips,
            "story_id": story_id or None,
            "set_id": set_id or None,
        },
        "recovered_from_manifest": True,
    })
    record["recoverable"] = bool(clips) and (not captions or track is not None)
    if not record["recoverable"]:
        if captions and track is None:
            record["recovery_error"] = (
                "The original caption track is missing; retry would change the captions."
            )
        else:
            record["recovery_error"] = (
                "The interrupted render has no stored plan clips to retry."
            )
    artifacts.ensure_job_schema(job, job_dir)
    return record


def _reconcile_orphan_manifests(job: dict, job_dir: Path) -> bool:
    """Tie queued/rendering manifests to a retryable interrupted record.

    A crash can leave an artifact manifest queued while ``job.json`` has no
    record for it. Retry only sees records, so the orphan would be stuck. The
    recovered record is always ``interrupted`` and never ``ready``.
    """
    changed = False
    manifests = artifacts.list_manifests(job_dir)
    if not manifests:
        return changed
    renders = job.get("renders")
    if not isinstance(renders, dict):
        renders = {}
        job["renders"] = renders
    for manifest in manifests:
        if str(manifest.get("status") or "") not in ACTIVE_RENDER:
            continue
        artifact = str(manifest.get("artifact_id") or "")
        error = "The server restarted while this reel was rendering."
        try:
            marked = artifacts.mark_status(
                job_dir, artifact, "interrupted", error=error,
            )
            changed = True
        except Exception:  # noqa: BLE001 - keep scanning other artifacts
            LOGGER.exception("could not interrupt artifact %s", artifact)
            continue
        if marked is not None:
            manifest = marked
        existing_key = next(
            (
                str(key) for key, record in renders.items()
                if isinstance(record, dict)
                and str(record.get("artifact_id") or "") == artifact
            ),
            "",
        )
        key = existing_key or _manifest_record_key(manifest, job)
        if not key:
            continue
        current = renders.get(key)
        if current is not None and not isinstance(current, dict):
            continue
        if current is not None and str(current.get("artifact_id") or "") not in ("", artifact):
            # Another render owns this key; never overwrite a real record.
            continue
        if current is None:
            renders[key] = _recovered_manifest_record(manifest, job, job_dir)
            changed = True
            continue
        if current.get("status") in ACTIVE_RENDER or current.get("status") == "ready":
            current.update({
                "status": "interrupted",
                "progress": 0.0,
                "message": "Interrupted",
                "error": error,
            })
            changed = True
        if str(current.get("artifact_id") or "") == artifact:
            current.setdefault("story_id", str(
                (manifest.get("spec") or {}).get("story_id") or ""
            ) or None)
    return changed


def recover_jobs() -> None:
    _stop_orphan_encoders()
    RENDER_CANCELS.clear()
    ANALYSIS_CANCELS.clear()
    fixed = 0
    for path in JOBS.glob("*/job.json"):
        try:
            with LOCK:
                job = json.loads(path.read_text())
                changed = False
                ingest_failed = False
                if job.get("status") in LIVE:
                    job["status"] = "interrupted"
                    job["message"] = "Interrupted"
                    job["error"] = "The server restarted while this job was running."
                    ingest = job.get("ingest")
                    if isinstance(ingest, dict):
                        ingest.update({
                            "phase": "interrupted",
                            "status": "interrupted",
                            "progress": 1.0,
                            "message": "Interrupted",
                            "error": job["error"],
                        })
                        ingest_failed = bool(ingest.get("source_url"))
                    changed = True
                for record in (job.get("renders") or {}).values():
                    if record.get("status") in ACTIVE_RENDER:
                        record["status"] = "interrupted"
                        record["message"] = "Interrupted"
                        record["error"] = "The server restarted while this reel was rendering."
                        changed = True
                        artifact = str(record.get("artifact_id") or "")
                        if artifacts.is_safe_artifact_id(artifact):
                            try:
                                artifacts.mark_status(
                                    _job_dir(job["id"]), artifact, "interrupted",
                                    error=record["error"],
                                )
                            except Exception:  # noqa: BLE001
                                LOGGER.exception(
                                    "could not interrupt artifact %s for %s",
                                    artifact, job["id"],
                                )
                        _record_render_history(
                            job["id"], record,
                            {"target": record.get("target"), "clips": []},
                            record.get("audio"), "interrupted",
                            script_id=record.get("script_id"),
                            error=record["error"],
                            latency_ms=0,
                            entry_id=record.get("history_id"),
                        )
                try:
                    if _reconcile_orphan_manifests(job, _job_dir(job["id"])):
                        changed = True
                except Exception:  # noqa: BLE001
                    LOGGER.exception(
                        "could not reconcile interrupted artifacts for %s",
                        job.get("id"),
                    )
                if changed:
                    _save_unlocked(job)
                    if ingest_failed:
                        ingest = job.get("ingest") or {}
                        _record_ingest_history(
                            job["id"],
                            str(ingest.get("provider") or ""),
                            str(ingest.get("source_url") or ""),
                            "interrupted",
                            error=job.get("error"),
                        )
                    fixed += 1
        except Exception:
            continue
    try:
        for job_dir in (path.parent for path in JOBS.glob("*/job.json")):
            try:
                for manifest in artifacts.list_manifests(job_dir):
                    status = str(manifest.get("status") or "")
                    if status not in {"queued", "rendering"}:
                        continue
                    artifacts.mark_status(
                        job_dir, str(manifest.get("artifact_id") or ""),
                        "interrupted",
                        error="The server restarted while this reel was rendering.",
                    )
            except Exception:  # noqa: BLE001
                LOGGER.exception("could not recover artifacts in %s", job_dir)
    except Exception:  # noqa: BLE001
        LOGGER.exception("could not scan artifact manifests")
    try:
        paused_batches = batch_store.recover_batches(DATA)
        if paused_batches:
            LOGGER.info("paused %d interrupted batch(es)", paused_batches)
    except Exception:  # noqa: BLE001
        LOGGER.exception("could not recover batches")
    try:
        paused_stories = story_queues().recover()
        if paused_stories:
            LOGGER.info("paused %d interrupted story queue(s); resume is manual", paused_stories)
    except Exception:  # noqa: BLE001
        LOGGER.exception("could not recover story queues")
    for tmp in JOBS.glob("*/renders/tmp_*"):
        shutil.rmtree(tmp, ignore_errors=True)
    if SOURCES.is_dir():
        for pattern in (
            ".ingest-*", "ingest-*",
            ".incoming-*", "incoming-*",
        ):
            for stale in SOURCES.glob(pattern):
                try:
                    if stale.is_dir():
                        shutil.rmtree(stale, ignore_errors=True)
                    else:
                        stale.unlink(missing_ok=True)
                except OSError:
                    pass
        for pattern in (".*.part", "*.part"):
            for stale in SOURCES.glob(pattern):
                try:
                    stale.unlink(missing_ok=True)
                except OSError:
                    pass
    if fixed:
        LOGGER.info("recovered %d interrupted job(s)", fixed)


def _active_share_state(
    job_id: str,
    *,
    strict: bool = False,
) -> tuple[set[str], list[tuple[int, str]]]:
    try:
        records = shares.active_records(SHARES, job_id=job_id, strict=strict)
    except shares.ShareStoreError:
        if strict:
            raise
        return set(), []
    except Exception:  # noqa: BLE001 - read paths must not block on a broken file
        if strict:
            raise
        return set(), []
    artifact_ids: set[str] = set()
    legacy: list[tuple[int, str]] = []
    for record in records:
        artifact = str(record.get("artifact_id") or "")
        if artifact:
            artifact_ids.add(artifact)
            continue
        try:
            target = int(record.get("target"))
        except (TypeError, ValueError):
            continue
        legacy.append((target, str(record.get("aspect") or "9:16")))
    return artifact_ids, legacy


def _collect_artifact_refs(value, found: set[str]) -> None:
    if isinstance(value, str):
        for match in artifacts.ARTIFACT_RE.finditer(value):
            found.add(match.group(0))
    elif isinstance(value, dict):
        for item in value.values():
            _collect_artifact_refs(item, found)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            _collect_artifact_refs(item, found)


def _packet_disk_refs(job_id: str) -> set[str]:
    """Artifact ids referenced by packets already written to disk.

    Older jobs may not have ``packet_refs`` in ``job.json`` yet. Reading the
    packet manifests keeps those packets protected without a migration and
    without rewriting the packet store.
    """
    found: set[str] = set()
    root = _job_dir(job_id) / packet.PACKET_ROOT
    if not root.is_dir():
        return found
    try:
        directories = list(root.iterdir())
    except OSError:
        return found
    for directory in directories:
        if not directory.is_dir() or not packet.PACKET_ID_RE.fullmatch(directory.name):
            continue
        try:
            manifest = json.loads(
                (directory / "packet.json").read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(manifest, dict):
            continue
        if str(manifest.get("packet_id") or "") != directory.name:
            continue
        _collect_artifact_refs(manifest.get("media"), found)
    return found


def _packet_artifact_ids(job: dict, manifests: list[dict] | None = None) -> set[str]:
    found: set[str] = set()
    for key in ("packet", "packets", "packet_refs", "packet_artifact_ids"):
        _collect_artifact_refs(job.get(key), found)
    for manifest in manifests or []:
        _collect_artifact_refs(manifest.get("packet_refs"), found)
    try:
        found |= _packet_disk_refs(str(job.get("id") or ""))
    except Exception:  # noqa: BLE001 - a broken packet must not unlock deletion
        LOGGER.exception("could not read packet refs for %s", job.get("id"))
    return found


def _adopt_legacy_shares(job: dict) -> list[dict]:
    """Bind active target/aspect shares to artifact ids before destructive work.

    Returns the active records that could not be bound. Callers must preserve
    their render files or abort. Raises when the share store is unreadable.
    """
    records = shares.active_records(
        SHARES, job_id=job["id"], strict=True,
    )
    remaining: list[dict] = []
    for record in records:
        if record.get("artifact_id"):
            continue
        try:
            target = int(record.get("target"))
        except (TypeError, ValueError):
            remaining.append(record)
            continue
        aspect = str(record.get("aspect") or "9:16")
        manifest = _find_artifact_for_target(
            job, target, aspect, not_after=float(record.get("created") or 0.0),
        )
        if (
            manifest is None
            or manifest.get("status") != "ready"
            or not artifacts.has_media(
                _job_dir(job["id"]), str(manifest.get("artifact_id") or ""),
            )
        ):
            remaining.append(record)
            continue
        artifact = str(manifest.get("artifact_id") or "")
        token = str(record.get("token") or "")
        if not artifacts.is_safe_artifact_id(artifact) or not token:
            remaining.append(record)
            continue
        bound = shares.bind_artifact(token, artifact, SHARES)
        if bound is None or not bound.get("artifact_id"):
            remaining.append(record)
    return remaining


def _protected_artifact_ids(
    job: dict,
    manifests: list[dict] | None = None,
    *,
    strict_shares: bool = False,
) -> set[str]:
    manifests = manifests if manifests is not None else artifacts.list_manifests(_job_dir(job["id"]))
    protected = {
        str(manifest.get("artifact_id"))
        for manifest in manifests
        if manifest.get("pinned") and artifacts.is_safe_artifact_id(manifest.get("artifact_id"))
    }
    shared, legacy = _active_share_state(job["id"], strict=strict_shares)
    protected |= {item for item in shared if artifacts.is_safe_artifact_id(item)}
    protected |= _packet_artifact_ids(job, manifests)
    for record in (job.get("renders") or {}).values():
        if not isinstance(record, dict) or not record.get("pinned"):
            continue
        artifact = str(record.get("artifact_id") or "")
        if artifacts.is_safe_artifact_id(artifact):
            protected.add(artifact)
    for manifest in manifests:
        spec = manifest.get("spec") or {}
        pair = (int(spec.get("target") or 0), str(spec.get("aspect") or "9:16"))
        if pair in legacy:
            artifact = str(manifest.get("artifact_id") or "")
            if artifacts.is_safe_artifact_id(artifact):
                protected.add(artifact)
    return protected


def _has_active_artifacts(job: dict) -> bool:
    try:
        manifests = artifacts.list_manifests(_job_dir(job["id"]))
    except Exception:  # noqa: BLE001
        return False
    return any(
        manifest.get("status") in ACTIVE_RENDER
        for manifest in manifests
    )


def _job_has_protection(job: dict, *, strict_shares: bool = True) -> bool:
    try:
        manifests = artifacts.list_manifests(_job_dir(job["id"]))
    except Exception:  # noqa: BLE001
        manifests = []
    if _protected_artifact_ids(
        job, manifests, strict_shares=strict_shares,
    ):
        return True
    try:
        return bool(shares.active_records(
            SHARES, job_id=job["id"], strict=strict_shares,
        ))
    except shares.ShareStoreError:
        if strict_shares:
            raise
        return False
    except Exception:  # noqa: BLE001
        if strict_shares:
            raise
        return False


def _record_hook(record: dict, key: str | None = None) -> int | None:
    for field in ("hook", "hook_scene", "hook_marker"):
        value = record.get(field)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    for candidate in (record.get("record_key"), key):
        match = re.search(r"(?:^|:)h(\d+)$", str(candidate or ""))
        if match:
            return int(match.group(1))
    return None


def _safe_unlink(job_dir: Path, name: str | None) -> str | None:
    path = _job_media_path(job_dir, name)
    if path is None:
        return None
    try:
        path.unlink()
        return str(name)
    except OSError:
        return None


def _render_pruning_enabled() -> bool:
    """Rendered artifacts are immutable outputs, not caches.

    Pruning older cuts is opt-in (``VIBECUT_PRUNE_RENDERS=1``) so a superseded
    v1 is never deleted behind the owner's back, after a render or on the
    retention pass.
    """
    return os.environ.get("VIBECUT_PRUNE_RENDERS", "0").lower() not in (
        "0", "false", "no", "off", "",
    )


def _prune_renders(job: dict) -> list[str]:
    """Keep hook variants, pinned artifacts, live shares and newest finals.

    Grouping is ``(story_id, target, quality, aspect, captions, audio_sig,
    hook_scene)``. Protected records stay even when they are older than the
    retention window for their group.
    """
    renders = job.get("renders") or {}
    job_dir = _job_dir(job["id"])
    manifests = artifacts.list_manifests(job_dir)
    protected_ids = _protected_artifact_ids(
        job, manifests, strict_shares=True,
    )
    _shared, legacy_targets = _active_share_state(job["id"], strict=True)
    if not renders:
        return []
    protected_manifests = [
        manifest for manifest in manifests
        if str(manifest.get("artifact_id") or "") in protected_ids
    ]
    try:
        keep_finals = max(1, int(os.environ.get("VIBECUT_KEEP_RENDERS", "1") or 1))
    except ValueError:
        keep_finals = 1
    keep_drafts = (os.environ.get("VIBECUT_KEEP_DRAFTS", "0") or "0").lower() not in (
        "0", "false", "no", "off", "",
    )

    def protected(record: dict) -> bool:
        if record.get("pinned"):
            return True
        artifact = str(record.get("artifact_id") or "")
        if artifact and artifact in protected_ids:
            return True
        try:
            target = int(record.get("target"))
        except (TypeError, ValueError):
            return False
        aspect = str(record.get("aspect") or "9:16")
        if (target, aspect) in legacy_targets:
            return True
        # A legacy projection may not know its artifact id yet. Match the
        # protected artifact's identity fields so a live share cannot lose its
        # only render record.
        hook = _record_hook(record)
        for manifest in protected_manifests:
            spec = manifest.get("spec") or {}
            caption = spec.get("caption") or {}
            if int(spec.get("target") or 0) != target:
                continue
            if str(spec.get("aspect") or "9:16") != aspect:
                continue
            if str(spec.get("quality") or "final") != (record.get("quality") or "final"):
                continue
            if bool(caption.get("enabled")) != bool(record.get("captions")):
                continue
            if (spec.get("audio_sig") or "") != (record.get("audio_sig") or ""):
                continue
            if hook is not None and spec.get("hook_scene") != hook:
                continue
            return True
        return False

    story_id = str(job.get("story_id") or job.get("id") or "")
    finals_groups: dict[tuple, list[tuple[float, str]]] = {}
    drafts_groups: dict[tuple, list[tuple[float, str]]] = {}
    for key, record in renders.items():
        if not record or record.get("status") != "ready":
            continue
        mix = (
            story_id,
            record.get("target"),
            record.get("aspect", "9:16"),
            bool(record.get("captions")),
            record.get("audio_sig") or "",
            _record_hook(record, key),
        )
        if (record.get("quality") or "final") == "draft":
            drafts_groups.setdefault(mix, []).append(
                (float(record.get("updated") or 0), key)
            )
        else:
            group = (mix[0], mix[1], record.get("quality") or "final", *mix[2:])
            finals_groups.setdefault(group, []).append(
                (float(record.get("updated") or 0), key)
            )

    doomed: list[str] = []
    for entries in finals_groups.values():
        finals = sorted(entries, reverse=True)
        doomed.extend(
            key for _updated, key in finals[keep_finals:]
            if not protected(renders[key])
        )
    for mix, entries in drafts_groups.items():
        drafts = sorted(entries, reverse=True)
        has_final = (
            mix[0], mix[1], mix[2], mix[3], mix[4], mix[5],
        ) in {
            (key[0], key[1], key[3], key[4], key[5], key[6])
            for key in finals_groups
        }
        if keep_drafts:
            doomed.extend(
                key for _updated, key in drafts[1:]
                if not protected(renders[key])
            )
        elif has_final:
            # A draft is redundant once a final exists for the same mix.
            doomed.extend(
                key for _updated, key in drafts
                if not protected(renders[key])
            )
    removed: list[str] = []
    for key in doomed:
        record = renders.pop(key, None) or {}
        artifact = str(record.get("artifact_id") or "")
        for name in (record.get("path"), record.get("poster")):
            item = _safe_unlink(job_dir, name)
            if item:
                removed.append(item)
        if artifacts.is_safe_artifact_id(artifact) and artifact not in protected_ids:
            still_used = any(
                isinstance(other, dict) and other.get("artifact_id") == artifact
                for other in renders.values()
            )
            if not still_used and artifacts.delete_artifact(job_dir, artifact):
                table = job.get("artifacts")
                if isinstance(table, dict):
                    table.pop(artifact, None)
    # A new render can replace the projection key before the older artifact is
    # pruned. Remove those orphans, but never a pinned or live shared copy.
    referenced = {
        str(record.get("artifact_id"))
        for record in renders.values()
        if isinstance(record, dict) and record.get("artifact_id")
    }
    for manifest in manifests:
        artifact = str(manifest.get("artifact_id") or "")
        if not artifacts.is_safe_artifact_id(artifact):
            continue
        if artifact in referenced or artifact in protected_ids:
            continue
        if manifest.get("record_key") not in renders:
            continue
        if manifest.get("status") in ACTIVE_RENDER:
            continue
        if artifacts.delete_artifact(job_dir, artifact):
            table = job.get("artifacts")
            if isinstance(table, dict):
                table.pop(artifact, None)
    artifacts.ensure_job_schema(job, job_dir)
    return removed


def clean_job_files(job: dict, profile: str = "workfiles") -> list[str]:
    """Delete working files for one job. Source video and job.json stay.

    Pinned artifacts, live share targets and packet references are never
    removed. The final artifacts live under ``artifacts/`` and are unaffected
    by deleting the legacy ``renders/`` projection.
    """
    directory = _job_dir(job["id"])
    removed: list[str] = []
    if _has_active_artifacts(job):
        raise HTTPException(409, "An artifact is still rendering.")
    shares.load(SHARES, strict=True)
    render_profile = profile in {"renders", "all"}
    if render_profile:
        remaining = _adopt_legacy_shares(job)
        if remaining:
            LOGGER.warning(
                "clean blocked for %s: %d live legacy share target(s) could not be adopted",
                job["id"], len(remaining),
            )
            raise HTTPException(
                409,
                "Live review links cannot be preserved for this clean; adopt or revoke them first.",
            )
    work = ("thumbs", "transcript", "audio")
    if profile in {"workfiles", "all"}:
        for name in work:
            target = directory / name
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
                removed.append(name)
        analysis = job.get("analysis")
        if analysis:
            for scene in analysis.get("scenes", []):
                scene["deep"] = False
            analysis["deep_count"] = 0
            analysis["deep_scene_ids"] = []
    if render_profile:
        manifests = artifacts.list_manifests(directory)
        protected = _protected_artifact_ids(
            job, manifests, strict_shares=True,
        )
        kept: dict[str, dict] = {}
        deleted_artifacts = False
        for manifest in manifests:
            artifact = str(manifest.get("artifact_id") or "")
            if artifact in protected:
                kept[artifact] = manifest
                continue
            if not artifacts.delete_artifact(directory, artifact):
                kept[artifact] = manifest
                continue
            deleted_artifacts = True
        if deleted_artifacts:
            removed.append("artifacts")
        target = directory / "renders"
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
            removed.append("renders")
        masters = DATA / "cache" / "masters" / job["id"]
        if masters.exists():
            shutil.rmtree(masters, ignore_errors=True)
            removed.append("masters")
        projections: dict[str, dict] = {}
        for artifact, manifest in kept.items():
            key = str(manifest.get("record_key") or artifact)
            if key in projections:
                key = f"{key}:{artifact[-8:]}"
            projections[key] = artifacts.render_record(manifest)
        job["renders"] = projections
        job["artifacts"] = {
            artifact: artifacts.manifest_summary(manifest)
            for artifact, manifest in kept.items()
        }
        job["artifact_ids"] = sorted(kept)
    return removed


def cleanup_storage() -> None:
    """Retention for old jobs, job working files and the caches."""
    try:
        days = float(os.environ.get("VIBECUT_RETENTION_DAYS", "0") or 0)
    except ValueError:
        days = 0.0
    try:
        clean_days = float(os.environ.get("VIBECUT_JOB_CLEAN_DAYS", "0") or 0)
    except ValueError:
        clean_days = 0.0
    try:
        shares.load(SHARES, strict=True)
    except shares.ShareStoreError:
        LOGGER.error("share store is unreadable; retention aborted")
        return
    if days > 0:
        cutoff = time.time() - days * 86400
        for path in JOBS.glob("*/job.json"):
            job_id = path.parent.name
            removed_job = False
            try:
                with LOCK:
                    job = _load_unlocked(job_id)
                    if job.get("status") in LIVE or _has_active_artifacts(job):
                        continue
                    if any(
                        record.get("status") in ACTIVE_RENDER
                        for record in (job.get("renders") or {}).values()
                    ):
                        continue
                    if float(job.get("updated", 0) or 0) >= cutoff:
                        continue
                    protected = _job_has_protection(job)
                    if protected:
                        LOGGER.info("retention kept protected job %s", job_id)
                        continue
                    shutil.rmtree(path.parent, ignore_errors=True)
                    removed_job = True
            except (HTTPException, OSError, json.JSONDecodeError):
                continue
            except shares.ShareStoreError:
                LOGGER.error("share store is unreadable; retention aborted")
                return
            if removed_job:
                LOGGER.info("retention removed job %s", job_id)
    if clean_days > 0:
        cutoff = time.time() - clean_days * 86400
        for path in JOBS.glob("*/job.json"):
            job_id = path.parent.name
            removed: list[str] = []
            try:
                with LOCK:
                    job = _load_unlocked(job_id)
                    if job.get("status") in LIVE:
                        continue
                    if float(job.get("updated", 0) or 0) >= cutoff:
                        continue
                    removed = clean_job_files(job, "workfiles")
                    if removed:
                        _save_unlocked(job)
            except (HTTPException, OSError, json.JSONDecodeError):
                continue
            except shares.ShareStoreError:
                LOGGER.error("share store is unreadable; workfile cleanup aborted")
                return
            if removed:
                LOGGER.info("cleaned %s for job %s", ", ".join(removed), job_id)
    for path in (JOBS.glob("*/job.json") if _render_pruning_enabled() else ()):
        job_id = path.parent.name
        removed: list[str] = []
        try:
            with LOCK:
                job = _load_unlocked(job_id)
                if (
                    job.get("status") in LIVE
                    or not job.get("renders")
                    or _has_active_artifacts(job)
                ):
                    continue
                removed = _prune_renders(job)
                if removed:
                    _save_unlocked(job)
        except (HTTPException, OSError, json.JSONDecodeError):
            continue
        except shares.ShareStoreError:
            LOGGER.error("share store is unreadable; render retention aborted")
            return
        if removed:
            LOGGER.info("render retention removed %d file(s) for %s", len(removed), job_id)
    try:
        cache_days = float(os.environ.get("VIBECUT_CACHE_DAYS", "14") or 0)
    except ValueError:
        cache_days = 14.0
    try:
        cache_max_gb = float(os.environ.get("VIBECUT_CACHE_MAX_GB", "2") or 0)
    except ValueError:
        cache_max_gb = 2.0
    removed_sources = gc_sources()
    if removed_sources:
        LOGGER.info("source store GC removed %d entries", removed_sources)
    result = audio.prune_cache(max_gb=cache_max_gb, days=cache_days)
    if result["removed"]:
        LOGGER.info(
            "cache prune removed %d files (%.1f MB)",
            result["removed"], result["freed_mb"],
        )
    try:
        removed_audit = admin_store.prune_audit()
        removed_pipeline = admin_store.prune_pipeline_events()
        removed_sessions = admin_store.prune_sessions()
        if removed_audit or removed_pipeline or removed_sessions:
            LOGGER.info(
                "admin retention removed audit=%d pipeline=%d sessions=%d",
                removed_audit, removed_pipeline, removed_sessions,
            )
    except Exception:  # noqa: BLE001
        LOGGER.exception("admin retention pass failed")


def _retention_loop() -> None:
    while True:
        time.sleep(3600)
        try:
            cleanup_storage()
        except Exception:  # noqa: BLE001
            LOGGER.exception("retention pass failed")


# ---------------------------------------------------------------- lifespan


@asynccontextmanager
async def lifespan(_: FastAPI):
    JOBS.mkdir(parents=True, exist_ok=True)
    # Migrate before recover_jobs restarts workers: migration rewrites
    # job.json without the job lock, so nothing else may be writing yet.
    migrations.migrate_all(JOBS)
    recover_jobs()
    cleanup_storage()
    threading.Thread(target=_retention_loop, daemon=True).start()
    threading.Thread(target=vision.available, daemon=True).start()
    yield


class _RevalidatedStatic(StaticFiles):
    """Static files that the browser must revalidate on every load.

    Studio is unversioned native ES modules. Without this header browsers
    cache them heuristically, so after an update one page can mix old and new
    modules. ETag revalidation keeps unchanged files at a cheap 304.
    """

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app = FastAPI(title="VibeCut", lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount("/static", _RevalidatedStatic(directory=STATIC), name="static")
app.include_router(admin_routes.router)
app.include_router(routes_batches.router)
app.include_router(routes_check.router)
app.include_router(routes_cleanup.router)
app.include_router(routes_cleanup.rights_router)
app.include_router(routes_edits.router)
app.include_router(__import__("routes_trim", fromlist=["router"]).router)
app.include_router(routes_overlays.router)
app.include_router(routes_voice_clone.router)
# Studio owns its page, so its build skips the Classic router entirely.
if not STUDIO_APP:
    app.include_router(routes_classic.router)
# Lane modules: new routes go here, not into app.py (docs/branching.md).
app.include_router(routes_auto_subs.router)
app.include_router(routes_studio.router)
app.include_router(music.router)
routes_library.install(app, JOBS)
app.include_router(packet.router)
app.include_router(preflight.router)


@app.exception_handler(disk.InsufficientSpace)
async def insufficient_space(_: Request, exc: disk.InsufficientSpace) -> JSONResponse:
    return JSONResponse(status_code=412, content=exc.as_dict())


# ---------------------------------------------------------------- auth


PUBLIC_PATHS = {"/", "/index.html", "/classic", "/voices", "/favicon.ico", "/api/health", "/docs/url-ingest.md"}
SHARES = DATA / "shares.json"


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
CLEANUP_PLAN_PATH = re.compile(r"^/api/jobs/[^/]+/cleanup/plan/?$")


@app.middleware("http")
async def gate_cleanup(request: Request, call_next):
    """Hide cleanup before FastAPI parses a body or validates content type."""
    if (
        CLEANUP_PLAN_PATH.fullmatch(request.url.path)
        and not routes_cleanup.cleanup_enabled()
    ):
        return JSONResponse(
            {"detail": "Cleanup is not enabled in this build."},
            status_code=404,
        )
    return await call_next(request)


@app.middleware("http")
async def require_token(request: Request, call_next):
    """Default-deny for every creator route.

    Loopback binds need no token. Any other bind needs ``VIBECUT_TOKEN``, sent
    as a bearer header. Tokens never travel in URLs; the ``vibecut_token``
    cookie only authorises reads, so ``<img>``/``<video>`` work without
    making cross-site writes possible. ``/_ductator`` has its own password,
    session and CSRF checks.
    """
    path = request.url.path
    if path.startswith("/_ductator"):
        return await call_next(request)
    if path in PUBLIC_PATHS or path.startswith("/static") or path.startswith("/r/"):
        return await call_next(request)
    token = os.environ.get("VIBECUT_TOKEN")
    if not token:
        if HOST in LOOPBACK_HOSTS:
            return await call_next(request)
        return JSONResponse(
            {
                "detail": (
                    "VibeCut is bound beyond loopback without VIBECUT_TOKEN. "
                    "Set VIBECUT_TOKEN before using the API remotely."
                )
            },
            status_code=403,
        )
    supplied = request.headers.get("authorization") or ""
    supplied = supplied[7:].strip() if supplied.lower().startswith("bearer ") else ""
    if not supplied and request.method in SAFE_METHODS:
        supplied = unquote(request.cookies.get("vibecut_token") or "")
    if not supplied or not hmac.compare_digest(supplied.encode(), token.encode()):
        return JSONResponse(
            {"detail": "Unauthorized. Provide VIBECUT_TOKEN."},
            status_code=401,
        )
    return await call_next(request)


@app.middleware("http")
async def audit_admin_requests(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/_ductator/api"):
        return await call_next(request)
    started = time.time()
    request_id = str(request.headers.get("x-request-id") or uuid.uuid4().hex[:12])
    try:
        response = await call_next(request)
    except Exception:
        elapsed = (time.time() - started) * 1000
        try:
            session = admin_store.get_session(str(request.cookies.get("vibecut_admin") or ""))
            admin_store.record_audit(
                session["email"] if session else "anonymous",
                "http.request",
                resource_type="admin_api",
                resource_id=path,
                outcome="error",
                ip=str(getattr(request.client, "host", "") or ""),
                user_agent=str(request.headers.get("user-agent") or ""),
                request_id=request_id,
                latency_ms=elapsed,
            )
        except Exception:  # noqa: BLE001
            pass
        raise
    elapsed = (time.time() - started) * 1000
    try:
        session = admin_store.get_session(str(request.cookies.get("vibecut_admin") or ""))
        admin_store.record_audit(
            session["email"] if session else "anonymous",
            "http.request",
            resource_type="admin_api",
            resource_id=path,
            outcome="ok" if response.status_code < 400 else "failed",
            ip=str(getattr(request.client, "host", "") or ""),
            user_agent=str(request.headers.get("user-agent") or ""),
            request_id=request_id,
            latency_ms=elapsed,
            after={"method": request.method, "status": response.status_code},
        )
    except Exception:  # noqa: BLE001
        pass
    return response


ADMIN_PATHS = ("/_ductator", "/static/admin")
ADMIN_HEADERS = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "X-Robots-Tag": "noindex, nofollow",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
    ),
}


def _admin_path(path: str) -> bool:
    return any(
        path == prefix or path.startswith(prefix + "/") or path.startswith(prefix + ".")
        for prefix in ADMIN_PATHS
    )


def _request_secure(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    if os.environ.get("VIBECUT_ADMIN_TRUST_PROXY", "").strip().lower() not in {"1", "true", "yes"}:
        return False
    return str(request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower() == "https"


def _loopback_client(request: Request) -> bool:
    import ipaddress  # noqa: PLC0415
    host = str(getattr(request.client, "host", "") or "")
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@app.middleware("http")
async def admin_security_headers(request: Request, call_next):
    path = request.url.path
    if not _admin_path(path):
        return await call_next(request)
    if not _loopback_client(request) and not _request_secure(request):
        return JSONResponse(
            {
                "detail": (
                    "The admin console requires HTTPS for remote access. "
                    "Use a TLS-terminating tunnel or open it on localhost."
                )
            },
            status_code=403,
            headers=ADMIN_HEADERS,
        )
    response = await call_next(request)
    for name, value in ADMIN_HEADERS.items():
        response.headers[name] = value
    return response


_OVERLAY_ROUTE = re.compile(r"^/api/jobs/[^/]+/overlays(?:/|$)")


@app.middleware("http")
async def gate_overlay_routes(request: Request, call_next):
    """Hide Flow 2 before FastAPI parses a request body.

    The router also has a dependency gate. This middleware is the outer layer
    because malformed JSON and wrong content types must return 404, not 422,
    when the feature is off.
    """

    if _OVERLAY_ROUTE.match(request.url.path) and not overlays.enabled():
        return JSONResponse({"detail": "Not found."}, status_code=404)
    return await call_next(request)


# ---------------------------------------------------------------- routes


@lru_cache(maxsize=1)
def ffmpeg_version() -> str:
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True, timeout=10,
        )
        return (result.stdout.splitlines() or ["ffmpeg"])[0]
    except Exception:
        return "missing"


def page_response(path: Path) -> Response:
    """Serve one lane's page with the build's edition inside it."""
    page = path.read_text(encoding="utf-8")
    page = page.replace("<!-- vibecut:edition -->", editions.boot_script(), 1)
    return Response(page, media_type="text/html", headers={"Cache-Control": "no-cache"})


def page_file(request: Request) -> Path:
    """Which lane page this request opens.

    Classic owns ``static/classic/index.html``; Studio owns ``static/index.html``.
    Edition ``all`` keeps the old ``?classic=1`` / ``?studio=1`` switch without
    loading the other lane's markup.
    """
    if STUDIO_APP:
        return STATIC / "index.html"
    if editions.edition() == "classic":
        return STATIC / "classic" / "index.html"
    if editions.edition() == "all" and request.query_params.get("classic") == "1":
        return STATIC / "classic" / "index.html"
    return STATIC / "index.html"


@app.get("/")
def index(request: Request) -> Response:
    # The boot block reads the build's edition before first paint.
    return page_response(page_file(request))


def voice_room(request: Request) -> FileResponse:
    if not editions.feature_on("voice_room"):
        raise HTTPException(404, "Not found")
    page = STATIC / ("voices-next.html" if request.query_params.get("ui") == "new" else "voices.html")
    return FileResponse(page)


# The Voice Room page belongs to its own lane. Studio ships the voice features
# inside Setup and Edit, not this page, so a Studio build does not register it.
if not STUDIO_APP:
    app.add_api_route("/voices", voice_room, methods=["GET"])


@app.get("/_ductator/")
def admin_index() -> FileResponse:
    response = FileResponse(STATIC / "admin.html", media_type="text/html")
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.get("/_ductator")
def admin_index_redirect() -> RedirectResponse:
    return RedirectResponse("/_ductator/", status_code=307)


@app.get("/docs/url-ingest.md")
def url_ingest_docs() -> FileResponse:
    path = ROOT / "docs" / "url-ingest.md"
    if not path.is_file():
        raise HTTPException(404, "URL ingest guide not found.")
    return FileResponse(path, media_type="text/markdown; charset=utf-8")


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "ffmpeg": ffmpeg_version(),
        "vision": vision.available(),
        "whisper": bool(shutil.which("mlx_whisper"))
        or (
            sys.platform == "darwin"
            and (
                (ROOT / "bin" / "transcribe_apple").is_file()
                or bool(shutil.which("swiftc"))
            )
        ),
        "data": str(DATA),
        "encoder": render._choose_encoder(),
        "opencode": audio.opencode_available(),
        "version": 2,
    }




class SettingsTestBody(BaseModel):
    kind: str = "opencode"
    engine: str = ""
    voice: str = ""
    provider: str = ""


def _validate_ingest_patch(patch: dict) -> None:
    """Validate and normalise the ingest settings before they are persisted."""
    ingest = patch.get("ingest")
    if ingest is None:
        return
    if not isinstance(ingest, dict):
        raise HTTPException(400, "Ingest settings must be an object.")

    cleaned = {
        key: value
        for key, value in ingest.items()
        if key not in _INGEST_SECRET_KEYS
    }

    provider_id = registry.AUTO
    if "provider" in cleaned:
        if cleaned.get("provider") not in (None, ""):
            try:
                provider_id = registry.normalize_provider_id(cleaned["provider"], strict=True)
            except IngestError as exc:
                raise HTTPException(400, str(exc)) from exc
        cleaned["provider"] = provider_id

    for field, allowed, label in (
        ("ytdlp_quality", YTDLP_QUALITY_VALUES, "yt-dlp quality"),
        ("ytdlp_codec", YTDLP_CODEC_VALUES, "yt-dlp codec"),
        ("ytdlp_container", YTDLP_CONTAINER_VALUES, "yt-dlp container"),
        ("ytdlp_audio", YTDLP_AUDIO_VALUES, "yt-dlp audio quality"),
        ("ytdlp_cookies", YTDLP_COOKIE_VALUES, "yt-dlp cookie source"),
        ("ytdlp_browser", YTDLP_BROWSER_VALUES, "yt-dlp cookie browser"),
    ):
        value = cleaned.get(field)
        if value in (None, ""):
            continue
        normalized = str(value).strip().lower()
        if normalized not in allowed:
            raise HTTPException(400, f"Unknown {label}.")
        cleaned[field] = normalized

    cookie_file = cleaned.get("ytdlp_cookie_file")
    if cookie_file not in (None, ""):
        cookie_file = str(cookie_file).strip()
        if len(cookie_file) > 4096:
            raise HTTPException(400, "The yt-dlp cookie file path is too long.")
        cleaned["ytdlp_cookie_file"] = cookie_file

    interval = cleaned.get("xhs_interval")
    if interval not in (None, ""):
        try:
            number = float(interval)
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "XHS interval must be a number.") from exc
        if not math.isfinite(number) or number < 0:
            raise HTTPException(400, "XHS interval must be zero or more seconds.")
        cleaned["xhs_interval"] = number

    current = settings_store.load_settings().get("ingest")
    current = current if isinstance(current, dict) else {}
    current = {
        key: value
        for key, value in current.items()
        if key not in _INGEST_SECRET_KEYS
    }
    patch["ingest"] = registry.normalize_settings(
        {"ingest": {**current, **cleaned}}
    )


def _setup_origin_ok(request: Request) -> bool:
    """Reject cross-site Setup mutations while allowing CLI/curl requests."""
    site = str(request.headers.get("sec-fetch-site") or "").lower()
    if site == "cross-site":
        return False
    origin = str(request.headers.get("origin") or "")
    if not origin:
        return True
    if origin == "null":
        return False
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    host = str(request.headers.get("host") or "")
    return bool(parsed.netloc and host and parsed.netloc.lower() == host.lower())


def _settings_state() -> dict:
    state = settings_store.public_state()
    state["edition"] = editions.public()
    state["runtime"] = {
        "opencode": audio.opencode_available(),
        "opencode_binary": audio.opencode_bin() or "",
        "opencode_model": audio.opencode_model(),
        "opencode_variant": audio.opencode_variant(),
        "opencode_mode": audio.opencode_mode(),
        "openrouter": audio.openrouter_status(),
        "whisper_models": pipeline.whisper_models(),
        "voice_fit": {
            "signalsmith": voice_fit.signalsmith_available(),
            "ffmpeg": bool(shutil.which("ffmpeg")),
            "preserve_max_speed": voice_fit.PRESERVE_MAX_SPEED,
            "chipmunk_max_speed": voice_fit.CHIPMUNK_MAX_SPEED,
        },
    }
    return state


@app.get("/api/settings")
def get_settings() -> dict:
    return _settings_state()


@app.get("/api/rights/policy")
def get_rights_policy() -> dict:
    """The rights policy for a new import, with no job attached."""
    return rights.policy()


@app.post("/api/settings")
async def save_settings(request: Request) -> dict:
    if not _setup_origin_ok(request):
        raise HTTPException(403, "Cross-site Setup writes are blocked.")
    body = await request.json()
    patch = body.get("settings") if isinstance(body, dict) else None
    secrets = body.get("secrets") if isinstance(body, dict) else None
    before_state = None
    if isinstance(patch, dict) or isinstance(secrets, dict):
        try:
            before_state = settings_store.public_state()
        except Exception:  # noqa: BLE001
            before_state = None
    if isinstance(patch, dict):
        # Model routes are admin-console owned. Setup may display the summary
        # but the public settings API must never bypass catalog validation.
        if "workflows" in patch:
            raise HTTPException(
                400, "Model routes are managed in the admin console (/_ductator/).",
            )
        allowed_settings = {
            "opencode", "translation", "openrouter", "minimax", "stt", "tts",
            "ingest", "preflight", "caption_styles", "rights", "voice_fit",
        }
        unknown = sorted(set(patch) - allowed_settings)
        if unknown:
            raise HTTPException(400, f"Unknown settings section: {unknown[0]}.")
        if "rights" in patch:
            section = patch["rights"]
            if not isinstance(section, dict):
                raise HTTPException(400, "rights must be an object.")
            unknown_rights = sorted(set(section) - {"lock"})
            if unknown_rights:
                raise HTTPException(
                    400, f"Unknown rights setting: {unknown_rights[0]}.",
                )
            if "lock" in section and not isinstance(section["lock"], bool):
                raise HTTPException(400, "rights.lock must be true or false.")
        if "voice_fit" in patch:
            section = patch["voice_fit"]
            if not isinstance(section, dict):
                raise HTTPException(400, "voice_fit must be an object.")
            unknown_voice = sorted(set(section) - {
                "preserve_pitch", "max_speed", "engine", "allow_extreme_speed",
            })
            if unknown_voice:
                raise HTTPException(
                    400, f"Unknown voice_fit setting: {unknown_voice[0]}.",
                )
            if "engine" in section and section["engine"] not in {
                None, "", "auto", "ffmpeg", "signalsmith",
            }:
                raise HTTPException(400, "Unknown voice_fit engine.")
            if "max_speed" in section:
                try:
                    speed = float(section["max_speed"])
                except (TypeError, ValueError) as exc:
                    raise HTTPException(400, "voice_fit.max_speed must be a number.") from exc
                if not math.isfinite(speed) or speed < 1.0 or speed > 2.5:
                    raise HTTPException(400, "voice_fit.max_speed must be between 1.0 and 2.5.")
        if "preflight" in patch:
            try:
                preflight.validate_settings(patch["preflight"])
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
        _validate_ingest_patch(patch)
        if "caption_styles" in patch:
            raw_styles = patch.get("caption_styles")
            if raw_styles is None:
                raise HTTPException(400, "Caption styles must be an object.")
            current_styles = (
                settings_store.load_settings().get("caption_styles") or {}
            )
            try:
                patch["caption_styles"] = caption_engine.merge_style_settings(
                    current_styles, raw_styles,
                )
            except caption_engine.CaptionStyleError as exc:
                raise HTTPException(400, str(exc)) from exc

        opencode = patch.get("opencode")
        if isinstance(opencode, dict):
            if "model" in opencode:
                model = str(opencode.get("model") or "").strip()
                if len(model) > 240:
                    raise HTTPException(400, "OpenCode model id is too long.")
                if model:
                    opencode["model"] = model
                else:
                    opencode.pop("model", None)
            if "variant" in opencode:
                variant = str(opencode.get("variant") or "").strip().lower()
                if variant and variant not in {"none", "low", "medium", "high", "max"}:
                    raise HTTPException(400, "Unknown OpenCode reasoning variant.")
                if variant:
                    opencode["variant"] = variant
                else:
                    opencode.pop("variant", None)
        stt = patch.get("stt")
        if isinstance(stt, dict):
            provider = str(stt.get("provider") or "").strip()
            model = str(stt.get("model") or "").strip()
            if len(provider) > 40:
                raise HTTPException(400, "Transcription provider id is too long.")
            if len(model) > 240:
                raise HTTPException(400, "Transcription model id is too long.")
        translation = patch.get("translation")
        if isinstance(translation, dict) and translation.get("mode") not in (None, "", "auto", "local_first", "local_only", "online_only"):
            raise HTTPException(400, "Unknown translation mode.")
        ingest = patch.get("ingest")
        if isinstance(ingest, dict):
            value = ingest.get("xhs_url")
            if value:
                try:
                    registry.validate_url(str(value))
                except IngestError as exc:
                    raise HTTPException(400, f"Invalid xhs_url: {exc}") from exc
            if "xhs_no_record" in ingest and not isinstance(ingest["xhs_no_record"], bool):
                raise HTTPException(400, "xhs_no_record must be true or false.")
            if "xhs_interval" in ingest:
                try:
                    interval = float(ingest["xhs_interval"])
                except (TypeError, ValueError) as exc:
                    raise HTTPException(400, "xhs_interval must be numeric.") from exc
                if interval < 0 or not math.isfinite(interval):
                    raise HTTPException(400, "xhs_interval must be a non-negative number.")
        tts = patch.get("tts")
        if isinstance(tts, dict):
            provider = str(tts.get("provider") or "").strip()
            if len(provider) > 40:
                raise HTTPException(400, "Voice provider id is too long.")
        settings_store.save_settings(patch)
    if isinstance(secrets, dict):
        settings_store.save_secrets(secrets)
        for name in secrets:
            if name == "openrouter":
                audio.clear_openrouter_quarantine()
                audio.reset_provider_breaker("openrouter")
                audio.OPENROUTER_LAST_ERROR = ""
                audio.OPENROUTER_LAST_STATUS = 0
            elif name in {"opencode", "minimax", "groq", "openai", "deepgram", "elevenlabs", "cartesia"}:
                audio.reset_provider_breaker(name)
        try:
            audio.clear_workflow_caches()
        except Exception:  # noqa: BLE001
            pass
    if before_state is not None:
        try:
            after_state = settings_store.public_state()
            admin_store.record_audit(
                "setup", "settings.update", resource_type="settings",
                before=before_state.get("settings"), after=after_state.get("settings"),
                ip=str(getattr(request.client, "host", "") or ""),
                user_agent=str(request.headers.get("user-agent") or ""),
            )
            if isinstance(secrets, dict):
                admin_store.record_audit(
                    "setup", "secrets.update", resource_type="secret",
                    before=before_state.get("secrets"), after=after_state.get("secrets"),
                    ip=str(getattr(request.client, "host", "") or ""),
                    user_agent=str(request.headers.get("user-agent") or ""),
                )
        except Exception:  # noqa: BLE001
            LOGGER.exception("setup audit write failed")
    return _settings_state()


@app.post("/api/settings/test")
def test_settings(body: SettingsTestBody) -> dict:
    kind = (body.kind or "opencode").strip().lower()
    if kind in {"xhs_get", "xhs-get", "xhsget", "rednote", "xiaohongshu"}:
        kind = registry.XHS
    if kind in {"yt-dlp", "yt_dlp", "youtube-dl"}:
        kind = registry.YTDLP
    if kind in {registry.YTDLP, registry.XHS}:
        started = time.time()
        provider_settings = _ingest_provider_settings()
        try:
            instance = registry.provider(kind, provider_settings)
            entry = _provider_status_entry(instance, provider_settings)
        except Exception as exc:  # noqa: BLE001
            entry = {
                "id": kind,
                "label": kind,
                "configured": False,
                "available": False,
                "error": _short_ingest_error(exc),
            }
        ok = bool(entry.get("available"))
        label = str(entry.get("label") or kind)
        error = str(entry.get("error") or "")
        if kind == registry.YTDLP:
            version = str(entry.get("version") or "").strip()
            detail = (
                f"{label} is ready{f' · {version}' if version else ''}."
                if ok else (error or f"{label} is not available. Install it with requirements.txt.")
            )
        else:
            detail = f"{label} is reachable." if ok else (
                error or f"{label} is not available. Check Setup."
            )
        result = {
            "ok": ok,
            "kind": kind,
            "provider": kind,
            "label": label,
            "configured": bool(entry.get("configured")),
            "available": ok,
            "error": error,
            "seconds": round(time.time() - started, 2),
            "status": entry,
            "detail": detail,
        }
        session = _ingest_session(entry)
        if session:
            result["session"] = session
            for key in _INGEST_SESSION_FIELDS:
                if key in session:
                    result[key] = session[key]
        return result
    if kind == "opencode":
        started = time.time()
        answer = audio._opencode_text(
            'Reply with JSON only: {"ok": true}', json_mode=True, max_tokens=200,
            force=True,
        )
        return {
            "ok": bool(answer),
            "kind": "opencode",
            "model": audio.opencode_model(),
            "variant": audio.opencode_variant(),
            "mode": audio.opencode_mode(),
            "seconds": round(time.time() - started, 2),
            "answer": (answer or "")[:160],
            "detail": (
                "OpenCode Go replied." if answer
                else "No reply. Check the OpenCode login, Go subscription, or service."
                + (f" {audio.OPENCODE_LAST_ERROR}" if audio.OPENCODE_LAST_ERROR else "")
            ),
        }
    if kind == "openrouter":
        started = time.time()
        source = settings_store.secret_source("openrouter")
        model = audio.openrouter_model()
        answer = audio._openrouter_text(
            'Reply with JSON only: {"ok": true}', json_mode=True, max_tokens=120,
            force=True,
        )
        if answer:
            audio.clear_openrouter_quarantine()
        key_info = {} if answer else audio.openrouter_key_info()
        management = bool(key_info.get("is_management_key"))
        detail = "OpenRouter replied."
        if not answer:
            if management:
                detail = (
                    "This is an OpenRouter management/provisioning key. "
                    "Management keys cannot call chat/inference. Create a normal inference key."
                )
            else:
                detail = "OpenRouter model check failed. " + (
                    audio.OPENROUTER_LAST_ERROR or "No reply."
                )
        return {
            "ok": bool(answer),
            "kind": "openrouter",
            "source": source,
            "model": model,
            "status": audio.OPENROUTER_LAST_STATUS,
            "blocked": audio.openrouter_blocked(),
            "retry_in": audio.openrouter_blocked_seconds(),
            "seconds": round(time.time() - started, 2),
            "answer": (answer or "")[:160],
            "management_key": management,
            "key_label": key_info.get("label") or "",
            "detail": detail,
        }
    if kind == "stt":
        apple = pipeline._apple_transcribe_helper()
        whisper = bool(shutil.which("mlx_whisper"))
        ok = bool(apple or whisper)
        return {
            "ok": ok,
            "kind": "stt",
            "provider": "apple" if apple else ("whisper" if whisper else None),
            "detail": (
                "Local STT ready: Apple Speech → Whisper."
                if ok else
                "Local STT unavailable. Install macOS 26 Apple Speech or mlx-whisper."
            ),
        }
    if kind == "tts":
        engines = audio.engine_status().get("voices") or {}
        ready = [
            name for name in ("heygen", "minimax", "elevenlabs", "fish", "gemini", "kokoro", "say")
            if (engines.get(name) or {}).get("available")
        ]
        return {
            "ok": bool(ready),
            "kind": "tts",
            "engines": {name: bool((engines.get(name) or {}).get("available")) for name in ready},
            "detail": ("Ready: " + ", ".join(ready)) if ready else "No voice engine ready.",
        }
    if kind == "stt_live":
        sample_dir = DATA / "cache" / "stt-test"
        sample_dir.mkdir(parents=True, exist_ok=True)
        sample = sample_dir / "sample.wav"
        engine = ""
        voice = ""
        for candidate in ("say", "kokoro"):
            info = audio.engine_status().get("voices", {}).get(candidate) or {}
            if not info.get("available"):
                continue
            voices = audio.list_voices(candidate)
            if voices:
                engine, voice = candidate, voices[0]["id"]
                break
        if not engine:
            return {"ok": False, "kind": "stt_live", "detail": "No local voice to generate the test clip."}
        started = time.time()
        try:
            audio.synthesize_line(engine, voice, "VibeCut transcription test. The garden is open.", sample)
            result = pipeline.transcribe_apple(sample, sample_dir, "en")
            provider = "apple" if result else ""
            if result is None:
                result = pipeline.transcribe(
                    sample, sample_dir, audio.media_duration(sample) or 3.0,
                    lambda fraction, message: None,
                )
                provider = "whisper" if result else ""
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "kind": "stt_live", "detail": str(exc)[:300]}
        if not result:
            return {"ok": False, "kind": "stt_live", "detail": "Local STT returned no transcript."}
        return {
            "ok": True,
            "kind": "stt_live",
            "provider": provider,
            "seconds": round(time.time() - started, 2),
            "text": " ".join(str(result.get("text") or "").split())[:300],
            "detail": f"{provider} transcribed the local test clip.",
        }
    if kind == "tts_live":
        requested = (body.engine or "").lower()
        engines = audio.engine_status().get("voices", {})
        candidates = [requested] if requested and requested not in {"auto", "local"} else [
            "heygen", "minimax", "elevenlabs", "fish", "gemini", "kokoro", "say",
        ]
        engine = next((name for name in candidates if (engines.get(name) or {}).get("available")), "")
        if not engine:
            return {"ok": False, "kind": "tts_live", "detail": "No available voice engine."}
        voices = audio.list_voices(engine)
        if not voices:
            return {"ok": False, "kind": "tts_live", "engine": engine, "detail": "No voices for this engine."}
        voice = body.voice or voices[0]["id"]
        output_dir = DATA / "cache" / "voice-test"
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / f"{engine}.wav"
        started = time.time()
        try:
            audio.synthesize_line(engine, voice, "VibeCut voice test. The garden is open.", output)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "kind": "tts_live", "engine": engine, "detail": str(exc)[:300]}
        return {
            "ok": True,
            "kind": "tts_live",
            "engine": engine,
            "voice": voice,
            "seconds": round(time.time() - started, 2),
            "url": f"/api/settings/tts-test/{engine}.wav?v={int(time.time())}",
            "detail": f"{engine} synthesized a local test clip.",
        }
    raise HTTPException(400, "Unknown test kind.")


class XhsCookieBody(BaseModel):
    cookie: str = ""
    url: str = ""
    token: str = ""


@app.post("/api/ingest/xhs/cookie")
def ingest_xhs_cookie(body: XhsCookieBody) -> dict:
    value = str(body.cookie or "").strip()
    if not value:
        raise HTTPException(400, "RedNote cookie is empty.")
    try:
        instance = registry.provider(
            registry.XHS,
            _ingest_provider_settings(
                xhs_url=(body.url.strip() if body.url.strip() else None),
                xhs_token=(body.token.strip() if body.token.strip() else None),
            ),
        )
        setter = getattr(instance, "set_cookie", None)
        if not callable(setter):
            raise IngestError("XHS provider cannot accept a cookie.")
        result = setter(value)
    except IngestError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "result": result}


class XhsInviteBody(BaseModel):
    url: str = ""
    token: str = ""


def _xhs_invite_response(base: str, token: str) -> dict:
    base = str(base or "").strip().rstrip("/")
    token = str(token or "").strip()
    if not base:
        raise HTTPException(400, "Set the XHS service URL first.")
    if not token:
        return {"url": base + "/", "token": False,
                "detail": "No access token saved; open the service URL and use the local account."}
    return {
        "url": f"{base}/#t={quote(token, safe='')}",
        "token": True,
        "detail": "Invite link includes the xhs_get access token.",
    }


@app.get("/api/ingest/xhs/invite")
def ingest_xhs_invite_get() -> dict:
    settings = _ingest_provider_settings().get("ingest") or {}
    return _xhs_invite_response(
        str(settings.get("xhs_url") or ""), str(settings.get("xhs_token") or ""),
    )


@app.post("/api/ingest/xhs/invite")
def ingest_xhs_invite(body: XhsInviteBody | None = None) -> dict:
    settings = _ingest_provider_settings(
        xhs_url=(body.url.strip() if body and body.url.strip() else None),
        xhs_token=(body.token.strip() if body and body.token.strip() else None),
    ).get("ingest") or {}
    return _xhs_invite_response(
        str(settings.get("xhs_url") or ""), str(settings.get("xhs_token") or ""),
    )


@app.post("/api/ingest/xhs/check")
def ingest_xhs_check(body: XhsInviteBody | None = None) -> dict:
    settings = _ingest_provider_settings(
        xhs_url=(body.url.strip() if body and body.url.strip() else None),
        xhs_token=(body.token.strip() if body and body.token.strip() else None),
    )
    try:
        instance = registry.provider(registry.XHS, settings)
        return {"ok": True, "status": _provider_status_entry(instance, settings)}
    except IngestError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/ingest/status")
def ingest_status() -> dict:
    provider_settings = _ingest_provider_settings()
    reported = registry.status(provider_settings)
    providers = dict(reported) if isinstance(reported, dict) else {}

    direct: dict = {}
    try:
        instance = registry.provider(registry.XHS, provider_settings)
        direct = _provider_status_entry(instance, provider_settings)
    except Exception as exc:  # noqa: BLE001
        direct = {
            "id": registry.XHS,
            "label": "XHS / RedNote",
            "configured": False,
            "available": False,
            "error": _short_ingest_error(exc),
            "session": {},
        }

    existing = providers.get(registry.XHS)
    xhs = dict(existing) if isinstance(existing, dict) else dict(direct)
    xhs.setdefault("id", registry.XHS)
    xhs.setdefault("label", "XHS / RedNote")
    xhs.setdefault("configured", bool(direct.get("configured")))
    xhs.setdefault("available", bool(direct.get("available")))
    xhs.setdefault("error", str(direct.get("error") or ""))
    if "token" in str(xhs.get("error") or "").lower():
        xhs["auth_required"] = True
    for key in _INGEST_SESSION_FIELDS:
        if direct.get(key) is not None:
            xhs[key] = direct.get(key)
    xhs["session"] = _ingest_session(direct or xhs)
    providers[registry.XHS] = xhs

    return {
        **providers,
        "providers": providers,
        "settings": _public_ingest_settings(provider_settings),
    }


@app.get("/api/settings/tts-test/{engine}.wav")
def settings_tts_test(engine: str) -> FileResponse:
    safe = "".join(ch for ch in engine if ch.isalnum() or ch in "-_")
    path = DATA / "cache" / "voice-test" / f"{safe}.wav"
    if not path.is_file():
        raise HTTPException(404, "No voice test yet.")
    return FileResponse(path, media_type="audio/wav", filename=f"vibecut-{safe}-test.wav")


class ShareBody(BaseModel):
    artifact_id: str | None = None
    expires_in_days: float | None = None
    label: str = ""


class SharePatchBody(BaseModel):
    label: str | None = None
    expires_at: float | None = None
    expires_in_days: float | None = None
    revoked: bool | None = None


class ShareTokenBody(BaseModel):
    token: str = ""


class PinBody(BaseModel):
    pinned: bool = True


def _expiry(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        days = float(value)
    except (TypeError, ValueError):
        raise HTTPException(400, "expires_in_days must be a number.") from None
    if days < 0:
        raise HTTPException(400, "expires_in_days cannot be negative.")
    return round(time.time() + days * 86400, 3) if days > 0 else None


def _ready_manifest(job: dict, artifact_id: str) -> dict:
    manifest = artifacts.load_manifest(_job_dir(job["id"]), artifact_id)
    if manifest is None:
        raise HTTPException(404, "Artifact not found.")
    if manifest.get("status") != "ready" or not artifacts.has_media(
        _job_dir(job["id"]), artifact_id,
    ):
        raise HTTPException(409, "Render this cut first, then create the review link.")
    return manifest


def _merge_adopted_record(
    job: dict,
    artifact: str,
    record_key: str,
    target: int,
    aspect: str,
    spec: dict,
) -> None:
    for record in (job.get("renders") or {}).values():
        if not isinstance(record, dict) or record.get("artifact_id"):
            continue
        if record.get("status") != "ready":
            continue
        if record_key and record.get("record_key"):
            if record.get("record_key") != record_key:
                continue
        else:
            try:
                same_target = int(record.get("target")) == int(target)
            except (TypeError, ValueError):
                same_target = False
            same_aspect = str(record.get("aspect") or "9:16") == aspect
            if not (same_target and same_aspect):
                path = str(record.get("path") or "")
                if f"reel_{int(target)}" not in path:
                    continue
                if aspect != "9:16" and aspect.replace(":", "x") not in path:
                    continue
        record["artifact_id"] = artifact
        record["record_key"] = record.get("record_key") or record_key or None
        record["resolved_encoder"] = spec.get("resolved_encoder")
    artifacts.ensure_job_schema(job, _job_dir(job["id"]))


def _publish_share(
    job_id: str,
    manifest: dict,
    target: int,
    aspect: str,
    *,
    expires_at: float | None,
    label: str,
    merge_legacy: bool,
) -> tuple[str, dict]:
    artifact = str(manifest.get("artifact_id") or "")
    spec = manifest.get("spec") or {}
    record_key = str(manifest.get("record_key") or "")
    result: dict = {}

    def mutate(job: dict) -> None:
        # Revalidate under the job lock so clean/delete cannot remove the
        # artifact between the first check and share publication.
        ready = _ready_manifest(job, artifact)
        if merge_legacy:
            _merge_adopted_record(
                job, artifact, record_key, target, aspect, spec,
            )
        token, _record = shares.create(
            job_id, artifact,
            expires_at=expires_at, label=label, path=SHARES,
        )
        result["token"] = token
        result["manifest"] = ready

    update_job(job_id, mutate)
    return str(result.get("token") or ""), result.get("manifest") or manifest


@app.post("/api/jobs/{job_id}/share")
def create_share(
    job_id: str,
    target: int = 30,
    aspect: str = "9:16",
    body: ShareBody | None = None,
) -> dict:
    job = load_job(job_id)
    try:
        shares.load(SHARES, strict=True)
    except shares.ShareStoreError as exc:
        raise _share_store_unavailable(exc) from exc
    requested = str(body.artifact_id or "") if body else ""
    merge_legacy = False
    if requested:
        if not artifacts.is_safe_artifact_id(requested):
            raise HTTPException(404, "Artifact not found.")
        manifest = _ready_manifest(job, requested)
        target = int((manifest.get("spec") or {}).get("target") or 0)
        aspect = str((manifest.get("spec") or {}).get("aspect") or "9:16")
    else:
        target = _valid_target(int(target))
        aspect = aspect if aspect in render.ASPECTS else "9:16"
        manifest = _find_artifact_for_target(job, target, aspect)
        if manifest is None:
            raise HTTPException(409, "Render this cut first, then create the review link.")
        manifest = _ready_manifest(job, str(manifest.get("artifact_id") or ""))
        merge_legacy = True
    expires_at = _expiry(body.expires_in_days if body else None)
    label = str(body.label or "")[:120] if body else ""
    try:
        token, manifest = _publish_share(
            job_id, manifest, target, aspect,
            expires_at=expires_at, label=label,
            merge_legacy=merge_legacy,
        )
    except shares.ShareStoreError as exc:
        raise _share_store_unavailable(exc) from exc
    spec = manifest.get("spec") or {}
    return {
        "token": token,
        "url": f"/r/{token}",
        "artifact_id": manifest["artifact_id"],
        "target": spec.get("target"),
        "aspect": spec.get("aspect"),
        "expires_at": expires_at,
        "label": label,
    }


@app.post("/api/jobs/{job_id}/share-token")
def recopy_share_token(
    job_id: str,
    body: ShareTokenBody,
    request: Request,
) -> dict:
    """Return one job-scoped review token to the local owner.

    The creating session may have closed without the token being copied. This
    is deliberately not a token listing: it needs the job id and the exact
    token, and it is only available to a loopback client.
    """
    if not _loopback_client(request):
        raise HTTPException(
            403,
            "Review links can only be re-copied on this Mac.",
        )
    job = load_job(job_id)
    token = str(body.token or "").strip()
    if not token:
        raise HTTPException(400, "Send the review token to re-copy.")
    try:
        record = shares.get(token, SHARES)
    except shares.ShareStoreError as exc:
        raise _share_store_unavailable(exc) from exc
    if record is None or str(record.get("job_id") or "") != str(job["id"]):
        raise HTTPException(404, "Review link not found for this job.")
    state = shares.state(record)
    if state == shares.EXPIRED:
        raise HTTPException(410, "This review link has expired.")
    if state == shares.REVOKED:
        raise HTTPException(410, "This review link was revoked.")
    if state != shares.ACTIVE:
        raise HTTPException(404, "Review link not found for this job.")
    public = {
        **record,
        "token": token,
        "url": f"/r/{token}",
    }
    return {**public, "share": record}


@app.get("/r/{token}")
def review_page(token: str) -> Response:
    found = _share(token)
    if not found:
        raise HTTPException(404, "Review link not found.")
    record, job, render_record = found
    title = html_lib.escape(Path(job["source"]["name"]).stem)
    versions = record.get("versions") or {}
    label = html_lib.escape(str(versions.get("label") or ""))
    version_banner = ""
    if label:
        kind = "current" if versions.get("current") else "superseded"
        version_banner = f'<p class="version {kind}" role="status">{label}</p>'
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>{title} · review</title>
<style>
body{{margin:0;background:#0a0a0b;color:#f2f0ec;font:15px/1.5 -apple-system,BlinkMacSystemFont,sans-serif;
display:grid;place-items:center;min-height:100vh}}
main{{width:min(92vw,520px);padding:24px 0}}
h1{{font-size:20px;font-weight:500;margin:0 0 4px}}
p{{color:#8b8a86;font-size:12px;margin:0 0 18px}}
video{{width:100%;border-radius:14px;background:#000}}
a{{display:inline-block;margin:16px 12px 0 0;color:#e8a266;text-decoration:none}}
.version{{display:inline-block;padding:4px 10px;border-radius:999px;font-size:13px;color:#f2f0ec;background:#2a2a2d}}
.version.superseded{{background:#5a3a14;color:#ffd9a8}}
</style></head><body><main>
<h1>{title}</h1><p>{record['target']}s · {record['aspect']} · review only</p>
{version_banner}
<video controls playsinline src="/r/{token}/video"></video>
<div><a href="/r/{token}/video" download>Download MP4</a>
<a href="/r/{token}/captions.srt">Captions SRT</a></div>
</main></body></html>"""
    return Response(content=html, media_type="text/html")


@app.get("/r/{token}/video")
def review_video(token: str) -> FileResponse:
    found = _share(token)
    if not found:
        raise HTTPException(404, "Review link not found.")
    _record, job, render_record = found
    path = _job_dir(job["id"]) / render_record["path"]
    if not path.is_file():
        raise HTTPException(404, "Render file missing.")
    return FileResponse(path, media_type="video/mp4", filename=Path(render_record["path"]).name)


@app.get("/r/{token}/captions.srt")
def review_captions(token: str) -> Response:
    found = _share(token)
    if not found:
        raise HTTPException(404, "Review link not found.")
    record, job, _render_record = found
    content = _share_captions(job, str(record["artifact_id"]))
    return Response(
        content=content, media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="captions.srt"'},
    )


class PathBody(BaseModel):
    path: str
    options: dict = {}
    job_id: str | None = None
    # The own-footage note from Import. Stored on the job; policy is unchanged.
    rights: bool | None = None


class InspectBody(BaseModel):
    path: str


class UrlInspectBody(BaseModel):
    url: str
    provider: str | None = None
    options: dict | None = None


class FromUrlBody(BaseModel):
    url: str
    provider: str | None = None
    options: dict | None = None
    ingest_options: dict | None = None
    job_id: str | None = None
    rights: bool | None = None


class PlanBody(BaseModel):
    target: int = 30
    hook_scene: int | None = None
    force: bool = False
    quality: str = "final"
    aspect: str = "9:16"
    encoder: str | None = None
    captions: bool = False
    clips: list[dict] | None = None
    audio: dict | None = None
    preset: str | None = None
    order: str = "source"
    caption_margin: float | None = None
    script_id: str | None = None
    caption_track_id: str | None = None
    caption_style_id: str | None = None
    caption_style: dict | None = None
    # Classic sends Studio-shaped text overlays and effects. app builds a
    # valid Edit from them before queueing; Studio keeps sending a stored Edit
    # through its own routes.
    edit: dict | None = None


class CaptionTrackBody(BaseModel):
    target: int = 30
    set_id: str | None = None
    story_id: str | None = None
    hook_scene: int | None = None
    clips: list[dict] | None = None
    style_id: str | None = None
    overrides: dict | None = None
    order: str = "source"


class CaptionEditBody(BaseModel):
    cues: list[dict] | None = None
    style: dict | None = None
    style_id: str | None = None
    overrides: dict | None = None


class VariantBody(BaseModel):
    name: str = ""
    target: int = 30
    hook_scene: int | None = None
    clips: list[dict]


UNREADABLE_VIDEO = (
    "This file isn't a readable video. Try exporting it again as MP4 (H.264)."
)


def _local_video_path(raw: str) -> Path:
    """A local path that names a file, with plain errors for the rest."""
    path = Path(raw).expanduser()
    if path.is_dir():
        raise HTTPException(400, "That path is a folder; choose a video file.")
    if not path.is_file():
        raise HTTPException(404, "File not found on this machine.")
    return path


def _probe_video(path: Path) -> dict:
    """ffprobe a source; its raw stderr goes to the log, not the creator."""
    try:
        return pipeline.probe(path)
    except pipeline.PipelineError as exc:
        LOGGER.warning("probe failed for %s: %s", path, str(exc)[:600])
        message = str(exc)
        # pipeline's own short sentences are already plain; tool output isn't.
        plain = "\n" not in message and "ffprobe" not in message and len(message) <= 120
        raise HTTPException(400, message if plain else UNREADABLE_VIDEO) from exc


@app.post("/api/inspect")
def inspect(body: InspectBody) -> dict:
    path = _local_video_path(body.path)
    meta = _probe_video(path)
    meta.pop("path", None)
    return meta


@app.post("/api/url/inspect")
def inspect_url(body: UrlInspectBody) -> dict:
    try:
        url = _validate_remote_ingest_url(body.url)
        provider_settings = _ingest_provider_settings()
        order = _ingest_provider_order(url, body.provider, provider_settings)
        options = registry.options_from_settings(provider_settings, body.options)
        chain = _ingest_provider_chain(provider_settings, order)
    except IngestError as exc:
        raise HTTPException(400, str(exc)) from exc

    provider_id = order[0]
    instance = None
    try:
        inspected = chain.inspect(url, options)
        if not isinstance(inspected, dict):
            raise IngestError("The ingest provider returned an invalid inspection result.")
        provider_id = chain.last_provider_id or provider_id
        instance = chain.last_provider
    except Exception as exc:  # noqa: BLE001
        # Show the primary provider and its error. Fallback attempts stay in
        # metadata.
        provider_id = order[0]
        instance = chain.last_provider if chain.last_provider_id == provider_id else None
        status_entry = (
            _provider_status_entry(instance, provider_settings, optimistic=True)
            if instance is not None
            else {"configured": True, "available": False, "error": ""}
        )
        label = str(
            getattr(instance, "label", "")
            or {
                registry.YTDLP: "yt-dlp",
                registry.XHS: "XHS / RedNote",
            }.get(provider_id)
            or provider_id
        )
        warning = _ingest_warning(
            _short_ingest_error(exc),
            _redact_ingest_text(status_entry.get("error") or ""),
            "Could not inspect this URL.",
        )
        attempts = _attempts_payload(getattr(chain, "last_attempts", ()))
        return {
            "provider": provider_id,
            "label": label,
            "available": False,
            "configured": bool(status_entry.get("configured")),
            "warning": warning,
            "session": _ingest_session(status_entry),
            "meta": {"error": _short_ingest_error(exc), "attempts": attempts},
            "title": "",
            "options": options.as_dict(),
            "provider_status": _redact_ingest_meta(status_entry),
        }

    status_entry = _provider_status_entry(instance, provider_settings, optimistic=True)
    meta = _redact_ingest_meta(inspected)
    label = str(
        getattr(instance, "label", "")
        or inspected.get("label")
        or status_entry.get("label")
        or provider_id
    )
    status_available = bool(status_entry.get("available"))
    inspected_available = inspected.get("available")
    available = (
        bool(inspected_available)
        if isinstance(inspected_available, bool)
        else status_available
    )
    inspected_warning = inspected.get("warning") or inspected.get("error")
    warning = _ingest_warning(
        inspected_warning,
        "" if inspected_warning else (status_entry.get("error") if not available else ""),
    )
    session = _ingest_session(inspected)
    status_session = _ingest_session(status_entry)
    for key, value in status_session.items():
        if key == "auth_required" or key not in session:
            session[key] = value
    if status_entry.get("auth_required"):
        session["auth_required"] = True
    title = str(inspected.get("title") or meta.get("title") or "").strip()
    if not title and meta.get("filename"):
        title = Path(str(meta["filename"])).stem
    choices = inspected.get("choices")
    if not isinstance(choices, list):
        choices = meta.get("choices") if isinstance(meta.get("choices"), list) else []
    choices = _redact_ingest_value(choices)
    needs_choice = bool(
        inspected.get("needs_choice")
        or str(inspected.get("status") or "") == "picker"
    )
    attempts = _attempts_payload(getattr(chain, "last_attempts", ()))
    return {
        "provider": provider_id,
        "label": label,
        "available": available,
        "configured": bool(status_entry.get("configured", True)),
        "warning": warning,
        "session": session,
        "meta": meta,
        "title": title,
        "duration": inspected.get("duration"),
        "thumbnail": _redact_ingest_value(inspected.get("thumbnail")),
        "uploader": inspected.get("uploader") or meta.get("uploader"),
        "needs_choice": needs_choice,
        "choices": choices,
        "options": inspected.get("options") if isinstance(inspected.get("options"), dict) else options.as_dict(),
        "provider_status": _redact_ingest_meta(status_entry),
        "attempts": attempts,
    }


def _reuse_partial_job_dir(directory: Path) -> bool:
    """Remove an empty or temp-only job dir left by a crash before job.json.

    Returns True only when the directory is gone afterwards.  A directory that
    already has job.json or unexpected files is never reused.
    """
    if not directory.exists():
        return True
    if (directory / "job.json").exists():
        return False
    try:
        entries = list(directory.iterdir())
    except OSError:
        return False
    for entry in entries:
        if not (
            entry.is_file()
            and entry.name.startswith(".job.")
            and entry.name.endswith(".tmp")
        ):
            return False
        try:
            entry.unlink()
        except OSError:
            return False
    try:
        directory.rmdir()
    except OSError:
        return False
    return True


def _requested_job_id(value: str | None) -> str:
    """Use a caller-provided job id only when it is fresh and safe."""
    if not value:
        return uuid.uuid4().hex[:12]
    job_id = str(value).strip().lower()
    if not re.fullmatch(r"[a-f0-9]{12}", job_id):
        raise HTTPException(400, "job_id must be 12 lowercase hex characters.")
    directory = JOBS / job_id
    if directory.exists() and not _reuse_partial_job_dir(directory):
        raise HTTPException(409, "That job_id already exists.")
    return job_id


def _require_import_rights(attested: bool | None) -> None:
    """Refuse an import while the rights lock is on and the tick is missing."""
    if not rights.may_import(attested):
        raise HTTPException(409, rights.IMPORT_CONFIRMATION)


def import_rights(attested: bool | None) -> dict | None:
    """The rights record an import stores, or None when Import sent none.

    Studio's Import asks for the own-footage note; it used to live only in
    browser storage. The record has the same shape POST /rights writes, with
    ``source: "import"``, so Check prefills from it and Clean's gate reads it.
    """
    if attested is None:
        return None
    return {"attested": bool(attested), "at": round(time.time(), 3), "source": "import"}


def _new_job(
    source_path: Path,
    name: str,
    meta: dict,
    options: dict,
    job_id: str | None = None,
    rights: dict | None = None,
) -> dict:
    job_id = job_id or uuid.uuid4().hex[:12]
    directory = JOBS / job_id
    directory.mkdir(parents=True, exist_ok=True)
    job = {
        "id": job_id,
        "created": round(time.time(), 3),
        "updated": round(time.time(), 3),
        "status": "queued",
        "progress": 0.0,
        "message": "Queued",
        "error": None,
        "source": {
            "path": str(source_path),
            "name": name,
            **meta,
        },
        "options": options,
        "analysis": None,
        "renders": {},
        "artifacts": {},
        "artifact_ids": [],
        "schema_version": artifacts.SCHEMA_VERSION,
        "render_version": artifacts.RENDER_VERSION,
        "story_id": job_id,
        "attempts": {"analysis": 0},
    }
    if rights is not None:
        job["rights"] = dict(rights)
    save_job(job)
    analysis_pool.submit(run_analysis, job_id)
    return job


@app.post("/api/jobs/upload")
async def upload_job(
    request: Request,
    file: UploadFile = File(...),
    options: str = Form("{}"),
    rights: str = Form(""),
) -> dict:
    try:
        parsed_options = clean_options(json.loads(options))
    except json.JSONDecodeError:
        parsed_options = clean_options({})
    attested = {"true": True, "1": True, "false": False, "0": False}.get(
        rights.strip().lower()
    )
    _require_import_rights(attested)

    try:
        declared = int(request.headers.get("content-length") or 0)
    except ValueError:
        declared = 0
    if declared > MAX_UPLOAD:
        raise HTTPException(
            413,
            f"Upload is larger than the {MAX_UPLOAD / 1024 ** 3:.0f} GB limit.",
        )
    if declared:
        try:
            disk.preflight(disk.estimate_upload(declared), DATA)
        except disk.InsufficientSpace as exc:
            return JSONResponse(status_code=507, content=exc.as_dict())

    original = Path(file.filename or "video.mp4").name
    suffix = Path(original).suffix.lower()
    if suffix not in {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".mpg", ".mpeg"}:
        suffix = ".mp4"
    job_id = uuid.uuid4().hex[:12]
    directory = JOBS / job_id
    directory.mkdir(parents=True, exist_ok=False)
    SOURCES.mkdir(parents=True, exist_ok=True)
    temp = SOURCES / f".incoming-{uuid.uuid4().hex}{suffix}"
    total = 0
    checked = 0
    try:
        with temp.open("wb") as output:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD:
                    raise HTTPException(
                        413,
                        f"Upload is larger than the {MAX_UPLOAD / 1024 ** 3:.0f} GB limit.",
                    )
                if total - checked >= 64 * 1024 ** 2:
                    disk.preflight(disk.estimate_upload(total), DATA)
                    checked = total
                output.write(chunk)
        disk.preflight(disk.estimate_upload(total), DATA)
        stored = store_source(temp, suffix, original)
        destination = link_source(stored, directory, suffix)
        meta = _probe_video(destination)
        job = _new_job(
            destination, original, meta, parsed_options, job_id=job_id,
            rights=import_rights(attested),
        )
        return {"id": job["id"], "status": job["status"]}
    except HTTPException:
        temp.unlink(missing_ok=True)
        shutil.rmtree(directory, ignore_errors=True)
        raise
    except disk.InsufficientSpace as exc:
        # An upload that runs out of room is a storage failure, not a
        # precondition: report 507 and leave no partial source behind.
        temp.unlink(missing_ok=True)
        shutil.rmtree(directory, ignore_errors=True)
        return JSONResponse(status_code=507, content=exc.as_dict())
    except OSError as exc:
        temp.unlink(missing_ok=True)
        shutil.rmtree(directory, ignore_errors=True)
        if exc.errno == errno.ENOSPC:
            return JSONResponse(
                status_code=507,
                content={"error": "insufficient_storage", "detail": "The disk filled up during upload. Nothing was kept."},
            )
        raise HTTPException(400, f"Could not ingest this video: {exc}") from exc
    except Exception as exc:
        temp.unlink(missing_ok=True)
        shutil.rmtree(directory, ignore_errors=True)
        raise HTTPException(400, f"Could not ingest this video: {exc}") from exc
    finally:
        await file.close()


@app.post("/api/jobs/path")
def job_from_path(body: PathBody) -> dict:
    _require_import_rights(body.rights)
    path = _local_video_path(body.path)
    disk.preflight(disk.estimate_path(path), DATA)
    meta = _probe_video(path)
    job_id = _requested_job_id(body.job_id)
    try:
        (JOBS / job_id).mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise HTTPException(409, "That job_id already exists.") from None
    job = _new_job(
        path.resolve(), path.name, meta, clean_options(body.options),
        job_id=job_id, rights=import_rights(body.rights),
    )
    return {"id": job["id"], "status": job["status"]}


@app.post("/api/jobs/from-url")
def job_from_url(body: FromUrlBody) -> dict:
    _require_import_rights(body.rights)
    try:
        url = _validate_remote_ingest_url(body.url)
        disk.preflight(0, DATA)
        provider_settings = _ingest_provider_settings()
        order = _ingest_provider_order(url, body.provider, provider_settings)
        options = registry.options_from_settings(provider_settings, body.ingest_options)
        chain = _ingest_provider_chain(provider_settings, order)
        inspected = chain.inspect(url, options)
        if not isinstance(inspected, dict):
            raise IngestError("The ingest provider returned an invalid inspection result.")
        if inspected.get("needs_choice") or str(inspected.get("status") or "") == "picker":
            raise HTTPException(
                409,
                "This link contains multiple items. Choose one entry from the picker.",
            )
        if inspected.get("available") is False:
            detail = (
                inspected.get("warning")
                or inspected.get("error")
                or "This link cannot be ingested."
            )
            raise HTTPException(400, str(detail))
        hint = inspected.get("filesize") or inspected.get("size_bytes")
        if hint is None:
            meta_hint = inspected.get("meta")
            if isinstance(meta_hint, dict):
                hint = meta_hint.get("filesize") or meta_hint.get("size_bytes")
        try:
            hint = disk.size_hint(hint, label="URL size hint")
        except disk.InvalidSize:
            hint = None
        if hint:
            disk.preflight(disk.estimate_upload(hint), DATA)
    except IngestError as exc:
        raise HTTPException(400, str(exc)) from exc

    provider_id = str(chain.last_provider_id or order[0])
    provider = chain.last_provider
    # If inspection already found the primary unavailable, start the download
    # with the provider that answered instead of repeating the failed attempt.
    download_order = [provider_id, *[item for item in order if item != provider_id]]
    chain = _ingest_provider_chain(provider_settings, download_order)
    analysis_options = clean_options(body.options)
    job_id = _requested_job_id(body.job_id)
    directory = JOBS / job_id
    try:
        directory.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise HTTPException(409, "That job_id already exists.") from None
    now = round(time.time(), 3)
    label = str(getattr(provider, "label", "") or provider_id)
    job = {
        "id": job_id,
        "created": now,
        "updated": now,
        "status": "downloading",
        "progress": 0.0,
        "message": "Preparing download",
        "error": None,
        "source": {"path": None, "name": "URL video"},
        "options": analysis_options,
        "ingest": {
            "provider": provider_id,
            "label": label,
            "source_url": _redact_source_url(url),
            "title": "",
            "thumbnail": None,
            "duration": None,
            "meta": {},
            "options": options.as_dict(),
            "progress": 0.0,
            "message": "Preparing download",
            "phase": "downloading",
            "status": "downloading",
            "error": None,
        },
        "analysis": None,
        "renders": {},
        "artifacts": {},
        "artifact_ids": [],
        "schema_version": artifacts.SCHEMA_VERSION,
        "render_version": artifacts.RENDER_VERSION,
        "story_id": job_id,
        "attempts": {"analysis": 0},
    }
    rights = import_rights(body.rights)
    if rights is not None:
        job["rights"] = rights
    save_job(job)

    cancel_event = threading.Event()
    INGEST_CANCELS[job_id] = cancel_event
    try:
        ingest_pool.submit(
            _run_url_ingest,
            job_id,
            chain,
            provider_id,
            label,
            url,
            options,
            cancel_event,
            analysis_options,
        )
    except Exception as exc:  # noqa: BLE001
        INGEST_CANCELS.pop(job_id, None)
        error = _short_ingest_error(exc)

        def fail(job: dict) -> None:
            job["status"] = "failed"
            job["progress"] = 1.0
            job["message"] = "URL ingest failed"
            job["error"] = error
            job.setdefault("ingest", {}).update({
                "phase": "failed",
                "status": "failed",
                "progress": 1.0,
                "message": "URL ingest failed",
                "error": error,
            })

        update_job(job_id, fail)
        _record_ingest_history(
            job_id, provider_id, url, "failed", error=error
        )
        raise HTTPException(500, "Could not start the URL download.") from exc

    return {"id": job_id, "status": "downloading", "provider": provider_id, "label": label}


# Derived job index: one row per job.json, keyed by file mtime so a row is
# re-read only when its job changes. job.json stays the source of truth; the
# index is rebuilt from it on demand and never written back.
_JOB_INDEX: dict[str, tuple[int, dict]] = {}
_JOB_INDEX_LOCK = threading.Lock()


def _job_index_row(job: dict) -> dict:
    analysis = job.get("analysis") or {}
    ingest = job.get("ingest") or {}
    source = job.get("source") or {}
    hook_id = analysis.get("hook_scene")
    hook_scene = next(
        (scene for scene in analysis.get("scenes") or []
         if isinstance(scene, dict) and scene.get("id") == hook_id),
        None,
    )
    hook_has_thumb = bool(hook_scene) and hook_scene.get("deep") is not False
    stories = [
        str(story.get("title") or "")
        for record in _clip_set_records(job)
        for story in record.get("stories") or []
        if isinstance(story, dict) and story.get("title")
    ]
    created = float(job.get("created") or 0)
    return {
        "id": job.get("id"),
        "created": job.get("created"),
        "name": source.get("name"),
        "duration": source.get("duration"),
        "status": job.get("status"),
        "progress": job.get("progress", 0),
        "message": job.get("message"),
        "error": job.get("error"),
        "provider": ingest.get("provider"),
        "provider_label": ingest.get("label") or ingest.get("provider"),
        "ingest_status": ingest.get("status"),
        "ingest_error": ingest.get("error"),
        "scene_count": analysis.get("scene_count"),
        "hook_thumb": (
            f"/api/jobs/{job['id']}/thumb/{hook_id}"
            if hook_id is not None and hook_has_thumb else None
        ),
        "story_titles": stories[:24],
        "source_deleted": bool(source.get("deleted_at")),
        "source_missing": bool(source_missing(job)),
        "_search": " ".join([
            str(job.get("id") or ""),
            str(source.get("name") or ""),
            time.strftime("%Y-%m-%d", time.localtime(created)) if created else "",
            *stories,
        ]).casefold(),
    }


def job_index() -> list[tuple[float, dict]]:
    """``(mtime, row)`` for every readable job, newest first. No cap."""
    rows: list[tuple[float, dict]] = []
    seen: set[str] = set()
    for path in JOBS.glob("*/job.json"):
        key = str(path)
        seen.add(key)
        try:
            stamp = path.stat().st_mtime_ns
        except OSError:
            continue
        with _JOB_INDEX_LOCK:
            cached = _JOB_INDEX.get(key)
        if cached is None or cached[0] != stamp:
            try:
                job = json.loads(path.read_text())
                _relocate_source(job)
                row = _job_index_row(job)
            except Exception:  # noqa: BLE001 - one unreadable job never hides the rest
                continue
            cached = (stamp, row)
            with _JOB_INDEX_LOCK:
                _JOB_INDEX[key] = cached
        rows.append((cached[0] / 1e9, cached[1]))
    with _JOB_INDEX_LOCK:
        for key in [key for key in _JOB_INDEX if key not in seen]:
            _JOB_INDEX.pop(key, None)
    rows.sort(key=lambda item: item[0], reverse=True)
    return rows


@app.get("/api/jobs")
def list_jobs(q: str = "", limit: int = 24, offset: int = 0) -> dict:
    """Search jobs by source name, job id, story title or date (YYYY-MM-DD)."""
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    terms = [term for term in str(q or "").casefold().split() if term]
    matched = [
        row for _, row in job_index()
        if all(term in row["_search"] for term in terms)
    ]
    page = [
        {key: value for key, value in row.items() if not key.startswith("_")}
        for row in matched[offset:offset + limit]
    ]
    return {
        "jobs": page,
        "total": len(matched),
        "offset": offset,
        "limit": limit,
        "q": q,
    }


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    return public_job(load_job(job_id))


@app.get("/api/jobs/{job_id}/usage")
def get_usage(job_id: str) -> dict:
    return _usage_summary(load_job(job_id))


@app.get("/api/jobs/{job_id}/status")
def get_status(job_id: str) -> dict:
    return public_status(load_job(job_id))


@app.post("/api/jobs/{job_id}/url/cancel")
def cancel_url_ingest(job_id: str) -> dict:
    job = load_job(job_id)
    event = INGEST_CANCELS.get(job_id)
    active = job.get("status") == "downloading"
    if event is not None:
        event.set()
    if active:
        def mark(job: dict) -> None:
            ingest = job.setdefault("ingest", {})
            ingest["cancel_requested"] = True
            if event is None:
                job["status"] = "failed"
                job["progress"] = 1.0
                job["message"] = "Download cancelled"
                job["error"] = "Download worker is no longer running."
                ingest.update({
                    "phase": "failed", "status": "failed", "progress": 1.0,
                    "message": "Download cancelled",
                    "error": job["error"],
                })

        try:
            job = update_job(job_id, mark)
            if event is None:
                _record_ingest_history(
                    job_id, str((job.get("ingest") or {}).get("provider") or ""),
                    str((job.get("ingest") or {}).get("source_url") or ""),
                    "failed", error=job.get("error"),
                )
        except Exception:  # noqa: BLE001
            pass
    return {"ok": True, "id": job_id, "cancelled": bool(active)}


@app.post("/api/jobs/{job_id}/reading/cancel")
def cancel_reading(job_id: str) -> dict:
    """Stop reading one video so the single analysis slot frees up.

    A queued read is dropped at once. A running one stops at its next
    checkpoint, or immediately when a speech engine is mid-file.
    """
    job = load_job(job_id)
    status = str(job.get("status") or "")
    if status not in ACTIVE and status != "queued":
        return {"ok": True, "id": job_id, "cancelled": False, "status": status}
    _analysis_cancel_event(job_id).set()
    task = analysis_pool.find_key("analysis", job_id)
    if task is None or task.state is job_queue.QueueState.QUEUED:
        analysis_pool.cancel_key("analysis", job_id)

        def mark(current: dict) -> None:
            current["status"] = "cancelled"
            current["progress"] = 1.0
            current["message"] = "Cancelled"
            current["error"] = None

        job = update_job(job_id, mark)
        ANALYSIS_CANCELS.pop(job_id, None)
    else:
        def stopping(current: dict) -> None:
            current["message"] = "Stopping…"

        job = update_job(job_id, stopping)
    return {"ok": True, "id": job_id, "cancelled": True, "status": job.get("status")}


@app.post("/api/jobs/{job_id}/reading/retry")
def retry_reading(job_id: str) -> dict:
    """Read a cancelled, failed or interrupted video again."""
    job = load_job(job_id)
    if job.get("status") not in {"cancelled", "failed", "interrupted"}:
        raise HTTPException(409, "This video is not stopped, so it can't be read again.")
    source = Path(str((job.get("source") or {}).get("path") or ""))
    if not source.is_file():
        raise HTTPException(409, f"The original file was moved or deleted: {source}")
    ANALYSIS_CANCELS.pop(job_id, None)

    def mark(current: dict) -> None:
        current["status"] = "queued"
        current["progress"] = 0.0
        current["message"] = "Queued"
        current["error"] = None

    job = update_job(job_id, mark)
    analysis_pool.submit(run_analysis, job_id)
    return {"ok": True, "id": job_id, "status": job.get("status")}


@app.get("/api/jobs/{job_id}/history")
def get_history(job_id: str, limit: int | None = None) -> dict:
    load_job(job_id)
    entries = history_store.list_entries(_job_dir(job_id), limit=limit)
    return {"entries": entries, "count": len(entries)}


@app.get("/api/jobs/{job_id}/history/{entry_id}")
def get_history_entry(job_id: str, entry_id: str) -> dict:
    load_job(job_id)
    item = history_store.get_entry(_job_dir(job_id), entry_id)
    if not item:
        raise HTTPException(404, "History entry not found.")
    return item


@app.delete("/api/jobs/{job_id}/history/{entry_id}")
def delete_history_entry(job_id: str, entry_id: str) -> dict:
    load_job(job_id)
    if not history_store.delete_entry(_job_dir(job_id), entry_id):
        raise HTTPException(404, "History entry not found.")
    return {"deleted": entry_id}


@app.post("/api/jobs/{job_id}/history/{entry_id}/restore")
def restore_history_entry(job_id: str, entry_id: str) -> dict:
    """Return the saved snapshot; the client decides what to apply."""
    load_job(job_id)
    item = history_store.get_entry(_job_dir(job_id), entry_id)
    if not item:
        raise HTTPException(404, "History entry not found.")
    return {"restored": True, **item}


@app.post("/api/jobs/{job_id}/scene/{scene_id}/read")
def read_scene(job_id: str, scene_id: int) -> dict:
    job = load_job(job_id)
    analysis = job.get("analysis")
    if job.get("status") != "ready" or not analysis:
        raise HTTPException(409, "Analysis is not ready yet.")
    scene = next((item for item in analysis.get("scenes", []) if item["id"] == scene_id), None)
    if not scene:
        raise HTTPException(404, "Scene not found.")
    if not scene.get("deep"):
        options = job.get("options") or {}
        pipeline.read_scene(
            job["source"]["path"], scene, _job_dir(job_id),
            bool(options.get("ocr", True)),
        )
        pipeline.score_scenes(
            analysis["scenes"], job["source"]["width"], job["source"]["height"],
        )
        if not options.get("smart_crop", True):
            for item in analysis["scenes"]:
                item["crop"] = {"cx": 0.5, "cy": 0.5}
                item["crop_mode"] = "center"
                item["crops"] = {aspect: {"cx": 0.5, "cy": 0.5} for aspect in pipeline.ASPECT_RATIOS}
                item["crop_modes"] = {aspect: "center" for aspect in pipeline.ASPECT_RATIOS}
        hook = pipeline.auto_hook(analysis["scenes"])
        analysis["hook_scene"] = hook["id"]
        analysis["deep_scene_ids"] = sorted(
            item["id"] for item in analysis["scenes"] if item.get("deep")
        )
        analysis["deep_count"] = len(analysis["deep_scene_ids"])
        analysis["plans"] = pipeline.make_plans(
            analysis["scenes"], job["source"]["duration"], None, hook["id"],
        )
        save_job(job)
    scene["thumb_url"] = f"/api/jobs/{job_id}/thumb/{scene_id}"
    return {
        "scene": scene,
        "hook_scene": analysis.get("hook_scene"),
        "deep_count": analysis.get("deep_count"),
        "plans": analysis.get("plans"),
    }


@app.get("/api/jobs/{job_id}/thumb/{scene_id}")
def get_thumb(job_id: str, scene_id: int) -> FileResponse:
    if scene_id < 0 or scene_id > 5000:
        raise HTTPException(404, "Still not found.")
    path = _job_dir(job_id) / "thumbs" / f"{scene_id:05d}.jpg"
    if not path.is_file():
        raise HTTPException(404, "Still not found.")
    return FileResponse(
        path, media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@app.get("/api/jobs/{job_id}/media/{filename}")
def get_media(job_id: str, filename: str) -> FileResponse:
    if not (filename.startswith("reel_") and (filename.endswith(".mp4") or filename.endswith(".jpg"))):
        raise HTTPException(404, "Media not found.")
    if "/" in filename or ".." in filename:
        raise HTTPException(404, "Media not found.")
    path = _job_dir(job_id) / "renders" / filename
    if not path.is_file():
        raise HTTPException(404, "Media not found.")
    media_type = "video/mp4" if filename.endswith(".mp4") else "image/jpeg"
    return FileResponse(
        path, media_type=media_type,
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/api/jobs/{job_id}/artifacts")
def get_artifacts(job_id: str) -> dict:
    job, adopted = _adopt_ready_artifacts(job_id)
    job_dir = _job_dir(job_id)
    manifests = artifacts.list_manifests(job_dir)
    rows = [
        {
            **artifacts.public_manifest(item, job_id),
            "versions": artifacts.version_info(job_dir, item),
        }
        for item in manifests
    ]
    return {
        "artifacts": rows,
        "artifact_ids": [item["artifact_id"] for item in rows],
        "adopted": [
            artifacts.public_manifest(item, job_id) for item in adopted
        ],
        "adopted_ids": [item["artifact_id"] for item in adopted],
        "renders": {
            key: _public_render(job_id, record)
            for key, record in (job.get("renders") or {}).items()
        },
    }


@app.get("/api/jobs/{job_id}/artifacts/{artifact_id}")
def get_artifact(job_id: str, artifact_id: str) -> dict:
    load_job(job_id)
    manifest = artifacts.load_manifest(_job_dir(job_id), artifact_id)
    if manifest is None:
        raise HTTPException(404, "Artifact not found.")
    public = {
        **artifacts.public_manifest(manifest, job_id),
        "versions": artifacts.version_info(_job_dir(job_id), manifest),
    }
    return {**public, "artifact": public}


@app.post("/api/jobs/{job_id}/artifacts/{artifact_id}/pin")
def pin_artifact(job_id: str, artifact_id: str, body: PinBody | None = None) -> dict:
    pinned = True if body is None else bool(body.pinned)
    job_dir = _job_dir(job_id)
    result: dict = {}

    def mutate(job: dict) -> None:
        manifest = artifacts.pin_artifact(job_dir, artifact_id, pinned)
        if manifest is None:
            raise HTTPException(404, "Artifact not found.")
        result["manifest"] = manifest
        artifacts.ensure_job_schema(job, job_dir)

    update_job(job_id, mutate)
    manifest = result["manifest"]
    public = {
        **artifacts.public_manifest(manifest, job_id),
        "versions": artifacts.version_info(_job_dir(job_id), manifest),
    }
    return {**public, "artifact": public}


@app.delete("/api/jobs/{job_id}/artifacts/{artifact_id}")
def delete_artifact(job_id: str, artifact_id: str) -> dict:
    load_job(job_id)
    job_dir = _job_dir(job_id)
    removed: list[str] = []

    def mutate(job: dict) -> None:
        manifest = artifacts.load_manifest(job_dir, artifact_id)
        if manifest is None:
            raise HTTPException(404, "Artifact not found.")
        if manifest.get("status") in ACTIVE_RENDER:
            raise HTTPException(409, "This artifact is still rendering.")
        records = [
            record for record in (job.get("renders") or {}).values()
            if isinstance(record, dict) and record.get("artifact_id") == artifact_id
        ]
        try:
            protected = _protected_artifact_ids(
                job, [manifest], strict_shares=True,
            )
        except shares.ShareStoreError as exc:
            raise _share_store_unavailable(exc) from exc
        if (
            manifest.get("pinned")
            or artifact_id in protected
            or any(record.get("pinned") for record in records)
        ):
            raise HTTPException(
                409, "Pinned, shared, or packet-referenced artifacts cannot be deleted."
            )
        if not artifacts.delete_artifact(job_dir, artifact_id):
            raise HTTPException(404, "Artifact not found.")
        for record in records:
            for name in (record.get("path"), record.get("poster")):
                _safe_unlink(job_dir, name)
        removed.extend(artifacts.remove_projection(job, artifact_id))
        artifacts.ensure_job_schema(job, job_dir)

    update_job(job_id, mutate)
    return {"deleted": artifact_id, "renders": removed}


@app.get("/api/jobs/{job_id}/artifacts/{artifact_id}/media/{filename}")
def get_artifact_media(job_id: str, artifact_id: str, filename: str) -> FileResponse:
    load_job(job_id)
    if filename not in artifacts.MEDIA_NAMES:
        raise HTTPException(404, "Artifact media not found.")
    try:
        path = artifacts.media_path(_job_dir(job_id), artifact_id, filename)
    except (artifacts.ArtifactError, OSError) as exc:
        raise HTTPException(404, "Artifact media not found.") from exc
    if not path.is_file():
        raise HTTPException(404, "Artifact media not found.")
    media_type = {
        "reel.mp4": "video/mp4",
        "poster.jpg": "image/jpeg",
        "captions.srt": "application/x-subrip; charset=utf-8",
        "captions.vtt": "text/vtt; charset=utf-8",
    }.get(filename, "application/octet-stream")
    return FileResponse(
        path, media_type=media_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@app.post("/api/jobs/{job_id}/artifacts/{artifact_id}/reveal")
def reveal_artifact(job_id: str, artifact_id: str) -> dict:
    """Show one finished cut in Finder. Local Mac only; nothing leaves the machine."""
    load_job(job_id)
    try:
        path = artifacts.media_path(_job_dir(job_id), artifact_id, "reel.mp4")
    except (artifacts.ArtifactError, OSError) as exc:
        raise HTTPException(404, "Artifact media not found.") from exc
    if not path.is_file():
        raise HTTPException(404, "Artifact media not found.")
    if sys.platform != "darwin":
        raise HTTPException(501, "Reveal in Finder works on a Mac only.")
    try:
        subprocess.Popen(
            ["open", "-R", str(path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise HTTPException(500, "Could not open Finder.") from exc
    return {"revealed": True, "path": str(path)}


@app.get("/api/jobs/{job_id}/artifacts/{artifact_id}/captions")
def get_artifact_captions(job_id: str, artifact_id: str) -> dict:
    """Caption-only preview of the exact cues saved for one artifact."""
    load_job(job_id)
    job_dir = _job_dir(job_id)
    manifest = artifacts.load_manifest(job_dir, artifact_id)
    if manifest is None:
        raise HTTPException(404, "Artifact not found.")
    path = artifacts.media_path(job_dir, artifact_id, "captions.srt")
    if not path.is_file():
        raise HTTPException(404, "Artifact captions not found.")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise HTTPException(404, "Artifact captions not found.") from exc
    cues = caption_engine.parse_srt(text)
    base = f"/api/jobs/{job_id}/artifacts/{artifact_id}/media"
    return {
        "artifact_id": artifact_id,
        "cue_count": len(cues),
        "cues": cues,
        "srt_url": f"{base}/captions.srt",
        "vtt_url": f"{base}/captions.vtt",
    }


@app.get("/api/shares")
def get_shares(job_id: str | None = None) -> dict:
    """List review links without returning capabilities.

    A token is only returned once at creation or by the loopback-only,
    job-scoped re-copy endpoint. Listing never exposes a token, even if an
    unknown query parameter asks for it.
    """
    try:
        rows = shares.list_records(SHARES, include_tokens=False, strict=True)
    except shares.ShareStoreError as exc:
        raise _share_store_unavailable(exc) from exc
    if job_id:
        rows = [row for row in rows if row.get("job_id") == job_id]
    return {"shares": rows, "count": len(rows)}


@app.patch("/api/shares/{token}")
def patch_share(token: str, body: SharePatchBody) -> dict:
    fields = body.model_fields_set
    updates: dict = {}
    if "label" in fields:
        updates["label"] = body.label or ""
    if "expires_at" in fields:
        updates["expires_at"] = body.expires_at
    elif "expires_in_days" in fields:
        if body.expires_in_days is not None and float(body.expires_in_days) < 0:
            raise HTTPException(400, "expires_in_days cannot be negative.")
        updates["expires_in_days"] = body.expires_in_days
    if "revoked" in fields:
        updates["revoked"] = bool(body.revoked)
    try:
        record = shares.patch(token, updates, SHARES)
    except shares.ShareStoreError as exc:
        raise _share_store_unavailable(exc) from exc
    if record is None:
        raise HTTPException(404, "Share not found.")
    return {**record, "share": record}


@app.delete("/api/shares/{token}")
def delete_share(token: str) -> dict:
    try:
        deleted = shares.delete(token, SHARES)
    except shares.ShareStoreError as exc:
        raise _share_store_unavailable(exc) from exc
    if not deleted:
        raise HTTPException(404, "Share not found.")
    return {"deleted": True}


def _valid_target(target: int) -> int:
    if target not in (15, 30, 60):
        raise HTTPException(400, "Target must be 15, 30 or 60 seconds.")
    return target


def _ensure_scene_deep(job: dict, scene: dict) -> None:
    if scene.get("deep", True):
        return
    analysis = job["analysis"]
    options = job.get("options") or {}
    pipeline.read_scene(
        job["source"]["path"], scene, _job_dir(job["id"]),
        bool(options.get("ocr", True)),
    )
    pipeline.score_scenes(
        analysis["scenes"], job["source"]["width"], job["source"]["height"],
    )
    if not options.get("smart_crop", True):
        scene["crop"] = {"cx": 0.5, "cy": 0.5}
        scene["crop_mode"] = "center"
    analysis["deep_scene_ids"] = sorted(
        item["id"] for item in analysis["scenes"] if item.get("deep")
    )
    analysis["deep_count"] = len(analysis["deep_scene_ids"])
    save_job(job)


def _plan_for(job: dict, target: int, hook_scene: int | None) -> dict:
    analysis = job.get("analysis")
    if job.get("status") != "ready" or not analysis:
        raise HTTPException(409, "Analysis is not ready yet.")
    scenes = analysis["scenes"]
    if hook_scene is not None:
        scene = next((item for item in scenes if item["id"] == hook_scene), None)
        if not scene:
            raise HTTPException(400, "Hook scene does not exist.")
        _ensure_scene_deep(job, scene)
    plan = pipeline.build_plan(
        scenes,
        job["source"]["duration"],
        target,
        hook_scene,
        analysis.get("hook_scene"),
    )
    plan["_source_lang"] = (
        (analysis.get("engine") or {}).get("transcript_language") or "en"
    )
    return plan


def _manual_plan_reasoning(plan: dict, note: str, source_duration: float) -> dict:
    """Truthful reasoning for a manually edited, custom, or arc-ordered cut.

    Automatic hook/payoff/selection claims no longer describe the resulting
    clips, so this deliberately drops those claims and reports only what can
    be verified from the current clip list.
    """
    clips = [clip for clip in plan.get("clips", []) if isinstance(clip, dict)]
    total = round(sum(float(clip.get("dur") or 0.0) for clip in clips), 3)
    body = [clip for clip in clips if str(clip.get("role") or "") == "beat"]
    body_order = all(
        float(body[index].get("start") or 0.0)
        <= float(body[index + 1].get("start") or 0.0) + 0.001
        for index in range(len(body) - 1)
    )
    starts = [float(clip.get("start") or 0.0) for clip in clips]
    ends = [float(clip.get("end") or 0.0) for clip in clips]
    target = int(plan.get("target") or 30)
    hook = clips[0] if clips else {}
    payoff = clips[-1] if clips else {}
    hook_scene = hook.get("scene")
    payoff_scene = payoff.get("scene")
    order_text = (
        "Bridge beats remain in source order."
        if body_order
        else "Bridge beats were reordered; source order no longer holds."
    )
    return {
        "target": target,
        "source_duration": round(float(source_duration or 0.0), 3),
        "summary": (
            f"{note}: {len(clips)} clip{'s' if len(clips) != 1 else ''}, "
            f"{total:.1f}s of a {target}s target. {order_text} "
            "Automatic hook/payoff scoring does not describe this manual cut."
        ),
        "hook": {
            "headline": (
                f"Manual opening: scene {hook_scene + 1}."
                if isinstance(hook_scene, int) else "Manual opening."
            ),
            "evidence": ["opening clip supplied by the manual edit"],
            "alternatives": [],
        },
        "structure": {
            "roles": [str(clip.get("role") or "beat") for clip in clips],
            "clip_count": len(clips),
            "beat_count": len(body),
            "body_order": "source" if body_order else "manual",
            "body_in_source_order": body_order,
            "hook_first": bool(clips and str(clips[0].get("role")) == "hook"),
            "source_span": {
                "start": round(min(starts), 3) if starts else None,
                "end": round(max(ends), 3) if ends else None,
            },
            "why": (
                f"{note} controls the clip list. {order_text} "
                "The original automatic hook/payoff explanation is not used."
            ),
        },
        "payoff": {
            "headline": (
                f"Manual ending: scene {payoff_scene + 1}."
                if isinstance(payoff_scene, int) else "Manual ending."
            ),
            "evidence": ["last clip supplied by the manual edit"],
            "why_late": None,
            "position_pct": None,
            "late_zone_pct": round(pipeline.PAYOFF_ZONE * 100, 1),
            "candidates": 0,
        },
        "selection": {
            "strategy": (
                f"{note}: automatic ranking, spacing, and budget claims were "
                "replaced by the manual clip list."
            ),
            "evidence": [
                f"{len(clips)} manual clips totalling {total:.1f}s",
                order_text,
                "re-run automatic Smart Cut to restore scored reasoning",
            ],
            "kept": [
                {
                    "scene": clip.get("scene"),
                    "role": str(clip.get("role") or "beat"),
                    "start": round(float(clip.get("start") or 0.0), 3),
                    "end": round(float(clip.get("end") or 0.0), 3),
                    "dur": round(float(clip.get("dur") or 0.0), 3),
                    "why": str(clip.get("why") or ""),
                    "evidence": [],
                }
                for clip in clips
            ],
            "target_budget": {
                "target": target,
                "source_duration": round(float(source_duration or 0.0), 3),
                "total": total,
                "headroom": round(max(0.0, target - total), 3),
                "over_target": round(max(0.0, total - target), 3),
            },
        },
    }


def _custom_plan(
    job: dict,
    target: int,
    hook_scene: int | None,
    clips: list[dict] | None,
) -> dict:
    analysis = job.get("analysis")
    if job.get("status") != "ready" or not analysis:
        raise HTTPException(409, "Analysis is not ready yet.")
    scenes = analysis["scenes"]
    by_id = {scene["id"]: scene for scene in scenes}
    hook_id = hook_scene if hook_scene is not None else analysis.get("hook_scene")
    hook = by_id.get(hook_id) if hook_id is not None else None
    if hook_id is not None and not hook:
        raise HTTPException(400, "Hook scene does not exist.")
    if hook:
        _ensure_scene_deep(job, hook)

    built: list[dict] = []
    for raw in (clips or [])[:240]:
        try:
            scene_id = int(raw.get("scene"))
        except (TypeError, ValueError):
            raise HTTPException(400, "Every clip needs a scene id.") from None
        scene = by_id.get(scene_id)
        if not scene:
            raise HTTPException(400, f"Scene {scene_id + 1} does not exist.")
        if not scene.get("deep", True):
            raise HTTPException(400, f"Scene {scene_id + 1} is not deep-read yet.")
        start = max(float(scene["start"]), float(raw.get("start", scene["start"])))
        end = min(float(scene["end"]), float(raw.get("end", scene["end"])))
        if end - start < 0.2:
            raise HTTPException(400, f"Clip on scene {scene_id + 1} is shorter than 0.2s.")
        role = str(raw.get("role") or "beat")[:12]
        built.append({
            "scene": scene_id,
            "start": round(start, 3),
            "end": round(end, 3),
            "dur": round(end - start, 3),
            "role": role,
            "why": f"Manual {role}: {end - start:.1f}s at {start:.1f}s.",
        })
    if not built:
        raise HTTPException(400, "The cut is empty.")
    total = round(sum(clip["dur"] for clip in built), 3)
    hook_clip = next((clip for clip in built if clip["role"] == "hook"), built[0])
    payoff_clip = next((clip for clip in built if clip["role"] == "payoff"), None)
    value = {
        "target": int(target),
        "total": total,
        "hook_scene": hook["id"] if hook else built[0]["scene"],
        "auto": False,
        "clip_count": len(built),
        "clips": built,
        "note": "Manual edit",
        "hook_why": hook_clip.get("why") or None,
        "payoff_why": (payoff_clip or {}).get("why") or None,
        "_source_lang": (
            (analysis.get("engine") or {}).get("transcript_language") or "en"
        ),
    }
    value["reasoning"] = _manual_plan_reasoning(
        value, "Manual edit", float((job.get("source") or {}).get("duration") or 0.0)
    )
    value["hook_why"] = value["reasoning"]["hook"]["headline"]
    value["payoff_why"] = value["reasoning"]["payoff"]["headline"]
    return value


def _apply_order(job: dict, plan: dict, order: str) -> dict:
    if order != "arc":
        return plan
    scenes = (job.get("analysis") or {}).get("scenes") or []
    ordered = pipeline.arc_order(plan["clips"], scenes)
    if ordered == plan["clips"]:
        plan["order"] = "arc"
        return plan
    total = round(sum(float(clip.get("dur") or 0.0) for clip in ordered), 3)
    value = {
        **plan,
        "clips": ordered,
        "clip_count": len(ordered),
        "total": total,
        "order": "arc",
    }
    value["reasoning"] = _manual_plan_reasoning(
        value,
        "Story-arc order",
        float((job.get("source") or {}).get("duration") or 0.0),
    )
    value["hook_why"] = value["reasoning"]["hook"]["headline"]
    value["payoff_why"] = value["reasoning"]["payoff"]["headline"]
    return value


def _plan_for_body(job: dict, target: int, body: PlanBody) -> dict:
    if body.clips is not None:
        return _apply_order(job, _custom_plan(job, target, body.hook_scene, body.clips), body.order)
    return _apply_order(job, _plan_for(job, target, body.hook_scene), body.order)


def _caption_style_for(
    style_id: str | None = None,
    overrides: dict | None = None,
    margin: float | None = None,
) -> dict:
    try:
        style = caption_engine.resolve_style(
            style_id,
            settings=settings_store.load_settings(),
            overrides=overrides,
        )
        explicit_zone = bool(
            isinstance(overrides, dict)
            and ("safe_zone" in overrides or "safe-zone" in overrides)
        )
        if margin is not None and style_id is None and not explicit_zone:
            style = caption_engine.apply_margin(style, margin)
        return style
    except caption_engine.CaptionStyleError as exc:
        raise HTTPException(400, str(exc)) from exc


def _attach_caption_track(plan: dict, track: caption_engine.CaptionTrack | None) -> None:
    if track is None:
        return
    plan["_caption_track"] = track.to_dict()
    plan["_caption_cues"] = [cue.to_dict() for cue in track.cues]
    plan["_caption_style"] = dict(track.style)
    plan["_caption_key"] = track.id


def _caption_track_by_id(job_id: str, track_id: str) -> caption_engine.CaptionTrack:
    track = caption_engine.load_track(_job_dir(job_id), track_id)
    if track is None:
        raise HTTPException(404, "Caption track not found.")
    return track


def _track_validation_clips(track: caption_engine.CaptionTrack) -> list[dict]:
    return [
        {
            "start": 0.0,
            "end": float(window.get("duration") or 0.0),
            "dur": float(window.get("duration") or 0.0),
            "scene": window.get("scene"),
        }
        for window in track.clip_windows
    ]


def _default_caption_track(
    job_id: str,
    job: dict,
    plan: dict,
    style_id: str | None = None,
    overrides: dict | None = None,
    margin: float | None = None,
) -> caption_engine.CaptionTrack:
    style = _caption_style_for(style_id, overrides, margin)
    try:
        return caption_engine.build_track(
            job,
            plan,
            style,
            job_dir=_job_dir(job_id),
        )
    except caption_engine.CaptionError as exc:
        raise HTTPException(400, str(exc)) from exc


def _caption_track_for_render(
    job_id: str,
    job: dict,
    plan: dict,
    body: PlanBody,
    enabled: bool,
    margin: float | None = None,
) -> caption_engine.CaptionTrack | None:
    if not enabled:
        return None
    if body.caption_track_id:
        if body.caption_style_id or body.caption_style:
            raise HTTPException(
                400,
                "Style belongs to the caption track. PATCH the track or omit its id.",
            )
        track = _caption_track_by_id(job_id, body.caption_track_id)
        if track.clip_hash != caption_engine.clip_hash(plan.get("clips")):
            raise HTTPException(
                409, "The caption track does not match this cut. Rebuild the track.",
            )
        return track
    return _default_caption_track(
        job_id, job, plan, body.caption_style_id, body.caption_style, margin,
    )


def _caption_poster_url(job: dict, track: caption_engine.CaptionTrack) -> str | None:
    records = [
        record for record in (job.get("renders") or {}).values()
        if record.get("status") == "ready" and record.get("poster")
    ]
    records.sort(key=lambda item: float(item.get("updated") or 0), reverse=True)
    if records:
        public = _public_render(job["id"], records[0]) or {}
        if public.get("poster_url"):
            return str(public["poster_url"])
    if track.clip_windows:
        scene = track.clip_windows[0].get("scene")
        if scene is not None:
            return f"/api/jobs/{job['id']}/thumb/{int(scene)}"
    return None


def _caption_track_payload(track: caption_engine.CaptionTrack) -> dict:
    return track.to_dict()


@app.post("/api/jobs/{job_id}/plan")
def make_plan(job_id: str, body: PlanBody) -> dict:
    job = load_job(job_id)
    target = _valid_target(int(body.target))
    plan = _plan_for_body(job, target, body)
    result = {"plan": plan}
    if body.hook_scene is not None:
        scene = next(
            (item for item in job["analysis"]["scenes"] if item["id"] == body.hook_scene),
            None,
        )
        if scene:
            scene["thumb_url"] = f"/api/jobs/{job_id}/thumb/{scene['id']}"
            result["scene"] = scene
    return result


def _top_hooks(job: dict, target: int, limit: int = 8) -> list[dict]:
    analysis = job.get("analysis") or {}
    scenes = [
        scene for scene in analysis.get("scenes", [])
        if scene.get("deep", True) and not scene.get("black") and scene["dur"] >= 0.55
    ]
    scenes.sort(key=lambda scene: (scene["hook"], -scene["start"]), reverse=True)
    return scenes[: max(1, limit)]


@app.get("/api/jobs/{job_id}/hooks")
def hook_candidates(job_id: str, target: int = 30, limit: int = 8) -> dict:
    job = load_job(job_id)
    analysis = job.get("analysis")
    if job.get("status") != "ready" or not analysis:
        raise HTTPException(409, "Analysis is not ready yet.")
    target = _valid_target(int(target))
    limit = max(1, min(int(limit), 24))
    scenes = _top_hooks(job, target, limit)
    hooks: list[dict] = []
    for scene in scenes[:limit]:
        plan = pipeline.build_plan(
            analysis["scenes"], job["source"]["duration"], target,
            scene["id"], analysis.get("hook_scene"),
        )
        hooks.append({
            "scene": scene["id"],
            "start": scene["start"],
            "end": scene["end"],
            "dur": scene["dur"],
            "hook": scene["hook"],
            "score": scene["score"],
            "tags": scene.get("tags", []),
            "ocr": scene.get("ocr", ""),
            "speech": scene.get("speech", ""),
            "plan_total": plan["total"],
            "clip_count": plan["clip_count"],
            "why": pipeline.hook_reason(scene, analysis["scenes"]),
            "thumb_url": f"/api/jobs/{job_id}/thumb/{scene['id']}",
        })
    if pipeline.llm_available():
        order = pipeline.llm_rank_hooks(hooks, target)
        if order:
            rank = {scene_id: index for index, scene_id in enumerate(order)}
            hooks.sort(key=lambda hook: rank.get(hook["scene"], len(rank)))
    return {"hooks": hooks, "target": target, "llm": pipeline.llm_available()}


@app.post("/api/jobs/{job_id}/variants")
def save_variant(job_id: str, body: VariantBody) -> dict:
    job = load_job(job_id)
    target = _valid_target(int(body.target))
    plan = _custom_plan(job, target, body.hook_scene, body.clips)
    variant = {
        "id": uuid.uuid4().hex[:8],
        "name": (body.name.strip()[:40] or f"{target}s edit"),
        "target": target,
        "hook_scene": plan["hook_scene"],
        "total": plan["total"],
        "clip_count": plan["clip_count"],
        "clips": plan["clips"],
        "reasoning": plan.get("reasoning"),
        "created": round(time.time(), 3),
    }

    def mutate(value: dict) -> None:
        value.setdefault("variants", []).append(variant)

    result = update_job(job_id, mutate)
    return {"variant": variant, "variants": result.get("variants", [])}


@app.delete("/api/jobs/{job_id}/variants/{variant_id}")
def delete_variant(job_id: str, variant_id: str) -> dict:
    load_job(job_id)
    removed: list[dict] = []

    def mutate(job: dict) -> None:
        variants = job.setdefault("variants", [])
        for index, variant in enumerate(variants):
            if variant.get("id") == variant_id:
                removed.append(variants.pop(index))
                break

    result = update_job(job_id, mutate)
    if not removed:
        raise HTTPException(404, "Variant not found.")
    return {"variants": result.get("variants", [])}


#: A voice task's request waits this long before it answers "running" and
#: the page polls. Most speech re-reads and scripts finish inside it.
VOICE_TASK_WAIT_S = 20.0
VOICE_TASK_KINDS = ("transcribe", "script")
VOICE_TASKS: dict[tuple[str, str], str] = {}
VOICE_CANCELS: dict[tuple[str, str], threading.Event] = {}


def _voice_task_run(work, cancel: threading.Event) -> dict:
    """Keep an HTTPException's status and message across the queue."""
    try:
        return {"ok": True, "result": work(cancel)}
    except HTTPException as exc:
        return {"ok": False, "status": exc.status_code, "detail": str(exc.detail)}


def _voice_task_reply(kind: str, job_id: str, task):
    if task is None:
        return {"kind": kind, "state": "idle"}
    if not task.terminal:
        return JSONResponse(status_code=202, content={
            "kind": kind, "state": task.status, "task_id": task.id,
        })
    if task.state in (job_queue.QueueState.CANCELLED, job_queue.QueueState.INTERRUPTED):
        raise HTTPException(409, "Cancelled. The video was not updated.")
    outcome = task.result if isinstance(task.result, dict) else None
    if task.state is job_queue.QueueState.FAILED or outcome is None:
        raise HTTPException(500, task.error or "The task failed.")
    if not outcome.get("ok"):
        raise HTTPException(int(outcome.get("status") or 500), outcome.get("detail") or "The task failed.")
    return outcome["result"]


def _voice_task(kind: str, job_id: str, work, *, reuse: bool):
    """Run ``work(cancel)`` on the voice pool; answer now if it is quick.

    ``reuse`` returns a running task of the same kind instead of starting a
    second one; otherwise a running task is a 409.
    """
    active = voice_pool.find_key(kind, job_id)
    if active is not None and not active.terminal:
        if not reuse:
            raise HTTPException(409, "This is already running for this video. Wait for it, or cancel it.")
        task = active
    else:
        cancel = threading.Event()
        VOICE_CANCELS[(kind, job_id)] = cancel
        task = voice_pool.submit_tracked(
            _voice_task_run, work, cancel, kind=kind, key=job_id,
        )
        VOICE_TASKS[(kind, job_id)] = task.id
    task.wait(VOICE_TASK_WAIT_S)
    return _voice_task_reply(kind, job_id, task)


@app.get("/api/jobs/{job_id}/voice-tasks/{kind}")
def voice_task_state(job_id: str, kind: str):
    """Poll a speech re-read or script task: 202 while it runs, then its result."""
    if kind not in VOICE_TASK_KINDS:
        raise HTTPException(404, "Unknown task.")
    load_job(job_id)
    task_id = VOICE_TASKS.get((kind, job_id))
    return _voice_task_reply(kind, job_id, voice_pool.get(task_id) if task_id else None)


@app.delete("/api/jobs/{job_id}/voice-tasks/{kind}")
def cancel_voice_task(job_id: str, kind: str, request: Request) -> dict:
    """Cancel it. A cloud call already in flight finishes, but its result is dropped."""
    if not _setup_origin_ok(request):
        raise HTTPException(403, "Cross-site writes are blocked.")
    if kind not in VOICE_TASK_KINDS:
        raise HTTPException(404, "Unknown task.")
    load_job(job_id)
    cancel = VOICE_CANCELS.get((kind, job_id))
    if cancel is not None:
        cancel.set()
    voice_pool.cancel_key(kind, job_id)
    return {"kind": kind, "state": "cancelled"}


class ScriptBriefBody(BaseModel):
    brief: str
    language: str = ""

    model_config = {"extra": "forbid"}


@app.post("/api/jobs/{job_id}/script-brief")
def write_script_brief(job_id: str, body: ScriptBriefBody, request: Request):
    """Write a voice script for a video with no speech, from a brief.

    The brief gives the topic, tone and mood or what to say, with exact lines
    in ``[script:"..."]``. The script is saved as the job's transcript, so
    Find stories cuts on it and story renders voice it over.
    """
    if not _setup_origin_ok(request):
        raise HTTPException(403, "Cross-site writes are blocked.")
    job = load_job(job_id)
    if job.get("status") != "ready":
        raise HTTPException(409, "Wait for the video to finish reading first.")
    transcript_info = (job.get("analysis") or {}).get("transcript") or {}
    engine = ((job.get("analysis") or {}).get("engine") or {}).get("transcript_provider")
    if transcript_info.get("segments") and engine not in (None, "", silent_script.ENGINE):
        raise HTTPException(
            409,
            "This video already has spoken words to cut stories on. A written script is for videos with no speech.",
        )

    def work(cancel: threading.Event) -> dict:
        try:
            result = silent_script.write_script(
                job, _job_dir(job_id), body.brief, language=body.language,
            )
        except silent_script.ScriptError as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc
        transcript = result["transcript"]

        def apply(record: dict) -> None:
            analysis = record.setdefault("analysis", {})
            pipeline.attach_speech(analysis.get("scenes") or [], transcript)
            analysis["transcript"] = {
                "language": result["language"],
                "text": str(transcript.get("text") or "")[:1000],
                "segments": result["lines"],
                "no_speech": False,
            }
            engine_info = analysis.setdefault("engine", {})
            engine_info["transcript_provider"] = silent_script.ENGINE
            engine_info["transcript_language"] = result["language"]
            record["script_brief"] = {
                "brief": result["brief"],
                "language": result["language"],
                "model": result["model"],
                "lines": result["lines"],
                "transcript_id": transcript.get("id"),
                "created": round(time.time(), 3),
            }

        if cancel.is_set():
            raise HTTPException(409, "Cancelled. The video was not updated.")
        update_job(job_id, apply)
        return {key: value for key, value in result.items() if key != "transcript"}

    return _voice_task("script", job_id, work, reuse=False)


@app.get("/api/jobs/{job_id}/transcript")
def job_transcript(job_id: str) -> dict:
    job = load_job(job_id)
    analysis = job.get("analysis") or {}
    path = _job_dir(job_id) / "transcript" / "transcript.json"
    if not path.is_file():
        summary = analysis.get("transcript") or {}
        if summary.get("text"):
            return {
                "available": False,
                "language": summary.get("language"),
                "text": summary.get("text", ""),
                "segments": [],
                "note": "Only the transcript summary was kept for this job.",
            }
        raise HTTPException(404, "No transcript for this job.")
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(500, f"Could not read the transcript: {exc}") from exc
    segments = []
    for item in data.get("segments", []):
        text = " ".join(str(item.get("text") or "").split())
        if not text:
            continue
        segments.append({
            "start": round(float(item.get("start", 0.0)), 2),
            "end": round(float(item.get("end", 0.0)), 2),
            "text": text,
        })
        if len(segments) >= 1200:
            break
    return {
        "available": True,
        "language": data.get("language"),
        "text": str(data.get("text") or "")[:4000],
        "segments": segments,
        "count": len(segments),
    }


# ---------------------------------------------------------------- clip sets


class ClipSetCreateBody(BaseModel):
    count: int = 3
    min_s: float = clipset.MIN_STORY_S
    max_s: float = clipset.MAX_STORY_S
    locks: list[int] = Field(default_factory=list)
    ban_scenes: list[int] = Field(default_factory=list)
    order: str = "source"


class ClipSetPatchBody(BaseModel):
    stories: list[dict] | None = None
    excluded_sentences: list[int] | None = None
    locks: list[int] | None = None
    ban_scenes: list[int] | None = None
    bans: list[int] | None = None
    order: str | None = None
    expected_revision: int | None = None


class ClipSetPlansBody(BaseModel):
    target: int | None = None


STORY_ASPECTS = ("9:16", "4:5", "1:1", "16:9", "16:10")


class StoryRenderBody(BaseModel):
    target: int | None = None
    quality: str = "final"
    aspect: str = "9:16"
    captions: bool = True
    caption_track_id: str | None = None


class SelectionV2Body(BaseModel):
    set_id: str | None = None
    prompt: str = ""
    exclusions: list[str] = Field(default_factory=list)
    count: int | None = None


class HookMatrixBody(BaseModel):
    set_id: str | None = None
    story_id: str | None = None
    prompt: str = ""
    exclusions: list[str] = Field(default_factory=list)
    count: int = 3


def _clipset_job(job_id: str) -> dict:
    job = load_job(job_id)
    if job.get("status") != "ready" or not job.get("analysis"):
        raise HTTPException(409, "Analysis is not ready yet.")
    require_source(job)
    return job


def _clipset_sentences(
    job: dict,
    record: dict | None = None,
) -> tuple[list[dict], list[dict], list[dict] | None]:
    """Source sentences the way ``record`` was built (new sets: word-timed).

    Clip sets made before word timing kept character-share sentence edges;
    they are re-read the same way so their fingerprint still matches.
    """
    scenes = list((job.get("analysis") or {}).get("scenes") or [])
    words = record is None or record.get("sentence_timing") == "words"
    try:
        transcript = pipeline.read_transcript(_job_dir(job["id"]), words=words)
    except Exception:  # noqa: BLE001
        transcript = None
    return clipset.source_sentences(scenes, transcript), scenes, transcript


def _clipset_pool(
    job: dict,
    record: dict | None = None,
) -> tuple[list[dict], list[dict], list[dict] | None]:
    """Keep stored sentence ids usable after a transcript cleanup."""
    sentences, scenes, transcript = _clipset_sentences(job, record)
    if record:
        pool = {
            int(sentence["id"]): sentence
            for sentence in sentences
            if sentence.get("id") is not None
        }
        for story in record.get("stories") or []:
            for sentence in story.get("sentences") or []:
                try:
                    sentence_id = int(sentence.get("id"))
                except (TypeError, ValueError):
                    continue
                pool.setdefault(sentence_id, sentence)
        sentences = [pool[key] for key in sorted(pool)]
    return sentences, scenes, transcript


def _clip_set_source_state(
    job: dict,
    record: dict,
    *,
    require_fingerprint: bool = False,
) -> tuple[list[dict], str | None]:
    """Reject stale sets and warn about legacy sets without a fingerprint."""
    current, _, _ = _clipset_sentences(job, record)
    stored = str(record.get("source_fingerprint") or "")
    if not stored:
        message = (
            "Clip set has no source fingerprint; source freshness is unverified."
        )
        if require_fingerprint:
            raise HTTPException(409, message + " Regenerate the clip set.")
        return current, message
    if clipset.source_fingerprint(current) != stored:
        raise HTTPException(
            409,
            "Clip set source changed since it was built; regenerate the clip set.",
        )
    return current, None


def _clip_set_records(job: dict) -> list[dict]:
    value = job.get("clip_sets") or []
    if isinstance(value, dict):
        return [record for record in value.values() if isinstance(record, dict)]
    return [record for record in value if isinstance(record, dict)]


def _clip_set_in_job(job: dict, set_id: str) -> dict:
    for record in _clip_set_records(job):
        if record.get("id") == set_id:
            return record
    raise HTTPException(404, "Clip set not found.")


def _find_clip_set(job_id: str, set_id: str) -> tuple[dict, dict]:
    job = load_job(job_id)
    return job, _clip_set_in_job(job, set_id)


def _store_clip_set(job_id: str, record: dict) -> dict:
    def mutate(job: dict) -> None:
        current = job.get("clip_sets")
        if isinstance(current, list):
            job["clip_sets"] = [
                item for item in current
                if not (isinstance(item, dict) and item.get("id") == record["id"])
            ]
            job["clip_sets"].append(record)
        else:
            job["clip_sets"] = dict(current or {})
            job["clip_sets"][record["id"]] = record

    return update_job(job_id, mutate)


def _new_clip_set(job: dict, body: ClipSetCreateBody) -> dict:
    sentences, scenes, transcript = _clipset_sentences(job)
    try:
        document = clipset.build_clipset(
            scenes,
            transcript,
            float((job.get("source") or {}).get("duration") or 0.0),
            count=body.count,
            min_s=body.min_s,
            max_s=body.max_s,
            locks=body.locks,
            ban_scenes=body.ban_scenes,
            order=body.order,
        )
    except clipset.ClipSetError as exc:
        raise HTTPException(400, str(exc)) from exc
    now = round(time.time(), 3)
    document.update({
        "id": "cs_" + uuid.uuid4().hex[:12],
        "job_id": job["id"],
        "created": now,
        "updated": now,
    })
    return document


def _clip_set_context(
    job: dict,
    count: int = 3,
) -> tuple[list[dict], list[dict], list[dict] | None, dict]:
    sentences, scenes, transcript = _clipset_sentences(job)
    document = clipset.build_clipset(
        scenes,
        transcript,
        float((job.get("source") or {}).get("duration") or 0.0),
        count=count,
    )
    return sentences, scenes, transcript, document


def _patch_bans(body: ClipSetPatchBody) -> list[int] | None:
    if body.ban_scenes is None and body.bans is None:
        return None
    values = list(body.ban_scenes or []) + list(body.bans or [])
    return sorted({int(value) for value in values})


@app.post("/api/jobs/{job_id}/clip-sets")
def create_clip_set(job_id: str, body: ClipSetCreateBody) -> dict:
    job = _clipset_job(job_id)
    record = _new_clip_set(job, body)
    _store_clip_set(job_id, record)
    return {"clip_set": record}


@app.get("/api/jobs/{job_id}/clip-sets")
def list_clip_sets(job_id: str) -> dict:
    job = load_job(job_id)
    records = _clip_set_records(job)
    records.sort(key=lambda record: (
        -float(record.get("created") or 0.0),
        str(record.get("id") or ""),
    ))
    return {"clip_sets": records, "count": len(records)}


@app.patch("/api/jobs/{job_id}/clip-sets/{set_id}")
def patch_clip_set(job_id: str, set_id: str, body: ClipSetPatchBody) -> dict:
    job, record = _find_clip_set(job_id, set_id)
    if job.get("status") != "ready" or not job.get("analysis"):
        raise HTTPException(409, "Analysis is not ready yet.")
    _clip_set_source_state(job, record, require_fingerprint=True)
    sentences, scenes, _ = _clipset_pool(job, record)

    def _revision(story: dict | None) -> int:
        try:
            return max(0, int((story or {}).get("revision") or 0))
        except (TypeError, ValueError, AttributeError):
            return 0

    def _range(story: dict | None) -> tuple:
        story = story or {}
        ids = []
        for sentence in story.get("sentences") or []:
            try:
                ids.append(int(sentence.get("id")))
            except (TypeError, ValueError):
                continue
        return (
            round(float(story.get("start") or 0.0), 3),
            round(float(story.get("end") or 0.0), 3),
            round(float(story.get("dur") or 0.0), 3),
            tuple(ids),
        )

    old_by_id = {
        str(story.get("id")): story
        for story in record.get("stories") or []
        if isinstance(story, dict) and story.get("id") is not None
    }
    expected = body.expected_revision
    targets = [
        str(patch.get("id"))
        for patch in body.stories or []
        if isinstance(patch, dict) and patch.get("id") is not None
    ]
    if expected is not None:
        if not targets:
            raise HTTPException(
                422,
                detail={
                    "code": "range_invalid",
                    "message": "expected_revision needs a story patch.",
                },
            )
        for story_id in targets:
            prior = old_by_id.get(story_id)
            if prior is None or _revision(prior) != int(expected):
                raise HTTPException(
                    409,
                    detail={
                        "code": "revision_mismatch",
                        "message": (
                            "This story changed in another window. "
                            "Reload and try again."
                        ),
                        "current": {
                            "revision": _revision(prior) if prior else None,
                        },
                    },
                )
    try:
        updated = clipset.apply_edits(
            record,
            sentences,
            scenes,
            float((job.get("source") or {}).get("duration") or 0.0),
            excluded_sentences=body.excluded_sentences,
            locks=body.locks,
            ban_scenes=_patch_bans(body),
            story_patches=body.stories,
            order=body.order,
        )
    except clipset.ClipSetError as exc:
        raise HTTPException(400, str(exc)) from exc
    updated["id"] = record["id"]
    updated["job_id"] = job["id"]
    updated["created"] = record.get("created")
    updated["updated"] = round(time.time(), 3)
    for story in updated.get("stories") or []:
        if not isinstance(story, dict):
            continue
        prior = old_by_id.get(str(story.get("id")))
        revision = _revision(prior)
        if prior is None:
            revision = 0
        elif _range(prior) != _range(story):
            revision += 1
        story["revision"] = revision

    class _RevisionMismatch(Exception):
        pass

    def mutate(current_job: dict) -> None:
        current_record = _clip_set_in_job(current_job, set_id)
        current_by_id = {
            str(story.get("id")): story
            for story in current_record.get("stories") or []
            if isinstance(story, dict) and story.get("id") is not None
        }
        if expected is not None:
            for story_id in targets:
                if _revision(current_by_id.get(story_id)) != int(expected):
                    raise _RevisionMismatch()
        current_sets = current_job.get("clip_sets")
        if isinstance(current_sets, list):
            current_job["clip_sets"] = [
                item for item in current_sets
                if not (isinstance(item, dict) and item.get("id") == updated["id"])
            ]
            current_job["clip_sets"].append(updated)
        else:
            current_job["clip_sets"] = dict(current_sets or {})
            current_job["clip_sets"][updated["id"]] = updated

    try:
        update_job(job["id"], mutate)
    except _RevisionMismatch as exc:
        raise HTTPException(
            409,
            detail={
                "code": "revision_mismatch",
                "message": (
                    "This story changed in another window. Reload and try again."
                ),
            },
        ) from exc
    return {"clip_set": updated}


@app.post("/api/jobs/{job_id}/clip-sets/{set_id}/plans")
def clip_set_plans(
    job_id: str,
    set_id: str,
    body: ClipSetPlansBody | None = None,
) -> dict:
    job, record = _find_clip_set(job_id, set_id)
    if job.get("status") != "ready" or not job.get("analysis"):
        raise HTTPException(409, "Analysis is not ready yet.")
    _, stale_warning = _clip_set_source_state(job, record)
    scenes = list((job.get("analysis") or {}).get("scenes") or [])
    target = None
    if body is not None and body.target is not None:
        target = int(body.target)
        if target < 1 or target > 180:
            raise HTTPException(400, "target must be between 1 and 180 seconds.")
    plans = []
    for story in record.get("stories") or []:
        try:
            plan = clipset.story_to_plan(
                story, scenes, target=target, set_id=set_id,
            )
        except clipset.ClipSetError as exc:
            raise HTTPException(422, str(exc)) from exc
        plans.append({
            "story_id": story.get("id"),
            "title": story.get("title"),
            "plan": plan,
        })
    return {
        "plans": plans,
        "count": len(plans),
        "set_id": set_id,
        "stale_check": "unverified" if stale_warning else "verified",
        "warnings": [stale_warning] if stale_warning else [],
    }


@app.post("/api/jobs/{job_id}/clip-sets/{set_id}/stories/{story_id}/render")
def render_clip_set_story(
    job_id: str,
    set_id: str,
    story_id: str,
    body: StoryRenderBody | None = None,
) -> dict:
    """Queue one clip-set story through the shared artifact render path.

    Duration is the stored story duration. When the story has a current Edit
    for the requested aspect, render_reel compiles that Edit: clean, motion,
    colour, text, graphics and captions. Without an Edit the legacy plan path
    runs unchanged and captions default on.
    """
    return _queue_story_render(
        job_id, set_id, story_id, body or StoryRenderBody(), reject_active=True,
    )


EDIT_STALE_MESSAGE = (
    "This story changed after its Edit was made. "
    "Open it in Edit and press Repair."
)


def _edit_stale_error() -> HTTPException:
    return HTTPException(
        409,
        detail={"code": "edit_stale", "message": EDIT_STALE_MESSAGE},
    )


def _caption_track_for_cut(
    job: dict,
    job_dir: Path,
    track: caption_engine.CaptionTrack,
    raw_clips: list[dict] | None,
    track_plan: dict,
) -> caption_engine.CaptionTrack:
    """Carry a story's own track onto the frame-rounded render cut.

    ``prepare_render`` can move clip ends by under a frame, which changes the
    clip hash. Re-reading the transcript here would drop hand-fixed caption
    text, so the track's own cues are retimed through the clips instead. Only
    when that fails does the track get rebuilt from the transcript.
    """
    import trim

    prepared = track_plan.get("clips") or []
    total = float(track_plan.get("total") or 0.0)
    raw = list(raw_clips or [])
    # Only frame rounding is carried over. A beat-synced or re-timed cut moves
    # clip lengths by more than a frame; it gets a track built for that cut.
    rounding_only = len(raw) == len(prepared) and all(
        abs(float(old.get("duration") or 0.0) - float(new.get("duration") or 0.0)) < 0.05
        for old, new in zip(raw, prepared)
    )
    if not rounding_only:
        return caption_engine.build_track(
            job, track_plan, track.style, job_dir=job_dir,
        )
    try:
        cues = []
        for cue in track.cues:
            start = max(0.0, trim.map_time(float(cue.start), raw_clips, prepared))
            end = min(total, trim.map_time(float(cue.end), raw_clips, prepared))
            if end - start <= 1e-3:
                continue
            cues.append(replace(cue, start=round(start, 3), end=round(end, 3)))
        if not cues and track.cues:
            raise ValueError("no cue survived the retime")
        clip_key = caption_engine.clip_hash(prepared)
        cue_key = caption_engine.cue_hash(cues)
        retimed = replace(
            track,
            id=caption_engine.track_id(
                job_id=track.job_id,
                target=track.target,
                clip_key=clip_key,
                cue_key=cue_key,
                style_key=f"{track.style_hash}:{track.style_id}",
                version=track.version,
            ),
            cues=cues,
            cue_hash=cue_key,
            clip_hash=clip_key,
            parent_id=track.id,
        )
        caption_engine.save_track(job_dir, retimed)
        return retimed
    except (TypeError, ValueError, KeyError, OSError) as exc:
        LOGGER.warning("caption track %s could not be retimed (%s); rebuilding", track.id, exc)
        return caption_engine.build_track(
            job, track_plan, track.style, job_dir=job_dir,
        )


def _story_edit_for_render(
    job: dict,
    story: dict,
    set_id: str,
    aspect: str,
) -> dict | None:
    """Return the story's current Edit for one aspect, or None.

    A pointer is a promise: when it exists, the Edit must still describe this
    story. A stale or unreadable Edit raises 409 instead of falling back to
    the plan path, because that fallback would render a different film. The
    legacy plan path runs only when no pointer exists at all.
    """
    key = edits.story_key(set_id, str(story.get("id") or ""), aspect)
    edit_id = edits.pointer_edit_id(job, key)
    if not edit_id:
        return None
    try:
        edit = edits.load_edit(_job_dir(job["id"]), edit_id)
    except edits.EditError:
        LOGGER.warning("story %s has an unreadable Edit %s", key, edit_id)
        raise _edit_stale_error() from None
    if edit is None or edit.get("aspect") != aspect:
        LOGGER.warning("story %s has a missing or mismatched Edit %s", key, edit_id)
        raise _edit_stale_error()
    if not edit.get("sequence") and edits.clip_snapshot_hash(
        story.get("clips") or []
    ) != (edit.get("story_ref") or {}).get("clip_hash"):
        LOGGER.warning("story %s changed since Edit %s", key, edit_id)
        raise _edit_stale_error()
    return edit


def _story_clip_hashes(job_id: str, edit: dict) -> set[str]:
    """Hashes that describe the story this Edit belongs to.

    The Edit records the story's clip hash. A track built for the render cut
    carries the same hash with clips frame-rounded by ``prepare_render``, so
    both forms count as current. Any other hash is an old cut.
    """
    reference = edit.get("story_ref") or {}
    hashes = {str(reference.get("clip_hash") or "")}
    try:
        job = load_job(job_id)
        set_id = str(reference.get("set_id") or "")
        story_id = str(reference.get("story_id") or "")
        record = _clip_set_in_job(job, set_id)
        story = _story_in_set(record, story_id)
        hashes.add(edits.clip_snapshot_hash(story.get("clips") or []))
        plan = _story_track_plan(job, _story_plan(job, record, story, set_id))
        hashes.add(caption_engine.clip_hash(plan.get("clips")))
    except (HTTPException, clipset.ClipSetError, OSError, ValueError, KeyError):
        pass
    hashes.discard("")
    return hashes


def _edit_caption_track(
    job_id: str,
    edit: dict,
) -> tuple[bool, caption_engine.CaptionTrack | None]:
    """Resolve the Edit's caption track; a deleted track renders no captions."""
    captions = edit.get("captions") or {}
    track_id = captions.get("track_id")
    if not captions.get("enabled", True) or not track_id:
        return False, None
    try:
        track = _caption_track_by_id(job_id, str(track_id))
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        LOGGER.warning("Edit %s references missing caption track %s", edit["id"], track_id)
        return False, None
    if track.clip_hash and track.clip_hash not in _story_clip_hashes(job_id, edit):
        raise HTTPException(
            409,
            "The caption track does not match this story. Rebuild the track.",
        )
    return True, track


def _scripted(job: dict) -> bool:
    """True when the job's speech is a written script, not a recording."""
    engine = ((job.get("analysis") or {}).get("engine") or {}).get("transcript_provider")
    return engine == silent_script.ENGINE


def _queue_story_render(
    job_id: str,
    set_id: str,
    story_id: str,
    body: StoryRenderBody,
    *,
    reject_active: bool,
) -> dict:
    job = _clipset_job(job_id)
    record = _clip_set_in_job(job, set_id)
    _clip_set_source_state(job, record)
    story = _story_in_set(record, story_id)
    if body.quality not in ("final", "720", "draft"):
        raise HTTPException(400, "Quality must be final, 720 or draft.")
    if body.aspect not in STORY_ASPECTS:
        raise HTTPException(400, "Story renders support 9:16, 4:5, 1:1, 16:9 and 16:10.")
    plan = _story_plan(job, record, story, set_id)
    if body.target is not None and int(body.target) != int(plan["target"]):
        raise HTTPException(
            400,
            f"Story renders use the stored story duration ({plan['target']}s); omit target.",
        )
    edit = _story_edit_for_render(job, story, set_id, body.aspect)
    if edit is not None and edit.get("sequence"):
        sequence = [
            {
                **clip,
                "dur": round(max(0.0, float(clip.get("end") or 0) - float(clip.get("start") or 0)), 3),
            }
            for clip in edit["sequence"]
        ]
        plan = {
            **plan,
            "clips": sequence,
            "total": round(sum(clip["dur"] for clip in sequence), 3),
            "clip_count": len(sequence),
            "hook_scene": sequence[0]["scene"] if sequence else plan.get("hook_scene"),
        }
    caption_track = None
    captions_on = False
    edit_audio_plan = None
    keep_chosen = False
    if edit is not None and body.captions:
        edit = _edit_with_default_captions(job_id, job, story, set_id, edit)
    if edit is not None:
        captions_on, caption_track = _edit_caption_track(job_id, edit)
        # The Edit's audio layer (bed, voice-over, dub) is mixed like any
        # AudioPlan. "original" stays None so captions-only Edits keep the
        # legacy audio signature.
        edit_audio_plan = audio.plan_from_edit(edit.get("audio"))
        if edit_audio_plan and audio.mixer_mode(edit_audio_plan.get("mode")) == "keep":
            # Every Edit stores mode "original" by default; only a mode the
            # creator picked in the panel opts a scripted story out of its voice.
            keep_chosen = bool((edit.get("audio") or {}).get("mode_chosen"))
            edit_audio_plan = None
    if edit_audio_plan is None and not keep_chosen and _scripted(job):
        # A written script has no recorded voice: speak it over the picture.
        edit_audio_plan = audio.normalize_audio_plan({
            "mode": "voice_over",
            "voice": {"engine": "auto", "voice": "", "rate": 1.0},
        })
    if edit is None and body.captions:
        track_id = body.caption_track_id or str(
            (job.get("story_captions") or {}).get(_story_key(set_id, story_id)) or ""
        )
        if track_id:
            caption_track = _caption_track_by_id(job_id, track_id)
        captions_on = True
    public_plan = {
        key: value for key, value in plan.items() if not key.startswith("_")
    }
    queued = _queue_render(
        job_id,
        job,
        plan,
        body.quality,
        body.aspect,
        None,
        captions_on,
        edit_audio_plan,
        False,
        check_space=True,
        caption_track=caption_track,
        reject_active=reject_active,
        edit=edit,
    )
    return {
        "plan": public_plan,
        "render": _public_render(job_id, queued),
        "artifact_id": queued.get("artifact_id"),
        "caption_track_id": caption_track.id if caption_track is not None else None,
        "edit_id": edit["id"] if edit is not None else None,
        "edit_hash": edit["hash"] if edit is not None else None,
    }


class StoryRenderBackend:
    """Story queue items render through the same path as a single story."""

    def start(self, item: dict) -> str:
        result = _queue_story_render(
            item["job_id"], item["set_id"], item["story_id"],
            StoryRenderBody(aspect=item["aspect"], quality=item["quality"]),
            reject_active=False,
        )
        artifact = str(result.get("artifact_id") or "")
        if not artifacts.is_safe_artifact_id(artifact):
            raise HTTPException(500, "The story render returned no artifact.")
        return artifact

    def status(self, item: dict, artifact_id: str) -> str:
        job_dir = _job_dir(item["job_id"])
        manifest = artifacts.load_manifest(job_dir, artifact_id)
        if manifest is None:
            return "failed"
        status = str(manifest.get("status") or "")
        if status == "ready" and not artifacts.has_media(job_dir, artifact_id):
            return "failed"
        return status

    def cancel(self, item: dict, artifact_id: str) -> None:
        job = load_job(item["job_id"])
        for key, record in (job.get("renders") or {}).items():
            if record.get("artifact_id") == artifact_id and record.get("status") in ACTIVE_RENDER:
                RENDER_CANCELS.setdefault((item["job_id"], key), threading.Event()).set()
                _set_render(
                    item["job_id"], key,
                    status="cancelling", message="Stopping…", error=None,
                )

    def error(self, item: dict, artifact_id: str) -> str:
        """The artifact's own failure reason, never a generic "Render failed"."""
        try:
            manifest = artifacts.load_manifest(_job_dir(item["job_id"]), artifact_id)
        except (HTTPException, OSError):
            return ""
        if not isinstance(manifest, dict):
            return ""
        for key in ("error", "message"):
            text = str(manifest.get(key) or "").strip()
            if text and not re.fullmatch(r"render failed\.?", text, re.IGNORECASE):
                return text[:1200]
        return ""

    def timeout_for(self, item: dict) -> float:
        try:
            fixed = float(os.environ.get("VIBECUT_STORY_TIMEOUT", "0") or 0)
        except ValueError:
            fixed = 0.0
        if fixed > 0:
            return fixed
        return 1800.0


_STORY_QUEUES: dict[str, story_queue.StoryQueueManager] = {}
# One create/attach decision at a time, so two quick Queue-all clicks cannot
# both see an empty active set and each start a queue for the same identity.
_STORY_QUEUE_SUBMIT_LOCK = threading.Lock()
# Per-queue ETA memory: a running item's estimate never rises inside one
# stage, and a queue header never rises while the same items are in flight.
_QUEUE_ETA_STATE: dict[str, dict] = {}


def _story_queue_identity(item: dict) -> tuple[str, str, str, str, str]:
    return (
        str(item.get("job_id") or ""),
        str(item.get("set_id") or ""),
        str(item.get("story_id") or ""),
        str(item.get("aspect") or "9:16"),
        str(item.get("quality") or "final"),
    )


def _active_queue_for(
    queues: list[dict],
    identity: tuple[str, str, str, str, str],
) -> dict | None:
    for queue in queues:
        if str(queue.get("status") or "") not in story_queue.ACTIVE_QUEUES:
            continue
        for item in queue.get("items") or []:
            if str(item.get("state") or "") not in {"queued", "running"}:
                continue
            if _story_queue_identity(item) == identity:
                return queue
    return None


def story_queues() -> story_queue.StoryQueueManager:
    key = str(DATA)
    manager = _STORY_QUEUES.get(key)
    if manager is None:
        manager = story_queue.StoryQueueManager(DATA, StoryRenderBackend())
        _STORY_QUEUES[key] = manager
    return manager


def _queue_http(exc: story_queue.QueueError) -> HTTPException:
    return HTTPException(exc.status_code, str(exc))


class StoryQueueBody(BaseModel):
    items: list[dict] = Field(default_factory=list)


@app.post("/api/story-queues")
def create_story_queue(body: StoryQueueBody) -> dict:
    """Up to ten story items render one after another; nothing auto-resumes.

    Queueing is idempotent by identity: a story/shape/quality already waiting
    or rendering is attached to its active queue instead of creating a second
    item or a failed "already rendering" row.
    """
    for item in body.items:
        if isinstance(item, dict) and item.get("job_id"):
            job = _clipset_job(str(item["job_id"]))
            set_id = str(item.get("set_id") or "")
            record = _clip_set_in_job(job, set_id)
            story = _story_in_set(record, str(item.get("story_id") or ""))
            # A stale Edit fails the queue request closed, before any item
            # starts; the worker would only report it after the 200.
            _story_edit_for_render(
                job, story, set_id, str(item.get("aspect") or "9:16"),
            )
    with _STORY_QUEUE_SUBMIT_LOCK:
        manager = story_queues()
        active = manager.list()
        pending: list[dict] = []
        attached: dict | None = None
        for item in body.items:
            queue = _active_queue_for(active, _story_queue_identity(item))
            if queue is not None:
                attached = attached or queue
            else:
                pending.append(item)
        if not pending and attached is not None:
            return {
                "queue": _live_queue(manager.get(str(attached["id"]))),
                "attached": True,
            }
        try:
            queue = manager.create(pending or body.items)
        except story_queue.QueueError as exc:
            raise _queue_http(exc) from exc
        return {"queue": _live_queue(queue), "attached": False}


def _smooth_item_eta(
    state: dict | None,
    item: dict,
    stage: str,
    raw: object,
) -> float | None:
    """Hide unknown and zero estimates; never rise inside one stage."""
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    if state is None:
        return round(value, 1)
    key = str(item.get("id") or item.get("artifact_id") or "")
    previous = state["items"].get(key)
    if isinstance(previous, dict) and previous.get("stage") == stage:
        value = min(value, float(previous.get("eta") or value))
    state["items"][key] = {"stage": stage, "eta": value}
    return round(value, 1)


def _live_queue(queue: dict) -> dict:
    """Add each running item's render progress, message and ETA.

    Queue progress used to count only finished items, so one long render sat
    at 50% with no sign of life. Running items now carry the render record's
    own progress and ETA, and the queue's progress and ETA include them.

    An ETA appears only after the renderer has a measured rate. It is never
    shown as 0.0 while running and never rises inside one render stage. The
    queue header and its running item are fed from the same estimate.
    """
    jobs: dict[str, dict] = {}
    items = queue.get("items") or []
    queue_id = str(queue.get("id") or "")
    state = None
    if queue_id and str(queue.get("status") or "") in story_queue.ACTIVE_QUEUES:
        state = _QUEUE_ETA_STATE.setdefault(queue_id, {"items": {}, "queue": None})
    elif queue_id:
        _QUEUE_ETA_STATE.pop(queue_id, None)
    partial = 0.0
    eta_total = 0.0
    eta_known = False
    running_ids: list[str] = []
    for item in items:
        if item.get("state") != "running" or not item.get("artifact_id"):
            continue
        job_id = str(item.get("job_id") or "")
        try:
            job = jobs.get(job_id) or load_job(job_id)
        except HTTPException:
            continue
        jobs[job_id] = job
        record = next(
            (
                value for value in (job.get("renders") or {}).values()
                if isinstance(value, dict) and value.get("artifact_id") == item["artifact_id"]
            ),
            None,
        )
        if record is None:
            continue
        fraction = max(0.0, min(1.0, float(record.get("progress") or 0.0)))
        item["progress"] = round(fraction, 4)
        item["message"] = record.get("message") or item.get("message")
        stage = str(record.get("message") or "Rendering")
        eta = _smooth_item_eta(state, item, stage, record.get("eta"))
        if eta is None:
            item.pop("eta", None)
        else:
            item["eta"] = eta
            eta_total += eta
            eta_known = True
        running_ids.append(str(item.get("id") or item["artifact_id"]))
        partial += fraction
    if items:
        done = sum(1 for item in items if item.get("state") in story_queue.TERMINAL_ITEMS)
        queue["progress"] = round((done + partial) / len(items), 4)
    waiting = sum(1 for item in items if item.get("state") == "queued")
    queue.pop("eta", None)
    if eta_known:
        # Items still waiting are estimated at the running item's full length.
        running = [item for item in items if item.get("eta") is not None and item.get("state") == "running"]
        per_item = 0.0
        if running:
            item = running[0]
            spent = float(item.get("progress") or 0.0)
            per_item = float(item["eta"]) / max(0.05, 1.0 - spent) if spent < 1 else 0.0
        total = round(eta_total + waiting * per_item, 1)
        if total > 0:
            if state is not None:
                signature = (
                    f"{queue.get('status')}:{len(items)}:"
                    f"{','.join(running_ids)}"
                )
                previous = state.get("queue")
                if isinstance(previous, dict) and previous.get("signature") == signature:
                    total = min(total, float(previous.get("eta") or total))
                state["queue"] = {"signature": signature, "eta": total}
            queue["eta"] = total
    return queue


@app.get("/api/story-queues")
def list_story_queues() -> dict:
    manager = story_queues()
    rows = [_live_queue(row) for row in manager.list()]
    return {
        "queues": rows,
        "interrupted": [row for row in rows if row["needs_resume"]],
    }


@app.get("/api/story-queues/{queue_id}")
def get_story_queue(queue_id: str) -> dict:
    try:
        return {"queue": _live_queue(story_queues().get(queue_id))}
    except story_queue.QueueError as exc:
        raise _queue_http(exc) from exc


@app.post("/api/story-queues/{queue_id}/{action}")
def act_on_story_queue(queue_id: str, action: str) -> dict:
    manager = story_queues()
    handlers = {"pause": manager.pause, "cancel": manager.cancel, "resume": manager.resume}
    handler = handlers.get(action)
    if handler is None:
        raise HTTPException(404, "Unknown queue action.")
    try:
        return {"queue": handler(queue_id)}
    except story_queue.QueueError as exc:
        raise _queue_http(exc) from exc


@app.post("/api/jobs/{job_id}/selection-v2")
def selection_v2(job_id: str, body: SelectionV2Body) -> dict:
    job = _clipset_job(job_id)
    if body.count is not None and (body.count < clipset.MIN_STORIES or body.count > clipset.MAX_STORIES):
        raise HTTPException(400, clipset.COUNT_MESSAGE)
    scenes = list((job.get("analysis") or {}).get("scenes") or [])
    stale_warning = None
    if body.set_id:
        record = _clip_set_in_job(job, body.set_id)
        _, stale_warning = _clip_set_source_state(job, record)
        stories = record.get("stories") or []
        source = "clip_set"
    else:
        # Ranking defaults to six candidates; MAX_STORIES grew to 12 for Stories.
        _, scenes, _, document = _clip_set_context(job, count=body.count or 6)
        stories = document.get("stories") or []
        source = "generated"
    result = selection.rank_stories(
        stories,
        prompt=body.prompt,
        exclusions=body.exclusions,
        scenes=scenes,
        source_duration=float((job.get("source") or {}).get("duration") or 0.0),
        limit=body.count,
    )
    result["job_id"] = job_id
    result["set_id"] = body.set_id
    result["source"] = source
    result["stale_check"] = (
        "not_applicable" if body.set_id is None
        else ("unverified" if stale_warning else "verified")
    )
    result["warnings"] = [stale_warning] if stale_warning else []
    return result


def _experimental_enabled() -> bool:
    return os.environ.get("VIBECUT_EXPERIMENTAL", "0").lower() not in (
        "0", "false", "no", "off", "",
    )


@app.post("/api/jobs/{job_id}/hook-matrix")
def hook_matrix(job_id: str, body: HookMatrixBody) -> dict:
    # The hook/cover matrix is post-v1 scope; it stays reachable only for
    # development with VIBECUT_EXPERIMENTAL=1.
    if not _experimental_enabled():
        raise HTTPException(404, "The hook matrix is not part of this release.")
    job = _clipset_job(job_id)
    if body.count < clipset.MIN_STORIES or body.count > clipset.MAX_STORIES:
        raise HTTPException(400, clipset.COUNT_MESSAGE)
    scenes = list((job.get("analysis") or {}).get("scenes") or [])
    stale_warning = None
    if body.set_id:
        record = _clip_set_in_job(job, body.set_id)
        _, stale_warning = _clip_set_source_state(job, record)
        stories = list(record.get("stories") or [])
        source = "clip_set"
    else:
        _, scenes, _, document = _clip_set_context(job, count=body.count)
        stories = list(document.get("stories") or [])
        source = "generated"
    if body.story_id:
        stories = [story for story in stories if story.get("id") == body.story_id]
        if not stories:
            raise HTTPException(404, "Story not found in this clip set.")
    if body.prompt or body.exclusions:
        ranked = selection.rank_stories(
            stories,
            prompt=body.prompt,
            exclusions=body.exclusions,
            scenes=scenes,
            source_duration=float((job.get("source") or {}).get("duration") or 0.0),
        )
        stories = ranked["ranked"]
    result = matrix.build_matrix_for_stories(stories, scenes)
    result["job_id"] = job_id
    result["set_id"] = body.set_id
    result["source"] = source
    result["queued"] = 0
    result["stale_check"] = (
        "not_applicable" if body.set_id is None
        else ("unverified" if stale_warning else "verified")
    )
    if stale_warning:
        result.setdefault("warnings", []).append(stale_warning)
    else:
        result.setdefault("warnings", [])
    return result


class VoiceBody(BaseModel):
    engine: str = "say"
    voice: str = ""
    rate: float = 1.0
    text: str | None = None


class TranslateInstallBody(BaseModel):
    source: str | None = None
    target: str | None = None


class ScriptBody(BaseModel):
    target: int = 30
    hook_scene: int | None = None
    clips: list[dict] | None = None
    translate: str | None = None
    provider: str = "auto"
    mode: str = "literal"
    rewrite_provider: str = "auto"
    force_translate: bool = False
    order: str = "source"
    overrides: dict | None = None


class CleanBody(BaseModel):
    profile: str = "workfiles"


@app.get("/api/audio/engines")
def audio_engines() -> dict:
    return audio.engine_status()


@app.get("/api/audio/voices")
def audio_voices(engine: str = "say") -> dict:
    try:
        return {"engine": engine, "voices": audio.list_voices(engine)}
    except audio.AudioError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/audio/music")
def audio_music(source: str = "library") -> dict:
    return {"source": source, "tracks": audio.list_music(source)}


@app.get("/api/audio/translate/status")
def translate_status(source: str = "", target: str = "") -> dict:
    return {
        "providers": audio.translate_providers(),
        "check": None,
    }


@app.post("/api/audio/translate/install")
def translate_install(body: TranslateInstallBody | None = None) -> dict:
    return {
        "ok": False,
        "detail": "Local fallback is Apple Translation. Install the language pack in System Settings.",
    }


@app.get("/api/jobs/{job_id}/audio/moods")
def job_moods(job_id: str, target: int = 30, hook_scene: int | None = None) -> dict:
    job = load_job(job_id)
    plan_target = _valid_target(int(target))
    plan = _plan_for(job, plan_target, hook_scene)
    scenes = job["analysis"]["scenes"]
    moods = audio.scene_moods(scenes, plan["clips"])
    return {
        "moods": moods,
        "prompt": audio.music_prompt(moods, plan["total"]),
    }


@app.post("/api/jobs/{job_id}/audio/voice-upload")
async def upload_voice_audio(job_id: str, file: UploadFile = File(...)) -> dict:
    load_job(job_id)
    started = time.time()
    original_name = Path(file.filename or "voice.wav").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".aiff", ".aif", ".webm"}:
        error = "Upload a WAV, MP3, M4A, FLAC, OGG, WebM or AIFF file."
        _record_upload_history(
            job_id, "voice", "failed", original_name, error=error,
            latency_ms=round((time.time() - started) * 1000),
        )
        raise HTTPException(400, error)
    directory = _job_dir(job_id) / "audio"
    directory.mkdir(parents=True, exist_ok=True)
    temp = directory / f"upload-source{suffix}"
    stored: Path | None = None
    try:
        with temp.open("wb") as handle:
            shutil.copyfileobj(file.file, handle)
        stored = audio.store_uploaded_voice(temp, _job_dir(job_id))
        digest = hashlib.sha1(stored.read_bytes()).hexdigest()[:12]
        versioned = stored.with_name(f"uploaded_voice_{digest}.wav")
        stored.replace(versioned)
        stored = versioned
        duration = audio.media_duration(stored)
        if duration <= 0.2:
            raise HTTPException(400, "The uploaded audio is empty or unreadable.")
    except HTTPException as exc:
        _record_upload_history(
            job_id, "voice", "failed", original_name,
            error=str(exc.detail)[:2400],
            latency_ms=round((time.time() - started) * 1000),
        )
        raise
    except audio.AudioError as exc:
        _record_upload_history(
            job_id, "voice", "failed", original_name,
            error=str(exc)[:2400],
            latency_ms=round((time.time() - started) * 1000),
        )
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        _record_upload_history(
            job_id, "voice", "failed", original_name,
            error=str(exc)[:2400],
            latency_ms=round((time.time() - started) * 1000),
        )
        raise
    finally:
        try:
            temp.unlink()
        except OSError:
            pass
    path = str(stored.relative_to(_job_dir(job_id)))
    size = stored.stat().st_size if stored else None
    _record_upload_history(
        job_id, "voice", "ok", original_name,
        path=path, duration=duration, size=size,
        latency_ms=round((time.time() - started) * 1000),
    )
    return {
        "path": path,
        "duration": round(duration, 3),
        "name": file.filename or stored.name,
    }


@app.post("/api/jobs/{job_id}/audio/music-upload")
async def upload_music_audio(job_id: str, file: UploadFile = File(...)) -> dict:
    load_job(job_id)
    started = time.time()
    original_name = Path(file.filename or "music.wav").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".aiff", ".aif", ".webm"}:
        error = "Upload a WAV, MP3, M4A, FLAC, OGG, WebM or AIFF file."
        _record_upload_history(
            job_id, "music", "failed", original_name, error=error,
            latency_ms=round((time.time() - started) * 1000),
        )
        raise HTTPException(400, error)
    directory = _job_dir(job_id) / "audio"
    directory.mkdir(parents=True, exist_ok=True)
    temp = directory / f"music-source{suffix}"
    stored: Path | None = None
    try:
        with temp.open("wb") as handle:
            shutil.copyfileobj(file.file, handle)
        stored = audio.store_uploaded_music(temp, _job_dir(job_id))
        digest = hashlib.sha1(stored.read_bytes()).hexdigest()[:12]
        versioned = stored.with_name(f"uploaded_music_{digest}.wav")
        stored.replace(versioned)
        stored = versioned
        duration = audio.media_duration(stored)
        if duration <= 0.2:
            raise HTTPException(400, "The uploaded music is empty or unreadable.")
    except HTTPException as exc:
        _record_upload_history(
            job_id, "music", "failed", original_name,
            error=str(exc.detail)[:2400],
            latency_ms=round((time.time() - started) * 1000),
        )
        raise
    except audio.AudioError as exc:
        _record_upload_history(
            job_id, "music", "failed", original_name,
            error=str(exc)[:2400],
            latency_ms=round((time.time() - started) * 1000),
        )
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        _record_upload_history(
            job_id, "music", "failed", original_name,
            error=str(exc)[:2400],
            latency_ms=round((time.time() - started) * 1000),
        )
        raise
    finally:
        try:
            temp.unlink()
        except OSError:
            pass
    path = str(stored.relative_to(_job_dir(job_id)))
    size = stored.stat().st_size if stored else None
    _record_upload_history(
        job_id, "music", "ok", original_name,
        path=path, duration=duration, size=size,
        latency_ms=round((time.time() - started) * 1000),
    )
    return {
        "path": path,
        "duration": round(duration, 3),
        "name": file.filename or stored.name,
    }


@app.post("/api/jobs/{job_id}/voice/sample")
def voice_sample(job_id: str, body: VoiceBody) -> FileResponse:
    load_job(job_id)
    text = (body.text or "").strip() or "This is a VibeCut voice test."
    cache = DATA / "cache" / "voice"
    cache.mkdir(parents=True, exist_ok=True)
    try:
        path = audio.voice_sample(body.engine, body.voice, text, cache, rate=body.rate)
    except audio.AudioError as exc:
        raise HTTPException(400, str(exc)) from exc
    return FileResponse(path, media_type="audio/wav", filename="voice-sample.wav")


@app.get("/api/audio/beats")
def audio_beats(source: str = "library", track: str = "", job_id: str = "") -> dict:
    """BPM and beat times for a library track or a job-relative upload."""
    path = None
    if job_id and track and not Path(track).is_absolute():
        job_root = _job_dir(job_id).resolve()
        candidate = (job_root / track).resolve()
        if candidate.is_relative_to(job_root) and candidate.is_file():
            path = candidate
    else:
        path = audio.resolve_music_track([], [], {"source": source, "track": track})
    if not path:
        raise HTTPException(404, "No track found for beat detection.")
    grid = audio.beat_grid(path)
    if not grid:
        raise HTTPException(400, "Beat detection unavailable (librosa missing or unreadable audio).")
    return {
        "track": path.name,
        "bpm": grid["bpm"],
        "beats": len(grid["beats"]),
        "times": grid["beats"],
    }


@app.get("/api/audio/licenses")
def audio_licenses() -> dict:
    rows = []
    for source in audio.MUSIC_DIRS:
        for track in audio.list_music(source):
            rows.append({
                "source": source,
                "name": track["name"],
                "id": track["id"],
                "license": track.get("license"),
            })
    return {
        "tracks": rows,
        "strict": os.environ.get("VIBECUT_AUDIO_LICENSE", "").lower() == "strict",
    }


@app.get("/api/sources")
def source_store() -> dict:
    rows = []
    if SOURCES.is_dir():
        for directory in sorted(SOURCES.iterdir()):
            if not directory.is_dir():
                continue
            files = [
                item for item in directory.iterdir()
                if item.is_file() and item.name.startswith("source")
            ]
            if not files:
                continue
            stored = files[0]
            meta = {}
            meta_path = directory / "meta.json"
            if meta_path.is_file():
                try:
                    meta = json.loads(meta_path.read_text())
                except (OSError, json.JSONDecodeError):
                    meta = {}
            rows.append({
                "id": directory.name,
                "name": meta.get("name") or stored.name,
                "mb": round(stored.stat().st_size / 1e6, 1),
                "links": stored.stat().st_nlink,
            })
    return {"entries": rows, "total_mb": round(sum(row["mb"] for row in rows), 1)}


@app.get("/api/jobs/{job_id}/mixer")
def job_mixer(
    job_id: str,
    target: int = 30,
    hook_scene: int | None = None,
    order: str = "source",
) -> dict:
    """Reel-time clip sections plus original/music envelopes for the mixer."""
    job = load_job(job_id)
    plan = _apply_order(job, _plan_for(job, _valid_target(int(target)), hook_scene), order)
    scenes = job["analysis"]["scenes"]
    scene_map = {scene["id"]: scene for scene in scenes}
    clips = [
        {
            "index": index,
            "scene": clip["scene"],
            "role": clip.get("role") or "beat",
            "start": round(float(clip.get("start") or 0.0), 3),
            "dur": round(float(clip.get("dur") or 0.0), 3),
            "label": f"{scene_map.get(clip['scene'], {}).get('start', 0):.0f}s",
        }
        for index, clip in enumerate(plan["clips"])
    ]
    total = round(sum(clip["dur"] for clip in clips), 3)
    fingerprint = str(job["source"].get("fingerprint") or job["source"].get("size") or "source")
    source_path = job["source"]["path"]
    original = audio.source_envelope(source_path, fingerprint, tag="mix")
    music_env: list[float] = []
    stem = audio.stem_cache_path(fingerprint, "no_vocals")
    if stem.is_file():
        music_env = audio.source_envelope(str(stem), fingerprint, tag="music")
    return {
        "total": total,
        "clips": clips,
        "envelopes": {
            "original": audio.reel_envelope(original, clips),
            "music": audio.reel_envelope(music_env, clips) if music_env else [],
            "music_available": bool(music_env),
            "bucket": 0.25,
        },
    }


@app.post("/api/jobs/{job_id}/ab")
def ab_package(job_id: str, body: PlanBody) -> dict:
    """Queue one render per top hook so 3 posts can be compared."""
    job = load_job(job_id)
    target = _valid_target(int(body.target))
    quality, aspect, encoder, captions, audio_plan, preset, margin = _render_options(body)
    script_id = _body_script_id(body, audio_plan)
    renders: list[dict] = []
    errors: list[dict] = []
    for scene in _top_hooks(job, target, 3):
        fresh = load_job(job_id)
        try:
            plan = _apply_order(
                fresh, _plan_for(fresh, target, scene["id"]), body.order,
            )
            caption_track = _caption_track_for_render(
                job_id, fresh, plan, body, captions, margin,
            )
            edit, edit_track = _classic_edit_from_body(
                job_id, fresh, plan, aspect, body, captions, margin, audio_plan,
            )
            if edit is not None:
                caption_track = edit_track
            record = _queue_render(
                job_id, fresh, plan, quality, aspect, encoder, captions,
                audio_plan, bool(body.force), preset=preset, caption_margin=margin,
                script_id=script_id, check_space=True,
                caption_track=caption_track, edit=edit,
            )
            renders.append(_public_render(job_id, record))
        except HTTPException as exc:
            errors.append({"hook": scene["id"], "detail": str(exc.detail)})
    return {"renders": renders, "errors": errors}


_NO_TRANSCRIPT_EXPORT = (
    "This cut has no transcript, so there are no captions to export. "
    "Import the video with Transcribe speech on, or use Retry speech."
)


def _caption_export_empty(content: str) -> bool:
    """True when an SRT or VTT holds no cues (a bare WEBVTT header counts)."""
    body = content.strip()
    if body.startswith("WEBVTT"):
        body = body[len("WEBVTT"):].strip()
    return not body


@app.get("/api/jobs/{job_id}/export/{kind}")
def export_cut(
    job_id: str,
    kind: str,
    target: int = 30,
    hook_scene: int | None = None,
    order: str = "source",
    artifact_id: str | None = None,
    caption_track_id: str | None = None,
) -> Response:
    if kind not in {"srt", "vtt", "edl", "xml"}:
        raise HTTPException(404, "Unknown export format.")
    job = load_job(job_id)
    if artifact_id:
        if kind not in {"srt", "vtt"}:
            raise HTTPException(400, "Artifact exports support SRT and VTT only.")
        manifest = artifacts.load_manifest(_job_dir(job_id), artifact_id)
        if manifest is None:
            raise HTTPException(404, "Artifact not found.")
        name = "captions.srt" if kind == "srt" else "captions.vtt"
        path = artifacts.media_path(_job_dir(job_id), artifact_id, name)
        if not path.is_file():
            raise HTTPException(404, "Artifact captions not found.")
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise HTTPException(404, "Artifact captions not found.") from exc
        if _caption_export_empty(content):
            raise HTTPException(409, _NO_TRANSCRIPT_EXPORT)
        return Response(
            content=content,
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{artifact_id}.{kind}"',
            },
        )
    plan = _apply_order(job, _plan_for(job, _valid_target(int(target)), hook_scene), order)
    return _export_plan_response(job_id, job, plan, kind, int(target), caption_track_id)


def _export_plan_response(
    job_id: str,
    job: dict,
    plan: dict,
    kind: str,
    target: int,
    caption_track_id: str | None = None,
) -> Response:
    scenes = job["analysis"]["scenes"]
    clips = plan["clips"]
    stem = Path(job["source"]["name"]).stem
    if kind in {"srt", "vtt"}:
        plan["_scenes"] = scenes
        prepared = render.prepare_render(plan, job["source"], None)
        track_plan = {
            **plan,
            "clips": prepared["clips"],
            "total": prepared["total"],
        }
        raw_hash = caption_engine.clip_hash(clips)
        prepared_hash = caption_engine.clip_hash(prepared["clips"])
        if caption_track_id:
            # A pinned track carries its own cut identity; trust it instead of
            # comparing against whichever auto plan this request happens to use.
            track = _caption_track_by_id(job_id, caption_track_id)
            if track.clip_hash == raw_hash and raw_hash != prepared_hash:
                track = caption_engine.build_track(
                    job, track_plan, track.style, job_dir=_job_dir(job_id),
                )
            elif track.clip_hash != prepared_hash:
                raise HTTPException(
                    409, "The caption track does not match this cut. Rebuild the track.",
                )
        else:
            track = _default_caption_track(
                job_id, job, track_plan, margin=0.075,
            )
        cues = [cue.to_dict() for cue in track.cues]
        content = cuts.srt(cues) if kind == "srt" else cuts.vtt(cues)
        media = "text/plain; charset=utf-8"
    elif kind == "edl":
        content = cuts.edl(plan, clips, job["source"]["name"])
        media = "text/plain; charset=utf-8"
    else:
        content = cuts.fcp7_xml(plan, clips, job["source"]["path"])
        media = "application/xml"
    if kind in {"srt", "vtt"} and _caption_export_empty(content):
        raise HTTPException(409, _NO_TRANSCRIPT_EXPORT)
    safe = "".join(
        ch if (ch.isascii() and (ch.isalnum() or ch in "._-")) else "-"
        for ch in stem
    ).strip("-") or "cut"
    filename = f"{safe}-{int(target)}s.{kind}"
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _story_key(set_id: str, story_id: str) -> str:
    return f"{set_id}:{story_id}"


def _story_in_set(record: dict, story_id: str) -> dict:
    story = next(
        (
            item for item in record.get("stories") or []
            if isinstance(item, dict) and item.get("id") == story_id
        ),
        None,
    )
    if story is None:
        raise HTTPException(404, "Story not found in this clip set.")
    return story


def _story_plan(job: dict, record: dict, story: dict, set_id: str) -> dict:
    """The story at its stored duration; never a 15/30/60 remap."""
    scenes = list((job.get("analysis") or {}).get("scenes") or [])
    try:
        return clipset.story_to_plan(story, scenes, target=None, set_id=set_id)
    except clipset.ClipSetError as exc:
        raise HTTPException(422, str(exc)) from exc


def _story_track_plan(job: dict, plan: dict) -> dict:
    """Plan with the clips render will actually burn, so the track is reused as-is."""
    plan = {**plan, "_scenes": (job.get("analysis") or {}).get("scenes") or []}
    prepared = render.prepare_render(plan, job.get("source") or {}, None)
    return {**plan, "clips": prepared["clips"], "total": prepared["total"]}


def _record_story_track(job_id: str, key: str, track_id: str) -> None:
    def mutate(job: dict) -> None:
        tracks = job.get("story_captions")
        if not isinstance(tracks, dict):
            tracks = {}
        tracks[key] = track_id
        job["story_captions"] = tracks

    update_job(job_id, mutate)


def _set_story_track(job_id: str, key: str, track_id: str) -> None:
    _record_story_track(job_id, key, track_id)
    _sync_story_edit_captions(job_id, key, track_id)


def default_story_caption_track(
    job_id: str,
    set_id: str,
    story_id: str,
) -> caption_engine.CaptionTrack | None:
    """The story's caption track in the default style, built when needed.

    Captions are on by default: a story Edit that never had a track gets the
    story's current track, or a new one built from the job's speech in the
    default style. Returns None when the job has no speech to caption or the
    story can't be resolved; this never raises, so it can't block an Edit or
    a render.
    """
    try:
        job = load_job(job_id)
        if job.get("status") != "ready" or not job.get("analysis"):
            return None
        job_dir = _job_dir(job_id)
        key = _story_key(set_id, story_id)
        record = _clip_set_in_job(job, set_id)
        _clip_set_source_state(job, record)
        story = _story_in_set(record, story_id)
        plan = _story_track_plan(job, _story_plan(job, record, story, set_id))
        current_hashes = {
            edits.clip_snapshot_hash(story.get("clips") or []),
            caption_engine.clip_hash(plan.get("clips")),
        }
        current_hashes.discard("")
        existing = str((job.get("story_captions") or {}).get(key) or "")
        if existing:
            track = caption_engine.load_track(job_dir, existing)
            if (
                track is not None
                and track.cues
                and (not track.clip_hash or track.clip_hash in current_hashes)
            ):
                return track
        segments = caption_engine.read_transcript_segments(job_dir)
        if not segments:
            return None
        track = caption_engine.build_track(
            job, plan, _caption_style_for(None),
            segments=segments, job_dir=job_dir,
        )
        if not track.cues:
            return None
        _record_story_track(job_id, key, track.id)
        return track
    except (HTTPException, caption_engine.CaptionError, OSError, ValueError) as exc:
        detail = getattr(exc, "detail", None) or str(exc)
        LOGGER.warning("No default captions for %s %s:%s: %s", job_id, set_id, story_id, detail)
        return None


def _edit_with_default_captions(
    job_id: str,
    job: dict,
    story: dict,
    set_id: str,
    edit: dict,
) -> dict:
    """Give an Edit that never had captions the story's default track.

    Edits made before captions were on by default (or migrated captions-only
    Edits) have ``enabled`` true but no track, which rendered no captions.
    Turning captions off stores ``enabled: false`` and is respected here.
    """
    captions = dict(edit.get("captions") or {})
    if captions.get("track_id") or captions.get("enabled") is False:
        return edit
    story_id = str(story.get("id") or "")
    track = default_story_caption_track(job_id, set_id, story_id)
    if track is None:
        return edit
    captions.update({"track_id": track.id, "style_id": track.style_id, "enabled": True})
    try:
        routes_edits.patch_edit(job_id, edit["id"], routes_edits.EditPatchBody(captions=captions))
    except HTTPException as exc:
        LOGGER.warning("Edit %s kept no captions: %s", edit["id"], exc.detail)
        return edit
    return _story_edit_for_render(load_job(job_id), story, set_id, edit["aspect"]) or edit


def _sync_story_edit_captions(job_id: str, key: str, track_id: str) -> None:
    """Point the story's current 9:16 Edit at a new Classic caption track.

    Migrated stories render through their Edit, so a Classic caption change
    must become a new Edit version or the next render would burn the old
    track. Same track is a no-op; any refusal leaves the Edit as it was.
    """
    set_id, _, story_id = key.partition(":")
    edit_key = edits.story_key(set_id, story_id, "9:16")
    edit_id = edits.pointer_edit_id(load_job(job_id), edit_key)
    if not edit_id:
        return
    try:
        edit = edits.load_edit(_job_dir(job_id), edit_id)
    except edits.EditError:
        return
    captions = dict((edit or {}).get("captions") or {})
    if not edit or captions.get("track_id") == track_id:
        return
    captions["track_id"] = track_id
    try:
        routes_edits.patch_edit(job_id, edit_id, routes_edits.EditPatchBody(captions=captions))
    except HTTPException as exc:
        LOGGER.warning("Edit %s kept its caption track: %s", edit_id, exc.detail)


def _build_story_caption_track(job_id: str, job: dict, body: CaptionTrackBody) -> dict:
    if not (body.set_id and body.story_id):
        raise HTTPException(400, "Send both set_id and story_id for a story track.")
    if job.get("status") != "ready" or not job.get("analysis"):
        raise HTTPException(409, "Analysis is not ready yet.")
    record = _clip_set_in_job(job, body.set_id)
    _clip_set_source_state(job, record)
    story = _story_in_set(record, body.story_id)
    plan = _story_track_plan(job, _story_plan(job, record, story, body.set_id))
    style = _caption_style_for(body.style_id, body.overrides)
    try:
        track = caption_engine.build_track(job, plan, style, job_dir=_job_dir(job_id))
    except caption_engine.CaptionError as exc:
        raise HTTPException(400, str(exc)) from exc
    _set_story_track(job_id, _story_key(body.set_id, body.story_id), track.id)
    return {
        "track": track.to_dict(),
        "id": track.id,
        "track_id": track.id,
        "version": track.version,
        "cue_count": len(track.cues),
        "set_id": body.set_id,
        "story_id": body.story_id,
        "duration": plan["total"],
    }


@app.post("/api/jobs/{job_id}/captions")
def build_caption_track(job_id: str, body: CaptionTrackBody) -> dict:
    """Build a speech-timed caption track for the requested cut.

    With ``set_id``/``story_id`` the track is built for the story at its stored
    duration, against the exact clips the story render will burn, and becomes
    that story's current track.
    """
    job = load_job(job_id)
    if body.set_id or body.story_id:
        return _build_story_caption_track(job_id, job, body)
    target = _valid_target(int(body.target))
    plan_body = PlanBody(
        target=target,
        hook_scene=body.hook_scene,
        clips=body.clips,
        order=body.order,
    )
    plan = _plan_for_body(job, target, plan_body)
    style = _caption_style_for(body.style_id, body.overrides)
    try:
        track = caption_engine.build_track(
            job, plan, style, job_dir=_job_dir(job_id),
        )
    except caption_engine.CaptionError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "track": track.to_dict(),
        "id": track.id,
        "track_id": track.id,
        "version": track.version,
        "cue_count": len(track.cues),
    }


@app.get("/api/jobs/{job_id}/captions/{track_id}/srt")
def caption_track_srt(job_id: str, track_id: str) -> Response:
    track = _caption_track_by_id(job_id, track_id)
    content = cuts.srt([cue.to_dict() for cue in track.cues])
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{track.id}.srt"',
        },
    )


@app.get("/api/jobs/{job_id}/captions/{track_id}/preview")
def caption_track_preview(job_id: str, track_id: str) -> dict:
    """Caption-only preview payload. Never starts a full render."""
    job = load_job(job_id)
    track = _caption_track_by_id(job_id, track_id)
    duration = round(sum(
        float(window.get("duration") or 0.0)
        for window in track.clip_windows
    ), 3)
    return {
        "track_id": track.id,
        "job_id": job_id,
        "version": track.version,
        "target": track.target,
        "cues": [cue.to_dict() for cue in track.cues],
        "style": track.style,
        "style_id": track.style_id,
        "style_hash": track.style_hash,
        "cue_hash": track.cue_hash,
        "clip_hash": track.clip_hash,
        "safe_zones": caption_engine.safe_zone_rects(track.style),
        "poster_url": _caption_poster_url(job, track),
        "duration": duration,
        "source": track.source,
        "warnings": track.warnings,
        "full_render": False,
        "caption_only": True,
    }


@app.get("/api/jobs/{job_id}/captions/{track_id}")
def get_caption_track(job_id: str, track_id: str) -> dict:
    return _caption_track_payload(_caption_track_by_id(job_id, track_id))


@app.patch("/api/jobs/{job_id}/captions/{track_id}")
def edit_caption_track(
    job_id: str,
    track_id: str,
    body: CaptionEditBody,
) -> dict:
    """Edit cue text/timing or style. Changed content becomes a new version."""
    load_job(job_id)
    track = _caption_track_by_id(job_id, track_id)
    clips = _track_validation_clips(track)
    total = round(sum(
        float(window.get("duration") or 0.0)
        for window in track.clip_windows
    ), 3)
    try:
        edited, changed = caption_engine.edit_track(
            track,
            cues=body.cues,
            style=body.style,
            style_id=body.style_id,
            overrides=body.overrides,
            settings=settings_store.load_settings(),
            clips=clips,
            total=total,
            job_dir=_job_dir(job_id),
        )
    except caption_engine.CaptionError as exc:
        raise HTTPException(400, str(exc)) from exc
    if changed and edited.id != track_id:
        story_keys = [
            key for key, value in (load_job(job_id).get("story_captions") or {}).items()
            if value == track_id
        ]
        for key in story_keys:
            _set_story_track(job_id, key, edited.id)
    return {
        "track": edited.to_dict(),
        "id": edited.id,
        "track_id": edited.id,
        "version": edited.version,
        "changed": changed,
    }


@app.post("/api/jobs/{job_id}/audio/script")
def audio_script(job_id: str, body: ScriptBody) -> dict:
    """List the cleaned, de-duplicated, time-fitted voice script for a cut."""
    job = load_job(job_id)
    started = time.time()
    script_id = uuid.uuid4().hex[:12]
    mode = body.mode if body.mode in {"literal", "smooth", "viral", "fun", "creative", "sad", "chill"} else "smooth"
    overrides = body.overrides if isinstance(body.overrides, dict) else {}
    target = int(body.target)
    source_lang = str(
        ((job.get("analysis") or {}).get("engine") or {}).get("transcript_language") or "en"
    ).split("-")[0]
    target_lang = str(body.translate or "").split("-")[0]
    before_usage = usage_store.snapshot()
    plan: dict | None = None
    clips: list[dict] = []
    script: list[dict] = []
    context: dict | None = None
    warning: str | None = None
    translated = False

    def record_failure(exc: Exception) -> None:
        try:
            detail = getattr(exc, "detail", None) or str(exc) or exc.__class__.__name__
            delta = usage_store.delta(before_usage)
            translation = audio.translation_status()
            rewrite = audio.rewrite_status()
            snapshot = {
                "script_id": script_id,
                "target": target,
                "style": mode,
                "source_lang": source_lang,
                "target_lang": target_lang or source_lang,
                "overrides": overrides,
                "clip_hash": _clip_hash((plan or {}).get("clips")),
                "original_lines": [
                    str(line.get("original") or line.get("text") or "") for line in script
                ],
                "literal_lines": [
                    str(line.get("literal") or line.get("text") or "") for line in script
                ],
                "final_lines": script,
                "translation": translation,
                "rewrite": rewrite,
                "translated": translated,
                "warning": None,
                "error": str(detail)[:2400],
                "usage": delta,
                "latency_ms": round((time.time() - started) * 1000),
            }
            _history_append(
                job_id,
                {
                    "id": script_id,
                    "type": "script",
                    "created": round(time.time(), 3),
                    "status": "failed",
                    "target": target,
                    "style": mode,
                    "source_lang": source_lang,
                    "target_lang": target_lang or source_lang,
                    "provider": str(body.provider or ""),
                    "fallback": False,
                    "tried": _history_tried(translation, rewrite),
                    "model": _provider_model(rewrite.get("provider")),
                    "latency_ms": snapshot["latency_ms"],
                    "usage": delta,
                    "warning": None,
                    "error": str(detail)[:2400],
                    "path": None,
                    "script_id": script_id,
                    "clip_hash": snapshot["clip_hash"],
                },
                snapshot,
            )
        except Exception:  # noqa: BLE001
            LOGGER.exception("could not record failed script attempt for %s", job_id)

    try:
        target = _valid_target(target)
        if body.clips:
            plan = _custom_plan(job, target, body.hook_scene, body.clips)
        else:
            plan = _plan_for(job, target, body.hook_scene)
        plan = _apply_order(job, plan, body.order)
        scenes = job["analysis"]["scenes"]
        clips = [
            {
                "scene": clip["scene"],
                "role": clip.get("role") or "beat",
                "duration": round(float(clip["dur"]), 3),
            }
            for clip in plan["clips"]
        ]
        segments = pipeline.read_transcript(_job_dir(job_id)) or []
        script = audio.build_script(scenes, clips, segments=segments)
        offsets: list[float] = []
        running = 0.0
        for clip in clips:
            offsets.append(running)
            running += float(clip["duration"])
        offsets.append(running)
        for line in script:
            index = max(0, min(int(line.get("clip") or 0), len(offsets) - 1))
            line["offset"] = round(offsets[index], 2)
        source_lang = str(
            plan.get("_source_lang")
            or (job["analysis"].get("engine") or {}).get("transcript_language")
            or "en"
        ).split("-")[0]
        target_lang = str(body.translate or "").split("-")[0]
        # Clear once per request, before context and script translation. Both passes
        # reuse the same memo; force_translate=false always reads the memo.
        if body.force_translate and target_lang and target_lang != source_lang:
            source_lines = [str(line.get("text") or "") for line in script]
            source_lines.extend(str(segment.get("text") or "") for segment in segments)
            audio.clear_translation_memo(source_lines, source_lang, target_lang, body.provider)

        def apply_overrides(lines: list[dict]) -> None:
            for line in lines:
                value = overrides.get(str(line.get("scene")))
                if isinstance(value, str) and value.strip():
                    line["text"] = audio.clean_line(value)
                    line["overridden"] = True

        context = (
            audio.transcript_context(
                segments, clips, scenes, source_lang,
                target_lang=target_lang, translate_provider=body.provider,
                brief_provider=body.provider, rewrite_provider=body.rewrite_provider,
            )
            if segments else None
        )
        try:
            script = audio.adapt_script(
                script, source_lang, target_lang, mode, body.provider, context,
                body.rewrite_provider,
            )
            apply_overrides(script)
            script = audio.refit_script(script)
            translated = bool(target_lang and target_lang != source_lang)
        except audio.AudioError as exc:
            warning = str(exc)[:400]
            if mode != "literal":
                audio.mark_rewrite_error(warning)
        rewrite = audio.rewrite_status()
        if rewrite.get("fallback") and not warning:
            warning = str(
                rewrite.get("error") or "Rewrite unavailable; kept the literal translation."
            )[:400]
        script_delta = usage_store.delta(before_usage)
        if script_delta["calls"] or script_delta["chars"] or script_delta["audio_seconds"]:
            job.setdefault("usage", []).append({
                "action": "script",
                "at": round(time.time(), 3),
                **script_delta,
            })
            job["usage"] = job["usage"][-100:]
            save_job(job)
        translation = audio.translation_status()
        moods = audio.scene_moods(scenes, clips)
        total = round(sum(float(clip["duration"]) for clip in clips), 3)
        clip_hash = _clip_hash(plan["clips"])
        fallback = bool(warning or rewrite.get("fallback"))
        provider = str(translation.get("provider") or "")
        if not provider or provider == "none":
            provider = str(rewrite.get("provider") or body.provider or "")
        tried = _history_tried(translation, rewrite)
        model_provider = str(translation.get("provider") or "")
        if not translated or model_provider in {"", "none", "cache"}:
            model_provider = str(rewrite.get("provider") or provider)
        model = _provider_model(model_provider)
        latency_ms = round((time.time() - started) * 1000)
        snapshot = {
            "script_id": script_id,
            "target": target,
            "style": mode,
            "source_lang": source_lang,
            "target_lang": target_lang or source_lang,
            "overrides": overrides,
            "clip_hash": clip_hash,
            "original_lines": [
                str(line.get("original") or line.get("text") or "") for line in script
            ],
            "literal_lines": [
                str(line.get("literal") or line.get("text") or "") for line in script
            ],
            "final_lines": script,
            "translation": translation,
            "rewrite": rewrite,
            "translated": translated,
            "warning": warning,
            "error": None,
            "provider": provider,
            "model": model,
            "rewrite_model": _provider_model(rewrite.get("provider")),
            "tried": tried,
            "fallback": fallback,
            "total": total,
            "moods": moods,
            "usage": script_delta,
            "latency_ms": latency_ms,
        }
        _history_append(
            job_id,
            {
                "id": script_id,
                "type": "script",
                "created": round(time.time(), 3),
                "status": "fallback" if warning else "ok",
                "target": target,
                "style": mode,
                "source_lang": source_lang,
                "target_lang": target_lang or source_lang,
                "provider": provider,
                "fallback": fallback,
                "tried": tried,
                "model": model,
                "latency_ms": latency_ms,
                "usage": script_delta,
                "warning": warning,
                "error": None,
                "path": None,
                "script_id": script_id,
                "clip_hash": clip_hash,
            },
            snapshot,
        )
        # Keep translation and rewrite as separate history rows. The script row
        # remains the combined artifact, but users can filter/replay each step.
        if target_lang and target_lang != source_lang:
            _history_append(
                job_id,
                {
                    "id": uuid.uuid4().hex[:12],
                    "type": "translation",
                    "created": round(time.time(), 3),
                    "status": "ok" if translated else "failed",
                    "target": target,
                    "style": mode,
                    "source_lang": source_lang,
                    "target_lang": target_lang,
                    "provider": str(translation.get("provider") or ""),
                    "fallback": bool(translation.get("tried") and len(translation.get("tried") or []) > 1),
                    "tried": translation.get("tried") or [],
                    "model": None,
                    "latency_ms": latency_ms,
                    "usage": {},
                    "warning": warning,
                    "error": None if translated else "Translation did not complete.",
                    "script_id": script_id,
                    "clip_hash": clip_hash,
                },
                {
                    "script_id": script_id,
                    "source_lang": source_lang,
                    "target_lang": target_lang,
                    "original_lines": snapshot["original_lines"],
                    "translated_lines": snapshot["literal_lines"],
                    "translation": translation,
                    "warning": warning,
                },
            )
        if mode != "literal":
            _history_append(
                job_id,
                {
                    "id": uuid.uuid4().hex[:12],
                    "type": "rewrite",
                    "created": round(time.time(), 3),
                    "status": "fallback" if rewrite.get("fallback") else "ok",
                    "target": target,
                    "style": mode,
                    "source_lang": source_lang,
                    "target_lang": target_lang or source_lang,
                    "provider": str(rewrite.get("provider") or ""),
                    "fallback": bool(rewrite.get("fallback")),
                    "tried": rewrite.get("attempts") or [],
                    "model": _provider_model(rewrite.get("provider")),
                    "latency_ms": latency_ms,
                    "usage": {},
                    "warning": warning,
                    "error": rewrite.get("error") or None,
                    "script_id": script_id,
                    "clip_hash": clip_hash,
                },
                {
                    "script_id": script_id,
                    "style": mode,
                    "lines": script,
                    "rewrite": rewrite,
                    "warning": warning,
                },
            )
        return {
            "lines": script,
            "mode": mode,
            "rewrite": (script[0].get("rewrite") if script else "literal"),
            "context_chars": len((context or {}).get("full_text") or ""),
            "overrides": overrides,
            "source_lang": source_lang,
            "target": target_lang or source_lang,
            "translated": translated,
            "warning": warning,
            "rewrite_status": rewrite,
            "moods": moods,
            "total": total,
            "usage": _usage_summary(job),
            "translation_status": translation,
            "script_id": script_id,
        }
    except Exception as exc:
        record_failure(exc)
        raise


def _valid_script_id(job_id: str, plan: dict, script_id: str | None) -> str | None:
    """Only attach a history script when its saved cut still matches this plan."""
    if not script_id:
        return None
    try:
        item = history_store.get_entry(_job_dir(job_id), script_id)
    except Exception:  # noqa: BLE001
        return None
    if not item:
        return None
    saved = str((item.get("entry") or {}).get("clip_hash") or "")
    current = _clip_hash(plan.get("clips"))
    if saved and current and saved != current:
        return None
    return script_id


def _queue_render(
    job_id: str,
    job: dict,
    plan: dict,
    quality: str,
    aspect: str,
    encoder: str | None,
    captions: bool,
    audio_plan: dict | None,
    force: bool,
    preset: str | None = None,
    caption_margin: float = 0.075,
    script_id: str | None = None,
    check_space: bool = False,
    caption_track: caption_engine.CaptionTrack | None = None,
    reject_active: bool = False,
    edit: dict | None = None,
) -> dict:
    """Serialize check/write/submit so one record key cannot queue twice."""
    require_source(job)
    with RENDER_SUBMIT_LOCK:
        return _queue_render_locked(
            job_id, job, plan, quality, aspect, encoder, captions, audio_plan,
            force, preset=preset, caption_margin=caption_margin,
            script_id=script_id, check_space=check_space,
            caption_track=caption_track, reject_active=reject_active,
            edit=edit,
        )


def _queue_render_locked(
    job_id: str,
    job: dict,
    plan: dict,
    quality: str,
    aspect: str,
    encoder: str | None,
    captions: bool,
    audio_plan: dict | None,
    force: bool,
    preset: str | None = None,
    caption_margin: float = 0.075,
    script_id: str | None = None,
    check_space: bool = False,
    caption_track: caption_engine.CaptionTrack | None = None,
    reject_active: bool = False,
    edit: dict | None = None,
) -> dict:
    # Reserve generations and write manifests serially so two force requests
    # can never race to the same artifact id.
    with QUEUE_LOCK:
        current = load_job(job_id)
        return _queue_render_locked_impl(
            job_id, current, plan, quality, aspect, encoder, captions,
            audio_plan, force, preset=preset,
            caption_margin=caption_margin, script_id=script_id,
            check_space=check_space, caption_track=caption_track,
            reject_active=reject_active, edit=edit,
        )


def _queue_render_locked_impl(
    job_id: str,
    job: dict,
    plan: dict,
    quality: str,
    aspect: str,
    encoder: str | None,
    captions: bool,
    audio_plan: dict | None,
    force: bool,
    preset: str | None = None,
    caption_margin: float = 0.075,
    script_id: str | None = None,
    check_space: bool = False,
    caption_track: caption_engine.CaptionTrack | None = None,
    reject_active: bool = False,
    edit: dict | None = None,
) -> dict:
    target = int(plan["target"])
    audio_sig = _audio_signature(audio_plan)
    record_key = _render_key(
        target, quality, aspect, captions, audio_sig, _hook_marker(plan),
        story_id=plan.get("story_id"),
    )
    job_dir = _job_dir(job_id)
    job_scenes = (job.get("analysis") or {}).get("scenes") or []
    plan["_scenes"] = job_scenes
    plan["_source_duration"] = float(
        (job.get("source") or {}).get("duration") or 0.0
    )
    raw_clip_hash = caption_engine.clip_hash(plan.get("clips"))
    prepared = render.prepare_render(
        plan, job.get("source") or {}, audio_plan,
    )
    prepared_clips = prepared["clips"]
    prepared_total = prepared["total"]
    cues: list[dict] = _reel_cues(job, plan, prepared_clips)
    if captions:
        track_plan = {
            **plan,
            "clips": prepared_clips,
            "total": prepared_total,
        }
        prepared_hash = caption_engine.clip_hash(prepared_clips)
        if caption_track is None:
            caption_track = _default_caption_track(
                job_id, job, track_plan, margin=caption_margin,
            )
        elif caption_track.clip_hash == prepared_hash:
            pass
        elif caption_track.clip_hash == raw_clip_hash:
            caption_track = _caption_track_for_cut(
                job, job_dir, caption_track, plan.get("clips"), track_plan,
            )
        else:
            raise HTTPException(
                409, "The caption track does not match this cut. Rebuild the track.",
            )
        _attach_caption_track(plan, caption_track)
        cues = [cue.to_dict() for cue in caption_track.cues]
    caption_sig = str(plan.get("_caption_key") or "") if captions else ""
    base_spec = artifacts.build_spec(
        job, plan,
        quality=quality, aspect=aspect, encoder=encoder,
        captions=captions, audio_sig=audio_sig, preset=preset,
        caption_margin=caption_margin,
        caption_style_key=(
            (plan.get("_caption_track") or {}).get("style_hash") or ""
        ),
        cues=cues,
        clips=prepared_clips,
        story_id=plan.get("story_id"),
        edit_hash=(edit or {}).get("hash") or "",
    )
    generation = artifacts.resolve_generation(job_dir, base_spec, force=force)
    spec = replace(base_spec, generation=generation)
    artifact = artifacts.artifact_id(spec)
    key = hashlib.sha1(json.dumps({
        "target": target,
        "clips": plan["clips"],
        "quality": quality,
        "aspect": aspect,
        "encoder": spec.resolved_encoder,
        "captions": captions,
        "caption": caption_sig,
        "caption_margin": round(float(caption_margin), 4) if captions else 0,
        "audio": audio_plan or None,
        "nonce": time.time() if force else None,
    }, sort_keys=True).encode()).hexdigest()[:12]

    existing = (load_job(job_id).get("renders") or {}).get(record_key)
    if existing and existing.get("status") in ACTIVE_RENDER:
        if reject_active:
            raise HTTPException(409, "That story is already rendering.")
        if existing.get("artifact_id") == artifact and not force:
            return existing
        raise HTTPException(409, "That reel is already rendering.")

    manifest = artifacts.load_manifest(job_dir, artifact)
    if (
        manifest is None
        and existing
        and existing.get("status") == "ready"
        and not existing.get("artifact_id")
        and not force
        and generation == 0
    ):
        adopted = _adopt_render_artifact(job, existing, target, aspect)
        if (
            adopted
            and adopted.get("artifact_id") == artifact
            and adopted.get("status") == "ready"
        ):
            existing["artifact_id"] = artifact
            existing["resolved_encoder"] = spec.resolved_encoder

            def adopt(value: dict) -> None:
                value.setdefault("renders", {})[record_key] = existing
                artifacts.ensure_job_schema(value, job_dir)

            update_job(job_id, adopt)
            return existing
    if (
        manifest
        and manifest.get("status") == "ready"
        and not force
        and artifacts.has_media(job_dir, artifact)
    ):
        if (
            existing
            and existing.get("status") == "ready"
            and existing.get("artifact_id") == artifact
        ):
            return existing
        reused = artifacts.render_record(manifest)
        reused["audio"] = audio_plan or None
        reused["preset"] = preset
        reused["caption_margin"] = caption_margin
        reused["script_id"] = script_id
        reused["caption_track_id"] = plan.get("_caption_key")
        reused["caption_clip_hash"] = (
            (plan.get("_caption_track") or {}).get("clip_hash")
        )
        reused["caption_style_id"] = (plan.get("_caption_style") or {}).get("id")
        reused["cue_hash"] = (plan.get("_caption_track") or {}).get("cue_hash")
        reused["style_hash"] = (plan.get("_caption_track") or {}).get("style_hash")
        reused["caption_count"] = len(cues)
        reused["story_id"] = plan.get("story_id")
        reused["set_id"] = plan.get("clip_set_id")

        def reuse(value: dict) -> None:
            value.setdefault("renders", {})[record_key] = reused
            artifacts.ensure_job_schema(value, job_dir)

        update_job(job_id, reuse)
        return reused

    if check_space:
        disk.preflight(disk.estimate_render(target, quality, aspect), DATA)
    try:
        attempts = int((existing or {}).get("attempts") or 0)
    except (TypeError, ValueError):
        attempts = 0
    if existing and existing.get("status") in {"failed", "interrupted", "cancelled"}:
        attempts += 1

    if manifest is None:
        manifest = artifacts.make_manifest(
            job_id, spec, status="queued", record_key=record_key,
            title=f"{Path(job.get('source', {}).get('name') or 'reel').stem} · {target}s cut",
        )
        artifacts.assign_version(job_dir, manifest)
    elif manifest.get("status") != "ready":
        manifest["status"] = "queued"
        manifest["error"] = None
        manifest["record_key"] = record_key
        manifest["spec"] = spec.payload()
    if manifest.get("artifact_id") not in (None, artifact):
        manifest["artifact_id"] = artifact
    manifest["caption_track_id"] = plan.get("_caption_key")
    manifest["caption_style_id"] = (plan.get("_caption_style") or {}).get("id")
    manifest["set_id"] = plan.get("clip_set_id")
    artifacts.save_manifest(job_dir, manifest)

    record = {
        "status": "queued",
        "progress": 0.0,
        "message": "Queued",
        "key": key,
        "record_key": record_key,
        "audio_sig": audio_sig,
        "audio": audio_plan or None,
        "hook": plan["hook_scene"],
        "target": target,
        "total": plan["total"],
        "quality": quality,
        "aspect": aspect,
        "encoder": spec.resolved_encoder,
        "resolved_encoder": spec.resolved_encoder,
        "captions": captions,
        "preset": preset,
        "caption_margin": caption_margin,
        "order": plan.get("order") or "source",
        "created": round(time.time(), 3),
        "script_id": script_id,
        "artifact_id": artifact,
        "generation": generation,
        "attempts": attempts,
        "story_id": plan.get("story_id"),
        "set_id": plan.get("clip_set_id"),
        "edit_id": (edit or {}).get("id"),
        "edit_hash": (edit or {}).get("hash"),
        "plan_snapshot": {
            "target": target,
            "hook_scene": plan.get("hook_scene"),
            "order": plan.get("order") or "source",
            "auto": bool(plan.get("auto", True)),
            "clips": plan.get("clips") or [],
            "story_id": plan.get("story_id"),
            "set_id": plan.get("clip_set_id"),
        },
        "caption_track_id": plan.get("_caption_key"),
        "caption_clip_hash": (plan.get("_caption_track") or {}).get("clip_hash"),
        "caption_style_id": (plan.get("_caption_style") or {}).get("id"),
        "cue_hash": (plan.get("_caption_track") or {}).get("cue_hash"),
        "style_hash": (plan.get("_caption_track") or {}).get("style_hash"),
        "caption_count": len(cues),
    }

    def mutate(value: dict) -> None:
        value.setdefault("renders", {})[record_key] = record
        artifacts.ensure_job_schema(value, job_dir)

    update_job(job_id, mutate)
    queued_history = _record_render_history(
        job_id, record, plan, audio_plan, "queued",
        script_id=script_id, latency_ms=0,
    )
    if queued_history:
        history_id = queued_history.get("id")

        def attach_history(value: dict) -> None:
            stored = (value.get("renders") or {}).get(record_key)
            if isinstance(stored, dict):
                stored["history_id"] = history_id

        update_job(job_id, attach_history)
    render_pool.submit(
        run_render, job_id, target, plan, key, quality, aspect, encoder, captions,
        audio_plan, audio_sig, preset, caption_margin, script_id, artifact,
        generation, prepared_clips, prepared_total,
        edit=edit,
        task_kind="render", task_key=f"render:{job_id}:{record_key}",
    )
    return record

def _render_options(
    body: PlanBody,
) -> tuple[str, str, str | None, bool, dict | None, str | None, float]:
    quality = body.quality if body.quality in ("final", "720", "draft") else "final"
    preset = body.preset if body.preset in render.PRESETS else None
    preset_cfg = render.PRESETS.get(preset or "", {})
    aspect = body.aspect if body.aspect in render.ASPECTS else "9:16"
    if preset_cfg.get("aspect"):
        aspect = preset_cfg["aspect"]
    captions = bool(body.captions) or bool(preset_cfg.get("captions"))
    margin = (
        float(body.caption_margin)
        if body.caption_margin is not None
        else float(preset_cfg.get("caption_margin") or 0.075)
    )
    audio_plan = body.audio if isinstance(body.audio, dict) else None
    if audio_plan and str(audio_plan.get("mode") or "keep") == "keep":
        audio_plan = None
    return quality, aspect, body.encoder, captions, audio_plan, preset, margin


def _classic_edit_from_body(
    job_id: str,
    job: dict,
    plan: dict,
    aspect: str,
    body: PlanBody,
    captions: bool,
    margin: float | None,
    audio_plan: dict | None,
):
    """Turn Classic's layer payload into the Edit the renderer compiles."""
    if STUDIO_APP:
        # Studio renders saved edits through routes_edits, never this payload.
        return None, None
    if not isinstance(body.edit, dict) or not body.edit:
        return None, None
    return routes_classic.prepare_classic_render(
        job_id, job, plan, aspect, body.edit,
        captions=captions, margin=margin, audio_plan=audio_plan,
    )


@app.post("/api/jobs/{job_id}/render")
def start_render(job_id: str, body: PlanBody) -> dict:
    job = load_job(job_id)
    target = _valid_target(int(body.target))
    quality, aspect, encoder, captions, audio_plan, preset, margin = _render_options(body)
    plan = _plan_for_body(job, target, body)
    caption_track = _caption_track_for_render(
        job_id, job, plan, body, captions, margin,
    )
    edit, edit_track = _classic_edit_from_body(
        job_id, job, plan, aspect, body, captions, margin, audio_plan,
    )
    if edit is not None:
        caption_track = edit_track
    record = _queue_render(
        job_id, job, plan, quality, aspect, encoder, captions, audio_plan,
        bool(body.force), preset=preset, caption_margin=margin,
        script_id=_body_script_id(body, audio_plan), check_space=True,
        caption_track=caption_track, edit=edit,
    )
    return {"render": _public_render(job_id, record)}


@app.post("/api/jobs/{job_id}/render-all")
def start_render_all(job_id: str, body: PlanBody) -> dict:
    load_job(job_id)
    quality, aspect, encoder, captions, audio_plan, preset, margin = _render_options(body)
    script_id = _body_script_id(body, audio_plan)
    renders: list[dict] = []
    errors: list[dict] = []
    for target in (15, 30, 60):
        job = load_job(job_id)
        try:
            plan = _apply_order(job, _plan_for(job, target, body.hook_scene), body.order)
            caption_track = _caption_track_for_render(
                job_id, job, plan, body, captions, margin,
            )
            edit, edit_track = _classic_edit_from_body(
                job_id, job, plan, aspect, body, captions, margin, audio_plan,
            )
            if edit is not None:
                caption_track = edit_track
            record = _queue_render(
                job_id, job, plan, quality, aspect, encoder, captions, audio_plan,
                bool(body.force), preset=preset, caption_margin=margin,
                script_id=script_id, check_space=True,
                caption_track=caption_track, edit=edit,
            )
            renders.append(_public_render(job_id, record))
        except HTTPException as exc:
            errors.append({"target": target, "detail": str(exc.detail)})
    return {"renders": renders, "errors": errors}


@app.post("/api/jobs/{job_id}/render/{target}/cancel")
def cancel_render(
    job_id: str,
    target: int,
    quality: str = "final",
    aspect: str = "9:16",
    captions: bool = False,
    audio_sig: str = "",
    hook_marker: int | None = None,
    record_key: str | None = None,
    story_id: str | None = None,
) -> dict:
    # Story renders carry their stored duration and a record key; only the
    # legacy key derivation needs a 15/30/60 target.
    if not record_key:
        target = _valid_target(int(target))
    quality = quality if quality in ("final", "720", "draft") else "final"
    aspect = aspect if aspect in render.ASPECTS else "9:16"
    if not record_key:
        record_key = _render_key(
            target, quality, aspect, captions, audio_sig,
            int(hook_marker) if hook_marker is not None else None,
            story_id=story_id,
        )
    job = load_job(job_id)
    record = (job.get("renders") or {}).get(record_key)
    if not record or record.get("status") not in ACTIVE_RENDER:
        raise HTTPException(409, "That reel is not rendering.")
    event = RENDER_CANCELS.setdefault((job_id, record_key), threading.Event())
    event.set()
    _set_render(
        job_id, record_key,
        status="cancelling", message="Stopping…", error=None,
    )
    latest = (load_job(job_id).get("renders") or {}).get(record_key) or record
    return {"render": _public_render(job_id, latest)}


@app.post("/api/jobs/{job_id}/clean")
def clean_job(job_id: str, body: CleanBody) -> dict:
    """Delete working files for a job. Source video and job.json stay."""
    profile = body.profile if body.profile in {"workfiles", "renders", "all"} else "workfiles"
    removed: list[str] = []

    def mutate(job: dict) -> None:
        if job.get("status") in LIVE or any(
            record.get("status") in ACTIVE_RENDER
            for record in (job.get("renders") or {}).values()
        ):
            raise HTTPException(409, "This job is still working.")
        removed.extend(clean_job_files(job, profile))

    try:
        update_job(job_id, mutate)
    except shares.ShareStoreError as exc:
        raise _share_store_unavailable(exc) from exc
    LOGGER.info("cleaned %s for job %s", ", ".join(removed) or "nothing", job_id)
    return {"cleaned": removed, "profile": profile}


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str) -> dict:
    with LOCK:
        job = _load_unlocked(job_id)
        if (
            job.get("status") in LIVE
            or _has_active_artifacts(job)
            or any(
                record.get("status") in ACTIVE_RENDER
                for record in (job.get("renders") or {}).values()
            )
        ):
            raise HTTPException(409, "This job is still working.")
        try:
            protected = _job_has_protection(job)
        except shares.ShareStoreError as exc:
            raise _share_store_unavailable(exc) from exc
        if protected:
            raise HTTPException(409, "Unpin artifacts and revoke review links before deleting this job.")
        shutil.rmtree(_job_dir(job_id), ignore_errors=True)
    routes_voice_clone.forget_job(job_id)
    return {"deleted": job_id}


# ------------------------------------------------ explicit source delete


RECEIPT_NAME = "deletion_receipt.json"


class SourceDeleteBody(BaseModel):
    cascade: bool = False


def _cas_entry_for(path: Path) -> Path | None:
    """The source-store file that shares this job file's inode, if any."""
    if not SOURCES.is_dir() or not path.is_file():
        return None
    for directory in SOURCES.iterdir():
        if not directory.is_dir():
            continue
        for item in directory.iterdir():
            if item.is_file() and item.name.startswith("source"):
                try:
                    if os.path.samefile(item, path):
                        return item
                except OSError:
                    continue
    return None


def _source_refs(job: dict) -> dict:
    job_dir = _job_dir(job["id"])
    source = job.get("source") or {}
    path = Path(str(source.get("path") or ""))
    in_job = bool(source.get("path")) and path.parent.resolve() == job_dir.resolve()
    cas = _cas_entry_for(path) if in_job else None
    manifests = artifacts.list_manifests(job_dir)
    try:
        live = shares.active_records(SHARES, job_id=job["id"], strict=True)
    except shares.ShareStoreError as exc:
        raise _share_store_unavailable(exc) from exc
    return {
        "job_id": job["id"],
        "source_name": source.get("name"),
        "present": path.is_file(),
        "managed": in_job,
        "bytes": path.stat().st_size if path.is_file() else 0,
        "cas_id": cas.parent.name if cas is not None else None,
        "refcount": (cas.stat().st_nlink - 1) if cas is not None else (1 if path.is_file() else 0),
        "artifacts": sum(1 for item in manifests if item.get("status") == "ready"),
        "packets": len(packet.list_packets(job_dir)),
        "shares": len(live),
        "deleted_at": source.get("deleted_at"),
    }


@app.get("/api/jobs/{job_id}/source")
def source_references(job_id: str) -> dict:
    """What deleting this source would touch: CAS refs, artifacts, packets, links."""
    return _source_refs(load_job(job_id))


@app.post("/api/jobs/{job_id}/source/delete")
def delete_source_now(job_id: str, body: SourceDeleteBody | None = None) -> dict:
    """Delete client footage on request and prove it left the store.

    Artifacts, packets and review links are outputs and stay. Because they
    pin this source's cuts, deleting with any of them present needs
    ``cascade: true``. A file imported by path is the user's own file and is
    never deleted; only the job's reference to it is dropped.
    """
    body = body or SourceDeleteBody()
    with LOCK:
        job = _load_unlocked(job_id)
        if job.get("status") in LIVE or _has_active_artifacts(job) or any(
            record.get("status") in ACTIVE_RENDER
            for record in (job.get("renders") or {}).values()
        ):
            raise HTTPException(409, "This job is still working.")
        refs = _source_refs(job)
        if refs["deleted_at"]:
            raise HTTPException(409, "This source was already deleted.")
        if (refs["artifacts"] or refs["packets"] or refs["shares"]) and not body.cascade:
            raise HTTPException(
                409,
                {
                    "code": "source_referenced",
                    "message": "Renders, packets or review links use this source. Confirm to delete it anyway; they stay.",
                    "refs": refs,
                },
            )
        source = job.get("source") or {}
        path = Path(str(source.get("path") or ""))
        job_dir = _job_dir(job_id)
        cas = _cas_entry_for(path) if refs["managed"] else None
        before = refs["refcount"]
        removed: list[str] = []
        if refs["managed"] and path.is_file():
            path.unlink()
            removed.append(path.name)
        after = (cas.stat().st_nlink - 1) if cas is not None and cas.is_file() else 0
        cas_deleted = False
        if cas is not None and cas.is_file() and cas.stat().st_nlink <= 1:
            shutil.rmtree(cas.parent, ignore_errors=True)
            cas_deleted = not cas.parent.exists()
            after = 0
        for derived in (job_dir / "audio", DATA / "cache" / "masters" / job_id):
            if derived.exists():
                shutil.rmtree(derived, ignore_errors=True)
                removed.append(str(derived.relative_to(DATA)))
        absent = not path.exists() if refs["managed"] else True
        cas_absent = cas is None or not cas.exists() or after > 0
        receipt = {
            "job_id": job_id,
            "source_name": refs["source_name"],
            "source_hash": refs["cas_id"],
            "bytes": refs["bytes"],
            "managed": refs["managed"],
            "refcount_before": before,
            "refcount_after": after,
            "cas_deleted": cas_deleted,
            "removed": removed,
            "path_absent": absent,
            "kept": {
                "artifacts": refs["artifacts"],
                "packets": refs["packets"],
                "shares": refs["shares"],
            },
            "time": round(time.time(), 3),
            "result": "deleted" if absent and cas_absent else "incomplete",
            "note": (
                "App-level deletion. SSDs may retain physical blocks until the OS reuses them."
                if refs["managed"]
                else "Imported by path: your original file was left in place; only VibeCut's reference was removed."
            ),
        }
        artifacts.atomic_write_json(job_dir / RECEIPT_NAME, receipt)
        source["deleted_at"] = receipt["time"]
        job["source"] = source
        _save_unlocked(job)
    return {"receipt": receipt}


@app.get("/api/jobs/{job_id}/source/receipt")
def source_deletion_receipt(job_id: str) -> dict:
    load_job(job_id)
    path = _job_dir(job_id) / RECEIPT_NAME
    if not path.is_file():
        raise HTTPException(404, "No deletion receipt for this job.")
    return {"receipt": json.loads(path.read_text(encoding="utf-8"))}


# ------------------------------------------------ publish packet / preflight / tighten


class PacketBody(BaseModel):
    story_id: str = ""
    artifact_ids: list[str] = []
    render_keys: list[str] = []
    titles: list[str] = []
    description: str = ""
    hashtags: list[str] = []
    cover_times: list[float] | None = None
    pin_comment: str = ""


class TightenBody(BaseModel):
    target: int = 30
    hook_scene: int | None = None
    clips: list[dict] | None = None
    plan: dict | None = None
    order: str = "source"
    options: dict | None = None
    silences: list[dict] | None = None
    detect_silence: bool = False


def _packet_http_error(exc: packet.PacketError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=exc.as_detail())


def _record_packet_refs(job_id: str, manifest: dict) -> None:
    """Persist the artifact ids a built packet references in its job.

    ``job.json`` is the fast path for delete/clean protection. The packet
    manifest on disk remains authoritative; this reference table only makes
    the job state self-describing and lets cleanup see old packets too.
    """
    packet_id = str(manifest.get("packet_id") or "")
    if not packet.PACKET_ID_RE.fullmatch(packet_id):
        return
    artifact_ids: set[str] = set()
    render_keys: set[str] = set()
    for item in manifest.get("media") or []:
        if not isinstance(item, dict):
            continue
        artifact = str(item.get("artifact_id") or "")
        if artifacts.is_safe_artifact_id(artifact):
            artifact_ids.add(artifact)
        render_key = str(item.get("render_key") or "")
        if render_key:
            render_keys.add(render_key)
    refs = {
        "packet_id": packet_id,
        "schema": manifest.get("schema"),
        "created": manifest.get("created"),
        "story_id": manifest.get("story_id"),
        "artifact_ids": sorted(artifact_ids),
        "render_keys": sorted(render_keys),
    }

    def mutate(job: dict) -> None:
        table = job.get("packet_refs")
        if not isinstance(table, dict):
            table = {}
        table[packet_id] = refs
        job["packet_refs"] = table
        artifacts.ensure_job_schema(job, _job_dir(job_id))

    update_job(job_id, mutate)


@app.post("/api/jobs/{job_id}/packets")
def build_publish_packet(job_id: str, body: PacketBody) -> dict:
    job = load_job(job_id)
    request = packet.PacketRequest(
        story_id=body.story_id,
        titles=body.titles,
        description=body.description,
        hashtags=body.hashtags,
        artifact_ids=body.artifact_ids,
        render_keys=body.render_keys,
        cover_times=body.cover_times,
        pin_comment=body.pin_comment,
    )
    try:
        manifest = packet.build_packet(job, _job_dir(job_id), request)
    except packet.PacketError as exc:
        raise _packet_http_error(exc) from exc
    _record_packet_refs(job_id, manifest)
    return manifest


@app.get("/api/jobs/{job_id}/packets")
def list_publish_packets(job_id: str) -> dict:
    """Packet history for a job, read from disk so it survives relaunch."""
    load_job(job_id)
    return {"packets": packet.list_packets(_job_dir(job_id))}


@app.get("/api/jobs/{job_id}/packets/{packet_id}")
def get_publish_packet(job_id: str, packet_id: str) -> dict:
    load_job(job_id)
    try:
        return packet.load_packet(_job_dir(job_id), packet_id)
    except packet.PacketError as exc:
        raise _packet_http_error(exc) from exc


@app.get("/api/jobs/{job_id}/packets/{packet_id}/zip")
def get_publish_packet_zip(job_id: str, packet_id: str) -> FileResponse:
    load_job(job_id)
    try:
        path = packet.packet_zip_path(_job_dir(job_id), packet_id)
    except packet.PacketError as exc:
        raise _packet_http_error(exc) from exc
    return FileResponse(
        path, media_type="application/zip",
        filename=path.name,
        headers={"Cache-Control": "private, max-age=0, must-revalidate"},
    )


@app.get("/api/jobs/{job_id}/preflight")
def run_job_preflight(job_id: str, story_id: str | None = None) -> dict:
    job = load_job(job_id)
    try:
        return preflight.run_preflight(
            job, story_id, _job_dir(job_id),
            settings=settings_store.load_settings(),
        )
    except preflight.PreflightError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.as_detail()) from exc


@app.post("/api/jobs/{job_id}/tighten")
def tighten_job_plan(job_id: str, body: TightenBody) -> dict:
    job = load_job(job_id)
    if body.plan is not None:
        if not isinstance(body.plan.get("clips"), list) or not body.plan.get("clips"):
            raise HTTPException(400, "The supplied plan has no clips.")
        plan = body.plan
    else:
        target = _valid_target(int(body.target))
        try:
            plan = _plan_for_body(
                job, target,
                PlanBody(
                    target=target,
                    hook_scene=body.hook_scene,
                    clips=body.clips,
                    order=body.order,
                ),
            )
        except HTTPException:
            raise
        except (TypeError, ValueError, KeyError) as exc:
            raise HTTPException(
                400,
                {
                    "code": "clip_invalid",
                    "message": f"The plan has invalid numeric clip fields: {exc}",
                },
            ) from exc
    silences = list(body.silences or [])
    if body.detect_silence:
        source_path = (job.get("source") or {}).get("path")
        if source_path:
            silences.extend(tighten.detect_silences(source_path))
    scenes = (job.get("analysis") or {}).get("scenes") or []
    try:
        value = tighten.tighten_plan(
            plan, scenes, options=body.options, silences=silences,
        )
    except tighten.TightenError as exc:
        raise HTTPException(
            status_code=exc.status, detail=exc.as_detail(),
        ) from exc
    return {"plan": value}


if __name__ == "__main__":
    LOGGER.info("VibeCut on http://%s:%s", HOST, PORT)
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
