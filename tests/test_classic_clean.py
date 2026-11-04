"""Classic Clean boxes: the C1/C2 layer, its rights gate and its frame route.

The box format is the Edit clean format. These tests prove that a Classic box
becomes the same clean filter the final render uses, that the frame route
compiles the cut on screen, and that a refused box is refused on the server —
not hidden in the browser.
"""

from __future__ import annotations

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
            _box(id="b", method="cover", box={"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.1}),
            _box(id="c", method="crop", box={"x": 0.0, "y": 0.0, "w": 0.9, "h": 0.1}),
        ],
        10.0,
    )
    assert [layer["method"] for layer in layers] == ["blur", "cover", "crop"]
    assert [
        routes_classic._classic_clean_edit([layer], clips)[0]["kind"]
        for layer in layers
    ] == ["blur", "plate", "crop_guard"]
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
    assert "Blur or Cover" in str(error.value)


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


def test_a_cover_box_draws_an_opaque_plate():
    clips = _clips()
    layers = routes_classic.normalize_classic_layers(
        [], [], routes_classic._classic_total(clips), [_box(method="cover")],
    )
    edit = routes_classic._build_classic_edit(clips, "9:16", layers)
    compiled = compose_render.compile_edit(
        edit, clips=clips, source={"width": 1920, "height": 1080},
        scenes=[], motion_engine="perspective",
    )
    filters = compiled["segments"][0]["pre_filters"]
    assert any("drawbox" in item for item in filters)


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


def test_a_box_drawn_on_a_16_9_frame_lands_inside_the_crop():
    """Frame coordinates converted through the crop cover the right pixels."""
    clips = _clips()
    compiled = _compile(clips, {})
    crop = routes_classic._classic_crop_box(
        compiled["segments"][0], compiled["source"],
    )
    assert crop is not None
    cx, cy, cw, ch = crop
    # The browser draws at 45-55% of the visible frame and converts the same way
    # the editor does: source = crop.origin + frame * crop.size.
    frame_box = {"x": 0.45, "y": 0.45, "w": 0.1, "h": 0.1}
    source_box = {
        "x": round(cx + frame_box["x"] * cw, 6),
        "y": round(cy + frame_box["y"] * ch, 6),
        "w": round(frame_box["w"] * cw, 6),
        "h": round(frame_box["h"] * ch, 6),
    }
    layers = routes_classic.normalize_classic_layers(
        [], [], 8.0, [_box(method="cover", box=source_box)],
    )
    filters = _compile(clips, layers)["segments"][0]["pre_filters"]
    drawbox = next(item for item in filters if "drawbox" in item)
    geometry = drawbox.split(":color=")[0].removeprefix("drawbox=")
    rect = {
        key: int(value)
        for key, value in (part.split("=", 1) for part in geometry.split(":"))
    }
    crop_px = (
        int(round(cx * 1920)), int(round(cy * 1080)),
        int(round(cw * 1920)), int(round(ch * 1080)),
    )
    left, top, width, height = crop_px
    assert rect["x"] >= left - 2, drawbox
    assert rect["x"] + rect["w"] <= left + width + 2, drawbox
    assert rect["y"] >= top - 2, drawbox
    assert rect["y"] + rect["h"] <= top + height + 2, drawbox


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


@pytest.mark.parametrize("kind", ["watermark", "screen_text"])
def test_the_server_refuses_a_box_the_policy_blocks(classic, kind):
    client, _ = classic
    response = client.put(
        "/api/classic/jobs/classic-clean/text",
        json={"clips": _clips(), "clean": [_box(kind=kind)]},
    )
    message = response.json()["detail"].lower()
    assert response.status_code == 409
    assert "watermark" in message or "screen" in message


def _unticked_job(client) -> None:
    """Rewrite the job as an import that did not carry the own-footage tick."""
    job = app.load_job("classic-clean")
    job["rights"] = {"attested": False, "source": "import", "at": 1.0}
    path = app._job_dir("classic-clean") / "job.json"
    path.write_text(json.dumps(job), encoding="utf-8")


def test_the_rights_lock_refuses_clean_without_the_tick(classic):
    import settings_store

    client, _ = classic
    settings_store.save_settings({"rights": {"lock": True}})
    _unticked_job(client)
    response = client.put(
        "/api/classic/jobs/classic-clean/text",
        json={"clips": _clips(), "clean": [_box()]},
    )
    assert response.status_code == 409
    assert "attestation" in response.text

    ticked = client.post(
        "/api/jobs/classic-clean/rights",
        json={"attested": True, "source": "import"},
    )
    assert ticked.status_code == 200, ticked.text
    allowed = client.put(
        "/api/classic/jobs/classic-clean/text",
        json={"clips": _clips(), "clean": [_box()]},
    )
    assert allowed.status_code == 200, allowed.text


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
    assert status["missing"] == ["LaMa", "STTN"]
    assert all(not item["installed"] for item in status["files"])
    assert "model pack" in status["note"]

    preview = client.post(
        "/api/classic/jobs/classic-clean/fill/preview",
        json={"clips": _clips(), "box": _box()["box"], "t": 1.0},
    )
    assert preview.status_code == 409
    assert preview.json()["error"] == "model_missing"

    models = tmp_path / "fill"
    models.mkdir()
    (models / routes_classic.FILL_MODELS["LaMa"]).write_bytes(b"x")
    (models / routes_classic.FILL_MODELS["STTN"]).write_bytes(b"x")
    monkeypatch.setenv("VIBECUT_FILL_MODELS", str(models))
    ready = client.get("/api/classic/fill").json()
    assert ready["available"] is True
    assert ready["missing"] == []
