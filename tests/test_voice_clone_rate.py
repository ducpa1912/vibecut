"""A cloned voice's preview speaks at the page's Rate, kept to 0.5-2.0×.

The speech call is faked; no media is made.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import audio
import settings_store
import voice_clone

ROOT = Path(__file__).resolve().parents[1]


def test_clone_sample_uses_the_rate_and_clamps_it(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(settings_store, "DATA", tmp_path)
    sample = tmp_path / "s.mp3"
    sample.write_bytes(b"ID3" + b"\x00" * 4000)
    record = voice_clone.create_clone(sample, name="Me", source="me", consent=True, seconds=30)
    rates = []

    def fake_sample(engine, voice, text, cache, rate=1.0, **extra):
        rates.append(rate)
        out = tmp_path / "out.wav"
        out.write_bytes(b"RIFF" + b"0" * 64)
        return out

    monkeypatch.setattr(audio, "voice_sample", fake_sample)
    api = TestClient(app.app)
    url = f"/api/voices/clones/{record['voice_id']}/sample"
    for rate in (1.15, 9, 0):
        assert api.post(url, json={"text": "hi", "rate": rate}).status_code == 200
    assert rates == [1.15, 2.0, 0.5]


def test_both_pages_send_the_rate_with_a_clone_preview():
    voice = ROOT / "static" / "voice"
    assert 'export function playClone(voiceId, text = "", rate = 1)' in (voice / "voiceclone.js").read_text()
    assert "{ text, rate }" in (voice / "voiceclone.js").read_text()
    assert "playClone(item.voice_id, testLine, rate)" in (voice / "voiceroom.js").read_text()
    assert "playClone(id, lineText, rate)" in (voice / "next.js").read_text()
