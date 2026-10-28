"""Opt-in acceptance run with real speech, music and reverb.

Set ``VIBECUT_VOICE_ACCEPTANCE=1`` on macOS with ffmpeg and ``say`` installed:

    VIBECUT_VOICE_ACCEPTANCE=1 python3 -m pytest -q tests/test_voice_extract_acceptance.py

It builds a 90 s fixture: two synthetic speakers, music bed, pink noise and
echo, then checks a real ffmpeg-only extraction and candidate search. It does
not download Demucs or any model. Set ``VIBECUT_VOICE_ACCEPTANCE_SEPARATE=1``
to add a real Demucs pass (slow, downloads weights on first use).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import wave
from pathlib import Path

import pytest

import audio
import voice_extract

pytestmark = pytest.mark.skipif(
    os.environ.get("VIBECUT_VOICE_ACCEPTANCE") != "1",
    reason="set VIBECUT_VOICE_ACCEPTANCE=1 to run the real audio acceptance",
)


def _say(path: Path, voice: str, text: str) -> Path:
    subprocess.run(
        ["say", "-v", voice, "-o", str(path), "--data-format=LEI16@44100", text],
        check=True, timeout=120,
    )
    return path


def _fixture(tmp_path: Path) -> Path:
    if not shutil.which("say"):
        pytest.skip("macOS say is not available")
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is not installed")
    first = _say(
        tmp_path / "a.wav", "Samantha",
        "The quick brown fox jumps over the lazy dog. "
        "This is a clean reference recording for voice cloning.",
    )
    second = _say(
        tmp_path / "b.wav", "Alex",
        "A second speaker talks over the first one here. "
        "That overlap is what the report should catch.",
    )
    third = _say(
        tmp_path / "c.wav", "Samantha",
        "Later the main speaker returns with a few more sentences. "
        "Names and numbers help a clone: VibeCut, two thousand twenty six.",
    )
    output = tmp_path / "source.wav"
    graph = (
        "[0:a]atrim=0:90,asetpts=N/SR/TB[base];"
        "[1:a]aresample=44100,adelay=2000,aecho=0.8:0.65:80:0.25[v1];"
        "[2:a]aresample=44100,adelay=31000,aecho=0.8:0.65:80:0.25[v2];"
        "[3:a]aresample=44100,adelay=30000,aecho=0.8:0.65:80:0.25[v3];"
        "[base][v1][v2][v3]amix=inputs=4:normalize=0[voice];"
        "sine=frequency=196:sample_rate=44100:duration=90,volume=0.04[music];"
        "anoisesrc=color=pink:sample_rate=44100:amplitude=0.006:duration=90[noise];"
        "[voice][music][noise]amix=inputs=3:normalize=0,alimiter=limit=0.9[out]"
    )
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:duration=90",
        "-i", str(first), "-i", str(second), "-i", str(third),
        "-filter_complex", graph, "-map", "[out]",
        "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(output),
    ], check=True, timeout=180)
    return output


def _wav_info(path: Path) -> tuple[int, int]:
    with wave.open(str(path), "rb") as handle:
        return handle.getframerate(), handle.getnchannels()


def test_real_music_reverb_fixture_single_clip(tmp_path):
    source = _fixture(tmp_path)
    report = voice_extract.extract_clean_voice(
        source, tmp_path / "out",
        separate=False, denoise="afftdn", target_seconds=20.0,
    )
    clean = Path(report["path"])
    assert clean.is_file()
    assert _wav_info(clean) == (44100, 1)
    assert report["duration"] <= 20.05
    assert report["quality"]["snr_db"] is not None
    assert report["quality"]["music_noise_residual_db"] is not None
    assert report["models"]["denoise"] == "afftdn"


def test_real_music_reverb_fixture_finds_candidates(tmp_path):
    source = _fixture(tmp_path)
    report = voice_extract.find_voice_candidates(
        source, tmp_path / "out",
        count=3, clip_seconds=20.0,
        separate=False, denoise="compare",
    )
    candidates = report["candidates"]
    assert len(candidates) == 3
    assert report["denoise_trials"]
    assert all(item["duration"] <= 20.05 for item in candidates)
    assert all(_wav_info(Path(item["path"])) == (44100, 1) for item in candidates)
    assert len({item["path"] for item in candidates}) == 3
    assert all(item["quality"]["snr_db"] is not None for item in candidates)


def test_real_demucs_pass_when_requested(tmp_path):
    if os.environ.get("VIBECUT_VOICE_ACCEPTANCE_SEPARATE") != "1":
        pytest.skip("set VIBECUT_VOICE_ACCEPTANCE_SEPARATE=1 for a real Demucs run")
    if not audio.demucs_available():
        pytest.skip("Demucs is not installed")
    source = _fixture(tmp_path)
    report = voice_extract.extract_clean_voice(
        source, tmp_path / "out",
        separate="htdemucs", denoise="afftdn", target_seconds=15.0,
    )
    assert report["models"]["separation"] == "htdemucs"
    assert Path(report["path"]).is_file()
