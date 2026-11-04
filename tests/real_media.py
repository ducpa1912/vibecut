"""Real files the tests read. No test makes its own audio or video.

The founder's rule: "They should ask for real media not invented one." The files
live in the git-ignored ``data/media`` folder of this worktree. A test that needs
a missing file skips and names the file; the end of the run lists every test
still waiting. ``docs/testing/real-media.md`` holds the list to ask for.

``clip`` copies a stretch of a real file into a test's own folder, because the
code under test moves, cleans or deletes what it is given and the founder's file
must stay untouched.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

MEDIA = Path(__file__).resolve().parents[1] / "data" / "media"

CATALOG = {
    "speech.wav": "One person talking clearly with natural pauses and no music, starting right at 0:00, at least 90 s.",
    "silence.wav": "A silent recording with the input muted, so no room sound, at least 20 s.",
    "hiss.wav": "Only faint room hiss or fan noise, with no voice, at least 2 s.",
    "quiet-speech.wav": "Someone talking far from the mic, recorded very quietly, at least 2 s.",
    "loud-speech.wav": "Someone talking very loudly and close to the mic, not distorted, at least 2 s.",
    "clipped-speech.wav": "Talking recorded too hot, so it distorts and clips, at least 6 s.",
    "noisy-speech.wav": "Talking over strong background noise, at least 4 s.",
    "mixed-voice.wav": "One main speaker with music, room echo and a second speaker talking over them for a moment, at least 90 s.",
    "music.wav": "An instrumental music track you may use, at least 120 s.",
    "music-120bpm.wav": "Instrumental music with a steady 120 BPM beat, at least 8 s.",
    "talking-video.mp4": "A landscape 1920x1080 video of someone talking, with sound, at least 30 s.",
    "vertical-video.mp4": "A vertical 1080x1920 video, at least 26 s.",
    "silent-video.mp4": "A video with no audio track at all, at least 2 s.",
    "bright-dot-video.mp4": "A 1920x1080 video of one small bright object on a dark background, at least 2 s.",
}

_REASON = "Needs real file data/media/{name}: {what}"
_NAMES = re.compile(r"data/media/([\w.-]+)")
#: Files a running test asked for and did not get. conftest fails such a test if
#: it still passes, because a worker thread swallowed the skip.
asked: list[str] = []


def _reason(name: str) -> str:
    return _REASON.format(name=name, what=CATALOG[name])


def needs(*names: str):
    """Mark a test whose media is used on a worker thread, where a skip would be lost."""
    missing = [name for name in names if not (MEDIA / name).is_file()]
    return pytest.mark.skipif(bool(missing), reason="; ".join(_reason(name) for name in missing))


def path(name: str) -> Path:
    """The founder's file itself, for reading only. Skips when it is missing."""
    found = MEDIA / name
    if not found.is_file():
        asked.append(name)
        pytest.skip(_reason(name))
    return found


def _duration(source: Path) -> float:
    done = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(source)],
        capture_output=True, text=True, check=True,
    )
    return float(done.stdout.strip())


def clip(
    name: str,
    dest: Path,
    seconds: float,
    *,
    rate: int = 16000,
    channels: int = 1,
    scale: str | None = None,
) -> Path:
    """Copy the first ``seconds`` of a real file to ``dest``, in ``dest``'s format."""
    source = path(name)
    if _duration(source) < seconds - 0.05:
        pytest.skip(f"data/media/{name} is too short: this test needs {seconds:g} s. {CATALOG[name]}")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    command = ["ffmpeg", "-y", "-v", "error", "-i", str(source), "-t", f"{seconds:g}"]
    if source.suffix == ".mp4":
        if scale:
            command += ["-vf", f"scale={scale}"]
        command += ["-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast", "-movflags", "+faststart"]
    else:
        command += ["-ar", str(rate), "-ac", str(channels)]
    subprocess.run([*command, str(dest)], check=True, timeout=180)
    return dest


def waiting_on(reason: str) -> list[str]:
    """The files named in a skip reason, empty for any other skip."""
    return _NAMES.findall(reason)
