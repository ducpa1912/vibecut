"""Transcript fallback tests.

Apple Speech cannot auto-detect a language. When it is the only ready local
engine, the system language must be used instead of dropping the transcript.
"""

from __future__ import annotations

from pathlib import Path

from duckcore.engine import stt


def test_apple_only_route_uses_system_language(tmp_path: Path, monkeypatch) -> None:
    wav = tmp_path / "audio.wav"
    wav.write_bytes(b"fake wave")
    seen: dict[str, str] = {}

    monkeypatch.setattr(stt, "has_speech_energy", lambda _path: True)
    monkeypatch.setattr(stt, "prepare_audio", lambda path, job_dir, **_kwargs: (path, "hash"))
    monkeypatch.setattr(
        stt, "_engine_ready",
        lambda provider, model: provider == "apple",
    )
    monkeypatch.setattr(stt, "_system_speech_language", lambda default="en": "vi")

    def chunked(*_args, language="", **_kwargs):
        seen["language"] = language
        return {
            "language": "vi",
            "segments": [{"start": 0.0, "end": 1.0, "text": "Xin chào."}],
            "words": [],
            "drift_ms_p95": 0.0,
        }

    monkeypatch.setattr(stt, "_chunked_run", chunked)
    errors: list[dict] = []
    result = stt.transcribe_source(
        wav,
        tmp_path,
        1.0,
        routes=[
            {"provider": "apple", "model": "on-device-3b"},
            {"provider": "whisper", "model": stt.DEFAULT_WHISPER_MODEL},
        ],
        language="auto",
        errors=errors,
    )

    assert result is not None
    assert seen["language"] == "vi"
    assert result["provider"] == "apple"
    assert result["segments"]
    assert not any(item.get("provider") == "apple" for item in errors)
