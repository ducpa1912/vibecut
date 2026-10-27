"""Migrate legacy jobs into the versioned Edit document.

Before Wave 1 a job stored its story captions as a pointer to one immutable
caption track::

    job["story_captions"]["{set_id}:{story_id}"] -> caption_track_id

The Studio editor reads and writes Edits instead. This module gives every
legacy story a captions-only 9:16 Edit and points ``job["story_edits"]`` at it.
Nothing else changes:

* the caption track file stays where it was;
* ``story_captions`` stays in the job so the Classic UI keeps reading and
  writing its track;
* a story/aspect that already has an Edit is never touched;
* no render is started and no legacy artifact is rewritten.

The migration is idempotent. It runs from the app startup hook and can also be
called directly, which is how the tests exercise it.

Only files under one job directory are touched: ``job.json`` and one immutable
Edit sidecar per migrated story. Jobs that are missing a track, have an invalid
story id, or whose track belongs to another job are skipped and reported.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

import captions
import edits

LOGGER = logging.getLogger("vibecut.migrations")

MIGRATION_VERSION = 1
DEFAULT_ASPECT = "9:16"


def _read_job(job_dir: Path) -> dict:
    path = job_dir / "job.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path} is unreadable.") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path} is not a job object.")
    return value


def _write_job(job_dir: Path, job: dict) -> None:
    """Replace job.json atomically. ``updated`` is intentionally preserved."""
    path = job_dir / "job.json"
    temporary = job_dir / f".job.migrate.{uuid.uuid4().hex}.tmp"
    try:
        temporary.write_text(
            json.dumps(job, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except OSError:
            pass


def _clip_sets(job: dict) -> list[dict]:
    value = job.get("clip_sets") or []
    if isinstance(value, dict):
        return [item for item in value.values() if isinstance(item, dict)]
    return [item for item in value if isinstance(item, dict)]


def _stories(job: dict) -> list[tuple[str, dict]]:
    rows: list[tuple[str, dict]] = []
    for record in _clip_sets(job):
        set_id = str(record.get("id") or "").strip()
        if not set_id:
            continue
        for story in record.get("stories") or []:
            if isinstance(story, dict):
                rows.append((set_id, story))
    return rows


def _story_pair(key: Any) -> tuple[str, str] | None:
    text = str(key or "")
    set_id, separator, story_id = text.partition(":")
    set_id = set_id.strip()
    story_id = story_id.strip()
    if not separator or not set_id or not story_id:
        return None
    return set_id, story_id


def _candidate(
    mapping: dict[tuple[str, str], list[dict]],
    set_id: str,
    story_id: str,
    track_id: str,
    source: str,
) -> None:
    track_id = str(track_id or "").strip()
    if not track_id:
        return
    rows = mapping.setdefault((set_id, story_id), [])
    if any(row["track_id"] == track_id for row in rows):
        return
    rows.append({"track_id": track_id, "source": source})


def legacy_tracks(job: dict) -> dict[tuple[str, str], list[dict]]:
    """Return candidate caption tracks per story, current pointer first.

    ``story_captions`` is authoritative. A story render record is a fallback
    for jobs that predate that table: it names the track that last rendered
    the story. Duplicate render records are ordered newest first.
    """
    mapping: dict[tuple[str, str], list[dict]] = {}
    table = job.get("story_captions")
    if isinstance(table, dict):
        for key, value in table.items():
            pair = _story_pair(key)
            if pair is not None:
                _candidate(mapping, pair[0], pair[1], str(value or ""), "story_captions")

    rendered: list[tuple[float, str, str, str]] = []
    records = job.get("renders")
    if isinstance(records, dict):
        for record in records.values():
            if not isinstance(record, dict):
                continue
            set_id = str(record.get("set_id") or "").strip()
            story_id = str(record.get("story_id") or "").strip()
            track_id = str(record.get("caption_track_id") or "").strip()
            if not (set_id and story_id and track_id):
                continue
            try:
                created = float(record.get("created") or 0.0)
            except (TypeError, ValueError):
                created = 0.0
            rendered.append((created, set_id, story_id, track_id))
    rendered.sort(reverse=True)
    for _, set_id, story_id, track_id in rendered:
        _candidate(mapping, set_id, story_id, track_id, "story_render")
    return mapping


def _story_ref(set_id: str, story: dict) -> dict:
    clips = [item for item in story.get("clips") or [] if isinstance(item, dict)]
    if not clips:
        raise edits.EditError("Story has no clips to edit.")
    duration = sum(
        float(item.get("dur") or (
            float(item.get("end") or 0.0) - float(item.get("start") or 0.0)
        ))
        for item in clips
    )
    return edits.normalize_story_ref({
        "set_id": set_id,
        "story_id": story.get("id"),
        "clip_hash": edits.clip_snapshot_hash(clips),
        "title": story.get("title") or "",
        "duration": round(max(0.0, duration), 3),
        "clip_count": len(clips),
    })


def _track(job_dir: Path, job_id: str, track_id: str) -> captions.CaptionTrack | None:
    try:
        track = captions.load_track(job_dir, track_id)
    except captions.CaptionError:
        return None
    if track is None or track.id != track_id:
        return None
    if track.job_id and track.job_id != job_id:
        return None
    return track


def _captions_layer(track: captions.CaptionTrack) -> dict:
    try:
        return edits.normalize_captions({
            "track_id": track.id,
            "style_id": track.style_id,
            "enabled": True,
        })
    except edits.EditError:
        # A legacy style name may not be a valid Edit id. The track carries
        # its own full style, so the reference alone is enough.
        return edits.normalize_captions({
            "track_id": track.id,
            "enabled": True,
        })


def _edit_for(
    set_id: str,
    story: dict,
    track: captions.CaptionTrack,
    now: float,
) -> dict:
    return edits.build_edit(
        story_ref=_story_ref(set_id, story),
        aspect=DEFAULT_ASPECT,
        captions=_captions_layer(track),
        created=now,
    )


def migrate_job(
    job_dir: Path | str,
    *,
    job: dict | None = None,
    now: float | None = None,
) -> dict:
    """Create captions-only Edits for one legacy job.

    Returns ``{"job_id", "changed", "migrated", "skipped"}`` where ``migrated``
    and ``skipped`` are per-story rows. Passing ``job`` lets a caller that
    already holds the parsed record reuse it; the pointer table on that object
    is updated in place when an Edit is created.
    """
    job_dir = Path(job_dir)
    record = job if job is not None else _read_job(job_dir)
    job_id = str(record.get("id") or job_dir.name)
    stamp = time.time() if now is None else float(now)
    candidates = legacy_tracks(record)
    migrated: list[dict] = []
    skipped: list[dict] = []
    changed = False

    seen: set[tuple[str, str]] = set()
    for set_id, story in _stories(record):
        story_id = str(story.get("id") or "").strip()
        pair = (set_id, story_id)
        if pair in seen or not story_id:
            continue
        seen.add(pair)
        rows = candidates.get(pair) or []
        if not rows:
            continue
        key = edits.story_key(set_id, story_id, DEFAULT_ASPECT)
        if edits.pointer_edit_id(record, key):
            skipped.append({
                "key": key,
                "story_id": story_id,
                "reason": "already_migrated",
            })
            continue
        # A cleared pointer is a deliberate reset in Studio; immutable versions
        # stay on disk. Never recreate an Edit behind that reset.
        if edits.list_edits(job_dir, key=key):
            skipped.append({
                "key": key,
                "story_id": story_id,
                "reason": "existing_versions",
            })
            continue

        chosen = None
        reasons: list[str] = []
        for candidate in rows:
            track = _track(job_dir, job_id, candidate["track_id"])
            if track is None:
                reasons.append(f"track_missing:{candidate['track_id']}")
                continue
            chosen = (candidate, track)
            break
        if chosen is None:
            skipped.append({
                "key": key,
                "story_id": story_id,
                "reason": ",".join(reasons) or "no_track",
            })
            continue

        candidate, track = chosen
        try:
            edit = _edit_for(set_id, story, track, stamp)
        except (edits.EditError, TypeError, ValueError) as exc:
            skipped.append({
                "key": key,
                "story_id": story_id,
                "reason": f"invalid_story:{exc}",
            })
            continue

        try:
            saved = edits.save_edit(job_dir, edit)
        except edits.EditError as exc:
            skipped.append({
                "key": key,
                "story_id": story_id,
                "reason": f"save_failed:{exc}",
            })
            continue
        edits.set_pointer(record, saved)
        edits.append_history(job_dir, saved)
        changed = True
        migrated.append({
            "key": key,
            "story_id": story_id,
            "track_id": saved["captions"]["track_id"],
            "edit_id": saved["id"],
            "version": saved["version"],
            "source": candidate["source"],
        })

    if changed:
        _write_job(job_dir, record)
    return {
        "job_id": job_id,
        "changed": changed,
        "migrated": migrated,
        "skipped": skipped,
    }


def migrate_all(jobs_dir: Path | str, *, now: float | None = None) -> dict:
    """Scan every ``<job>/job.json`` under ``jobs_dir``.

    A broken job cannot stop startup or any other job. Errors are collected in
    the returned summary and logged once.
    """
    root = Path(jobs_dir)
    summary: dict[str, Any] = {
        "version": MIGRATION_VERSION,
        "scanned": 0,
        "migrated": 0,
        "skipped": 0,
        "failed": 0,
        "jobs": [],
        "errors": [],
    }
    if not root.is_dir():
        return summary
    for path in sorted(root.glob("*/job.json")):
        summary["scanned"] += 1
        job_dir = path.parent
        try:
            result = migrate_job(job_dir, now=now)
        except Exception as exc:  # noqa: BLE001 - one bad job must not block
            summary["failed"] += 1
            summary["errors"].append({
                "job_id": job_dir.name,
                "error": str(exc),
            })
            LOGGER.warning("edit migration failed for %s: %s", job_dir.name, exc)
            continue
        summary["migrated"] += len(result["migrated"])
        summary["skipped"] += len(result["skipped"])
        if result["migrated"] or result["skipped"]:
            summary["jobs"].append(result)

    if summary["migrated"] or summary["failed"]:
        LOGGER.info(
            "edit migration: scanned=%d migrated=%d skipped=%d failed=%d",
            summary["scanned"], summary["migrated"],
            summary["skipped"], summary["failed"],
        )
    return summary
