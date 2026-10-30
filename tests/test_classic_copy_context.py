"""Classic Copy keeps full-transcript context when no translation is chosen."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _segments() -> list[dict]:
    return [
        {"start": 0.0, "end": 2.5, "text": "The garden opens at dawn."},
        {"start": 4.0, "end": 7.0, "text": "She waters every row by hand."},
        {"start": 9.0, "end": 12.0, "text": "The payoff is the quiet harvest."},
    ]


def _scenes() -> list[dict]:
    return [
        {"id": 0, "start": 0.0, "end": 3.0, "speech": "The garden opens at dawn.", "tags": ["garden"], "attention": {"face": True}},
        {"id": 1, "start": 4.0, "end": 8.0, "speech": "She waters every row by hand.", "tags": ["hands"], "attention": {"face": False}},
        {"id": 2, "start": 9.0, "end": 13.0, "speech": "The payoff is the quiet harvest.", "tags": ["harvest"], "attention": {"face": False}},
    ]


def _clips() -> list[dict]:
    return [
        {"scene": 0, "role": "hook", "duration": 3.0},
        {"scene": 1, "role": "beat", "duration": 4.0},
        {"scene": 2, "role": "payoff", "duration": 4.0},
    ]


def test_no_translation_still_builds_cut_beats_and_the_full_transcript(monkeypatch):
    import audio

    monkeypatch.setattr(audio, "opencode_available", lambda: True)
    monkeypatch.setattr(
        audio.settings_store,
        "load_settings",
        lambda: {"opencode": {"use_rewrite": True}},
    )

    context = audio.transcript_context(
        _segments(), _clips(), _scenes(), "en", target_lang="",
    )

    assert context["full_text"] == " ".join(segment["text"] for segment in _segments())
    assert [beat["role"] for beat in context["beats"]] == ["hook", "beat", "payoff"]
    assert [beat["source"] for beat in context["beats"]] == [
        "The garden opens at dawn",
        "She waters every row by hand",
        "The payoff is the quiet harvest",
    ]
    assert "target_text" not in context
    assert context["full_context"] is True


def test_the_no_translation_rewrite_prompt_reads_the_full_script(monkeypatch):
    import audio

    monkeypatch.setattr(audio, "opencode_available", lambda: True)
    monkeypatch.setattr(
        audio.settings_store,
        "load_settings",
        lambda: {"opencode": {"use_rewrite": True}},
    )
    context = audio.transcript_context(
        _segments(), _clips(), _scenes(), "en", target_lang="",
    )
    script = [
        {"scene": 0, "role": "hook", "text": "Dawn opens the garden.", "duration": 3.0, "rate": 1.0},
        {"scene": 1, "role": "beat", "text": "Every row is watered by hand.", "duration": 4.0, "rate": 1.0},
        {"scene": 2, "role": "payoff", "text": "The quiet harvest pays off.", "duration": 4.0, "rate": 1.0},
    ]

    prompt = audio._rewrite_prompt(
        script, "en", "en", "smooth", [line["text"] for line in script], context,
    )

    assert "FULL VOICE SCRIPT:" in prompt
    assert "She waters every row by hand." in prompt
    assert '"source_line": "The garden opens at dawn"' in prompt


def test_the_script_route_always_builds_context_from_segments():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    start = source.index("def audio_script(job_id: str")
    body = source[start:source.index("\ndef ", start + 10)]
    assert "segments = pipeline.read_transcript(" in body
    assert "audio.transcript_context(" in body
    assert "if segments else None" in body
