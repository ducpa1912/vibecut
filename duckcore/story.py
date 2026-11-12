"""One story from the whole transcript: thesis, non-contiguous beats.

The on-device model is text-only and small (4,096 tokens on macOS 26), so the
transcript is compressed to one line per scene before it is asked anything.
Long sources are mapped in batches, then reduced. Every beat keeps a verbatim
cue from the transcript, so a result can always be traced back to the source.
No model means a deterministic fallback, labelled as such.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Callable

MIN_BEATS = 3
MAX_BEATS = 6
MIN_RUNTIME = 15.0
MAX_RUNTIME = 90.0
MAX_SUMMARY_CHARS = 120
PROMPT_TOKEN_BUDGET = 4096
BATCH_SIZE = 20
SENTENCE_END = re.compile(r"(?<=[.!?。！？])\s+")

ModelCall = Callable[[dict], dict]


class StoryError(ValueError):
    """The transcript cannot carry a story."""


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _trim(text: str, limit: int) -> str:
    text = _clean(text)
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",;:") + "…"


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in SENTENCE_END.split(_clean(text)) if part.strip()]


def scene_context(check: dict, transcript: dict | None) -> list[dict]:
    """One row per scene that has speech, with a verbatim cue."""
    segments = [
        row for row in (transcript or {}).get("segments") or []
        if isinstance(row, dict) and _clean(row.get("text"))
    ]
    scenes = sorted(
        (scene for scene in check.get("scenes") or [] if isinstance(scene, dict)),
        key=lambda scene: float(scene.get("start") or 0.0),
    )
    rows: list[dict] = []
    for scene in scenes:
        start = float(scene.get("start") or 0.0)
        end = float(scene.get("end") or 0.0)
        if end - start < 0.4:
            continue
        text = " ".join(
            _clean(seg.get("text"))
            for seg in segments
            if float(seg.get("end") or 0.0) > start and float(seg.get("start") or 0.0) < end
        )
        text = re.sub(r"(\b[\w'’]+\b)( \1\b)+", r"\1", text)
        if not _clean(text):
            continue
        sentences = _sentences(text)
        cue = next((item for item in sentences if len(item.split()) >= 3), sentences[0] if sentences else text)
        rows.append({
            "id": int(scene.get("id")),
            "start": start,
            "end": end,
            "seconds": max(0.0, end - start),
            "text": _trim(text, 240),
            "cue": _trim(cue, 140),
        })
    return rows


def _line(row: dict) -> str:
    return f'{row["id"]} | {row["seconds"]:.1f}s | {_trim(row["cue"], MAX_SUMMARY_CHARS)}'


def _prompt_chars(rows: list[dict]) -> int:
    return sum(len(_line(row)) + 1 for row in rows)


def _fits(rows: list[dict]) -> bool:
    # Rough budget: four characters per token, leave a third for instructions.
    return _prompt_chars(rows) <= (PROMPT_TOKEN_BUDGET * 4) // 3


def _model_call(payload: dict) -> dict:
    from duckcore import script

    helper = script._helper("story_apple")
    if helper is None:
        raise StoryError("The story helper is missing from this build.")
    try:
        result = subprocess.run(
            [str(helper)], input=json.dumps(payload), text=True,
            capture_output=True, timeout=240,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise StoryError(f"The story helper could not run: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise StoryError(detail[-400:] or "The story model is unavailable.")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise StoryError("The story model returned unreadable text.") from exc
    if not isinstance(value, dict):
        raise StoryError("The story model returned the wrong shape.")
    return value


def _beat(row: dict, reason: str) -> dict:
    return {
        "scene_id": int(row["id"]),
        "cue": row["cue"],
        "reason": _trim(reason, 90),
        "start": round(float(row["start"]), 3),
        "end": round(float(row["end"]), 3),
        "seconds": round(float(row["seconds"]), 3),
    }


def _first_sentence_score(text: str) -> float:
    from duckcore.engine.textscore import hook_text_score

    try:
        return float(hook_text_score(text))
    except Exception:  # noqa: BLE001 - scoring must never block a story
        return 0.0


def _runtime(rows: list[dict]) -> float:
    return sum(float(row["seconds"]) for row in rows)


def fallback_story(context: list[dict], count: int = 4, reason: str = "No model") -> dict:
    """Deterministic story: strongest hook, spread beats, a closing line."""
    if len(context) < 2:
        raise StoryError("The transcript has too little speech for a story.")
    ranked = sorted(context, key=lambda row: _first_sentence_score(row["cue"]), reverse=True)
    hook = ranked[0]
    closing = next(
        (row for row in reversed(context)
         if row["id"] != hook["id"] and re.search(r"[.!?。！？]$", row["cue"])),
        ranked[1],
    )
    middle = [row for row in context if row["id"] not in {hook["id"], closing["id"]}]
    want = max(MIN_BEATS, min(MAX_BEATS, int(count))) - 2
    picks: list[dict] = []
    if middle:
        step = max(1, len(middle) // max(1, want))
        picks = middle[::step][:want]
    chosen = [hook] + picks + [closing]
    # Keep the runtime inside the story window without dropping the hook.
    while _runtime(chosen) > MAX_RUNTIME and len(chosen) > MIN_BEATS:
        chosen.pop(1)
    index = 0
    while _runtime(chosen) < MIN_RUNTIME and index < len(middle):
        if middle[index] not in chosen:
            chosen.insert(1, middle[index])
        index += 1
    if _runtime(chosen) > MAX_RUNTIME:
        raise StoryError("The selected scenes run longer than a story.")
    beats = [_beat(chosen[0], "Strongest opening line")]
    beats += [_beat(row, "Development beat") for row in chosen[1:-1]]
    beats += [_beat(chosen[-1], "Closing line")]
    return {
        "thesis": _trim(hook["cue"], 180),
        "beats": beats,
        "scene_ids": [beat["scene_id"] for beat in beats],
        "model": "none",
        "reason": reason,
        "title": _trim(hook["cue"], 60) or "Story",
        "runtime": round(_runtime(chosen), 3),
    }


def _select_with_model(context: list[dict], count: int, model: ModelCall) -> dict:
    rows = context if _fits(context) else None
    if rows is not None:
        payload = {
            "count": int(count),
            "scenes": [{"id": row["id"], "seconds": round(row["seconds"], 2), "cue": _trim(row["cue"], MAX_SUMMARY_CHARS)} for row in rows],
        }
        return model(payload)

    # Long source: map batches to a theme and a few candidates, then reduce.
    batches = [context[i:i + BATCH_SIZE] for i in range(0, len(context), BATCH_SIZE)]
    themes: list[dict] = []
    for index, batch in enumerate(batches):
        payload = {
            "count": 3,
            "scenes": [{"id": row["id"], "seconds": round(row["seconds"], 2), "cue": _trim(row["cue"], MAX_SUMMARY_CHARS)} for row in batch],
            "batch": index,
        }
        result = model(payload)
        ids = [int(value) for value in result.get("ids") or [] if str(value).isdigit()]
        themes.append({"theme": _trim(result.get("theme") or "", 120), "ids": ids[:3]})
    by_id = {row["id"]: row for row in context}
    candidates = []
    for theme in themes:
        for scene_id in theme["ids"]:
            if scene_id in by_id and by_id[scene_id] not in candidates:
                candidates.append(by_id[scene_id])
    if len(candidates) < MIN_BEATS:
        raise StoryError("The model found too few beats in the batches.")
    payload = {
        "count": int(count),
        "scenes": [{"id": row["id"], "seconds": round(row["seconds"], 2), "cue": _trim(row["cue"], MAX_SUMMARY_CHARS)} for row in candidates[:24]],
        "themes": [theme["theme"] for theme in themes if theme["theme"]],
    }
    return model(payload)


def _validated(context: list[dict], result: dict, count: int) -> dict:
    by_id = {row["id"]: row for row in context}
    beats: list[dict] = []
    seen: set[int] = set()
    for item in result.get("beats") or []:
        if not isinstance(item, dict):
            continue
        try:
            scene_id = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        row = by_id.get(scene_id)
        if row is None or scene_id in seen:
            continue
        seen.add(scene_id)
        beats.append(_beat(row, str(item.get("reason") or "Model pick")))
    if not (MIN_BEATS <= len(beats) <= MAX_BEATS):
        raise StoryError("The model did not pick 3-6 beats.")
    chosen = [by_id[beat["scene_id"]] for beat in beats]
    runtime = _runtime(chosen)
    if runtime < MIN_RUNTIME or runtime > MAX_RUNTIME:
        raise StoryError(f"The model picked {runtime:.0f}s; a story is {MIN_RUNTIME:.0f}-{MAX_RUNTIME:.0f}s.")
    thesis = _trim(result.get("thesis") or beats[0]["cue"], 180)
    if not thesis:
        thesis = beats[0]["cue"]
    return {
        "thesis": thesis,
        "beats": beats,
        "scene_ids": [beat["scene_id"] for beat in beats],
        "model": "apple",
        "reason": "",
        "title": _trim(thesis, 60) or "Story",
        "runtime": round(runtime, 3),
    }


def write_story(
    check: dict,
    transcript: dict | None,
    *,
    count: int = 4,
    model: ModelCall | None = None,
) -> dict:
    """Return a story document; never raises for a missing model."""
    context = scene_context(check, transcript)
    if not context:
        raise StoryError("No speech in this project; a story needs the transcript.")
    count = max(MIN_BEATS, min(MAX_BEATS, int(count or 4)))
    try:
        result = _select_with_model(context, count, model or _model_call)
        return _validated(context, result, count)
    except Exception as exc:  # noqa: BLE001 - the fallback is the contract
        return fallback_story(context, count, reason=str(exc)[:160] or "No model")
