"""M2b worker tests: OCR on a real clip with real text.

The clip is built by drawing text into an image and compositing it over a real
H.264 encode, so the detector has something genuine to read. Nothing here
asserts a fake detection: if the OCR model is missing the health route says so
and this test fails rather than silently passing.
"""

from __future__ import annotations

import base64
import io
import json
import subprocess
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from duckclean_worker import detect as detect_module
from duckclean_worker.app import app
from duckclean_worker.contract import DetectOptions
from duckclean_worker.signing import sign
from fastapi.testclient import TestClient
from httpx import Response
from PIL import Image, ImageDraw, ImageFont


def _run(args: list[str]) -> None:
    subprocess.run(args, check=True, capture_output=True)


def _text_image(path: Path, width: int, height: int) -> None:
    image = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 64)
    except OSError:
        font = ImageFont.load_default(size=64)
    draw.text((20, 20), "DUCK", fill=(255, 255, 255), font=font)
    image.save(path)


def _text_clip(path: Path, work: Path) -> None:
    still = work / "text.png"
    _text_image(still, 320, 160)
    _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x14213d:size=640x360:rate=10:duration=1.5",
            "-loop",
            "1",
            "-i",
            str(still),
            "-filter_complex",
            "[0:v][1:v]overlay=60:80,format=yuv420p[v]",
            "-map",
            "[v]",
            "-frames:v",
            "15",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            str(path),
        ]
    )


@pytest.fixture()
def text_clip(tmp_path: Path) -> Path:
    path = tmp_path / "text.mp4"
    _text_clip(path, tmp_path)
    return path


@pytest.fixture()
def app_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DUCKCLEAN_HMAC_SECRET", "test-worker-secret")
    monkeypatch.setenv("DUCKCLEAN_WORKER_ALLOW_LOCAL", "1")
    with TestClient(app) as client:
        yield client


def _signed(client: TestClient, url: str, payload: dict[str, object]) -> Response:
    body = json.dumps(payload).encode()
    return cast(
        Response,
        client.request(
            "POST",
            url,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-DuckClean-Signature": sign("test-worker-secret", body),
            },
        ),
    )


def _input(clip: Path) -> dict[str, object]:
    return {
        "url": clip.as_uri(),
        "method": "GET",
        "headers": {"content-type": "video/mp4"},
        "expires_at": (datetime.now(UTC) + timedelta(minutes=15)).isoformat(),
    }


def _probe(client: TestClient, clip: Path) -> dict[str, object]:
    response = _signed(client, "/v1/probe", {"job_id": str(uuid4()), "input": _input(clip)})
    assert response.status_code == 200, response.text
    return cast(dict[str, object], response.json()["probe"])


def test_health_reports_the_real_ocr_model(app_client: TestClient) -> None:
    models = app_client.get("/health").json()["models"]
    by_name = {model["name"]: model for model in models}
    if not by_name["ocr"]["available"]:
        pytest.fail(f"OCR model is unavailable: {by_name['ocr']['reason']}")
    assert by_name["logo"]["available"] is False
    assert by_name["logo"]["reason"]


