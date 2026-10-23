import json
import math
import os
import time

import pytest
from fastapi import HTTPException

import app
import audio
import pipeline
import render


def make_scene(index, start, dur, hook=50.0, score=50.0, deep=True, **extra):
    scene = {
        "id": index,
        "start": float(start),
        "end": float(start + dur),
        "dur": float(dur),
        "mid": float(start + dur / 2),
        "hook": hook,
        "score": score,
        "deep": deep,
        "visual_score": score,
        "motion_score": score,
        "audio_score": score,
        "text_score": 0.0,
        "ocr": "",
        "speech": "",
        "tags": [],
        "crop": {"cx": 0.5, "cy": 0.5},
        "crop_mode": "center",
    }
    scene.update(extra)
    return scene


def test_render_key_matches_ui_contract():
    assert app._render_key(30) == "30"
    assert app._render_key(30, "draft") == "30:draft"
    assert app._render_key(30, "final", "4:5") == "30:4x5"
    assert app._render_key(30, "final", "9:16", True) == "30:cap"
    assert app._render_key(30, "draft", "4:5", True) == "30:draft:4x5:cap"
    assert app._render_key(30, "final", "9:16", False, "abcd1234") == "30:aabcd1234"


def test_audio_signature_stable_and_sensitive():
    plan = {
        "mode": "full",
        "translate": {"target": "vi", "provider": "auto"},
        "voice": {"engine": "say", "voice": "Samantha", "rate": 1, "gain_db": 0},
        "music": {"source": "cc0", "prompt": "auto", "gain_db": -18, "duck": True},
    }
    first = app._audio_signature(plan)
    assert first and first == app._audio_signature(dict(plan))
    changed = {**plan, "translate": {"target": "en", "provider": "auto"}}
    assert app._audio_signature(changed) != first
    assert app._audio_signature(None) == ""
    assert app._audio_signature({"mode": "keep"}) == ""


def test_fnv1a_is_deterministic():
    assert app._fnv1a("") == "811c9dc5"
    assert app._fnv1a("a") == app._fnv1a("a")
    assert app._fnv1a("a") != app._fnv1a("b")


def test_scene_moods_and_music_pick():
    scenes = [
        make_scene(0, 0.0, 4.0, face=True),
        make_scene(1, 4.0, 4.0, face=True, tags=["motion"]),
        make_scene(2, 8.0, 4.0, face=True, tags=["motion"]),
    ]
    clips = [{"scene": 0}, {"scene": 1}, {"scene": 2}]
    moods = audio.scene_moods(scenes, clips)
    assert moods
    assert any(mood in moods for mood in ("upbeat", "warm", "calm"))
    tracks = [
        {"id": "a.mp3", "name": "calm piano", "moods": ["calm"]},
        {"id": "b.mp3", "name": "upbeat groove", "moods": ["upbeat"]},
    ]
    picked = audio.pick_music(tracks, ["upbeat"])
    assert picked and picked["id"] == "b.mp3"
    prompt = audio.music_prompt(moods, 30)
    assert "no vocals" in prompt


def test_music_listing_reads_assets(tmp_path, monkeypatch):
    directory = tmp_path / "cc0"
    directory.mkdir()
    (directory / "morning-calm-loop.mp3").write_bytes(b"x" * 64)
    (directory / "notes.txt").write_text("skip me")
    monkeypatch.setitem(audio.MUSIC_DIRS, "cc0", directory)
    tracks = audio.list_music("cc0")
    assert len(tracks) == 1
    assert tracks[0]["name"] == "morning-calm-loop"
    assert "calm" in tracks[0]["moods"]


def test_translate_identity_returns_input():
    lines = ["a", "b"]
    assert audio.translate_lines(lines, "zh", "zh") == lines
    assert audio.translate_lines(lines, "zh", "") == lines


def test_voice_sample_engine_registry(monkeypatch, tmp_path):
    calls = {}

    def fake_synth(engine, voice, text, output, rate=1.0, cancel_event=None):
        calls.update(engine=engine, voice=voice, text=text, rate=rate)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"RIFF" + b"0" * 1024)
        return output

    monkeypatch.setattr(audio, "synthesize_line", fake_synth)
    path = audio.voice_sample("say", "Samantha", "hello", tmp_path, rate=1.1)
    assert path.is_file()
    assert calls["engine"] == "say" and calls["text"] == "hello"


