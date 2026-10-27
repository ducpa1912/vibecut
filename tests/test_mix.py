"""AudioPlan modes, ducking, loudness, SNR and dub slot fitting.

Every engine is faked. No unit test reaches the network or needs a model pack.
The two fixture tests at the bottom are opt-in through environment variables.
"""

from __future__ import annotations

import json
import math
import os
import struct
import wave
from pathlib import Path

import pytest

import audio
import music
import tts


def _tone(path: Path, seconds: float, frequency: float, amplitude: float,
          rate: int = 16000, spans: list[tuple[float, float]] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = bytearray()
    total = max(1, int(seconds * rate))
    for index in range(total):
        at = index / rate
        active = True if spans is None else any(start <= at < end for start, end in spans)
        value = amplitude * math.sin(2 * math.pi * frequency * at) if active else 0.0
        frames.extend(struct.pack("<h", max(-32767, min(32767, int(value * 32767)))))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(bytes(frames))
    return path


# ---------------------------------------------------------------- AudioPlan modes


def test_audio_modes_match_revamp_plan_and_map_to_mixer_branches():
    assert audio.AUDIO_MODES == (
        "original", "original_bed", "voice_over", "dub", "music_only",
    )
    assert audio.mixer_mode("original") == "keep"
    assert audio.mixer_mode("original_bed") == "original_bed"
    assert audio.mixer_mode("voice_over") == "full"
    assert audio.mixer_mode("dub") == "full"
    assert audio.mixer_mode("music_only") == "music_only"
    assert audio.mixer_mode("keep") == "keep"
    assert audio.mixer_mode("bed") == "bed"
    assert audio.mixer_mode("voice") == "voice"
    assert audio.mixer_mode("full") == "full"


def test_audio_plan_defaults_duck_and_loudness():
    plan = audio.normalize_audio_plan({"mode": "original_bed"})
    assert plan["duck_db"] == -12.0
    assert plan["duck"] is True
    assert plan["loudness"] == {"lufs": -14.0, "true_peak": -1.5, "lra": 11.0}
    assert plan["music"]["gain_db"] == -18.0
    custom = audio.normalize_audio_plan({
        "mode": "dub", "duck_db": -18,
        "loudness": {"lufs": -15, "true_peak": -2},
    })
    assert custom["duck_db"] == -18.0
    assert custom["loudness"]["lufs"] == -15.0
    assert custom["loudness"]["true_peak"] == -2.0


def test_plan_from_edit_maps_locked_file_hash_and_translate():
    plan = audio.plan_from_edit({
        "mode": "dub",
        "duck_db": -18,
        "loudness": {"lufs": -15, "true_peak": -1},
        "music": {"source": "library", "file_hash": "a" * 64},
        "voice": {"engine": "say", "voice": "Tingting"},
        "translate": {"target": "zh"},
    })
    assert plan["mode"] == "dub"
    assert plan["music"]["locked_hash"] == "a" * 64
    assert plan["voice"]["voice"] == "Tingting"
    assert plan["loudness"]["lufs"] == -15.0


def test_signature_ignores_original_but_changes_for_bed():
    assert audio.signature({"mode": "original"}) == ""
    assert audio.signature({"mode": "keep"}) == ""
    assert audio.signature({"mode": "original_bed"}) != ""


# ---------------------------------------------------------------- duck + mix


def test_duck_filter_uses_section_8_5_defaults():
    text = audio.duck_filter()
    assert "sidechaincompress" in text
    assert "attack=150" in text
    assert "release=400" in text
    assert "ratio=2.333" in text
    deeper = audio.duck_filter(-18)
    assert "ratio=" in deeper and deeper != text


def test_duck_and_mix_sidechain_graph(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(list(args))

    monkeypatch.setattr(audio, "_run", fake_run)
    voice = tmp_path / "voice.wav"
    bed = tmp_path / "music.wav"
    mixed = audio._duck_and_mix(
        voice, bed, tmp_path, 10.0, True, -18.0, 0.0,
        duck_db=-12, attack_ms=150, release_ms=400,
    )
    graph = calls[-1][calls[-1].index("-filter_complex") + 1]
    assert "sidechaincompress" in graph
    assert "attack=150" in graph and "release=400" in graph
    assert "amix=inputs=2" in graph
    assert mixed == tmp_path / "mix.wav"


def test_duck_and_mix_ducks_original_speech_and_new_bed_under_dub(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(list(args))

    monkeypatch.setattr(audio, "_run", fake_run)
    original = tmp_path / "original.wav"
    mixed = audio._duck_and_mix(
        tmp_path / "voice.wav", tmp_path / "music.wav", tmp_path, 10.0,
        True, -18.0, 0.0, original=original,
    )
    graph = calls[-1][calls[-1].index("-filter_complex") + 1]
    assert "amix=inputs=3" in graph
    assert str(original) in calls[-1]
    assert mixed == tmp_path / "mix.wav"


def test_voice_track_uses_slot_band_and_never_past_1_15(monkeypatch, tmp_path):
    calls: list[list[str]] = []
    monkeypatch.setattr(audio, "_run", lambda args, **kwargs: calls.append(list(args)))
    monkeypatch.setattr(audio, "media_duration", lambda path: 8.0)
    line = {
        "path": tmp_path / "line.wav",
        "text": "hello",
        "offset": 0.0,
        "slot": 4.0,
        "rate": 1.0,
        "fit": tts.plan_slot_fit(8.0, 4.0),
    }
    audio._voice_track([], [line], tmp_path, 10.0, 0.0)
    graph = calls[-1][calls[-1].index("-filter_complex") + 1]
    assert "atempo=1.1500" in graph
    assert "atempo=1.3500" not in graph
    assert line["fit"]["action"] == "shorten"
    assert line["fit"]["overflow"] == 3.4


# ---------------------------------------------------------------- slot fit


def test_slot_fit_band():
    inside = tts.plan_slot_fit(10.0, 10.0)
    assert inside["fits"] is True and inside["action"] == "fit"
    fast = tts.plan_slot_fit(11.4, 10.0)
    assert fast["fits"] is True
    assert fast["tempo"] == 1.14
    too_long = tts.plan_slot_fit(13.0, 10.0)
    assert too_long["fits"] is False
    assert too_long["action"] == "shorten"
    assert too_long["tempo"] == 1.15
    assert too_long["overflow"] == 1.5
    too_short = tts.plan_slot_fit(7.0, 10.0)
    assert too_short["action"] == "pad"
    assert too_short["tempo"] == 0.9


def test_fit_dub_lines_calls_shorten_and_summarises():
    lines = [{
        "path": Path("fake.wav"), "slot": 4.0, "native": 8.0,
    }]
    calls: list[float] = []

    def shorten(line, overflow):
        calls.append(overflow)
        return "短句"

    fitted = tts.fit_dub_lines(lines, shorten=shorten)
    assert calls == [3.4]
    assert fitted[0]["text"] == "短句"
    assert fitted[0]["shortened"] is True
    assert fitted[0]["too_long_by"] == 3.4
    assert tts.slot_fit_summary(fitted) == {
        "total": 1, "fitted": 0, "percent": 0.0, "flagged": 1,
    }


def test_shorten_dub_line_prefers_ai_and_falls_back_to_a_clause(monkeypatch):
    text = "每天清晨，面包店在太阳升起之前就开门了。"
    monkeypatch.setattr(
        audio, "_opencode_json_attempts",
        lambda *args, **kwargs: '["面包店每天天亮前开门。"]',
    )
    assert audio._shorten_dub_line(text, 4.73, 2.58, "zh") == "面包店每天天亮前开门。"
    monkeypatch.setattr(audio, "_opencode_json_attempts", lambda *args, **kwargs: None)
    fallback = audio._shorten_dub_line(text, 4.73, 2.58, "zh")
    assert fallback != text
    assert fallback.endswith("。")


# ---------------------------------------------------------------- SNR


def test_speech_band_snr_reports_ducked_margin(tmp_path):
    voice = _tone(
        tmp_path / "voice.wav", 3.0, 400.0, 0.20,
        spans=[(0.0, 1.0), (1.4, 2.4)],
    )
    bed = _tone(tmp_path / "bed.wav", 3.0, 400.0, 0.20)
    spans = audio.speech_spans(voice)
    assert spans and spans[0][0] == 0.0
    ducked = audio.speech_band_snr(voice, bed, spans, duck_db=-12, music_gain_db=0)
    dry = audio.speech_band_snr(voice, bed, spans, duck_db=0, music_gain_db=0)
    assert ducked is not None and ducked >= 12.0
    assert dry is not None and dry < ducked - 8


def test_measure_loudness_reads_ffmpeg_summary(tmp_path):
    tone = _tone(tmp_path / "tone.wav", 3.0, 440.0, 0.1)
    result = audio.measure_loudness(tone)
    assert result is None or "integrated_lufs" in result


# ---------------------------------------------------------------- build_bed modes


def _fake_bed_job(tmp_path):
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    voice = _tone(tmp_path / "voice.wav", 3.0, 400.0, 0.15, spans=[(0.2, 2.8)])
    bed = _tone(tmp_path / "bed.wav", 8.0, 500.0, 0.10)
    mix = _tone(tmp_path / "mix.wav", 3.0, 400.0, 0.15)
    return job_dir, voice, bed, mix


def test_build_bed_original_bed_mixes_ducked_bed_and_writes_music_json(
    tmp_path, monkeypatch,
):
    job_dir, voice, bed, mix = _fake_bed_job(tmp_path)
    calls: list[list[str]] = []

    monkeypatch.setattr(audio, "_source_audio_bed", lambda *args, **kwargs: voice)
    monkeypatch.setattr(audio, "resolve_music_track", lambda *args, **kwargs: bed)
    monkeypatch.setattr(audio, "beat_grid", lambda path: None)
    monkeypatch.setattr(audio, "ensure_licensed", lambda paths: [])
    monkeypatch.setattr(audio, "media_duration", lambda path: 8.0)

    def fake_loop(path, total, gain_db, tmp, expr=None, offset=0.0):
        return bed

    monkeypatch.setattr(audio, "_music_loop", fake_loop)

    def fake_mix(*args, **kwargs):
        return mix

    monkeypatch.setattr(audio, "_duck_and_mix", fake_mix)

    def fake_run(args, **kwargs):
        calls.append(list(args))
        Path(args[-1]).write_bytes(b"RIFF-final")

    monkeypatch.setattr(audio, "_run", fake_run)
    plan = {"mode": "original_bed", "music": {"source": "library", "track": str(bed)}}
    result = audio.build_bed(
        "source.mp4", {}, {}, [], [], job_dir, plan, 3.0, tmp_path / "tmp",
        lambda *args: None,
    )
    assert result.is_file()
    loudnorm = calls[-1][calls[-1].index("-af") + 1]
    assert loudnorm == "loudnorm=I=-14.00:TP=-1.50:LRA=11.00"
    payload = json.loads((job_dir / "audio" / "music.json").read_text())
    assert payload["source"] == "library"
    assert payload["file_hash"] == music.sha256_file(bed)
    assert payload["licence"]["type"] == "unknown"
    assert plan["_loudness"]["lufs"] == -14.0
    assert plan["_music_meta"]["duck"]["enabled"] is True


def test_build_bed_music_only_never_ducks(tmp_path, monkeypatch):
    job_dir, _voice, bed, mix = _fake_bed_job(tmp_path)
    seen: dict = {}
    monkeypatch.setattr(audio, "resolve_music_track", lambda *args, **kwargs: bed)
    monkeypatch.setattr(audio, "beat_grid", lambda path: None)
    monkeypatch.setattr(audio, "ensure_licensed", lambda paths: [])
    monkeypatch.setattr(audio, "media_duration", lambda path: 8.0)
    monkeypatch.setattr(
        audio, "_music_loop", lambda path, total, gain, tmp, expr=None, offset=0: bed,
    )
    monkeypatch.setattr(
        audio, "_duck_and_mix",
        lambda *args, **kwargs: (seen.update(args=args, kwargs=kwargs), mix)[1],
    )
    monkeypatch.setattr(audio, "_run", lambda args, **kwargs: Path(args[-1]).write_bytes(b"RIFF"))
    plan = {"mode": "music_only", "music": {"source": "library", "track": str(bed)}}
    result = audio.build_bed(
        "source.mp4", {}, {}, [], [], job_dir, plan, 3.0, tmp_path / "tmp",
        lambda *args: None,
    )
    assert result.is_file()
    assert seen["args"][4] is False


def test_build_bed_voice_over_ducks_original_and_new_bed(tmp_path, monkeypatch):
    job_dir, voice, bed, mix = _fake_bed_job(tmp_path)
    original = _tone(tmp_path / "original.wav", 3.0, 300.0, 0.10)
    uploaded = _tone(job_dir / "audio" / "uploaded_voice.wav", 3.0, 500.0, 0.10)
    seen: dict = {}
    monkeypatch.setattr(audio, "_source_audio_bed", lambda *args, **kwargs: original)
    monkeypatch.setattr(audio, "_fit_uploaded_voice", lambda *args, **kwargs: voice)
    monkeypatch.setattr(audio, "resolve_music_track", lambda *args, **kwargs: bed)
    monkeypatch.setattr(audio, "beat_grid", lambda path: None)
    monkeypatch.setattr(audio, "ensure_licensed", lambda paths: [])
    monkeypatch.setattr(audio, "media_duration", lambda path: 8.0)
    monkeypatch.setattr(
        audio, "_music_loop", lambda path, total, gain, tmp, expr=None, offset=0: bed,
    )

    def fake_mix(*args, **kwargs):
        seen.update(kwargs=kwargs)
        return mix

    monkeypatch.setattr(audio, "_duck_and_mix", fake_mix)
    monkeypatch.setattr(audio, "_run", lambda args, **kwargs: Path(args[-1]).write_bytes(b"RIFF"))
    plan = {
        "mode": "voice_over",
        "voice": {
            "source": "upload",
            "upload": str(uploaded.relative_to(job_dir)),
        },
        "music": {"source": "library", "track": str(bed)},
    }
    result = audio.build_bed(
        "source.mp4", {}, {}, [], [], job_dir, plan, 3.0, tmp_path / "tmp",
        lambda *args: None,
    )
    assert result.is_file()
    assert seen["kwargs"]["original"] == original


# ---------------------------------------------------------------- live fixtures


def _fixture_audio(source: Path, target: Path) -> Path:
    import subprocess

    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(source), "-vn",
         "-ac", "1", "-ar", "16000", str(target)],
        check=True,
    )
    return target


def _fixture_scenes(segments: list[dict]) -> tuple[list[dict], list[dict]]:
    scenes: list[dict] = []
    clips: list[dict] = []
    for index, segment in enumerate(segments):
        duration = float(segment["end"]) - float(segment["start"])
        if duration <= 0:
            continue
        scenes.append({
            "id": index, "start": segment["start"], "end": segment["end"],
            "dur": duration, "mid": (float(segment["start"]) + float(segment["end"])) / 2,
            "speech": segment.get("text") or "", "ocr": "", "tags": [],
            "face": True, "crop": {"cx": 0.5, "cy": 0.5}, "crop_mode": "center",
            "hook": 50, "score": 50, "visual_score": 50, "motion_score": 50,
            "audio_score": 50, "text_score": 0, "deep": True,
        })
        clips.append({
            "scene": index, "start": segment["start"], "end": segment["end"],
            "duration": duration, "role": "hook" if index == 0 else "beat",
            "score": 50,
        })
    return scenes, clips


def _synthetic_bed(path: Path, seconds: float) -> Path:
    import subprocess

    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
            (
                "aevalsrc=0.07*(sin(2*PI*261.63*t)+0.8*sin(2*PI*329.63*t)"
                "+0.7*sin(2*PI*392*t))*(0.7+0.3*sin(2*PI*0.125*t)):"
                f"s=48000:d={seconds}"
            ),
            "-ac", "2", "-c:a", "pcm_s16le", str(path),
        ],
        check=True,
    )
    return path


