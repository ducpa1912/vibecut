import json
import math
import os
import time

import pytest
from fastapi import HTTPException

import app
import audio
import exports as cuts
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


# ---------------------------------------------------------------- 0.6.0 features


def test_rules_rewrite_smooth_and_viral(monkeypatch):
    monkeypatch.setattr(audio, "REWRITE", __import__("pathlib").Path("/tmp/vibecut-rewrite-test"))
    script = [
        {"scene": 0, "clip": 0, "role": "hook", "duration": 3.0, "rate": 1.0, "text": "orig hook"},
        {"scene": 1, "clip": 1, "role": "beat", "duration": 3.0, "rate": 1.0, "text": "orig beat"},
        {"scene": 2, "clip": 2, "role": "payoff", "duration": 4.0, "rate": 1.0, "text": "orig payoff"},
    ]
    literals = ["the garden is finally real, and it took years",
                "friends keep asking how",
                "come see the whole place"]
    smooth = audio._rules_rewrite(script, "en", "en", "smooth", literals)
    # hook stays connector-free, just fitted to its slot
    assert not smooth[0].startswith(("and", "but", "so", "then", "turns out"))
    assert literals[0].startswith(smooth[0]) or smooth[0] in literals[0]
    assert smooth[1].startswith(("and", "but", "so", "then", "turns out"))
    viral = audio._rules_rewrite(script, "en", "en", "viral", literals)
    assert viral[0] == "the garden is finally real"
    assert any(cta in viral[2] for cta in audio.CTAS["en"])


def test_adapt_script_literal_and_memo(tmp_path, monkeypatch):
    monkeypatch.setattr(audio, "REWRITE", tmp_path / "rewrite")
    monkeypatch.setattr(audio, "translate_lines", lambda lines, s, t, p="auto": [f"L:{x}" for x in lines])
    script = [{
        "scene": 3, "clip": 0, "role": "beat", "duration": 3.0, "rate": 1.0,
        "text": "original text",
    }]
    literal = audio.adapt_script(script, "zh", "en", "literal")
    assert literal[0]["text"] == "L:original text"
    assert literal[0]["rewrite"] == "literal"
    smooth = audio.adapt_script(script, "zh", "en", "smooth")
    assert smooth[0]["rewrite"] in {"rules", "cached"}
    assert smooth[0]["literal"] == "L:original text"
    assert list((tmp_path / "rewrite").rglob("*.txt"))


def test_music_mix_expression():
    clips = [{"duration": 2.0}, {"duration": 2.0}]
    assert audio.music_mix_expression(clips, [{"music_db": 0}, {"music_db": 0}], -18) is None
    expr = audio.music_mix_expression(clips, [{"music_db": 0}, {"music_db": -6}], -18)
    assert expr and "between(t,2.000,4.000)" in expr and "-24.00" in expr


def test_snap_clips_guard_and_apply():
    beats = {"bpm": 120.0, "beats": [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]}
    clips = [{"duration": 1.97}, {"duration": 1.97}]
    snapped, drift = audio.snap_clips(clips, beats)
    assert abs(drift) <= 0.4
    far = [{"duration": 5.0}, {"duration": 5.0}]
    unchanged, drift_far = audio.snap_clips(far, beats)
    assert drift_far == 0.0
    assert unchanged[0]["duration"] == 5.0


def test_beat_grid_click_track(tmp_path):
    import subprocess

    path = tmp_path / "click.wav"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi",
        "-i", "aevalsrc='0.6*gt(mod(t\\,0.5)\\,0.45)':d=8:s=48000",
        "-ac", "2", str(path),
    ], check=True)
    grid = audio.beat_grid(path)
    assert grid and grid["beats"]
    spacing = grid["beats"][1] - grid["beats"][0]
    assert 0.45 <= spacing <= 0.55  # ~120 BPM


def test_exports_shapes():
    scenes = [make_scene(0, 0.0, 2.0, speech="hello world"),
              make_scene(1, 5.0, 2.0, ocr="screen text")]
    clips = [
        {"scene": 0, "start": 0.0, "dur": 2.0, "role": "hook"},
        {"scene": 1, "start": 5.0, "dur": 2.0, "role": "payoff"},
    ]
    cues = cuts.plan_cues({}, clips, scenes)
    assert len(cues) == 2 and cues[1]["start"] == 2.0
    assert "00:00:00,000 --> 00:00:02,000" in cuts.srt(cues)
    assert cuts.vtt(cues).startswith("WEBVTT")
    edl = cuts.edl({}, clips, "source.mp4")
    assert "TITLE: source" in edl and "00:00:05:00" in edl
    xml = cuts.fcp7_xml({}, clips, "/tmp/source.mp4")
    assert "<xmeml" in xml and "<in>150</in>" in xml


