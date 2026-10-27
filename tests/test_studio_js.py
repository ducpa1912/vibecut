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


def run_module(module: str, body: str):
    """Import ``static/studio/<module>`` as ``m``, run ``body``, return its JSON."""
    url = (STUDIO / module).as_uri()
    script = (
        f"const m = await import({json.dumps(url)});\n"
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
