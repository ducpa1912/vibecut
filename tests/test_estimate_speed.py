"""The estimate is stored, joined and fast (loop 8, revision 2)."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from duckcore import inkcheck, render
from duckcore import ink as inkmod
from duckcore.engine import textfill


def _edit() -> dict:
    return {
        "id": "ed_speed", "updated": 1.0,
        "clean": [{
            "id": "cl_one", "kind": "fill", "enabled": True,
            "box": {"x": 0.1, "y": 0.1, "w": 0.4, "h": 0.1},
            "ranges": [{"start": 0.0, "end": 1.0}],
        }],
    }


def _ink() -> list:
    mask = np.zeros((10, 10), dtype=bool)
    mask[2:5, 3:6] = True
    return [inkmod.Ink(mask=mask, rect=(0, 0, 11, 11), first=0, last=29, fps=30.0)]


def test_the_ink_store_is_read_the_second_time(tmp_path, monkeypatch) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x" * 16)
    meta = {"width": 100, "height": 100, "fps": 30.0}
    calls = {"n": 0}

    def fake_layer_inks(layer, meta, *, source, size=None):
        calls["n"] += 1
        return _ink(), ""

    monkeypatch.setattr(inkcheck, "layer_inks", fake_layer_inks)
    first = inkcheck.build_inks(_edit(), meta, source=source, data_root=tmp_path)
    second = inkcheck.build_inks(_edit(), meta, source=source, data_root=tmp_path)
    assert calls["n"] == 1, "the second call must read the store, not the frames"
    assert second["cl_one"]["inks"][0].mask.sum() == first["cl_one"]["inks"][0].mask.sum()
    assert second["cl_one"]["inks"][0].rect == (0, 0, 11, 11)
    assert second["cl_one"]["inks"][0].first == 0
    assert second["cl_one"]["inks"][0].last == 29

    # A changed layer rebuilds only itself.
    changed = _edit()
    changed["clean"][0]["ranges"] = [{"start": 0.5, "end": 1.0}]
    inkcheck.build_inks(changed, meta, source=source, data_root=tmp_path)
    assert calls["n"] == 2


def test_stored_units_never_decode(tmp_path, monkeypatch) -> None:
    def no_decode(*_args, **_kwargs):
        raise AssertionError("a stored span must not decode")

    monkeypatch.setattr(textfill, "dry_units", no_decode)
    row = textfill.estimate_span(
        meta={"width": 100, "height": 100, "fps": 30.0},
        start=0.0, duration=1.0, layers=_edit()["clean"], method="lama",
        cache_dir=tmp_path, data_root=tmp_path, strokes={}, units_override=12.5,
    )
    assert row["units"] == 12.5


def test_a_second_request_joins_the_one_worker(tmp_path, monkeypatch) -> None:
    calls = {"n": 0}

    def slow_estimate(edit, meta, data_root, progress=None):
        calls["n"] += 1
        if progress:
            progress(0.5, "half")
        time.sleep(0.4)
        return {"total_seconds": 100.0, "states": "ready"}

    monkeypatch.setattr(render, "estimate_edit", slow_estimate)
    meta = {"width": 100, "height": 100, "fps": 30.0, "path": str(tmp_path / "s.mp4")}
    first = render.estimate_status(_edit(), meta, tmp_path, wait=0.0)
    second = render.estimate_status(_edit(), meta, tmp_path, wait=0.0)
    assert first["state"] == "working" and second["state"] == "working"
    got = render.wait_for_estimate(_edit(), meta, tmp_path, timeout=5.0)
    assert got["total_seconds"] == 100.0
    assert calls["n"] == 1, "a second request must join the running estimate"
    warm = render.estimate_status(_edit(), meta, tmp_path, wait=0.1)
    assert warm["state"] == "ready"
