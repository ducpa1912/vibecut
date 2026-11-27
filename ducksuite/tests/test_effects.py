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


def test_split_at_uses_output_timeline(tmp_path: Path) -> None:
    from duckcore import edits

    edit = {
        "id": "ed_split01",
        "project_id": "prj_split",
        "kind": "story",
        "end": 8.0,
        "clips": [
            {"scene": 8, "start": 10.0, "end": 13.0, "dur": 3.0},
            {"scene": 11, "start": 20.0, "end": 25.0, "dur": 5.0},
        ],
    }
    edits.save_edit(edit, tmp_path)
    split = edits.split_at(edit, tmp_path, 4.0)
    assert [clip["scene"] for clip in split["clips"]] == [8, 11, 11]
    assert split["clips"][1]["start"] == 20.0
    assert split["clips"][1]["end"] == 21.0
    assert split["end"] == 8.0


def test_audio_tracks_merge_legacy_voice_and_music(tmp_path: Path) -> None:
    from duckcore import edits

    edit = {
        "id": "ed_audio01",
        "project_id": "prj_audio",
        "voice": {"id": "at_voice", "audio": "voice/a.wav", "duration": 2.0, "mode": "voice_over"},
        "music": {"id": "at_music", "audio": "music/a.m4a", "duration": 3.0, "volume": 0.25},
    }
    rows = edits.ensure_audio_tracks(edit)
    assert [row["kind"] for row in rows] == ["voice", "music"]
    assert rows[0]["start"] == 0.0
    edits.remove_audio_track(edit, "at_music")
    assert [row["kind"] for row in edit["audio_tracks"]] == ["voice"]
    assert "music" not in edit


def test_patch_audio_track_keeps_offset_volume_and_flags(tmp_path: Path) -> None:
    from duckcore import edits

    edit = {
        "id": "ed_audio02",
        "project_id": "prj_audio",
        "audio_tracks": [
            {"id": "at_music", "kind": "music", "audio": "music/a.m4a", "start": 0.0, "duration": 3.0, "volume": 0.25},
        ],
    }
    row = edits.patch_audio_track(edit, "at_music", {
        "start": 1.5,
        "duration": 4.0,
        "offset": 2.25,
        "volume": 0.0,
        "fade_in": 0.5,
        "fade_out": 1.0,
        "muted": True,
        "solo": True,
        "name": "Bed",
    })
    assert row["start"] == 1.5
    assert row["duration"] == 4.0
    assert row["offset"] == 2.25
    assert row["volume"] == 0.0
    assert row["fade_in"] == 0.5
    assert row["fade_out"] == 1.0
    assert row["muted"] is True
    assert row["solo"] is True
    assert row["name"] == "Bed"

    clamped = edits.patch_audio_track(edit, "at_music", {
        "start": -3.0, "duration": 0.01, "volume": -1.0, "offset": -1.0,
    })
    assert clamped["start"] == 0.0
    assert clamped["duration"] == 0.2
    assert clamped["volume"] == 0.0
    assert clamped["offset"] == 0.0

    import pytest
    with pytest.raises(KeyError):
        edits.patch_audio_track(edit, "at_missing", {"volume": 0.5})


def test_ensure_audio_tracks_rebuilds_legacy_rows_from_empty_list() -> None:
    from duckcore import edits

    edit = {
        "audio_tracks": [],
        "music": {"id": "at_music", "audio": "music/a.m4a", "duration": 3.0},
    }
    rows = edits.ensure_audio_tracks(edit)
    assert [row["kind"] for row in rows] == ["music"]
    assert edit["audio_tracks"] is rows


def test_render_keeps_solo_voice_and_solo_sound_together(tmp_path: Path) -> None:
    import array
    import math
    import shutil
    import subprocess

    import pytest

    from duckcore import media, render

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg is not installed")

    source = tmp_path / "base.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=c=black:s=160x90:d=4",
         "-f", "lavfi", "-i", "sine=frequency=220:duration=4",
         "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", str(source)],
        check=True,
    )
    (tmp_path / "music").mkdir()
    (tmp_path / "sfx").mkdir()
    voice = tmp_path / "music" / "voice.wav"
    beep = tmp_path / "sfx" / "beep.wav"
    subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=4", str(voice)],
        check=True,
    )
    subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-f", "lavfi",
         "-i", "sine=frequency=880:duration=1", str(beep)],
        check=True,
    )
    edit = {
        "end": 4.0,
        "audio_tracks": [{
            "id": "at_voice", "kind": "voice", "audio": "music/voice.wav",
            "start": 0, "duration": 3, "volume": 1.0, "solo": True,
        }],
        "sfx": [{
            "id": "fx_beep", "kind": "sound", "file": "sfx/beep.wav",
            "start": 3.0, "end": 3.5, "volume": 1.0, "solo": True,
        }],
    }
    render._mix_audio(ffmpeg, source, edit, tmp_path)
    render._mix_sfx_audio(ffmpeg, source, edit, tmp_path)

    def rms(at: float, duration: float) -> int:
        raw = subprocess.run(
            [ffmpeg, "-v", "error", "-ss", str(at), "-t", str(duration),
             "-i", str(source), "-f", "s16le", "-ac", "1", "-ar", "8000", "-"],
            capture_output=True, check=True,
        ).stdout
        samples = array.array("h")
        samples.frombytes(raw)
        if not samples:
            return 0
        return int(math.sqrt(sum(value * value for value in samples) / len(samples)))

    assert abs(media.duration(source) - 4.0) < 0.3
    assert rms(1.0, 0.4) > 200, "solo voice was dropped by the SFX mix"
    assert rms(3.1, 0.3) > 200, "solo sound effect was dropped"
    assert rms(3.6, 0.3) < 80, "solo voice leaked past its trimmed end"


