"""In-process task scheduler for analysis and render submission.

VibeCut deliberately has no external queue service.  This module gives the two
existing single-worker thread pools one explicit abstraction:

* a task has a state (``queued``, ``running``, ``done``, ``failed``,
  ``interrupted`` or ``cancelled``) and an attempt count;
* every task exposes a :class:`RetryHandle`, and retrying is idempotent: asking
  the same failed task to retry twice returns the one replacement task;
* an interrupted process can mark pending/running tasks without turning them
  into permanent failures.

The file is named ``queue.py`` because that is the product-level name.  Python
resolves imports in the application directory before the standard library, so
this module also re-exports the standard-library ``queue`` API.  That keeps
``concurrent.futures.ThreadPoolExecutor`` and any dependency that imports
``queue`` working normally.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sysconfig
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

LOGGER = logging.getLogger("vibecut.queue")


def _load_stdlib_queue():
    """Load the real standard-library queue module under a private name."""
    try:
        path = Path(sysconfig.get_paths()["stdlib"]) / "queue.py"
        if not path.is_file() or path.resolve() == Path(__file__).resolve():
            return None
        spec = importlib.util.spec_from_file_location("_vibecut_stdlib_queue", path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:  # noqa: BLE001
        LOGGER.exception("could not load the standard-library queue module")
        return None


_STDLIB_QUEUE = _load_stdlib_queue()
if _STDLIB_QUEUE is not None:
    for _name in ("Empty", "Full", "Queue", "LifoQueue", "PriorityQueue", "SimpleQueue"):
        if hasattr(_STDLIB_QUEUE, _name):
            globals()[_name] = getattr(_STDLIB_QUEUE, _name)
    # Keep less-common standard-library names available too (deque, heappush,
    # GenericAlias and any future public addition).
    for _name in dir(_STDLIB_QUEUE):
        if not _name.startswith("_") and _name not in globals():
            globals()[_name] = getattr(_STDLIB_QUEUE, _name)


class QueueState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"


STATES = tuple(state.value for state in QueueState)
TERMINAL_STATES = frozenset({
    QueueState.DONE,
    QueueState.FAILED,
    QueueState.INTERRUPTED,
    QueueState.CANCELLED,
})
RETRYABLE_STATES = frozenset({QueueState.FAILED, QueueState.INTERRUPTED})


class QueueError(RuntimeError):
    """Base error for scheduler misuse."""


class TaskNotFound(QueueError):
    """The task id is unknown or has been pruned."""


@dataclass
class RetryHandle:
    """A stable handle that can requeue one terminal task."""

    scheduler: "Scheduler"
    task_id: str

    def retry(self) -> "Task":
        return self.scheduler.retry(self.task_id)

    @property
    def available(self) -> bool:
        task = self.scheduler.get(self.task_id)
        return bool(task and task.retryable)

    def as_dict(self) -> dict:
        return {"task_id": self.task_id, "available": self.available}


@dataclass
class Task:
    """One submitted unit of work."""

    id: str
    kind: str
    key: str | None
    state: QueueState = QueueState.QUEUED
    attempts: int = 0
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    error: str | None = None
    result: Any = None
    retry_of: str | None = None
    retried_by: str | None = None
    _fn: Callable[..., Any] | None = field(default=None, repr=False)
    _args: tuple = field(default_factory=tuple, repr=False)
    _kwargs: dict = field(default_factory=dict, repr=False)
    _scheduler: "Scheduler | None" = field(default=None, repr=False)
    _done: threading.Event = field(default_factory=threading.Event, repr=False)

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def status(self) -> str:
        return self.state.value

    @property
    def retryable(self) -> bool:
        return self.state in RETRYABLE_STATES and self.retried_by is None

    @property
    def retry_handle(self) -> RetryHandle:
        if self._scheduler is None:
            raise QueueError("This task is not attached to a scheduler.")
        return RetryHandle(self._scheduler, self.id)

    def retry(self) -> "Task":
        return self.retry_handle.retry()

    def wait(self, timeout: float | None = None) -> bool:
        return self._done.wait(timeout)

    def as_dict(self, *, include_retry: bool = True) -> dict:
        value = {
            "id": self.id,
            "kind": self.kind,
            "key": self.key,
            "state": self.state.value,
            "attempts": self.attempts,
            "created": round(self.created, 3),
            "started": round(self.started, 3) if self.started else None,
            "finished": round(self.finished, 3) if self.finished else None,
            "error": self.error,
            "retry_of": self.retry_of,
            "retried_by": self.retried_by,
        }
        if include_retry:
            value["retry"] = {
                "available": self.retryable,
                "task_id": self.id,
            }
        return value


class Scheduler:
    """A small stateful wrapper around one ``ThreadPoolExecutor``.

    ``max_workers`` stays one for analysis and render so the current serial
    behaviour is preserved.  The wrapper is intentionally permissive about
    extra submission keywords: ``task_kind``, ``task_key`` and ``retry_payload``
    are scheduler metadata and are not forwarded to the worker function.
    """

    def __init__(
        self,
        name: str,
        *,
        max_workers: int = 1,
        thread_name_prefix: str | None = None,
        history_limit: int = 2000,
        executor=None,
    ) -> None:
        from concurrent.futures import ThreadPoolExecutor

        self.name = name
        self.max_workers = max(1, int(max_workers))
        self.history_limit = max(1, int(history_limit))
        self._executor = executor or ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix=thread_name_prefix or f"vibecut-{name}",
        )
        self._lock = threading.RLock()
        self._tasks: dict[str, Task] = {}
        self._closed = False

    # -- submission -----------------------------------------------------
    def submit(self, fn: Callable[..., Any], *args, **kwargs) -> Task:
        task_kind = kwargs.pop("task_kind", None)
        task_key = kwargs.pop("task_key", None)
        kwargs.pop("retry_payload", None)
        kind = str(task_kind or self._infer_kind(fn))
        key = str(task_key) if task_key is not None else (
            str(args[0]) if args and isinstance(args[0], str) else None
        )
        task = Task(
            id=uuid.uuid4().hex[:12],
            kind=kind,
            key=key,
            _fn=fn,
            _args=tuple(args),
            _kwargs=dict(kwargs),
            _scheduler=self,
        )
        with self._lock:
            if self._closed:
                task.state = QueueState.FAILED
                task.error = "Scheduler is shut down."
                task.finished = time.time()
                task._done.set()
                return task
            self._tasks[task.id] = task
            self._prune()
        self._schedule(task)
        return task

    def submit_tracked(
        self,
        fn: Callable[..., Any],
        *args,
        kind: str = "task",
        key: str | None = None,
        **kwargs,
    ) -> Task:
        """Explicit form used when a caller wants a stable kind/key."""
        return self.submit(fn, *args, task_kind=kind, task_key=key, **kwargs)

    def _infer_kind(self, fn: Callable[..., Any]) -> str:
        name = str(getattr(fn, "__name__", "") or "task")
        if "render" in name:
            return "render"
        if "analysis" in name or "analy" in name:
            return "analysis"
        return "task"

    def _schedule(self, task: Task) -> None:
        try:
            self._executor.submit(self._run, task)
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                task.state = QueueState.FAILED
                task.error = str(exc)[:2400]
                task.finished = time.time()
            task._done.set()

    def _run(self, task: Task) -> None:
        with self._lock:
            if task.state is not QueueState.QUEUED:
                task._done.set()
                return
            task.state = QueueState.RUNNING
            task.attempts += 1
            task.started = task.started or time.time()
            fn = task._fn
            args = task._args
            kwargs = dict(task._kwargs)
        try:
            if fn is None:
                raise QueueError("Task has no callable.")
            result = fn(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001
            with self._lock:
                if task.state is QueueState.RUNNING:
                    task.state = QueueState.FAILED
                    task.error = str(exc)[:2400]
                    task.finished = time.time()
            LOGGER.exception("task %s (%s) failed", task.id, task.kind)
        else:
            with self._lock:
                if task.state is QueueState.RUNNING:
                    task.state = QueueState.DONE
                    task.result = result
                    task.error = None
                    task.finished = time.time()
        finally:
            task._done.set()

    # -- inspection -----------------------------------------------------
    def get(self, task_id: str) -> Task | None:
        with self._lock:
            return self._tasks.get(task_id)

    def retry_handle(self, task_id: str) -> RetryHandle:
        if self.get(task_id) is None:
            raise TaskNotFound(task_id)
        return RetryHandle(self, task_id)

    def retry(self, task_id: str) -> Task:
        """Requeue a failed/interrupted task once.

        Calling retry again for the same task returns the already-created
        replacement instead of submitting duplicate work.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFound(task_id)
            if task.retried_by:
                existing = self._tasks.get(task.retried_by)
                if existing is not None:
                    return existing
            if task.state not in RETRYABLE_STATES:
                raise QueueError(
                    f"Task {task_id} is {task.state.value}; only failed or "
                    "interrupted tasks can retry."
                )
            replacement = Task(
                id=uuid.uuid4().hex[:12],
                kind=task.kind,
                key=task.key,
                retry_of=task.id,
                attempts=task.attempts,
                _fn=task._fn,
                _args=task._args,
                _kwargs=dict(task._kwargs),
                _scheduler=self,
            )
            task.retried_by = replacement.id
            self._tasks[replacement.id] = replacement
            self._prune()
        self._schedule(replacement)
        return replacement

    def wait(self, task_id: str, timeout: float | None = None) -> Task:
        task = self.get(task_id)
        if task is None:
            raise TaskNotFound(task_id)
        task.wait(timeout)
        return task

    def tasks(self) -> list[Task]:
        with self._lock:
            return sorted(self._tasks.values(), key=lambda item: item.created)

    def snapshot(self) -> list[dict]:
        return [task.as_dict() for task in self.tasks()]

    def stats(self) -> dict:
        counts = {state: 0 for state in STATES}
        with self._lock:
            for task in self._tasks.values():
                counts[task.state.value] += 1
        return {
            "name": self.name,
            "max_workers": self.max_workers,
            "tasks": len(self._tasks),
            "states": counts,
        }

    # -- lifecycle ------------------------------------------------------
    def cancel(self, task_id: str) -> bool:
        """Cancel queued work.  Running work is marked interrupted instead."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFound(task_id)
            if task.state is QueueState.QUEUED:
                task.state = QueueState.CANCELLED
                task.error = "Cancelled before start."
                task.finished = time.time()
                task._done.set()
                return True
            if task.state is QueueState.RUNNING:
                task.state = QueueState.INTERRUPTED
                task.error = "Interrupted."
                task.finished = time.time()
                task._done.set()
                return True
            return False

    def interrupt_all(self, reason: str = "The server restarted.") -> int:
        """Mark in-flight and pending tasks interrupted without failing them."""
        changed = 0
        with self._lock:
            for task in self._tasks.values():
                if task.state in {QueueState.QUEUED, QueueState.RUNNING}:
                    task.state = QueueState.INTERRUPTED
                    task.error = reason
                    task.finished = time.time()
                    task._done.set()
                    changed += 1
        return changed

    def shutdown(self, wait: bool = True) -> None:
        with self._lock:
            self._closed = True
        self._executor.shutdown(wait=wait)

    def _prune(self) -> None:
        if len(self._tasks) <= self.history_limit:
            return
        removable = [
            task for task in self._tasks.values()
            if task.terminal and task.retried_by is None
        ]
        removable.sort(key=lambda item: item.finished or item.created)
        for task in removable:
            if len(self._tasks) <= self.history_limit:
                break
            self._tasks.pop(task.id, None)


# Backwards-friendly names for integrations.
JobQueue = Scheduler
TaskState = QueueState

# The standard-library API remains importable as ``queue.Queue`` etc.
__all__ = [
    "Empty",
    "Full",
    "Queue",
    "LifoQueue",
    "PriorityQueue",
    "SimpleQueue",
    "QueueState",
    "TaskState",
    "Scheduler",
    "JobQueue",
    "Task",
    "RetryHandle",
    "QueueError",
    "TaskNotFound",
    "STATES",
    "TERMINAL_STATES",
    "RETRYABLE_STATES",
]
