"""M2a worker tests: beat dissection on real files, plus the pure planner.

The planner is a function of frame_count, fps, cut frames and params, so its
exact output can be asserted. The route test scans a real two-scene clip with
ffmpeg: no cut is invented and the spans must tile the source.
"""

from __future__ import annotations

import itertools
import json
import subprocess
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from duckclean_worker.app import app
from duckclean_worker.contract import BeatBoundary, DissectParams
from duckclean_worker.dissect import plan_beats, sha256_file, snap_to_frames
from duckclean_worker.signing import sign
from fastapi.testclient import TestClient
from httpx import Response


def _run(args: list[str]) -> None:
    subprocess.run(args, check=True, capture_output=True)


def _two_scene_clip(path: Path) -> None:
    """Red for two seconds, then blue: ffmpeg must see exactly one cut."""
    _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:size=640x360:duration=2:rate=30",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:size=640x360:duration=2:rate=30",
            "-filter_complex",
            "[0:v][1:v]concat=n=2:v=1:a=0,format=yuv420p[v]",
            "-map",
            "[v]",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            str(path),
        ]
    )


@pytest.fixture()
def scene_clip(tmp_path: Path) -> Path:
    path = tmp_path / "scenes.mp4"
    _two_scene_clip(path)
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


def _probe(client: TestClient, clip: Path) -> dict[str, object]:
    response = _signed(
        client,
        "/v1/probe",
        {
            "job_id": str(uuid4()),
            "input": {
                "url": clip.as_uri(),
                "method": "GET",
                "headers": {"content-type": "video/mp4"},
                "expires_at": (datetime.now(UTC) + timedelta(minutes=15)).isoformat(),
            },
        },
    )
    assert response.status_code == 200, response.text
    return cast(dict[str, object], response.json()["probe"])


def test_plan_beats_caps_static_span() -> None:
    beats = plan_beats(
        frame_count=300,
        fps_num=30,
        fps_den=1,
        cut_frames=[],
        params=DissectParams(max_seconds_milli=4000, min_seconds_milli=1000),
    )
    assert [(b.start_frame, b.end_frame) for b in beats] == [
        (0, 120),
        (120, 240),
        (240, 300),
    ]
    assert beats[0].boundary is BeatBoundary.START
    assert [b.boundary for b in beats[1:]] == [BeatBoundary.CAP, BeatBoundary.CAP]
    assert [b.index for b in beats] == [0, 1, 2]


def test_plan_beats_splits_on_scene_and_merges_short_spans() -> None:
    # A cut 10 frames in is under the 1 s minimum: it must merge into beat 0.
    # The cut at frame 90 is legal and starts its own beat.
    beats = plan_beats(
        frame_count=200,
        fps_num=30,
        fps_den=1,
        cut_frames=[10, 90, 95],
        params=DissectParams(max_seconds_milli=4000, min_seconds_milli=1000),
    )
    assert [(b.start_frame, b.end_frame, b.boundary) for b in beats] == [
        (0, 90, BeatBoundary.START),
        (90, 200, BeatBoundary.SCENE),
    ]


def test_plan_beats_caps_between_scene_cuts() -> None:
    beats = plan_beats(
        frame_count=400,
        fps_num=30,
        fps_den=1,
        cut_frames=[300],
        params=DissectParams(max_seconds_milli=2000, min_seconds_milli=500),
    )
    assert [(b.start_frame, b.end_frame) for b in beats] == [
        (0, 60),
        (60, 120),
        (120, 180),
        (180, 240),
        (240, 300),
        (300, 360),
        (360, 400),
    ]
    assert beats[5].boundary is BeatBoundary.SCENE


def test_snap_to_frames_is_stable() -> None:
    # Both timestamps land on frame 60 and collapse to one cut; frame 0 never counts.
    assert snap_to_frames([0.0, 1.999, 2.0], 30, 1) == [60]
    assert snap_to_frames([0.0], 30, 1) == []


def test_dissect_route_tiles_a_real_two_scene_clip(
    app_client: TestClient, scene_clip: Path
) -> None:
    probe = _probe(app_client, scene_clip)
    response = _signed(
        app_client,
        "/v1/dissect",
        {
            "job_id": str(uuid4()),
            "input": {
                "url": scene_clip.as_uri(),
                "method": "GET",
                "headers": {"content-type": "video/mp4"},
                "expires_at": (datetime.now(UTC) + timedelta(minutes=15)).isoformat(),
            },
            "probe": probe,
            "params": {"max_seconds_milli": 4000, "min_seconds_milli": 1000},
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    beats = data["beats"]
    assert data["source_sha256"] == sha256_file(scene_clip)
    assert beats[0]["start_frame"] == 0
    assert beats[-1]["end_frame"] == probe["frame_count"]
    for previous, beat in itertools.pairwise(beats):
        assert beat["start_frame"] == previous["end_frame"]
        assert beat["index"] == previous["index"] + 1
    # Colour change at 2 s must produce a scene boundary near frame 60.
    exits = [
        beat for beat in beats if beat["boundary"] == "scene" and abs(beat["start_frame"] - 60) <= 3
    ]
    assert exits, beats
    assert data["usage"]["input_bytes"] == scene_clip.stat().st_size


def test_dissect_is_idempotent_by_job_id(app_client: TestClient, scene_clip: Path) -> None:
    probe = _probe(app_client, scene_clip)
    job_id = str(uuid4())
    payload: dict[str, object] = {
        "job_id": job_id,
        "input": {
            "url": scene_clip.as_uri(),
            "method": "GET",
            "headers": {"content-type": "video/mp4"},
            "expires_at": (datetime.now(UTC) + timedelta(minutes=15)).isoformat(),
        },
        "probe": probe,
    }
    first = _signed(app_client, "/v1/dissect", payload)
    second = _signed(app_client, "/v1/dissect", payload)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["beats"] == second.json()["beats"]
    assert first.json()["source_sha256"] == second.json()["source_sha256"]


def test_dissect_rejects_a_payload_without_an_input(app_client: TestClient) -> None:
    response = _signed(app_client, "/v1/dissect", {"job_id": str(uuid4()), "input": {}})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "payload_invalid"
