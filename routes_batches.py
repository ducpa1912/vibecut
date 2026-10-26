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
    size_bytes: object = None
    source_bytes: object = None


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
        try:
            disk.size_hint(
                item.size_bytes,
                label=f"Item {index + 1} size_bytes",
            )
            disk.size_hint(
                item.source_bytes,
                label=f"Item {index + 1} source_bytes",
            )
            disk.size_hint(
                (item.options or {}).get("size_bytes",
                    (item.options or {}).get("source_bytes")),
                label=f"Item {index + 1} size_bytes",
            )
        except disk.InvalidSize as exc:
            raise HTTPException(400, str(exc)) from exc


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
            "size_bytes": item.size_bytes,
            "source_bytes": item.source_bytes,
        }
        for item in body.items
    ]
    try:
        required = disk.estimate_batch(items)
    except disk.InvalidSize as exc:
        raise HTTPException(400, str(exc)) from exc
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


@router.post("/api/batches/{batch_id}/pause")
def pause_batch(batch_id: str) -> dict:
    try:
        return _manager().pause(batch_id)
    except batch.BatchNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
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
    """Idempotently requeue analysis or failed/interrupted renders.

    The status check and state transition happen in one ``update_job``
    mutator, so two simultaneous retry requests cannot both claim analysis.
    """
    claim = {"analysis": False, "renders": False, "error": None}
    job_id = str(job["id"])

    def mutate(value: dict) -> None:
        status = str(value.get("status") or "")
        if status in {"queued", "downloading", "scanning", "reading", "scoring"}:
            return
        if not value.get("analysis"):
            source = (value.get("source") or {}).get("path")
            if not source or not Path(str(source)).expanduser().is_file():
                claim["error"] = (
                    "This job has no local source to retry. "
                    "Start a new URL download."
                )
                return
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
            claim["analysis"] = True
            return
        if status != "ready":
            value["status"] = "ready"
            value["message"] = "Ready"
            value["error"] = None
        claim["renders"] = True

    updated = app.update_job(job_id, mutate)
    if claim["error"]:
        raise HTTPException(409, claim["error"])
    if claim["analysis"]:
        app.ANALYSIS_CANCELS.pop(job_id, None)
        app.analysis_pool.submit(app.run_analysis, job_id)
        return True, 0
    if claim["renders"]:
        return False, _retry_renders(app, updated)
    return False, 0


def _retry_snapshot(record: dict) -> dict:
    snapshot = record.get("plan_snapshot")
    return snapshot if isinstance(snapshot, dict) else {}


def _retry_clip_seconds(clip: dict) -> float:
    value = clip.get("dur", clip.get("duration"))
    if value is not None:
        try:
            return float(value)
        except (TypeError, ValueError):
            pass
    try:
        return max(
            0.0,
            float(clip.get("end") or 0.0) - float(clip.get("start") or 0.0),
        )
    except (TypeError, ValueError):
        return 0.0


def _retry_snapshot_clips(record: dict) -> list[dict] | None:
    """Validate stored plan clips without consulting the current analysis."""
    snapshot = _retry_snapshot(record)
    clips = snapshot.get("clips")
    if not isinstance(clips, list) or not clips:
        return None
    cleaned: list[dict] = []
    for clip in clips:
        if not isinstance(clip, dict):
            return None
        try:
            int(clip.get("scene"))
            start = float(clip.get("start"))
            end = clip.get("end")
            if end is None:
                duration = clip.get("dur", clip.get("duration"))
                if duration is None:
                    return None
                end = start + float(duration)
            else:
                end = float(end)
        except (TypeError, ValueError):
            return None
        if end <= start:
            return None
        cleaned.append(dict(clip))
    return cleaned


def _clip_set_story_rows(app, job: dict) -> list[tuple[str, str, dict]]:
    rows: list[tuple[str, str, dict]] = []
    for record in app._clip_set_records(job):
        if not isinstance(record, dict):
            continue
        set_id = str(record.get("id") or "")
        for story in record.get("stories") or []:
            if not isinstance(story, dict):
                continue
            story_id = str(story.get("id") or "")
            if story_id:
                rows.append((set_id, story_id, story))
    return rows


