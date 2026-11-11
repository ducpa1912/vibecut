"""Loop 1: the render cost is shown before a render starts."""

from __future__ import annotations

import json

from duckcore import render
from duckcore.engine import textfill

META = {"width": 1080, "height": 1920, "fps": 30.0, "duration": 10.0, "size": 1}


def _layer(kind: str, start: float, end: float, *, quality: str = "steady", enabled: bool = True) -> dict:
    return {
        "id": f"cl_{kind}_{start}",
        "kind": kind,
        "enabled": enabled,
        "quality": quality,
        "box": {"x": 0.3, "y": 0.4, "w": 0.3, "h": 0.05},
        "ranges": [{"start": start, "end": end}],
        "fill_keys": 3.0,
    }


def _edit(clean: list[dict]) -> dict:
    return {
        "id": "ed_estimate01",
        "project_id": "prj_estimate",
        "source": dict(META),
        "clips": [
            {"scene": 0, "start": 0.0, "end": 4.0},
            {"scene": 1, "start": 4.0, "end": 10.0},
        ],
        "clean": clean,
    }


def test_estimate_uses_the_seed_rate_and_says_it_is_a_guess(tmp_path) -> None:
    edit = _edit([_layer("fill", 1.0, 3.0, quality="moving"), _layer("blur", 5.0, 5.3)])
    result = render.estimate_edit(edit, META, tmp_path)

    assert result["layers"] == {"fill": 1, "blur": 1, "off": 0, "moving_fill": 1}
    assert result["beats"] == 1
    assert result["frames"] == 60
    assert result["fill_seconds"] == 2.0
    assert result["seconds"] > 0
    assert result["measured"] is False
    assert "first guess" in result["text"]


def test_estimate_uses_the_rate_measured_on_this_mac(tmp_path) -> None:
    edit = _edit([_layer("fill", 1.0, 3.0)])
    guess = render.estimate_edit(edit, META, tmp_path)
    (tmp_path / textfill.RATES_FILE).write_text(
        json.dumps({"lama_run": {"seconds": 8.0, "runs": 3, "recent": [8.0, 8.0, 8.0]}}),
        encoding="utf-8",
    )
    measured = render.estimate_edit(edit, META, tmp_path)

    assert measured["measured"] is True
    assert "first guess" not in measured["text"]
    # The seed is 4.0 s a unit; the measured rate here is twice that.
    assert abs(measured["seconds"] - guess["seconds"] * 2) <= 0.2


def test_estimate_with_no_fill_layers_adds_no_time(tmp_path) -> None:
    edit = _edit([_layer("blur", 1.0, 3.0), _layer("fill", 5.0, 6.0, enabled=False)])
    result = render.estimate_edit(edit, META, tmp_path)

    assert result["layers"] == {"fill": 0, "blur": 1, "off": 1, "moving_fill": 0}
    assert result["beats"] == 0
    assert result["seconds"] == 0
    assert result["text"] == ""


def test_estimate_warns_when_disk_is_under_the_saved_fill_floor(tmp_path, monkeypatch) -> None:
    edit = _edit([_layer("fill", 1.0, 3.0)])
    monkeypatch.setattr(textfill, "_free_disk", lambda _path: textfill.SAVED_MIN_FREE - 1)
    low = render.estimate_edit(edit, META, tmp_path)
    monkeypatch.setattr(textfill, "_free_disk", lambda _path: textfill.SAVED_MIN_FREE * 2)
    fine = render.estimate_edit(edit, META, tmp_path)

    assert low["disk"]["low"] is True
    assert low["disk"]["floor_bytes"] == textfill.SAVED_MIN_FREE
    assert "10 GB" in low["disk"]["text"]
    assert fine["disk"]["low"] is False
    assert fine["disk"]["text"] == ""


def test_estimate_route_answers_for_a_saved_edit(tmp_path) -> None:
    from fastapi.testclient import TestClient

    from duckcore import edits
    from duckcore.main import create_app

    source = tmp_path / "source.mp4"
    source.write_bytes(b"not a real video")
    app = create_app("test-token", tmp_path)
    headers = {"Authorization": "Bearer test-token"}

    with TestClient(app) as client:
        project = client.post(
            "/api/projects", headers=headers,
            json={"name": "Estimate test", "source_path": str(source)},
        ).json()["project"]
        edit = _edit([_layer("fill", 1.0, 3.0)])
        edit.update({
            "schema": 1, "project_id": project["id"], "kind": "full", "title": "Full video",
            "created": 1.0, "updated": 1.0, "start": 0.0, "end": 10.0,
            "captions": None, "audio": {"mode": "original"},
        })
        edits.save_edit(edit, tmp_path)

        found = client.get(
            f"/api/projects/{project['id']}/edits/ed_estimate01/render/estimate", headers=headers,
        )
        missing = client.get(
            f"/api/projects/{project['id']}/edits/ed_nope/render/estimate", headers=headers,
        )

    assert found.status_code == 200
    estimate = found.json()["estimate"]
    assert estimate["layers"]["fill"] == 1
    assert estimate["frames"] == 60
    assert missing.status_code == 404


def test_one_slow_fill_does_not_hold_the_rate_up(tmp_path) -> None:
    """Loop 3: a 35 s rate from a starved run made a 3 min clip read as 19 min."""
    (tmp_path / textfill.RATES_FILE).write_text(
        json.dumps({"lama_run": {"seconds": 35.0, "runs": 61}}), encoding="utf-8",
    )
    textfill.record_rate(tmp_path, "lama", 30, 180.0)   # 6 s a unit
    textfill.record_rate(tmp_path, "lama", 30, 186.0)   # 6.2 s a unit
    rate = textfill.fill_rate(tmp_path, "lama")

    assert rate["measured"] is True
    assert rate["seconds"] == 6.2
    stored = json.loads((tmp_path / textfill.RATES_FILE).read_text(encoding="utf-8"))
    assert stored["lama_run"]["runs"] == 63
    assert len(stored["lama_run"]["recent"]) == 3


def test_a_single_slow_fill_is_outvoted(tmp_path) -> None:
    for seconds in (180.0, 186.0, 900.0, 183.0):
        textfill.record_rate(tmp_path, "lama", 30, seconds)
    assert textfill.fill_rate(tmp_path, "lama")["seconds"] == 6.2


def test_a_stale_rate_file_is_not_trusted(tmp_path: Path) -> None:
    """A rate from before the median rule has no samples; treat it as a guess."""
    import json

    from duckcore.engine import textfill

    (tmp_path / "fill_rates.json").write_text(
        json.dumps({"lama_run": {"seconds": 20.4, "runs": 62}}), encoding="utf-8",
    )
    rate = textfill.fill_rate(tmp_path, "lama", "cpu")
    assert rate["measured"] is False
    assert rate["seconds"] == textfill.SEED_RATES["lama"]
