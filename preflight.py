"""Muted-first preflight checks for a story or ready render.

Each check can be toggled independently from ``settings.preflight`` or
``job.preflight``. Findings are advisory unless a check's severity is set to
``block``. Every finding carries the toggle that produced it, and the response
also exposes check-level style, toggle, and severity metadata for the UI.
"""

from __future__ import annotations

import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

import exports
import history_store

CHECK_SPECS = (
    {
        "id": "dangling_claims",
        "label": "Dangling claims",
        "style": "copy",
        "default_toggle": True,
        "default_severity": "warn",
        "suggestion": (
            "Remove the forward reference, or add the promised beat before the payoff."
        ),
    },
    {
        "id": "truncated_payoff",
        "label": "Truncated payoff",
        "style": "edit",
        "default_toggle": True,
        "default_severity": "warn",
        "suggestion": (
            "Extend the final clip until the payoff sentence finishes, or re-cut the ending."
        ),
    },
    {
        "id": "caption_density",
        "label": "Caption density",
        "style": "captions",
        "default_toggle": True,
        "default_severity": "warn",
        "suggestion": (
            "Split the cue or shorten the text so pace stays under 20 characters per second."
        ),
    },
    {
        "id": "safe_zone_contrast",
        "label": "Safe-zone contrast",
        "style": "frame",
        "default_toggle": True,
        "default_severity": "warn",
        "suggestion": (
            "Move captions to a calmer area, add a subtle plate, or pick a darker cover frame."
        ),
    },
    {
        "id": "loudness",
        "label": "Loudness",
        "style": "audio",
        "default_toggle": True,
        "default_severity": "warn",
        "suggestion": (
            "Normalize the final mix to about -14 LUFS without clipping."
        ),
    },
)

CHECK_IDS = tuple(spec["id"] for spec in CHECK_SPECS)
CHECK_BY_ID = {spec["id"]: spec for spec in CHECK_SPECS}
SEVERITIES = ("info", "warn", "block")
SEVERITY_ALIASES = {
    "info": "info", "notice": "info", "low": "info",
    "warn": "warn", "warning": "warn", "medium": "warn",
    "block": "block", "blocking": "block", "high": "block", "error": "block",
}
MAX_CAPTION_CPS = 20.0
TARGET_LUFS = -14.0
LOW_LUFS = -16.0
HIGH_LUFS = -12.0
FORWARD_RE = re.compile(
    r"\b(?:"
    r"later|coming up|stay tuned|next up|in a moment|at the end|"
    r"i(?:'ll| will) (?:show|tell|explain|cover)|let me show|"
    r"we(?:'ll| will) (?:cover|show|talk about|get to|learn)|"
    r"this video (?:will|is about)|here(?:'s| is) (?:how|why|what)|"
    r"you(?:'ll| will) (?:learn|see|find out)"
    r")\b",
    re.IGNORECASE,
)
PROMISE_RE = re.compile(
    r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)"
    r"\s+(?:things|ways|tips|steps|reasons|lessons|mistakes|rules|secrets|questions)\b",
    re.IGNORECASE,
)
DANGLING_END_RE = re.compile(
    r"(?:\b(?:and|but|or|so|because|which|that|with|for|to|of|the|a|an)\s*[,;:]?|[,;:\-])\s*$",
    re.IGNORECASE,
)
TERMINAL_RE = re.compile(r"""[.!?…"'”’)\]]\s*$""")
CONNECTOR_RE = re.compile(
    r"\b(?:and|but|or|so|because|which|that|with|for|to|of|the|a|an)\W*$",
    re.IGNORECASE,
)


class PreflightError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        suggestion: str = "",
        status: int = 404,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.suggestion = suggestion
        self.status = int(status)

    def as_detail(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "suggestion": self.suggestion,
        }


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return []


