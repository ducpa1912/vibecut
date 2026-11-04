"""Clean R0: two methods, layers stay on the video, one layer per scanned text."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import cleanup
import compose_render
import detect
import edits
import textfill
from textfill import mask as masks

ROOT = Path(__file__).resolve().parents[1]
CLEAN = (ROOT / "static/studio/edit/layers/clean.js").read_text(encoding="utf-8")
INDEX = (ROOT / "static/studio/edit/index.js").read_text(encoding="utf-8")
PREVIEW = (ROOT / "static/studio/edit/preview.js").read_text(encoding="utf-8")
TIMELINE = (ROOT / "static/studio/edit/timeline.js").read_text(encoding="utf-8")

BOX = {"x": 0.1, "y": 0.8, "w": 0.8, "h": 0.05}


def _stroke(*points, r=0.0125):
    return {"box": BOX, "mask": {"space": "source", "strokes": [{
        "r": r, "points": [{"x": x, "y": y} for x, y in points],
    }]}}


def _covered(rects, width=720, height=1280):
    return masks.rasterize(rects, width, height)


def test_one_click_fills_the_box_not_a_dot():
    rects = masks.layer_rects(_stroke((0.42, 0.82)), 720, 1280)
    assert rects == [masks.layer_rect({"box": BOX}, 720, 1280)]


def test_a_tiny_stroke_is_a_slip_too():
    rects = masks.layer_rects(_stroke((0.42, 0.82), (0.421, 0.82)), 720, 1280)
    assert rects == [masks.layer_rect({"box": BOX}, 720, 1280)]


def test_strokes_are_joined_across_a_fast_drag():
    rects = masks.layer_rects(_stroke((0.2, 0.82), (0.6, 0.82)), 720, 1280)
    row = _covered(rects)[int(0.82 * 1280)]
    assert row[int(0.2 * 720):int(0.6 * 720)].all()


def test_a_mask_only_narrows_the_box():
    rects = masks.layer_rects(_stroke((0.5, 0.4), (0.5, 0.82), r=0.02), 720, 1280)
    x0, y0, x1, y1 = masks.layer_rect({"box": BOX}, 720, 1280)
    picture = _covered(rects)
    assert not picture[:y0].any() and not picture[y1:].any()
    assert not picture[:, :x0].any() and not picture[:, x1:].any()
    assert picture.any()


def test_a_mask_wholly_outside_the_box_keeps_the_box():
    rects = masks.layer_rects(_stroke((0.5, 0.2), (0.6, 0.2)), 720, 1280)
    assert rects == [masks.layer_rect({"box": BOX}, 720, 1280)]


def test_brush_stamps_are_round_not_square():
    rects = masks.layer_rects(_stroke((0.5, 0.82), (0.54, 0.82), r=0.04), 720, 1280)
    corner = _covered(rects)
    xs = np.where(corner.any(axis=0))[0]
    ys = np.where(corner.any(axis=1))[0]
    assert not corner[ys[0], xs[0]]


def _fill_layer(**extra):
    return {"id": "a", "kind": "fill", "method": "sttn", "box": dict(BOX), "ranges": [], "z": 0, **extra}


CROP = {"x": 656, "y": 0, "w": 608, "h": 1080}


def test_fill_skips_a_layer_fully_hidden_by_the_crop():
    hidden = _fill_layer(box={"x": 0.0, "y": 0.8, "w": 0.2, "h": 0.05})
    plan, _ = compose_render._fill_plan(
        [hidden], 0.0, 4.0, crop=CROP, source_width=1920, source_height=1080, skip_hidden=True,
    )
    assert plan is None


def test_a_partly_visible_layer_still_fills():
    partly = _fill_layer(box={"x": 0.2, "y": 0.8, "w": 0.2, "h": 0.05})
    plan, _ = compose_render._fill_plan(
        [partly], 0.0, 4.0, crop=CROP, source_width=1920, source_height=1080, skip_hidden=True,
    )
    assert plan["ids"] == ["a"]


def test_a_source_mask_survives_a_shape_change_and_ignores_the_crop():
    mask = {"space": "source", "aspect": "9:16", "strokes": [{
        "id": "s", "r": 0.02, "points": [{"x": 0.3, "y": 0.8}, {"x": 0.5, "y": 0.8}],
    }]}
    plan, _ = compose_render._fill_plan(
        [_fill_layer(mask=mask)], 0.0, 4.0, crop=CROP, source_width=1920, source_height=1080, aspect="4:5",
    )
    assert plan["layers"][0]["mask"]["strokes"][0]["points"] == mask["strokes"][0]["points"]


def test_an_old_output_mask_of_another_shape_falls_back_to_the_box():
    mask = {"space": "output", "aspect": "9:16", "strokes": [{
        "id": "s", "r": 0.02, "points": [{"x": 0.3, "y": 0.8}, {"x": 0.5, "y": 0.8}],
    }]}
    plan, _ = compose_render._fill_plan(
        [_fill_layer(mask=mask)], 0.0, 4.0, crop=CROP, source_width=1920, source_height=1080, aspect="4:5",
    )
    assert "mask" not in plan["layers"][0]


def _obs(t, text, y=0.8, h=0.05):
    return {
        "t": t, "start": t, "end": t + 2.0, "text": text,
        "box": {"x": 0.1, "y": y, "w": 0.8, "h": h},
        "confidence": 0.9, "source": "sampled",
    }


def test_returning_text_in_the_same_area_is_one_tracklet():
    rows = [_obs(t, "same words") for t in (10, 12, 14, 30, 32, 34)]
    tracklets = detect.build_tracklets(rows, 60.0)
    assert len(tracklets) == 1
    assert tracklets[0]["ranges"] == [{"start": 10, "end": 16.0}, {"start": 30, "end": 36.0}]


def test_different_text_in_the_same_area_at_other_times_stays_separate():
    rows = [_obs(t, "first words") for t in (10, 12)] + [_obs(t, "other words") for t in (30, 32)]
    assert len(detect.build_tracklets(rows, 60.0)) == 2


def test_tracklet_ids_do_not_depend_on_what_else_was_scanned():
    same = [_obs(t, "same words") for t in (10, 12, 14)]
    title = [_obs(t, "a title", y=0.1) for t in (2, 4, 6)]
    alone = detect.build_tracklets(same, 60.0)
    both = detect.build_tracklets(title + same, 60.0)
    assert alone[0]["id"] in {item["id"] for item in both}
    assert alone[0]["id"] != detect.build_tracklets(title, 60.0)[0]["id"]


def _layer(tracklet_id, box=None, ranges=None, **extra):
    return {
        "id": f"cl_{tracklet_id}",
        "kind": "fill",
        "box": dict(box or BOX),
        "ranges": ranges if ranges is not None else [{"start": 10.0, "end": 16.0}],
        "tracklet_id": tracklet_id,
        "tracklet_kind": "subtitle",
        **extra,
    }


def test_rescan_with_a_new_id_and_a_shifted_box_adds_no_duplicate():
    shifted = {"x": 0.1, "y": 0.802, "w": 0.8, "h": 0.052}
    merged = cleanup.merge_auto_clean_layers([_layer("trk_old")], [_layer("trk_new", shifted)])
    assert merged["layers"] == []
    assert "already" in merged["skipped"][0]["reason"]


def test_an_id_reused_for_other_text_elsewhere_is_not_skipped():
    existing = _layer("trk_0001", {"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.05})
    merged = cleanup.merge_auto_clean_layers([existing], [_layer("trk_0001")])
    assert len(merged["layers"]) == 1


def test_same_text_later_widens_the_layer_instead_of_adding_one():
    existing = _layer("trk_a", text_key="abc12345")
    later = _layer("trk_b", ranges=[{"start": 30.0, "end": 36.0}], text_key="abc12345")
    merged = cleanup.merge_auto_clean_layers([existing], [later])
    assert merged["layers"] == []
    assert merged["updated"] == [{
        "id": "cl_trk_a",
        "ranges": [{"start": 10.0, "end": 16.0}, {"start": 30.0, "end": 36.0}],
    }]
    assert existing["ranges"] == [{"start": 10.0, "end": 16.0}]


def test_other_text_in_the_same_area_at_another_time_gets_its_own_layer():
    existing = _layer("trk_a", text_key="abc12345")
    later = _layer("trk_b", ranges=[{"start": 30.0, "end": 36.0}], text_key="def67890")
    merged = cleanup.merge_auto_clean_layers([existing], [later])
    assert len(merged["layers"]) == 1


def test_scan_layers_never_merge_into_a_drawn_box():
    drawn = {"id": "cl_manual_1", "kind": "blur", "box": dict(BOX), "ranges": [{"start": 10.0, "end": 16.0}]}
    merged = cleanup.merge_auto_clean_layers([drawn], [_layer("trk_a")])
    assert len(merged["layers"]) == 1


def test_text_key_reaches_the_layer_and_passes_the_edit_format():
    tracklet = {
        "id": "trk_a", "kind": "subtitle", "box": dict(BOX), "text_sample": "Same Words",
        "ranges": [{"start": 10.0, "end": 16.0}], "confidence": 0.9,
    }
    built = cleanup.tracklet_clean_layers([tracklet], attested=True)
    assert built["layers"][0]["text_key"]
    assert edits.normalize_clean(built["layers"])[0]["text_key"] == built["layers"][0]["text_key"]


def test_status_is_not_ready_without_the_package(tmp_path, monkeypatch):
    (tmp_path / textfill.MODEL_FILES["lama"]).write_bytes(b"x")
    monkeypatch.setattr(textfill.importlib.util, "find_spec", lambda name: None)
    assert "onnxruntime" in textfill.method_problem("lama", tmp_path)
    assert textfill.MODEL_FILES["sttn"] in textfill.method_problem("sttn", tmp_path)


def test_preview_waits_for_no_render_and_frees_the_model(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBECUT_FILL_MODELS", str(tmp_path))
    (tmp_path / textfill.MODEL_FILES["lama"]).write_bytes(b"x")
    released = []

    class Filler:
        def fill(self, work, hole):
            return work

    monkeypatch.setattr(textfill, "_filler", lambda method, path: Filler())
    monkeypatch.setattr(textfill, "release_fillers", lambda: released.append(True))
    frame = np.zeros((64, 64, 3), dtype=np.uint8)
    textfill.fill_frame(frame, [(4, 4, 20, 20)], data_root=tmp_path)
    assert released == [True]
    assert textfill._LOCK.locked() is False

    with textfill._LOCK:
        with pytest.raises(textfill.FillError, match="busy"):
            textfill.fill_frame(frame, [(4, 4, 20, 20)], data_root=tmp_path)


def test_clean_offers_ai_fill_and_blur_only():
    assert 'const KIND_ORDER = ["fill", "blur"];' in CLEAN
    assert 'value: "cover"' not in CLEAN
    assert "Mid-frame" not in CLEAN
    assert 'data-tl-action="mosaic"' not in TIMELINE
    assert "addMosaicLayer" not in INDEX
    assert "(old)" in CLEAN


def test_each_box_has_its_own_switch():
    assert 'id="st-box-method"' in PREVIEW
    assert "onCleanMethod" in PREVIEW
    assert "function methodSwitch(layer)" in CLEAN
    assert "function setCleanMethod(layerId, kind)" in INDEX
    assert "Hidden by crop" in CLEAN


def test_a_new_box_starts_on_the_current_beat():
    assert "layer.ranges = [{ start: round(at.start, 2), end: round(at.end, 2) }]" in INDEX


def test_brush_marks_are_saved_on_the_video():
    assert 'mask.space = "source";' in INDEX
    assert "frame.x + x * frame.w" in INDEX
    assert "function upgradeMasks(edit)" in INDEX
    assert "callbacks.onPaint(current.layerId, points, currentCrop())" in PREVIEW


def test_brush_button_reuses_the_layer_and_drops_an_unpainted_one():
    assert 'item.kind === "fill" && sameScanText(item, row.tracklet)' in CLEAN
    assert "function dropUnpaintedLayers()" in INDEX
    assert "callbacks.onPaintEnd()" in PREVIEW
    assert "A single click does nothing." in INDEX
