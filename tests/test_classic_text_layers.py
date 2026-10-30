"""Classic Texts & Effects layers: Studio shape, API validation and storage.

The card stores Studio text layers and Studio motion/fx entries per cut. These
tests use the real routes and the real ``edits`` validators; no render runs.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import app
import compose_render
import edits
import routes_classic


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
            "has_audio": True, "fingerprint": "classic-text-layers",
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
    return TestClient(app.app)


def _plan(client: TestClient, target: int = 30) -> dict:
    planned = client.post("/api/jobs/classic1/plan", json={"target": target})
    assert planned.status_code == 200, planned.text
    return planned.json()["plan"]


def test_layer_builder_keeps_the_studio_shape():
    layers = routes_classic.normalize_classic_layers(
        [{"text": "  First   hook  ", "anchor": "top", "start": 0.5, "end": 2.5}],
        [
            {"kind": "shake", "duration": 1.0},
            {"kind": "circle", "duration": 1.5},
        ],
        10.0,
    )
    overlay = layers["overlays"][0]
    assert overlay["type"] == "text"
    assert overlay["kind"] == "hook"
    assert overlay["anchor"] == "top-center"
    assert overlay["text"] == "First hook"
    assert overlay["box"] == {"w": 0.76, "h": 0.16}
    assert overlay["style"]["font"] == "sans"
    assert overlay["safe_zone"] is True
    assert set(overlay) <= set(edits._GRAPHIC_TEXT_KEYS)
    assert layers["motion"][0]["kind"] == "shake"
    assert layers["motion"][0]["amount"] == 0.01
    assert layers["graphics"][0]["kind"] == "circle"
    assert layers["graphics"][0]["type"] == "fx"


def test_classic_edit_compiles_to_text_and_effect_layers():
    clips = routes_classic._classic_clips([
        {"scene": 0, "role": "hook", "start": 0.0, "end": 4.0, "dur": 4.0},
        {"scene": 1, "role": "payoff", "start": 4.0, "end": 8.0, "dur": 4.0},
    ])
    layers = routes_classic.normalize_classic_layers(
        [{"text": "First hook", "anchor": "top", "start": 0.2, "end": 3.0}],
        [
            {"kind": "punch_in", "duration": 1.2},
            {"kind": "circle", "duration": 1.5},
        ],
        routes_classic._classic_total(clips),
    )
    edit = routes_classic._build_classic_edit(clips, "9:16", layers)
    compiled = compose_render.compile_edit(
        edit,
        clips=clips,
        source={"width": 1920, "height": 1080},
        scenes=[],
        motion_engine="perspective",
    )
    assert compiled["canvas"] == {"w": 1080, "h": 1920}
    overlays = {(layer["type"], layer["kind"]): layer for layer in compiled["overlays"]}
    assert ("text", "hook") in overlays
    assert overlays[("text", "hook")]["rect"] == {
        "x": 0.12, "y": 0.05, "w": 0.76, "h": 0.16,
    }
    assert ("fx", "circle") in overlays
    assert compiled["segments"][0]["motion_ids"] == ["mo01"]
    assert "perspective" in compiled["segments"][0]["post_filter"]


def test_save_and_lookup_persist_layers_in_job_state(classic):
    clips = _plan(classic)["clips"]
    payload = {
        "clips": clips,
        "overlays": [
            {"text": "First hook", "anchor": "top", "start": 0.5, "end": 3.0},
            {"text": "Payoff line", "anchor": "bottom", "start": 5.0, "end": 8.0},
        ],
        "effects": [
            {"kind": "punch_in", "duration": 1.2},
            {"kind": "shake", "duration": 2.0},
            {"kind": "circle", "duration": 1.5},
        ],
    }
    saved = classic.put("/api/classic/jobs/classic1/text", json=payload)
    assert saved.status_code == 200, saved.text
    cut = saved.json()["cut"]
    assert [layer["kind"] for layer in cut["overlays"]] == ["hook", "lower_third"]
    assert [layer["anchor"] for layer in cut["overlays"]] == [
        "top-center", "bottom-center",
    ]
    assert {effect["kind"] for effect in cut["effects"]} == {
        "punch_in", "shake", "circle",
    }
    assert cut["clips_hash"] == edits.clip_snapshot_hash(clips)

    lookup = classic.post(
        "/api/classic/jobs/classic1/text", json={"clips": clips},
    )
    assert lookup.status_code == 200, lookup.text
    assert lookup.json()["cut"]["overlays"] == cut["overlays"]
    assert lookup.json()["cut"]["effects"] == cut["effects"]

    stored = json.loads((app.JOBS / "classic1" / "job.json").read_text("utf-8"))
    row = stored["classic_text"]["cuts"][cut["clips_hash"]]
    assert row["overlays"][0]["text"] == "First hook"
    assert row["motion"][0]["kind"] == "punch_in"


def test_lookup_without_a_saved_cut_returns_null(classic):
    clips = _plan(classic)["clips"]
    lookup = classic.post(
        "/api/classic/jobs/classic1/text", json={"clips": clips},
    )
    assert lookup.status_code == 200, lookup.text
    assert lookup.json()["cut"] is None


def test_save_rejects_bad_layers_with_plain_reasons(classic):
    clips = _plan(classic)["clips"]

    def save(**overrides):
        body = {"clips": clips, "overlays": [], "effects": [], **overrides}
        return classic.put("/api/classic/jobs/classic1/text", json=body)

    empty = save(overlays=[{"text": "   ", "anchor": "top", "start": 0, "end": 2}])
    assert empty.status_code == 422
    assert "needs words" in empty.json()["detail"]

    bad_anchor = save(
        overlays=[{"text": "Hi", "anchor": "left", "start": 0, "end": 2}],
    )
    assert bad_anchor.status_code == 422
    assert "top, center or bottom" in bad_anchor.json()["detail"]

    after_cut = save(
        overlays=[{"text": "Hi", "anchor": "top", "start": 0, "end": 999}],
    )
    assert after_cut.status_code == 422
    assert "after the cut ends" in after_cut.json()["detail"]

    bad_effect = save(effects=[{"kind": "explode", "duration": 1}])
    assert bad_effect.status_code == 422
    assert "Effect kind must be one of" in bad_effect.json()["detail"]


def test_unsupported_aspect_is_refused_before_building_an_edit():
    clips = routes_classic._classic_clips([
        {"scene": 0, "start": 0.0, "end": 4.0, "role": "hook"},
    ])
    with pytest.raises(Exception) as error:
        routes_classic.prepare_classic_render(
            "classic1", {}, {"clips": clips}, "16:9",
            {"overlays": [{"text": "Hi", "anchor": "top", "start": 0, "end": 2}]},
            captions=False, margin=0.075, audio_plan=None,
        )
    assert getattr(error.value, "status_code", None) == 422
    assert "9:16 and 4:5" in str(error.value.detail)
