"""Voice library backup: export, restore, refusals, and no duplicates on a second restore.

Samples are short placeholder bytes, not media; nothing decodes them.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

import settings_store
import voice_clone


@pytest.fixture
def api(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(settings_store, "DATA", tmp_path)
    return TestClient(app.app)


def _clone(tmp_path, name, fill):
    sample = tmp_path / f"{name}.mp3"
    sample.write_bytes(b"ID3" + fill * 4000)
    return voice_clone.create_clone(sample, name=name, source="me", consent=True, language="vi", seconds=30)


def _restore(api, raw, consent=True):
    return api.post(
        "/api/voices/library/import",
        files={"file": ("library.zip", raw, "application/zip")},
        data={"consent": "true" if consent else "false"},
    )


def test_export_then_restore_into_an_empty_library(api, tmp_path):
    first = _clone(tmp_path, "Andy-VN", b"\x01")
    _clone(tmp_path, "Andy-EN", b"\x02")
    exported = api.get("/api/voices/library/export")
    assert exported.status_code == 200 and exported.headers["content-type"] == "application/zip"
    archive = zipfile.ZipFile(io.BytesIO(exported.content))
    manifest = json.loads(archive.read("manifest.json"))
    assert manifest["version"] == 1 and len(manifest["voices"]) == 2
    raw = exported.content

    for row in voice_clone.list_clones():
        voice_clone.delete_clone(row["voice_id"])
    restored = _restore(api, raw)
    assert restored.json() == {"imported": 2, "skipped": 0, "already": 0}
    names = sorted(row["name"] for row in voice_clone.list_clones())
    assert names == ["Andy-EN", "Andy-VN"]
    back = next(row for row in voice_clone.list_clones() if row["name"] == "Andy-VN")
    assert voice_clone.sample_path(back["voice_id"]).read_bytes() == b"ID3" + b"\x01" * 4000
    assert back["voice_id"] != first["voice_id"]


def test_a_second_restore_adds_nothing(api, tmp_path):
    _clone(tmp_path, "Andy-VN", b"\x01")
    raw = api.get("/api/voices/library/export").content
    again = _restore(api, raw)
    assert again.json() == {"imported": 0, "skipped": 0, "already": 1}
    assert len(voice_clone.list_clones()) == 1


def test_restore_refusals(api, tmp_path):
    _clone(tmp_path, "Andy-VN", b"\x01")
    raw = api.get("/api/voices/library/export").content
    assert _restore(api, raw, consent=False).status_code == 400
    assert _restore(api, b"not a zip").status_code == 400

    unsafe = io.BytesIO()
    with zipfile.ZipFile(unsafe, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"version": 1, "voices": []}))
        archive.writestr("../evil.mp3", b"x")
    assert _restore(api, unsafe.getvalue()).status_code == 400

    future = io.BytesIO()
    with zipfile.ZipFile(future, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"version": 9, "voices": []}))
    assert "another version" in _restore(api, future.getvalue()).json()["detail"]


def test_restore_is_same_origin_only(api):
    response = api.post(
        "/api/voices/library/import",
        files={"file": ("library.zip", b"PK", "application/zip")},
        data={"consent": "true"},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403
