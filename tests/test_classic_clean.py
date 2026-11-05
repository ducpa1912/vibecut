"""Classic Clean boxes: the C1/C2 layer, its rights gate and its frame route.

The box format is the Edit clean format. These tests prove that a Classic box
becomes the same clean filter the final render uses, that the frame route
compiles the cut on screen, and that a refused box is refused on the server —
not hidden in the browser.
"""

from __future__ import annotations

from pathlib import Path

import json

import pytest
from fastapi.testclient import TestClient

import app
import compose_render
import routes_classic


def _scene(index: int, start: float) -> dict:
    return {
        "id": index, "start": start, "end": start + 4.0, "dur": 4.0,
        "mid": start + 2.0, "hook": 60.0, "score": 60.0, "deep": True,
        "visual_score": 60.0, "motion_score": 60.0, "audio_score": 60.0,
        "text_score": 0.0, "ocr": "", "speech": "", "tags": [],
        "crop": {"cx": 0.5, "cy": 0.5}, "crop_mode": "center",
    }


def _job(**overrides) -> dict:
    job = {
        "id": "classic-clean", "created": 1.0, "updated": 1.0,
        "status": "ready", "progress": 1.0, "message": "Ready", "error": None,
        "source": {
            "path": "", "name": "source.mp4", "duration": 20.0,
            "width": 1920, "height": 1080, "fps": 30.0, "size": 16,
            "has_audio": True, "fingerprint": "classic-clean",
        },
        "options": {},
        "analysis": {
            "scene_count": 4, "hook_scene": 0, "deep_count": 4,
            "deep_scene_ids": [0, 1, 2, 3],
            "engine": {"transcript_language": "en"},
            "scenes": [_scene(index, index * 4.0) for index in range(4)],
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
    job = _job()
    directory = jobs / job["id"]
    directory.mkdir()
    (directory / "job.json").write_text(json.dumps(job), encoding="utf-8")
    client = TestClient(app.app)
    return client, tmp_path


def _clips() -> list[dict]:
    return routes_classic._classic_clips([
        {"scene": 0, "role": "hook", "start": 0.0, "end": 4.0, "dur": 4.0},
        {"scene": 1, "role": "beat", "start": 4.0, "end": 8.0, "dur": 4.0},
    ])


def _box(**overrides) -> dict:
    box = {
        "id": "cl01",
        "method": "blur",
        "box": {"x": 0.08, "y": 0.72, "w": 0.84, "h": 0.18},
        "label": "Burned-in subtitle",
        "kind": "subtitle",
        "source": "scan",
    }
    box.update(overrides)
    return box


# ------------------------------------------------------------------ the format


def test_a_clean_box_keeps_the_method_and_maps_to_an_edit_kind():
    clips = _clips()
    layers = routes_classic.normalize_classic_clean(
        [
            _box(id="a", method="blur"),
            _box(id="c", method="crop", box={"x": 0.0, "y": 0.0, "w": 0.9, "h": 0.1}),
        ],
        10.0,
    )
    assert [layer["method"] for layer in layers] == ["blur", "crop"]
    assert [
        routes_classic._classic_clean_edit([layer], clips)[0]["kind"]
        for layer in layers
    ] == ["blur", "crop_guard"]
    assert layers[0]["source"] == "scan"
    assert layers[0]["hidden"] is False
    assert layers[0]["ranges"] == []


def test_a_clean_box_is_validated_by_the_edit_rules():
    with pytest.raises(routes_classic.ClassicTextError):
        routes_classic.normalize_classic_clean(
            [_box(box={"x": 0.9, "y": 0.2, "w": 0.4, "h": 0.1})], 10.0,
        )
    with pytest.raises(routes_classic.ClassicTextError):
        routes_classic.normalize_classic_clean([_box(method="inpaint")], 10.0)
    with pytest.raises(routes_classic.ClassicTextError):
        routes_classic.normalize_classic_clean(
            [_box() for _ in range(routes_classic.MAX_CLASSIC_CLEAN + 1)], 10.0,
        )


def test_ai_fill_is_refused_while_its_models_are_missing():
    with pytest.raises(routes_classic.ClassicTextError) as error:
        routes_classic.normalize_classic_clean([_box(method="fill")], 10.0)
    # LaMa is the default engine; a missing model names its file.
    assert "lama_fp32.onnx" in str(error.value)


# ------------------------------------------------------------------ the render


def test_a_classic_box_compiles_to_the_same_clean_filter_the_reel_uses():
    clips = _clips()
    layers = routes_classic.normalize_classic_layers(
        [], [], routes_classic._classic_total(clips), [_box()],
    )
    edit = routes_classic._build_classic_edit(clips, "9:16", layers)
    compiled = compose_render.compile_edit(
        edit,
        clips=clips,
        source={"width": 1920, "height": 1080},
        scenes=[],
        motion_engine="perspective",
    )
    # No time ranges, so the box holds on every clip of the cut.
    assert compiled["counts"]["clean"] == len(compiled["segments"])
    segment = compiled["segments"][0]
    assert segment["clean_ids"] == ["cl01"]
    assert any("boxblur" in item for item in segment["pre_filters"])


def test_a_hidden_box_is_kept_in_the_editor_and_left_out_of_the_render():
    clips = _clips()
    layers = routes_classic.normalize_classic_layers(
        [], [], routes_classic._classic_total(clips),
        [_box(hidden=True)],
    )
    assert len(layers["clean"]) == 1
    assert layers["clean"][0]["hidden"] is True
    assert routes_classic._classic_clean_edit(layers["clean"], clips) == []
    compiled = compose_render.compile_edit(
        routes_classic._build_classic_edit(clips, "9:16", layers),
        clips=clips, source={"width": 1920, "height": 1080},
        scenes=[], motion_engine="perspective",
    )
    assert compiled["counts"]["clean"] == 0


# ------------------------------------------------- ranges: cut time to source


def _compile(clips: list[dict], layers: list[dict]) -> dict:
    return compose_render.compile_edit(
        routes_classic._build_classic_edit(clips, "9:16", layers),
        clips=clips,
        source={"width": 1920, "height": 1080},
        scenes=[],
        motion_engine="perspective",
    )


def test_a_range_is_translated_to_the_clips_source_time():
    """Cut time 1-2 s on a clip at source 40 s is source 41-42 s, not 1-2 s."""
    clips = routes_classic._classic_clips([
        {"scene": 0, "role": "hook", "start": 40.0, "end": 44.0, "dur": 4.0},
    ])
    layers = routes_classic.normalize_classic_layers(
        [], [], 4.0, [_box(ranges=[{"start": 1.0, "end": 2.0}])],
    )
    assert routes_classic._classic_clean_edit(layers["clean"], clips)[0]["ranges"] == [
        {"start": 41.0, "end": 42.0},
    ]
    segment = _compile(clips, layers)["segments"][0]
    assert segment["clean_ids"] == ["cl01"]
    assert "between(t,1.000,2.000)" in segment["pre_filter"]


def test_a_range_across_two_clips_becomes_one_source_range_each():
    clips = routes_classic._classic_clips([
        {"scene": 0, "role": "hook", "start": 40.0, "end": 44.0, "dur": 4.0},
        {"scene": 1, "role": "beat", "start": 100.0, "end": 104.0, "dur": 4.0},
    ])
    layers = routes_classic.normalize_classic_layers(
        [], [], 8.0, [_box(ranges=[{"start": 3.0, "end": 5.0}])],
    )
    assert routes_classic._classic_clean_edit(layers["clean"], clips)[0]["ranges"] == [
        {"start": 43.0, "end": 44.0},
        {"start": 100.0, "end": 101.0},
    ]
    compiled = _compile(clips, layers)
    first, second = compiled["segments"]
    assert first["clean_ids"] == ["cl01"] and second["clean_ids"] == ["cl01"]
    assert "between(t,3.000,4.000)" in first["pre_filter"]
    assert "between(t,0.000,1.000)" in second["pre_filter"]


def test_a_part_of_the_clip_the_cut_dropped_never_comes_back():
    # 4 s of source used for 2 s: source 42-44 never plays, so a range reaching
    # past the cut end must stop at 2 s of cut time, not at the clip's end.
    clips = routes_classic._classic_clips([
        {"scene": 0, "role": "hook", "start": 40.0, "end": 42.0, "dur": 2.0},
    ])
    layers = routes_classic.normalize_classic_layers(
        [], [], 2.0, [_box(ranges=[{"start": 1.0, "end": 2.0}])],
    )
    assert routes_classic._classic_clean_edit(layers["clean"], clips)[0]["ranges"] == [
        {"start": 41.0, "end": 42.0},
    ]


def test_a_box_without_ranges_applies_at_the_same_source_time_in_every_clip():
    """Why the editor ties a drawn box to the clip it was drawn on.

    No ranges means "the whole clip", and the box is source space, so the same
    rectangle lands on whatever those clips show at that source time. The
    browser now adds the clip's window; this test pins the server behaviour it
    is working around, so a change here is deliberate.
    """
    clips = routes_classic._classic_clips([
        {"scene": 0, "role": "hook", "start": 10.0, "end": 14.0, "dur": 4.0},
        {"scene": 1, "role": "beat", "start": 50.0, "end": 54.0, "dur": 4.0},
    ])
    layers = routes_classic.normalize_classic_layers([], [], 8.0, [_box()])
    compiled = _compile(clips, layers)
    assert [segment["clean_ids"] for segment in compiled["segments"]] == [
        ["cl01"], ["cl01"],
    ]


# ------------------------------------------------------------------ the routes


def test_saving_a_box_stores_it_with_the_cut(classic):
    client, _ = classic
    clips = _clips()
    saved = client.put(
        "/api/classic/jobs/classic-clean/text",
        json={"clips": clips, "overlays": [], "effects": [], "clean": [_box()]},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["cut"]["clean"][0]["method"] == "blur"
    looked_up = client.post(
        "/api/classic/jobs/classic-clean/text", json={"clips": clips},
    )
    assert looked_up.status_code == 200
    assert looked_up.json()["cut"]["clean"][0]["id"] == "cl01"


def test_a_drawn_box_saves_without_a_check_kind(classic):
    client, _ = classic
    response = client.put(
        "/api/classic/jobs/classic-clean/text",
        json={"clips": _clips(), "clean": [_box(kind="manual", label="Drawn box")]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["cut"]["clean"][0]["kind"] == "manual"


@pytest.mark.parametrize("kind", ["watermark", "screen_text", "handle_or_logo"])
def test_every_check_kind_can_be_saved(classic, kind):
    client, _ = classic
    response = client.put(
        "/api/classic/jobs/classic-clean/text",
        json={"clips": _clips(), "clean": [_box(kind=kind)]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["cut"]["clean"][0]["kind"] == kind


def _unticked_job(client) -> None:
    """Rewrite the job as an import that did not carry the own-footage tick."""
    job = app.load_job("classic-clean")
    job["rights"] = {"attested": False, "source": "import", "at": 1.0}
    path = app._job_dir("classic-clean") / "job.json"
    path.write_text(json.dumps(job), encoding="utf-8")


def test_clean_has_no_attestation_step(classic):
    import settings_store

    client, _ = classic
    settings_store.save_settings({"rights": {"lock": True}})
    _unticked_job(client)
    response = client.put(
        "/api/classic/jobs/classic-clean/text",
        json={"clips": _clips(), "clean": [_box()]},
    )
    assert response.status_code == 200, response.text


def test_the_frame_route_renders_the_cut_on_screen(classic, monkeypatch):
    client, _ = classic
    calls = {}

    def fake_frame(path, meta, job_dir, compiled, at, **options):
        calls.update({"compiled": compiled, "at": at, **options})
        return b"\xff\xd8frame"

    monkeypatch.setattr(routes_classic.render, "render_story_frame", fake_frame)
    response = client.post(
        "/api/classic/jobs/classic-clean/frame",
        json={
            "clips": _clips(), "clean": [_box()], "t": 1.5,
            "aspect": "9:16", "quality": "draft",
        },
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/jpeg"
    assert int(response.headers["x-vibecut-clean"]) >= 1
    # The browser draws boxes from this crop, so it must come from the server.
    assert response.headers["x-vibecut-segment"] == "0"
    crop = [float(value) for value in response.headers["x-vibecut-crop"].split(",")]
    assert crop == pytest.approx([656 / 1920, 0.0, 608 / 1920, 1.0], abs=1e-6)
    assert calls["at"] == 1.5
    assert calls["compiled"]["counts"]["clean"] >= 1
    assert calls["compiled"]["segments"][0]["clean_ids"] == ["cl01"]


def test_the_frame_route_refuses_times_outside_the_cut(classic, monkeypatch):
    client, _ = classic
    monkeypatch.setattr(
        routes_classic.render, "render_story_frame",
        lambda *args, **options: b"jpeg",
    )
    late = client.post(
        "/api/classic/jobs/classic-clean/frame",
        json={"clips": _clips(), "t": 99.0},
    )
    assert late.status_code == 422
    shape = client.post(
        "/api/classic/jobs/classic-clean/frame",
        json={"clips": _clips(), "t": 1.0, "aspect": "1:1"},
    )
    assert shape.status_code == 422


def test_boxes_saved_in_frame_space_are_dropped_and_counted(classic):
    """Version 1 boxes were drawn on the cropped frame. Do not reinterpret them."""
    client, _ = classic
    clips = _clips()
    job = app.load_job("classic-clean")
    hash_key = routes_classic.edits.clip_snapshot_hash(clips)
    job["classic_text"] = {
        "version": 1,
        "cuts": {
            hash_key: {
                "clips_hash": hash_key,
                "clip_count": len(clips),
                "duration": 8.0,
                "overlays": [],
                "effects": [],
                "clean": [_box()],
                "updated": 1.0,
            },
        },
    }
    path = app._job_dir("classic-clean") / "job.json"
    path.write_text(json.dumps(job), encoding="utf-8")

    looked_up = client.post(
        "/api/classic/jobs/classic-clean/text", json={"clips": clips},
    )
    assert looked_up.status_code == 200, looked_up.text
    cut = looked_up.json()["cut"]
    assert cut["clean"] == []
    assert cut["clean_reset"] == 1

    saved = client.put(
        "/api/classic/jobs/classic-clean/text",
        json={"clips": clips, "clean": [_box()]},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["cut"]["clean"][0]["id"] == "cl01"
    assert saved.json()["cut"]["clean_reset"] == 0


def test_fill_status_names_the_missing_models_and_never_lies(classic, monkeypatch):
    client, tmp_path = classic
    status = client.get("/api/classic/fill").json()
    assert status["available"] is False
    assert status["missing"] == ["LaMa"]
    assert all(not item["installed"] for item in status["files"])
    assert "model pack" in status["note"]
    assert status["engines"]["lama"]["ready"] is False
    assert "lama_fp32.onnx" in status["engines"]["lama"]["reason"]
    assert "sttn" not in status["engines"]
    assert status["preview"] is None

    preview = client.post(
        "/api/classic/jobs/classic-clean/fill/preview",
        json={"clips": _clips(), "clean": [_box(method="fill")], "t": 1.0},
    )
    assert preview.status_code == 409, preview.text
    assert preview.json()["error"] == "model_missing"


# A model file without its runtime package is not a ready engine.
def test_a_model_without_its_package_is_not_ready(classic, monkeypatch):
    client, tmp_path = classic
    models = tmp_path / "fill"
    models.mkdir()
    for filename in routes_classic.FILL_MODELS.values():
        (models / filename).write_bytes(b"x")
    monkeypatch.setenv("VIBECUT_FILL_MODELS", str(models))
    monkeypatch.setattr(
        routes_classic, "_classic_runtime_installed",
        lambda engine: (False, f"AI fill with {engine.upper()} needs the package."),
    )
    status = client.get("/api/classic/fill").json()
    assert status["available"] is False
    assert status["missing"] == []
    assert status["engines"]["lama"]["model"] is True
    assert "needs the package" in status["engines"]["lama"]["reason"]
    with pytest.raises(routes_classic.ClassicTextError) as error:
        routes_classic.normalize_classic_clean([_box(method="fill")], 10.0)
    assert "needs the package" in str(error.value)


# A box saved with the retired STTN engine still opens, and fills as LaMa.
def test_a_saved_sttn_box_opens_as_lama(classic, monkeypatch):
    client, tmp_path = classic
    models = tmp_path / "fill"
    models.mkdir()
    (models / routes_classic.FILL_MODELS["LaMa"]).write_bytes(b"x")
    monkeypatch.setenv("VIBECUT_FILL_MODELS", str(models))
    monkeypatch.setattr(routes_classic, "_classic_runtime_installed", lambda engine: (True, ""))
    status = client.get("/api/classic/fill").json()
    assert status["available"] is True
    assert status["default"] == "lama"
    assert list(status["engines"]) == ["lama"]

    layers = routes_classic.normalize_classic_clean(
        [_box(method="fill", engine="sttn")], 10.0,
    )
    assert layers[0]["method"] == "fill"
    assert layers[0]["engine"] == "lama"
    edit = routes_classic._classic_clean_edit(layers, _clips())
    assert edit[0]["kind"] == "fill"
    assert edit[0]["method"] == "lama"

    with pytest.raises(routes_classic.ClassicTextError) as error:
        routes_classic.normalize_classic_clean(
            [_box(method="fill", engine="propainter")], 10.0,
        )
    assert "LaMa" in str(error.value)


# Hand-drawn boxes start at the playhead for three seconds, and their time can be edited.
def test_the_panel_places_and_times_a_drawn_box():
    source = (Path(__file__).resolve().parents[1] / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    assert "CLEAN_MANUAL_SECONDS = 3" in source
    assert "window: cleanManualRange(currentCleanTime())" in source
    assert "ranges: [cleanManualRange(currentCleanTime())].filter(Boolean)" in source
    assert 'data-clean-time="${side}"' in source
    assert "A box must end after it starts." in source


def test_the_panel_offers_one_engine_and_the_still_option():
    source = (Path(__file__).resolve().parents[1] / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    assert "data-clean-engine" not in source
    assert "clean-found-engine" not in source
    assert "STTN" not in source and "sttn" not in source
    assert 'id="clean-fill-reuse"' in source
    assert "{ fill_reuse: true }" in source


# No rights gate in Classic: any video, and any found kind can be cleaned.
@pytest.mark.parametrize("kind", ["watermark", "screen_text", "handle_or_logo", "subtitle"])
def test_every_found_kind_can_be_cleaned_in_classic(monkeypatch, kind):
    import cleanup
    import detect
    import rights

    monkeypatch.setenv("VIBECUT_EDITION", "classic")
    job = {"rights": {"attested": False}}
    assert rights.clean_block_reason(kind, job=job) is None
    assert rights.may_import(False) is True
    tracklet = {
        "id": "trk_a", "kind": kind, "confidence": 0.9,
        "box": {"x": 0.8, "y": 0.05, "w": 0.15, "h": 0.05},
        "ranges": [{"start": 0.0, "end": 2.0}], "text_sample": "mark",
    }
    entry = detect.clean_prefill([tracklet], job=job)[0]
    assert entry["enabled"] is True and entry["blocked"] is None
    built = cleanup.tracklet_clean_layers([tracklet], job=job)
    assert {layer["tracklet_id"] for layer in built["layers"]} == {"trk_a"}
    assert built["refused"] == []


def test_a_box_named_watermark_saves_in_classic_and_stays_refused_elsewhere(monkeypatch):
    import cleanup
    import edits

    layer = {"id": "a", "kind": "fill", "label": "watermark",
             "box": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.1}}
    monkeypatch.setenv("VIBECUT_EDITION", "classic")
    assert edits.normalize_clean([layer])[0]["label"] == "watermark"
    assert cleanup.require_attestation(None)["accepted"] is True
    monkeypatch.setenv("VIBECUT_EDITION", "all")
    with pytest.raises(edits.EditError):
        edits.normalize_clean([layer])
    with pytest.raises(cleanup.CleanupValidationError):
        cleanup.require_attestation(None)

