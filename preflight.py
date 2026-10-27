"""Muted-first preflight checks for a story or ready render.

Each check can be toggled independently from ``settings.preflight`` or
``job.preflight``. Findings are advisory unless a check's severity is set to
``block``. Every finding carries the toggle that produced it, and the response
also exposes check-level style, toggle, and severity metadata for the UI.
"""

from __future__ import annotations

import logging
import math
import re
import shutil
import subprocess
import tempfile
from itertools import combinations
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException

import captions as caption_engine
import cleanup
import compose_render
import detect
import edits
import overlays
import routes_cleanup

LOGGER = logging.getLogger("vibecut.preflight")

import exports
import history_store
import packet

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


def validate_settings(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("preflight must be an object.")
    for key in ("toggles", "checks", "severity", "severities", "styles", "style"):
        if key in value and value[key] is not None and not isinstance(value[key], dict):
            raise ValueError(f"preflight.{key} must be an object.")
    return value


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
    if path.is_absolute() or ".." in path.parts:
        return None
    root = Path(job_dir).resolve()
    candidates = [root / path]
    if len(path.parts) == 1:
        candidates.extend(root / name / path for name in subdirs)
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved != root and root not in resolved.parents:
            continue
        if resolved.is_file():
            return resolved
    return None


def _source_media_path(job: dict) -> Path | None:
    """Job-owned source path. Never accept a story/artifact absolute import."""
    source_path = str((job.get("source") or {}).get("path") or "").strip()
    if not source_path:
        return None
    path = Path(source_path)
    return path if path.is_absolute() and path.is_file() else None


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
        end = _parse_time(right.strip().split()[0] if right.strip() else "")
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
    scenes.sort(key=lambda scene: (
        _number(scene.get("start")) or 0.0, scene.get("id") or 0,
    ))
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


def _relative_artifact_path(job_dir: Path | None, value: object) -> str | None:
    if job_dir is None or not value:
        return None
    path = Path(str(value))
    if path.is_absolute():
        try:
            relative = path.resolve().relative_to(Path(job_dir).resolve())
        except (OSError, ValueError):
            return None
        return relative.as_posix()
    if ".." in path.parts:
        return None
    return path.as_posix()


def _artifact_entry(
    job: dict,
    job_dir: Path | None,
    artifact_id: str,
    summary: dict | None = None,
) -> dict:
    entry = dict(summary or {})
    if job_dir is not None:
        try:
            resolved = packet.resolve_trust_artifact(job, job_dir, artifact_id)
        except Exception:  # noqa: BLE001 - preflight stays advisory
            resolved = None
        if isinstance(resolved, dict):
            entry.update({
                key: value for key, value in resolved.items()
                if value is not None
            })
    for key in ("path", "poster", "captions_path"):
        if key in entry:
            entry[key] = _relative_artifact_path(job_dir, entry.get(key))
    entry.setdefault("id", artifact_id)
    entry.setdefault("artifact_id", artifact_id)
    return entry


def _select_story(
    job: dict,
    story_id: str | None,
    job_dir: Path | None = None,
) -> dict:
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
        for key, record in records.items():
            if str(record.get("artifact_id") or "") == sid:
                return {
                    "id": sid,
                    "render_key": key,
                    "record": record,
                    "artifact": _artifact_entry(
                        job, job_dir, sid, artifacts.get(sid),
                    ),
                    "artifact_id": sid,
                }
        if sid in artifacts:
            return {
                "id": sid,
                "artifact": _artifact_entry(job, job_dir, sid, artifacts[sid]),
                "artifact_id": sid,
            }
        if sid.startswith("art_") and job_dir is not None:
            resolved = _artifact_entry(job, job_dir, sid, None)
            if resolved and (resolved.get("path") or resolved.get("plan")):
                return {
                    "id": sid,
                    "artifact": resolved,
                    "artifact_id": sid,
                }
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
    entry = _select_story(job, story_id, job_dir)
    records = _records(job)
    render_key = str(entry.get("render_key") or entry.get("record_key") or "")
    record = entry.get("record")
    if not isinstance(record, dict) and render_key in records:
        record = records[render_key]
    record = record if isinstance(record, dict) else {}
    artifact = entry.get("artifact") if isinstance(entry.get("artifact"), dict) else {}
    artifact_id = str(
        entry.get("artifact_id")
        or artifact.get("artifact_id")
        or record.get("artifact_id")
        or ""
    )
    if artifact_id and not artifact and job_dir is not None:
        artifact = _artifact_entry(
            job, job_dir, artifact_id, _artifact_rows(job).get(artifact_id),
        )
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
    render_story = bool(record or render_key or artifact or path_value)
    media_path = _job_path(job_dir, path_value, ("renders", "artifacts", "media"))
    if media_path is not None:
        media_source = "artifact" if artifact else "render"
    elif render_story:
        media_source = "missing_render"
    else:
        media_path = _source_media_path(job)
        media_source = "source_fallback" if media_path is not None else None

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
        "media_source": media_source,
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
    if (
        measured is None
        and context.get("media_path") is not None
        and context.get("media_source") in {"render", "artifact"}
    ):
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
    media_source = context.get("media_source")
    source = "metadata"
    if value is None and media_source == "missing_render":
        return {
            "unavailable": True,
            "reason": "Render media is missing; source fallback was not used.",
            "media_source": media_source,
        }
    if value is None and context.get("media_path") is not None:
        value = measure_loudness(context["media_path"])
        source = (
            "ffmpeg_source_fallback"
            if media_source == "source_fallback"
            else "ffmpeg_render"
        )
    if value is None:
        return {
            "unavailable": True,
            "reason": "Loudness could not be measured.",
            "media_source": media_source,
        }
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
            "media_source": media_source,
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
    narrative_only = context.get("media_source") in {None, "source_fallback"}
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
        if enabled and narrative_only and check_id in {
            "safe_zone_contrast", "loudness",
        }:
            meta["status"] = "unavailable"
            meta["reason"] = (
                "No render is available; source fallback is not used for "
                "audio or frame checks."
            )
        elif enabled:
            try:
                result = CHECK_FUNCS[check_id](context)
            except Exception as exc:  # noqa: BLE001 - one bad check must not fail all
                meta["status"] = "error"
                meta["error"] = str(exc)[:240]
                result = None
            if result and result.get("media_source"):
                meta["media_source"] = result["media_source"]
            elif check_id == "loudness":
                meta["media_source"] = context.get("media_source")
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
        "media_source": context.get("media_source"),
        "narrative_only": narrative_only,
        "blocked": any(item["severity"] == "block" for item in findings),
        "findings": findings,
        "checks": checks,
        "toggles": config["toggles"],
        "severities": config["severities"],
        "styles": config["styles"],
    }


