"""DuckClean worker — M1 routes.

    GET  /health          unsigned, reports what is actually available
    POST /v1/probe        ffprobe facts
    POST /v1/proxy        720p H.264 proxy + poster
    POST /v1/cancel       honest: reports whether anything is running

Every signed route verifies the HMAC before parsing the body, is idempotent by
``job_id``, and reports ``usage`` from measured compute. A missing model or
ffmpeg is reported, never silently skipped. Dissect, detect, render and preview
arrive with tasks 4-8; none of them is stubbed here.
"""

from __future__ import annotations

import shutil
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import WORKER_CONTRACT_VERSION
from .contract import (
    CancelRequest,
    CancelResponse,
    DeviceClass,
    HealthResponse,
    JobStatus,
    ModelState,
    PosterFacts,
    ProbeRequest,
    ProbeResponse,
    ProxyRequest,
    ProxyResponse,
    Usage,
    WorkerError,
    WorkerErrorCode,
    WorkerErrorEnvelope,
)
from .media import MediaError, ffmpeg_version, make_poster, make_proxy, probe_file, proxy_facts
from .signing import KEY_ID_HEADER, SIGNATURE_HEADER, SignatureError, verify
from .storage import StorageError, download, upload

WORKER_VERSION = "0.1.0-m1"


