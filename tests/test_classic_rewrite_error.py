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
