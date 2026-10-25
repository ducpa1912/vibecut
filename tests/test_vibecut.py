import io
import json
import math
import os
import stat
import time
import urllib.error
import wave

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app
import audio
import exports as cuts
import pipeline
import render
import settings_store


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
    assert set(status["voices"]) == {
        "say", "piper", "kokoro", "elevenlabs", "openai", "groq", "deepgram",
        "cartesia", "minimax", "fish", "gemini",
    }
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
    aspect_crop = render._segment_cache_key(
        meta, scene, 1.0, 30, 540, 960, "final", "libx264", True, False,
        {"cx": 0.5, "cy": 0.8},
    )
    assert base == same
    assert base != moved
    assert base != draft
    assert base != aspect_crop

def test_crop_center_bilateral():
    portrait = {
        "attention": {
            "face": {"x": 0.4, "y": 0.8, "w": 0.1, "h": 0.1, "confidence": 0.9},
            "salient": None,
        },
    }
    cx, cy = pipeline.crop_center(portrait, 1080, 1920, 16 / 9)
    assert cx == 0.5 and 0.7 <= cy <= 0.85
    cx, cy = pipeline.crop_center(portrait, 1080, 1920, 9 / 16)
    assert (cx, cy) == (0.5, 0.5)

    landscape = {
        "attention": {
            "face": {"x": 0.2, "y": 0.4, "w": 0.1, "h": 0.1, "confidence": 0.9},
            "salient": None,
        },
    }
    cx, cy = pipeline.crop_center(landscape, 1920, 1080, 9 / 16)
    assert 0.1 <= cx <= 0.3 and cy == 0.5

    square = {
        "attention": {
            "face": {"x": 0.45, "y": 0.8, "w": 0.1, "h": 0.1, "confidence": 0.9},
            "salient": None,
        },
    }
    cx, cy = pipeline.crop_center(square, 1000, 1000, 16 / 9)
    assert cx == 0.5 and 0.7 <= cy <= 0.88


def test_score_scenes_stores_all_aspect_crops():
    scene = make_scene(0, 0.0, 3.0)
    scene.update({
        "visual": {"sharp": 60.0, "bright": 0.5, "contrast": 40.0, "saturation": 50.0, "color": 40.0},
        "faces": [{"x": 0.4, "y": 0.8, "w": 0.12, "h": 0.12, "confidence": 0.9}],
        "salient": [],
        "motion_raw": 20.0,
        "audio_mean": -20.0,
        "audio_peak": -10.0,
        "onset": 1.0,
    })
    pipeline.score_scenes([scene], 1080, 1920)
    assert set(scene["crops"]) == set(pipeline.ASPECT_RATIOS)
    assert scene["crop"] == scene["crops"]["9:16"]
    assert scene["crops"]["16:9"]["cy"] > 0.5
    assert scene["crop_modes"]["16:9"] == "smart"
    assert "attention" in scene

    pipeline.score_scenes([scene], 1080, 1920)
    assert "attention" in scene
    assert scene["crops"]["16:9"]["cy"] > 0.5


def test_render_scene_crop_uses_aspect():
    meta = {"width": 1080, "height": 1920, "fingerprint": "abc", "duration": 10.0}
    scene = {
        "crop": {"cx": 0.5, "cy": 0.5},
        "crops": {"16:9": {"cx": 0.5, "cy": 0.8}},
        "attention": {"face": {"x": 0.45, "y": 0.8, "w": 0.1, "h": 0.1, "confidence": 0.9}},
    }
    assert render._scene_crop(scene, "16:9", meta, 1920, 1080) == {"cx": 0.5, "cy": 0.8}
    assert render._scene_crop(scene, "9:16", meta, 1080, 1920) == {"cx": 0.5, "cy": 0.5}


def test_opencode_direct_api_payload(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["auth"] = request.get_header("Authorization")
        captured["session"] = request.get_header("X-opencode-session")
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse(json.dumps({
            "choices": [{"message": {"content": '{"ok": true}'}}],
        }).encode("utf-8"))

    monkeypatch.setattr(audio, "opencode_key", lambda: "test-project-key")
    monkeypatch.setattr(audio.urllib.request, "urlopen", fake_urlopen)
    answer = audio._opencode_http_text("hello")
    assert answer == '{"ok": true}'
    assert captured["url"] == audio.OPENCODE_URL
    assert captured["auth"] == "Bearer test-project-key"
    assert captured["session"].startswith("vibecut-")
    assert captured["body"]["model"] == "deepseek-v4.1-flash"
    assert "reasoning_effort" not in captured["body"]
    assert captured["body"]["thinking"] == {"type": "disabled"}
    assert "response_format" not in captured["body"]


def test_opencode_direct_json_mode_changes_request(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=0):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse(json.dumps({
            "choices": [{"message": {"content": '{"ok": true}'}}],
        }).encode("utf-8"))

    monkeypatch.setattr(audio, "opencode_key", lambda: "test-project-key")
    monkeypatch.setattr(audio.urllib.request, "urlopen", fake_urlopen)
    assert audio._opencode_http_text("hello", json_mode=True) == '{"ok": true}'
    assert captured["body"]["response_format"] == {"type": "json_object"}


def test_opencode_length_empty_retries_reasoning_off(monkeypatch):
    captured = []

    def fake_urlopen(request, timeout=0):
        captured.append(json.loads(request.data.decode("utf-8")))
        if len(captured) == 1:
            return FakeResponse(json.dumps({
                "choices": [{
                    "message": {"content": ""},
                    "finish_reason": "length",
                }],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 120,
                    "completion_tokens_details": {"reasoning_tokens": 120},
                },
            }).encode("utf-8"))
        return FakeResponse(json.dumps({
            "choices": [{
                "message": {"content": '{"ok": true}'},
                "finish_reason": "stop",
            }],
        }).encode("utf-8"))

    monkeypatch.setattr(audio, "opencode_key", lambda: "test-project-key")
    monkeypatch.setattr(audio.urllib.request, "urlopen", fake_urlopen)
    assert audio._opencode_http_text("hello", max_tokens=120) == '{"ok": true}'
    assert len(captured) == 2
    assert "reasoning_effort" not in captured[0]
    assert captured[1]["reasoning_effort"] == "none"
    assert captured[1]["max_tokens"] > captured[0]["max_tokens"]


def test_opencode_length_empty_error_names_reasoning(monkeypatch):
    def fake_urlopen(request, timeout=0):
        return FakeResponse(json.dumps({
            "choices": [{
                "message": {"content": ""},
                "finish_reason": "length",
            }],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 120,
                "completion_tokens_details": {"reasoning_tokens": 120},
            },
        }).encode("utf-8"))

    monkeypatch.setattr(audio, "opencode_key", lambda: "test-project-key")
    monkeypatch.setattr(audio.urllib.request, "urlopen", fake_urlopen)
    assert audio._opencode_http_text("hello", max_tokens=120) is None
    assert "finish_reason=length" in audio.OPENCODE_LAST_ERROR
    assert "reasoning_tokens=120" in audio.OPENCODE_LAST_ERROR
    assert "reasoning-off retry" in audio.OPENCODE_LAST_ERROR


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


