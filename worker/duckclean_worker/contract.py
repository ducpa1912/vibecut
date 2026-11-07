"""Worker wire contract (M0).

One Docker image serves both modes:

    GET  /health
    POST /v1/probe
    POST /v1/dissect
    POST /v1/detect
    POST /v1/render
    POST /v1/preview
    POST /v1/cancel

Rules enforced here, not in each route:

* Every call is idempotent by `job_id`; a repeated job returns the stored
  result instead of recomputing.
* Every response reports `usage`: compute seconds, device class, model versions
  and byte counts. The API bills from these numbers.
* `range_mode` is `ranges` or `whole_source`. An empty range list is invalid and
  never means "the whole video".
* Beat spans are half-open `[start_frame, end_frame)` and must tile the source
  exactly once, so concat cannot drop or duplicate a frame.
* Times crossing the wire are integer milliseconds and frame indices. Seconds
  appear only as derived convenience fields, never in a hash.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

CONTRACT_VERSION = "1.0.0"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeviceClass(StrEnum):
    CPU = "cpu"
    GPU_STANDARD = "gpu_standard"
    GPU_PREMIUM = "gpu_premium"


class JobKind(StrEnum):
    PROBE = "probe"
    DISSECT = "dissect"
    DETECT = "detect"
    RENDER = "render"
    PREVIEW = "preview"


class JobStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FillEngine(StrEnum):
    AUTO = "auto"
    BLUR = "blur"
    LAMA = "lama"
    PROPAINTER = "propainter"
    GENERATIVE = "generative"
    COVER = "cover"


class RangeMode(StrEnum):
    RANGES = "ranges"
    WHOLE_SOURCE = "whole_source"


class Provenance(StrEnum):
    OCR = "ocr"
    LOGO = "logo"
    USER_BOX = "user_box"
    MANUAL = "manual"


class BeatBoundary(StrEnum):
    START = "start"
    SCENE = "scene"
    CAP = "cap"
    END = "end"


class GroupKind(StrEnum):
    TEXT = "text"
    LOGO = "logo"
    WATERMARK = "watermark"
    IMAGE = "image"
    USER_BOX = "user_box"


class WarningCode(StrEnum):
    SCAN_TRUNCATED = "scan_truncated"
    OCR_UNAVAILABLE = "ocr_unavailable"
    LOGO_MODEL_UNAVAILABLE = "logo_model_unavailable"
    FRAME_CAP = "frame_cap"
    LOW_CONFIDENCE_ONLY = "low_confidence_only"


class WorkerErrorCode(StrEnum):
    INVALID_SIGNATURE = "invalid_signature"
    CLOCK_SKEW = "clock_skew"
    PAYLOAD_INVALID = "payload_invalid"
    SOURCE_UNREADABLE = "source_unreadable"
    MODEL_UNAVAILABLE = "model_unavailable"
    JOB_NOT_FOUND = "job_not_found"
    CANCELLED = "cancelled"
    RENDER_FAILED = "render_failed"
    STORAGE_FAILED = "storage_failed"
    INTERNAL = "internal"


# --------------------------------------------------------------- primitives


class Box(StrictModel):
    """Integer pixel box in the source display frame (rotation applied)."""

    x: Annotated[int, Field(ge=0)]
    y: Annotated[int, Field(ge=0)]
    w: Annotated[int, Field(ge=1)]
    h: Annotated[int, Field(ge=1)]


class FrameRange(StrictModel):
    """Half-open span [start_frame, end_frame) inside one beat."""

    beat_id: UUID
    beat_index: Annotated[int, Field(ge=0)]
    start_frame: Annotated[int, Field(ge=0)]
    end_frame: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def _non_empty(self) -> FrameRange:
        if self.end_frame <= self.start_frame:
            raise ValueError("range must be non-empty: end_frame > start_frame")
        return self


class PresignedUrl(StrictModel):
    url: str
    method: Literal["GET", "PUT"] = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    expires_at: datetime
    bytes: Annotated[int, Field(ge=0)] | None = None


class Usage(StrictModel):
    """Billing truth. The API writes one ledger row from this."""

    compute_seconds: Annotated[float, Field(ge=0)]
    device_class: DeviceClass
    model_versions: dict[str, str] = Field(default_factory=dict)
    input_bytes: Annotated[int, Field(ge=0)] = 0
    output_bytes: Annotated[int, Field(ge=0)] = 0


class CallbackTarget(StrictModel):
    url: str
    secret_id: str


class WorkerError(StrictModel):
    code: WorkerErrorCode
    message: str
    detail: dict[str, object] = Field(default_factory=dict)
    retryable: bool = False


class WorkerErrorEnvelope(StrictModel):
    error: WorkerError


# --------------------------------------------------------------- health/probe


class ModelState(StrictModel):
    """A missing model is reported, never silently skipped."""

    name: str
    version: str | None = None
    available: bool
    reason: str | None = None


class HealthResponse(StrictModel):
    status: Literal["ok", "degraded"]
    contract_version: str
    git_sha: str
    device_class: DeviceClass
    ffmpeg_version: str
    models: list[ModelState]
    busy: bool
    active_jobs: Annotated[int, Field(ge=0)]
    disk_free_bytes: Annotated[int, Field(ge=0)]


class ProbeInfo(StrictModel):
    duration_ms: Annotated[int, Field(ge=1)]
    display_width: Annotated[int, Field(ge=1)]
    display_height: Annotated[int, Field(ge=1)]
    coded_width: Annotated[int, Field(ge=1)] | None = None
    coded_height: Annotated[int, Field(ge=1)] | None = None
    rotation: Literal[0, 90, 180, 270] = 0
    fps_num: Annotated[int, Field(ge=1)]
    fps_den: Annotated[int, Field(ge=1)] = 1
    frame_count: Annotated[int, Field(ge=1)]
    video_codec: str
    pixel_format: str
    audio_codec: str | None = None
    has_audio: bool
    bit_rate: int | None = None


class ProbeRequest(StrictModel):
    job_id: UUID
    input: PresignedUrl
    callback: CallbackTarget | None = None


class ProbeResponse(StrictModel):
    job_id: UUID
    status: JobStatus
    probe: ProbeInfo
    usage: Usage


# --------------------------------------------------------------------- proxy


class ProxyOptions(StrictModel):
    """Review proxy: small, fast to start, visually faithful, never the output."""

    max_height: Annotated[int, Field(ge=144, le=2160)] = 720
    crf: Annotated[int, Field(ge=18, le=32)] = 26
    preset: Literal["ultrafast", "superfast", "veryfast", "faster", "fast"] = "veryfast"
    # Defaults to 10% of the duration, floored at 0.
    poster_at_ms: Annotated[int, Field(ge=0)] | None = None


class ProxyFacts(StrictModel):
    width: Annotated[int, Field(ge=1)]
    height: Annotated[int, Field(ge=1)]
    duration_ms: Annotated[int, Field(ge=1)]
    fps_num: Annotated[int, Field(ge=1)]
    fps_den: Annotated[int, Field(ge=1)]
    bytes: Annotated[int, Field(ge=0)]


class PosterFacts(StrictModel):
    width: Annotated[int, Field(ge=1)]
    height: Annotated[int, Field(ge=1)]
    bytes: Annotated[int, Field(ge=0)]
    frame_index: Annotated[int, Field(ge=0)] | None = None


class ProxyRequest(StrictModel):
    """Generate the review proxy and poster from the verified source."""

    job_id: UUID
    input: PresignedUrl
    output: PresignedUrl
    poster: PresignedUrl
    probe: ProbeInfo | None = None
    options: ProxyOptions = Field(default_factory=ProxyOptions)
    callback: CallbackTarget | None = None

    @model_validator(mode="after")
    def _writes_use_put(self) -> ProxyRequest:
        if self.output.method != "PUT" or self.poster.method != "PUT":
            raise ValueError("proxy output and poster must use presigned PUT URLs")
        return self


class ProxyResponse(StrictModel):
    job_id: UUID
    status: JobStatus
    proxy: ProxyFacts
    poster: PosterFacts
    usage: Usage


# ------------------------------------------------------------------- dissect


class BeatSpec(StrictModel):
    index: Annotated[int, Field(ge=0)]
    start_frame: Annotated[int, Field(ge=0)]
    end_frame: Annotated[int, Field(ge=1)]
    boundary: BeatBoundary


class DissectParams(StrictModel):
    max_seconds_milli: Annotated[int, Field(gt=0)] = 4000
    min_seconds_milli: Annotated[int, Field(gt=0)] = 1000
    scene_threshold_milli: Annotated[int, Field(ge=0, le=1000)] = 300
    scene_analysis_height: Annotated[int, Field(ge=120)] = 480

    @model_validator(mode="after")
    def _min_not_above_max(self) -> DissectParams:
        if self.min_seconds_milli > self.max_seconds_milli:
            raise ValueError("min_seconds_milli cannot exceed max_seconds_milli")
        return self


class DissectRequest(StrictModel):
    job_id: UUID
    input: PresignedUrl
    probe: ProbeInfo
    params: DissectParams = Field(default_factory=DissectParams)
    callback: CallbackTarget | None = None


class DissectResponse(StrictModel):
    job_id: UUID
    status: JobStatus
    beats: list[BeatSpec]
    beat_manifest_hash: str
    usage: Usage

    @model_validator(mode="after")
    def _beats_tile_source(self) -> DissectResponse:
        expected = 0
        for position, beat in enumerate(self.beats):
            if beat.index != position:
                raise ValueError(f"beat at position {position} has index {beat.index}")
            if beat.start_frame != expected:
                raise ValueError(
                    f"beat {beat.index} starts at frame {beat.start_frame}, expected {expected}"
                )
            if beat.end_frame <= beat.start_frame:
                raise ValueError(f"beat {beat.index} is empty")
            expected = beat.end_frame
        return self


# -------------------------------------------------------------------- detect


class DetectRegion(StrictModel):
    region_id: UUID | None = None
    box: Box
    prompt: str | None = Field(default=None, max_length=100)


class DetectOptions(StrictModel):
    text: bool = True
    logos: bool = True
    tile_small_text: bool = True
    tile_grid: Literal["2x2", "3x3"] = "2x2"
    frame_policy: Literal["every_frame"] = "every_frame"
    max_width: Annotated[int, Field(ge=320, le=3840)] = 1920
    min_confidence_milli: Annotated[int, Field(ge=0, le=1000)] = 350
    regions: list[DetectRegion] = Field(default_factory=list)


class DetectBeat(StrictModel):
    id: UUID
    index: Annotated[int, Field(ge=0)]
    start_frame: Annotated[int, Field(ge=0)]
    end_frame: Annotated[int, Field(ge=1)]


class DetectRequest(StrictModel):
    job_id: UUID
    input: PresignedUrl
    probe: ProbeInfo
    revision: str
    beats: list[DetectBeat]
    detect: DetectOptions = Field(default_factory=DetectOptions)
    callback: CallbackTarget | None = None


class MaskResult(StrictModel):
    """Masks are written to R2 and referenced, never returned as pixels."""

    mask_id: UUID
    r2_key: str
    format: Literal["png", "webp"]
    frame_start: Annotated[int, Field(ge=0)]
    frame_end: Annotated[int, Field(ge=0)]
    provenance: Provenance
    model_version: str
    bytes: Annotated[int, Field(ge=0)] = 0


class DetectedMember(StrictModel):
    member_id: UUID
    order_index: Annotated[int, Field(ge=0)] = 0
    text: str | None = None
    range_mode: RangeMode = RangeMode.RANGES
    ranges: list[FrameRange]
    box: Box
    confidence_milli: Annotated[int, Field(ge=0, le=1000)]
    provenance: Provenance
    mask: MaskResult | None = None
    included_default: bool = True
    low_confidence: bool = False
    fill_keys: list[Annotated[int, Field(ge=0)]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _ranges_never_mean_whole_source(self) -> DetectedMember:
        if self.range_mode is RangeMode.RANGES and not self.ranges:
            raise ValueError(
                "range_mode=ranges requires at least one range; empty ranges are not whole_source"
            )
        return self


class DetectedGroup(StrictModel):
    group_id: UUID
    kind: GroupKind
    lane: Annotated[int, Field(ge=0)] = 0
    order_index: Annotated[int, Field(ge=0)]
    sample_text: str | None = None
    box: Box
    confidence_milli: Annotated[int, Field(ge=0, le=1000)]
    included_default: bool = True
    low_confidence: bool = False
    members: list[DetectedMember]

    @model_validator(mode="after")
    def _member_count_matches(self) -> DetectedGroup:
        if not self.members:
            raise ValueError("a group must contain at least one member")
        return self


class DetectionCoverage(StrictModel):
    frames_total: Annotated[int, Field(ge=0)]
    frames_read: Annotated[int, Field(ge=0)]
    frames_skipped: Annotated[int, Field(ge=0)]
    effective_fps_milli: Annotated[int, Field(ge=0)]
    truncated: bool = False
    ocr_available: bool = True
    logo_model_available: bool = True
    warnings: list[WarningCode] = Field(default_factory=list)

    @model_validator(mode="after")
    def _read_plus_skipped_is_total(self) -> DetectionCoverage:
        if self.frames_read + self.frames_skipped != self.frames_total:
            raise ValueError("frames_read + frames_skipped must equal frames_total")
        return self


class DetectResponse(StrictModel):
    job_id: UUID
    status: JobStatus
    revision: str
    groups: list[DetectedGroup] = Field(default_factory=list)
    coverage: DetectionCoverage
    usage: Usage


# -------------------------------------------------------------------- render


class WorkerMaskRef(StrictModel):
    mask_id: UUID
    url: str
    format: Literal["png", "webp"]
    frame_start: Annotated[int, Field(ge=0)]
    frame_end: Annotated[int, Field(ge=0)]
    provenance: Provenance


class SelectionMember(StrictModel):
    member_id: UUID
    range_mode: RangeMode
    ranges: list[FrameRange]
    masks: list[WorkerMaskRef] = Field(default_factory=list)
    box: Box | None = None

    @model_validator(mode="after")
    def _ranges_never_mean_whole_source(self) -> SelectionMember:
        if self.range_mode is RangeMode.RANGES and not self.ranges:
            raise ValueError(
                "range_mode=ranges requires at least one range; empty ranges are not whole_source"
            )
        return self


class SelectionGroup(StrictModel):
    group_id: UUID
    kind: GroupKind
    engine: FillEngine
    device_class: DeviceClass
    members: list[SelectionMember]


class ManualRegion(StrictModel):
    region_id: UUID
    box: Box
    engine: FillEngine
    device_class: DeviceClass
    ranges: list[FrameRange]


class RenderSelection(StrictModel):
    detection_revision: str
    selection_revision: str
    groups: list[SelectionGroup]
    manual_regions: list[ManualRegion] = Field(default_factory=list)


class RenderBeat(StrictModel):
    """`mode` is decided by the API planner, not re-derived in the worker.

    fill: at least one selected range intersects this beat.
    passthrough: no target; encode with identical parameters and no model call.
    """

    id: UUID
    index: Annotated[int, Field(ge=0)]
    start_frame: Annotated[int, Field(ge=0)]
    end_frame: Annotated[int, Field(ge=1)]
    mode: Literal["fill", "passthrough"]


class RenderOutput(StrictModel):
    url: str
    method: Literal["PUT"] = "PUT"
    headers: dict[str, str] = Field(default_factory=dict)
    expires_at: datetime
    codec: Literal["h264"] = "h264"
    pixel_format: Literal["yuv420p"] = "yuv420p"
    crf: Annotated[int, Field(ge=0, le=51)] = 18
    preset: str = "medium"
    fps: Literal["source"] = "source"
    audio: Literal["source"] = "source"
    width: Annotated[int, Field(ge=1)]
    height: Annotated[int, Field(ge=1)]
    resolution_scale_milli: Annotated[int, Field(ge=100, le=1000)] = 1000
    time_limit_s: Annotated[int, Field(gt=0)] | None = None


class AssembleParams(StrictModel):
    strategy: Literal["parallel_beats"] = "parallel_beats"
    max_parallel: Annotated[int, Field(ge=1, le=16)] = 4


class RenderRequest(StrictModel):
    job_id: UUID
    kind: Literal["render"] = "render"
    input: PresignedUrl
    probe: ProbeInfo
    beats: list[RenderBeat]
    selection: RenderSelection
    output: RenderOutput
    assemble: AssembleParams = Field(default_factory=AssembleParams)
    callback: CallbackTarget | None = None


class PreviewRequest(StrictModel):
    job_id: UUID
    kind: Literal["preview"] = "preview"
    input: PresignedUrl
    probe: ProbeInfo
    beats: list[RenderBeat]
    selection: RenderSelection
    output: RenderOutput
    preview: PreviewOptions = Field(default_factory=lambda: PreviewOptions())
    callback: CallbackTarget | None = None


class PreviewOptions(StrictModel):
    """Preview is diagnostic playback, never presented as the final render."""

    engine: Literal["blur", "lama"] = "blur"
    time_limit_s: Annotated[int, Field(gt=0)] = 120


class RenderedSegment(StrictModel):
    beat_id: UUID
    beat_index: Annotated[int, Field(ge=0)]
    mode: Literal["fill", "passthrough"]
    status: Literal["done", "failed", "cancelled"]
    fill_engine: FillEngine | None = None
    fill_seconds: Annotated[float, Field(ge=0)] = 0.0
    encode_seconds: Annotated[float, Field(ge=0)] = 0.0
    compute_seconds: Annotated[float, Field(ge=0)] = 0.0
    output_bytes: Annotated[int, Field(ge=0)] = 0
    error: WorkerError | None = None


class RenderOutputFacts(StrictModel):
    bytes: Annotated[int, Field(ge=0)]
    duration_ms: Annotated[int, Field(ge=1)]
    width: Annotated[int, Field(ge=1)]
    height: Annotated[int, Field(ge=1)]
    fps_num: Annotated[int, Field(ge=1)]
    fps_den: Annotated[int, Field(ge=1)]
    has_audio: bool
    sha256: str


class RenderResponse(StrictModel):
    job_id: UUID
    status: JobStatus
    kind: Literal["render", "preview"]
    selection_revision: str
    segments: list[RenderedSegment]
    output: RenderOutputFacts | None = None
    usage: Usage


# -------------------------------------------------------------------- cancel


class CancelRequest(StrictModel):
    job_id: UUID


class CancelResponse(StrictModel):
    job_id: UUID
    cancelled: bool
    status: Literal["cancelling", "not_running", "already_finished"]
    usage: Usage


# ------------------------------------------------------------------ callbacks


class CallbackError(StrictModel):
    code: WorkerErrorCode
    message: str
    retryable: bool = False


class ProgressCallback(StrictModel):
    """At most one per second per job. `seq` is monotonic and deduped by the API."""

    job_id: UUID
    seq: Annotated[int, Field(ge=1)]
    kind: JobKind
    status: JobStatus
    stage: str | None = None
    progress: Annotated[float, Field(ge=0, le=1)]
    stage_detail: str | None = Field(default=None, max_length=200)
    compute_seconds: Annotated[float, Field(ge=0)]
    device_class: DeviceClass
    model_versions: dict[str, str] = Field(default_factory=dict)
    input_bytes: Annotated[int, Field(ge=0)] = 0
    output_bytes: Annotated[int, Field(ge=0)] = 0
    beats_done: Annotated[int, Field(ge=0)] | None = None
    beats_total: Annotated[int, Field(ge=0)] | None = None
    frames_read: Annotated[int, Field(ge=0)] | None = None
    error: CallbackError | None = None


PreviewRequest.model_rebuild()