# ------------------------------------------------------------ edit markers API

#: Timeline marker kinds consumed by Studio. ``aspect_4_5`` is a 4:5-only
#: platform-chrome result; the other kinds are shared by both aspects.
MARKER_KINDS = (
    "collision",
    "face_overlap",
    "safe_zone",
    "residual_text",
    "caption_density",
    "loudness",
    "voice_fit",
    "missing_music_license",
    "aspect_4_5",
)
PREFLIGHT_RESIDUAL_FPS = 0.5
PREFLIGHT_RESIDUAL_FRAMES = 24
PREFLIGHT_RESIDUAL_TIMEOUT = 90.0
MARKER_LIMIT = 200
VOICE_FIT_MIN = 0.90
VOICE_FIT_MAX = 1.15
_LOUDNESS_KEYS = ("integrated_lufs", "measured_lufs", "loudness_lufs")

router = APIRouter()


def _marker(
    t: object,
    end: object,
    kind: str,
    message: str,
    *,
    severity: str = "warn",
    layer_id: str | None = None,
) -> dict:
    start = _number(t)
    finish = _number(end)
    if start is None:
        start = 0.0
    if finish is None or finish <= start:
        finish = start + 0.001
    item = {
        "t": round(max(0.0, start), 3),
        "end": round(max(0.0, finish), 3),
        "kind": str(kind),
        "severity": severity if severity in SEVERITIES else "warn",
        "message": " ".join(str(message).split())[:400],
    }
    if layer_id:
        item["layer_id"] = str(layer_id)
    return item


def _rect(layer: dict) -> dict | None:
    rect = layer.get("rect")
    if isinstance(rect, dict):
        try:
            return {
                "x": float(rect["x"]),
                "y": float(rect["y"]),
                "w": float(rect["w"]),
                "h": float(rect["h"]),
            }
        except (KeyError, TypeError, ValueError):
            pass
    anchor = str(layer.get("anchor") or "center")
    box = layer.get("box")
    if isinstance(box, dict):
        try:
            return overlays.normalize_rect(anchor, box)
        except (KeyError, TypeError, ValueError):
            return None
    return None


def _intersection(first: dict, second: dict) -> float:
    left = max(float(first["x"]), float(second["x"]))
    top = max(float(first["y"]), float(second["y"]))
    right = min(
        float(first["x"]) + float(first["w"]),
        float(second["x"]) + float(second["w"]),
    )
    bottom = min(
        float(first["y"]) + float(first["h"]),
        float(second["y"]) + float(second["h"]),
    )
    return max(0.0, right - left) * max(0.0, bottom - top)


def _area(box: dict) -> float:
    return max(1e-9, float(box.get("w") or 0.0) * float(box.get("h") or 0.0))


def _inside(box: dict, region: dict) -> bool:
    cx = float(box["x"]) + float(box["w"]) / 2.0
    cy = float(box["y"]) + float(box["h"]) / 2.0
    return (
        float(region["x"]) <= cx <= float(region["x"]) + float(region["w"])
        and float(region["y"]) <= cy <= float(region["y"]) + float(region["h"])
    )


def _outside_area(box: dict, area: dict) -> float:
    return max(0.0, _area(box) - _intersection(box, area))


def _clamp_window(start: object, end: object, duration: float) -> tuple[float, float] | None:
    low = _number(start)
    high = _number(end)
    if low is None or high is None:
        return None
    low = max(0.0, min(duration, low))
    high = max(0.0, min(duration, high))
    if high - low <= 0.001:
        return None
    return low, high


