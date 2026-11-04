"""VibeCut core contract and app profiles.

The modules still live at the repository root during this migration. This
package owns the versioned profile contract so Studio and Classic can compose
pinned features without copying the backend.
"""

from .version import CORE_VERSION, CONTRACT_VERSION
from .profiles import (
    CLASSIC, LEGACY, PROFILE_VERSION, STUDIO, AppProfile,
    active_profile, configure,
)

__all__ = [
    "AppProfile", "CORE_VERSION", "CONTRACT_VERSION", "CLASSIC", "LEGACY",
    "PROFILE_VERSION", "STUDIO", "active_profile", "configure",
]
