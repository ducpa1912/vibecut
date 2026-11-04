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
import real_media

import audio
import voice_extract

pytestmark = pytest.mark.skipif(
    os.environ.get("VIBECUT_VOICE_ACCEPTANCE") != "1",
    reason="set VIBECUT_VOICE_ACCEPTANCE=1 to run the real audio acceptance",
)





def _fixture(tmp_path: Path) -> Path:
    return real_media.clip("mixed-voice.wav", tmp_path / "source.wav", 90.0, rate=44100)


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