def _duration(compiled: dict) -> float:
    segments = [
        item for item in compiled.get("segments") or [] if isinstance(item, dict)
    ]
    return max(0.0, float(segments[-1].get("out_end") or 0.0)) if segments else 0.0


def _output_window(compiled: dict, source_start: float, source_end: float) -> tuple[float, float] | None:
    segments = [
        item for item in compiled.get("segments") or [] if isinstance(item, dict)
    ]
    starts: list[float] = []
    ends: list[float] = []
    for segment in segments:
        low = max(float(segment.get("start") or 0.0), float(source_start))
        high = min(float(segment.get("end") or 0.0), float(source_end))
        if high - low <= 0.001:
            continue
        starts.append(
            float(segment.get("out_start") or 0.0)
            + (low - float(segment.get("start") or 0.0))
        )
        ends.append(
            float(segment.get("out_start") or 0.0)
            + (high - float(segment.get("start") or 0.0))
        )
    if not starts:
        return None
    return min(starts), max(ends)


def _map_face(box: dict, segment: dict, source: dict) -> dict | None:
    crop = segment.get("crop") or {}
    try:
        crop_x = float(crop["x"])
        crop_y = float(crop["y"])
        crop_w = float(crop["w"])
        crop_h = float(crop["h"])
        width = float(source["width"])
        height = float(source["height"])
    except (KeyError, TypeError, ValueError):
        return None
    if crop_w <= 0 or crop_h <= 0 or width <= 0 or height <= 0:
        return None
    try:
        left = (float(box["x"]) * width - crop_x) / crop_w
        top = (float(box["y"]) * height - crop_y) / crop_h
        right = ((float(box["x"]) + float(box["w"])) * width - crop_x) / crop_w
        bottom = ((float(box["y"]) + float(box["h"])) * height - crop_y) / crop_h
    except (KeyError, TypeError, ValueError):
        return None
    left = max(0.0, min(1.0, left))
    top = max(0.0, min(1.0, top))
    right = max(0.0, min(1.0, right))
    bottom = max(0.0, min(1.0, bottom))
    if right - left <= 1e-4 or bottom - top <= 1e-4:
        return None
    return {
        "x": left,
        "y": top,
        "w": right - left,
        "h": bottom - top,
    }


def _scene_faces(scene: dict) -> list[dict]:
    faces = [item for item in scene.get("faces") or [] if isinstance(item, dict)]
    if not faces:
        attention = scene.get("attention") or {}
        face = attention.get("face") if isinstance(attention, dict) else None
        if isinstance(face, dict):
            faces = [face]
    return faces


def collision_markers(compiled: dict, duration: float) -> list[dict]:
    """Text and graphic layers that occupy the same pixels at the same time."""
    layers = [item for item in compiled.get("overlays") or [] if isinstance(item, dict)]
    markers: list[dict] = []
    for first, second in combinations(layers, 2):
        if str(first.get("id")) == str(second.get("id")):
            continue
        try:
            start = max(float(first.get("start") or 0.0), float(second.get("start") or 0.0))
            end = min(float(first.get("end") or 0.0), float(second.get("end") or 0.0))
        except (TypeError, ValueError):
            continue
        window = _clamp_window(start, end, duration)
        if window is None:
            continue
        first_rect = _rect(first)
        second_rect = _rect(second)
        if first_rect is None or second_rect is None:
            continue
        ratio = _intersection(first_rect, second_rect) / min(
            _area(first_rect), _area(second_rect),
        )
        if ratio < 0.12:
            continue
        markers.append(_marker(
            window[0], window[1], "collision",
            (
                f"{str(first.get('kind') or 'layer').replace('_', ' ').title()} "
                f"{first.get('id')} overlaps "
                f"{str(second.get('kind') or 'layer').replace('_', ' ')} "
                f"{second.get('id')} ({ratio * 100:.0f}% of the smaller layer)."
            ),
            layer_id=str(first.get("id") or "") or None,
        ))
    return markers


