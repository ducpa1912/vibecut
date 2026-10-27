"""Music brief, candidates, lock, cache, licence metadata and beat fitting.

Every engine is faked. No test reaches the network or needs a model pack.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException

import app
import audio
import music
import packs


def _wav(path: Path, payload: bytes = b"RIFF" + b"0" * 512) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


# ---------------------------------------------------------------- brief


def test_brief_has_editable_fields_and_four_second_tail():
    brief = music.build_brief("a calm warm story about a garden", 26, moods=["calm"])
    assert brief["mood"] == "calm"
    assert brief["genre"]
    assert brief["tempo"]["min"] < brief["tempo"]["max"]
    assert brief["instrumental"] is True
    assert brief["seconds"] == 26
    assert brief["duration"] == 30
    assert "no vocals" in brief["prompt"]
    assert brief["energy"]["shape"] == "hook_payoff"


def test_brief_hash_changes_with_fields_and_is_stable():
    first = music.build_brief("upbeat market", 20, moods=["upbeat"])
    same = music.build_brief("upbeat market", 20, moods=["upbeat"])
    other = music.build_brief("calm rain", 20, moods=["calm"])
    assert music.brief_hash(first) == music.brief_hash(same)
    assert music.brief_hash(first) != music.brief_hash(other)
    assert len(music.brief_hash(first)) == 32


def test_generation_cache_key_covers_provider_model_brief_and_seed():
    brief = music.build_brief("warm kitchen", 20, moods=["warm"])
    base = music.generation_cache_key("minimax", "music-3.0", brief, 7)
    assert base == music.generation_cache_key("minimax", "music-3.0", brief, 7)
    assert base != music.generation_cache_key("openrouter", "music-3.0", brief, 7)
    assert base != music.generation_cache_key("minimax", "other", brief, 7)
    assert base != music.generation_cache_key("minimax", "music-3.0", brief, 8)
    assert base != music.generation_cache_key(
        "minimax", "music-3.0", music.build_brief("calm rain", 20), 7,
    )


# ---------------------------------------------------------------- candidates


def test_generate_candidates_returns_two_parallel_seeded_tracks(monkeypatch, tmp_path):
    calls: list[dict] = []

    def fake_generate(descriptor, prompt, seconds, cancel_event=None, *, timeout=600,
                      seed=0, brief_hash=""):
        calls.append({"descriptor": descriptor, "seed": seed, "brief": brief_hash})
        path = _wav(tmp_path / f"candidate-{seed}.wav")
        return path

    monkeypatch.setattr(music, "generate_music", fake_generate)
    brief = music.build_brief("energetic run", 18, moods=["energetic"])
    candidates = music.generate_candidates(
        brief,
        routes=[
            {"provider": "minimax", "model": "music-3.0"},
            {"provider": "openrouter", "model": "google/lyria-3-clip-preview"},
        ],
        count=2,
    )
    assert len(candidates) == 2
    assert [item["seed"] for item in candidates] == [7, 8]
    assert len({item["cache_key"] for item in candidates}) == 2
    assert all(Path(item["path"]).is_file() for item in candidates)
    assert len(calls) == 2
    assert all(call["brief"] == music.brief_hash(brief) for call in calls)


def test_generate_candidates_keeps_successes_and_raises_when_all_fail(monkeypatch, tmp_path):
    def half_fail(descriptor, prompt, seconds, cancel_event=None, *, timeout=600,
                  seed=0, brief_hash=""):
        if seed == 7:
            raise audio.AudioError("provider down")
        return _wav(tmp_path / f"ok-{seed}.wav")

    monkeypatch.setattr(music, "generate_music", half_fail)
    brief = music.build_brief("calm", 12)
    candidates = music.generate_candidates(
        brief, routes=[{"provider": "minimax", "model": "music-3.0"}], count=2,
    )
    assert candidates[0]["error"] == "provider down"
    assert candidates[1]["error"] == ""
    assert Path(candidates[1]["path"]).is_file()

    monkeypatch.setattr(
        music, "generate_music",
        lambda *args, **kwargs: (_ for _ in ()).throw(audio.AudioError("down")),
    )
    with pytest.raises(audio.AudioError, match="down"):
        music.generate_candidates(
            brief, routes=[{"provider": "minimax", "model": "music-3.0"}], count=2,
        )


def test_generate_music_cache_is_keyed_by_seed_and_brief(monkeypatch, tmp_path):
    monkeypatch.setattr(audio, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(audio, "minimax_key", lambda: "key")
    calls: list[Path] = []

    def fake_minimax(prompt, seconds, output, model="", timeout=600):
        calls.append(Path(output))
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_bytes(b"RIFF" + b"0" * 4096)

    monkeypatch.setattr(audio, "_minimax_music", fake_minimax)
    monkeypatch.setattr(audio, "save_generated_asset", lambda *args, **kwargs: None)
    first = music.generate_music(
        "minimax:music-3.0", "calm bed", 10, seed=1, brief_hash="brief-a",
    )
    second = music.generate_music(
        "minimax:music-3.0", "calm bed", 10, seed=1, brief_hash="brief-a",
    )
    third = music.generate_music(
        "minimax:music-3.0", "calm bed", 10, seed=2, brief_hash="brief-a",
    )
    assert first == second
    assert first != third
    assert len(calls) == 2


# ---------------------------------------------------------------- fitting


def test_fit_plan_starts_on_downbeat_and_fades_at_story_end():
    grid = {"bpm": 120.0, "beats": [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]}
    plan = music.fit_plan(60.0, 30.0, grid)
    assert plan["in"] == 0.5
    assert plan["out"] == 30.5
    assert plan["loop"] is False
    assert plan["fade_out"] == 1.5
    assert plan["fade_out_start"] == 28.5
    assert plan["bar"] == 2.0


def test_fit_plan_loops_a_short_source_on_whole_bars():
    grid = {"bpm": 120.0, "beats": [0.1, 0.6, 1.1, 1.6, 2.1, 2.6, 3.1, 3.6]}
    plan = music.fit_plan(7.5, 30.0, grid)
    assert plan["loop"] is True
    assert plan["loop_seconds"] == 6.0
    assert plan["crossfade"] == music.DEFAULT_CROSSFADE_SECONDS
    assert plan["fade_out"] == 1.5


def test_fit_plan_without_beats_uses_plain_trim():
    plan = music.fit_plan(40.0, 20.0)
    assert plan["in"] == 0.0
    assert plan["loop"] is False
    assert plan["bar"] == 4.0


# ---------------------------------------------------------------- lock + metadata


def test_lock_track_copies_content_hash_and_keeps_history(tmp_path):
    job_dir = tmp_path / "job"
    first = _wav(tmp_path / "first.wav", b"RIFF-one")
    second = _wav(tmp_path / "second.wav", b"RIFF-two")
    one = music.lock_track(first, job_dir, source_type="library", brief={"mood": "calm"})
    two = music.lock_track(second, job_dir, source_type="upload")
    assert one["file_hash"] == music.sha256_file(first)
    assert one["locked"] is True
    assert (job_dir / one["file"]).is_file()
    assert len(music.locked_history(job_dir)) == 2
    assert music.resolve_locked_track(job_dir, one["file_hash"]).is_file()
    assert music.resolve_locked_track(job_dir, two["file_hash"]).is_file()
    assert music.resolve_locked_track(job_dir, "0" * 64) is None


def test_music_json_has_source_hash_licence_provider_brief_bpm_and_points(tmp_path):
    track = _wav(tmp_path / "bed.wav", b"RIFF-bed")
    Path(str(track) + ".license.json").write_text(json.dumps({
        "license": "cc", "attribution": "Artist", "attestation": "own recording",
    }))
    brief = music.build_brief("warm", 20, moods=["warm"])
    payload = music.music_json(
        track,
        source_type="library",
        brief=brief,
        provider={"id": "minimax", "model": "music-3.0", "request_id": "req-1"},
        licence={"type": "cc", "attestation": "own recording", "attribution": "Artist"},
        bpm=96.5,
        in_point=1.25,
        out_point=21.25,
        job_dir=tmp_path,
    )
    assert payload["schema"] == music.MUSIC_SCHEMA
    assert payload["source"] == "library"
    assert payload["file"] == "bed.wav"
    assert payload["file_hash"] == music.sha256_file(track)
    assert payload["licence"]["type"] == "cc"
    assert payload["licence"]["attestation"] == "own recording"
    assert payload["provider"]["id"] == "minimax"
    assert payload["provider"]["request_id"] == "req-1"
    assert payload["brief"]["mood"] == "warm"
    assert payload["bpm"] == 96.5
    assert payload["in"] == 1.25
    assert payload["out"] == 21.25


# ---------------------------------------------------------------- routes


def test_music_routes_brief_candidates_and_lock(tmp_path, monkeypatch):
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    job = {
        "id": "job1",
        "analysis": {
            "language": "en",
            "scenes": [{"id": 0, "speech": "A warm story about bread."}],
        },
    }
    plan = {
        "target": 30,
        "total": 28.0,
        "clips": [{"scene": 0, "duration": 28.0}],
    }
    monkeypatch.setattr(app, "load_job", lambda job_id: job)
    monkeypatch.setattr(app, "_job_dir", lambda job_id: job_dir)
    monkeypatch.setattr(app, "_plan_for", lambda *args, **kwargs: plan)

    brief = music.job_music_brief("job1", 30)
    assert brief["brief"]["instrumental"] is True
    assert brief["seconds"] == 28.0

    candidate = _wav(job_dir / "audio" / "candidate.wav", b"RIFF-candidate")
    monkeypatch.setattr(
        music, "generate_candidates",
        lambda brief, routes=None, count=2: [{
            "index": 0, "seed": 7, "path": str(candidate),
            "file": candidate.name, "error": "",
        }],
    )
    generated = music.job_music_candidates(
        "job1", music.CandidatesRequest(brief=brief["brief"]),
    )
    assert generated["candidates"][0]["path"] == str(candidate)
    served = music.job_music_candidate_file("job1", 0)
    assert Path(served.path) == candidate

    locked = music.job_music_lock(
        "job1", music.LockRequest(path=str(candidate), source_type="generated"),
    )
    assert locked["locked"]["locked"] is True
    assert len(locked["history"]) == 1


def test_music_route_rejects_paths_outside_allowed_roots(tmp_path, monkeypatch):
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    outside = _wav(tmp_path / "outside.wav")
    monkeypatch.setattr(app, "load_job", lambda job_id: {"id": job_id})
    monkeypatch.setattr(app, "_job_dir", lambda job_id: job_dir)
    with pytest.raises(HTTPException):
        music.job_music_lock("job1", music.LockRequest(path=str(outside)))


# ---------------------------------------------------------------- installed packs


def test_installed_packs_are_found_before_today_locations(tmp_path, monkeypatch):
    root = tmp_path / "packs"
    speech_bin = root / "speech" / "bin" / "mlx_whisper"
    speech_bin.parent.mkdir(parents=True)
    speech_bin.write_text("#!/bin/sh\n")
    speech_bin.chmod(0o755)
    voice_dir = root / "voice" / "models" / "kokoro"
    voice_dir.mkdir(parents=True)
    (voice_dir / "kokoro-v1.0.onnx").write_bytes(b"onnx")
    (voice_dir / "voices-v1.0.bin").write_bytes(b"voices")
    separation_bin = root / "separation" / "bin" / "demucs"
    separation_bin.parent.mkdir(parents=True)
    separation_bin.write_text("#!/bin/sh\n")
    separation_bin.chmod(0o755)
    monkeypatch.setenv(packs.ROOT_ENV, str(root))

    import stt
    import tts

    assert Path(stt._whisper_binary()) == speech_bin
    assert stt._whisper_command() == [str(speech_bin)]
    assert tts.kokoro_model_dir() == voice_dir
    model, voices = tts._kokoro_files_for("af_heart")
    assert model == voice_dir / "kokoro-v1.0.onnx"
    assert voices == voice_dir / "voices-v1.0.bin"
    assert packs.find_command("separation", "demucs") == separation_bin
    assert packs.installed_dir("speech") == root / "speech"
    assert packs.installed_dir("missing") is None


def test_no_installed_pack_falls_back_to_today_locations(tmp_path, monkeypatch):
    monkeypatch.setenv(packs.ROOT_ENV, str(tmp_path / "empty"))
    import stt
    import tts

    assert packs.installed_dir("speech") is None
    monkeypatch.setattr(stt, "_which", lambda name: None)
    monkeypatch.setattr(stt.importlib.util, "find_spec", lambda name: None)
    assert stt._whisper_binary() is None
    assert stt._whisper_command() is None
    assert tts.kokoro_model_dir() == audio.VOICE_DIRS["kokoro"]


def test_beats_route_reads_job_relative_upload_and_returns_times(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "JOBS", tmp_path)
    upload = _wav(tmp_path / "job1" / "audio" / "uploaded_music.wav")
    seen = []
    monkeypatch.setattr(
        audio, "beat_grid",
        lambda path: seen.append(path) or {"bpm": 120.0, "beats": [0.5, 1.0]},
    )
    result = app.audio_beats(track="audio/uploaded_music.wav", job_id="job1")
    assert seen == [upload.resolve()]
    assert result == {
        "track": "uploaded_music.wav", "bpm": 120.0, "beats": 2, "times": [0.5, 1.0],
    }


def test_beats_route_refuses_paths_outside_the_job(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "JOBS", tmp_path / "jobs")
    _wav(tmp_path / "secret.wav")
    (tmp_path / "jobs" / "job1").mkdir(parents=True)
    with pytest.raises(HTTPException) as exc:
        app.audio_beats(track="../../secret.wav", job_id="job1")
    assert exc.value.status_code == 404
