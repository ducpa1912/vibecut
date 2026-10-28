"""Voice scripts for videos with no speech.

A silent or music-only video has nothing to cut stories on. The creator writes
a short brief instead:

* the topic, tone and mood, or what the voice should say;
* exact lines inside ``[script:"..."]``, kept word for word where they fit.

The brief, the scene timeline and a handful of keyframes go to a vision model
on OpenRouter, which writes one short line per beat of the footage. The lines
are stored as the job's transcript (engine ``script``), so stories, captions,
trim and the voice-over render all work the way they do for real speech.
"""

from __future__ import annotations

import base64
import json
import math
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import settings_store

#: Sees images and writes well in Vietnamese and English; cheap per call.
#: Fallback only; the admin "script" workflow route is used when it is set.
MODEL = "google/gemini-3.5-flash-lite"


def configured_model() -> str:
    """The first OpenRouter model on the admin "script" workflow, else MODEL."""
    try:
        import workflow_config

        routes = workflow_config.routes(
            settings_store.load_settings().get("workflows"), "script",
        )
    except Exception:  # noqa: BLE001 - a bad settings file keeps the default
        return MODEL
    for route in routes:
        if route.get("provider") == "openrouter" and route.get("model"):
            return str(route["model"])
    return MODEL
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
ENGINE = "script"
MAX_BRIEF_CHARS = 6000
MAX_BEATS = 160
MIN_BEAT_S = 2.5
MAX_BEAT_S = 8.0
MAX_IMAGES = 32
#: Beats per model call. One call over a long video writes one arc and stops,
#: so long videos are written in parts with the previous lines as context.
CHUNK_BEATS = 40
IMAGES_PER_CHUNK = 16
#: Speaking pace used to size each line: words per second, or characters per
#: second for languages written without spaces.
WORDS_PER_SECOND = {"en": 2.6, "vi": 3.4, "es": 2.8, "fr": 2.8, "de": 2.3, "pt": 2.8, "id": 2.6}
CHARS_PER_SECOND = {"zh": 4.2, "ja": 6.0, "ko": 5.0, "th": 9.0}
_SCRIPT_RE = re.compile(
    r"""\[\s*script\s*:\s*(?:"([^"]*)"|“([^”]*)”|'([^']*)'|([^\]]*))\s*\]""",
    re.IGNORECASE | re.DOTALL,
)


