"""One definition of when two OCR readings carry the same words.

Three places compare text: clustering observations into tracklets, refining a
tracklet's edge against the source, and the render leak check. Each had its own
rule, and the edge check ignored a one-character misread (叉 read for 又), which
ended a range before the line did.

``normalize`` keeps the words and folds case. ``compact`` also drops spaces and
punctuation, which OCR inserts and drops at will. ``same_text`` is the only
comparison callers should use.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

# One misread character in a short CJK line is a match; unrelated lines fall
# below this. Tuned on the review project's tracklets.
MATCH = 0.6


def normalize(value: object) -> str:
    """Collapse whitespace and fold case. Keeps punctuation."""
    return " ".join(str(value or "").split()).casefold()


def compact(value: object) -> str:
    """Normalize, then drop everything that is not a letter or a digit."""
    return re.sub(r"[\W_]+", "", normalize(value))


def same_text(left: object, right: object, threshold: float = MATCH) -> bool:
    """Whether two readings are the same words.

    Containment covers a frame where OCR catches part of a line; similarity
    covers a single misread character inside it.
    """
    first, second = compact(left), compact(right)
    if not first or not second:
        return False
    if first in second or second in first:
        return True
    return SequenceMatcher(None, first, second).ratio() >= threshold
