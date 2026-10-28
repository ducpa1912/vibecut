"""Reflow a story's caption track after its clip range changes.

A trim does not rewrite captions from scratch. Each old cue is mapped from
old output time to source time through the old clips, then back to new output
time through the new clips. Cues that survive keep their own text, so a manual
name fix is never re-transcribed. Only source material that the old story did
not cover gets fresh cues from the transcript, with the old track's style.

The result is a :class:`ReflowResult` holding an unsaved
``captions.CaptionTrack``. The trim transaction writes it with
``result.save(job_dir)`` before the single job commit, so a failed trim never
leaves a visible track or pointer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import captions as caption_engine

TIME_EPSILON = 0.002
COUNT_KEYS = ("kept", "moved", "dropped", "added", "manual_kept")


class ReflowError(Exception):
    """A caption track cannot be reflowed onto the new story range."""


@dataclass(frozen=True)
class _Window:
    """One clip in output time plus the source span it shows."""

    index: int
    scene: Any
    source_start: float
    source_end: float
    out_start: float
    out_end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.out_end - self.out_start)


@dataclass
class ReflowResult:
    """The rebuilt, not-yet-saved track plus what happened to each cue."""

    track: caption_engine.CaptionTrack
    counts: dict[str, int]
    old_track_id: str | None = None

    @property
    def track_id(self) -> str:
        return self.track.id

    @property
    def kept(self) -> int:
        return self.counts["kept"]

    @property
    def moved(self) -> int:
        return self.counts["moved"]

    @property
    def dropped(self) -> int:
        return self.counts["dropped"]

    @property
    def added(self) -> int:
        return self.counts["added"]

    @property
    def manual_kept(self) -> int:
        return self.counts["manual_kept"]

    def save(self, job_dir: Path | str) -> str:
        """Write the track sidecar. The caller's job commit points at it."""
        try:
            caption_engine.save_track(Path(job_dir), self.track)
        except OSError as exc:
            raise ReflowError(f"The caption track could not be saved: {exc}") from exc
        return self.track.id


# ---------------------------------------------------------------- clip windows


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _clip_end(clip: dict) -> float:
    start = _number(clip.get("start"))
    end = clip.get("end")
    if end is None:
        return start + _number(clip.get("dur", clip.get("duration")))
    return _number(end)


