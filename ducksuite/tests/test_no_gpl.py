from pathlib import Path
import subprocess

import pytest

from duckcore import packs, voice


SCAN = Path(__file__).resolve().parents[1] / "scripts/scan-bundle-gpl.sh"


@pytest.mark.parametrize(("path", "content", "blocked"), [
    ("libespeak-ng.dylib", b"binary", True),
    ("runtime/libpcaudio.0.dylib", b"binary", True),
    ("pkg.dist-info/METADATA", b"License-Expression: MIT OR AGPL-3.0-only", True),
    ("NOTICE", b"If you combine this Software with\nsoftware that is licensed under the GPLv2 ...", False),
    ("package.json", b'{"license":"GPL-3.0-only"}', True),
    ("module.py", b'__license__ = "AGPLv3"', True),
    ("some/file", b"// SPDX-License-Identifier: GPL-2.0-or-later", True),
    ("pkg.py", b"# Licensed under the GNU Affero General Public License.", True),
    ("COPYING.GPL-2", b"see the accompanying source", True),
    ("binary", b"binary\x00SPDX-License-Identifier: GPL-2.0-only\x00", True),
    ("license", b"GNU GENERAL PUBLIC LICENSE\nVersion 3", True),
    ("LICENSE", b"GNU LESSER GENERAL PUBLIC LICENSE\nordinary GNU General Public License.", False),
    ("pkg.dist-info/METADATA", b"License: MIT", False),
])
def test_bundle_scan(tmp_path, path, content, blocked):
    app = tmp_path / "Duck Test.app"
    entry = app / "Contents" / path
    entry.parent.mkdir(parents=True)
    entry.write_bytes(content)
    result = subprocess.run([SCAN, app], capture_output=True, text=True)
    assert result.returncode == int(blocked), result.stdout + result.stderr
    if blocked or b"LESSER" in content:
        assert path in result.stdout + result.stderr


GCC_NOTICE = (b"Name: GCC runtime library\nFiles: numpy/.dylibs/libgfortran*, numpy/.dylibs/libgcc*\n"
              b"License: GPL-3.0-or-later WITH GCC-exception-3.1\n")


@pytest.mark.parametrize(("runtime", "blocked"), [(None, False), ("libgfortran.5.dylib", True), ("libgcc_s.1.1.dylib", True)])
def test_gcc_exception_is_allowed_only_without_gcc_runtime(tmp_path, runtime, blocked):
    app = tmp_path / "Duck Test.app"
    notice = app / "Contents/numpy-2.4.6.dist-info/licenses/LICENSE.txt"
    notice.parent.mkdir(parents=True)
    notice.write_bytes(b"BSD 3-Clause\n\n" + GCC_NOTICE)
    if runtime:
        (app / "Contents/numpy/.dylibs").mkdir(parents=True)
        (app / "Contents/numpy/.dylibs" / runtime).write_bytes(b"binary\x00")
    result = subprocess.run([SCAN, app], capture_output=True, text=True)
    assert result.returncode == int(blocked), result.stdout + result.stderr
    assert ("EXCEPTION" in result.stdout) is (not blocked)


def test_retired_voice_pack_is_unavailable(tmp_path):
    assert all(row["id"] != "tts-kokoro" for row in packs.status(tmp_path))
    with pytest.raises(KeyError):
        packs.start_download(tmp_path, "tts-kokoro")


def test_saved_voice_previews_with_apple_default(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(voice, "_synthesize", lambda text, name, out: calls.append(name))
    monkeypatch.setattr(voice, "_to_wave", lambda *args: None)
    monkeypatch.setattr(voice, "_duration", lambda _: 0)
    result = voice.preview_line("hello", "kokoro:af_heart", "test", tmp_path)
    assert calls == ["macOS default"]
    assert "macOS" in result["message"]


def test_legacy_user_folder_reports_missing_frontend(tmp_path):
    from duckcore import app_settings, model_slots
    import numpy as np

    (tmp_path / "kokoro-v1.0.onnx").write_bytes(b"model")
    with (tmp_path / "voices-v1.0.bin").open("wb") as f:
        np.savez(f, voice=np.ones((2, 3)))
    app_settings.save(tmp_path, {"model_slots": {"voice": {"enabled": True, "path": str(tmp_path)}}})
    status = model_slots.status(tmp_path, "voice")
    assert not status["ready"]
    assert "tokenizer.onnx" in status["problem"]


def test_saved_workflow_normalizes_retired_route():
    from duckcore.engine.workflow_config import normalize_workflow

    routes = [{"provider": "local", "model": model} for model in ("kokoro", "say")]
    assert normalize_workflow("tts", {"routes": routes})["routes"] == routes[1:]


def test_saved_voice_uses_default_say_argument(tmp_path, monkeypatch):
    calls = []
    output = tmp_path / "stub.aiff"
    output.touch()
    monkeypatch.setattr(voice, "_which_say", lambda: "/usr/bin/say")
    monkeypatch.setattr(voice.subprocess, "run", lambda cmd, **kwargs:
                        calls.append(cmd) or subprocess.CompletedProcess(cmd, 0))
    voice._synthesize("line", "tts-kokoro", output)
    assert calls == [["/usr/bin/say", "-o", str(output), "--", "line"]]
