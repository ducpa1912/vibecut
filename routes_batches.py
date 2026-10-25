"""HTTP surface for durable local batches and job retry."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import batch
import disk

LOGGER = logging.getLogger("vibecut.routes.batches")
router = APIRouter()


class BatchItemBody(BaseModel):
    path: str | None = None
    url: str | None = None
    options: dict = {}
    targets: list[int] | None = None


class BatchBody(BaseModel):
    name: str = ""
    items: list[BatchItemBody] = []
    max: int = batch.MAX_ITEMS


def _backend():
    return _AppBackend()


def _manager() -> batch.BatchManager:
    import app

    return batch.manager_for(app.DATA, _backend())


def _validate_body(body: BatchBody) -> None:
    if body.max < 1 or body.max > batch.MAX_ITEMS:
        raise HTTPException(400, "max must be between 1 and 10.")
    if not body.items:
        raise HTTPException(400, "A batch needs at least one item.")
    if len(body.items) > batch.MAX_ITEMS:
        raise HTTPException(400, "A batch can contain at most 10 items.")
    if len(body.items) > body.max:
        raise HTTPException(400, f"This batch allows at most {body.max} items.")
    for index, item in enumerate(body.items):
        if bool(item.path) == bool(item.url):
            raise HTTPException(
                400,
                f"Item {index + 1} needs exactly one of path or url.",
            )


@router.post("/api/batches")
def create_batch(body: BatchBody) -> dict:
    import app

    _validate_body(body)
    items = [
        {
            "path": item.path,
            "url": item.url,
            "options": dict(item.options or {}),
            "targets": item.targets,
        }
        for item in body.items
    ]
    required = disk.estimate_batch(items)
    disk.preflight(required, app.DATA)
    manager = _manager()
    try:
        created = manager.create(
            body.name,
            items,
            max_items=body.max,
            start=False,
        )
    except batch.BatchError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    try:
        return manager.start(str(created["id"]))
    except batch.BatchError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.get("/api/batches")
def list_batches() -> dict:
    return {"batches": _manager().list()}


@router.get("/api/batches/{batch_id}")
def get_batch(batch_id: str) -> dict:
    try:
        return _manager().get(batch_id)
    except batch.BatchNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except batch.BatchError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.post("/api/batches/{batch_id}/resume")
def resume_batch(batch_id: str) -> dict:
    try:
        return _manager().resume(batch_id)
    except batch.BatchNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except batch.BatchConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except batch.BatchError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.post("/api/batches/{batch_id}/cancel")
def cancel_batch(batch_id: str) -> dict:
    try:
        return _manager().cancel(batch_id)
    except batch.BatchNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except batch.BatchError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: str) -> dict:
    import app

    job = app.load_job(job_id)
    analysis_retried, renders_retried = _retry_job(app, job)
    latest = app.load_job(job_id)
    value = app.public_job(latest)
    value["retried"] = bool(analysis_retried or renders_retried)
    value["retry"] = {
        "analysis": bool(analysis_retried),
        "renders": int(renders_retried),
    }
    return value


def _retry_job(app, job: dict) -> tuple[bool, int]:
    """Idempotently requeue analysis or failed/interrupted renders."""
    status = str(job.get("status") or "")
    if status in {"queued", "downloading", "scanning", "reading", "scoring"}:
        return False, 0

    if not job.get("analysis"):
        source = (job.get("source") or {}).get("path")
        if not source or not Path(str(source)).expanduser().is_file():
            raise HTTPException(
                409,
                "This job has no local source to retry. Start a new URL download.",
            )

        def mutate(value: dict) -> None:
            attempts = value.get("attempts")
            if not isinstance(attempts, dict):
                attempts = {}
                value["attempts"] = attempts
            attempts["analysis"] = int(attempts.get("analysis") or 0) + 1
            value["status"] = "queued"
            value["progress"] = 0.0
            value["message"] = "Queued for retry"
            value["error"] = None
            ingest = value.get("ingest")
            if isinstance(ingest, dict) and ingest.get("status") in {
                "failed", "interrupted",
            }:
                ingest.update({
                    "phase": "queued",
                    "status": "queued",
                    "progress": 0.0,
                    "message": "Queued for retry",
                    "error": None,
                })

        app.update_job(str(job["id"]), mutate)
        app.analysis_pool.submit(app.run_analysis, str(job["id"]))
        return True, 0

    if status in {"interrupted", "failed"}:
        def restore(value: dict) -> None:
            value["status"] = "ready"
            value["message"] = "Ready"
            value["error"] = None

        job = app.update_job(str(job["id"]), restore)
    return False, _retry_renders(app, job)


def _retry_renders(app, job: dict) -> int:
    count = 0
    for record_key, record in list((job.get("renders") or {}).items()):
        if not isinstance(record, dict):
            continue
        if record.get("status") not in {"failed", "interrupted"}:
            continue
        target = int(record.get("target") or 0)
        if target not in (15, 30, 60):
            continue
        fresh = app.load_job(str(job["id"]))
        try:
            body = _retry_body(app, record, target)
            plan = app._plan_for_body(fresh, target, body)
            quality, aspect, encoder, captions, audio_plan, preset, margin = (
                app._render_options(body)
            )
            app._queue_render(
                str(job["id"]), fresh, plan, quality, aspect, encoder, captions,
                audio_plan, False, preset=preset, caption_margin=margin,
                script_id=body.script_id, check_space=True,
            )
            count += 1
        except HTTPException:
            raise
        except disk.InsufficientSpace:
            raise
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("could not retry render %s for %s", record_key, job["id"])
            raise HTTPException(
                409,
                f"Could not retry render {record_key}: {str(exc)[:240]}",
            ) from exc
    return count


def _retry_body(app, record: dict, target: int):
    snapshot = record.get("plan_snapshot")
    if not isinstance(snapshot, dict):
        snapshot = {}
    clips = snapshot.get("clips") if snapshot.get("auto") is False else None
    encoder = record.get("encoder")
    return app.PlanBody(
        target=target,
        hook_scene=snapshot.get("hook_scene", record.get("hook")),
        quality=str(record.get("quality") or "final"),
        aspect=str(record.get("aspect") or "9:16"),
        encoder=None if encoder in (None, "", "auto") else str(encoder),
        captions=bool(record.get("captions")),
        clips=clips if isinstance(clips, list) else None,
        audio=record.get("audio") if isinstance(record.get("audio"), dict) else None,
        preset=record.get("preset"),
        order=str(record.get("order") or "source"),
        caption_margin=record.get("caption_margin"),
        script_id=record.get("script_id"),
    )


class _AppBackend:
    """Concrete batch backend backed by app.py job/render helpers."""

    def create_job(self, item: dict) -> dict:
        import app

        options = dict(item.get("options") or {})
        if item.get("url"):
            result = app.job_from_url(app.FromUrlBody(
                url=str(item["url"]),
                options=options,
            ))
        else:
            result = app.job_from_path(app.PathBody(
                path=str(item["path"]),
                options=options,
            ))
        return app.load_job(str(result["id"]))

    def load_job(self, job_id: str) -> dict:
        import app

        return app.load_job(job_id)

    def retry_job(self, job_id: str) -> dict:
        import app

        job = app.load_job(job_id)
        _retry_job(app, job)
        return app.load_job(job_id)

    def cancel_job(self, job_id: str) -> None:
        import app

        try:
            job = app.load_job(job_id)
        except Exception:  # noqa: BLE001
            return
        event = app.INGEST_CANCELS.get(job_id)
        if event is not None:
            event.set()
        if job.get("status") == "downloading":
            try:
                app.cancel_url_ingest(job_id)
            except Exception:  # noqa: BLE001
                LOGGER.exception("could not cancel URL ingest for %s", job_id)
        for (active_job, _record_key), cancel in list(app.RENDER_CANCELS.items()):
            if active_job == job_id:
                cancel.set()

    def start_renders(
        self, job_id: str, targets: list[int], options: dict
    ) -> list[dict]:
        import app

        job = app.load_job(job_id)
        records: list[dict] = []
        for target in targets:
            body = _render_body(app, target, options)
            plan = app._plan_for_body(job, target, body)
            quality, aspect, encoder, captions, audio_plan, preset, margin = (
                app._render_options(body)
            )
            records.append(app._queue_render(
                job_id, job, plan, quality, aspect, encoder, captions,
                audio_plan, False, preset=preset, caption_margin=margin,
                script_id=body.script_id, check_space=True,
            ))
        return records

    def render_states(
        self, job_id: str, targets: list[int], options: dict
    ) -> dict[int, str]:
        import app

        job = app.load_job(job_id)
        records = list((job.get("renders") or {}).values())
        records.sort(
            key=lambda value: value.get("updated") or value.get("created") or 0,
            reverse=True,
        )
        result: dict[int, str] = {}
        for target in targets:
            body = _render_body(app, target, options)
            quality, aspect, _encoder, captions, _audio, _preset, _margin = (
                app._render_options(body)
            )
            matching = []
            for record in records:
                if not isinstance(record, dict):
                    continue
                try:
                    record_target = int(record.get("target") or 0)
                except (TypeError, ValueError):
                    continue
                if record_target != target:
                    continue
                if str(record.get("quality") or "final") != quality:
                    continue
                if str(record.get("aspect") or "9:16") != aspect:
                    continue
                if bool(record.get("captions")) != bool(captions):
                    continue
                matching.append(record)
            latest = matching[0] if matching else None
            result[target] = str((latest or {}).get("status") or "missing")
        return result


def _render_body(app, target: int, options: dict):
    return app.PlanBody(
        target=int(target),
        hook_scene=options.get("hook_scene"),
        quality=str(options.get("quality") or "final"),
        aspect=str(options.get("aspect") or "9:16"),
        encoder=options.get("encoder"),
        captions=bool(options.get("captions")),
        audio=options.get("audio") if isinstance(options.get("audio"), dict) else None,
        preset=options.get("preset"),
        order=str(options.get("order") or "source"),
        caption_margin=options.get("caption_margin"),
        script_id=options.get("script_id"),
    )
