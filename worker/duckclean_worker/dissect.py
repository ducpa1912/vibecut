"""Beat dissection: cut the source into frame-exact spans, measured not guessed.

Two real passes over the file:

1. ffmpeg decodes at ``scene_analysis_height`` and reports every frame whose
   scene score passes the threshold. The timestamps come from ffmpeg, not from a
   guess about the file.
2. Those timestamps are snapped to source frame numbers and merged into spans of
   at least ``min_seconds_milli`` and at most ``max_seconds_milli``.

The result tiles ``[0, frame_count)`` exactly once, so a later concat cannot drop
or duplicate a frame. Every span starts on a frame boundary, and the plan is a
pure function of (frame_count, fps, cut frames, params): re-dissecting the same
file with the same params produces the same spans.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .contract import BeatBoundary, BeatSpec, DissectParams, ProbeInfo
from .media import MediaError, _binary, _run

# ffmpeg's metadata filter prints one block per selected frame:
#   frame:0    pts:1234   pts_time:0.0411
#   lavfi.scene_score=0.412
_PTS = re.compile(r"pts_time:(?P<time>-?\d+(?:\.\d+)?)")
_SCORE = re.compile(r"lavfi\.scene_score=(?P<score>-?\d+(?:\.\d+)?)")
_READ_CHUNK = 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_READ_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scene_cut_times(path: Path, params: DissectParams) -> list[float]:
    """Timestamps, in seconds, of frames ffmpeg scores above the threshold."""
    threshold = params.scene_threshold_milli / 1000
    result = _run(
        [
            _binary("ffmpeg"),
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-an",
            "-filter:v",
            (
                f"scale=-2:{params.scene_analysis_height},"
                f"select='gt(scene,{threshold:.3f})',metadata=print:file=-"
            ),
            "-f",
            "null",
            "-",
        ]
    )
    if result.returncode != 0:
        raise MediaError("scene_scan_failed")

    cuts: list[float] = []
    pending: float | None = None
    for line in result.stdout.splitlines():
        match = _PTS.search(line)
        if match is not None:
            pending = float(match.group("time"))
            continue
        score = _SCORE.search(line)
        if score is not None and pending is not None:
            cuts.append(pending)
            pending = None
    cuts.sort()
    return cuts


def snap_to_frames(cut_times: list[float], fps_num: int, fps_den: int) -> list[int]:
    """Frame numbers for cut timestamps, de-duplicated and never frame 0."""
    frames: set[int] = set()
    for moment in cut_times:
        if moment <= 0:
            continue
        frames.add(round(moment * fps_num / fps_den))
    return sorted(frames)


def _frames_for(milliseconds: int, fps_num: int, fps_den: int) -> int:
    return max(1, round(milliseconds * fps_num / (1000 * fps_den)))


def plan_beats(
    *,
    frame_count: int,
    fps_num: int,
    fps_den: int,
    cut_frames: list[int],
    params: DissectParams,
) -> list[BeatSpec]:
    """Split ``[0, frame_count)`` on scene cuts, then cap every long span."""
    if frame_count < 1:
        raise MediaError("frame_count_unreadable")
    min_frames = _frames_for(params.min_seconds_milli, fps_num, fps_den)
    max_frames = max(min_frames + 1, _frames_for(params.max_seconds_milli, fps_num, fps_den))

    cuts = sorted({frame for frame in cut_frames if 0 < frame < frame_count})
    beats: list[BeatSpec] = []
    start = 0
    boundary = BeatBoundary.START
    while start < frame_count:
        limit = min(start + max_frames, frame_count)
        cut = next((frame for frame in cuts if start + min_frames <= frame <= limit), None)
        if cut is not None and cut < frame_count:
            end = cut
            next_boundary = BeatBoundary.SCENE
        else:
            end = limit
            next_boundary = BeatBoundary.CAP
        if end >= frame_count:
            next_boundary = BeatBoundary.CAP
        beats.append(
            BeatSpec(
                index=len(beats),
                start_frame=start,
                end_frame=end,
                boundary=boundary,
            )
        )
        start = end
        boundary = next_boundary
    return beats


def beat_start_ms(start_frame: int, fps_num: int, fps_den: int) -> int:
    """Frame -> integer milliseconds, floored so spans stay ordered."""
    return (start_frame * 1000 * fps_den) // fps_num


def dissect_file(path: Path, probe: ProbeInfo, params: DissectParams) -> list[BeatSpec]:
    cut_times = scene_cut_times(path, params)
    return plan_beats(
        frame_count=probe.frame_count,
        fps_num=probe.fps_num,
        fps_den=probe.fps_den,
        cut_frames=snap_to_frames(cut_times, probe.fps_num, probe.fps_den),
        params=params,
    )
