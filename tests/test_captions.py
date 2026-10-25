"""Speech-timed caption tracks and Caption Studio backend."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app
import captions
import exports as cuts
import render
import settings_store


def _scene(index: int, start: float, duration: float, **extra) -> dict:
    value = {
        "id": index,
        "start": float(start),
        "end": float(start + duration),
        "dur": float(duration),
        "deep": True,
        "speech": "",
        "ocr": "",
    }
    value.update(extra)
    return value


def _clip(scene: int, start: float, duration: float) -> dict:
    return {
        "scene": scene,
        "start": float(start),
        "end": float(start + duration),
        "dur": float(duration),
        "role": "beat",
    }


def _plan(clips: list[dict], scenes: list[dict], target: int = 30) -> dict:
    return {
        "target": target,
        "clips": clips,
        "hook_scene": clips[0]["scene"] if clips else None,
        "total": round(sum(float(clip["dur"]) for clip in clips), 3),
        "_scenes": scenes,
    }


def _job(scenes: list[dict], job_id: str = "cap-job") -> dict:
    return {
        "id": job_id,
        "status": "ready",
        "analysis": {"scenes": scenes},
        "source": {"name": "source.mp4", "duration": 120.0},
    }


def _write_transcript(job_dir: Path, segments: list[dict]) -> None:
    directory = job_dir / "transcript"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "transcript.json").write_text(
        json.dumps({"language": "en", "segments": segments}),
        encoding="utf-8",
    )


def test_sentence_boundaries_become_separate_cues():
    scenes = [_scene(0, 0.0, 4.0)]
    plan = _plan([_clip(0, 0.0, 4.0)], scenes)
    cues, source, warnings = captions.build_cues(
        plan,
        style=captions.resolve_style(),
        segments=[{
            "index": 0, "start": 0.0, "end": 4.0,
            "text": "First sentence. Second sentence!",
        }],
    )
    assert source == "transcript"
    assert warnings == []
    assert [cue["text"] for cue in cues] == [
        "First sentence.", "Second sentence!",
    ]
    assert cues[0]["start"] == 0.0
    assert cues[-1]["end"] == 4.0
    assert all(cue["end"] > cue["start"] for cue in cues)


def test_clip_window_slices_transcript_and_clamps_times():
    scenes = [_scene(0, 10.0, 2.0)]
    plan = _plan([_clip(0, 10.0, 2.0)], scenes)
    cues, _source, _warnings = captions.build_cues(
        plan,
        style=captions.resolve_style(),
        segments=[{
            "index": 0, "start": 8.0, "end": 12.0,
            "text": "one two three four five six seven eight",
        }],
    )
    assert len(cues) == 1
    assert cues[0]["start"] == 0.0
    assert cues[0]["end"] == 2.0
    assert "one" not in cues[0]["text"]
    assert cues[0]["text"].startswith("five")


def test_cue_durations_stay_inside_min_and_max():
    style = captions.resolve_style()
    short_plan = _plan([_clip(0, 0.0, 5.0)], [_scene(0, 0.0, 5.0)])
    short_cues, _source, _warnings = captions.build_cues(
        short_plan,
        style=style,
        segments=[{"index": 0, "start": 0.0, "end": 0.3, "text": "Hi"}],
    )
    assert short_cues
    assert all(cue["end"] - cue["start"] >= captions.MIN_CUE - 0.001 for cue in short_cues)

    long_plan = _plan([_clip(0, 0.0, 10.0)], [_scene(0, 0.0, 10.0)])
    long_cues, _source, _warnings = captions.build_cues(
        long_plan,
        style=style,
        segments=[{
            "index": 0, "start": 0.0, "end": 10.0,
            "text": " ".join(["word"] * 40),
        }],
    )
    assert long_cues
    assert all(cue["end"] - cue["start"] <= captions.MAX_CUE + 0.001 for cue in long_cues)
    for previous, current in zip(long_cues, long_cues[1:]):
        assert current["start"] >= previous["end"] - 0.001


def test_legacy_job_without_transcript_falls_back_to_speech_then_ocr(tmp_path):
    scenes = [
        _scene(0, 0.0, 2.0, speech="Spoken line"),
        _scene(1, 5.0, 2.0, ocr="Screen line"),
    ]
    job = _job(scenes)
    plan = _plan([_clip(0, 0.0, 2.0), _clip(1, 5.0, 2.0)], scenes)
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    track = captions.build_track(
        job, plan, captions.resolve_style(), job_dir=job_dir,
    )
    assert track.source == "mixed"
    assert [cue.text for cue in track.cues] == ["Spoken line", "Screen line"]
    assert any("scene speech" in warning for warning in track.warnings)
    assert any("OCR text" in warning for warning in track.warnings)
    sidecar = job_dir / "caption_tracks" / f"{track.id}.json"
    assert sidecar.is_file()
    loaded = captions.load_track(job_dir, track.id)
    assert loaded is not None and loaded.cue_hash == track.cue_hash


def test_build_track_writes_default_data_sidecar(tmp_path, monkeypatch):
    scenes = [_scene(0, 0.0, 2.0, speech="Default sidecar line.")]
    job = _job(scenes, job_id="auto-job")
    plan = _plan([_clip(0, 0.0, 2.0)], scenes)
    monkeypatch.setattr(captions, "DATA", tmp_path / "data")
    track = captions.build_track(job, plan, captions.resolve_style())
    path = tmp_path / "data" / "jobs" / "auto-job" / "caption_tracks" / f"{track.id}.json"
    assert path.is_file()
    assert track.id in path.name


def test_track_hashes_are_deterministic_and_style_sensitive(tmp_path):
    scenes = [_scene(0, 0.0, 3.0)]
    job = _job(scenes)
    plan = _plan([_clip(0, 0.0, 3.0)], scenes)
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    _write_transcript(job_dir, [{
        "start": 0.0, "end": 3.0, "text": "One line.",
    }])
    style = captions.resolve_style()
    first = captions.build_track(job, plan, style, job_dir=job_dir)
    second = captions.build_track(job, plan, style, job_dir=job_dir)
    assert first.id == second.id
    assert first.cue_hash == second.cue_hash
    assert first.style_hash == second.style_hash
    assert first.cue_hash == captions.cue_hash(first.cues)
    assert first.style_hash == captions.style_hash(style)

    changed_style = captions.resolve_style(overrides={"color": "#FF0000", "uppercase": True})
    third = captions.build_track(job, plan, changed_style, job_dir=job_dir)
    assert third.style_hash != first.style_hash
    assert third.id != first.id


def test_validate_track_rejects_overlap_zero_out_of_bounds_and_lines():
    style = captions.resolve_style()
    clips = [_clip(0, 0.0, 2.0)]
    valid = [{
        "start": 0.0, "end": 1.0, "text": "ok", "clip_index": 0,
    }]
    captions.validate_track(valid, style=style, clips=clips, total=2.0)

    with pytest.raises(captions.CaptionValidationError):
        captions.validate_track(
            [
                {"start": 0.0, "end": 1.5, "text": "a", "clip_index": 0},
                {"start": 1.0, "end": 1.8, "text": "b", "clip_index": 0},
            ],
            style=style, clips=clips, total=2.0,
        )
    with pytest.raises(captions.CaptionValidationError):
        captions.validate_track(
            [{"start": 1.0, "end": 1.0, "text": "a", "clip_index": 0}],
            style=style, clips=clips, total=2.0,
        )
    with pytest.raises(captions.CaptionValidationError):
        captions.validate_track(
            [{"start": 0.0, "end": 2.5, "text": "a", "clip_index": 0}],
            style=style, clips=clips, total=2.0,
        )
    with pytest.raises(captions.CaptionValidationError):
        captions.validate_track(
            [{"start": 0.0, "end": 1.5, "text": "a\nb\nc", "clip_index": 0}],
            style=style, clips=clips, total=2.0,
        )


def test_burn_and_srt_use_identical_cues(tmp_path):
    scenes = [_scene(0, 0.0, 5.0)]
    job = _job(scenes)
    plan = _plan([_clip(0, 0.0, 5.0)], scenes)
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    _write_transcript(job_dir, [{
        "start": 0.0, "end": 5.0,
        "text": "This is one sentence. This is another sentence!",
    }])
    track = captions.build_track(
        job, plan, captions.resolve_style(), job_dir=job_dir,
    )
    app._attach_caption_track(plan, track)
    burned = render._caption_cues(plan, plan["clips"])
    exported = cuts.plan_cues(plan, plan["clips"], scenes)
    assert [(row[0], row[1], row[2]) for row in burned] == [
        (row["start"], row["end"], row["text"]) for row in exported
    ]
    assert [row[2] for row in burned] == [cue.text for cue in track.cues]


def test_render_track_binding_and_stale_cut_guard(tmp_path, monkeypatch):
    scenes = [_scene(0, 0.0, 4.0)]
    job = _job(scenes, job_id="render-job")
    jobs = tmp_path / "jobs"
    (jobs / job["id"] / "transcript").mkdir(parents=True)
    transcript = jobs / job["id"] / "transcript" / "transcript.json"
    transcript.write_text(json.dumps({
        "segments": [{"start": 0.0, "end": 4.0, "text": "Bound line."}],
    }), encoding="utf-8")
    (jobs / job["id"] / "job.json").write_text(json.dumps(job), encoding="utf-8")
    monkeypatch.setattr(app, "JOBS", jobs)
    plan = _plan([_clip(0, 0.0, 4.0)], scenes)
    track = captions.build_track(
        job, plan, captions.resolve_style(), job_dir=jobs / job["id"],
    )
    body = app.PlanBody(captions=True, caption_track_id=track.id)
    bound = app._caption_track_for_render(job["id"], job, plan, body, True)
    assert bound is not None and bound.id == track.id

    stale = _plan([_clip(0, 0.0, 3.0)], scenes)
    with pytest.raises(HTTPException) as excinfo:
        app._caption_track_for_render(job["id"], job, stale, body, True)
    assert excinfo.value.status_code == 409
    assert "does not match" in str(excinfo.value.detail)


def test_edit_changes_hash_and_version_but_unchanged_edit_is_stable(tmp_path):
    scenes = [_scene(0, 0.0, 4.0)]
    job = _job(scenes)
    plan = _plan([_clip(0, 0.0, 4.0)], scenes)
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    _write_transcript(job_dir, [{
        "start": 0.0, "end": 4.0, "text": "Original line.",
    }])
    track = captions.build_track(
        job, plan, captions.resolve_style(), job_dir=job_dir,
    )

    same, changed = captions.edit_track(track, job_dir=job_dir)
    assert changed is False
    assert same.id == track.id

    edited, changed = captions.edit_track(
        track,
        cues=[{
            "id": "c001", "start": 0.0, "end": 3.0,
            "text": "Edited line.", "clip_index": 0, "scene": 0,
        }],
        job_dir=job_dir,
    )
    assert changed is True
    assert edited.version == track.version + 1
    assert edited.parent_id == track.id
    assert edited.id != track.id
    assert edited.cue_hash != track.cue_hash
    assert captions.load_track(job_dir, edited.id) is not None

    styled, changed = captions.edit_track(
        edited,
        style={"color": "#00FF00", "position": "top"},
        job_dir=job_dir,
    )
    assert changed is True
    assert styled.style_hash != edited.style_hash
    assert styled.style["color"] == "#00FF00"
    assert styled.version == edited.version + 1


def test_preview_returns_safe_zones_and_never_renders(tmp_path, monkeypatch):
    scenes = [_scene(0, 0.0, 4.0, speech="Preview line one. Preview line two.")]
    job = _job(scenes, job_id="job-preview")
    jobs = tmp_path / "jobs"
    job_dir = jobs / job["id"]
    job_dir.mkdir(parents=True)
    job["renders"] = {
        "30": {
            "status": "ready", "path": "renders/reel_30.mp4",
            "poster": "renders/reel_30.jpg", "key": "abc", "updated": 1.0,
        },
    }
    (job_dir / "job.json").write_text(json.dumps(job), encoding="utf-8")
    monkeypatch.setattr(app, "JOBS", jobs)
    plan = _plan([_clip(0, 0.0, 4.0)], scenes)
    monkeypatch.setattr(
        app, "_plan_for_body", lambda current, target, body: dict(plan, target=target),
    )
    monkeypatch.setattr(
        app, "_queue_render",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("full render")),
    )
    monkeypatch.setattr(
        render, "render_reel",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("full render")),
    )
    client = TestClient(app.app, base_url="http://127.0.0.1")
    created = client.post(f"/api/jobs/{job['id']}/captions", json={"target": 30})
    assert created.status_code == 200, created.text
    track_id = created.json()["track"]["id"]

    response = client.get(f"/api/jobs/{job['id']}/captions/{track_id}/preview")
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["full_render"] is False
    assert preview["caption_only"] is True
    assert preview["cues"] == created.json()["track"]["cues"]
    assert preview["poster_url"].startswith(f"/api/jobs/{job['id']}/media/")
    assert preview["safe_zones"]["caption"]["w"] > 0
    assert preview["safe_zones"]["caption"]["h"] > 0
    assert preview["safe_zones"]["platform"]["x"] > 0


def test_api_patch_srt_and_old_version_are_preserved(tmp_path, monkeypatch):
    scenes = [_scene(0, 0.0, 4.0, speech="First line. Second line.")]
    job = _job(scenes, job_id="job-edit")
    jobs = tmp_path / "jobs"
    job_dir = jobs / job["id"]
    job_dir.mkdir(parents=True)
    (job_dir / "job.json").write_text(json.dumps(job), encoding="utf-8")
    monkeypatch.setattr(app, "JOBS", jobs)
    plan = _plan([_clip(0, 0.0, 4.0)], scenes)
    monkeypatch.setattr(
        app, "_plan_for_body", lambda current, target, body: dict(plan, target=target),
    )
    client = TestClient(app.app, base_url="http://127.0.0.1")
    created = client.post(f"/api/jobs/{job['id']}/captions", json={"target": 30})
    track = created.json()["track"]
    track_id = track["id"]

    srt = client.get(f"/api/jobs/{job['id']}/captions/{track_id}/srt")
    assert srt.status_code == 200
    assert track["cues"][0]["text"] in srt.text

    edited = client.patch(
        f"/api/jobs/{job['id']}/captions/{track_id}",
        json={"cues": [{
            "id": "c001", "start": 0.0, "end": 2.0,
            "text": "Edited line.", "clip_index": 0, "scene": 0,
        }]},
    )
    assert edited.status_code == 200, edited.text
    payload = edited.json()
    assert payload["changed"] is True
    assert payload["track"]["version"] == 2
    assert payload["track"]["id"] != track_id
    assert payload["track"]["cues"][0]["text"] == "Edited line."

    old = client.get(f"/api/jobs/{job['id']}/captions/{track_id}")
    assert old.status_code == 200 and old.json()["version"] == 1
    new_srt = client.get(
        f"/api/jobs/{job['id']}/captions/{payload['track']['id']}/srt",
    )
    assert "Edited line." in new_srt.text


def test_cjk_emoji_and_missing_font_do_not_break_render(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBECUT_CAPTION_FONT_FILE", str(tmp_path / "missing.ttf"))
    style = captions.resolve_style(overrides={
        "font": str(tmp_path / "also-missing.ttf"),
        "max_chars": 12,
        "max_lines": 2,
    })
    text = "你好，世界 🌱👩‍🌾"
    wrapped = captions.wrap_lines(text, 12)
    assert "".join(wrapped).replace(" ", "") == text.replace(" ", "")
    paths = render._caption_pngs(
        tmp_path,
        [(0.0, 1.0, text)],
        540,
        960,
        style=style,
    )
    assert len(paths) == 1
    assert paths[0].stat().st_size > 0


def test_caption_style_settings_accept_custom_styles(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(settings_store, "DATA", data)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", data / "settings.json")
    monkeypatch.setattr(settings_store, "SECRETS_PATH", data / "secrets.json")
    settings_store.save_settings({
        "caption_styles": {
            "default": "neon",
            "styles": {
                "neon": {
                    "color": "#00FF88",
                    "stroke_width": 7,
                    "max_lines": 3,
                    "uppercase": True,
                },
            },
        },
    })
    loaded = settings_store.load_settings()["caption_styles"]
    assert loaded["default"] == "neon"
    assert loaded["styles"]["neon"]["color"] == "#00FF88"
    assert loaded["styles"]["neon"]["max_lines"] == 3

    style = captions.resolve_style(settings=settings_store.load_settings())
    assert style["id"] == "neon"
    assert style["color"] == "#00FF88"
    assert style["uppercase"] is True
    assert captions.normalize_style(style)["id"] == "neon"


def test_settings_api_accepts_caption_styles(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(settings_store, "DATA", data)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", data / "settings.json")
    monkeypatch.setattr(settings_store, "SECRETS_PATH", data / "secrets.json")
    monkeypatch.setattr(app, "DATA", data)
    client = TestClient(app.app, base_url="http://127.0.0.1")
    response = client.post("/api/settings", json={
        "settings": {
            "caption_styles": {
                "styles": {
                    "studio": {"color": "#123456", "position": "center"},
                },
            },
        },
    })
    assert response.status_code == 200, response.text
    styles = response.json()["settings"]["caption_styles"]["styles"]
    assert styles["studio"]["color"] == "#123456"
    assert styles["studio"]["position"] == "center"
