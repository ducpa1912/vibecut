"""Clean voice reference extraction.

Sound comes from the founder's real files in data/media. Model binaries and
ffmpeg are faked, so the file runs without Demucs, DeepFilterNet or pyannote.
One test at the bottom needs a real ffmpeg.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import threading
import time
import types
import wave
from pathlib import Path

import pytest

from real_media import real_wav

import audio
import settings_store
import voice_extract


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch, tmp_path):
    """Cache keys are content hashes, so tests with equal bytes must not share."""
    monkeypatch.setattr(audio, "CACHE", tmp_path / "cache")


@pytest.fixture
def fake_torch(monkeypatch):
    """Diarization tests fake pyannote; torch is optional in CI too."""
    module = types.ModuleType("torch")
    module.backends = types.SimpleNamespace(
        mps=types.SimpleNamespace(is_available=lambda: False),
    )
    module.device = lambda name: name
    monkeypatch.setitem(sys.modules, "torch", module)
    return module


def _speech_wav(path: Path, seconds: float = 6.0, *, gain_db: float | None = None) -> Path:
    """The founder's real voice as 48 kHz mono PCM; ``gain_db`` overdrives a take."""
    return real_wav("voice-clean", path, seconds=seconds, gain_db=gain_db)


def _stub_pipeline(monkeypatch, *, speech: Path | None = None, clipped: bool = False):
    """Keep every model and ffmpeg call out of the unit tests."""
    calls = {"decode": 0}

    def fake_decode(source, work, cancel_event):
        calls["decode"] += 1
        output = work / "source.wav"
        if speech is not None and speech.is_file():
            shutil.copyfile(speech, output)
        else:
            _speech_wav(output, gain_db=40.0 if clipped else None)
        return output

    def fake_normalize(path, output, *, target_lufs, sample_rate, cancel_event=None):
        shutil.copyfile(path, output)
        return {"gain_db": 0.0, "measured": None, "warning": ""}

    def fake_denoise(path, work, cancel_event, mode="auto"):
        return path, voice_extract.DENOISE_FALLBACK, []

    monkeypatch.setattr(voice_extract, "_decode", fake_decode)
    monkeypatch.setattr(voice_extract, "_normalize", fake_normalize)
    monkeypatch.setattr(voice_extract, "_denoise_stage", fake_denoise)
    monkeypatch.setattr(audio, "demucs_available", lambda: False)
    monkeypatch.setattr(voice_extract, "_deepfilter", lambda: None)
    monkeypatch.setattr(voice_extract, "_audio_separator", lambda: None)
    monkeypatch.setattr(voice_extract, "_roformer_model", lambda: None)
    monkeypatch.setattr(voice_extract, "_silero", lambda: False)
    monkeypatch.setattr(voice_extract, "_pyannote", lambda: False)
    monkeypatch.setattr(audio, "measure_loudness", lambda path: None)
    monkeypatch.setattr(audio, "_ffmpeg", lambda: "ffmpeg")
    return calls


# ---------------------------------------------------------------- end to end


def test_extract_returns_mono_clean_clip_and_plain_report(tmp_path, monkeypatch):
    calls = _stub_pipeline(monkeypatch)
    source = tmp_path / "talk.mp4"
    source.write_bytes(b"not really a video")
    out_dir = tmp_path / "out"
    report = voice_extract.extract_clean_voice(str(source), out_dir)

    clean = out_dir / "clean_voice.wav"
    assert clean.is_file()
    assert report["path"] == str(clean)
    assert report["duration"] > 3.0
    assert report["sample_rate"] == 44100
    assert report["channels"] == 1
    assert report["models"]["separation"] is None
    assert report["models"]["denoise"] == "afftdn"
    assert report["models"]["vad"] == "energy"
    assert report["models"]["diarization"] is None
    assert report["cached"] is False
    assert calls["decode"] == 1
    with wave.open(str(clean), "rb") as handle:
        assert handle.getnchannels() == 1
    quality = report["quality"]
    assert quality["snr_db"] is not None and quality["snr_db"] > 5
    assert quality["music_noise_residual_db"] is not None
    assert quality["clipping"]["clipped"] is False
    assert "No voice separation engine is installed" in " ".join(report["warnings"])


