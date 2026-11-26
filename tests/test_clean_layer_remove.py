"""Remove a Clean layer for good, and keep it gone after a re-plan.

REQ-20261118-01, REQ-20261125-03 (P-E). The layer leaves the edit; turning it
Off is a different action and stays in the list.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from duckcore import clean, edits
from duckcore.main import create_app

HEADERS = {"Authorization": "Bearer test-token"}


def _layer(layer_id: str, **extra) -> dict:
    return {
        "id": layer_id,
        "kind": "fill",
        "method": "lama",
        "enabled": True,
        "auto": False,
        "box": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.1},
        "ranges": [{"start": 1.0, "end": 2.0}],
        "fill_keys": 3.0,
        **extra,
    }


def _project(tmp_path: Path, layers: list[dict]) -> dict:
    project = tmp_path / "projects" / "prj_remove"
    (project / "edits").mkdir(parents=True)
    edit = {
        "id": "ed_remove",
        "project_id": "prj_remove",
        "start": 0.0,
        "end": 10.0,
        "clips": [],
        "clean": layers,
        "source": {"duration": 10.0, "width": 1920, "height": 1080, "fps": 24.0},
    }
    (project / "edits" / "ed_remove.json").write_text(json.dumps(edit), encoding="utf-8")
    return edit


def _route(layer_id: str) -> str:
    return f"/api/projects/prj_remove/edits/ed_remove/clean/{layer_id}"


def _ids(edit: dict) -> list[str]:
    return [str(layer.get("id")) for layer in edit.get("clean") or []]


def test_remove_layer_deletes_it_and_keeps_the_other_layer_intact(tmp_path: Path) -> None:
    _project(tmp_path, [_layer("cl_go"), _layer("cl_keep", fill_keys=7.5)])
    app = create_app("test-token", tmp_path)
    with TestClient(app) as client:
        response = client.delete(_route("cl_go"), headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["removed"] == "cl_go"

    saved = edits.get_edit(tmp_path, "prj_remove", "ed_remove")
    assert _ids(saved) == ["cl_keep"]
    keep = saved["clean"][0]
    assert keep["ranges"] == [{"start": 1.0, "end": 2.0}]
    assert keep["fill_keys"] == 7.5
    assert saved["removed_clean"] == ["cl_go"]


def test_remove_unknown_layer_is_404_and_leaves_the_edit_alone(tmp_path: Path) -> None:
    _project(tmp_path, [_layer("cl_go"), _layer("cl_keep")])
    app = create_app("test-token", tmp_path)
    with TestClient(app) as client:
        response = client.delete(_route("cl_nope"), headers=HEADERS)
    assert response.status_code == 404

    saved = edits.get_edit(tmp_path, "prj_remove", "ed_remove")
    assert _ids(saved) == ["cl_go", "cl_keep"]
    assert "removed_clean" not in saved


def test_a_manual_layer_can_be_removed(tmp_path: Path) -> None:
    _project(tmp_path, [
        _layer("cl_manual_abc", auto=True, tracklet_id="", kind="blur", method=""),
        _layer("cl_keep"),
    ])
    app = create_app("test-token", tmp_path)
    with TestClient(app) as client:
        response = client.delete(_route("cl_manual_abc"), headers=HEADERS)
    assert response.status_code == 200, response.text
    assert _ids(edits.get_edit(tmp_path, "prj_remove", "ed_remove")) == ["cl_keep"]


def test_a_removed_detected_layer_does_not_come_back_on_a_clean_replan(tmp_path: Path) -> None:
    go_id = clean._layer_id({"id": "trk_go"})
    keep_id = clean._layer_id({"id": "trk_keep"})
    _project(tmp_path, [_layer(go_id), _layer(keep_id)])
    check = {
        "scenes": [{"id": 0, "start": 0.0, "end": 10.0}],
        "meta": {"duration": 10.0},
        "report": {
            "tracklets": [
                {
                    "id": "trk_go",
                    "kind": "title",
                    "box": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.1},
                    "ranges": [{"start": 1.0, "end": 2.0}],
                    "text_sample": "wrong box",
                },
                {
                    "id": "trk_keep",
                    "kind": "title",
                    "box": {"x": 0.4, "y": 0.6, "w": 0.2, "h": 0.1},
                    "ranges": [{"start": 3.0, "end": 4.0}],
                    "text_sample": "keep me",
                },
            ]
        },
    }
    (tmp_path / "projects" / "prj_remove" / "check.json").write_text(
        json.dumps(check), encoding="utf-8"
    )
    app = create_app("test-token", tmp_path)
    with TestClient(app) as client:
        assert client.delete(_route(go_id), headers=HEADERS).status_code == 200
        rebuilt = client.post(
            "/api/projects/prj_remove/edits/ed_remove/clean/from-check",
            headers=HEADERS,
        )
        assert rebuilt.status_code == 200, rebuilt.text

    saved = edits.get_edit(tmp_path, "prj_remove", "ed_remove")
    assert _ids(saved) == [keep_id]
    keep = saved["clean"][0]
    # The re-plan keeps the user's fill decision and the saved fill keys.
    assert keep["kind"] == "fill"
    assert keep["auto"] is False
    assert keep["fill_keys"] == 3.0
    assert keep["ranges"] == [{"start": 3.0, "end": 4.0}]
    assert saved["removed_clean"] == [go_id]
