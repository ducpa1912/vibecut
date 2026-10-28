"""The Voice Room page (`/voices`): one self-contained page for voices.

* Static: the page loads its own modules and holds the library, cloning and
  the clean-clip finder.
* Node: the clip finder's pure helpers.
* Routes: rename a clone.
* Chromium: the whole page against a live server, with the slow model work
  faked by ``tests/browser/voice_room_server.py``.
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
VOICE = ROOT / "static" / "voice"
BROWSER = ROOT / "tests" / "browser"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(not NODE, reason="node is not installed")

sys.path.insert(0, str(BROWSER))
import voice_room_server  # noqa: E402


def run_module(module: str, body: str):
    """Import ``static/voice/<module>`` as ``m``, run ``body``, return its JSON."""
    url = (VOICE / module).as_uri()
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


# ---------------------------------------------------------------- static


def test_voices_page_loads_its_own_modules():
    page = (ROOT / "static" / "voices.html").read_text(encoding="utf-8")
    assert 'id="voice-root"' in page
    assert "/static/voice/voiceroom.js" in page
    assert "/static/voice/voice.css" in page
    room = (VOICE / "voiceroom.js").read_text(encoding="utf-8")
    assert 'getElementById("voice-root")' in room
    assert 'from "./clipfinder.js"' in room
    for panel in ("your-voices", "clone", "stock-voices"):
        assert f'"data-panel": "{panel}"' in room
    # The library lists clones itself; the record panel only clones.
    assert "list: false" in room
    assert "renameClone" in room and "deleteClone" in room and "playClone" in room
    assert "../studio/" not in room


def _tokens(css: str) -> dict[str, str]:
    import re

    block = css.split(":root {", 1)[1].split("}", 1)[0]
    return {name: value.strip() for name, value in re.findall(r"(--[\w-]+):\s*([^;]+);", block)}


def test_voices_page_has_the_classic_look_without_studio_css():
    page = (ROOT / "static" / "voices.html").read_text(encoding="utf-8")
    assert "studio.css" not in page and "/static/studio/" not in page
    assert '<body class="vr-root">' in page
    voice = (VOICE / "voice.css").read_text(encoding="utf-8")
    assert "--st-" not in voice
    classic = _tokens((ROOT / "static" / "style.css").read_text(encoding="utf-8"))
    mine = _tokens(voice)
    assert classic, "Classic's :root tokens moved"
    for name, value in classic.items():
        assert mine.get(name) == value, f"{name}: Classic {value}, Voice Room {mine.get(name)}"
    # Classic's components the page uses, and the record panel's st-* names.
    for rule in (".vr-root .primary", ".vr-root .ghost", ".vr-root .topbar", ".vr-root .brand-mark",
                 ".vr-root .hint", ".vr-root .error", ".vr-root .st-btn", ".vr-root .st-status"):
        assert rule in voice, rule


def test_classic_top_bar_links_the_voice_room_only_when_it_is_on(monkeypatch):
    import app

    index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert '<a id="classic-voice-room" href="/voices">Voice Room</a>' in index
    assert 'html:not([data-features~="voice_room"]) #classic-voice-room' in index
    api = TestClient(app.app)
    monkeypatch.setenv("VIBECUT_EDITION", "classic")
    monkeypatch.setenv("VIBECUT_FEATURES", "")
    assert '"features":[]' in api.get("/").text
    assert api.get("/voices").status_code == 404
    monkeypatch.setenv("VIBECUT_FEATURES", "voice_room")
    assert '"features":["voice_room"]' in api.get("/").text
    assert api.get("/voices").status_code == 200


def test_clip_finder_uses_the_candidate_routes():
    finder = (VOICE / "clipfinder.js").read_text(encoding="utf-8")
    for name in ("findVoiceCandidates", "voiceCandidateState", "voiceCandidateAudioUrl", "cloneFromVideo"):
        assert name in finder
    assert "body.candidate = clip.index" in finder
    assert "CONSENT_COPY.video" in finder


def test_voiceclone_keeps_its_studio_exports():
    """Studio's Edit and Setup import these; the Voice Room adds, never removes."""
    text = (VOICE / "voiceclone.js").read_text(encoding="utf-8")
    for name in (
        "CONSENT_COPY", "listClones", "deleteClone", "cloneFromVideo", "findVoiceCandidates",
        "voiceCandidateState", "cancelVoiceCandidates", "voiceCandidateAudioUrl", "cloneFromFile",
        "playClone", "playVoice", "stopPlayback", "createMyVoicePanel",
    ):
        assert f"export function {name}" in text or f"export const {name}" in text or f"export async function {name}" in text, name
    assert 'title = "My voice", list = true' in text


# ---------------------------------------------------------------- node


