"""Voice Room runs on its own copy of the shared backend.

Studio is moving its shared code into ``features/`` and ``core/`` on its own
branch. These tests fail on an unmarked change to a copy, on a module that runs
here unpinned, and on any reach into Studio's layout or another worktree.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


def _pin():
    spec = importlib.util.spec_from_file_location(
        "voice_runtime_pin", ROOT / "scripts" / "voice_runtime_pin.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


pin = _pin()


def test_every_copy_matches_the_manifest_and_every_module_is_pinned():
    found = pin.problems(pin.load())
    assert not found, "Resync the copy or bump its version:\n" + "\n".join(found)


def test_the_named_shared_modules_are_pinned():
    pinned = {entry["path"] for entry in pin.load()["copies"]}
    for name in (
        "audio.py", "tts.py", "stt.py", "music.py", "pipeline.py",
        "settings_store.py", "job_queue.py", "workflow_config.py",
        "voice_clone.py", "voice_extract.py", "rights.py", "editions.py",
        "packs.py", "scripts/lane-env.sh", "scripts/ship-lane.sh",
    ):
        assert name in pinned


def test_an_unmarked_change_is_caught(tmp_path, monkeypatch):
    copy = tmp_path / "shared.py"
    copy.write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.setattr(pin, "ROOT", tmp_path)
    monkeypatch.setattr(pin, "ENTRY_POINTS", ("shared.py",))
    manifest = {"copies": [pin._entry("shared.py", "base")]}
    assert pin.problems(manifest) == []

    copy.write_text("VALUE = 2\n", encoding="utf-8")
    found = pin.problems(manifest)
    assert len(found) == 1 and "changed without a mark" in found[0]

    monkeypatch.setattr(pin, "_head", lambda: "abc1234")
    pin.mark(manifest, "shared.py", "Port a fix")
    assert pin.problems(manifest) == []
    assert manifest["copies"][0]["lane_version"] == "1.0.1"
    assert manifest["copies"][0]["changes"][0]["note"] == "Port a fix"


def test_a_new_unpinned_module_is_caught(tmp_path, monkeypatch):
    (tmp_path / "shared.py").write_text("def later():\n    import extra\n", encoding="utf-8")
    (tmp_path / "extra.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(pin, "ROOT", tmp_path)
    monkeypatch.setattr(pin, "ENTRY_POINTS", ("shared.py",))
    manifest = {"copies": [pin._entry("shared.py", "base")]}
    assert any("extra.py: runs in this lane" in line for line in pin.problems(manifest))


def test_the_walk_sees_everything_the_server_really_loads():
    probe = (
        "import sys; from pathlib import Path; import app; root = Path.cwd(); "
        "print('\\n'.join(sorted({Path(m.__file__).resolve().relative_to(root).as_posix() "
        "for m in list(sys.modules.values()) if getattr(m, '__file__', None) "
        "and Path(m.__file__).resolve().is_relative_to(root)})))"
    )
    env = {**os.environ, "VIBECUT_EDITION": "voice", "VIBECUT_FEATURES": "voice_room"}
    output = subprocess.check_output([sys.executable, "-c", probe], cwd=ROOT, env=env, text=True)
    loaded = set(output.split())
    assert "routes_voice_clone.py" in loaded
    assert loaded <= pin.runtime_modules() | pin.OWNED_MODULES


def test_nothing_reaches_into_studios_layout():
    assert not (ROOT / "features").exists()
    assert not (ROOT / "core").exists()
    for relative in sorted(pin.runtime_modules() | pin.OWNED_MODULES):
        tree = ast.parse((ROOT / relative).read_bytes(), filename=relative)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                assert name.split(".")[0] not in {"features", "core"}, f"{relative}: {name}"


def test_no_runtime_file_names_another_worktree():
    scripts = [
        "scripts/lane-env.sh", "scripts/ship-lane.sh", "scripts/voice-serve.sh",
        "scripts/voice-record.sh", "scripts/Voice Room Server.command",
        "scripts/Record Voice Room.command",
    ]
    for relative in sorted(pin.runtime_modules() | pin.OWNED_MODULES) + scripts:
        text = (ROOT / relative).read_text(encoding="utf-8")
        for other in ("vibecut-studio", "vibecut-classic", "drop_eval/vibecut"):
            assert other not in text, f"{relative} names {other}"


@pytest.mark.parametrize("path", ["/", "/voices"])
def test_voices_page_runs_with_the_lane_settings(monkeypatch, path):
    monkeypatch.setenv("VIBECUT_EDITION", "voice")
    monkeypatch.setenv("VIBECUT_FEATURES", "voice_room")
    import app

    reply = TestClient(app.app).get(path)
    assert reply.status_code == 200
    assert "/static/voice/next.js" in reply.text


def test_lane_env_names_only_the_voice_lane():
    output = subprocess.check_output(
        ["bash", str(ROOT / "scripts" / "lane-env.sh"), "voice"],
        env={"HOME": "/home/founder", "PATH": "/usr/bin:/bin"}, text=True,
    )
    assert "VIBECUT_PORT=8797" in output
    assert "VIBECUT_DATA=/home/founder/vibecut-lanes/voice" in output
    assert "VIBECUT_FEATURES=voice_room" in output
    assert "VIBECUT_EDITION=voice" in output