def _section(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _severity(value: object) -> str | None:
    return SEVERITY_ALIASES.get(str(value or "").strip().lower())


def resolve_config(settings: dict | None = None, job: dict | None = None) -> dict:
    """Merge global and per-job toggles/severities/styles. Job wins."""
    toggles = {spec["id"]: bool(spec["default_toggle"]) for spec in CHECK_SPECS}
    severities = {spec["id"]: spec["default_severity"] for spec in CHECK_SPECS}
    styles = {spec["id"]: spec["style"] for spec in CHECK_SPECS}

    def apply(raw: object) -> None:
        section = _section(raw)
        if not section:
            return
        nested_toggles = _section(section.get("toggles"))
        if not nested_toggles:
            nested_toggles = _section(section.get("checks"))
        for check_id in CHECK_IDS:
            if check_id in nested_toggles and isinstance(nested_toggles[check_id], bool):
                toggles[check_id] = nested_toggles[check_id]
            value = section.get(check_id)
            if isinstance(value, bool):
                toggles[check_id] = value
            elif isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {"off", "false", "disabled", "no", "0"}:
                    toggles[check_id] = False
                elif lowered in {"on", "true", "enabled", "yes", "1"}:
                    toggles[check_id] = True
                else:
                    severity = _severity(lowered)
                    if severity:
                        severities[check_id] = severity
            elif isinstance(value, dict):
                if isinstance(value.get("enabled"), bool):
                    toggles[check_id] = value["enabled"]
                severity = _severity(value.get("severity"))
                if severity:
                    severities[check_id] = severity
                style = str(value.get("style") or "").strip()
                if style:
                    styles[check_id] = style[:40]
        for key in ("severity", "severities"):
            values = _section(section.get(key))
            for check_id in CHECK_IDS:
                severity = _severity(values.get(check_id))
                if severity:
                    severities[check_id] = severity
        for key in ("styles", "style"):
            values = _section(section.get(key))
            for check_id in CHECK_IDS:
                style = str(values.get(check_id) or "").strip()
                if style:
                    styles[check_id] = style[:40]

    if isinstance(settings, dict):
        apply(settings.get("preflight") if isinstance(settings.get("preflight"), dict) else settings)
    if isinstance(job, dict):
        apply(job.get("preflight"))
    return {"toggles": toggles, "severities": severities, "styles": styles}


# ------------------------------------------------------------------ context


def _job_path(job_dir: Path | None, raw: object, subdirs: tuple[str, ...] = ()) -> Path | None:
    if job_dir is None:
        return None
    text = str(raw or "").strip()
    if not text:
        return None
    path = Path(text)
    if path.is_absolute():
        return path if path.is_file() else None
    root = Path(job_dir)
    candidates = [root / path]
    if len(path.parts) == 1:
        candidates.extend(root / name / path for name in subdirs)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _parse_time(value: str) -> float | None:
    text = str(value or "").strip().replace(",", ".")
    match = re.fullmatch(r"(?:(\d+):)?(\d{1,2}):(\d{1,2}(?:\.\d+)?)", text)
    if not match:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = float(match.group(3))
    return hours * 3600 + minutes * 60 + seconds


def parse_srt(text: str) -> list[dict]:
    cues: list[dict] = []
    blocks = re.split(r"\n\s*\n", str(text or "").replace("\r\n", "\n"))
    for block in blocks:
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        index = 1 if "-->" not in lines[0] else 0
        if index >= len(lines) or "-->" not in lines[index]:
            continue
        left, right = lines[index].split("-->", 1)
        start = _parse_time(left)
        end = _parse_time(right)
        body = " ".join(lines[index + 1:]).strip()
        if start is None or end is None or end <= start or not body:
            continue
        cues.append({"start": round(start, 3), "end": round(end, 3), "text": body})
    return cues


def _normalize_cues(raw: object) -> list[dict]:
    if isinstance(raw, str):
        return parse_srt(raw) if "-->" in raw else []
    if not isinstance(raw, list):
        return []
    cues: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            start = float(item.get("start"))
            end = float(item.get("end"))
        except (TypeError, ValueError):
            continue
        text = " ".join(str(item.get("text") or "").split())
        if not text or not math.isfinite(start) or not math.isfinite(end) or end <= start:
            continue
        cues.append({"start": round(start, 3), "end": round(end, 3), "text": text})
    return cues


def _scene_map(job: dict) -> dict:
    scenes = (job.get("analysis") or {}).get("scenes") or []
    mapped: dict = {}
    for scene in scenes:
        if not isinstance(scene, dict) or scene.get("id") is None:
            continue
        try:
            scene_id = int(scene["id"])
        except (TypeError, ValueError):
            continue
        mapped[scene_id] = scene
    return mapped


def _scene_text(scene: dict | None) -> str:
    if not isinstance(scene, dict):
        return ""
    return " ".join(str(scene.get("speech") or scene.get("ocr") or "").split())


def _clip_text(clip: dict, scenes: dict) -> str:
    if not isinstance(clip, dict):
        return ""
    text = str(clip.get("text") or "").strip()
    if text:
        return " ".join(text.split())
    try:
        scene_id = int(clip.get("scene"))
    except (TypeError, ValueError):
        return ""
    return _scene_text(scenes.get(scene_id))


def _cues_from_plan(plan: dict | None, scenes: dict) -> list[dict]:
    plan = plan if isinstance(plan, dict) else {}
    clips = [clip for clip in (plan.get("clips") or []) if isinstance(clip, dict)]
    if not clips:
        return []
    if scenes:
        try:
            scene_rows = [scenes[key] for key in sorted(scenes)]
            cues = exports.plan_cues(plan, clips, scene_rows)
            return _normalize_cues(cues)
        except Exception:  # noqa: BLE001 - preflight must stay advisory
            pass
    cues: list[dict] = []
    offset = 0.0
    for clip in clips:
        try:
            duration = float(clip.get("dur") or (float(clip.get("end")) - float(clip.get("start"))))
        except (TypeError, ValueError):
            duration = 0.0
        text = str(clip.get("text") or "").strip()
        if text and duration > 0.2:
            cues.append({
                "start": round(offset, 3),
                "end": round(offset + duration, 3),
                "text": text,
            })
        offset += max(0.0, duration)
    return cues


def _plan_with_target(job: dict, target: object, *, exact: bool = False) -> dict | None:
    try:
        target = int(target)
    except (TypeError, ValueError):
        target = None
    plans = (job.get("analysis") or {}).get("plans") or {}
    if isinstance(plans, dict):
        keys = [str(target)] if target is not None else []
        if not exact:
            keys.extend(["30", "15", "60"])
        for key in keys:
            plan = plans.get(key)
            if isinstance(plan, dict) and plan.get("clips"):
                return plan
    return None


def _simple_plan(job: dict, target: int) -> dict | None:
    scenes = [
        scene for scene in ((job.get("analysis") or {}).get("scenes") or [])
        if isinstance(scene, dict) and not scene.get("black")
    ]
    scenes.sort(key=lambda scene: (float(scene.get("start") or 0.0), scene.get("id") or 0))
    if not scenes:
        return None
    clips: list[dict] = []
    total = 0.0
    for scene in scenes:
        try:
            start = float(scene.get("start") or 0.0)
            end = float(scene.get("end") or (start + float(scene.get("dur") or 0.0)))
        except (TypeError, ValueError):
            continue
        if end - start <= 0.1:
            continue
        if total >= target:
            break
        clip_end = min(end, start + max(0.2, target - total))
        clips.append({
            "scene": scene.get("id"),
            "start": round(start, 3),
            "end": round(clip_end, 3),
            "dur": round(clip_end - start, 3),
            "role": "beat",
        })
        total += clip_end - start
    if not clips:
        return None
    clips[0]["role"] = "hook"
    if len(clips) > 1:
        clips[-1]["role"] = "payoff"
    return {
        "target": target,
        "total": round(total, 3),
        "hook_scene": clips[0].get("scene"),
        "auto": False,
        "clip_count": len(clips),
        "clips": clips,
        "note": "Fallback plan for preflight",
    }


def _fallback_plan(job: dict, target: object, hook: object) -> dict | None:
    scenes = (job.get("analysis") or {}).get("scenes") or []
    try:
        target_int = int(target)
    except (TypeError, ValueError):
        return None
    if not scenes:
        return None
    duration = float((job.get("source") or {}).get("duration") or 0.0)
    if duration <= 0:
        try:
            duration = max(float(scene.get("end") or 0.0) for scene in scenes if isinstance(scene, dict))
        except (TypeError, ValueError):
            duration = 0.0
    if duration > 0:
        try:
            import pipeline

            hook_int = int(hook) if hook is not None else None
            plan = pipeline.build_plan(
                scenes, duration, target_int, hook_int,
                (job.get("analysis") or {}).get("hook_scene"),
            )
            if isinstance(plan, dict) and plan.get("clips"):
                return plan
        except Exception:  # noqa: BLE001
            pass
    return _simple_plan(job, target_int)


def _plan_from_history(job_dir: Path | None, record: dict) -> dict | None:
    if job_dir is None:
        return None
    entry_id = str(record.get("history_id") or "").strip()
    if not entry_id:
        return None
    try:
        item = history_store.get_entry(Path(job_dir), entry_id)
    except Exception:  # noqa: BLE001
        return None
    plan = ((item or {}).get("snapshot") or {}).get("plan")
    return plan if isinstance(plan, dict) and plan.get("clips") else None


def _plan_from_entry(entry: dict) -> dict | None:
    plan = entry.get("plan")
    if isinstance(plan, dict) and plan.get("clips"):
        return plan
    clips = entry.get("clips")
    if isinstance(clips, list) and clips:
        total = 0.0
        for clip in clips:
            try:
                total += float(clip.get("dur") or 0.0)
            except (TypeError, ValueError):
                pass
        return {
            "target": entry.get("target"),
            "total": round(total, 3),
            "clip_count": len(clips),
            "hook_scene": entry.get("hook_scene"),
            "clips": clips,
        }
    return None


def _records(job: dict) -> dict:
    rows = job.get("renders") or {}
    return rows if isinstance(rows, dict) else {}


def _story_rows(job: dict) -> list[dict]:
    rows: list[dict] = []
    for raw in (job.get("stories"), job.get("story")):
        if isinstance(raw, dict):
            if all(isinstance(value, dict) for value in raw.values()):
                for key, value in raw.items():
                    row = dict(value)
                    row.setdefault("id", str(key))
                    rows.append(row)
            else:
                rows.append(dict(raw))
        elif isinstance(raw, list):
            rows.extend(dict(value) for value in raw if isinstance(value, dict))
    return rows


def _artifact_rows(job: dict) -> dict:
    raw = job.get("artifacts")
    rows: dict[str, dict] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            row = dict(value) if isinstance(value, dict) else {"path": value}
            row.setdefault("id", str(key))
            rows[str(row.get("id"))] = row
    elif isinstance(raw, list):
        for value in raw:
            if not isinstance(value, dict):
                continue
            row = dict(value)
            if not row.get("id") and row.get("artifact_id"):
                row["id"] = row["artifact_id"]
            if row.get("id"):
                rows[str(row["id"])] = row
    return rows


def _select_story(job: dict, story_id: str | None) -> dict:
    sid = " ".join(str(story_id or "").split())
    rows = _story_rows(job)
    records = _records(job)
    artifacts = _artifact_rows(job)

    if sid:
        for row in rows:
            if str(row.get("id") or "") == sid:
                return row
        if sid in records:
            return {"id": sid, "render_key": sid, "record": records[sid]}
        if sid in artifacts:
            return {"id": sid, "artifact": artifacts[sid]}
        plan = _plan_with_target(job, sid, exact=True)
        if plan:
            return {"id": sid, "plan": plan}
        try:
            target = int(sid)
        except (TypeError, ValueError):
            target = None
        if target is not None:
            plan = _fallback_plan(
                job, target, (job.get("analysis") or {}).get("hook_scene"),
            )
            if plan:
                return {"id": sid, "plan": plan}
        raise PreflightError(
            "story_not_found", f"Story {sid!r} was not found in this job.",
            suggestion="Pass a render key, artifact id, or saved story id.",
        )

    if rows:
        return rows[0]
    ready = [
        (key, record) for key, record in records.items()
        if isinstance(record, dict) and record.get("status") == "ready"
    ]
    if ready:
        preference = {"30": 0, "15": 1, "60": 2}
        ready.sort(key=lambda item: (
            preference.get(str(item[1].get("target") or ""), 3),
            item[1].get("target") or 0,
            item[0],
        ))
        key, record = ready[0]
        return {"id": key, "render_key": key, "record": record}
    plans = (job.get("analysis") or {}).get("plans") or {}
    if isinstance(plans, dict):
        for key in ("30", "15", "60", *plans.keys()):
            plan = plans.get(key)
            if isinstance(plan, dict) and plan.get("clips"):
                return {"id": str(key), "plan": plan}
    fallback = _fallback_plan(
        job, 30, (job.get("analysis") or {}).get("hook_scene"),
    )
    if fallback:
        return {"id": "30", "plan": fallback}
    raise PreflightError(
        "story_not_found", "This job has no story to preflight.",
        suggestion="Choose a target or render the cut first.",
    )


def _context(job: dict, story_id: str | None, job_dir: Path | None) -> dict:
    entry = _select_story(job, story_id)
    records = _records(job)
    render_key = str(entry.get("render_key") or entry.get("record_key") or "")
    record = entry.get("record")
    if not isinstance(record, dict) and render_key in records:
        record = records[render_key]
    record = record if isinstance(record, dict) else {}
    artifact = entry.get("artifact") if isinstance(entry.get("artifact"), dict) else {}
    story_id = str(entry.get("id") or render_key or (record.get("target") or "story"))

    plan = _plan_from_entry(entry)
    if plan is None:
        plan = _plan_from_entry(artifact)
    if plan is None:
        plan = _plan_from_entry(record)
    if plan is None:
        plan = _plan_from_history(job_dir, record)
    target_value = (
        record.get("target")
        or entry.get("target")
        or artifact.get("target")
    )
    if plan is None:
        plan = _plan_with_target(job, target_value)
    if plan is None:
        plan = _fallback_plan(
            job,
            target_value,
            record.get("hook") or entry.get("hook_scene") or artifact.get("hook"),
        )
    plan = plan if isinstance(plan, dict) else {}
    clips = [clip for clip in (plan.get("clips") or []) if isinstance(clip, dict)]
    scenes = _scene_map(job)

    raw_cues = (
        entry.get("cues")
        or entry.get("caption_cues")
        or entry.get("captions")
        or entry.get("captions_srt")
        or entry.get("srt")
        or artifact.get("cues")
        or artifact.get("captions_srt")
        or record.get("cues")
        or record.get("captions_srt")
        or record.get("srt")
    )
    if raw_cues is None and isinstance(job.get("captions"), dict):
        raw_cues = job["captions"].get(story_id) or job["captions"].get(render_key)
    cues = _normalize_cues(raw_cues)
    if not cues:
        caption_path = _job_path(
            job_dir,
            entry.get("captions_path") or artifact.get("captions_path") or record.get("captions_path"),
            ("captions", "renders"),
        )
        if caption_path is not None:
            try:
                cues = _normalize_cues(caption_path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                cues = []
    if not cues:
        cues = _cues_from_plan(plan, scenes)

    path_value = (
        entry.get("media_path")
        or entry.get("path")
        or artifact.get("path")
        or artifact.get("artifact_path")
        or artifact.get("video")
        or artifact.get("video_path")
        or artifact.get("file")
        or record.get("path")
    )
    media_path = _job_path(job_dir, path_value, ("renders", "artifacts", "media"))
    if media_path is None:
        source_path = (job.get("source") or {}).get("path")
        media_path = _job_path(job_dir, source_path) if source_path else None

    image_path = _job_path(
        job_dir,
        entry.get("image_path")
        or entry.get("poster_path")
        or entry.get("poster")
        or entry.get("cover_path")
        or artifact.get("poster")
        or artifact.get("poster_path")
        or record.get("poster")
        or record.get("poster_path"),
        ("renders", "covers", "artifacts", "media"),
    )

    return {
        "job": job,
        "job_dir": job_dir,
        "id": story_id,
        "render_key": render_key or None,
        "entry": entry,
        "record": record,
        "artifact": artifact,
        "plan": plan,
        "clips": clips,
        "scenes": scenes,
        "cues": cues,
        "media_path": media_path,
        "image_path": image_path,
        "hook_text": str(entry.get("hook_text") or record.get("hook_text") or "").strip(),
    }


def _number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _value_from_context(context: dict, keys: tuple[str, ...]) -> float | None:
    for source in (context.get("entry") or {}, context.get("record") or {}, context.get("artifact") or {}):
        for key in keys:
            value = _number(source.get(key))
            if value is not None:
                return value
    return None


def _loudness_from_context(context: dict) -> float | None:
    for source in (
        context.get("entry") or {},
        context.get("record") or {},
        context.get("artifact") or {},
        context.get("job") or {},
    ):
        loudness = source.get("loudness")
        if isinstance(loudness, dict):
            for key in ("integrated_lufs", "lufs", "integrated"):
                value = _number(loudness.get(key))
                if value is not None:
                    return value
        elif loudness is not None:
            value = _number(loudness)
            if value is not None:
                return value
        for key in ("loudness_lufs", "integrated_lufs", "lufs"):
            value = _number(source.get(key))
            if value is not None:
                return value
    return None


# ------------------------------------------------------------------- checks


def check_dangling_claims(context: dict) -> dict | None:
    plan = context.get("plan") or {}
    clips = context.get("clips") or []
    scenes = context.get("scenes") or {}
    explicit = bool(
        context.get("entry", {}).get("dangling_claim")
        or context.get("record", {}).get("dangling_claim")
        or plan.get("dangling_claim")
    )
    hook_text = context.get("hook_text") or (
        _clip_text(clips[0], scenes) if clips else ""
    )
    if not hook_text and not explicit:
        return None
    body_text = " ".join(_clip_text(clip, scenes) for clip in clips[1:]).strip()
    body_words = len(re.findall(r"\w+", body_text))
    forward = bool(FORWARD_RE.search(hook_text))
    promise = bool(PROMISE_RE.search(hook_text))
    dangling_end = bool(DANGLING_END_RE.search(hook_text))
    weak_body = len(clips) <= 2 or body_words < 25
    if not explicit and not ((forward or promise or dangling_end) and weak_body):
        return None
    phrase = " ".join(hook_text.split())[:90]
    return {
        "message": (
            f"The opening promises a payoff the selected clips do not deliver: {phrase!r}."
        ),
        "details": {
            "hook_text": phrase,
            "forward_reference": forward,
            "numbered_promise": promise,
            "clip_count": len(clips),
            "body_words": body_words,
        },
    }


def check_truncated_payoff(context: dict) -> dict | None:
    plan = context.get("plan") or {}
    clips = context.get("clips") or []
    scenes = context.get("scenes") or {}
    cues = context.get("cues") or []
    last = clips[-1] if clips else {}
    explicit = bool(
        plan.get("payoff_truncated")
        or context.get("entry", {}).get("payoff_truncated")
        or context.get("record", {}).get("payoff_truncated")
        or last.get("truncated")
        or last.get("end_truncated")
    )
    try:
        last_dur = float(last.get("dur") or 0.0)
    except (TypeError, ValueError):
        last_dur = 0.0
    text = _clip_text(last, scenes) if last else ""
    if cues:
        try:
            last_start = float(last.get("start") or 0.0)
        except (TypeError, ValueError):
            last_start = 0.0
        tail = [cue["text"] for cue in cues if float(cue.get("end") or 0.0) >= last_start]
        if tail:
            text = tail[-1]
    if not text and not explicit and last_dur >= 0.8:
        return None
    bad_ending = bool(CONNECTOR_RE.search(text)) or str(text).rstrip().endswith((",", ";", ":", "-"))
    terminal = bool(TERMINAL_RE.search(text))
    if not explicit and not bad_ending and not (0 < last_dur < 0.8):
        return None
    if explicit and not text:
        text = "the ending was marked incomplete"
    phrase = " ".join(str(text).split())[-90:]
    return {
        "message": f"The payoff ends before it resolves: {phrase!r}.",
        "details": {
            "last_clip_duration": round(last_dur, 3),
            "terminal_punctuation": terminal,
            "dangling_connector": bad_ending,
        },
    }


def check_caption_density(context: dict) -> dict | None:
    cues = context.get("cues") or []
    override = _value_from_context(context, ("caption_cps", "caption_density"))
    if override is not None:
        if override <= MAX_CAPTION_CPS:
            return None
        return {
            "message": (
                f"Caption density is {override:.1f} characters per second; "
                f"limit is {MAX_CAPTION_CPS:.0f}."
            ),
            "details": {"cps": round(override, 2), "limit": MAX_CAPTION_CPS},
        }
    if not cues:
        return {"unavailable": True, "reason": "No caption cues are attached to this story."}
    worst: tuple[float, int, dict] | None = None
    for index, cue in enumerate(cues, 1):
        try:
            duration = float(cue["end"]) - float(cue["start"])
        except (KeyError, TypeError, ValueError):
            continue
        if duration <= 0.05:
            continue
        chars = len(" ".join(str(cue.get("text") or "").split()))
        cps = chars / duration
        if worst is None or cps > worst[0]:
            worst = (cps, index, cue)
    if worst is None or worst[0] <= MAX_CAPTION_CPS:
        return None
    cps, index, cue = worst
    return {
        "message": (
            f"Caption {index} runs at {cps:.1f} characters per second; "
            f"limit is {MAX_CAPTION_CPS:.0f}."
        ),
        "details": {
            "cps": round(cps, 2),
            "limit": MAX_CAPTION_CPS,
            "cue": index,
            "cue_text": str(cue.get("text") or "")[:120],
        },
    }


def _extract_cover_frame(video: Path, destination: Path, seconds: float = 0.5) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not video.is_file():
        return False
    try:
        result = subprocess.run(
            [
                ffmpeg, "-y", "-v", "error", "-ss", f"{max(0.0, seconds):.3f}",
                "-i", str(video), "-frames:v", "1", "-vf", "scale=540:-2",
                "-q:v", "3", str(destination),
            ],
            capture_output=True, timeout=45,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return (
        result.returncode == 0
        and destination.is_file()
        and destination.stat().st_size > 0
    )


def _safe_zone_measure(path: Path) -> dict | None:
    try:
        from PIL import Image, ImageStat
    except Exception:  # noqa: BLE001
        return None
    try:
        with Image.open(path) as image:
            gray = image.convert("L")
            width, height = gray.size
            if width < 16 or height < 16:
                return None
            zone = gray.crop((
                int(width * 0.10), int(height * 0.62),
                int(width * 0.90), int(height * 0.90),
            ))
            stats = ImageStat.Stat(zone)
            luminance = max(0.0, min(1.0, float(stats.mean[0]) / 255.0))
            deviation = max(0.0, min(1.0, float(stats.stddev[0]) / 255.0))
    except Exception:  # noqa: BLE001
        return None
    contrast = (1.0 + 0.05) / (luminance + 0.05)
    return {
        "contrast": round(contrast, 2),
        "luminance": round(luminance, 3),
        "stddev": round(deviation, 3),
    }


def check_safe_zone_contrast(context: dict) -> dict | None:
    explicit = _value_from_context(context, ("safe_zone_contrast", "contrast"))
    ok = context.get("entry", {}).get("safe_zone_ok")
    if ok is None:
        ok = context.get("record", {}).get("safe_zone_ok")
    measured: dict | None = None
    if explicit is not None:
        measured = {"contrast": round(explicit, 2), "source": "metadata"}
    elif isinstance(context.get("entry", {}).get("safe_zone"), dict):
        zone = context["entry"]["safe_zone"]
        value = _number(zone.get("contrast"))
        if value is None:
            value = _number(zone.get("ratio"))
        if value is not None:
            measured = {
                "contrast": round(value, 2),
                "luminance": _number(zone.get("luminance")),
                "stddev": _number(zone.get("stddev")),
                "source": "metadata",
            }
        if zone.get("ok") is False:
            ok = False
    if measured is None and context.get("image_path") is not None:
        measured = _safe_zone_measure(context["image_path"])
        if measured is not None:
            measured["source"] = "poster"
    if measured is None and context.get("media_path") is not None:
        with tempfile.TemporaryDirectory(prefix="vibecut-preflight-") as temporary:
            cover = Path(temporary) / "cover.jpg"
            if _extract_cover_frame(context["media_path"], cover):
                measured = _safe_zone_measure(cover)
                if measured is not None:
                    measured["source"] = "ffmpeg"
    if measured is None and ok is True:
        return None
    if measured is None and ok is not False:
        return {"unavailable": True, "reason": "No poster or safe-zone sample is available."}
    contrast = measured.get("contrast") if measured else None
    stddev = measured.get("stddev") if measured else None
    low = ok is False or (contrast is not None and contrast < 4.5)
    busy = stddev is not None and stddev > 0.32
    if not low and not busy:
        return None
    if low and contrast is not None:
        message = (
            f"White captions would reach only {contrast:.2f}:1 contrast "
            "in the lower safe zone (minimum 4.5:1)."
        )
    elif ok is False:
        message = "The lower safe zone was marked unsafe for white captions."
    else:
        message = (
            f"The lower safe zone is visually busy (variation {stddev:.2f}); "
            "captions may be hard to read."
        )
    return {
        "message": message,
        "details": measured or {"source": "metadata"},
    }


def measure_loudness(path: Path | str, timeout: float = 120.0) -> float | None:
    """Return integrated LUFS from ffmpeg ebur128, or None when unavailable."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not Path(path).is_file():
        return None
    try:
        result = subprocess.run(
            [
                ffmpeg, "-hide_banner", "-nostats", "-i", str(path),
                "-map", "0:a:0", "-af", "ebur128=peak=true",
                "-f", "null", "-",
            ],
            capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    matches = re.findall(
        r"\bI:\s*(-?\d+(?:\.\d+)?)\s*LUFS", result.stderr or "", re.IGNORECASE,
    )
    if not matches:
        return None
    try:
        value = float(matches[-1])
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def check_loudness(context: dict) -> dict | None:
    value = _loudness_from_context(context)
    source = "metadata"
    if value is None and context.get("media_path") is not None:
        value = measure_loudness(context["media_path"])
        source = "ffmpeg"
    if value is None:
        return {"unavailable": True, "reason": "Loudness could not be measured."}
    if LOW_LUFS <= value <= HIGH_LUFS:
        return None
    if value < LOW_LUFS:
        direction = "below"
    else:
        direction = "above"
    return {
        "message": (
            f"Integrated loudness is {value:.1f} LUFS, {direction} the "
            f"{LOW_LUFS:.0f} to {HIGH_LUFS:.0f} LUFS window (target {TARGET_LUFS:.0f})."
        ),
        "details": {
            "integrated_lufs": round(value, 2),
            "target_lufs": TARGET_LUFS,
            "low_lufs": LOW_LUFS,
            "high_lufs": HIGH_LUFS,
            "source": source,
        },
    }


CHECK_FUNCS: dict[str, Callable[[dict], dict | None]] = {
    "dangling_claims": check_dangling_claims,
    "truncated_payoff": check_truncated_payoff,
    "caption_density": check_caption_density,
    "safe_zone_contrast": check_safe_zone_contrast,
    "loudness": check_loudness,
}


def run_preflight(
    job: dict,
    story_id: str | None = None,
    job_dir: Path | str | None = None,
    settings: dict | None = None,
) -> dict:
    """Run enabled checks. Findings never block unless severity is ``block``."""
    context = _context(job, story_id, Path(job_dir) if job_dir is not None else None)
    config = resolve_config(settings, job)
    findings: list[dict] = []
    checks: dict[str, dict] = {}
    for spec in CHECK_SPECS:
        check_id = spec["id"]
        enabled = config["toggles"][check_id]
        severity = config["severities"][check_id]
        style = config["styles"][check_id]
        meta = {
            "label": spec["label"],
            "toggle": check_id,
            "enabled": enabled,
            "style": style,
            "severity": severity,
            "status": "disabled" if not enabled else "pass",
        }
        if enabled:
            try:
                result = CHECK_FUNCS[check_id](context)
            except Exception as exc:  # noqa: BLE001 - one bad check must not fail all
                meta["status"] = "error"
                meta["error"] = str(exc)[:240]
                result = None
            if result and result.get("unavailable"):
                meta["status"] = "unavailable"
                meta["reason"] = result.get("reason")
            elif result:
                meta["status"] = "finding"
                if result.get("details"):
                    meta["details"] = result["details"]
                findings.append({
                    "id": check_id,
                    "severity": severity,
                    "toggle": check_id,
                    "message": result["message"],
                    "suggestion": result.get("suggestion") or spec["suggestion"],
                })
        checks[check_id] = meta
    return {
        "job_id": str(job.get("id") or ""),
        "story_id": context["id"],
        "render_key": context.get("render_key"),
        "blocked": any(item["severity"] == "block" for item in findings),
        "findings": findings,
        "checks": checks,
        "toggles": config["toggles"],
        "severities": config["severities"],
        "styles": config["styles"],
    }
