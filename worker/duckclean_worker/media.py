"""Real media work: probe, review proxy and poster.

Everything here is measured from the file with ffprobe/ffmpeg. There is no
synthetic frame, no guessed duration and no placeholder poster: if ffmpeg
cannot read the source, the job fails as ``source_unreadable``.

The proxy is review material only. It is H.264/yuv420p at most 720 px tall with
faststart, so a phone can start playing before the file is complete. The final
render keeps the source's own dimensions and frame rate.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from .contract import ProbeInfo, ProxyFacts, ProxyOptions

FFMPEG_TIMEOUT_SECONDS = 1_800


class MediaError(Exception):
    """A source the worker cannot read, or an ffmpeg call that failed."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class MediaFacts:
    width: int
    height: int
    duration_ms: int
    fps_num: int
    fps_den: int


def _binary(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise MediaError(f"{name}_missing")
    return path


def _run(
    args: list[str], *, timeout: int = FFMPEG_TIMEOUT_SECONDS
) -> subprocess.CompletedProcess[str]:
    try:
        # S603: the argument list is built here, never from a request field, and
        # shell execution is never used.
        return subprocess.run(  # noqa: S603
            args,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaError("timeout") from exc


def ffprobe_json(path: Path) -> dict[str, Any]:
    result = _run(
        [
            _binary("ffprobe"),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
    )
    if result.returncode != 0:
        raise MediaError("unreadable")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise MediaError("unreadable") from exc
    if not isinstance(data, dict):
        raise MediaError("unreadable")
    return data


def normalise_rotation(value: float) -> Literal[0, 90, 180, 270]:
    """ffmpeg reports display rotation as e.g. -90; the display frame is 270."""
    degrees = round(value) % 360
    if degrees in (0, 90, 180, 270):
        return cast(Literal[0, 90, 180, 270], degrees)
    return 0


def _rotation_of(video: dict[str, Any]) -> Literal[0, 90, 180, 270]:
    side_data = video.get("side_data_list")
    if isinstance(side_data, list):
        for entry in side_data:
            if isinstance(entry, dict) and "rotation" in entry:
                try:
                    return normalise_rotation(float(entry["rotation"]))
                except (TypeError, ValueError):
                    continue
    tags = video.get("tags")
    if isinstance(tags, dict) and "rotate" in tags:
        try:
            return normalise_rotation(float(tags["rotate"]))
        except (TypeError, ValueError):
            return 0
    return 0


def _fps(value: object) -> tuple[int, int]:
    if not isinstance(value, str):
        raise MediaError("frame_rate_unreadable")
    numerator, _, denominator = value.partition("/")
    try:
        num = int(numerator)
        den = int(denominator or "1")
    except ValueError as exc:
        raise MediaError("frame_rate_unreadable") from exc
    if num <= 0 or den <= 0:
        raise MediaError("frame_rate_unreadable")
    return num, den


def probe_file(path: Path) -> ProbeInfo:
    """Read the facts the rest of the pipeline is built on."""
    data = ffprobe_json(path)
    streams = data.get("streams")
    if not isinstance(streams, list):
        raise MediaError("no_video_stream")
    video = next(
        (
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "video"
        ),
        None,
    )
    if video is None:
        raise MediaError("no_video_stream")
    audio = next(
        (
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "audio"
        ),
        None,
    )

    format_info = data.get("format")
    duration_raw: object = None
    if isinstance(format_info, dict):
        duration_raw = format_info.get("duration")
    if duration_raw is None:
        duration_raw = video.get("duration")

    try:
        duration_s = float(duration_raw)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise MediaError("duration_unreadable") from exc
    if duration_s <= 0:
        raise MediaError("duration_unreadable")
    duration_ms = max(1, round(duration_s * 1000))

    fps_num, fps_den = _fps(video.get("r_frame_rate") or video.get("avg_frame_rate"))

    coded_width = int(video.get("width") or 0)
    coded_height = int(video.get("height") or 0)
    if coded_width <= 0 or coded_height <= 0:
        raise MediaError("dimensions_unreadable")

    rotation = _rotation_of(video)
    display_width, display_height = (
        (coded_height, coded_width) if rotation in (90, 270) else (coded_width, coded_height)
    )

    nb_frames = video.get("nb_frames")
    try:
        frame_count = int(nb_frames) if nb_frames is not None else 0
    except (TypeError, ValueError):
        frame_count = 0
    if frame_count <= 0:
        frame_count = max(1, round(duration_s * fps_num / fps_den))

    bit_rate_raw = format_info.get("bit_rate") if isinstance(format_info, dict) else None
    try:
        bit_rate = int(bit_rate_raw) if bit_rate_raw is not None else None
    except (TypeError, ValueError):
        bit_rate = None

    return ProbeInfo(
        duration_ms=duration_ms,
        display_width=display_width,
        display_height=display_height,
        coded_width=coded_width,
        coded_height=coded_height,
        rotation=rotation,
        fps_num=fps_num,
        fps_den=fps_den,
        frame_count=frame_count,
        video_codec=str(video.get("codec_name") or "unknown"),
        pixel_format=str(video.get("pix_fmt") or "unknown"),
        audio_codec=str(audio.get("codec_name")) if audio is not None else None,
        has_audio=audio is not None,
        bit_rate=bit_rate,
    )


def _target_height(source_height: int, max_height: int) -> int:
    target = min(max_height, source_height)
    if target % 2 == 1:
        target -= 1
    return max(target, 2)


def make_proxy(input_path: Path, output_path: Path, options: ProxyOptions) -> ProbeInfo:
    """Encode the review proxy and return the facts of the file actually written."""
    source = probe_file(input_path)
    height = _target_height(source.display_height, options.max_height)
    result = _run(
        [
            _binary("ffmpeg"),
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(input_path),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-vf",
            f"scale=-2:{height}",
            "-c:v",
            "libx264",
            "-preset",
            options.preset,
            "-crf",
            str(options.crf),
            "-pix_fmt",
            "yuv420p",
            "-profile:v",
            "high",
            "-movflags",
            "+faststart",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ac",
            "2",
            str(output_path),
        ]
    )
    if result.returncode != 0 or not output_path.exists():
        raise MediaError("proxy_failed")
    written = probe_file(output_path)
    if (
        written.duration_ms != source.duration_ms
        and abs(written.duration_ms - source.duration_ms) > 100
    ):
        # One frame of rounding is normal; a real length change is a bug.
        raise MediaError("proxy_duration_drift")
    return written


def make_poster(
    input_path: Path,
    output_path: Path,
    *,
    duration_ms: int,
    source_height: int,
    at_ms: int | None,
    max_height: int = 720,
) -> MediaFacts:
    """One real decoded frame, never the first black frame by accident."""
    moment = at_ms if at_ms is not None else max(0, (duration_ms * 10) // 100)
    moment = min(max(0, moment), max(0, duration_ms - 100))
    height = _target_height(source_height, max_height)
    result = _run(
        [
            _binary("ffmpeg"),
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-ss",
            f"{moment / 1000:.3f}",
            "-i",
            str(input_path),
            "-frames:v",
            "1",
            "-vf",
            f"scale=-2:{height}",
            "-q:v",
            "3",
            "-f",
            "image2",
            str(output_path),
        ]
    )
    if result.returncode != 0 or not output_path.exists() or output_path.stat().st_size == 0:
        raise MediaError("poster_failed")

    data = ffprobe_json(output_path)
    streams = data.get("streams")
    stream = (
        streams[0] if isinstance(streams, list) and streams and isinstance(streams[0], dict) else {}
    )
    return MediaFacts(
        width=int(stream.get("width") or 0),
        height=int(stream.get("height") or 0),
        duration_ms=duration_ms,
        fps_num=1,
        fps_den=1,
    )


def proxy_facts(written: ProbeInfo, size_bytes: int) -> ProxyFacts:
    return ProxyFacts(
        width=written.display_width,
        height=written.display_height,
        duration_ms=written.duration_ms,
        fps_num=written.fps_num,
        fps_den=written.fps_den,
        bytes=size_bytes,
    )


def ffmpeg_version() -> str:
    try:
        result = _run([_binary("ffmpeg"), "-version"], timeout=10)
    except MediaError:
        return "missing"
    first_line = result.stdout.splitlines()[0] if result.stdout else ""
    return first_line.strip() or "unknown"
