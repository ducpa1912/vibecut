"""Which views and hidden features a build shows.

One codebase serves every lane (see ``docs/branching.md``); a build differs
only by two environment switches:

* ``VIBECUT_EDITION``: ``all`` (default, both views, Studio opens first),
  ``classic`` (Classic only, the beta build) or ``studio`` (Studio only).
* ``VIBECUT_FEATURES``: comma-separated hidden features to turn on, such as
  ``voice_room``. Edition ``all`` turns every feature on unless the variable
  is set, so a development checkout keeps today's behaviour.

Switches hide links and answer 404; they never remove code.
"""

from __future__ import annotations

import json
import os

EDITIONS = ("all", "classic", "studio")
FEATURES = ("voice_room",)


def edition() -> str:
    value = str(os.environ.get("VIBECUT_EDITION") or "all").strip().lower()
    return value if value in EDITIONS else "all"


def features() -> frozenset[str]:
    raw = os.environ.get("VIBECUT_FEATURES")
    if raw is None:
        return frozenset(FEATURES) if edition() == "all" else frozenset()
    names = {item.strip().lower() for item in raw.split(",")}
    return frozenset(name for name in names if name in FEATURES)


def feature_on(name: str) -> bool:
    return name in features()


def views() -> tuple[str, ...]:
    current = edition()
    if current == "classic":
        return ("classic",)
    if current == "studio":
        return ("studio",)
    return ("studio", "classic")


def public() -> dict:
    """What the page needs before first paint: allowed views and features."""
    allowed = views()
    return {
        "edition": edition(),
        "views": list(allowed),
        "default_view": allowed[0],
        "features": sorted(features()),
    }


def boot_script() -> str:
    """An inline script that hands ``public()`` to the page's boot block."""
    payload = json.dumps(public(), separators=(",", ":")).replace("</", "<\\/")
    return f"<script>window.VIBECUT_EDITION={payload};</script>"
