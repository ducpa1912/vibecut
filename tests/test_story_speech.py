"""Stories need speech: OpenRouter transcription, language and re-reading."""

import base64
import json
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import settings_store
import stt
import workflow_config


class Reply:
    def __init__(self, payload):
        self.body = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.body


def _wav(path: Path, seconds: float = 1.0) -> Path:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * int(16000 * seconds))
    return path


def test_openrouter_stt_request_and_parse(tmp_path, monkeypatch):
    sent = {}

    def fake_run(cmd, timeout=None):
        Path(cmd[-1]).write_bytes(b"ID3-mp3")

    def fake_urlopen(request, timeout=0):
        sent["url"] = request.full_url
        sent["auth"] = request.headers.get("Authorization")
        sent["body"] = json.loads(request.data.decode())
        return Reply({
            "language": "vi",
            "text": "Xin chào mọi người. Cảm ơn các bạn đã theo dõi.",
            "segments": [
                {"start": 0.0, "end": 1.5, "text": " Xin chào mọi người."},
                {"start": 1.5, "end": 3.0, "text": " Cảm ơn các bạn đã theo dõi."},
            ],
            "words": [
                {"word": "Xin", "start": 0.0, "end": 0.3},
                {"word": "chào", "start": 0.3, "end": 0.7},
            ],
        })

    monkeypatch.setattr(stt, "_run", fake_run)
    monkeypatch.setattr(settings_store, "get_secret", lambda name: "sk-or" if name == "openrouter" else "")
    result = stt._cloud_speech(
        _wav(tmp_path / "a.wav"), tmp_path / "job", "openrouter", "vi-VN", urlopen=fake_urlopen,
    )
    assert sent["url"] == "https://openrouter.ai/api/v1/audio/transcriptions"
    assert sent["auth"] == "Bearer sk-or"
    body = sent["body"]
    assert body["model"] == stt.OPENROUTER_STT_MODEL
    assert body["response_format"] == "verbose_json"
    assert body["timestamp_granularities"] == ["segment", "word"]
    assert body["language"] == "vi"
    assert body["input_audio"]["format"] == "mp3"
    assert base64.b64decode(body["input_audio"]["data"]) == b"ID3-mp3"
    assert result["provider"] == "openrouter"
    # The outro line Whisper writes over music is dropped.
    assert [item["text"] for item in result["segments"]] == ["Xin chào mọi người."]


def test_openrouter_auto_language_is_not_sent(tmp_path, monkeypatch):
    sent = {}
    monkeypatch.setattr(stt, "_run", lambda cmd, timeout=None: Path(cmd[-1]).write_bytes(b"x"))
    monkeypatch.setattr(settings_store, "get_secret", lambda name: "sk-or")

    def fake_urlopen(request, timeout=0):
        sent.update(json.loads(request.data.decode()))
        return Reply({"segments": [{"start": 0, "end": 1, "text": "hi there"}]})

    stt._cloud_speech(_wav(tmp_path / "a.wav"), tmp_path / "job", "openrouter", "auto", urlopen=fake_urlopen)
    assert "language" not in sent


def test_openrouter_is_a_ready_stt_route_with_only_its_key(monkeypatch):
    monkeypatch.setattr(settings_store, "get_secret", lambda name: "sk-or" if name == "openrouter" else "")
    assert stt.normalize_engine("openrouter") == {
        "provider": "openrouter", "model": stt.OPENROUTER_STT_MODEL,
    }
    assert stt._engine_ready("openrouter", stt.OPENROUTER_STT_MODEL)
    assert not stt._engine_ready("groq", "whisper-large-v3-turbo")
    assert "openrouter" in workflow_config.STT_PROVIDERS
    routes = workflow_config.DEFAULT_WORKFLOWS["stt"]["routes"]
    assert routes[-1] == {"provider": "openrouter", "model": "openai/whisper-large-v3-turbo"}


