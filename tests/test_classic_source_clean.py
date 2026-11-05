"""Phase 1 Source Clean backend: extraction-only jobs, Check, fill, render.

Most tests fake the probe, the model and ffmpeg so they run without media.
The one end-to-end render test reads the founder's real ``wide-video`` through
``tests/real_media.py`` and skips when that file is absent. No test generates
media; ``tests/test_no_generated_media.py`` owns that rule.
"""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
import time
from concurrent.futures import Future
from pathlib import Path

import numpy as np
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app
import clean_source
import job_queue
import pipeline
import real_media
import render
import routes_check
import routes_classic
import textfill

SOURCE_META = {
    "duration": 1.2,
    "width": 320,
    "height": 180,
    "fps": 30.0,
    "has_audio": True,
    "size": 1024,
    "rotation": 0.0,
    "fingerprint": "source-clean-test",
}


class CapturePool:
    """Record submitted workers. Clean jobs must not submit analysis."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def submit(self, fn, *args, **kwargs):
        self.calls.append((fn, args, kwargs))
        return type("Task", (), {"id": "captured", "terminal": False})()

    def find_key(self, *args, **kwargs):
        return None

    def get(self, *args, **kwargs):
        return None


class ParkedPool(CapturePool):
    """A submitted task that stays running, so a second start is refused."""

    def __init__(self) -> None:
        super().__init__()
        self.submitted = False
        self.task = type(
            "Task", (), {
                "id": "parked", "terminal": False,
                "state": job_queue.QueueState.RUNNING,
            },
        )()

    def submit(self, fn, *args, **kwargs):
        super().submit(fn, *args, **kwargs)
        self.submitted = True
        return self.task

    def find_key(self, *args, **kwargs):
        return self.task if self.submitted else None

    def get(self, *args, **kwargs):
        return self.task if self.submitted else None


class InlineExecutor:
    """Run scheduler work on the calling thread so route tests stay fast."""

    def submit(self, fn, *args, **kwargs):
        future: Future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as exc:  # noqa: BLE001
            future.set_exception(exc)
        return future

    def shutdown(self, *args, **kwargs):
        return None


def _wait(getter, predicate, timeout: float = 20.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = getter()
        if predicate(last):
            return last
        time.sleep(0.05)
    raise AssertionError(f"timed out; last value was {last!r}")


@pytest.fixture
def classic(tmp_path, monkeypatch):
    data = tmp_path / "data"
    jobs = data / "jobs"
    sources = data / "sources"
    (data / "models" / "fill").mkdir(parents=True)
    jobs.mkdir(parents=True)
    sources.mkdir()
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.setattr(app, "SOURCES", sources)
    monkeypatch.setattr(app, "SHARES", tmp_path / "shares.json")
    monkeypatch.delenv("VIBECUT_FILL_MODELS", raising=False)
    client = TestClient(app.app)
    return client, tmp_path, data


@pytest.fixture
def source_file(tmp_path, monkeypatch):
    """A placeholder file plus a faked probe: no media is generated."""
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"not really a video")
    meta = dict(SOURCE_META, size=path.stat().st_size)
    monkeypatch.setattr(app.pipeline, "probe", lambda _path: dict(meta))
    return path, meta


def _path_job(client, video: Path, mode: str = "clean") -> dict:
    response = client.post(
        "/api/jobs/path", json={"path": str(video), "mode": mode},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    if mode == "clean":
        assert body["status"] == "source_ready"
    return app.load_job(body["id"])


def _fake_job(
    job_id: str, source: Path, meta: dict, *, has_audio: bool = True,
) -> dict:
    job = {
        "id": job_id,
        "created": 1.0,
        "updated": 1.0,
        "status": "source_ready",
        "progress": 1.0,
        "message": "Source ready",
        "error": None,
        "mode": "clean",
        "source": {"path": str(source), "name": source.name, **meta,
                   "has_audio": has_audio},
        "options": {},
        "analysis": None,
        "renders": {},
        "artifacts": {},
        "artifact_ids": [],
    }
    directory = app.JOBS / job_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "job.json").write_text(json.dumps(job), encoding="utf-8")
    return job


def _source_clip(job: dict) -> dict:
    return clean_source.source_clip(job["source"]["duration"])


def _blur_box(**overrides) -> dict:
    box = {
        "id": "cl01",
        "method": "blur",
        "box": {"x": 0.2, "y": 0.2, "w": 0.3, "h": 0.15},
        "radius": 8,
    }
    box.update(overrides)
    return box


def _fill_box(**overrides) -> dict:
    box = {
        "id": "cl01",
        "method": "fill",
        "engine": "lama",
        "box": {"x": 0.1, "y": 0.7, "w": 0.8, "h": 0.16},
        "ranges": [],
        "label": "Remove subtitle",
        "kind": "subtitle",
    }
    box.update(overrides)
    return box


def _ready_fill() -> dict:
    return {
        "available": True,
        "path": "/models/fill",
        "missing": [],
        "files": [],
        "engines": {
            "lama": {"id": "lama", "ready": True, "reason": "", "model": True},
        },
        "default": "lama",
        "preview": "lama",
        "methods": ["blur", "crop", "lama"],
        "note": "AI fill is ready with LaMa.",
    }


def _install_dummy_model(data: Path) -> None:
    (data / "models" / "fill" / textfill.MODEL_FILES["lama"]).write_bytes(b"x" * 32)


# ------------------------------------------------------------------ job mode


def test_path_clean_mode_is_source_ready_without_analysis(
    classic, source_file, monkeypatch,
):
    client, _tmp, _data = classic
    video, _meta = source_file
    pool = CapturePool()
    monkeypatch.setattr(app, "analysis_pool", pool)

    response = client.post(
        "/api/jobs/path", json={"path": str(video), "mode": "clean"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "source_ready"
    assert pool.calls == []

    job = app.load_job(body["id"])
    assert job["status"] == "source_ready"
    assert job["message"] == "Source ready"
    assert job["analysis"] is None
    assert job["mode"] == "clean"
    assert job["source"]["duration"] == SOURCE_META["duration"]
    assert job["source"]["width"] == SOURCE_META["width"]
    assert job["source"]["height"] == SOURCE_META["height"]
    assert job["source"]["fps"] == SOURCE_META["fps"]
    assert job["source"]["fingerprint"] == SOURCE_META["fingerprint"]


def test_upload_clean_mode_skips_analysis(classic, source_file, monkeypatch):
    client, _tmp, _data = classic
    video, _meta = source_file
    pool = CapturePool()
    monkeypatch.setattr(app, "analysis_pool", pool)
    response = client.post(
        "/api/jobs/upload",
        files={"file": ("clip.mp4", video.read_bytes(), "video/mp4")},
        data={"mode": "clean"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "source_ready"
    assert pool.calls == []


def test_unknown_job_mode_is_rejected(classic, source_file):
    client, _tmp, _data = classic
    video, _meta = source_file
    response = client.post(
        "/api/jobs/path", json={"path": str(video), "mode": "vertical"},
    )
    assert response.status_code == 422
    assert "reel or clean" in response.json()["detail"]


# ------------------------------------------------------------------ check


def test_check_runs_on_source_ready_without_analysis(
    classic, source_file, monkeypatch,
):
    client, _tmp, _data = classic
    video, meta = source_file
    monkeypatch.setattr(app, "analysis_pool", CapturePool())
    job = _path_job(client, video)
    monkeypatch.setattr(
        routes_check, "CHECK_POOL",
        job_queue.Scheduler("check-source-test", executor=InlineExecutor()),
    )
    seen = {}

    def sampler(path, job_dir, duration, *, fps, max_frames, **options):
        seen.update({
            "duration": duration, "fps": fps, "max_frames": max_frames,
            "start": options.get("start"), "end": options.get("end"),
        })
        return {
            "vision": True,
            "fps": fps,
            "frames": [{
                "index": 0,
                "t": 0.6,
                "start": 0.6,
                "end": 1.1,
                "text": [{
                    "text": "SOURCE TIME",
                    "confidence": 0.95,
                    "box": {"x": 0.1, "y": 0.6, "w": 0.4, "h": 0.1},
                }],
            }],
        }

    monkeypatch.setattr(pipeline, "read_text_samples", sampler)
    monkeypatch.setattr(pipeline, "extract_audio", lambda *args, **kwargs: None)
    response = client.post(f"/api/jobs/{job['id']}/check", json={})
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["status"] == "ready"
    # No analysis means the whole source: no scoped start/end were passed.
    assert seen["duration"] == pytest.approx(meta["duration"])
    assert seen["start"] is None and seen["end"] is None
    assert report["tracklets"]
    first = report["tracklets"][0]
    window = first["ranges"][0]
    assert window["start"] == pytest.approx(0.6, abs=0.35)
    assert window["end"] > window["start"]
    stored_check = app.load_job(job["id"])["check"]
    assert stored_check["message"] == "1 text region found"
    assert "clean_then_compose" not in stored_check["message"]
    assert stored_check["recommendation"] == report["recommendation"]
    assert app.load_job(job["id"])["analysis"] is None
    fetched = client.get(f"/api/jobs/{job['id']}/check")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "ready"
    assert app.load_job(job["id"])["check"]["status"] == "ready"


def test_check_message_pluralizes_and_keeps_recommendation_field(
    classic, source_file, monkeypatch,
):
    _client, _tmp, _data = classic
    video, meta = source_file
    job = _fake_job("check-plural", video, meta)

    def fake_check(job_id, job, job_dir, **options):
        return {
            "status": "ready",
            "tracklets": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
            "recommendation": "clean_then_compose",
        }

    monkeypatch.setattr(routes_check.detect, "run_check", fake_check)
    routes_check.run_check_job(job["id"], {"sample_text": False, "fps": 0.5})
    record = app.load_job(job["id"])["check"]
    assert record["message"] == "3 text regions found"
    assert "clean_then_compose" not in record["message"]
    assert record["recommendation"] == "clean_then_compose"
    assert record["tracklet_count"] == 3


# ------------------------------------------------------------------ analyze later


def test_analyze_starts_later_and_is_idempotent(
    classic, source_file, monkeypatch,
):
    client, _tmp, _data = classic
    video, _meta = source_file
    monkeypatch.setattr(app, "analysis_pool", CapturePool())
    job = _path_job(client, video)
    assert job["analysis"] is None

    def fake_analysis(job_id):
        current = app.load_job(job_id)
        current["status"] = "ready"
        current["progress"] = 1.0
        current["message"] = "1 moment · hook found"
        current["analysis"] = {
            "scene_count": 1,
            "hook_scene": 0,
            "scenes": [{"id": 0, "start": 0.0, "end": 1.0}],
        }
        app.save_job(current)

    monkeypatch.setattr(app, "run_analysis", fake_analysis)
    monkeypatch.setattr(
        app, "analysis_pool",
        job_queue.Scheduler("analysis-source-test", executor=InlineExecutor()),
    )
    started = client.post(f"/api/jobs/{job['id']}/analyze")
    assert started.status_code == 202, started.text
    assert started.json()["started"] is True
    assert app.load_job(job["id"])["status"] == "ready"

    again = client.post(f"/api/jobs/{job['id']}/analyze")
    assert again.status_code == 200, again.text
    assert again.json()["started"] is False


# ------------------------------------------------------------------ renderer


def _render_source(client, job: dict, clean: list[dict]):
    return client.post(
        f"/api/classic/jobs/{job['id']}/clean/source/render",
        json={"clips": [_source_clip(job)], "clean": clean},
    )


def _wait_ready(client, job_id: str) -> dict:
    return _wait(
        lambda: client.get(f"/api/classic/jobs/{job_id}/clean/source").json(),
        lambda record: record.get("status") in {"ready", "failed", "cancelled"},
    )


def _fake_render_io(monkeypatch, data: Path):
    """Stand-ins for the encoder and mux: no media, still real state changes."""

    def fake_encode(input_path, filters, duration, width, height, fps, output, cancel):
        output.write_bytes(b"clean-video" + b"x" * 2048)
        return None

    def fake_mux(video, source, output, duration, cancel):
        output.write_bytes(Path(video).read_bytes())
        return "copy"

    monkeypatch.setattr(clean_source, "_encode", fake_encode)
    monkeypatch.setattr(clean_source, "_mux_audio", fake_mux)


def test_cache_key_changes_with_fill_keys(classic, source_file, monkeypatch):
    _client, _tmp, _data = classic
    video, meta = source_file
    job = _fake_job("cache-keys", video, meta)
    base = {
        "id": "cl01", "kind": "fill", "method": "lama",
        "box": {"x": 0.1, "y": 0.7, "w": 0.8, "h": 0.16},
        "ranges": [], "tracklet_id": "t1", "fill_keys": 0.0,
    }
    still = clean_source._cache_key(job, [base], meta["duration"], "lama", "model")
    busy = clean_source._cache_key(
        job, [{**base, "fill_keys": 6.0}], meta["duration"], "lama", "model",
    )
    relabelled = clean_source._cache_key(
        job,
        [{
            **base, "id": "cl99", "label": "new label", "source": "scan",
            "tracklet_kind": "subtitle", "text_key": "new text",
        }],
        meta["duration"], "lama", "model",
    )
    assert still != busy
    assert still == relabelled

    monkeypatch.setattr(clean_source, "CHUNK_SECONDS", clean_source.CHUNK_SECONDS + 1)
    assert clean_source._cache_key(
        job, [base], meta["duration"], "lama", "model",
    ) != still


def test_source_render_state_cache_and_part_cleanup(classic, source_file, monkeypatch):
    client, _tmp, data = classic
    video, meta = source_file
    _fake_render_io(monkeypatch, data)
    job = _fake_job("source-render", video, meta)
    started = _render_source(client, job, [_blur_box()])
    assert started.status_code in {200, 202}, started.text
    record = _wait_ready(client, job["id"])
    assert record["status"] == "ready", record
    assert record["cached"] is False
    assert set(record["timings"]) == {"check", "fill", "encode", "mux"}
    assert record["width"] == meta["width"]
    assert record["height"] == meta["height"]
    assert record["duration"] == pytest.approx(meta["duration"])
    assert record["audio_mode"] == "copy"
    output = Path(record["path"])
    assert output.is_file()
    assert not list(output.parent.glob(".*.part.mp4"))

    again = _render_source(client, job, [_blur_box()])
    assert again.status_code == 200, again.text
    second = again.json()
    assert second["status"] == "ready"
    assert second["cached"] is True
    assert Path(second["path"]) == output
    assert second["timings"]["fill"] == 0.0


def test_source_fill_render_uses_prepare_span_and_muxes_audio(
    classic, source_file, monkeypatch,
):
    client, tmp, data = classic
    video, meta = source_file
    monkeypatch.setattr(routes_classic, "classic_fill_status", lambda: _ready_fill())
    _install_dummy_model(data)
    job = _fake_job("source-fill", video, meta)
    filled = tmp / "filled.mp4"
    filled.write_bytes(b"filled-video" + b"x" * 2048)
    calls = []

    def fake_prepare(**options):
        calls.append(options)
        return {
            "path": str(filled), "key": "fake", "cached": False, "method": "lama",
        }

    monkeypatch.setattr(textfill, "prepare_span", fake_prepare)
    monkeypatch.setattr(
        clean_source, "_mux_audio",
        lambda video_path, source, output, duration, cancel: (
            output.write_bytes(Path(video_path).read_bytes()), "copy"
        )[1],
    )
    started = _render_source(client, job, [_fill_box()])
    assert started.status_code in {200, 202}, started.text
    record = _wait_ready(client, job["id"])
    assert record["status"] == "ready", record
    assert calls and calls[0]["start"] == 0.0
    assert calls[0]["duration"] == pytest.approx(meta["duration"], abs=0.01)
    assert calls[0]["method"] == "lama"
    assert Path(record["path"]).is_file()
    assert record["audio_mode"] == "copy"


def test_source_cancel_leaves_no_part(classic, source_file, monkeypatch):
    client, _tmp, _data = classic
    video, meta = source_file
    job = _fake_job("source-cancel", video, meta)
    encode_started = threading.Event()
    parts: list[Path] = []

    def slow_encode(input_path, filters, duration, width, height, fps, output, cancel):
        record = app.load_job("source-cancel")["source_clean"]
        part = Path(record["path"]).parent / f".{record['key']}.part.mp4"
        part.write_bytes(b"partial" + b"x" * 2048)
        parts.append(part)
        encode_started.set()
        while not cancel.is_set():
            time.sleep(0.01)
        raise render.RenderCancelled("Render cancelled.")

    monkeypatch.setattr(clean_source, "_encode", slow_encode)
    started = _render_source(client, job, [_blur_box()])
    assert started.status_code in {200, 202}, started.text
    assert encode_started.wait(10), "the render never reached the encoder"
    assert parts and parts[0].is_file()
    cancelled = client.post(f"/api/classic/jobs/{job['id']}/clean/source/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["cancelled"] is True
    assert cancelled.json()["status"] == "cancelling"
    record = _wait(
        lambda: client.get(f"/api/classic/jobs/{job['id']}/clean/source").json(),
        lambda value: value.get("status") == "cancelled",
    )
    assert record["status"] == "cancelled"
    assert record["path"] is None
    assert record["url"] is None
    cache = app._job_dir(job["id"]) / "clean" / "source"
    assert parts[0].is_file() is False
    assert not list(cache.glob(".*.part.mp4"))


def test_source_failure_clears_the_download_path(
    classic, source_file, monkeypatch,
):
    client, _tmp, _data = classic
    video, meta = source_file
    job = _fake_job("source-fail", video, meta)

    def fail_encode(input_path, filters, duration, width, height, fps, output, cancel):
        raise RuntimeError("encoder exploded")

    monkeypatch.setattr(clean_source, "_encode", fail_encode)
    started = _render_source(client, job, [_blur_box()])
    assert started.status_code in {200, 202}, started.text
    record = _wait(
        lambda: client.get(f"/api/classic/jobs/{job['id']}/clean/source").json(),
        lambda value: value.get("status") == "failed",
    )
    assert record["status"] == "failed"
    assert "encoder exploded" in record["error"]
    assert record["path"] is None
    assert record["url"] is None
    assert record["cached"] is False


def test_crop_guard_is_refused_in_source_mode(classic, source_file, monkeypatch):
    client, _tmp, _data = classic
    video, meta = source_file
    job = _fake_job("source-crop", video, meta)
    response = _render_source(
        client, job,
        [_blur_box(method="crop", box={"x": 0.1, "y": 0.1, "w": 0.5, "h": 0.5})],
    )
    assert response.status_code == 422
    assert "keeps the full frame" in response.json()["detail"]


def test_odd_source_dimensions_are_refused_plainly(
    classic, source_file, monkeypatch,
):
    client, _tmp, _data = classic
    video, meta = source_file
    odd = dict(meta, width=321, height=181)
    job = _fake_job("source-odd", video, odd)
    response = _render_source(client, job, [_blur_box()])
    assert response.status_code == 422
    assert "even width and height" in response.json()["detail"]


# ------------------------------------------------------------------ estimate and preview


def test_source_estimate_and_preview_use_source_aspect(
    classic, source_file, monkeypatch,
):
    client, _tmp, data = classic
    video, meta = source_file
    monkeypatch.setattr(routes_classic, "classic_fill_status", lambda: _ready_fill())
    _install_dummy_model(data)
    job = _fake_job("source-preview", video, meta)
    clip = _source_clip(job)

    estimate = client.post(
        f"/api/classic/jobs/{job['id']}/fill/estimate",
        json={"clips": [clip], "clean": [_fill_box()], "aspect": "source"},
    )
    assert estimate.status_code == 200, estimate.text
    body = estimate.json()
    assert body["scope"] == "source"
    assert body["method"] == "lama"
    assert body["frames"] > 0

    implicit = client.post(
        f"/api/classic/jobs/{job['id']}/fill/estimate",
        json={"clips": [clip], "clean": [_fill_box()]},
    )
    assert implicit.status_code == 200, implicit.text
    assert implicit.json()["scope"] == "source"

    calls = {"fill": [], "released": 0}

    def fake_read(path, width, height, at):
        return np.full((height, width, 3), 40, dtype=np.uint8)

    def fake_fill(frame_rgb, rects, **options):
        calls["fill"].append({"rects": rects, **options})
        return np.full_like(frame_rgb, 200)

    def fake_jpeg(png, output, chain):
        output.write_bytes(png.read_bytes())

    monkeypatch.setattr(routes_classic, "_read_source_frame", fake_read)
    monkeypatch.setattr(textfill, "fill_frame", fake_fill)
    monkeypatch.setattr(routes_classic, "_render_preview_jpeg", fake_jpeg)
    monkeypatch.setattr(
        textfill, "release_fillers",
        lambda: calls.__setitem__("released", calls["released"] + 1),
    )

    preview = client.post(
        f"/api/classic/jobs/{job['id']}/fill/preview",
        json={"clips": [clip], "clean": [_fill_box()], "t": 0.4, "aspect": "source"},
    )
    assert preview.status_code == 200, preview.text
    payload = preview.json()
    assert payload["scope"] == "source"
    assert (payload["width"], payload["height"]) == (meta["width"], meta["height"])
    assert payload["before"].startswith("data:image/jpeg;base64,")
    assert payload["after"].startswith("data:image/jpeg;base64,")
    assert calls["fill"] and calls["fill"][0]["rects"]
    assert calls["released"] >= 1

    sample = client.post(
        f"/api/classic/jobs/{job['id']}/fill/sample",
        json={"clips": [clip], "clean": [_fill_box()], "t": 0.4, "aspect": "source"},
    )
    assert sample.status_code == 200, sample.text
    assert sample.json()["cached"] is True

    implicit_preview = client.post(
        f"/api/classic/jobs/{job['id']}/fill/preview",
        json={"clips": [clip], "clean": [_fill_box()], "t": 0.4},
    )
    assert implicit_preview.status_code == 200, implicit_preview.text
    assert implicit_preview.json()["scope"] == "source"
    assert implicit_preview.json()["cached"] is True


def test_source_frame_route_returns_original_dimensions(
    classic, source_file, monkeypatch,
):
    client, _tmp, _data = classic
    video, meta = source_file
    job = _fake_job("source-frame", video, meta)
    monkeypatch.setattr(
        routes_classic, "_read_source_frame",
        lambda path, width, height, at: np.full((height, width, 3), 60, dtype=np.uint8),
    )
    monkeypatch.setattr(
        routes_classic, "_render_preview_jpeg",
        lambda png, output, chain: output.write_bytes(png.read_bytes()),
    )
    response = client.post(
        f"/api/classic/jobs/{job['id']}/frame/source",
        json={"clips": [_source_clip(job)], "clean": [_blur_box()], "t": 0.4},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("image/jpeg")
    assert response.headers["x-vibecut-width"] == str(meta["width"])
    assert response.headers["x-vibecut-height"] == str(meta["height"])


def test_source_frame_uses_only_blur_active_at_the_still(
    classic, source_file, monkeypatch,
):
    client, _tmp, _data = classic
    video, meta = source_file
    job = _fake_job("source-frame-range", video, meta)
    chains: list[str] = []
    monkeypatch.setattr(
        routes_classic, "_read_source_frame",
        lambda path, width, height, at: np.full((height, width, 3), 60, dtype=np.uint8),
    )

    def capture(png, output, chain):
        chains.append(chain)
        output.write_bytes(png.read_bytes())

    monkeypatch.setattr(routes_classic, "_render_preview_jpeg", capture)
    box = _blur_box(ranges=[{"start": 0.8, "end": 1.2}])
    before = client.post(
        f"/api/classic/jobs/{job['id']}/frame/source",
        json={"clips": [_source_clip(job)], "clean": [box], "t": 0.4},
    )
    after = client.post(
        f"/api/classic/jobs/{job['id']}/frame/source",
        json={"clips": [_source_clip(job)], "clean": [box], "t": 1.0},
    )
    assert before.status_code == 200 and after.status_code == 200
    assert "boxblur" not in chains[0]
    assert "boxblur" in chains[1]
    assert "enable" not in chains[1]


def test_source_preview_uses_only_blur_active_at_the_still(
    classic, source_file, monkeypatch,
):
    client, _tmp, data = classic
    video, meta = source_file
    monkeypatch.setattr(routes_classic, "classic_fill_status", lambda: _ready_fill())
    _install_dummy_model(data)
    job = _fake_job("source-preview-range", video, meta)
    clip = _source_clip(job)
    chains: list[str] = []

    monkeypatch.setattr(
        routes_classic, "_read_source_frame",
        lambda path, width, height, at: np.full((height, width, 3), 40, dtype=np.uint8),
    )
    monkeypatch.setattr(
        textfill, "fill_frame",
        lambda frame_rgb, rects, **options: np.full_like(frame_rgb, 200),
    )

    def capture(png, output, chain):
        chains.append(chain)
        output.write_bytes(png.read_bytes())

    monkeypatch.setattr(routes_classic, "_render_preview_jpeg", capture)
    monkeypatch.setattr(textfill, "release_fillers", lambda: None)
    box = _blur_box(
        id="cl02", ranges=[{"start": 0.8, "end": 1.2}],
    )
    body = {"clips": [clip], "clean": [_fill_box(), box], "aspect": "source"}
    before = client.post(
        f"/api/classic/jobs/{job['id']}/fill/preview", json={**body, "t": 0.4},
    )
    after = client.post(
        f"/api/classic/jobs/{job['id']}/fill/preview", json={**body, "t": 1.0},
    )
    assert before.status_code == 200 and after.status_code == 200
    assert "boxblur" not in chains[0]
    assert "boxblur" in chains[-1]
    assert "enable" not in chains[-1]


def test_source_estimate_is_summed_per_bounded_span(
    classic, source_file, monkeypatch,
):
    client, _tmp, data = classic
    video, meta = source_file
    monkeypatch.setattr(routes_classic, "classic_fill_status", lambda: _ready_fill())
    _install_dummy_model(data)
    monkeypatch.setattr(clean_source, "CHUNK_SECONDS", 0.5)
    job = _fake_job("source-estimate-chunks", video, meta)
    calls = []

    def fake_estimate(**options):
        calls.append(
            (options["start"], options["duration"], len(options["layers"]))
        )
        return {
            "method": "lama", "frames": 2, "units": 2,
            "cached": options["start"] == 0.0,
        }

    monkeypatch.setattr(textfill, "estimate_span", fake_estimate)
    response = client.post(
        f"/api/classic/jobs/{job['id']}/fill/estimate",
        json={
            "clips": [_source_clip(job)], "clean": [_fill_box()],
            "aspect": "source",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(calls) > 1
    assert [call[0] for call in calls] == sorted(call[0] for call in calls)
    assert all(call[2] == 1 for call in calls)
    assert body["frames"] == 2 * len(calls)
    assert body["units"] == 2 * len(calls)
    assert body["cached"] is False


def test_source_fill_estimate_uses_frame_rounded_span(
    classic, source_file, monkeypatch,
):
    client, _tmp, data = classic
    video, _meta = source_file
    monkeypatch.setattr(routes_classic, "classic_fill_status", lambda: _ready_fill())
    _install_dummy_model(data)
    job = _fake_job("source-estimate-span", video, SOURCE_META)
    seen = {}

    def fake_estimate(**options):
        seen.update(options)
        return {"method": "lama", "frames": 1, "units": 1, "cached": False}

    monkeypatch.setattr(textfill, "estimate_span", fake_estimate)
    clip = {"scene": 0, "start": 0.0, "end": 0.97, "dur": 0.97, "role": "beat"}
    response = client.post(
        f"/api/classic/jobs/{job['id']}/fill/estimate",
        json={"clips": [clip], "clean": [_fill_box()], "aspect": "9:16"},
    )
    assert response.status_code == 200, response.text
    assert seen["duration"] == pytest.approx(29 / render.OUT_FPS)
    assert seen["duration"] != pytest.approx(0.97)


def test_source_render_holds_the_fill_lock(
    classic, source_file, tmp_path, monkeypatch,
):
    client, _tmp, data = classic
    video, meta = source_file
    monkeypatch.setattr(routes_classic, "classic_fill_status", lambda: _ready_fill())
    _install_dummy_model(data)
    job = _fake_job("source-lock", video, meta)
    filled = tmp_path / "locked-fill.mp4"
    seen = {}

    def fake_prepare(**options):
        seen["locked"] = render.FILL_LOCK.locked()
        filled.write_bytes(b"filled" + b"x" * 2048)
        return {
            "path": str(filled), "key": "fake", "cached": False, "method": "lama",
        }

    monkeypatch.setattr(textfill, "prepare_span", fake_prepare)
    monkeypatch.setattr(
        clean_source, "_mux_audio",
        lambda video_path, source, output, duration, cancel: (
            output.write_bytes(Path(video_path).read_bytes()), "copy"
        )[1],
    )
    started = _render_source(client, job, [_fill_box()])
    assert started.status_code in {200, 202}, started.text
    record = _wait_ready(client, job["id"])
    assert record["status"] == "ready", record
    assert seen["locked"] is True
    assert render.FILL_LOCK.locked() is False


def test_two_starts_reserve_one_job_key(classic, source_file, monkeypatch):
    _client, _tmp, _data = classic
    video, meta = source_file
    _fake_job("source-reserve", video, meta)
    monkeypatch.setattr(clean_source, "POOL", ParkedPool())
    layer = {
        "id": "cl01", "kind": "blur",
        "box": {"x": 0.2, "y": 0.2, "w": 0.3, "h": 0.15},
        "ranges": [], "radius": 8,
    }
    first = clean_source.start("source-reserve", [layer])
    assert first["status"] in {"queued", "running"}
    with pytest.raises(HTTPException) as caught:
        clean_source.start("source-reserve", [{**layer, "radius": 16}])
    assert caught.value.status_code == 409


def test_cancel_does_not_overwrite_a_ready_result(
    classic, source_file, monkeypatch,
):
    _client, _tmp, data = classic
    video, meta = source_file
    job = _fake_job("source-ready-race", video, meta)
    output = data / "jobs" / job["id"] / "clean" / "source" / "done.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"ready" + b"x" * 2048)
    job["source_clean"] = {
        "status": "running", "progress": 0.4, "message": "Encoding",
        "key": "done", "task_id": "gone", "path": str(output),
    }
    app.save_job(job)

    def finish(job_dir, key=""):
        current = app.load_job(job["id"])
        current["source_clean"].update(
            status="ready", progress=1.0, message="Clean video ready",
        )
        app.save_job(current)

    monkeypatch.setattr(clean_source, "_clean_parts", finish)
    reply = clean_source.cancel(job["id"])
    assert reply["cancelled"] is False
    assert reply["status"] == "ready"
    assert app.load_job(job["id"])["source_clean"]["message"] == "Clean video ready"


def test_source_preview_refuses_while_a_fill_holds_the_lock(
    classic, source_file, monkeypatch,
):
    client, _tmp, data = classic
    video, meta = source_file
    monkeypatch.setattr(routes_classic, "classic_fill_status", lambda: _ready_fill())
    _install_dummy_model(data)
    job = _fake_job("source-preview-busy", video, meta)
    assert render.FILL_LOCK.acquire(blocking=False)
    try:
        response = client.post(
            f"/api/classic/jobs/{job['id']}/fill/preview",
            json={
                "clips": [_source_clip(job)], "clean": [_fill_box()],
                "t": 0.4, "aspect": "source",
            },
        )
    finally:
        render.FILL_LOCK.release()
    assert response.status_code == 409
    assert response.json()["error"] == "fill_running"


def test_source_preview_releases_lock_when_tmp_mkdir_fails(
    classic, source_file, monkeypatch,
):
    _client, _tmp, data = classic
    video, meta = source_file
    monkeypatch.setattr(routes_classic, "classic_fill_status", lambda: _ready_fill())
    _install_dummy_model(data)
    job = _fake_job("source-preview-mkdir", video, meta)
    layers = routes_classic.normalize_classic_layers(
        [], [], meta["duration"], [_fill_box()],
    )
    original = Path.mkdir

    def fail(self, *args, **kwargs):
        if self.name.startswith("tmp_fill_preview_"):
            raise OSError("disk full")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail)
    with pytest.raises(OSError):
        routes_classic._classic_source_fill_preview(
            job["id"], job, layers, 0.4, _ready_fill(),
        )
    assert render.FILL_LOCK.locked() is False


def test_fill_spans_are_chunked_for_long_or_many_layers():
    one = [{"ranges": []}]
    spans = clean_source._chunk_spans(120.0, 30.0, one)
    assert len(spans) > 1
    assert max(high - low for low, high in spans) <= clean_source.CHUNK_SECONDS

    many = [{"ranges": []} for _ in range(1000)]
    spans = clean_source._chunk_spans(120.0, 30.0, many)
    for low, high in spans:
        assert (high - low) * 30.0 * len(many) <= clean_source.MAX_CHUNK_RECTS + 1.0


def test_encode_and_mux_command_shape(monkeypatch, tmp_path):
    commands = []

    def fake_run(command, **options):
        commands.append(command)
        return None

    monkeypatch.setattr(render, "_run", fake_run)
    clean_source._encode(
        tmp_path / "in.mp4", [], 1.0, 320, 180, 30.0,
        tmp_path / "out.mp4", threading.Event(),
    )
    encode = commands[0]
    joined = " ".join(str(item) for item in encode)
    assert "scale=320:180:flags=lanczos" in joined
    assert "fps=30.000000" in joined
    assert "setsar=1" in joined
    assert "-map 0:v:0" in joined

    mode = clean_source._mux_audio(
        tmp_path / "video.mp4", tmp_path / "source.mp4",
        tmp_path / "final.mp4", 1.0, threading.Event(),
    )
    assert mode == "copy"
    mux = [str(item) for item in commands[1]]
    assert "-map" in mux and "0:v:0" in mux
    assert "-map" in mux and "1:a:0" in mux
    assert "-c:v" in mux and "copy" in mux
    assert "-c:a" in mux and "copy" in mux


def test_fill_master_chunks_unfilled_span_and_forces_reencode(
    classic, source_file, monkeypatch,
):
    _client, _tmp, data = classic
    video, meta = source_file
    monkeypatch.setattr(clean_source, "CHUNK_SECONDS", 2.0)
    long_meta = dict(meta, duration=4.0)
    job = _fake_job("source-two-span", video, long_meta)
    layers = [{
        "id": "cl01", "kind": "fill", "method": "lama",
        "box": {"x": 0.1, "y": 0.7, "w": 0.8, "h": 0.16},
        "ranges": [{"start": 0.0, "end": 2.0}],
    }]
    prepared = []
    encoded = []
    concatenated = {}

    def fake_prepare(**options):
        path = Path(options["cache_dir"]) / f"fill-{options['start']:.1f}.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fill" + b"x" * 2048)
        prepared.append((options["start"], options["duration"]))
        return {
            "path": str(path), "key": path.name, "cached": False, "method": "lama",
        }

    def fake_encode(
        input_path, filters, duration, width, height, fps, output, cancel,
        *, start=0.0,
    ):
        encoded.append({
            "input": Path(input_path).name,
            "start": start,
            "duration": duration,
            "filters": list(filters),
        })
        output.write_bytes(b"encoded" + b"x" * 2048)

    def fake_concat(tmp, target, segments, quality, cancel):
        concatenated["segments"] = [
            (Path(item).name, Path(item).is_file(), Path(item).stat().st_size)
            for item in segments
        ]
        target.write_bytes(b"master" + b"x" * 2048)

    monkeypatch.setattr(textfill, "prepare_span", fake_prepare)
    monkeypatch.setattr(clean_source, "_encode", fake_encode)
    monkeypatch.setattr(render, "_concat_video", fake_concat)
    monkeypatch.setattr(
        clean_source, "_mux_audio",
        lambda video_path, source, output, duration, cancel: (
            output.write_bytes(Path(video_path).read_bytes()), "copy"
        )[1],
    )

    record = clean_source.run(job["id"], layers, "chunk-test", "lama")
    assert record["status"] == "ready", record
    assert prepared == [(0.0, 2.0)]
    assert [item["start"] for item in encoded] == [2.0, 0.0]
    assert encoded[0]["input"] == video.name
    assert encoded[0]["filters"] == []
    assert encoded[1]["input"] == "fill_master.mp4"
    assert concatenated["segments"] == [
        ("chunk_0000.mp4", True, pytest.approx(2052)),
        ("chunk_0001.mp4", True, pytest.approx(2055)),
    ]
    assert Path(record["path"]).is_file()
    assert record["audio_mode"] == "copy"
    assert render.FILL_LOCK.locked() is False


def test_source_posts_reject_cross_site_origin(
    classic, source_file, monkeypatch,
):
    client, _tmp, _data = classic
    video, meta = source_file
    monkeypatch.setattr(app, "analysis_pool", CapturePool())
    job = _fake_job("source-origin", video, meta)
    headers = {"sec-fetch-site": "cross-site"}
    render = client.post(
        f"/api/classic/jobs/{job['id']}/clean/source/render",
        json={"clips": [_source_clip(job)], "clean": [_blur_box()]},
        headers=headers,
    )
    analyze = client.post(
        f"/api/jobs/{job['id']}/analyze", headers=headers,
    )
    assert render.status_code == 403
    assert analyze.status_code == 403


def test_cut_fill_preview_uses_only_blur_active_at_the_still(
    classic, source_file, monkeypatch,
):
    client, _tmp, data = classic
    video, meta = source_file
    monkeypatch.setattr(routes_classic, "classic_fill_status", lambda: _ready_fill())
    _install_dummy_model(data)
    job = _fake_job("cut-preview-range", video, meta)
    chains: list[str] = []

    monkeypatch.setattr(
        routes_classic, "_read_source_frame",
        lambda path, width, height, at: np.full((height, width, 3), 40, dtype=np.uint8),
    )
    monkeypatch.setattr(
        textfill, "fill_frame",
        lambda frame_rgb, rects, **options: np.full_like(frame_rgb, 200),
    )

    def capture(png, output, chain):
        chains.append(chain)
        output.write_bytes(png.read_bytes())

    def fake_burn(frame, layers, output, out_w, out_h, at, cache):
        output.write_bytes(Path(frame).read_bytes())

    monkeypatch.setattr(routes_classic, "_render_preview_jpeg", capture)
    monkeypatch.setattr(render, "_burn_frame", fake_burn)
    monkeypatch.setattr(textfill, "release_fillers", lambda: None)
    box = _blur_box(
        id="cl02", ranges=[{"start": 0.8, "end": 1.2}],
    )
    clip = {"scene": 0, "start": 0.0, "end": 1.2, "dur": 1.2, "role": "beat"}
    body = {"clips": [clip], "clean": [_fill_box(), box], "aspect": "9:16"}
    before = client.post(
        f"/api/classic/jobs/{job['id']}/fill/preview", json={**body, "t": 0.4},
    )
    after = client.post(
        f"/api/classic/jobs/{job['id']}/fill/preview", json={**body, "t": 1.0},
    )
    assert before.status_code == 200, before.text
    assert after.status_code == 200, after.text
    assert "boxblur" not in chains[0]
    assert "boxblur" in chains[-1]
    assert "enable" not in chains[-1]


# ------------------------------------------------------------------ real clip


def test_source_render_real_clip_keeps_size_audio_and_caches(
    classic, tmp_path, monkeypatch,
):
    """End-to-end on the founder's real clip; skips when data/media is absent."""
    client, _tmp, _data = classic
    video = real_media.real_clip("wide-video", tmp_path / "wide.mp4", 1.2)
    meta = pipeline.probe(video)
    job = _fake_job("source-real", video, meta)
    started = _render_source(client, job, [_blur_box()])
    assert started.status_code in {200, 202}, started.text
    record = _wait_ready(client, job["id"])
    assert record["status"] == "ready", record
    output = Path(record["path"])
    assert output.is_file()
    assert not list(output.parent.glob(".*.part.mp4"))
    out_meta = pipeline.probe(output)
    assert (out_meta["width"], out_meta["height"]) == (meta["width"], meta["height"])
    assert out_meta["fps"] == pytest.approx(meta["fps"], abs=0.2)
    assert out_meta["has_audio"] is True

    again = _render_source(client, job, [_blur_box()])
    assert again.status_code == 200, again.text
    assert again.json()["cached"] is True


def test_a_clean_video_render_keeps_the_mac_awake(monkeypatch):
    seen = []

    @contextmanager
    def awake():
        seen.append("awake")
        yield
        seen.append("may sleep")

    monkeypatch.setattr(clean_source.render, "keep_awake", awake)
    monkeypatch.setattr(clean_source, "run", lambda *args, **kwargs: seen.append("run") or {"ok": True})
    assert clean_source._run_awake("job") == {"ok": True}
    assert seen == ["awake", "run", "may sleep"]

