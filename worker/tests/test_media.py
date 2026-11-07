"""M1 worker tests: real ffmpeg probe, proxy + poster, cache and cancel.

The clip is generated with ffmpeg because the worker needs a real container to
read. No product screen or API response is faked here.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from duckclean_worker.app import app
from duckclean_worker.contract import DeviceClass, JobStatus
from duckclean_worker.signing import sign
from fastapi.testclient import TestClient
from httpx import Response

FFMPEG = "ffmpeg"


def _clip(path: Path, width: int = 1280, height: int = 720, duration: float = 5.0) -> None:
    cmd = [
        FFMPEG,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size={width}x{height}:duration={duration}:rate=30",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=44100:cl=stereo",
        "-map",
        "0:0",
        "-map",
        "1:0",
        "-t",
        str(duration),
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "64k",
        str(path),
    ]
    import subprocess

    subprocess.run(cmd, check=True, capture_output=True)


@pytest.fixture()
def clip(tmp_path: Path) -> Path:
    path = tmp_path / "source.mp4"
    _clip(path)
    return path


@pytest.fixture()
def app_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DUCKCLEAN_HMAC_SECRET", "test-worker-secret")
    monkeypatch.setenv("DUCKCLEAN_WORKER_ALLOW_LOCAL", "1")
    with TestClient(app) as client:
        yield client


def _expires() -> str:
    return (datetime.now(UTC) + timedelta(minutes=15)).isoformat()


def _url(path: Path, method: str = "GET") -> dict[str, object]:
    return {
        "url": path.as_uri(),
        "method": method,
        "headers": {"content-type": "video/mp4"} if method == "PUT" else {},
        "expires_at": _expires(),
    }


def _signed(
    client: TestClient,
    method: str,
    url: str,
    payload: dict[str, object],
    secret: str = "test-worker-secret",
) -> Response:
    body = json.dumps(payload).encode()
    return cast(
        Response,
        client.request(
            method,
            url,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-DuckClean-Signature": sign(secret, body),
            },
        ),
    )


def _probe_body(clip: Path, job_id: UUID) -> dict[str, object]:
    return {"job_id": str(job_id), "input": _url(clip)}


def _proxy_body(clip: Path, tmp_path: Path, job_id: UUID) -> dict[str, object]:
    return {
        "job_id": str(job_id),
        "input": _url(clip),
        "output": _url(tmp_path / "proxy.mp4", "PUT"),
        "poster": _url(tmp_path / "poster.jpg", "PUT"),
        "options": {"max_height": 720, "poster_at_ms": 2000},
    }


def test_health_is_declared_not_stubbed(app_client: TestClient) -> None:
    response = app_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["contract_version"] == "1.0.0"
    assert data["device_class"] == DeviceClass.CPU
    assert data["ffmpeg_version"].startswith("ffmpeg ")
    assert data["models"][0]["available"] is True

    unsigned = app_client.post(
        "/v1/cancel",
        json={"job_id": str(uuid4())},
        headers={"X-DuckClean-Signature": "missing"},
    )
    assert unsigned.status_code == 401
    body = unsigned.json()
    assert body["error"]["code"] == "invalid_signature"
    assert body["error"]["retryable"] is False


def test_probe_then_proxy_roundtrip(app_client: TestClient, clip: Path, tmp_path: Path) -> None:
    probe = _signed(app_client, "POST", "/v1/probe", _probe_body(clip, uuid4()))
    assert probe.status_code == 200, probe.text
    data = probe.json()
    assert data["status"] == JobStatus.SUCCEEDED
    assert data["probe"]["duration_ms"] == pytest.approx(5000, abs=100)
    assert data["probe"]["display_width"] == 1280
    assert data["probe"]["display_height"] == 720
    assert data["probe"]["fps_num"] == 30
    assert data["probe"]["frame_count"] >= 149
    assert data["probe"]["has_audio"] is True
    assert data["usage"]["device_class"] == DeviceClass.CPU
    assert data["usage"]["compute_seconds"] > 0

    proxy = _signed(
        app_client,
        "POST",
        "/v1/proxy",
        _proxy_body(clip, tmp_path, uuid4()),
    )
    assert proxy.status_code == 200, proxy.text
    facts = proxy.json()
    assert facts["status"] == JobStatus.SUCCEEDED
    assert facts["proxy"]["width"] == 1280
    assert facts["proxy"]["height"] == 720
    assert facts["proxy"]["fps_num"] == 30
    assert facts["proxy"]["bytes"] > 0
    assert facts["poster"]["width"] > 0
    assert facts["poster"]["bytes"] > 0
    assert (tmp_path / "proxy.mp4").stat().st_size > 0
    assert (tmp_path / "poster.jpg").stat().st_size > 0


def test_duplicate_job_id_returns_cached(app_client: TestClient, clip: Path) -> None:
    body = _probe_body(clip, uuid4())
    first = _signed(app_client, "POST", "/v1/probe", body)
    second = _signed(app_client, "POST", "/v1/probe", body)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["probe"] == second.json()["probe"]


def test_cancel_reports_not_running(app_client: TestClient) -> None:
    response = _signed(
        app_client,
        "POST",
        "/v1/cancel",
        {"job_id": str(uuid4())},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "not_running"
    assert data["cancelled"] is False


def test_cancel_after_finished_reports_finished(app_client: TestClient, clip: Path) -> None:
    job_id = uuid4()
    probe = _signed(app_client, "POST", "/v1/probe", _probe_body(clip, job_id))
    assert probe.status_code == 200, probe.text

    cancel = _signed(app_client, "POST", "/v1/cancel", {"job_id": str(job_id)})
    assert cancel.status_code == 200
    data = cancel.json()
    assert data["status"] == "already_finished"
    assert data["cancelled"] is False


def test_probe_missing_input_is_rejected(app_client: TestClient) -> None:
    body: dict[str, object] = {
        "job_id": str(uuid4()),
        "input": _url(Path("/does/not/exist.mp4")),
    }
    response = _signed(app_client, "POST", "/v1/probe", body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "source_unreadable"


def test_probe_requires_a_signature(app_client: TestClient, clip: Path) -> None:
    body = _probe_body(clip, uuid4())
    response = app_client.post("/v1/probe", json=body)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_signature"
