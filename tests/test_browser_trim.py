"""Mounted Studio trim drag, driven by Node Playwright.

The test starts uvicorn on a free loopback port with a scratch VIBECUT_DATA
directory, then runs ``tests/browser/trim_drag.spec.mjs`` against it. The
server is always stopped, including when the spec skips or fails.
"""

from __future__ import annotations

import glob
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

pytest.importorskip("routes_trim")

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "trim_job"
SPEC = ROOT / "tests" / "browser" / "trim_drag.spec.mjs"
if str(FIXTURE_DIR) not in sys.path:
    sys.path.insert(0, str(FIXTURE_DIR))
import trim_fixture  # noqa: E402


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
            "-i", "color=c=red:s=1080x1920:d=26:r=10",
            "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast",
            "-movflags", "+faststart", str(path),
        ],
        check=True,
        timeout=60,
    )


def test_studio_trim_drag_in_chromium(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    module = _playwright_module()
    if module is None:
        pytest.skip("Node Playwright is not installed")
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is needed for a stable preview")

    source = tmp_path / "source.mp4"
    _source_video(source)
    data = tmp_path / "data"
    (data / "jobs").mkdir(parents=True)
    fixture = trim_fixture.build_browser_job(
        data, source_path=str(source), source_duration=26.0,
    )

    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    log_path = tmp_path / "uvicorn.log"
    environment = {
        **os.environ,
        "VIBECUT_DATA": str(data),
        "VIBECUT_EXPERIMENTAL": "1",
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
                "TRIM_BASE_URL": base,
                "TRIM_JOB_ID": fixture["job_id"],
                "TRIM_SCREENSHOT": str(tmp_path / "trim_drag.png"),
                "PLAYWRIGHT_MODULE": module.as_uri(),
            }
            completed = subprocess.run(
                [node, str(SPEC)],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )
            output = (completed.stdout or "") + (completed.stderr or "")
            if completed.returncode == 2:
                pytest.skip(output.strip() or "Playwright cannot run here")
            assert completed.returncode == 0, output
        finally:
            _stop(process)
