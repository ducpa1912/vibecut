from __future__ import annotations

import threading

from duckcore import render
from duckcore.engine import textfill
from duckcore.main import _active_clean
from duckcore.render import _picture_plan

META = {"width": 1920, "height": 1080, "fps": 30}


def test_crop_offsets_at_zero_stay_at_zero() -> None:
    plan = _picture_plan(META, {"cut": {"crop": {"x": 0.0, "y": 0.0, "w": 0.5, "h": 0.5}}})
    assert plan["parts"][0] == "crop=960:540:0:0"
    plan = _picture_plan(META, {"cut": {"crop": {"x": 0.25, "y": 0.5, "w": 0.5, "h": 0.25}}})
    assert plan["parts"][0] == "crop=960:270:480:540"


def test_units_key_separates_geometry_source_and_method() -> None:
    one = [{"id": "x", "kind": "fill", "box": {"x": 0, "y": 0, "w": 0.1, "h": 0.1}, "ranges": [{"start": 0, "end": 2}]}]
    two = [{"id": "x", "kind": "fill", "box": {"x": 0.5, "y": 0.5, "w": 0.4, "h": 0.4}, "ranges": [{"start": 0, "end": 2}]}]
    base = textfill.units_key(META, one, 0, 2, method="lama", device="gpu", source_key="1:2")
    assert base != textfill.units_key(META, two, 0, 2, method="lama", device="gpu", source_key="1:2")
    assert base != textfill.units_key(META, one, 0, 2, method="lama", device="cpu", source_key="1:2")
    assert base != textfill.units_key(META, one, 0, 2, method="lama", device="gpu", source_key="3:4")
    assert base == textfill.units_key(META, one, 0, 2, method="lama", device="gpu", source_key="1:2")


def test_active_clean_includes_layers_without_ranges() -> None:
    edit = {"clean": [
        {"id": "always", "kind": "blur", "box": {"x": 0, "y": 0, "w": 0.2, "h": 0.2}},
        {"id": "later", "kind": "fill", "ranges": [{"start": 5, "end": 6}]},
    ]}
    assert [layer["id"] for layer in _active_clean(edit, 1.0)] == ["always"]


def test_enqueue_creates_one_job_under_concurrent_calls(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(render.RenderQueue, "_loop", lambda self: None)
    queue = render.RenderQueue(tmp_path)
    results: list[dict] = []
    threads = [
        threading.Thread(target=lambda: results.append(queue.enqueue("prj", "ed", "Render")))
        for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(results) == 8
    assert len({row["id"] for row in results}) == 1


def test_proof_key_changes_when_the_source_changes(tmp_path) -> None:
    from pathlib import Path

    from duckcore.main import _proof_cache_key

    source = tmp_path / "source.mp4"
    source.write_bytes(b"one")
    project = {"source_path": str(source)}
    edit = {"cut": {"aspect": "source"}}
    first = _proof_cache_key(project, edit, [], {"start": 0, "end": 2}, "blur")
    source.write_bytes(b"two")
    second = _proof_cache_key(project, edit, [], {"start": 0, "end": 2}, "blur")
    assert first != second