class WorkerApiError(Exception):
    """Turns into the one worker error envelope."""

    def __init__(
        self,
        code: WorkerErrorCode,
        message: str,
        *,
        status: int = 400,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.retryable = retryable


@dataclass(frozen=True)
class Settings:
    secret: str
    key_id: str
    device_class: DeviceClass
    work_dir: Path


@lru_cache(maxsize=1)
def settings() -> Settings:
    raw_class = __import__("os").environ.get("DUCKCLEAN_DEVICE_CLASS", "cpu")
    try:
        device_class = DeviceClass(raw_class)
    except ValueError:
        device_class = DeviceClass.CPU
    import os

    return Settings(
        secret=os.environ.get("DUCKCLEAN_HMAC_SECRET", ""),
        key_id=os.environ.get("DUCKCLEAN_KEY_ID", "v1"),
        device_class=device_class,
        work_dir=Path(os.environ.get("DUCKCLEAN_WORK_DIR", tempfile.gettempdir())),
    )


_results: dict[str, dict[str, Any]] = {}
_finished: set[str] = set()
_state_lock = threading.Lock()
_slots = threading.Semaphore(1)
_active_jobs = 0
_current_job: str | None = None
_cancel = threading.Event()


@lru_cache(maxsize=1)
def _ffmpeg_version() -> str:
    return ffmpeg_version()


@contextmanager
def _slot(job_id: str) -> Iterator[None]:
    global _active_jobs, _current_job
    _slots.acquire()
    with _state_lock:
        _active_jobs += 1
        _current_job = job_id
    _cancel.clear()
    try:
        yield
    finally:
        with _state_lock:
            _active_jobs -= 1
            _current_job = None
        _cancel.clear()
        _slots.release()


def _cached(job_id: str) -> dict[str, Any] | None:
    with _state_lock:
        return _results.get(job_id)


def _remember(job_id: str, payload: dict[str, Any]) -> None:
    with _state_lock:
        _results[job_id] = payload
        _finished.add(job_id)


def _check_cancel() -> None:
    if _cancel.is_set():
        raise WorkerApiError(WorkerErrorCode.CANCELLED, "cancelled", status=409)


async def require_signature(
    request: Request,
    signature: Annotated[str | None, Header(alias=SIGNATURE_HEADER)] = None,
    key_id: Annotated[str | None, Header(alias=KEY_ID_HEADER)] = None,
) -> None:
    config = settings()
    if not config.secret:
        raise WorkerApiError(
            WorkerErrorCode.INTERNAL, "worker secret is not configured", status=500
        )
    if key_id is not None and key_id != config.key_id:
        raise WorkerApiError(WorkerErrorCode.INVALID_SIGNATURE, "unknown key id", status=401)
    body = await request.body()
    try:
        verify(config.secret, signature, body)
    except SignatureError as exc:
        code = (
            WorkerErrorCode.CLOCK_SKEW
            if exc.reason == "clock_skew"
            else WorkerErrorCode.INVALID_SIGNATURE
        )
        raise WorkerApiError(code, exc.reason, status=401) from exc


app = FastAPI(title="DuckClean worker", version=WORKER_VERSION)


@app.exception_handler(WorkerApiError)
async def _worker_error_handler(_request: Request, exc: WorkerApiError) -> JSONResponse:
    envelope = WorkerErrorEnvelope(
        error=WorkerError(code=exc.code, message=exc.message, retryable=exc.retryable)
    )
    return JSONResponse(envelope.model_dump(mode="json"), status_code=exc.status)


@app.exception_handler(RequestValidationError)
async def _validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    envelope = WorkerErrorEnvelope(
        error=WorkerError(
            code=WorkerErrorCode.PAYLOAD_INVALID,
            message="request payload is invalid",
            detail={"errors": len(exc.errors())},
        )
    )
    return JSONResponse(envelope.model_dump(mode="json"), status_code=422)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    config = settings()
    with _state_lock:
        active = _active_jobs
    try:
        free = shutil.disk_usage(config.work_dir).free
    except OSError:
        free = 0
    return HealthResponse(
        status="ok" if config.secret and _ffmpeg_version() != "missing" else "degraded",
        contract_version=WORKER_CONTRACT_VERSION,
        git_sha=__import__("os").environ.get("DUCKCLEAN_GIT_SHA", "dev"),
        device_class=config.device_class,
        ffmpeg_version=_ffmpeg_version(),
        models=[ModelState(name="m1-media", version=WORKER_VERSION, available=True)],
        busy=active > 0,
        active_jobs=active,
        disk_free_bytes=free,
    )


@app.post(
    "/v1/probe",
    response_model=ProbeResponse,
    dependencies=[Depends(require_signature)],
)
def probe(request: ProbeRequest) -> JSONResponse:
    job_id = str(request.job_id)
    cached = _cached(job_id)
    if cached is not None:
        return JSONResponse(cached)

    started = time.monotonic()
    with _slot(job_id), tempfile.TemporaryDirectory(dir=settings().work_dir) as tmp:
        source = Path(tmp) / "source"
        try:
            download(request.input.url, source)
            _check_cancel()
            facts = probe_file(source)
        except StorageError as exc:
            raise WorkerApiError(WorkerErrorCode.SOURCE_UNREADABLE, exc.reason, status=422) from exc
        except MediaError as exc:
            raise WorkerApiError(WorkerErrorCode.SOURCE_UNREADABLE, exc.reason, status=422) from exc

        response = ProbeResponse(
            job_id=request.job_id,
            status=JobStatus.SUCCEEDED,
            probe=facts,
            usage=Usage(
                compute_seconds=round(time.monotonic() - started, 3),
                device_class=settings().device_class,
                input_bytes=source.stat().st_size,
            ),
        )
        payload = response.model_dump(mode="json")
        _remember(job_id, payload)
        return JSONResponse(payload)


@app.post(
    "/v1/proxy",
    response_model=ProxyResponse,
    dependencies=[Depends(require_signature)],
)
def proxy(request: ProxyRequest) -> JSONResponse:
    job_id = str(request.job_id)
    cached = _cached(job_id)
    if cached is not None:
        return JSONResponse(cached)

    started = time.monotonic()
    with _slot(job_id), tempfile.TemporaryDirectory(dir=settings().work_dir) as tmp:
        source = Path(tmp) / "source"
        proxy_path = Path(tmp) / "proxy.mp4"
        poster_path = Path(tmp) / "poster.jpg"
        try:
            input_bytes = download(request.input.url, source)
            _check_cancel()
            input_facts = request.probe or probe_file(source)
            written = make_proxy(source, proxy_path, request.options)
            _check_cancel()
            poster_facts = make_poster(
                source,
                poster_path,
                duration_ms=input_facts.duration_ms,
                source_height=input_facts.display_height,
                at_ms=request.options.poster_at_ms,
                max_height=request.options.max_height,
            )
            _check_cancel()
            proxy_bytes = upload(
                request.output.url,
                proxy_path,
                content_type=request.output.headers.get("content-type", "video/mp4"),
                headers=request.output.headers,
            )
            poster_bytes = upload(
                request.poster.url,
                poster_path,
                content_type=request.poster.headers.get("content-type", "image/jpeg"),
                headers=request.poster.headers,
            )
        except StorageError as exc:
            raise WorkerApiError(WorkerErrorCode.STORAGE_FAILED, exc.reason, status=502) from exc
        except MediaError as exc:
            raise WorkerApiError(WorkerErrorCode.SOURCE_UNREADABLE, exc.reason, status=422) from exc

        response = ProxyResponse(
            job_id=request.job_id,
            status=JobStatus.SUCCEEDED,
            proxy=proxy_facts(written, proxy_bytes),
            poster=PosterFacts(
                width=poster_facts.width,
                height=poster_facts.height,
                bytes=poster_bytes,
                frame_index=None,
            ),
            usage=Usage(
                compute_seconds=round(time.monotonic() - started, 3),
                device_class=settings().device_class,
                input_bytes=input_bytes,
                output_bytes=proxy_bytes + poster_bytes,
            ),
        )
        payload = response.model_dump(mode="json")
        _remember(job_id, payload)
        return JSONResponse(payload)


@app.post(
    "/v1/cancel",
    response_model=CancelResponse,
    dependencies=[Depends(require_signature)],
)
def cancel(request: CancelRequest) -> CancelResponse:
    job_id = str(request.job_id)
    with _state_lock:
        running = _current_job == job_id
        finished = job_id in _finished
    if finished:
        return CancelResponse(
            job_id=request.job_id,
            cancelled=False,
            status="already_finished",
            usage=Usage(compute_seconds=0, device_class=settings().device_class),
        )
    if not running:
        return CancelResponse(
            job_id=request.job_id,
            cancelled=False,
            status="not_running",
            usage=Usage(compute_seconds=0, device_class=settings().device_class),
        )
    _cancel.set()
    return CancelResponse(
        job_id=request.job_id,
        cancelled=True,
        status="cancelling",
        usage=Usage(compute_seconds=0, device_class=settings().device_class),
    )
