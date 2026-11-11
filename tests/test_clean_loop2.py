from __future__ import annotations

import numpy as np

from duckcore import clean
from duckcore.engine.textfill import mask as masks


def _layer(track: list[dict], box: dict | None = None) -> dict:
    return {
        "id": "cl_test",
        "tracklet_id": "trk_test",
        "kind": "fill",
        "box": box or {"x": 0.1, "y": 0.1, "w": 0.5, "h": 0.2},
        "ranges": [{"start": 0.0, "end": 2.0}],
        "track": track,
    }


def test_layer_rects_at_follows_track() -> None:
    layer = _layer([
        {"t": 1.0, "box": {"x": 0.10, "y": 0.10, "w": 0.20, "h": 0.10}},
        {"t": 2.0, "box": {"x": 0.55, "y": 0.10, "w": 0.20, "h": 0.10}},
    ])
    first = masks.layer_rects_at(layer, 1.05, 1000, 1000)
    second = masks.layer_rects_at(layer, 1.95, 1000, 1000)
    assert first and second
    assert first != second
    assert first[0][0] < second[0][0]


def test_layer_rects_at_returns_empty_outside_track() -> None:
    layer = _layer([
        {"t": 1.0, "box": {"x": 0.10, "y": 0.10, "w": 0.20, "h": 0.10}},
    ])
    assert masks.layer_rects_at(layer, 10.0, 1000, 1000) == []


def test_layers_from_report_preserves_track_and_fill_keys() -> None:
    track = [
        {"t": 1.0, "box": {"x": 0.10, "y": 0.10, "w": 0.20, "h": 0.10}},
        {"t": 1.5, "box": {"x": 0.11, "y": 0.10, "w": 0.20, "h": 0.10}},
    ]
    report = {
        "tracklets": [
            {
                "id": "trk_test",
                "kind": "title",
                "box": {"x": 0.10, "y": 0.10, "w": 0.21, "h": 0.10},
                "ranges": [{"start": 1.0, "end": 1.5}],
                "text_sample": "obviously",
                "confidence": 0.9,
                "track": track,
                "large": True,
                "fill_plan": {"keys": 4.0, "motion": 1.2, "noise": 0.2},
            }
        ]
    }
    layers = clean.layers_from_report(report)
    assert len(layers) == 1
    assert layers[0]["track"] == track
    assert layers[0]["large"] is True
    assert layers[0]["fill_keys"] == 4.0


def test_span_key_changes_with_track() -> None:
    from duckcore.engine import textfill

    meta = {"fingerprint": "test", "size": 100, "duration": 10.0, "width": 100, "height": 100, "fps": 24.0}
    tracked = _layer([{"t": 1.0, "box": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.1}}])
    static = {**tracked}
    static.pop("track")
    first = textfill.span_key(
        meta=meta, start=0.0, duration=2.0, layers=[tracked],
        method="lama", model_stamp="test-model",
    )
    second = textfill.span_key(
        meta=meta, start=0.0, duration=2.0, layers=[static],
        method="lama", model_stamp="test-model",
    )
    assert first != second


def test_text_in_region_finds_dense_glyph() -> None:
    image = np.zeros((80, 80, 3), dtype=np.uint8)
    image[:, :] = (40, 80, 50)
    image[16:64, 16:64] = (245, 245, 245)
    found = masks.text_in_region(image, 4)
    assert found is not None
    assert float(found.mean()) > 0.3


def test_frame_rects_follow_track() -> None:
    layer = _layer([
        {"t": 1.0, "box": {"x": 0.10, "y": 0.10, "w": 0.20, "h": 0.10}},
        {"t": 1.9, "box": {"x": 0.55, "y": 0.10, "w": 0.20, "h": 0.10}},
    ])
    table = masks.frame_rects([layer], start=1.0, fps=2, frames=2, width=1000, height=1000)
    assert table[0] and table[1]
    assert table[0] != table[1]