def face_overlap_markers(
    compiled: dict,
    scenes: list[dict],
    clean: list[dict],
    duration: float,
) -> list[dict]:
    """Graphics, captions and Clean covers that sit on a detected face."""
    source = compiled.get("source") or {}
    markers: list[dict] = []
    scene_map = {
        str(scene.get("id")): scene
        for scene in scenes
        if isinstance(scene, dict) and scene.get("id") is not None
    }
    overlays_list = [
        item for item in compiled.get("overlays") or [] if isinstance(item, dict)
    ]
    seen: set[tuple] = set()
    for segment in compiled.get("segments") or []:
        if not isinstance(segment, dict):
            continue
        scene = scene_map.get(str(segment.get("scene")))
        if scene is None:
            continue
        faces = _scene_faces(scene)
        if not faces:
            continue
        out_start = float(segment.get("out_start") or 0.0)
        out_end = float(segment.get("out_end") or out_start)
        for face in faces:
            mapped = _map_face(face, segment, source)
            if mapped is None:
                continue
            for layer in overlays_list:
                try:
                    start = max(out_start, float(layer.get("start") or 0.0))
                    end = min(out_end, float(layer.get("end") or 0.0))
                except (TypeError, ValueError):
                    continue
                window = _clamp_window(start, end, duration)
                if window is None:
                    continue
                rect = _rect(layer)
                if rect is None:
                    continue
                if (
                    _intersection(rect, mapped) / _area(mapped) < 0.10
                    and not _inside(mapped, rect)
                ):
                    continue
                key = ("overlay", layer.get("id"), scene.get("id"))
                if key in seen:
                    continue
                seen.add(key)
                markers.append(_marker(
                    window[0], window[1], "face_overlap",
                    (
                        f"{str(layer.get('kind') or 'Overlay').replace('_', ' ').title()} "
                        f"{layer.get('id')} covers a face in scene {scene.get('id')}."
                    ),
                    layer_id=str(layer.get("id") or "") or None,
                ))
    for layer in clean or []:
        if not isinstance(layer, dict):
            continue
        if str(layer.get("kind") or "") not in {"blur", "plate", "mask"}:
            continue
        box = layer.get("box")
        if not isinstance(box, dict):
            continue
        ranges = [
            item for item in layer.get("ranges") or [] if isinstance(item, dict)
        ] or [{"start": 0.0, "end": duration}]
        for scene in scene_map.values():
            scene_start = _number(scene.get("start"))
            scene_end = _number(scene.get("end"))
            if scene_start is None or scene_end is None:
                continue
            for face in _scene_faces(scene):
                if (
                    _intersection(box, face) / _area(face) < 0.10
                    and not _inside(face, box)
                ):
                    continue
                key = ("clean", layer.get("id"), scene.get("id"))
                if key in seen:
                    continue
                window = None
                for item in ranges:
                    low = max(scene_start, float(item.get("start") or 0.0))
                    high = min(scene_end, float(item.get("end") or scene_end))
                    if high - low <= 0.001:
                        continue
                    window = _output_window(compiled, low, high)
                    if window is not None:
                        break
                if window is None:
                    continue
                seen.add(key)
                markers.append(_marker(
                    window[0], window[1], "face_overlap",
                    (
                        f"Clean layer {layer.get('id')} covers a detected face "
                        f"in scene {scene.get('id')}."
                    ),
                    layer_id=str(layer.get("id") or "") or None,
                ))
    return markers


def safe_zone_markers(compiled: dict, duration: float) -> list[dict]:
    """Overlays outside the safe area or inside platform chrome.

    For 4:5 the platform-chrome hits use the dedicated ``aspect_4_5`` kind so
    Studio can tell a 4:5-only problem from a shared safe-zone warning.
    """
    aspect = str(compiled.get("aspect") or "9:16")
    area = overlays.SAFE_AREAS.get(aspect, overlays.SAFE_AREAS["9:16"])
    zones = overlays.RESERVED_ZONES.get(aspect, overlays.RESERVED_ZONES["9:16"])
    markers: list[dict] = []
    for layer in compiled.get("overlays") or []:
        if not isinstance(layer, dict) or layer.get("safe_zone") is False:
            continue
        rect = _rect(layer)
        if rect is None or _area(rect) <= 0:
            continue
        hits = [
            zone["name"] for zone in zones
            if _intersection(rect, zone) / _area(rect) > 0.005
        ]
        outside = _outside_area(rect, area) / _area(rect) > 0.005
        if not hits and not outside:
            continue
        try:
            start = float(layer.get("start") or 0.0)
            end = float(layer.get("end") or duration)
        except (TypeError, ValueError):
            start, end = 0.0, duration
        window = _clamp_window(start, end, duration) or (0.0, max(0.001, duration))
        kind = "aspect_4_5" if aspect == "4:5" and hits else "safe_zone"
        if hits:
            where = ", ".join(hits)
            message = (
                f"{str(layer.get('kind') or 'Overlay').replace('_', ' ').title()} "
                f"{layer.get('id')} intersects the {aspect} {where} zone."
            )
        else:
            message = (
                f"{str(layer.get('kind') or 'Overlay').replace('_', ' ').title()} "
                f"{layer.get('id')} sits outside the {aspect} safe area."
            )
        markers.append(_marker(
            window[0], window[1], kind, message,
            layer_id=str(layer.get("id") or "") or None,
        ))
    return markers


def caption_density_markers(
    caption_track: dict | None,
    duration: float,
) -> list[dict]:
    cues = [
        item for item in (caption_track or {}).get("cues") or []
        if isinstance(item, dict)
    ]
    markers: list[dict] = []
    for index, cue in enumerate(cues, 1):
        try:
            start = float(cue.get("start"))
            end = float(cue.get("end"))
        except (TypeError, ValueError):
            continue
        if end - start <= 0.05:
            continue
        chars = len(" ".join(str(cue.get("text") or "").split()))
        cps = chars / (end - start)
        if cps <= MAX_CAPTION_CPS:
            continue
        window = _clamp_window(start, end, duration)
        if window is None:
            continue
        markers.append(_marker(
            window[0], window[1], "caption_density",
            (
                f"Caption {index} runs at {cps:.1f} characters per second; "
                f"limit is {MAX_CAPTION_CPS:.0f}."
            ),
            layer_id=f"cap{index:02d}",
        ))
    return markers


