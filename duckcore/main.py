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
