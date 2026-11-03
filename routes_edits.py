"""Versioned Edit API for the Studio editor.

The router is always registered. Every route works on one job and one story:
``/api/jobs/{job_id}/edits``. Nothing here starts a render or touches ffmpeg.
Storage and validation live in :mod:`edits`; preview compilation lives in
:mod:`compose_render`.
"""

from __future__ import annotations

import math
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field

import captions
import compose_render
import detect
import edits
import history_store
import render
import rights


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
    sequence: list[dict] = Field(default_factory=list)
    clean: list[dict] = Field(default_factory=list)
    reframe: dict = Field(default_factory=dict)
    motion: list[dict] = Field(default_factory=list)
    color: dict = Field(default_factory=dict)
    graphics: list[dict] = Field(default_factory=list)
    captions: dict = Field(default_factory=dict)
    audio: dict = Field(default_factory=dict)
    border: dict = Field(default_factory=dict)
    output: dict = Field(default_factory=dict)


class EditPatchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: list[dict] = Field(default_factory=list)
    clean: list[dict] = Field(default_factory=list)
    reframe: dict = Field(default_factory=dict)
    motion: list[dict] = Field(default_factory=list)
    color: dict = Field(default_factory=dict)
    graphics: list[dict] = Field(default_factory=list)
    captions: dict = Field(default_factory=dict)
    audio: dict = Field(default_factory=dict)
    border: dict = Field(default_factory=dict)
    output: dict = Field(default_factory=dict)
    # Studio autosave sets this: a save within COALESCE_S of the head it
    # replaces folds into that version instead of adding one per keystroke.
    coalesce: bool = False


# Autosaves this close together become one version in the history.
COALESCE_S = 5.0


class EditRestoreBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str | None = Field(default=None, max_length=64)
    history_entry: str | None = Field(default=None, max_length=64)


router = APIRouter()

