"""VibeCut — local, self-hosted long-video to reel cutter."""

from __future__ import annotations

import hashlib
import html as html_lib
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import audio
import exports as cuts
import history_store
import pipeline
import render
import settings_store
import usage_store
import vision

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DATA = Path(os.environ.get("VIBECUT_DATA", ROOT / "data")).expanduser().resolve()
JOBS = DATA / "jobs"
HOST = os.environ.get("VIBECUT_HOST", "127.0.0.1")
PORT = int(os.environ.get("VIBECUT_PORT", "8787"))
MAX_UPLOAD = int(float(os.environ.get("VIBECUT_MAX_UPLOAD_GB", "20")) * 1024 ** 3)
ACTIVE = {"scanning", "reading", "scoring"}
LIVE = ACTIVE | {"queued"}
LOCK = threading.RLock()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
LOGGER = logging.getLogger("vibecut")
JOBS.mkdir(parents=True, exist_ok=True)
SOURCES = DATA / "sources"

analysis_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vibecut-analyze")
render_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vibecut-render")
RENDER_CANCELS: dict[tuple[str, str], threading.Event] = {}
ACTIVE_RENDER = {"queued", "rendering", "cancelling"}


def _fnv1a(text: str) -> str:
    return audio.fnv1a(text)


def _canonical(value) -> str:
    return audio.canonical_json(value)


def _audio_signature(audio_plan: dict | None) -> str:
    return audio.signature(audio_plan)


