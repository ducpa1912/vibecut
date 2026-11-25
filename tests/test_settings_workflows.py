"""Settings → Workflows and the plain speech failure (REQ-20261118-02 leftovers).

The local-only change left text, music and the silent-video script with no
ladder at all. An empty ladder is not a choice, so Settings draws one plain
line per workflow and never an empty list. The speech report says the failure
once; the engine's own words go to the log.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from duckcore.engine import detect, workflow_config

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "static" / "duck" / "app.js"


def test_speech_engine_empty_message_is_plain_and_keeps_the_language(caplog) -> None:
    detail = "whisper model not installed at /models/whisper"
    with caplog.at_level(logging.WARNING, logger="duckcore.engine.detect"):
        warnings = detect._report_warnings(
            [],
            audio={
                "has_audio": True,
                "speech_state": "engine_empty",
                "speech_error": detail,
                "speech_language": "vi",
            },
            quality={},
            text={"confirmed": True},
            attested=True,
            sampled_error=None,
            truncated=False,
            lock=False,
        )
    found = [item for item in warnings if item["code"] == "speech_engine_empty"]
    assert len(found) == 1
    message = found[0]["message"]
    assert "Engine:" not in message
    assert "vi" in message
    assert detail not in message
    assert "Retry speech on this video" in message
    assert "re-importing is not needed" in message
    assert "Setup → Engines" in message
    assert detail in caplog.text


def test_empty_workflow_ladders_stay_empty_in_this_build() -> None:
    # The note under each empty ladder is only true while the provider list is
    # empty. A loop that adds a local provider updates the note and this test.
    for name in ("story_brief", "rewrite", "translate", "hook_rank"):
        assert workflow_config.WORKFLOW_PROVIDERS[name] == ()
    assert workflow_config.WORKFLOW_PROVIDERS["script"] == ()
    assert workflow_config.WORKFLOW_PROVIDERS["music"] == ()


def _workflow_rows_source() -> str:
    js = APP.read_text(encoding="utf-8")
    match = re.search(r"\n\s*function workflowRows\(.*?\n\s*}\n", js, re.S)
    assert match, "workflowRows is gone; the Workflows test is stale"
    return match.group(0)


def test_workflows_draw_one_plain_line_and_never_an_empty_ladder(tmp_path: Path) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    helper = _workflow_rows_source()
    script = """
import assert from 'node:assert/strict';
""" + helper + """
const ready = workflowRows(
  { rewrite: { available: true }, speech: { default: 'whisper' } },
  { model_slots: { rewrite: { ready: false } } },
  3,
);
assert.equal(ready.length, 5);
for (const row of ready) {
  assert.deepEqual(Object.keys(row).sort(), ['id', 'label', 'note']);
}
const byId = Object.fromEntries(ready.map((row) => [row.id, row.note]));
assert.equal(byId.rewrite, 'On-device writer.');
assert.equal(byId.tts, 'On-device voices.');
assert.equal(byId.stt, 'On-device speech.');
assert.equal(byId.script, 'Not set up in this build.');
assert.match(byId.music, /No music generator/);
const joined = Object.values(byId).join(' ').toLowerCase();
for (const name of ['whisper', 'kokoro', 'lama', 'openai', 'gpt', 'claude', 'ctranslate2']) {
  assert.ok(!joined.includes(name), `the UI named ${name}`);
}

const off = workflowRows(
  { rewrite: { available: false, reason: 'appleIntelligenceNotEnabled' }, speech: {} },
  { model_slots: { rewrite: { ready: false } } },
  0,
);
const offById = Object.fromEntries(off.map((row) => [row.id, row.note]));
assert.equal(offById.rewrite, 'Apple Intelligence is off.');
assert.equal(offById.tts, 'No voices found.');
assert.equal(offById.stt, 'On-device speech is unavailable.');
console.log('ok');
"""
    path = tmp_path / "workflows.mjs"
    path.write_text(script, encoding="utf-8")
    result = subprocess.run(
        [node, str(path)], cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert result.stdout.strip() == "ok"


def test_settings_workflows_section_has_no_list_markup() -> None:
    js = APP.read_text(encoding="utf-8")
    assert "<h3>Workflows</h3>" in js
    assert "${workflowsMarkup()}" in js
    match = re.search(r"\n\s*function workflowsMarkup\(.*?\n\s*}\n", js, re.S)
    assert match, "workflowsMarkup is gone; the Workflows test is stale"
    body = match.group(0)
    for tag in ("<ul", "<ol", "<li", "<select"):
        assert tag not in body, f"an empty ladder was drawn with {tag}"
