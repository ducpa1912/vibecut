"""Caption track for DuckSuite edits."""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path

from duckcore import edits


def _segment_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _pieces(text: str, limit: int = 72) -> list[str]:
    if len(text) <= limit:
        return [text]
    sentences = [item.strip() for item in re.split(r"(?<=[.!?。！？])\s+", text) if item.strip()]
    if len(sentences) <= 1:
        sentences = [item.strip() for item in re.split(r"(?<=[,;，；])\s+", text) if item.strip()]
    pieces: list[str] = []
    for sentence in sentences or [text]:
        while len(sentence) > limit:
            cut = sentence.rfind(" ", 0, limit)
            if cut < limit // 2:
                cut = limit
            pieces.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if sentence:
            pieces.append(sentence)
    return pieces or [text]


def _cues_for_clip(
    segments: list[dict],
    *,
    clip_start: float,
    clip_end: float,
    out_start: float,
) -> list[tuple[float, float, str]]:
    rows: list[tuple[float, float, str]] = []
    for segment in segments:
        try:
            start = max(float(clip_start), float(segment.get("start") or 0.0))
            end = min(float(clip_end), float(segment.get("end") or 0.0))
        except (TypeError, ValueError):
            continue
        if end <= start:
            continue
        text = _segment_text(segment.get("text"))
        if not text:
            continue
        pieces = _pieces(text)
        total_chars = sum(max(1, len(piece)) for piece in pieces)
        cursor = start
        for piece in pieces:
            share = max(1, len(piece)) / total_chars
            piece_end = min(end, cursor + (end - start) * share)
            pieces_start = out_start + (cursor - clip_start)
            pieces_end = out_start + (piece_end - clip_start)
            if pieces_end > pieces_start:
                rows.append((pieces_start, pieces_end, piece))
            cursor = piece_end
    return rows


def generate(edit: dict, transcript: dict, data_root: Path) -> dict:
    segments = [item for item in transcript.get("segments") or [] if isinstance(item, dict)]
    if not segments:
        raise ValueError("No transcript is available for captions.")
    cues = []
    out_cursor = 0.0
    for clip in edit.get("clips") or []:
        start = float(clip.get("start") or 0.0)
        end = float(clip.get("end") or 0.0)
        duration = max(0.0, end - start)
        for cue_start, cue_end, text in _cues_for_clip(
            segments, clip_start=start, clip_end=end, out_start=out_cursor,
        ):
            cues.append({
                "id": f"cq_{hashlib.sha1(f'{cue_start}:{cue_end}:{text}'.encode()).hexdigest()[:10]}",
                "start": round(cue_start, 3),
                "end": round(cue_end, 3),
                "text": text,
            })
        out_cursor += duration
    if not cues:
        raise ValueError("No speech overlaps this edit.")
    track = {
        "track_id": f"cap_{hashlib.sha1(str(time.time()).encode()).hexdigest()[:10]}",
        "style": "clean",
        "burn": False,
        "cues": cues,
    }
    edit["captions"] = track
    edits.save_edit(edit, data_root)
    return track


def srt(track: dict) -> str:
    def stamp(value: float) -> str:
        value = max(0.0, float(value))
        hours = int(value // 3600)
        minutes = int((value % 3600) // 60)
        seconds = int(value % 60)
        millis = int(round((value - int(value)) * 1000))
        if millis >= 1000:
            seconds += 1
            millis = 0
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"

    rows = []
    for index, cue in enumerate(track.get("cues") or [], 1):
        rows.append(str(index))
        rows.append(f"{stamp(cue.get('start', 0))} --> {stamp(cue.get('end', 0))}")
        rows.append(str(cue.get("text") or ""))
        rows.append("")
    return "\n".join(rows)


def update_cue(edit: dict, cue_id: str, text: str, data_root: Path) -> dict:
    track = edit.get("captions")
    if not isinstance(track, dict):
        raise KeyError(cue_id)
    for cue in track.get("cues") or []:
        if str(cue.get("id")) == cue_id:
            cue["text"] = " ".join(str(text or "").split())[:240]
            edits.save_edit(edit, data_root)
            return track
    raise KeyError(cue_id)


def set_burn(edit: dict, burn: bool, data_root: Path) -> dict:
    track = edit.get("captions")
    if not isinstance(track, dict):
        raise ValueError("Generate captions first.")
    track["burn"] = bool(burn)
    edits.save_edit(edit, data_root)
    return track