def test_extract_caps_the_clip_at_target_seconds(tmp_path, monkeypatch):
    _stub_pipeline(monkeypatch)
    source = tmp_path / "long.mov"
    source.write_bytes(b"x")
    report = voice_extract.extract_clean_voice(
        source, tmp_path / "out", target_seconds=3.0,
    )
    assert report["duration"] == pytest.approx(3.0, abs=0.2)
    assert report["duration"] <= 3.05


def test_extract_reports_source_clipping(tmp_path, monkeypatch):
    _stub_pipeline(monkeypatch, clipped=True)
    source = tmp_path / "hot.wav"
    source.write_bytes(b"x")
    report = voice_extract.extract_clean_voice(source, tmp_path / "out")
    assert report["quality"]["source_clipping"]["clipped"] is True
    assert any("clips at full scale" in item for item in report["warnings"])


def test_extract_fails_plainly_when_there_is_no_speech(tmp_path, monkeypatch):
    silent = real_wav("room-silence", tmp_path / "silent.wav", seconds=6.0)
    _stub_pipeline(monkeypatch, speech=silent)
    source = tmp_path / "silent.mp4"
    source.write_bytes(b"x")
    with pytest.raises(audio.AudioError, match="No speech was found"):
        voice_extract.extract_clean_voice(source, tmp_path / "out")


def test_extract_rejects_a_target_shorter_than_one_second(tmp_path, monkeypatch):
    _stub_pipeline(monkeypatch)
    source = tmp_path / "talk.mp4"
    source.write_bytes(b"x")
    with pytest.raises(audio.AudioError, match="at least 1 second"):
        voice_extract.extract_clean_voice(source, tmp_path / "out", target_seconds=0.5)


def test_extract_reports_missing_source(tmp_path):
    with pytest.raises(audio.AudioError, match="Source file not found"):
        voice_extract.extract_clean_voice(tmp_path / "missing.mp4", tmp_path / "out")


def test_extract_respects_a_set_cancel_event(tmp_path, monkeypatch):
    _stub_pipeline(monkeypatch)
    source = tmp_path / "talk.mp4"
    source.write_bytes(b"x")
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(audio.AudioError, match="cancelled"):
        voice_extract.extract_clean_voice(
            source, tmp_path / "out", cancel_event=cancel,
        )


def test_extract_declines_a_speaker_filter_without_pyannote(tmp_path, monkeypatch):
    _stub_pipeline(monkeypatch)
    source = tmp_path / "panel.mp4"
    source.write_bytes(b"x")
    with pytest.raises(audio.AudioError, match="pyannote.audio"):
        voice_extract.extract_clean_voice(source, tmp_path / "out", speaker=1)


def test_extract_runs_separation_when_demucs_is_available(tmp_path, monkeypatch):
    _stub_pipeline(monkeypatch)
    monkeypatch.setattr(audio, "demucs_available", lambda: True)
    monkeypatch.setattr(
        voice_extract, "_separate_stage",
        lambda decoded, fingerprint, work, cancel_event, engine="best": (decoded, "htdemucs_ft"),
    )
    source = tmp_path / "music_video.mp4"
    source.write_bytes(b"x")
    report = voice_extract.extract_clean_voice(source, tmp_path / "out")
    assert report["models"]["separation"] == "htdemucs_ft"
    assert "No voice separation engine" not in " ".join(report["warnings"])


def test_cache_hit_skips_decode_and_pipeline(tmp_path, monkeypatch):
    calls = _stub_pipeline(monkeypatch)
    source = tmp_path / "talk.mp4"
    source.write_bytes(b"same bytes")
    first = voice_extract.extract_clean_voice(source, tmp_path / "out1")
    second = voice_extract.extract_clean_voice(source, tmp_path / "out2")
    assert first["cached"] is False
    assert second["cached"] is True
    assert calls["decode"] == 1
    assert Path(second["path"]).is_file()
    assert second["duration"] == first["duration"]


