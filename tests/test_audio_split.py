"""Audio split contracts: facade re-exports and dead-engine removal."""

import audio
import music
import stt
import tts


def test_audio_reexports_tts_helpers():
    assert audio.list_voices is tts.list_voices
    assert audio.synthesize_line is tts.synthesize_line
    assert audio.voice_sample is tts.voice_sample
    assert audio._tts_route_candidates is tts._tts_route_candidates


def test_audio_reexports_music_helpers():
    assert audio.list_music is music.list_music
    assert audio.generate_music is music.generate_music
    assert audio.resolve_music_track is music.resolve_music_track
    assert audio.beat_grid is music.beat_grid
    assert audio.snap_clips is music.snap_clips


def test_audio_reexports_stt_keys():
    assert audio.groq_key is stt.groq_key
    assert audio.deepgram_key is stt.deepgram_key
    assert audio.openai_key is stt.openai_key


def test_stt_module_has_no_local_engine():
    source = stt.__file__
    with open(source, encoding="utf-8") as handle:
        body = handle.read().lower()
    assert "mlx_whisper" not in body
    assert "whisper" not in body
    assert "argostranslate" not in body


REMOVED_ENGINES = (
    "mlx_lm_available",
    "stable_audio_available",
    "musicgen_available",
    "argos_pair_ready",
    "_translate_argos",
    "_translate_marian",
    "_ollama_workflow_text",
    "_mlx_text",
    "_rewrite_mlx",
    "_rewrite_ollama",
)


def test_removed_engines_are_absent():
    for name in REMOVED_ENGINES:
        assert not hasattr(audio, name), name


def test_removed_music_sources_are_absent():
    assert "cc0" not in audio.MUSIC_DIRS
    status = audio.engine_status()
    for key in ("cc0", "stable-small", "stable-1.0", "musicgen-small"):
        assert key not in status["music"]
        assert key not in status["assets"]
    assert "mlx_lm" not in status
    rewrite_ids = {item["id"] for item in status["rewrite_models"]}
    assert "mlx" not in rewrite_ids and "ollama" not in rewrite_ids
    assert {item["id"] for item in status["translation"]} == {
        "opencode", "openrouter", "apple_fm",
    }


def test_removed_tool_files_are_gone():
    from pathlib import Path

    root = Path(audio.__file__).resolve().parent
    for relative in (
        "tools/musicgen_generate.py",
        "tools/music_generate.py",
        "tools/rewrite_mlx.py",
        "requirements-music.txt",
    ):
        assert not (root / relative).exists(), relative
