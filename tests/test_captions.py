"""Speech-timed caption tracks and Caption Studio backend."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app
import artifacts
import captions
import exports as cuts
import render
import settings_store
import shares


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


def _artifact_spec(job: dict, plan: dict, track, *, margin: float = 0.075):
    return artifacts.build_spec(
        job,
        plan,
        captions=True,
        cues=[cue.to_dict() for cue in track.cues],
        caption_margin=margin,
        caption_style_key=track.style_hash,
    )


def _store_ready_artifact(
    job: dict,
    job_dir: Path,
    plan: dict,
    track,
    *,
    record_key: str = "30:cap",
) -> tuple[str, dict]:
    spec = _artifact_spec(job, plan, track)
    artifact = artifacts.artifact_id(spec)
    manifest = artifacts.make_manifest(
        job["id"], spec, status="ready", record_key=record_key,
    )
    artifacts.save_manifest(job_dir, manifest)
    renders = job_dir / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    reel = renders / f"{artifact}.mp4"
    poster = renders / f"{artifact}.jpg"
    reel.write_bytes(b"reel")
    poster.write_bytes(b"poster")
    artifacts.store_media(job_dir, artifact, reel=reel, poster=poster)
    artifacts.write_captions(
        job_dir,
        artifact,
        cuts.srt([cue.to_dict() for cue in track.cues]),
        cuts.vtt([cue.to_dict() for cue in track.cues]),
    )
    return artifact, artifacts.load_manifest(job_dir, artifact) or manifest


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


def test_cjk_partial_segment_clips_only_in_window_text():
    scenes = [_scene(0, 3.0, 3.0)]
    plan = _plan([_clip(0, 3.0, 3.0)], scenes)
    cues, _source, _warnings = captions.build_cues(
        plan,
        style=captions.resolve_style(),
        segments=[{
            "index": 0, "start": 0.0, "end": 9.0,
            "text": "第一句。第二句。第三句。",
        }],
    )
    assert cues
    text = "".join(cue["text"] for cue in cues)
    assert "第二句" in text
    assert "第一句" not in text
    assert "第三句" not in text


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


def test_sparse_speech_never_exceeds_max_duration():
    style = captions.resolve_style()
    for duration in (10.0, 20.0):
        plan = _plan([_clip(0, 0.0, duration)], [_scene(0, 0.0, duration)])
        cues, _source, warnings = captions.build_cues(
            plan,
            style=style,
            segments=[{
                "index": 0, "start": 0.0, "end": duration, "text": "Hi",
            }],
        )
        assert len(cues) == 1
        assert cues[0]["text"] == "Hi"
        assert cues[0]["end"] - cues[0]["start"] <= captions.MAX_CUE + 0.001
        assert any("capped" in warning for warning in warnings)


def test_sparse_multiword_speech_stays_inside_max_duration():
    style = captions.resolve_style()
    plan = _plan([_clip(0, 0.0, 20.0)], [_scene(0, 0.0, 20.0)])
    cues, _source, warnings = captions.build_cues(
        plan,
        style=style,
        segments=[{
            "index": 0, "start": 0.0, "end": 20.0, "text": "Hello world",
        }],
    )
    assert cues
    assert all(cue["end"] - cue["start"] <= captions.MAX_CUE + 0.001 for cue in cues)
    assert any("capped" in warning for warning in warnings)


def test_sentence_split_keeps_decimals_and_abbreviations():
    assert captions.split_sentences("Pi is 3.14 today. Dr. Smith agrees.") == [
        "Pi is 3.14 today.",
        "Dr. Smith agrees.",
    ]
    assert captions.split_sentences("Version 2.0. Next.") == [
        "Version 2.0.", "Next.",
    ]
    assert captions.split_sentences("Use e.g. this. Fine.") == [
        "Use e.g. this.", "Fine.",
    ]
    assert captions.split_sentences("The U.S. team won. Yes.") == [
        "The U.S. team won.", "Yes.",
    ]


def test_emoji_zwj_sequences_are_not_split():
    text = "👩‍🌾" * 12
    lines = captions.wrap_lines(text, 8)
    assert len(lines) == 2
    assert "".join(lines) == text
    assert not any(line.endswith("\u200d") or line.startswith("\u200d") for line in lines)


def test_beat_sync_snaps_clips_before_caption_timing(tmp_path, monkeypatch):
    scenes = [_scene(0, 0.0, 3.1), _scene(1, 3.1, 3.1)]
    job = _job(scenes)
    job["source"]["duration"] = 10.0
    plan = _plan([
        {"scene": 0, "start": 0.0, "end": 3.1, "dur": 3.1, "role": "hook"},
        {"scene": 1, "start": 3.1, "end": 6.2, "dur": 3.1, "role": "beat"},
    ], scenes)
    monkeypatch.setattr(
        render.audio, "resolve_music_track",
        lambda scenes, clips, music: Path("/tmp/beat-track.mp3"),
    )
    monkeypatch.setattr(
        render.audio, "beat_grid",
        lambda track: {
            "bpm": 120.0,
            "beats": [round(index * 0.5, 3) for index in range(40)],
        },
    )
    synced, info = render.sync_beat_clips(
        plan, scenes, 10.0, {"beat_sync": True, "music": {}},
    )
    assert synced["_beat_snapped"] is True
    assert info["bpm"] == 120.0
    assert synced["clips"][0]["dur"] == pytest.approx(3.0)
    assert synced["clips"][1]["dur"] == pytest.approx(3.1)
    assert synced["total"] == pytest.approx(6.1)
    track = captions.build_track(
        job,
        synced,
        captions.resolve_style(),
        segments=[
            {"index": 0, "start": 0.0, "end": 3.1, "text": "First beat."},
            {"index": 1, "start": 3.1, "end": 6.2, "text": "Second beat."},
        ],
        job_dir=tmp_path / "beat-job",
    )
    assert [
        window["duration"] for window in track.clip_windows
    ] == pytest.approx([3.0, 3.1])
    assert track.cues[-1].end <= 6.1


def test_queue_uses_beat_synced_clips_for_artifact(tmp_path, monkeypatch):
    scenes = [
        _scene(0, 0.0, 3.1, speech="Beat one."),
        _scene(1, 3.1, 3.1, speech="Beat two."),
    ]
    job = _job(scenes, job_id="beat-queue-job")
    job["source"]["duration"] = 10.0
    jobs = tmp_path / "jobs"
    job_dir = jobs / job["id"]
    job_dir.mkdir(parents=True)
    (job_dir / "job.json").write_text(json.dumps(job), encoding="utf-8")
    monkeypatch.setattr(app, "JOBS", jobs)
    plan = _plan([
        {"scene": 0, "start": 0.0, "end": 3.1, "dur": 3.1, "role": "hook"},
        {"scene": 1, "start": 3.1, "end": 6.2, "dur": 3.1, "role": "beat"},
    ], scenes)
    synced = {
        **_plan([
            {"scene": 0, "start": 0.0, "end": 2.0, "dur": 2.0, "role": "hook"},
            {"scene": 1, "start": 2.0, "end": 4.0, "dur": 2.0, "role": "beat"},
        ], scenes),
        "_beat_snapped": True,
        "_beat_bpm": 120.0,
    }
    monkeypatch.setattr(
        render, "sync_beat_clips",
        lambda *args, **kwargs: (dict(synced), {"bpm": 120.0, "drift": -1.0}),
    )
    monkeypatch.setattr(app.render_pool, "submit", lambda *args, **kwargs: None)
    record = app._queue_render(
        job["id"], job, plan, "final", "9:16", None, True,
        {"beat_sync": True, "music": {}}, False,
    )
    manifest = artifacts.load_manifest(job_dir, record["artifact_id"])
    assert manifest is not None
    assert [
        clip["dur"] for clip in manifest["spec"]["clips"]
    ] == pytest.approx([2.0, 2.0])
    assert record["caption_count"] > 0
    assert manifest["spec"]["caption"]["cue_count"] == record["caption_count"]


def test_frame_quantized_clip_timing_matches_burn(tmp_path):
    scenes = [_scene(0, 0.0, 2.1), _scene(1, 2.02, 2.02)]
    job = _job(scenes)
    job["source"]["duration"] = 10.0
    plan = _plan([
        {"scene": 0, "start": 0.0, "end": 2.016, "dur": 2.016, "role": "hook"},
        {"scene": 1, "start": 2.02, "end": 4.04, "dur": 2.02, "role": "beat"},
    ], scenes)
    track = captions.build_track(
        job,
        plan,
        captions.resolve_style(),
        segments=[
            {"index": 0, "start": 0.0, "end": 2.016, "text": "First clip."},
            {"index": 1, "start": 2.02, "end": 4.04, "text": "Second clip."},
        ],
        job_dir=tmp_path / "capture-job",
    )
    assert track.clip_windows[0]["duration"] == pytest.approx(60 / 30)
    assert track.clip_windows[1]["duration"] == pytest.approx(61 / 30)
    assert track.clip_windows[1]["start"] == pytest.approx(2.02)
    second = next(cue for cue in track.cues if cue.text == "Second clip.")
    assert second.start == pytest.approx(2.0)
    assert second.end <= 2.0 + 61 / 30 + 0.001
    assert second.start != pytest.approx(2.016)


def test_tiny_cue_drop_is_warned():
    style = captions.resolve_style()
    warnings: list[str] = []
    window = {
        "index": 0, "start": 0.0, "end": 2.0, "duration": 2.0,
    }
    kept = captions._fit_clip_cues(
        [{
            "start": 0.0, "end": 0.005, "text": "x",
            "clip_index": 0, "scene": 0,
        }],
        window,
        style,
        warnings,
    )
    assert kept == []
    assert any("shorter than" in warning for warning in warnings)


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
    with pytest.raises(captions.CaptionValidationError):
        captions.validate_track(
            [{"start": 0.0, "end": 5.0, "text": "too long", "clip_index": 0}],
            style=style, total=5.0,
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


def test_vtt_uses_the_same_track_as_srt_and_burn(tmp_path):
    scenes = [_scene(0, 0.0, 5.0)]
    job = _job(scenes)
    plan = _plan([_clip(0, 0.0, 5.0)], scenes)
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    _write_transcript(job_dir, [{
        "start": 0.0, "end": 5.0,
        "text": "First line. Second line!",
    }])
    track = captions.build_track(
        job, plan, captions.resolve_style(), job_dir=job_dir,
    )
    app._attach_caption_track(plan, track)
    rows = cuts.plan_cues(plan, plan["clips"], scenes)
    assert [row["text"] for row in rows] == [cue.text for cue in track.cues]
    vtt = cuts.vtt(rows)
    assert vtt.startswith("WEBVTT")
    assert "00:00:00.000 -->" in vtt
    for cue in track.cues:
        assert cue.text in vtt
    assert [row[2] for row in render._caption_cues(plan, plan["clips"])] == [
        cue.text for cue in track.cues
    ]


def test_generic_export_builds_default_or_pinned_custom_track(tmp_path, monkeypatch):
    scenes = [_scene(0, 0.0, 4.0, speech="Hello. World.")]
    job = _job(scenes, job_id="export-job")
    jobs = tmp_path / "jobs"
    job_dir = jobs / job["id"]
    job_dir.mkdir(parents=True)
    (job_dir / "job.json").write_text(json.dumps(job), encoding="utf-8")
    plan = _plan([_clip(0, 0.0, 4.0)], scenes)
    custom = captions.build_track(
        job,
        plan,
        captions.resolve_style(overrides={"uppercase": True}),
        job_dir=job_dir,
    )
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.setattr(app, "_plan_for", lambda current, target, hook: plan)
    client = TestClient(app.app, base_url="http://127.0.0.1")
    default = client.get(f"/api/jobs/{job['id']}/export/srt?target=30")
    assert default.status_code == 200
    assert "Hello." in default.text
    assert "HELLO." not in default.text

    pinned = client.get(
        f"/api/jobs/{job['id']}/export/srt?target=30&caption_track_id={custom.id}",
    )
    assert pinned.status_code == 200
    assert "HELLO." in pinned.text
    pinned_vtt = client.get(
        f"/api/jobs/{job['id']}/export/vtt?target=30&caption_track_id={custom.id}",
    )
    assert pinned_vtt.status_code == 200
    assert pinned_vtt.text.startswith("WEBVTT")
    assert "HELLO." in pinned_vtt.text


def test_artifact_share_srt_survives_track_change_and_record_slotting(
    tmp_path, monkeypatch,
):
    scenes = [_scene(0, 0.0, 2.0), _scene(1, 5.0, 2.0)]
    job = _job(scenes, job_id="share-job")
    job["source"]["duration"] = 10.0
    jobs = tmp_path / "jobs"
    job_dir = jobs / job["id"]
    job_dir.mkdir(parents=True)
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.setattr(app, "SHARES", tmp_path / "shares.json")
    _write_transcript(job_dir, [
        {"start": 0.0, "end": 2.0, "text": "First source."},
        {"start": 5.0, "end": 7.0, "text": "Second source."},
    ])
    custom_plan = _plan([
        _clip(1, 5.0, 2.0),
        _clip(0, 0.0, 2.0),
    ], scenes)
    track_a = captions.build_track(
        job,
        custom_plan,
        captions.resolve_style(),
        segments=[
            {"index": 0, "start": 0.0, "end": 2.0, "text": "First source."},
            {"index": 1, "start": 5.0, "end": 7.0, "text": "Second source."},
        ],
        job_dir=job_dir,
    )
    artifact_a, manifest_a = _store_ready_artifact(
        job, job_dir, custom_plan, track_a,
    )
    pinned_srt = cuts.srt([cue.to_dict() for cue in track_a.cues])
    assert pinned_srt.index("Second source.") < pinned_srt.index("First source.")
    assert app._share_captions(job, artifact_a) == pinned_srt

    style_track = captions.build_track(
        job,
        custom_plan,
        captions.resolve_style(overrides={
            "font_size": 80, "color": "#FF0000",
        }),
        segments=[
            {"index": 0, "start": 0.0, "end": 2.0, "text": "First source."},
            {"index": 1, "start": 5.0, "end": 7.0, "text": "Second source."},
        ],
        job_dir=job_dir,
    )
    assert [cue.text for cue in style_track.cues] == [
        cue.text for cue in track_a.cues
    ]
    style_spec = _artifact_spec(job, custom_plan, style_track)
    assert artifacts.artifact_id(style_spec) != artifact_a

    job["renders"] = {"30:cap": artifacts.render_record(manifest_a)}
    (job_dir / "job.json").write_text(json.dumps(job), encoding="utf-8")
    token, _record = shares.create(job["id"], artifact_a, path=app.SHARES)
    found = app._share(token)
    assert found is not None and found[0]["artifact_id"] == artifact_a

    edited_cues = [cue.to_dict() for cue in track_a.cues]
    edited_cues[0]["text"] = "Changed pinned cue."
    track_b, changed = captions.edit_track(
        track_a, cues=edited_cues, job_dir=job_dir,
    )
    assert changed is True
    spec_b = _artifact_spec(job, custom_plan, track_b)
    artifact_b = artifacts.artifact_id(spec_b)
    assert artifact_b != artifact_a

    monkeypatch.setattr(app.render_pool, "submit", lambda *args, **kwargs: None)
    job_now = app.load_job(job["id"])
    app._queue_render(
        job["id"], job_now, custom_plan, "final", "9:16", None,
        True, None, False, preset=None, caption_margin=0.075,
        script_id=None, caption_track=track_b,
    )
    job_after = app.load_job(job["id"])
    assert job_after["renders"]["30:cap"]["artifact_id"] == artifact_b
    assert artifacts.load_manifest(job_dir, artifact_a)["status"] == "ready"
    assert artifacts.has_media(job_dir, artifact_a)
    assert app._share_captions(job_after, artifact_a) == pinned_srt
    found_after = app._share(token)
    assert found_after is not None
    assert found_after[0]["artifact_id"] == artifact_a
    assert app._share_captions(job_after, found_after[0]["artifact_id"]) == pinned_srt


def test_legacy_adoption_uses_stored_caption_track(tmp_path, monkeypatch):
    scenes = [_scene(0, 0.0, 4.0, speech="Old scene text.")]
    job = _job(scenes, job_id="legacy-track-job")
    jobs = tmp_path / "jobs"
    job_dir = jobs / job["id"]
    (job_dir / "renders").mkdir(parents=True)
    (job_dir / "renders" / "reel_30.mp4").write_bytes(b"legacy")
    (job_dir / "renders" / "reel_30.jpg").write_bytes(b"poster")
    monkeypatch.setattr(app, "JOBS", jobs)
    plan = _plan([_clip(0, 0.0, 4.0)], scenes)
    job["analysis"]["plans"] = {"30": plan}
    track = captions.build_track(
        job,
        plan,
        captions.resolve_style(),
        segments=[{
            "index": 0, "start": 0.0, "end": 4.0,
            "text": "Pinned legacy line.",
        }],
        job_dir=job_dir,
    )
    record = {
        "status": "ready", "target": 30, "quality": "final", "aspect": "9:16",
        "caption_margin": 0.075, "captions": True, "audio_sig": "",
        "path": "renders/reel_30.mp4", "poster": "renders/reel_30.jpg",
        "record_key": "30:cap", "updated": 1.0,
        "caption_track_id": track.id, "caption_style_id": track.style_id,
    }
    manifest = app._adopt_render_artifact(job, record, 30, "9:16")
    assert manifest is not None
    assert manifest["caption_source"] == "track"
    assert manifest["caption_track_id"] == track.id
    assert "caption_warning" not in manifest
    srt = artifacts.media_path(
        job_dir, manifest["artifact_id"], "captions.srt",
    ).read_text(encoding="utf-8")
    assert srt == cuts.srt([cue.to_dict() for cue in track.cues])
    assert "Pinned legacy line." in srt


def test_legacy_adoption_without_track_marks_regenerated_srt(tmp_path, monkeypatch):
    scenes = [_scene(0, 0.0, 4.0, speech="Regenerated legacy line.")]
    job = _job(scenes, job_id="legacy-no-track-job")
    jobs = tmp_path / "jobs"
    job_dir = jobs / job["id"]
    (job_dir / "renders").mkdir(parents=True)
    (job_dir / "renders" / "reel_30.mp4").write_bytes(b"legacy")
    (job_dir / "renders" / "reel_30.jpg").write_bytes(b"poster")
    monkeypatch.setattr(app, "JOBS", jobs)
    plan = _plan([_clip(0, 0.0, 4.0)], scenes)
    job["analysis"]["plans"] = {"30": plan}
    record = {
        "status": "ready", "target": 30, "quality": "final", "aspect": "9:16",
        "caption_margin": 0.075, "captions": True, "audio_sig": "",
        "path": "renders/reel_30.mp4", "poster": "renders/reel_30.jpg",
        "record_key": "30:cap", "updated": 1.0,
    }
    manifest = app._adopt_render_artifact(job, record, 30, "9:16")
    assert manifest is not None
    assert manifest["caption_source"] == "plan"
    assert "no pinned caption track" in manifest["caption_warning"]
    srt = artifacts.media_path(
        job_dir, manifest["artifact_id"], "captions.srt",
    ).read_text(encoding="utf-8")
    assert "Regenerated legacy line." in srt


def test_render_default_track_honours_caption_margin(tmp_path, monkeypatch):
    scenes = [_scene(0, 0.0, 4.0, speech="Margin line.")]
    job = _job(scenes, job_id="margin-job")
    jobs = tmp_path / "jobs"
    (jobs / job["id"]).mkdir(parents=True)
    monkeypatch.setattr(app, "JOBS", jobs)
    plan = _plan([_clip(0, 0.0, 4.0)], scenes)
    track = app._default_caption_track(job["id"], job, plan, margin=0.2)
    assert track.style["safe_zone"]["bottom"] == pytest.approx(0.2)
    other = app._default_caption_track(job["id"], job, plan, margin=0.075)
    assert other.style["safe_zone"]["bottom"] == pytest.approx(0.075)
    assert other.id != track.id


def test_caption_margin_applies_to_default_style_and_cache():
    default = app._caption_style_for(None, None, 0.2)
    assert default["safe_zone"]["bottom"] == pytest.approx(0.2)
    minimal = app._caption_style_for("minimal", None, 0.2)
    assert minimal["safe_zone"]["bottom"] == pytest.approx(0.12)
    assert minimal["safe_zone"]["left"] == pytest.approx(0.07)
    partial = captions.resolve_style(
        "minimal", overrides={"safe_zone": {"bottom": 0.2}},
    )
    assert partial["safe_zone"]["bottom"] == pytest.approx(0.2)
    assert partial["safe_zone"]["left"] == pytest.approx(0.07)
    assert partial["safe_zone"]["right"] == pytest.approx(0.07)
    saved = captions.normalize_style_settings({
        "styles": {"minimal": {"safe_zone": {"bottom": 0.2}}},
    })["styles"]["minimal"]
    assert saved["safe_zone"]["bottom"] == pytest.approx(0.2)
    assert saved["safe_zone"]["left"] == pytest.approx(0.07)
    assert saved["font_size"] == 46

    plan = _plan([_clip(0, 0.0, 3.0)], [_scene(0, 0.0, 3.0)])
    low = render._caption_cache_signature(plan, True, None, 0.075)
    high = render._caption_cache_signature(plan, True, None, 0.2)
    styled = render._caption_cache_signature(
        plan, True, captions.resolve_style(overrides={"color": "#FF0000"}), 0.075,
    )
    assert low != high
    assert low != styled


def test_settings_reject_malformed_caption_style_shapes(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(settings_store, "DATA", data)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", data / "settings.json")
    monkeypatch.setattr(settings_store, "SECRETS_PATH", data / "secrets.json")
    monkeypatch.setattr(app, "DATA", data)
    client = TestClient(app.app, base_url="http://127.0.0.1")
    for malformed in (
        None,
        [],
        {"styles": []},
        {"styles": None},
        {"styles": "not-a-map"},
        {"styles": {"broken": []}},
        {"default": []},
    ):
        response = client.post(
            "/api/settings", json={"settings": {"caption_styles": malformed}},
        )
        assert response.status_code == 400, (malformed, response.text)


def test_patch_rejects_overlong_text_and_unknown_tracks(tmp_path, monkeypatch):
    scenes = [_scene(0, 0.0, 4.0, speech="Short line.")]
    job = _job(scenes, job_id="patch-job")
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
    overlong = client.patch(
        f"/api/jobs/{job['id']}/captions/{track['id']}",
        json={"cues": [{
            "id": "c001", "start": 0.0, "end": 4.0,
            "text": "x" * 275, "clip_index": 0, "scene": 0,
        }]},
    )
    assert overlong.status_code == 400
    assert "style allows" in overlong.text

    reflowed = client.patch(
        f"/api/jobs/{job['id']}/captions/{track['id']}",
        json={"cues": [{
            "id": "c001", "start": 0.0, "end": 4.0,
            "text": "This line is deliberately long.",
            "clip_index": 0, "scene": 0,
        }]},
    )
    assert reflowed.status_code == 200, reflowed.text
    assert "\n" in reflowed.json()["track"]["cues"][0]["text"]
    new_id = reflowed.json()["track"]["id"]
    srt = client.get(f"/api/jobs/{job['id']}/captions/{new_id}/srt")
    assert "This line is deliberately" in srt.text

    missing = client.patch(
        f"/api/jobs/{job['id']}/captions/cap_missing",
        json={"overrides": {"color": "#000000"}},
    )
    assert missing.status_code == 404
    assert client.get(f"/api/jobs/{job['id']}/captions/cap_missing").status_code == 404
    assert client.get(
        f"/api/jobs/{job['id']}/captions/cap_missing/srt",
    ).status_code == 404
    with pytest.raises(captions.CaptionError):
        captions.track_path(tmp_path, "../escape")
    assert captions.load_track(tmp_path, "../escape") is None


def test_burn_never_truncates_prepared_lines(tmp_path, monkeypatch):
    captured: list[str] = []

    def capture_text(_draw, _xy, text, **_kwargs):
        captured.append(str(text))

    monkeypatch.setattr(render.ImageDraw.ImageDraw, "text", capture_text)
    style = captions.resolve_style(overrides={"max_lines": 2, "max_chars": 20})
    paths = render._caption_pngs(
        tmp_path,
        [(0.0, 1.0, "one\ntwo\nthree\nfour")],
        540,
        960,
        style=style,
    )
    assert len(paths) == 1
    assert captured == ["one", "two", "three", "four"]


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