def test_engine_status_shape():
    status = audio.engine_status()
    assert set(status["voices"]) == {"say", "piper", "kokoro", "elevenlabs"}
    assert "stable-small" in status["music"]
    assert "demucs" in status["separation"]
    for entry in status["voices"].values():
        assert "available" in entry and "install" in entry


def test_deep_limit_env(monkeypatch):
    monkeypatch.setenv("VIBECUT_DEEP_SCENES", "120")
    assert pipeline._deep_limit() == 120
    monkeypatch.setenv("VIBECUT_DEEP_SCENES", "nonsense")
    assert pipeline._deep_limit() == 300


def test_select_deep_scenes_reads_short_video_fully():
    scenes = [make_scene(i, i * 2.0, 2.0) for i in range(40)]
    deep = pipeline.select_deep_scenes(scenes, duration=80.0, limit=10)
    assert deep == list(range(40))


def test_select_deep_scenes_caps_long_video():
    scenes = [make_scene(i, i * 3.0, 3.0) for i in range(900)]
    deep = pipeline.select_deep_scenes(scenes, duration=2700.0, limit=100)
    assert 0 < len(deep) <= 260
    assert deep == sorted(deep)


def test_cheap_rank_scores_are_bounded():
    scenes = [make_scene(i, i * 2.0, 2.0) for i in range(12)]
    for index, scene in enumerate(scenes):
        scene["motion_raw"] = index * 1.5
        scene["audio_mean"] = -30 + index
        scene["audio_peak"] = -20 + index
        scene["onset"] = index * 0.5
    pipeline.cheap_rank(scenes)
    for scene in scenes:
        assert 0.0 <= scene["cheap_score"] <= 100.0


def test_build_plan_respects_target_and_skips_black():
    scenes = [make_scene(i, i * 4.0, 4.0, hook=40 + i, score=40 + i) for i in range(40)]
    scenes[5]["black"] = True
    scenes[5]["hook"] = 99.0
    scenes[5]["score"] = 99.0
    plan = pipeline.build_plan(scenes, source_duration=160.0, target=30)
    assert plan["clip_count"] >= 2
    assert plan["total"] <= 30.2
    assert all(clip["scene"] != 5 for clip in plan["clips"])
    assert plan["clips"][0]["role"] == "hook"


def test_build_plan_can_force_an_explicit_hook():
    scenes = [make_scene(i, i * 4.0, 4.0, hook=40 + i, score=40 + i) for i in range(40)]
    plan = pipeline.build_plan(
        scenes, source_duration=160.0, target=15, hook_id=9, auto_hook_id=3,
    )
    assert plan["hook_scene"] == 9
    assert plan["auto"] is False


def test_build_plan_explains_hook_payoff_and_beats():
    scenes = [
        make_scene(i, i * 4.0, 4.0, hook=40 + i, score=40 + i,
                   speech=f"line {i}" if i % 3 == 0 else "")
        for i in range(40)
    ]
    plan = pipeline.build_plan(scenes, source_duration=160.0, target=30)
    assert plan["hook_why"].startswith("Hook score")
    assert "top" in plan["hook_why"]
    assert plan["payoff_why"] and "late beat" in plan["payoff_why"]
    assert all(clip.get("why") for clip in plan["clips"])
    assert plan["clips"][0]["why"] == plan["hook_why"]


def test_scene_note_uses_text_signals():
    scene = make_scene(1, 0.0, 2.0, speech="hello world", face=True)
    note = pipeline.scene_note(scene)
    assert "hello world" in note
    assert "face" in note


