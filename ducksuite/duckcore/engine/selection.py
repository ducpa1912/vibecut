"""Selection v2: explicit multi-signal story ranking with prompt exclusions.

Version 1 (the automatic 15/30/60 Smart Cut) stays the default. This module is
only called by the explicit selection-v2 endpoint. It ranks existing clip-set
stories, drops stories that match a prompt exclusion, attaches explainable
evidence, and prepares three real hook candidates per story.
"""

from __future__ import annotations

import math
import re

from . import clipset

V2_WEIGHTS = {
    "hook_score": 0.27,
    "speech_coherence": 0.23,
    "audio_energy": 0.12,
    "visual_quality": 0.12,
    "payoff_position": 0.14,
    "novelty": 0.12,
}
_ALLOWED_EVIDENCE = set(clipset.EVIDENCE_TYPES)

_MARKER = (
    r"(?:do not|don't|doesn't|must not|should not|never|no|not|avoid|"
    r"exclude|excluding|skip|without|remove)"
)
_MARKER_RE = re.compile(rf"(?i)\b{_MARKER}\b")
_OPTIONAL_LEAD = re.compile(
    r"(?i)^(?:any|more|the|a|an|of|about|on|with|use|using|include|including|"
    r"mention|mentions|talk about|anything about)\b[\s:,-]+"
)
_BAD_TERMS = {
    "more than", "less than", "than", "only", "just", "please", "anything",
    "something", "that", "this",
}


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if math.isfinite(number) else fallback


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _clean(text: str) -> str:
    return " ".join(str(text or "").split())


