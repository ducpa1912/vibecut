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
