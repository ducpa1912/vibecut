"""Selection v2: explicit multi-signal story ranking with prompt exclusions.

Version 1 (the automatic 15/30/60 Smart Cut) stays the default. This module is
only called by the explicit selection-v2 endpoint. It ranks existing clip-set
stories, drops stories that match a prompt exclusion, attaches explainable
evidence, and prepares three real hook candidates per story.
"""

from __future__ import annotations

import copy
import math
import re
from typing import Iterable

import clipset
from pipeline import hook_text_score

V2_WEIGHTS = {
    "hook_score": 0.27,
    "speech_coherence": 0.23,
    "audio_energy": 0.12,
    "visual_quality": 0.12,
    "payoff_position": 0.14,
    "novelty": 0.12,
}
_ALLOWED_EVIDENCE = set(clipset.EVIDENCE_TYPES)

_MARKER = (
    r"(?:do not|don't|doesn't|must not|should not|never|no|not|avoid|"
    r"exclude|excluding|skip|without|remove)"
)
_MARKER_RE = re.compile(rf"(?i)\b{_MARKER}\b")
_OPTIONAL_LEAD = re.compile(
    r"(?i)^(?:any|more|the|a|an|of|about|on|with|use|using|include|including|"
    r"mention|mentions|talk about|anything about)\b[\s:,-]*"
)
_BAD_TERMS = {
    "more than", "less than", "than", "only", "just", "please", "anything",
    "something", "that", "this",
}


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if math.isfinite(number) else fallback


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _clean(text: str) -> str:
    return " ".join(str(text or "").split())


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", (text or "").lower()).strip()


def parse_exclusions(prompt: str = "", explicit: Iterable[str] | None = None) -> list[str]:
    """Turn natural prompt exclusions and an explicit list into terms.

    Examples: ``no politics, avoid crypto`` -> ``["politics", "crypto"]``.
    Text is never invented; only phrases already present in the prompt are
    returned. A prompt with no exclusion marker returns no terms.
    """
    terms: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        value = _clean(term).strip(" .,;:!?。，；：！？-–—'\"")
        value = re.sub(r"(?i)\b(?:please|thanks)\b", "", value).strip()
        if not value:
            return
        if len(value) < 2 or len(value) > 48:
            return
        key = value.casefold()
        if key in _BAD_TERMS or key in seen:
            return
        if re.match(r"^(?:than|more than|less than|fewer than)\b", key):
            return
        if re.fullmatch(r"[\d\s/.-]+", value):
            return
        seen.add(key)
        terms.append(value)

    for item in explicit or []:
        add(str(item))

    text = _clean(prompt)
    if text:
        # A marker is a whole word. Scan each comma/clause so "no X, Y, or Z"
        # keeps the exclusion context across the list, while a new instruction
        # such as "but make it funny" ends that list.
        continuation = False
        for clause in re.split(r"[,;\n]+|(?<=[.!?])\s+", text):
            matches = list(_MARKER_RE.finditer(clause))
            if matches:
                continuation = True
                for index, match in enumerate(matches):
                    stop = matches[index + 1].start() if index + 1 < len(matches) else len(clause)
                    tail = clause[match.end():stop]
                    tail = re.sub(r"^[\s:=-]+", "", tail)
                    previous = None
                    while previous != tail:
                        previous = tail
                        tail = _OPTIONAL_LEAD.sub("", tail).strip()
                    for part in re.split(r"\s+(?:and|or)\s+", tail):
                        add(part)
            elif continuation:
                stripped = clause.strip()
                if re.match(
                    r"(?i)^(?:but|however|then|make|use|keep|add|include|"
                    r"with|for|so|plus)\b",
                    stripped,
                ):
                    continuation = False
                    continue
                stripped = re.sub(r"(?i)^(?:or|and)\s+", "", stripped)
                for part in re.split(r"\s+(?:and|or)\s+", stripped):
                    add(part)
            else:
                free = re.search(r"(?i)\b([a-z][\w -]{1,36}?)[- ]free\b", clause)
                if free:
                    add(free.group(1))
    return terms


def _contains_term(text: str, term: str) -> bool:
    haystack = " " + _normalise(text) + " "
    needle = _normalise(term)
    if not needle:
        return False
    forms = {needle}
    if needle.endswith("s") and len(needle) > 3:
        forms.add(needle[:-1])
    elif len(needle) > 3:
        forms.add(needle + "s")
    for form in forms:
        if re.search(r"[a-z]", form):
            if f" {form} " in haystack:
                return True
        elif form in haystack:
            return True
    return False


def story_text(story: dict) -> str:
    parts = [str(story.get("title") or "")]
    for sentence in story.get("sentences") or []:
        parts.append(str(sentence.get("text") or ""))
    return " ".join(part for part in parts if part)


