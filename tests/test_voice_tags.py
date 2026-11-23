"""Voice tags: one script, the syntax of the selected engine.

HeyGen takes square-bracket tags in the text. MiniMax takes one emotion
field per request plus parenthesis interjections and <#x#> pauses.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

import audio
import settings_store
import stt
import tts
import voice_takes
import voice_tags

ROOT = Path(__file__).resolve().parents[1]
def test_heygen_keeps_its_tags_and_lowercases_them():
    out = voice_tags.prepare("[SAD] I walked past the house. [sighs] The garden is gone.", "heygen")
    assert out["text"] == "[sad] I walked past the house. [sighs] The garden is gone."
    assert out["emotion"] == ""


def test_heygen_picker_adds_one_span_tag_and_intensity():
    assert voice_tags.prepare("Hello", "heygen", "sad")["text"] == "[sad] Hello"
    assert voice_tags.prepare("Hello", "heygen", "slightly sad")["text"] == "[slightly sad] Hello"
    # A tag already in the script wins; do not stack two.
    out = voice_tags.prepare("[happy] Hello", "heygen", "sad")
    assert out["text"] == "[happy] Hello"


def test_minimax_gets_emotion_events_and_pauses_not_square_tags():
    out = voice_tags.prepare("[sad] I missed you. [sighs] It is late. [pause]", "minimax")
    assert out["emotion"] == "sad"
    assert "[" not in out["text"]
    assert "(sighs)" in out["text"]
    assert "<#0.50#>" in out["text"]


def test_minimax_maps_the_picker_and_says_what_it_cannot_do():
    out = voice_tags.prepare("Hello", "minimax", "fearful")
    assert out["emotion"] == "fearful"
    assert out["text"] == "Hello"

    whisper = voice_tags.prepare("[whispers] A secret", "minimax")
    assert whisper["emotion"] == "calm"
    assert "no whisper" in " ".join(whisper["notes"])
    assert "[" not in whisper["text"]

    shout = voice_tags.prepare("[shouts] Stop", "minimax")
    assert shout["emotion"] == ""
    assert "cannot perform" in " ".join(shout["notes"])


def test_other_engines_never_speak_the_tags():
    out = voice_tags.prepare("[sad] Hello [laughs]", "say")
    assert out["text"] == "Hello"
    assert out["notes"]


def test_compare_text_removes_marks_but_keeps_words():
    script = "[sad] I missed you. (sighs) It is late. <#0.5#>"
    assert voice_tags.compare_text(script) == "I missed you. It is late."
    # A normal parenthesis is speech, not a MiniMax event.
    assert voice_tags.compare_text("(important) Hello") == "(important) Hello"
    assert voice_tags.prepare("(important) Hello", "say")["text"] == "(important) Hello"


def test_catalog_has_engine_specific_options():
    catalog = voice_tags.catalog()["engines"]
    assert [row["id"] for row in catalog["heygen"]["options"]][:3] == ["auto", "happy", "sad"]
    assert "whispers" in [row["id"] for row in catalog["heygen"]["options"]]
    minimax = [row["id"] for row in catalog["minimax"]["options"]]
    assert "fearful" in minimax and "whispers" not in minimax
    assert "no whisper" in catalog["minimax"]["hint"]


def test_cache_key_changes_with_emotion():
    plain = tts.line_cache_key("minimax", "", "voice", "hello", 1.0, "en")
    sad = tts.line_cache_key("minimax", "", "voice", "hello", 1.0, "en", "sad")
    assert plain != sad


def test_minimax_request_carries_the_emotion_and_clean_text(monkeypatch, tmp_path):
    import urllib.request

    monkeypatch.setattr(tts.audio, "minimax_key", lambda: "test-key")
    monkeypatch.setattr(tts.audio, "_convert", lambda source, output, extra=None: output.write_bytes(b"RIFF" + b"0" * 64))
    seen = {}

    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps({"data": {"audio": "00" * 100}, "base_resp": {"status_code": 0}}).encode()

    def fake_urlopen(request, timeout=0):
        seen["body"] = json.loads(request.data.decode())
        return Reply()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    tts._minimax_voice("I missed you.", "female-shaonv", tmp_path / "out.wav", emotion="sad")
    assert seen["body"]["voice_setting"]["emotion"] == "sad"
    assert seen["body"]["text"] == "I missed you."


def test_voiceover_prepares_each_line_for_the_selected_engine(monkeypatch, tmp_path):
    monkeypatch.setattr(settings_store, "DATA", tmp_path)
    monkeypatch.setattr(settings_store, "get_secret", lambda name: "sk-test" if name == "openrouter" else "")
    monkeypatch.setattr(audio, "openrouter_available", lambda: True)
    monkeypatch.setattr(audio, "openrouter_blocked", lambda: False)
    monkeypatch.setattr(audio, "openrouter_media_available", lambda: True)
    monkeypatch.setattr(stt, "_whisper_command", lambda: None)
    calls = []

    def fake_sample(engine, voice, text, cache, rate=1.0, language="", emotion=""):
        calls.append((engine, text, emotion))
        path = Path(cache) / f"line-{len(calls)}.wav"
        path.write_bytes(b"RIFF" + b"0" * 64)
        return path

    monkeypatch.setattr(tts, "voice_sample", fake_sample)
    monkeypatch.setattr(voice_takes, "_probe", lambda path: 0.4)
    monkeypatch.setattr(voice_takes, "_check", lambda path: {"available": True, "duration": 0.4})
    monkeypatch.setattr(
        voice_takes, "_concat",
        lambda parts, output: output.write_bytes(parts[0].read_bytes()),
    )
    import app

    api = TestClient(app.app)
    reply = api.post("/api/voices/voiceovers", json={
        "engine": "minimax", "voice": "female-shaonv",
        "text": "[sad] I missed you. [laughs] It is late.",
    })
    assert reply.status_code == 200, reply.text
    assert calls == [
        ("minimax", "I missed you.", "sad"),
        ("minimax", "(laughs) It is late.", ""),
    ]
    take = reply.json()
    assert take["settings"]["emotion"] == ""
    assert take["chunks"][0]["emotion"] == "sad"
    assert take["chunks"][0]["spoken"] == "I missed you."


def test_heygen_voiceover_keeps_tags_in_the_text(monkeypatch, tmp_path):
    monkeypatch.setattr(settings_store, "DATA", tmp_path)
    monkeypatch.setattr(stt, "_whisper_command", lambda: None)
    calls = []

    def fake_sample(engine, voice, text, cache, rate=1.0, language="", emotion=""):
        calls.append((text, emotion))
        path = Path(cache) / f"line-{len(calls)}.wav"
        path.write_bytes(b"RIFF" + b"0" * 64)
        return path

    monkeypatch.setattr(tts, "voice_sample", fake_sample)
    monkeypatch.setattr(voice_takes, "_probe", lambda path: 0.4)
    monkeypatch.setattr(voice_takes, "_check", lambda path: {"available": True, "duration": 0.4})
    monkeypatch.setattr(
        voice_takes, "_concat",
        lambda parts, output: output.write_bytes(parts[0].read_bytes()),
    )
    import app

    api = TestClient(app.app)
    reply = api.post("/api/voices/voiceovers", json={
        "engine": "heygen", "voice": "bram", "text": "[sad] I missed you.",
    })
    assert reply.status_code == 200, reply.text
    assert calls == [("[sad] I missed you.", "")]


def test_catalog_exposes_the_tag_options_and_the_page_uses_them():
    from pathlib import Path as P

    import app

    catalog = TestClient(app.app).get("/api/voices/catalog").json()
    assert catalog["voice_tags"]["heygen"]["options"]
    assert catalog["voice_tags"]["minimax"]["options"]
    page = (P(__file__).resolve().parents[1] / "static" / "voice" / "next.js").read_text()
    assert "emotionRows" in page and "Emotion" in page
    assert "emotion: scriptEmotion" in page
