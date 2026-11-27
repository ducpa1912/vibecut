"""Creator sentences for import and Check failures.

The technical text (ffmpeg stderr, Python exceptions) stays in the log and in a
`detail` field; what the creator reads is one sentence with a next step.
Messages that are already written for a creator pass through unchanged.
"""

from __future__ import annotations

import logging
import re

LOG = logging.getLogger("duckcore.import")

REEXPORT = "Export it again as H.264 or HEVC MP4 and try again."
UNREADABLE = f"DuckSuite could not read the frames of this video. {REEXPORT}"
FALLBACK = f"This video could not be imported. {REEXPORT}"

# (pattern, creator sentence), first match wins. Order matters: disk space is
# checked before the generic ffmpeg and upload rules.
RULES: tuple[tuple[str, str], ...] = (
    (r"no space left|errno 28|disk (is )?full|not enough (free )?space",
     "There is not enough free disk space. Free some space, then import again."),
    (r"is not installed or bundled",
     "DuckSuite is missing its video tools. Reinstall DuckSuite, then import again."),
    (r"ffmpeg frame read failed|could not read a frame",
     UNREADABLE),
    (r"moov atom not found|invalid data found when processing input|end of file|truncated",
     f"This video file is incomplete or damaged. {REEXPORT}"),
    (r"decoder .*not found|unknown codec|unsupported codec|codec not (currently )?supported|"
     r"could not find codec",
     f"This video uses a format DuckSuite cannot read. {REEXPORT}"),
    (r"does not contain any stream|no video stream|stream specifier .*v:0.* matches no streams|"
     r"output file .*does not contain",
     "This file has no video picture. Choose a video export, then import again."),
    (r"does not match the master streams",
     "This clip's picture size, frame rate or audio differs from the project. Export it with the "
     "project's settings, then import again."),
    (r"ffmpeg could not join the videos",
     "This clip could not be joined to the project. Export it as H.264 or HEVC MP4 with the "
     "project's size and frame rate, then import again."),
    (r"could not read the video durations|has no duration",
     f"DuckSuite could not read how long this video is. {REEXPORT}"),
    (r"scene detection failed",
     f"DuckSuite could not find the scenes in this video. {REEXPORT}"),
    (r"the check result is unreadable",
     "This project's Check result is damaged. Run Check again, then import."),
    (r"the upload failed",
     "The video could not be copied into DuckSuite. Check the free disk space, then import again."),
    (r"the read could not start",
     "DuckSuite could not start reading the new video. Reopen the project, then import again."),
    (r"permission denied|read-only file system|operation not permitted",
     "DuckSuite could not access this video. Choose a file you can read, then import again."),
    (r"file not found|no such file or directory",
     "This video is no longer available. Choose the file again, then import it."),
)

# Text that marks a message as technical: it never reaches the creator as is.
_TECHNICAL = re.compile(
    r"ffmpeg|ffprobe|errno|traceback|exception|\[[a-z0-9_ ]+ @ 0x|0x[0-9a-f]{6,}|"
    r"returned non-zero|subprocess|\.py\b|/users/|/private/|/tmp/|\bpath\b",
    re.I,
)


def creator_message(text: str) -> str:
    """One creator sentence for `text`; already-plain messages pass through."""
    raw = str(text or "").strip()
    if not raw:
        return FALLBACK
    lowered = raw.lower()
    for pattern, sentence in RULES:
        if re.search(pattern, lowered):
            return sentence
    if _TECHNICAL.search(raw) or "\n" in raw:
        return FALLBACK
    return raw


def explain(exc: BaseException | str, where: str = "import") -> str:
    """Log the technical text and return the creator sentence."""
    raw = str(exc)
    message = creator_message(raw)
    if message != raw:
        LOG.warning("%s failed: %s", where, raw[:2000])
    return message
