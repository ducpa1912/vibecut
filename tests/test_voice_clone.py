"""Cloned voices: store, consent, samples and the OpenRouter HeyGen route."""

import base64
import json
import shutil
import subprocess
import threading
import time
import urllib.error
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import audio
import settings_store
import tts
import voice_clone


@pytest.fixture(autouse=True)
def clone_store(monkeypatch, tmp_path):
    monkeypatch.setattr(settings_store, "DATA", tmp_path)
    yield tmp_path


@pytest.fixture(autouse=True)
def clear_candidate_state():
    import routes_voice_clone as routes

    for table in (
        routes.CANDIDATE_CANCELS, routes.CANDIDATE_STAGES,
        routes.CANDIDATE_RESULTS, routes.CANDIDATE_ERRORS,
    ):
        table.clear()
    yield
    for table in (
        routes.CANDIDATE_CANCELS, routes.CANDIDATE_STAGES,
        routes.CANDIDATE_RESULTS, routes.CANDIDATE_ERRORS,
    ):
        table.clear()


@pytest.fixture
def openrouter(monkeypatch):
    monkeypatch.setattr(audio, "openrouter_available", lambda: True)
    monkeypatch.setattr(audio, "openrouter_key", lambda: "sk-test")
    monkeypatch.setattr(audio, "openrouter_blocked", lambda: False)
    monkeypatch.setattr(audio, "_convert", lambda s, o, e=None: o.write_bytes(b"RIFF" + b"0" * 64) or o)


class Reply:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return b"\x01\x00" * 4410


def _clone(tmp_path, *, source="me", language="en", name="Me"):
    sample = tmp_path / "sample.mp3"
    sample.write_bytes(b"ID3" + b"\x00" * 4000)
    return voice_clone.create_clone(
        sample, name=name, source=source, consent=True, language=language, seconds=42,
    )


def test_speech_windows_merge_and_cap():
    segments = [
        {"start": 0.0, "end": 4.0, "text": "one"},
        {"start": 4.2, "end": 9.0, "text": "two"},
        {"start": 20.0, "end": 21.0, "text": ""},
        {"start": 30.0, "end": 400.0, "text": "long"},
    ]
    windows = voice_clone.speech_windows(segments, limit=60)
    assert windows[0] == (0.0, 9.0)
    assert windows[1][0] == 30.0
    assert sum(b - a for a, b in windows) == pytest.approx(60, abs=0.01)
    assert voice_clone.speech_windows(segments, start=5, end=8) == [(5.0, 8.0)]


def test_clone_needs_consent(tmp_path):
    sample = tmp_path / "s.mp3"
    sample.write_bytes(b"ID3" + b"\x00" * 4000)
    with pytest.raises(voice_clone.CloneError, match="permission"):
        voice_clone.create_clone(sample, name="x", source="me", consent=False)
    assert voice_clone.list_clones() == []


def test_create_clone_keeps_sample_locally_without_network(monkeypatch, tmp_path):
    def no_network(*args, **kwargs):
        raise AssertionError("cloning must not call the network")

    monkeypatch.setattr("urllib.request.urlopen", no_network)
    record = _clone(tmp_path, language="en-US", name="  My   voice ")
    assert voice_clone.is_voice_id(record["voice_id"])
    assert record["name"] == "My voice" and record["language"] == "en"
    assert record["status"] == "ACTIVE" and record["consent"]["confirmed"] is True
    assert voice_clone.sample_path(record["voice_id"]).is_file()


def test_delete_removes_record_and_sample(tmp_path):
    record = _clone(tmp_path)
    voice_clone.delete_clone(record["voice_id"])
    assert voice_clone.list_clones() == []
    assert not voice_clone.sample_path(record["voice_id"]).exists()
    with pytest.raises(voice_clone.CloneError):
        voice_clone.delete_clone(record["voice_id"])


def test_heygen_voice_list_puts_clones_first(tmp_path, openrouter):
    record = _clone(tmp_path)
    voices = tts.list_voices("heygen")
    assert voices[0]["id"] == record["voice_id"] and voices[0]["clone"] is True
    assert {voice["id"] for voice in voices[1:]} == set(tts.HEYGEN_VOICES)


def test_no_openrouter_key_means_no_heygen_voices(tmp_path, monkeypatch):
    _clone(tmp_path)
    monkeypatch.setattr(audio, "openrouter_media_available", lambda: False)
    assert tts.list_voices("heygen") == []


