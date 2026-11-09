"""Special-effect model tests."""

from __future__ import annotations

from pathlib import Path

from duckcore import effects


def _edit(project_id: str = "prj_sfx") -> dict:
    return {
        "id": "ed_sfx01",
        "project_id": project_id,
        "end": 5.0,
        "clips": [],
        "sfx": [],
    }


def test_text_effect_creates_png(tmp_path: Path) -> None:
    edit = _edit()
    effect = effects.add_text(
        edit, tmp_path,
        text="Hello effects", start=0.5, end=3.5,
        style="headline", color="#ffffff",
    )
    png = effects.text_png(effect, "prj_sfx", tmp_path, 1080, 1080)
    assert png.is_file()
    assert png.stat().st_size > 1000
    assert (tmp_path / "projects" / "prj_sfx" / "edits" / "ed_sfx01.json").is_file()


def test_filter_effect_and_remove(tmp_path: Path) -> None:
    edit = _edit()
    effect = effects.add_filter(edit, tmp_path, preset="warm", start=0, end=5)
    assert effect["preset"] == "warm"
    assert len(effects.visual_effects(edit)) == 1
    effects.remove(edit, tmp_path, effect["id"])
    assert effects.visual_effects(edit) == []


def test_sound_effect_upload(tmp_path: Path) -> None:
    edit = _edit()
    effect = effects.add_upload(
        edit, tmp_path,
        kind="sound", filename="pop.wav", raw=b"RIFFfake",
        start=1.0, end=2.0,
    )
    assert effect["kind"] == "sound"
    assert (tmp_path / "projects" / "prj_sfx" / effect["file"]).is_file()


def test_story_from_selected_scenes_keeps_order(tmp_path: Path) -> None:
    from duckcore import edits

    check = {
        "meta": {"duration": 10.0, "width": 1920, "height": 1080, "fps": 30.0},
        "scenes": [
            {"id": 1, "start": 0.0, "end": 2.0},
            {"id": 2, "start": 2.0, "end": 5.0},
            {"id": 3, "start": 5.0, "end": 9.0},
        ],
    }
    edit = edits.create_story_from_scenes(
        "prj_story", check, tmp_path,
        scene_ids=[3, 1], title="Mix",
    )
    assert edit["kind"] == "story"
    assert [clip["scene"] for clip in edit["clips"]] == [3, 1]
    assert edit["end"] == 6.0
    assert edit["scene_ids"] == [3, 1]
