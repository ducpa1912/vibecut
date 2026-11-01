"""The 15 s reference guard and the trimmer's server side.

A 60 s tone is written by the test. Cleaning is faked to copy the cut, so no
model runs; the cloud is never called.
"""

from __future__ import annotations

import json
import math
import shutil
import struct
import subprocess
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import audio
import settings_store
import voice_audio
import voice_extract
import voice_reference

ROOT = Path(__file__).resolve().parents[1]
VOICE = ROOT / "static" / "voice"
needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is not installed")


def tone(path: Path, seconds: float = 60.0, rate: int = 16000, amplitude: int = 9000) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frames = bytearray()
        for index in range(int(rate * seconds)):
            frames += struct.pack("<h", int(amplitude * math.sin(2 * math.pi * 220 * index / rate)))
        handle.writeframes(bytes(frames))
    return path


def silent(path: Path, seconds: float = 20.0, rate: int = 16000) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * int(rate * seconds))
    return path


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_store, "DATA", tmp_path)
    monkeypatch.setattr(settings_store, "get_secret", lambda name: "sk-test" if name == "openrouter" else "")
    monkeypatch.setattr(audio, "openrouter_available", lambda: True)
    monkeypatch.setattr(audio, "openrouter_blocked", lambda: False)
    monkeypatch.setattr(audio, "openrouter_media_available", lambda: True)

    def fake_clean(source, out_dir, **kwargs):
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        target = out / "clean.wav"
        shutil.copyfile(source, target)
        return {"path": str(target), "quality": {}, "warnings": []}

    monkeypatch.setattr(voice_extract, "extract_clean_voice", fake_clean)
    yield tmp_path


@pytest.fixture
def api():
    import app

    return TestClient(app.app)


def upload(api, path: Path):
    with path.open("rb") as handle:
        return api.post(
            "/api/voices/reference",
            files={"file": (path.name, handle, "audio/wav")},
        )


@needs_ffmpeg
def test_a_long_clip_opens_on_a_clean_10_to_15_second_window(api, tmp_path):
    reply = upload(api, tone(tmp_path / "long.wav", 60.0))
    assert reply.status_code == 200, reply.text
    body = reply.json()
    assert 59.5 <= body["duration"] <= 60.5
    best = body["best"]
    length = best["end"] - best["start"]
    assert 10.0 <= length <= 15.0
    assert best["start"] >= 0 and best["end"] <= body["duration"] + 0.01
    assert body["best"]["ok"] is True
    assert len(body["peaks"]) >= 24
    assert body["limits"]["min_seconds"] == 8
    assert body["limits"]["max_seconds"] == 15
    assert body["audio_url"] == f"/api/voices/reference/{body['id']}/audio"


@needs_ffmpeg
def test_the_reference_audio_is_served_with_range_support(api, tmp_path):
    ref = upload(api, tone(tmp_path / "long.wav", 20.0)).json()
    reply = api.get(ref["audio_url"])
    assert reply.status_code == 200
    assert reply.headers["content-type"].startswith("audio/wav")
    ranged = api.get(ref["audio_url"], headers={"Range": "bytes=0-1023"})
    assert ranged.status_code in (200, 206)
    assert len(ranged.content) <= 4096


@needs_ffmpeg
def test_clone_from_the_best_window_and_the_session_is_removed(api, tmp_path):
    ref = upload(api, tone(tmp_path / "long.wav", 60.0)).json()
    best = ref["best"]
    reply = api.post(f"/api/voices/reference/{ref['id']}/clone", json={
        "name": "Trimmed", "language": "en", "consent": True,
        "start": best["start"], "end": best["end"],
    })
    assert reply.status_code == 200, reply.text
    body = reply.json()
    assert body["name"] == "Trimmed"
    assert 10.0 <= body["trim"]["seconds"] <= 15.0
    assert body["voice_id"].startswith("clone_")
    # The session, and its raw upload, are gone.
    assert api.get(ref["audio_url"]).status_code == 404
    assert not (tmp_path / "cache" / "reference" / ref["id"]).exists()