@pytest.mark.parametrize("text, expected", [
    ("Thanks for watching!", True),
    ("Subtitles by the Amara.org community", True),
    ("Hẹn gặp lại các bạn trong những video tiếp theo.", True),
    ("Thank you so much for the gift.", False),
    ("Cảm ơn mẹ đã nấu cơm.", False),
])
def test_hallucinated_lines(text, expected):
    assert stt._hallucinated(text, {}) is expected


def test_thank_you_dropped_only_when_repeated():
    assert stt._hallucinated("Thank you.", {"thank you": 3})
    assert not stt._hallucinated("Thank you.", {"thank you": 1})


@pytest.mark.parametrize("title, expected", [
    ("DAILY VLOG_ Ở NHÀ MỘT MÌNH_ unbox ip17, nấu ăn", "vi"),
    ("東京の旅", "ja"),
    ("北京旅行 vlog", "zh"),
    ("서울 브이로그", "ko"),
    ("The Real Reason Everyone SEEMS Richer Than Me", ""),
    ("cn-1min29s-720x1280-voice-subtiltle.mp4", "zh"),
    ("en-53s-1080x1920-subtitle.mp4", "en"),
    ("no-voice-1min-1080x1920-text-overlay.mp4", ""),
])
def test_guess_language_from_title(title, expected):
    assert stt.guess_language(title) == expected


def test_speech_language_prefers_explicit_then_title_then_setting():
    meta = {"name": "Một ngày ở nhà.mp4"}
    assert stt.speech_language_for({"speech_language": "en"}, meta) == "vi"
    assert stt.speech_language_for({"speech_language": "en", "speech_language_explicit": "ja"}, meta) == "ja"
    assert stt.speech_language_for({"speech_language": "fr"}, {"name": "Paris trip.mp4"}) == "fr"


def _ready_job(app, job_id, tmp_path, *, has_audio=True):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    job = {
        "id": job_id, "status": "ready", "created": 1.0, "options": {},
        "source": {"path": str(source), "name": "Một ngày ở nhà.mp4", "duration": 60.0, "has_audio": has_audio},
        "analysis": {"scenes": [{"id": 0, "start": 0.0, "end": 60.0}], "transcript": None},
    }
    app.save_job(job)
    return job


def test_transcribe_route_refuses_a_video_without_sound(tmp_path):
    import app

    _ready_job(app, "silentjob001", tmp_path, has_audio=False)
    response = TestClient(app.app).post("/api/jobs/silentjob001/transcribe", json={})
    assert response.status_code == 400 and "no sound track" in response.json()["detail"]


def test_transcribe_route_reads_speech_and_attaches_it(tmp_path, monkeypatch):
    import app

    _ready_job(app, "speechjob001", tmp_path)
    monkeypatch.setattr(app.pipeline, "extract_audio", lambda path, has_audio, job_dir: _wav(tmp_path / "a.wav"))
    monkeypatch.setattr(app.pipeline.stt, "_engine_ready", lambda provider, model: provider == "openrouter")
    seen = {}

    def fake_transcribe(wav, job_dir, duration, progress, **kwargs):
        seen.update(language=kwargs["language"])
        return {
            "language": "vi", "provider": "openrouter", "text": "Xin chào.",
            "segments": [{"start": 1.0, "end": 2.0, "text": "Xin chào."}],
            "words": [],
        }

    monkeypatch.setattr(app.pipeline.stt, "transcribe_source", fake_transcribe)
    response = TestClient(app.app).post("/api/jobs/speechjob001/transcribe", json={})
    assert response.status_code == 200, response.text
    assert response.json() == {"segments": 1, "language": "vi", "provider": "openrouter", "no_speech": False}
    assert seen["language"] == "vi"
    job = app.load_job("speechjob001")
    assert job["analysis"]["transcript"]["segments"] == 1
    assert job["analysis"]["engine"]["transcript_provider"] == "openrouter"
    assert not (tmp_path / "a.wav").exists()


