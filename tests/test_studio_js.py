"""Pure Studio ES-module helpers, run under Node when it is installed.

Studio is a no-build vanilla UI, so these tests import the shipped modules
directly. Only side-effect-free exports are exercised; nothing touches the DOM.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STUDIO = Path(__file__).resolve().parents[1] / "static" / "studio"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(not NODE, reason="node is not installed")


# shell.js boots Studio on import; a page with no #studio-root is a no-op.
NO_PAGE = (
    "globalThis.document = {readyState: 'complete', getElementById: () => null,"
    " addEventListener: () => {}, documentElement: {dataset: {}}};\n"
    "globalThis.window = {addEventListener: () => {}, location: {hash: ''}};\n"
)


def run_module(module: str, body: str, prelude: str = ""):
    """Import ``static/studio/<module>`` as ``m``, run ``body``, return its JSON."""
    url = (STUDIO / module).as_uri()
    script = (
        prelude
        + f"const m = await import({json.dumps(url)});\n"
        f"const out = await (async () => {{ {body} }})();\n"
        "process.stdout.write(JSON.stringify(out));\n"
    )
    result = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout or "null")


# ---------------------------------------------------------------- api.js (QA #4)


@needs_node
def test_error_detail_reads_structured_detail_message():
    out = run_module("api.js", """
        return [
          m.errorDetail({detail: {code: "story_id_invalid",
            message: "story_id must be a short non-empty string.",
            suggestion: "Use the story this packet belongs to."}}),
          m.errorDetail({detail: {code: "titles_invalid"}}),
          m.errorDetail({detail: "Plain text."}),
          m.errorDetail({detail: [{loc: ["body", "count"], msg: "too big"}]}),
        ];
    """)
    assert out == [
        "story_id must be a short non-empty string. Use the story this packet belongs to.",
        "titles invalid",
        "Plain text.",
        "count: too big",
    ]


# ---------------------------------------------------------------- shell.js (QA #10)


@needs_node
def test_reading_action_cancels_a_read_and_restarts_a_stopped_one():
    out = run_module("shell.js", """
        return ["queued", "reading", "scoring", "cancelled", "interrupted", "failed", "ready"]
          .map((status) => m.readingAction(status));
    """, prelude=NO_PAGE)
    kinds = [row["kind"] if row else None for row in out]
    assert kinds == ["cancel", "cancel", "cancel", "retry", "retry", "retry", None]


# ---------------------------------------------------------------- edit/overlay.js (QA #6)


@needs_node
def test_overlay_draws_active_text_fx_and_caption_cue():
    out = run_module("edit/overlay.js", """
        const edit = {
          graphics: [
            {id: "t1", type: "text", kind: "hook", text: "Hook", start: 0, end: 3,
             anchor: "top-center", box: {w: 0.76, h: 0.16}, style: {size: 64}},
            {id: "t2", type: "text", kind: "title", text: "Later", start: 5, end: 6},
            {id: "p1", type: "fx", kind: "progress_bar", start: 0, end: 4,
             anchor: "bottom-center", box: {w: 0.9, h: 0.01}},
          ],
          captions: {track_id: "cap1", enabled: true},
        };
        const captions = {id: "cap1", style: {font_size: 72, color: "#ffd400",
          stroke_width: 4, stroke_color: "#111111", position: "bottom"},
          cues: [{start: 0.5, end: 1.5, text: "FIRST\\nLINE"}, {start: 1.5, end: 2.5, text: "NEXT"}]};
        const at1 = m.overlayLayers(edit, captions, 1.0);
        const off = m.overlayLayers({...edit, captions: {track_id: "cap1", enabled: false}}, captions, 1.0);
        return {at1: at1.map((row) => [row.type, row.kind, row.text || null]),
          fraction: at1.find((row) => row.kind === "progress_bar").fraction,
          caption: at1.find((row) => row.kind === "caption"),
          off: off.map((row) => row.kind),
          late: m.overlayLayers(edit, captions, 5.5).map((row) => row.text)};
    """)
    assert out["at1"] == [
        ["text", "hook", "Hook"], ["fx", "progress_bar", None], ["text", "caption", "FIRST\nLINE"],
    ]
    assert out["fraction"] == 0.25
    caption = out["caption"]
    assert caption["style"]["size"] == 72 and caption["style"]["color"] == "#ffd400"
    assert caption["style"]["stroke"] == "#111111"
    # Bottom-center caption box above the 8% bottom margin, like the server.
    assert caption["rect"] == {"x": 0.12, "y": 0.8, "w": 0.76, "h": 0.12}
    assert out["off"] == ["hook", "progress_bar"]
    assert out["late"] == ["Later"]


@needs_node
def test_overlay_wrap_keeps_line_breaks_like_the_renderer():
    out = run_module("edit/overlay.js", """
        const measure = (value) => value.length * 10;
        return [m.wrapText(measure, "ONE TWO THREE\\nFOUR", 75),
                m.wrapText(measure, "ABCDEFGHIJ", 40)];
    """)
    assert out == [["ONE TWO", "THREE", "FOUR"], ["ABCD", "EFGH", "IJ"]]


# ---------------------------------------------------------------- finish.js (QA #5)


@needs_node
def test_finish_banner_counts_failures():
    out = run_module("finish.js", """
        const queues = [{id: "q1", items: [
          {state: "done", artifact_id: "a1"}, {state: "failed", artifact_id: "a2"},
        ]}, {id: "q2", items: [{state: "failed"}]}];
        const artifacts = [{artifact_id: "a1", status: "ready"},
          {artifact_id: "a3", status: "failed"}];
        const outcome = m.finishOutcome(queues, ["q1"], artifacts, ["a1", "a3"]);
        return [outcome, m.finishBanner(outcome), m.finishBanner({done: 2}),
          m.finishBanner({failed: 1})];
    """)
    assert out[0] == {"done": 1, "failed": 2}
    assert out[1]["tone"] == "bad" and "1 of 3" in out[1]["text"]
    assert out[2] == {"text": "2 renders finished. New versions are ready.", "tone": "ok"}
    assert out[3]["tone"] == "bad" and out[3]["text"].startswith("The render failed.")


@needs_node
def test_apply_summary_reports_what_changed_and_what_was_skipped():
    """Apply to all must not claim success for stories it left alone (QA #7)."""
    out = run_module("finish.js", """
        return [
          m.applySummary([
            {name: "02", changed: ["captions", "colour"], skipped: [], error: ""},
            {name: "03", changed: ["colour"], skipped: [{field: "captions", reason: "no speech to caption"}], error: ""},
            {name: "04", changed: [], skipped: [], error: "Conflict"},
          ]),
          m.applySummary([{name: "02", changed: [], skipped: [], error: ""}]),
        ];
    """)
    assert out[0]["text"] == (
        "Updated 2 stories (captions on 1, colour on 2). "
        "Skipped 03: captions, no speech to caption. "
        "1 could not be updated: 04: Conflict"
    )
    assert out[0]["tone"] == "bad"
    assert out[1] == {"text": "No story changed.", "tone": ""}


@needs_node
def test_failure_reason_and_download_name():
    out = run_module("finish.js", """
        return [
          m.failureReason({error: "can't measure length of multiline text\\nTraceback"}),
          m.failureReason({message: "Render failed."}),
          m.failureReason({message: "Source missing"}),
          m.downloadName({aspect: "4:5", versions: {version: 2}}, 0),
          m.downloadName({spec: {aspect: "9:16"}, quality: "draft"}, 11),
        ];
    """)
    assert out == [
        "can't measure length of multiline text",
        "No reason was recorded.",
        "Source missing",
        "story-01-4x5-v2.mp4",
        "story-12-9x16-draft.mp4",
    ]
