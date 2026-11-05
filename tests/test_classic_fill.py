"""AI text fill, from a Classic box to the fill plan and back.

These are code checks: no model files, no torch, no video. The fakes sit where
the models would be, so the contract around them — engine choice, source
ranges, cache keys, the untouched pixels outside the mask — is what is tested.
A real fill is a founder test on a real video, not this file.
"""

from __future__ import annotations

import json
import threading

import numpy as np
import pytest

import compose_render
import edits
import render
import textfill


def _scene(index: int, start: float) -> dict:
    return {
        "id": index, "start": start, "end": start + 4.0, "dur": 4.0,
        "mid": start + 2.0, "hook": 60.0, "score": 60.0, "deep": True,
        "visual_score": 60.0, "motion_score": 60.0, "audio_score": 60.0,
        "text_score": 0.0, "ocr": "", "speech": "", "tags": [],
        "crop": {"cx": 0.5, "cy": 0.5}, "crop_mode": "center",
    }


def _clips() -> list[dict]:
    return [
        {"scene": 0, "role": "hook", "start": 40.0, "end": 44.0, "dur": 4.0},
        {"scene": 1, "role": "beat", "start": 100.0, "end": 104.0, "dur": 4.0},
    ]


def _edit(clean: list[dict] | None = None) -> dict:
    return edits.build_edit(
        story_ref={
            "set_id": "classic",
            "story_id": "cut_fill",
            "clip_hash": "0123456789abcdef",
            "title": "Fill test",
            "duration": 8.0,
            "clip_count": 2,
        },
        aspect="9:16",
        clean=clean if clean is not None else [],
    )


def _layer(**overrides) -> dict:
    layer = {
        "id": "cl01",
        "kind": "fill",
        "method": "sttn",
        "box": {"x": 0.1, "y": 0.7, "w": 0.8, "h": 0.16},
        "ranges": [{"start": 43.0, "end": 44.0}],
        "label": "subtitle",
    }
    layer.update(overrides)
    return layer


def _compile(edit: dict, *, scenes: list[dict] | None = None) -> dict:
    return compose_render.compile_edit(
        edit,
        clips=_clips(),
        source={"width": 1920, "height": 1080},
        scenes=scenes if scenes is not None else [_scene(0, 40.0), _scene(1, 100.0)],
        motion_engine="perspective",
    )


# ------------------------------------------------------------------ the schema


def test_only_a_fill_layer_carries_an_engine_and_it_defaults_to_sttn():
    layer = edits.normalize_clean([
        {"id": "a", "kind": "fill", "box": {"x": 0, "y": 0, "w": 0.2, "h": 0.1}},
        {"id": "b", "kind": "blur", "box": {"x": 0, "y": 0, "w": 0.2, "h": 0.1}},
    ])
    assert layer[0]["method"] == "sttn"
    assert "method" not in layer[1]


def test_an_unknown_engine_is_refused():
    with pytest.raises(edits.EditError):
        edits.normalize_clean([_layer(method="delogo")])


# ------------------------------------------------------------------ the plan


def test_a_fill_box_compiles_to_a_fill_plan_not_a_filter():
    compiled = _compile(_edit([_layer()]))
    segment = compiled["segments"][0]
    assert segment["clean_ids"] == []
    assert [item for item in segment["pre_filters"] if "boxblur" in item or "drawbox" in item] == []
    assert segment["fill"]["ids"] == ["cl01"]
    assert segment["fill"]["method"] == "sttn"
    # Ranges in the plan are source time: 43-44 s of source, not 3-4 s of cut.
    assert segment["fill"]["layers"][0]["ranges"] == [{"start": 43.0, "end": 44.0}]


def test_a_fill_box_limited_to_one_clip_leaves_the_other_alone():
    compiled = _compile(_edit([_layer()]))
    first, second = compiled["segments"]
    assert first["fill"] is not None
    assert second["fill"] is None


def test_the_top_layer_decides_the_engine_and_a_mix_is_warned():
    compiled = _compile(_edit([
        _layer(id="cl01", method="sttn", box={"x": 0.1, "y": 0.7, "w": 0.8, "h": 0.1}),
        _layer(id="cl02", method="lama", z=5, box={"x": 0.1, "y": 0.2, "w": 0.8, "h": 0.1}),
    ]))
    segment = compiled["segments"][0]
    assert segment["fill"]["method"] == "lama"
    assert segment["fill"]["ids"] == ["cl01", "cl02"]
    assert any(item["code"] == "fill_method_mixed" for item in compiled["warnings"])


