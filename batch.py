"""Durable local batch manifests and a sequential batch runner.

A batch is a JSON file at ``data/batches/<batch_id>.json``.  It holds at most
ten items, each of which is a path or URL plus analysis/render options.  One
runner thread processes items strictly in order, waits for each job to finish
and isolates item failures: a failed item does not cancel the rest of the
batch.

The runner talks to the application through a small backend protocol so the
manifest and ordering rules can be tested without ffmpeg or FastAPI:

``create_job(item)``
    Create a job from ``item["path"]`` or ``item["url"]`` and return its job
    record.
``load_job(job_id)``
    Return the latest job record.
``retry_job(job_id)``
    Requeue an interrupted/failed analysis or render.
``cancel_job(job_id)``
    Best-effort cancellation of active ingest/render work.
``start_renders(job_id, targets, options)``
    Queue the requested render targets.  It must be idempotent for outputs
    that are already ready.
``render_states(job_id, targets, options)``
    Return ``{target: "ready"|"queued"|"running"|"failed"|...}``.

Restart semantics: :func:`recover_batches` turns an active batch into
``paused`` and any running item into ``paused``.  Resume requeues paused items;
done items and their outputs are left untouched.  A render retry starts from
the existing segment cache; no partial ffmpeg output is resumed.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Mapping, Protocol

LOGGER = logging.getLogger("vibecut.batch")

MAX_ITEMS = 10
BATCH_STATES = ("queued", "running", "paused", "done", "failed", "cancelled")
ITEM_STATES = ("queued", "running", "paused", "done", "failed", "cancelled")
TERMINAL_ITEM_STATES = frozenset({"done", "failed", "cancelled"})
ACTIVE_BATCH_STATES = frozenset({"queued", "running"})
VALID_TARGETS = (15, 30, 60)
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class BatchError(RuntimeError):
    """Invalid batch request or manifest."""

    status_code = 400


class BatchNotFound(BatchError):
    status_code = 404


class BatchConflict(BatchError):
    status_code = 409


class BatchItemError(RuntimeError):
    """One item failed; the batch continues."""


class _BatchCancelled(RuntimeError):
    pass


class BatchBackend(Protocol):
    def create_job(self, item: dict) -> dict: ...

    def load_job(self, job_id: str) -> dict: ...

    def retry_job(self, job_id: str) -> dict: ...

    def cancel_job(self, job_id: str) -> None: ...

    def start_renders(
        self, job_id: str, targets: list[int], options: dict
    ) -> list[dict]: ...

    def render_states(
        self, job_id: str, targets: list[int], options: dict
    ) -> dict[int, str]: ...


def _now() -> float:
    return round(time.time(), 3)


def _error_text(exc: BaseException) -> str:
    detail = getattr(exc, "detail", None)
    if detail not in (None, ""):
        return str(detail)[:2400]
    return str(exc)[:2400]


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return json.loads(json.dumps(value, default=str))


def normalize_targets(value) -> list[int]:
    """Return validated render targets in the canonical 15/30/60 order."""
    if value is None or value == "":
        return []
    if isinstance(value, (int, str)):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        raise BatchError("targets must be a list of 15, 30 or 60.")
    selected: set[int] = set()
    for raw in value:
        try:
            target = int(raw)
        except (TypeError, ValueError):
            raise BatchError("targets must contain only 15, 30 or 60.") from None
        if target not in VALID_TARGETS:
            raise BatchError("targets must contain only 15, 30 or 60.")
        selected.add(target)
    return [target for target in VALID_TARGETS if target in selected]


def _atomic_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        temp.write_text(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _read_manifest(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BatchError(f"Batch data is unreadable: {path.name}") from exc
    if not isinstance(value, dict):
        raise BatchError(f"Batch data is invalid: {path.name}")
    return value


def _counts(batch: dict) -> dict:
    counts = {state: 0 for state in ITEM_STATES}
    for item in batch.get("items") or []:
        state = str(item.get("state") or "queued")
        counts[state] = counts.get(state, 0) + 1
    return counts


def _progress(batch: dict) -> float:
    items = batch.get("items") or []
    if not items:
        return 0.0
    terminal = sum(
        1 for item in items if item.get("state") in TERMINAL_ITEM_STATES
    )
    return round(terminal / len(items), 4)


def public_batch(batch: dict) -> dict:
    """Copy the manifest and add derived counts/progress."""
    value = json.loads(json.dumps(batch, ensure_ascii=False))
    value["counts"] = _counts(batch)
    value["progress"] = _progress(batch)
    value["item_count"] = len(batch.get("items") or [])
    return value


def recover_batches(data_dir: str | Path) -> int:
    """Mark active batch manifests paused after a restart.

    Running items become paused.  Queued items stay queued so resume can pick
    them up in order.  Finished items and their outputs are not changed.
    """
    directory = Path(data_dir).expanduser() / "batches"
    if not directory.is_dir():
        return 0
    changed = 0
    for path in sorted(directory.glob("*.json")):
        try:
            batch = _read_manifest(path)
        except BatchError:
            LOGGER.exception("could not recover batch %s", path)
            continue
        touched = False
        if batch.get("status") in ACTIVE_BATCH_STATES:
            batch["status"] = "paused"
            batch["message"] = "Paused after restart"
            batch["error"] = "The server restarted while this batch was active."
            batch["current"] = None
            touched = True
        for item in batch.get("items") or []:
            if item.get("state") == "running":
                item["state"] = "paused"
                item["message"] = "Paused after restart"
                touched = True
        if touched:
            batch["updated"] = _now()
            batch["progress"] = _progress(batch)
            _atomic_write(path, batch)
            changed += 1
    return changed


class BatchManager:
    """Own one data directory and its sequential batch runner threads."""

    def __init__(
        self,
        data_dir: str | Path,
        backend: BatchBackend | None = None,
        *,
        poll_interval: float = 0.25,
    ) -> None:
        self.data_dir = Path(data_dir).expanduser()
        self.directory = self.data_dir / "batches"
        self.backend = backend
        self.poll_interval = max(0.01, float(poll_interval))
        self._lock = threading.RLock()
        self._threads: dict[str, threading.Thread] = {}
        self._running: set[str] = set()
        self._cancels: dict[str, threading.Event] = {}

    # -- storage --------------------------------------------------------
    def _path(self, batch_id: str) -> Path:
        if not batch_id or not _ID_RE.match(str(batch_id)):
            raise BatchNotFound("Batch not found.")
        return self.directory / f"{batch_id}.json"

    def load(self, batch_id: str) -> dict:
        path = self._path(batch_id)
        if not path.is_file():
            raise BatchNotFound("Batch not found.")
        with self._lock:
            return _read_manifest(path)

    def save(self, batch: dict) -> dict:
        batch_id = str(batch.get("id") or "")
        path = self._path(batch_id)
        with self._lock:
            batch["updated"] = _now()
            batch["progress"] = _progress(batch)
            _atomic_write(path, batch)
        return batch

    def create(
        self,
        name: str,
        items: list[Mapping],
        *,
        max_items: int = MAX_ITEMS,
        start: bool = False,
    ) -> dict:
        """Validate and persist a batch.  Call ``start`` to run it."""
        try:
            limit = int(max_items)
        except (TypeError, ValueError):
            raise BatchError("max must be an integer from 1 to 10.") from None
        if limit < 1 or limit > MAX_ITEMS:
            raise BatchError("max must be between 1 and 10.")
        if not items:
            raise BatchError("A batch needs at least one item.")
        if len(items) > MAX_ITEMS:
            raise BatchError("A batch can contain at most 10 items.")
        if len(items) > limit:
            raise BatchError(f"This batch allows at most {limit} items.")

        now = _now()
        batch_id = uuid.uuid4().hex[:12]
        while self._path(batch_id).exists():
            batch_id = uuid.uuid4().hex[:12]
        normalized: list[dict] = []
        for index, raw in enumerate(items):
            if not isinstance(raw, Mapping):
                raise BatchError(f"Item {index + 1} is not an object.")
            path = str(raw.get("path") or "").strip()
            url = str(raw.get("url") or "").strip()
            if bool(path) == bool(url):
                raise BatchError(
                    f"Item {index + 1} needs exactly one of path or url."
                )
            options = raw.get("options")
            if options is None:
                options = {}
            if not isinstance(options, Mapping):
                raise BatchError(f"Item {index + 1} options must be an object.")
            options = _json_safe(dict(options))
            targets = normalize_targets(
                raw.get("targets")
                or options.get("targets")
                or options.get("render_targets")
            )
            normalized.append({
                "id": uuid.uuid4().hex[:8],
                "index": index,
                "path": path or None,
                "url": url or None,
                "options": options,
                "targets": targets,
                "state": "queued",
                "attempts": 0,
                "job_id": None,
                "error": None,
                "message": "Queued",
                "outputs": [],
                "created": now,
                "updated": now,
                "started": None,
                "finished": None,
            })

        clean_name = str(name or "").strip() or time.strftime("Batch %Y-%m-%d %H:%M")
        batch = {
            "id": batch_id,
            "name": clean_name[:200],
            "created": now,
            "updated": now,
            "status": "queued",
            "progress": 0.0,
            "current": None,
            "max": limit,
            "message": "Queued",
            "error": None,
            "finished": None,
            "items": normalized,
        }
        self.save(batch)
        if start:
            return self.start(batch_id)
        return public_batch(batch)

    def list(self) -> list[dict]:
        if not self.directory.is_dir():
            return []
        values: list[dict] = []
        for path in self.directory.glob("*.json"):
            try:
                values.append(public_batch(_read_manifest(path)))
            except BatchError:
                LOGGER.exception("could not read batch %s", path)
        values.sort(key=lambda item: item.get("created") or 0, reverse=True)
        return values

    def get(self, batch_id: str) -> dict:
        return public_batch(self.load(batch_id))

    # -- lifecycle ------------------------------------------------------
    def start(self, batch_id: str) -> dict:
        """Start or restart the runner for a queued/paused manifest."""
        with self._lock:
            batch = self.load(batch_id)
            thread = self._threads.get(batch_id)
            if batch_id in self._running and thread and thread.is_alive():
                return public_batch(batch)
            if batch.get("status") == "cancelled":
                raise BatchConflict("This batch was cancelled.")
            if batch.get("status") == "done":
                return public_batch(batch)
            if not any(item.get("state") == "queued" for item in batch.get("items") or []):
                if batch.get("status") in {"failed", "paused"}:
                    # Nothing safe left to run.
                    return public_batch(batch)
            batch["status"] = "queued"
            batch["message"] = "Queued"
            batch["error"] = None
            batch["current"] = None
            batch["finished"] = None
            self.save(batch)
            event = threading.Event()
            self._cancels[batch_id] = event
            thread = threading.Thread(
                target=self._run_batch,
                args=(batch_id, event),
                name=f"vibecut-batch-{batch_id}",
                daemon=True,
            )
            self._running.add(batch_id)
            self._threads[batch_id] = thread
            thread.start()
        return self.get(batch_id)

    def resume(self, batch_id: str) -> dict:
        """Requeue paused work and start the runner.  Done items stay done."""
        with self._lock:
            batch = self.load(batch_id)
            thread = self._threads.get(batch_id)
            if batch_id in self._running and thread and thread.is_alive():
                return public_batch(batch)
            if batch.get("status") == "cancelled":
                raise BatchConflict("This batch was cancelled; create a new batch.")
            requeued = False
            for item in batch.get("items") or []:
                if item.get("state") in {"paused", "running"}:
                    item["state"] = "queued"
                    item["message"] = "Queued for resume"
                    item["error"] = None
                    item["finished"] = None
                    requeued = True
            if not any(item.get("state") == "queued" for item in batch.get("items") or []):
                if all(
                    item.get("state") in TERMINAL_ITEM_STATES
                    for item in batch.get("items") or []
                ):
                    self._finalize(batch)
                return self.get(batch_id)
            batch["status"] = "queued"
            batch["message"] = "Resuming"
            batch["error"] = None
            batch["finished"] = None
            self.save(batch)
        return self.start(batch_id)

    def cancel(self, batch_id: str) -> dict:
        """Cancel pending work and ask the active job to stop when possible."""
        with self._lock:
            batch = self.load(batch_id)
            if batch.get("status") in {"done", "failed", "cancelled"}:
                return public_batch(batch)
            event = self._cancels.get(batch_id)
            if event is not None:
                event.set()
            now = _now()
            active_jobs: list[str] = []
            for item in batch.get("items") or []:
                if item.get("state") in {"queued", "running", "paused"}:
                    if item.get("state") == "running" and item.get("job_id"):
                        active_jobs.append(str(item["job_id"]))
                    item["state"] = "cancelled"
                    item["message"] = "Cancelled"
                    item["error"] = None
                    item["finished"] = now
                    item["updated"] = now
            batch["status"] = "cancelled"
            batch["message"] = "Cancelled"
            batch["error"] = None
            batch["current"] = None
            batch["finished"] = now
            self.save(batch)
        for job_id in active_jobs:
            try:
                if self.backend is not None:
                    self.backend.cancel_job(job_id)
            except Exception:  # noqa: BLE001
                LOGGER.exception("could not cancel job %s", job_id)
        return self.get(batch_id)

    # -- runner ---------------------------------------------------------
    def _run_batch(self, batch_id: str, event: threading.Event) -> None:
        try:
            while True:
                with self._lock:
                    batch = self.load(batch_id)
                    if batch.get("status") == "cancelled" or event.is_set():
                        break
                    item = next(
                        (
                            value for value in batch.get("items") or []
                            if value.get("state") == "queued"
                        ),
                        None,
                    )
                    if item is None:
                        self._finalize(batch)
                        return
                    item["state"] = "running"
                    item["attempts"] = int(item.get("attempts") or 0) + 1
                    item["message"] = "Running"
                    item["error"] = None
                    item["started"] = item.get("started") or _now()
                    item["updated"] = _now()
                    batch["status"] = "running"
                    batch["current"] = item.get("index")
                    batch["message"] = (
                        f"Item {int(item.get('index') or 0) + 1} of "
                        f"{len(batch.get('items') or [])}"
                    )
                    self.save(batch)
                    item_id = str(item["id"])

                try:
                    result = self._run_item(batch_id, item_id, event)
                except _BatchCancelled:
                    self._finish_item(
                        batch_id, item_id,
                        state="cancelled", message="Cancelled", error=None,
                    )
                    with self._lock:
                        batch = self.load(batch_id)
                        if batch.get("status") != "cancelled":
                            batch["status"] = "cancelled"
                            batch["message"] = "Cancelled"
                            batch["finished"] = _now()
                            self.save(batch)
                    return
                except Exception as exc:  # noqa: BLE001
                    LOGGER.exception("batch %s item %s failed", batch_id, item_id)
                    self._finish_item(
                        batch_id, item_id,
                        state="failed", message="Item failed",
                        error=_error_text(exc),
                    )
                else:
                    self._finish_item(
                        batch_id, item_id,
                        state="done", message="Done", error=None,
                        job_id=result.get("job_id"),
                        outputs=result.get("outputs") or [],
                    )
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("batch %s runner failed", batch_id)
            with self._lock:
                try:
                    batch = self.load(batch_id)
                except BatchError:
                    return
                if batch.get("status") != "cancelled":
                    batch["status"] = "failed"
                    batch["message"] = "Batch failed"
                    batch["error"] = _error_text(exc)
                    batch["current"] = None
                    batch["finished"] = _now()
                    self.save(batch)
        finally:
            with self._lock:
                self._running.discard(batch_id)
                self._threads.pop(batch_id, None)
                self._cancels.pop(batch_id, None)

    def _run_item(self, batch_id: str, item_id: str, event: threading.Event) -> dict:
        backend = self.backend
        if backend is None:
            raise BatchError("No batch backend is configured.")
        item = self._item(batch_id, item_id)
        job: dict | None = None
        job_id = str(item.get("job_id") or "")
        if job_id:
            try:
                job = backend.load_job(job_id)
            except Exception:  # noqa: BLE001
                job = None
        if job is None:
            job = backend.create_job(item)
            job_id = str(job.get("id") or "")
            if not job_id:
                raise BatchError("The job backend returned no job id.")
            self._checkpoint_item(batch_id, item_id, job_id=job_id)

        status = str(job.get("status") or "")
        if status in {"failed", "interrupted"}:
            job = backend.retry_job(job_id) or backend.load_job(job_id)
            status = str(job.get("status") or "")
        if status not in {"ready", "failed", "interrupted", "cancelled"}:
            job = self._wait_for_analysis(job_id, event)
            status = str(job.get("status") or "")
        if status != "ready":
            error = job.get("error") or f"Job ended as {status or 'unknown'}."
            raise BatchItemError(str(error))
        if event.is_set():
            self._safe_cancel(job_id)
            raise _BatchCancelled()

        targets = normalize_targets(
            item.get("targets")
            or (item.get("options") or {}).get("targets")
            or (item.get("options") or {}).get("render_targets")
        )
        outputs: list[dict] = []
        if targets:
            backend.start_renders(job_id, targets, dict(item.get("options") or {}))
            job = self._wait_for_renders(job_id, targets, item, event)
            outputs = self._outputs(job, targets, dict(item.get("options") or {}))
        return {"job_id": job_id, "outputs": outputs}

    def _wait_for_analysis(self, job_id: str, event: threading.Event) -> dict:
        backend = self.backend
        assert backend is not None
        while True:
            if event.is_set():
                self._safe_cancel(job_id)
                raise _BatchCancelled()
            job = backend.load_job(job_id)
            status = str(job.get("status") or "")
            if status in {"ready", "failed", "interrupted", "cancelled"}:
                return job
            if status not in {
                "queued", "downloading", "scanning", "reading", "scoring",
            }:
                # Unknown but non-terminal state: keep polling, but do not spin.
                time.sleep(self.poll_interval)
            else:
                time.sleep(self.poll_interval)

    def _wait_for_renders(
        self,
        job_id: str,
        targets: list[int],
        item: dict,
        event: threading.Event,
    ) -> dict:
        backend = self.backend
        assert backend is not None
        options = dict(item.get("options") or {})
        while True:
            if event.is_set():
                self._safe_cancel(job_id)
                raise _BatchCancelled()
            states = backend.render_states(job_id, targets, options)
            states = {int(key): str(value) for key, value in states.items()}
            missing = [
                target for target in targets
                if states.get(target) not in {"ready", "failed", "interrupted", "cancelled"}
            ]
            if not missing:
                bad = [
                    target for target in targets
                    if states.get(target) != "ready"
                ]
                if bad:
                    job = backend.load_job(job_id)
                    details = [
                        str(
                            ((job.get("renders") or {}).get(key) or {}).get("error")
                            or ""
                        )
                        for key, record in (job.get("renders") or {}).items()
                        if int(record.get("target") or 0) in bad
                    ]
                    detail = next((value for value in details if value), "")
                    raise BatchItemError(
                        detail or f"Render failed for target(s): {', '.join(map(str, bad))}."
                    )
                return backend.load_job(job_id)
            time.sleep(self.poll_interval)

    def _safe_cancel(self, job_id: str) -> None:
        try:
            if self.backend is not None:
                self.backend.cancel_job(job_id)
        except Exception:  # noqa: BLE001
            LOGGER.exception("could not cancel job %s", job_id)

    def _item(self, batch_id: str, item_id: str) -> dict:
        batch = self.load(batch_id)
        for item in batch.get("items") or []:
            if item.get("id") == item_id:
                return item
        raise BatchError("Batch item is missing from the manifest.")

    def _checkpoint_item(self, batch_id: str, item_id: str, **values) -> None:
        with self._lock:
            batch = self.load(batch_id)
            for item in batch.get("items") or []:
                if item.get("id") == item_id:
                    item.update(values)
                    item["updated"] = _now()
                    break
            self.save(batch)

    def _finish_item(
        self,
        batch_id: str,
        item_id: str,
        *,
        state: str,
        message: str,
        error: str | None,
        job_id: str | None = None,
        outputs: list[dict] | None = None,
    ) -> None:
        with self._lock:
            batch = self.load(batch_id)
            if batch.get("status") == "cancelled":
                state = "cancelled"
                message = "Cancelled"
                error = None
            for item in batch.get("items") or []:
                if item.get("id") != item_id:
                    continue
                item["state"] = state
                item["message"] = message
                item["error"] = error
                item["finished"] = _now()
                item["updated"] = _now()
                if job_id:
                    item["job_id"] = job_id
                if outputs is not None:
                    item["outputs"] = outputs
                break
            batch["current"] = None
            self.save(batch)

    def _finalize(self, batch: dict) -> None:
        counts = _counts(batch)
        done = counts.get("done", 0)
        failed = counts.get("failed", 0)
        cancelled = counts.get("cancelled", 0)
        if batch.get("status") == "cancelled":
            batch["message"] = "Cancelled"
        elif failed and not done and not cancelled:
            batch["status"] = "failed"
            batch["message"] = "All items failed"
            batch["error"] = f"{failed} item(s) failed."
        else:
            batch["status"] = "done"
            batch["message"] = f"{done} done, {failed} failed"
            batch["error"] = f"{failed} item(s) failed." if failed else None
        batch["current"] = None
        batch["finished"] = _now()
        batch["progress"] = _progress(batch)
        self.save(batch)

    def _outputs(self, job: dict, targets: list[int], options: dict) -> list[dict]:
        records = list((job.get("renders") or {}).values())
        records.sort(
            key=lambda value: value.get("updated") or value.get("created") or 0,
            reverse=True,
        )
        found: dict[int, dict] = {}
        for record in records:
            try:
                target = int(record.get("target") or 0)
            except (TypeError, ValueError):
                continue
            if target not in targets or target in found:
                continue
            if record.get("status") != "ready":
                continue
            found[target] = {
                "target": target,
                "path": record.get("path"),
                "poster": record.get("poster"),
                "key": record.get("key"),
                "duration": record.get("duration"),
            }
        return [found[target] for target in targets if target in found]


_MANAGERS: dict[str, BatchManager] = {}
_MANAGERS_LOCK = threading.RLock()


def manager_for(
    data_dir: str | Path,
    backend: BatchBackend | None = None,
) -> BatchManager:
    """Return the cached manager for a data directory."""
    key = str(Path(data_dir).expanduser().resolve())
    with _MANAGERS_LOCK:
        manager = _MANAGERS.get(key)
        if manager is None:
            manager = BatchManager(key)
            _MANAGERS[key] = manager
        if backend is not None:
            manager.backend = backend
        return manager


def clear_managers() -> None:
    """Test helper: drop cached managers without cancelling their runners."""
    with _MANAGERS_LOCK:
        _MANAGERS.clear()


# Convenience wrappers for CLI use and small integrations.
def create_batch(
    data_dir: str | Path,
    name: str,
    items: list[Mapping],
    *,
    max_items: int = MAX_ITEMS,
    start: bool = True,
    backend: BatchBackend | None = None,
) -> dict:
    return manager_for(data_dir, backend).create(
        name, items, max_items=max_items, start=start,
    )


def load_batch(data_dir: str | Path, batch_id: str) -> dict:
    return manager_for(data_dir).get(batch_id)


def list_batches(data_dir: str | Path) -> list[dict]:
    return manager_for(data_dir).list()


def resume_batch(
    data_dir: str | Path,
    batch_id: str,
    backend: BatchBackend | None = None,
) -> dict:
    return manager_for(data_dir, backend).resume(batch_id)


def cancel_batch(
    data_dir: str | Path,
    batch_id: str,
    backend: BatchBackend | None = None,
) -> dict:
    return manager_for(data_dir, backend).cancel(batch_id)


recover = recover_batches
