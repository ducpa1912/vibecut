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


# ---------------------------------------------------------------- stories.js (QA #13)


@needs_node
def test_story_length_presets_match_the_server():
    import clipset

    out = run_module("stories.js", """
        return {presets: m.LENGTH_PRESETS,
          picked: [m.lengthPreset({min_s: 15, max_s: 30}), m.lengthPreset({min_s: 20, max_s: 75}),
                   m.lengthPreset(null)]};
    """)
    for name, (low, high) in clipset.LENGTH_PRESETS.items():
        assert (out["presets"][name]["min"], out["presets"][name]["max"]) == (low, high)
    auto = out["presets"]["auto"]
    assert (auto["min"], auto["max"]) == (clipset.MIN_STORY_S, clipset.MAX_STORY_S)
    assert out["picked"] == ["short", "auto", "auto"]


@needs_node
def test_adjust_sentences_moves_one_edge_by_one_sentence():
    """Story cards' ± start/end controls (QA #14)."""
    out = run_module("stories.js", """
        const ids = [{id: 5}, {id: 6}, {id: 7}];
        return [m.adjustSentences(ids, "start", -1), m.adjustSentences(ids, "start", 1),
          m.adjustSentences(ids, "end", 1), m.adjustSentences(ids, "end", -1),
          m.adjustSentences([{id: 0}], "start", -1), m.adjustSentences([3], "end", -1)];
    """)
    assert out == [[4, 5, 6, 7], [6, 7], [5, 6, 7, 8], [5, 6], None, None]


@needs_node
def test_check_samples_short_sources_at_one_fps():
    """QA #15: 0.5 fps missed short word-pop captions."""
    out = run_module("check.js", "return [m.checkFps(53), m.checkFps(600), m.checkFps(1442), m.checkFps(0)];")
    assert out == [1, 1, 0.5, 0.5]


@needs_node
def test_idle_watcher_polls_status_only():
    """QA #21: an idle ready video re-reads status, not check and clip-sets."""
    out = run_module("shell.js", """
        const ready = {jobId: "j1", loaded: true, status: "ready", check: "done"};
        return [
          m.canReuseSteps(ready, "j1", "ready", true),
          m.canReuseSteps(ready, "j1", "ready", false),
          m.canReuseSteps({...ready, check: "running"}, "j1", "ready", true),
          m.canReuseSteps({...ready, status: "reading"}, "j1", "ready", true),
          m.canReuseSteps(ready, "j2", "ready", true),
        ];
    """, prelude=NO_PAGE)
    assert out == [True, False, False, False, False]


@needs_node
def test_reload_resumes_at_the_best_step():
    """QA #24: a reload with a video open no longer always lands on Import."""
    out = run_module("shell.js", """
        return [
          m.bestStepFor(false, {}),
          m.bestStepFor(true, {status: "reading"}),
          m.bestStepFor(true, {status: "cancelled"}),
          m.bestStepFor(true, {status: "ready", sourceMissing: "gone"}),
          m.bestStepFor(true, {status: "ready", check: "none", stories: 0}),
          m.bestStepFor(true, {status: "ready", check: "done", stories: 0}),
          m.bestStepFor(true, {status: "ready", check: "done", stories: 3}),
        ];
    """, prelude=NO_PAGE)
    assert out == ["import", "import", "import", "import", "moments", "moments", "edit"]


@needs_node
def test_import_knows_when_a_video_is_still_reading():
    out = run_module("import.js", """
        return ["queued", "downloading", "reading", "ready", "failed", "cancelled"].map(m.isReadingStatus);
    """)
    assert out == [True, True, True, False, False, False]


# ---------------------------------------------------------------- edit/model.js (QA #20)


