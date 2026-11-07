"""DuckClean worker: one image, CPU and GPU modes.

M0 ships the wire contract only. `app.py` (FastAPI routes), `beats.py`
(dissection), `frames.py`, `ocr.py`, `logos.py`, `masks.py`, `render.py`,
`assemble.py` and `usage.py` arrive with tasks 4-8.
"""

WORKER_CONTRACT_VERSION = "1.0.0"

__all__ = ["WORKER_CONTRACT_VERSION"]