def test_detect_reads_burnt_in_text(app_client: TestClient, text_clip: Path) -> None:
    probe = _probe(app_client, text_clip)
    frame_count = cast(int, probe["frame_count"])
    response = _signed(
        app_client,
        "/v1/detect",
        {
            "job_id": str(uuid4()),
            "input": _input(text_clip),
            "probe": probe,
            "revision": "r" * 64,
            "beats": [{"id": str(uuid4()), "index": 0, "start_frame": 0, "end_frame": frame_count}],
            "detect": {"max_width": 640},
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["revision"] == "r" * 64
    coverage = data["coverage"]
    assert coverage["ocr_available"] is True
    assert coverage["logo_model_available"] is False
    assert coverage["frames_read"] + coverage["frames_skipped"] == coverage["frames_total"]
    assert coverage["frames_total"] == frame_count
    assert coverage["truncated"] is False
    assert "logo_model_unavailable" in coverage["warnings"]
    assert coverage["effective_fps_milli"] == 10_000

    text_groups = [group for group in data["groups"] if group["kind"] == "text"]
    assert text_groups, data["groups"]
    read = " ".join((group["sample_text"] or "") for group in text_groups).upper()
    assert "DUCK" in read

    group = text_groups[0]
    member = group["members"][0]
    assert member["range_mode"] == "ranges"
    assert member["ranges"]
    assert member["provenance"] == "ocr"
    assert member["confidence_milli"] > 0
    mask = member["mask"]
    assert mask["format"] == "png"
    assert mask["r2_key"] == ""
    assert mask["png_base64"]
    image = Image.open(io.BytesIO(base64.b64decode(mask["png_base64"])))
    assert image.size == (probe["display_width"], probe["display_height"])


def test_user_region_is_a_whole_source_group(app_client: TestClient, text_clip: Path) -> None:
    probe = _probe(app_client, text_clip)
    frame_count = cast(int, probe["frame_count"])
    response = _signed(
        app_client,
        "/v1/detect",
        {
            "job_id": str(uuid4()),
            "input": _input(text_clip),
            "probe": probe,
            "revision": "s" * 64,
            "beats": [{"id": str(uuid4()), "index": 0, "start_frame": 0, "end_frame": frame_count}],
            "detect": {
                "text": False,
                "regions": [{"box": {"x": 40, "y": 40, "w": 200, "h": 100}}],
            },
        },
    )
    assert response.status_code == 200, response.text
    groups = response.json()["groups"]
    assert len(groups) == 1
    assert groups[0]["kind"] == "user_box"
    member = groups[0]["members"][0]
    assert member["range_mode"] == "whole_source"
    assert member["ranges"] == []
    assert member["provenance"] == "user_box"
    assert member["box"] == {"x": 40, "y": 40, "w": 200, "h": 100}


def test_truncated_scan_reports_real_effective_fps(
    monkeypatch: pytest.MonkeyPatch, text_clip: Path
) -> None:
    from duckclean_worker.contract import DetectBeat
    from duckclean_worker.detect import detect_file

    monkeypatch.setattr(detect_module, "MAX_OCR_FRAMES", 0)
    _, coverage, _ = detect_file(
        text_clip,
        display_width=640,
        display_height=360,
        beats=[DetectBeat(id=uuid4(), index=0, start_frame=0, end_frame=15)],
        frame_count=15,
        fps_num=10,
        fps_den=1,
        options=DetectOptions(),
    )
    assert coverage.truncated is True
    assert coverage.frames_read == 0
    assert coverage.frames_skipped == 15
    assert coverage.effective_fps_milli == 0


def test_scope_does_not_claim_unread_beats(text_clip: Path) -> None:
    from duckclean_worker.contract import DetectBeat
    from duckclean_worker.detect import detect_file

    groups, coverage, _ = detect_file(
        text_clip,
        display_width=640,
        display_height=360,
        beats=[DetectBeat(id=uuid4(), index=1, start_frame=5, end_frame=10)],
        frame_count=15,
        fps_num=10,
        fps_den=1,
        options=DetectOptions(),
    )
    assert coverage.frames_total == 5
    assert coverage.frames_read + coverage.frames_skipped == 5
    assert all(group.members[0].ranges[0].start_frame >= 5 for group in groups)


def test_missing_ocr_is_reported_not_skipped(
    monkeypatch: pytest.MonkeyPatch, text_clip: Path
) -> None:
    from duckclean_worker.contract import DetectBeat
    from duckclean_worker.detect import detect_file

    monkeypatch.setattr(detect_module, "ocr_engine", lambda: (None, "not_installed"))
    groups, coverage, models = detect_file(
        text_clip,
        display_width=640,
        display_height=360,
        beats=[DetectBeat(id=uuid4(), index=0, start_frame=0, end_frame=15)],
        frame_count=15,
        fps_num=10,
        fps_den=1,
        options=DetectOptions(),
    )
    assert groups == []
    assert coverage.ocr_available is False
    assert coverage.frames_read == 0
    assert coverage.frames_skipped == 15
    assert "ocr_unavailable" in [warning.value for warning in coverage.warnings]
    assert models["ocr"] == "not_installed"
