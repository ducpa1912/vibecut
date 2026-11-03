"""Classic Texts & Effects reach the renderer as a real Edit.

The render is faked; the request path, the Edit builder and the queue handoff
are real. The fake records the Edit that ``render_reel`` receives.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import app
import edits
import render


def _scene(index: int, start: float, speech: str) -> dict:
    return {
        "id": index, "start": start, "end": start + 4.0, "dur": 4.0,
        "mid": start + 2.0, "hook": 60.0, "score": 60.0, "deep": True,
        "visual_score": 60.0, "motion_score": 60.0, "audio_score": 60.0,
        "text_score": 0.0, "ocr": "", "speech": speech, "tags": [],
        "crop": {"cx": 0.5, "cy": 0.5}, "crop_mode": "center",
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
    speech = [
        "Here is the hook.",
        "Then the second beat.",
        "A third beat.",
        "The payoff lands.",
        "Extra.",
    ]
    job = {
        "id": "classic1", "created": 1.0, "updated": 1.0, "status": "ready",
        "progress": 1.0, "message": "Ready", "error": None,
        "source": {
            "path": str(source), "name": "source.mp4", "duration": 20.0,
            "width": 1920, "height": 1080, "fps": 30.0, "size": 16,
            "has_audio": True, "fingerprint": "classic-text-render",
        },
        "options": {},
        "analysis": {
            "scene_count": 5, "hook_scene": 0, "deep_count": 5,
            "deep_scene_ids": [0, 1, 2, 3, 4],
            "engine": {"transcript_language": "en"},
            "scenes": [
                _scene(index, index * 4.0, text)
                for index, text in enumerate(speech)
            ],
        },
        "renders": {},
    }
    directory = jobs / job["id"]
    directory.mkdir()
    (directory / "job.json").write_text(json.dumps(job), encoding="utf-8")

    captured: list[dict] = []

    def run_now(fn, *args, **kwargs):
        for key in ("task_kind", "task_key", "retry_payload"):
            kwargs.pop(key, None)
        fn(*args, **kwargs)

    def fake_render_reel(source, meta, job_dir, plan, title, progress, **kwargs):
        captured.append({"plan": plan, "edit": kwargs.get("edit")})
        renders = job_dir / "renders"
        renders.mkdir(parents=True, exist_ok=True)
        (renders / "reel_30.mp4").write_bytes(b"fake-mp4")
        (renders / "reel_30.jpg").write_bytes(b"fake-jpg")
        progress(1.0, "Reel ready")
        return {
            "path": "reel_30.mp4", "poster": "reel_30.jpg", "duration": 12.0,
            "width": 1080, "height": 1920, "size": 8, "has_audio": True,
            "clip_count": len(plan.get("clips") or []), "quality": "final",
            "aspect": "9:16", "encoder": "libx264", "captions": False,
            "caption_count": 0, "cached": 0, "used_assets": [],
        }

    monkeypatch.setattr(app.render_pool, "submit", run_now)
    monkeypatch.setattr(render, "render_reel", fake_render_reel)
    return TestClient(app.app), captured


def _clips(client: TestClient, target: int = 30) -> list[dict]:
    planned = client.post("/api/jobs/classic1/plan", json={"target": target})
    assert planned.status_code == 200, planned.text
    return planned.json()["plan"]["clips"]


def _edit_payload(clips: list[dict]) -> dict:
    total = sum(
        float(clip.get("end", clip["start"] + clip.get("dur", 0.0)))
        - float(clip["start"])
        for clip in clips
    )
    return {
        "overlays": [
            {
                "text": "The one line",
                "anchor": "top",
                "start": 0.0,
                "end": min(2.5, total),
            },
        ],
        "effects": [
            {"kind": "punch_in", "duration": min(1.2, total)},
            {"kind": "circle", "duration": min(1.5, total)},
        ],
    }


def test_render_request_carries_the_edit(classic):
    client, captured = classic
    clips = _clips(client)
    payload = _edit_payload(clips)
    response = client.post("/api/jobs/classic1/render", json={
        "target": 30,
        "quality": "final",
        "aspect": "9:16",
        "captions": False,
        "clips": clips,
        "edit": payload,
    })
    assert response.status_code == 200, response.text
    assert captured, "render_reel was not called"
    edit = captured[-1]["edit"]
    assert edit is not None
    assert edit["aspect"] == "9:16"
    assert [layer["kind"] for layer in edit["graphics"]] == ["hook", "circle"]
    assert edit["graphics"][0]["text"] == "The one line"
    assert edit["graphics"][0]["anchor"] == "top-center"
    assert edit["motion"][0]["kind"] == "punch_in"
    assert edit["captions"]["enabled"] is False
    render_record = response.json()["render"]
    assert render_record["edit_hash"] == edit["hash"]
    assert render_record["edit_id"] == edit["id"]

    stored = json.loads((app.JOBS / "classic1" / "job.json").read_text("utf-8"))
    saved = stored["classic_text"]["cuts"][edits.clip_snapshot_hash(clips)]
    assert saved["overlays"][0]["text"] == "The one line"
    assert saved["motion"][0]["kind"] == "punch_in"


def test_render_without_layers_uses_the_legacy_path(classic):
    client, captured = classic
    clips = _clips(client)
    response = client.post("/api/jobs/classic1/render", json={
        "target": 30,
        "quality": "final",
        "aspect": "9:16",
        "captions": False,
        "clips": clips,
    })
    assert response.status_code == 200, response.text
    assert captured[-1]["edit"] is None


def test_captions_and_layers_share_one_render(classic):
    client, captured = classic
    clips = _clips(client)
    payload = _edit_payload(clips)
    response = client.post("/api/jobs/classic1/render", json={
        "target": 30,
        "quality": "final",
        "aspect": "9:16",
        "captions": True,
        "clips": clips,
        "edit": payload,
    })
    assert response.status_code == 200, response.text
    edit = captured[-1]["edit"]
    assert edit["captions"]["enabled"] is True
    assert edit["captions"]["track_id"].startswith("cap_")
    assert edit["graphics"][0]["text"] == "The one line"


def test_sixteen_by_nine_refuses_layers_with_a_reason(classic):
    client, captured = classic
    clips = _clips(client)
    response = client.post("/api/jobs/classic1/render", json={
        "target": 30,
        "quality": "final",
        "aspect": "16:9",
        "captions": False,
        "clips": clips,
        "edit": _edit_payload(clips),
    })
    assert response.status_code == 422, response.text
    assert "9:16 and 4:5" in response.json()["detail"]
    assert not captured


def test_an_empty_layer_payload_renders_on_any_shape(classic):
    client, captured = classic
    clips = _clips(client)
    response = client.post("/api/jobs/classic1/render", json={
        "target": 30,
        "quality": "final",
        "aspect": "16:9",
        "captions": False,
        "clips": clips,
        "edit": {"overlays": [], "effects": []},
    })
    assert response.status_code == 200, response.text
    assert captured and not captured[-1].get("edit")


def test_the_card_offers_overlays_effects_and_a_disabled_reason():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    page = (root / "static" / "classic" / "index.html").read_text("utf-8")
    for control in (
        'id="captions"',
        'id="text-overlay-text"',
        'id="text-overlay-anchor"',
        'id="text-overlay-start"',
        'id="text-overlay-end"',
        'id="text-overlay-add"',
        'id="effect-kind"',
        'id="effect-duration"',
        'id="effect-add"',
        'id="text-overlay-list"',
        'id="effect-list"',
        'id="text-shape-note"',
    ):
        assert control in page, control
    script = (root / "static" / "classic" / "app.js").read_text("utf-8")
    assert "Text overlays and effects render on 9:16 and 4:5." in script
    assert "edit: classicEditPayload()" in script
    assert "/api/classic/jobs/${state.job.id}/text" in script
