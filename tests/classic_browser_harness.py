"""Shared harness for the Classic browser specs.

One ready fixture job (six 4 s scenes, real plans, real thumbs, real transcript)
on a private loopback uvicorn, plus Playwright discovery. The C1/C2 Clean spec
uses this; the C0 frame spec predates it and keeps its own copy.
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "trim_job"
if str(FIXTURE_DIR) not in sys.path:
    sys.path.insert(0, str(FIXTURE_DIR))

SCENES = 6


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def playwright_module() -> Path | None:
    candidates: list[Path] = []
    explicit = os.environ.get("PLAYWRIGHT_MODULE")
    if explicit:
        candidates.append(Path(explicit.replace("file://", "")))
    candidates.append(ROOT / "node_modules" / "playwright" / "index.mjs")
    candidates.extend(
        Path(path) for path in glob.glob(
            str(Path.home() / ".npm" / "_npx" / "*" / "node_modules"
                / "playwright" / "index.mjs")
        )
    )
    npm = shutil.which("npm")
    if npm:
        try:
            root = subprocess.run(
                [npm, "root", "-g"], capture_output=True, text=True, timeout=10,
                check=False,
            ).stdout.strip()
            if root:
                candidates.append(Path(root) / "playwright" / "index.mjs")
        except (OSError, subprocess.SubprocessError):
            pass
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def requirements(need_ffmpeg: bool = True) -> tuple[str, Path]:
    """Node, Playwright and (usually) ffmpeg, or skip the spec."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    module = playwright_module()
    if module is None:
        pytest.skip("Node Playwright is not installed")
    if need_ffmpeg and not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is needed for the fixture video")
    return node, module


def write_source_video(
    path: Path, seconds: float, size: tuple[int, int] = (1080, 1920),
) -> None:
    width, height = size
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error", "-f", "lavfi",
            "-i", f"color=c=0x1f2a36:s={width}x{height}:d={seconds:g}:r=10",
            "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast",
            "-movflags", "+faststart", str(path),
        ],
        check=True,
        timeout=60,
    )


def _thumbs(
    job_dir: Path, source: Path, scene_seconds: float,
    size: tuple[int, int] = (180, 320),
) -> None:
    folder = job_dir / "thumbs"
    folder.mkdir(parents=True, exist_ok=True)
    for index in range(SCENES):
        subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error",
                "-ss", f"{index * scene_seconds + 1:g}",
                "-i", str(source), "-frames:v", "1",
                "-vf", f"scale={size[0]}:{size[1]}",
                str(folder / f"{index:05d}.jpg"),
            ],
            check=True,
            timeout=60,
        )


def build_job(
    data: Path, source: Path, job_id: str = "j1",
    size: tuple[int, int] = (1080, 1920),
) -> str:
    """The smallest job the Classic editor can actually render.

    ``size`` must match the video that was written, because clean geometry is
    computed in source pixels and a mismatch hides crop mistakes.
    """
    import pipeline
    import trim_fixture

    scene_seconds = trim_fixture.SCENE_SECONDS
    duration = SCENES * scene_seconds
    scenes = [trim_fixture.make_scene(index) for index in range(SCENES)]
    job = trim_fixture.make_job(job_id, source_path=str(source))
    # The fixture meta says 1920x1080. Clean geometry is computed in source
    # pixels, so the record must match the file that was actually written.
    job["source"]["width"], job["source"]["height"] = size
    job["source"]["duration"] = duration
    job["analysis"].update({
        "scenes": scenes,
        "scene_count": len(scenes),
        "hook_scene": 0,
        "deep_scene_ids": [scene["id"] for scene in scenes],
        "deep_count": len(scenes),
        "plans": pipeline.make_plans(scenes, duration, None, 0),
        "elapsed": 12.5,
        "engine": {},
    })
    job_dir = data / "jobs" / job_id
    thumb_width = 180
    _thumbs(
        job_dir, source, scene_seconds,
        (thumb_width, max(1, round(thumb_width * size[1] / max(1, size[0])))),
    )
    (job_dir / "transcript").mkdir(parents=True, exist_ok=True)
    (job_dir / "job.json").write_text(json.dumps(job), encoding="utf-8")
    (job_dir / "transcript" / "transcript.json").write_text(
        json.dumps({
            "language": "en",
            "segments": trim_fixture.transcript_segments()[:SCENES],
        }),
        encoding="utf-8",
    )
    return job_id


def _wait_for_health(base: str, process: subprocess.Popen, log: Path) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            tail = log.read_text(errors="replace")[-4000:] if log.is_file() else ""
            pytest.fail(f"uvicorn exited before health check:\n{tail}")
        try:
            with urllib.request.urlopen(f"{base}/api/health", timeout=1) as reply:
                if reply.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.2)
    pytest.fail("uvicorn did not become healthy in 30 s")


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def run_spec(
    spec: Path, data: Path, job_id: str, tmp_path: Path, timeout: int = 240,
    extra_env: dict[str, str] | None = None,
) -> str:
    """Serve the fixture on a free port, run one spec, return its output."""
    node, module = requirements()
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    log_path = tmp_path / "uvicorn.log"
    environment = {
        **os.environ,
        "VIBECUT_DATA": str(data),
        "VIBECUT_EDITION": "classic",
        "PYTHONUNBUFFERED": "1",
    }
    environment.pop("VIBECUT_TOKEN", None)
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn", "app:app",
                "--host", "127.0.0.1", "--port", str(port),
                "--log-level", "warning",
            ],
            cwd=ROOT,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            _wait_for_health(base, process, log_path)
            env = {
                **environment,
                "CLASSIC_BASE_URL": base,
                "CLASSIC_JOB_ID": job_id,
                "CLASSIC_SHOT_DIR": str(tmp_path / "shots"),
                "PLAYWRIGHT_MODULE": module.as_uri(),
                **(extra_env or {}),
            }
            completed = subprocess.run(
                [node, str(spec)],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = (completed.stdout or "") + (completed.stderr or "")
            if completed.returncode == 2:
                pytest.skip(output.strip() or "Playwright cannot run here")
            assert completed.returncode == 0, output
            return output
        finally:
            _stop(process)