@needs_ffmpeg
def test_the_server_enforces_the_8_to_15_second_limits(api, tmp_path):
    ref = upload(api, tone(tmp_path / "long.wav", 60.0)).json()
    url = f"/api/voices/reference/{ref['id']}/clone"
    too_long = api.post(url, json={"consent": True, "start": 0, "end": 30})
    assert too_long.status_code == 400
    assert "15 s or less" in too_long.json()["detail"]
    too_short = api.post(url, json={"consent": True, "start": 1, "end": 4})
    assert too_short.status_code == 400
    assert "at least 8 s" in too_short.json()["detail"]
    no_consent = api.post(url, json={"consent": False, "start": 0, "end": 12})
    assert no_consent.status_code == 400
    assert "consent" in no_consent.json()["detail"].lower()
    backwards = api.post(url, json={"consent": True, "start": 9, "end": 2})
    assert backwards.status_code == 400
    assert "end" in backwards.json()["detail"].lower()


@needs_ffmpeg
def test_a_silent_reference_never_opens_the_trimmer(api, tmp_path):
    reply = upload(api, silent(tmp_path / "silent.wav"))
    assert reply.status_code == 400
    assert "No speech could be heard" in reply.json()["detail"]


@needs_ffmpeg
def test_a_discarded_reference_leaves_nothing_behind(api, tmp_path):
    ref = upload(api, tone(tmp_path / "long.wav", 20.0)).json()
    assert api.delete(f"/api/voices/reference/{ref['id']}").json()["deleted"] is True
    assert api.get(ref["audio_url"]).status_code == 404


def test_bad_uploads_say_what_to_do_next(api, tmp_path):
    wrong = tmp_path / "notes.txt"
    wrong.write_text("not audio")
    with wrong.open("rb") as handle:
        reply = api.post("/api/voices/reference", files={"file": ("notes.txt", handle, "text/plain")})
    assert reply.status_code == 400
    assert "WAV" in reply.json()["detail"]


@needs_ffmpeg
def test_window_defaults_to_the_best_part_when_no_range_is_sent():
    meta = {"duration": 60.0, "best": {"start": 12.0, "end": 24.0}}
    assert voice_reference.window_for(meta, None, None) == (12.0, 24.0)
    assert voice_reference.window_for(meta, 2.0, 15.0) == (2.0, 15.0)
    # The chosen range is kept inside the file.
    assert voice_reference.window_for(meta, 2.0, 900.0) == (2.0, 60.0)


def test_trimmer_js_holds_the_controls_and_limits():
    text = (VOICE / "trimmer.js").read_text(encoding="utf-8")
    for name in ("openTrimmer", "clampWindow", "windowLabel", "zoomRange"):
        assert f"export function {name}" in text, name
    for copy in ("Fit all", "Fit selection", "Loop the selection", "Use this part", "too short", "too long"):
        assert copy in text, copy
    assert "Shift+scroll" in text and "Space plays" in text and "Esc cancels" in text


def test_both_voice_pages_trim_long_references():
    clone = (VOICE / "voiceclone.js").read_text(encoding="utf-8")
    assert "trim = false" in clone
    for name in ("uploadReference", "cloneReference", "discardReference", "openTrimmer"):
        assert name in clone, name
    assert "trim: true" in (VOICE / "next.js").read_text(encoding="utf-8")
    assert "trim: true" in (VOICE / "voiceroom.js").read_text(encoding="utf-8")


def test_trimmer_pure_helpers_clamp_and_read_out():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    script = (
        f"const m = await import({json.dumps((VOICE / 'trimmer.js').as_uri())});\n"
        "const out = {\n"
        "  big: m.clampWindow(0, 60, 60),\n"
        "  small: m.clampWindow(2, 4, 60),\n"
        "  edge: m.clampWindow(-3, 500, 20),\n"
        "  ok: m.windowLabel(0, 12),\n"
        "  short: m.windowLabel(0, 4),\n"
        "  long: m.windowLabel(0, 30),\n"
        "  zoom: m.zoomRange({start: 0, end: 60}, 0.5, 30, 60),\n"
        "};\n"
        "process.stdout.write(JSON.stringify(out));\n"
    )
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["big"]["seconds"] == 15
    assert out["small"]["seconds"] == 8
    assert out["edge"] == {"start": 0, "end": 15, "seconds": 15}
    assert out["ok"] == {"tone": "ok", "text": "12.0 s · ok"}
    assert out["short"]["tone"] == "bad" and "too short" in out["short"]["text"]
    assert out["long"]["tone"] == "bad" and "too long" in out["long"]["text"]
    assert out["zoom"]["end"] - out["zoom"]["start"] == 30
