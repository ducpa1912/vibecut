"""Durable, sequential story render queue.

A queue holds at most ten story items. An item is one story render:
``(job_id, set_id, story_id)`` plus ``aspect`` and ``quality``. Items may span
jobs. One runner thread renders them strictly in order and waits for each
artifact to finish before starting the next.

Exactly one output per item: artifact ids are deterministic for a story spec,
so starting an item whose artifact is already ready reuses it, and an item
that is already rendering is waited on rather than queued twice.

Restart semantics: :meth:`StoryQueueManager.recover` pauses every active
queue and marks its running item ``interrupted``. Nothing ever resumes on its
own; :meth:`StoryQueueManager.resume` is the one-click path. A watchdog
cancels an item that runs past its timeout, marks it failed and moves on.

Pause semantics: :meth:`StoryQueueManager.pause` stops the running render at
once and puts its item back in line. AI fills and encoded beats stay on disk, so
resume starts that item again and only does the work still missing.

The manager talks to the app through :class:`StoryBackend`, so ordering,
recovery and timeout rules are testable without ffmpeg or FastAPI.
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
from typing import Protocol

LOGGER = logging.getLogger("vibecut.story_queue")

MAX_ITEMS = 10
ASPECTS = ("9:16", "4:5", "1:1", "16:9", "16:10")
QUALITIES = ("360", "draft", "720", "final", "1440", "2160")
QUEUE_STATES = ("queued", "running", "paused", "done", "cancelled")
ITEM_STATES = ("queued", "running", "done", "failed", "interrupted", "cancelled")
TERMINAL_ITEMS = frozenset({"done", "failed", "cancelled"})
ACTIVE_QUEUES = frozenset({"queued", "running"})
READY = "ready"
# Longest a resume waits for a paused render to stop. A model run ends in seconds.
STOP_WAIT = 120.0
FAILED_RENDERS = frozenset({"failed", "cancelled", "interrupted"})
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class QueueError(RuntimeError):
    status_code = 400


class QueueNotFound(QueueError):
    status_code = 404


class QueueConflict(QueueError):
    status_code = 409


class StoryBackend(Protocol):
    # Optional: ``error(item, artifact_id) -> str``. When a backend provides it,
    # the queue shows the artifact manifest's reason instead of "Render failed."
    # Old backends without the method keep the fallback.
    def start(self, item: dict) -> str:
        """Queue the story render and return its artifact id (idempotent)."""

    def status(self, item: dict, artifact_id: str) -> str:
        """Return the artifact status: ready, queued, rendering, failed, ..."""

    def cancel(self, item: dict, artifact_id: str) -> None:
        """Stop the render and its ffmpeg process group."""

    def timeout_for(self, item: dict) -> float:
        """Seconds an item may render before the watchdog stops it."""


def _now() -> float:
    return round(time.time(), 3)


def _error_text(exc: BaseException) -> str:
    detail = getattr(exc, "detail", None)
    if isinstance(detail, dict):
        detail = detail.get("message") or detail.get("detail") or json.dumps(detail)
    return str(detail if detail not in (None, "") else exc)[:1200]


def _failure_text(backend: StoryBackend, item: dict, artifact_id: str, status: str) -> str:
    """The backend's reason for a failed artifact, else a plain fallback."""
    hook = getattr(backend, "error", None)
    if callable(hook):
        try:
            text = hook(item, artifact_id)
        except Exception:  # noqa: BLE001 - a broken hook never hides the row
            LOGGER.exception("backend could not explain failed artifact %s", artifact_id)
        else:
            text = str(text or "").strip()
            if text:
                return text[:1200]
    return f"Render {status}."


