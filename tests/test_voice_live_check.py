"""scripts/voice_live_check.py: one live OpenRouter request, never by accident.

No media is made here: the sample cut, the speech reply and its conversion
are faked. The tests prove the dry run sends nothing, the real run sends
exactly one request carrying the cut sample, and the temporary clone it
makes is always deleted.
"""

from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path

import pytest

import audio
import settings_store
import tts
import voice_clone

ROOT = Path(__file__).resolve().parents[1]
CUT = b"ID3" + b"\x07" * 4000


def _script():
    spec = importlib.util.spec_from_file_location("voice_live_check", ROOT / "scripts" / "voice_live_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def clone(monkeypatch, tmp_path):
    monkeypatch.setattr(settings_store, "DATA", tmp_path)
    cuts = []

    def fake_prepare(source, output, **kwargs):
        cuts.append(kwargs)
        Path(output).write_bytes(CUT)
        return 10.0

    monkeypatch.setattr(voice_clone, "prepare_sample", fake_prepare)
    monkeypatch.setattr(voice_clone, "_probe_seconds", lambda path: 2.0)
    sample = tmp_path / "sample.mp3"
    sample.write_bytes(b"ID3" + b"\x01" * 8000)
    record = voice_clone.create_clone(sample, name="Founder", source="me", consent=True, language="en", seconds=95)
    return {"record": record, "cuts": cuts}


class Reply:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return b"\x01\x00" * 4410


def test_dry_run_sends_nothing(monkeypatch, clone, capsys):
    import urllib.request

    def refuse(*_args, **_kwargs):
        raise AssertionError("the dry run must not touch the network")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    assert _script().main([]) == 2
    out = capsys.readouterr().out
    assert "Dry run: nothing was sent." in out
    assert "Founder" in out and "1 x POST https://openrouter.ai/api/v1/audio/speech" in out
    assert clone["cuts"] == [{"start": 0.0, "duration": 10.0}]
    assert [row["voice_id"] for row in voice_clone.list_clones()] == [clone["record"]["voice_id"]]


def test_live_run_sends_one_request_with_the_cut_sample(monkeypatch, clone, tmp_path, capsys):
    import urllib.request

    monkeypatch.setattr(audio, "openrouter_key", lambda: "sk-test")
    monkeypatch.setattr(audio, "openrouter_blocked", lambda: False)
    monkeypatch.setattr(audio, "_convert", lambda s, o, e=None: Path(o).write_bytes(b"RIFF" + b"0" * 64) or o)
    sent = []

    def fake_urlopen(request, timeout=0):
        sent.append(json.loads(request.data.decode()))
        return Reply()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    out_path = tmp_path / "reply.wav"
    assert _script().main(["--yes-send-to-openrouter", "--out", str(out_path)]) == 0
    assert len(sent) == 1
    body = sent[0]
    assert body["model"] == tts.DEFAULT_MODELS["heygen"] and "voice" not in body
    data = body["input_references"][0]["input_audio"]["data"].split(",", 1)[1]
    assert base64.b64decode(data) == CUT
    assert out_path.is_file()
    assert "OK:" in capsys.readouterr().out
    # The temporary clone is gone; the founder's clone is untouched.
    assert [row["voice_id"] for row in voice_clone.list_clones()] == [clone["record"]["voice_id"]]


def test_live_run_without_a_key_sends_nothing(monkeypatch, clone):
    import urllib.request

    def refuse(*_args, **_kwargs):
        raise AssertionError("sent without a key")

    monkeypatch.setattr(audio, "openrouter_key", lambda: "")
    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    assert _script().main(["--yes-send-to-openrouter"]) == 1
    assert len(voice_clone.list_clones()) == 1


def test_no_clone_stops_before_anything(monkeypatch, tmp_path):
    monkeypatch.setattr(settings_store, "DATA", tmp_path)
    with pytest.raises(SystemExit) as stop:
        _script().main([])
    assert "No cloned voices yet" in str(stop.value)