def test_cache_key_changes_with_target_and_speaker(tmp_path):
    source = tmp_path / "talk.mp4"
    source.write_bytes(b"x")
    base = voice_extract._fingerprint(source, {"target": 30.0, "speaker": None})
    other = voice_extract._fingerprint(source, {"target": 20.0, "speaker": None})
    speaker = voice_extract._fingerprint(source, {"target": 30.0, "speaker": 1})
    assert base != other != speaker


# ---------------------------------------------------------------- stages


def test_decode_asks_for_mono_48k_source(tmp_path, monkeypatch):
    seen = {}

    def fake_bed(source, tmp, cancel_event=None, **kwargs):
        seen.update(source=source, kwargs=kwargs)
        return tmp / kwargs["name"]

    monkeypatch.setattr(audio, "_source_audio_bed", fake_bed)
    result = voice_extract._decode(tmp_path / "clip.mp4", tmp_path, None)
    assert result == tmp_path / "source.wav"
    assert seen["kwargs"] == {"channels": 1, "rate": 48000, "name": "source.wav"}


def test_denoise_stage_prefers_deepfilternet(tmp_path, monkeypatch):
    monkeypatch.setattr(voice_extract, "_deepfilter", lambda: "/opt/deep-filter")
    monkeypatch.setattr(audio, "_ffmpeg", lambda: "ffmpeg")

    def fake_run(cmd, **kwargs):
        output_dir = Path(cmd[cmd.index("-o") + 1])
        (output_dir / "clip_DeepFilterNet3.wav").write_bytes(b"RIFF")
        return None

    monkeypatch.setattr(audio, "_run", fake_run)
    path, name, warnings = voice_extract._denoise_stage(tmp_path / "in.wav", tmp_path, None)
    assert name == "deepfilternet3"
    assert path.name == "clip_DeepFilterNet3.wav"
    assert warnings == []


def test_denoise_stage_falls_back_to_ffmpeg_when_the_model_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(voice_extract, "_deepfilter", lambda: "/opt/deep-filter")
    commands = []

    def fake_run(cmd, **kwargs):
        commands.append(cmd)
        if len(commands) == 1:
            raise audio.AudioError("Audio command failed.\nmodel missing")
        Path(cmd[-1]).write_bytes(b"RIFF")
        return None

    monkeypatch.setattr(audio, "_run", fake_run)
    path, name, warnings = voice_extract._denoise_stage(tmp_path / "in.wav", tmp_path, None)
    assert name == "afftdn"
    assert path.name == "denoised.wav"
    assert any("DeepFilterNet failed" in item for item in warnings)
    assert voice_extract.DENOISE_FILTER in commands[-1]


def test_normalize_clamps_gain_to_true_peak_headroom(tmp_path, monkeypatch):
    monkeypatch.setattr(
        audio, "measure_loudness",
        lambda path: {"integrated_lufs": -30.0, "true_peak_dbtp": -2.0},
    )
    commands = []
    monkeypatch.setattr(audio, "_run", lambda cmd, **kwargs: commands.append(cmd))
    monkeypatch.setattr(audio, "_ffmpeg", lambda: "ffmpeg")
    result = voice_extract._normalize(
        tmp_path / "in.wav", tmp_path / "out.wav",
        target_lufs=-16.0, sample_rate=44100,
    )
    assert result["gain_db"] == 0.5
    graph = commands[-1][commands[-1].index("-af") + 1]
    assert "volume=0.50dB" in graph
    assert commands[-1][commands[-1].index("-ar") + 1] == "44100"
    assert commands[-1][commands[-1].index("-ac") + 1] == "1"