class ScriptError(Exception):
    """The voice script could not be written; safe to show the creator."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------- brief


def parse_brief(text: str) -> dict:
    """Split a brief into exact ``[script:"..."]`` lines and free guidance."""
    value = str(text or "")
    lines: list[str] = []
    for match in _SCRIPT_RE.finditer(value):
        line = next((group for group in match.groups() if group is not None), "")
        line = " ".join(line.split())
        if line:
            lines.append(line)
    guidance = " ".join(_SCRIPT_RE.sub(" ", value).split())
    return {"script": lines, "guidance": guidance}


def _speech_rate(language: str) -> tuple[float, bool]:
    """(units per second, counts characters)."""
    code = str(language or "en").lower().split("-")[0]
    if code in CHARS_PER_SECOND:
        return CHARS_PER_SECOND[code], True
    return WORDS_PER_SECOND.get(code, 2.6), False


def budget(seconds: float, language: str) -> int:
    rate, _chars = _speech_rate(language)
    return max(1, int(seconds * rate * 0.85))


def spoken_seconds(text: str, language: str) -> float:
    rate, chars = _speech_rate(language)
    units = len(re.sub(r"\s+", "", text)) if chars else len(text.split())
    return units / rate


# ---------------------------------------------------------------- beats


def build_beats(scenes: Sequence[Mapping[str, Any]], duration: float) -> list[dict]:
    """Group scenes into speakable beats of a few seconds.

    Short cuts are merged until a beat is long enough for a phrase; long
    static shots are split so a line can land every few seconds.
    """
    ordered = sorted(
        (scene for scene in scenes if float(scene.get("end") or 0) > float(scene.get("start") or 0)),
        key=lambda scene: float(scene.get("start") or 0),
    )
    if not ordered:
        return []
    floor = max(MIN_BEAT_S, (duration or 0.0) / MAX_BEATS)
    beats: list[dict] = []
    current: dict | None = None
    for scene in ordered:
        start = float(scene["start"])
        end = float(scene["end"])
        if current is None:
            current = {"start": start, "end": end, "scenes": [scene]}
        else:
            current["end"] = end
            current["scenes"].append(scene)
        if current["end"] - current["start"] >= floor:
            beats.append(current)
            current = None
    if current is not None:
        if beats and current["end"] - current["start"] < floor:
            beats[-1]["end"] = current["end"]
            beats[-1]["scenes"].extend(current["scenes"])
        else:
            beats.append(current)
    split: list[dict] = []
    for beat in beats:
        length = beat["end"] - beat["start"]
        parts = max(1, math.ceil(length / MAX_BEAT_S - 1e-9)) if len(beats) < MAX_BEATS else 1
        step = length / parts
        for index in range(parts):
            split.append({
                "start": round(beat["start"] + index * step, 3),
                "end": round(beat["start"] + (index + 1) * step, 3),
                "scenes": beat["scenes"],
            })
    rows = []
    for index, beat in enumerate(split[: MAX_BEATS * 2]):
        scenes_in = beat["scenes"]
        text = " ".join(
            dict.fromkeys(str(scene.get("ocr") or "").strip() for scene in scenes_in if scene.get("ocr"))
        )[:140]
        rows.append({
            "beat": index,
            "start": beat["start"],
            "end": beat["end"],
            "scene": int(scenes_in[0].get("id") or 0),
            "scene_ids": [int(scene.get("id") or 0) for scene in scenes_in],
            "on_screen": text,
            "face": any(bool(scene.get("face")) for scene in scenes_in),
            "motion": round(max(float(scene.get("motion_score") or 0) for scene in scenes_in)),
            "hook": round(max(float(scene.get("hook") or 0) for scene in scenes_in)),
        })
    return rows


def _keyframes(job_dir: Path, beats: Sequence[dict], limit: int = IMAGES_PER_CHUNK) -> list[tuple[int, str]]:
    """Up to ``limit`` (beat, data URI) pairs spread across the video."""
    thumbs = Path(job_dir) / "thumbs"
    if not thumbs.is_dir() or not beats:
        return []
    picks: list[tuple[int, str]] = []
    step = max(1.0, len(beats) / limit)
    index = 0.0
    seen: set[int] = set()
    while int(index) < len(beats) and len(picks) < limit:
        beat = beats[int(index)]
        index += step
        if beat["beat"] in seen:
            continue
        seen.add(beat["beat"])
        for scene_id in beat["scene_ids"]:
            path = thumbs / f"{scene_id:05d}.jpg"
            if path.is_file() and path.stat().st_size < 400_000:
                data = base64.b64encode(path.read_bytes()).decode("ascii")
                picks.append((beat["beat"], f"data:image/jpeg;base64,{data}"))
                break
    return picks


# ---------------------------------------------------------------- model


def _prompt(
    brief: dict, beats: Sequence[dict], language: str, title: str,
    *, part: int = 1, parts: int = 1, previous: Sequence[str] = (),
    exact: Sequence[str] | None = None,
) -> str:
    timeline = [
        {
            "beat": beat["beat"],
            "at": f"{beat['start']:.1f}-{beat['end']:.1f}s",
            "max_words": budget(beat["end"] - beat["start"], language),
            **({"on_screen": beat["on_screen"]} if beat["on_screen"] else {}),
            **({"face": True} if beat["face"] else {}),
            **({"motion": beat["motion"]} if beat["motion"] >= 40 else {}),
        }
        for beat in beats
    ]
    exact = list(brief["script"] if exact is None else exact)
    last_part = part >= parts
    rules = [
        "You write the voice-over for a silent video that will be cut into short vertical stories.",
        f"Write in language code '{language}' unless the creator's description is clearly in another language; then use that language.",
        "Write one short spoken line per beat you choose to fill. Leave a beat out when silence suits the picture better, but keep the voice going: fill at least two of every three beats.",
        "Each line must fit its beat: never more words than its max_words (count characters for Chinese, Japanese, Korean or Thai).",
        "Each line is a complete sentence that ends with . ! or ? so the video can be cut after it.",
        "Match what is on screen in that beat (the keyframes are labelled with their beat number). Do not describe the camera or the editing.",
        "Group lines into small arcs of 15 to 60 seconds: a hook, a few beats of detail, a payoff. Do not repeat yourself across the video.",
    ]
    if parts > 1:
        rules.append(
            f"This is part {part} of {parts} of one continuous video; write only for the beats listed here and fill them "
            "from the first to the last. Carry on naturally from PREVIOUS_LINES without repeating them."
        )
    if exact:
        where = (
            "Use every one of them in this part"
            if last_part else
            "Use the ones that fit these beats now; any you leave out will be used in a later part"
        )
        rules.append(
            f"The creator gave exact lines (EXACT_LINES). {where}. Keep their wording and place each on the beat where "
            "it fits the picture best. You may split a long exact line across consecutive beats at natural pauses, and "
            "you may add short linking lines around them, but do not paraphrase them."
        )
    rules.append(
        'Reply with JSON only: {"language": "<code>", "lines": [{"beat": <int>, "text": "<line>"}]} in beat order.'
    )
    payload = {
        "video_title": title,
        "creator_description": brief["guidance"] or "(none: infer the topic from the pictures and on-screen text)",
        **({"EXACT_LINES": exact} if exact else {}),
        **({"PREVIOUS_LINES": list(previous)[-4:]} if previous else {}),
        "beats": timeline,
    }
    return "\n".join(f"- {rule}" for rule in rules) + "\n\n" + json.dumps(payload, ensure_ascii=False)


def _call_model(prompt: str, images: Sequence[tuple[int, str]], *, model: str, timeout: float) -> str:
    key = settings_store.get_secret("openrouter")
    if not key:
        raise ScriptError("Add an OpenRouter key in Setup to write a voice script.")
    content: list[dict] = [{"type": "text", "text": prompt}]
    for beat, uri in images:
        content.append({"type": "text", "text": f"Keyframe for beat {beat}:"})
        content.append({"type": "image_url", "image_url": {"url": uri}})
    body = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.6,
        "max_tokens": 8000,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8787",
            "X-Title": "VibeCut",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=max(30, timeout)) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read().decode("utf-8", "replace")).get("error", {}).get("message", "")
        except Exception:  # noqa: BLE001
            pass
        raise ScriptError(f"OpenRouter could not write the script ({exc.code}){': ' + detail if detail else '.'}", 502) from exc
    except Exception as exc:  # noqa: BLE001
        raise ScriptError(f"Could not reach OpenRouter: {exc}", 502) from exc
    try:
        import usage_store

        usage = data.get("usage") or {}
        usage_store.record(
            "llm", "openrouter", model=model,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
        )
    except Exception:  # noqa: BLE001
        pass
    choices = data.get("choices") or []
    message = (choices[0].get("message") or {}) if choices else {}
    text = message.get("content")
    if isinstance(text, list):
        text = "".join(str(part.get("text") or "") for part in text if isinstance(part, dict))
    if not str(text or "").strip():
        raise ScriptError("OpenRouter returned an empty script. Try again.", 502)
    return str(text)


def _parse_reply(text: str) -> dict:
    value = str(text or "").strip()
    fence = re.search(r"\{.*\}", value, re.DOTALL)
    if fence:
        value = fence.group(0)
    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ScriptError("The model did not return a readable script. Try again.", 502) from exc
    if not isinstance(data, dict) or not isinstance(data.get("lines"), list):
        raise ScriptError("The model did not return script lines. Try again.", 502)
    return data


# ---------------------------------------------------------------- timing


def _beat_of(line: Mapping[str, Any]) -> int:
    try:
        return int(line.get("beat"))
    except (TypeError, ValueError):
        return -1


def _norm(text: Any) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", str(text or "").casefold()).split())


def _ensure_terminal(text: str) -> str:
    value = " ".join(str(text or "").split()).strip()
    if value and not re.search(r"""[.!?。！？]["'”’)\]]*$""", value):
        value += "."
    return value