@pytest.mark.skipif(
    not os.environ.get("VIBECUT_FIXTURE_B"),
    reason="live fixture B; set VIBECUT_FIXTURE_B",
)
def test_live_fixture_b_apple_stt_and_ducked_music(tmp_path):
    """Opt-in: zh-CN Apple STT words, ducked bed, LUFS and speech-band SNR."""
    import stt

    source = Path(os.environ["VIBECUT_FIXTURE_B"]).expanduser()
    assert source.is_file(), source
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    wav = _fixture_audio(source, tmp_path / "source.wav")
    transcript = stt.transcribe_apple(wav, job_dir, "zh-CN")
    assert transcript and transcript.get("words"), "Apple STT returned no words"
    assert transcript.get("language", "").startswith("zh")
    segments = [
        segment for segment in transcript["segments"]
        if str(segment.get("text") or "").strip()
    ]
    stt.save_transcript(job_dir, stt.build_transcript(
        engine="apple", model="on-device-3b", language="zh",
        segments=transcript["segments"], words=transcript["words"],
        audio_duration=30.0, source_hash="fixture-b",
    ))
    scenes, clips = _fixture_scenes(segments)
    bed = _synthetic_bed(tmp_path / "bed.wav", 30.0)
    uploaded = audio.store_uploaded_music(bed, job_dir)
    plan = {"clips": clips, "total": 30.0, "_scenes": scenes}
    audio_plan = {
        "mode": "original_bed", "duck": True, "duck_db": -12,
        "loudness": {"lufs": -14, "true_peak": -1.5},
        "music": {
            "source": "upload", "upload": str(uploaded.relative_to(job_dir)),
            "gain_db": -18,
            "licence": {"type": "own", "attestation": "synthetic fixture bed"},
        },
    }
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    final = audio.build_bed(
        str(source), {"fingerprint": "fixture-b"}, plan, clips, scenes,
        job_dir, audio_plan, 30.0, tmp, lambda *args: None, source_lang="zh",
    )
    loudness = audio.measure_loudness(final)
    assert loudness is not None
    assert abs(loudness["integrated_lufs"] + 14.0) <= 1.0
    assert loudness["true_peak_dbtp"] <= -1.0
    snr = audio_plan.get("_speech_snr_db")
    assert snr is not None and snr >= audio.SPEECH_SNR_TARGET_DB
    music_file = job_dir / "audio" / "music.json"
    assert music_file.is_file()
    payload = json.loads(music_file.read_text())
    assert payload["source"] == "upload" and payload["file_hash"]
    assert payload["licence"]["type"] == "own"
    assert payload["brief"] and payload["duck"]["db"] == -12.0
    assert audio.media_duration(final) >= 29.0
    print(
        f"live B: zh words={len(transcript['words'])} "
        f"lufs={loudness['integrated_lufs']} tp={loudness['true_peak_dbtp']} "
        f"snr={snr}dB music_json={payload['source']}",
    )


