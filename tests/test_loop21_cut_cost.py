from __future__ import annotations

from pathlib import Path
from dataclasses import fields

import numpy as np
import pytest

from duckcore import inkcheck
from duckcore import ink as inkmod
from duckcore import render


def _fill(layer_id: str, x: float, y: float, w: float, h: float) -> dict:
    return {
        "id": layer_id, "kind": "fill", "enabled": True,
        "box": {"x": x, "y": y, "w": w, "h": h},
        "ranges": [{"start": 0.0, "end": 2.0}],
    }


def test_check_passes_data_root_to_the_ink_store(monkeypatch, tmp_path: Path) -> None:
    seen: dict = {}

    def fake_build(edit, meta, *, source, size=None, data_root=None, progress=None):
        seen["data_root"] = data_root
        return {}

    monkeypatch.setattr(inkcheck, "build_inks", fake_build)
    edit = {"clean": []}
    report = inkcheck.check(
        tmp_path / "out.mp4", edit, {"width": 1920, "height": 1080, "fps": 30},
        source=tmp_path / "source.mp4", fps=30, data_root=tmp_path,
    )
    assert report["frames"] == 0
    assert seen["data_root"] == tmp_path


def test_a_view_ink_is_stored_and_the_second_build_reads_no_frames(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    ink = inkmod.Ink(
        mask=np.eye(8, dtype=bool), rect=(0, 0, 10, 10),
        first=0, last=10, fps=29.97, settled=True,
        glyphs=((0, 4), (5, 8)), spans=((0, 10), (2, 8)),
    )
    calls = {"n": 0}

    def fake_layer_inks(layer, meta, *, source, size=None):
        calls["n"] += 1
        return [ink], ""

    monkeypatch.setattr(inkcheck, "layer_inks", fake_layer_inks)
    view = inkmod.View(chain="scale=10:10", width=10, height=10)
    edit = {"clean": [_fill("cl", 0.1, 0.1, 0.2, 0.2)]}
    meta = {"width": 1920, "height": 1080, "fps": 30}
    first = inkcheck.build_inks(edit, meta, source=source, size=view, data_root=tmp_path)
    second = inkcheck.build_inks(edit, meta, source=source, size=view, data_root=tmp_path)
    assert calls["n"] == 1
    built = second["cl"]["inks"][0]
    assert built.rect == ink.rect
    assert built.first == ink.first and built.last == ink.last
    assert built.glyphs == ink.glyphs and built.spans == ink.spans
    assert built.settled is True
    assert first["cl"]["inks"][0].mask.shape == built.mask.shape
    for field in fields(ink):
        np.testing.assert_equal(getattr(built, field.name), getattr(ink, field.name))
    crop = render.check_view(meta, {"cut": {"crop": {"x": 0.5, "y": 0, "w": 0.5, "h": 1}}})
    grade = render.check_view(meta, {"cut": {"grade": {"exposure": 20}}})
    assert inkcheck._store_key(edit["clean"][0], meta, source, crop) != inkcheck._store_key(
        edit["clean"][0], meta, source, grade,
    )
    graded_crop = render.check_view(meta, {"cut": {
        "crop": {"x": 0.5, "y": 0, "w": 0.5, "h": 1},
        "grade": {"exposure": 20},
    }})
    assert (crop.width, crop.height) == (graded_crop.width, graded_crop.height)
    assert inkcheck._store_key(edit["clean"][0], meta, source, crop) != inkcheck._store_key(
        edit["clean"][0], meta, source, graded_crop,
    )


def test_a_crop_removes_only_the_outside_fill_and_keeps_a_partial_line() -> None:
    meta = {"width": 1920, "height": 1080, "fps": 30}
    edit = {
        "cut": {"crop": {"x": 0.5, "y": 0.0, "w": 0.5, "h": 1.0}},
        "clean": [
            _fill("outside", 0.0, 0.4, 0.2, 0.1),
            _fill("inside", 0.6, 0.4, 0.2, 0.1),
            _fill("partial", 0.45, 0.4, 0.1, 0.1),
        ],
    }
    kept = {layer["id"] for layer in render._fill_layers_in_view(edit, meta)}
    assert kept == {"inside", "partial"}


def test_fill_to_9x16_drops_a_line_at_the_far_left_but_fit_keeps_it() -> None:
    meta = {"width": 1920, "height": 1080, "fps": 30}
    layers = [
        _fill("far_left", 0.0, 0.4, 0.03, 0.1),
        _fill("middle", 0.48, 0.4, 0.04, 0.1),
    ]
    fill = {"cut": {"aspect": "9:16", "fit": "fill"}, "clean": layers}
    assert {layer["id"] for layer in render._fill_layers_in_view(fill, meta)} == {"middle"}
    fit = {"cut": {"aspect": "9:16", "fit": "fit"}, "clean": layers}
    assert {layer["id"] for layer in render._fill_layers_in_view(fit, meta)} == {"far_left", "middle"}


def test_no_cut_keeps_every_fill_layer() -> None:
    meta = {"width": 1920, "height": 1080, "fps": 30}
    edit = {"clean": [_fill("a", 0.0, 0.0, 0.1, 0.1)]}
    assert [layer["id"] for layer in render._fill_layers_in_view(edit, meta)] == ["a"]


def test_a_second_check_with_a_view_reads_no_ink_frame(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    ink = inkmod.Ink(
        mask=np.ones((8, 8), dtype=bool), rect=(0, 0, 10, 10),
        first=0, last=10, fps=30.0, settled=True,
        glyphs=((0, 4),), spans=((0, 10),),
    )
    calls = {"n": 0}

    def fake_layer_inks(layer, meta, *, source, size=None):
        calls["n"] += 1
        return [ink], ""

    def fake_judge(layer, built, output, source, spans, *, fps, size):
        return {"frames": 1, "hits": [], "flicker": [], "problem": ""}

    monkeypatch.setattr(inkcheck, "layer_inks", fake_layer_inks)
    monkeypatch.setattr(inkcheck, "_judge", fake_judge)
    view = inkmod.View(chain="scale=10:10", width=10, height=10)
    edit = {"clean": [_fill("cl", 0.1, 0.1, 0.2, 0.2)]}
    meta = {"width": 1920, "height": 1080, "fps": 30}
    first = render._check_output(
        tmp_path / "out.mp4", edit, meta, source=source, fps=30,
        size=view, data_root=tmp_path, inks={},
    )
    second = render._check_output(
        tmp_path / "out.mp4", edit, meta, source=source, fps=30,
        size=view, data_root=tmp_path, inks={},
    )
    assert calls["n"] == 1
    assert first["frames"] == second["frames"] == 1
    first.pop("seconds")
    second.pop("seconds")
    assert first == second


@pytest.mark.parametrize("cut,expected", [
    ({"crop": {"x": 0.5, "y": 0, "w": 0.5, "h": 1}}, {"inside", "partial"}),
    ({"aspect": "9:16", "fit": "fill"}, {"inside", "partial"}),
    ({"aspect": "9:16", "fit": "fit"}, {"outside", "inside", "partial"}),
])
def test_render_and_estimate_use_the_same_visible_fill_plan(monkeypatch, tmp_path, cut, expected):
    from duckcore.engine import pipeline, textfill

    meta = {"width": 1920, "height": 1080, "fps": 30, "path": "source.mp4"}
    edit = {
        "id": "test", "project_id": "project", "cut": cut,
        "clips": [{"start": 0, "end": 2}],
        "clean": [_fill("outside", 0, 0.4, 0.03, 0.1),
                  _fill("inside", 0.55, 0.4, 0.03, 0.1),
                  _fill("partial", 0.45, 0.4, 0.1, 0.1)],
    }
    plans = []
    monkeypatch.setattr(pipeline, "probe", lambda source: meta)
    monkeypatch.setattr(inkcheck, "build_inks", lambda *args, **kwargs: {})
    monkeypatch.setattr(render, "_inked_layers", lambda layers, inks, meta: (layers, {}))

    class PlanCaptured(Exception):
        pass

    def capture(**kwargs):
        plans.append({layer["id"] for layer in kwargs["layers"]})
        raise PlanCaptured

    monkeypatch.setattr(textfill, "prepare_span", capture)
    monkeypatch.setattr(textfill, "estimate_span", capture)
    with pytest.raises(PlanCaptured):
        render.render_edit({"id": "project", "source_path": "source.mp4"}, edit, tmp_path)
    with pytest.raises(PlanCaptured):
        render.estimate_edit(edit, meta, tmp_path)
    assert plans == [expected, expected]


def test_changed_layer_set_changes_fill_cache_key():
    from duckcore.engine import textfill

    inside = _fill("inside", 0.6, 0.4, 0.2, 0.1)
    outside = _fill("outside", 0, 0.4, 0.1, 0.1)
    args = {"meta": {"width": 1920, "height": 1080, "fps": 30},
            "start": 0, "duration": 2, "method": "lama", "model_stamp": "test:gpu"}
    assert textfill.span_key(layers=[inside, outside], **args) != textfill.span_key(layers=[inside], **args)