def _story_key_matches(record_key: str, story_ids: set[str]) -> list[str]:
    key = str(record_key or "")
    return sorted(
        story_id for story_id in story_ids
        if story_id and key.endswith(f":s{story_id}")
    )


def _story_id_from_record_key(record_key: str) -> str | None:
    _prefix, marker, suffix = str(record_key or "").rpartition(":s")
    if not marker or not suffix:
        return None
    if ":" in suffix or "/" in suffix:
        return None
    return suffix


def _resolve_retry_story_identity(
    app,
    job: dict,
    record_key: str,
    record: dict,
    target: int,
    snapshot: dict,
    clips: list[dict] | None,
) -> tuple[str | None, str | None, bool]:
    """Resolve a story render's stored identity without trusting the caller.

    Public plan/render bodies cannot carry a story id. A retry may only use the
    id stored on the record, the id embedded in its record key, or an
    unambiguous exact clip-set match.
    """
    rows = _clip_set_story_rows(app, job)
    story_ids = {row[1] for row in rows}
    job_id = str(job.get("id") or "")
    key_matches = [
        story_id for story_id in _story_key_matches(record_key, story_ids)
        if story_id != job_id
    ]
    if len(key_matches) > 1:
        raise HTTPException(
            409,
            f"Could not retry render {record_key}: "
            "its record key matches more than one story.",
        )
    key_story = key_matches[0] if key_matches else _story_id_from_record_key(record_key)
    if key_story == job_id:
        # A legacy recovery could write the job id into the key as a fake
        # story suffix. It is never a story identity.
        key_story = None
    explicit_story = str(
        record.get("story_id") or snapshot.get("story_id") or ""
    )
    if explicit_story and explicit_story == job_id:
        # Older recovery wrote the job id where build_spec fell back to it.
        # That is not a story identity.
        explicit_story = ""
    explicit_set = str(record.get("set_id") or snapshot.get("set_id") or "")
    if explicit_story and key_story and explicit_story != key_story:
        raise HTTPException(
            409,
            f"Could not retry render {record_key}: "
            "its stored story id conflicts with its record key.",
        )
    story_id = explicit_story or key_story or ""
    set_id = explicit_set
    storyish = bool(story_id or set_id) or target not in (15, 30, 60)
    if story_id:
        if set_id:
            exact = [
                row for row in rows
                if row[0] == set_id and row[1] == story_id
            ]
            if exact:
                return story_id, set_id, True
            if rows:
                raise HTTPException(
                    409,
                    f"Could not retry render {record_key}: "
                    "its stored story is not in the stored clip set.",
                )
            return story_id, set_id, True
        matches = [row for row in rows if row[1] == story_id]
        if len(matches) == 1:
            return story_id, matches[0][0], True
        if len(matches) > 1:
            raise HTTPException(
                409,
                f"Could not retry render {record_key}: "
                "its story id is ambiguous across clip sets.",
            )
        if rows:
            raise HTTPException(
                409,
                f"Could not retry render {record_key}: "
                "its stored story is not in any clip set.",
            )
        return story_id, None, True
    # Clip-hash inference is only safe when the record already looks like a
    # story: explicit set/marker, or a non-preset target. A normal 15/30/60
    # retry must never be reclassified just because a story shares its cut.
    if not storyish:
        return None, None, False
    pool = rows
    if set_id:
        pool = [row for row in rows if row[0] == set_id]
        if rows and not pool:
            raise HTTPException(
                409,
                f"Could not retry render {record_key}: "
                "its stored clip set no longer exists.",
            )
    if clips:
        signature = app.caption_engine.clip_hash(clips)
        candidates = []
        for row_set, row_story, story in pool:
            story_duration = story.get("dur")
            if story_duration is None:
                story_duration = sum(
                    _retry_clip_seconds(clip)
                    for clip in story.get("clips") or []
                    if isinstance(clip, dict)
                )
            try:
                story_target = int(round(float(story_duration or 0.0)))
            except (TypeError, ValueError):
                continue
            if story_target != target:
                continue
            if app.caption_engine.clip_hash(story.get("clips") or []) != signature:
                continue
            candidates.append((row_set, row_story))
        if len(candidates) == 1:
            return candidates[0][1], candidates[0][0], True
        if len(candidates) > 1:
            raise HTTPException(
                409,
                f"Could not retry render {record_key}: "
                "its story identity is ambiguous.",
            )
    raise HTTPException(
        409,
        f"Could not retry render {record_key}: "
        "its story identity is missing.",
    )