def test_preset_render_options():
    body = app.PlanBody(target=30, preset="tiktok")
    quality, aspect, encoder, captions, audio_plan, preset, margin = app._render_options(body)
    assert preset == "tiktok" and aspect == "9:16" and captions is True
    assert margin == 0.12
    body = app.PlanBody(target=30, preset="landscape")
    _, aspect, _, captions, _, _, margin = app._render_options(body)
    assert aspect == "16:9" and captions is False and margin == 0.07


def test_hook_marker_and_render_key():
    auto_plan = {"auto": True, "hook_scene": 4}
    custom_plan = {"auto": False, "hook_scene": 9}
    assert app._hook_marker(auto_plan) is None
    assert app._hook_marker(custom_plan) == 9
    assert app._render_key(15, "draft", "9:16", False, "abc", 9) == "15:draft:aabc:h9"


def test_store_source_dedupe_and_links(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SOURCES", tmp_path / "sources")
    first = tmp_path / "a.bin"
    first.write_bytes(b"same bytes")
    second = tmp_path / "b.bin"
    second.write_bytes(b"same bytes")
    stored_a = app.store_source(first, ".mp4", "a.mp4")
    stored_b = app.store_source(second, ".mp4", "b.mp4")
    assert stored_a == stored_b
    assert len(list((tmp_path / "sources").iterdir())) == 1
    job_dir = tmp_path / "jobs" / "one"
    job_dir.mkdir(parents=True)
    linked = app.link_source(stored_a, job_dir, ".mp4")
    assert linked.is_file()
    assert linked.stat().st_nlink >= 2
    job_two = tmp_path / "jobs" / "two"
    job_two.mkdir(parents=True)
    app.link_source(stored_a, job_two, ".mp4")
    assert stored_a.stat().st_nlink >= 3


def test_arc_order_hook_first_payoff_last():
    scenes = [
        make_scene(0, 0.0, 3.0, motion_score=90),
        make_scene(1, 3.0, 3.0, motion_score=10, tags=["subject"]),
        make_scene(2, 6.0, 3.0, motion_score=60, speech="proof line"),
        make_scene(3, 9.0, 3.0, motion_score=20),
    ]
    clips = [
        {"scene": 0, "dur": 3.0, "role": "hook"},
        {"scene": 3, "dur": 3.0, "role": "beat"},
        {"scene": 1, "dur": 3.0, "role": "beat"},
        {"scene": 2, "dur": 3.0, "role": "payoff"},
    ]
    ordered = pipeline.arc_order(clips, scenes)
    assert ordered[0]["role"] == "hook"
    assert ordered[-1]["role"] == "payoff"
    middle = [clip["scene"] for clip in ordered[1:-1]]
    assert middle.index(1) < middle.index(3)  # calm setup before energetic


def test_license_strict_mode(tmp_path, monkeypatch):
    assets = tmp_path / "assets"
    track = assets / "music" / "bed.wav"
    track.parent.mkdir(parents=True)
    track.write_bytes(b"x")
    monkeypatch.setattr(audio, "ASSETS", assets)
    monkeypatch.setenv("VIBECUT_AUDIO_LICENSE", "strict")
    with pytest.raises(audio.AudioError):
        audio.ensure_licensed([track])
    sidecar = track.with_suffix(".wav.license.json")
    sidecar.write_text('{"license": "cc0"}')
    used = audio.ensure_licensed([track])
    assert used[0]["license"] == "cc0"
    monkeypatch.delenv("VIBECUT_AUDIO_LICENSE")


def test_save_generated_asset(tmp_path, monkeypatch):
    directory = tmp_path / "generated"
    monkeypatch.setitem(audio.MUSIC_DIRS, "generated", directory)
    source = tmp_path / "cache.wav"
    source.write_bytes(b"RIFF" + b"0" * 512)
    saved = audio.save_generated_asset(source, "stabilityai/stable-audio-open-small", "calm bed", 20.0)
    assert saved.is_file()
    license_file = saved.with_suffix(".wav.license.json")
    assert license_file.is_file()
    meta = json.loads(license_file.read_text())
    assert meta["license"] == "generated"
    assert "calm-bed" in saved.name


def test_transcribe_apple_none_without_helper(monkeypatch):
    monkeypatch.setattr(pipeline, "_apple_transcribe_helper", lambda: None)
    assert pipeline.transcribe_apple(__import__("pathlib").Path("/tmp/none.wav"), __import__("pathlib").Path("/tmp"), "en") is None