def _render_key(
    target: int,
    quality: str = "final",
    aspect: str = "9:16",
    captions: bool = False,
    audio_sig: str = "",
    hook_marker: int | None = None,
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
        days = float(os.environ.get("VIBECUT_SOURCES_GC_DAYS", "30") or 0)
    except ValueError:
        days = 30.0
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
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(500, "Job data is unreadable.") from exc


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
    return {
        "ocr": bool(raw.get("ocr", True)),
        "transcribe": bool(raw.get("transcribe", False)),
        "smart_crop": bool(raw.get("smart_crop", True)),
        "crop_tracking": bool(raw.get("crop_tracking", True)),
        "transcribe_engine": str(raw.get("transcribe_engine") or "auto"),
        "speech_language": str(
            raw.get("speech_language")
            or (settings_store.load_settings().get("stt") or {}).get("language")
            or "en"
        ),
    }


def _public_render(job_id: str, record: dict | None) -> dict | None:
    if not record:
        return None
    value = dict(record)
    if record.get("status") == "ready":
        suffix = f"?v={record.get('key', '')}"
        value["url"] = f"/api/jobs/{job_id}/media/{record['path']}{suffix}"
        value["poster_url"] = f"/api/jobs/{job_id}/media/{record['poster']}{suffix}"
    return value


def public_job(job: dict) -> dict:
    value = dict(job)
    value.pop("source", None)
    value.pop("history", None)
    value["renders"] = {
        key: _public_render(job["id"], record)
        for key, record in (job.get("renders") or {}).items()
    }
    value["source"] = {
        key: job.get("source", {}).get(key)
        for key in ("name", "duration", "width", "height", "fps", "has_audio", "size")
    }
    value["usage"] = _usage_summary(job)
    analysis = value.get("analysis")
    if analysis:
        for scene in analysis.get("scenes", []):
            scene["thumb_url"] = f"/api/jobs/{job['id']}/thumb/{scene['id']}"
    return value


def public_status(job: dict) -> dict:
    return {
        "id": job["id"],
        "status": job.get("status"),
        "progress": job.get("progress", 0),
        "message": job.get("message", ""),
        "error": job.get("error"),
        "renders": {
            key: _public_render(job["id"], record)
            for key, record in (job.get("renders") or {}).items()
        },
    }


# ---------------------------------------------------------------- workers


def run_analysis(job_id: str) -> None:
    job = load_job(job_id)
    job["status"] = "scanning"
    job["progress"] = 0.01
    job["message"] = "Warming up"
    job["error"] = None
    save_job(job)

    def progress(stage: str, fraction: float, message: str) -> None:
        job["status"] = stage if stage in ACTIVE else "scoring"
        job["progress"] = round(max(0.01, min(0.995, fraction)), 4)
        job["message"] = message
        save_job(job)

    try:
        before_usage = usage_store.snapshot()
        analysis = pipeline.analyze_source(
            job["source"]["path"],
            job["source"],
            _job_dir(job_id),
            job.get("options") or {},
            progress,
        )
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
        job["message"] = f"{analysis['scene_count']} moments · hook found"
        job["error"] = None
        save_job(job)
        LOGGER.info("job %s ready in %.1fs", job_id, analysis["elapsed"])
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("analysis failed for %s", job_id)
        job["status"] = "failed"
        job["progress"] = 1.0
        job["message"] = "Analysis failed"
        job["error"] = str(exc)[:2400]
        save_job(job)


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


def _load_shares() -> dict:
    if not SHARES.is_file():
        return {}
    try:
        value = json.loads(SHARES.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _save_shares(value: dict) -> None:
    SHARES.parent.mkdir(parents=True, exist_ok=True)
    SHARES.write_text(json.dumps(value, indent=1), encoding="utf-8")
    try:
        SHARES.chmod(0o600)
    except OSError:
        pass


def _find_share_render(job: dict, target: int, aspect: str) -> dict | None:
    rows = []
    for record in (job.get("renders") or {}).values():
        if record.get("status") != "ready" or not record.get("path"):
            continue
        if f"reel_{int(target)}" not in str(record["path"]):
            continue
        path = str(record["path"])
        if aspect == "9:16" and any(token in path for token in ("_16x9", "_1x1", "_4x5")):
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
        if aspect == "9:16" and any(token in name for token in ("_16x9", "_1x1", "_4x5")):
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


def _share(token: str) -> tuple[dict, dict, dict] | None:
    record = _load_shares().get(token)
    if not record:
        return None
    try:
        job = load_job(record["job_id"])
    except HTTPException:
        return None
    render_record = _find_share_render(job, int(record["target"]), record.get("aspect") or "9:16")
    if not render_record:
        return None
    return record, job, render_record


def _share_captions(job: dict, target: int) -> str:
    plan = _plan_for(job, target, None)
    scenes = job["analysis"]["scenes"]
    clips = plan.get("clips") or []
    cues = cuts.plan_cues(plan, clips, scenes)
    return cuts.srt(cues)


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
) -> None:
    plan["_source_lang"] = plan.get("_source_lang") or "en"
    record_key = _render_key(
        target, quality, aspect, captions, audio_sig, _hook_marker(plan),
    )
    cancel_event = RENDER_CANCELS.setdefault((job_id, record_key), threading.Event())
    started = time.time()
    try:
        job = load_job(job_id)
        history_id = str(
            ((job.get("renders") or {}).get(record_key) or {}).get("history_id") or ""
        ) or None
        scenes = job["analysis"]["scenes"]
        plan["_scenes"] = scenes
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
        )
        render_delta = usage_store.delta(before_usage)
        _append_usage(job_id, "render", render_delta)
        _set_render(
            job_id, record_key,
            status="ready", progress=1.0, message="Reel ready",
            error=None, key=key, hook=plan["hook_scene"],
            total=plan["total"], eta=0, audio_sig=audio_sig,
            preset=preset, caption_margin=caption_margin,
            usage=render_delta,
            **result,
        )
        ready_record = {
            "status": "ready",
            "progress": 1.0,
            "message": "Reel ready",
            "error": None,
            "key": key,
            "hook": plan["hook_scene"],
            "total": plan["total"],
            "eta": 0,
            "audio_sig": audio_sig,
            "preset": preset,
            "caption_margin": caption_margin,
            "usage": render_delta,
            "target": target,
            "quality": quality,
            "aspect": aspect,
            "encoder": encoder or "auto",
            "captions": bool(captions),
            "record_key": record_key,
            "created": round(time.time(), 3),
            "script_id": script_id,
            **result,
        }
        _record_render_history(
            job_id, ready_record, plan, audio_plan, "ready",
            script_id=script_id,
            latency_ms=round((time.time() - started) * 1000),
            entry_id=history_id,
        )
        LOGGER.info("render %s/%s ready in %s", job_id, record_key, result["path"])
        pruned: list[str] = []
        update_job(job_id, lambda value: pruned.extend(_prune_renders(value)))
        if pruned:
            LOGGER.info("pruned %d old render file(s) for %s", len(pruned), job_id)
    except render.RenderCancelled:
        LOGGER.info("render %s/%s cancelled", job_id, record_key)
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