def test_splice_removes_gaps_and_writes_pcm(tmp_path):
    source = _speech_wav(tmp_path / "in.wav", seconds=6.0)
    spans = voice_extract._select_spans(
        audio.speech_spans(source, threshold_db=-30.0, min_speech=0.2, min_silence=0.2),
        None,
    )
    output = tmp_path / "out.wav"
    timeline, duration = voice_extract._splice(source, spans, output)
    assert output.is_file()
    assert duration == pytest.approx(sum(end - start for start, end in spans), abs=0.05)
    assert timeline[-1][1] == pytest.approx(duration, abs=0.01)
    with wave.open(str(output), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getframerate() == 48000
        assert handle.getsampwidth() == 2


def test_select_spans_pads_merges_and_caps():
    spans = [(1.0, 2.0), (2.1, 3.0), (8.0, 9.0)]
    selected = voice_extract._select_spans(spans, 4.0, pad=0.12)
    assert len(selected) == 2
    assert selected[0] == (pytest.approx(0.88), pytest.approx(3.12))
    total = sum(end - start for start, end in selected)
    assert total <= 4.0 + 1e-9


def test_select_spans_caps_a_none_target_at_five_minutes():
    spans = [(index * 10.0, index * 10.0 + 8.0) for index in range(40)]
    selected = voice_extract._select_spans(spans, None, pad=0.0)
    total = sum(end - start for start, end in selected)
    assert total == pytest.approx(voice_extract.MAX_CLIP_SECONDS)


def test_available_backends_reports_installed_engines(monkeypatch):
    monkeypatch.setattr(audio, "demucs_available", lambda: True)
    monkeypatch.setattr(voice_extract, "_audio_separator", lambda: None)
    monkeypatch.setattr(voice_extract, "_roformer_model", lambda: None)
    monkeypatch.setattr(voice_extract, "_deepfilter", lambda: "/opt/deep-filter")
    monkeypatch.setattr(voice_extract, "_silero", lambda: True)
    monkeypatch.setattr(voice_extract, "_pyannote", lambda: True)
    assert voice_extract.available_backends() == {
        "separation": "htdemucs_ft",
        "separations": {"htdemucs": True, "htdemucs_ft": True, "roformer": False},
        "denoise": "deepfilternet3",
        "vad": "silero",
        "diarization": "pyannote",
    }


def test_speaker_filter_keeps_only_the_chosen_speaker(tmp_path, monkeypatch, fake_torch):
    annotation = types.SimpleNamespace(
        itertracks=lambda yield_label=False: iter([
            (types.SimpleNamespace(start=0.0, end=2.0), None, "SPEAKER_00"),
            (types.SimpleNamespace(start=2.0, end=4.0), None, "SPEAKER_01"),
            (types.SimpleNamespace(start=4.0, end=6.0), None, "SPEAKER_00"),
        ]),
    )

    class FakePipeline:
        @staticmethod
        def from_pretrained(name, use_auth_token=None):
            return FakePipeline()

        def to(self, device):
            return self

        def __call__(self, path):
            return annotation

    fake_module = types.ModuleType("pyannote.audio")
    fake_module.Pipeline = FakePipeline
    monkeypatch.setitem(sys.modules, "pyannote.audio", fake_module)
    monkeypatch.setitem(sys.modules, "pyannote", types.ModuleType("pyannote"))
    monkeypatch.setattr(voice_extract, "_pyannote", lambda: True)
    monkeypatch.setattr(settings_store, "get_secret", lambda name: "hf_test")
    spans = [(0.0, 6.0)]
    kept, label, warnings = voice_extract._speaker_spans(
        tmp_path / "in.wav", spans, 1, None,
    )
    assert label == "pyannote:SPEAKER_00"
    assert kept == [(0.0, 2.0), (4.0, 6.0)]
    assert warnings == []


def test_speaker_filter_warns_about_overlapping_speech(tmp_path, monkeypatch, fake_torch):
    annotation = types.SimpleNamespace(
        itertracks=lambda yield_label=False: iter([
            (types.SimpleNamespace(start=0.0, end=3.0), None, "SPEAKER_00"),
            (types.SimpleNamespace(start=2.0, end=4.0), None, "SPEAKER_01"),
        ]),
    )

    class FakePipeline:
        @staticmethod
        def from_pretrained(name, token=None, use_auth_token=None):
            return FakePipeline()

        def to(self, device):
            return self

        def __call__(self, path):
            return annotation

    fake_module = types.ModuleType("pyannote.audio")
    fake_module.Pipeline = FakePipeline
    monkeypatch.setitem(sys.modules, "pyannote.audio", fake_module)
    monkeypatch.setitem(sys.modules, "pyannote", types.ModuleType("pyannote"))
    monkeypatch.setattr(voice_extract, "_pyannote", lambda: True)
    monkeypatch.setattr(settings_store, "get_secret", lambda name: "hf_test")
    _kept, _label, warnings = voice_extract._speaker_spans(
        tmp_path / "in.wav", [(0.0, 4.0)], 1, None,
    )
    assert any("Overlapping speech" in item for item in warnings)


def test_speaker_filter_names_available_labels(tmp_path, monkeypatch, fake_torch):
    annotation = types.SimpleNamespace(
        itertracks=lambda yield_label=False: iter([
            (types.SimpleNamespace(start=0.0, end=2.0), None, "SPEAKER_00"),
        ]),
    )

    class FakePipeline:
        @staticmethod
        def from_pretrained(name, use_auth_token=None):
            return FakePipeline()

        def to(self, device):
            return self

        def __call__(self, path):
            return annotation

    fake_module = types.ModuleType("pyannote.audio")
    fake_module.Pipeline = FakePipeline
    monkeypatch.setitem(sys.modules, "pyannote.audio", fake_module)
    monkeypatch.setitem(sys.modules, "pyannote", types.ModuleType("pyannote"))
    monkeypatch.setattr(voice_extract, "_pyannote", lambda: True)
    monkeypatch.setattr(settings_store, "get_secret", lambda name: "hf_test")
    with pytest.raises(audio.AudioError, match="Available: SPEAKER_00"):
        voice_extract._speaker_spans(tmp_path / "in.wav", [(0.0, 2.0)], "SPEAKER_09", None)


def test_speaker_filter_reports_missing_torch(tmp_path, monkeypatch):
    monkeypatch.setattr(voice_extract, "_pyannote", lambda: True)
    monkeypatch.setattr(settings_store, "get_secret", lambda name: "hf_test")
    import builtins

    original = builtins.__import__

    def no_torch(name, *args, **kwargs):
        if name == "torch":
            raise ImportError("No module named 'torch'")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_torch)
    monkeypatch.setattr(
        voice_extract.importlib.util, "find_spec",
        lambda name: None if name == "torch" else importlib.util.find_spec(name),
    )
    with pytest.raises(audio.AudioError, match="needs torch"):
        voice_extract._speaker_spans(
            tmp_path / "in.wav", [(0.0, 2.0)], 1, None,
        )