def test_llm_rank_uses_admin_routes(monkeypatch):
    calls = []

    def fake_workflow(workflow, prompt, **kwargs):
        calls.append((workflow, prompt, kwargs))
        return "[7, 2, 9]"

    monkeypatch.setattr(pipeline, "llm_available", lambda: True)
    monkeypatch.setattr(audio, "_workflow_text", fake_workflow)
    candidates = [{"scene": 2, "dur": 2.0, "hook": 50.0, "speech": "a"},
                  {"scene": 7, "dur": 3.0, "hook": 40.0, "ocr": "b"}]
    assert pipeline.llm_rank_hooks(candidates, 30) == [7, 2]
    assert calls[0][0] == "hook_rank"
    assert calls[0][2]["json_mode"] is True


def test_llm_rank_returns_none_without_available_route(monkeypatch):
    monkeypatch.setattr(pipeline, "llm_available", lambda: False)
    assert pipeline.llm_rank_hooks(
        [{"scene": 1, "dur": 1.0, "hook": 1.0}, {"scene": 2, "dur": 1.0, "hook": 1.0}]
    ) is None


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
    assert script[0]["emotion"] == "energetic" and script[0]["shortened"] is False
    assert script[1]["from_ocr"] is True
    assert script[0]["text"].endswith(".")


def test_refit_script_dedupes_translated_lines():
    lines = [
        {"scene": 1, "duration": 2.0, "rate": 1.0, "text": "hello world"},
        {"scene": 2, "duration": 2.0, "rate": 1.0, "text": "hello world"},
        {"scene": 3, "duration": 2.0, "rate": 1.0, "text": "a different line"},
    ]
    fitted = audio.refit_script(lines)
    assert [line["scene"] for line in fitted] == [1, 3]


def test_provider_order_prefers_ready_engine(monkeypatch):
    monkeypatch.setattr(audio, "opencode_available", lambda: False)
    monkeypatch.setattr(audio, "openrouter_available", lambda: False)
    monkeypatch.setattr(audio, "apple_pair_status", lambda source, target: "installed")
    monkeypatch.setattr(audio, "argos_pair_ready", lambda source, target: False)
    order = audio._provider_order("zh", "en", "auto")
    assert order == ["apple_fm"]


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
    named_zh_model, named_zh_voices = audio._kokoro_files_for("zf_xiaobei")
    assert named_zh_model.name == "kokoro-v1.0.int8.onnx"
    assert named_zh_voices.name == "voices-v1.0.bin"
    zh_model, zh_voices = audio._kokoro_files_for("zf_001")
    assert zh_model.name == "kokoro-v1.1-zh.onnx"
    assert zh_voices.name == "voices-v1.1-zh.bin"


def test_stem_cache_is_flac():
    assert audio.stem_cache_path("abc", "no_vocals").suffix == ".flac"


def test_translate_memo_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(audio, "MEMO", tmp_path / "translate")
    audio._memo_put("zh", "en", "你好", "hello")
    assert audio._memo_get("zh", "en", "你好") == "hello"
    assert audio._memo_get("zh", "en", "你好", "opencode") is None
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
    monkeypatch.setattr(audio, "opencode_available", lambda: False)
    monkeypatch.setattr(audio, "openrouter_available", lambda: False)
    seen = {}

    def fake_translate(lines, source, target, provider="auto"):
        seen["provider"] = provider
        return [f"L:{x}" for x in lines]

    monkeypatch.setattr(audio, "translate_lines", fake_translate)
    monkeypatch.setattr(audio, "_rewrite_candidates", lambda: ["rules"])
    script = [{
        "scene": 3, "clip": 0, "role": "beat", "duration": 3.0, "rate": 1.0,
        "text": "original text",
    }]
    literal = audio.adapt_script(script, "zh", "en", "literal", "opencode")
    assert literal[0]["text"] == "L:original text"
    assert seen["provider"] == "opencode"
    assert literal[0]["rewrite"] == "literal"
    smooth = audio.adapt_script(script, "zh", "en", "smooth")
    assert smooth[0]["rewrite"] == "rules"
    assert smooth[0]["literal"] == "L:original text"
    assert not list((tmp_path / "rewrite").rglob("*.txt"))


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

    pytest.importorskip("librosa")
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


# ---------------------------------------------------------------- transcript context


def test_window_text_uses_complete_segments():
    segments = [
        {"start": 12.9, "end": 16.8, "text": "friends keep asking about the garden"},
        {"start": 16.8, "end": 20.5, "text": "and how much work it really takes"},
        {"start": 40.0, "end": 44.0, "text": "unrelated later sentence"},
    ]
    text = audio.window_text(segments, 13.0, 17.0)
    assert "friends keep asking" in text
    assert "unrelated" not in text
    assert audio.window_text([], 0, 1) == ""


def test_transcript_context_has_full_text_and_beats():
    segments = [
        {"start": 0.0, "end": 2.0, "text": "first line about the product"},
        {"start": 2.0, "end": 4.0, "text": "second line with 42 uses"},
    ]
    scenes = [make_scene(0, 0.0, 2.0), make_scene(1, 2.0, 2.0)]
    clips = [
        {"scene": 0, "role": "hook", "duration": 2.0},
        {"scene": 1, "role": "beat", "duration": 2.0},
    ]
    context = audio.transcript_context(segments, clips, scenes, "en")
    assert "first line about the product" in context["full_text"]
    assert context["beats"][0]["role"] == "hook"
    assert "first line" in context["beats"][0]["source"]
    assert context["beats"][1]["seconds"] == 1.75


def test_build_script_prefers_transcript_window():
    scenes = [make_scene(0, 10.0, 5.0, speech="truncated scene speech fragment")]
    clips = [{"scene": 0, "duration": 5.0, "role": "beat"}]
    segments = [{"start": 9.5, "end": 15.0, "text": "the complete sentence from the transcript"}]
    script = audio.build_script(scenes, clips, segments=segments)
    assert script and script[0]["text"] == "the complete sentence from the transcript."
    without = audio.build_script(scenes, clips)
    assert without[0]["text"].startswith("truncated scene speech")


def test_adapt_script_passes_context_to_llm(monkeypatch, tmp_path):
    monkeypatch.setattr(audio, "REWRITE", tmp_path / "rewrite")
    captured: dict = {}

    def fake_llm(script, source, target, mode, literal, context=None):
        captured["context"] = context
        captured["literal"] = literal
        return [f"rewritten {index}" for index in range(len(script))]

    monkeypatch.setattr(audio, "_rewrite_ollama", fake_llm)
    monkeypatch.setattr(audio, "translate_lines", lambda lines, s, t, p="auto": [f"L:{x}" for x in lines])
    script = [{
        "scene": 0, "clip": 0, "role": "hook", "duration": 3.0, "rate": 1.0,
        "text": "original",
    }]
    context = {"full_text": "the whole video transcript", "beats": [{"scene": 0, "source": "original"}]}
    result = audio.adapt_script(script, "zh", "en", "viral", "llm", context)
    assert captured["context"]["full_text"] == "the whole video transcript"
    assert result[0]["text"] == "rewritten 0"
    # memo key depends on the context
    files_first = len(list((tmp_path / "rewrite").rglob("*.txt")))
    other = {"full_text": "different transcript", "beats": []}
    audio.adapt_script(script, "zh", "en", "viral", "llm", other)
    assert len(list((tmp_path / "rewrite").rglob("*.txt"))) > files_first


def test_char_cut_stays_on_word_boundary():
    cut = audio._char_cut("responsive plants need good soil", 1.0, 1.0)
    assert not cut.endswith(("respon", "responsi"))
    assert "responsive" in cut or cut in "responsive plants need good soil"


