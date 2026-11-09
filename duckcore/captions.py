"""Caption track for DuckSuite edits."""

from __future__ import annotations

import hashlib
import math
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


def _clean_segments(
    segments: list[dict],
    *,
    clip_start: float,
    clip_end: float,
) -> list[dict]:
    """Clamp, order and de-duplicate speech segments inside one clip.

    Whisper emits overlapping chunks, and a chunk boundary repeats the same
    sentence. Left alone, those chunks become two caption cues with the same
    text and a 5 ms cue at the seam. Merge a repeated sentence, trim the
    overlap of different sentences, and drop slivers.
    """
    rows: list[dict] = []
    for segment in segments:
        try:
            start = max(float(clip_start), float(segment.get("start") or 0.0))
            end = min(float(clip_end), float(segment.get("end") or 0.0))
        except (TypeError, ValueError):
            continue
        text = _segment_text(segment.get("text"))
        if not text or end <= start:
            continue
        full_start = float(segment.get("start") or 0.0)
        full_end = float(segment.get("end") or 0.0)
        if full_end > full_start:
            ratio = (end - start) / (full_end - full_start)
            # A sentence that mostly belongs to the next clip is emitted
            # there, whole. On an exact half, the clip that holds its start.
            if ratio < 0.5 or (ratio <= 0.5 and full_start < clip_start - 1e-6):
                continue
        rows.append({
            "start": start,
            "end": end,
            "full_start": float(segment.get("start") or 0.0),
            "full_end": float(segment.get("end") or 0.0),
            "text": text,
        })
    rows.sort(key=lambda item: (item["start"], item["end"]))

    merged: list[dict] = []
    for row in rows:
        if not merged:
            merged.append(row)
            continue
        previous = merged[-1]
        same = _normalize_words(previous["text"]) == _normalize_words(row["text"])
        gap = row["start"] - previous["end"]
        if same and gap <= 0.75:
            previous["end"] = max(previous["end"], row["end"])
            if len(row["text"]) > len(previous["text"]):
                previous["text"] = row["text"]
            continue
        if row["start"] < previous["end"] - 0.02:
            row["start"] = previous["end"]
            if row["end"] - row["start"] < 0.12:
                continue
        merged.append(row)
    return merged