def _find_loudness(value: object, depth: int = 0) -> float | None:
    if depth > 5:
        return None
    if isinstance(value, dict):
        for key in _LOUDNESS_KEYS:
            number = _number(value.get(key))
            if number is not None:
                return number
        for item in value.values():
            found = _find_loudness(item, depth + 1)
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for item in value[:200]:
            found = _find_loudness(item, depth + 1)
            if found is not None:
                return found
    return None


def _render_media(job: dict, job_dir: Path | None, edit: dict) -> Path | None:
    if job_dir is None:
        return None
    records = job.get("renders") or {}
    if isinstance(records, dict):
        for record in records.values():
            if not isinstance(record, dict):
                continue
            if (
                str(record.get("edit_hash") or "") != str(edit.get("hash") or "")
                and str(record.get("edit_id") or "") != str(edit.get("id") or "")
            ):
                continue
            path = _job_path(
                job_dir,
                record.get("path") or record.get("media_path"),
                ("renders", "artifacts", "media"),
            )
            if path is not None:
                return path
    artifacts_value = job.get("artifacts") or {}
    if isinstance(artifacts_value, dict):
        for record in artifacts_value.values():
            if not isinstance(record, dict):
                continue
            if str(record.get("edit_hash") or "") != str(edit.get("hash") or ""):
                continue
            path = _job_path(
                job_dir,
                record.get("path") or record.get("artifact_path"),
                ("renders", "artifacts", "media"),
            )
            if path is not None:
                return path
    return None


def loudness_markers(
    edit: dict,
    job: dict,
    job_dir: Path | None,
    duration: float,
    *,
    measure_media: bool = True,
) -> list[dict]:
    audio = edit.get("audio") if isinstance(edit.get("audio"), dict) else {}
    measured = _find_loudness(audio.get("measured"))
    if measured is None:
        measured = _find_loudness(job.get("audio") or {})
    if measured is None:
        measured = _find_loudness(job.get("renders") or {})
    if measured is None and measure_media:
        media = _render_media(job, job_dir, edit)
        if media is not None:
            try:
                measured = measure_loudness(media)
            except Exception:  # noqa: BLE001 - advisory only
                measured = None
    if measured is not None:
        if LOW_LUFS <= measured <= HIGH_LUFS:
            return []
        direction = "below" if measured < LOW_LUFS else "above"
        return [_marker(
            0.0, duration, "loudness",
            (
                f"Integrated loudness is {measured:.1f} LUFS, {direction} the "
                f"{LOW_LUFS:.0f} to {HIGH_LUFS:.0f} LUFS window "
                f"(target {TARGET_LUFS:.0f})."
            ),
        )]
    target = _number((audio.get("loudness") or {}).get("lufs"))
    if target is not None and not (LOW_LUFS <= target <= HIGH_LUFS):
        return [_marker(
            0.0, duration, "loudness",
            (
                f"Target loudness is {target:.1f} LUFS, outside the "
                f"{LOW_LUFS:.0f} to {HIGH_LUFS:.0f} LUFS window "
                f"(target {TARGET_LUFS:.0f})."
            ),
        )]
    return []


def _voice_lines(value: object, depth: int = 0, out: list[dict] | None = None) -> list[dict]:
    if out is None:
        out = []
    if depth > 6:
        return out
    if isinstance(value, dict):
        fit = value.get("fit")
        action = str(
            (fit.get("action") if isinstance(fit, dict) else "")
            or value.get("action")
            or ""
        ).lower()
        if (
            isinstance(fit, dict)
            or action in {"shorten", "pad"}
            or (
                ("native" in value or "slot" in value)
                and ("overflow" in value or "slot_fit" in value)
            )
        ):
            out.append(value)
        for key in (
            "voice", "lines", "line_fits", "_slot_lines", "dub", "segments",
            "sentences", "voice_fit", "fit_summary",
        ):
            if key in value:
                _voice_lines(value[key], depth + 1, out)
    elif isinstance(value, (list, tuple)):
        for item in value[:200]:
            _voice_lines(item, depth + 1, out)
    return out


