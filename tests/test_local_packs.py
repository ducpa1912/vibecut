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
