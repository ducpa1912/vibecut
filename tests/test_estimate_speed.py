"""The estimate is stored, joined and fast (loop 8, revision 2)."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest

from duckcore import inkcheck, render
from duckcore import ink as inkmod
from duckcore.engine import textfill


@pytest.fixture(autouse=True)
def _fresh_jobs():
    """Each test starts with no estimate jobs from the one before it."""
    with render._ESTIMATE_LOCK:
        render._ESTIMATE_JOBS.clear()
        render._ESTIMATE_QUEUE.clear()
        render._ESTIMATE_LAST.clear()
    yield
    with render._ESTIMATE_LOCK:
        render._ESTIMATE_JOBS.clear()
        render._ESTIMATE_QUEUE.clear()
        render._ESTIMATE_LAST.clear()


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


def test_the_store_keeps_every_letter_of_an_ink(tmp_path, monkeypatch) -> None:
    """Fault A: a stored line must have the same letters, pieces and key."""
    import dataclasses

    from duckcore import render
    from duckcore.engine.textfill import mask as masks

    source = tmp_path / "source.mp4"
    source.write_bytes(b"x" * 16)
    meta = {"width": 100, "height": 100, "fps": 30.0}
    letter = np.zeros((30, 40), dtype=bool)
    letter[5:25, 2:10] = True
    letter[5:25, 20:30] = True
    ink = inkmod.Ink(
        mask=letter, rect=(0, 0, 41, 31), first=3, last=50, fps=30.0,
        settled=False, glyphs=((2, 10), (20, 30)), spans=((3, 20), (15, 50)),
    )

    def fake_layer_inks(layer, meta, *, source, size=None):
        return [ink], ""

    monkeypatch.setattr(inkcheck, "layer_inks", fake_layer_inks)
    inkcheck.build_inks(_edit(), meta, source=source, data_root=tmp_path)
    stored = inkcheck.build_inks(_edit(), meta, source=source, data_root=tmp_path)["cl_one"]["inks"][0]

    for item in dataclasses.fields(inkmod.Ink):
        before, after = getattr(ink, item.name), getattr(stored, item.name)
        if isinstance(before, np.ndarray):
            assert np.array_equal(before, after), item.name
        else:
            assert before == after, item.name
    assert stored.reach == ink.reach
    before_pieces = ink.pieces()
    after_pieces = stored.pieces()
    assert [(a, b) for a, b, _hole in before_pieces] == [(a, b) for a, b, _hole in after_pieces]
    assert all(np.array_equal(x[2], y[2]) for x, y in zip(before_pieces, after_pieces))

    def key_of(inks):
        out, _strokes = render._inked_layers(
            [{"id": "cl_one", "kind": "fill", "enabled": True,
              "box": {"x": 0.1, "y": 0.1, "w": 0.4, "h": 0.1},
              "ranges": [{"start": 0.0, "end": 1.0}]}],
            {"cl_one": {"inks": inks}}, meta,
        )
        return out[0].get("ink_key")

    assert key_of([ink]) == key_of([stored])


def test_a_new_ink_field_must_be_stored() -> None:
    import dataclasses

    fields = {item.name for item in dataclasses.fields(inkmod.Ink)}
    assert set(inkcheck.STORE_FIELDS) == fields


def test_a_working_job_is_never_trimmed(tmp_path, monkeypatch) -> None:
    """Fault B: the worker's job must survive the map being trimmed."""
    calls = {"n": 0}

    def slow_estimate(edit, meta, data_root, progress=None):
        calls["n"] += 1
        time.sleep(0.5)
        return {"total_seconds": 1.0}

    monkeypatch.setattr(render, "estimate_edit", slow_estimate)
    meta = {"width": 100, "height": 100, "fps": 30.0, "path": str(tmp_path / "s.mp4")}
    for index in range(20):
        edit = _edit()
        edit["id"] = f"ed_{index}"
        render.estimate_status(edit, meta, tmp_path, wait=0.0)
    with render._ESTIMATE_LOCK:
        working = [job for job in render._ESTIMATE_JOBS.values() if job["state"] == "working"]
    assert working, "a working job was trimmed away"
    assert len(render._ESTIMATE_JOBS) <= 20


def test_the_worker_survives_a_bad_job(tmp_path, monkeypatch) -> None:
    """Fault B: one failure must not kill the thread or hang the wait."""
    calls = {"n": 0}

    def flaky(edit, meta, data_root, progress=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return {"total_seconds": 2.0}

    monkeypatch.setattr(render, "estimate_edit", flaky)
    meta = {"width": 100, "height": 100, "fps": 30.0, "path": str(tmp_path / "s.mp4")}
    render.estimate_status(_edit(), meta, tmp_path, wait=0.0)
    first = render.wait_for_estimate(_edit(), meta, tmp_path, timeout=5.0)
    assert first == {}
    edit2 = _edit()
    edit2["id"] = "ed_after"
    render.estimate_status(edit2, meta, tmp_path, wait=0.0)
    second = render.wait_for_estimate(edit2, meta, tmp_path, timeout=5.0)
    assert second["total_seconds"] == 2.0


def test_a_fill_model_changes_the_estimate_key(tmp_path) -> None:
    """Fault C: the answer depends on the engine, so the key does too."""
    torch = pytest.importorskip("torch")
    from duckcore import app_settings

    class Stub(torch.nn.Module):
        def forward(self, image: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
            return image * 0.0 + 0.5

    meta = {"width": 100, "height": 100, "fps": 30.0, "path": str(tmp_path / "s.mp4")}
    before = render._estimate_key(_edit(), meta, tmp_path)
    folder = tmp_path / "mine"
    folder.mkdir()
    torch.jit.save(torch.jit.script(Stub()), str(folder / "model.pt"))
    app_settings.update(tmp_path, {"fill_model_path": str(folder)})
    after = render._estimate_key(_edit(), meta, tmp_path)
    assert after != before
