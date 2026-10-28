"""Classic guard: a speech-on job with no transcript says so and can retry."""

from __future__ import annotations

from pathlib import Path

import app
import routes_studio

ROOT = Path(__file__).resolve().parents[1]


def test_result_view_has_the_speech_notice_and_retry():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert 'id="speech-notice"' in html
    assert 'id="speech-notice-detail"' in html
    assert 'id="speech-retry"' in html
    assert "Setup → Transcription" in html

    script = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    assert "engine?.stt_enabled" in script
    assert "engine?.whisper" in script
    assert "/transcribe`" in script
    assert "/voice-tasks/transcribe" in script


def test_the_speech_retry_routes_are_registered():
    # FastAPI keeps included routers lazy (``_IncludedRouter``), so read the
    # lane router itself for the speech retry and the app for the poll route.
    studio_paths = {route.path for route in routes_studio.router.routes}
    assert "/api/jobs/{job_id}/transcribe" in studio_paths
    poll_paths = {getattr(route, "path", "") for route in app.app.routes}
    assert "/api/jobs/{job_id}/voice-tasks/{kind}" in poll_paths
