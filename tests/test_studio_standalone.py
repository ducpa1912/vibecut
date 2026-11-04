"""Studio owns its runtime.

Studio is a separate app, not an overlay: it boots without the Classic router
or the ``static/classic`` and ``static/voice`` trees, and its own JavaScript
never imports another view's files.

The boot test copies the checkout without those trees and runs the real
entrypoint in a subprocess, so a hidden import or a hard-coded asset path
fails here instead of on the founder's machine.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "static" / "studio"

# Everything that is not part of a shippable Studio tree.
_SKIP_ANYWHERE = {".git", ".venv", "data", "tests", "__pycache__", ".pytest_cache"}
_SKIP_AT_ROOT = {"routes_classic.py", "round_1.md"}
_SKIP_IN_STATIC = {"classic", "voice", "voices.html", "voices-next.html"}

_IMPORT = re.compile(r'^\s*(?:import|export)\s[^;]*?from\s+["\']([^"\']+)["\']', re.MULTILINE)


def test_studio_javascript_does_not_import_another_view():
    for path in sorted(STUDIO.rglob("*.js")):
        text = path.read_text(encoding="utf-8")
        for target in _IMPORT.findall(text):
            if not target.startswith("."):
                continue
            resolved = (path.parent / target).resolve()
            assert "static/voice" not in resolved.as_posix(), f"{path} imports {target}"
            assert "static/classic" not in resolved.as_posix(), f"{path} imports {target}"


def test_studio_has_its_own_voice_client():
    client = STUDIO / "voice" / "voiceclone.js"
    assert client.is_file(), "Studio's voice client must live under static/studio"
    text = client.read_text(encoding="utf-8")
    assert 'from "../api.js"' in text and 'from "../ui.js"' in text
    assert 'from "./api.js"' not in text
    for importer, expected in (
        (STUDIO / "setup.js", "./voice/voiceclone.js"),
        (STUDIO / "edit" / "layers" / "audio.js", "../../voice/voiceclone.js"),
    ):
        source = importer.read_text(encoding="utf-8")
        assert expected in source, importer
        assert (importer.parent / expected).resolve() == client.resolve(), importer


def _studio_tree(destination: Path) -> Path:
    repo = destination / "repo"

    def ignore(directory: str, names: list[str]) -> set[str]:
        here = Path(directory)
        skipped = {name for name in names if name in _SKIP_ANYWHERE}
        if here == ROOT:
            skipped.update(name for name in names if name in _SKIP_AT_ROOT)
        if here == ROOT / "static":
            skipped.update(name for name in names if name in _SKIP_IN_STATIC)
        return skipped

    shutil.copytree(ROOT, repo, ignore=ignore, symlinks=True)
    return repo


def test_studio_boots_with_the_classic_and_voice_trees_absent(tmp_path):
    repo = _studio_tree(tmp_path)
    assert not (repo / "static" / "classic").exists()
    assert not (repo / "static" / "voice").exists()
    assert not (repo / "routes_classic.py").exists()

    script = """
import sys
sys.path.insert(0, ".")
import studio_app
from fastapi.testclient import TestClient

assert "routes_classic" not in sys.modules, "Studio imported the Classic router"
api = TestClient(studio_app.app)

health = api.get("/api/health")
assert health.status_code == 200, health.text

page = api.get("/")
assert page.status_code == 200, page.text
assert "/static/studio/shell.js" in page.text
assert "/static/classic" not in page.text
assert 'href="/voices"' not in page.text

assert api.get("/classic").status_code == 404
assert api.get("/voices").status_code == 404
assert api.get("/static/studio/shell.js").status_code == 200
assert api.get("/static/studio/voice/voiceclone.js").status_code == 200

# Studio keeps its own voice features even though the Voice Room page is gone.
assert api.get("/api/voices/clones").status_code == 200
assert api.get("/api/voices/catalog").status_code == 200
print("studio-ok")
"""
    env = {
        **os.environ,
        "PYTHONPATH": str(repo),
        "PYTHONDONTWRITEBYTECODE": "1",
        "VIBECUT_DATA": str(tmp_path / "data"),
        "VIBECUT_EDITION": "studio",
        "VIBECUT_FEATURES": "voice_room",
    }
    env.pop("VIBECUT_APP", None)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "studio-ok" in result.stdout


def test_studio_page_does_not_boot_from_editions():
    page = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert "vibecut:edition" not in page
    assert "VIBECUT_EDITION" not in page
    assert 'data-features="voice_room"' in page
    assert 'data-views="studio"' in page


def test_separate_app_entrypoints_and_scripts_exist():
    classic = (ROOT / "classic_app.py").read_text(encoding="utf-8")
    assert 'VIBECUT_APP"] = "classic"' in classic
    assert 'VIBECUT_EDITION"] = "classic"' in classic
    assert 'VIBECUT_PORT", "8796"' in classic
    assert 'vibecut-lanes" / "classic"' in classic
    studio = (ROOT / "studio_app.py").read_text(encoding="utf-8")
    assert 'VIBECUT_PORT", "8795"' in studio
    assert 'vibecut-lanes" / "studio"' in studio
    assert (ROOT / "scripts" / "serve-studio.sh").is_file()
    assert (ROOT / "scripts" / "serve-classic.sh").is_file()
    assert not (ROOT / "scripts" / "integrate.sh").exists()