def normalize_items(raw: object) -> list[dict]:
    """Validate a request's story items and return clean item records."""
    if not isinstance(raw, list) or not raw:
        raise QueueError("items must be a non-empty list of stories.")
    if len(raw) > MAX_ITEMS:
        raise QueueError(f"A queue holds at most {MAX_ITEMS} story items.")
    items: list[dict] = []
    seen: set[tuple] = set()
    for index, value in enumerate(raw, 1):
        if not isinstance(value, dict):
            raise QueueError(f"Item {index} must be an object.")
        ids = {}
        for key in ("job_id", "set_id", "story_id"):
            text = str(value.get(key) or "").strip()
            if not _ID_RE.match(text):
                raise QueueError(f"Item {index} needs a valid {key}.")
            ids[key] = text
        aspect = str(value.get("aspect") or "9:16")
        if aspect not in ASPECTS:
            raise QueueError(f"Item {index}: story renders support 9:16, 4:5, 1:1, 16:9 and 16:10.")
        quality = str(value.get("quality") or "final")
        if quality not in QUALITIES:
            raise QueueError(
                f"Item {index}: quality must be one of "
                + ", ".join(QUALITIES) + "."
            )
        fill_device = "gpu" if value.get("fill_device") == "gpu" else ""
        fill_follow = value.get("fill_follow") is True
        edit_hash = str(value.get("edit_hash") or "")[:80]
        fill_method = str(value.get("fill_method") or "")
        fill_method = fill_method if fill_method in ("lama", "migan", "sttn", "telea", "ns") else ""
        # What this render's AI fill runs on, for the queue to show. Not part of its identity.
        fill_model = str(value.get("fill_model") or "")
        fill_model = fill_model if fill_model in ("lama", "migan", "sttn", "telea", "ns", "mixed") else ""
        identity = (ids["job_id"], ids["set_id"], ids["story_id"], aspect, quality, fill_device, fill_follow, fill_method)
        if identity in seen:
            raise QueueError(f"Item {index} repeats an earlier story and aspect.")
        seen.add(identity)
        items.append({
            "id": f"i{index}",
            **ids,
            "aspect": aspect,
            "quality": quality,
            "fill_device": fill_device,
            "fill_follow": fill_follow,
            "edit_hash": edit_hash,
            "fill_method": fill_method,
            "fill_model": fill_model,
            "title": str(value.get("title") or "")[:200],
            "state": "queued",
            "artifact_id": None,
            "error": None,
            "attempts": 0,
            "started": None,
            "finished": None,
        })
    return items


