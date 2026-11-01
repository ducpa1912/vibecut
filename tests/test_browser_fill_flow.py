"""Mounted P2 fill flow: found text, ticks, method picker and fill preview."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("routes_trim")
pytest.importorskip("caption_reflow")

from test_browser_trim import (  # noqa: E402
    _free_port,
    _playwright_module,
    _source_video,
    _stop,
    _wait_for_health,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "trim_job"
SPEC = ROOT / "tests" / "browser" / "fill_flow.spec.mjs"
if str(FIXTURE_DIR) not in sys.path:
    sys.path.insert(0, str(FIXTURE_DIR))
import trim_fixture  # noqa: E402


def test_studio_found_text_and_fill_preview_in_chromium(tmp_path):
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
                "FILL_BASE_URL": base,
                "FILL_JOB_ID": fixture["job_id"],
                "FILL_SCREENSHOT": str(tmp_path / "fill_flow.png"),
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
        finally:
            _stop(process)