def test_a_blur_and_a_fill_box_on_one_beat_keep_their_own_jobs():
    compiled = _compile(_edit([
        _layer(id="cl01", method="sttn"),
        {"id": "cl02", "kind": "blur", "box": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.1}},
    ]))
    segment = compiled["segments"][0]
    assert segment["clean_ids"] == ["cl02"]
    assert segment["fill"]["ids"] == ["cl01"]


# ------------------------------------------------------------------ the cache


def test_a_fill_segment_has_its_own_cache_entry():
    meta = {"fingerprint": "abc", "duration": 10.0, "size": 1000}
    scene = {"crop": {"cx": 0.5, "cy": 0.5}}
    base = render._segment_cache_key(
        meta, scene, 40.0, 90, 540, 960, "draft", "libx264", True, True,
    )
    filled = render._segment_cache_key(
        meta, scene, 40.0, 90, 540, 960, "draft", "libx264", True, True,
        fill_key="a" * 20,
    )
    other = render._segment_cache_key(
        meta, scene, 40.0, 90, 540, 960, "draft", "libx264", True, True,
        fill_key="b" * 20,
    )
    assert base != filled and filled != other


def test_the_span_key_follows_the_box_and_the_model(tmp_path):
    meta = {"fingerprint": "abc", "width": 1920, "height": 1080, "fps": 30.0}
    base = textfill.span_key(
        meta=meta, start=40.0, duration=4.0, layers=[_layer()],
        method="sttn", model_stamp="m1",
    )
    moved = textfill.span_key(
        meta=meta, start=40.0, duration=4.0,
        layers=[_layer(box={"x": 0.1, "y": 0.6, "w": 0.8, "h": 0.16})],
        method="sttn", model_stamp="m1",
    )
    model = textfill.span_key(
        meta=meta, start=40.0, duration=4.0, layers=[_layer()],
        method="sttn", model_stamp="m2",
    )
    assert len({base, moved, model}) == 3

    model_file = tmp_path / textfill.MODEL_FILES["sttn"]
    model_file.write_bytes(b"x" * 10)
    first = textfill.model_signature(["sttn"], tmp_path)
    model_file.write_bytes(b"x" * 20)
    assert textfill.model_signature(["sttn"], tmp_path) != first
    # A missing model is part of the signature, not an error.
    assert textfill.model_signature(["lama"], tmp_path)


# ------------------------------------------------------------------ the pixels


def test_the_fill_leaves_pixels_outside_the_feather_bit_identical():
    height, width = 40, 60
    original = np.random.default_rng(7).integers(0, 256, (height, width, 3), dtype=np.uint8)
    filled = np.zeros_like(original)
    hole = textfill.masks.rasterize([(10, 10, 30, 30)], width, height)
    alpha = textfill.masks.feather(hole)
    out = textfill.masks.paste(original, filled, alpha)
    outside = alpha <= 0.0
    assert np.array_equal(out[outside], original[outside])
    assert not np.array_equal(out[~outside], original[~outside])


def test_a_missing_package_is_a_plain_message_not_a_crash(tmp_path, monkeypatch):
    from textfill import lama as lama_module

    def boom(*args, **kwargs):
        raise ImportError("onnxruntime is not installed")

    monkeypatch.setattr(lama_module, "LamaFiller", boom)
    textfill.release_fillers()
    frame = np.zeros((32, 32, 3), dtype=np.uint8)
    model = tmp_path / textfill.MODEL_FILES["lama"]
    model.write_bytes(b"x" * 10)
    monkeypatch.setenv("VIBECUT_FILL_MODELS", str(tmp_path))
    with pytest.raises(textfill.FillError) as error:
        textfill.fill_frame(frame, [(4, 4, 12, 12)], data_root=tmp_path)
    assert "onnxruntime" in str(error.value)
    textfill.release_fillers()


def test_a_missing_model_file_names_the_file(tmp_path, monkeypatch):
    textfill.release_fillers()
    monkeypatch.setenv("VIBECUT_FILL_MODELS", str(tmp_path))
    with pytest.raises(textfill.FillError) as error:
        textfill.fill_frame(
            np.zeros((8, 8, 3), dtype=np.uint8), [(2, 2, 6, 6)], data_root=tmp_path,
        )
    assert "lama_fp32.onnx" in str(error.value)


