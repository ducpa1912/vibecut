"""VibeCut Classic's own server entrypoint.

    python classic_app.py
    # or: uvicorn classic_app:app --host 127.0.0.1 --port 8796

Classic is a supported product with its own page, data folder and port. It
keeps the shared backend graph for now (no core extraction in this pass), but
it does not boot through Studio's entrypoint or page.
"""

from __future__ import annotations

from core.profiles import CLASSIC, configure

configure(CLASSIC)

from app import HOST, PORT, app  # noqa: E402  (configured before app imports)

__all__ = ["app", "HOST", "PORT"]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
