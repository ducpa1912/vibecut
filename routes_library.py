"""Finished-video library: one read-only list of render artifacts across jobs.

The library is a projection over files that already exist:

    data/jobs/<job_id>/job.json
    data/jobs/<job_id>/artifacts/<artifact_id>/manifest.json
    data/jobs/<job_id>/artifacts/<artifact_id>/reel.mp4
    data/jobs/<job_id>/artifacts/<artifact_id>/poster.jpg

Nothing here writes, migrates or creates an index. A missing or corrupt job
or manifest is skipped instead of hiding the rest of the library, and old
manifests without story/aspect/version/size still list with those fields
blank. Artifact ids are validated by ``artifacts.load_manifest`` before they
are used in a URL or a path.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Request

import artifacts

ROOT = Path(__file__).resolve().parent
DEFAULT_LIMIT = 60
MAX_LIMIT = 200

router = APIRouter()


def data_root() -> Path:
    """The data directory, resolved the same way app.py resolves it."""
    value = os.environ.get("VIBECUT_DATA")
    return Path(value).expanduser().resolve() if value else (ROOT / "data")


def jobs_root(request: Request) -> Path:
    """Jobs directory for this app.

    ``install()`` pins the app's own JOBS/DATA path on ``app.state`` so a test
    app or a differently configured host never reads the default checkout.
    The environment stays the fallback for a bare ``include_router`` install.
    """
    state = getattr(getattr(request, "app", None), "state", None)
    override = getattr(state, "library_jobs_dir", None) if state is not None else None
    if override:
        return Path(override)
    return data_root() / "jobs"


def install(app: Any, jobs_dir: str | Path | None = None) -> Any:
    """Register ``GET /api/artifacts`` on an existing FastAPI app.

    app.py can use either::

        import routes_library
        routes_library.install(app)

    or the bare ``app.include_router(routes_library.router)`` line. The
    helper additionally pins ``app.JOBS``/``app.DATA`` so the route follows
    the host's configured data root.
    """
    root = Path(jobs_dir) if jobs_dir is not None else getattr(app, "JOBS", None)
    if root is None:
        data = getattr(app, "DATA", None)
        if data is not None:
            root = Path(data) / "jobs"
    if root is not None:
        app.state.library_jobs_dir = Path(root)
    app.include_router(router)
    return app


def _int(value: Any, default: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(number, high))


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _date(created: float | None) -> str:
    if not created:
        return ""
    try:
        return time.strftime("%Y-%m-%d", time.localtime(created))
    except (OSError, OverflowError, ValueError):
        return ""


def _load_job(job_dir: Path) -> dict:
    """Read job.json for labels only. Unreadable jobs still list artifacts."""
    try:
        value = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _story_titles(job: dict) -> tuple[dict[str, str], str]:
    """Map story id -> title, plus the first titled story for a job label."""
    records = job.get("clip_sets")
    if isinstance(records, dict):
        records = list(records.values())
    titles: dict[str, str] = {}
    first = ""
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict):
            continue
        stories = record.get("stories")
        for story in stories if isinstance(stories, list) else []:
            if not isinstance(story, dict):
                continue
            story_id = _text(story.get("id"))
            title = _text(story.get("title"))
            if story_id and title and story_id not in titles:
                titles[story_id] = title
            if title and not first:
                first = title
    return titles, first


def _job_labels(job: dict, job_id: str) -> tuple[str, str, dict[str, str]]:
    source = job.get("source") if isinstance(job.get("source"), dict) else {}
    ingest = job.get("ingest") if isinstance(job.get("ingest"), dict) else {}
    titles, first_story = _story_titles(job)
    title = _text(job.get("title")) or _text(ingest.get("title"))
    source_label = _text(source.get("name"))
    job_title = title or first_story or source_label or job_id
    return job_title, source_label, titles


def _number_and_date(manifest: dict) -> tuple[float | None, str]:
    created = _number(manifest.get("created"))
    if created is None:
        created = _number(manifest.get("completed"))
    return created, _date(created)


def _size(job_dir: Path, artifact_id: str, manifest: dict) -> int | None:
    try:
        path = artifacts.media_path(job_dir, artifact_id, "reel.mp4")
        if path.is_file():
            size = path.stat().st_size
            if size > 0:
                return int(size)
    except (OSError, artifacts.ArtifactError):
        pass
    render_info = manifest.get("render")
    if isinstance(render_info, dict):
        try:
            size = int(render_info.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        if size > 0:
            return size
    return None


def _media(job_dir: Path, job_id: str, artifact_id: str) -> tuple[str | None, str | None]:
    base = f"/api/jobs/{quote(job_id, safe='')}/artifacts/{artifact_id}/media"
    reel = f"{base}/reel.mp4" if artifacts.has_media(job_dir, artifact_id, "reel.mp4") else None
    poster = (
        f"{base}/poster.jpg"
        if artifacts.has_media(job_dir, artifact_id, "poster.jpg")
        else None
    )
    return reel, poster


def _search_text(row: dict) -> str:
    return " ".join(
        str(value)
        for value in (
            row.get("artifact_id"),
            row.get("job_id"),
            row.get("job_title"),
            row.get("source_label"),
            row.get("story_id"),
            row.get("story_title"),
            row.get("aspect"),
            row.get("quality"),
            row.get("version_label"),
            row.get("date"),
            row.get("status"),
        )
        if value not in (None, "")
    ).casefold()


def _collect(jobs: Path) -> list[dict]:
    """Every valid manifest under ``jobs``, with neutral metadata attached."""
    rows: list[dict] = []
    root = jobs.resolve()
    try:
        children = list(jobs.iterdir())
    except OSError:
        return rows
    for child in children:
        try:
            if not child.is_dir() or child.is_symlink():
                continue
            child.resolve().relative_to(root)
        except (OSError, ValueError):
            continue
        job_id = child.name
        job = _load_job(child)
        job_title, source_label, story_titles = _job_labels(job, job_id)
        try:
            manifests = artifacts.list_manifests(child)
        except OSError:
            continue
        for manifest in manifests:
            artifact_id = _text(manifest.get("artifact_id"))
            if not artifacts.is_safe_artifact_id(artifact_id):
                continue
            spec = manifest.get("spec") if isinstance(manifest.get("spec"), dict) else {}
            story_id = _text(manifest.get("story_id")) or _text(spec.get("story_id"))
            aspect = _text(manifest.get("aspect")) or _text(spec.get("aspect"))
            quality = _text(manifest.get("quality")) or _text(spec.get("quality"))
            target = manifest.get("target")
            if target in (None, ""):
                target = spec.get("target")
            created, date = _number_and_date(manifest)
            reel, poster = _media(child, job_id, artifact_id)
            render_info = manifest.get("render") if isinstance(manifest.get("render"), dict) else {}
            row = {
                "artifact_id": artifact_id,
                "job_id": job_id,
                "job_title": job_title,
                "source_label": source_label,
                "story_id": story_id,
                "story_title": (
                    story_titles.get(story_id)
                    or _text(manifest.get("title"))
                ),
                "aspect": aspect,
                "shape": aspect,
                "quality": quality,
                "target": target,
                "version": _number(manifest.get("version")),
                "version_label": "",
                "created": created,
                "date": date,
                "size": _size(child, artifact_id, manifest),
                "status": _text(manifest.get("status")) or None,
                "pinned": bool(manifest.get("pinned")),
                "url": reel,
                "media_url": reel,
                "poster_url": poster,
                "thumb_url": poster,
                "download_url": reel,
                "duration": render_info.get("duration"),
                "width": render_info.get("width"),
                "height": render_info.get("height"),
                "_sort": created or 0.0,
            }
            rows.append(row)
    return rows


def _assign_versions(rows: list[dict]) -> None:
    """Use the stored version, else a deterministic per-story sequence.

    Old manifests predate ``version``. Their sequence is derived from
    creation time inside the same job/story/aspect group; nothing is written
    back, so repeated calls and old links are stable.
    """
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for row in rows:
        story = row.get("story_id") or f"target:{row.get('target') or 0}"
        key = (str(row.get("job_id") or ""), story, str(row.get("aspect") or ""))
        groups.setdefault(key, []).append(row)
    for group in groups.values():
        group.sort(key=lambda item: (item.get("_sort") or 0, item["artifact_id"]))
        for index, row in enumerate(group, start=1):
            version = row.get("version")
            if not version:
                row["version"] = index
            row["version_label"] = f"v{int(row['version'])}"


@router.get("/api/artifacts")
def list_artifacts(
    request: Request,
    q: str = "",
    job_id: str = "",
    shape: str = "",
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> dict:
    """List finished renders across every job, newest first.

    Read-only. ``q`` searches id, job/source/story titles, shape, quality,
    version, date and status. ``job_id`` and ``shape`` are exact filters.
    Pagination is clamped so a caller cannot ask for the whole disk or a
    negative offset.
    """
    limit = _int(limit, DEFAULT_LIMIT, 1, MAX_LIMIT)
    offset = _int(offset, 0, 0, 10 ** 9)
    terms = [term for term in str(q or "").casefold().split() if term]
    wanted_job = str(job_id or "")
    wanted_shape = str(shape or "")

    rows = _collect(jobs_root(request))
    _assign_versions(rows)
    for row in rows:
        row["_search"] = _search_text(row)

    matched = [
        row for row in rows
        if (not wanted_job or row.get("job_id") == wanted_job)
        and (not wanted_shape or row.get("aspect") == wanted_shape)
        and all(term in row["_search"] for term in terms)
    ]
    matched.sort(
        key=lambda row: (row.get("_sort") or 0.0, row["artifact_id"]),
        reverse=True,
    )

    page = []
    for row in matched[offset:offset + limit]:
        value = {key: item for key, item in row.items() if not key.startswith("_")}
        page.append(value)
    return {
        "artifacts": page,
        "total": len(matched),
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(page) < len(matched),
        "q": str(q or ""),
        "job_id": wanted_job,
        "shape": wanted_shape,
    }