def test_read_transcript_roundtrip(tmp_path):
    job_dir = tmp_path / "job"
    (job_dir / "transcript").mkdir(parents=True)
    (job_dir / "transcript" / "transcript_apple.json").write_text(json.dumps({
        "language": "zh-CN",
        "segments": [{"start": 0.0, "end": 1.5, "text": "你好世界"}],
    }), encoding="utf-8")
    segments = pipeline.read_transcript(job_dir)
    assert segments and segments[0]["text"] == "你好世界"


# ---------------------------------------------------------------- automation mixer


def test_automation_expression_smooth_and_anchored():
    expr = audio.automation_expression([[0, 0], [4, -6], [8, 0]], 10.0)
    assert expr and "if(lt(t,4.000)" in expr and "if(lt(t,8.000)" in expr
    assert "cos(PI" in expr
    assert "if(lt(t,10.000)" in expr  # implicit 100% end anchor
    single = audio.automation_expression([[2, -3]], 10.0)
    assert single and "cos(PI" in single and "if(lt(t,0.000)" in single
    assert audio.automation_expression([], 10.0) is None
    assert audio.automation_expression([[5, 0]], 10.0) is None  # flat 100%
    clamped = audio.automation_expression([[2, -90]], 10.0)
    assert "(-24.00)" in clamped


def test_reel_envelope_slices_source():
    envelope = [-30.0 + index for index in range(20)]  # 1 dB step, 0.25s buckets
    clips = [{"start": 0.0, "duration": 1.0}, {"start": 2.0, "duration": 1.0}]
    points = audio.reel_envelope(envelope, clips, bucket_seconds=0.25)
    assert points
    assert points[0][0] == 0.0
    assert points[-1][0] <= 2.0
    assert all(isinstance(item[1], float) for item in points)


def test_retrieve_lines_prefers_relevant_sentence():
    text = (
        "The garden took three years to grow and it was hard work. "
        "Friends kept asking how much effort it really takes. "
        "The soil mix matters more than the fertilizer brand. "
        "Watering in the morning keeps the roots healthy. "
        "The payoff is picking fruit on a quiet morning. "
        "Follow for more garden tours."
    )
    lines = audio.retrieve_lines(text, "fertilizer soil mix", limit=2)
    assert any("soil mix" in line for line in lines)
    assert len(lines) <= 2


def test_story_brief_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(audio, "BRIEFS", tmp_path / "brief")
    calls = {"count": 0}

    def fake_llm(workflow, prompt, **kwargs):
        calls["count"] += 1
        return '{"topic": "garden", "audience": "hobbyists", "promise": "easy growing"}'

    monkeypatch.setattr(audio, "_workflow_text", fake_llm)
    first = audio.story_brief("x" * 200, "en")
    assert first and first["topic"] == "garden"
    second = audio.story_brief("x" * 200, "en")
    assert second == first
    assert calls["count"] == 1


def test_rewrite_mlx_prompt_uses_brief_and_relevant(monkeypatch, tmp_path):
    monkeypatch.setattr(audio, "REWRITE", tmp_path / "rewrite")
    captured = {}

    def fake_llm(prompt, provider="auto"):
        captured["prompt"] = prompt
        return json.dumps(["hook rewrite", "beat rewrite"])

    monkeypatch.setattr(audio, "_llm_text", fake_llm)
    monkeypatch.setattr(audio, "mlx_lm_available", lambda: True)
    script = [
        {"scene": 0, "role": "hook", "duration": 3.0, "rate": 1.0, "text": "hook"},
        {"scene": 1, "role": "beat", "duration": 3.0, "rate": 1.0, "text": "beat"},
    ]
    context = {
        "full_text": "source text",
        "target_text": "Sentence one about the soil mix. Sentence two about watering. Sentence three about fruit.",
        "brief": {"topic": "garden", "promise": "easy"},
        "aesthetic": {"moods": ["calm"], "pace": "measured"},
        "beats": [
            {"scene": 0, "role": "hook", "seconds": 2.75, "source": "hook source"},
            {"scene": 1, "role": "beat", "seconds": 2.75, "source": "beat source"},
        ],
    }
    result = audio._rewrite_mlx(script, "zh", "en", "viral", ["hook literal", "beat literal"], context)
    assert result and result[0] == "hook rewrite"
    assert "STORY BRIEF" in captured["prompt"]
    assert "RELEVANT VOICE SCRIPT LINES" in captured["prompt"]
    assert "BEAT SLOTS" in captured["prompt"]
    assert '"max_chars"' in captured["prompt"]
    assert '"max_words"' in captured["prompt"]
    assert "VIDEO AESTHETIC" in captured["prompt"]


def test_adapt_script_rewrite_provider_routing(monkeypatch, tmp_path):
    monkeypatch.setattr(audio, "REWRITE", tmp_path / "rewrite")
    called = {}

    def fake_mlx(script, source, target, mode, literal, context=None):
        called["mlx"] = True
        return [f"mlx {index}" for index in range(len(script))]

    def fake_ollama(script, source, target, mode, literal, context=None):
        called["ollama"] = True
        return ["ollama line"]

    monkeypatch.setattr(audio, "_rewrite_mlx", fake_mlx)
    monkeypatch.setattr(audio, "_rewrite_ollama", fake_ollama)
    monkeypatch.setattr(audio, "translate_lines", lambda lines, s, t, p="auto": [f"L:{x}" for x in lines])
    script = [{"scene": 0, "role": "hook", "duration": 3.0, "rate": 1.0, "text": "orig"}]
    result = audio.adapt_script(script, "zh", "en", "smooth", "auto", None, "mlx")
    assert called.get("mlx") and not called.get("ollama")
    assert result[0]["text"] == "mlx 0"
    assert result[0]["rewrite"] == "mlx"


def test_rewrite_models_shape():
    models = audio.rewrite_models()
    ids = {model["id"] for model in models}
    assert {"mlx", "ollama", "apple"} <= ids
    for model in models:
        assert "available" in model and "size_mb" in model


# ---------------------------------------------------------------- 0.7.0 cloud config


class FakeResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


def test_settings_roundtrip_masks_secrets(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_store, "DATA", tmp_path)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(settings_store, "SECRETS_PATH", tmp_path / "secrets.json")
    for name in settings_store.ENV_KEYS.values():
        for env_name in name:
            monkeypatch.delenv(env_name, raising=False)

    settings_store.save_settings({
        "opencode": {"model": "deepseek-v4.1-flash", "variant": "low"},
        "stt": {"provider": "groq"},
    })
    settings_store.save_secrets({"groq": "gsk-test-value"})
    state = settings_store.public_state()

    assert state["settings"]["opencode"]["model"] == "deepseek-v4.1-flash"
    assert state["settings"]["stt"]["provider"] == "groq"
    assert state["secrets"]["groq"] is True
    assert state["secrets"]["openai"] is False
    assert "gsk-test-value" not in json.dumps(state)
    assert stat.S_IMODE((tmp_path / "secrets.json").stat().st_mode) == 0o600
    assert settings_store.get_secret("groq") == "gsk-test-value"

    monkeypatch.setenv("GROQ_API_KEY", "env-wins")
    assert settings_store.get_secret("groq") == "env-wins"