_LAYER_FIELDS = (
    "sequence", "clean", "reframe", "motion", "color", "graphics", "captions",
    "audio", "border", "output",
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


def _edit_clips(edit: dict, story: dict) -> list[dict]:
    """The clip order this Edit renders. A custom sequence wins."""
    sequence = edit.get("sequence") or []
    if not sequence:
        return story.get("clips") or []
    clips = []
    for index, clip in enumerate(sequence):
        start = float(clip.get("start") or 0.0)
        end = float(clip.get("end") or start)
        clips.append({
            **clip,
            "index": index,
            "dur": round(max(0.0, end - start), 3),
        })
    return clips


def _story_clips_changed(edit: dict, story: dict) -> bool:
    if edit.get("sequence"):
        return False
    return edits.clip_snapshot_hash(story.get("clips") or []) != (
        edit.get("story_ref") or {}
    ).get("clip_hash")


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


def _clean_rights_attested(job: dict) -> bool:
    """Whether the job carries the tick, keeping the legacy-job rule."""
    return rights.job_attested(job)


def _require_clean_rights(job: dict, edit: dict) -> None:
    """Enforce the server-side rights gate on every save of Clean layers.

    The gate reads ``rights.py`` only. It never trusts a request body or
    browser storage. With the lock off, Clean saves are open except for the
    hard kind rules enforced by :func:`_require_clean_kinds`. Missing rights
    on a legacy job is allowed for migration; an explicit unattested record is
    refused while the lock is on.
    """
    if not edit.get("clean"):
        return
    if not rights.lock_enabled():
        return
    if _clean_rights_attested(job):
        return
    raise HTTPException(
        409,
        "Rights attestation is required before saving a Clean layer. "
        "Attest at Import or Check.",
    )


_CLEAN_KIND_MESSAGES = {
    "watermark": "Watermark removal is not supported. Use your original file.",
    "screen_text": (
        "Screen-recording text is never cleaned. Leave that Clean layer out."
    ),
    "attestation_required": (
        "Own-footage attestation is required for a handle or logo Clean layer."
    ),
    "rights_not_attested": (
        "Rights attestation is required before saving a Clean layer. "
        "Attest at Import or Check."
    ),
}


def _require_clean_kinds(job: dict, edit: dict, job_dir=None) -> None:
    """Re-run the detected-kind policy for layers that name a Check tracklet.

    This is the second line of defence behind the Clean rights gate: a layer
    that names its Check kind cannot smuggle a watermark or screen text in,
    and a handle/logo layer needs the server-side attestation even when the
    rest of the Edit would be allowed. ``tracklet_kind`` is the explicit form;
    a layer that only carries ``tracklet_id`` is resolved from the stored
    Check report when one is available.
    """
    record = job.get("rights")
    attested = (
        rights.normalize_attestation(record.get("attested"))
        if isinstance(record, dict) else False
    )
    report_kinds: dict[str, str] | None = None
    for layer in edit.get("clean") or []:
        kind = str(layer.get("tracklet_kind") or "").strip()
        if not kind:
            tracklet_id = str(layer.get("tracklet_id") or "").strip()
            if not tracklet_id or job_dir is None:
                continue
            if report_kinds is None:
                report_kinds = {}
                try:
                    report = detect.load_report(job_dir)
                except Exception:  # noqa: BLE001 - a bad report is not a save gate
                    report = None
                for tracklet in (report or {}).get("tracklets") or []:
                    if isinstance(tracklet, dict) and tracklet.get("id"):
                        report_kinds[str(tracklet["id"])] = str(
                            tracklet.get("kind") or "",
                        )
            kind = report_kinds.get(tracklet_id, "")
        if not kind:
            continue
        blocked = detect.cleanup_block_reason(
            kind, attested=attested, job=job,
        )
        # The lock itself is enforced on Clean saves by _require_clean_rights.
        # This pass only enforces the hard kind rules on every save, so a
        # colour or text edit never rewrites what an old Clean layer can do.
        if blocked not in {"watermark", "screen_text", "attestation_required"}:
            continue
        raise HTTPException(
            409,
            _CLEAN_KIND_MESSAGES.get(
                blocked, f"Clean layer {layer.get('id')} is not allowed.",
            ),
        )


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
    merged = {key: base.get(key) for key in _LAYER_FIELDS}
    for key in _LAYER_FIELDS:
        if key in values:
            merged[key] = values[key]
    return merged


class _StaleHead(Exception):
    pass


def _persist(job_id: str, edit: dict, *, replaces: str | None = None) -> dict:
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
        # A folded autosave replaces the head instead of extending it.
        expected = replaces or saved.get("parent")
        if edits.pointer_edit_id(job, key) != expected:
            raise _StaleHead()
        edits.set_pointer(job, saved)

    try:
        job = _app().update_job(job_id, mutate)
    except _StaleHead:
        raise HTTPException(409, "This story changed in another window. Reload and try again.")
    edits.append_history(_job_dir(job_id), saved)
    return job


def _story_for_edit(job: dict, edit: dict) -> dict | None:
    reference = edit.get("story_ref") or {}
    set_id = str(reference.get("set_id") or "")
    story_id = str(reference.get("story_id") or "")
    raw = job.get("clip_sets")
    records = raw.values() if isinstance(raw, dict) else raw or []
    record = next(
        (
            item for item in records
            if isinstance(item, dict) and str(item.get("id") or "") == set_id
        ),
        None,
    )
    if record is None:
        return None
    return next(
        (
            item for item in record.get("stories") or []
            if isinstance(item, dict) and str(item.get("id") or "") == story_id
        ),
        None,
    )


def _edit_is_stale(job: dict | None, edit: dict) -> bool:
    """True when the Edit's story moved since the Edit was made."""
    if job is None:
        return False
    story = _story_for_edit(job, edit)
    if story is None:
        return True
    return _story_clips_changed(edit, story)


def _payload(edit: dict, *, changed: bool = False, job: dict | None = None) -> dict:
    key = edits.story_key(
        edit["story_ref"]["set_id"],
        edit["story_ref"]["story_id"],
        edit["aspect"],
    )
    current = edits.pointer_edit_id(job, key) if job is not None else edit["id"]
    stale = _edit_is_stale(job, edit)
    value = edits.public_edit(edit)
    value.update({
        "changed": bool(changed),
        "is_current": current == edit["id"],
        "stale": stale,
    })
    return {
        "edit": value,
        "id": edit["id"],
        "version": edit["version"],
        "hash": edit["hash"],
        "key": key,
        "changed": bool(changed),
        "stale": stale,
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


def _default_captions(job_id: str, set_id: str, story_id: str, value) -> dict | None:
    """Captions are on by default: a new story Edit without a track gets the
    story's track in the default style when the job has speech. An explicit
    ``enabled: false`` or a malformed value is left for validation."""
    if value is not None and not isinstance(value, dict):
        return value
    captions = dict(value or {})
    if captions.get("track_id") or captions.get("enabled") is False:
        return value
    track = _app().default_story_caption_track(job_id, set_id, story_id)
    if track is None:
        return value
    captions.update({"track_id": track.id, "style_id": track.style_id, "enabled": True})
    return captions


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
        layers["captions"] = _default_captions(
            job_id, body.set_id, body.story_id, layers.get("captions"),
        )
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
    _require_clean_rights(job, edited)
    _require_clean_kinds(job, edited, _job_dir(job_id))
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
    if _story_clips_changed(edit, story):
        raise HTTPException(
            409, "Story clips changed since this Edit was created; create a new Edit.",
        )
    values = body.model_dump(exclude_unset=True)
    coalesce = bool(values.pop("coalesce", False))
    layers = _merge_layers(edit, values)
    # Fold a burst of autosaves into one version: the new head takes the
    # replaced head's place in the chain (same parent and number). The old
    # sidecar stays on disk, immutable, but is no longer in the history.
    fold = (
        coalesce
        and edit.get("parent")
        and time.time() - float(edit.get("created") or 0.0) < COALESCE_S
    )
    try:
        edited = edits.build_edit(
            story_ref=edit["story_ref"],
            aspect=edit["aspect"],
            version=edit["version"] if fold else edit["version"] + 1,
            parent=edit["parent"] if fold else edit["id"],
            **layers,
        )
    except edits.EditError as exc:
        raise _http(exc) from exc
    _validate_edit(job_id, edited)
    if "clean" in values:
        _require_clean_rights(job, edited)
    _require_clean_kinds(job, edited, _job_dir(job_id))
    if edited["hash"] == edit["hash"]:
        return _payload(edit, changed=False, job=job)
    _persist(job_id, edited, replaces=edit["id"] if fold else None)
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
    _require_clean_rights(job, restored)
    _require_clean_kinds(job, restored, _job_dir(job_id))
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
    _require_clean_rights(job, restored)
    _require_clean_kinds(job, restored, _job_dir(job_id))
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
    if _story_clips_changed(edit, story):
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
            clips=_edit_clips(edit, story),
            source=job.get("source") or {},
            scenes=(job.get("analysis") or {}).get("scenes") or [],
            caption_track=caption_track,
            include_captions=include_captions,
        )
    except compose_render.ComposeError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return compiled


def _fresh_story(
    job_id: str,
    edit_id: str,
) -> tuple[dict, dict, dict]:
    """Load the job, Edit and story, refusing a stale story with 409."""
    job = _app().load_job(job_id)
    _app().require_source(job)
    edit = _load(edit_id, _job_dir(job_id))
    record, story = _resolve_story(
        job, edit["story_ref"]["set_id"], edit["story_ref"]["story_id"],
    )
    _check_fresh(record, job)
    if _story_clips_changed(edit, story):
        raise HTTPException(
            409, "Story clips changed since this Edit was created; create a new Edit.",
        )
    return job, edit, story


def _compiled_preview(
    job_id: str,
    job: dict,
    edit: dict,
    story: dict,
    *,
    size: tuple[int, int],
) -> dict:
    track = _caption_track(job_id, edit, missing=409)
    caption_track = None
    if track is not None:
        caption_track = {
            "track_id": track.id,
            "style_id": track.style_id,
            "style": track.style,
            "cues": [cue.to_dict() for cue in track.cues],
        }
    try:
        return compose_render.compile_edit(
            edit,
            clips=_edit_clips(edit, story),
            source=job.get("source") or {},
            scenes=(job.get("analysis") or {}).get("scenes") or [],
            caption_track=caption_track,
            size=size,
            motion_engine=compose_render.EDIT_MOTION_ENGINE,
        )
    except compose_render.ComposeError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.get(
    "/api/jobs/{job_id}/edits/{edit_id}/frame",
    responses={200: {"content": {"image/jpeg": {}}}},
)
def edit_frame(
    job_id: str,
    edit_id: str,
    t: float | None = None,
    quality: str = "draft",
) -> Response:
    """One JPEG frame from the exact graph the final render uses."""
    job, edit, story = _fresh_story(job_id, edit_id)
    quality = str(quality or "draft").strip().lower()
    if quality not in {"draft", "final"}:
        raise HTTPException(422, "quality must be draft or final.")
    if t is None or not math.isfinite(float(t)):
        raise HTTPException(422, "t must be a finite time in seconds.")
    quality = "draft" if quality == "draft" else "final"
    out_w, out_h = render._dims(edit["aspect"], quality)
    compiled = _compiled_preview(
        job_id, job, edit, story, size=(out_w, out_h),
    )
    total = float(
        (compiled.get("segments") or [{}])[-1].get("out_end") or 0.0
    )
    at = float(t)
    if not math.isfinite(at):
        raise HTTPException(422, "t must be a finite time in seconds.")
    if at < 0.0:
        raise HTTPException(
            422, f"t must be between 0 and the story duration ({total:.3f}s).",
        )
    # A scrubber sends the story end exactly. render_story_frame already
    # clamps to the last frame; accept that one request instead of 422.
    if at > total + (1.0 / 30.0):
        raise HTTPException(
            422, f"t must be between 0 and the story duration ({total:.3f}s).",
        )
    at = min(at, total)
    try:
        payload = render.render_story_frame(
            str(job["source"]["path"]),
            job["source"],
            _job_dir(job_id),
            compiled,
            at,
            quality=quality,
            aspect=edit["aspect"],
        )
    except render.PipelineError as exc:
        raise HTTPException(500, str(exc)) from exc
    return Response(
        content=payload,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@router.get(
    "/api/jobs/{job_id}/edits/{edit_id}/proxy",
    responses={200: {"content": {"video/mp4": {}}}},
)
def edit_proxy(job_id: str, edit_id: str) -> FileResponse:
    """540-wide H.264 proxy of the story range, built once and reused."""
    job, edit, story = _fresh_story(job_id, edit_id)
    try:
        path = render.build_story_proxy(
            str(job["source"]["path"]),
            job["source"],
            _job_dir(job_id),
            _edit_clips(edit, story),
            scenes=(job.get("analysis") or {}).get("scenes") or [],
            aspect=edit["aspect"],
        )
    except render.PipelineError as exc:
        raise HTTPException(500, str(exc)) from exc
    return FileResponse(path, media_type="video/mp4")
