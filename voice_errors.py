"""Every Voice Room failure says what went wrong and what to do next.

House rules for this lane:

* One or two sentences: the cause first, then the next step.
* No stack traces, no ffmpeg tails, no file paths the creator cannot use.
* Say "try again" only when trying again can work.

The constants are the shared wording; routes raise them as the HTTP detail so
the page shows the same sentence the tests check.
"""

from __future__ import annotations

import re

NO_SPEECH = (
    "No speech could be heard in that recording. Record closer to the microphone and check that the input level moves."
)
UNREADABLE = (
    "Could not read that audio. Check that the file plays in another app, then choose it again."
)
EMPTY_FILE = "That file is empty. Choose a recording with sound in it, then try again."
TOO_LARGE = "That file is over 100 MB. Use a shorter recording, then try again."
BAD_FORMAT = "Use a WAV, MP3, M4A, OGG, WebM or FLAC file."
CONSENT_CLONE = (
    "Confirm this is your own voice, or that you have the speaker's permission to clone it. "
    "Tick the consent box, then try again."
)
CONSENT_VIDEO = (
    "Confirm you own this voice or have the speaker's permission to clone it. "
    "Tick the consent box, then try again."
)
CONSENT_RESTORE = (
    "Confirm you have permission to restore these voices. "
    "Tick the consent box, then restore the backup again."
)
NO_KEY = "Add an OpenRouter key in Setup, then try again."
MISSING_SOURCE = (
    "The source video for this job is missing. Import the video again, then retry."
)
MISSING_VOICE = "That cloned voice is not in the library. Reload the page; if it is gone, clone the voice again."
MISSING_TAKE = "That take is not in the library. Reload the page; if it is gone, make a new one."
BAD_TASK = "The page sent an unusable task id. Reload the page, then try the step again."
CROSS_SITE = "This page is not allowed to change voices. Reload Voice Room and try again."
NO_ENGINE = "That voice engine is unknown. Pick a voice from the library, then try again."
END_BEFORE_START = "The end must come after the start. Move the end marker right, then try again."
PICK_CLIP = "Pick one of the found clips first, then clone it."
FIND_CLIPS = "Find the best voice clips first, then clone one."
MISSING_CLIP = "That clip is not on this Mac. Run Find clean clips again, then pick one."
NO_CLONES = "No cloned voices yet. Clone your own voice first, then try again."

UNREADABLE_BACKUP = (
    "That file is not a VibeCut voice library backup. Choose the ZIP file made by Download backup, then restore it."
)
BAD_MANIFEST = (
    "That ZIP has no voice library manifest. Export a fresh backup from Library backup, then restore that file."
)
OLD_BACKUP = (
    "That backup comes from another version of VibeCut. Open it in the version that made it, or export a new backup here."
)
UNSAFE_BACKUP = (
    "That backup holds an unsafe file path. Use a backup made by this app; do not rename or rebuild its files."
)
MISMATCHED_BACKUP = (
    "A file in that backup does not match a voice in its manifest. Export a fresh backup from the Mac that holds those voices, then restore that file."
)
DUPLICATE_SAMPLE = (
    "That backup holds two samples for the same voice. Export a fresh backup, then restore that file."
)
BIG_SAMPLE = (
    "A voice sample in that backup is over 15 MB. Remove that voice from the library, then export a new backup."
)
BIG_BACKUP = "That backup is over 100 MB. Restore fewer voices at a time, or export a smaller library."
CLEANUP_WARNING = (
    "Old unstarred takes can be removed. Review them first; starred takes are always kept."
)


def trim_too_long(seconds: float, limit: float = 15.0) -> str:
    return (
        f"That selection is {seconds:.1f} s. Trim it to {limit:.0f} s or less, then clone it."
    )


def trim_too_short(seconds: float, minimum: float = 8.0) -> str:
    return (
        f"That selection is {seconds:.1f} s. Choose at least {minimum:.0f} s of clear speech, then clone it."
    )

_TRACEBACK = re.compile(r"(?i)\btraceback\b|\bfile \"[^\"]+\", line \d+|stack trace")
_WHITESPACE = re.compile(r"\s+")


def clean(message: str, fallback: str = "That step failed. Try again.") -> str:
    """One safe sentence or two: no newlines, no traceback, no ffmpeg tail.

    Only the first two sentences survive, which keeps a raw command error from
    pushing the useful cause off the page.
    """
    text = _WHITESPACE.sub(" ", str(message or "")).strip()
    if not text or _TRACEBACK.search(text):
        return fallback
    text = text.replace("Audio command failed.", "The audio step failed.")
    parts = [part for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    if not parts:
        return fallback
    kept = " ".join(parts[:2]).strip()
    if len(kept) > 320:
        kept = kept[:317].rstrip() + "…"
    return kept


def fix(cause: str, action: str) -> str:
    """Join a cause and its next step as two sentences."""
    head = clean(cause, "That step failed.")
    tail = _WHITESPACE.sub(" ", str(action or "")).strip()
    if not tail:
        return head
    if not head.endswith((".", "!", "?", "…")):
        head += "."
    if not tail.endswith((".", "!", "?", "…")):
        tail += "."
    return f"{head} {tail}"


def has_next_step(message: str) -> bool:
    """True when the message tells the creator what to do next."""
    text = str(message or "").lower()
    cues = (
        "try again", "then ", "choose", "pick", "add ", "tick", "check ",
        "install", "reload", "record ", "use ", "restore", "export ",
        "import ", "move ", "wait ", "open ", "run ", "download",
    )
    return any(cue in text for cue in cues)
