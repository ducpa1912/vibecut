"""An effect can be re-timed and re-styled after it was added."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from duckcore import effects


def _edit(tmp_path: Path) -> dict:
    project = tmp_path / "projects" / "prj_test"
    (project / "edits").mkdir(parents=True)
    edit = {
        "id": "ed_test",
        "project_id": "prj_test",
        "source": {"width": 1080, "height": 1920, "fps": 30},
        "end": 20.0,
        "sfx": [
            {
                "id": "fx_text", "kind": "text", "name": "Old", "text": "Old",
                "start": 1.0, "end": 4.0, "style": "headline", "color": "#ffffff",
                "x": 0.5, "y": 0.84, "opacity": 1.0,
            },
            {"id": "fx_snd", "kind": "sound", "name": "Whoosh", "start": 2.0, "end": 3.0, "volume": 0.9},
        ],
    }
    (project / "edits" / "ed_test.json").write_text(json.dumps(edit), encoding="utf-8")
    return edit


def test_update_moves_and_restyles_a_text_effect(tmp_path: Path) -> None:
    edit = _edit(tmp_path)

    row = effects.update(edit, tmp_path, "fx_text", {"start": 5.5, "end": 9.0, "text": "New copy", "x": 0.2})

    assert row["start"] == 5.5
    assert row["end"] == 9.0
    assert row["text"] == "New copy"
    assert row["name"] == "New copy"
    assert row["x"] == 0.2
    saved = json.loads((tmp_path / "projects" / "prj_test" / "edits" / "ed_test.json").read_text())
    assert saved["sfx"][0]["start"] == 5.5


def test_update_clamps_level_and_width(tmp_path: Path) -> None:
    edit = _edit(tmp_path)

    row = effects.update(edit, tmp_path, "fx_snd", {"volume": 9.0, "width": 0.01})

    assert row["volume"] == 1.5
    assert row["width"] == 0.04


def test_update_rejects_empty_text_and_missing_id(tmp_path: Path) -> None:
    edit = _edit(tmp_path)

    with pytest.raises(effects.EffectError):
        effects.update(edit, tmp_path, "fx_text", {"text": "   "})
    with pytest.raises(KeyError):
        effects.update(edit, tmp_path, "fx_missing", {"start": 1.0})
