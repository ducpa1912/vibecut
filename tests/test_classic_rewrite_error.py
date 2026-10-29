"""A rewrite that gets no model output must report, not crash the request.

Classic's second Rewrite returned 500 because `_rewrite_opencode` assigned
`OPENCODE_LAST_ERROR` without declaring it global, so Python treated the name
as local and raised UnboundLocalError on the read.
"""

from __future__ import annotations


def test_rewrite_without_model_output_sets_the_error(monkeypatch):
    import audio

    monkeypatch.setattr(audio, "opencode_available", lambda: True)
    monkeypatch.setattr(
        audio.settings_store,
        "load_settings",
        lambda: {"opencode": {"use_rewrite": True}},
    )
    monkeypatch.setattr(audio, "_opencode_json_attempts", lambda *args, **kwargs: None)
    monkeypatch.setattr(audio, "OPENCODE_LAST_ERROR", "")

    result = audio._rewrite_opencode(
        [{"scene": 0, "text": "a line"}], "en", "vi", "smooth", ["a line"],
    )

    assert result is None
    assert "no usable rewrite" in audio.OPENCODE_LAST_ERROR.lower()


def test_a_provider_lockout_falls_back_instead_of_raising(monkeypatch):
    """The pass-1 500 path: OpenCode returns nothing, OpenRouter is locked.

    With no usable rewrite the cut keeps its literal lines and the request
    reports a fallback; it must not raise through to a 500.
    """
    import audio

    monkeypatch.setattr(audio, "opencode_available", lambda: True)
    monkeypatch.setattr(
        audio.settings_store,
        "load_settings",
        lambda: {"opencode": {"use_rewrite": True}},
    )
    monkeypatch.setattr(audio, "_opencode_json_attempts", lambda *args, **kwargs: None)
    monkeypatch.setattr(audio, "OPENCODE_LAST_ERROR", "")

    lines = [{"scene": 0, "text": "The garden is easy.", "duration": 2.0}]
    result = audio.adapt_script(lines, "en", "en", "smooth")

    assert result and "garden" in result[0]["text"].lower()
    assert isinstance(audio.rewrite_status(), dict)
