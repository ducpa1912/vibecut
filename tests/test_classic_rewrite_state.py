"""A running rewrite must not leave the Rewrite button disabled.

Changing a setting while a rewrite is in flight used to reset the panel but
leave the old fetch pending, so the button stayed disabled until it returned.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _script() -> str:
    return (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")


def test_resetting_the_script_cancels_the_running_request():
    script = _script()
    start = script.index("function resetAudioScript(")
    body = script[start:script.index("function cancelAudioScript(", start)]
    assert "cancelAudioScript();" in body
    assert "dom.audioRewriteRun.disabled = false" in script[
        script.index("function cancelAudioScript("):
        script.index("async function loadAudioScript(", script.index("function cancelAudioScript("))
    ]


def test_the_rewrite_fetch_carries_an_abort_signal():
    script = _script()
    start = script.index("async function loadAudioScript(")
    body = script[start:script.index("function scriptHeadLabel(", start)]
    assert "new AbortController()" in body
    assert "signal: controller.signal" in body
    assert 'error?.name === "AbortError"' in body
    assert "state.scriptAbort === controller" in body


def test_an_old_response_cannot_clear_a_newer_rewrite():
    script = _script()
    assert "if (state.scriptAbort === controller) {" in script
    assert "state.scriptAbort = null;" in script