@pytest.mark.skipif(
    not os.environ.get("VIBECUT_FIXTURE_A"),
    reason="live fixture A; set VIBECUT_FIXTURE_A",
)
def test_live_fixture_a_dub_slot_fit(tmp_path, monkeypatch):
    """Opt-in: dub a real story to Chinese and report slot-fit percent."""
    import stt
    import tts

    source = Path(os.environ["VIBECUT_FIXTURE_A"]).expanduser()
    assert source.is_file(), source
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    wav = _fixture_audio(source, tmp_path / "source.wav")
    transcript = stt.transcribe_apple(wav, job_dir, "en")
    assert transcript and transcript.get("segments"), "Apple STT returned no segments"
    segments = [
        segment for segment in transcript["segments"]
        if str(segment.get("text") or "").strip()
    ]
    stt.save_transcript(job_dir, stt.build_transcript(
        engine="apple", model="on-device-3b", language="en",
        segments=transcript["segments"], words=transcript["words"],
        audio_duration=30.0, source_hash="fixture-a",
    ))
    scenes, clips = _fixture_scenes(segments)
    engine = "kokoro" if audio.kokoro_available() else "say"
    voice = "zf_001" if engine == "kokoro" else "Tingting"
    monkeypatch.setattr(
        audio, "_tts_route_candidates",
        lambda: [{"engine": engine, "provider": "local", "model": engine}],
    )
    plan = {"clips": clips, "total": 30.0, "_scenes": scenes}
    audio_plan = {
        "mode": "dub", "duck": True, "duck_db": -12,
        "loudness": {"lufs": -14, "true_peak": -1.5},
        "voice": {"engine": engine, "voice": voice, "rate": 1.0, "gain_db": 0},
        "translate": {
            "target": "zh", "mode": "literal", "provider": "auto",
            "rewrite_provider": "auto",
        },
        "music": {"source": "none"},
    }
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    final = audio.build_bed(
        str(source), {"fingerprint": "fixture-a"}, plan, clips, scenes,
        job_dir, audio_plan, 30.0, tmp, lambda *args: None, source_lang="en",
    )
    summary = audio_plan.get("_slot_fit") or {}
    assert summary.get("percent", 0) >= 90.0, summary
    loudness = audio.measure_loudness(final)
    assert loudness is not None and abs(loudness["integrated_lufs"] + 14.0) <= 1.0
    assert audio.media_duration(final) >= 29.0
    print(
        f"live A: engine={engine} voice={voice} slot_fit={summary.get('percent')}% "
        f"({summary.get('fitted')}/{summary.get('total')}) "
        f"lufs={loudness['integrated_lufs']} tp={loudness['true_peak_dbtp']}",
    )
