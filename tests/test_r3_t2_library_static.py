"""Static contracts for the R3 T2 finished/sources library (library.js + shell.js)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STUDIO = Path(__file__).resolve().parents[1] / "static" / "studio"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(not NODE, reason="node is not installed")

NO_PAGE = (
    "globalThis.document = {readyState: 'complete', getElementById: () => null,"
    " addEventListener: () => {}, documentElement: {dataset: {}}};\n"
    "globalThis.window = {addEventListener: () => {}, location: {hash: ''}};\n"
)


def run_module(module: str, body: str):
    url = (STUDIO / module).as_uri()
    script = (
        NO_PAGE
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


@needs_node
def test_source_title_prefers_job_and_story_over_source_mp4():
    out = run_module("library.js", """
        return [
          m.sourceTitle({name: "source.mp4", story_titles: ["JOYLO AV1 talking head"]}),
          m.sourceTitle({name: "source.mp4", title: "rednote garden",
            story_titles: ["红笔记花园"]}),
          m.sourceTitle({name: "source.mp4", id: "7610134fee5e", created: 1793186105}),
          m.sourceTitle({name: "episode-12.mp4", id: "job1"}),
        ];
    """)
    assert out[0] == "JOYLO AV1 talking head"
    assert out[1] == "rednote garden"
    assert "source.mp4" not in out[2]
    assert "4fee5e" in out[2]
    assert out[3] == "episode-12"


@needs_node
def test_artifact_meta_omits_missing_old_fields():
    out = run_module("library.js", """
        return [
          m.artifactMeta({aspect: "9:16", quality: "final", version: 2,
            created: 1793186105, size: 1048576}),
          m.artifactMeta({artifact_id: "art_x"}),
          m.artifactTitle({story_title: "Pricing"}, 0),
          m.artifactTitle({job_title: "JOYLO"}, 0),
          m.downloadFileName({aspect: "4:5", version: 2}, 0),
        ];
    """)
    assert out[0][0] == "9:16" and out[0][1] == "Final"
    assert out[0][2] == "v2"
    assert out[0][-1] == "1.0 MB"
    assert out[1] == []
    assert out[2] == "Pricing"
    assert out[3] == "JOYLO"
    assert out[4] == "story-01-4x5-v2.mp4"


@needs_node
def test_artifacts_path_and_tab_contract():
    out = run_module("library.js", """
        return {
          path: m.artifactsPath({query: "red note", limit: 25, offset: 5}),
          tabs: [m.FINISHED_TAB, m.SOURCES_TAB],
          root: m.ARTIFACTS_PATH,
        };
    """)
    assert out["root"] == "/api/artifacts"
    assert out["tabs"] == ["finished", "sources"]
    assert out["path"].startswith("/api/artifacts?")
    assert "q=red+note" in out["path"]
    assert "limit=25" in out["path"] and "offset=5" in out["path"]


def test_library_module_has_finished_sources_tabs_and_actions():
    text = (STUDIO / "library.js").read_text(encoding="utf-8")
    for needle in (
        'data-library-tab="finished"',
        'data-library-tab="sources"',
        ">Finished</button>",
        ">Sources</button>",
        "Open in Finish",
        "Download",
        "Play",
        "GET /api/artifacts",
        "ARTIFACTS_PATH = \"/api/artifacts\"",
    ):
        assert needle in text, needle


def test_shell_mounts_the_single_library_and_removes_the_old_picker():
    shell = (STUDIO / "shell.js").read_text(encoding="utf-8")
    assert 'import { mount as mountLibrary } from "./library.js";' in shell
    assert 'id="st-library-host"' in shell
    assert "mountLibrary(dom.libraryHost, ctx)" in shell
    assert "libraryUi?.refresh()" in shell
    assert "openFinished:" in shell
    # The old source-only row/list code is gone; there is no second library.
    assert "function libraryRow(" not in shell
    assert "function loadLibrary(" not in shell
    assert "st-library-list" not in shell