def timed_lines(lines: Sequence[Mapping[str, Any]], beats: Sequence[dict], language: str) -> list[dict]:
    """Place model lines on their beats; one line per beat, in time order."""
    by_beat = {beat["beat"]: beat for beat in beats}
    placed: dict[int, dict] = {}
    for raw in lines:
        if not isinstance(raw, Mapping):
            continue
        try:
            index = int(raw.get("beat"))
        except (TypeError, ValueError):
            continue
        beat = by_beat.get(index)
        text = _ensure_terminal(raw.get("text") or "")
        if beat is None or not text or index in placed:
            continue
        room = max(0.6, beat["end"] - beat["start"] - 0.15)
        start = round(beat["start"] + 0.1, 3)
        end = round(start + min(room, max(0.6, spoken_seconds(text, language))), 3)
        placed[index] = {"beat": index, "scene": beat["scene"], "start": start, "end": end, "text": text}
    return [placed[key] for key in sorted(placed)]


def enforce_exact(lines: list[dict], exact: Sequence[str], beats: Sequence[dict], language: str) -> list[dict]:
    """Make every ``[script:"..."]`` line appear word for word, once.

    Models paraphrase or repeat quoted lines. The line most like each exact
    line is replaced by it, and other copies are dropped.
    """
    import difflib

    by_beat = {beat["beat"]: beat for beat in beats}
    fixed: list[dict] = []
    for text in exact:
        wanted = _ensure_terminal(text)
        key = _norm(wanted)
        if not key:
            continue
        pool = [line for line in lines if not any(line is item for item in fixed)]
        if not pool:
            break
        same = [line for line in pool if _norm(line["text"]) == key]
        if same:
            keep = same[0]
        else:
            keep = max(pool, key=lambda line: difflib.SequenceMatcher(None, _norm(line["text"]), key).ratio())
            beat = by_beat.get(keep["beat"])
            room = max(0.6, (beat["end"] - beat["start"] - 0.15) if beat else 3.0)
            keep["text"] = wanted
            keep["end"] = round(keep["start"] + min(room, max(0.6, spoken_seconds(wanted, language))), 3)
        fixed.append(keep)
        lines = [
            line for line in lines
            if line is keep
            or difflib.SequenceMatcher(None, _norm(line["text"]), key).ratio() < 0.85
        ]
    return lines


