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
