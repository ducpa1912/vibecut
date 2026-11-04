"""Takes beside the work: previews and voiceovers, stars, cleanup, saving.

Audio is a short tone written by the test itself; the speech call is faked.
Nothing is sent anywhere, and no media is downloaded.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pytest
import real_media
from fastapi.testclient import TestClient

import audio
import settings_store
import tts
import voice_clone
import voice_takes

ROOT = Path(__file__).resolve().parents[1]
needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is not installed")


def tone(path: Path, seconds: float = 0.5, rate: int = 16000) -> Path:
    return real_media.clip("speech.wav", path, seconds, rate=rate)


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_store, "DATA", tmp_path)
    import routes_voice_clone as routes

    routes.VOICE_TASK_CANCELS.clear()
    yield tmp_path
    voice_takes._VOICEOVER.release() if voice_takes._VOICEOVER.locked() else None
    routes.VOICE_TASK_CANCELS.clear()


@pytest.fixture
def api(monkeypatch):
    import app

    def fake_sample(engine, voice, text, cache, rate=1.0, **extra):
        out = Path(cache) / f"fake-{abs(hash((engine, voice, text, rate))) % 10 ** 10}.wav"
        return tone(out, 0.4)

    monkeypatch.setattr(audio, "voice_sample", fake_sample)
    monkeypatch.setattr(tts, "voice_sample", fake_sample)
    monkeypatch.setattr(settings_store, "get_secret", lambda name: "sk-test" if name == "openrouter" else "")
    monkeypatch.setattr(audio, "openrouter_available", lambda: True)
    monkeypatch.setattr(audio, "openrouter_blocked", lambda: False)
    monkeypatch.setattr(audio, "openrouter_media_available", lambda: True)
    return TestClient(app.app)


def _clone(tmp_path: Path) -> dict:
    sample = tone(tmp_path / "reference.wav", 9.0)
    return voice_clone.create_clone(
        sample, name="My voice", source="me", consent=True, seconds=9.0,
    )


@needs_ffmpeg
@real_media.needs("speech.wav")
def test_three_previews_and_the_starred_one_comes_first(api, tmp_path):
    for line in ("first line", "second line", "third line"):
        reply = api.post("/api/voices/sample", json={
            "engine": "say", "voice": "Samantha", "text": line, "rate": 1.0,
        })
        assert reply.status_code == 200
    takes = api.get("/api/voices/takes").json()["takes"]
    assert len(takes) == 3
    assert [take["settings"]["text"] for take in takes] == [
        "third line", "second line", "first line",
    ]
    starred = api.patch(f"/api/voices/takes/{takes[1]['id']}", json={"starred": True})
    assert starred.status_code == 200
    # A reload reads the same store from disk.
    again = api.get("/api/voices/takes").json()["takes"]
    assert again[0]["id"] == takes[1]["id"]
    assert again[0]["starred"] is True
    assert again[0]["settings"]["voice"] == "Samantha"
    assert again[0]["settings"]["rate"] == 1.0
    assert len(again) == 3
    assert api.get(again[0]["audio_url"]).status_code == 200


@needs_ffmpeg
def test_clone_preview_keeps_the_clone_name_and_a_saved_voice(api, tmp_path):
    record = _clone(tmp_path)
    reply = api.post(f"/api/voices/clones/{record['voice_id']}/sample", json={"text": "hello"})
    assert reply.status_code == 200
    take = api.get("/api/voices/takes").json()["takes"][0]
    assert take["clone_voice"] == record["voice_id"]
    assert take["label"] == "My voice"
    saved = api.post(f"/api/voices/takes/{take['id']}/save-voice", json={"name": "My voice two"})
    assert saved.status_code == 200
    assert saved.json()["name"] == "My voice two"
    names = [row["name"] for row in api.get("/api/voices/clones").json()["voices"]]
    assert "My voice two" in names
    stock = api.get("/api/voices/takes").json()["takes"]
    assert stock


@needs_ffmpeg
@real_media.needs("speech.wav")
def test_a_stock_take_cannot_become_a_voice(api):
    api.post("/api/voices/sample", json={"engine": "say", "voice": "Samantha", "text": "hi"})
    take = api.get("/api/voices/takes").json()["takes"][0]
    reply = api.post(f"/api/voices/takes/{take['id']}/save-voice", json={"name": "Nope"})
    assert reply.status_code == 400
    assert "cloned voice" in reply.json()["detail"]
    assert "then save that take" in reply.json()["detail"]


@needs_ffmpeg
def test_old_unstarred_takes_are_only_cleaned_after_a_warning(api, tmp_path):
    paths = [tone(tmp_path / f"t{index}.wav") for index in range(3)]
    for index, path in enumerate(paths):
        voice_takes.record_preview(
            path, engine="say", voice="Samantha", text=f"line {index}", rate=1.0,
        )
    rows = voice_takes.list_takes()
    voice_takes.star(rows[0]["id"], True)
    data = json.loads(voice_takes.store_path().read_text())
    old = time.time() - 31 * 86400
    for row in data["takes"]:
        row["created"] = old
    voice_takes.store_path().write_text(json.dumps(data))

    plan = api.get("/api/voices/takes/cleanup").json()
    assert plan["count"] == 2
    assert plan["days"] == voice_takes.CLEANUP_DAYS
    assert api.get("/api/voices/takes").json()["takes"]

    dry = api.post("/api/voices/takes/cleanup", json={"confirm": False}).json()
    assert dry["deleted"] == 0 and dry["kept"] == 2
    assert len(api.get("/api/voices/takes").json()["takes"]) == 3

    done = api.post("/api/voices/takes/cleanup", json={"confirm": True}).json()
    assert done["deleted"] == 2
    left = api.get("/api/voices/takes").json()["takes"]
    assert [row["id"] for row in left] == [rows[0]["id"]]


@needs_ffmpeg
def test_cleanup_removes_every_expired_take_not_only_the_review_page(api, tmp_path):
    source = tone(tmp_path / "one.wav")
    old = time.time() - 31 * 86400
    rows = []
    voice_takes.audio_dir().mkdir(parents=True, exist_ok=True)
    for index in range(55):
        take_id = f"take_{index:024x}"
        voice_takes.audio_dir().joinpath(f"{take_id}.wav").write_bytes(source.read_bytes())
        rows.append({
            "id": take_id, "kind": "preview", "label": f"take {index}",
            "created": old, "starred": False, "clone_voice": "", "cached": False,
            "seconds": 0.5, "check": None,
            "settings": {"text": "line", "engine": "say", "voice": "Samantha", "rate": 1.0, "language": ""},
        })
    voice_takes.store_path().write_text(json.dumps({"version": 1, "takes": rows}))
    plan = api.get("/api/voices/takes/cleanup").json()
    assert plan["count"] == 55
    assert len(plan["takes"]) == 50
    done = api.post("/api/voices/takes/cleanup", json={"confirm": True}).json()
    assert done["deleted"] == 55
    assert api.get("/api/voices/takes").json()["takes"] == []


def test_split_script_keeps_sentences_whole_and_under_the_limit():
    text = "One short line. " + ("A much longer sentence, with clauses, that has to be split. " * 4)
    chunks = voice_takes.split_script(text)
    assert chunks
    assert all(len(chunk) <= voice_takes.MAX_CHUNK_CHARS for chunk in chunks)
    assert chunks[0] == "One short line."
    assert all(chunk.strip() for chunk in chunks)


def test_compare_line_flags_drift_but_tolerates_punctuation():
    script = "Hello there, this is my voice."
    assert voice_takes.compare_line(script, "Hello there this is my voice") > 0.95
    assert voice_takes.compare_line(script, "Goodbye now, nothing like it") < 0.4


@needs_ffmpeg
@real_media.needs("speech.wav")
def test_voiceover_is_one_take_with_lines_and_no_whisper(api, monkeypatch):
    import stt

    monkeypatch.setattr(stt, "_whisper_command", lambda: None)
    reply = api.post("/api/voices/voiceovers", json={
        "engine": "say", "voice": "Samantha",
        "text": "First line. Second line. Third line.",
        "rate": 1.1,
    })
    assert reply.status_code == 200, reply.text
    take = reply.json()
    assert take["kind"] == "voiceover"
    assert take["settings"]["text"] == "First line. Second line. Third line."
    assert take["settings"]["rate"] == 1.1
    assert take["chunks"] and take["chunks"][0]["index"] == 1
    assert take["check"]["available"] is True
    assert take["selfcheck"]["status"] == "unavailable"
    assert "Install it in Setup" in take["selfcheck"]["note"]
    assert api.get(take["audio_url"]).status_code == 200


@needs_ffmpeg
def test_voiceover_cancel_and_one_at_a_time(api, monkeypatch):
    import routes_voice_clone as routes

    event = routes._task_event("vt_cancel_test")
    event.set()
    reply = api.post("/api/voices/voiceovers", json={
        "engine": "say", "voice": "Samantha", "text": "One line.", "task": "vt_cancel_test",
    })
    assert reply.status_code == 409
    assert "No voiceover was made" in reply.json()["detail"]
    assert api.get("/api/voices/takes").json()["takes"] == []

    assert voice_takes._VOICEOVER.acquire(blocking=False)
    try:
        busy = api.post("/api/voices/voiceovers", json={
            "engine": "say", "voice": "Samantha", "text": "One line.",
        })
        assert busy.status_code == 409
        assert "already being made" in busy.json()["detail"]
    finally:
        voice_takes._VOICEOVER.release()


def test_new_shell_holds_the_takes_aside():
    next_js = (ROOT / "static" / "voice" / "next.js").read_text(encoding="utf-8")
    takes_js = (ROOT / "static" / "voice" / "takes.js").read_text(encoding="utf-8")
    assert 'from "./takes.js"' in next_js
    assert "vg-takes" in takes_js
    for name in ("onLoadSettings", "saveTakeAsVoice", "starTake", "deleteTake"):
        assert name in takes_js
    assert "takesPanel.refresh()" in next_js


def test_cancel_stops_waiting_for_a_line_already_sent():
    import threading

    event = threading.Event()
    release = threading.Event()

    def slow_line():
        release.wait(5)
        return Path("late.wav")

    timer = threading.Timer(0.1, event.set)
    timer.start()
    started = time.monotonic()
    try:
        with pytest.raises(voice_takes.TakeError) as caught:
            voice_takes._speak(slow_line, event)
    finally:
        release.set()
        timer.cancel()
    assert caught.value.status_code == 409
    assert time.monotonic() - started < 2.0
