"""HTTP surface for Source Check.

``POST /api/jobs/{id}/check`` starts one Check pass; ``GET`` returns its
``SourceReport``. The pass runs on its own single-worker scheduler so a long
0.5 fps text sample never blocks the analysis or render queues.

The report is stored under ``jobs/<id>/check/source_report.json`` and its
summary on ``job["check"]``. A report is trusted only when ``status`` is
``ready`` and ``text.confirmed`` is true; while a pass is queued or running the
endpoint returns a ``SourceReport``-shaped envelope with ``complete: false``.
``POST /api/jobs/{id}/check/cancel`` stops a queued or running pass; a
running one stops at its next frame batch and keeps the last finished report.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

import detect
import job_queue
import pipeline

LOGGER = logging.getLogger("vibecut.routes_check")

CHECK_POOL = job_queue.Scheduler(
    "check", max_workers=1, thread_name_prefix="vibecut-check",
)

ACTIVE_STATES = {"queued", "running"}

#: One cancel event per job's current Check pass. ``start_check`` replaces it,
#: the worker binds it to its thread so the frame reader stops mid-batch.
CHECK_CANCELS: dict[str, threading.Event] = {}


class CheckCancelled(RuntimeError):
    """The founder pressed Cancel while Check was running."""


class CheckBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    force: bool = False
    # Accepted for older clients only. Check's rights policy comes from the
    # job record written by POST /rights and from rights.py, never this body.
    attestation: bool | str | None = None
    sample_text: bool = True
    fps: float = Field(default=detect.DEFAULT_SAMPLE_FPS, ge=0.1, le=2.0)


router = APIRouter()


def _job_app():
    import app

    return app


def _check_record(job: dict) -> dict:
    value = job.get("check")
    return dict(value) if isinstance(value, dict) else {}


def _set_check(job_id: str, app, **values: Any) -> dict:
    def mutate(job: dict) -> None:
        record = dict(job.get("check") or {})
        record.update(values)
        record["updated"] = round(time.time(), 3)
        job["check"] = record

    return app.update_job(job_id, mutate)


def _running_report(job: dict, state: str, error: str | None = None) -> dict:
    report = detect.state_report(job, state, error=error)
    record = _check_record(job)
    report["message"] = record.get("message") or ""
    report["progress"] = record.get("progress", 0.0)
    return report


def _ready_report(app, job: dict) -> dict | None:
    report = detect.load_report(app._job_dir(job["id"]))
    if report is None:
        return None
    if _check_record(job).get("status") != "ready":
        return None
    return report


def _finish_cancelled(job_id: str, app) -> dict:
    """Mark a cancelled pass. A report from an earlier pass stays in use."""
    if detect.load_report(app._job_dir(job_id)) is not None:
        return _set_check(
            job_id, app, status="ready", progress=1.0,
            message="Cancelled · showing the last Check", error=None,
        )
    return _set_check(
        job_id, app, status="cancelled", progress=1.0,
        message="Cancelled", error=None,
    )


def run_check_job(job_id: str, options: dict) -> dict:
    """Worker entry point. Always persists a terminal state on the job."""
    app = _job_app()
    started = time.time()
    job = {"id": job_id}
    cancel = CHECK_CANCELS.setdefault(job_id, threading.Event())
    pipeline.stt.set_cancel_event(cancel)
    try:
        if cancel.is_set():
            raise CheckCancelled("Check cancelled.")
        job = app.load_job(job_id)
        _set_check(
            job_id, app, status="running", progress=0.01,
            message="Reading the source", error=None,
        )

        def progress(fraction: float, message: str) -> None:
            if cancel.is_set():
                raise CheckCancelled("Check cancelled.")
            _set_check(
                job_id, app, status="running", progress=round(
                    max(0.01, min(0.99, float(fraction))), 4,
                ),
                message=message,
            )

        report = detect.run_check(
            job_id,
            job,
            app._job_dir(job_id),
            sampler=(
                pipeline.read_text_samples
                if options.get("sample_text", True) else None
            ),
            audio_extractor=pipeline.extract_audio,
            sample_text=bool(options.get("sample_text", True)),
            fps=float(options.get("fps") or detect.DEFAULT_SAMPLE_FPS),
            progress=progress,
        )
        recommendation = report.get("recommendation")
        tracklet_count = len(report.get("tracklets") or [])
        _set_check(
            job_id, app,
            status="ready",
            progress=1.0,
            message=(
                f"{tracklet_count} text "
                f"{'region' if tracklet_count == 1 else 'regions'} found"
            ),
            recommendation=recommendation,
            tracklet_count=tracklet_count,
            duration_s=round(time.time() - started, 3),
            report=detect.REPORT_DIR + "/" + detect.REPORT_FILE,
            error=None,
        )
        return report
    except (CheckCancelled, pipeline.stt.SttCancelled):
        _finish_cancelled(job_id, app)
        return detect.state_report(job, "cancelled")
    except Exception as exc:  # noqa: BLE001
        if cancel.is_set():
            _finish_cancelled(job_id, app)
            return detect.state_report(job, "cancelled")
        LOGGER.exception("check failed for %s", job_id)
        _set_check(
            job_id, app, status="failed", progress=1.0,
            message="Check failed", error=str(exc)[:2400],
        )
        return detect.state_report(job, "failed", error=str(exc)[:2400])
    finally:
        pipeline.stt.set_cancel_event(None)


@router.post("/api/jobs/{job_id}/check")
def start_check(job_id: str, body: CheckBody | None = None):
    body = body or CheckBody()
    app = _job_app()
    job = app.load_job(job_id)
    analysis = job.get("analysis") or {}
    analysis_ready = job.get("status") == "ready" and bool(analysis.get("scenes"))
    # Clean mode stops at source_ready with no analysis. Check samples the whole
    # source when scenes are empty, so it needs no invented scene.
    source_ready = job.get("status") == "source_ready" and not analysis
    if not analysis_ready and not source_ready:
        raise HTTPException(409, "Analysis is not ready yet.")
    app.require_source(job)

    record = _check_record(job)
    task_id = record.get("task_id")
    if record.get("status") in ACTIVE_STATES:
        task = CHECK_POOL.get(task_id) if task_id else None
        # A stale "running" record after a restart has no live task. Let the
        # next POST replace it instead of blocking forever.
        if task is not None and not task.terminal:
            return JSONResponse(
                _running_report(job, record["status"]), status_code=202,
            )
    ready = _ready_report(app, job)
    if ready is not None and not body.force:
        return ready

    options = {
        "sample_text": body.sample_text,
        "fps": body.fps,
    }
    CHECK_CANCELS[job_id] = threading.Event()
    _set_check(
        job_id, app, status="queued", progress=0.0,
        message="Queued for Check", error=None,
    )
    task = CHECK_POOL.submit(
        run_check_job, job_id, options,
        task_kind="check", task_key=job_id,
    )
    _set_check(job_id, app, task_id=task.id)
    after = app.load_job(job_id)
    ready = _ready_report(app, after)
    if ready is not None:
        return ready
    state = _check_record(after).get("status") or "queued"
    return JSONResponse(
        _running_report(after, state),
        status_code=500 if state == "failed" else 202,
        headers={"Location": f"/api/jobs/{job_id}/check"},
    )


@router.get("/api/jobs/{job_id}/check")
def get_check(job_id: str):
    app = _job_app()
    job = app.load_job(job_id)
    record = _check_record(job)
    if record.get("status") in ACTIVE_STATES:
        return JSONResponse(
            _running_report(job, record["status"]), status_code=202,
        )
    ready = _ready_report(app, job)
    if ready is not None:
        return ready
    if record.get("status") == "failed":
        return _running_report(job, "failed", error=record.get("error"))
    if record.get("status") == "cancelled":
        return _running_report(job, "cancelled")
    report = detect.load_report(app._job_dir(job_id))
    if report is not None:
        return report
    raise HTTPException(404, "Check has not run yet.")


@router.post("/api/jobs/{job_id}/check/cancel")
def cancel_check(job_id: str, request: Request) -> dict:
    """Stop Check. A queued pass is dropped at once; a running one stops at
    its next frame batch, and the job keeps the last finished report."""
    app = _job_app()
    if not app._setup_origin_ok(request):
        raise HTTPException(403, "Cross-site writes are blocked.")
    job = app.load_job(job_id)
    record = _check_record(job)
    if record.get("status") not in ACTIVE_STATES:
        return {"ok": True, "cancelled": False, "status": record.get("status")}
    CHECK_CANCELS.setdefault(job_id, threading.Event()).set()
    task_id = record.get("task_id")
    task = CHECK_POOL.get(task_id) if task_id else None
    if task is None or task.terminal or task.state is job_queue.QueueState.QUEUED:
        CHECK_POOL.cancel_key("check", job_id)
        job = _finish_cancelled(job_id, app)
    else:
        job = _set_check(job_id, app, message="Stopping…")
    return {"ok": True, "cancelled": True, "status": _check_record(job).get("status")}