def test_opencode_service_pins_model_and_low_variant(monkeypatch):
    calls = []

    class Result:
        def __init__(self, payload):
            self.returncode = 0
            self.stdout = json.dumps(payload)
            self.stderr = ""

    def fake_run(command, capture_output=None, text=None, timeout=None):
        calls.append(command)
        if command[2:4] == ["post", "/api/session"]:
            return Result({"data": {"id": "ses_test"}})
        if command[2] == "post" and "/generate" in command[3]:
            return Result({"data": {"text": "{\"ok\": true}"}})
        return Result({"data": True})

    monkeypatch.setattr(audio, "opencode_bin", lambda: "/usr/local/bin/opencode")
    monkeypatch.setattr(audio, "opencode_key", lambda: "")
    monkeypatch.setattr(settings_store, "load_settings", lambda: {
        "opencode": {
            "enabled": True,
            "model": "deepseek-v4.1-flash",
            "variant": "low",
            "use_rewrite": True,
            "use_brief": True,
            "use_translate": False,
        },
    })
    monkeypatch.setattr(audio.subprocess, "run", fake_run)

    answer = audio._opencode_text("write a line", json_mode=True)
    assert answer == '{"ok": true}'
    create = json.loads(calls[0][calls[0].index("-d") + 1])
    assert create["model"] == {
        "id": "deepseek-v4.1-flash",
        "providerID": "opencode-go",
        "variant": "low",
    }
    generate = json.loads(calls[1][calls[1].index("-d") + 1])
    assert generate["prompt"].endswith("Reply with JSON only.")
    assert any("/generate" in part for part in calls[1])
    assert calls[-1][:3] == ["/usr/local/bin/opencode", "api", "delete"]
    assert audio.opencode_model() == "deepseek-v4.1-flash"
    assert audio.opencode_variant() == "low"


def test_opencode_leads_rewrite_candidates(monkeypatch):
    monkeypatch.setattr(audio, "opencode_available", lambda: True)
    monkeypatch.setattr(audio, "mlx_lm_available", lambda: True)
    monkeypatch.setattr(settings_store, "load_settings", lambda: {
        "opencode": {"enabled": True, "use_rewrite": True},
    })
    assert audio._rewrite_candidates()[0] == "opencode"


def _write_silent_wav(path, seconds=1.0):
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\0\0" * int(16000 * seconds))


def test_cloud_stt_groq_parses_segments(tmp_path, monkeypatch):
    wav = tmp_path / "audio.wav"
    _write_silent_wav(wav)
    job_dir = tmp_path / "job"
    captured = {}

    def fake_run(cmd, timeout=None):
        target = __import__("pathlib").Path(cmd[-1])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"fake-mp3")
        return None

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["body"] = request.data
        return FakeResponse(json.dumps({
            "language": "en",
            "text": " hello world ",
            "segments": [{"start": 0.0, "end": 1.2, "text": " hello world "}],
        }).encode("utf-8"))

    monkeypatch.setattr(pipeline, "_run", fake_run)
    monkeypatch.setattr(settings_store, "get_secret", lambda name: "gsk-test" if name == "groq" else "")
    monkeypatch.setattr(pipeline.urllib.request, "urlopen", fake_urlopen)

    result = pipeline._cloud_speech(wav, job_dir, "groq", "en")
    assert result["provider"] == "groq"
    assert result["model"] == "whisper-large-v3-turbo"
    assert result["segments"] == [{"start": 0.0, "end": 1.2, "text": "hello world"}]
    assert captured["url"].startswith("https://api.groq.com/")
    assert b"whisper-large-v3-turbo" in captured["body"]


def test_cloud_stt_deepgram_parses_utterances(tmp_path, monkeypatch):
    wav = tmp_path / "audio.wav"
    _write_silent_wav(wav)
    job_dir = tmp_path / "job"
    captured = {}

    def fake_run(cmd, timeout=None):
        target = __import__("pathlib").Path(cmd[-1])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"fake-mp3")
        return None

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["auth"] = request.get_header("Authorization")
        captured["content_type"] = request.get_header("Content-type")
        return FakeResponse(json.dumps({
            "metadata": {"language": "en"},
            "results": {"utterances": [
                {"start": 0.2, "end": 1.4, "transcript": "hello from deepgram"},
            ]},
        }).encode("utf-8"))

    monkeypatch.setattr(pipeline, "_run", fake_run)
    monkeypatch.setattr(settings_store, "get_secret", lambda name: "dg-test" if name == "deepgram" else "")
    monkeypatch.setattr(pipeline.urllib.request, "urlopen", fake_urlopen)

    result = pipeline._cloud_speech(wav, job_dir, "deepgram", "en")
    assert result["provider"] == "deepgram"
    assert result["segments"][0]["text"] == "hello from deepgram"
    assert "model=nova-3" in captured["url"]
    assert captured["auth"] == "Token dg-test"
    assert captured["content_type"] == "audio/mpeg"


def test_cloud_tts_payloads(monkeypatch, tmp_path):
    captured = {}

    def fake_convert(source, output, extra=None):
        output.write_bytes(b"RIFF-fake")
        return output

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["auth"] = request.get_header("Authorization")
        return FakeResponse(b"fake-audio")

    monkeypatch.setattr(audio, "_convert", fake_convert)
    monkeypatch.setattr(audio.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(audio, "openai_key", lambda: "sk-openai")
    monkeypatch.setattr(audio, "groq_key", lambda: "gsk-groq")
    monkeypatch.setattr(audio, "deepgram_key", lambda: "dg-key")

    openai_out = tmp_path / "openai.wav"
    audio._openai_voice("hello", "alloy", openai_out, 1.0)
    assert captured["url"].endswith("/v1/audio/speech")
    assert captured["body"]["model"] == "gpt-4o-mini-tts"
    assert captured["body"]["voice"] == "alloy"
    assert captured["body"]["input"] == "hello"
    assert captured["auth"] == "Bearer sk-openai"
    assert openai_out.is_file()

    groq_out = tmp_path / "groq.wav"
    audio._groq_voice("hello", "troy", groq_out, 1.0)
    assert captured["body"]["model"] == "canopylabs/orpheus-v1-english"
    assert captured["body"]["voice"] == "troy"
    assert groq_out.is_file()

    deepgram_out = tmp_path / "deepgram.wav"
    audio._deepgram_voice("hello", "aura-2-thalia-en", deepgram_out, 1.0)
    assert "model=aura-2-thalia-en" in captured["url"]
    assert captured["body"] == {"text": "hello"}
    assert captured["auth"] == "Token dg-key"
    assert deepgram_out.is_file()


def test_kokoro_exposes_chinese_voices():
    voices = {item["id"]: item for item in audio.list_voices("kokoro")}
    for voice in ("zf_xiaobei", "zm_yunjian", "zf_001", "zm_009"):
        assert voice in voices
        assert voices[voice]["lang"] == "zh"
    assert voices["af_heart"]["lang"] == "en"


def test_openrouter_settings_survive_settings_load(monkeypatch, tmp_path):
    monkeypatch.setattr(settings_store, "DATA", tmp_path)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(settings_store, "SECRETS_PATH", tmp_path / "secrets.json")
    for names in settings_store.ENV_KEYS.values():
        for env_name in names:
            monkeypatch.delenv(env_name, raising=False)
    settings_store.save_settings({
        "openrouter": {"enabled": False, "model": "custom/model-x"},
    })
    loaded = settings_store.load_settings()["openrouter"]
    assert loaded["enabled"] is False
    assert loaded["model"] == "custom/model-x"


def test_settings_api_locks_model_and_masks_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_store, "DATA", tmp_path)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(settings_store, "SECRETS_PATH", tmp_path / "secrets.json")
    for names in settings_store.ENV_KEYS.values():
        for env_name in names:
            monkeypatch.delenv(env_name, raising=False)

    client = TestClient(app.app)
    bad = client.post("/api/settings", json={
        "settings": {"opencode": {"model": "openai/gpt-4"}},
    })
    assert bad.status_code == 400
    bad_reasoning = client.post("/api/settings", json={
        "settings": {"opencode": {"variant": "high"}},
    })
    assert bad_reasoning.status_code == 400

    saved = client.post("/api/settings", json={
        "settings": {
            "opencode": {"model": "deepseek-v4.1-flash", "variant": "low"},
            "stt": {"provider": "auto", "language": "vi"},
        },
        "secrets": {"minimax": "mm-hidden", "opencode": "oc-hidden"},
    })
    assert saved.status_code == 200
    body = saved.json()
    assert body["settings"]["stt"]["provider"] == "auto"
    assert body["settings"]["stt"]["language"] == "vi"
    assert body["settings"]["stt"]["model"] == "mlx-community/whisper-small-mlx"
    assert body["secrets"]["minimax"] is True
    assert body["secrets"]["opencode"] is True
    assert body["sources"]["minimax"] == "file"
    assert body["sources"]["opencode"] == "file"
    assert "mm-hidden" not in saved.text


