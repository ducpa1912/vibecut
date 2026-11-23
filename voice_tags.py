"""Voice tags and emotional delivery for the two cloud voices.

The script stays the creator's script. This module translates it for the
engine that will speak it:

* **HeyGen Voice Turbo** reads English square-bracket tags in the text:
  ``[sad]``, ``[whispers]``, ``[laughs]``, ``[slightly angry]``. Tags last about
  233 characters and end at the next tag; sound tags play once.
* **MiniMax Speech 2.8** has no inline emotion tags. It takes one
  ``voice_setting.emotion`` per request (happy, sad, angry, fearful, disgusted,
  surprised, calm, fluent), parenthesis interjections such as ``(laughs)`` and
  ``<#0.5#>`` pauses. Speech 2.8 does not support ``whisper``.

The voiceover splitter sends one sentence at a time, so a MiniMax line gets the
emotion of that line. Unsupported tags are removed, never spoken, and the
caller gets a note saying what was dropped.
"""

from __future__ import annotations

import re
from typing import Any

HEYGEN = "heygen"
MINIMAX = "minimax"

HEYGEN_EMOTIONS = (
    "happy", "sad", "angry", "excited", "nervous", "frustrated", "surprised",
    "scared", "sarcastic", "warm", "serious", "calm", "amused", "annoyed",
    "anxious", "awestruck", "bored", "confident", "confused", "curious",
    "determined", "disgusted", "embarrassed", "exhausted", "grateful",
    "guilty", "heartbroken", "hopeful", "jealous", "lonely", "melancholic",
    "panicked", "proud", "relieved", "shy", "sleepy", "tender", "worried",
    "apologetic", "authoritative", "cheerful", "cold", "dismissive", "dreamy",
    "encouraging", "enthusiastic", "firm", "flirtatious", "gentle",
    "matter-of-fact", "mischievous", "playful", "reassuring", "sincere",
    "smug", "solemn", "stern", "suspicious", "thoughtful",
)
HEYGEN_DELIVERY = (
    "whispers", "softly", "shouts", "deep voice", "trembling voice",
    "stammers", "sings", "slowly", "quickly", "on the verge of tears",
    "trying not to laugh", "through gritted teeth", "barely containing excitement",
    "deadpan, dry humor", "as if sharing a secret", "like a sports commentator",
    "like reading a bedtime story", "voice dropping to a whisper",
    "building to a shout", "loudly", "quietly", "murmurs", "yells", "screams",
    "monotone", "breathy", "raspy", "nasal", "rushed", "enunciating clearly",
)
HEYGEN_EVENTS = (
    "pause", "hesitates", "laughs", "chuckles", "giggles", "sighs", "gasps",
    "sobs", "sniffles", "coughs", "clears throat", "groans", "scoffs", "hmm",
)
HEYGEN_TAGS = frozenset(HEYGEN_EMOTIONS + HEYGEN_DELIVERY + HEYGEN_EVENTS)

MINIMAX_EMOTIONS = ("happy", "sad", "angry", "fearful", "disgusted", "surprised", "calm", "fluent")
#: Speech 2.8 does not support MiniMax's whisper emotion.
MINIMAX_UNSUPPORTED = {"whisper"}

#: A HeyGen tag, and the one MiniMax emotion that comes closest. MiniMax can
#: apply one emotion to the whole line; a line with no tag stays automatic.
MINIMAX_FROM_TAG = {
    "happy": "happy", "cheerful": "happy", "excited": "happy", "enthusiastic": "happy",
    "playful": "happy", "amused": "happy", "proud": "happy", "hopeful": "happy",
    "grateful": "happy", "relieved": "happy", "warm": "happy", "encouraging": "happy",
    "reassuring": "happy", "sincere": "happy",
    "sad": "sad", "melancholic": "sad", "heartbroken": "sad", "lonely": "sad",
    "guilty": "sad", "tender": "sad", "on the verge of tears": "sad",
    "angry": "angry", "frustrated": "angry", "annoyed": "angry", "stern": "angry",
    "firm": "angry", "authoritative": "angry", "through gritted teeth": "angry",
    "scared": "fearful", "nervous": "fearful", "anxious": "fearful",
    "worried": "fearful", "panicked": "fearful", "trembling voice": "fearful",
    "disgusted": "disgusted",
    "surprised": "surprised", "awestruck": "surprised",
    "calm": "calm", "serious": "calm", "softly": "calm", "quietly": "calm", "whispers": "calm",
    "matter-of-fact": "calm", "monotone": "calm", "gentle": "calm", "sleepy": "calm",
    "thoughtful": "calm", "solemn": "calm", "cold": "calm", "dismissive": "calm",
    "dreamy": "calm", "suspicious": "calm", "shy": "calm", "bored": "calm",
    "sarcastic": "calm", "deadpan, dry humor": "calm", "fluent": "fluent",
}

