from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from duckclean_worker.contract import (
    CONTRACT_VERSION,
    BeatBoundary,
    BeatSpec,
    Box,
    DetectedGroup,
    DetectedMember,
    DetectionCoverage,
    DetectResponse,
    DeviceClass,
    DissectParams,
    DissectResponse,
    FillEngine,
    FrameRange,
    GroupKind,
    JobStatus,
    ManualRegion,
    PresignedUrl,
    ProbeInfo,
    Provenance,
    RangeMode,
    RenderBeat,
    RenderedSegment,
    RenderOutput,
    RenderRequest,
    RenderSelection,
    SelectionGroup,
    SelectionMember,
    Usage,
)
from pydantic import ValidationError


def usage() -> Usage:
    return Usage(compute_seconds=12.5, device_class=DeviceClass.CPU, model_versions={"ocr": "x"})


def probe() -> ProbeInfo:
    return ProbeInfo(
        duration_ms=5572,
        display_width=1440,
        display_height=2560,
        fps_num=30,
        frame_count=167,
        video_codec="hevc",
        pixel_format="yuv420p",
        has_audio=True,
    )


def member(*, ranges: list[FrameRange], range_mode: RangeMode = RangeMode.RANGES) -> DetectedMember:
    return DetectedMember(
        member_id=uuid4(),
        text="HELLO",
        range_mode=range_mode,
        ranges=ranges,
        box=Box(x=100, y=900, w=600, h=80),
        confidence_milli=940,
        provenance=Provenance.OCR,
    )


def test_contract_version_is_exposed() -> None:
    assert CONTRACT_VERSION == "1.0.0"


def test_detect_response_accepts_a_real_group() -> None:
    frame_range = FrameRange(beat_id=uuid4(), beat_index=0, start_frame=10, end_frame=40)
    group = DetectedGroup(
        group_id=uuid4(),
        kind=GroupKind.TEXT,
        order_index=0,
        sample_text="HELLO",
        box=Box(x=100, y=900, w=600, h=80),
        confidence_milli=940,
        members=[member(ranges=[frame_range])],
    )
    response = DetectResponse(
        job_id=uuid4(),
        status=JobStatus.SUCCEEDED,
        revision="a" * 64,
        groups=[group],
        coverage=DetectionCoverage(
            frames_total=167, frames_read=167, frames_skipped=0, effective_fps_milli=30000
        ),
        usage=usage(),
    )
    assert response.groups[0].members[0].ranges[0].end_frame == 40


def test_ranges_mode_with_no_ranges_is_rejected() -> None:
    with pytest.raises(ValidationError, match="not whole_source"):
        member(ranges=[])


def test_whole_source_requires_an_explicit_marker() -> None:
    parsed = member(ranges=[], range_mode=RangeMode.WHOLE_SOURCE)
    assert parsed.range_mode is RangeMode.WHOLE_SOURCE


def test_empty_ranges_do_not_mean_whole_source() -> None:
    with pytest.raises(ValidationError):
        FrameRange(beat_id=uuid4(), beat_index=0, start_frame=30, end_frame=30)


def test_dissect_beats_must_tile_the_source() -> None:
    beats = [
        BeatSpec(index=0, start_frame=0, end_frame=60, boundary=BeatBoundary.START),
        BeatSpec(index=1, start_frame=61, end_frame=120, boundary=BeatBoundary.END),
    ]
    with pytest.raises(ValidationError, match="starts at frame 61"):
        DissectResponse(
            job_id=uuid4(),
            status=JobStatus.SUCCEEDED,
            beats=beats,
            source_sha256="f" * 64,
            usage=usage(),
        )


def test_dissect_params_reject_min_above_max() -> None:
    with pytest.raises(ValidationError):
        DissectParams(min_seconds_milli=5000, max_seconds_milli=4000)


def test_coverage_accounts_for_every_frame() -> None:
    with pytest.raises(ValidationError, match="frames_read"):
        DetectionCoverage(
            frames_total=100, frames_read=90, frames_skipped=5, effective_fps_milli=30000
        )


def test_render_beat_mode_is_explicit() -> None:
    parsed = RenderBeat(id=uuid4(), index=0, start_frame=0, end_frame=30, mode="passthrough")
    assert parsed.mode == "passthrough"
    with pytest.raises(ValidationError):
        RenderBeat.model_validate(
            {"id": str(uuid4()), "index": 0, "start_frame": 0, "end_frame": 30, "mode": "maybe"}
        )


def test_render_request_carries_masks_and_source_audio() -> None:
    request = RenderRequest(
        job_id=uuid4(),
        input=PresignedUrl(
            url="https://r2.example/source.mp4?sig=1",
            expires_at=datetime(2026, 11, 7, 12, 0, tzinfo=UTC),
        ),
        probe=probe(),
        beats=[RenderBeat(id=uuid4(), index=0, start_frame=0, end_frame=167, mode="fill")],
        selection=RenderSelection(
            detection_revision="a" * 64,
            selection_revision="b" * 64,
            groups=[],
            manual_regions=[],
        ),
        output=RenderOutput(
            url="https://r2.example/out.mp4?sig=2",
            expires_at=datetime(2026, 11, 7, 12, 0, tzinfo=UTC),
            width=1440,
            height=2560,
        ),
    )
    assert request.output.codec == "h264"
    assert request.output.audio == "source"
    assert request.assemble.max_parallel == 4


def test_selection_member_honours_the_range_rule() -> None:
    with pytest.raises(ValidationError):
        SelectionMember(member_id=uuid4(), range_mode=RangeMode.RANGES, ranges=[])


def test_every_job_response_reports_usage() -> None:
    from duckclean_worker.contract import DetectResponse, DissectResponse, ProbeResponse

    for response_model in (ProbeResponse, DissectResponse, DetectResponse):
        assert "usage" in response_model.model_fields
    assert FillEngine.BLUR.value == "blur"


def test_rendered_segment_defaults_do_not_invent_work() -> None:
    segment = RenderedSegment(beat_id=uuid4(), beat_index=0, mode="passthrough", status="done")
    assert segment.fill_engine is None
    assert segment.fill_seconds == 0.0


def test_lama_is_cpu_only() -> None:
    group = SelectionGroup(
        group_id=uuid4(),
        kind=GroupKind.TEXT,
        engine=FillEngine.LAMA,
        device_class=DeviceClass.CPU,
        members=[],
    )
    assert group.device_class is DeviceClass.CPU

    with pytest.raises(ValidationError, match="LaMa must run on CPU"):
        SelectionGroup(
            group_id=uuid4(),
            kind=GroupKind.TEXT,
            engine=FillEngine.LAMA,
            device_class=DeviceClass.GPU_STANDARD,
            members=[],
        )

    with pytest.raises(ValidationError, match="LaMa must run on CPU"):
        ManualRegion(
            region_id=uuid4(),
            box=Box(x=0, y=0, w=100, h=50),
            engine=FillEngine.LAMA,
            device_class=DeviceClass.GPU_PREMIUM,
            ranges=[],
        )
