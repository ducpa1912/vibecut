"""Routes the Studio view adds from now on (lane: ``studio``).

New Studio endpoints go here, not into ``app.py``, so the lanes stop
editing the same file (see ``docs/branching.md``). Existing Studio routes
stay where they are. Use ``import app`` inside a handler when it needs app
helpers; importing at module level would be circular.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()