def _retry_plan(
    app,
    fresh: dict,
    target: int,
    body,
    record: dict,
    clips: list[dict] | None,
    is_story: bool,
) -> dict:
    """Rebuild the stored plan exactly; never fall back to a current default."""
    snapshot = _retry_snapshot(record)
    if clips:
        auto = (
            bool(snapshot.get("auto"))
            if "auto" in snapshot
            else not is_story
        )
        return {
            "target": int(target),
            "total": round(sum(
                _retry_clip_seconds(clip)
                for clip in clips
            ), 3),
            "hook_scene": snapshot.get("hook_scene", record.get("hook")),
            "auto": auto,
            "clip_count": len(clips),
            "clips": clips,
            "order": str(snapshot.get("order") or record.get("order") or "source"),
        }
    if is_story:
        raise HTTPException(
            409,
            "Could not retry story render: its stored plan clips are missing.",
        )
    return app._plan_for_body(fresh, target, body)


def _retry_renders(app, job: dict) -> int:
    count = 0
    for record_key, record in list((job.get("renders") or {}).items()):
        if not isinstance(record, dict):
            continue
        if record.get("status") not in {"failed", "interrupted"}:
            continue
        try:
            target = int(record.get("target") or 0)
        except (TypeError, ValueError):
            continue
        # Story renders use their stored duration (1-180s), not only the
        # legacy 15/30/60 presets.
        if target < 1 or target > 180:
            continue
        if record.get("recoverable") is False:
            raise HTTPException(
                409,
                f"Could not retry render {record_key}: "
                f"{record.get('recovery_error') or 'its stored plan is incomplete.'}",
            )
        snapshot = _retry_snapshot(record)
        clips = _retry_snapshot_clips(record)
        job_id = str(job.get("id") or "")
        raw_explicit_story = str(
            record.get("story_id") or snapshot.get("story_id") or ""
        )
        raw_key_story = _story_id_from_record_key(str(record_key))
        legacy_fake_story = bool(
            job_id
            and job_id in {raw_explicit_story, raw_key_story}
        )
        story_id, set_id, is_story = _resolve_retry_story_identity(
            app, job, str(record_key), record, target, snapshot, clips,
        )
        if is_story and not clips:
            raise HTTPException(
                409,
                f"Could not retry render {record_key}: "
                "its stored plan clips are missing.",
            )
        caption_track = None
        if record.get("captions"):
            track_id = str(record.get("caption_track_id") or "")
            if track_id:
                try:
                    caption_track = app._caption_track_by_id(
                        str(job["id"]), track_id,
                    )
                except HTTPException as exc:
                    raise HTTPException(
                        409,
                        f"Could not retry render {record_key}: "
                        f"{str(exc.detail)[:240]}",
                    ) from exc
            elif is_story:
                # A story retry must not silently build a new default track.
                raise HTTPException(
                    409,
                    f"Could not retry render {record_key}: "
                    "its caption track is missing.",
                )
        fresh = app.load_job(str(job["id"]))
        try:
            body = _retry_body(app, record, target)
            plan = _retry_plan(
                app, fresh, target, body, record, clips, is_story,
            )
            # Identity is attached only after the stored plan is rebuilt.
            if story_id:
                plan["story_id"] = story_id
            if set_id:
                plan["clip_set_id"] = set_id
            if (
                legacy_fake_story
                and not story_id
                and ":h" not in str(record_key)
            ):
                # e4476d0 recovery hardcoded auto=False and derived a fake
                # story key without a hook marker. The key proves the original
                # plan was automatic; restore that so retry returns to "30".
                plan["auto"] = True
            quality, aspect, encoder, captions, audio_plan, preset, margin = (
                app._render_options(body)
            )
            queued_record = app._queue_render(
                str(job["id"]), fresh, plan, quality, aspect, encoder, captions,
                audio_plan, False, preset=preset, caption_margin=margin,
                script_id=body.script_id, check_space=True,
                caption_track=caption_track,
            )
            new_record = queued_record or {}
            new_key = str(new_record.get("record_key") or "")
            if new_key and new_key != record_key:
                def migrate(value: dict) -> None:
                    renders = value.get("renders")
                    if not isinstance(renders, dict):
                        return
                    renders.pop(record_key, None)
                    current = renders.get(new_key)
                    if isinstance(current, dict):
                        current["attempts"] = max(
                            int(current.get("attempts") or 0),
                            int(record.get("attempts") or 0) + 1,
                        )

                app.update_job(str(job["id"]), migrate)
            count += 1
        except HTTPException as exc:
            if exc.status_code == 409 and "already rendering" in str(exc.detail):
                # Another retry request or a live render already owns it.
                continue
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
    snapshot = _retry_snapshot(record)
    clips = _retry_snapshot_clips(record)
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
        caption_track_id=record.get("caption_track_id"),
    )


