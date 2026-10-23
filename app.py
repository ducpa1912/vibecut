"""VibeCut — local, self-hosted long-video to reel cutter."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import audio
import pipeline
import render
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
    return key


# ---------------------------------------------------------------- store


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
    value["renders"] = {
        key: _public_render(job["id"], record)
        for key, record in (job.get("renders") or {}).items()
    }
    value["source"] = {
        key: job.get("source", {}).get(key)
        for key in ("name", "duration", "width", "height", "fps", "has_audio", "size")
    }
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
        analysis = pipeline.analyze_source(
            job["source"]["path"],
            job["source"],
            _job_dir(job_id),
            job.get("options") or {},
            progress,
        )
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
) -> None:
    plan["_source_lang"] = plan.get("_source_lang") or "en"
    record_key = _render_key(target, quality, aspect, captions, audio_sig)
    cancel_event = RENDER_CANCELS.setdefault((job_id, record_key), threading.Event())
    started = time.time()
    try:
        job = load_job(job_id)
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
        result = render.render_reel(
            source, meta, _job_dir(job_id), plan, title, progress,
            quality=quality, aspect=aspect, encoder=encoder,
            captions=captions, audio_plan=audio_plan, audio_sig=audio_sig,
            cancel_event=cancel_event,
        )
        _set_render(
            job_id, record_key,
            status="ready", progress=1.0, message="Reel ready",
            error=None, key=key, hook=plan["hook_scene"],
            total=plan["total"], eta=0, audio_sig=audio_sig,
            **result,
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
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("render failed for %s/%s", job_id, record_key)
        _set_render(
            job_id, record_key, status="failed", progress=1.0,
            message="Render failed", error=str(exc)[:2400], eta=None,
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


@app.middleware("http")
async def require_token(request: Request, call_next):
    token = os.environ.get("VIBECUT_TOKEN")
    if not token:
        return await call_next(request)
    path = request.url.path
    if path in PUBLIC_PATHS or path.startswith("/static"):
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
        "whisper": bool(shutil.which("mlx_whisper")),
        "data": str(DATA),
        "encoder": render._choose_encoder(),
        "version": 2,
    }


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
    destination = directory / f"source{suffix}"
    total = 0
    try:
        with destination.open("wb") as output:
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
        meta = pipeline.probe(destination)
        job = _new_job(destination, original, meta, parsed_options, job_id=job_id)
        return {"id": job["id"], "status": job["status"]}
    except HTTPException:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    except Exception as exc:
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


@app.get("/api/jobs/{job_id}/status")
def get_status(job_id: str) -> dict:
    return public_status(load_job(job_id))


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
            scene["crop"] = {"cx": 0.5, "cy": 0.5}
            scene["crop_mode"] = "center"
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


def _plan_for_body(job: dict, target: int, body: PlanBody) -> dict:
    if body.clips is not None:
        return _custom_plan(job, target, body.hook_scene, body.clips)
    return _plan_for(job, target, body.hook_scene)


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


@app.get("/api/jobs/{job_id}/hooks")
def hook_candidates(job_id: str, target: int = 30, limit: int = 8) -> dict:
    job = load_job(job_id)
    analysis = job.get("analysis")
    if job.get("status") != "ready" or not analysis:
        raise HTTPException(409, "Analysis is not ready yet.")
    target = _valid_target(int(target))
    limit = max(1, min(int(limit), 24))
    scenes = [
        scene for scene in analysis["scenes"]
        if scene.get("deep", True) and not scene.get("black") and scene["dur"] >= 0.55
    ]
    scenes.sort(key=lambda scene: (scene["hook"], -scene["start"]), reverse=True)
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
        "install": audio.ARGOS_STATE,
        "providers": audio.translate_providers(),
        "check": audio.translate_check(source, target) if source and target else None,
    }


@app.post("/api/audio/translate/install")
def translate_install(body: TranslateInstallBody | None = None) -> dict:
    source = (body.source if body else None) or ""
    target = (body.target if body else None) or ""
    if not audio.ARGOS_STATE.get("running"):
        threading.Thread(
            target=_install_argos_safe, args=(source, target), daemon=True,
        ).start()
    return {"install": audio.ARGOS_STATE}


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


@app.post("/api/jobs/{job_id}/audio/script")
def audio_script(job_id: str, body: ScriptBody) -> dict:
    """List the cleaned, de-duplicated, time-fitted voice script for a cut."""
    job = load_job(job_id)
    target = _valid_target(int(body.target))
    if body.clips:
        plan = _custom_plan(job, target, body.hook_scene, body.clips)
    else:
        plan = _plan_for(job, target, body.hook_scene)
    scenes = job["analysis"]["scenes"]
    clips = [
        {"scene": clip["scene"], "duration": round(float(clip["dur"]), 3)}
        for clip in plan["clips"]
    ]
    script = audio.build_script(scenes, clips)
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
    warning = None
    translated = False
    if target_lang and target_lang != source_lang and script:
        try:
            texts = audio.translate_lines(
                [line["text"] for line in script],
                source_lang, target_lang, body.provider,
            )
            for line, text in zip(script, texts):
                line["text"] = text
            script = audio.refit_script(script)
            translated = True
        except audio.AudioError as exc:
            warning = str(exc)[:400]
    return {
        "lines": script,
        "source_lang": source_lang,
        "target": target_lang or source_lang,
        "translated": translated,
        "warning": warning,
        "moods": audio.scene_moods(scenes, clips),
        "total": round(sum(float(clip["duration"]) for clip in clips), 3),
    }


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
) -> dict:
    target = int(plan["target"])
    audio_sig = _audio_signature(audio_plan)
    record_key = _render_key(target, quality, aspect, captions, audio_sig)
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
        "created": round(time.time(), 3),
    }

    def mutate(value: dict) -> None:
        value.setdefault("renders", {})[record_key] = record

    update_job(job_id, mutate)
    render_pool.submit(
        run_render, job_id, target, plan, key, quality, aspect, encoder, captions,
        audio_plan, audio_sig,
    )
    return record


def _render_options(body: PlanBody) -> tuple[str, str, str | None, bool, dict | None]:
    quality = body.quality if body.quality in ("final", "draft") else "final"
    aspect = body.aspect if body.aspect in render.ASPECTS else "9:16"
    audio_plan = body.audio if isinstance(body.audio, dict) else None
    if audio_plan and str(audio_plan.get("mode") or "keep") == "keep":
        audio_plan = None
    return quality, aspect, body.encoder, bool(body.captions), audio_plan


@app.post("/api/jobs/{job_id}/render")
def start_render(job_id: str, body: PlanBody) -> dict:
    job = load_job(job_id)
    target = _valid_target(int(body.target))
    quality, aspect, encoder, captions, audio_plan = _render_options(body)
    plan = _plan_for_body(job, target, body)
    record = _queue_render(
        job_id, job, plan, quality, aspect, encoder, captions, audio_plan, bool(body.force),
    )
    return {"render": _public_render(job_id, record)}


@app.post("/api/jobs/{job_id}/render-all")
def start_render_all(job_id: str, body: PlanBody) -> dict:
    load_job(job_id)
    quality, aspect, encoder, captions, audio_plan = _render_options(body)
    renders: list[dict] = []
    errors: list[dict] = []
    for target in (15, 30, 60):
        job = load_job(job_id)
        try:
            plan = _plan_for(job, target, body.hook_scene)
            record = _queue_render(
                job_id, job, plan, quality, aspect, encoder, captions, audio_plan, bool(body.force),
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
) -> dict:
    target = _valid_target(int(target))
    quality = quality if quality in ("final", "draft") else "final"
    aspect = aspect if aspect in render.ASPECTS else "9:16"
    record_key = _render_key(target, quality, aspect, captions, audio_sig)
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
