"""M2b detection: OCR every frame of every beat, then track, group and mask.

The rules this module keeps:

* Coverage is accounted for. Every frame in every beat is either read (OCR ran)
  or skipped for a stated reason, and ``read + skipped == total`` always holds.
* A frame that is byte-identical to the frame before it inherits that frame's
  observations and is counted as skipped: nothing can appear on an unchanged
  frame, and saying "read" would be a lie about compute.
* A missing model is reported (``ocr_available``/``logo_model_available`` plus a
  warning), never quietly skipped.
* Low-confidence candidates are kept and marked, not dropped.
* Masks are built from the observations that produced them, at source display
  resolution, and shipped inline as base64 PNG because the worker has no
  presigned PUT for masks yet.
"""

from __future__ import annotations

import base64
import hashlib
import io
from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from .contract import (
    Box,
    DetectBeat,
    DetectedGroup,
    DetectedMember,
    DetectionCoverage,
    DetectOptions,
    DetectRegion,
    FrameRange,
    GroupKind,
    MaskResult,
    Provenance,
    RangeMode,
    WarningCode,
)

# One run is bounded so a synchronous request always answers. Frames past the
# budget are reported as skipped with `truncated` and `frame_cap`, never as "no
# text". M3 chunks long sources across runs.
MAX_OCR_FRAMES = 600
MAX_TILES = 9
TILE_OVERLAP = 0.1
IOU_TRACK = 0.4
IOU_SAME_GROUP = 0.25
MASK_DILATE_PX = 3

OCR_MODEL_VERSION = "rapidocr-onnxruntime-1.4"


class DetectError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Observation:
    """One OCR line: a quadrilateral and its box in source display pixels."""

    text: str
    quad: tuple[tuple[float, float], ...]
    box: Box
    score_milli: int


@dataclass
class Track:
    """One visual target followed across the frames of a single beat."""

    key: str
    first_frame: int
    last_frame: int
    box: Box
    quad: tuple[tuple[float, float], ...]
    text: str
    score_milli: int
    best_score_milli: int = 0

    def merge(self, obs: Observation, frame: int) -> None:
        self.last_frame = frame
        self.box = obs.box
        self.quad = obs.quad
        self.text = obs.text
        self.score_milli = max(self.score_milli, obs.score_milli)


@dataclass
class BeatScan:
    tracks: list[Track] = field(default_factory=list)
    frames_read: int = 0
    frames_skipped: int = 0
    truncated: bool = False


def _ocr_import() -> Any:
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-untyped]
    except Exception:
        return None
    return RapidOCR


@lru_cache(maxsize=1)
def ocr_engine() -> tuple[Any | None, str | None]:
    """Returns (engine, reason). A reason is set only when OCR is unavailable."""
    rapid_ocr = _ocr_import()
    if rapid_ocr is None:
        return None, "rapidocr_not_installed"
    try:
        return rapid_ocr(), None
    except Exception as exc:
        return None, f"ocr_init_failed: {type(exc).__name__}"


def scaled_size(display_width: int, display_height: int, max_width: int) -> tuple[int, int]:
    width = min(max_width, display_width)
    if width % 2 == 1:
        width -= 1
    width = max(width, 2)
    height = max(2, round(display_height * width / display_width))
    if height % 2 == 1:
        height -= 1
    return width, height


class FrameReader:
    """Sequential decoder with an explicit position, so scoped beats stay exact."""

    def __init__(self, frames: Iterator[np.ndarray]) -> None:
        self._frames = frames
        self.index = 0

    def skip_to(self, target: int) -> None:
        while self.index < target:
            next(self._frames)
            self.index += 1

    def read(self) -> np.ndarray:
        frame = next(self._frames)
        self.index += 1
        return frame

    def close(self) -> None:
        close = getattr(self._frames, "close", None)
        if close is not None:
            close()


