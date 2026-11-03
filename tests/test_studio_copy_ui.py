"""Edit Audio: transcript, translation and Write Copy are explicit actions."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIO = (ROOT / "static" / "studio" / "edit" / "layers" / "audio.js").read_text(encoding="utf-8")
API = (ROOT / "static" / "studio" / "edit" / "api.js").read_text(encoding="utf-8")
ROUTES = (ROOT / "routes_studio.py").read_text(encoding="utf-8")


def test_audio_shows_the_full_transcript_and_two_actions():
    assert "Full transcript" in AUDIO
    assert "Translate transcript" in AUDIO
    assert "Write Copy" in AUDIO
    assert "No rewrite happens until you press Write Copy." in AUDIO


def test_open_never_translates_or_rewrites():
    mount_tail = AUDIO[AUDIO.rindex("  render();"):]
    assert "void loadTranscript();" in mount_tail
    assert "void runTranslate();" not in mount_tail
    assert "void runCopy();" not in mount_tail


def test_translation_is_one_route_for_the_whole_transcript():
    assert '"/api/jobs/{job_id}/transcript/translate"' in ROUTES
    assert "audio.translate_lines(source_lines" in ROUTES
    assert "translateTranscript" in API


def test_copy_uses_the_existing_script_route_with_moment_clips():
    assert "writeMomentCopy" in API
    assert '`${jobRoot(jobId)}/audio/script`' in API
    assert "mode: copyStyle" in AUDIO
