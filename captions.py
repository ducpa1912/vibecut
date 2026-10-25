"""Canonical caption cue list shared by burn-in, exports, and artifacts.

The renderer, SRT/VTT export, review links, and artifact identity must all
describe the same cues. Keep cue generation here so a future caption engine
only has to change this module and its callers keep parity.
"""

from __future__ import annotations

from typing import Iterable

CUE_WIDTH = 72


def caption_text(scene: dict | None) -> str:
    text = str((scene or {}).get("speech") or (scene or {}).get("ocr") or "").strip()
    return " ".join(text.replace("\n", " ").split())


def chunk_text(text: str, width: int = CUE_WIDTH) -> list[str]:
    if len(text) <= width:
        return [text]
    words = text.split()
    if len(words) <= 1:
        return [text[index:index + width] for index in range(0, len(text), width)]
    chunks: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            chunks.append(current)
            current = word
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _duration(clip: dict) -> float:
    value = clip.get("duration")
    if value is None:
        value = clip.get("dur")
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


def reel_cues(
    plan: dict,
    clips: Iterable[dict] | None,
    scenes: Iterable[dict] | None,
) -> list[dict]:
    """One cue list for a rendered reel, relative to reel start.

    A long scene line is chunked at ``CUE_WIDTH``, and chunks share the clip
    duration. Times are rounded to milliseconds to match SRT and the artifact
    hash exactly.
    """
    by_id = {
        scene.get("id"): scene
        for scene in scenes or []
        if isinstance(scene, dict)
    }
    cues: list[dict] = []
    offset = 0.0
    for clip in clips or []:
        if not isinstance(clip, dict):
            continue
        scene = by_id.get(clip.get("scene")) or {}
        text = caption_text(scene)
        duration = _duration(clip)
        if text and duration > 0:
            chunks = chunk_text(text)
            share = duration / max(1, len(chunks))
            for index, chunk in enumerate(chunks):
                start = round(offset + index * share, 3)
                end = round(min(offset + duration, offset + (index + 1) * share), 3)
                if end <= start:
                    continue
                cues.append({
                    "start": start,
                    "end": end,
                    "text": chunk,
                    "scene": clip.get("scene"),
                })
        offset += duration
    return cues


def cue_tuples(cues: Iterable[dict]) -> list[tuple[float, float, str]]:
    """Tuple form used by the ffmpeg caption burner."""
    return [
        (float(cue.get("start") or 0.0), float(cue.get("end") or 0.0),
         str(cue.get("text") or ""))
        for cue in cues
        if isinstance(cue, dict)
    ]
