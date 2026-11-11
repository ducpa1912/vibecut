"""Minimal DuckSuite core for the Day 1 shell spike.

Run locally:

    DUCK_TOKEN=dev python3 duck_app.py --data-root /tmp/ducksuite --port 8797

The Swift shell starts the same entrypoint with port 0 and a random token on
stdin. Stdout is reserved for the single handshake line:

    {"port": 51234, "pid": 1234}
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from duckcore import append, app_settings, captions, clean, edits, effects, media, packs, preview, render, script, voice
from duckcore.check import CheckManager
from duckcore.store import ProjectStore

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(os.environ.get("DUCK_STATIC_DIR", ROOT / "static" / "duck")).expanduser()
if not STATIC.is_dir():
    # PyInstaller one-folder app: static lives beside the duckcore folder in
    # Contents/Resources, not inside _internal.
    bundled_static = Path(sys.executable).resolve().parent.parent / "static" / "duck"
    if bundled_static.is_dir():
        STATIC = bundled_static
APP_VERSION = "1.0.0"
PROOF_VERSION = 10
MAX_IMPORT_BYTES = 8 * 1024**3


class ProjectCreate(BaseModel):
    name: str = Field(default="", max_length=160)
    source_path: str


class ProjectRename(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class ProjectAppend(BaseModel):
    source_path: str
    mode: str = Field(default="scenes", pattern="^(scenes|full)$")
    cleanup: bool = False


class StoryEditBody(BaseModel):
    story_id: str = ""
    start: float | None = None
    end: float | None = None
    title: str = Field(default="", max_length=120)


class SceneStoryBody(BaseModel):
    scene_ids: list[int] = Field(min_length=1, max_length=500)
    title: str = Field(default="", max_length=120)


class StorySceneBody(BaseModel):
    scene_id: int
    index: int | None = None


class StoryMoveBody(BaseModel):
    index: int
    delta: int = Field(ge=-500, le=500)


class LayerAction(BaseModel):
    action: str = Field(pattern="^(fill|blur|exclude)$")


class SettingsPatch(BaseModel):
    online_enabled: bool | None = None
    online_endpoint: str | None = None
    translation_engine: str | None = None
    translation_model_path: str | None = None


class CuePatch(BaseModel):
    text: str = Field(max_length=240)


class CaptionsPatch(BaseModel):
    burn: bool | None = None
    style: str | None = None
    position: str | None = None


class ClipPatch(BaseModel):
    start: float | None = None
    end: float | None = None


class SplitClipBody(BaseModel):
    time: float = Field(ge=0.0)


class SlipClipBody(BaseModel):
    delta: float = Field(ge=-30.0, le=30.0)


class AudioTrackPatch(BaseModel):
    start: float | None = Field(default=None, ge=0.0)
    duration: float | None = Field(default=None, ge=0.2)
    offset: float | None = Field(default=None, ge=0.0)
    volume: float | None = Field(default=None, ge=0.0, le=1.5)
    muted: bool | None = None
    solo: bool | None = None
    fade_in: float | None = Field(default=None, ge=0.0)
    fade_out: float | None = Field(default=None, ge=0.0)
    name: str | None = Field(default=None, max_length=120)


class VoicePatch(BaseModel):
    voice: str = Field(min_length=1, max_length=80)
    mode: str = Field(default="voice_over", pattern="^(voice_over|voice_only)$")


class ScriptTranslate(BaseModel):
    target: str = Field(default="vi", pattern="^(en|vi|zh)$")
    source: str = Field(default="en", pattern="^(en|vi|zh)$")


class ScriptRewrite(BaseModel):
    mode: str = Field(default="clean", pattern="^(clean|short|punchy)$")


class VoicePreviewBody(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    voice: str = Field(min_length=1, max_length=80)


class VoiceRecordBody(BaseModel):
    path: str = Field(min_length=1, max_length=4096)


class DubBody(BaseModel):
    voice: str = Field(min_length=1, max_length=80)
    language: str = Field(default="", max_length=20)


class SfxTextBody(BaseModel):
    text: str = Field(min_length=1, max_length=240)
    start: float = 0.0
    end: float = 3.0
    style: str = Field(default="headline", pattern="^(headline|caption|badge)$")
    color: str = Field(default="#ffffff", max_length=9)
    x: float = 0.5
    y: float = 0.84


class SfxFilterBody(BaseModel):
    preset: str = Field(default="warm", pattern="^(warm|cool|bw|vivid)$")
    start: float = 0.0
    end: float | None = None


class BrushPoint(BaseModel):
    x: float
    y: float


class BrushStroke(BaseModel):
    r: float = 0.02
    points: list[BrushPoint]


class ManualLayerBody(BaseModel):
    kind: str = Field(default="fill", pattern="^(fill|blur)$")
    start: float
    end: float
    strokes: list[BrushStroke]


class DevImport(BaseModel):
    source_path: str
    name: str = Field(default="", max_length=160)


class RevealBody(BaseModel):
    path: str = Field(min_length=1, max_length=4096)


def _active_clean(edit: dict, when: float) -> list[dict]:
    """Clean layers that can touch this frame, for a stable proof cache key."""
    active = []
    for layer in edit.get("clean") or []:
        if not isinstance(layer, dict):
            continue
        for item in layer.get("ranges") or []:
            try:
                if float(item.get("start") or 0.0) <= when <= float(item.get("end") or 0.0):
                    active.append(layer)
                    break
            except (TypeError, ValueError):
                continue
    return active


def _proof_scope(edit: dict, when: float) -> tuple[list[dict], dict]:
    """The layers and clip that define one proof frame.

    The proof cache must change when its own layers or clip change, and must
    not change when a layer in another scene changes.
    """
    active = _active_clean(edit, when)
    clips = [item for item in edit.get("clips") or [] if isinstance(item, dict)]
    clip = next(
        (
            item for item in clips
            if float(item.get("start") or 0.0) <= when < float(item.get("end") or 0.0)
        ),
        clips[-1] if clips else {},
    )
    return active, {
        "start": round(float(clip.get("start") or 0.0), 3),
        "end": round(float(clip.get("end") or 0.0), 3),
    }


def create_app(token: str, data_root: Path) -> FastAPI:
    if not token:
        raise ValueError("DuckSuite core requires a launch token.")

    data_root = Path(data_root).expanduser().resolve()
    data_root.mkdir(parents=True, exist_ok=True)
    os.environ["DUCK_DATA_ROOT"] = str(data_root)
    store = ProjectStore(data_root)
    append.recover_commits(store, data_root)
    checks = CheckManager(data_root, store)
    renders = render.RenderQueue(data_root)
    dev_mode = os.environ.get("DUCK_DEV", "").strip() == "1"
    engine_cache: dict = {"at": 0.0, "value": None}

    app = FastAPI(
        title="DuckSuite Core",
        version=APP_VERSION,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    def require_token(request: Request) -> None:
        header = request.headers.get("authorization", "")
        scheme, _, value = header.partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(value, token):
            raise HTTPException(status_code=401, detail="Unauthorized")

    def require_media(request: Request, media_token: str | None = None) -> None:
        """Authorize an <img>/<video> read.

        Media elements cannot attach the bearer header. The local shell passes
        the same launch token as a short-lived query value; the HttpOnly cookie
        is accepted as a fallback.
        """
        candidates = [media_token or "", request.cookies.get("duck_session", "")]
        if any(item and secrets.compare_digest(item, token) for item in candidates):
            return
        raise HTTPException(status_code=401, detail="Unauthorized")

    async def stage_upload(request: Request) -> tuple[Path, Path]:
        filename = Path(request.headers.get("x-filename", "video.mp4")).name
        suffix = Path(filename).suffix.lower() or ".mp4"
        if suffix not in {".mp4", ".mov", ".m4v"}:
            raise HTTPException(status_code=400, detail="Use MP4, MOV or M4V.")
        target_dir = data_root / "imports" / uuid.uuid4().hex[:12]
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"source{suffix}"
        size = 0
        try:
            with target.open("wb") as writer:
                async for chunk in request.stream():
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > MAX_IMPORT_BYTES:
                        raise HTTPException(status_code=413, detail="The video is larger than 8 GB.")
                    writer.write(chunk)
        except HTTPException:
            shutil.rmtree(target_dir, ignore_errors=True)
            raise
        except Exception as exc:  # noqa: BLE001
            shutil.rmtree(target_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail=f"The upload failed: {exc}") from exc
        if size == 0:
            shutil.rmtree(target_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail="The video file is empty.")
        return target_dir, target

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
            "frame-ancestors 'none'; form-action 'none'"
        )
        if request.url.path.startswith("/api/"):
            media_read = any(
                marker in request.url.path
                for marker in ("/frame", "/source", "/clean/preview", "/render/file", "/voice/audio")
            )
            response.headers["Cache-Control"] = (
                "private, max-age=300" if media_read else "no-store"
            )
        return response

    @app.get("/assets/{asset_path:path}")
    def static_asset(asset_path: str) -> FileResponse:
        target = (STATIC / asset_path).resolve()
        try:
            target.relative_to(STATIC.resolve())
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Asset not found.") from exc
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Asset not found.")
        media_type = {
            ".html": "text/html",
            ".css": "text/css",
            ".js": "text/javascript",
            ".mjs": "text/javascript",
            ".json": "application/json",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".woff2": "font/woff2",
        }.get(target.suffix.lower(), "application/octet-stream")
        return FileResponse(target, media_type=media_type)

    @app.get("/api/health")
    def health(_: None = Depends(require_token)) -> dict:
        return {
            "ok": True,
            "app": "DuckSuite",
            "version": APP_VERSION,
            "data_root": str(data_root),
        }

    @app.post("/api/session")
    def session(response: Response, _: None = Depends(require_token)) -> dict:
        # The shell uses the bearer token in JS memory. The cookie is reserved
        # for media reads in the local core; it is HttpOnly, SameSite=Strict.
        response.set_cookie(
            "duck_session",
            token,
            httponly=True,
            samesite="strict",
            secure=False,
            path="/",
        )
        return {"ok": True}

    @app.get("/api/engine")
    def engine_status(_: None = Depends(require_token)) -> dict:
        if engine_cache["value"] is not None and time.monotonic() - engine_cache["at"] < 30:
            return engine_cache["value"]
        from duckcore.engine import stt, textfill, vision

        model_dir = textfill.models_dir(data_root)
        model = model_dir / "lama_fp32.onnx"
        vision_ready = vision.available()
        apple_speech = stt._apple_transcribe_helper()
        whisper = stt._whisper_command()
        fill_problem = textfill.method_problem("lama", model_dir)
        rewrite = {"available": False, "reason": "The rewrite helper is missing."}
        rewrite_helper = script._helper("rewrite_apple")
        if rewrite_helper is not None:
            try:
                checked = subprocess.run(
                    [str(rewrite_helper), "--check"],
                    capture_output=True, text=True, timeout=15,
                )
                rewrite = json.loads(checked.stdout.strip() or "{}")
            except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
                rewrite = {"available": False, "reason": "The rewrite check did not answer."}
        value = {
            "vision": {
                "available": vision_ready,
                "helper": str(vision.BINARY),
                "features": ["ocr", "faces", "saliency", "smart_crop"],
            },
            "speech": {
                "apple": bool(apple_speech),
                "apple_helper": str(apple_speech) if apple_speech else "",
                "whisper": bool(whisper),
                "default": "apple" if apple_speech else ("whisper" if whisper else ""),
            },
            "fill": {
                "method": "lama",
                "model": str(model),
                "model_bytes": model.stat().st_size if model.is_file() else 0,
                "ready": fill_problem is None,
                "problem": fill_problem or "",
            },
            "rewrite": rewrite,
            "stories": {"engine": "local", "ready": True},
        }
        engine_cache["at"] = time.monotonic()
        engine_cache["value"] = value
        return value

    @app.get("/api/models")
    def list_models(_: None = Depends(require_token)) -> dict:
        from duckcore.engine import textfill

        model_dir = textfill.models_dir(data_root)
        model = model_dir / "lama_fp32.onnx"
        return {
            "models": [
                {
                    "id": "lama",
                    "label": "LaMa text fill",
                    "file": str(model),
                    "installed": model.is_file() and model.stat().st_size > 0,
                    "bytes": model.stat().st_size if model.is_file() else 0,
                    "license": "Apache-2.0",
                    "required": True,
                    "ready": textfill.method_problem("lama", model_dir) is None,
                }
            ]
        }

    @app.get("/api/settings")
    def get_settings(_: None = Depends(require_token)) -> dict:
        return app_settings.snapshot(data_root)

    @app.patch("/api/settings")
    def patch_settings(body: SettingsPatch, _: None = Depends(require_token)) -> dict:
        try:
            app_settings.update(data_root, body.model_dump(exclude_none=True))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return app_settings.snapshot(data_root)

    @app.get("/api/translation/model")
    def translation_model_status(_: None = Depends(require_token)) -> dict:
        from duckcore import app_settings, nllb

        settings = app_settings.load(data_root)
        path = nllb.model_dir(
            data_root, custom_path=str(settings.get("translation_model_path") or ""),
        )
        required = ("model.bin", "config.json", "sentencepiece.bpe.model")
        if path is None:
            return {"ready": False, "path": "", "missing": list(required)}
        missing = [name for name in required if not (path / name).is_file()]
        return {"ready": not missing, "path": str(path), "missing": missing}

    @app.post("/api/models/{model_id}/verify")
    def verify_model(model_id: str, _: None = Depends(require_token)) -> dict:
        return app_settings.verify_model(data_root, model_id)

    @app.get("/api/projects")
    def list_projects(_: None = Depends(require_token)) -> dict:
        return {"projects": store.list()}

    @app.post("/api/projects")
    def create_project(body: ProjectCreate, _: None = Depends(require_token)) -> dict:
        try:
            project = store.create(body.name, body.source_path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail="Source file not found.") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"project": project}

    @app.post("/api/projects/upload")
    async def upload_project(request: Request, _: None = Depends(require_token)) -> dict:
        """Browser fallback for Import. The sandboxed app uses NSOpenPanel."""
        raw = await request.body()
        if not raw:
            raise HTTPException(status_code=400, detail="The video file is empty.")
        filename = Path(request.headers.get("x-filename", "video.mp4")).name
        suffix = Path(filename).suffix.lower() or ".mp4"
        if suffix not in {".mp4", ".mov", ".m4v"}:
            raise HTTPException(status_code=400, detail="Use MP4, MOV or M4V.")
        target_dir = data_root / "imports" / uuid.uuid4().hex[:12]
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"source{suffix}"
        target.write_bytes(raw)
        try:
            project = store.create(Path(filename).stem, target)
        except (FileNotFoundError, ValueError) as exc:
            target.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        threading.Thread(
            target=media.ensure_preview,
            args=(target, media.preview_path(data_root, project["id"])),
            daemon=True,
        ).start()
        return {"project": project}

    @app.post("/api/projects/{project_id}/append")
    def append_project(
        project_id: str, body: ProjectAppend, _: None = Depends(require_token),
    ) -> dict:
        try:
            store.get(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found.") from exc
        if append.busy(project_id):
            raise HTTPException(status_code=409, detail="An import is already running.")
        status = checks.status(project_id)
        if status.get("state") in {"queued", "running", "cancelling"}:
            raise HTTPException(status_code=409, detail="Wait for Check to finish first.")
        if renders.busy_for(project_id):
            raise HTTPException(status_code=409, detail="Wait for the render to finish first.")
        try:
            result = append.append_locked(
                project_id,
                body.source_path,
                body.mode,
                store=store,
                data_root=data_root,
                checks=checks,
                renders=renders,
                cleanup=body.cleanup,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found.") from exc
        except append.AppendError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)[:300]) from exc
        return result

    @app.post("/api/projects/{project_id}/append/job", status_code=202)
    def append_project_job(
        project_id: str, body: ProjectAppend, _: None = Depends(require_token),
    ) -> dict:
        try:
            store.get(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found.") from exc
        if append.busy(project_id):
            raise HTTPException(status_code=409, detail="An import is already running.")
        status = checks.status(project_id)
        if status.get("state") in {"queued", "running", "cancelling"}:
            raise HTTPException(status_code=409, detail="Wait for Check to finish first.")
        if renders.busy_for(project_id):
            raise HTTPException(status_code=409, detail="Wait for the render to finish first.")
        try:
            job = append.start_job(
                project_id,
                body.source_path,
                body.mode,
                store=store,
                data_root=data_root,
                checks=checks,
                renders=renders,
                cleanup=body.cleanup,
            )
        except append.AppendError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"job": job}

    @app.get("/api/projects/{project_id}/append/job")
    def append_project_job_current(
        project_id: str, _: None = Depends(require_token),
    ) -> dict:
        return {"job": append.active_job(project_id)}

    @app.get("/api/projects/{project_id}/append/job/{job_id}")
    def append_project_job_status(
        project_id: str, job_id: str, _: None = Depends(require_token),
    ) -> dict:
        try:
            job = append.job_status(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Append job not found.") from exc
        if str(job.get("project_id")) != project_id:
            raise HTTPException(status_code=404, detail="Append job not found.")
        return {"job": job}

    @app.post("/api/projects/{project_id}/append/upload")
    async def append_project_upload(
        project_id: str, request: Request, _: None = Depends(require_token),
    ) -> dict:
        try:
            store.get(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found.") from exc
        if append.busy(project_id):
            raise HTTPException(status_code=409, detail="An import is already running.")
        status = checks.status(project_id)
        if status.get("state") in {"queued", "running", "cancelling"}:
            raise HTTPException(status_code=409, detail="Wait for Check to finish first.")
        if renders.busy_for(project_id):
            raise HTTPException(status_code=409, detail="Wait for the render to finish first.")
        mode = str(request.headers.get("x-mode", "scenes")).lower()
        if mode not in {"scenes", "full"}:
            raise HTTPException(status_code=400, detail="Choose Add scenes or Use full video.")
        target_dir, target = await stage_upload(request)
        try:
            return await run_in_threadpool(
                append.append_locked,
                project_id,
                target,
                mode,
                store=store,
                data_root=data_root,
                checks=checks,
                renders=renders,
                cleanup=True,
            )
        except append.AppendError as exc:
            shutil.rmtree(target_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (OSError, ValueError) as exc:
            shutil.rmtree(target_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            shutil.rmtree(target_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail=str(exc)[:300]) from exc

    @app.post("/api/projects/{project_id}/append/upload/job", status_code=202)
    async def append_project_upload_job(
        project_id: str, request: Request, _: None = Depends(require_token),
    ) -> dict:
        try:
            store.get(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found.") from exc
        if append.busy(project_id):
            raise HTTPException(status_code=409, detail="An import is already running.")
        status = checks.status(project_id)
        if status.get("state") in {"queued", "running", "cancelling"}:
            raise HTTPException(status_code=409, detail="Wait for Check to finish first.")
        if renders.busy_for(project_id):
            raise HTTPException(status_code=409, detail="Wait for the render to finish first.")
        mode = str(request.headers.get("x-mode", "scenes")).lower()
        if mode not in {"scenes", "full"}:
            raise HTTPException(status_code=400, detail="Choose Add scenes or Use full video.")
        target_dir, target = await stage_upload(request)
        try:
            job = append.start_job(
                project_id,
                target,
                mode,
                store=store,
                data_root=data_root,
                checks=checks,
                renders=renders,
                cleanup=True,
            )
        except append.AppendError as exc:
            shutil.rmtree(target_dir, ignore_errors=True)
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            shutil.rmtree(target_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail=str(exc)[:300]) from exc
        return {"job": job}

    @app.get("/api/projects/{project_id}/frame")
    def project_frame(
        project_id: str,
        request: Request,
        time: float = 0.0,
        t: str | None = None,
    ) -> FileResponse:
        require_media(request, t)
        try:
            project = store.get(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found.") from exc
        when = max(0.0, float(time))
        cache = data_root / "projects" / project_id / "frames" / f"frame_{int(when * 1000)}.jpg"
        if not cache.is_file():
            cache.parent.mkdir(parents=True, exist_ok=True)
            try:
                image = media.extract_frame(project["source_path"], when)
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(status_code=500, detail=str(exc)[:300]) from exc
            image.save(cache, format="JPEG", quality=88)
        return FileResponse(cache, media_type="image/jpeg")

    @app.get(
        "/api/projects/{project_id}/source",
        responses={200: {"content": {"video/mp4": {}}}},
    )
    def project_source(
        project_id: str,
        request: Request,
        t: str | None = None,
    ) -> FileResponse:
        require_media(request, t)
        try:
            project = store.get(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found.") from exc
        path = Path(project["source_path"])
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Source is missing.")
        # WKWebView cannot reliably decode AV1/HEVC. Serve a cached H.264
        # proxy for the editor; the original stays the render master.
        playable = media.ensure_preview(
            path, media.preview_path(data_root, project_id),
        ) or path
        return FileResponse(playable, media_type="video/mp4")

    @app.get("/api/projects/{project_id}/transcript")
    def project_transcript(project_id: str, _: None = Depends(require_token)) -> dict:
        try:
            store.get(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found.") from exc
        from duckcore.engine import stt

        job_dir = data_root / "projects" / project_id
        return {"transcript": stt.load_latest_transcript(job_dir) or {}}

    @app.post("/api/projects/{project_id}/transcript/retry")
    def retry_transcript(project_id: str, _: None = Depends(require_token)) -> dict:
        try:
            store.get(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found.") from exc
        status = checks.status(project_id)
        result = status.get("result")
        if not isinstance(result, dict) or not result.get("scenes"):
            raise HTTPException(status_code=409, detail="Run Check first.")
        from duckcore.engine import pipeline

        job = {
            "id": project_id,
            "source": result.get("meta") or result.get("source") or {},
            "analysis": {"scenes": result.get("scenes") or []},
            "options": {},
        }
        retry = pipeline.retry_speech(job, data_root / "projects" / project_id)
        if not retry.get("ok"):
            raise HTTPException(
                status_code=400,
                detail=retry.get("reason") or "No speech was found in this video.",
            )
        if retry.get("scenes"):
            result["scenes"] = retry["scenes"]
        if retry.get("transcript"):
            result["transcript"] = retry["transcript"]
        result["engine"] = {**(result.get("engine") or {}), **(retry.get("engine") or {})}
        append._save_check(data_root, project_id, result)
        checks.adopt(project_id, result)
        return {"ok": True, "transcript": result.get("transcript") or {}, "check": result}

    @app.post("/api/reveal")
    def reveal_file(body: RevealBody, _: None = Depends(require_token)) -> dict:
        path = Path(body.path).expanduser().resolve()
        try:
            path.relative_to(data_root)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Path is outside DuckSuite.") from exc
        if not path.exists():
            raise HTTPException(status_code=404, detail="File not found.")
        subprocess.run(["open", "-R", str(path)], check=False)
        return {"ok": True}

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str, _: None = Depends(require_token)) -> dict:
        try:
            project = store.get(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found.") from exc
        status = checks.status(project_id)
        result = status.get("result")
        if isinstance(result, dict):
            expired = append.expire_pending(data_root, project_id, result)
            if expired is not None:
                checks.adopt(project_id, expired)
                status = checks.status(project_id)
        return {"project": project, "check": status}

    @app.post("/api/projects/{project_id}/check")
    def start_check(project_id: str, _: None = Depends(require_token)) -> dict:
        try:
            store.get(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found.") from exc
        status = checks.status(project_id)
        result = status.get("result")
        if append.busy(project_id):
            raise HTTPException(status_code=409, detail="Wait for the import to finish first.")
        if isinstance(result, dict) and (result.get("append") or {}).get("analysis") == "pending":
            expired = append.expire_pending(data_root, project_id, result)
            if expired is None:
                raise HTTPException(
                    status_code=409,
                    detail="Wait for the added scenes to finish reading.",
                )
            checks.adopt(project_id, expired)
        return {"check": checks.start(project_id)}

    @app.get("/api/projects/{project_id}/check")
    def check_status(project_id: str, _: None = Depends(require_token)) -> dict:
        try:
            store.get(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found.") from exc
        status = checks.status(project_id)
        result = status.get("result")
        if isinstance(result, dict):
            expired = append.expire_pending(data_root, project_id, result)
            if expired is not None:
                checks.adopt(project_id, expired)
                status = checks.status(project_id)
        return {"check": status}

    @app.post("/api/projects/{project_id}/check/cancel")
    def cancel_check(project_id: str, _: None = Depends(require_token)) -> dict:
        try:
            store.get(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found.") from exc
        return {"check": checks.cancel(project_id)}

    def completed_check(project_id: str) -> dict:
        status = checks.status(project_id)
        result = status.get("result")
        # Stories may still be running after text and transcript are saved.
        # The Editor only needs scenes and a report; allow that partial check.
        if not isinstance(result, dict) or not result.get("scenes"):
            raise HTTPException(
                status_code=409,
                detail="Run Check first; the edit needs Check results.",
            )
        return result

    @app.get("/api/projects/{project_id}/edits")
    def list_project_edits(project_id: str, _: None = Depends(require_token)) -> dict:
        try:
            store.get(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found.") from exc
        return {"edits": edits.list_edits(data_root, project_id)}

    @app.post("/api/projects/{project_id}/edits/full")
    def create_full_edit(project_id: str, _: None = Depends(require_token)) -> dict:
        try:
            store.get(project_id)
            check = completed_check(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found.") from exc
        return {"edit": edits.create_full(project_id, check, data_root)}

    @app.post("/api/projects/{project_id}/edits/story")
    def create_story_edit(
        project_id: str, body: StoryEditBody, _: None = Depends(require_token)
    ) -> dict:
        try:
            store.get(project_id)
            check = completed_check(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found.") from exc
        try:
            edit = edits.create_story(
                project_id,
                check,
                data_root,
                story_id=body.story_id,
                start=body.start,
                end=body.end,
                title=body.title,
            )
        except edits.EditError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"edit": edit}

    @app.post("/api/projects/{project_id}/edits/story/scenes")
    def create_scene_story(
        project_id: str, body: SceneStoryBody, _: None = Depends(require_token),
    ) -> dict:
        try:
            store.get(project_id)
            check = completed_check(project_id)
            edit = edits.create_story_from_scenes(
                project_id, check, data_root,
                scene_ids=body.scene_ids, title=body.title,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found.") from exc
        except edits.EditError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"edit": edit}

    @app.post("/api/projects/{project_id}/edits/{edit_id}/story/scene")
    def add_story_scene(
        project_id: str, edit_id: str, body: StorySceneBody,
        _: None = Depends(require_token),
    ) -> dict:
        try:
            check = completed_check(project_id)
            edit = edits.get_edit(data_root, project_id, edit_id)
            edits.add_story_scene(
                edit, check, data_root, scene_id=body.scene_id, index=body.index,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        except edits.EditError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"edit": edit}

    @app.post("/api/projects/{project_id}/edits/{edit_id}/story/beat")
    async def add_story_beat(
        project_id: str, edit_id: str, request: Request,
        _: None = Depends(require_token),
    ) -> dict:
        raw = await request.body()
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
            edits.add_story_media(
                edit, data_root,
                kind=request.headers.get("x-kind", "image"),
                filename=request.headers.get("x-filename", "beat"),
                raw=raw,
                duration=float(request.headers.get("x-duration", "0") or 0),
                index=(
                    int(request.headers["x-index"])
                    if request.headers.get("x-index") not in (None, "") else None
                ),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"edit": edit}

    @app.delete("/api/projects/{project_id}/edits/{edit_id}/story/clip/{index}")
    def delete_story_clip(
        project_id: str, edit_id: str, index: int,
        _: None = Depends(require_token),
    ) -> dict:
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
            edits.remove_story_clip(edit, data_root, index)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        except edits.EditError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"edit": edit}

    @app.post("/api/projects/{project_id}/edits/{edit_id}/story/clip/move")
    def move_story_clip(
        project_id: str, edit_id: str, body: StoryMoveBody,
        _: None = Depends(require_token),
    ) -> dict:
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
            edits.move_story_clip(edit, data_root, body.index, body.delta)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        except edits.EditError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"edit": edit}

    @app.get("/api/projects/{project_id}/edits/{edit_id}/story/file")
    def story_beat_file(
        project_id: str, edit_id: str, name: str,
        request: Request, t: str | None = None,
    ) -> FileResponse:
        require_media(request, t)
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        if not any(str(clip.get("file") or "") == name for clip in edit.get("clips") or []):
            raise HTTPException(status_code=404, detail="Story beat not found.")
        project_dir = (data_root / "projects" / project_id).resolve()
        path = (project_dir / name).resolve()
        if project_dir not in path.parents or not path.is_file():
            raise HTTPException(status_code=404, detail="Story beat file is missing.")
        suffix = path.suffix.lower()
        media_type = (
            "image/png" if suffix == ".png"
            else "image/jpeg" if suffix in {".jpg", ".jpeg"}
            else "image/gif" if suffix == ".gif"
            else "image/webp" if suffix == ".webp"
            else "video/mp4" if suffix in {".mp4", ".m4v"}
            else "video/quicktime" if suffix == ".mov"
            else "application/octet-stream"
        )
        return FileResponse(path, media_type=media_type)

    @app.post("/api/projects/{project_id}/stories/{story_id}/smart-cut")
    def create_smart_cut(
        project_id: str, story_id: str, _: None = Depends(require_token)
    ) -> dict:
        try:
            store.get(project_id)
            check = completed_check(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found.") from exc
        try:
            edit = edits.create_story(
                project_id, check, data_root, story_id=story_id,
            )
        except edits.EditError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"edit": edit}

    @app.get("/api/projects/{project_id}/edits/{edit_id}")
    def get_project_edit(
        project_id: str, edit_id: str, _: None = Depends(require_token)
    ) -> dict:
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
            if not edit.get("audio_tracks"):
                rows = edits.ensure_audio_tracks(edit)
                if rows:
                    edits.save_edit(edit, data_root)
            return {"edit": edit}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        except edits.EditError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/projects/{project_id}/edits/{edit_id}/clean/from-check")
    def clean_from_check(
        project_id: str, edit_id: str, _: None = Depends(require_token)
    ) -> dict:
        try:
            check = completed_check(project_id)
            edit = edits.get_edit(data_root, project_id, edit_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        report = check.get("report") or {}
        edit = clean.apply_report(edit, report)
        edits.save_edit(edit, data_root)
        return {
            "edit": edit,
            "layers": len(edit.get("clean") or []),
            "plan": clean.plan_summary(edit),
        }

    @app.patch("/api/projects/{project_id}/edits/{edit_id}/clips/{clip_index}")
    def patch_clip(
        project_id: str,
        edit_id: str,
        clip_index: int,
        body: ClipPatch,
        _: None = Depends(require_token),
    ) -> dict:
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        clips = [item for item in edit.get("clips") or [] if isinstance(item, dict)]
        if clip_index < 0 or clip_index >= len(clips):
            raise HTTPException(status_code=404, detail="Clip not found.")
        clip = clips[clip_index]
        old_start = float(clip.get("start") or 0.0)
        old_end = float(clip.get("end") or 0.0)
        start = float(body.start) if body.start is not None else old_start
        end = float(body.end) if body.end is not None else old_end
        lower = float(clips[clip_index - 1].get("end") or 0.0) if clip_index else 0.0
        duration = float((edit.get("source") or {}).get("duration") or end)
        upper = float(clips[clip_index + 1].get("start") or duration) if clip_index + 1 < len(clips) else duration
        start = max(lower, min(start, upper - 0.1))
        end = min(upper, max(end, start + 0.1))
        if end - start < 0.1:
            raise HTTPException(status_code=400, detail="Clip is too short.")
        clip["start"] = round(start, 3)
        clip["end"] = round(end, 3)
        clip["dur"] = round(end - start, 3)
        edit["start"] = round(float(clips[0].get("start") or 0.0), 3)
        edit["end"] = round(float(clips[-1].get("end") or 0.0), 3)
        edits.save_edit(edit, data_root)
        return {"edit": edit}

    @app.post("/api/projects/{project_id}/edits/{edit_id}/clips/{clip_index}/slip")
    def slip_clip(
        project_id: str, edit_id: str, clip_index: int, body: SlipClipBody,
        _: None = Depends(require_token),
    ) -> dict:
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
            edit = edits.slip_clip(edit, data_root, clip_index, body.delta)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        except edits.EditError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"edit": edit}

    @app.post("/api/projects/{project_id}/edits/{edit_id}/clips/split")
    def split_clip(
        project_id: str, edit_id: str, body: SplitClipBody,
        _: None = Depends(require_token),
    ) -> dict:
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
            edit = edits.split_at(edit, data_root, body.time)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        except edits.EditError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"edit": edit}

    @app.post("/api/projects/{project_id}/edits/{edit_id}/clean/manual")
    def create_manual_layer(
        project_id: str, edit_id: str, body: ManualLayerBody,
        _: None = Depends(require_token),
    ) -> dict:
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        strokes = [
            {"r": max(0.003, min(0.12, float(stroke.r))), "points": [
                {"x": max(0.0, min(1.0, float(point.x))), "y": max(0.0, min(1.0, float(point.y)))}
                for point in stroke.points
            ]}
            for stroke in body.strokes if stroke.points
        ]
        points = [point for stroke in strokes for point in stroke["points"]]
        if not points:
            raise HTTPException(status_code=400, detail="Paint at least one stroke.")
        start = max(0.0, float(body.start))
        end = max(start + 0.05, float(body.end))
        radius = max(stroke["r"] for stroke in strokes)
        x0 = max(0.0, min(point["x"] for point in points) - radius)
        y0 = max(0.0, min(point["y"] for point in points) - radius)
        x1 = min(1.0, max(point["x"] for point in points) + radius)
        y1 = min(1.0, max(point["y"] for point in points) + radius)
        layer = {
            "id": f"cl_manual_{uuid.uuid4().hex[:8]}",
            "kind": body.kind,
            "method": "lama" if body.kind == "fill" else "",
            "enabled": True,
            "label": "Manual brush",
            "tracklet_kind": "manual",
            "text_sample": "Manual brush",
            "box": {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0},
            "ranges": [{"start": start, "end": end}],
            "mask": {"strokes": strokes},
            "large": False,
            "track": [],
            "fill_keys": None,
            "tracklet_id": "",
            "confidence": 1.0,
        }
        edit.setdefault("clean", []).append(layer)
        edits.save_edit(edit, data_root)
        return {"edit": edit, "layer": layer}

    @app.get(
        "/api/projects/{project_id}/edits/{edit_id}/clean/preview",
        responses={200: {"content": {"image/jpeg": {}}}},
    )
    def clean_preview(
        project_id: str,
        edit_id: str,
        request: Request,
        time: float | None = None,
        t: str | None = None,
    ) -> FileResponse:
        require_media(request, t)
        try:
            project = store.get(project_id)
            edit = edits.get_edit(data_root, project_id, edit_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        when = float(time if time is not None else (edit.get("start") or 0.0) + 0.5)
        active, clip_scope = _proof_scope(edit, when)
        clean_hash = hashlib.sha1(
            json.dumps({"clean": active, "clip": clip_scope}, sort_keys=True).encode("utf-8")
        ).hexdigest()[:12]
        output = data_root / "projects" / project_id / "previews" / f"{edit_id}_{clean_hash}_v{PROOF_VERSION}_{int(when * 1000)}.jpg"
        if output.is_file():
            return FileResponse(output, media_type="image/jpeg")
        try:
            render.render_frame(
                project,
                {**edit, "clean": active},
                data_root,
                output,
                when=when,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)[:500]) from exc
        return FileResponse(output, media_type="image/jpeg")

    @app.get("/api/projects/{project_id}/edits/{edit_id}/captions")
    def get_captions(
        project_id: str, edit_id: str, _: None = Depends(require_token)
    ) -> dict:
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        return {"captions": edit.get("captions")}

    @app.post("/api/projects/{project_id}/edits/{edit_id}/captions/generate")
    def generate_captions(
        project_id: str, edit_id: str, _: None = Depends(require_token)
    ) -> dict:
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        from duckcore.engine import stt

        job_dir = data_root / "projects" / project_id
        transcript = stt.load_latest_transcript(job_dir) or {}
        try:
            track = captions.generate(edit, transcript, data_root)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"captions": track}

    @app.patch("/api/projects/{project_id}/edits/{edit_id}/captions/cues/{cue_id}")
    def patch_caption_cue(
        project_id: str,
        edit_id: str,
        cue_id: str,
        body: CuePatch,
        _: None = Depends(require_token),
    ) -> dict:
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
            track = captions.update_cue(edit, cue_id, body.text, data_root)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Cue not found.") from exc
        return {"captions": track}

    @app.patch("/api/projects/{project_id}/edits/{edit_id}/captions")
    def patch_captions(
        project_id: str,
        edit_id: str,
        body: CaptionsPatch,
        _: None = Depends(require_token),
    ) -> dict:
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
            track = None
            if body.style or body.position:
                track = captions.set_style(
                    edit,
                    style_id=body.style or "",
                    position=body.position or "",
                    data_root=data_root,
                )
            if body.burn is not None:
                track = captions.set_burn(edit, body.burn, data_root)
            if track is None:
                track = edit.get("captions")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"captions": track}

    @app.get(
        "/api/projects/{project_id}/edits/{edit_id}/captions.srt",
        responses={200: {"content": {"application/x-subrip": {}}}},
    )
    def captions_srt(
        project_id: str, edit_id: str, _: None = Depends(require_token)
    ) -> Response:
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        track = edit.get("captions")
        if not isinstance(track, dict):
            raise HTTPException(status_code=409, detail="Generate captions first.")
        return Response(
            captions.srt(track),
            media_type="application/x-subrip",
            headers={"Content-Disposition": f'attachment; filename="{edit_id}.srt"'},
        )

    @app.post("/api/projects/{project_id}/edits/{edit_id}/script/translate")
    def translate_script(
        project_id: str, edit_id: str, body: ScriptTranslate,
        _: None = Depends(require_token),
    ) -> dict:
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
            track = script.translate(edit, data_root, target=body.target, source=body.source)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"captions": track, "script": edit.get("script") or {}}

    @app.post("/api/projects/{project_id}/edits/{edit_id}/script/rewrite")
    def rewrite_script(
        project_id: str, edit_id: str, body: ScriptRewrite,
        _: None = Depends(require_token),
    ) -> dict:
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
            track = script.rewrite(edit, data_root, mode=body.mode)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"captions": track, "script": edit.get("script") or {}}

    @app.post("/api/projects/{project_id}/edits/{edit_id}/script/reset")
    def reset_script(
        project_id: str, edit_id: str, _: None = Depends(require_token),
    ) -> dict:
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
            track = script.reset(edit, data_root)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"captions": track, "script": edit.get("script") or {}}

    @app.post("/api/projects/{project_id}/edits/{edit_id}/voice/preview")
    def preview_voice_line(
        project_id: str, edit_id: str, body: VoicePreviewBody,
        _: None = Depends(require_token),
    ) -> dict:
        try:
            edits.get_edit(data_root, project_id, edit_id)
            track = voice.preview_line(body.text, body.voice, project_id, data_root)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"preview": track}

    @app.get("/api/projects/{project_id}/voice/preview/{name}")
    def preview_audio(
        project_id: str, name: str, request: Request, t: str | None = None,
    ) -> FileResponse:
        require_media(request, t)
        target = (data_root / "projects" / project_id / "voice" / "previews" / Path(name).name).resolve()
        try:
            target.relative_to((data_root / "projects" / project_id / "voice" / "previews").resolve())
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Preview not found.") from exc
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Preview not found.")
        return FileResponse(target, media_type="audio/wav")

    @app.post("/api/projects/{project_id}/edits/{edit_id}/voice/record")
    def save_recording(
        project_id: str, edit_id: str, body: VoiceRecordBody,
        _: None = Depends(require_token),
    ) -> dict:
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        source = Path(body.path).expanduser()
        if not source.is_file():
            raise HTTPException(status_code=400, detail="Recording file is missing.")
        target_dir = data_root / "projects" / project_id / "voice"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"record_{uuid.uuid4().hex[:12]}{source.suffix or '.wav'}"
        shutil.copy2(source, target)
        track = {
            "id": f"at_{uuid.uuid4().hex[:10]}",
            "kind": "voice",
            "name": "Microphone",
            "engine": "record",
            "voice": "Microphone",
            "mode": "voice_over",
            "audio": str(target.relative_to(data_root / "projects" / project_id)),
            "duration": media.duration(target),
            "start": 0.0,
            "volume": 1.0,
        }
        edits.ensure_audio_tracks(edit)
        edit["audio_tracks"].append(track)
        edit["voice"] = track
        edits.save_edit(edit, data_root)
        return {"voice": track, "edit": edit}

    @app.post("/api/projects/{project_id}/edits/{edit_id}/dub")
    def build_dub(
        project_id: str, edit_id: str, body: DubBody,
        _: None = Depends(require_token),
    ) -> dict:
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        try:
            track = voice.build_track(
                (edit.get("captions") or {}).get("cues") or [],
                voice_name=body.voice, mode="voice_only",
                project_id=project_id, data_root=data_root,
                total_duration=float(edit.get("end") or 0.0),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        track["id"] = f"at_{uuid.uuid4().hex[:10]}"
        track["kind"] = "dub"
        track["name"] = f"Dub · {body.voice}"
        track["start"] = 0.0
        track["volume"] = 1.0
        track["language"] = body.language
        edits.ensure_audio_tracks(edit)
        edit["audio_tracks"] = [row for row in edit["audio_tracks"] if row.get("kind") != "dub"]
        edit["audio_tracks"].append(track)
        edit["dub"] = track
        edits.save_edit(edit, data_root)
        return {"dub": track, "edit": edit}

    @app.post("/api/projects/{project_id}/edits/{edit_id}/sfx/text")
    def add_sfx_text(
        project_id: str, edit_id: str, body: SfxTextBody,
        _: None = Depends(require_token),
    ) -> dict:
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
            effect = effects.add_text(
                edit, data_root,
                text=body.text, start=body.start, end=body.end,
                style=body.style, color=body.color, x=body.x, y=body.y,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        except effects.EffectError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"effect": effect, "edit": edit}

    @app.post("/api/projects/{project_id}/edits/{edit_id}/sfx/filter")
    def add_sfx_filter(
        project_id: str, edit_id: str, body: SfxFilterBody,
        _: None = Depends(require_token),
    ) -> dict:
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
            effect = effects.add_filter(
                edit, data_root,
                preset=body.preset, start=body.start, end=body.end,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        except effects.EffectError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"effect": effect, "edit": edit}

    @app.post("/api/projects/{project_id}/edits/{edit_id}/sfx/upload")
    async def upload_sfx(
        project_id: str, edit_id: str, request: Request,
        _: None = Depends(require_token),
    ) -> dict:
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        raw = await request.body()
        if not raw:
            raise HTTPException(status_code=400, detail="The effect file is empty.")
        try:
            effect = effects.add_upload(
                edit, data_root,
                kind=request.headers.get("x-kind", ""),
                filename=request.headers.get("x-filename", "effect"),
                raw=raw,
                start=float(request.headers.get("x-start", "0") or 0),
                end=float(request.headers.get("x-end", "3") or 3),
                volume=float(request.headers.get("x-volume", "0.9") or 0.9),
            )
        except effects.EffectError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"effect": effect, "edit": edit}

    @app.delete("/api/projects/{project_id}/edits/{edit_id}/sfx/{effect_id}")
    def delete_sfx(
        project_id: str, edit_id: str, effect_id: str,
        _: None = Depends(require_token),
    ) -> dict:
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
            rows = effects.remove(edit, data_root, effect_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Effect not found.") from exc
        return {"effects": rows, "edit": edit}

    @app.get("/api/projects/{project_id}/edits/{edit_id}/audio/{track_id}/file")
    def audio_track_file(
        project_id: str, edit_id: str, track_id: str,
        request: Request, t: str | None = None,
    ) -> FileResponse:
        require_media(request, t)
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        rows = edit.get("audio_tracks")
        if not isinstance(rows, list) or not rows:
            rows = edits.ensure_audio_tracks(edit)
        row = next((item for item in rows if str(item.get("id")) == track_id), None)
        if row is None:
            row = next((item for item in edit.get("sfx") or [] if str(item.get("id")) == track_id and item.get("kind") == "sound"), None)
        if row is None:
            raise HTTPException(status_code=404, detail="Audio track not found.")
        path = data_root / "projects" / project_id / str(row.get("audio") or row.get("file") or "")
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Audio file is missing.")
        suffix = path.suffix.lower()
        media_type = "audio/wav" if suffix == ".wav" else "audio/mp4" if suffix in {".m4a", ".aac"} else "audio/mpeg" if suffix == ".mp3" else "application/octet-stream"
        return FileResponse(path, media_type=media_type)

    @app.patch("/api/projects/{project_id}/edits/{edit_id}/audio/{track_id}")
    def patch_audio_track(
        project_id: str, edit_id: str, track_id: str, body: AudioTrackPatch,
        _: None = Depends(require_token),
    ) -> dict:
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        values = body.model_dump(exclude_none=True)
        try:
            row = edits.patch_audio_track(edit, track_id, values)
        except KeyError:
            effect = next((item for item in edit.get("sfx") or [] if str(item.get("id")) == track_id and item.get("kind") == "sound"), None)
            if effect is None:
                raise HTTPException(status_code=404, detail="Audio track not found.")
            old_start = float(effect.get("start") or 0.0)
            old_end = float(effect.get("end") or old_start)
            if "start" in values:
                effect["start"] = max(0.0, float(values["start"]))
                if "duration" not in values:
                    effect["end"] = max(float(effect["start"]) + 0.2, old_end + (float(effect["start"]) - old_start))
            if "duration" in values:
                effect["end"] = float(effect["start"] or 0.0) + max(0.2, float(values["duration"]))
            if "offset" in values:
                effect["offset"] = max(0.0, float(values["offset"]))
            if "volume" in values:
                effect["volume"] = max(0.0, min(1.5, float(values["volume"])))
            for key in ("muted", "solo", "fade_in", "fade_out"):
                if key in values:
                    effect[key] = values[key]
            row = effect
        edits.save_edit(edit, data_root)
        return {"audio_track": row, "edit": edit}

    @app.delete("/api/projects/{project_id}/edits/{edit_id}/audio/{track_id}")
    def delete_audio_track(
        project_id: str, edit_id: str, track_id: str,
        _: None = Depends(require_token),
    ) -> dict:
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        try:
            rows = edits.remove_audio_track(edit, track_id)
        except KeyError:
            try:
                effects.remove(edit, data_root, track_id)
                rows = edits.ensure_audio_tracks(edit)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="Audio track not found.") from exc
        edits.save_edit(edit, data_root)
        return {"audio_tracks": rows, "edit": edit}

    @app.post("/api/projects/{project_id}/edits/{edit_id}/music")
    async def upload_music(
        project_id: str, edit_id: str, request: Request,
        _: None = Depends(require_token),
    ) -> dict:
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        raw = await request.body()
        if not raw:
            raise HTTPException(status_code=400, detail="Music file is empty.")
        name = Path(request.headers.get("x-filename", "music.m4a")).name
        target_dir = data_root / "projects" / project_id / "music"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / name
        target.write_bytes(raw)
        track = {
            "id": f"at_{uuid.uuid4().hex[:10]}",
            "kind": "music",
            "name": name,
            "audio": str(target.relative_to(data_root / "projects" / project_id)),
            "duration": media.duration(target),
            "start": 0.0,
            "volume": 0.25,
        }
        edits.ensure_audio_tracks(edit)
        edit["audio_tracks"].append(track)
        edit["music"] = track
        edits.save_edit(edit, data_root)
        return {"music": track, "edit": edit}

    @app.delete("/api/projects/{project_id}/edits/{edit_id}/music")
    def remove_music(project_id: str, edit_id: str, _: None = Depends(require_token)) -> dict:
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        music = edit.get("music")
        if isinstance(music, dict) and music.get("id"):
            try:
                edits.remove_audio_track(edit, str(music["id"]))
            except KeyError:
                pass
        edit.pop("music", None)
        edits.save_edit(edit, data_root)
        return {"ok": True}

    @app.get("/api/packs")
    def list_packs(_: None = Depends(require_token)) -> dict:
        return {"packs": packs.status(data_root)}

    @app.post("/api/packs/{pack_id}/download")
    def download_pack(pack_id: str, _: None = Depends(require_token)) -> dict:
        try:
            return {"packs": packs.start_download(data_root, pack_id)}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Pack not found.") from exc

    @app.delete("/api/packs/{pack_id}")
    def remove_pack(pack_id: str, _: None = Depends(require_token)) -> dict:
        try:
            return {"packs": packs.remove(data_root, pack_id)}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Pack not found.") from exc

    @app.get("/api/voices")
    def local_voices(_: None = Depends(require_token)) -> dict:
        return {"voices": voice.list_voices(data_root)}

    @app.get("/api/projects/{project_id}/edits/{edit_id}/voice")
    def get_voice(
        project_id: str, edit_id: str, _: None = Depends(require_token)
    ) -> dict:
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        return {"voice": edit.get("voice")}

    @app.post("/api/projects/{project_id}/edits/{edit_id}/voice")
    def build_voice(
        project_id: str, edit_id: str, body: VoicePatch, _: None = Depends(require_token)
    ) -> dict:
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        try:
            track = voice.build_voice(
                edit, edit.get("captions") or {}, data_root,
                voice=body.voice, mode=body.mode,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)[:500]) from exc
        return {"voice": track, "edit": edit}

    @app.get(
        "/api/projects/{project_id}/edits/{edit_id}/voice/audio",
        responses={200: {"content": {"audio/wav": {}}}},
    )
    def voice_audio(
        project_id: str,
        edit_id: str,
        request: Request,
        t: str | None = None,
    ) -> FileResponse:
        require_media(request, t)
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        track = edit.get("voice") or edit.get("dub") or {}
        path = data_root / "projects" / project_id / str(track.get("audio") or "")
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Voice audio is missing.")
        return FileResponse(path, media_type="audio/wav")

    @app.post("/api/projects/{project_id}/edits/{edit_id}/render")
    def start_render(
        project_id: str, edit_id: str, _: None = Depends(require_token)
    ) -> dict:
        if append.busy(project_id):
            raise HTTPException(status_code=409, detail="Wait for the import to finish first.")
        status = checks.status(project_id)
        result = status.get("result")
        if isinstance(result, dict) and (result.get("append") or {}).get("analysis") == "pending":
            expired = append.expire_pending(data_root, project_id, result)
            if expired is None:
                raise HTTPException(status_code=409, detail="Wait for the added scenes to finish reading.")
            checks.adopt(project_id, expired)
        try:
            return {"render": renders.start(project_id, edit_id)}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        except edits.EditError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/projects/{project_id}/edits/{edit_id}/render")
    def render_status(
        project_id: str, edit_id: str, _: None = Depends(require_token)
    ) -> dict:
        return {"render": renders.status(project_id, edit_id)}

    @app.post("/api/projects/{project_id}/edits/{edit_id}/render/cancel")
    def cancel_render(
        project_id: str, edit_id: str, _: None = Depends(require_token)
    ) -> dict:
        return {"render": renders.cancel(project_id, edit_id)}

    @app.get("/api/queue")
    def render_queue(_: None = Depends(require_token)) -> dict:
        return {"paused": renders.paused, "items": renders.list()}

    @app.post("/api/queue/pause")
    def pause_queue(_: None = Depends(require_token)) -> dict:
        return renders.pause()

    @app.post("/api/queue/resume")
    def resume_queue(_: None = Depends(require_token)) -> dict:
        return renders.resume()

    @app.post("/api/queue/clear")
    def clear_queue(_: None = Depends(require_token)) -> dict:
        return {"items": renders.clear_finished()}

    @app.get(
        "/api/projects/{project_id}/edits/{edit_id}/render/file",
        responses={200: {"content": {"video/mp4": {}}}},
    )
    def render_file(
        project_id: str,
        edit_id: str,
        request: Request,
        t: str | None = None,
    ) -> FileResponse:
        require_media(request, t)
        status = renders.status(project_id, edit_id)
        if status.get("state") != "done" or not status.get("output"):
            raise HTTPException(status_code=409, detail="Render is not ready.")
        path = Path(str(status["output"]))
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Render file is missing.")
        return FileResponse(path, media_type="video/mp4", filename=path.name)

    @app.patch("/api/projects/{project_id}/edits/{edit_id}/clean/{layer_id}")
    def patch_clean_layer(
        project_id: str,
        edit_id: str,
        layer_id: str,
        body: LayerAction,
        _: None = Depends(require_token),
    ) -> dict:
        try:
            edit = edits.get_edit(data_root, project_id, edit_id)
            edit = clean.patch_layer(edit, layer_id, body.action)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Layer not found.") from exc
        except edits.EditError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        edits.save_edit(edit, data_root)
        return {"edit": edit}

    @app.patch("/api/projects/{project_id}")
    def rename_project(
        project_id: str, body: ProjectRename, _: None = Depends(require_token)
    ) -> dict:
        try:
            return {"project": store.rename(project_id, body.name)}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found.") from exc

    @app.delete("/api/projects/{project_id}")
    def delete_project(project_id: str, _: None = Depends(require_token)) -> dict:
        try:
            store.delete(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found.") from exc
        return {"ok": True}

    if dev_mode:
        @app.post("/api/projects/dev-import")
        def dev_import(body: DevImport, _: None = Depends(require_token)) -> dict:
            """Development only: copy a local file into the app data folder.

            The sandboxed Mac app uses NSOpenPanel and copies the file itself.
            This endpoint is disabled unless DUCK_DEV=1.
            """
            source = Path(body.source_path).expanduser().resolve()
            if not source.is_file():
                raise HTTPException(status_code=400, detail="Source file not found.")
            target_dir = data_root / "imports" / uuid.uuid4().hex[:12]
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f"source{source.suffix.lower() or '.mp4'}"
            shutil.copy2(source, target)
            project = store.create(body.name or source.stem, target)
            threading.Thread(
                target=media.ensure_preview,
                args=(target, media.preview_path(data_root, project["id"])),
                daemon=True,
            ).start()
            return {"project": project}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html", media_type="text/html")

    @app.get("/favicon.ico")
    def favicon() -> Response:
        return Response(status_code=204)

    return app


def _read_token() -> str:
    token = os.environ.get("DUCK_TOKEN", "").strip()
    if token:
        return token
    line = sys.stdin.readline().strip()
    return line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="duckcore")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args(argv)

    token = _read_token()
    if not token:
        print("duckcore: missing launch token", file=sys.stderr)
        return 2

    app = create_app(token, args.data_root)

    # Bind before uvicorn starts so the shell receives the real port. Port 0 is
    # the production path; a fixed port is only for local development.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", args.port))
    sock.listen(128)
    port = sock.getsockname()[1]

    print(json.dumps({"port": port, "pid": os.getpid()}), flush=True)
    config = uvicorn.Config(app, log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    server.run(sockets=[sock])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