class StoryQueueManager:
    """Own the queue manifests in ``data_dir/story_queues`` and their runners."""

    def __init__(
        self,
        data_dir: str | Path,
        backend: StoryBackend | None = None,
        *,
        poll_interval: float = 0.5,
    ) -> None:
        self.directory = Path(data_dir).expanduser() / "story_queues"
        self.backend = backend
        self.poll_interval = poll_interval
        self._lock = threading.RLock()
        self._threads: dict[str, threading.Thread] = {}
        self._stops: dict[str, threading.Event] = {}
        # One queue renders at a time on this machine, oldest first.
        self._turn = threading.Condition()
        self._turn_taken = False
        self._waiting: dict[str, float] = {}

    # ------------------------------------------------------------ storage

    def _path(self, queue_id: str) -> Path:
        if not _ID_RE.match(str(queue_id or "")):
            raise QueueNotFound("Queue not found.")
        return self.directory / f"{queue_id}.json"

    def _read(self, queue_id: str) -> dict:
        path = self._path(queue_id)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise QueueNotFound("Queue not found.") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise QueueError(f"Queue data is unreadable: {path.name}") from exc
        if not isinstance(value, dict) or value.get("id") != queue_id:
            raise QueueError(f"Queue data is invalid: {path.name}")
        return value

    def _write(self, queue: dict) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        queue["updated"] = _now()
        path = self._path(queue["id"])
        temp = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
        try:
            temp.write_text(json.dumps(queue, ensure_ascii=False), encoding="utf-8")
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)

    def _mutate(self, queue_id: str, mutator) -> dict:
        with self._lock:
            queue = self._read(queue_id)
            mutator(queue)
            self._write(queue)
            return queue

    @staticmethod
    def public(queue: dict) -> dict:
        value = json.loads(json.dumps(queue))
        counts = {state: 0 for state in ITEM_STATES}
        for item in queue.get("items") or []:
            counts[item.get("state") or "queued"] = counts.get(item.get("state") or "queued", 0) + 1
        value["counts"] = counts
        total = len(queue.get("items") or [])
        value["progress"] = round(
            sum(1 for item in queue.get("items") or [] if item.get("state") in TERMINAL_ITEMS)
            / total, 4,
        ) if total else 0.0
        value["needs_resume"] = queue.get("status") == "paused" and any(
            item.get("state") in {"queued", "interrupted"} for item in queue.get("items") or []
        )
        return value

    # ------------------------------------------------------------ API

    def create(self, raw_items: object, *, start: bool = True) -> dict:
        items = normalize_items(raw_items)
        queue = {
            "id": f"sq_{uuid.uuid4().hex[:12]}",
            "created": _now(),
            "updated": _now(),
            "status": "queued",
            "message": "Queued",
            "items": items,
        }
        with self._lock:
            self._write(queue)
        if start:
            self._start(queue["id"])
        return self.public(queue)

    def list(self) -> list[dict]:
        if not self.directory.is_dir():
            return []
        rows = []
        for path in self.directory.glob("sq_*.json"):
            try:
                rows.append(self.public(self._read(path.stem)))
            except QueueError:
                LOGGER.warning("skipping unreadable story queue %s", path.name)
        rows.sort(key=lambda item: float(item.get("created") or 0), reverse=True)
        return rows

    def get(self, queue_id: str) -> dict:
        return self.public(self._read(queue_id))

    def interrupted(self) -> list[dict]:
        """Queues that need the one-click resume banner."""
        return [row for row in self.list() if row["needs_resume"]]

    def pause(self, queue_id: str) -> dict:
        running: list[dict] = []

        def mutate(queue: dict) -> None:
            if queue.get("status") not in ACTIVE_QUEUES:
                raise QueueConflict("Only an active queue can be paused.")
            queue["status"] = "paused"
            queue["message"] = "Paused. Resume keeps the work already done."
            for item in queue.get("items") or []:
                if item.get("state") == "running":
                    running.append(dict(item))
                    item["state"] = "queued"
                    # Resume must not start again until this render has stopped.
                    item["stopping"] = item.get("artifact_id")

        queue = self._mutate(queue_id, mutate)
        self._stops.setdefault(queue_id, threading.Event()).set()
        for item in running:
            if item.get("artifact_id") and self.backend is not None:
                try:
                    self.backend.cancel(item, item["artifact_id"])
                except Exception:  # noqa: BLE001
                    LOGGER.exception("could not pause story render %s", item.get("artifact_id"))
        return self.public(queue)

    def cancel(self, queue_id: str) -> dict:
        running: list[dict] = []

        def mutate(queue: dict) -> None:
            if queue.get("status") in {"done", "cancelled"}:
                raise QueueConflict("This queue already finished.")
            queue["status"] = "cancelled"
            queue["message"] = "Cancelled"
            for item in queue.get("items") or []:
                if item.get("state") == "running":
                    running.append(dict(item))
                if item.get("state") not in TERMINAL_ITEMS:
                    item["state"] = "cancelled"
                    item["finished"] = _now()

        queue = self._mutate(queue_id, mutate)
        self._stops.setdefault(queue_id, threading.Event()).set()
        for item in running:
            if item.get("artifact_id") and self.backend is not None:
                try:
                    self.backend.cancel(item, item["artifact_id"])
                except Exception:  # noqa: BLE001
                    LOGGER.exception("could not cancel story render %s", item.get("artifact_id"))
        return self.public(queue)

    def delete(self, queue_id: str) -> dict:
        """Remove a finished or paused queue record. Never races a live run."""
        with self._lock:
            queue = self._read(queue_id)
            if queue.get("status") in ACTIVE_QUEUES:
                raise QueueConflict("Cancel this queue before deleting it.")
            self._stops.setdefault(queue_id, threading.Event()).set()
            self._threads.pop(queue_id, None)
            self._stops.pop(queue_id, None)
            self._waiting.pop(queue_id, None)
            self._path(queue_id).unlink(missing_ok=True)
        return {"id": queue_id}

    def waiting_for_job(self, job_id: str) -> int:
        """Items of one video that have not started yet, across all queues."""
        return sum(
            1
            for queue in self.list()
            for item in queue.get("items") or []
            if item.get("job_id") == job_id and item.get("state") == "queued"
        )

    def drop_job(self, job_id: str) -> None:
        """Take one video out of every queue, stopping its render if one runs."""
        for summary in self.list():
            running: list[dict] = []

            def mutate(queue: dict) -> None:
                for item in queue.get("items") or []:
                    if item.get("job_id") != job_id or item.get("state") in TERMINAL_ITEMS:
                        continue
                    if item.get("state") == "running":
                        running.append(dict(item))
                    item["state"] = "cancelled"
                    item["finished"] = _now()

            if not any(item.get("job_id") == job_id for item in summary.get("items") or []):
                continue
            self._mutate(summary["id"], mutate)
            for item in running:
                if item.get("artifact_id") and self.backend is not None:
                    try:
                        self.backend.cancel(item, item["artifact_id"])
                    except Exception:  # noqa: BLE001
                        LOGGER.exception("could not cancel story render %s", item.get("artifact_id"))

    def resume(self, queue_id: str) -> dict:
        """One click: requeue interrupted items and run the rest in order."""
        def mutate(queue: dict) -> None:
            if queue.get("status") not in {"paused", "queued"}:
                raise QueueConflict("Only a paused queue can resume.")
            for item in queue.get("items") or []:
                if item.get("state") == "interrupted":
                    item["state"] = "queued"
                    item["error"] = None
            queue["status"] = "queued"
            queue["message"] = "Resuming"

        queue = self._mutate(queue_id, mutate)
        self._start(queue_id)
        return self.public(queue)

    def recover(self) -> int:
        """After a restart: pause active queues, mark running items interrupted."""
        if not self.directory.is_dir():
            return 0
        changed = 0
        for path in self.directory.glob("sq_*.json"):
            try:
                def mutate(queue: dict) -> None:
                    nonlocal changed
                    touched = False
                    if queue.get("status") in ACTIVE_QUEUES:
                        queue["status"] = "paused"
                        queue["message"] = "Interrupted. Resume to continue."
                        touched = True
                    for item in queue.get("items") or []:
                        if item.get("state") == "running":
                            item["state"] = "interrupted"
                            item["error"] = "VibeCut stopped while this story was rendering."
                            touched = True
                    if touched:
                        changed += 1

                self._mutate(path.stem, mutate)
            except QueueError:
                LOGGER.exception("could not recover story queue %s", path.name)
        return changed

    def wait(self, queue_id: str, timeout: float | None = None) -> bool:
        thread = self._threads.get(queue_id)
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()

    # ------------------------------------------------------------ runner

    def _start(self, queue_id: str) -> None:
        if self.backend is None:
            raise QueueError("Story renders are not available in this build.")
        with self._lock:
            thread = self._threads.get(queue_id)
            if thread is not None and thread.is_alive():
                return
            stop = threading.Event()
            self._stops[queue_id] = stop
            thread = threading.Thread(
                target=self._run, args=(queue_id, stop), daemon=True,
                name=f"story-queue-{queue_id}",
            )
            self._threads[queue_id] = thread
            thread.start()

    def _set_item(self, queue_id: str, item_id: str, **fields) -> dict:
        def mutate(queue: dict) -> None:
            for item in queue.get("items") or []:
                if item.get("id") == item_id:
                    item.update(fields)

        return self._mutate(queue_id, mutate)

    def _take_turn(self, queue_id: str, order: float, stop: threading.Event) -> bool:
        """Wait until this queue is the oldest waiting and nothing renders."""
        with self._turn:
            if self._turn_taken or self._waiting:
                self._mutate(queue_id, lambda queue: queue.update(message="Waiting for the render before it"))
            self._waiting[queue_id] = order
            try:
                while not stop.is_set():
                    first = min(self._waiting, key=lambda name: (self._waiting[name], name))
                    if not self._turn_taken and first == queue_id:
                        self._turn_taken = True
                        return True
                    self._turn.wait(self.poll_interval)
                return False
            finally:
                self._waiting.pop(queue_id, None)
                self._turn.notify_all()

    def _give_turn(self) -> None:
        with self._turn:
            self._turn_taken = False
            self._turn.notify_all()

    def _run(self, queue_id: str, stop: threading.Event) -> None:
        has_turn = False
        try:
            queue = self._mutate(queue_id, lambda queue: queue.update(status="running", message="Rendering"))
            # One queue at a time on this machine, oldest first, each to its end.
            has_turn = self._take_turn(queue_id, float(queue.get("created") or 0), stop)
            if not has_turn:
                return
            self._mutate(queue_id, lambda queue: queue.update(message="Rendering"))
            while not stop.is_set():
                queue = self._read(queue_id)
                if queue.get("status") != "running":
                    return
                item = next(
                    (row for row in queue.get("items") or [] if row.get("state") == "queued"),
                    None,
                )
                if item is None:
                    failed = sum(1 for row in queue["items"] if row.get("state") == "failed")
                    self._mutate(queue_id, lambda queue: queue.update(
                        status="done",
                        message=f"Done · {failed} failed" if failed else "Done",
                    ))
                    return
                began = time.time()
                try:
                    self._run_item(queue_id, item, stop)
                finally:
                    # Time spent over every try, so a resumed render reports it all.
                    self._set_item(
                        queue_id, item["id"],
                        spent=round(float(item.get("spent") or 0.0) + time.time() - began, 1),
                    )
        except Exception:  # noqa: BLE001
            LOGGER.exception("story queue %s stopped unexpectedly", queue_id)
        finally:
            if has_turn:
                self._give_turn()
            with self._lock:
                if self._threads.get(queue_id) is threading.current_thread():
                    self._threads.pop(queue_id, None)

    def _wait_until_stopped(self, queue_id: str, item: dict, stop: threading.Event) -> bool:
        """A pause asked this item's render to stop. False if stopped again meanwhile."""
        backend = self.backend
        assert backend is not None
        deadline = time.time() + STOP_WAIT
        while time.time() < deadline:
            try:
                if str(backend.status(item, item["stopping"]) or "") in FAILED_RENDERS | {READY}:
                    break
            except Exception:  # noqa: BLE001 - e.g. the video was deleted; start reports it
                break
            if stop.wait(self.poll_interval):
                return False
        self._set_item(queue_id, item["id"], stopping=None)
        return True

    def _run_item(self, queue_id: str, item: dict, stop: threading.Event) -> None:
        backend = self.backend
        assert backend is not None
        if item.get("stopping") and not self._wait_until_stopped(queue_id, item, stop):
            return
        started = time.time()
        self._set_item(
            queue_id, item["id"], state="running", started=_now(),
            attempts=int(item.get("attempts") or 0) + 1, error=None,
        )
        try:
            artifact_id = backend.start(item)
        except Exception as exc:  # noqa: BLE001 - one bad item never stops the queue
            self._set_item(queue_id, item["id"], state="failed", error=_error_text(exc), finished=_now())
            return
        self._set_item(queue_id, item["id"], artifact_id=artifact_id)
        if stop.is_set():
            # A pause or cancel landed while this render was starting.
            try:
                backend.cancel(item, artifact_id)
            except Exception:  # noqa: BLE001
                LOGGER.exception("could not stop story render %s", artifact_id)
            if self._read(queue_id).get("status") == "paused":
                self._set_item(queue_id, item["id"], state="queued", stopping=artifact_id)
            return
        limit = max(1.0, float(backend.timeout_for(item)))
        while True:
            try:
                status = str(backend.status(item, artifact_id) or "")
            except Exception as exc:  # noqa: BLE001 - e.g. the video was deleted meanwhile
                self._set_item(
                    queue_id, item["id"], state="failed", finished=_now(), error=_error_text(exc),
                )
                return
            if status == READY:
                self._set_item(queue_id, item["id"], state="done", finished=_now())
                return
            if stop.is_set():
                # Paused or cancelled: the render's end is not this item's failure.
                return
            if status in FAILED_RENDERS:
                self._set_item(
                    queue_id, item["id"], state="failed", finished=_now(),
                    error=_failure_text(backend, item, artifact_id, status),
                )
                return
            if time.time() - started > limit:
                try:
                    backend.cancel(item, artifact_id)
                except Exception:  # noqa: BLE001
                    LOGGER.exception("watchdog could not cancel %s", artifact_id)
                self._set_item(
                    queue_id, item["id"], state="failed", finished=_now(),
                    error=f"Timed out after {int(limit)}s; the render was stopped.",
                )
                return
            if stop.wait(self.poll_interval):
                # Paused or cancelled: both already asked the render to stop.
                return