def _normalize_words(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", text.lower()))


def _split_words(text: str, parts: int) -> list[str]:
    words = text.split()
    if parts <= 1 or len(words) <= 1:
        return [text]
    total = sum(max(1, len(word)) for word in words)
    chunks: list[str] = []
    current: list[str] = []
    seen = 0
    target = total
    for index, word in enumerate(words):
        current.append(word)
        seen += max(1, len(word))
        left = len(words) - index - 1
        if len(chunks) < parts - 1 and (seen >= target / parts or left <= parts - len(chunks) - 1):
            chunks.append(" ".join(current))
            current = []
            seen = 0
    if current:
        chunks.append(" ".join(current))
    return chunks or [text]


def _split_long_cues(cues: list[list]) -> list[list]:
    out: list[list] = []
    for start, end, text in cues:
        duration = end - start
        if duration <= 4.0 + 1e-6:
            out.append([start, end, text])
            continue
        parts = max(2, min(4, int(math.ceil(duration / 4.0))))
        chunks = _split_words(text, parts)
        if len(chunks) <= 1:
            out.append([start, end, text])
            continue
        step = duration / len(chunks)
        for index, chunk in enumerate(chunks):
            piece_start = start + step * index
            piece_end = end if index == len(chunks) - 1 else start + step * (index + 1)
            out.append([piece_start, piece_end, chunk])
    return out


def _finish_cues(
    rows: list[tuple[float, float, str]],
    *,
    out_start: float,
    out_end: float,
) -> list[tuple[float, float, str]]:
    """No overlaps, no repeated neighbours, no flash cues."""
    rows = sorted(rows, key=lambda item: (item[0], item[1]))
    cleaned: list[list] = []
    for start, end, text in rows:
        start = max(out_start, float(start))
        end = min(out_end, float(end))
        if end - start < 0.05:
            continue
        if cleaned:
            previous = cleaned[-1]
            same = _normalize_words(previous[2]) == _normalize_words(text)
            if same and start <= previous[1] + 0.2:
                previous[1] = max(previous[1], end)
                continue
            if start < previous[1]:
                start = previous[1]
                if end - start < 0.05:
                    continue
        cleaned.append([start, end, text])

    # A cue shorter than 0.6 s flashes. Merge a neighbour, borrow silence, or
    # drop it when the clip is too dense to hold a readable line.
    index = 0
    while index < len(cleaned):
        start, end, text = cleaned[index]
        duration = end - start
        if duration >= 0.6 - 1e-6:
            index += 1
            continue
        previous = cleaned[index - 1] if index > 0 else None
        nxt = cleaned[index + 1] if index + 1 < len(cleaned) else None
        if nxt and _normalize_words(text) == _normalize_words(nxt[2]) and nxt[1] - start <= 4.0:
            cleaned[index] = [start, nxt[1], text]
            del cleaned[index + 1]
            continue
        target_end = min(out_end, start + 0.6)
        if nxt:
            target_end = min(target_end, nxt[0])
        if target_end - start >= 0.6 - 1e-6:
            cleaned[index][1] = target_end
            index += 1
            continue
        target_start = max(out_start, end - 0.6)
        if previous:
            target_start = max(target_start, previous[1])
        if end - target_start >= 0.6 - 1e-6:
            cleaned[index][0] = target_start
            index += 1
            continue
        if nxt is not None and nxt[1] - start <= 4.0:
            cleaned[index] = [start, nxt[1], f"{text} {nxt[2]}".strip()]
            del cleaned[index + 1]
            continue
        if previous is not None and end - previous[0] <= 4.0:
            previous[1] = end
            previous[2] = f"{previous[2]} {text}".strip()
            del cleaned[index]
            continue
        if duration < 0.25:
            del cleaned[index]
            continue
        index += 1
    cleaned = _split_long_cues(cleaned)
    return [(round(start, 3), round(end, 3), text) for start, end, text in cleaned]


def _cues_for_clip(
    segments: list[dict],
    *,
    clip_start: float,
    clip_end: float,
    out_start: float,
) -> list[tuple[float, float, str]]:
    out_end = out_start + (clip_end - clip_start)
    rows: list[tuple[float, float, str]] = []
    for segment in _clean_segments(
        segments, clip_start=clip_start, clip_end=clip_end,
    ):
        start = segment["start"]
        end = segment["end"]
        text = segment["text"]
        if not text.strip():
            continue
        for piece in _pieces(text):
            share = max(1, len(piece)) / max(1, len(text))
            piece_end = min(end, start + (end - start) * share)
            piece_start = out_start + (start - clip_start)
            pieces_end = out_start + (piece_end - clip_start)
            if pieces_end > piece_start:
                rows.append((piece_start, pieces_end, piece))
            start = piece_end
    return _finish_cues(rows, out_start=out_start, out_end=out_end)


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
        if str(clip.get("kind")) == "media":
            # Inserted images and videos have no source speech. Keep their
            # space on the story timeline, but do not pull source captions
            # into the beat.
            out_cursor += duration
            continue
        for cue_start, cue_end, text in _cues_for_clip(
            segments, clip_start=start, clip_end=end, out_start=out_cursor,
        ):
            cues.append({
                "id": f"cq_{hashlib.sha1(f'{cue_start}:{cue_end}:{text}'.encode()).hexdigest()[:10]}",
                "start": round(cue_start, 3),
                "end": round(cue_end, 3),
                "text": text,
                "source_text": text,
            })
        out_cursor += duration
    if not cues:
        raise ValueError("No speech overlaps this edit.")
    existing = edit.get("captions") if isinstance(edit.get("captions"), dict) else {}
    track = {
        "track_id": f"cap_{hashlib.sha1(str(time.time()).encode()).hexdigest()[:10]}",
        "style": existing.get("style") or "clean",
        "burn": bool(existing.get("burn")),
        "cues": cues,
    }
    edit["captions"] = track
    edits.save_edit(edit, data_root)
    return track


def append_appended(
    edit: dict,
    transcript: dict,
    data_root: Path,
    offset: float,
    scene_ids: set[int] | None = None,
) -> dict | None:
    """Add caption cues for clips appended after ``offset``.

    Existing cues stay untouched, including user edits and translations. New
    cues use the source transcript for the appended range.
    """
    try:
        edit = edits.get_edit(data_root, str(edit["project_id"]), str(edit["id"]))
    except (KeyError, edits.EditError):
        pass
    track = edit.get("captions")
    if not isinstance(track, dict) or not track.get("cues"):
        return None
    clips = [
        clip for clip in edit.get("clips") or []
        if float(clip.get("end") or 0.0) > float(clip.get("start") or 0.0)
    ]
    if scene_ids:
        first = next(
            (index for index, clip in enumerate(clips)
             if int(clip.get("scene") or -1) in scene_ids),
            None,
        )
    else:
        first = next(
            (index for index, clip in enumerate(clips)
             if float(clip.get("start") or 0.0) >= float(offset) - 0.05),
            None,
        )
    if first is None:
        return None
    segments = [item for item in transcript.get("segments") or [] if isinstance(item, dict)]
    if not segments:
        return None
    out_cursor = 0.0
    for clip in clips[:first]:
        out_cursor += max(0.0, float(clip.get("end") or 0.0) - float(clip.get("start") or 0.0))
    existing = list(track.get("cues") or [])
    known = {
        (round(float(cue.get("start") or 0.0), 2), round(float(cue.get("end") or 0.0), 2),
         str(cue.get("text") or ""))
        for cue in existing
    }
    added: list[dict] = []
    for clip in clips[first:]:
        start = float(clip.get("start") or 0.0)
        end = float(clip.get("end") or 0.0)
        duration = max(0.0, end - start)
        for cue_start, cue_end, text in _cues_for_clip(
            segments, clip_start=start, clip_end=end, out_start=out_cursor,
        ):
            key = (round(cue_start, 2), round(cue_end, 2), text)
            if key in known:
                continue
            known.add(key)
            added.append({
                "id": f"cq_{hashlib.sha1(f'{cue_start}:{cue_end}:{text}'.encode()).hexdigest()[:10]}",
                "start": round(cue_start, 3),
                "end": round(cue_end, 3),
                "text": text,
                "source_text": text,
            })
        out_cursor += duration
    if not added:
        return track
    track["cues"] = sorted(existing + added, key=lambda cue: float(cue.get("start") or 0.0))
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


def set_style(
    edit: dict,
    *,
    style_id: str = "",
    position: str = "",
    data_root: Path,
) -> dict:
    from duckcore import caption_style

    track = edit.get("captions")
    if not isinstance(track, dict):
        raise ValueError("Generate captions first.")
    current = caption_style.normalize(track.get("style"))
    if style_id:
        current = caption_style.normalize(style_id)
    if position:
        if position not in caption_style.POSITIONS:
            raise ValueError("Caption position must be bottom, middle or top.")
        current["position"] = position
    track["style"] = current
    edits.save_edit(edit, data_root)
    return track


def set_burn(edit: dict, burn: bool, data_root: Path) -> dict:
    track = edit.get("captions")
    if not isinstance(track, dict):
        raise ValueError("Generate captions first.")
    track["burn"] = bool(burn)
    edits.save_edit(edit, data_root)
    return track