def test_opencode_rewrite_requires_fit_and_parses(monkeypatch):
    monkeypatch.setattr(settings_store, "load_settings", lambda: {
        "opencode": {"enabled": True, "use_rewrite": True},
    })
    monkeypatch.setattr(audio, "opencode_available", lambda: True)
    monkeypatch.setattr(audio, "_opencode_text", lambda *args, **kwargs: '["short line"]')
    script = [{"role": "hook", "duration": 3.0, "rate": 1.0, "text": "source"}]
    result = audio._rewrite_opencode(script, "en", "en", "smooth", ["a much longer literal line"])
    assert result == ["short line."]

    monkeypatch.setattr(audio, "_opencode_text", lambda *args, **kwargs: '["this line is far too long to fit the slot at normal pace"]')
    trimmed = audio._rewrite_opencode(script, "en", "en", "smooth", ["literal"])
    assert trimmed and trimmed[0]


def test_opencode_direct_key_is_exclusive(monkeypatch):
    called = {"local": False}

    def fail_local(*args, **kwargs):
        called["local"] = True
        return None

    monkeypatch.setattr(audio, "opencode_key", lambda: "project-key")
    monkeypatch.setattr(
        audio, "_opencode_http_text",
        lambda prompt, max_tokens=0, json_mode=False, record_failure=True: "direct answer",
    )
    monkeypatch.setattr(audio, "_opencode_api", fail_local)
    assert audio._opencode_text("hello") == "direct answer"
    assert called["local"] is False


# ---------------------------------------------------------------- 0.9.0 P1/P2


def test_usage_store_costs_and_delta():
    import usage_store
    before = usage_store.snapshot()
    usage_store.record("llm", "opencode", model="deepseek", input_tokens=1_000_000, output_tokens=1_000_000)
    usage_store.record("stt", "groq", audio_seconds=3600)
    usage_store.record("tts", "openai", chars=1_000_000)
    delta = usage_store.delta(before)
    assert delta["calls"] == 3
    assert delta["input_tokens"] == 1_000_000
    assert delta["audio_seconds"] == 3600
    assert abs(delta["cost_usd"] - (0.75 + 0.04 + 15.0)) < 0.001


def test_job_usage_summary_sums_entries():
    job = {"usage": [
        {"action": "script", "calls": 2, "input_tokens": 1000, "output_tokens": 200, "chars": 0,
         "audio_seconds": 0, "cost_usd": 0.001},
        {"action": "render", "calls": 0, "input_tokens": 0, "output_tokens": 0, "chars": 500,
         "audio_seconds": 0, "cost_usd": 0.2},
    ]}
    summary = app._usage_summary(job)
    assert summary["totals"]["calls"] == 2
    assert summary["totals"]["chars"] == 500
    assert abs(summary["totals"]["cost_usd"] - 0.201) < 0.000001


def test_attach_crop_paths_smooths_samples():
    scene = make_scene(0, 0.0, 4.0)
    scene["deep"] = True
    scene["attention"] = {
        "face": {"x": 0.42, "y": 0.5, "w": 0.12, "h": 0.12, "confidence": 0.9},
        "salient": None,
    }
    records = {
        "s00000_0.jpg": {"faces": [{"x": 0.5, "y": 0.2, "w": 0.1, "h": 0.1, "confidence": 0.8}], "salient": []},
        "s00000_1.jpg": {"faces": [{"x": 0.5, "y": 0.8, "w": 0.1, "h": 0.1, "confidence": 0.8}], "salient": []},
    }
    pipeline.attach_crop_paths([scene], records, 1080, 1920)
    paths = scene["crop_paths"]
    assert set(paths) == set(pipeline.ASPECT_RATIOS)
    nine = paths["16:9"]
    assert len(nine) == 5
    assert all(0.0 <= item["t"] <= 4.0 for item in nine)
    assert nine[0]["cy"] != nine[-1]["cy"]


def test_crop_filter_dynamic_path_expression():
    meta = {"width": 1080, "height": 1920}
    vf = render._crop_filter(
        meta, {"cx": 0.5, "cy": 0.5}, 1920, 1080,
        crop_path=[{"t": 0.0, "cy": 0.2}, {"t": 2.0, "cy": 0.8}], duration=2.0,
    )
    assert "cos(PI" in vf
    assert "y='" in vf
    assert "crop=1080:608" in vf


def test_cartesia_payload(monkeypatch, tmp_path):
    captured = {}

    def fake_convert(source, output, extra=None):
        output.write_bytes(b"RIFF")
        return output

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse(b"fake-wav")

    monkeypatch.setattr(audio, "_convert", fake_convert)
    monkeypatch.setattr(audio, "cartesia_key", lambda: "sk_car_test")
    monkeypatch.setattr(audio.urllib.request, "urlopen", fake_urlopen)
    output = tmp_path / "cartesia.wav"
    audio._cartesia_voice("hello", "voice-id", output, 1.0)
    assert captured["url"] == "https://api.cartesia.ai/tts/bytes"
    assert captured["headers"].get("X-api-key") == "sk_car_test"
    assert captured["body"]["model_id"] == "sonic-3.6"
    assert captured["body"]["voice"] == "voice-id"
    assert output.is_file()


def test_whisper_models_shape():
    models = pipeline.whisper_models()
    ids = {item["id"] for item in models}
    assert "mlx-community/whisper-large-v3-turbo-q4" in ids
    assert all("cached" in item and "size_mb" in item for item in models)


def test_share_token_and_review(tmp_path, monkeypatch):
    job_dir = tmp_path / "job"
    renders = job_dir / "renders"
    renders.mkdir(parents=True)
    video = renders / "reel_15.mp4"
    video.write_bytes(b"fake-mp4")
    scenes = [make_scene(0, 0.0, 2.0, speech="hello")]
    job = {
        "id": "job1",
        "source": {"name": "clip.mp4"},
        "analysis": {
            "scenes": scenes,
            "plans": {"15": {"target": 15, "clips": [
                {"scene": 0, "start": 0.0, "duration": 2.0, "dur": 2.0, "role": "hook"},
            ]}},
        },
        "renders": {"15": {"status": "ready", "path": "renders/reel_15.mp4", "updated": 1}},
    }
    monkeypatch.setattr(app, "SHARES", tmp_path / "shares.json")
    monkeypatch.setattr(app, "_job_dir", lambda job_id: job_dir)
    monkeypatch.setattr(app, "load_job", lambda job_id: job)
    result = app.create_share("job1", 15, "9:16")
    assert result["url"].startswith("/r/")
    found = app._share(result["token"])
    assert found and found[0]["target"] == 15
    page = app.review_page(result["token"])
    assert b"review only" in page.body
    media = app.review_video(result["token"])
    assert media.path == video