def voice_fit_markers(edit: dict, duration: float) -> list[dict]:
    audio = edit.get("audio") if isinstance(edit.get("audio"), dict) else {}
    voice = audio.get("voice") if isinstance(audio.get("voice"), dict) else {}
    markers: list[dict] = []
    seen: set[tuple] = set()
    for line in _voice_lines(audio):
        fit = line.get("fit") if isinstance(line.get("fit"), dict) else {}
        action = str(fit.get("action") or line.get("action") or "").lower()
        native = _number(fit.get("native") if fit else line.get("native"))
        slot = _number(line.get("slot"))
        if action not in {"shorten", "pad"} and native and slot and slot > 0.05:
            ratio = native / slot
            if ratio > VOICE_FIT_MAX:
                action = "shorten"
            elif ratio < VOICE_FIT_MIN:
                action = "pad"
        if action not in {"shorten", "pad"}:
            continue
        start = _number(line.get("start"))
        if start is None:
            start = _number(line.get("offset"))
        if start is None:
            start = 0.0
        length = _number(line.get("slot")) or _number(line.get("native")) or 0.5
        end = start + max(0.2, length)
        overflow = _number(fit.get("overflow") if fit else line.get("overflow")) or 0.0
        text = " ".join(str(line.get("text") or "").split())[:80]
        if action == "shorten":
            message = (
                f"Voice line {text!r} is too long by {overflow:.1f} s for its "
                f"{length:.1f} s slot. Shorten it or allow overlap."
            )
        else:
            message = (
                f"Voice line {text!r} is short for its {length:.1f} s slot. "
                "The mix pads it; check the pause."
            )
        key = (round(start, 3), action, text)
        if key in seen:
            continue
        seen.add(key)
        markers.append(_marker(
            start, end, "voice_fit", message,
        ))
    rate = _number(voice.get("rate"))
    if rate is not None and not (VOICE_FIT_MIN <= rate <= VOICE_FIT_MAX):
        markers.append(_marker(
            0.0, duration, "voice_fit",
            (
                f"Voice rate is {rate:.2f}×, outside the "
                f"{VOICE_FIT_MIN:.2f}–{VOICE_FIT_MAX:.2f}× slot-fit band."
            ),
        ))
    if not markers:
        summary = voice.get("slot_fit") or voice.get("fit_summary")
        if isinstance(summary, dict):
            flagged = _number(summary.get("flagged"))
            if flagged is not None and flagged > 0:
                total = _number(summary.get("total")) or flagged
                markers.append(_marker(
                    0.0, duration, "voice_fit",
                    (
                        f"{int(flagged)} of {int(total)} voice lines sit outside "
                        f"the {VOICE_FIT_MIN:.2f}–{VOICE_FIT_MAX:.2f}× fit band."
                    ),
                ))
    return markers


def _licence_type(value: object) -> tuple[str, str, str]:
    if isinstance(value, dict):
        kind = str(
            value.get("type") or value.get("license") or value.get("licence")
            or value.get("kind") or ""
        ).strip().lower()
        attestation = str(value.get("attestation") or value.get("attested") or "").strip()
        attribution = str(value.get("attribution") or "").strip()
        if not kind and attestation:
            kind = "licensed"
        return kind, attestation, attribution
    text = str(value or "").strip().lower()
    return text, "", ""


def music_licence_markers(edit: dict, duration: float) -> list[dict]:
    audio = edit.get("audio") if isinstance(edit.get("audio"), dict) else {}
    music = audio.get("music")
    if not isinstance(music, dict) or not music:
        return []
    present = any(
        music.get(key) not in (None, "", [], {})
        for key in ("track", "path", "file", "file_hash", "name")
    )
    if not present and str(music.get("source") or "").strip().lower() in {"", "none"}:
        return []
    raw = music.get("licence", music.get("license"))
    kind, attestation, attribution = _licence_type(raw)
    if kind in {"", "unknown", "none", "null"} and not attestation:
        reason = "has no licence note"
    elif kind == "cc" and not attribution:
        reason = "is CC but has no attribution text"
    else:
        return []
    name = " ".join(str(music.get("name") or music.get("track") or "Music bed").split())[:80]
    return [_marker(
        0.0, duration, "missing_music_license",
        f"Music bed {name!r} {reason}. Add own, licensed or CC details.",
    )]


def uncovered_text_markers(
    job_dir: Path | str | None,
    edit: dict,
    compiled: dict,
    duration: float,
) -> list[dict]:
    """Baked Check text that no active Clean layer covers.

    This is the plan-level half of residual text. The rendered residual pass
    catches glyphs that survive a layer; this catches an old caption block
    that has no layer at all (for example after a layer is deleted). Screen
    text and watermarks are excluded because the policy never cleans them.
    """
    if job_dir is None:
        return []
    try:
        report = detect.load_report(Path(job_dir))
    except Exception:  # noqa: BLE001 - a missing report is not a marker
        return []
    if not isinstance(report, dict):
        return []
    clean = [item for item in edit.get("clean") or [] if isinstance(item, dict)]
    markers: list[dict] = []
    for tracklet in report.get("tracklets") or []:
        if not isinstance(tracklet, dict):
            continue
        kind = str(tracklet.get("kind") or "")
        if kind not in {"subtitle", "title", "lower_third", "credit"}:
            continue
        box = tracklet.get("box")
        if not isinstance(box, dict):
            continue
        ranges = [
            item for item in tracklet.get("ranges") or [] if isinstance(item, dict)
        ] or [{"start": 0.0, "end": duration}]
        uncovered = None
        for item in ranges:
            low = float(item.get("start") or 0.0)
            high = float(item.get("end") or duration)
            if high - low <= 0.001:
                continue
            covered = False
            for layer in clean:
                layer_box = layer.get("box")
                if not isinstance(layer_box, dict):
                    continue
                if _intersection(layer_box, box) / _area(box) < 0.5:
                    continue
                layer_ranges = [
                    value for value in layer.get("ranges") or []
                    if isinstance(value, dict)
                ]
                if not layer_ranges:
                    covered = True
                    break
                if any(
                    min(high, float(value.get("end") or high))
                    - max(low, float(value.get("start") or low)) > 0.001
                    for value in layer_ranges
                ):
                    covered = True
                    break
            if not covered:
                uncovered = (low, high)
                break
        if uncovered is None:
            continue
        window = _output_window(compiled, uncovered[0], uncovered[1]) or (
            0.0, duration,
        )
        sample = " ".join(str(tracklet.get("text_sample") or "").split())[:80]
        markers.append(_marker(
            window[0], window[1], "residual_text",
            (
                f"Check found baked {kind.replace('_', ' ')} text with no "
                f"active Clean layer: {sample!r}."
            ),
        ))
    return markers


