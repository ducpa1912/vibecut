"""REQ-20261125-02: a thinner data folder with the same pixels and warm caches."""
from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np
import pytest

from duckcore.engine import textfill


@pytest.fixture(autouse=True)
def _roomy_disk(monkeypatch):
    """Saved fills skip writing below 10 GB free; this Mac's disk must not decide the test."""
    monkeypatch.setattr(textfill, "_free_disk", lambda path: 100 * 1024 ** 3)


class _Model:
    def __init__(self):
        self.calls = 0

    def fill(self, area, mask):
        self.calls += 1
        out = area.copy()
        out[mask] = (np.arange(mask.sum() * 3) % 251).reshape(-1, 3).astype(np.uint8)
        return out


def _box(seed: int = 0):
    rng = np.random.default_rng(seed)
    area = rng.integers(0, 255, (24, 40, 3), dtype=np.uint8)
    mask = np.zeros((24, 40), bool)
    mask[6:18, 8:30] = True
    return area, mask


def test_saved_fills_are_png_and_read_back_identical(tmp_path) -> None:
    model = _Model()
    first = textfill._SavedFills(model, tmp_path, "stamp")
    area, mask = _box()
    made = first.fill(area, mask)
    files = list(tmp_path.iterdir())
    assert [f.suffix for f in files] == [".png"]
    again = textfill._SavedFills(model, tmp_path, "stamp")
    assert np.array_equal(again.fill(area, mask), made)
    assert model.calls == 1 and again.hits == 1


def test_an_older_npy_fill_is_still_reused_and_touched(tmp_path) -> None:
    model = _Model()
    saved = textfill._SavedFills(model, tmp_path, "stamp")
    area, mask = _box(1)
    legacy = saved._path(area, mask).with_suffix(".npy")
    expected = model.fill(area, mask)
    np.save(legacy, expected, allow_pickle=False)
    old = time.time() - 10 * 24 * 3600
    os.utime(legacy, (old, old))
    calls = model.calls
    assert np.array_equal(saved.fill(area, mask), expected)
    assert model.calls == calls and saved.hits == 1
    assert legacy.stat().st_mtime > old + 1


def test_a_result_that_is_not_8_bit_pixels_is_not_saved(tmp_path) -> None:
    class Odd:
        def fill(self, area, mask):
            return area.astype(np.float32)

    saved = textfill._SavedFills(Odd(), tmp_path, "stamp")
    saved.fill(*_box())
    assert not [f for f in tmp_path.iterdir() if not f.name.endswith(".tmp")]


def _bundle(tmp_path: Path, payload: bytes = b"lama" * 1000) -> Path:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "big-lama.pt").write_bytes(payload)
    package = bundle / "lama_fill.mlpackage"
    (package / "Data").mkdir(parents=True)
    (package / "Manifest.json").write_text("{}")
    (package / "Data" / "weights.bin").write_bytes(b"w" * 64)
    return bundle


def test_an_identical_copy_becomes_a_link_and_keeps_its_stamp(tmp_path, monkeypatch) -> None:
    bundle = _bundle(tmp_path)
    data = tmp_path / "data"
    target = data / "models" / "fill"
    target.mkdir(parents=True)
    copy = target / "big-lama.pt"
    copy.write_bytes((bundle / "big-lama.pt").read_bytes())
    os.utime(copy, (1_700_000_000, 1_700_000_000))
    before = textfill._model_stamp(copy)
    monkeypatch.setenv("DUCK_FILL_MODELS", str(bundle))
    textfill.seed_models(data)
    assert copy.is_symlink() and Path(os.path.realpath(copy)) == (bundle / "big-lama.pt").resolve()
    assert textfill._model_stamp(copy) == before
    # A rebuild or app update moves the bundle's file time, not its content.
    os.utime(bundle / "big-lama.pt", (1_800_000_000, 1_800_000_000))
    assert textfill._model_stamp(copy) == before
    # New content is a new model: a new stamp.
    (bundle / "big-lama.pt").write_bytes(b"newer" * 1000)
    assert textfill._model_stamp(copy) != before


def test_a_same_size_file_with_other_content_is_left_alone(tmp_path, monkeypatch) -> None:
    bundle = _bundle(tmp_path)
    data = tmp_path / "data"
    target = data / "models" / "fill"
    target.mkdir(parents=True)
    mine = target / "big-lama.pt"
    mine.write_bytes(b"x" * (bundle / "big-lama.pt").stat().st_size)
    monkeypatch.setenv("DUCK_FILL_MODELS", str(bundle))
    textfill.seed_models(data)
    assert not mine.is_symlink() and mine.read_bytes().startswith(b"xxxx")


