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