def recover_jobs() -> None:
    RENDER_CANCELS.clear()
    fixed = 0
    for path in JOBS.glob("*/job.json"):
        try:
            with LOCK:
                job = json.loads(path.read_text())
                changed = False
                if job.get("status") in LIVE:
                    job["status"] = "failed"
                    job["message"] = "Interrupted"
                    job["error"] = "The server restarted while this job was running."
                    changed = True
                for record in (job.get("renders") or {}).values():
                    if record.get("status") in ACTIVE_RENDER:
                        record["status"] = "failed"
                        record["message"] = "Interrupted"
                        record["error"] = "The server restarted while this reel was rendering."
                        changed = True
                        _record_render_history(
                            job["id"], record,
                            {"target": record.get("target"), "clips": []},
                            record.get("audio"), "failed",
                            script_id=record.get("script_id"),
                            error=record["error"],
                            latency_ms=0,
                            entry_id=record.get("history_id"),
                        )
                if changed:
                    _save_unlocked(job)
                    fixed += 1
        except Exception:
            continue
    for tmp in JOBS.glob("*/renders/tmp_*"):
        shutil.rmtree(tmp, ignore_errors=True)
    if fixed:
        LOGGER.info("recovered %d interrupted job(s)", fixed)


def _prune_renders(job: dict) -> list[str]:
    """Keep the newest final per config (+ drafts only when asked)."""
    renders = job.get("renders") or {}
    try:
        keep_finals = max(1, int(os.environ.get("VIBECUT_KEEP_RENDERS", "1") or 1))
    except ValueError:
        keep_finals = 1
    keep_drafts = (os.environ.get("VIBECUT_KEEP_DRAFTS", "0") or "0").lower() not in (
        "0", "false", "no", "off", "",
    )
    groups: dict[tuple, list[tuple[float, str]]] = {}
    for key, record in renders.items():
        if not record or record.get("status") != "ready":
            continue
        group = (
            record.get("target"),
            record.get("aspect", "9:16"),
            bool(record.get("captions")),
            record.get("audio_sig", ""),
        )
        groups.setdefault(group, []).append((float(record.get("updated") or 0), key))

    doomed: list[str] = []
    for entries in groups.values():
        finals = sorted(
            (item for item in entries if (renders[item[1]].get("quality") or "final") == "final"),
            reverse=True,
        )
        drafts = sorted(
            (item for item in entries if (renders[item[1]].get("quality") or "final") == "draft"),
            reverse=True,
        )
        doomed.extend(key for _updated, key in finals[keep_finals:])
        if keep_drafts:
            doomed.extend(key for _updated, key in drafts[1:])
        elif finals:
            # Draft preview is only redundant once a final exists for the same mix.
            doomed.extend(key for _updated, key in drafts)
    if not doomed:
        return []
    directory = _job_dir(job["id"]) / "renders"
    removed: list[str] = []
    for key in doomed:
        record = renders.pop(key, None) or {}
        for name in (record.get("path"), record.get("poster")):
            if not name:
                continue
            try:
                (directory / name).unlink()
                removed.append(name)
            except OSError:
                continue
    return removed


def clean_job_files(job: dict, profile: str = "workfiles") -> list[str]:
    """Delete working files for one job. Source video and job.json stay."""
    directory = _job_dir(job["id"])
    removed: list[str] = []
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
    if profile in {"renders", "all"}:
        target = directory / "renders"
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
            removed.append("renders")
        masters = DATA / "cache" / "masters" / job["id"]
        if masters.exists():
            shutil.rmtree(masters, ignore_errors=True)
            removed.append("masters")
        job["renders"] = {}
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
    if days > 0:
        cutoff = time.time() - days * 86400
        for path in JOBS.glob("*/job.json"):
            try:
                job = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if job.get("status") in LIVE:
                continue
            if float(job.get("updated", 0) or 0) < cutoff:
                shutil.rmtree(path.parent, ignore_errors=True)
                LOGGER.info("retention removed job %s", job.get("id"))
    if clean_days > 0:
        cutoff = time.time() - clean_days * 86400
        for path in JOBS.glob("*/job.json"):
            try:
                job = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if job.get("status") in LIVE:
                continue
            if float(job.get("updated", 0) or 0) >= cutoff:
                continue
            removed = clean_job_files(job, "workfiles")
            if removed:
                save_job(job)
                LOGGER.info("cleaned %s for job %s", ", ".join(removed), job.get("id"))
    for path in JOBS.glob("*/job.json"):
        try:
            job = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if job.get("status") in LIVE or not job.get("renders"):
            continue
        removed = _prune_renders(job)
        if removed:
            with LOCK:
                _save_unlocked(job)
            LOGGER.info("render retention removed %d file(s) for %s", len(removed), job.get("id"))
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
    recover_jobs()
    cleanup_storage()
    threading.Thread(target=_retention_loop, daemon=True).start()
    threading.Thread(target=vision.available, daemon=True).start()
    yield


