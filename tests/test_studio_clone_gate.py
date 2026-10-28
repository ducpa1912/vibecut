"""Phase B 3: Edit shows voice cloning only when voice_room is on."""

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


def run_module(module: str, body: str, prelude: str = NO_PAGE):
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


@needs_node
def test_voice_room_switch_reads_the_feature_list():
    out = run_module("edit/layers/audio.js", """
        return [
          m.voiceRoomOn({features: ["voice_room"]}),
          m.voiceRoomOn({features: []}),
          m.voiceRoomOn("voice_room other"),
          m.voiceRoomOn(undefined),
          m.voiceRoomOn(["other"]),
          m.voiceRoomOn({features: "other,voice_room"}),
        ];
    """)
    assert out == [True, False, True, False, False, True]


@needs_node
def test_no_argument_reader_uses_the_page_then_the_html_feature_string():
    page = (
        "globalThis.document = {readyState: 'complete', getElementById: () => null,"
        " addEventListener: () => {}, documentElement: {dataset: {features: 'voice_room'}}};\n"
        "globalThis.window = {addEventListener: () => {}, location: {hash: ''},"
        " VIBECUT_EDITION: {features: ['voice_room']}};\n"
    )
    off = page.replace("VIBECUT_EDITION: {features: ['voice_room']}",
                       "VIBECUT_EDITION: {features: []}")
    assert run_module("edit/layers/audio.js", "return m.voiceRoomOn();", prelude=page) is True
    assert run_module("edit/layers/audio.js", "return m.voiceRoomOn();", prelude=off) is False


def test_edit_gates_the_clone_block_behind_the_feature():
    audio = (STUDIO / "edit" / "layers" / "audio.js").read_text(encoding="utf-8")
    assert "if (engines && voiceRoomOn()) card.append(cloneBlock());" in audio