def _match_evidence(story: dict, term: str) -> dict:
    for sentence in story.get("sentences") or []:
        if _contains_term(str(sentence.get("text") or ""), term):
            return {
                "type": "transcript",
                "text": f"Excluded term '{term}' appears in: {clipset._clip_text(sentence.get('text'), 120)}",
                "scene": sentence.get("scene"),
                "time": round(_safe_float(sentence.get("start")), 3),
            }
    hook = story.get("hook") or {}
    return {
        "type": "structure",
        "text": f"Excluded term '{term}' matched the story title or hook.",
        "scene": hook.get("scene"),
        "time": round(_safe_float(hook.get("start")), 3),
    }


def _signals(story: dict) -> dict:
    breakdown = story.get("score_breakdown") or {}
    if breakdown:
        return {
            key: round(_clamp(_safe_float(breakdown.get(key), 0.5)), 4)
            for key in V2_WEIGHTS
        }
    hook = story.get("hook") or {}
    text = str(hook.get("text") or story.get("title") or "")
    sentences = story.get("sentences") or []
    full = " ".join(str(item.get("text") or "") for item in sentences)
    words = re.findall(r"[a-z0-9']+|[\u4e00-\u9fff]", full.lower())
    variety = len(set(words)) / max(1, len(words))
    terminal = bool(sentences) and clipset._terminal_text(
        sentences[-1].get("text") if sentences else "",
    )
    return {
        "hook_score": round(_clamp(hook_text_score(text)), 4),
        "speech_coherence": round(_clamp(0.55 + 0.45 * variety), 4),
        "audio_energy": 0.5,
        "visual_quality": 0.5,
        "payoff_position": 1.0 if terminal else 0.5,
        "novelty": round(
            _clamp(_safe_float(breakdown.get("novelty"), 0.8)), 4,
        ),
    }


def _evidence_entry(
    evidence_type: str,
    text: str,
    scene,
    time,
) -> dict:
    return {
        "type": evidence_type if evidence_type in _ALLOWED_EVIDENCE else "structure",
        "text": text,
        "scene": scene,
        "time": round(_safe_float(time), 3),
    }


def _v2_evidence(story: dict, signals: dict) -> list[dict]:
    hook = story.get("hook") or {}
    scene = hook.get("scene")
    time = hook.get("start")
    evidence: list[dict] = []
    for item in story.get("evidence") or []:
        if not isinstance(item, dict) or not item.get("text"):
            continue
        evidence.append(_evidence_entry(
            str(item.get("type") or "structure"),
            str(item.get("text")),
            item.get("scene"),
            item.get("time"),
        ))
    evidence.extend([
        _evidence_entry(
            "structure",
            f"Hook signal {signals['hook_score']:.2f}: "
            f"{clipset._clip_text(hook.get('text'), 110)}",
            scene, time,
        ),
        _evidence_entry(
            "structure",
            f"Speech coherence {signals['speech_coherence']:.2f} across "
            f"{len(story.get('sentences') or [])} sentence(s).",
            scene, time,
        ),
        _evidence_entry(
            "audio",
            f"Audio energy {signals['audio_energy']:.2f} from scene scores.",
            scene, time,
        ),
        _evidence_entry(
            "visual",
            f"Visual quality {signals['visual_quality']:.2f} from scene scores.",
            scene, time,
        ),
        _evidence_entry(
            "structure",
            f"Payoff position {signals['payoff_position']:.2f}: the story ends on "
            "its final selected sentence.",
            (story.get("payoff") or {}).get("scene"),
            (story.get("payoff") or {}).get("start"),
        ),
        _evidence_entry(
            "structure",
            f"Novelty {signals['novelty']:.2f} against earlier stories.",
            scene, time,
        ),
    ])
    return evidence


def _shorten(text: str, limit: int) -> str:
    value = _clean(text)
    if len(value) <= limit:
        return value
    words = value.split()
    out: list[str] = []
    for word in words:
        candidate = " ".join([*out, word])
        if len(candidate) > limit:
            break
        out.append(word)
    if not out:
        return value[:limit].rstrip()
    return " ".join(out).rstrip(" ,;:-") + "…"


def _hook_source(
    label: str,
    text: str,
    sentence: dict,
    story_id: str,
    index: int,
    extra: dict | None = None,
) -> dict:
    value = {
        "id": f"hk_{story_id}_{index}",
        "story_id": story_id,
        "source": label,
        "text": text,
        "sentence": sentence.get("id"),
        "scene": sentence.get("scene"),
        "start": round(_safe_float(sentence.get("start")), 3),
        "end": round(_safe_float(sentence.get("end")), 3),
        "time": round(_safe_float(sentence.get("start")), 3),
        "score": round(_clamp(hook_text_score(text)), 4),
        "trimmed": bool(extra and extra.get("trimmed")),
        "evidence": [{
            "type": "transcript",
            "text": f"Hook candidate ({label}): {clipset._clip_text(text, 120)}",
            "scene": sentence.get("scene"),
            "time": round(_safe_float(sentence.get("start")), 3),
        }],
    }
    if extra:
        value.update(extra)
    return value


