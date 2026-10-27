"""Versioned Edit API for the Studio editor.

The router is always registered. Every route works on one job and one story:
``/api/jobs/{job_id}/edits``. Nothing here starts a render or touches ffmpeg.
Storage and validation live in :mod:`edits`; preview compilation lives in
:mod:`compose_render`.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

import captions
import compose_render
import edits
import history_store


def _app():
    import app

    return app


def _job_dir(job_id: str):
    return _app()._job_dir(job_id)


class EditCreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    set_id: str = Field(min_length=1, max_length=64)
    story_id: str = Field(min_length=1, max_length=64)
    aspect: str = Field(min_length=1, max_length=8)
    clean: list[dict] = Field(default_factory=list)
    reframe: dict = Field(default_factory=dict)
    motion: list[dict] = Field(default_factory=list)
    color: dict = Field(default_factory=dict)
    graphics: list[dict] = Field(default_factory=list)
    captions: dict = Field(default_factory=dict)
    audio: dict = Field(default_factory=dict)


class EditPatchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clean: list[dict] = Field(default_factory=list)
    reframe: dict = Field(default_factory=dict)
    motion: list[dict] = Field(default_factory=list)
    color: dict = Field(default_factory=dict)
    graphics: list[dict] = Field(default_factory=list)
    captions: dict = Field(default_factory=dict)
    audio: dict = Field(default_factory=dict)


class EditRestoreBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str | None = Field(default=None, max_length=64)
    history_entry: str | None = Field(default=None, max_length=64)


router = APIRouter()

_LAYER_FIELDS = (
    "clean", "reframe", "motion", "color", "graphics", "captions", "audio",
)


def _http(exc: edits.EditError) -> HTTPException:
    return HTTPException(exc.status_code, str(exc))


def _load(edit_id: str, job_dir) -> dict:
    try:
        edit = edits.load_edit(job_dir, edit_id)
    except edits.EditError as exc:
        raise _http(exc) from exc
    if edit is None:
        raise HTTPException(404, "Edit not found.")
    return edit


def _story_records(job: dict) -> list[dict]:
    value = job.get("clip_sets") or []
    if isinstance(value, dict):
        return [item for item in value.values() if isinstance(item, dict)]
    return [item for item in value if isinstance(item, dict)]


def _resolve_story(job: dict, set_id: str, story_id: str) -> tuple[dict, dict]:
    record = next(
        (item for item in _story_records(job) if str(item.get("id") or "") == set_id),
        None,
    )
    if record is None:
        raise HTTPException(404, "Clip set not found.")
    story = next(
        (
            item for item in record.get("stories") or []
            if isinstance(item, dict) and str(item.get("id") or "") == story_id
        ),
        None,
    )
    if story is None:
        raise HTTPException(404, "Story not found in this clip set.")
    return record, story


def _story_ref(record: dict, story: dict) -> dict:
    clips = [item for item in story.get("clips") or [] if isinstance(item, dict)]
    if not clips:
        raise HTTPException(409, "Story has no clips to edit.")
    duration = sum(
        float(item.get("dur") or (
            float(item.get("end") or 0.0) - float(item.get("start") or 0.0)
        ))
        for item in clips
    )
    try:
        return edits.normalize_story_ref({
            "set_id": record["id"],
            "story_id": story["id"],
            "clip_hash": edits.clip_snapshot_hash(clips),
            "title": story.get("title") or "",
            "duration": round(max(0.0, duration), 3),
            "clip_count": len(clips),
        })
    except edits.EditError as exc:
        raise _http(exc) from exc


def _check_fresh(record: dict, job: dict) -> None:
    _app()._clip_set_source_state(job, record)


def _caption_track(job_id: str, edit: dict, *, missing: int = 404):
    track_id = (edit.get("captions") or {}).get("track_id")
    if not track_id:
        return None
    track = captions.load_track(_job_dir(job_id), track_id)
    if track is None:
        raise HTTPException(missing, "Caption track not found.")
    if track.job_id and track.job_id != job_id:
        raise HTTPException(409, "Caption track belongs to another job.")
    return track


def _validate_edit(job_id: str, edit: dict) -> None:
    _caption_track(job_id, edit)


def _current(job: dict, edit: dict) -> str:
    key = edits.story_key(
        edit["story_ref"]["set_id"],
        edit["story_ref"]["story_id"],
        edit["aspect"],
    )
    current = edits.pointer_edit_id(job, key)
    if current != edit["id"]:
        raise HTTPException(
            409,
            "Edit is not the current version; open the current version or restore it.",
        )
    return key


def _merge_layers(base: dict, values: dict) -> dict:
    merged = {key: base[key] for key in _LAYER_FIELDS}
    for key in _LAYER_FIELDS:
        if key in values:
            merged[key] = values[key]
    return merged


class _StaleHead(Exception):
    pass


def _persist(job_id: str, edit: dict) -> dict:
    try:
        saved = edits.save_edit(_job_dir(job_id), edit)
    except edits.EditError as exc:
        raise _http(exc) from exc
    key = edits.story_key(
        saved["story_ref"]["set_id"], saved["story_ref"]["story_id"], saved["aspect"],
    )

    def mutate(job: dict) -> None:
        # Compare-and-swap: a concurrent save moved the head after this edit
        # was built from it, so refuse instead of forking the version chain.
        if edits.pointer_edit_id(job, key) != saved.get("parent"):
            raise _StaleHead()
        edits.set_pointer(job, saved)

    try:
        job = _app().update_job(job_id, mutate)
    except _StaleHead:
        raise HTTPException(409, "This story changed in another window. Reload and try again.")
    edits.append_history(_job_dir(job_id), saved)
    return job


def _payload(edit: dict, *, changed: bool = False, job: dict | None = None) -> dict:
    key = edits.story_key(
        edit["story_ref"]["set_id"],
        edit["story_ref"]["story_id"],
        edit["aspect"],
    )
    current = edits.pointer_edit_id(job, key) if job is not None else edit["id"]
    value = edits.public_edit(edit)
    value.update({
        "changed": bool(changed),
        "is_current": current == edit["id"],
    })
    return {
        "edit": value,
        "id": edit["id"],
        "version": edit["version"],
        "hash": edit["hash"],
        "key": key,
        "changed": bool(changed),
    }


def _find_key(
    set_id: str | None,
    story_id: str | None,
    aspect: str | None,
) -> str | None:
    values = [set_id, story_id, aspect]
    supplied = [value for value in values if value]
    if not supplied:
        return None
    if len(supplied) != 3:
        raise HTTPException(422, "Pass set_id, story_id and aspect together.")
    try:
        return edits.story_key(set_id, story_id, edits.normalize_aspect(aspect))
    except edits.EditError as exc:
        raise _http(exc) from exc


@router.get("/api/jobs/{job_id}/edits")
def list_edits(
    job_id: str,
    set_id: str | None = None,
    story_id: str | None = None,
    aspect: str | None = None,
) -> dict:
    job = _app().load_job(job_id)
    key = _find_key(set_id, story_id, aspect)
    rows = edits.list_edits(_job_dir(job_id), key=key)
    return {
        "edits": rows,
        "count": len(rows),
        "key": key,
        "pointers": dict(edits.pointer_table(job)),
    }


@router.get("/api/jobs/{job_id}/edits/current")
def current_edit(
    job_id: str,
    set_id: str,
    story_id: str,
    aspect: str,
) -> dict:
    job = _app().load_job(job_id)
    key = _find_key(set_id, story_id, aspect)
    current = edits.pointer_edit_id(job, key or "")
    if not current:
        raise HTTPException(404, "This story has no Edit yet.")
    edit = _load(current, _job_dir(job_id))
    return {
        "edit": edits.public_edit(edit),
        "id": edit["id"],
        "version": edit["version"],
        "hash": edit["hash"],
        "key": key,
        "is_current": True,
    }


@router.post("/api/jobs/{job_id}/edits")
def create_edit(job_id: str, body: EditCreateBody) -> dict:
    job = _app().load_job(job_id)
    record, story = _resolve_story(job, body.set_id, body.story_id)
    _check_fresh(record, job)
    try:
        aspect = edits.normalize_aspect(body.aspect)
    except edits.EditError as exc:
        raise _http(exc) from exc
    story_ref = _story_ref(record, story)
    key = edits.story_key(body.set_id, body.story_id, aspect or "")
    current = edits.pointer_edit_id(job, key)
    values = body.model_dump(exclude_unset=True)
    for field in ("set_id", "story_id", "aspect"):
        values.pop(field, None)
    base = None
    if current:
        base = _load(current, _job_dir(job_id))
        layers = _merge_layers(base, values)
        parent = base
    else:
        layers = {key: values.get(key) for key in _LAYER_FIELDS}
        parent = None
    try:
        edited = edits.build_edit(
            story_ref=story_ref,
            aspect=aspect,
            version=(base["version"] + 1) if base else 1,
            parent=base["id"] if base else None,
            **layers,
        )
    except edits.EditError as exc:
        raise _http(exc) from exc
    _validate_edit(job_id, edited)
    if base is not None and edited["hash"] == base["hash"]:
        return _payload(base, changed=False, job=job)
    _persist(job_id, edited)
    return _payload(edited, changed=True, job=_app().load_job(job_id))


@router.patch("/api/jobs/{job_id}/edits/{edit_id}")
def patch_edit(job_id: str, edit_id: str, body: EditPatchBody) -> dict:
    job = _app().load_job(job_id)
    edit = _load(edit_id, _job_dir(job_id))
    _current(job, edit)
    record, story = _resolve_story(
        job, edit["story_ref"]["set_id"], edit["story_ref"]["story_id"],
    )
    _check_fresh(record, job)
    if edits.clip_snapshot_hash(story.get("clips") or []) != edit["story_ref"]["clip_hash"]:
        raise HTTPException(
            409, "Story clips changed since this Edit was created; create a new Edit.",
        )
    values = body.model_dump(exclude_unset=True)
    layers = _merge_layers(edit, values)
    try:
        edited = edits.build_edit(
            story_ref=edit["story_ref"],
            aspect=edit["aspect"],
            version=edit["version"] + 1,
            parent=edit["id"],
            **layers,
        )
    except edits.EditError as exc:
        raise _http(exc) from exc
    _validate_edit(job_id, edited)
    if edited["hash"] == edit["hash"]:
        return _payload(edit, changed=False, job=job)
    _persist(job_id, edited)
    return _payload(edited, changed=True, job=_app().load_job(job_id))


@router.get("/api/jobs/{job_id}/edits/{edit_id}")
def get_edit(job_id: str, edit_id: str) -> dict:
    job = _app().load_job(job_id)
    edit = _load(edit_id, _job_dir(job_id))
    return _payload(edit, changed=False, job=job)


@router.get("/api/jobs/{job_id}/edits/{edit_id}/versions")
def edit_versions(job_id: str, edit_id: str) -> dict:
    job = _app().load_job(job_id)
    edit = _load(edit_id, _job_dir(job_id))
    chain = edits.version_chain(_job_dir(job_id), edit_id)
    key = edits.story_key(
        edit["story_ref"]["set_id"],
        edit["story_ref"]["story_id"],
        edit["aspect"],
    )
    current = edits.pointer_edit_id(job, key)
    return {
        "edit_id": edit_id,
        "key": key,
        "current": current,
        "count": len(chain),
        "versions": [
            {
                "id": item["id"],
                "version": item["version"],
                "parent": item["parent"],
                "hash": item["hash"],
                "created": item["created"],
                "current": item["id"] == current,
            }
            for item in chain
        ],
    }


@router.post("/api/jobs/{job_id}/edits/{edit_id}/undo")
def undo_edit(job_id: str, edit_id: str) -> dict:
    job = _app().load_job(job_id)
    head = _load(edit_id, _job_dir(job_id))
    _current(job, head)
    if not head.get("parent"):
        raise HTTPException(409, "The first Edit version has nothing to undo.")
    target = _load(head["parent"], _job_dir(job_id))
    try:
        restored = edits.restored_edit(target, parent_edit=head)
    except edits.EditError as exc:
        raise _http(exc) from exc
    _validate_edit(job_id, restored)
    _persist(job_id, restored)
    return _payload(restored, changed=True, job=_app().load_job(job_id))


@router.post("/api/jobs/{job_id}/edits/{edit_id}/restore")
def restore_edit(job_id: str, edit_id: str, body: EditRestoreBody) -> dict:
    if not body.version and not body.history_entry:
        raise HTTPException(422, "Pass version or history_entry.")
    job = _app().load_job(job_id)
    head = _load(edit_id, _job_dir(job_id))
    key = _current(job, head)
    target_id = body.version or body.history_entry or ""
    target = _load(target_id, _job_dir(job_id))
    target_key = edits.story_key(
        target["story_ref"]["set_id"],
        target["story_ref"]["story_id"],
        target["aspect"],
    )
    if target_key != key:
        raise HTTPException(409, "The version belongs to a different story or aspect.")
    if target["hash"] == head["hash"]:
        return _payload(head, changed=False, job=job)
    try:
        restored = edits.restored_edit(target, parent_edit=head)
    except edits.EditError as exc:
        raise _http(exc) from exc
    _validate_edit(job_id, restored)
    _persist(job_id, restored)
    return _payload(restored, changed=True, job=_app().load_job(job_id))


@router.delete("/api/jobs/{job_id}/edits/{edit_id}")
def delete_edit(job_id: str, edit_id: str) -> dict:
    """Reset the story/aspect to "no edit". Versions stay on disk: they are
    immutable and rendered artifacts may reference their hashes."""
    job = _app().load_job(job_id)
    edit = _load(edit_id, _job_dir(job_id))
    key = _current(job, edit)

    def mutate(current: dict) -> None:
        edits.clear_pointer(current, key)

    _app().update_job(job_id, mutate)
    return {"cleared": key, "kept_versions": len(edits.list_edits(_job_dir(job_id), key=key))}


@router.get("/api/jobs/{job_id}/edits/{edit_id}/compile")
def compile_edit(
    job_id: str,
    edit_id: str,
    include_captions: bool = True,
) -> dict:
    job = _app().load_job(job_id)
    edit = _load(edit_id, _job_dir(job_id))
    record, story = _resolve_story(
        job, edit["story_ref"]["set_id"], edit["story_ref"]["story_id"],
    )
    _check_fresh(record, job)
    if edits.clip_snapshot_hash(story.get("clips") or []) != edit["story_ref"]["clip_hash"]:
        raise HTTPException(
            409, "Story clips changed since this Edit was created; create a new Edit.",
        )
    caption_track = None
    if include_captions:
        track = _caption_track(job_id, edit, missing=409)
        if track is not None:
            caption_track = {
                "track_id": track.id,
                "style_id": track.style_id,
                "style": track.style,
                "cues": [cue.to_dict() for cue in track.cues],
            }
    try:
        compiled = compose_render.compile_edit(
            edit,
            clips=story.get("clips") or [],
            source=job.get("source") or {},
            scenes=(job.get("analysis") or {}).get("scenes") or [],
            caption_track=caption_track,
            include_captions=include_captions,
        )
    except compose_render.ComposeError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return compiled