def words_for(lines: Sequence[Mapping[str, Any]], language: str) -> list[dict]:
    """Evenly spaced word timings inside each line, for captions and trims."""
    _rate, chars = _speech_rate(language)
    words: list[dict] = []
    for line in lines:
        tokens = list(re.sub(r"\s+", "", line["text"])) if chars else line["text"].split()
        if not tokens:
            continue
        span = (float(line["end"]) - float(line["start"])) / len(tokens)
        for index, token in enumerate(tokens):
            start = float(line["start"]) + index * span
            words.append({
                "word": token,
                "start": round(start, 3),
                "end": round(start + span * 0.92, 3),
                "confidence": 1.0,
            })
    return words


# ---------------------------------------------------------------- entry


def write_script(
    job: Mapping[str, Any],
    job_dir: Path,
    brief_text: str,
    *,
    language: str = "",
    model: str | None = None,
    timeout: float = 240,
    call: Callable[..., str] | None = None,
) -> dict:
    """Write, time and save a voice script for a job; return a summary."""
    import stt

    model = model or configured_model()
    brief_text = str(brief_text or "").strip()
    if not brief_text:
        raise ScriptError("Describe the video first: the topic, tone and mood, or what to say.")
    if len(brief_text) > MAX_BRIEF_CHARS:
        raise ScriptError(f"Keep the description under {MAX_BRIEF_CHARS} characters.")
    analysis = job.get("analysis") or {}
    scenes = list(analysis.get("scenes") or [])
    source = job.get("source") or {}
    duration = float(source.get("duration") or 0.0)
    if not scenes or duration <= 0:
        raise ScriptError("Wait for the video to finish reading first.", 409)
    brief = parse_brief(brief_text)
    title = Path(str(source.get("name") or "video")).stem
    lang = (
        str(language or "").strip().lower().split("-")[0]
        or stt.guess_language(brief_text)
        or stt.guess_language(title)
        or str((settings_store.load_settings().get("stt") or {}).get("language") or "en").split("-")[0]
    )
    if lang == "auto":
        lang = "en"
    beats = build_beats(scenes, duration)
    if not beats:
        raise ScriptError("This video has no scenes to write for.", 409)
    started = time.time()
    chunks = [beats[index:index + CHUNK_BEATS] for index in range(0, len(beats), CHUNK_BEATS)]
    if len(chunks) > 1 and len(chunks[-1]) < CHUNK_BEATS // 3:
        chunks[-2].extend(chunks.pop())
    remaining = list(brief["script"])
    raw_lines: list[dict] = []
    out_lang = lang
    images_sent = 0
    for number, chunk in enumerate(chunks, start=1):
        images = _keyframes(Path(job_dir), chunk)
        images_sent += len(images)
        prompt = _prompt(
            brief, chunk, out_lang, title,
            part=number, parts=len(chunks),
            previous=[str(line.get("text") or "") for line in raw_lines],
            exact=remaining,
        )
        data = _parse_reply((call or _call_model)(prompt, images, model=model, timeout=timeout))
        if number == 1:
            out_lang = str(data.get("language") or lang).strip().lower().split("-")[0] or lang
        allowed = {beat["beat"] for beat in chunk}
        written = [
            line for line in data["lines"]
            if isinstance(line, Mapping) and _beat_of(line) in allowed
        ]
        raw_lines.extend(written)
        said = " ".join(_norm(line.get("text")) for line in written)
        remaining = [line for line in remaining if _norm(line) not in said]
    lines = enforce_exact(timed_lines(raw_lines, beats, out_lang), brief["script"], beats, out_lang)
    if len(lines) < 3:
        raise ScriptError("The model wrote too few lines for this video. Add more detail and try again.", 502)
    transcript = stt.build_transcript(
        engine=ENGINE,
        model=model,
        language=out_lang,
        segments=[{"start": line["start"], "end": line["end"], "text": line["text"]} for line in lines],
        words=words_for(lines, out_lang),
        audio_duration=duration,
        source_hash=f"brief:{stt._hash_json({'brief': brief_text, 'model': model})}",
    )
    path = stt.save_transcript(Path(job_dir), transcript)
    return {
        "transcript": {**transcript, "provider": ENGINE, "path": str(path)},
        "brief": brief_text,
        "language": out_lang,
        "model": model,
        "lines": len(lines),
        "exact_lines": len(brief["script"]),
        "images": images_sent,
        "parts": len(chunks),
        "missing_exact": remaining,
        "beats": len(beats),
        "seconds": round(time.time() - started, 1),
    }