def hook_candidates(story: dict, limit: int = 3) -> list[dict]:
    """Three deterministic hook options built only from story sentences."""
    sentences = story.get("sentences") or []
    if not sentences:
        return []
    story_id = str(story.get("id") or "story")
    first = sentences[0]
    pool: list[tuple[str, str, dict, dict | None]] = [
        ("opening", _clean(first.get("text")), first, None),
    ]
    if len(sentences) > 1:
        pool.append(("lead_in", _clean(sentences[1].get("text")), sentences[1], None))
    if len(sentences) > 2:
        pool.append(("payoff_tease", _clean(sentences[-1].get("text")), sentences[-1], None))
    pool.extend([
        (
            "opening_trim",
            _shorten(first.get("text"), 64),
            first,
            {"trimmed": True},
        ),
        (
            "opening_micro",
            _shorten(first.get("text"), 40),
            first,
            {"trimmed": True},
        ),
    ])

    hooks: list[dict] = []
    seen: set[str] = set()
    for label, text, sentence, extra in pool:
        value = _clean(text)
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        hooks.append(_hook_source(
            label, value, sentence, story_id, len(hooks), extra,
        ))
        if len(hooks) >= limit:
            break
    return hooks[:limit]


def rank_stories(
    stories: list[dict],
    prompt: str = "",
    exclusions: Iterable[str] | None = None,
    scenes: list[dict] | None = None,
    source_duration: float | None = None,
    limit: int | None = None,
) -> dict:
    """Rank stories with v2. Prompt-matching stories are excluded, not downranked."""
    terms = parse_exclusions(prompt, exclusions)
    ranked: list[dict] = []
    excluded: list[dict] = []
    for original in stories or []:
        story = copy.deepcopy(original)
        text = story_text(story)
        matched = [term for term in terms if _contains_term(text, term)]
        if matched:
            hook = story.get("hook") or {}
            excluded.append({
                "id": story.get("id"),
                "title": story.get("title"),
                "matched_exclusions": matched,
                "why": "Prompt exclusion matched: " + ", ".join(matched),
                "start": story.get("start"),
                "end": story.get("end"),
                "evidence": [_match_evidence(story, matched[0])],
            })
            continue
        signals = _signals(story)
        total = sum(V2_WEIGHTS[key] * signals[key] for key in V2_WEIGHTS)
        ranked_story = story
        ranked_story["v2"] = {
            "version": 2,
            "weights": dict(V2_WEIGHTS),
            "score": round(total * 100, 2),
            "prompt_exclusions": terms,
        }
        ranked_story["v2_score"] = round(total * 100, 2)
        ranked_story["v2_breakdown"] = signals
        ranked_story["v2_evidence"] = _v2_evidence(story, signals)
        ranked_story["hook_candidates"] = hook_candidates(story, 3)
        ranked_story["hook_candidates_complete"] = (
            len(ranked_story["hook_candidates"]) >= 3
        )
        ranked_story["why"] = (
            f"Selection v2 score {total * 100:.1f}: hook {signals['hook_score']:.2f}, "
            f"coherence {signals['speech_coherence']:.2f}, "
            f"audio {signals['audio_energy']:.2f}, "
            f"visual {signals['visual_quality']:.2f}, "
            f"payoff {signals['payoff_position']:.2f}, "
            f"novelty {signals['novelty']:.2f}."
        )
        if scenes is not None:
            try:
                ranked_story["plan"] = clipset.story_to_plan(
                    story,
                    scenes,
                    target=int(round(_safe_float(story.get("dur"), 30.0))),
                )
            except clipset.ClipSetError as exc:
                ranked_story["plan"] = None
                ranked_story["plan_error"] = str(exc)
        ranked.append(ranked_story)

    ranked.sort(key=lambda story: (
        -_safe_float(story.get("v2_score")),
        _safe_float(story.get("start")),
        str(story.get("id") or ""),
    ))
    if limit is not None:
        ranked = ranked[: max(0, int(limit))]
    note = None
    if not ranked:
        if excluded:
            note = "Every candidate matched a prompt exclusion."
        else:
            note = "No story candidates were available to rank."
    return {
        "version": 2,
        "explicit": True,
        "prompt": prompt,
        "exclusions": terms,
        "ranked": ranked,
        "excluded": excluded,
        "count": len(ranked),
        "note": note,
        "default_plan_unchanged": True,
    }
