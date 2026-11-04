"""Voice-fit policy, pitch preservation and the shared settings contract."""

from __future__ import annotations

import shutil
import wave
from pathlib import Path

import numpy as np
import pytest

from real_media import PLACEHOLDER_WAV, real_wav

import settings_store
import voice_fit

HAS_FFMPEG = bool(shutil.which("ffmpeg"))


def _tone(path: Path) -> Path:
    """Two seconds of the founder's steady hum, in the format the fit expects."""
    return real_wav("voice-hum", path, seconds=2.0, channels=2)


def _duration(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / handle.getframerate()


def _f0(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        channels = handle.getnchannels()
        data = handle.readframes(handle.getnframes())
    values = np.frombuffer(data, dtype=np.int16).astype(np.float64)
    mono = values.reshape(-1, channels)[:, 0]
    start = rate // 2
    segment = mono[start:start + rate]
    segment = segment - segment.mean()
    correlation = np.correlate(segment, segment, "full")[len(segment) - 1:]
    low, high = int(rate / 400), int(rate / 80)
    lag = low + int(np.argmax(correlation[low:high]))
    return rate / lag


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg is not installed")
def test_preserve_pitch_keeps_f0_and_shortens(tmp_path):
    source = _tone(tmp_path / "in.wav")
    output = tmp_path / "out.wav"
    result = voice_fit.fit_audio(
        source, output, 1.25, preserve_pitch=True, max_speed=1.25, engine="ffmpeg",
    )
    assert result.backend == "ffmpeg"
    assert result.pitch_shift == 0.0
    assert _duration(output) == pytest.approx(1.6, abs=0.06)
    assert _f0(output) == pytest.approx(_f0(source), abs=5.0)


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg is not installed")
def test_chipmunk_raises_pitch_on_purpose(tmp_path):
    source = _tone(tmp_path / "in.wav")
    output = tmp_path / "out.wav"
    result = voice_fit.fit_audio(
        source, output, 1.25, preserve_pitch=False, max_speed=1.8, engine="ffmpeg",
    )
    assert result.backend == "ffmpeg-resample"
    assert result.pitch_shift == 1.25
    assert result.warning
    assert _f0(output) == pytest.approx(_f0(source) * 1.25, abs=7.0)


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg is not installed")
def test_preserve_voice_caps_at_1_25(tmp_path):
    source = _tone(tmp_path / "in.wav")
    output = tmp_path / "out.wav"
    result = voice_fit.fit_audio(
        source, output, 1.8, preserve_pitch=True, max_speed=1.8, engine="ffmpeg",
    )
    assert result.applied == 1.25
    assert result.capped is True
    assert "capped at 1.25" in result.warning.lower()


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg is not installed")
@pytest.mark.skipif(not voice_fit.signalsmith_available(), reason="python-stretch is not installed")
def test_signalsmith_backend_keeps_pitch(tmp_path):
    source = _tone(tmp_path / "in.wav")
    output = tmp_path / "out.wav"
    result = voice_fit.fit_audio(
        source, output, 1.25, preserve_pitch=True, max_speed=1.25, engine="signalsmith",
    )
    assert result.backend == "signalsmith"
    assert _duration(output) == pytest.approx(1.6, abs=0.08)
    assert _f0(output) == pytest.approx(_f0(source), abs=6.0)


def test_voice_fit_settings_are_normalized():
    value = settings_store._normalize_voice_fit({
        "preserve_pitch": "off",
        "max_speed": "1.80",
        "engine": "SIGNALSMITH",
        "allow_extreme_speed": "yes",
    })
    assert value == {
        "preserve_pitch": False,
        "max_speed": 1.8,
        "engine": "signalsmith",
        "allow_extreme_speed": True,
    }
    assert settings_store._normalize_voice_fit({})["preserve_pitch"] is True


def test_setup_and_voice_room_expose_voice_fit_controls():
    root = Path(__file__).resolve().parents[1]
    classic = (root / "static" / "classic" / "index.html").read_text(encoding="utf-8")
    room = (root / "static" / "voice" / "voiceroom.js").read_text(encoding="utf-8")
    assert 'id="setup-voice-preserve"' in classic
    assert 'id="setup-voice-engine"' in classic
    assert "Preserve voice pitch &amp; tone" in classic
    assert "Advanced voice fit" in room
    assert "Preserve voice pitch & tone" in room
    app = (root / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    assert "option.disabled = preserve" in app
    assert 'dom.setupVoiceMax.value = "1.25"' in app


def test_provider_synthesis_is_normalized_and_fit_once(monkeypatch, tmp_path):
    import audio
    import tts
    import types

    source = tmp_path / "raw.wav"
    source.write_bytes(PLACEHOLDER_WAV)
    seen = {"say": None, "fit": []}

    def fake_say(text, voice, rate, output):
        seen["say"] = rate
        output.write_bytes(source.read_bytes())

    def fake_fit(input_path, output_path, rate, **kwargs):
        seen["fit"].append(rate)
        Path(output_path).write_bytes(Path(input_path).read_bytes())
        return types.SimpleNamespace(applied=rate, backend="ffmpeg", warning="")

    monkeypatch.setattr(audio, "say_available", lambda: True)
    monkeypatch.setattr(audio, "_say_voice", fake_say)
    monkeypatch.setattr(tts.voice_fit, "fit_audio", fake_fit)
    out = tmp_path / "out.wav"
    tts.synthesize_line("say", "Samantha", "hello", out, rate=1.3)
    assert seen["say"] == 1.0
    assert seen["fit"] == [1.3]
    assert out.is_file()


def test_preview_cache_key_includes_voice_fit_policy():
    import tts

    base = tts.line_cache_key("heygen", "m", "nadine", "hello", 1.25, "en")
    other = tts.line_cache_key(
        "heygen", "m", "nadine", "hello", 1.25, "en", policy="different",
    )
    assert base != other


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg is not installed")
def test_effective_cap_warning_names_actual_cap(tmp_path):
    source = _tone(tmp_path / "in.wav")
    output = tmp_path / "out.wav"
    result = voice_fit.fit_audio(
        source, output, 1.3, preserve_pitch=True, max_speed=1.10, engine="ffmpeg",
    )
    assert result.applied == 1.10
    assert "1.10x" in result.warning
    assert "1.25x" not in result.warning


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg is not installed")
def test_slow_chipmunk_mode_keeps_pitch(tmp_path):
    source = _tone(tmp_path / "in.wav")
    output = tmp_path / "out.wav"
    result = voice_fit.fit_audio(
        source, output, 0.8, preserve_pitch=False, max_speed=1.8, engine="ffmpeg",
    )
    assert result.backend == "ffmpeg-slow"
    assert result.pitch_shift == 0.0
    assert _f0(output) == pytest.approx(_f0(source), abs=6.0)
