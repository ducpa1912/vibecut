"""Local frame reader: Apple Vision OCR + face + attention saliency.

Compiles a tiny Swift helper on first use. Everything stays on this machine.
On non-macOS systems, or if Swift is unavailable, callers fall back to
center crops and no on-screen text.

OCR lines may carry several Vision candidates. ``choose_ocr_candidate``
re-ranks those candidates with lexical evidence and only accepts a brand/URL
when it is both present in the candidate list and reasonably confident.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("vibecut.vision")
ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "tools" / "vision_probe.swift"
BINARY = ROOT / "bin" / "vision_probe"
_checked = False
_ok = False
_lock = threading.Lock()

# Keep this list small and in sync with overlayWords in the Swift helper. Each
# entry is a hint for Apple Vision and lexical evidence for the Python
# selector, not a brand-replacement dictionary.
CUSTOM_WORDS: tuple[str, ...] = (
    "LINKTREE",
    "linktr.ee",
    "Instagram",
    "TikTok",
    "YouTube",
    "RedNote",
    "Xiaohongshu",
)
_CUSTOM_BY_KEY = {word.casefold(): word for word in CUSTOM_WORDS}
_CUSTOM_TOKEN_RE = re.compile(
    r"(?<![0-9A-Za-z])(?:"
    + "|".join(
        re.escape(word.casefold())
        for word in sorted(CUSTOM_WORDS, key=len, reverse=True)
    )
    + r")(?![0-9A-Za-z])",
    re.IGNORECASE,
)
_URL_RE = re.compile(
    r"(?:https?://|www\.)[^\s]+"
    r"|\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}(?:/[^\s]*)?",
    re.IGNORECASE,
)
_HASHTAG_RE = re.compile(r"#[0-9A-Za-z_\u3400-\u9fff]+")
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_LETTER_SPACING_RE = re.compile(
    r"(?<![0-9A-Za-z])(?:[A-Z](?:[ \t\u00a0\u00b7\-]+)){2,}[A-Z](?![0-9A-Za-z])"
)
_COMMON_ENGLISH = frozenset(
    """
    a about account after again all also am an and any are as at be because been
    before being bio but buy by can channel click could did do does follow for
    free from get got had has have he her here him his how i if in into is it
    its just know like link live me more my new no not now of on one only or our
    out over profile see she shop so some subscribe than that the their them
    then there these they this to today too up us use very video want was watch
    we were what when where which who why will with you your
    """.split()
)
_COMMON_CHINESE = (
    "关注", "点赞", "评论", "收藏", "分享", "链接", "主页",
    "视频", "直播", "订阅", "博主", "频道", "小红书", "抖音",
    "微博", "微信",
)

# A brand/URL candidate must clear this confidence before it can win. A generic
# high-confidence alternative needs both a larger score and confidence lead.
_MIN_LEXICAL_CONFIDENCE = 0.30
_MIN_ALTERNATIVE_CONFIDENCE = 0.55
_MIN_ALTERNATIVE_DELTA = 0.12


def correct_ocr_text(text: str) -> str:
    """Normalize whitespace and join obviously letter-spaced all-caps text.

    ``"L I N K T R E E"`` becomes ``"LINKTREE"``. Only runs of single ASCII
    uppercase letters are joined, so ordinary words and Chinese text survive.
    """
    if not isinstance(text, str):
        return ""
    value = unicodedata.normalize("NFKC", text)
    value = value.replace("\u200b", "").replace("\ufeff", "")
    value = " ".join(value.split())
    value = _LETTER_SPACING_RE.sub(lambda match: re.sub(r"[^A-Z]", "", match.group(0)), value)
    return value.strip()


@dataclass(frozen=True)
class _Candidate:
    text: str
    confidence: float
    order: int


def _confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return min(1.0, max(0.0, number))


def _raw_candidate(item: Any) -> tuple[str, float] | None:
    if isinstance(item, str):
        return item, 0.0
    if isinstance(item, dict):
        text = item.get("text") or item.get("string") or item.get("value")
        confidence = item.get("confidence", item.get("score", 0.0))
        return (str(text), _confidence(confidence)) if text is not None else None
    if isinstance(item, (tuple, list)) and item:
        confidence = item[1] if len(item) > 1 else 0.0
        return str(item[0]), _confidence(confidence)
    text = getattr(item, "text", None)
    if text is not None:
        return str(text), _confidence(getattr(item, "confidence", 0.0))
    return None


def _prepare_candidates(candidates: Any) -> list[_Candidate]:
    if candidates is None:
        return []
    if (
        isinstance(candidates, tuple)
        and len(candidates) == 2
        and isinstance(candidates[1], (int, float))
    ):
        candidates = [candidates]
    elif isinstance(candidates, (str, dict)) or not isinstance(candidates, (list, tuple)):
        candidates = [candidates]
    prepared: dict[str, _Candidate] = {}
    for order, item in enumerate(candidates):
        parsed = _raw_candidate(item)
        if parsed is None:
            continue
        cleaned = correct_ocr_text(parsed[0])
        if not cleaned:
            continue
        key = cleaned.casefold()
        candidate = _Candidate(cleaned, parsed[1], order)
        current = prepared.get(key)
        if current is None or candidate.confidence > current.confidence:
            prepared[key] = candidate
    return list(prepared.values())


def _lexical_evidence(text: str) -> tuple[float, bool, bool]:
    """Return (bonus, custom_word_present, url_present) for a candidate."""
    cleaned = correct_ocr_text(text)
    if not cleaned:
        return 0.0, False, False
    folded = cleaned.casefold()
    exact_custom = folded in _CUSTOM_BY_KEY
    custom = exact_custom or bool(_CUSTOM_TOKEN_RE.search(cleaned))
    url = bool(_URL_RE.search(cleaned))
    bonus = 0.0
    if exact_custom:
        bonus += 0.38
    elif custom:
        bonus += 0.24
    if url:
        bonus += 0.22
    if _HASHTAG_RE.search(cleaned):
        bonus += 0.07
    chinese = sum(1 for token in _COMMON_CHINESE if token in cleaned)
    if chinese:
        bonus += min(0.06, 0.02 * chinese)
    elif _CJK_RE.search(cleaned):
        bonus += 0.04
    tokens = re.findall(r"[a-z]+", folded)
    common = sum(1 for token in tokens if token in _COMMON_ENGLISH)
    if common:
        bonus += min(0.08, 0.015 * common)
    if re.search(r"\b[A-Z]{3,}\b", cleaned):
        bonus += 0.02
    return min(0.60, bonus), custom, url


def _canonical_custom(text: str) -> str:
    cleaned = correct_ocr_text(text)
    return _CUSTOM_BY_KEY.get(cleaned.casefold(), cleaned)


def choose_ocr_candidate(
    candidates: Any,
    original: str | None = None,
    *,
    min_lexical_confidence: float = _MIN_LEXICAL_CONFIDENCE,
    min_alternative_confidence: float = _MIN_ALTERNATIVE_CONFIDENCE,
    min_alternative_delta: float = _MIN_ALTERNATIVE_DELTA,
) -> str:
    """Pick the safest OCR text from Vision's ranked candidates.

    Selection is confidence plus lexical evidence (custom overlay words, URLs,
    hashtags, common English words, Chinese characters). A brand or URL can
    only win when it is one of the supplied candidates and clears the evidence
    confidence floor. Otherwise the original text is preserved. The function
    never invents a brand from unrelated text.
    """
    prepared = _prepare_candidates(candidates)
    original_text = correct_ocr_text(original or "")
    if not prepared:
        return original_text
    if not original_text:
        original_text = prepared[0].text

    baseline = next(
        (item for item in prepared if item.text.casefold() == original_text.casefold()),
        None,
    )
    if baseline is None:
        baseline = _Candidate(original_text, prepared[0].confidence, -1)

    baseline_bonus, baseline_custom, baseline_url = _lexical_evidence(baseline.text)
    baseline_score = baseline.confidence + baseline_bonus

    def score(item: _Candidate) -> float:
        return item.confidence + _lexical_evidence(item.text)[0]

    best = max(prepared, key=lambda item: (score(item), item.confidence, -item.order))
    best_bonus, best_custom, best_url = _lexical_evidence(best.text)
    best_score = best.confidence + best_bonus

    if best.text.casefold() == original_text.casefold():
        return _canonical_custom(original_text)

    # Never churn between two already-brand/URL-like readings. The original
    # line is a valid lexical reading, so a different candidate has to be
    # handled by normal confidence rules, not brand evidence alone.
    if baseline_custom or baseline_url:
        return original_text

    exact_custom = _CUSTOM_BY_KEY.get(best.text.casefold())
    if exact_custom:
        if best.confidence >= min_lexical_confidence:
            return exact_custom
        return original_text

    if (best_custom or best_url) and best.confidence >= min_lexical_confidence:
        if best_score >= baseline_score + 0.04:
            return correct_ocr_text(best.text)
        return original_text

    if (
        best.confidence >= min_alternative_confidence
        and best.confidence >= baseline.confidence + min_alternative_delta
        and best_score >= baseline_score + min_alternative_delta
    ):
        return correct_ocr_text(best.text)
    return original_text


def _correct_record_text(record: dict) -> None:
    """Apply OCR candidate selection in place, keeping line structure intact."""
    lines = record.get("text")
    if not isinstance(lines, list):
        return
    for line in lines:
        if not isinstance(line, dict):
            continue
        original = str(line.get("text") or "")
        chosen = choose_ocr_candidate(line.get("candidates"), original=original)
        if chosen and chosen != original:
            LOGGER.debug("OCR correction: %r -> %r", original, chosen)
            line["original_text"] = original
            line["text"] = chosen


def _build() -> bool:
    global _checked, _ok
    if _checked:
        return _ok
    with _lock:
        if _checked:
            return _ok
        if sys.platform != "darwin" or not shutil.which("swiftc"):
            LOGGER.info("Apple Vision helper unavailable; using center crops.")
            _checked = True
            return False
        try:
            needs_build = (
                not BINARY.exists()
                or BINARY.stat().st_mtime < SOURCE.stat().st_mtime
            )
            if needs_build:
                BINARY.parent.mkdir(parents=True, exist_ok=True)
                LOGGER.info("Compiling Vision helper…")
                result = subprocess.run(
                    ["swiftc", "-O", "-swift-version", "5", str(SOURCE), "-o", str(BINARY)],
                    capture_output=True, text=True, timeout=180,
                )
                if result.returncode != 0:
                    LOGGER.warning("Vision helper compile failed: %s", result.stderr[-800:])
                    _checked = True
                    return False
            _ok = True
        except Exception as exc:
            LOGGER.warning("Vision helper unavailable: %s", exc)
            _ok = False
        _checked = True
        return _ok


def available() -> bool:
    return _build()


def probe_images(directory: Path, files: list[Path] | None = None) -> dict[str, dict]:
    """Return {filename: {text, faces, salient, width, height}}.

    Each ``text`` line keeps its original confidence and gains optional
    ``candidates``/``box`` fields plus ``original_text`` when correction
    changed it. Pass ``files`` to analyze only those stills. The helper reads a
    directory, so selected files are linked into a temporary directory first.
    """
    if not _build() or not directory.is_dir():
        return {}
    if files is None:
        jpgs = sorted(directory.glob("*.jpg"))
        target = directory
        cleanup = None
    else:
        jpgs = [path for path in files if path.is_file()]
        if not jpgs:
            return {}
        cleanup = tempfile.TemporaryDirectory(prefix=".vision-", dir=directory)
        target = Path(cleanup.name)
        for path in jpgs:
            try:
                os.link(path, target / path.name)
            except OSError:
                shutil.copy2(path, target / path.name)
    try:
        try:
            result = subprocess.run(
                [str(BINARY), str(target)],
                capture_output=True, text=True,
                timeout=max(180, len(jpgs) * 0.8),
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("Vision helper timed out on %d frames.", len(jpgs))
            return {}
        if result.returncode != 0:
            LOGGER.warning("Vision helper failed: %s", result.stderr[-800:])
            return {}
        output: dict[str, dict] = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if item.get("file"):
                _correct_record_text(item)
                output[item["file"]] = item
        if result.stderr.strip():
            LOGGER.debug("vision stderr: %s", result.stderr[-400:])
        return output
    finally:
        if cleanup:
            cleanup.cleanup()


def probe_image(path: Path) -> dict:
    return probe_images(path.parent, files=[path]).get(path.name, {})