def test_large_layer_gets_more_padding() -> None:
    small = {"box": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.04}, "tracklet_id": "trk"}
    large = {"box": {"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.2}, "tracklet_id": "trk"}
    small_rect = masks.layer_rect(small, 1000, 1000)
    large_rect = masks.layer_rect(large, 1000, 1000)
    small_pad = int(0.1 * 1000) - small_rect[1]
    large_pad = int(0.1 * 1000) - large_rect[1]
    assert large_pad > small_pad


def test_span_key_changes_with_fill_keys() -> None:
    from duckcore.engine import textfill

    meta = {"fingerprint": "test", "size": 100, "duration": 10.0, "width": 100, "height": 100, "fps": 24.0}
    layer = _layer([])
    layer["fill_keys"] = 0.0
    first = textfill.span_key(meta=meta, start=0.0, duration=2.0, layers=[layer], method="lama", model_stamp="test-model")
    layer["fill_keys"] = 4.0
    second = textfill.span_key(meta=meta, start=0.0, duration=2.0, layers=[layer], method="lama", model_stamp="test-model")
    assert first != second


def test_text_in_region_finds_bright_text_on_bright_background() -> None:
    image = np.zeros((80, 80, 3), dtype=np.uint8)
    image[:, :] = (120, 180, 210)
    image[20:60, 12:68] = (246, 246, 246)
    found = masks.text_in_region(image, 4)
    assert found is not None
    assert float(found.mean()) > 0.3


def _report(motion: float, kind: str = "subtitle") -> dict:
    return {
        "tracklets": [
            {
                "id": "trk_motion",
                "kind": kind,
                "box": {"x": 0.3, "y": 0.48, "w": 0.4, "h": 0.04},
                "ranges": [{"start": 1.0, "end": 3.0}],
                "text_sample": "words",
                "confidence": 0.9,
                "fill_plan": {"keys": 6.0, "motion": motion, "noise": 1.0},
            }
        ]
    }


def test_still_line_keeps_ai_fill() -> None:
    layer = clean.layers_from_report(_report(2.0))[0]
    assert layer["kind"] == "fill"
    assert layer["method"] == "lama"
    assert layer["quality"] == "steady"
    assert layer["auto"] is True


def test_moving_line_keeps_fill_and_is_flagged() -> None:
    layer = clean.layers_from_report(_report(31.0))[0]
    assert layer["kind"] == "fill"
    assert layer["method"] == "lama"
    assert layer["quality"] == "moving"
    assert layer["motion"] == 31.0


def _short_report() -> dict:
    report = _report(4.0)
    report["tracklets"][0]["ranges"] = [{"start": 0.0, "end": 0.25}]
    return report


def test_flash_of_text_defaults_to_blur() -> None:
    layer = clean.layers_from_report(_short_report())[0]
    assert layer["kind"] == "blur"
    assert layer["method"] == ""


def test_clean_all_keeps_a_user_choice_and_replans_its_own() -> None:
    fresh = clean.layers_from_report(_short_report())
    planned = clean.layers_from_report(_report(4.0))[0]
    merged = clean.merge_layers(
        [
            {**planned, "id": "cl_picked", "auto": False, "kind": "fill", "method": "lama"},
            {**planned, "id": "cl_planned", "auto": True},
        ],
        [{**fresh[0], "id": "cl_picked"}, {**fresh[0], "id": "cl_planned"}],
    )
    by_id = {layer["id"]: layer for layer in merged}
    assert by_id["cl_picked"]["kind"] == "fill"
    assert by_id["cl_picked"]["auto"] is False
    assert by_id["cl_planned"]["kind"] == "blur"


def test_patch_layer_marks_the_choice_as_the_users() -> None:
    edit = {"clean": [{"id": "cl_one", "kind": "blur", "method": "", "enabled": True, "auto": True}]}
    clean.patch_layer(edit, "cl_one", "fill")
    assert edit["clean"][0]["kind"] == "fill"
    assert edit["clean"][0]["auto"] is False


def test_plan_summary_counts_fill_blur_and_off() -> None:
    edit = {"clean": [
        {"kind": "fill", "enabled": True, "quality": "steady"},
        {"kind": "blur", "enabled": True, "quality": "moving"},
        {"kind": "fill", "enabled": False, "quality": "moving"},
    ]}
    assert clean.plan_summary(edit) == {"fill": 1, "blur": 1, "off": 1, "moving": 2}


def test_top_display_type_reads_as_a_title() -> None:
    """A card near the top of the frame is a title, not a word-pop caption."""
    from duckcore.engine import detect

    tracklet = {
        "box": {"x": 0.227, "y": 0.321, "w": 0.535, "h": 0.063},
        "text_sample": "人吃啥咪吃啥",
        "confidence": 1.0,
        "samples": 1,
        "duration": 0.25,
        "track": [{"t": 0.0, "box": {"x": 0.227, "y": 0.321, "w": 0.535, "h": 0.063}}],
    }
    kind, rule = detect.classify(tracklet, 160.0)
    assert kind == "title"
    assert rule >= 0.7


def test_fill_hole_is_tighter_than_the_blur_hole() -> None:
    box = {"x": 0.30, "y": 0.48, "w": 0.40, "h": 0.04}
    fill = masks.layer_rect(
        {"box": box, "tracklet_id": "trk", "kind": "fill"}, 1080, 1920,
    )
    blur = masks.layer_rect(
        {"box": box, "tracklet_id": "trk", "kind": "blur"}, 1080, 1920,
    )
    fill_w, fill_h = fill[2] - fill[0], fill[3] - fill[1]
    blur_w, blur_h = blur[2] - blur[0], blur[3] - blur[1]
    assert fill_w < blur_w and fill_h < blur_h
    # The hole still covers the box and the smallest shadow margin.
    assert fill[0] < int(box["x"] * 1080)
    assert fill[1] <= int(box["y"] * 1920) - masks.TEXT_SHADOW_MIN_PX
    assert fill_h >= int(box["h"] * 1920) + 2 * masks.TEXT_SHADOW_MIN_PX