app = FastAPI(title="VibeCut", lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


# ---------------------------------------------------------------- auth


PUBLIC_PATHS = {"/", "/index.html", "/favicon.ico", "/api/health"}
SHARES = DATA / "shares.json"


@app.middleware("http")
async def require_token(request: Request, call_next):
    token = os.environ.get("VIBECUT_TOKEN")
    if not token:
        return await call_next(request)
    path = request.url.path
    if path in PUBLIC_PATHS or path.startswith("/static") or path.startswith("/r/"):
        return await call_next(request)
    supplied = request.headers.get("authorization") or ""
    if supplied.lower().startswith("bearer "):
        supplied = supplied[7:]
    supplied = (
        supplied.strip()
        or request.query_params.get("token")
        or request.cookies.get("vibecut_token")
        or ""
    )
    if supplied != token:
        return JSONResponse(
            {"detail": "Unauthorized. Provide VIBECUT_TOKEN."},
            status_code=401,
        )
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


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


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


OPENCODE_MODEL = "deepseek-v4.1-flash"
OPENCODE_VARIANT = "low"
STT_PROVIDERS = {"auto", "apple", "whisper"}
TTS_PROVIDERS = {"auto", "local", "say", "piper", "kokoro", "openai", "elevenlabs", "groq", "deepgram", "cartesia", "minimax", "fish", "gemini"}


class SettingsTestBody(BaseModel):
    kind: str = "opencode"
    engine: str = ""
    voice: str = ""
    provider: str = ""


def _settings_state() -> dict:
    state = settings_store.public_state()
    state["runtime"] = {
        "opencode": audio.opencode_available(),
        "opencode_binary": audio.opencode_bin() or "",
        "opencode_model": audio.opencode_model(),
        "opencode_variant": audio.opencode_variant(),
        "opencode_mode": audio.opencode_mode(),
        "openrouter": audio.openrouter_status(),
        "whisper_models": pipeline.whisper_models(),
    }
    return state


@app.get("/api/settings")
def get_settings() -> dict:
    return _settings_state()


@app.post("/api/settings")
async def save_settings(request: Request) -> dict:
    body = await request.json()
    patch = body.get("settings") if isinstance(body, dict) else None
    secrets = body.get("secrets") if isinstance(body, dict) else None
    if isinstance(patch, dict):
        opencode = patch.get("opencode")
        if isinstance(opencode, dict):
            requested = str(opencode.get("model") or OPENCODE_MODEL)
            if requested != OPENCODE_MODEL:
                raise HTTPException(400, f"Only {OPENCODE_MODEL} is supported.")
            requested_variant = str(opencode.get("variant") or OPENCODE_VARIANT)
            if requested_variant != OPENCODE_VARIANT:
                raise HTTPException(400, "OpenCode reasoning is locked to low.")
            opencode["model"] = OPENCODE_MODEL
            opencode["variant"] = OPENCODE_VARIANT
        stt = patch.get("stt")
        if isinstance(stt, dict) and stt.get("provider") not in (None, "") and stt["provider"] not in STT_PROVIDERS:
            raise HTTPException(400, "Unknown transcription provider.")
        if isinstance(stt, dict) and stt.get("model") not in (None, "") and stt["model"] not in {
            item["id"] for item in pipeline.WHISPER_MODELS
        }:
            raise HTTPException(400, "Unknown Whisper model.")
        translation = patch.get("translation")
        if isinstance(translation, dict) and translation.get("mode") not in (None, "", "auto", "local_first", "local_only", "online_only"):
            raise HTTPException(400, "Unknown translation mode.")
        tts = patch.get("tts")
        if isinstance(tts, dict) and tts.get("provider") not in (None, "") and tts["provider"] not in TTS_PROVIDERS:
            raise HTTPException(400, "Unknown voice provider.")
        settings_store.save_settings(patch)
    if isinstance(secrets, dict):
        settings_store.save_secrets(secrets)
        if "openrouter" in secrets:
            audio.clear_openrouter_quarantine()
            audio.reset_provider_breaker("openrouter")
            audio.OPENROUTER_LAST_ERROR = ""
            audio.OPENROUTER_LAST_STATUS = 0
    return _settings_state()


@app.post("/api/settings/test")
def test_settings(body: SettingsTestBody) -> dict:
    kind = (body.kind or "opencode").lower()
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
            "variant": OPENCODE_VARIANT,
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
            name for name in ("minimax", "fish", "gemini", "kokoro", "piper", "say")
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
        for candidate in ("say", "kokoro", "piper"):
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
            "minimax", "fish", "gemini", "kokoro", "say", "piper",
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


@app.get("/api/settings/tts-test/{engine}.wav")
def settings_tts_test(engine: str) -> FileResponse:
    safe = "".join(ch for ch in engine if ch.isalnum() or ch in "-_")
    path = DATA / "cache" / "voice-test" / f"{safe}.wav"
    if not path.is_file():
        raise HTTPException(404, "No voice test yet.")
    return FileResponse(path, media_type="audio/wav", filename=f"vibecut-{safe}-test.wav")


@app.post("/api/jobs/{job_id}/share")
def create_share(job_id: str, target: int = 30, aspect: str = "9:16") -> dict:
    job = load_job(job_id)
    target = _valid_target(int(target))
    aspect = aspect if aspect in render.ASPECTS else "9:16"
    record = _find_share_render(job, target, aspect)
    if not record:
        raise HTTPException(409, "Render this cut first, then create the review link.")
    token = uuid.uuid4().hex + uuid.uuid4().hex[:12]
    shares = _load_shares()
    shares[token] = {
        "job_id": job_id,
        "target": target,
        "aspect": aspect,
        "created": round(time.time(), 3),
    }
    _save_shares(shares)
    return {"token": token, "url": f"/r/{token}", "target": target, "aspect": aspect}


@app.get("/r/{token}")
def review_page(token: str) -> Response:
    found = _share(token)
    if not found:
        raise HTTPException(404, "Review link not found.")
    record, job, render_record = found
    title = html_lib.escape(Path(job["source"]["name"]).stem)
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
</style></head><body><main>
<h1>{title}</h1><p>{record['target']}s · {record['aspect']} · review only</p>
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
    try:
        content = _share_captions(job, int(record["target"]))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Captions unavailable: {exc}") from exc
    return Response(
        content=content, media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="captions.srt"'},
    )


class PathBody(BaseModel):
    path: str
    options: dict = {}


class InspectBody(BaseModel):
    path: str


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


class VariantBody(BaseModel):
    name: str = ""
    target: int = 30
    hook_scene: int | None = None
    clips: list[dict]


@app.post("/api/inspect")
def inspect(body: InspectBody) -> dict:
    path = Path(body.path).expanduser()
    if not path.is_file():
        raise HTTPException(404, "File not found on this machine.")
    try:
        meta = pipeline.probe(path)
    except pipeline.PipelineError as exc:
        raise HTTPException(400, str(exc)) from exc
    meta.pop("path", None)
    return meta


def _new_job(
    source_path: Path,
    name: str,
    meta: dict,
    options: dict,
    job_id: str | None = None,
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
    }
    save_job(job)
    analysis_pool.submit(run_analysis, job_id)
    return job


@app.post("/api/jobs/upload")
async def upload_job(
    file: UploadFile = File(...),
    options: str = Form("{}"),
) -> dict:
    try:
        parsed_options = clean_options(json.loads(options))
    except json.JSONDecodeError:
        parsed_options = clean_options({})

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
                output.write(chunk)
        stored = store_source(temp, suffix, original)
        destination = link_source(stored, directory, suffix)
        meta = pipeline.probe(destination)
        job = _new_job(destination, original, meta, parsed_options, job_id=job_id)
        return {"id": job["id"], "status": job["status"]}
    except HTTPException:
        temp.unlink(missing_ok=True)
        shutil.rmtree(directory, ignore_errors=True)
        raise
    except Exception as exc:
        temp.unlink(missing_ok=True)
        shutil.rmtree(directory, ignore_errors=True)
        raise HTTPException(400, f"Could not ingest this video: {exc}") from exc
    finally:
        await file.close()


@app.post("/api/jobs/path")
def job_from_path(body: PathBody) -> dict:
    path = Path(body.path).expanduser()
    if not path.is_file():
        raise HTTPException(404, "File not found on this machine.")
    try:
        meta = pipeline.probe(path)
    except pipeline.PipelineError as exc:
        raise HTTPException(400, str(exc)) from exc
    job = _new_job(path.resolve(), path.name, meta, clean_options(body.options))
    return {"id": job["id"], "status": job["status"]}


@app.get("/api/jobs")
def list_jobs() -> dict:
    items = []
    paths = sorted(JOBS.glob("*/job.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:24]
    for path in paths:
        try:
            job = json.loads(path.read_text())
        except Exception:
            continue
        analysis = job.get("analysis") or {}
        scenes = analysis.get("scenes") or []
        hook_id = analysis.get("hook_scene")
        hook_thumb = None
        if hook_id is not None:
            hook_thumb = f"/api/jobs/{job['id']}/thumb/{hook_id}"
        items.append({
            "id": job.get("id"),
            "created": job.get("created"),
            "name": (job.get("source") or {}).get("name"),
            "duration": (job.get("source") or {}).get("duration"),
            "status": job.get("status"),
            "progress": job.get("progress", 0),
            "message": job.get("message"),
            "scene_count": analysis.get("scene_count"),
            "hook_thumb": hook_thumb,
        })
    return {"jobs": items}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    return public_job(load_job(job_id))


@app.get("/api/jobs/{job_id}/usage")
def get_usage(job_id: str) -> dict:
    return _usage_summary(load_job(job_id))


@app.get("/api/jobs/{job_id}/status")
def get_status(job_id: str) -> dict:
    return public_status(load_job(job_id))


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
            "why": str(raw.get("why") or "")[:240],
        })
    if not built:
        raise HTTPException(400, "The cut is empty.")
    total = round(sum(clip["dur"] for clip in built), 3)
    hook_clip = next((clip for clip in built if clip["role"] == "hook"), built[0])
    payoff_clip = next((clip for clip in built if clip["role"] == "payoff"), None)
    return {
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
    return value


def _plan_for_body(job: dict, target: int, body: PlanBody) -> dict:
    if body.clips is not None:
        return _apply_order(job, _custom_plan(job, target, body.hook_scene, body.clips), body.order)
    return _apply_order(job, _plan_for(job, target, body.hook_scene), body.order)


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


def _install_argos_safe(source: str = "", target: str = "") -> None:
    try:
        audio.install_argos()
        if source and target and source.split("-")[0] != target.split("-")[0]:
            audio.ensure_argos_pair(source, target)
    except Exception:  # noqa: BLE001
        LOGGER.exception("argos install failed")


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
def audio_music(source: str = "cc0") -> dict:
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
    if suffix not in {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".aiff", ".aif"}:
        error = "Upload a WAV, MP3, M4A, FLAC, OGG or AIFF file."
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
    if suffix not in {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".aiff", ".aif"}:
        error = "Upload a WAV, MP3, M4A, FLAC, OGG or AIFF file."
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
def audio_beats(source: str = "cc0", track: str = "") -> dict:
    path = audio.resolve_music_track([], [], {"source": source, "track": track})
    if not path:
        raise HTTPException(404, "No track found for beat detection.")
    grid = audio.beat_grid(path)
    if not grid:
        raise HTTPException(400, "Beat detection unavailable (librosa missing or unreadable audio).")
    return {"track": path.name, "bpm": grid["bpm"], "beats": len(grid["beats"])}


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
            record = _queue_render(
                job_id, fresh, plan, quality, aspect, encoder, captions,
                audio_plan, bool(body.force), preset=preset, caption_margin=margin,
                script_id=script_id,
            )
            renders.append(_public_render(job_id, record))
        except HTTPException as exc:
            errors.append({"hook": scene["id"], "detail": str(exc.detail)})
    return {"renders": renders, "errors": errors}


@app.get("/api/jobs/{job_id}/export/{kind}")
def export_cut(
    job_id: str,
    kind: str,
    target: int = 30,
    hook_scene: int | None = None,
    order: str = "source",
) -> Response:
    if kind not in {"srt", "vtt", "edl", "xml"}:
        raise HTTPException(404, "Unknown export format.")
    job = load_job(job_id)
    plan = _apply_order(job, _plan_for(job, _valid_target(int(target)), hook_scene), order)
    scenes = job["analysis"]["scenes"]
    clips = plan["clips"]
    stem = Path(job["source"]["name"]).stem
    if kind in {"srt", "vtt"}:
        cues = cuts.plan_cues(plan, clips, scenes)
        content = cuts.srt(cues) if kind == "srt" else cuts.vtt(cues)
        media = "text/plain; charset=utf-8"
    elif kind == "edl":
        content = cuts.edl(plan, clips, job["source"]["name"])
        media = "text/plain; charset=utf-8"
    else:
        content = cuts.fcp7_xml(plan, clips, job["source"]["path"])
        media = "application/xml"
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
) -> dict:
    script_id = _valid_script_id(job_id, plan, script_id)
    target = int(plan["target"])
    audio_sig = _audio_signature(audio_plan)
    record_key = _render_key(
        target, quality, aspect, captions, audio_sig, _hook_marker(plan),
    )
    key = hashlib.sha1(json.dumps({
        "target": target,
        "clips": plan["clips"],
        "quality": quality,
        "aspect": aspect,
        "encoder": encoder or "auto",
        "captions": captions,
        "audio": audio_plan or None,
        "nonce": time.time() if force else None,
    }, sort_keys=True).encode()).hexdigest()[:12]

    existing = (job.get("renders") or {}).get(record_key)
    if existing and existing.get("key") == key and existing.get("status") in ACTIVE_RENDER | {"ready"}:
        return existing
    if existing and existing.get("status") in ACTIVE_RENDER:
        raise HTTPException(409, "That reel is already rendering.")

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
        "encoder": encoder or "auto",
        "captions": captions,
        "preset": preset,
        "caption_margin": caption_margin,
        "order": plan.get("order") or "source",
        "created": round(time.time(), 3),
        "script_id": script_id,
    }

    def mutate(value: dict) -> None:
        value.setdefault("renders", {})[record_key] = record

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
        audio_plan, audio_sig, preset, caption_margin, script_id,
    )
    return record


