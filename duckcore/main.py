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
import socket
import sys
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static" / "duck"
APP_VERSION = "0.1.0"


def create_app(token: str, data_root: Path) -> FastAPI:
    if not token:
        raise ValueError("DuckSuite core requires a launch token.")

    data_root = Path(data_root).expanduser().resolve()
    data_root.mkdir(parents=True, exist_ok=True)

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
