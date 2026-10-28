"""Phase B 1d: Open in Finish lands on the cut's story and shape."""

from __future__ import annotations

import artifacts
from test_r3_t2_library import add_artifact, library, make_job  # noqa: F401
from test_r3_t2_library_static import STUDIO, needs_node, run_module


def test_library_rows_carry_the_clip_set(library):
    job = make_job(library.jobs, "job1", stories={"s2": "Second"})
    manifest = add_artifact(job, story_id="s2", aspect="4:5")
    manifest["set_id"] = "setB"
    artifacts.save_manifest(job, manifest)
    row = library.get("/api/artifacts").json()["artifacts"][0]
    assert (row["set_id"], row["story_id"], row["aspect"]) == ("setB", "s2", "4:5")


@needs_node
def test_focus_from_a_library_row():
    out = run_module("shell.js", """
        return m.finishFocusFrom({job_id: "j1", set_id: "setB", story_id: "s2",
                                  shape: "4:5", artifact_id: "a1"});
    """)
    assert out == {"jobId": "j1", "setId": "setB", "storyId": "s2", "aspect": "4:5", "artifactId": "a1"}


@needs_node
def test_finish_focus_pick_keeps_only_what_still_exists():
    out = run_module("finish.js", """
        const sets = [
          {id: "setA", stories: [{id: "s1"}]},
          {id: "setB", stories: [{id: "s2"}, {id: "s3"}]},
        ];
        return [
          m.finishFocusPick({setId: "setB", storyId: "s3", aspect: "4:5", artifactId: "a1"}, sets),
          m.finishFocusPick({setId: "", storyId: "s2", aspect: "9:16"}, sets),
          m.finishFocusPick({setId: "setA", storyId: "gone", aspect: "1:1"}, sets),
          m.finishFocusPick(null, sets),
        ];
    """)
    assert out == [
        {"setId": "setB", "storyId": "s3", "aspect": "4:5", "artifactId": "a1"},
        {"setId": "setB", "storyId": "s2", "aspect": "9:16", "artifactId": ""},
        {"setId": "setA", "storyId": "", "aspect": "", "artifactId": ""},
        None,
    ]


def test_shell_hands_the_focus_to_finish_once():
    shell = (STUDIO / "shell.js").read_text(encoding="utf-8")
    assert "finishFocus = finishFocusFrom(artifact);" in shell
    assert "takeFinishFocus: (jobId) =>" in shell
    finish = (STUDIO / "finish.js").read_text(encoding="utf-8")
    assert "ctx.takeFinishFocus?.(ctx.getJobId())" in finish
    assert "finishFocusPick(focus, sets)" in finish
