"""Minimal DuckSuite core for the Day 1 shell spike.

Run locally:

    DUCK_TOKEN=dev python3 duck_app.py --data-root /tmp/ducksuite --port 8797

The Swift shell starts the same entrypoint with port 0 and a random token on
stdin. Stdout is reserved for the single handshake line:

    {"port": 51234, "pid": 1234}
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import socket
import sys
import time
import uuid
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from duckcore import app_settings, captions, clean, edits, preview, render
from duckcore.check import CheckManager
from duckcore.store import ProjectStore

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(os.environ.get("DUCK_STATIC_DIR", ROOT / "static" / "duck")).expanduser()
APP_VERSION = "0.1.0"


class ProjectCreate(BaseModel):
    name: str = Field(default="", max_length=160)
    source_path: str


class ProjectRename(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class StoryEditBody(BaseModel):
    story_id: str = ""
    start: float | None = None
    end: float | None = None
    title: str = Field(default="", max_length=120)


class LayerAction(BaseModel):
    action: str = Field(pattern="^(fill|blur|exclude)$")


class SettingsPatch(BaseModel):
    online_enabled: bool | None = None
    online_endpoint: str | None = None


class CuePatch(BaseModel):
    text: str = Field(max_length=240)


class CaptionsPatch(BaseModel):
    burn: bool | None = None
    style: str | None = None
    position: str | None = None


class DevImport(BaseModel):
    source_path: str
    name: str = Field(default="", max_length=160)


def create_app(token: str, data_root: Path) -> FastAPI:
    if not token:
        raise ValueError("DuckSuite core requires a launch token.")

    data_root = Path(data_root).expanduser().resolve()
    data_root.mkdir(parents=True, exist_ok=True)
    store = ProjectStore(data_root)
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
    app.mount("/assets", StaticFiles(directory=STATIC), name="assets")

    def require_token(request: Request) -> None:
        header = request.headers.get("authorization", "")
        scheme, _, value = header.partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(value, token):
            raise HTTPException(status_code=401, detail="Unauthorized")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
            "frame-ancestors 'none'; form-action 'none'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

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

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str, _: None = Depends(require_token)) -> dict:
        try:
            project = store.get(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found.") from exc
        return {"project": project, "check": checks.status(project_id)}

    @app.post("/api/projects/{project_id}/check")
    def start_check(project_id: str, _: None = Depends(require_token)) -> dict:
        try:
            store.get(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found.") from exc
        return {"check": checks.start(project_id)}

    @app.get("/api/projects/{project_id}/check")
    def check_status(project_id: str, _: None = Depends(require_token)) -> dict:
        try:
            store.get(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found.") from exc
        return {"check": checks.status(project_id)}

    @app.post("/api/projects/{project_id}/check/cancel")
    def cancel_check(project_id: str, _: None = Depends(require_token)) -> dict:
        try:
            store.get(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found.") from exc
        return {"check": checks.cancel(project_id)}

    def completed_check(project_id: str) -> dict:
        status = checks.status(project_id)
        if status.get("state") != "done" or not isinstance(status.get("result"), dict):
            raise HTTPException(
                status_code=409,
                detail="Run Check first; the edit needs Check results.",
            )
        return status["result"]

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
            return {"edit": edits.get_edit(data_root, project_id, edit_id)}
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
        return {"edit": edit, "layers": len(edit.get("clean") or [])}

    @app.get(
        "/api/projects/{project_id}/edits/{edit_id}/clean/preview",
        responses={200: {"content": {"image/jpeg": {}}}},
    )
    def clean_preview(
        project_id: str,
        edit_id: str,
        time: float | None = None,
        _: None = Depends(require_token),
    ) -> FileResponse:
        try:
            project = store.get(project_id)
            edit = edits.get_edit(data_root, project_id, edit_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edit not found.") from exc
        when = float(time if time is not None else (edit.get("start") or 0.0) + 0.5)
        output = data_root / "projects" / project_id / "previews" / f"{edit_id}_{int(when * 1000)}.jpg"
        try:
            preview.render_clean_preview(
                project["source_path"],
                edit,
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

    @app.post("/api/projects/{project_id}/edits/{edit_id}/render")
    def start_render(
        project_id: str, edit_id: str, _: None = Depends(require_token)
    ) -> dict:
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

    @app.get(
        "/api/projects/{project_id}/edits/{edit_id}/render/file",
        responses={200: {"content": {"video/mp4": {}}}},
    )
    def render_file(
        project_id: str, edit_id: str, _: None = Depends(require_token)
    ) -> FileResponse:
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