# ---------------------------------------------------------------- denoise + engines


def test_pick_separation_prefers_roformer_then_finetuned_demucs():
    both = {"separations": {"htdemucs": True, "htdemucs_ft": True, "roformer": True}}
    demucs_only = {"separations": {"htdemucs": True, "htdemucs_ft": True, "roformer": False}}
    assert voice_extract._pick_separation("best", both) == "roformer"
    assert voice_extract._pick_separation("best", demucs_only) == "htdemucs_ft"
    assert voice_extract._pick_separation(False, both) is None
    assert voice_extract._pick_separation("htdemucs", both) == "htdemucs"
    with pytest.raises(audio.AudioError, match="Mel-Band RoFormer"):
        voice_extract._pick_separation("roformer", demucs_only)


def test_roformer_stage_runs_audio_separator(tmp_path, monkeypatch):
    monkeypatch.setattr(voice_extract, "_audio_separator", lambda: "/bin/audio-separator")
    monkeypatch.setattr(voice_extract, "_roformer_model", lambda: Path("/models/mel.ckpt"))
    monkeypatch.setattr(audio, "_ffmpeg", lambda: "ffmpeg")

    def fake_run(cmd, **kwargs):
        if "--model_filename" in cmd:
            output = Path(cmd[cmd.index("--output_dir") + 1])
            (output / "clip_(Vocals)_mel.wav").write_bytes(b"RIFF" + b"\0" * 2048)
        else:
            Path(cmd[-1]).write_bytes(b"RIFF" + b"\0" * 2048)
        return None

    monkeypatch.setattr(audio, "_run", fake_run)
    path, label = voice_extract._separate_stage(
        tmp_path / "in.wav", "fp", tmp_path, None, engine="roformer",
    )
    assert label == "roformer"
    assert path.name == "separated.wav"
    assert path.is_file()