def residual_markers(
    edit: dict,
    compiled: dict,
    report: dict | None,
    duration: float,
    *,
    issue: str = "",
) -> list[dict]:
    if not edit.get("clean"):
        return []
    if issue:
        return [_marker(
            0.0, duration, "residual_text",
            f"Residual text could not be checked: {issue}",
            severity="info",
        )]
    if not isinstance(report, dict):
        return []
    if report.get("pass") is None:
        return [_marker(
            0.0, duration, "residual_text",
            "Residual text is unknown because Vision OCR was unavailable.",
            severity="info",
        )]
    if report.get("pass"):
        return []
    markers: list[dict] = []
    layers = {
        str(item.get("id")): item
        for item in edit.get("clean") or []
        if isinstance(item, dict)
    }
    for stats in report.get("layers") or []:
        if not isinstance(stats, dict):
            continue
        frames = int(stats.get("residual_frames") or 0)
        if frames <= 0:
            continue
        layer_id = str(stats.get("layer_id") or "")
        layer = layers.get(layer_id) or {}
        ranges = layer.get("ranges") or [{"start": 0.0, "end": duration}]
        window = None
        for item in ranges:
            if not isinstance(item, dict):
                continue
            window = _output_window(
                compiled,
                float(item.get("start") or 0.0),
                float(item.get("end") or duration),
            )
            if window is not None:
                break
        window = window or (0.0, duration)
        pct = _number(stats.get("residual_pct")) or 0.0
        markers.append(_marker(
            window[0], window[1], "residual_text",
            (
                f"Residual old text was detected inside Clean layer {layer_id} "
                f"({frames} frame{'s' if frames != 1 else ''}, {pct:.1f}%)."
            ),
            layer_id=layer_id or None,
        ))
    if not markers:
        for sample in report.get("samples") or []:
            if not isinstance(sample, dict) or not sample.get("residual"):
                continue
            start = _number(sample.get("t")) or 0.0
            text = ", ".join(str(item) for item in sample.get("text") or [])[:120]
            markers.append(_marker(
                start, start + 0.5, "residual_text",
                f"Residual old text was detected at {start:.1f} s: {text or 'OCR text'}.",
            ))
    if not markers:
        markers.append(_marker(
            0.0, duration, "residual_text",
            (
                f"Residual OCR is {float(report.get('residual_pct') or 0.0):.1f}%, "
                f"above the {float(report.get('target_pct') or cleanup.RESIDUAL_TARGET_PCT):.1f}% target."
            ),
        ))
    return markers


def _story_for_edit(job: dict, edit: dict) -> dict:
    set_id = edit["story_ref"]["set_id"]
    story_id = edit["story_ref"]["story_id"]
    sets = job.get("clip_sets") or []
    rows = list(sets.values()) if isinstance(sets, dict) else list(sets)
    record = next(
        (item for item in rows if isinstance(item, dict) and str(item.get("id") or "") == set_id),
        None,
    )
    if record is None:
        raise PreflightError(
            "story_not_found", "The Edit's clip set is missing from this job.",
            suggestion="Reopen the story from Stories and save the Edit again.",
            status=409,
        )
    story = next(
        (
            item for item in record.get("stories") or []
            if isinstance(item, dict) and str(item.get("id") or "") == story_id
        ),
        None,
    )
    if story is None:
        raise PreflightError(
            "story_not_found", "The Edit's story is missing from its clip set.",
            suggestion="Reopen the story from Stories and save the Edit again.",
            status=409,
        )
    return story


def _caption_track(job_dir: Path | None, edit: dict) -> dict | None:
    if job_dir is None:
        return None
    captions_value = edit.get("captions") or {}
    track_id = str(captions_value.get("track_id") or "")
    if not track_id:
        return None
    try:
        track = caption_engine.load_track(job_dir, track_id)
    except Exception:  # noqa: BLE001 - missing track stays advisory
        return None
    return track.to_dict() if track is not None else None


