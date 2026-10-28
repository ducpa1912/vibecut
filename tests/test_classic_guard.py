"""Classic beta guard: the core Classic flow through its own HTTP routes.

Studio and Voice Room work ships through main into the classic lane
(docs/branching.md). These tests fail that ship if it breaks Classic:
plan → render → job state → history → export, and the Classic page itself.
Rendering is faked; everything else is the real route code.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app
import render

ROOT = Path(__file__).resolve().parents[1]


def _scene(index: int, start: float, speech: str) -> dict:
    return {
        "id": index, "start": start, "end": start + 4.0, "dur": 4.0, "mid": start + 2.0,
        "hook": 60.0, "score": 60.0, "deep": True, "visual_score": 60.0,
        "motion_score": 60.0, "audio_score": 60.0, "text_score": 0.0, "ocr": "",
        "speech": speech, "tags": [], "crop": {"cx": 0.5, "cy": 0.5}, "crop_mode": "center",
    }


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
    source = tmp_path / "source.mp4"
    source.write_bytes(b"not a real video")
    speech = ["Here is the hook.", "Then the second beat.", "A third beat.", "The payoff lands.", "Extra."]
    job = {
        "id": "classic1", "created": 1.0, "updated": 1.0, "status": "ready",
        "progress": 1.0, "message": "Ready", "error": None,
        "source": {
            "path": str(source), "name": "source.mp4", "duration": 20.0,
            "width": 1920, "height": 1080, "fps": 30.0, "size": 16,
            "has_audio": True, "fingerprint": "classic-guard",
        },
        "options": {},
        "analysis": {
            "scene_count": 5, "hook_scene": 0, "deep_count": 5,
            "deep_scene_ids": [0, 1, 2, 3, 4],
            "engine": {"transcript_language": "en"},
            "scenes": [_scene(index, index * 4.0, text) for index, text in enumerate(speech)],
        },
        "renders": {},
    }
    directory = jobs / job["id"]
    directory.mkdir()
    (directory / "job.json").write_text(json.dumps(job), encoding="utf-8")

    def run_now(fn, *args, **kwargs):
        for key in ("task_kind", "task_key", "retry_payload"):
            kwargs.pop(key, None)
        fn(*args, **kwargs)

    def fake_render_reel(source, meta, job_dir, plan, title, progress, **kwargs):
        renders = job_dir / "renders"
        renders.mkdir(parents=True, exist_ok=True)
        (renders / "reel_15.mp4").write_bytes(b"fake-mp4")
        (renders / "reel_15.jpg").write_bytes(b"fake-jpg")
        progress(1.0, "Reel ready")
        return {
            "path": "reel_15.mp4", "poster": "reel_15.jpg", "duration": 12.0,
            "width": 1080, "height": 1920, "size": 8, "has_audio": True,
            "clip_count": len(plan.get("clips") or []), "quality": "final",
            "aspect": "9:16", "encoder": "libx264", "captions": False,
            "caption_count": 0, "cached": 0, "used_assets": [],
        }

    monkeypatch.setattr(app.render_pool, "submit", run_now)
    monkeypatch.setattr(render, "render_reel", fake_render_reel)
    return TestClient(app.app)


def test_classic_plan_render_history_and_export(classic):
    planned = classic.post("/api/jobs/classic1/plan", json={"target": 15})
    assert planned.status_code == 200, planned.text
    plan = planned.json()["plan"]
    assert plan["clips"], "Classic must plan at least one clip"

    rendered = classic.post("/api/jobs/classic1/render", json={"target": 15, "quality": "final"})
    assert rendered.status_code == 200, rendered.text

    job = classic.get("/api/jobs/classic1").json()
    ready = [record for record in job["renders"].values() if record.get("status") == "ready"]
    assert ready, f"render did not finish: {job['renders']}"

    history = classic.get("/api/jobs/classic1/history?limit=50")
    assert history.status_code == 200, history.text
    assert history.json()["count"] >= 1, "a finished Classic render must land in History"

    for kind in ("srt", "edl"):
        exported = classic.get(f"/api/jobs/classic1/export/{kind}?target=15")
        assert exported.status_code == 200, (kind, exported.text)
        assert exported.content


def test_classic_page_opens_with_its_scripts_and_controls(monkeypatch):
    monkeypatch.setenv("VIBECUT_EDITION", "classic")
    monkeypatch.delenv("VIBECUT_FEATURES", raising=False)
    html = TestClient(app.app).get("/").text
    for needed in ("/static/app.js", "/static/creator.js", 'id="creator-open"', 'id="setup-open"'):
        assert needed in html, needed
    assert '"views":["classic"]' in html


def test_every_static_file_the_classic_page_names_exists():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    for path in set(re.findall(r'"/static/([^"?]+)', html)):
        assert (ROOT / "static" / path).is_file(), path