def test_denoise_compare_keeps_the_cleaner_variant(tmp_path, monkeypatch):
    noisy = real_wav("voice-noisy", tmp_path / "noisy.wav", seconds=4.0)
    clean = _speech_wav(tmp_path / "clean.wav", seconds=4.0)

    def fake_denoise(path, work, cancel_event, mode="auto"):
        work.mkdir(parents=True, exist_ok=True)
        if mode == "afftdn":
            output = work / "denoised.wav"
            shutil.copyfile(noisy, output)
            return output, "afftdn", []
        output = work / "denoised.wav"
        shutil.copyfile(clean, output)
        return output, "deepfilternet3", []

    monkeypatch.setattr(voice_extract, "_deepfilter", lambda: "/opt/deep-filter")
    monkeypatch.setattr(voice_extract, "_denoise_stage", fake_denoise)
    path, label, warnings, trials = voice_extract._denoise_compare(
        tmp_path / "in.wav", tmp_path / "work", None,
    )
    assert label == "deepfilternet3"
    assert {trial["engine"] for trial in trials} == {"afftdn", "deepfilternet3"}
    assert any(trial["kept"] for trial in trials if trial["engine"] == "deepfilternet3")
    assert path.is_file()


def test_denoise_compare_flags_a_close_call(tmp_path, monkeypatch):
    same = _speech_wav(tmp_path / "same.wav", seconds=4.0)

    def fake_denoise(path, work, cancel_event, mode="auto"):
        work.mkdir(parents=True, exist_ok=True)
        output = work / "denoised.wav"
        shutil.copyfile(same, output)
        return output, ("afftdn" if mode == "afftdn" else "deepfilternet3"), []

    monkeypatch.setattr(voice_extract, "_deepfilter", lambda: "/opt/deep-filter")
    monkeypatch.setattr(voice_extract, "_denoise_stage", fake_denoise)
    _path, _label, warnings, _trials = voice_extract._denoise_compare(
        tmp_path / "in.wav", tmp_path / "work", None,
    )
    assert any("within 0.5 dB" in item for item in warnings)


# ---------------------------------------------------------------- candidates


def _long_speech(path: Path) -> Path:
    return _speech_wav(path, seconds=90.0)


def test_find_candidates_returns_three_to_five_batches(tmp_path, monkeypatch):
    speech = _long_speech(tmp_path / "long.wav")
    calls = _stub_pipeline(monkeypatch, speech=speech)
    source = tmp_path / "long.mp4"
    source.write_bytes(b"x")
    report = voice_extract.find_voice_candidates(
        source, tmp_path / "out", count=3, clip_seconds=20.0,
    )
    candidates = report["candidates"]
    assert len(candidates) == 3
    assert calls["decode"] == 1
    for item in candidates:
        assert Path(item["path"]).is_file()
        assert 2.0 <= item["duration"] <= 20.05
        assert item["quality"]["snr_db"] is not None
    assert any("more than one speaker" in item for item in report["warnings"])
    assert len({item["path"] for item in candidates}) == 3


def test_candidate_cache_skips_the_second_run(tmp_path, monkeypatch):
    speech = _long_speech(tmp_path / "long.wav")
    calls = _stub_pipeline(monkeypatch, speech=speech)
    source = tmp_path / "long.mp4"
    source.write_bytes(b"x")
    first = voice_extract.find_voice_candidates(
        source, tmp_path / "out1", count=3, clip_seconds=20.0,
    )
    second = voice_extract.find_voice_candidates(
        source, tmp_path / "out2", count=3, clip_seconds=20.0,
    )
    assert calls["decode"] == 1
    assert second["cached"] is True
    assert len(second["candidates"]) == len(first["candidates"])
    assert all(Path(item["path"]).is_file() for item in second["candidates"])


