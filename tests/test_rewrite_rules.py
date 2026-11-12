"""Loop 9: rewrite stays local, no cloud call, no model name in the UI."""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from duckcore import app_settings, edits, script
from duckcore.engine import stt


def _edit(tmp_path: Path) -> dict:
    edit = {
        "id": "ed_test01", "project_id": "prj_test", "schema": 1, "kind": "full",
        "title": "Test", "created": 1.0, "updated": 1.0, "start": 0.0, "end": 10.0,
        "captions": {
            "cues": [
                {"start": 0.0, "end": 1.0, "text": "Um, this is, you know, fine."},
                {"start": 1.0, "end": 2.0, "text": "Basically really very good."},
            ],
        },
    }
    (tmp_path / "projects" / "prj_test" / "edits").mkdir(parents=True, exist_ok=True)
    return edit


def test_rewrite_falls_back_to_basic_cleanup_without_apple(tmp_path, monkeypatch) -> None:
    edit = _edit(tmp_path)

    def no_apple(*_args, **_kwargs):
        raise ValueError("Apple Intelligence is not available.")

    monkeypatch.setattr(script, "_run", no_apple)
    out = script.rewrite(edit, tmp_path, mode="clean")
    meta = edit["script"]
    assert meta["engine"] == "basic-cleanup"
    assert meta["fallback"] is True
    assert "Um" not in out["cues"][0]["text"]
    assert "you know" not in out["cues"][0]["text"].lower()
    # Saved through the normal edit path.
    assert json.loads(
        (tmp_path / "projects" / "prj_test" / "edits" / "ed_test01.json").read_text(),
    )["script"]["engine"] == "basic-cleanup"


def test_nothing_leaves_the_mac_with_every_key_set(tmp_path, monkeypatch) -> None:
    for name in ("GROQ_API_KEY", "DEEPGRAM_API_KEY", "OPENROUTER_API_KEY",
                 "OPENAI_API_KEY", "DUCK_STT_PROVIDER"):
        monkeypatch.setenv(name, "test-key")
    for name in ("DUCK_OLLAMA_URL", "DUCK_OLLAMA_MODEL"):
        monkeypatch.setenv(name, "http://127.0.0.1:11434")

    contacted: list[str] = []
    original = socket.socket.connect

    def guarded(self, address):
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in {"127.0.0.1", "localhost", "::1"}:
            contacted.append(str(host))
            raise AssertionError(f"network call to {host}")
        return original(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded)
    edit = _edit(tmp_path)
    monkeypatch.setattr(script, "_run", lambda *_a, **_k: (_ for _ in ()).throw(ValueError("off")))
    script.rewrite(edit, tmp_path, mode="short")

    wav = tmp_path / "silence.wav"
    wav.write_bytes(b"RIFF" + b"\0" * 64)
    try:
        stt.transcribe(wav, tmp_path, 0.5, lambda *_a: None)
    except Exception:  # no whisper pack in the test: still no network
        pass
    assert contacted == []


def test_old_online_settings_load_and_are_dropped(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({
        "language": "auto",
        "online_enabled": True,
        "online_endpoint": "https://render.example.com",
    }))
    loaded = app_settings.load(tmp_path)
    assert "online_enabled" not in loaded and "online_endpoint" not in loaded
    snap = app_settings.snapshot(tmp_path)
    assert "online" not in snap
    app_settings.update(tmp_path, {"fill_device": "gpu"})
    saved = json.loads(path.read_text())
    assert "online_enabled" not in saved and "online_endpoint" not in saved


def test_the_review_project_loop_is_dropped() -> None:
    """(a) 90.0, 91.86 and 94.7 s: one run of copies, the last 23 s for ten words."""
    same = "I'm going to eat a little bit of chicken."
    data = {
        "segments": [
            {"start": 90.0, "end": 91.86, "text": same},
            {"start": 91.86, "end": 92.96, "text": same},
            {"start": 94.7, "end": 118.06, "text": same},
        ],
        "words": [],
    }
    assert stt._whisper_payload(data)["segments"] == []


def test_the_same_line_a_minute_later_keeps_both() -> None:
    """(b) A real repeat is not a loop: 60 s apart, one copy slow."""
    same = "We are going to eat a little bit of chicken."
    data = {
        "segments": [
            {"start": 10.0, "end": 12.0, "text": same},
            {"start": 72.0, "end": 96.0, "text": same},
        ],
        "words": [],
    }
    assert len(stt._whisper_payload(data)["segments"]) == 2


def test_a_chorus_at_speaking_pace_keeps_all_three() -> None:
    """(c) Three back-to-back copies, none slow: a chorus, not a loop."""
    same = "Everybody sing it now"
    data = {
        "segments": [
            {"start": 0.0, "end": 1.6, "text": same},
            {"start": 1.6, "end": 3.2, "text": same},
            {"start": 3.2, "end": 4.8, "text": same},
        ],
        "words": [],
    }
    assert len(stt._whisper_payload(data)["segments"]) == 3


def test_one_slow_line_is_kept_when_it_is_not_repeated() -> None:
    data = {
        "segments": [
            {"start": 0.0, "end": 30.0, "text": "a deliberately slow line of speech"},
        ],
        "words": [],
    }
    assert len(stt._whisper_payload(data)["segments"]) == 1


def test_no_model_name_in_the_ui() -> None:
    root = Path(__file__).resolve().parent.parent / "static" / "duck"
    names = ("lama", "big-lama", "whisper", "kokoro", "qwen", "nllb", "deepseek",
             "gemini", "openai", "groq", "deepgram", "ollama")
    found = []
    for path in root.rglob("*"):
        if path.suffix not in {".js", ".html", ".css"} or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        found += [f"{path.name}:{name}" for name in names if name in text]
    assert found == []