def test_global_solo_filters_music_and_sound_together(tmp_path: Path) -> None:
    from duckcore import render

    (tmp_path / "music").mkdir()
    (tmp_path / "sfx").mkdir()
    (tmp_path / "music" / "bed.wav").write_bytes(b"a")
    (tmp_path / "music" / "voice.wav").write_bytes(b"b")
    (tmp_path / "sfx" / "one.wav").write_bytes(b"c")
    (tmp_path / "sfx" / "two.wav").write_bytes(b"d")
    edit = {
        "audio_tracks": [
            {"id": "at_music", "kind": "music", "audio": "music/bed.wav", "start": 0, "duration": 4},
            {"id": "at_voice", "kind": "voice", "audio": "music/voice.wav", "start": 0, "duration": 4, "solo": True},
        ],
        "sfx": [
            {"id": "fx_one", "kind": "sound", "file": "sfx/one.wav", "start": 0, "end": 1},
            {"id": "fx_two", "kind": "sound", "file": "sfx/two.wav", "start": 0, "end": 1, "solo": True},
        ],
    }
    rows, items, solo = render._audible_audio(edit, tmp_path)
    assert solo is True
    assert [row["id"] for row in rows] == ["at_voice"]
    assert [item["id"] for item in items] == ["fx_two"]

    for row in edit["audio_tracks"]:
        row["solo"] = False
    edit["sfx"][1]["solo"] = False
    rows, items, solo = render._audible_audio(edit, tmp_path)
    assert solo is False
    assert [row["id"] for row in rows] == ["at_music", "at_voice"]
    assert [item["id"] for item in items] == ["fx_one", "fx_two"]


def test_mix_audio_keeps_full_duration_for_solo_zero_volume_row(tmp_path: Path) -> None:
    import shutil
    import subprocess

    import pytest

    from duckcore import media, render

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg is not installed")

    source = tmp_path / "base.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=c=black:s=160x90:d=2",
         "-f", "lavfi", "-i", "sine=frequency=220:duration=2",
         "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", str(source)],
        check=True,
    )
    (tmp_path / "music").mkdir()
    music = tmp_path / "music" / "a.wav"
    subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-f", "lavfi",
         "-i", "sine=frequency=880:duration=1", str(music)],
        check=True,
    )
    edit = {
        "end": 2.0,
        "audio_tracks": [{
            "id": "at_music", "kind": "music", "audio": "music/a.wav",
            "start": 0.5, "duration": 1.0, "offset": 0.2,
            "volume": 0.0, "solo": True,
        }],
    }
    render._mix_audio(ffmpeg, source, edit, tmp_path)

    assert source.is_file()
    assert abs(media.duration(source) - 2.0) < 0.3
    assert media.has_audio(source)


def _story_check() -> dict:
    return {
        "meta": {"duration": 12.0, "width": 160, "height": 90, "fps": 24.0},
        "scenes": [
            {"id": 1, "start": 0.0, "end": 4.0},
            {"id": 2, "start": 4.0, "end": 8.0},
        ],
        "transcript": {
            "segments": [
                {"start": 0.5, "end": 3.5, "text": "First line"},
                {"start": 4.5, "end": 7.5, "text": "Second line"},
            ],
        },
    }