def test_candidate_count_and_clip_are_validated(tmp_path, monkeypatch):
    _stub_pipeline(monkeypatch)
    source = tmp_path / "talk.mp4"
    source.write_bytes(b"x")
    with pytest.raises(audio.AudioError, match="between 1 and 5"):
        voice_extract.find_voice_candidates(source, tmp_path / "out", count=6)
    with pytest.raises(audio.AudioError, match="clip_seconds"):
        voice_extract.find_voice_candidates(source, tmp_path / "out", clip_seconds=0.5)


# ---------------------------------------------------------------- audio.py hooks


def test_separate_voice_keeps_the_vocal_stem_and_separate_vocals_keeps_the_bed(
    tmp_path, monkeypatch,
):
    created = []

    def fake_run(cmd, **kwargs):
        created.append(list(cmd))
        if "demucs" in cmd:
            model = cmd[cmd.index("-n") + 1]
            output = Path(cmd[cmd.index("-o") + 1]) / model / "clip"
            output.mkdir(parents=True, exist_ok=True)
            (output / "vocals.wav").write_bytes(b"RIFF" + b"\0" * 2048)
            (output / "no_vocals.wav").write_bytes(b"RIFF" + b"\0" * 2048)
        else:
            Path(cmd[-1]).write_bytes(b"RIFF" + b"\0" * 2048)
        return None

    monkeypatch.setattr(audio, "demucs_available", lambda: True)
    monkeypatch.setattr(audio, "_run", fake_run)
    monkeypatch.setattr(audio, "_ffmpeg", lambda: "ffmpeg")
    voice = audio.separate_voice("clip.wav", "test-voice-hook")
    fine = audio.separate_voice("clip.wav", "test-ft-hook", model="htdemucs_ft")
    bed = audio.separate_vocals("clip.wav", "test-bed-hook")
    try:
        assert voice.name == "vocals.flac"
        assert fine.name == "vocals-htdemucs_ft.flac"
        assert bed.name == "no_vocals.flac"
        assert voice.is_file() and fine.is_file() and bed.is_file()
        demucs_calls = [cmd for cmd in created if "demucs" in cmd]
        assert len(demucs_calls) == 3
        assert [cmd[cmd.index("-n") + 1] for cmd in demucs_calls] == [
            "htdemucs", "htdemucs_ft", "htdemucs",
        ]
    finally:
        for path in (voice, fine, bed):
            shutil.rmtree(path.parent, ignore_errors=True)


# ---------------------------------------------------------------- opt-in smoke


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_ffmpeg_denoise_and_export_smoke(tmp_path):
    source = _speech_wav(tmp_path / "in.wav", seconds=4.0)
    denoised, name, _warnings = voice_extract._denoise_stage(source, tmp_path, None)
    assert name == "afftdn"
    assert denoised.is_file() and denoised.stat().st_size > 1024
    exported = tmp_path / "clean.wav"
    voice_extract._normalize(
        denoised, exported, target_lufs=-16.0, sample_rate=44100,
    )
    with wave.open(str(exported), "rb") as handle:
        assert handle.getframerate() == 44100
        assert handle.getnchannels() == 1


# ---------------------------------------------------------------- cache hygiene


def test_same_recording_under_a_new_temp_path_hits_the_cache(tmp_path, monkeypatch):
    calls = _stub_pipeline(monkeypatch)
    first = tmp_path / "upload-1" / "raw.m4a"
    second = tmp_path / "upload-2" / "raw.m4a"
    for path in (first, second):
        path.parent.mkdir()
        path.write_bytes(b"the same recording")
    voice_extract.extract_clean_voice(first, tmp_path / "out1")
    report = voice_extract.extract_clean_voice(second, tmp_path / "out2")
    assert report["cached"] is True
    assert calls["decode"] == 1


