"""Small frame thumbnails for the timeline filmstrip (REQ-20261126-01, T1).

The `/frame` route keeps today's full-size frame when no width is asked for,
and serves a snapped small JPEG, cached under its own name, when one is.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from duckcore import media
from duckcore.main import create_app

HEADERS = {"Authorization": "Bearer test-token"}


def _client(tmp_path: Path, calls: list[float] | None = None) -> tuple[TestClient, dict]:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"not a real video")

    def extract(_source, when):
        if calls is not None:
            calls.append(float(when))
        return Image.new("RGB", (640, 360), (120, 40, 20))

    original = media.extract_frame
    media.extract_frame = extract
    app = create_app("test-token", tmp_path)
    client = TestClient(app)
    client.__enter__()
    created = client.post(
        "/api/projects",
        headers=HEADERS,
        json={"name": "Thumbs", "source_path": str(source)},
    )
    assert created.status_code == 200, created.text
    project = created.json()["project"]
    return client, {"project": project, "restore": original}


def _close(client: TestClient, state: dict) -> None:
    client.__exit__(None, None, None)
    media.extract_frame = state["restore"]


def _jpeg(response) -> Image.Image:
    return Image.open(BytesIO(response.content))


def test_small_frame_snaps_to_the_fixed_width_and_is_cached(tmp_path: Path) -> None:
    calls: list[float] = []
    client, state = _client(tmp_path, calls)
    try:
        url = f"/api/projects/{state['project']['id']}/frame"
        first = client.get(url, params={"time": 1.5, "w": 97, "t": "test-token"})
        assert first.status_code == 200, first.text
        small = _jpeg(first)
        assert small.width == 96
        assert small.height == 54
        assert calls == [1.5]

        cached = client.get(url, params={"time": 1.5, "w": 96, "t": "test-token"})
        assert cached.status_code == 200
        assert _jpeg(cached).size == (96, 54)
        assert calls == [1.5], "the cached thumbnail must not re-read the source"

        file = tmp_path / "projects" / state["project"]["id"] / "frames" / "w96" / "frame_1500.jpg"
        assert file.is_file()
    finally:
        _close(client, state)


def test_each_width_has_its_own_cache_entry(tmp_path: Path) -> None:
    calls: list[float] = []
    client, state = _client(tmp_path, calls)
    try:
        url = f"/api/projects/{state['project']['id']}/frame"
        for width, expected in ((160, 160), (240, 240), (320, 320), (320, 320)):
            response = client.get(url, params={"time": 2, "w": width, "t": "test-token"})
            assert response.status_code == 200, response.text
            assert _jpeg(response).width == expected
        assert calls == [2, 2, 2], "320 is requested once and then reused"
        frames = tmp_path / "projects" / state["project"]["id"] / "frames"
        assert sorted(path.name for path in frames.iterdir()) == ["w160", "w240", "w320"]
    finally:
        _close(client, state)


def test_width_outside_the_range_is_rejected(tmp_path: Path) -> None:
    calls: list[float] = []
    client, state = _client(tmp_path, calls)
    try:
        url = f"/api/projects/{state['project']['id']}/frame"
        for width in (10, 63, 321, 4096):
            response = client.get(url, params={"time": 1, "w": width, "t": "test-token"})
            assert response.status_code == 400, f"{width}: {response.text}"
        assert calls == []
        assert not (tmp_path / "projects" / state["project"]["id"] / "frames").exists()
    finally:
        _close(client, state)


def test_no_width_keeps_todays_full_size_frame(tmp_path: Path) -> None:
    calls: list[float] = []
    client, state = _client(tmp_path, calls)
    try:
        url = f"/api/projects/{state['project']['id']}/frame"
        response = client.get(url, params={"time": 3, "t": "test-token"})
        assert response.status_code == 200, response.text
        assert _jpeg(response).size == (640, 360)
        assert calls == [3]
        file = tmp_path / "projects" / state["project"]["id"] / "frames" / "frame_3000.jpg"
        assert file.is_file()
    finally:
        _close(client, state)