# ------------------------------------------------------------------ the pre-pass


def test_the_pre_pass_fills_only_beats_that_ask_and_releases_the_models(tmp_path, monkeypatch):
    job_dir = tmp_path / "jobs" / "j1"
    job_dir.mkdir(parents=True)
    calls = []

    def fake_prepare(**kwargs):
        calls.append(kwargs)
        # The real span reports its own progress; the wrapper labels it.
        kwargs["progress"](0.5, "STTN 60/120")
        return {"path": str(tmp_path / "filled.mp4"), "key": "k" * 20,
                "cached": False, "method": kwargs["method"]}

    released = []
    monkeypatch.setattr(textfill, "prepare_span", fake_prepare)
    monkeypatch.setattr(textfill, "release_fillers", lambda: released.append(True))

    segments = [
        {"start": 40.0, "frames": 120,
         "fill": {"method": "sttn", "layers": [{"box": {}, "ranges": []}]}},
        {"start": 100.0, "frames": 120, "fill": None},
    ]
    progress = []
    fills = render._prepare_fills(
        "source.mp4", {"width": 1920, "height": 1080}, job_dir, segments,
        lambda fraction, message: progress.append((fraction, message)),
        threading.Event(),
    )
    assert len(calls) == 1
    assert fills[0]["key"] == "k" * 20
    assert fills[1] is None
    assert calls[0]["duration"] == pytest.approx(4.0)
    assert released == [True]
    assert "Filling text, beat 1/1" in progress[-1][1]
    assert "STTN 60/120" in progress[-1][1]
    # Progress starts after the filler's share and stays inside it.
    assert 0.02 <= progress[-1][0] <= 0.45


def test_a_cancelled_fill_stops_the_render(tmp_path, monkeypatch):
    job_dir = tmp_path / "jobs" / "j1"
    job_dir.mkdir(parents=True)

    def fake_prepare(**kwargs):
        raise textfill.FillCancelled("Render cancelled.")

    monkeypatch.setattr(textfill, "prepare_span", fake_prepare)
    monkeypatch.setattr(textfill, "release_fillers", lambda: None)
    segments = [{"start": 0.0, "frames": 30, "fill": {"method": "sttn", "layers": []}}]
    with pytest.raises(render.RenderCancelled):
        render._prepare_fills(
            "source.mp4", {"width": 1, "height": 1}, job_dir, segments,
            lambda *args: None, threading.Event(),
        )


def test_a_fill_failure_is_a_render_error_with_its_reason(tmp_path, monkeypatch):
    job_dir = tmp_path / "jobs" / "j1"
    job_dir.mkdir(parents=True)

    def fake_prepare(**kwargs):
        raise textfill.FillError("The STTN fill model is missing.")

    monkeypatch.setattr(textfill, "prepare_span", fake_prepare)
    monkeypatch.setattr(textfill, "release_fillers", lambda: None)
    segments = [{"start": 0.0, "frames": 30, "fill": {"method": "sttn", "layers": []}}]
    with pytest.raises(Exception) as error:
        render._prepare_fills(
            "source.mp4", {"width": 1, "height": 1}, job_dir, segments,
            lambda *args: None, threading.Event(),
        )
    assert "model is missing" in str(error.value)


def test_a_clean_mask_is_schema_data_and_keeps_the_box():
    layer = edits.normalize_clean([{
        "id": "a", "kind": "fill", "method": "lama",
        "box": {"x": 0.1, "y": 0.2, "w": 0.4, "h": 0.1},
        "mask": {"strokes": [{"r": 0.02, "points": [{"x": 0.2, "y": 0.25}]}]},
        "text_key": "same text",
    }])[0]
    assert layer["method"] == "lama"
    assert layer["text_key"] == "same text"
    assert layer["mask"]["strokes"][0]["points"] == [{"x": 0.2, "y": 0.25}]
    # The box is still there; a brush extends it rather than replacing it.
    rects = textfill.masks.layer_rects(layer, 1000, 1000)
    assert len(rects) >= 2


def test_top_and_bottom_text_do_not_share_one_sttn_strip():
    rects = [(100, 900, 900, 980), (100, 40, 900, 120)]
    strips = textfill.masks.sttn_strips(rects, 1000, 1000)
    assert len(strips) >= 2
    assert not any(a <= 500 <= b for a, b in strips)