def test_candidate_cache_hit_after_a_skipped_window(tmp_path, monkeypatch):
    speech = _long_speech(tmp_path / "long.wav")
    calls = _stub_pipeline(monkeypatch, speech=speech)
    source = tmp_path / "long.mp4"
    source.write_bytes(b"x")
    voice_extract.find_voice_candidates(source, tmp_path / "out1", count=3, clip_seconds=20.0)
    [report_path] = (tmp_path / "cache" / "voice_refs").glob("*/report.json")
    root = report_path.parent
    data = json.loads(report_path.read_text())
    # Simulate a first run that skipped window 2: files 01 and 03 only.
    last = data["candidates"][-1]
    (root / f"candidate-{last['index']:02d}.wav").rename(root / "candidate-09.wav")
    last["index"] = 9
    data["candidates"] = [data["candidates"][0], last]
    (root / "candidate-02.wav").unlink(missing_ok=True)
    report_path.write_text(json.dumps(data))
    second = voice_extract.find_voice_candidates(
        source, tmp_path / "out2", count=3, clip_seconds=20.0,
    )
    assert second["cached"] is True
    assert calls["decode"] == 1
    assert [Path(item["path"]).name for item in second["candidates"]] == [
        "candidate-01.wav", "candidate-09.wav",
    ]


def test_prune_cache_covers_voice_refs_and_clone_scratch(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    monkeypatch.setattr(audio, "CACHE", cache)
    old = time.time() - 30 * 86400
    files = [cache / "voice_refs" / "abc" / "clean.wav", cache / "voice-clone" / "x" / "raw.m4a"]
    for path in files:
        path.parent.mkdir(parents=True)
        path.write_bytes(b"x" * 2048)
        os.utime(path, (old, old))
    usage = audio.cache_usage()
    assert usage["voice_refs"]["files"] == 1
    assert usage["voice-clone"]["files"] == 1
    audio.prune_cache(max_gb=0, days=14)
    assert not any(path.exists() for path in files)


def test_prune_keeps_a_live_demucs_run_and_drops_a_stale_one(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    monkeypatch.setattr(audio, "CACHE", cache)
    live = cache / "stems" / "run-live" / "htdemucs" / "clip" / "vocals.wav"
    stale = cache / "stems" / "run-stale"
    live.parent.mkdir(parents=True)
    live.write_bytes(b"x" * 4096)
    stale.mkdir(parents=True)
    old = time.time() - 3 * 3600
    os.utime(stale, (old, old))
    audio.prune_cache(max_gb=0.000001, days=14)
    assert live.is_file()
    assert not stale.exists()


def test_two_concurrent_separations_do_not_share_scratch(tmp_path, monkeypatch):
    monkeypatch.setattr(audio, "demucs_available", lambda: True)
    monkeypatch.setattr(audio.packs, "find_command", lambda *a: None)
    monkeypatch.setattr(audio, "_ffmpeg", lambda: "ffmpeg")
    both_running = threading.Barrier(2, timeout=5)
    scratch: list[Path] = []

    def fake_run(cmd, timeout=0, cancel_event=None):
        if "--two-stems=vocals" in cmd:
            if "-d" in cmd:
                raise audio.AudioError("no mps")
            output = Path(cmd[cmd.index("-o") + 1])
            scratch.append(output)
            stem = output / "htdemucs" / "clip"
            stem.mkdir(parents=True, exist_ok=True)
            (stem / "vocals.wav").write_bytes(b"RIFF" + b"\0" * 2048)
            both_running.wait()  # the other run is mid-flight here
        else:
            Path(cmd[-1]).write_bytes(b"fLaC" + b"\0" * 2048)

    monkeypatch.setattr(audio, "_run", fake_run)
    results: list[Path] = []
    errors: list[Exception] = []

    def separate(fingerprint):
        try:
            results.append(audio.separate_voice("clip.wav", fingerprint))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=separate, args=(name,)) for name in ("aaa", "bbb")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert errors == []
    assert len(results) == 2
    assert len(set(scratch)) == 2
    assert not any(path.exists() for path in scratch)
