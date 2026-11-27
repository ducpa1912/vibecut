"""Independent QA follow-up, 2026-11-13: the findings the first repair left open."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from duckcore import render
from duckcore.main import create_app

ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "static" / "duck" / "app.js").read_text(encoding="utf-8")


def _done_job(queue: render.RenderQueue, data_root: Path, name: str, body: bytes) -> dict:
    job = queue.enqueue("prj_play", "ed_play", "Render")
    out = data_root / "projects" / "prj_play" / "renders" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(body)
    queue._update(job["id"], state="done", output=str(out))
    return job


def test_a_card_plays_its_own_render_not_the_latest(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(render.RenderQueue, "_loop", lambda self: None)
    app = create_app("test-token", tmp_path)
    queue = render.RenderQueue(tmp_path)
    old = _done_job(queue, tmp_path, "old.mp4", b"old render")
    new = _done_job(queue, tmp_path, "new.mp4", b"new render")
    base = "/api/projects/prj_play/edits/ed_play/render/file?t=test-token"
    with TestClient(app) as client:
        assert client.get(base).content == b"new render"
        assert client.get(f"{base}&job={old['id']}").content == b"old render"
        assert client.get(f"{base}&job={new['id']}").content == b"new render"
        # A job id from another edit is not this edit's render.
        other = queue.enqueue("prj_play", "ed_other", "Render")
        assert client.get(f"{base}&job={other['id']}").status_code == 404
        assert client.get(f"{base}&job=rq_nothere").status_code == 404


def test_a_render_file_outside_the_project_is_refused(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(render.RenderQueue, "_loop", lambda self: None)
    app = create_app("test-token", tmp_path)
    queue = render.RenderQueue(tmp_path)
    job = queue.enqueue("prj_play", "ed_play", "Render")
    outside = tmp_path / "elsewhere.mp4"
    outside.write_bytes(b"not a render")
    queue._update(job["id"], state="done", output=str(outside))
    with TestClient(app) as client:
        response = client.get(
            f"/api/projects/prj_play/edits/ed_play/render/file?t=test-token&job={job['id']}"
        )
    assert response.status_code == 404


def test_a_check_that_judged_no_frame_is_still_recorded(tmp_path) -> None:
    queue = render.RenderQueue(tmp_path)
    job = queue.enqueue("prj_c", "ed_c", "Render")
    queue._update(job["id"], state="done", checked_frames=0, check_unchecked=1, check_ran=1)
    row = queue.job(job["id"])
    assert row["check_ran"] == 1 and row["check_unchecked"] == 1


def test_every_play_button_carries_its_job() -> None:
    buttons = re.findall(r'data-action="play-render"[^>]*>', APP_JS)
    assert buttons and all("data-job=" in button for button in buttons)
    assert "{ job: jobId }" in APP_JS


def test_the_frame_rate_is_shown_not_offered() -> None:
    """The selector changed nothing: the render picks 24 or 30 from the source."""
    assert 'data-action="render-fps"' not in APP_JS
    assert "set from the source" in APP_JS


def test_render_settings_size_follows_the_cut() -> None:
    body = APP_JS.split("function outputSizeLabel() {", 1)[1].split("\n}", 1)[0]
    assert "cutOutputSize()" in body


def test_the_render_player_modal_wires_its_controls_once() -> None:
    modal = APP_JS.split("function openVideoModal(", 1)[1].split("\n}", 1)[0]
    assert "setupPlayerBars()" in modal
    bars = APP_JS.split("function setupPlayerBars() {", 1)[1].split("\n}", 1)[0]
    assert "barWired" in bars


def test_the_js_even_rule_matches_the_render() -> None:
    """render._target_size rounds, then moves up to an even number."""
    for width, height in ((1281, 720), (1366, 768), (720, 1280), (1080, 1920), (641, 361)):
        out_w, out_h = render._target_size({"width": width, "height": height})
        value = (width * 1080 / height) if width >= height else (height * 1080 / width)
        rounded = round(value + 1e-9) if value % 1 != 0.5 else int(value) + 1  # JS Math.round
        js = rounded + (rounded % 2)
        assert js == (out_w if width >= height else out_h), (width, height)


def _js_function(name: str) -> str:
    start = APP_JS.index(f"function {name}(")
    end = APP_JS.index("\n}\n", start) + 2
    return APP_JS[start:end]


def test_focus_goes_back_to_the_same_card_not_the_first(tmp_path) -> None:
    """Two queue cards each have a "Show" button: the signature must tell them apart."""
    import json
    import shutil
    import subprocess

    import pytest

    node = shutil.which("node") or "/Users/happynghia/.nvm/versions/node/v26.11.1/bin/node"
    if not Path(node).exists():
        pytest.skip("node is not available")
    script = tmp_path / "focus.cjs"
    script.write_text(
        _js_function("focusSignature") + "\n" + _js_function("focusTarget") + """
function button(data, text) {
  return { tagName: 'BUTTON', id: '', textContent: text, dataset: data,
           getAttribute: () => null, focus() {} };
}
const first = button({ action: 'reveal', path: '/r/one.mp4' }, 'Show');
const second = button({ action: 'reveal', path: '/r/two.mp4' }, 'Show');
const twinA = button({ action: 'noop' }, 'Same');
const twinB = button({ action: 'noop' }, 'Same');
const document = { body: {}, getElementById: () => null };
const app = { querySelectorAll: () => [first, second, twinA, twinB] };
const result = {
  differ: focusSignature(first) !== focusSignature(second),
  back: focusTarget(focusSignature(second)) === second,
  twins: focusTarget(focusSignature(twinA)),
};
console.log(JSON.stringify(result));
""",
        encoding="utf-8",
    )
    done = subprocess.run([node, str(script)], capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr[-400:]
    result = json.loads(done.stdout)
    assert result == {"differ": True, "back": True, "twins": None}