def test_clear_translation_memo_by_provider(tmp_path, monkeypatch):
    monkeypatch.setattr(audio, "MEMO", tmp_path / "translate")
    audio._memo_put("zh", "en", "你好", "hello", "opencode")
    assert audio._memo_get("zh", "en", "你好", "opencode") == "hello"
    removed = audio.clear_translation_memo(["你好"], "zh", "en", "opencode")
    assert removed == 1
    assert audio._memo_get("zh", "en", "你好", "opencode") is None


def test_generate_music_selects_worker(tmp_path, monkeypatch):
    monkeypatch.setattr(audio, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(audio, "stable_audio_available", lambda: True)
    monkeypatch.setattr(audio, "musicgen_available", lambda: True)
    monkeypatch.setattr(audio, "save_generated_asset", lambda *args: None)
    calls = []

    def fake_run(cmd, timeout=None, cancel_event=None):
        calls.append(cmd)
        target = __import__("pathlib").Path(cmd[cmd.index("--out") + 1])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"RIFF" + b"0" * 2048)

    monkeypatch.setattr(audio, "_run", fake_run)
    audio.generate_music("facebook/musicgen-small", "calm bed", 8.0)
    assert "musicgen_generate.py" in calls[-1][1]
    audio.generate_music("stabilityai/stable-audio-open-small", "calm bed", 8.0)
    assert "music_generate.py" in calls[-1][1]


def test_music_engine_lists_musicgen():
    status = audio.engine_status()
    assert "musicgen-small" in status["music"]


