"""Classic Copy card: transcript icon, honest badge, one rewrite at a time."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")
PAGE = (ROOT / "static" / "classic" / "index.html").read_text(encoding="utf-8")
STYLE = (ROOT / "static" / "classic" / "style.css").read_text(encoding="utf-8")


def _function(name: str, next_name: str) -> str:
    start = SCRIPT.index(f"function {name}(")
    return SCRIPT[start:SCRIPT.index(f"function {next_name}(", start)]


def test_the_copy_card_has_a_transcript_ready_icon():
    assert 'id="copy-transcript"' in PAGE
    assert 'aria-label="Transcript ready"' in PAGE
    assert ".copy-transcript" in STYLE
    assert ".copy-transcript[hidden]" in STYLE


def test_a_job_with_a_transcript_shows_the_icon():
    body = _function("transcriptInfo", "paintTranscriptReady")
    assert "state.job?.analysis?.transcript" in body
    assert "segments" in body
    assert "text" in body
    paint = _function("paintTranscriptReady", "isAbortError")
    assert "hidden = !info.ready" in paint
    assert "Transcript ready" in paint
    assert "paintTranscriptReady();" in SCRIPT


def test_the_badge_is_hidden_until_there_is_real_translation_state():
    body = _function("paintTranslateBadge", "translationStatus")
    assert '["ready", "running", "failed"].includes(status)' in body
    assert "hidden = true" in body
    # Failure is only painted from a real failed state, never from idle.
    assert 'status === "failed"' in body
    assert "Translation failed" in body


def test_a_translation_status_read_error_never_paints_failure():
    body = _function("ensureTranslation", "cancelTranslationWarm")
    assert "status === \"failed\"" in body
    # The three-strike status read path returns without a failed badge.
    read_error = body[body.index("Could not read translation status"):]
    assert "paintTranslateBadge" not in read_error[:160]


def test_language_change_cancels_the_old_warm_up_and_starts_one_new_one():
    body = _function("warmTranslation", "resetAudioScript")
    assert "cancelTranslationWarm();" in body
    assert "new AbortController()" in body
    assert "ensureTranslation(controller)" in body
    assert "state.translationWarm?." in body
    # The badge goes to Translating… immediately, before the first response.
    assert 'status: "running"' in body
    assert "paintTranslateBadge(state.translation);" in body
    handler = SCRIPT[SCRIPT.index('dom.audioLang.addEventListener(event'):]
    handler = handler[:handler.index("\n      });") + 9]
    assert handler.index("loadAudioScript();") < handler.index("warmTranslation();")


def test_story_cut_cannot_start_two_rewrites():
    click = SCRIPT[SCRIPT.index('dom.audioRewriteRun.addEventListener("click"'):]
    click = click[:click.index("\n    });") + 8]
    assert "if (state.scriptAbort) return;" in click
    assert "loadAudioScript({ run: true });" in click
    body = _function("loadAudioScript", "scriptHeadLabel")
    assert "if (state.scriptAbort) return;" in body
    assert "new AbortController()" in body
    assert "signal: controller.signal" in body


def test_a_setting_change_cancels_the_script_request_and_frees_the_button():
    cancel = _function("cancelAudioScript", "showScriptFailure")
    assert "state.scriptAbort.abort();" in cancel
    assert "state.scriptAbort = null;" in cancel
    assert "dom.audioRewriteRun.disabled = false" in cancel
    reset = _function("resetAudioScript", "cancelAudioScript")
    assert "cancelAudioScript();" in reset


def test_a_ready_memo_reaches_the_rewrite_without_a_translation_request():
    body = _function("ensureTranslation", "cancelTranslationWarm")
    ready = body.index("state.translation.status === \"ready\"")
    status = body.index("await translationStatus(")
    assert ready < status
    assert "paintTranslateBadge(state.translation);" in body[ready:status]
    assert "error.status === 409" in body
    assert 'paintTranslateBadge({ status: "failed", target });' in body


def test_translation_polling_also_aborts_on_a_setting_change():
    body = _function("ensureTranslation", "cancelTranslationWarm")
    assert "translationStatus(target, jobId, controller?.signal)" in body
    assert "controller?.signal.aborted" in body


def test_a_failure_keeps_the_last_good_script():
    body = _function("showScriptFailure", "loadAudioScript")
    assert "state.lastScript?.lines?.length" in body
    assert "renderScriptBlock(" in body
    assert "showing last good script." in body
    run = _function("loadAudioScript", "scriptHeadLabel")
    assert "showScriptFailure(" in run
    assert "if (!translatedReady) {" in run
