"""VibeCut Studio's own server entrypoint.

    python studio_app.py
    # or: uvicorn studio_app:app --host 127.0.0.1 --port 8795

Studio serves its own page and the shared backend features it ships. It does
not import Classic's router and does not need ``static/classic`` or
``static/voice`` on disk, so those trees can be split out without touching
Studio.

Environment is the same as the shared app: ``VIBECUT_DATA``, ``VIBECUT_PORT``,
``VIBECUT_TOKEN``. ``VIBECUT_APP=studio`` marks the build; Studio always ships
its voice features (clone, speech) inside Setup and Edit.
"""

from __future__ import annotations

from core.profiles import STUDIO, configure

configure(STUDIO)

from app import HOST, PORT, app  # noqa: E402  (configured before app imports)

__all__ = ["app", "HOST", "PORT"]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
