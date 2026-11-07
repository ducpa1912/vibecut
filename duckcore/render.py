"""Minimal DuckSuite render: cut clips, fill clean layers, concat."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from duckcore import edits, media
from duckcore.store import ProjectStore


class RenderError(RuntimeError):
    pass


def _target_size(meta: dict) -> tuple[int, int]:
    width = max(2, int(meta.get("width") or 0))
    height = max(2, int(meta.get("height") or 0))
    if width >= height:
        out_h = 1080
        out_w = max(2, int(round(width * out_h / height)))
    else:
        out_w = 1080
        out_h = max(2, int(round(height * out_w / width)))
    return out_w + (out_w % 2), out_h + (out_h % 2)


def _video_codec() -> list[str]:
    override = os.environ.get("DUCK_RENDER_ENCODER", "").strip().lower()
    if override in {"h264_videotoolbox", "videotoolbox"} or (
        not override and sys.platform == "darwin"
    ):
        return ["-c:v", "h264_videotoolbox", "-q:v", "65"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]


def _run(command: list[str], timeout: float = 3600) -> None:
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RenderError((result.stderr or result.stdout or "ffmpeg failed")[-800:])


def _fill_layers(edit: dict) -> list[dict]:
    return [
        layer for layer in edit.get("clean") or []
        if isinstance(layer, dict)
        and layer.get("enabled") is not False
        and layer.get("kind") == "fill"
    ]


def render_edit(
    project: dict,
    edit: dict,
    data_root: Path,
    *,
    progress: Callable[[float, str], None] | None = None,
) -> Path:
    from duckcore.engine import pipeline, textfill

    source = str(project["source_path"])
    meta = pipeline.probe(source)
    out_w, out_h = _target_size(meta)
    fps = float(meta.get("fps") or 30.0)
    target_fps = 24 if abs(fps - 24.0) < 0.6 else 30
    project_id = str(project["id"])
    job_dir = Path(data_root) / "projects" / project_id
    cache = job_dir / "fill"
    output_dir = job_dir / "renders"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    output = output_dir / f"{edit['id']}_{stamp}.mp4"
    clips = [clip for clip in edit.get("clips") or [] if float(clip.get("end") or 0) > float(clip.get("start") or 0)]
    if not clips:
        raise RenderError("This edit has no clips.")

    layers = _fill_layers(edit)
    segments: list[Path] = []
    ffmpeg = media.ffmpeg()
    try:
        for index, clip in enumerate(clips):
            start = float(clip.get("start") or 0.0)
            duration = max(0.04, float(clip.get("end") or 0.0) - start)
            if progress:
                progress(index / max(1, len(clips)), f"Rendering clip {index + 1}/{len(clips)}")
            filled = None
            if layers:
                filled = textfill.prepare_span(
                    source=source,
                    meta=meta,
                    start=start,
                    duration=duration,
                    layers=layers,
                    method="lama",
                    cache_dir=cache,
                    data_root=data_root,
                    ffmpeg=ffmpeg,
                    progress=(
                        (lambda fraction, message: progress(
                            (index + max(0.0, min(1.0, float(fraction)))) / max(1, len(clips)),
                            message,
                        ))
                        if progress is not None else None
                    ),
                )
            segment = output_dir / f".{edit['id']}_{index:04d}.mp4"
            scale = (
                f"scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,"
                f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps={target_fps}"
            )
            if filled:
                command = [
                    ffmpeg, "-y", "-v", "error",
                    "-i", str(filled["path"]),
                    "-ss", f"{start:.6f}", "-t", f"{duration:.6f}", "-i", source,
                    "-map", "0:v:0", "-map", "1:a?",
                    "-vf", scale,
                    *_video_codec(),
                    "-c:a", "aac", "-b:a", "192k", "-shortest",
                    str(segment),
                ]
            else:
                command = [
                    ffmpeg, "-y", "-v", "error",
                    "-ss", f"{start:.6f}", "-t", f"{duration:.6f}", "-i", source,
                    "-map", "0:v:0", "-map", "0:a?",
                    "-vf", scale,
                    *_video_codec(),
                    "-c:a", "aac", "-b:a", "192k", "-shortest",
                    str(segment),
                ]
            _run(command)
            segments.append(segment)

        if progress:
            progress(0.96, "Joining clips")
        listing = output_dir / f".{edit['id']}_concat.txt"
        listing.write_text(
            "".join(f"file '{segment.as_posix()}'\n" for segment in segments),
            encoding="utf-8",
        )
        _run([
            ffmpeg, "-y", "-v", "error",
            "-f", "concat", "-safe", "0", "-i", str(listing),
            "-c", "copy", "-movflags", "+faststart", str(output),
        ])
        listing.unlink(missing_ok=True)
        for segment in segments:
            segment.unlink(missing_ok=True)
        if progress:
            progress(1.0, "Render complete")
        return output
    except Exception:
        for segment in segments:
            segment.unlink(missing_ok=True)
        raise


class RenderManager:
    def __init__(self, data_root: Path, store: ProjectStore):
        self.data_root = Path(data_root)
        self.store = store
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="duck-render")
        self.states: dict[tuple[str, str], dict[str, Any]] = {}
        self.lock = threading.Lock()

    def _set(self, key: tuple[str, str], **values: Any) -> None:
        with self.lock:
            state = self.states.setdefault(key, {})
            state.update(values)
            state["updated"] = time.time()

    def start(self, project_id: str, edit_id: str) -> dict:
        project = self.store.get(project_id)
        edit = edits.get_edit(self.data_root, project_id, edit_id)
        key = (project_id, edit_id)
        with self.lock:
            current = self.states.get(key)
            if current and current.get("state") in {"queued", "running"}:
                return dict(current)
        self._set(key, state="queued", stage="Queued", progress=0.0, message="Waiting to render", output="")
        self.executor.submit(self._run, key, project, edit)
        return self.status(project_id, edit_id)

    def status(self, project_id: str, edit_id: str) -> dict:
        with self.lock:
            return dict(self.states.get((project_id, edit_id)) or {
                "state": "idle", "stage": "Not rendered", "progress": 0.0, "message": "", "output": "",
            })

    def _run(self, key: tuple[str, str], project: dict, edit: dict) -> None:
        self._set(key, state="running", stage="Rendering", progress=0.01, message="Starting")

        def progress(fraction: float, message: str) -> None:
            self._set(
                key,
                state="running",
                stage="Rendering",
                progress=max(0.01, min(0.99, float(fraction))),
                message=message,
            )

        try:
            output = render_edit(project, edit, self.data_root, progress=progress)
            self._set(
                key,
                state="done",
                stage="Done",
                progress=1.0,
                message="Render complete",
                output=str(output),
            )
        except Exception as exc:  # noqa: BLE001
            self._set(
                key,
                state="failed",
                stage="Failed",
                progress=1.0,
                message=str(exc)[:500],
            )
