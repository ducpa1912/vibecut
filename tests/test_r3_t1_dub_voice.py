"""R3 T1: Dub target/source, editable script, and queue failure reasons.

The Studio helpers run under Node when it is installed; the rest is pure
Python. Nothing here renders, calls a model, or touches the network.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

import audio
import edits
import story_queue as sq

STUDIO = Path(__file__).resolve().parents[1] / "static" / "studio"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(not NODE, reason="node is not installed")

STORY_REF = {
    "set_id": "cs_r3",
    "story_id": "st_r3",
    "clip_hash": "46d92491cfb1bbd7",
    "title": "R3 story",
    "duration": 10.0,
    "clip_count": 2,
}

NO_PAGE = (
    "globalThis.document = {readyState: 'complete', getElementById: () => null,"
    " addEventListener: () => {}, documentElement: {dataset: {}}};\n"
    "globalThis.window = {addEventListener: () => {}, location: {hash: ''}};\n"
)


def run_module(module: str, body: str, prelude: str = NO_PAGE):
    """Import a shipped Studio ES module as ``m`` and return its JSON output."""
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


# ---------------------------------------------------------------- Studio plan


@needs_node
def test_build_plan_writes_dub_source_target_and_script_only_when_present():
    out = run_module("edit/layers/audio.js", """
        const dub = m.buildAudioPlan({
          mode: "dub",
          duck_db: -18,
          loudness: {lufs: -15, true_peak: -2},
          voice: {engine: "say", voice: "Karen", rate: 1},
          translate: {source: "en", target: "es", mode: "smooth"},
          scriptOverrides: {4: "Hola.", 5: "   "},
        });
        const plain = m.buildAudioPlan({mode: "original"});
        const voice = m.buildAudioPlan({mode: "voice_over", translate: null, scriptOverrides: null});
        return {dub, plain, voice};
    """)
    dub = out["dub"]
    assert dub["mode"] == "dub"
    assert dub["duck_db"] == -18
    assert dub["loudness"] == {"lufs": -15, "true_peak": -2}
    assert dub["translate"] == {"source": "en", "target": "es", "mode": "smooth"}
    assert dub["script_overrides"] == {"4": "Hola."}
    assert dub["voice"] == {"engine": "say", "voice": "Karen", "rate": 1}
    assert "translate" not in out["plain"] and "script_overrides" not in out["plain"]
    assert out["voice"]["mode"] == "voice_over"
    assert "translate" not in out["voice"] and "script_overrides" not in out["voice"]


@needs_node
def test_translate_merge_keeps_a_saved_style_and_only_applies_to_dub():
    out = run_module("edit/layers/audio.js", """
        return [
          m.mergeTranslatePlan("dub", {mode: "viral", target: "fr"}, "en", "es", ""),
          m.mergeTranslatePlan("voice_over", {mode: "viral"}, "en", "es"),
          m.mergeTranslatePlan("dub", null, "zh", "en", "literal"),
        ];
    """)
    assert out[0] == {"mode": "viral", "source": "en", "target": "es"}
    assert out[1] is None
    assert out[2] == {"source": "zh", "target": "en", "mode": "literal"}


@needs_node
def test_script_lines_follow_clips_and_recover_scene_keys_from_sentences():
    out = run_module("edit/layers/audio.js", """
        const story = {
          sentences: [
            {id: 7, text: "First source line.", scene: 11},
            {id: 8, text: "Second source line.", scenes: [12]},
            {id: 9, text: "No scene sentence."},
          ],
          clips: [
            {dur: 3, why: "Sentence 7: First source line.", role: "hook"},
            {scene: 12, dur: 2, why: "Sentence 8: Second source line.", role: "payoff"},
          ],
        };
        const fallback = {
          sentences: [
            {id: 1, text: "Only sentence.", scene: 3},
          ],
          clips: [],
        };
        return {
          rows: m.storyScriptLines(story),
          fallback: m.storyScriptLines(fallback),
          empty: m.storyScriptLines({}),
        };
    """)
    assert out["rows"] == [
        {"key": "11", "scene": 11, "text": "First source line.", "role": "hook"},
        {"key": "12", "scene": 12, "text": "Second source line.", "role": "payoff"},
    ]
    assert out["fallback"] == [
        {"key": "3", "scene": 3, "text": "Only sentence.", "role": "hook"},
    ]
    assert out["empty"] == []


@needs_node
def test_script_overrides_trim_blanks_and_enforce_the_backend_limits():
    out = run_module("edit/layers/audio.js", """
        return m.cleanScriptOverrides({
          3: "  Hello there.  ",
          4: "   ",
          5: "x".repeat(700),
          "": "ignored",
        });
    """)
    assert out == {"3": "Hello there.", "5": "x" * 600}


@needs_node
def test_dub_blocks_without_a_target_and_accepts_one():
    out = run_module("edit/layers/audio.js", """
        return [
          m.dubBlockReason("dub", ""),
          m.dubBlockReason("dub", "es"),
          m.dubBlockReason("voice_over", ""),
        ];
    """)
    assert "target language" in out[0]
    assert out[1] == ""
    assert out[2] == ""


@needs_node
def test_story_language_detection_prefers_scripts_over_latin():
    out = run_module("edit/layers/audio.js", """
        return [
          m.detectStoryLanguage({sentences: [{text: "你好世界，今天很好。"}]}),
          m.detectStoryLanguage({sentences: [{text: "こんにちは、元気ですか。"}]}),
          m.detectStoryLanguage({sentences: [{text: "안녕하세요 반갑습니다."}]}),
          m.detectStoryLanguage({sentences: [{text: "A normal English line."}]}),
        ];
    """)
    assert out == ["zh", "ja", "ko", "en"]


# ---------------------------------------------------------------- Edit schema


def test_edit_keeps_translate_source_and_script_overrides_into_the_audio_plan():
    edit = edits.build_edit(
        story_ref=STORY_REF,
        aspect="9:16",
        audio={
            "mode": "dub",
            "voice": {"engine": "say", "voice": "Tingting"},
            "translate": {"source": "en", "target": "zh", "mode": "smooth"},
            "script_overrides": {"11": "你好。", "12": "   "},
        },
    )
    assert edit["audio"]["translate"] == {
        "source": "en", "target": "zh", "mode": "smooth",
    }
    assert edit["audio"]["script_overrides"] == {"11": "你好。"}
    plan = audio.plan_from_edit(edit["audio"])
    assert plan["translate"]["source"] == "en"
    assert plan["translate"]["target"] == "zh"
    assert plan["script_overrides"] == {"11": "你好。"}
    assert edits.normalize_edit(edit)["hash"] == edit["hash"]


def test_edits_without_the_new_fields_hash_exactly_as_before():
    base = edits.build_edit(story_ref=STORY_REF, aspect="9:16", audio={"mode": "dub"})
    explicit = edits.build_edit(
        story_ref=STORY_REF,
        aspect="9:16",
        audio={"mode": "dub", "translate": None, "script_overrides": None},
    )
    empty = edits.build_edit(
        story_ref=STORY_REF,
        aspect="9:16",
        audio={"mode": "dub", "translate": None, "script_overrides": {}},
    )
    assert base["hash"] == explicit["hash"] == empty["hash"]
    assert "translate" not in base["audio"]
    assert "script_overrides" not in base["audio"]


def test_edit_rejects_bad_translate_source_and_too_long_script_lines():
    with pytest.raises(edits.EditError):
        edits.build_edit(
            story_ref=STORY_REF,
            aspect="9:16",
            audio={"mode": "dub", "translate": {"source": "not a language", "target": "zh"}},
        )
    with pytest.raises(edits.EditError):
        edits.build_edit(
            story_ref=STORY_REF,
            aspect="9:16",
            audio={"mode": "voice_over", "script_overrides": {"3": "x" * 601}},
        )


def test_dub_refusal_names_the_missing_target_and_the_fix(tmp_path):
    with pytest.raises(audio.AudioError) as caught:
        audio.build_bed(
            "source.mp4", {}, {}, [], [], tmp_path,
            {"mode": "dub"}, 3.0, tmp_path / "tmp",
            lambda *args: None,
        )
    message = str(caught.value)
    assert "target language" in message
    assert "Edit > Audio > Dub" in message
    assert "choose a target" in message


# ---------------------------------------------------------------- Queue reason


class FailedBackend:
    """Every render fails; ``error`` is optional like a real old backend."""

    def __init__(self, message: str | None = None, raises: bool = False):
        self.message = message
        self.raises = raises

    def start(self, item: dict) -> str:
        return f"art_{item['story_id']}"

    def status(self, item: dict, artifact_id: str) -> str:
        return "failed"

    def cancel(self, item: dict, artifact_id: str) -> None:
        return None

    def timeout_for(self, item: dict) -> float:
        return 5.0

    def error(self, item: dict, artifact_id: str) -> str | None:
        if self.raises:
            raise RuntimeError("manifest unreadable")
        return self.message


def _queued(tmp_path, backend):
    manager = sq.StoryQueueManager(tmp_path, backend, poll_interval=0.01)
    queue = manager.create([{
        "job_id": "job1", "set_id": "set1", "story_id": "s1", "aspect": "9:16",
    }])
    assert manager.wait(queue["id"], timeout=5)
    return manager.get(queue["id"])["items"][0]


def test_queue_shows_the_backend_reason_instead_of_render_failed(tmp_path):
    item = _queued(
        tmp_path,
        FailedBackend("Dub needs a target language. Choose a target in Edit."),
    )
    assert item["state"] == "failed"
    assert item["error"] == "Dub needs a target language. Choose a target in Edit."


def test_queue_falls_back_for_old_backends_and_broken_hooks(tmp_path):
    class OldBackend:
        def start(self, item):
            return "art_old"

        def status(self, item, artifact_id):
            return "failed"

        def cancel(self, item, artifact_id):
            return None

        def timeout_for(self, item):
            return 5.0

    old = sq.StoryQueueManager(tmp_path / "old", OldBackend(), poll_interval=0.01)
    queue = old.create([{"job_id": "j", "set_id": "s", "story_id": "old"}])
    assert old.wait(queue["id"], timeout=5)
    assert old.get(queue["id"])["items"][0]["error"] == "Render failed."

    broken = _queued(tmp_path / "broken", FailedBackend(raises=True))
    assert broken["error"] == "Render failed."

    blank = _queued(tmp_path / "blank", FailedBackend("   "))
    assert blank["error"] == "Render failed."
