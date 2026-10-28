"""Routes the Classic view adds from now on (lane: ``classic``).

New Classic endpoints go here, not into ``app.py``, so the lanes stop
editing the same file (see ``docs/branching.md``). Existing Classic routes
stay in ``app.py`` until someone has a reason to touch them. Use
``import app`` inside a handler when it needs app helpers; importing at
module level would be circular.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()