def _scene_id(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _windows(clips: Iterable[dict] | None) -> list[_Window]:
    rows: list[_Window] = []
    offset = 0.0
    for clip in clips or []:
        if not isinstance(clip, dict):
            continue
        start = max(0.0, _number(clip.get("start")))
        end = max(start, _clip_end(clip))
        if end - start <= TIME_EPSILON:
            continue
        rows.append(_Window(
            index=len(rows),
            scene=_scene_id(clip.get("scene")),
            source_start=start,
            source_end=end,
            out_start=offset,
            out_end=offset + (end - start),
        ))
        offset += end - start
    return rows


def _find_window(windows: list[_Window], cue: caption_engine.CaptionCue) -> list[_Window]:
    """Windows the cue overlaps, preferring the cue's own clip index."""
    middle = (float(cue.start) + float(cue.end)) / 2.0
    chosen = [
        window for window in windows
        if window.out_start <= middle < window.out_end
        or abs(middle - window.out_end) <= TIME_EPSILON
    ]
    if not chosen and 0 <= int(cue.clip_index) < len(windows):
        candidate = windows[int(cue.clip_index)]
        if candidate.out_end > float(cue.start) and candidate.out_start < float(cue.end):
            chosen = [candidate]
    return chosen


def _map_old_cue(
    cue: caption_engine.CaptionCue,
    old: list[_Window],
    new: list[_Window],
) -> list[dict]:
    """Map one old cue through old clips to source, then through new clips."""
    overlaps = [
        window for window in old
        if min(float(cue.end), window.out_end) - max(float(cue.start), window.out_start)
        > TIME_EPSILON
    ]
    if not overlaps:
        overlaps = _find_window(old, cue)
    pieces: list[dict] = []
    for window in overlaps:
        out_start = max(float(cue.start), window.out_start)
        out_end = min(float(cue.end), window.out_end)
        if out_end - out_start <= TIME_EPSILON:
            continue
        source_start = window.source_start + (out_start - window.out_start)
        source_end = window.source_start + (out_end - window.out_start)
        for target in new:
            start = max(source_start, target.source_start)
            end = min(source_end, target.source_end)
            if end - start <= TIME_EPSILON:
                continue
            pieces.append({
                "start": target.out_start + (start - target.source_start),
                "end": target.out_start + (end - target.source_start),
                "clip_index": target.index,
                "scene": target.scene,
                "source_start": start,
                "source_end": end,
            })
    pieces.sort(key=lambda item: (item["start"], item["end"]))
    merged: list[dict] = []
    for piece in pieces:
        if (
            merged
            and piece["start"] <= merged[-1]["end"] + TIME_EPSILON
        ):
            merged[-1]["end"] = max(merged[-1]["end"], piece["end"])
            merged[-1]["source_end"] = max(merged[-1]["source_end"], piece["source_end"])
            continue
        merged.append(dict(piece))
    return merged


# ---------------------------------------------------------------- added material


def _merged_ranges(ranges: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    ordered = sorted(
        (max(0.0, start), max(0.0, end))
        for start, end in ranges
        if end - start > TIME_EPSILON
    )
    merged: list[tuple[float, float]] = []
    for start, end in ordered:
        if merged and start <= merged[-1][1] + TIME_EPSILON:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            continue
        merged.append((start, end))
    return merged


def _added_spans(
    old: list[_Window],
    new: list[_Window],
) -> list[tuple[float, float, _Window]]:
    """Source spans in the new story that no old clip covered."""
    covered = _merged_ranges(
        (window.source_start, window.source_end) for window in old
    )
    spans: list[tuple[float, float, _Window]] = []
    for window in new:
        cursor = window.source_start
        for start, end in covered:
            if end <= cursor + TIME_EPSILON:
                continue
            if start >= window.source_end - TIME_EPSILON:
                break
            start = max(start, window.source_start)
            end = min(end, window.source_end)
            if start - cursor > TIME_EPSILON:
                spans.append((cursor, start, window))
            cursor = max(cursor, end)
            if cursor >= window.source_end - TIME_EPSILON:
                break
        if window.source_end - cursor > TIME_EPSILON:
            spans.append((cursor, window.source_end, window))
    return spans


def _span_cues(
    spans: list[tuple[float, float, _Window]],
    style: dict,
    segments: list[dict],
    warnings: list[str],
) -> list[caption_engine.CaptionCue]:
    """Fresh cues for newly added source material, in the old track's style."""
    cues: list[caption_engine.CaptionCue] = []
    for start, end, window in spans:
        plan = {
            "target": max(1, int(round(end - start))),
            "clips": [{
                "scene": window.scene,
                "start": start,
                "end": end,
                "dur": end - start,
                "role": "beat",
            }],
        }
        try:
            built, _source, built_warnings = caption_engine.build_cues(
                plan, style=style, segments=segments,
            )
        except caption_engine.CaptionError as exc:
            raise ReflowError(f"New captions could not be built: {exc}") from exc
        warnings.extend(built_warnings)
        shift = window.out_start + (start - window.source_start)
        for cue in built:
            cue_start = shift + float(cue["start"])
            cue_end = shift + float(cue["end"])
            if cue_end - cue_start <= TIME_EPSILON:
                continue
            cues.append(caption_engine.CaptionCue(
                id="",
                start=round(cue_start, 3),
                end=round(cue_end, 3),
                text=str(cue.get("text") or ""),
                clip_index=window.index,
                scene=window.scene,
                source_segment=(
                    int(cue["source_segment"])
                    if cue.get("source_segment") is not None else None
                ),
                style_safe=bool(cue.get("style_safe", True)),
            ))
    return cues


# ---------------------------------------------------------------- manual text


def _squash(value: str) -> str:
    return "".join(char for char in str(value or "").lower() if char.isalnum())


def _source_excerpt(
    segments: list[dict],
    start: float,
    end: float,
) -> str:
    parts: list[str] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        try:
            segment_start = float(segment["start"])
            segment_end = float(segment["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if min(end, segment_end) - max(start, segment_start) <= TIME_EPSILON:
            continue
        parts.append(caption_engine._slice_segment_text(  # noqa: SLF001
            segment, max(start, segment_start), min(end, segment_end),
        ))
    return "".join(parts)


def _is_manual(text: str, excerpt: str) -> bool:
    wanted = _squash(text)
    haystack = _squash(excerpt)
    return bool(wanted) and bool(haystack) and wanted not in haystack


# ---------------------------------------------------------------- reflow


def _job_dir_for(job_id: str, job: dict, job_dir: Path | str | None) -> Path:
    if job_dir is not None:
        return Path(job_dir)
    hint = job.get("_job_dir") if isinstance(job, dict) else None
    if hint:
        return Path(str(hint))
    return Path(caption_engine.DATA) / "jobs" / job_id


def _load_old_track(job_dir: Path, old_track_id: str | None) -> caption_engine.CaptionTrack | None:
    if not old_track_id:
        return None
    track = caption_engine.load_track(job_dir, str(old_track_id))
    if track is None:
        raise ReflowError(
            f"The old caption track {old_track_id!r} could not be read."
        )
    return track


def _build_track(
    *,
    job_id: str,
    target: int,
    cues: list[caption_engine.CaptionCue],
    style: dict,
    clip_hash: str,
    new_windows: list[_Window],
    parent_id: str | None,
    source: str,
    warnings: list[str],
    transcript_id: str | None,
    version: int,
) -> caption_engine.CaptionTrack:
    cue_key = caption_engine.cue_hash(cues)
    style_key = caption_engine.style_hash(style)
    identifier = caption_engine.track_id(
        job_id=job_id,
        target=target,
        clip_key=clip_hash,
        cue_key=cue_key,
        style_key=f"{style_key}:{style['id']}",
        version=version,
    )
    return caption_engine.CaptionTrack(
        id=identifier,
        job_id=job_id,
        version=version,
        target=target,
        cues=cues,
        style=style,
        style_id=str(style["id"]),
        cue_hash=cue_key,
        style_hash=style_key,
        clip_hash=clip_hash,
        parent_id=parent_id,
        source=source,
        warnings=list(dict.fromkeys(warnings)),
        clip_windows=[
            {
                "index": window.index,
                "scene": window.scene,
                "start": round(window.source_start, 6),
                "end": round(window.source_end, 6),
                "duration": round(window.duration, 6),
            }
            for window in new_windows
        ],
        transcript_id=transcript_id,
    )


def rebuild_for_story(
    job_id: str,
    job: dict,
    set_id: str,
    old_story: dict,
    new_story: dict,
    old_track_id: str | None,
    *,
    job_dir: Path | str | None = None,
) -> ReflowResult:
    """Rebuild one story's caption track for its new clip range.

    The track is not written. ``ReflowResult.save(job_dir)`` writes the
    immutable sidecar and returns the new track id.
    """
    del set_id  # The story carries its own clips; kept for the route contract.
    directory = _job_dir_for(job_id, job, job_dir)
    new_clips = new_story.get("clips") if isinstance(new_story, dict) else None
    new_windows = _windows(new_clips)
    if not new_windows:
        raise ReflowError("The new story has no timed clips to caption.")
    old_windows = _windows((old_story or {}).get("clips"))
    old_track = _load_old_track(directory, old_track_id)

    style = caption_engine.normalize_style(
        old_track.style if old_track is not None else None,
        style_id=old_track.style_id if old_track is not None else None,
    )
    try:
        segments = caption_engine.read_transcript_segments(directory)
    except OSError as exc:
        raise ReflowError(f"The transcript could not be read: {exc}") from exc
    transcript = caption_engine.read_transcript_v2(directory)
    transcript_id = (
        old_track.transcript_id if old_track is not None and old_track.transcript_id
        else (str(transcript.get("id")) if transcript and transcript.get("id") else None)
    )

    counts = {key: 0 for key in COUNT_KEYS}
    warnings: list[str] = []
    cues: list[caption_engine.CaptionCue] = []

    for old_cue in (old_track.cues if old_track is not None else []):
        pieces = _map_old_cue(old_cue, old_windows, new_windows)
        if not pieces:
            counts["dropped"] += 1
            continue
        unchanged = (
            len(pieces) == 1
            and abs(pieces[0]["start"] - float(old_cue.start)) <= TIME_EPSILON
            and abs(pieces[0]["end"] - float(old_cue.end)) <= TIME_EPSILON
        )
        counts["kept" if unchanged else "moved"] += 1
        manual = _is_manual(
            old_cue.text,
            _source_excerpt(segments, pieces[0]["source_start"], pieces[0]["source_end"]),
        ) if segments else False
        if manual:
            counts["manual_kept"] += 1
        for piece in pieces:
            cue_scene = (
                _scene_id(piece["scene"])
                if piece["scene"] is not None else old_cue.scene
            )
            cues.append(caption_engine.CaptionCue(
                id="",
                start=round(piece["start"], 3),
                end=round(piece["end"], 3),
                text=old_cue.text,
                clip_index=int(piece["clip_index"]),
                scene=cue_scene,
                source_segment=old_cue.source_segment,
                style_safe=old_cue.style_safe,
            ))

    spans = _added_spans(old_windows, new_windows)
    if spans and not segments:
        raise ReflowError(
            "The job has no transcript to caption the newly added material."
        )
    added = _span_cues(spans, style, segments, warnings)
    counts["added"] = len(added)
    cues.extend(added)

    cues.sort(key=lambda cue: (cue.start, cue.end))
    cues = [
        caption_engine.CaptionCue(
            id=f"c{index:03d}",
            start=cue.start,
            end=cue.end,
            text=cue.text,
            clip_index=cue.clip_index,
            scene=cue.scene,
            source_segment=cue.source_segment,
            style_safe=cue.style_safe,
        )
        for index, cue in enumerate(cues, 1)
    ]
    total = sum(window.duration for window in new_windows)
    target = max(1, int(round(_number((new_story or {}).get("dur"), total))))
    clip_hash = caption_engine.clip_hash(new_clips)
    track = _build_track(
        job_id=job_id,
        target=target,
        cues=cues,
        style=style,
        clip_hash=clip_hash,
        new_windows=new_windows,
        parent_id=old_track.id if old_track is not None else None,
        source=(
            old_track.source if old_track is not None and old_track.source
            else "reflow"
        ),
        warnings=warnings,
        transcript_id=transcript_id,
        version=(old_track.version + 1) if old_track is not None else 1,
    )
    return ReflowResult(
        track=track,
        counts=counts,
        old_track_id=old_track.id if old_track is not None else None,
    )