def test_transcribe_route_explains_when_no_engine_is_ready(tmp_path, monkeypatch):
    import app

    _ready_job(app, "nokeyjob0001", tmp_path)
    monkeypatch.setattr(app.pipeline.stt, "_engine_ready", lambda provider, model: False)
    response = TestClient(app.app).post("/api/jobs/nokeyjob0001/transcribe", json={})
    assert response.status_code == 400 and "OpenRouter" in response.json()["detail"]


def test_import_language_that_differs_from_setup_beats_a_title_guess(monkeypatch):
    import app

    monkeypatch.setattr(settings_store, "load_settings", lambda: {"stt": {"language": "en"}})
    picked = app.clean_options({"speech_language": "vi"})
    assert picked["speech_language_explicit"] == "vi"
    assert stt.speech_language_for(picked, {"name": "東京の夜"}) == "vi"
    # Classic sends the Setup language on every import: that is no pick.
    default = app.clean_options({"speech_language": "en"})
    assert "speech_language_explicit" not in default
    assert stt.speech_language_for(default, {"name": "東京の夜"}) == "ja"
    flagged = app.clean_options({"speech_language": "en", "speech_language_explicit": True})
    assert flagged["speech_language_explicit"] == "en"
    assert "speech_language_explicit" not in app.clean_options({"speech_language": "auto"})


def _slow_transcribe(app, monkeypatch, tmp_path, release):
    monkeypatch.setattr(app.pipeline, "extract_audio", lambda path, has_audio, job_dir: _wav(tmp_path / "a.wav"))
    monkeypatch.setattr(app.pipeline.stt, "_engine_ready", lambda provider, model: provider == "openrouter")

    def fake_transcribe(wav, job_dir, duration, progress, **kwargs):
        release.wait(5)
        return {
            "language": "vi", "provider": "openrouter", "text": "Xin chào.",
            "segments": [{"start": 1.0, "end": 2.0, "text": "Xin chào."}], "words": [],
        }

    monkeypatch.setattr(app.pipeline.stt, "transcribe_source", fake_transcribe)
    monkeypatch.setattr(app, "VOICE_TASK_WAIT_S", 0.05)


def test_slow_transcribe_answers_running_then_the_poll_returns_the_result(tmp_path, monkeypatch):
    import threading
    import time

    import app

    _ready_job(app, "slowread0001", tmp_path)
    release = threading.Event()
    _slow_transcribe(app, monkeypatch, tmp_path, release)
    api = TestClient(app.app)
    first = api.post("/api/jobs/slowread0001/transcribe", json={})
    assert first.status_code == 202
    assert first.json()["state"] in ("queued", "running")
    again = api.post("/api/jobs/slowread0001/transcribe", json={})
    assert again.status_code == 202 and again.json()["task_id"] == first.json()["task_id"]
    release.set()
    for _ in range(100):
        polled = api.get("/api/jobs/slowread0001/voice-tasks/transcribe")
        if polled.status_code != 202:
            break
        time.sleep(0.05)
    assert polled.status_code == 200, polled.text
    assert polled.json()["segments"] == 1
    assert app.load_job("slowread0001")["analysis"]["transcript"]["segments"] == 1


def test_cancelled_transcribe_never_updates_the_job(tmp_path, monkeypatch):
    import threading
    import time

    import app

    _ready_job(app, "cancelread01", tmp_path)
    release = threading.Event()
    _slow_transcribe(app, monkeypatch, tmp_path, release)
    api = TestClient(app.app)
    assert api.post("/api/jobs/cancelread01/transcribe", json={}).status_code == 202
    assert api.delete("/api/jobs/cancelread01/voice-tasks/transcribe").json()["state"] == "cancelled"
    release.set()
    time.sleep(0.3)
    assert api.get("/api/jobs/cancelread01/voice-tasks/transcribe").status_code == 409
    assert app.load_job("cancelread01")["analysis"]["transcript"] is None
