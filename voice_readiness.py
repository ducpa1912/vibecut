"""Is this Mac ready to clone and hear a voice?

Three checks, in the order a new person needs them: the OpenRouter key, the
clone engine that key unlocks, and local Whisper. Each row is Ready or Failed
and carries one action. "Working" is the page's state while that action runs.

The check is local and read-only. It never spends a request; the page's Test
key button does that through the existing /api/settings/test route.
"""

from __future__ import annotations

import time

import settings_store

READY = "ready"
FAILED = "failed"


def _openrouter() -> dict:
    import audio

    if not settings_store.get_secret("openrouter"):
        return {
            "id": "openrouter",
            "label": "OpenRouter key",
            "state": FAILED,
            "detail": "No OpenRouter key is saved for this app. Cloning and every cloud voice need one.",
            "action": {"kind": "test_key", "label": "Test key"},
        }
    if audio.openrouter_blocked():
        seconds = int(audio.openrouter_blocked_seconds() or 0)
        wait = f" Retry in {seconds} s." if seconds > 0 else ""
        return {
            "id": "openrouter",
            "label": "OpenRouter key",
            "state": FAILED,
            "detail": f"OpenRouter refused the key on its last call.{wait}",
            "action": {"kind": "test_key", "label": "Test key"},
        }
    return {
        "id": "openrouter",
        "label": "OpenRouter key",
        "state": READY,
        "detail": "The key is saved for this app. Test it once to confirm OpenRouter accepts it.",
        "action": {"kind": "test_key", "label": "Test key"},
    }


def _clone_engine() -> dict:
    import tts

    status = tts.voice_engine_status().get("heygen") or {}
    available = bool(status.get("available"))
    if available:
        return {
            "id": "clone",
            "label": "Clone engine",
            "state": READY,
            "detail": "HeyGen Voice Turbo can clone from a 10-15 s reference through OpenRouter.",
            "action": {"kind": "check_clone", "label": "Check again"},
        }
    return {
        "id": "clone",
        "label": "Clone engine",
        "state": FAILED,
        "detail": status.get("install")
        or "Cloning needs the OpenRouter key. Add it above, then check again.",
        "action": {"kind": "check_clone", "label": "Check again"},
    }


def _whisper() -> dict:
    import stt

    command = stt._whisper_command()
    if not command:
        return {
            "id": "whisper",
            "label": "Local Whisper",
            "state": FAILED,
            "detail": "Local Whisper is not installed, so language detection and line checks cannot run. Install it with `brew install openai-whisper`.",
            "action": {"kind": "check_whisper", "label": "Check again"},
        }
    detail = "Local Whisper is ready for language detection and line checks."
    try:
        rows = stt.whisper_models()
        current = next((row for row in rows if row.get("current")), None)
        if current and not current.get("cached"):
            detail += " Its model downloads on first use, which can take a minute or two."
    except (OSError, ValueError):
        pass
    return {
        "id": "whisper",
        "label": "Local Whisper",
        "state": READY,
        "detail": detail,
        "action": {"kind": "check_whisper", "label": "Check again"},
    }


def checklist() -> dict:
    return {
        "items": [_openrouter(), _clone_engine(), _whisper()],
        "checked": round(time.time(), 3),
    }
