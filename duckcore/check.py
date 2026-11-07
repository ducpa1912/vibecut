"""Background check job for DuckSuite.

One local check at a time: probe, read scenes, OCR/transcript, smart stories,
then the full Check report with clean tracklets.
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from duckcore.store import ProjectStore


class CheckManager:
    def __init__(self, data_root: Path, store: ProjectStore):
        self.data_root = Path(data_root)
        self.store = store
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="duck-check")
        self.states: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._cancel: dict[str, threading.Event] = {}

    def _project_dir(self, project_id: str) -> Path:
        path = self.data_root / "projects" / project_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _set(self, project_id: str, **values: Any) -> None:
        with self._lock:
            state = self.states.setdefault(project_id, {})
            state.update(values)
            state["updated"] = time.time()

    def _saved(self, project_id: str) -> dict[str, Any] | None:
        path = self._project_dir(project_id) / "check.json"
        if not path.is_file():
            return None
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return saved if isinstance(saved, dict) else None

    def status(self, project_id: str) -> dict[str, Any]:
        with self._lock:
            state = dict(self.states.get(project_id) or {})
        if state:
            if state.get("state") == "done" and state.get("result") is None:
                state["result"] = self._saved(project_id)
            return state
        saved = self._saved(project_id)
        if saved is not None:
            return {
                "state": "done",
                "stage": "Done",
                "progress": 1.0,
                "message": "Check complete",
                "result": saved,
            }
        return {"state": "idle", "stage": "Not checked", "progress": 0.0, "message": ""}

    def start(self, project_id: str) -> dict[str, Any]:
        project = self.store.get(project_id)
        current = self.status(project_id)
        if current.get("state") in {"queued", "running", "cancelling"}:
            return current
        cancel = threading.Event()
        self._cancel[project_id] = cancel
        self._set(
            project_id,
            state="queued",
            stage="Queued",
            progress=0.0,
            message="Waiting for the local engine",
            error="",
            result=None,
        )
        self.executor.submit(self._run, project, cancel)
        return self.status(project_id)

    def cancel(self, project_id: str) -> dict[str, Any]:
        event = self._cancel.get(project_id)
        if event is not None:
            event.set()
            self._set(project_id, state="cancelling", stage="Cancelling", message="Stopping the check")
        return self.status(project_id)

    def _run(self, project: dict[str, Any], cancel: threading.Event) -> None:
        project_id = str(project["id"])
        job_dir = self._project_dir(project_id)
        try:
            from duckcore.engine import clipset, detect, pipeline, stt

            stt.set_cancel_event(cancel)
            self._set(project_id, state="running", stage="Probing", progress=0.01, message="Reading the file")
            source = str(project["source_path"])
            meta = pipeline.probe(source)

            def analyze_progress(stage: str, fraction: float, message: str) -> None:
                self._set(
                    project_id,
                    state="running",
                    stage=stage.title(),
                    progress=min(0.72, 0.02 + 0.70 * max(0.0, min(1.0, float(fraction)))),
                    message=message,
                )

            analysis = pipeline.analyze_source(
                source,
                meta,
                job_dir,
                {
                    "ocr": True,
                    "smart_crop": True,
                    "crop_tracking": True,
                    "transcribe": True,
                    "job_id": project_id,
                    "request_id": project_id,
                },
                analyze_progress,
            )

            transcript = stt.load_latest_transcript(job_dir) or {}
            segments = transcript.get("segments") or []
            self._set(project_id, stage="Stories", progress=0.74, message="Finding smart stories")
            stories = clipset.build_clipset(
                analysis.get("scenes") or [],
                segments,
                float(meta.get("duration") or 0.0),
                count=6,
                min_s=15.0,
                max_s=90.0,
            )

            self._set(project_id, stage="Check", progress=0.76, message="Checking text and speech")

            def check_progress(fraction: float, message: str) -> None:
                self._set(
                    project_id,
                    state="running",
                    stage="Check",
                    progress=min(0.98, 0.76 + 0.22 * max(0.0, min(1.0, float(fraction)))),
                    message=message,
                )

            job = {
                "id": project_id,
                "source": meta,
                "analysis": {"scenes": analysis.get("scenes") or []},
            }
            report = detect.run_check(
                project_id,
                job,
                job_dir,
                sampler=pipeline.read_text_samples,
                audio_extractor=pipeline.extract_audio,
                sample_text=True,
                progress=check_progress,
            )

            result = {
                "project_id": project_id,
                "meta": meta,
                "source": {
                    "path": source,
                    "duration": meta.get("duration"),
                    "width": meta.get("width"),
                    "height": meta.get("height"),
                    "fps": meta.get("fps"),
                },
                "transcript": {
                    "provider": transcript.get("provider") or transcript.get("engine"),
                    "language": transcript.get("language"),
                    "segments": len(segments),
                    "text": str(transcript.get("text") or "")[:4000],
                },
                "engine": analysis.get("engine") or {},
                "scenes": analysis.get("scenes") or [],
                "stories": stories,
                "report": report,
                "finished": time.time(),
            }
            temporary = job_dir / "check.json.tmp"
            temporary.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
            temporary.replace(job_dir / "check.json")
            self._set(
                project_id,
                state="cancelled" if cancel.is_set() else "done",
                stage="Cancelled" if cancel.is_set() else "Done",
                progress=1.0,
                message="Check stopped" if cancel.is_set() else "Check complete",
                result=None,
            )
        except Exception as exc:  # noqa: BLE001
            self._set(
                project_id,
                state="cancelled" if cancel.is_set() else "failed",
                stage="Cancelled" if cancel.is_set() else "Failed",
                progress=1.0,
                message=str(exc)[:400] or "Check failed",
                error=str(exc)[:800],
            )
        finally:
            from duckcore.engine import stt

            stt.set_cancel_event(None)
            self._cancel.pop(project_id, None)