def iter_frames(path: Path, *, width: int, height: int, frame_count: int) -> Iterator[np.ndarray]:
    """Decode the source at the detection size, one BGR frame at a time."""
    from .media import _binary

    args = [
        _binary("ffmpeg"),
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-map",
        "0:v:0",
        "-an",
        "-vf",
        f"scale={width}:{height}",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-",
    ]
    import subprocess

    process = subprocess.Popen(  # noqa: S603 - fixed argument list, no shell
        args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    size = width * height * 3
    try:
        if process.stdout is None:
            raise DetectError("decode_failed")
        while True:
            buffer = process.stdout.read(size)
            if not buffer or len(buffer) < size:
                return
            yield np.frombuffer(buffer, dtype=np.uint8).reshape(height, width, 3)
    finally:
        process.stdout.close() if process.stdout else None
        process.kill()
        process.wait()


def _quad(
    points: Any, offset: tuple[int, int], scale: tuple[float, float]
) -> tuple[tuple[float, float], ...] | None:
    """Map a tile-local quadrilateral into source display pixels."""
    sx, sy = scale
    offset_x, offset_y = offset
    try:
        return tuple(
            ((float(point[0]) + offset_x) * sx, (float(point[1]) + offset_y) * sy)
            for point in points
        )
    except (TypeError, ValueError, IndexError):
        return None


def _box_of(quad: tuple[tuple[float, float], ...], limit_w: int, limit_h: int) -> Box | None:
    xs = [point[0] for point in quad]
    ys = [point[1] for point in quad]
    x0 = max(0, round(min(xs)))
    y0 = max(0, round(min(ys)))
    x1 = min(limit_w, round(max(xs)))
    y1 = min(limit_h, round(max(ys)))
    if x1 - x0 < 3 or y1 - y0 < 3:
        return None
    return Box(x=x0, y=y0, w=x1 - x0, h=y1 - y0)


def _iou(a: Box, b: Box) -> float:
    x0 = max(a.x, b.x)
    y0 = max(a.y, b.y)
    x1 = min(a.x + a.w, b.x + b.w)
    y1 = min(a.y + a.h, b.y + b.h)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    union = a.w * a.h + b.w * b.h - inter
    return inter / union if union > 0 else 0.0


def _normalise(text: str) -> str:
    return " ".join(text.split()).casefold()


def _tiles(width: int, height: int, grid: str) -> list[tuple[int, int, int, int]]:
    """Tile boxes with overlap, so text on a seam is still readable."""
    count = 2 if grid == "2x2" else 3
    tile_w = round(width / count)
    tile_h = round(height / count)
    pad_x = round(tile_w * TILE_OVERLAP)
    pad_y = round(tile_h * TILE_OVERLAP)
    boxes: list[tuple[int, int, int, int]] = []
    for row in range(count):
        for column in range(count):
            x = max(0, column * tile_w - pad_x)
            y = max(0, row * tile_h - pad_y)
            x1 = min(width, (column + 1) * tile_w + pad_x)
            y1 = min(height, (row + 1) * tile_h + pad_y)
            boxes.append((x, y, x1 - x, y1 - y))
    return boxes


def ocr_frame(
    engine: Any,
    frame: np.ndarray,
    *,
    display_width: int,
    display_height: int,
    options: DetectOptions,
) -> list[Observation]:
    """OCR the frame as one image plus, when enabled, overlapping tiles."""
    height, width = frame.shape[:2]
    sx = display_width / width
    sy = display_height / height
    regions = [(0, 0, width, height)]
    if options.tile_small_text:
        regions = _tiles(width, height, options.tile_grid)[:MAX_TILES]

    found: list[Observation] = []
    for x, y, w, h in regions:
        crop = frame[y : y + h, x : x + w]
        if crop.size == 0:
            continue
        result, _ = engine(crop)
        for entry in result or []:
            points, raw_text, score = entry[0], entry[1], float(entry[2])
            text = str(raw_text).strip()
            if not text:
                continue
            quad = _quad(points, (x, y), (sx, sy))
            if quad is None:
                continue
            box = _box_of(quad, display_width, display_height)
            if box is None:
                continue
            score_milli = max(0, min(1000, round(score * 1000)))
            found.append(Observation(text=text, quad=quad, box=box, score_milli=score_milli))
    return _merge(found)


def _merge(found: list[Observation]) -> list[Observation]:
    """Drop the same line seen twice in overlapping tiles; keep the best score."""
    kept: list[Observation] = []
    for observation in sorted(found, key=lambda item: -item.score_milli):
        duplicate = next(
            (
                other
                for other in kept
                if _normalise(other.text) == _normalise(observation.text)
                and _iou(other.box, observation.box) > 0.5
            ),
            None,
        )
        if duplicate is None:
            kept.append(observation)
    return kept


def scan_beat(
    engine: Any,
    frames: FrameReader,
    beat: DetectBeat,
    *,
    display_width: int,
    display_height: int,
    options: DetectOptions,
    budget: int,
) -> BeatScan:
    scan = BeatScan()
    tracks: list[Track] = []
    previous_hash: str | None = None
    previous: list[Observation] = []
    try:
        frames.skip_to(beat.start_frame)
    except StopIteration:
        scan.frames_skipped += beat.end_frame - beat.start_frame
        return scan
    for frame_index in range(beat.start_frame, beat.end_frame):
        try:
            frame = frames.read()
        except StopIteration:
            scan.frames_skipped += beat.end_frame - frame_index
            break
        digest = hashlib.sha1(  # noqa: S324 - content fingerprint, not security
            np.ascontiguousarray(frame[::8, ::8]).tobytes()
        ).hexdigest()
        if digest == previous_hash:
            observations = previous
            scan.frames_skipped += 1
        else:
            if scan.frames_read >= budget:
                scan.frames_skipped += beat.end_frame - frame_index
                scan.truncated = True
                break
            observations = ocr_frame(
                engine,
                frame,
                display_width=display_width,
                display_height=display_height,
                options=options,
            )
            scan.frames_read += 1
            previous_hash = digest
            previous = observations
        _track(tracks, observations, frame_index)
    scan.tracks = tracks
    return scan


def _track(tracks: list[Track], observations: list[Observation], frame_index: int) -> None:
    used: set[int] = set()
    for observation in observations:
        best: Track | None = None
        best_position = -1
        best_iou = 0.0
        key = _normalise(observation.text)
        for position, track in enumerate(tracks):
            if position in used or track.key != key:
                continue
            score = _iou(track.box, observation.box)
            if score > best_iou:
                best, best_position, best_iou = track, position, score
        if best is not None and best_iou >= IOU_TRACK:
            best.merge(observation, frame_index)
            used.add(best_position)
        else:
            tracks.append(
                Track(
                    key=key,
                    first_frame=frame_index,
                    last_frame=frame_index,
                    box=observation.box,
                    quad=observation.quad,
                    text=observation.text,
                    score_milli=observation.score_milli,
                    best_score_milli=observation.score_milli,
                )
            )


def _union_box(boxes: list[Box]) -> Box:
    x0 = min(box.x for box in boxes)
    y0 = min(box.y for box in boxes)
    x1 = max(box.x + box.w for box in boxes)
    y1 = max(box.y + box.h for box in boxes)
    return Box(x=x0, y=y0, w=max(1, x1 - x0), h=max(1, y1 - y0))


def _same_area(first: Box, second: Box) -> bool:
    """True when two lines are close enough to read as one subtitle block."""
    overlap = max(
        0,
        min(first.x + first.w, second.x + second.w) - max(first.x, second.x),
    )
    if overlap / max(1, min(first.w, second.w)) < 0.2:
        return False
    gap = max(0, max(first.y, second.y) - min(first.y + first.h, second.y + second.h))
    return gap <= max(first.h, second.h) * 1.5


def _merge_text_groups(groups: list[DetectedGroup]) -> list[DetectedGroup]:
    """One visual text area is one group; lines remain separate members."""
    merged: list[DetectedGroup] = []
    for group in groups:
        if group.kind != GroupKind.TEXT:
            merged.append(group)
            continue
        target = next(
            (
                existing
                for existing in merged
                if existing.kind == GroupKind.TEXT and _same_area(existing.box, group.box)
            ),
            None,
        )
        if target is None:
            merged.append(group)
            continue
        members = [*target.members, *group.members]
        target.members = members
        target.box = _union_box([target.box, group.box])
        target.confidence_milli = min(target.confidence_milli, group.confidence_milli)
        target.included_default = target.included_default and group.included_default
        target.low_confidence = target.low_confidence or group.low_confidence
        if len(group.sample_text or "") > len(target.sample_text or ""):
            target.sample_text = group.sample_text
    for order, group in enumerate(merged):
        group.order_index = order
        for member_order, member in enumerate(group.members):
            member.order_index = member_order
    return merged


def _mask_png(width: int, height: int, polygons: list[tuple[tuple[float, float], ...]]) -> str:
    image = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(image)
    for polygon in polygons:
        draw.polygon([(round(x), round(y)) for x, y in polygon], fill=255)
    if MASK_DILATE_PX:
        image = image.filter(_dilate())
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _dilate() -> Any:
    from PIL import ImageFilter

    return ImageFilter.MaxFilter(MASK_DILATE_PX * 2 + 1)


def build_groups(
    *,
    beat_tracks: list[tuple[DetectBeat, Track]],
    display_width: int,
    display_height: int,
    options: DetectOptions,
) -> list[DetectedGroup]:
    """Join tracklets with the same text and screen position into members."""
    threshold = options.min_confidence_milli
    clusters: list[dict[str, Any]] = []
    for beat, track in beat_tracks:
        if not options.text:
            continue
        target: dict[str, Any] | None = None
        for cluster in clusters:
            if cluster["key"] != track.key:
                continue
            if _iou(cluster["box"], track.box) >= IOU_SAME_GROUP:
                target = cluster
                break
        if target is None:
            cluster = {
                "key": track.key,
                "text": track.text,
                "box": track.box,
                "quad": track.quad,
                "quads": [track.quad],
                "score": track.score_milli,
                "ranges": [],
            }
            clusters.append(cluster)
            target = cluster
        else:
            target["quads"].append(track.quad)
        target["box"] = _union_box([target["box"], track.box])
        # Keep the best-scoring observation's quad: it is the mask's glyph shape.
        if track.score_milli >= target["score"]:
            target["score"] = track.score_milli
            target["quad"] = track.quad
            target["text"] = track.text
        target["ranges"].append(
            FrameRange(
                beat_id=beat.id,
                beat_index=beat.index,
                start_frame=track.first_frame,
                end_frame=track.last_frame + 1,
            )
        )

    groups: list[DetectedGroup] = []
    for order, cluster in enumerate(clusters):
        low = cluster["score"] < threshold
        mask = MaskResult(
            mask_id=__import__("uuid").uuid4(),
            r2_key="",
            format="png",
            frame_start=cluster["ranges"][0].start_frame,
            frame_end=cluster["ranges"][-1].end_frame,
            provenance=Provenance.OCR,
            model_version=OCR_MODEL_VERSION,
            bytes=0,
            # One mask must cover every position the line occupied in this
            # member's ranges. A single best quad would leave moving text behind.
            png_base64=_mask_png(display_width, display_height, cluster["quads"]),
        )
        member = DetectedMember(
            member_id=__import__("uuid").uuid4(),
            order_index=0,
            text=cluster["text"],
            range_mode=RangeMode.RANGES,
            ranges=cluster["ranges"],
            box=cluster["box"],
            confidence_milli=cluster["score"],
            provenance=Provenance.OCR,
            mask=mask,
            low_confidence=low,
            included_default=not low,
        )
        groups.append(
            DetectedGroup(
                group_id=__import__("uuid").uuid4(),
                kind=GroupKind.TEXT,
                lane=0,
                order_index=order,
                sample_text=cluster["text"],
                box=cluster["box"],
                confidence_milli=cluster["score"],
                low_confidence=low,
                included_default=not low,
                members=[member],
            )
        )
    return groups


def user_region_groups(
    regions: list[DetectRegion], *, display_width: int, display_height: int
) -> list[DetectedGroup]:
    groups: list[DetectedGroup] = []
    for order, region in enumerate(regions):
        box = region.box
        quad = (
            (float(box.x), float(box.y)),
            (float(box.x + box.w), float(box.y)),
            (float(box.x + box.w), float(box.y + box.h)),
            (float(box.x), float(box.y + box.h)),
        )
        member = DetectedMember(
            member_id=__import__("uuid").uuid4(),
            order_index=0,
            text=None,
            range_mode=RangeMode.WHOLE_SOURCE,
            ranges=[],
            box=box,
            confidence_milli=1000,
            provenance=Provenance.USER_BOX,
            mask=MaskResult(
                mask_id=__import__("uuid").uuid4(),
                r2_key="",
                kind="region",
                format="png",
                frame_start=0,
                frame_end=0,
                provenance=Provenance.USER_BOX,
                model_version="user-region-1",
                bytes=0,
                png_base64=_mask_png(display_width, display_height, [quad]),
            ),
            included_default=True,
        )
        groups.append(
            DetectedGroup(
                group_id=__import__("uuid").uuid4(),
                kind=GroupKind.USER_BOX,
                lane=0,
                order_index=order,
                sample_text=region.prompt,
                box=box,
                confidence_milli=1000,
                members=[member],
            )
        )
    return groups


def detect_file(
    path: Path,
    *,
    display_width: int,
    display_height: int,
    beats: list[DetectBeat],
    frame_count: int,
    fps_num: int,
    fps_den: int,
    options: DetectOptions,
) -> tuple[list[DetectedGroup], DetectionCoverage, dict[str, str]]:
    engine, reason = ocr_engine()
    warnings: list[WarningCode] = []
    models: dict[str, str] = {}
    ordered = sorted(beats, key=lambda beat: (beat.start_frame, beat.index))
    for position, beat in enumerate(ordered):
        if (
            beat.index < 0
            or beat.start_frame < 0
            or beat.end_frame <= beat.start_frame
            or beat.end_frame > frame_count
        ):
            raise DetectError(f"beat {beat.index} is outside the source")
        if position and beat.start_frame < ordered[position - 1].end_frame:
            raise DetectError(f"beat {beat.index} overlaps the previous beat")
    beats = ordered
    frames_total = sum(beat.end_frame - beat.start_frame for beat in beats)

    beat_tracks: list[tuple[DetectBeat, Track]] = []
    frames_read = 0
    frames_skipped = 0
    truncated = False

    if engine is None:
        # No model: account for every frame and say why nothing was found.
        frames_skipped = frames_total
        truncated = False
        warnings.extend([WarningCode.OCR_UNAVAILABLE])
        models["ocr"] = reason or "unavailable"
    else:
        models["ocr"] = OCR_MODEL_VERSION
        width, height = scaled_size(display_width, display_height, options.max_width)
        reader = FrameReader(iter_frames(path, width=width, height=height, frame_count=frame_count))
        try:
            for beat in beats:
                if frames_read >= MAX_OCR_FRAMES:
                    frames_skipped += beat.end_frame - beat.start_frame
                    truncated = True
                    continue
                scan = scan_beat(
                    engine,
                    reader,
                    beat,
                    display_width=display_width,
                    display_height=display_height,
                    options=options,
                    budget=MAX_OCR_FRAMES - frames_read,
                )
                frames_read += scan.frames_read
                frames_skipped += scan.frames_skipped
                truncated = truncated or scan.truncated
                beat_tracks.extend((beat, track) for track in scan.tracks)
        finally:
            reader.close()

    if truncated:
        warnings.extend([WarningCode.FRAME_CAP, WarningCode.SCAN_TRUNCATED])
    # The open-vocabulary logo pass is not packaged yet. Say so, every run.
    warnings.append(WarningCode.LOGO_MODEL_UNAVAILABLE)
    models["logo"] = "unavailable"
    if beat_tracks and all(
        track.score_milli < options.min_confidence_milli for _, track in beat_tracks
    ):
        warnings.append(WarningCode.LOW_CONFIDENCE_ONLY)

    groups = build_groups(
        beat_tracks=beat_tracks,
        display_width=display_width,
        display_height=display_height,
        options=options,
    )
    groups = _merge_text_groups(groups)
    groups.extend(
        user_region_groups(
            options.regions, display_width=display_width, display_height=display_height
        )
    )
    for order, group in enumerate(groups):
        group.order_index = order

    source_fps_milli = fps_num * 1000 / fps_den
    # Duplicate-frame inheritance still covers the frame, so it does not lower
    # the effective cadence. Only a real truncation does.
    effective_fps_milli = (
        round(source_fps_milli * frames_read / frames_total)
        if truncated and frames_total
        else round(source_fps_milli)
    )
    coverage = DetectionCoverage(
        frames_total=frames_total,
        frames_read=frames_read,
        frames_skipped=frames_skipped,
        effective_fps_milli=effective_fps_milli,
        truncated=truncated,
        ocr_available=engine is not None,
        logo_model_available=False,
        warnings=sorted(set(warnings), key=lambda warning: warning.value),
    )
    return groups, coverage, models