def test_clone_is_sent_as_openrouter_input_reference(monkeypatch, tmp_path, openrouter):
    record = _clone(tmp_path, language="vi")
    sent = {}

    def fake_urlopen(request, timeout=0):
        sent["url"] = request.full_url
        sent["body"] = json.loads(request.data.decode())
        return Reply()

    monkeypatch.setattr(tts.urllib.request, "urlopen", fake_urlopen)
    tts.synthesize_line("heygen", record["voice_id"], "Xin chào", tmp_path / "line.wav",
                        model="heygen/heygen-voice-1-turbo:free")
    body = sent["body"]
    assert sent["url"] == "https://openrouter.ai/api/v1/audio/speech"
    assert body["model"] == "heygen/heygen-voice-1-turbo:free"
    assert "voice" not in body
    assert body["response_format"] == "pcm"
    ref = body["input_references"][0]
    assert ref["type"] == "input_audio"
    data = ref["input_audio"]["data"]
    assert data.startswith("data:audio/mpeg;base64,")
    assert base64.b64decode(data.split(",", 1)[1]) == voice_clone.sample_path(record["voice_id"]).read_bytes()
    assert body["provider"] == {"options": {"heygen": {"language": "vi"}}}


def test_stock_voice_request_is_unchanged(monkeypatch, tmp_path, openrouter):
    sent = {}

    def fake_urlopen(request, timeout=0):
        sent.update(json.loads(request.data.decode()))
        return Reply()

    monkeypatch.setattr(tts.urllib.request, "urlopen", fake_urlopen)
    tts.synthesize_line("heygen", "bram", "Hi", tmp_path / "line.wav")
    assert sent["voice"] == "bram" and "input_references" not in sent


def test_clone_failure_raises_and_never_calls_heygen_directly(monkeypatch, tmp_path, openrouter):
    record = _clone(tmp_path)
    urls = []

    def refuse(request, timeout=0):
        urls.append(request.full_url)
        raise urllib.error.HTTPError(request.full_url, 400, "bad", {}, None)

    monkeypatch.setattr(tts.urllib.request, "urlopen", refuse)
    with pytest.raises(audio.AudioError, match="OpenRouter heygen voice failed"):
        tts.synthesize_line("heygen", record["voice_id"], "Hi", tmp_path / "line.wav")
    assert urls == ["https://openrouter.ai/api/v1/audio/speech"]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is not installed")
def test_prepare_sample_cuts_a_small_mono_mp3(tmp_path):
    source = tmp_path / "talk.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=220:duration=30",
         "-f", "lavfi", "-i", "color=c=black:s=320x240:d=30", "-shortest",
         "-c:v", "libx264", "-c:a", "aac", str(source)],
        check=True,
    )
    out = tmp_path / "sample.mp3"
    seconds = voice_clone.prepare_sample(source, out, windows=[(2.0, 12.0), (15.0, 25.0)])
    assert seconds == pytest.approx(20, abs=0.5)
    assert out.stat().st_size < 400_000
    with pytest.raises(voice_clone.CloneError, match="only"):
        voice_clone.prepare_sample(source, tmp_path / "short.mp3", windows=[(0.0, 3.0)])


