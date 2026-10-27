"""Pack manifest, SHA-256 verification, install and remove contracts."""

from __future__ import annotations

import io
import json
import tarfile
import zipfile

import pytest

import packs


def _zip(path, files):
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return path


def _manifest(archive, pack_id="speech", **overrides):
    item = {
        "id": pack_id,
        "name": "Speech Pack" if pack_id == "speech" else pack_id.title(),
        "version": "1.0.0",
        "size_bytes": archive.stat().st_size,
        "sha256": packs.sha256_file(archive),
        "url": "",
        "contents": ["test"],
    }
    item.update(overrides)
    return {"schema": 1, "packs": [item]}


def test_builtin_manifest_lists_the_three_optional_packs():
    data = packs.manifest()
    assert data["schema"] == 1
    ids = [item["id"] for item in data["packs"]]
    assert ids == ["speech", "voice", "separation"]
    assert all(item["size_bytes"] > 0 for item in data["packs"])
    assert all(item["name"] for item in data["packs"])


def test_manifest_rejects_duplicates_and_bad_ids(tmp_path):
    path = tmp_path / "packs.json"
    path.write_text(json.dumps({
        "schema": 1,
        "packs": [
            {"id": "voice", "name": "Voice", "version": "1"},
            {"id": "voice", "name": "Voice again", "version": "1"},
        ],
    }), encoding="utf-8")
    with pytest.raises(packs.PackError, match="Duplicate"):
        packs.manifest(path)
    with pytest.raises(packs.PackError, match="Invalid pack id"):
        packs.manifest({"schema": 1, "packs": [{"id": "../evil", "name": "x", "version": "1"}]})


def test_sha256_verify_accepts_and_rejects(tmp_path):
    archive = _zip(tmp_path / "pack.zip", {"model.bin": b"weights"})
    digest = packs.sha256_file(archive)
    assert packs.verify_sha256(archive, digest) == digest
    with pytest.raises(packs.PackError, match="checksum mismatch"):
        packs.verify_sha256(archive, "0" * 64)
    with pytest.raises(packs.PackError, match="SHA-256"):
        packs.verify_sha256(archive, "")


def test_install_and_remove_pack_under_a_root(tmp_path):
    archive = _zip(tmp_path / "speech.zip", {
        "model.bin": b"weights",
        "runtime/bin/tool": b"binary",
    })
    root = tmp_path / "packs-root"
    result = packs.install_pack(
        "speech", archive=archive, manifest_data=_manifest(archive), root=root,
    )

    assert result["installed"] is True
    directory = root / "speech"
    assert (directory / "model.bin").read_bytes() == b"weights"
    assert (directory / "runtime" / "bin" / "tool").is_file()
    meta = json.loads((directory / packs.INSTALL_META).read_text())
    assert meta["sha256"] == packs.sha256_file(archive)

    listed = packs.list_packs(manifest_data=_manifest(archive), root=root)
    assert listed[0]["installed"] is True
    assert listed[0]["installed_version"] == "1.0.0"
    assert listed[0]["installed_size"] > 0

    removed = packs.remove_pack("speech", manifest_data=_manifest(archive), root=root)
    assert removed["removed"] is True
    assert not directory.exists()
    again = packs.remove_pack("speech", manifest_data=_manifest(archive), root=root)
    assert again["removed"] is False


def test_bad_checksum_leaves_previous_install_untouched(tmp_path):
    root = tmp_path / "packs-root"
    good = _zip(tmp_path / "good.zip", {"model.bin": b"v1"})
    packs.install_pack("voice", archive=good, manifest_data=_manifest(good, "voice"), root=root)

    bad = _zip(tmp_path / "bad.zip", {"model.bin": b"v2"})
    with pytest.raises(packs.PackError, match="checksum mismatch"):
        packs.install_pack(
            "voice", archive=bad,
            manifest_data=_manifest(bad, "voice", sha256="0" * 64), root=root,
        )

    assert (root / "voice" / "model.bin").read_bytes() == b"v1"


def test_archive_path_traversal_is_refused(tmp_path):
    root = tmp_path / "packs-root"
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../escape.txt", b"no")
    with pytest.raises(packs.PackError, match="Unsafe path"):
        packs.install_pack(
            "separation", archive=archive, manifest_data=_manifest(archive, "separation"),
            root=root,
        )
    assert not (tmp_path / "escape.txt").exists()
    assert not (root / "separation").exists()


def test_tar_install_works_and_symlinks_are_refused(tmp_path):
    root = tmp_path / "packs-root"
    archive = tmp_path / "pack.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        data = b"weights"
        info = tarfile.TarInfo("model.bin")
        info.size = len(data)
        handle.addfile(info, io.BytesIO(data))
    result = packs.install_pack(
        "speech", archive=archive, manifest_data=_manifest(archive), root=root,
    )
    assert result["installed"] is True
    assert (root / "speech" / "model.bin").read_bytes() == b"weights"

    linked = tmp_path / "linked.tar"
    with tarfile.open(linked, "w") as handle:
        info = tarfile.TarInfo("link")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        handle.addfile(info)
    with pytest.raises(packs.PackError, match="link or device"):
        packs.install_pack(
            "voice", archive=linked,
            manifest_data=_manifest(linked, "voice"), root=root,
        )


def test_install_collapses_a_single_top_level_directory(tmp_path):
    archive = _zip(tmp_path / "pack.zip", {
        "kokoro/model.onnx": b"weights",
        "kokoro/voices.bin": b"voices",
    })
    root = tmp_path / "packs-root"
    packs.install_pack(
        "voice", archive=archive, manifest_data=_manifest(archive, "voice"), root=root,
    )
    assert (root / "voice" / "model.onnx").is_file()
    assert not (root / "voice" / "kokoro" / "model.onnx").exists()


def test_pack_root_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv(packs.ROOT_ENV, str(tmp_path / "from-env"))
    assert packs.packs_root() == (tmp_path / "from-env").resolve()
    monkeypatch.delenv(packs.ROOT_ENV)
    assert packs.packs_root(tmp_path / "explicit") == (tmp_path / "explicit").resolve()


def test_unknown_pack_is_rejected(tmp_path):
    with pytest.raises(packs.PackError, match="Unknown pack"):
        packs.status("nope", manifest_data=packs.manifest(), root=tmp_path)