def test_transcript_endpoint_reads_segments(tmp_path, monkeypatch):
    job_dir = tmp_path / "tj"
    (job_dir / "transcript").mkdir(parents=True)
    (job_dir / "transcript" / "transcript.json").write_text(
        json.dumps({
            "language": "en",
            "text": "hello world",
            "segments": [
                {"start": 0.0, "end": 1.0, "text": "hello"},
                {"start": 1.0, "end": 2.0, "text": "  world  "},
            ],
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(app, "load_job", lambda job_id: {"id": job_id, "analysis": {}})
    monkeypatch.setattr(app, "_job_dir", lambda job_id: job_dir)
    result = app.job_transcript("tj")
    assert result["available"] is True
    assert result["language"] == "en"
    assert [segment["text"] for segment in result["segments"]] == ["hello", "world"]


def test_transcript_endpoint_falls_back_to_summary(tmp_path, monkeypatch):
    job_dir = tmp_path / "tj2"
    job_dir.mkdir()
    monkeypatch.setattr(
        app, "load_job",
        lambda job_id: {
            "id": job_id,
            "analysis": {"transcript": {"language": "zh", "text": "kept summary"}},
        },
    )
    monkeypatch.setattr(app, "_job_dir", lambda job_id: job_dir)
    result = app.job_transcript("tj2")
    assert result["available"] is False
    assert result["text"] == "kept summary"


def test_caption_cues_follow_the_cut():
    scenes = [
        make_scene(0, 0.0, 2.0, ocr="first line"),
        make_scene(1, 5.0, 2.0, speech="second line"),
    ]
    clips = [
        {"scene": 0, "start": 0.0, "end": 2.0, "dur": 2.0, "duration": 2.0, "role": "hook"},
        {"scene": 1, "start": 5.0, "end": 7.0, "dur": 2.0, "duration": 2.0, "role": "beat"},
    ]
    plan = {"_scenes": scenes, "clips": clips}
    cues = render._caption_cues(plan, clips)
    assert len(cues) == 2
    assert cues[0][2] == "first line"
    assert cues[1][0] == pytest.approx(2.0)
    assert cues[1][2] == "second line"


def test_segment_cache_key_changes_with_crop_and_quality():
    meta = {"fingerprint": "abc", "duration": 10.0, "size": 1000}
    scene = {"crop": {"cx": 0.5, "cy": 0.5}}
    base = render._segment_cache_key(meta, scene, 1.0, 30, 540, 960, "final", "libx264", True, False)
    same = render._segment_cache_key(meta, scene, 1.0, 30, 540, 960, "final", "libx264", True, False)
    moved = render._segment_cache_key(
        meta, {"crop": {"cx": 0.7, "cy": 0.5}}, 1.0, 30, 540, 960, "final", "libx264", True, False,
    )
    draft = render._segment_cache_key(meta, scene, 1.0, 30, 540, 960, "draft", "libx264", True, False)
    assert base == same
    assert base != moved
    assert base != draft


def _fake_job():
    scenes = [make_scene(i, i * 3.0, 3.0) for i in range(20)]
    return {
        "id": "testjob",
        "status": "ready",
        "source": {"duration": 60.0, "width": 1920, "height": 1080, "path": "/tmp/none.mp4", "name": "none.mp4"},
        "analysis": {"scenes": scenes, "hook_scene": 3, "deep_count": 20, "deep_scene_ids": list(range(20))},
        "renders": {},
    }


def test_custom_plan_trims_and_orders_clips():
    job = _fake_job()
    clips = [
        {"scene": 4, "start": 12.0, "end": 14.5, "role": "beat"},
        {"scene": 3, "start": 9.0, "end": 12.0, "role": "hook"},
    ]
    plan = app._custom_plan(job, 15, 3, clips)
    assert plan["clip_count"] == 2
    assert plan["clips"][0]["scene"] == 4
    assert plan["total"] == pytest.approx(5.5)
    assert plan["auto"] is False


def test_custom_plan_rejects_unknown_scene():
    job = _fake_job()
    with pytest.raises(HTTPException):
        app._custom_plan(job, 15, 3, [{"scene": 999, "start": 0, "end": 1}])


def test_custom_plan_rejects_too_short_clip():
    job = _fake_job()
    with pytest.raises(HTTPException):
        app._custom_plan(job, 15, 3, [{"scene": 1, "start": 3.0, "end": 3.05}])


def test_custom_plan_clamps_to_scene_bounds():
    job = _fake_job()
    plan = app._custom_plan(job, 15, 3, [{"scene": 2, "start": -5.0, "end": 99.0}])
    clip = plan["clips"][0]
    assert clip["start"] == 6.0
    assert clip["end"] == 9.0
    assert clip["dur"] == pytest.approx(3.0)


def test_dims_and_encoders():
    assert render._dims("9:16", "final") == (1080, 1920)
    assert render._dims("9:16", "draft") == (540, 960)
    assert render._dims("4:5", "final") == (1080, 1350)
    assert render._dims("16:9", "final") == (1920, 1080)
    assert render._choose_encoder("libx264") == "libx264"
    assert render._choose_encoder("videotoolbox") == "videotoolbox"


def test_frames_for_never_exceeds_source():
    assert render._frames_for(0.0, 2.0, 10.0) == 60
    assert render._frames_for(9.5, 2.0, 10.0) == 15
    assert render._frames_for(0.0, 0.01, 10.0) >= 1


def test_llm_rank_parses_response(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"response": "[7, 2, 9]"}'

    def fake_urlopen(request, timeout=None):
        return FakeResponse()

    monkeypatch.setenv("VIBECUT_LLM_URL", "http://127.0.0.1:11434/api/generate")
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    candidates = [{"scene": 2, "dur": 2.0, "hook": 50.0, "speech": "a"},
                  {"scene": 7, "dur": 3.0, "hook": 40.0, "ocr": "b"}]
    assert pipeline.llm_rank_hooks(candidates, 30) == [7, 2]


def test_llm_rank_returns_none_without_url(monkeypatch):
    monkeypatch.delenv("VIBECUT_LLM_URL", raising=False)
    assert pipeline.llm_rank_hooks([{"scene": 1}, {"scene": 2}]) is None


def test_caption_chunks_respects_width():
    chunks = render._caption_chunks("one two three four five six seven eight", width=12)
    assert all(len(chunk) <= 12 for chunk in chunks)
    assert " ".join(chunks) == "one two three four five six seven eight"


def test_clean_line_strips_fillers_and_markers():
    assert audio.clean_line("Um, so this is it") == "so this is it"
    assert audio.clean_line("uh hello") == "hello"
    assert audio.clean_line("嗯 那个，这就是 测试 [Music] 12:03") == "这就是 测试"
    assert audio.clean_line("（笑）你好世界") == "你好世界"


def test_estimate_and_trim_to_seconds():
    long_text = "hello world this is a very long line that will not fit the slot"
    fitted = audio.trim_to_seconds(long_text, 1.5, 1.0)
    assert fitted and fitted != long_text
    assert audio.estimate_seconds(fitted, 1.0) <= 1.7
    short = "hi there"
    assert audio.trim_to_seconds(short, 3.0, 1.0) == short


def test_build_script_dedupes_and_tags_emotion():
    scenes = [
        {"id": 0, "dur": 3.0, "tags": ["motion"], "audio_score": 80,
         "speech": "hello world this is a long line that should be trimmed because the slot is small"},
        {"id": 1, "dur": 2.0, "tags": ["subject"],
         "speech": "hello world this is a long line that should be trimmed because the slot is small"},
        {"id": 2, "dur": 2.0, "tags": ["text"], "ocr": "on screen text here"},
        {"id": 3, "dur": 2.0, "tags": [], "speech": ""},
    ]
    clips = [
        {"scene": 0, "duration": 2.0},
        {"scene": 1, "duration": 2.0},
        {"scene": 2, "duration": 2.0},
        {"scene": 3, "duration": 2.0},
    ]
    script = audio.build_script(scenes, clips)
    assert [line["scene"] for line in script] == [0, 2]
    assert script[0]["emotion"] == "energetic" and script[0]["shortened"] is True
    assert script[1]["from_ocr"] is True
    assert audio.estimate_seconds(script[0]["text"], script[0]["rate"]) <= 2.0


def test_refit_script_dedupes_translated_lines():
    lines = [
        {"scene": 1, "duration": 2.0, "rate": 1.0, "text": "hello world"},
        {"scene": 2, "duration": 2.0, "rate": 1.0, "text": "hello world"},
        {"scene": 3, "duration": 2.0, "rate": 1.0, "text": "a different line"},
    ]
    fitted = audio.refit_script(lines)
    assert [line["scene"] for line in fitted] == [1, 3]


def test_provider_order_prefers_ready_engine(monkeypatch):
    monkeypatch.setattr(audio, "argos_pair_ready", lambda source, target: True)
    monkeypatch.setattr(audio, "apple_pair_status", lambda source, target: "supported")
    monkeypatch.setattr(
        audio, "_module", lambda name: name in {"transformers", "torch"},
    )
    monkeypatch.delenv("VIBECUT_LLM_URL", raising=False)
    order = audio._provider_order("zh", "en", "auto")
    assert order[0] == "argos"
    assert "marian" in order


def test_provider_order_explicit_wins():
    assert audio._provider_order("zh", "en", "marian") == ["marian"]


def test_scene_emotion_labels():
    _, energetic = audio.scene_emotion({"tags": ["motion"]}, 2.0)
    _, calm = audio.scene_emotion({"tags": []}, 4.5)
    _, warm = audio.scene_emotion({"tags": ["subject"], "face": True}, 2.0)
    assert energetic > calm
    assert 0.9 <= warm <= 1.1


def test_ensure_scene_deep_trusts_legacy_scenes(tmp_path, monkeypatch):
    job = _fake_job()
    scene = job["analysis"]["scenes"][0]
    scene.pop("deep", None)

    def fail(*args, **kwargs):
        raise AssertionError("legacy scene should not be re-read")

    monkeypatch.setattr(pipeline, "read_scene", fail)
    app._ensure_scene_deep(job, scene)


def test_cleanup_storage_removes_old_jobs_and_cache(tmp_path, monkeypatch):
    import json
    import os
    import time

    jobs = tmp_path / "jobs"
    old = jobs / "oldjob"
    old.mkdir(parents=True)
    (old / "job.json").write_text(json.dumps({
        "id": "oldjob", "status": "ready", "updated": time.time() - 10 * 86400,
    }))
    fresh = jobs / "freshjob"
    fresh.mkdir(parents=True)
    (fresh / "job.json").write_text(json.dumps({
        "id": "freshjob", "status": "ready", "updated": time.time(),
    }))
    cache = tmp_path / "cache" / "segments"
    cache.mkdir(parents=True)
    stale = cache / "stale.mp4"
    stale.write_bytes(b"x")
    os.utime(stale, (time.time() - 10 * 86400, time.time() - 10 * 86400))

    monkeypatch.setattr(app, "DATA", tmp_path)
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.setattr(audio, "CACHE", tmp_path / "cache")
    monkeypatch.setenv("VIBECUT_RETENTION_DAYS", "1")
    monkeypatch.setenv("VIBECUT_CACHE_DAYS", "1")
    app.cleanup_storage()

    assert not old.exists()
    assert fresh.exists()
    assert not stale.exists()


def test_prune_cache_size_and_age(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    monkeypatch.setattr(audio, "CACHE", cache)
    segments = cache / "segments"
    segments.mkdir(parents=True)
    old = segments / "old.mp4"
    old.write_bytes(b"x" * 4096)
    os.utime(old, (time.time() - 30 * 86400, time.time() - 30 * 86400))
    new = segments / "new.mp4"
    new.write_bytes(b"y" * 4096)
    result = audio.prune_cache(max_gb=0, days=14)
    assert result["removed"] >= 1
    assert not old.exists()
    assert new.exists()
    usage = audio.cache_usage()
    assert usage["segments"]["files"] == 1


def test_kokoro_prefers_language_and_int8(tmp_path, monkeypatch):
    directory = tmp_path / "kokoro"
    directory.mkdir()
    for name in ("kokoro-v1.0.onnx", "kokoro-v1.0.int8.onnx", "kokoro-v1.1-zh.onnx",
                 "voices-v1.0.bin", "voices-v1.1-zh.bin"):
        (directory / name).write_bytes(b"x")
    monkeypatch.setitem(audio.VOICE_DIRS, "kokoro", directory)
    model, voices = audio._kokoro_files_for("af_heart")
    assert model.name == "kokoro-v1.0.int8.onnx"
    assert voices.name == "voices-v1.0.bin"
    zh_model, zh_voices = audio._kokoro_files_for("zf_xiaobei")
    assert zh_model.name == "kokoro-v1.1-zh.onnx"
    assert zh_voices.name == "voices-v1.1-zh.bin"


def test_stem_cache_is_flac():
    assert audio.stem_cache_path("abc", "no_vocals").suffix == ".flac"


def test_translate_memo_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(audio, "MEMO", tmp_path / "translate")
    audio._memo_put("zh", "en", "你好", "hello")
    assert audio._memo_get("zh", "en", "你好") == "hello"
    assert audio._memo_get("zh", "en", "别的") is None
    lines = audio.translate_lines(["你好"], "zh", "en")
    assert lines == ["hello"]


def test_prune_renders_keeps_newest_final(tmp_path, monkeypatch):
    job_dir = tmp_path / "job"
    renders = job_dir / "renders"
    renders.mkdir(parents=True)
    records = {}
    names = []
    for index, quality in enumerate(("draft", "final", "final")):
        name = f"reel_15_{quality}_{index}.mp4"
        (renders / name).write_bytes(b"video")
        names.append(name)
        records[f"15:{quality}:{index}"] = {
            "status": "ready", "quality": quality, "target": 15,
            "aspect": "9:16", "captions": False, "audio_sig": "sig",
            "updated": index + 1, "path": name, "poster": "",
        }
    job = {"id": "job", "status": "ready", "renders": records}
    monkeypatch.setattr(app, "_job_dir", lambda job_id: job_dir)
    monkeypatch.setenv("VIBECUT_KEEP_DRAFTS", "0")
    monkeypatch.setenv("VIBECUT_KEEP_RENDERS", "1")
    removed = app._prune_renders(job)
    assert len(removed) == 2
    assert list(job["renders"]) == ["15:final:2"]
    assert not (renders / "reel_15_draft_0.mp4").exists()
    assert not (renders / "reel_15_final_1.mp4").exists()
    assert (renders / "reel_15_final_2.mp4").exists()


def test_prune_renders_keeps_lone_draft(tmp_path, monkeypatch):
    job_dir = tmp_path / "job"
    renders = job_dir / "renders"
    renders.mkdir(parents=True)
    (renders / "reel_15_draft.mp4").write_bytes(b"video")
    job = {
        "id": "job", "status": "ready",
        "renders": {
            "15:draft": {
                "status": "ready", "quality": "draft", "target": 15,
                "aspect": "9:16", "captions": False, "audio_sig": "",
                "updated": 1, "path": "reel_15_draft.mp4", "poster": "",
            },
        },
    }
    monkeypatch.setattr(app, "_job_dir", lambda job_id: job_dir)
    monkeypatch.setenv("VIBECUT_KEEP_DRAFTS", "0")
    monkeypatch.setenv("VIBECUT_KEEP_RENDERS", "1")
    assert app._prune_renders(job) == []
    assert (renders / "reel_15_draft.mp4").exists()


def test_clean_job_files_keeps_source(tmp_path, monkeypatch):
    job_dir = tmp_path / "job"
    (job_dir / "thumbs").mkdir(parents=True)
    (job_dir / "thumbs" / "00000.jpg").write_bytes(b"thumb")
    (job_dir / "renders").mkdir()
    (job_dir / "renders" / "reel_15.mp4").write_bytes(b"video")
    (job_dir / "source.mp4").write_bytes(b"source")
    job = {
        "id": "job", "status": "ready", "renders": {"15": {"path": "reel_15.mp4"}},
        "analysis": {"scenes": [{"id": 0, "deep": True}], "deep_count": 1},
    }
    monkeypatch.setattr(app, "_job_dir", lambda job_id: job_dir)
    monkeypatch.setattr(app, "DATA", tmp_path)
    removed = app.clean_job_files(job, "workfiles")
    assert "thumbs" in removed
    assert (job_dir / "source.mp4").exists()
    assert (job_dir / "renders" / "reel_15.mp4").exists()
    assert job["analysis"]["scenes"][0]["deep"] is False
    removed_all = app.clean_job_files(job, "all")
    assert "renders" in removed_all
    assert job["renders"] == {}
    assert (job_dir / "source.mp4").exists()