@needs_node
def test_clip_finder_stage_copy_and_facts():
    out = run_module("clipfinder.js", """
        return {
          queued: m.stageCopy({state: "queued", stage: "queued"}),
          scoring: m.stageCopy({state: "running", stage: "scoring"}),
          failed: m.stageCopy({state: "failed", error: "No speech."}),
          cancelled: m.stageCopy({state: "cancelled"}),
          done: m.stageCopy({state: "done"}),
          none: m.stageCopy(null),
          running: [m.isRunning({state: "queued"}), m.isRunning({state: "running"}), m.isRunning({state: "done"})],
          facts: m.clipFacts({duration: 59.6, speech_fraction: 0.92, quality: {snr_db: 19.5}}),
          bare: m.clipFacts({}),
        };
    """)
    assert out["queued"] == "Queued behind other voice work…"
    assert out["scoring"] == "Scoring speech windows…"
    assert out["failed"] == "No speech."
    assert out["cancelled"] == "Search cancelled."
    assert out["done"] == "" and out["none"] == ""
    assert out["running"] == [True, True, False]
    assert out["facts"] == "60 s · clarity 20 dB · 92% speech"
    assert out["bare"] == ""


# ---------------------------------------------------------------- routes


def test_rename_a_clone(tmp_path, monkeypatch):
    import app
    import settings_store
    import voice_clone

    monkeypatch.setattr(settings_store, "DATA", tmp_path)
    sample = voice_room_server.tone(tmp_path / "s.wav", 1.0)
    record = voice_clone.create_clone(sample, name="Old", source="me", consent=True)
    api = TestClient(app.app)
    url = f"/api/voices/clones/{record['voice_id']}"
    renamed = api.patch(url, json={"name": "  New   name "})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "New name"
    assert api.get(url).json()["name"] == "New name"
    assert api.patch(url, json={"name": "   "}).status_code == 400
    assert api.patch("/api/voices/clones/clone_missing", json={"name": "x"}).status_code == 404


# ---------------------------------------------------------------- chromium


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _playwright_module() -> Path | None:
    candidates: list[Path] = []
    explicit = os.environ.get("PLAYWRIGHT_MODULE")
    if explicit:
        candidates.append(Path(explicit.replace("file://", "")))
    candidates.append(ROOT / "node_modules" / "playwright" / "index.mjs")
    candidates.extend(
        Path(path) for path in glob.glob(
            str(Path.home() / ".npm" / "_npx" / "*" / "node_modules" / "playwright" / "index.mjs")
        )
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _wait_for_health(base: str, process: subprocess.Popen, log: Path) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            tail = log.read_text(errors="replace")[-4000:] if log.is_file() else ""
            pytest.fail(f"server exited before health check:\n{tail}")
        try:
            with urllib.request.urlopen(f"{base}/api/health", timeout=1) as reply:
                if reply.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.2)
    pytest.fail("server did not become healthy in 30 s")


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def run_spec(tmp_path: Path, spec: str, extra_env: dict | None = None) -> dict:
    """Serve a scratch data folder with one ready video and run ``spec``."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    module = _playwright_module()
    if module is None:
        pytest.skip("Node Playwright is not installed")
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is needed to cut clone samples")

    data = tmp_path / "data"
    job_dir = data / "jobs" / "vr-job"
    job_dir.mkdir(parents=True)
    source = voice_room_server.tone(tmp_path / "talk.wav", 12.0)
    (job_dir / "job.json").write_text(json.dumps({
        "id": "vr-job", "created": time.time(), "status": "ready",
        "source": {"path": str(source), "name": "founder-talk.mp4", "duration": 120.0, "has_audio": True},
    }), encoding="utf-8")
    upload = voice_room_server.tone(tmp_path / "me.wav", 10.0, 180.0)

    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    log_path = tmp_path / "server.log"
    environment = {
        **os.environ,
        "VIBECUT_DATA": str(data),
        "VIBECUT_FEATURES": "voice_room",
        "PYTHONUNBUFFERED": "1",
        **(extra_env or {}),
    }
    environment.pop("VIBECUT_TOKEN", None)
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            [sys.executable, str(BROWSER / "voice_room_server.py"), str(port)],
            cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            _wait_for_health(base, process, log_path)
            completed = subprocess.run(
                [node, str(BROWSER / spec)],
                cwd=ROOT,
                env={
                    **environment,
                    "VR_BASE_URL": base,
                    "VR_JOB_ID": "vr-job",
                    "VR_UPLOAD": str(upload),
                    "VR_SCREENSHOT": str(tmp_path / "voice_room.png"),
                    "PLAYWRIGHT_MODULE": module.as_uri(),
                },
                capture_output=True, text=True, timeout=180,
            )
        finally:
            _stop(process)
    output = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode == 2:
        pytest.skip(output.strip() or "Playwright cannot run here")
    assert completed.returncode == 0, output
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_voice_room_page_in_chromium(tmp_path):
    report = run_spec(tmp_path, "voice_room.spec.mjs")
    assert report["classic_link"] is True
    assert report["stylesheets"] and not any("studio" in href for href in report["stylesheets"])
    assert report["clips"] == 3
    assert report["left"] == 1