def test_routes_list_consent_and_origin(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(voice_clone, "available", lambda: True)
    record = _clone(tmp_path)
    api = TestClient(app.app)
    listed = api.get("/api/voices/clones").json()
    assert listed["available"] is True and listed["voices"][0]["voice_id"] == record["voice_id"]
    assert api.get(f"/api/voices/clones/{record['voice_id']}").json()["name"] == "Me"
    refused = api.post(
        "/api/voices/clones",
        files={"file": ("me.wav", b"RIFF" + b"0" * 100, "audio/wav")},
        data={"consent": "false"},
    )
    assert refused.status_code == 400 and "own voice" in refused.json()["detail"]
    cross = api.delete(f"/api/voices/clones/{record['voice_id']}", headers={"sec-fetch-site": "cross-site"})
    assert cross.status_code == 403
    assert api.delete(f"/api/voices/clones/{record['voice_id']}").json() == {"deleted": record["voice_id"]}


def test_voice_room_catalog_lists_engines_and_clones(tmp_path, monkeypatch, openrouter):
    import app

    record = _clone(tmp_path)
    monkeypatch.setattr(voice_clone, "available", lambda: True)
    monkeypatch.setattr(audio, "say_available", lambda: False)
    monkeypatch.setattr(audio, "kokoro_available", lambda: False)
    api = TestClient(app.app)
    data = api.get("/api/voices/catalog").json()
    engines = {engine["id"]: engine for engine in data["engines"]}
    assert set(engines) == set(tts.SYNTHESIZERS)
    heygen = engines["heygen"]
    assert heygen["available"] and heygen["clone"]
    assert heygen["voices"][0]["id"] == record["voice_id"]
    assert not engines["say"]["available"] and engines["say"]["voices"] == []
    assert data["clones"][0]["voice_id"] == record["voice_id"]
    assert api.get("/voices").status_code == 200


def test_voice_room_sample_any_engine(tmp_path, monkeypatch):
    import app

    calls = {}

    def fake_sample(engine, voice, text, cache, rate=1.0, **extra):
        calls.update(engine=engine, voice=voice, text=text, rate=rate)
        out = tmp_path / "s.wav"
        out.write_bytes(b"RIFF" + b"0" * 64)
        return out

    monkeypatch.setattr(audio, "voice_sample", fake_sample)
    api = TestClient(app.app)
    ok = api.post("/api/voices/sample", json={"engine": "say", "voice": "Samantha", "text": "  hi  there ", "rate": 9})
    assert ok.status_code == 200 and ok.headers["content-type"] == "audio/wav"
    assert calls == {"engine": "say", "voice": "Samantha", "text": "hi there", "rate": 2.0}
    assert api.post("/api/voices/sample", json={"engine": "piper"}).status_code == 400


# ---------------------------------------------------------------- candidates


def _job(tmp_path, monkeypatch, job_id="job-test", name="talk.mp4"):
    import app

    jobs = tmp_path / "jobs"
    monkeypatch.setattr(app, "JOBS", jobs)
    directory = jobs / job_id
    directory.mkdir(parents=True, exist_ok=True)
    source = tmp_path / name
    source.write_bytes(b"\x00" * 2048)
    job = {
        "id": job_id,
        "source": {"path": str(source), "name": name},
        "status": "ready",
    }
    (directory / "job.json").write_text(json.dumps(job), encoding="utf-8")
    return job, source, directory


def _candidate_report(out_dir: Path, *, index: int = 1) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"candidate-{index:02d}.wav"
    path.write_bytes(b"RIFF" + b"\x00" * 128)
    return {
        "version": 2,
        "candidates": [{
            "index": index,
            "path": str(path),
            "duration": 60.0,
            "speech_seconds": 58.0,
            "speech_fraction": 0.92,
            "score": 118.4,
            "window": [12.0, 72.0],
            "quality": {"snr_db": 19.5, "music_noise_residual_db": -31.0},
            "warnings": ["Candidates may include more than one speaker."],
        }],
        "models": {"separation": "htdemucs_ft", "denoise": "deepfilternet3", "vad": "silero"},
        "warnings": ["No speaker filter."],
    }


def _wait_state(api, job_id, expected=("done", "failed", "cancelled"), timeout=5.0):
    deadline = time.time() + timeout
    data = {}
    while time.time() < deadline:
        data = api.get(f"/api/jobs/{job_id}/voices/candidates").json()
        if data.get("state") in expected:
            return data
        time.sleep(0.02)
    raise AssertionError(f"candidate task never finished: {data}")


def test_candidate_routes_start_poll_and_serve_audio(tmp_path, monkeypatch):
    import app
    import voice_extract

    job, _source, _directory = _job(tmp_path, monkeypatch)

    def fake_find(source, out_dir, **kwargs):
        assert Path(source).is_file()
        callback = kwargs.get("on_stage")
        if callback:
            callback("exporting")
        return _candidate_report(out_dir)

    monkeypatch.setattr(voice_extract, "find_voice_candidates", fake_find)
    api = TestClient(app.app)

    started = api.post(f"/api/jobs/{job['id']}/voices/candidates").json()
    assert started["state"] in {"queued", "running"}

    done = _wait_state(api, job["id"])
    assert done["state"] == "done"
    assert done["candidates"][0]["index"] == 1
    assert done["candidates"][0]["start"] == 12.0
    assert done["candidates"][0]["duration"] == 60.0
    assert done["candidates"][0]["engines"]["denoise"] == "deepfilternet3"
    assert done["candidates"][0]["warnings"]
    assert done["warnings"] == ["No speaker filter."]

    audio = api.get(done["candidates"][0]["audio_url"])
    assert audio.status_code == 200 and audio.headers["content-type"] == "audio/wav"
    assert api.get(f"/api/jobs/{job['id']}/voices/candidates/9/audio").status_code == 404


def test_candidate_routes_cancel_a_running_search(tmp_path, monkeypatch):
    import app
    import audio as audio_module
    import voice_extract

    job, _source, _directory = _job(tmp_path, monkeypatch, job_id="job-cancel")
    started = threading.Event()

    def slow_find(source, out_dir, **kwargs):
        started.set()
        cancel = kwargs["cancel_event"]
        while not cancel.is_set():
            time.sleep(0.01)
        raise audio_module.AudioError("Voice extraction cancelled.")

    monkeypatch.setattr(voice_extract, "find_voice_candidates", slow_find)
    api = TestClient(app.app)

    api.post(f"/api/jobs/{job['id']}/voices/candidates")
    assert started.wait(5.0)
    again = api.post(f"/api/jobs/{job['id']}/voices/candidates").json()
    assert again["state"] in {"queued", "running"}

    cancelled = api.delete(f"/api/jobs/{job['id']}/voices/candidates").json()
    assert cancelled["state"] == "cancelled"
    final = _wait_state(api, job["id"], expected=("cancelled",))
    assert final["state"] == "cancelled"


def test_clone_from_a_candidate_uses_the_clean_wav(tmp_path, monkeypatch):
    import app

    job, _source, directory = _job(tmp_path, monkeypatch, job_id="job-candidate-clone")
    candidates = directory / "voice-candidates"
    candidates.mkdir(parents=True)
    clean = candidates / "candidate-01.wav"
    clean.write_bytes(b"RIFF" + b"\x00" * 256)
    (candidates / "report.json").write_text(json.dumps({
        "candidates": [{"index": 1, "window": [4.0, 64.0]}],
    }), encoding="utf-8")
    monkeypatch.setattr(voice_clone, "available", lambda: True)
    called = {}

    def fake_prepare(source, output, **kwargs):
        called["source"] = Path(source)
        output.write_bytes(b"ID3" + b"\x00" * 4000)
        return 60.0

    monkeypatch.setattr(voice_clone, "prepare_sample", fake_prepare)
    api = TestClient(app.app)
    response = api.post(
        f"/api/jobs/{job['id']}/voices/clone",
        json={"name": "Interview", "consent": True, "candidate": 1},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["source"] == "video" and data["candidate"] == 1
    assert data["cleaned"] is True and data["warning"] == ""
    assert called["source"] == clean


def test_range_clone_falls_back_to_the_raw_cut(tmp_path, monkeypatch):
    import app
    import audio as audio_module
    import voice_extract

    job, _source, _directory = _job(tmp_path, monkeypatch, job_id="job-range-fallback")
    monkeypatch.setattr(voice_clone, "available", lambda: True)
    seen = {}

    def fake_prepare(source, output, **kwargs):
        output.write_bytes(b"ID3" + b"\x00" * 4000)
        return 42.0

    def broken_extract(source, out_dir, **kwargs):
        seen["called"] = True
        raise audio_module.AudioError("Demucs is not installed.")

    monkeypatch.setattr(voice_clone, "prepare_sample", fake_prepare)
    monkeypatch.setattr(voice_extract, "extract_clean_voice", broken_extract)
    api = TestClient(app.app)
    response = api.post(
        f"/api/jobs/{job['id']}/voices/clone",
        json={"consent": True, "start": 0, "end": 30},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert seen["called"] is True
    assert data["cleaned"] is False
    assert "raw cut" in data["warning"]


def test_my_voice_upload_is_cleaned_before_the_sample(tmp_path, monkeypatch):
    import app
    import voice_extract

    monkeypatch.setattr(voice_clone, "available", lambda: True)
    calls = {}

    def fake_extract(source, out_dir, **kwargs):
        calls["separate"] = kwargs.get("separate")
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        clean = out / "clean_voice.wav"
        clean.write_bytes(b"RIFF" + b"\x00" * 128)
        return {"path": str(clean), "warnings": ["Denoise was light."], "quality": {}}

    def fake_prepare(source, output, **kwargs):
        calls["sample_source"] = Path(source)
        output.write_bytes(b"ID3" + b"\x00" * 4000)
        return 30.0

    monkeypatch.setattr(voice_extract, "extract_clean_voice", fake_extract)
    monkeypatch.setattr(voice_clone, "prepare_sample", fake_prepare)
    api = TestClient(app.app)
    response = api.post(
        "/api/voices/clones",
        files={"file": ("me.wav", b"RIFF" + b"\x00" * 128, "audio/wav")},
        data={"consent": "true", "name": "Me"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["cleaned"] is True
    assert data["warnings"] == ["Denoise was light."]
    assert calls["separate"] is False
    assert calls["sample_source"].name == "clean_voice.wav"


def test_my_voice_upload_falls_back_when_cleaning_fails(tmp_path, monkeypatch):
    import app
    import audio as audio_module
    import voice_extract

    monkeypatch.setattr(voice_clone, "available", lambda: True)

    def broken_extract(source, out_dir, **kwargs):
        raise audio_module.AudioError("ffmpeg failed.")

    def fake_prepare(source, output, **kwargs):
        output.write_bytes(b"ID3" + b"\x00" * 4000)
        return 30.0

    monkeypatch.setattr(voice_extract, "extract_clean_voice", broken_extract)
    monkeypatch.setattr(voice_clone, "prepare_sample", fake_prepare)
    api = TestClient(app.app)
    response = api.post(
        "/api/voices/clones",
        files={"file": ("me.wav", b"RIFF" + b"\x00" * 128, "audio/wav")},
        data={"consent": "true"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["cleaned"] is False
    assert "raw recording" in data["warning"]


# ---------------------------------------------------------------- merge review fixes


def test_deleted_clone_never_speaks_as_a_stock_voice(monkeypatch, tmp_path, openrouter):
    record = _clone(tmp_path)
    voice_id = record["voice_id"]
    voice_clone.delete_clone(voice_id)
    sent = []
    monkeypatch.setattr(tts.urllib.request, "urlopen", lambda request, timeout=0: sent.append(request) or Reply())
    with pytest.raises(audio.AudioError, match="was deleted"):
        tts.synthesize_line("heygen", voice_id, "Hi", tmp_path / "line.wav")
    assert sent == []


def test_deleted_clone_is_refused_before_the_line_cache(tmp_path):
    record = _clone(tmp_path)
    voice_clone.delete_clone(record["voice_id"])
    # build_bed resolves every candidate's voice before it looks in the cache.
    with pytest.raises(audio.AudioError, match="was deleted"):
        tts._tts_voice_for("heygen", record["voice_id"], "heygen")
    with pytest.raises(audio.AudioError, match="was deleted"):
        tts.synthesize_story(["Hi."], engine="heygen", voice=record["voice_id"],
                             cache_dir=tmp_path / "voice", routes=[{"provider": "openrouter", "model": "heygen/heygen-voice-1-turbo:free"}])


def test_live_clone_and_stock_voices_pass_the_guard(tmp_path):
    record = _clone(tmp_path)
    tts.require_live_clone(record["voice_id"])
    tts.require_live_clone("nadine")
    tts.require_live_clone("")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is not installed")
def test_clone_sample_is_a_real_mp3_whatever_the_name(tmp_path):
    source = tmp_path / "tone.m4a"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=220:duration=12",
         "-c:a", "aac", str(source)],
        check=True,
    )
    out = tmp_path / "sample.wav"
    voice_clone.prepare_sample(source, out)
    assert out.read_bytes()[:4] != b"RIFF"
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=format_name",
         "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, check=True,
    )
    assert probe.stdout.strip() == "mp3"


def test_speech_fields_mime_matches_an_old_wav_wrapped_sample(tmp_path):
    record = _clone(tmp_path)
    path = voice_clone.sample_path(record["voice_id"])
    assert voice_clone.speech_fields(record["voice_id"])["input_references"][0]["input_audio"]["data"].startswith("data:audio/mpeg;")
    path.write_bytes(b"RIFF" + b"\0" * 4000)
    data = voice_clone.speech_fields(record["voice_id"])["input_references"][0]["input_audio"]["data"]
    assert data.startswith("data:audio/wav;base64,")
