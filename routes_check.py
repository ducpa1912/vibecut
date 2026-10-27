"""HTTP surface for Source Check.

``POST /api/jobs/{id}/check`` starts one Check pass; ``GET`` returns its
``SourceReport``. The pass runs on its own single-worker scheduler so a long
0.5 fps text sample never blocks the analysis or render queues.

The report is stored under ``jobs/<id>/check/source_report.json`` and its
summary on ``job["check"]``. A report is trusted only when ``status`` is
``ready`` and ``text.confirmed`` is true; while a pass is queued or running the
endpoint returns a ``SourceReport``-shaped envelope with ``complete: false``.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException
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


class CheckBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    force: bool = False
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


def run_check_job(job_id: str, options: dict) -> dict:
    """Worker entry point. Always persists a terminal state on the job."""
    app = _job_app()
    started = time.time()
    job = {"id": job_id}
    try:
        job = app.load_job(job_id)
        _set_check(
            job_id, app, status="running", progress=0.01,
            message="Reading the source", error=None,
        )

        def progress(fraction: float, message: str) -> None:
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
            attestation=options.get("attestation"),
            sample_text=bool(options.get("sample_text", True)),
            fps=float(options.get("fps") or detect.DEFAULT_SAMPLE_FPS),
            progress=progress,
        )
        recommendation = report.get("recommendation")
        _set_check(
            job_id, app,
            status="ready",
            progress=1.0,
            message=(
                f"{len(report.get('tracklets') or [])} text regions · "
                f"{recommendation}"
            ),
            recommendation=recommendation,
            tracklet_count=len(report.get("tracklets") or []),
            duration_s=round(time.time() - started, 3),
            report=detect.REPORT_DIR + "/" + detect.REPORT_FILE,
            error=None,
        )
        return report
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("check failed for %s", job_id)
        _set_check(
            job_id, app, status="failed", progress=1.0,
            message="Check failed", error=str(exc)[:2400],
        )
        return detect.state_report(job, "failed", error=str(exc)[:2400])


@router.post("/api/jobs/{job_id}/check")
def start_check(job_id: str, body: CheckBody | None = None):
    body = body or CheckBody()
    app = _job_app()
    job = app.load_job(job_id)
    analysis = job.get("analysis") or {}
    if job.get("status") != "ready" or not analysis.get("scenes"):
        raise HTTPException(409, "Analysis is not ready yet.")

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
        "attestation": body.attestation,
        "sample_text": body.sample_text,
        "fps": body.fps,
    }
    _set_check(
        job_id, app, status="queued", progress=0.0,
        message="Queued for Check", error=None, attestation=body.attestation,
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
    report = detect.load_report(app._job_dir(job_id))
    if report is not None:
        return report
    raise HTTPException(404, "Check has not run yet.")
