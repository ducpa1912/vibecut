"""C0 frame, driven by Node Playwright on a fixture job.

Starts uvicorn on a free loopback port with a scratch ``VIBECUT_DATA`` holding
one ready job (six 4 s scenes, real plans for 15/30/60, a real transcript), then
runs ``tests/browser/classic_frame.spec.mjs`` against the Classic page. The
server is always stopped, including when the spec skips or fails.
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

pytest.importorskip("pipeline")
pytest.importorskip("clipset")

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "trim_job"
SPEC = ROOT / "tests" / "browser" / "classic_frame.spec.mjs"
if str(FIXTURE_DIR) not in sys.path:
    sys.path.insert(0, str(FIXTURE_DIR))
import trim_fixture  # noqa: E402

import pipeline  # noqa: E402

SCENES = 6
SCENE_SECONDS = trim_fixture.SCENE_SECONDS
DURATION = SCENES * SCENE_SECONDS


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _playwright_module() -> Path | None:
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


def _source_video(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error", "-f", "lavfi",
            "-i", f"color=c=0x1f2a36:s=1080x1920:d={DURATION:g}:r=10",
            "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast",
            "-movflags", "+faststart", str(path),
        ],
        check=True,
        timeout=60,
    )


def _thumbs(job_dir: Path, source: Path) -> None:
    """One still per scene; the hook panel and moment cards show real frames."""
    folder = job_dir / "thumbs"
    folder.mkdir(parents=True, exist_ok=True)
    for index in range(SCENES):
        subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error", "-ss", f"{index * SCENE_SECONDS + 1:g}",
                "-i", str(source), "-frames:v", "1", "-vf", "scale=180:320",
                str(folder / f"{index:05d}.jpg"),
            ],
            check=True,
            timeout=60,
        )


def _build_job(data: Path, source: Path) -> str:
    """The smallest job the Classic result screen can actually render."""
    job_id = "j1"
    scenes = [trim_fixture.make_scene(index) for index in range(SCENES)]
    job = trim_fixture.make_job(job_id, source_path=str(source))
    job["source"]["duration"] = DURATION
    job["analysis"].update({
        "scenes": scenes,
        "scene_count": len(scenes),
        "hook_scene": 0,
        "deep_scene_ids": [scene["id"] for scene in scenes],
        "deep_count": len(scenes),
        "plans": pipeline.make_plans(scenes, DURATION, None, 0),
        # The result header prints the analysis time, so the fixture has one.
        "elapsed": 12.5,
        "engine": {},
    })
    job_dir = data / "jobs" / job_id
    _thumbs(job_dir, source)
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


def test_classic_result_screen_is_a_frame_in_chromium(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    module = _playwright_module()
    if module is None:
        pytest.skip("Node Playwright is not installed")
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is needed for the fixture video")

    source = tmp_path / "source.mp4"
    _source_video(source)
    data = tmp_path / "data"
    (data / "jobs").mkdir(parents=True)
    job_id = _build_job(data, source)

    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    log_path = tmp_path / "uvicorn.log"
    environment = {
        **os.environ,
        "VIBECUT_DATA": str(data),
        # The lane's own edition: `/` must open the Classic page, not Studio.
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
            }
            completed = subprocess.run(
                [node, str(SPEC)],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=180,
            )
            output = (completed.stdout or "") + (completed.stderr or "")
            if completed.returncode == 2:
                pytest.skip(output.strip() or "Playwright cannot run here")
            assert completed.returncode == 0, output
            shots = sorted((tmp_path / "shots").glob("*.png"))
            assert len(shots) == 2, output
        finally:
            _stop(process)
