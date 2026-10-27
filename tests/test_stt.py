"""STT track tests: chunking, engines, Transcript v2, vocabulary, captions.

Every engine is faked.  No test reaches the network, needs a model pack, or
requires Apple Speech to be installed.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

import captions
import pipeline
import settings_store
import stt


def _write(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _word(text: str, start: float, end: float, confidence: float = 0.9) -> dict:
    return {
        "w": text,
        "start": start,
        "end": end,
        "confidence": confidence,
    }


def _transcript(job_dir: Path, *, created: float | None = None) -> dict:
    transcript = stt.build_transcript(
        engine="apple",
        model="on-device-3b",
        language="en",
        segments=[{
            "start": 0.0, "end": 3.2, "text": "Hello. World.",
        }],
        words=[
            _word("Hello.", 0.0, 0.8),
            _word("World.", 2.5, 3.2),
        ],
        audio_duration=10.0,
        source_hash="source-abc",
        created=created,
    )
    stt.save_transcript(job_dir, transcript)
    return transcript


# ---------------------------------------------------------------- chunking


def test_chunk_ranges_use_ten_minutes_and_five_second_overlap():
    ranges = stt.chunk_ranges(1200)
    assert ranges == [
        {"index": 0, "start": 0.0, "end": 600.0},
        {"index": 1, "start": 595.0, "end": 1195.0},
        {"index": 2, "start": 1190.0, "end": 1200.0},
    ]
    assert stt.chunk_ranges(0) == []
    assert stt.chunk_ranges(42) == [{"index": 0, "start": 0.0, "end": 42.0}]


def test_chunk_cache_key_covers_audio_engine_model_and_index():
    key = stt.chunk_cache_key("abc", "whisper", "turbo", 2)
    assert key == stt.chunk_cache_key("abc", "whisper", "turbo", 2)
    assert key != stt.chunk_cache_key("abc", "whisper", "turbo", 3)
    assert key != stt.chunk_cache_key("abc", "apple", "turbo", 2)
    assert key != stt.chunk_cache_key("abc", "whisper", "q4", 2)
    assert key != stt.chunk_cache_key("def", "whisper", "turbo", 2)


def test_prepare_audio_reuses_cached_hash_file(tmp_path):
    source = tmp_path / "source.wav"
    source.write_bytes(b"RIFF" + b"0" * 64)
    cached = tmp_path / "job" / "transcript" / "audio" / "abcdef1234567890_16k.wav"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"RIFF" + b"1" * 64)
    path, digest = stt.prepare_audio(source, tmp_path / "job", source_hash="abcdef1234567890")
    assert path == cached
    assert digest == "abcdef1234567890"


# ---------------------------------------------------------------- engines


def test_apple_payload_reads_per_run_word_ranges():
    payload = stt._apple_payload({
        "language": "en-US",
        "segments": [{
            "start": 0.0,
            "end": 1.2,
            "text": "Hello world",
            "words": [
                {"w": "Hello", "start": 0.0, "end": 0.4, "confidence": 0.9},
                {"w": "world", "start": 0.45, "end": 1.1, "confidence": 0.7},
            ],
        }],
    })
    assert payload["language"] == "en"
    assert [word["w"] for word in payload["words"]] == ["Hello", "world"]
    assert payload["words"][1]["start"] == 0.45
    assert payload["segments"][0]["confidence"] == 0.8
    assert all(word["segment"] == 0 for word in payload["words"])


def test_apple_helper_receives_contextual_strings(tmp_path, monkeypatch):
    captured = {}
    wav = tmp_path / "audio.wav"
    wav.write_bytes(b"RIFF" + b"0" * 64)

    class Result:
        returncode = 0

    def fake_run(cmd, capture_output=True, text=True, timeout=None):
        captured["cmd"] = cmd
        out = Path(cmd[cmd.index("--out") + 1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "language": "en-US",
            "segments": [{
                "start": 0.0, "end": 1.0, "text": "Acme",
                "words": [{"w": "Acme", "start": 0.0, "end": 1.0}],
            }],
        }), encoding="utf-8")
        return Result()

    monkeypatch.setattr(stt.subprocess, "run", fake_run)
    result = stt.transcribe_apple(
        wav, tmp_path, "en", helper=tmp_path / "helper", vocabulary=["Acme", "VibeCut"],
    )
    cmd = captured["cmd"]
    assert "--vocabulary" in cmd
    assert json.loads(cmd[cmd.index("--vocabulary") + 1]) == ["Acme", "VibeCut"]
    assert result["words"][0]["w"] == "Acme"


def test_whisper_uses_word_timestamps_and_turbo_default(tmp_path, monkeypatch):
    captured = {}
    wav = tmp_path / "audio.wav"
    wav.write_bytes(b"RIFF" + b"0" * 64)

    class Result:
        returncode = 0

    def fake_run(cmd, stdout=None, stderr=None, timeout=None):
        captured["cmd"] = cmd
        output_dir = Path(cmd[cmd.index("--output-dir") + 1])
        name = cmd[cmd.index("--output-name") + 1]
        _write(output_dir / f"{name}.json", {
            "language": "en",
            "segments": [{
                "start": 0.0, "end": 1.0, "text": "Hello world",
                "avg_logprob": -0.2, "no_speech_prob": 0.01,
                "compression_ratio": 1.1,
                "words": [
                    {"word": "Hello", "start": 0.0, "end": 0.4, "probability": 0.9},
                    {"word": "world", "start": 0.4, "end": 1.0, "probability": 0.8},
                ],
            }],
        })
        return Result()

    monkeypatch.setattr(stt, "_whisper_binary", lambda: "mlx_whisper")
    monkeypatch.setattr(stt.subprocess, "run", fake_run)
    result = stt.transcribe(
        wav, tmp_path, 1.0, lambda *_args: None,
        language="en", vocabulary=["Acme"],
    )
    cmd = captured["cmd"]
    assert cmd[cmd.index("--model") + 1] == stt.DEFAULT_WHISPER_MODEL
    assert cmd[cmd.index("--word-timestamps") + 1] == "True"
    assert cmd[cmd.index("--initial-prompt") + 1] == "Acme"
    assert result["model"] == stt.DEFAULT_WHISPER_MODEL
    assert [word["w"] for word in result["words"]] == ["Hello", "world"]


def test_whisper_payload_drops_hallucinations_and_their_words():
    payload = stt._whisper_payload({
        "language": "en",
        "segments": [
            {
                "start": 0.0, "end": 1.0, "text": "keep this",
                "avg_logprob": -0.2, "no_speech_prob": 0.01,
                "compression_ratio": 1.1,
                "words": [{"word": "keep", "start": 0.0, "end": 0.4}],
            },
            {
                "start": 1.0, "end": 2.0, "text": "boilerplate loop",
                "avg_logprob": -2.5, "no_speech_prob": 0.01,
                "compression_ratio": 1.1,
                "words": [{"word": "boilerplate", "start": 1.0, "end": 1.4}],
            },
        ],
    })
    assert [segment["text"] for segment in payload["segments"]] == ["keep this"]
    assert [word["w"] for word in payload["words"]] == ["keep"]


def test_deepgram_payload_keeps_words_and_speakers():
    payload = stt._deepgram_payload({
        "metadata": {"language": "en"},
        "results": {
            "utterances": [{
                "start": 0.1, "end": 1.4, "transcript": "hello there",
                "speaker": 0,
                "words": [
                    {"word": "hello", "start": 0.1, "end": 0.5, "confidence": 0.9},
                    {"word": "there", "start": 0.6, "end": 1.4, "confidence": 0.8},
                ],
            }],
        },
    }, duration=2.0)
    assert payload["segments"][0]["speaker"] == "S1"
    assert all(word["speaker"] == "S1" for word in payload["words"])
    assert [word["w"] for word in payload["words"]] == ["hello", "there"]


def test_removed_cloud_engines_are_rejected():
    wav = Path("/tmp/none.wav")
    assert stt.transcribe_cloud(wav, Path("/tmp"), provider="auto") is None
    assert stt.transcribe_cloud(wav, Path("/tmp"), provider="") is None
    assert stt.transcribe_cloud(wav, Path("/tmp"), provider="openai") is None
    assert stt.transcribe_cloud(wav, Path("/tmp"), provider="groq") is None


def test_resolve_routes_maps_auto_local_to_turbo_and_drops_openai():
    routes = stt.resolve_routes([
        {"provider": "openai", "model": "whisper-1"},
        {"provider": "auto", "model": "mlx-community/whisper-small-mlx"},
        {"provider": "local", "model": ""},
    ])
    assert routes == [
        {"provider": "whisper", "model": stt.DEFAULT_WHISPER_MODEL},
    ]
    assert stt.resolve_routes([{"provider": "openai", "model": "whisper-1"}]) == [
        {"provider": "apple", "model": "on-device-3b"},
        {"provider": "whisper", "model": stt.DEFAULT_WHISPER_MODEL},
    ]


def test_explicit_cloud_route_is_kept_in_order():
    routes = stt.resolve_routes([
        {"provider": "groq", "model": "whisper-large-v3-turbo"},
        {"provider": "apple", "model": "on-device-3b"},
    ])
    assert [route["provider"] for route in routes] == ["groq", "apple"]
    assert stt.resolve_routes(engine="deepgram") == [
        {"provider": "deepgram", "model": "nova-3"},
    ]


def test_swift_helper_reads_audio_time_ranges_and_contextual_strings():
    source = (stt.ROOT / "tools" / "transcribe_apple.swift").read_text(encoding="utf-8")
    assert "run.audioTimeRange" in source
    assert "transcriptionConfidence" in source
    assert "contextualStrings[.general]" in source


# ---------------------------------------------------------------- transcript v2


def test_transcript_v2_schema_and_quality():
    transcript = stt.build_transcript(
        engine="whisper",
        model="turbo",
        language="en-US",
        segments=[{"start": 0.0, "end": 2.0, "text": "a b"}],
        words=[
            _word("a", 0.0, 1.0, 0.8),
            _word("b", 1.0, 2.0, 0.3),
        ],
        audio_duration=4.0,
        source_hash="hash",
        drift_ms_p95=12.34,
        created=100.0,
    )
    assert transcript["schema"] == 2
    assert transcript["language"] == "en"
    assert transcript["id"].startswith("tr_")
    assert transcript["source_hash"] == "hash"
    assert transcript["engine"] == "whisper"
    assert transcript["model"] == "turbo"
    assert transcript["created"] == 100.0
    assert set(transcript["words"][0]) >= {
        "w", "start", "end", "confidence", "segment",
    }
    assert transcript["quality"] == {
        "coverage": 0.5,
        "mean_confidence": 0.55,
        "low_conf_words": 1,
        "drift_ms_p95": 12.3,
    }
    body = {key: transcript[key] for key in (
        "schema", "source_hash", "engine", "model", "language",
        "segments", "words", "quality",
    )}
    assert transcript["hash"] == stt._hash_json(body)


def test_rerun_gets_a_new_id_but_the_content_hash_is_stable():
    first = stt.build_transcript(
        engine="apple", model="on-device-3b", language="en",
        segments=[{"start": 0.0, "end": 1.0, "text": "hello"}],
        words=[_word("hello", 0.0, 1.0)], audio_duration=1.0,
        source_hash="h", created=1.0,
    )
    second = stt.build_transcript(
        engine="apple", model="on-device-3b", language="en",
        segments=[{"start": 0.0, "end": 1.0, "text": "hello"}],
        words=[_word("hello", 0.0, 1.0)], audio_duration=1.0,
        source_hash="h", created=2.0,
    )
    assert first["id"] != second["id"]
    assert first["hash"] == second["hash"]


def test_save_transcript_is_immutable_and_mirrors_legacy(tmp_path):
    transcript = _transcript(tmp_path)
    path = tmp_path / "transcript" / f"transcript_v2_{transcript['id']}.json"
    original = path.read_text(encoding="utf-8")
    changed = {**transcript, "engine": "changed"}
    stt.save_transcript(tmp_path, changed)
    assert path.read_text(encoding="utf-8") == original
    legacy = json.loads((tmp_path / "transcript" / "transcript.json").read_text())
    assert legacy["id"] == transcript["id"]
    assert stt.load_latest_transcript(tmp_path)["id"] == transcript["id"]


def test_load_latest_transcript_picks_newest(tmp_path):
    first = stt.build_transcript(
        engine="apple", model="m", language="en",
        segments=[{"start": 0.0, "end": 1.0, "text": "one"}],
        words=[], audio_duration=2.0, source_hash="h", created=1.0,
    )
    second = stt.build_transcript(
        engine="apple", model="m", language="en",
        segments=[{"start": 0.0, "end": 1.0, "text": "two"}],
        words=[], audio_duration=2.0, source_hash="h", created=2.0,
    )
    stt.save_transcript(tmp_path, first)
    stt.save_transcript(tmp_path, second)
    assert stt.load_latest_transcript(tmp_path)["id"] == second["id"]


def test_read_transcript_prefers_v2_over_legacy(tmp_path):
    _write(tmp_path / "transcript" / "transcript.json", {
        "segments": [{"start": 0.0, "end": 1.0, "text": "legacy"}],
    })
    transcript = _transcript(tmp_path)
    segments = stt.read_transcript(tmp_path)
    assert segments[0]["text"] == "Hello. World."
    assert transcript["id"] != ""


# ---------------------------------------------------------------- merge/resume


def test_merge_chunks_dedupes_overlap_words_by_time():
    merged = stt._merge_chunks([
        {
            "index": 0, "start": 0.0, "end": 600.0, "language": "en",
            "segments": [{"start": 590.0, "end": 600.0, "text": "tail words"}],
            "words": [
                _word("tail", 598.0, 598.4),
                _word("words", 598.5, 599.0),
            ],
        },
        {
            "index": 1, "start": 595.0, "end": 1195.0, "language": "en",
            "segments": [{"start": 595.0, "end": 607.0, "text": "tail words"}],
            "words": [
                _word("tail", 598.05, 598.45),
                _word("words", 598.55, 599.05),
                _word("next", 599.2, 599.6),
            ],
        },
    ], duration=1195.0)
    assert [word["w"] for word in merged["words"]] == ["tail", "words", "next"]
    assert merged["drift_ms_p95"] > 0


def test_merge_chunks_keeps_repeated_words_outside_the_overlap():
    merged = stt._merge_chunks([
        {
            "index": 0, "start": 0.0, "end": 10.0, "language": "en",
            "segments": [], "words": [_word("no", 1.0, 1.2)],
        },
        {
            "index": 1, "start": 5.0, "end": 20.0, "language": "en",
            "segments": [], "words": [_word("no", 12.0, 12.2)],
        },
    ], duration=20.0)
    assert [word["w"] for word in merged["words"]] == ["no", "no"]


def test_transcribe_source_uses_chunk_cache_and_resumes(tmp_path, monkeypatch):
    wav = tmp_path / "audio.wav"
    wav.write_bytes(b"RIFF" + b"0" * 64)
    calls = []

    def fake_prepare(source, job_dir, *, source_hash=""):
        return source, "audio-hash"

    def fake_chunk(prepared, job_dir, chunk, *, key, engine, model, language,
                   vocabulary, timeout, helper):
        calls.append(int(chunk["index"]))
        start = float(chunk["start"])
        return {
            "index": int(chunk["index"]),
            "start": start,
            "end": float(chunk["end"]),
            "language": "en",
            "segments": [{
                "start": start, "end": start + 1.0, "text": f"chunk {chunk['index']}",
            }],
            "words": [_word(f"c{chunk['index']}", start, start + 0.5)],
        }

    monkeypatch.setattr(stt, "prepare_audio", fake_prepare)
    monkeypatch.setattr(stt, "_engine_ready", lambda provider, model: True)
    monkeypatch.setattr(stt, "_run_engine_chunk_keyed", fake_chunk)
    first = stt.transcribe_source(
        wav, tmp_path, 1200.0, routes=[{"provider": "whisper", "model": ""}],
    )
    assert first and calls == [0, 1, 2]
    calls.clear()
    second = stt.transcribe_source(
        wav, tmp_path, 1200.0, routes=[{"provider": "whisper", "model": ""}],
    )
    assert second and calls == []  # every chunk came from cache
    assert first["id"] != second["id"]


def test_transcribe_source_resumes_after_a_crash(tmp_path, monkeypatch):
    wav = tmp_path / "audio.wav"
    wav.write_bytes(b"RIFF" + b"0" * 64)
    calls = []
    fail = {"once": True}

    def fake_prepare(source, job_dir, *, source_hash=""):
        return source, "crash-hash"

    def fake_chunk(prepared, job_dir, chunk, *, key, engine, model, language,
                   vocabulary, timeout, helper):
        index = int(chunk["index"])
        calls.append(index)
        if index == 1 and fail["once"]:
            fail["once"] = False
            raise RuntimeError("simulated crash")
        start = float(chunk["start"])
        return {
            "index": index, "start": start, "end": float(chunk["end"]),
            "language": "en",
            "segments": [{"start": start, "end": start + 1.0, "text": "ok"}],
            "words": [_word("ok", start, start + 0.5)],
        }

    monkeypatch.setattr(stt, "prepare_audio", fake_prepare)
    monkeypatch.setattr(stt, "_engine_ready", lambda provider, model: True)
    monkeypatch.setattr(stt, "_run_engine_chunk_keyed", fake_chunk)
    assert stt.transcribe_source(
        wav, tmp_path, 1200.0, routes=[{"provider": "whisper", "model": ""}],
    ) is None
    assert calls == [0, 1]
    cached = list((tmp_path / "transcript" / "chunks").glob("*.json"))
    assert len(cached) == 1  # chunk 0 survived the crash
    calls.clear()
    result = stt.transcribe_source(
        wav, tmp_path, 1200.0, routes=[{"provider": "whisper", "model": ""}],
    )
    assert result is not None
    assert calls == [1, 2]  # resumed after the last finished chunk


def test_transcribe_source_skips_removed_openai_route(tmp_path, monkeypatch):
    wav = tmp_path / "audio.wav"
    wav.write_bytes(b"RIFF" + b"0" * 64)
    monkeypatch.setattr(
        stt, "prepare_audio", lambda source, job_dir, *, source_hash="": (source, "h"),
    )
    monkeypatch.setattr(stt, "_engine_ready", lambda provider, model: provider != "openai")
    monkeypatch.setattr(
        stt, "_run_engine_chunk_keyed",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not run")),
    )
    assert stt.transcribe_source(
        wav, tmp_path, 30.0, routes=[{"provider": "openai", "model": "whisper-1"}],
    ) is None


def test_transcribe_source_writes_v2_and_legacy_mirror(tmp_path, monkeypatch):
    wav = tmp_path / "audio.wav"
    wav.write_bytes(b"RIFF" + b"0" * 64)

    monkeypatch.setattr(
        stt, "prepare_audio", lambda source, job_dir, *, source_hash="": (source, "h"),
    )
    monkeypatch.setattr(stt, "_engine_ready", lambda provider, model: True)
    monkeypatch.setattr(stt, "_run_engine_chunk_keyed", lambda prepared, job_dir, chunk, **kwargs: {
        "index": 0, "start": 0.0, "end": 30.0, "language": "en",
        "segments": [{"start": 0.0, "end": 1.0, "text": "hello"}],
        "words": [_word("hello", 0.0, 0.6)],
    })
    result = stt.transcribe_source(
        wav, tmp_path, 30.0, routes=[{"provider": "apple", "model": "on-device-3b"}],
    )
    assert result["provider"] == "apple"
    assert Path(result["path"]).is_file()
    assert (tmp_path / "transcript" / "transcript.json").is_file()
    assert stt.load_latest_transcript(tmp_path)["id"] == result["id"]


# ---------------------------------------------------------------- pipeline facade


def test_pipeline_keeps_compatibility_exports():
    assert pipeline.transcribe_apple is not stt.transcribe_apple  # helper override wrapper
    assert pipeline.transcribe is stt.transcribe
    assert pipeline.read_transcript is stt.read_transcript
    assert pipeline.CLOUD_STT_PROVIDERS == ("groq", "deepgram")


# ---------------------------------------------------------------- vocabulary


def test_vocabulary_terms_merge_job_and_global(tmp_path, monkeypatch):
    job = {
        "id": "j", "vocabulary": ["Acme", "VibeCut"],
    }
    _write(tmp_path / "job.json", job)
    monkeypatch.setattr(settings_store, "load_settings", lambda: {
        "stt": {"vocabulary": ["Acme", "Globex"]},
    })
    terms = stt.vocabulary_terms(job_dir=tmp_path)
    assert terms == ["Acme", "Globex", "VibeCut"]


def test_apply_vocabulary_corrects_names_and_preserves_punctuation():
    words = [
        {"w": "acme,", "start": 0.0, "end": 0.2, "confidence": 0.8, "segment": 0},
        {"w": "vibecutt", "start": 0.2, "end": 0.4, "confidence": 0.7, "segment": 0},
    ]
    segments = [{"start": 0.0, "end": 0.4, "text": "acme, vibecutt"}]
    corrected_words, corrected_segments = stt.apply_vocabulary(
        words, segments, ["Acme", "VibeCut"],
    )
    assert corrected_words[0]["w"] == "Acme,"
    assert corrected_words[1]["w"] == "VibeCut"
    assert corrected_segments[0]["text"] == "Acme, VibeCut"


# ---------------------------------------------------------------- captions


def _scene(index: int, start: float, duration: float) -> dict:
    return {
        "id": index, "start": start, "end": start + duration,
        "dur": duration, "deep": True, "speech": "", "ocr": "",
    }


def _plan(clips: list[dict], scenes: list[dict]) -> dict:
    return {
        "target": 30, "clips": clips, "hook_scene": clips[0]["scene"],
        "total": round(sum(float(clip["dur"]) for clip in clips), 3),
        "_scenes": scenes,
    }


def test_captions_build_from_v2_word_times(tmp_path):
    transcript = _transcript(tmp_path)
    scenes = [_scene(0, 0.0, 5.0)]
    plan = _plan([{
        "scene": 0, "start": 0.0, "end": 5.0, "dur": 5.0, "role": "hook",
    }], scenes)
    cues, source, _warnings = captions.build_cues(
        plan,
        style=captions.resolve_style(),
        segments=captions.read_transcript_segments(tmp_path),
    )
    assert source == "transcript"
    assert [(cue["start"], cue["end"]) for cue in cues] == [
        (0.0, 0.8), (2.5, 3.2),
    ]
    assert [cue["text"] for cue in cues] == ["Hello.", "World."]
    assert transcript["words"][0]["start"] == 0.0


def test_caption_track_records_transcript_id(tmp_path):
    transcript = _transcript(tmp_path)
    scenes = [_scene(0, 0.0, 5.0)]
    plan = _plan([{
        "scene": 0, "start": 0.0, "end": 5.0, "dur": 5.0, "role": "hook",
    }], scenes)
    job = {
        "id": "cap", "source": {"duration": 5.0},
        "analysis": {"scenes": scenes},
    }
    track = captions.build_track(job, plan, job_dir=tmp_path)
    assert track.transcript_id == transcript["id"]
    payload = track.to_dict()
    assert payload["transcript_id"] == transcript["id"]
    assert captions.CaptionTrack.from_dict(payload).transcript_id == transcript["id"]


def test_legacy_transcript_still_uses_interpolation(tmp_path):
    _write(tmp_path / "transcript" / "transcript.json", {
        "language": "en",
        "segments": [{"start": 0.0, "end": 4.0, "text": "First. Second."}],
    })
    scenes = [_scene(0, 0.0, 4.0)]
    plan = _plan([{
        "scene": 0, "start": 0.0, "end": 4.0, "dur": 4.0, "role": "hook",
    }], scenes)
    cues, source, _warnings = captions.build_cues(
        plan,
        style=captions.resolve_style(),
        segments=captions.read_transcript_segments(tmp_path),
    )
    assert source == "transcript"
    assert [cue["text"] for cue in cues] == ["First.", "Second."]
    assert cues[0]["start"] == 0.0 and cues[-1]["end"] == 4.0