def test_openrouter_text_payload_and_fallback_order(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=0):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["auth"] = request.get_header("Authorization")
        return FakeResponse(json.dumps({
            "choices": [{"message": {"content": '{"ok": true}'}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 5},
        }).encode("utf-8"))

    monkeypatch.setattr(audio, "openrouter_key", lambda: "sk-or-test")
    monkeypatch.setattr(settings_store, "load_settings", lambda: {
        "openrouter": {
            "enabled": True,
            "model": "deepseek/deepseek-v4.1-flash:floor",
            "use_rewrite": True,
            "use_translate": True,
        },
        "opencode": {"enabled": True, "use_translate": True, "use_rewrite": True},
    })
    monkeypatch.setattr(audio.urllib.request, "urlopen", fake_urlopen)
    assert audio._openrouter_text("hello") == '{"ok": true}'
    assert captured["body"]["model"] == "deepseek/deepseek-v4.1-flash:floor"
    assert captured["body"]["reasoning"] == {"effort": "low"}
    assert captured["body"]["provider"] == {"sort": "price"}
    assert captured["auth"] == "Bearer sk-or-test"

    monkeypatch.setattr(audio, "opencode_available", lambda: True)
    monkeypatch.setattr(audio, "openrouter_available", lambda: True)
    monkeypatch.setattr(audio, "apple_pair_status", lambda source, target: "installed")
    assert audio._provider_order("zh", "en", "auto")[:3] == ["opencode", "openrouter", "apple_fm"]


def test_minimax_tts_payload(monkeypatch, tmp_path):
    captured = {}
    fake_audio = b"RIFF" + b"0" * 2048

    def fake_convert(source, output, extra=None):
        output.write_bytes(b"RIFF-converted")
        return output

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["auth"] = request.get_header("Authorization")
        return FakeResponse(json.dumps({
            "data": {"audio": fake_audio.hex()},
            "base_resp": {"status_code": 0},
        }).encode("utf-8"))

    monkeypatch.setattr(audio, "minimax_key", lambda: "mm-test")
    monkeypatch.setattr(audio, "_convert", fake_convert)
    monkeypatch.setattr(audio.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(settings_store, "load_settings", lambda: {
        "minimax": {"tts_model": "speech-2.8-turbo"},
    })
    out = tmp_path / "minimax.wav"
    audio._minimax_voice("hello", "female-shaonv", out, 1.0)
    assert captured["url"] == "https://api.minimax.io/v1/t2a_v2"
    assert captured["body"]["model"] == "speech-2.8-turbo"
    assert captured["body"]["voice_setting"]["voice_id"] == "female-shaonv"
    assert captured["auth"] == "Bearer mm-test"
    assert out.is_file()


def test_openrouter_tts_payload(monkeypatch, tmp_path):
    captured = {}

    def fake_convert(source, output, extra=None):
        captured["convert_source"] = source
        output.write_bytes(b"RIFF")
        return output

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse(b"fake-mp3")

    monkeypatch.setattr(audio, "openrouter_key", lambda: "sk-or")
    monkeypatch.setattr(audio, "_convert", fake_convert)
    monkeypatch.setattr(audio.urllib.request, "urlopen", fake_urlopen)
    out = tmp_path / "fish.wav"
    audio._openrouter_voice("hello", "", out, 1.0, "fish")
    assert captured["url"] == "https://openrouter.ai/api/v1/audio/speech"
    assert captured["body"]["model"] == "fish-audio/s2.1-pro-free:free"
    assert captured["body"]["input"] == "hello"
    assert captured["body"]["voice"] == ""
    assert captured["body"]["response_format"] == "mp3"
    assert captured["convert_source"].suffix == ".mp3"
    assert out.is_file()


def test_openrouter_tts_consults_quarantine(monkeypatch, tmp_path):
    monkeypatch.setattr(audio, "openrouter_key", lambda: "sk-or")
    monkeypatch.setattr(audio, "openrouter_blocked", lambda: True)
    with pytest.raises(audio.AudioError, match="quarantined"):
        audio._openrouter_voice("hello", "", tmp_path / "fish.wav", 1.0, "fish")


def test_minimax_music_payload(monkeypatch, tmp_path):
    captured = {}
    fake_audio = b"RIFF" + b"1" * 4096

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse(json.dumps({
            "data": {"audio": fake_audio.hex()},
            "base_resp": {"status_code": 0},
        }).encode("utf-8"))

    monkeypatch.setattr(audio, "minimax_key", lambda: "mm-test")
    monkeypatch.setattr(audio.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(settings_store, "load_settings", lambda: {
        "minimax": {"music_model": "music-3.0"},
    })
    out = tmp_path / "music.wav"
    audio._minimax_music("calm bed", 30, out)
    assert captured["url"] == "https://api.minimax.io/v1/music_generation"
    assert captured["body"]["model"] == "music-3.0"
    assert captured["body"]["is_instrumental"] is True
    assert captured["body"]["output_format"] == "hex"
    assert out.read_bytes() == fake_audio


def test_uploaded_voice_fit(tmp_path, monkeypatch):
    source = tmp_path / "voice.wav"
    source.write_bytes(b"RIFF" + b"0" * 4096)
    calls = []

    def fake_media_duration(path):
        return 4.0

    def fake_run(cmd, timeout=None, cancel_event=None):
        calls.append(cmd)
        target = __import__("pathlib").Path(cmd[-1])
        target.write_bytes(b"RIFF" + b"0" * 4096)

    monkeypatch.setattr(audio, "media_duration", fake_media_duration)
    monkeypatch.setattr(audio, "_run", fake_run)
    out = audio._fit_uploaded_voice(source, 2.0, tmp_path, 0.0)
    assert out == tmp_path / "uploaded_voice.wav"
    assert any("atempo=" in part for part in calls[0])
    assert any("apad" in part for part in calls[0])


def test_lyria_streams_audio(monkeypatch, tmp_path):
    import base64

    class Stream:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def __iter__(self):
            payload = {"choices": [{"delta": {"audio": {"data": base64.b64encode(b"mp3-bytes").decode()}}}]}
            yield (b"data: " + json.dumps(payload).encode() + b"\n")
            yield b"data: [DONE]\n"

    captured = {}

    def fake_urlopen(request, timeout=0):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return Stream()

    def fake_convert(source, output, extra=None):
        output.write_bytes(b"wav-bytes")
        return output

    monkeypatch.setattr(audio, "openrouter_key", lambda: "sk-or")
    monkeypatch.setattr(audio.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(audio, "_convert", fake_convert)
    out = tmp_path / "lyria.wav"
    audio._lyria_music("calm bed", 30, out)
    assert captured["body"]["model"] == "google/lyria-3-clip-preview"
    assert captured["body"]["stream"] is True
    assert captured["body"]["modalities"] == ["text", "audio"]
    assert out.is_file()


# ---------------------------------------------------------------- 0.11 cloud reliability


@pytest.fixture
def provider_state():
    audio.clear_openrouter_quarantine()
    audio.reset_provider_breaker()
    audio.OPENROUTER_LAST_ERROR = ""
    audio.OPENROUTER_LAST_STATUS = 0
    audio.OPENCODE_LAST_ERROR = ""
    audio._rewrite_status_reset(False)
    yield
    audio.clear_openrouter_quarantine()
    audio.reset_provider_breaker()
    audio.OPENROUTER_LAST_ERROR = ""
    audio.OPENROUTER_LAST_STATUS = 0
    audio.OPENCODE_LAST_ERROR = ""
    audio._rewrite_status_reset(False)


def test_openrouter_project_file_key_beats_invalid_env(
    tmp_path, monkeypatch, provider_state,
):
    monkeypatch.setattr(settings_store, "DATA", tmp_path)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(settings_store, "SECRETS_PATH", tmp_path / "secrets.json")
    for env_name in settings_store.ENV_KEYS["openrouter"]:
        monkeypatch.delenv(env_name, raising=False)

    settings_store.save_secrets({"openrouter": "sk-or-project-key"})
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-invalid-env-key")

    assert settings_store.get_secret("openrouter") == "sk-or-project-key"
    assert audio.openrouter_key() == "sk-or-project-key"
    assert settings_store.secret_source("openrouter") == "file"
    state = settings_store.public_state()
    assert state["sources"]["openrouter"] == "file"
    assert state["secrets"]["openrouter"] is True
    assert "sk-or-project-key" not in json.dumps(state)
    assert "sk-or-invalid-env-key" not in json.dumps(state)

    captured = {}

    def fake_urlopen(request, timeout=0):
        captured["auth"] = request.get_header("Authorization")
        return FakeResponse(json.dumps({
            "choices": [{"message": {"content": "ok"}}],
        }).encode("utf-8"))

    monkeypatch.setattr(settings_store, "load_settings", lambda: {
        "openrouter": {
            "enabled": True,
            "model": "deepseek/deepseek-v4.1-flash:floor",
        },
    })
    monkeypatch.setattr(audio.urllib.request, "urlopen", fake_urlopen)
    assert audio._openrouter_text("hello") == "ok"
    assert captured["auth"] == "Bearer sk-or-project-key"

    settings_store.save_secrets({"openrouter": ""})
    assert settings_store.get_secret("openrouter") == "sk-or-invalid-env-key"
    assert settings_store.secret_source("openrouter") == "env"


def test_openrouter_401_quarantines_and_success_clears(monkeypatch, provider_state):
    calls = []

    def reject(request, timeout=0):
        calls.append(request)
        raise urllib.error.HTTPError(
            request.full_url, 401, "Unauthorized", {},
            io.BytesIO(b'{"error":{"message":"invalid sk-or-test"}}'),
        )

    monkeypatch.setattr(audio, "openrouter_key", lambda: "sk-or-test")
    monkeypatch.setattr(settings_store, "load_settings", lambda: {
        "openrouter": {
            "enabled": True,
            "model": "deepseek/deepseek-v4.1-flash:floor",
        },
    })
    monkeypatch.setattr(audio.urllib.request, "urlopen", reject)

    assert audio._openrouter_text("hello") is None
    assert audio.OPENROUTER_LAST_STATUS == 401
    assert "sk-or-test" not in audio.OPENROUTER_LAST_ERROR
    assert audio.openrouter_blocked()
    assert not audio.openrouter_available()
    assert len(calls) == 1

    # A quarantined provider is not called again until the key test succeeds.
    assert audio._openrouter_text("again") is None
    assert len(calls) == 1
    assert "quarantined" in audio.OPENROUTER_LAST_ERROR.lower()

    def accept(request, timeout=0):
        calls.append(request)
        return FakeResponse(json.dumps({
            "choices": [{"message": {"content": '{"ok": true}'}}],
        }).encode("utf-8"))

    monkeypatch.setattr(audio.urllib.request, "urlopen", accept)
    assert audio._openrouter_text("hello", force=True) == '{"ok": true}'
    assert not audio.openrouter_blocked()
    assert audio.openrouter_available()


def test_openrouter_404_names_model_and_endpoint_reports_source(
    tmp_path, monkeypatch, provider_state,
):
    monkeypatch.setattr(settings_store, "DATA", tmp_path)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(settings_store, "SECRETS_PATH", tmp_path / "secrets.json")
    for env_name in settings_store.ENV_KEYS["openrouter"]:
        monkeypatch.delenv(env_name, raising=False)
    settings_store.save_secrets({"openrouter": "sk-or-file-key"})
    monkeypatch.setattr(settings_store, "load_settings", lambda: {
        "openrouter": {
            "enabled": True,
            "model": "deepseek/deepseek-v4.1-flash:floor",
        },
    })

    captured = {}

    def missing(request, timeout=0):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        raise urllib.error.HTTPError(
            request.full_url, 404, "Not Found", {},
            io.BytesIO(
                b'{"error":{"message":"No endpoints found for '
                b'deepseek/deepseek-v4.1-flash:floor"}}'
            ),
        )

    monkeypatch.setattr(audio.urllib.request, "urlopen", missing)
    client = TestClient(app.app)
    response = client.post("/api/settings/test", json={"kind": "openrouter"})
    body = response.json()

    assert body["ok"] is False
    assert body["source"] == "file"
    assert body["model"] == "deepseek/deepseek-v4.1-flash:floor"
    assert body["status"] == 404
    assert "deepseek/deepseek-v4.1-flash:floor" in body["detail"]
    assert "sk-or-file-key" not in response.text
    assert captured["body"]["model"] == "deepseek/deepseek-v4.1-flash:floor"
    assert not audio.openrouter_blocked()


def test_opencode_empty_retry_uses_short_backoff(monkeypatch, provider_state):
    calls = []
    sleeps = []

    def fake_text(prompt, json_mode=False, max_tokens=1200, force=False, record_failure=True):
        calls.append((json_mode, max_tokens))
        if len(calls) == 3:
            return '["ok"]'
        audio.OPENCODE_LAST_ERROR = "OpenCode returned an empty reply."
        return None

    monkeypatch.setattr(audio, "_opencode_text", fake_text)
    monkeypatch.setattr(audio.time, "sleep", lambda seconds: sleeps.append(seconds))

    assert audio._opencode_json_attempts("prompt", 120) == '["ok"]'
    assert sleeps == [0.4, 1.0]
    assert [mode for mode, _tokens in calls] == [True, False, True]


def test_opencode_empty_replies_trip_circuit_breaker(monkeypatch, provider_state):
    monkeypatch.setattr(audio, "opencode_key", lambda: "")
    monkeypatch.setattr(audio, "opencode_bin", lambda: "/usr/local/bin/opencode")
    monkeypatch.setattr(settings_store, "load_settings", lambda: {
        "opencode": {
            "enabled": True,
            "model": "deepseek-v4.1-flash",
            "variant": "low",
        },
    })
    api_calls = []

    def fake_api(args, body=None, allow_empty=False):
        api_calls.append(list(args))
        if args[:2] == ["post", "/api/session"]:
            return {"data": {"id": "ses_test"}}
        if args[0] == "post" and "/generate" in args[1]:
            return {"data": {"text": ""}}
        return {"data": True}

    monkeypatch.setattr(audio, "_opencode_api", fake_api)

    for _ in range(audio.PROVIDER_BREAKER_FAILURES):
        assert audio._opencode_text("write") is None
    assert audio._provider_breaker_open("opencode")
    assert not audio.opencode_available()

    before = len(api_calls)
    assert audio._opencode_text("write") is None
    assert len(api_calls) == before
    assert "circuit" in audio.OPENCODE_LAST_ERROR.lower()

    # The explicit Setup test still probes once, even while the circuit is open.
    assert audio._opencode_text("write", force=True) is None
    assert len(api_calls) > before


def test_translation_memo_reused_and_duplicate_clear_once(tmp_path, monkeypatch):
    monkeypatch.setattr(audio, "MEMO", tmp_path / "translate")
    audio._memo_put("en", "vi", "hello", "xin chào", "auto")
    monkeypatch.setattr(audio, "_provider_order", lambda *args: [])

    assert audio.translate_lines(["hello"], "en", "vi") == ["xin chào"]
    assert audio.clear_translation_memo(["hello", "hello"], "en", "vi") == 1


def test_adapt_script_reports_rewrite_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(audio, "REWRITE", tmp_path / "rewrite")
    monkeypatch.setattr(audio, "_rewrite_candidates", lambda: ["opencode"])
    monkeypatch.setattr(audio, "_rewrite_opencode", lambda *args, **kwargs: None)
    monkeypatch.setattr(audio, "OPENCODE_LAST_ERROR", "OpenCode returned an empty reply.")
    script = [{
        "scene": 0, "role": "hook", "duration": 3.0, "rate": 1.0,
        "text": "original",
    }]

    result = audio.adapt_script(script, "en", "en", "smooth", "auto")
    status = audio.rewrite_status()
    assert status["ok"] is False
    assert status["fallback"] is True
    assert "opencode" in status["error"].lower()
    assert result[0]["rewrite"] == "literal"
    assert result[0]["text"] == "original"


def test_rewrite_memo_key_includes_provider_and_clear(tmp_path, monkeypatch):
    monkeypatch.setattr(audio, "REWRITE", tmp_path / "rewrite")
    audio._rewrite_put(
        "en", "en", "smooth", "text", "one", None, "opencode:model-a",
    )
    assert audio._rewrite_memo(
        "en", "en", "smooth", "text", None, "opencode:model-a",
    ) == "one"
    assert audio._rewrite_memo(
        "en", "en", "smooth", "text", None, "openrouter:model-b",
    ) is None
    assert audio.clear_rewrite_memo(
        ["text"], "en", "en", "smooth", "opencode:model-a",
    ) == 1
    assert audio._rewrite_memo(
        "en", "en", "smooth", "text", None, "opencode:model-a",
    ) is None


def test_rules_fallback_after_ai_failure_is_flagged_and_not_cached(
    monkeypatch, tmp_path,
):
    monkeypatch.setattr(audio, "REWRITE", tmp_path / "rewrite")
    monkeypatch.setattr(audio, "_rewrite_candidates", lambda: ["opencode", "rules"])
    monkeypatch.setattr(audio, "_rewrite_opencode", lambda *args, **kwargs: None)
    monkeypatch.setattr(audio, "OPENCODE_LAST_ERROR", "OpenCode returned an empty reply.")
    script = [{
        "scene": 0, "role": "hook", "duration": 3.0, "rate": 1.0,
        "text": "original",
    }]

    result = audio.adapt_script(script, "en", "en", "smooth", "auto")
    status = audio.rewrite_status()
    assert status["ok"] is True
    assert status["used"] == "rules"
    assert status["fallback"] is True
    assert "AI rewrite failed" in status["error"]
    assert result[0]["rewrite"] == "rules"
    assert not list((tmp_path / "rewrite").rglob("*.txt"))


def test_tts_candidates_follow_admin_routes(monkeypatch):
    monkeypatch.setattr(audio.settings_store, "load_settings", lambda: {
        "workflows": {
            "tts": {
                "routes": [
                    {"provider": "minimax", "model": "speech-2.8-turbo"},
                    {"provider": "openrouter", "model": "fish-audio/s2.1-pro-free:free"},
                    {"provider": "openrouter", "model": "google/gemini-3.8-flash-lite-tts"},
                    {"provider": "local", "model": "kokoro"},
                ],
                "timeout_s": 120,
            }
        }
    })
    assert audio._tts_candidates("minimax") == ["minimax", "fish", "gemini", "kokoro"]
    assert [item["model"] for item in audio._tts_route_candidates()] == [
        "speech-2.8-turbo",
        "fish-audio/s2.1-pro-free:free",
        "google/gemini-3.8-flash-lite-tts",
        "kokoro",
    ]
    assert audio._tts_candidates("fish") == ["minimax", "fish", "gemini", "kokoro"]


def test_tts_candidates_do_not_add_unconfigured_local_fallbacks(monkeypatch):
    monkeypatch.setattr(audio.settings_store, "load_settings", lambda: {
        "workflows": {
            "tts": {
                "routes": [{"provider": "openrouter", "model": "fish-audio/s2.1-pro-free:free"}],
                "timeout_s": 120,
            }
        }
    })
    assert audio._tts_candidates("auto") == ["fish"]


def test_lyria_consults_quarantine(monkeypatch, tmp_path):
    monkeypatch.setattr(audio, "openrouter_key", lambda: "sk-or")
    monkeypatch.setattr(audio, "openrouter_blocked", lambda: True)
    with pytest.raises(audio.AudioError, match="quarantined"):
        audio._lyria_music("calm bed", 30, tmp_path / "lyria.wav")


def test_tts_voice_defaults_and_fish_empty(monkeypatch):
    monkeypatch.setattr(audio, "list_voices", lambda engine: [])
    assert audio._tts_voice_for("fish", "default", "fish") == ""
    assert audio._tts_voice_for("fish", "female-shaonv", "minimax") == ""
    assert audio._tts_voice_for("fish", "custom-fish", "fish") == "custom-fish"
    assert audio._tts_voice_for("gemini", "", "gemini") == "Kore"
    assert audio._tts_voice_for("gemini", "default", "gemini") == "Kore"
    assert audio._tts_voice_for("kokoro", "female-shaonv", "minimax") == "af_heart"
    assert audio._tts_voice_for("minimax", "Samantha", "say") == "female-shaonv"