def test_a_fresh_data_folder_links_and_a_moved_app_is_followed(tmp_path, monkeypatch) -> None:
    bundle = _bundle(tmp_path)
    data = tmp_path / "data"
    monkeypatch.setenv("DUCK_FILL_MODELS", str(bundle))
    textfill.seed_models(data)
    model = data / "models" / "fill" / "big-lama.pt"
    package = data / "models" / "fill" / "lama_fill.mlpackage"
    assert model.is_symlink() and package.is_symlink()
    stamp = textfill.method_stamp("lama", data / "models" / "fill", "gpu")
    moved = tmp_path / "moved"
    os.replace(bundle, moved)
    monkeypatch.setenv("DUCK_FILL_MODELS", str(moved))
    textfill.seed_models(data)
    assert Path(os.path.realpath(model)) == (moved / "big-lama.pt").resolve()
    assert textfill.method_stamp("lama", data / "models" / "fill", "gpu") == stamp


def test_an_identical_core_ml_copy_becomes_a_link_and_keeps_its_stamp(tmp_path, monkeypatch) -> None:
    from duckcore.engine.textfill import coreml_fill

    bundle = _bundle(tmp_path)
    data = tmp_path / "data"
    target = data / "models" / "fill"
    target.mkdir(parents=True)
    import shutil

    shutil.copytree(bundle / "lama_fill.mlpackage", target / "lama_fill.mlpackage")
    before = coreml_fill.package_stamp(target / "lama_fill.mlpackage")
    monkeypatch.setenv("DUCK_FILL_MODELS", str(bundle))
    textfill.seed_models(data)
    package = target / "lama_fill.mlpackage"
    assert package.is_symlink() and (package / "Manifest.json").is_file()
    monkeypatch.setattr(textfill, "gpu_engine", lambda *a: "coreml")
    assert textfill.method_stamp("lama", target, "gpu") == f"{before}:coreml-gpu"


def test_clips_unused_for_two_weeks_are_pruned(tmp_path) -> None:
    fill = tmp_path / "projects" / "prj_x" / "fill"
    fill.mkdir(parents=True)
    old, fresh, part = fill / "old.mp4", fill / "fresh.mp4", fill / ".x.part.mp4"
    for path in (old, fresh, part):
        path.write_bytes(b"x" * 2048)
    stale = time.time() - textfill.SAVED_MAX_AGE - 3600
    os.utime(old, (stale, stale))
    os.utime(part, (stale, stale))
    assert textfill._prune_clips(tmp_path) == 1
    assert not old.exists() and fresh.exists() and part.exists()


def test_old_npy_fills_convert_to_identical_png_and_keep_their_age(tmp_path) -> None:
    saved = tmp_path / "projects" / "prj_x" / "fill" / "saved"
    saved.mkdir(parents=True)
    area, _mask = _box(3)
    np.save(saved / "a.npy", area, allow_pickle=False)
    np.save(saved / "odd.npy", area.astype(np.float32), allow_pickle=False)
    old = time.time() - 5 * 24 * 3600
    os.utime(saved / "a.npy", (old, old))
    result = textfill.convert_saved_fills(tmp_path)
    assert result["converted"] == 1 and result["kept"] == 1
    assert not (saved / "a.npy").exists() and (saved / "odd.npy").exists()
    from PIL import Image

    with Image.open(saved / "a.png") as image:
        assert np.array_equal(np.asarray(image), area)
    assert abs((saved / "a.png").stat().st_mtime - old) < 2
    # A converted fill is found by the reader under the same name.
    reader = textfill._SavedFills(_Model(), saved, "stamp")
    assert np.array_equal(reader._read(saved / "a.png", area.shape), area)


def test_conversion_waits_for_a_running_fill(tmp_path, monkeypatch) -> None:
    saved = tmp_path / "projects" / "prj_x" / "fill" / "saved"
    saved.mkdir(parents=True)
    np.save(saved / "a.npy", _box()[0], allow_pickle=False)
    monkeypatch.setattr(textfill, "busy", lambda: True)
    result = textfill.convert_saved_fills(tmp_path)
    assert result["stopped"] and (saved / "a.npy").exists()


def test_saved_fill_limits_cover_every_project(tmp_path) -> None:
    for name in ("prj_a", "prj_b"):
        (tmp_path / "projects" / name / "fill" / "saved").mkdir(parents=True)
    found = textfill._saved_folders(tmp_path)
    assert {p.parent.parent.name for p in found} == {"prj_a", "prj_b"}