MINIMAX_EVENTS = {
    "laughs": "laughs", "chuckles": "chuckle", "giggles": "laughs",
    "sighs": "sighs", "gasps": "gasps", "sniffles": "sniffs", "sniffs": "sniffs",
    "coughs": "coughs", "clears throat": "clear-throat", "groans": "groans",
    "hmm": "emm", "snorts": "snorts", "inhales": "inhale", "exhales": "exhale",
    "pants": "pant", "humming": "humming", "sneezes": "sneezes",
    "burps": "burps", "lip-smacking": "lip-smacking", "hissing": "hissing",
}
MINIMAX_PAUSES = {
    "pause": 0.5, "hesitates": 0.3, "after a long pause": 1.0,
    "voice cracking": 0.2, "trailing off": 0.3, "catching themselves mid-sentence": 0.2,
}

_TAG = re.compile(r"\[([^\[\]]{1,80})\]", re.UNICODE)
_MINIMAX_EVENT = re.compile(
    r"\((?:" + "|".join(re.escape(value) for value in sorted(set(MINIMAX_EVENTS.values()))) + r")\)",
    re.IGNORECASE,
)
_SPACE = re.compile(r"\s+", re.UNICODE)


def _clean_tag(value: str) -> str:
    return _SPACE.sub(" ", str(value or "").strip().lower())


def _emotion_of_tag(tag: str) -> str:
    """``slightly sad`` -> ``sad``; ``[whispering urgently]`` -> ``""``."""
    text = _clean_tag(tag)
    if text.startswith("slightly "):
        text = text[9:]
    elif text.startswith("extremely "):
        text = text[10:]
    return text if text in HEYGEN_EMOTIONS else ""


def _minimax_emotion(value: str) -> tuple[str, str]:
    """Return ``(emotion, note)`` for one requested or tagged emotion."""
    text = _clean_tag(value)
    if not text or text == "auto":
        return "", ""
    if text.startswith("slightly "):
        text = text[9:]
    elif text.startswith("extremely "):
        text = text[10:]
    if text in MINIMAX_UNSUPPORTED or text in {"whispers", "whisper"}:
        return "calm", "MiniMax Speech 2.8 has no whisper; calm is used instead."
    mapped = MINIMAX_FROM_TAG.get(text, text)
    if mapped in MINIMAX_EMOTIONS:
        return mapped, ""
    return "", f"MiniMax has no {text} emotion; automatic delivery is used."


def strip_marks(text: str) -> str:
    """The spoken words only: no HeyGen tags, MiniMax events or pause markers."""
    clean = _TAG.sub(" ", str(text or ""))
    clean = _MINIMAX_EVENT.sub(" ", clean)
    clean = re.sub(r"<#\d+(?:\.\d{1,2})?#>", " ", clean)
    clean = clean.replace("**", "").replace("__", "")
    return _SPACE.sub(" ", clean).strip()


def _tagged_heygen(tag: str) -> str:
    raw = _clean_tag(tag)
    if raw.startswith("slightly ") or raw.startswith("extremely "):
        prefix, _, rest = raw.partition(" ")
        return f"[{prefix} {rest}]" if rest in HEYGEN_EMOTIONS else f"[{raw}]"
    return f"[{raw}]" if raw in HEYGEN_TAGS else f"[{raw}]"