def _dedupe(markers: list[dict], duration: float) -> list[dict]:
    output: list[dict] = []
    seen: set[tuple] = set()
    ceiling = max(0.001, float(duration))
    for marker in markers:
        start = max(0.0, min(ceiling - 0.001, float(marker.get("t") or 0.0)))
        end = max(start + 0.001, min(ceiling, float(marker.get("end") or 0.0)))
        item = {**marker, "t": round(start, 3), "end": round(end, 3)}
        key = (
            item["t"],
            item["end"],
            item.get("kind"),
            item.get("severity"),
            item.get("message"),
            item.get("layer_id"),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    output.sort(key=lambda item: (
        float(item.get("t") or 0.0),
        float(item.get("end") or 0.0),
        str(item.get("kind") or ""),
        str(item.get("layer_id") or ""),
        str(item.get("message") or ""),
    ))
    return output[:MARKER_LIMIT]


def run_edit_preflight(
    job: dict,
    edit: dict,
    job_dir: Path | str | None = None,
    *,
    measure_media: bool = True,
    check_residual: bool = True,
    residual_report: dict | None = None,
    residual_error: str = "",
) -> dict:
    """Return timeline markers for one Edit.

    The response contract is ``{"markers": [...], "pass": bool}``. Markers
    carry ``t``, ``end``, ``kind``, ``severity`` and ``message``; ``layer_id``
    is present when a layer owns the finding. ``pass`` is false for any
    ``warn`` or ``block`` marker; an unavailable advisory check is ``info``.
    """
    directory = Path(job_dir) if job_dir is not None else None
    story = _story_for_edit(job, edit)
    track = _caption_track(directory, edit)
    try:
        compiled = compose_render.compile_edit(
            edit,
            clips=story.get("clips") or [],
            source=job.get("source") or {},
            scenes=(job.get("analysis") or {}).get("scenes") or [],
            caption_track=track,
            include_captions=True,
            motion_engine=compose_render.EDIT_MOTION_ENGINE,
        )
    except compose_render.ComposeError as exc:
        raise PreflightError(
            "compose_failed", str(exc),
            suggestion="Fix the Edit layer that the compiler rejected.",
            status=int(getattr(exc, "status_code", 422)),
        ) from exc
    duration = _duration(compiled)
    scenes = [
        item for item in (job.get("analysis") or {}).get("scenes") or []
        if isinstance(item, dict)
    ]
    markers: list[dict] = []
    families: tuple[tuple[str, Callable[[], list[dict]]], ...] = (
        ("collision", lambda: collision_markers(compiled, duration)),
        (
            "face_overlap",
            lambda: face_overlap_markers(
                compiled, scenes, edit.get("clean") or [], duration,
            ),
        ),
        ("safe_zone", lambda: safe_zone_markers(compiled, duration)),
        ("caption_density", lambda: caption_density_markers(track, duration)),
        (
            "loudness",
            lambda: loudness_markers(
                edit, job, directory, duration, measure_media=measure_media,
            ),
        ),
        ("voice_fit", lambda: voice_fit_markers(edit, duration)),
        ("missing_music_license", lambda: music_licence_markers(edit, duration)),
    )
    for name, run in families:
        try:
            markers.extend(run())
        except Exception:  # noqa: BLE001 - one advisory check must not hide others
            LOGGER.exception("preflight check %s failed", name)
    try:
        markers.extend(
            uncovered_text_markers(directory, edit, compiled, duration),
        )
    except Exception:  # noqa: BLE001 - missing Check data stays advisory
        LOGGER.exception("preflight uncovered-text check failed")
    issue = residual_error
    report = residual_report
    if report is None and issue == "" and check_residual and edit.get("clean"):
        try:
            report = routes_cleanup.measure_residual(
                job,
                edit,
                directory or Path("."),
                max_frames=PREFLIGHT_RESIDUAL_FRAMES,
                fps=PREFLIGHT_RESIDUAL_FPS,
                quality="draft",
                story=story,
                timeout=PREFLIGHT_RESIDUAL_TIMEOUT,
            )
        except routes_cleanup.ResidualFailure as exc:
            issue = exc.reason
        except Exception as exc:  # noqa: BLE001 - residual is a marker, not a blocker
            LOGGER.exception("preflight residual failed")
            issue = f"{type(exc).__name__}: {exc}"
    elif report is None and check_residual and not edit.get("clean"):
        issue = ""
    try:
        markers.extend(residual_markers(
            edit, compiled, report, duration, issue=issue,
        ))
    except Exception:  # noqa: BLE001
        LOGGER.exception("preflight residual marker failed")
    markers = _dedupe(markers, duration)
    return {
        "markers": markers,
        "pass": not any(
            item.get("severity") in {"warn", "block"} for item in markers
        ),
    }


@router.get("/api/jobs/{job_id}/edits/{edit_id}/preflight")
def edit_preflight(job_id: str, edit_id: str) -> dict:
    """Inline preflight markers for one Edit version."""
    import app as app_module  # noqa: PLC0415 - avoid an import cycle

    job = app_module.load_job(job_id)
    if job.get("status") != "ready" or not job.get("analysis"):
        raise HTTPException(409, "Analysis is not ready yet.")
    try:
        edit = edits.load_edit(app_module._job_dir(job_id), edit_id)
    except edits.EditError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    if edit is None:
        raise HTTPException(404, "Edit not found.")
    try:
        return run_edit_preflight(
            job, edit, app_module._job_dir(job_id),
        )
    except PreflightError as exc:
        raise HTTPException(exc.status, exc.as_detail()) from exc
    except Exception as exc:  # noqa: BLE001 - keep the JSON error contract
        LOGGER.exception(
            "edit preflight crashed for job %s edit %s", job_id, edit_id,
        )
        raise HTTPException(
            500, f"Preflight failed: {type(exc).__name__}: {exc}",
        ) from exc
