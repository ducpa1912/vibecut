"""Local model pack resolution."""

from __future__ import annotations

from pathlib import Path

from duckcore import packs


def test_pack_requires_primary_and_extra_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(packs, "PACKS", (
        {
            "id": "test-pack",
            "name": "Test",
            "purpose": "test",
            "detail": "",
            "size_bytes": 4,
            "license": "test",
            "filename": "model.bin",
            "url": "https://example.invalid/model.bin",
            "extra_files": [{
                "filename": "config.json",
                "size_bytes": 2,
                "url": "https://example.invalid/config.json",
            }],
        },
    ))
    folder = tmp_path / "models" / "packs" / "test-pack"
    folder.mkdir(parents=True)
    (folder / "model.bin").write_bytes(b"1234")
    assert packs.installed_path(tmp_path, "test-pack") is None

    (folder / "config.json").write_bytes(b"{}")
    assert packs.installed_path(tmp_path, "test-pack") == folder

    assert packs.status(tmp_path)[0]["installed"] is True
    assert packs.status(tmp_path)[0]["size_bytes"] == 6


def test_cpu_fill_pack_installs_into_the_model_folder(tmp_path: Path) -> None:
    pack = next(item for item in packs.PACKS if item["id"] == "fill-lama-cpu")
    assert pack["dest"] == "fill"
    assert pack["sha256"] == "1faef5301d78db7dda502fe59966957ec4b79dd64e16f03ed96913c7a4eb68d6"
    folder = tmp_path / "models" / "fill"
    folder.mkdir(parents=True)
    assert packs.installed_path(tmp_path, "fill-lama-cpu") is None
    with (folder / "lama_fp32.onnx").open("wb") as handle:
        handle.truncate(pack["size_bytes"])  # sparse, size is what the check reads
    assert packs.installed_path(tmp_path, "fill-lama-cpu") == folder


def test_removing_the_cpu_pack_keeps_other_files(tmp_path: Path) -> None:
    folder = tmp_path / "models" / "fill"
    folder.mkdir(parents=True)
    (folder / "lama_fp32.onnx").write_bytes(b"x")
    (folder / "keep.txt").write_bytes(b"x")
    packs.remove(tmp_path, "fill-lama-cpu")
    assert not (folder / "lama_fp32.onnx").exists()
    assert (folder / "keep.txt").exists()