def prepare(text: str, engine: str, emotion: str = "") -> dict[str, Any]:
    """Adapt one line for one engine.

    Returns ``text`` (what is sent), ``emotion`` (MiniMax's field), ``notes``
    (what was changed or dropped) and the engine name.
    """
    engine = str(engine or "").strip().lower()
    original = str(text or "")
    notes: list[str] = []
    if engine == HEYGEN:
        # Keep HeyGen's own tags, lowercase the known ones, and add the chosen
        # emotion before the first words when the script has no span tag.
        tags = [_clean_tag(match) for match in _TAG.findall(original)]
        has_span = any(_emotion_of_tag(tag) or tag in HEYGEN_DELIVERY for tag in tags)
        body = original
        for raw in _TAG.findall(original):
            clean = _clean_tag(raw)
            if clean in HEYGEN_TAGS:
                body = body.replace(f"[{raw}]", _tagged_heygen(clean), 1)
            else:
                notes.append(f"HeyGen does not know [{clean}]; it is left in the script and is not spoken.")
        chosen = _clean_tag(emotion)
        if chosen and chosen != "auto" and not has_span:
            tag = chosen
            if chosen.startswith("slightly ") or chosen.startswith("extremely "):
                prefix, _, rest = chosen.partition(" ")
                if rest not in HEYGEN_EMOTIONS:
                    tag = rest
                    notes.append(f"HeyGen intensity only applies to emotions; [{tag}] is used without it.")
            elif chosen not in HEYGEN_TAGS:
                notes.append(f"HeyGen does not know [{chosen}]; automatic delivery is used.")
                tag = ""
            if tag:
                body = f"[{tag}] {body.lstrip()}"
        return {"text": _SPACE.sub(" ", body).strip(), "emotion": "", "notes": notes, "engine": engine}

    if engine == MINIMAX:
        # MiniMax cannot change emotion inline. The first emotion tag on the
        # line, or the picker, becomes voice_setting.emotion. Events and pauses
        # become MiniMax's own marks.
        chosen = ""
        for raw in _TAG.findall(original):
            tag = _clean_tag(raw)
            found = _emotion_of_tag(tag)
            if not found and tag in {"whispers", "whisper", "softly", "quietly"}:
                found = tag
            if found and not chosen:
                chosen = tag
                break
        mapped, note = _minimax_emotion(chosen or emotion)
        if note:
            notes.append(note)
        out: list[str] = []
        cursor = 0
        for match in _TAG.finditer(original):
            out.append(original[cursor:match.start()])
            tag = _clean_tag(match.group(1))
            if tag in MINIMAX_EVENTS:
                out.append(f"({MINIMAX_EVENTS[tag]})")
            elif tag in MINIMAX_PAUSES:
                out.append(f"<#{MINIMAX_PAUSES[tag]:.2f}#>")
            elif _emotion_of_tag(tag):
                pass  # carried by voice_setting.emotion
            elif tag in HEYGEN_DELIVERY:
                notes.append(f"MiniMax cannot perform [{tag}]; the words are spoken without it.")
            else:
                notes.append(f"[{tag}] is not a MiniMax tag; it was removed.")
            cursor = match.end()
        out.append(original[cursor:])
        spoken = _SPACE.sub(" ", "".join(out)).strip()
        # Pause markers cannot touch each other; keep the first.
        spoken = re.sub(r"(<#\d+(?:\.\d{1,2})?#>)(?:\s*<#\d+(?:\.\d{1,2})?#>)+", r"\1", spoken)
        return {
            "text": spoken,
            "emotion": mapped,
            "notes": notes,
            "engine": engine,
        }

    # Local, ElevenLabs and other engines do not read these tags.
    if _TAG.search(original):
        notes.append(f"{engine or 'This voice'} does not read voice tags; the bracketed directions were removed.")
    return {"text": strip_marks(original), "emotion": "", "notes": notes, "engine": engine}


def compare_text(text: str) -> str:
    """Script words for the re-transcription check, with every mark removed."""
    return strip_marks(text)


def options(engine: str) -> list[dict[str, str]]:
    """The emotion choices the app offers for one engine."""
    if engine == HEYGEN:
        rows = [
            ("happy", "Happy"), ("sad", "Sad"), ("angry", "Angry"),
            ("excited", "Excited"), ("nervous", "Nervous"),
            ("frustrated", "Frustrated"), ("surprised", "Surprised"),
            ("scared", "Scared"), ("sarcastic", "Sarcastic"),
            ("warm", "Warm"), ("serious", "Serious"), ("calm", "Calm"),
            ("whispers", "Whisper"),
        ]
    elif engine == MINIMAX:
        rows = [
            ("happy", "Happy"), ("sad", "Sad"), ("angry", "Angry"),
            ("fearful", "Fearful"), ("disgusted", "Disgusted"),
            ("surprised", "Surprised"), ("calm", "Calm"), ("fluent", "Fluent"),
        ]
    else:
        rows = []
    return [{"id": "auto", "label": "Automatic"}] + [
        {"id": key, "label": label} for key, label in rows
    ]


def hint(engine: str) -> str:
    if engine == HEYGEN:
        return "HeyGen tags in the script: [sad], [slightly angry], [whispers], [laughs], [pause]. Tags last about one sentence."
    if engine == MINIMAX:
        return "MiniMax uses the emotion picker, plus (laughs), (sighs) and <#0.5#> pauses in the script. Speech 2.8 has no whisper."
    return "This voice does not read emotion tags."


def catalog() -> dict[str, Any]:
    """What the page needs to build the emotion picker per engine."""
    return {
        "engines": {
            HEYGEN: {
                "label": "HeyGen Voice Turbo",
                "options": options(HEYGEN),
                "hint": hint(HEYGEN),
            },
            MINIMAX: {
                "label": "MiniMax Speech 2.8",
                "options": options(MINIMAX),
                "hint": hint(MINIMAX),
            },
        }
    }
