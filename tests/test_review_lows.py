"""Low findings from docs/shared/reviews/merge-cff3ba1-review.md (F10-F19)."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import audio
import settings_store
import stt
import tts
import voice_clone
import workflow_config

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolated_data(monkeypatch, tmp_path):
    monkeypatch.setattr(settings_store, "DATA", tmp_path)
    yield tmp_path


# ---------------------------------------------------------------- F10


@pytest.mark.parametrize("path, body", [
    ("/api/voices/clones/vc_missing/sample", {"text": "hi"}),
    ("/api/voices/sample", {"engine": "say", "voice": "Samantha", "text": "hi"}),
])
def test_cross_site_voice_samples_are_rejected(path, body):
    import app

    api = TestClient(app.app)
    refused = api.post(path, json=body, headers={"sec-fetch-site": "cross-site"})
    assert refused.status_code == 403


def test_cross_site_transcribe_is_rejected():
    import app

    api = TestClient(app.app)
    refused = api.post("/api/jobs/abc123/transcribe", json={}, headers={"sec-fetch-site": "cross-site"})
    assert refused.status_code == 403


# ---------------------------------------------------------------- F11


def test_single_bye_is_kept():
    assert not stt._hallucinated("Bye.", {"bye": 1})
    assert not stt._hallucinated("Okay.", {"okay": 2})


def test_short_filler_dropped_from_the_third_repeat_unless_confident():
    assert stt._hallucinated("Thank you.", {"thank you": 3})
    confident = {"no_speech_prob": 0.05, "avg_logprob": -0.2}
    assert not stt._hallucinated("Thank you.", {"thank you": 3}, confident)
    assert stt._hallucinated("Thanks for watching!", {}, confident)


def test_okay_twice_in_dialogue_is_kept():
    segment = {
        "text": "Okay.", "avg_logprob": -0.9, "no_speech_prob": 0.4,
        "compression_ratio": 1.0,
    }
    payload = stt._whisper_payload({"language": "en", "segments": [
        {**segment, "start": 0.0, "end": 0.5},
        {**segment, "start": 2.0, "end": 2.5},
    ]})
    assert [item["text"] for item in payload["segments"]] == ["Okay.", "Okay."]


# ---------------------------------------------------------------- F13


def test_candidate_state_is_dropped_when_the_job_is_deleted():
    import routes_voice_clone as routes

    event = threading.Event()
    routes._remember(routes.CANDIDATE_CANCELS, "job1", event)
    routes._set_stage("job1", "done")
    routes._remember(routes.CANDIDATE_RESULTS, "job1", {"candidates": []})
    routes.forget_job("job1")
    assert event.is_set()
    for table in routes._CANDIDATE_TABLES:
        assert "job1" not in table


def test_candidate_tables_are_bounded(monkeypatch):
    import routes_voice_clone as routes

    monkeypatch.setattr(routes, "CANDIDATE_MEMORY", 3)
    for index in range(6):
        routes._set_stage(f"job{index}", "done")
    assert list(routes.CANDIDATE_STAGES) == ["job3", "job4", "job5"]
    routes.CANDIDATE_STAGES.clear()


def test_finished_search_releases_its_cancel_switch(monkeypatch, tmp_path):
    import routes_voice_clone as routes
    import voice_extract

    source = tmp_path / "source.mp4"
    source.write_bytes(b"0")
    monkeypatch.setattr(routes, "_app", lambda: type("A", (), {
        "load_job": staticmethod(lambda job_id: {"source": {"path": str(source)}}),
    }))
    monkeypatch.setattr(voice_extract, "find_voice_candidates", lambda *a, **k: {"candidates": []})
    event = threading.Event()
    routes._remember(routes.CANDIDATE_CANCELS, "job9", event)
    routes._run_candidate_search("job9", event, tmp_path)
    assert "job9" not in routes.CANDIDATE_CANCELS
    for table in routes._CANDIDATE_TABLES:
        table.pop("job9", None)


# ---------------------------------------------------------------- F14


def test_voice_room_hides_cloning_when_openrouter_is_disabled_or_quarantined(monkeypatch):
    monkeypatch.setattr(settings_store, "get_secret", lambda name: "sk-test")
    monkeypatch.setattr(audio, "openrouter_media_available", lambda: True)
    assert voice_clone.available()
    monkeypatch.setattr(audio, "openrouter_media_available", lambda: False)
    assert not voice_clone.available()
    monkeypatch.setattr(settings_store, "get_secret", lambda name: "")
    monkeypatch.setattr(audio, "openrouter_media_available", lambda: True)
    assert not voice_clone.available()


# ---------------------------------------------------------------- F15


def test_clone_panels_show_the_server_cleaning_warning():
    voice = ROOT / "static" / "voice"
    text = (voice / "voiceclone.js").read_text(encoding="utf-8")
    assert "export function cleaningNote(record)" in text
    assert "record?.warning" in text and "record?.cleaned === false" in text
    assert text.count("cleaningNote(record)") >= 2
    # The Voice Room's video clone shows the same warning.
    finder = (voice / "clipfinder.js").read_text(encoding="utf-8")
    assert "cleaningNote," in finder and "cleaningNote(record)" in finder


# ---------------------------------------------------------------- F16 / F17


def _fake_run_capture(calls):
    def fake(cmd, timeout=0, cancel_event=None):
        calls.append(list(cmd))
        Path(cmd[-1]).write_bytes(b"RIFF")
    return fake


def test_silent_source_without_ffprobe_still_gets_a_silence_bed(monkeypatch, tmp_path):
    calls: list[list[str]] = []
    monkeypatch.setattr(audio.shutil, "which", lambda name: None)
    monkeypatch.setattr(audio, "media_duration", lambda path: 3.0)
    monkeypatch.setattr(audio, "_ffmpeg", lambda: "ffmpeg")

    def fake(cmd, timeout=0, cancel_event=None):
        calls.append(list(cmd))
        if "anullsrc" not in " ".join(cmd):
            raise audio.AudioError("Audio command failed.\nno audio stream")
        Path(cmd[-1]).write_bytes(b"RIFF")

    monkeypatch.setattr(audio, "_run", fake)
    out = audio._source_audio_bed(str(tmp_path / "silent.mp4"), tmp_path)
    assert out.is_file()
    assert "-map" not in calls[0]
    assert any("anullsrc" in part for part in calls[-1])


def test_cancel_is_not_turned_into_silence_without_ffprobe(monkeypatch, tmp_path):
    monkeypatch.setattr(audio.shutil, "which", lambda name: None)
    monkeypatch.setattr(audio, "_ffmpeg", lambda: "ffmpeg")

    def fake(cmd, timeout=0, cancel_event=None):
        raise audio.AudioError("Audio build cancelled.")

    monkeypatch.setattr(audio, "_run", fake)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(audio.AudioError, match="cancelled"):
        audio._source_audio_bed(str(tmp_path / "x.mp4"), tmp_path, cancel)


def test_multi_audio_source_uses_the_track_with_most_channels(monkeypatch, tmp_path):
    calls: list[list[str]] = []
    monkeypatch.setattr(audio.shutil, "which", lambda name: "/usr/bin/ffprobe")
    monkeypatch.setattr(audio, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(audio.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a[0], 0, stdout="1,1\n2,2\n3,2\n", stderr="",
    ))
    monkeypatch.setattr(audio, "_run", _fake_run_capture(calls))
    audio._source_audio_bed(str(tmp_path / "camera.mov"), tmp_path)
    mapped = calls[0][calls[0].index("-map") + 1]
    assert mapped == "0:2"


def test_probe_with_no_audio_streams_is_silent(monkeypatch, tmp_path):
    calls: list[list[str]] = []
    monkeypatch.setattr(audio.shutil, "which", lambda name: "/usr/bin/ffprobe")
    monkeypatch.setattr(audio, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(audio, "media_duration", lambda path: 2.0)
    monkeypatch.setattr(audio.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a[0], 0, stdout="", stderr="",
    ))
    monkeypatch.setattr(audio, "_run", _fake_run_capture(calls))
    audio._source_audio_bed(str(tmp_path / "silent.mp4"), tmp_path)
    assert len(calls) == 1 and any("anullsrc" in part for part in calls[0])
    assert audio._has_audio_stream(str(tmp_path / "silent.mp4")) is False


# ---------------------------------------------------------------- F18


def test_script_workflow_defaults_to_the_catalog_vision_model():
    from admin import catalog

    defaults = workflow_config.default_workflows()
    assert defaults["script"]["routes"] == [
        {"provider": "openrouter", "model": "google/gemini-3.5-flash-lite"},
    ]
    assert workflow_config.WORKFLOW_PROVIDERS["script"] == ("openrouter",)
    ids = {item["id"] for item in catalog._STATIC["openrouter"]}
    assert "google/gemini-3.5-flash-lite" in ids


def test_script_brief_uses_the_admin_script_route(monkeypatch):
    import silent_script

    monkeypatch.setattr(settings_store, "load_settings", lambda: {"workflows": {"script": {
        "routes": [{"provider": "openrouter", "model": "google/gemini-3.1-flash-lite"}],
    }}})
    assert silent_script.configured_model() == "google/gemini-3.1-flash-lite"
    monkeypatch.setattr(settings_store, "load_settings", lambda: {})
    assert silent_script.configured_model() == silent_script.MODEL


# ---------------------------------------------------------------- F19


def test_synthesize_story_is_removed():
    assert not hasattr(tts, "synthesize_story")
    assert not hasattr(tts, "StoryVoice")