@needs_node
def test_hook_card_starts_at_zero_with_the_story_hook_in_bold():
    import overlays

    out = run_module("edit/model.js", """
        const hook = m.newTextLayer("hook", {duration: 30, playhead: 14.5,
          hookText: "During an open AI cyber security test, AI agents found ways around their controls."});
        const title = m.newTextLayer("title", {duration: 30, playhead: 14.5});
        const empty = m.newTextLayer("hook", {duration: 30, playhead: 4});
        return {hook, title, empty};
    """)
    hook = out["hook"]
    assert hook["start"] == 0 and hook["end"] == 3
    assert hook["text"].startswith("During an open AI cyber security test") and hook["text"].endswith("…")
    assert len(hook["text"]) <= 61
    assert hook["style"]["weight"] == 900 and hook["style"]["background"] == "#000000b3"
    assert out["title"]["start"] == 14.5
    assert out["empty"]["text"] == "Your hook" and out["empty"]["start"] == 0
    # The server accepts the default hook style as is.
    overlays.edit_text_layer({k: hook[k] for k in ("kind", "text", "start", "end", "style")})


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
    assert caption["style"]["stroke_width"] == 4 and caption["style"]["weight"] == 700
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
def test_edit_history_lists_only_the_current_chain():
    """QA #19: folded autosaves leave sidecars that are not history."""
    out = run_module("finish.js", """
        const rows = [{id: "a", version: 1, parent: null}, {id: "b", version: 2, parent: "a"},
          {id: "c", version: 2, parent: "a"}, {id: "d", version: 3, parent: "c"}];
        return [m.editChain(rows, "d").map((row) => row.id), m.editChain(rows, "zz").length];
    """)
    assert out == [["d", "c", "a"], 4]


@needs_node
def test_queue_item_progress_text():
    """QA #18: a running item shows its % and time left."""
    out = run_module("finish.js", """
        return [m.itemProgressText({progress: 0.42, eta: 80}), m.itemProgressText({progress: 0.1}),
                m.etaText(45), m.etaText(120), m.etaText(1000), m.etaText(3780)];
    """)
    assert out == ["42% · about 1 min 20 s left", "10%", "45 s", "2 min", "17 min", "1 h 3 min"]


@needs_node
def test_preflight_failures_say_why():
    """QA #17: a 404 means "render first", other errors keep their reason."""
    out = run_module("finish.js", """
        return [m.checksFailedNote({status: 404}), m.checksFailedNote({status: 500, message: "Boom"}),
                m.checksFailedNote(null)];
    """)
    assert out[0] == "Render this story first; checks run on the render."
    assert out[1] == "Checks could not run for this story: Boom"
    assert out[2].endswith("Try Check again.")


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


# ---------------------------------------------------------------- Phase B 1b


@needs_node
def test_import_reading_line_carries_the_server_eta():
    out = run_module("import.js", """
        return [
          m.readingLine({progress: 0.462, message: "Reading frames · about 2 min left"}),
          m.readingLine({progress: 0, message: ""}),
        ];
    """)
    assert out == [
        {"percent": 46, "text": "Reading the video · 46% · Reading frames · about 2 min left"},
        {"percent": 0, "text": "Reading the video · 0%"},
    ]


@needs_node
def test_import_upload_line_estimates_time_left():
    out = run_module("import.js", """
        return [m.uploadLine(0.01, 5), m.uploadLine(0.5, 1), m.uploadLine(0.25, 10),
                m.uploadLine(0.1, 30), m.uploadLine(1, 40)];
    """)
    assert out == [
        "1% · estimating",
        "50% · estimating",
        "25% · about 30 s left",
        "10% · about 5 min left",
        "100% · reading starts next",
    ]


@needs_node
def test_cancelled_check_reads_as_not_run_in_the_rail():
    out = run_module("shell.js", """
        return [
          m.checkState({status: "cancelled", complete: false}),
          m.checkState({status: "running", complete: false}),
          m.checkState({status: "failed", complete: false}),
          m.checkState({status: "ready", complete: true}),
        ];
    """, prelude=NO_PAGE)
    assert out == ["none", "running", "failed", "done"]


def test_check_and_import_show_cancel_controls():
    check = (STUDIO / "check.js").read_text(encoding="utf-8")
    assert "/check/cancel" in check and "Cancel Check" in check
    assert '"Check was cancelled"' in check
    page = (STUDIO / "import.js").read_text(encoding="utf-8")
    assert "/reading/cancel" in page and "st-reading-cancel" in page
    assert "Cancel upload" in page and "signal: upload.signal" in page
