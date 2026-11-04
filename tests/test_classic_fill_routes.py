"""Classic's AI fill routes: the engine on the box, the rights gate, the preview.

The preview is a single frame through the real compiler and the real fill
entry point, with the model replaced by a fake; no models, no torch, no video.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

import app
import render
import routes_classic
import textfill


def _scene(index: int, start: float) -> dict:
    return {
        "id": index, "start": start, "end": start + 4.0, "dur": 4.0,
        "mid": start + 2.0, "hook": 60.0, "score": 60.0, "deep": True,
        "visual_score": 60.0, "motion_score": 60.0, "audio_score": 60.0,
        "text_score": 0.0, "ocr": "", "speech": "", "tags": [],
        "crop": {"cx": 0.5, "cy": 0.5}, "crop_mode": "center",
    }


def _job(tmp_path, **overrides) -> dict:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"not really a video")
    job = {
        "id": "classic-fill", "created": 1.0, "updated": 1.0,
        "status": "ready", "progress": 1.0, "message": "Ready", "error": None,
        "source": {
            "path": str(source), "name": "source.mp4", "duration": 20.0,
            "width": 1920, "height": 1080, "fps": 30.0, "size": 16,
            "has_audio": True, "fingerprint": "classic-fill",
        },
        "options": {},
        "analysis": {
            "scene_count": 2, "hook_scene": 0, "deep_count": 2,
            "deep_scene_ids": [0, 1],
            "engine": {"transcript_language": "en"},
            "scenes": [_scene(0, 40.0), _scene(1, 100.0)],
        },
        "renders": {},
    }
    job.update(overrides)
    return job


@pytest.fixture
def classic(tmp_path, monkeypatch):
    data = tmp_path / "data"
    jobs = data / "jobs"
    (data / "sources").mkdir(parents=True)
    jobs.mkdir(parents=True)
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.setattr(app, "SOURCES", data / "sources")
    monkeypatch.setattr(app, "SHARES", tmp_path / "shares.json")
    monkeypatch.delenv("VIBECUT_FILL_MODELS", raising=False)
    monkeypatch.delenv("VIBECUT_RIGHTS_LOCK", raising=False)
    job = _job(tmp_path)
    directory = jobs / job["id"]
    directory.mkdir()
    (directory / "job.json").write_text(json.dumps(job), encoding="utf-8")
    client = TestClient(app.app)
    return client, tmp_path


def _ready(**overrides) -> dict:
    status = {
        "available": True,
        "path": "/models/fill",
        "missing": [],
        "files": [],
        "engines": {
            "sttn": {"id": "sttn", "ready": True, "reason": "", "model": True},
            "lama": {"id": "lama", "ready": True, "reason": "", "model": True},
        },
        "default": "sttn",
        "preview": "lama",
        "methods": ["blur", "cover", "crop", "sttn"],
        "note": "AI fill is ready with STTN and LaMa.",
    }
    status.update(overrides)
    return status


def _clips() -> list[dict]:
    return routes_classic._classic_clips([
        {"scene": 0, "role": "hook", "start": 40.0, "end": 44.0, "dur": 4.0},
        {"scene": 1, "role": "beat", "start": 100.0, "end": 104.0, "dur": 4.0},
    ])


def _fill_box(**overrides) -> dict:
    box = {
        "id": "cl01",
        "method": "fill",
        "engine": "sttn",
        "box": {"x": 0.1, "y": 0.7, "w": 0.8, "h": 0.16},
        "ranges": [{"start": 0.0, "end": 4.0}],
        "label": "Remove subtitle",
        "kind": "subtitle",
        "source": "scan",
    }
    box.update(overrides)
    return box


# ------------------------------------------------------------------ the box


def test_a_fill_box_saves_its_engine_and_comes_back(classic, monkeypatch):
    client, _ = classic
    monkeypatch.setattr(routes_classic, "classic_fill_status", lambda: _ready())
    saved = client.put(
        "/api/classic/jobs/classic-fill/text",
        json={"clips": _clips(), "clean": [_fill_box(engine="lama")]},
    )
    assert saved.status_code == 200, saved.text
    cut = saved.json()["cut"]
    assert cut["clean"][0]["method"] == "fill"
    assert cut["clean"][0]["engine"] == "lama"

    looked_up = client.post(
        "/api/classic/jobs/classic-fill/text", json={"clips": _clips()},
    )
    assert looked_up.json()["cut"]["clean"][0]["engine"] == "lama"


def test_a_fill_box_compiles_to_a_fill_segment(classic, monkeypatch):
    client, _ = classic
    monkeypatch.setattr(routes_classic, "classic_fill_status", lambda: _ready())
    rendered = {}

    def fake_frame(path, meta, job_dir, compiled, at, **options):
        rendered.update({"compiled": compiled, "at": at})
        return b"\xff\xd8frame"

    monkeypatch.setattr(routes_classic.render, "render_story_frame", fake_frame)
    response = client.post(
        "/api/classic/jobs/classic-fill/frame",
        json={"clips": _clips(), "clean": [_fill_box()], "t": 1.0},
    )
    assert response.status_code == 200, response.text
    segment = rendered["compiled"]["segments"][0]
    assert segment["clean_ids"] == []
    assert segment["fill"]["method"] == "sttn"
    # Cut time 0-4 s on a clip at source 40 s is source 40-44 s.
    assert segment["fill"]["layers"][0]["ranges"] == [{"start": 40.0, "end": 44.0}]
    # The picture on the frame is not filled: say so where the client can read.
    assert response.headers["x-vibecut-fill"] == "1"


def test_a_fill_box_on_a_watermark_is_refused(classic, monkeypatch):
    client, _ = classic
    monkeypatch.setattr(routes_classic, "classic_fill_status", lambda: _ready())
    response = client.put(
        "/api/classic/jobs/classic-fill/text",
        json={"clips": _clips(), "clean": [_fill_box(kind="watermark")]},
    )
    assert response.status_code == 409, response.text
    assert "watermark" in response.text.lower()


def test_the_rights_lock_refuses_fill_without_the_tick(classic, monkeypatch):
    import settings_store

    client, _ = classic
    monkeypatch.setattr(routes_classic, "classic_fill_status", lambda: _ready())
    settings_store.save_settings({"rights": {"lock": True}})
    job = app.load_job("classic-fill")
    job["rights"] = {"attested": False, "source": "import", "at": 1.0}
    (app._job_dir("classic-fill") / "job.json").write_text(
        json.dumps(job), encoding="utf-8",
    )
    response = client.put(
        "/api/classic/jobs/classic-fill/text",
        json={"clips": _clips(), "clean": [_fill_box()]},
    )
    assert response.status_code == 409
    assert "attestation" in response.text


# ------------------------------------------------------------------ the preview


@pytest.fixture
def preview_env(classic, monkeypatch):
    client, tmp_path = classic
    monkeypatch.setattr(routes_classic, "classic_fill_status", lambda: _ready())
    models = tmp_path / "models" / "fill"
    models.mkdir(parents=True)
    (models / textfill.MODEL_FILES["lama"]).write_bytes(b"x" * 32)
    monkeypatch.setenv("VIBECUT_FILL_MODELS", str(models))
    calls = {"fill": [], "read": [], "cache": 0}

    def fake_read(path, width, height, at):
        calls["read"].append(at)
        return np.full((height, width, 3), 40, dtype=np.uint8)

    def fake_fill(frame_rgb, rects, **options):
        calls["fill"].append({"rects": rects, **options})
        out = frame_rgb.copy()
        out[:, :] = 200
        return out

    def fake_preview_jpeg(png, output, chain):
        calls["cache"] += 1
        output.write_bytes(png.read_bytes())

    def fake_burn(png, overlays, output, out_w, out_h, at, cache):
        output.write_bytes(png.read_bytes())

    monkeypatch.setattr(routes_classic, "_read_source_frame", fake_read)
    monkeypatch.setattr(textfill, "fill_frame", fake_fill)
    monkeypatch.setattr(routes_classic, "_render_preview_jpeg", fake_preview_jpeg)
    monkeypatch.setattr(routes_classic.render, "_burn_frame", fake_burn)
    monkeypatch.setattr(textfill, "release_fillers", lambda: calls.__setitem__("released", True))
    return client, calls


def test_the_preview_fills_unsaved_boxes_at_the_right_source_time(preview_env):
    client, calls = preview_env
    response = client.post(
        "/api/classic/jobs/classic-fill/fill/preview",
        json={
            "clips": _clips(),
            "clean": [_fill_box()],
            "t": 1.0,
            "aspect": "9:16",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["before"].startswith("data:image/jpeg;base64,")
    assert payload["after"].startswith("data:image/jpeg;base64,")
    assert payload["method"] == "lama"
    # The render will use the box's engine; say which, so the copy can too.
    assert payload["render_method"] == "sttn"
    assert payload["cached"] is False
    # t=1.0 on a clip that starts at source 40 s reads source 41 s.
    assert calls["read"] == [41.0]
    assert calls["fill"] and calls["fill"][0]["rects"]
    x0, y0, x1, y1 = calls["fill"][0]["rects"][0]
    # layer_rects pads the box slightly; the rect must still cover it.
    assert x0 <= int(0.1 * 1920) and x1 >= int(0.9 * 1920)
    assert y0 <= int(0.7 * 1080) and y1 >= int(0.86 * 1080)
    assert calls.get("released") is True


def test_the_preview_is_cached_by_edit_frame_and_model(preview_env):
    client, calls = preview_env
    body = {"clips": _clips(), "clean": [_fill_box()], "t": 1.0}
    first = client.post("/api/classic/jobs/classic-fill/fill/preview", json=body)
    assert first.status_code == 200, first.text
    second = client.post("/api/classic/jobs/classic-fill/fill/preview", json=body)
    assert second.status_code == 200, second.text
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert len(calls["fill"]) == 1

    # A different box is a different frame to fill, not a cache hit.
    moved = dict(body)
    moved["clean"] = [_fill_box(box={"x": 0.1, "y": 0.4, "w": 0.8, "h": 0.16})]
    third = client.post("/api/classic/jobs/classic-fill/fill/preview", json=moved)
    assert third.status_code == 200, third.text
    assert third.json()["cached"] is False
    assert len(calls["fill"]) == 2


def test_the_preview_refuses_while_a_fill_is_running(preview_env):
    client, calls = preview_env
    assert render.FILL_LOCK.acquire(blocking=False)
    try:
        response = client.post(
            "/api/classic/jobs/classic-fill/fill/preview",
            json={"clips": _clips(), "clean": [_fill_box()], "t": 1.0},
        )
    finally:
        render.FILL_LOCK.release()
    assert response.status_code == 409, response.text
    assert response.json()["error"] == "fill_running"
    assert "Wait for the render" in response.json()["message"]
    assert calls["fill"] == []


def test_the_preview_says_which_frame_has_no_fill_box(preview_env):
    client, _ = preview_env
    response = client.post(
        "/api/classic/jobs/classic-fill/fill/preview",
        json={
            "clips": _clips(),
            "clean": [_fill_box(ranges=[{"start": 6.0, "end": 8.0}])],
            "t": 1.0,
        },
    )
    assert response.status_code == 422
    assert "No AI fill box" in response.json()["detail"]