def test_story_inherits_clean_and_captions(tmp_path: Path) -> None:
    from duckcore import edits

    check = _story_check()
    full = edits.create_full("prj_story", check, tmp_path)
    full["clean"] = [{
        "id": "cl_one", "kind": "blur", "enabled": True,
        "ranges": [{"start": 0.0, "end": 4.0}],
    }]
    full["captions"] = {
        "track_id": "cap_full", "style": "bold", "burn": True,
        "cues": [{"id": "c1", "start": 0, "end": 1, "text": "old"}],
    }
    edits.save_edit(full, tmp_path)

    story = edits.create_story_from_scenes(
        "prj_story", check, tmp_path, scene_ids=[1, 2],
    )
    assert [layer["id"] for layer in story["clean"]] == ["cl_one"]
    assert story["captions"]["burn"] is True
    assert story["captions"]["style"] == "bold"
    assert [cue["text"] for cue in story["captions"]["cues"]] == ["First line", "Second line"]
    assert story["end"] == 8.0


def test_story_captions_skip_media_beats_and_keep_style(tmp_path: Path) -> None:
    from duckcore import captions, edits

    check = _story_check()
    full = edits.create_full("prj_story_cap", check, tmp_path)
    full["captions"] = {
        "track_id": "cap_full", "style": "bold", "burn": True,
        "cues": [{"id": "c1", "start": 0, "end": 1, "text": "old"}],
    }
    edits.save_edit(full, tmp_path)
    story = edits.create_story_from_scenes(
        "prj_story_cap", check, tmp_path, scene_ids=[1, 2],
    )
    edits.add_story_media(
        story, tmp_path, kind="image", filename="hook.png",
        raw=b"png", duration=3.0, index=0,
    )
    track = captions.generate(story, check["transcript"], tmp_path)
    assert track["style"] == "bold"
    assert track["burn"] is True
    assert track["cues"]
    assert all(float(cue["start"]) >= 3.0 for cue in track["cues"])
    assert all(float(cue["end"]) <= 11.0 for cue in track["cues"])


def test_story_extension_adds_scene_media_and_reorders(tmp_path: Path) -> None:
    from duckcore import edits

    check = _story_check()
    story = edits.create_story_from_scenes("prj_story2", check, tmp_path, scene_ids=[1])
    assert story["end"] == 4.0

    edits.add_story_scene(story, check, tmp_path, scene_id=2)
    assert [clip.get("scene") for clip in story["clips"]] == [1, 2]
    assert story["end"] == 8.0

    edited = edits.add_story_media(
        story, tmp_path, kind="image", filename="hook.png",
        raw=b"not-a-real-png", duration=3.0, index=0,
    )
    assert edited["clips"][0]["kind"] == "media"
    assert edited["end"] == 11.0
    assert (tmp_path / "projects" / "prj_story2" / edited["clips"][0]["file"]).is_file()

    edits.move_story_clip(edited, tmp_path, 0, 1)
    assert edited["clips"][1]["kind"] == "media"
    edits.remove_story_clip(edited, tmp_path, 1)
    assert edited["end"] == 8.0


def test_render_story_media_beat(tmp_path: Path) -> None:
    import shutil
    import subprocess

    import pytest

    from duckcore import edits, media, render

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg is not installed")
    source = tmp_path / "source.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=c=black:s=160x90:d=1",
         "-f", "lavfi", "-i", "sine=frequency=220:duration=1",
         "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", str(source)],
        check=True,
    )
    image = tmp_path / "beat.png"
    subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-f", "lavfi",
         "-i", "color=c=red:s=160x90", "-frames:v", "1", str(image)],
        check=True,
    )
    check = _story_check()
    story = edits.create_story_from_scenes("prj_story3", check, tmp_path, scene_ids=[1])
    story["clips"] = story["clips"][:1]
    story["end"] = 1.0
    story["clips"][0]["end"] = 1.0
    story["clips"][0]["dur"] = 1.0
    edits.save_edit(story, tmp_path)
    edits.add_story_media(
        story, tmp_path, kind="image", filename="end.png",
        raw=image.read_bytes(), duration=1.0,
    )
    edits.add_story_media(
        story, tmp_path, kind="video", filename="beat.mp4",
        raw=source.read_bytes(), duration=1.0,
    )
    project = {"id": "prj_story3", "source_path": str(source)}
    output = render.render_edit(project, story, tmp_path)
    assert output.is_file()
    assert abs(media.duration(output) - 3.0) < 0.4


def test_slip_clip_preserves_duration(tmp_path: Path) -> None:
    from duckcore import edits

    edit = {
        "id": "ed_slip01",
        "project_id": "prj_slip",
        "source": {"duration": 20.0},
        "clips": [
            {"scene": 1, "start": 0.0, "end": 4.0, "dur": 4.0},
            {"scene": 2, "start": 8.0, "end": 12.0, "dur": 4.0},
        ],
    }
    edits.save_edit(edit, tmp_path)
    slipped = edits.slip_clip(edit, tmp_path, 1, 1.0)
    assert slipped["clips"][1]["start"] == 9.0
    assert slipped["clips"][1]["end"] == 13.0
    assert slipped["clips"][1]["dur"] == 4.0
