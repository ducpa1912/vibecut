"""Real media for tests. Tests never make video, sound or pictures.

The founder keeps real files in ``data/media`` (gitignored). A test that decodes
media asks for one by name. A missing file skips that test with a line naming the
file, and the end of the pytest run counts the tests waiting on each file. See
``docs/classic/testing/real-media.md``.

``real_clip`` and ``real_wav`` cut or convert the founder's file so a test gets a
known length and format. They only ever start from a real file.

``PLACEHOLDER_WAV`` is not media: it cannot be played. It stands in for a file in
tests where nothing reads the sound, such as a faked provider.
"""

from __future__ import annotations

import functools
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytest

MEDIA_DIR = Path(__file__).resolve().parents[1] / "data" / "media"

PLACEHOLDER_WAV = b"RIFF" + b"\x00" * 64


@dataclass(frozen=True)
class Need:
    what: str
    min_seconds: float = 0.0
    size: tuple[int, int] | None = None


NEEDS: dict[str, Need] = {
    "portrait-video": Need(
        "your own vertical video, exactly 1080x1920, with someone talking", 30.0, (1080, 1920),
    ),
    "wide-video": Need(
        "your own horizontal video, exactly 1920x1080, with sound", 24.0, (1920, 1080),
    ),
    "silent-video": Need("your own video that has no sound track at all", 2.0),
    "light-in-dark": Need(
        "a still shot, exactly 1920x1080, of one small bright light in a dark room, "
        "with no other bright thing in the picture",
        2.0, (1920, 1080),
    ),
    "voice-clean": Need("one person talking in a quiet room, no music", 90.0),
    "voice-noisy": Need("one person talking with loud background noise", 4.0),
    "voice-hum": Need("one person holding one steady hum, no words", 2.0),
    "talk-over-music": Need("people talking with music playing behind them", 90.0),
    "music": Need("a music track you have the rights to", 8.0),
    "metronome-120bpm": Need("a metronome set to 120 BPM, with nothing else in the sound", 8.0),
    "room-silence": Need("a recording of a quiet room, with nobody talking", 6.0),
    "bright-photo": Need("a JPEG photo that is almost all white, like a white wall", 0.0),
}


def _needed(stem: str, problem: str) -> None:
    pytest.skip(f"REAL MEDIA NEEDED: data/media/{stem}.* {problem}: {NEEDS[stem].what}")


def _probe(path: Path) -> tuple[float, tuple[int, int] | None]:
    """Return the file's seconds and its picture size, when it has a video stream."""
    output = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height:format=duration",
            "-of", "default=noprint_wrappers=1", str(path),
        ],
        capture_output=True, text=True, check=True, timeout=60,
    ).stdout
    fields = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
    try:
        seconds = float(fields.get("duration", "0"))
    except ValueError:
        seconds = 0.0
    if fields.get("width", "").isdigit() and fields.get("height", "").isdigit():
        return seconds, (int(fields["width"]), int(fields["height"]))
    return seconds, None


def real_file(stem: str) -> Path:
    """The founder's file for ``stem``. It skips, naming the file, when it is unusable."""
    need = NEEDS[stem]
    matches = sorted(
        path for path in MEDIA_DIR.glob(f"{stem}.*")
        if path.is_file() and not path.name.startswith(".")
    )
    if not matches:
        _needed(stem, "is missing")
    path = matches[0]
    if need.min_seconds or need.size:
        if not shutil.which("ffprobe"):
            pytest.skip("ffprobe is needed to read real media")
        seconds, size = _probe(path)
        if seconds < need.min_seconds:
            _needed(stem, f"is {seconds:.1f} s, it must be at least {need.min_seconds:g} s")
        if need.size and size != need.size:
            _needed(stem, f"is {size}, it must be {need.size[0]}x{need.size[1]}")
    return path


def _ffmpeg(*args: str) -> None:
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is needed to read real media")
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True, timeout=300)


def real_clip(stem: str, path: Path, seconds: float) -> Path:
    """The first ``seconds`` of the founder's video, cut on an exact frame."""
    source = real_file(stem)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg(
        "-i", str(source), "-t", f"{seconds:g}",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-movflags", "+faststart", str(path),
    )
    return path


def real_wav(
    stem: str,
    path: Path,
    *,
    seconds: float | None = None,
    rate: int = 48000,
    channels: int = 1,
    gain_db: float | None = None,
) -> Path:
    """The founder's sound as PCM WAV. ``gain_db`` makes a real take louder."""
    source = real_file(stem)
    path.parent.mkdir(parents=True, exist_ok=True)
    args = ["-i", str(source)]
    if seconds is not None:
        args += ["-t", f"{seconds:g}"]
    if gain_db is not None:
        args += ["-af", f"volume={gain_db:g}dB"]
    _ffmpeg(*args, "-vn", "-ac", str(channels), "-ar", str(rate), "-c:a", "pcm_s16le", str(path))
    return path


@functools.lru_cache(maxsize=1)
def real_clip_bytes() -> bytes:
    """A playable one-second cut of the founder's video, for a finished reel."""
    with tempfile.TemporaryDirectory(prefix="vibecut-real-clip-") as folder:
        return real_clip("portrait-video", Path(folder) / "clip.mp4", 1.0).read_bytes()


@functools.lru_cache(maxsize=1)
def _real_frame() -> bytes:
    source = real_file("portrait-video")
    with tempfile.TemporaryDirectory(prefix="vibecut-real-frame-") as folder:
        path = Path(folder) / "frame.jpg"
        _ffmpeg("-ss", "0.5", "-i", str(source), "-frames:v", "1", "-vf", "scale=64:-2", str(path))
        return path.read_bytes()


def real_jpeg(tag: str = "") -> bytes:
    """One frame of the founder's video. ``tag`` makes two covers differ byte for byte."""
    return _real_frame() + tag.encode()