class _AppBackend:
    """Concrete batch backend backed by app.py job/render helpers."""

    def create_job(self, item: dict) -> dict:
        import app

        options = dict(item.get("options") or {})
        requested_id = item.get("job_id")
        if item.get("url"):
            result = app.job_from_url(app.FromUrlBody(
                url=str(item["url"]),
                options=options,
                job_id=str(requested_id) if requested_id else None,
            ))
        else:
            result = app.job_from_path(app.PathBody(
                path=str(item["path"]),
                options=options,
                job_id=str(requested_id) if requested_id else None,
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

        if str(job.get("status") or "") in app.LIVE:
            app._analysis_cancel_event(job_id).set()

        analysis_find = getattr(app.analysis_pool, "find_key", None)
        analysis = analysis_find("analysis", job_id) if analysis_find else None
        if analysis is not None:
            was_queued = str(analysis.status) == "queued"
            app.analysis_pool.cancel_key("analysis", job_id)
            if was_queued:
                def cancel_analysis(value: dict) -> None:
                    value["status"] = "cancelled"
                    value["message"] = "Cancelled"
                    value["error"] = None
                    ingest = value.get("ingest")
                    if isinstance(ingest, dict):
                        ingest.update({
                            "phase": "cancelled",
                            "status": "cancelled",
                            "progress": 1.0,
                            "message": "Cancelled",
                            "error": None,
                        })

                try:
                    app.update_job(job_id, cancel_analysis)
                except Exception:  # noqa: BLE001
                    LOGGER.exception("could not mark job %s cancelled", job_id)

        for record_key, record in list((job.get("renders") or {}).items()):
            if not isinstance(record, dict):
                continue
            if record.get("status") not in app.ACTIVE_RENDER:
                continue
            key = f"render:{job_id}:{record_key}"
            render_find = getattr(app.render_pool, "find_key", None)
            task = render_find("render", key) if render_find else None
            was_queued = bool(task is not None and str(task.status) == "queued")
            if hasattr(app.render_pool, "cancel_key"):
                app.render_pool.cancel_key("render", key)
            cancel = app.RENDER_CANCELS.get((job_id, record_key))
            if cancel is not None:
                cancel.set()
            if was_queued:
                app._set_render(
                    job_id, record_key,
                    status="cancelled", progress=1.0,
                    message="Cancelled", error=None, eta=None,
                )

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
            quality, aspect, _encoder, captions, audio_plan, preset, _margin = (
                app._render_options(body)
            )
            expected_audio = app._audio_signature(audio_plan)
            expected_hook = options.get("hook_scene")
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
                if str(record.get("audio_sig") or "") != expected_audio:
                    continue
                if preset is not None and record.get("preset") != preset:
                    continue
                if expected_hook is not None and record.get("hook") != expected_hook:
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