def _render_options(
    body: PlanBody,
) -> tuple[str, str, str | None, bool, dict | None, str | None, float]:
    quality = body.quality if body.quality in ("final", "draft") else "final"
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


@app.post("/api/jobs/{job_id}/render")
def start_render(job_id: str, body: PlanBody) -> dict:
    job = load_job(job_id)
    target = _valid_target(int(body.target))
    quality, aspect, encoder, captions, audio_plan, preset, margin = _render_options(body)
    plan = _plan_for_body(job, target, body)
    record = _queue_render(
        job_id, job, plan, quality, aspect, encoder, captions, audio_plan,
        bool(body.force), preset=preset, caption_margin=margin,
        script_id=_body_script_id(body, audio_plan),
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
            record = _queue_render(
                job_id, job, plan, quality, aspect, encoder, captions, audio_plan,
                bool(body.force), preset=preset, caption_margin=margin,
                script_id=script_id,
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
) -> dict:
    target = _valid_target(int(target))
    quality = quality if quality in ("final", "draft") else "final"
    aspect = aspect if aspect in render.ASPECTS else "9:16"
    if not record_key:
        record_key = _render_key(
            target, quality, aspect, captions, audio_sig,
            int(hook_marker) if hook_marker is not None else None,
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
    job = load_job(job_id)
    if job.get("status") in LIVE or any(
        record.get("status") in ACTIVE_RENDER
        for record in (job.get("renders") or {}).values()
    ):
        raise HTTPException(409, "This job is still working.")
    profile = body.profile if body.profile in {"workfiles", "renders", "all"} else "workfiles"
    removed = clean_job_files(job, profile)
    save_job(job)
    LOGGER.info("cleaned %s for job %s", ", ".join(removed) or "nothing", job_id)
    return {"cleaned": removed, "profile": profile}


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str) -> dict:
    job = load_job(job_id)
    if job.get("status") in LIVE or any(
        record.get("status") in ACTIVE_RENDER
        for record in (job.get("renders") or {}).values()
    ):
        raise HTTPException(409, "This job is still working.")
    shutil.rmtree(_job_dir(job_id), ignore_errors=True)
    return {"deleted": job_id}


if __name__ == "__main__":
    LOGGER.info("VibeCut on http://%s:%s", HOST, PORT)
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
