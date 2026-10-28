"""Atomic story trim routes.

One job lock, one ``app.update_job`` commit point. Immutable Edit sidecars, the
rebuilt caption track and the trim receipt are written before the commit; a
failed commit leaves unreferenced orphans and never mutates the story.

Contract: ``docs/R2_TRIM_PLAN.md`` sections 2.1-2.5.
"""

from __future__ import annotations

import copy
import json
import os
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

import artifacts
import captions as caption_engine
import clipset
import edits
import trim

router = APIRouter()

ASPECTS = edits.ASPECTS
MIN_S = trim.MIN_STORY_S
MAX_S = trim.MAX_STORY_S
CAPTION_COUNT_KEYS = ("kept", "moved", "dropped", "added", "manual_kept")


class TrimBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int
    start_sentence: int
    end_sentence: int
    dry_run: bool = False
    # Optional caller snapshot of GET trim's ``aspects`` map. Accepts either
    # ``{aspect: edit_id}`` or the GET shape ``{aspect: {edit_id, stale}}``.
    # When present it is the edit_changed compare-and-swap guard.
    aspects: dict[str, str | dict] | None = None


class TrimUndoBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    undo_token: str = Field(min_length=1, max_length=64)
    expected_revision: int


class TrimRebindBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int
    aspects: dict[str, str | dict] | None = None


class _Conflict(Exception):
    def __init__(
        self,
        payload: dict | None = None,
        code: str = "edit_changed",
        message: str = "An Edit changed in another window. Reload before trimming.",
    ):
        super().__init__("conflict")
        self.payload = payload
        self.code = code
        self.message = message


# ---------------------------------------------------------------- app glue


def _app():
    import app

    return app


def _job_dir(job_id: str):
    return _app()._job_dir(job_id)


def _http(status: int, code: str, message: str, current: dict | None = None):
    detail = {"code": code, "message": message}
    if current is not None:
        detail["current"] = current
    return HTTPException(status, detail=detail)


def _resolve(job_id: str, set_id: str, story_id: str) -> tuple[dict, dict, dict]:
    app = _app()
    job = app.load_job(job_id)
    if job.get("status") != "ready" or not job.get("analysis"):
        raise HTTPException(409, "Analysis is not ready yet.")
    record = app._clip_set_in_job(job, set_id)
    story = app._story_in_set(record, story_id)
    return job, record, story


def _clip_hash(story: dict) -> str:
    return edits.clip_snapshot_hash(story.get("clips") or [])


def _pool(job: dict, record: dict, story: dict):
    app = _app()
    sentences, scenes, _ = app._clipset_pool(job, record)
    rows, bounds = trim.build_pool(sentences, record.get("stories") or [], story)
    return sentences, scenes, rows, bounds


def _neighbours(bounds: dict) -> dict:
    return {"before": bounds.get("before"), "after": bounds.get("after")}


def _aspects(job: dict, story: dict, set_id: str) -> dict:
    job_dir = _job_dir(job["id"])
    current_hash = _clip_hash(story)
    values: dict[str, dict] = {}
    for aspect in ASPECTS:
        key = edits.story_key(set_id, str(story.get("id") or ""), aspect)
        edit_id = edits.pointer_edit_id(job, key)
        if not edit_id:
            continue
        stale = True
        try:
            edit = edits.load_edit(job_dir, edit_id)
        except edits.EditError:
            edit = None
        if (
            edit is not None
            and edit.get("aspect") == aspect
            and (edit.get("story_ref") or {}).get("clip_hash") == current_hash
        ):
            stale = False
        values[aspect] = {"edit_id": edit_id, "stale": stale}
    return values


def _get_payload(job: dict, record: dict, story: dict) -> dict:
    _, _, rows, bounds = _pool(job, record, story)
    return {
        "revision": trim.story_revision(story),
        "story": trim.story_summary(story),
        "clip_hash": _clip_hash(story),
        "pool": [
            {
                "id": item.get("id"),
                "start": item.get("start"),
                "end": item.get("end"),
                "text": item.get("text"),
            }
            for item in rows
        ],
        "neighbours": _neighbours(bounds),
        "aspects": _aspects(job, story, str(record.get("id") or "")),
        "limits": {"min_s": MIN_S, "max_s": MAX_S},
    }


def _check_expected(
    expectation: dict[str, str | dict] | None,
    job: dict,
    story: dict,
    set_id: str,
    current: dict,
) -> None:
    if expectation is None:
        return
    actual = _aspects(job, story, set_id)
    for aspect, wanted in expectation.items():
        edit_id = wanted.get("edit_id") if isinstance(wanted, dict) else wanted
        live = actual.get(aspect) or {}
        if live.get("edit_id") != edit_id:
            raise _http(
                409,
                "edit_changed",
                "An Edit changed in another window. Reload before trimming.",
                current,
            )


def _load_live(
    job: dict, story: dict, set_id: str, current: dict | None = None,
) -> dict[str, dict]:
    job_dir = _job_dir(job["id"])
    live: dict[str, dict] = {}
    for aspect, info in _aspects(job, story, set_id).items():
        try:
            edit = edits.load_edit(job_dir, info["edit_id"])
        except edits.EditError as exc:
            raise _http(
                409,
                "edit_changed",
                "An aspect Edit is unreadable. Open it in Edit and repair it.",
                current,
            ) from exc
        if edit is None:
            raise _http(
                409,
                "edit_changed",
                "An aspect Edit is missing. Open it in Edit and repair it.",
                current,
            )
        live[aspect] = edit
    return live


def _story_ref(record: dict, story: dict) -> dict:
    clips = [item for item in story.get("clips") or [] if isinstance(item, dict)]
    duration = sum(
        float(item.get("dur") or (
            float(item.get("end") or 0.0) - float(item.get("start") or 0.0)
        ))
        for item in clips
    )
    return edits.normalize_story_ref({
        "set_id": record["id"],
        "story_id": story["id"],
        "clip_hash": edits.clip_snapshot_hash(clips),
        "title": story.get("title") or "",
        "duration": round(max(0.0, duration), 3),
        "clip_count": len(clips),
    })


def _restore_edit(
    target: dict,
    parent: dict,
    story_ref: dict,
    *,
    current: dict | None = None,
) -> dict:
    """Restore ``target``'s layers after ``parent`` on the old story ref."""
    try:
        return edits.restored_edit(
            target,
            parent_edit={**parent, "story_ref": story_ref},
        )
    except edits.EditError as exc:
        raise _http(
            409,
            "edit_changed",
            f"Could not restore the {target.get('aspect') or 'aspect'} Edit: {exc}",
            current,
        ) from exc


def _new_edit(
    old: dict,
    story_ref: dict,
    *,
    graphics: list[dict] | None = None,
    captions: dict | None = None,
    current: dict | None = None,
) -> dict:
    try:
        return edits.build_edit(
            story_ref=story_ref,
            aspect=old["aspect"],
            version=int(old["version"]) + 1,
            parent=str(old["id"]),
            clean=old["clean"],
            reframe=old["reframe"],
            motion=old["motion"],
            color=old["color"],
            graphics=old["graphics"] if graphics is None else graphics,
            captions=old["captions"] if captions is None else captions,
            audio=old["audio"],
        )
    except edits.EditError as exc:
        raise _http(
            409,
            "edit_changed",
            f"Could not rebuild the {old.get('aspect') or 'aspect'} Edit: {exc}",
            current,
        ) from exc


# ---------------------------------------------------------------- captions


def _field(value, name: str, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _counts(result) -> dict:
    raw = _field(result, "counts", {}) or {}
    out = {}
    for key in CAPTION_COUNT_KEYS:
        try:
            out[key] = int((raw or {}).get(key) or 0)
        except (TypeError, ValueError):
            out[key] = 0
    return out


def _caption_state(job_id: str, track_id: str | None, clip_hash: str) -> dict:
    if not track_id:
        return {
            "track_id": None,
            "clip_hash": clip_hash,
            "cue_hash": "",
            "rebuilt": False,
        }
    track = caption_engine.load_track(_job_dir(job_id), str(track_id))
    if track is None:
        return {
            "track_id": str(track_id),
            "clip_hash": clip_hash,
            "cue_hash": "",
            "rebuilt": False,
        }
    return {
        "track_id": str(track_id),
        "clip_hash": track.clip_hash or clip_hash,
        "cue_hash": track.cue_hash or caption_engine.cue_hash(track.cues),
        "rebuilt": False,
    }


def _rebuild_captions(
    job_id: str,
    job: dict,
    set_id: str,
    old_story: dict,
    new_story: dict,
    old_track_id: str | None,
    *,
    dry_run: bool,
    current: dict | None = None,
) -> dict:
    """Call T2's caption reflow lazily; map every failure to 409."""
    try:
        import caption_reflow
    except Exception as exc:  # noqa: BLE001 - missing T2 build is a trim failure
        raise _http(
            409,
            "caption_rebuild_failed",
            "Captions could not be rebuilt for the trimmed story.",
            current,
        ) from exc
    error_type = getattr(caption_reflow, "ReflowError", Exception)
    try:
        result = caption_reflow.rebuild_for_story(
            job_id, job, set_id, old_story, new_story, old_track_id,
        )
    except error_type as exc:
        raise _http(
            409,
            "caption_rebuild_failed",
            f"Captions could not be rebuilt: {exc}",
            current,
        ) from exc
    except Exception as exc:  # noqa: BLE001 - T2 faults must not half-commit
        raise _http(
            409,
            "caption_rebuild_failed",
            f"Captions could not be rebuilt: {exc}",
            current,
        ) from exc
    track = _field(result, "track")
    track_id = str(_field(track, "id", "") or "").strip()
    if not track_id:
        raise _http(
            409,
            "caption_rebuild_failed",
            "Caption reflow returned no track.",
            current,
        )
    expected_hash = _clip_hash(new_story)
    track_hash = str(_field(track, "clip_hash", "") or "")
    if track_hash and track_hash != expected_hash:
        raise _http(
            409,
            "caption_rebuild_failed",
            "The rebuilt caption track does not match the new story clips.",
            current,
        )
    cue_hash = str(_field(track, "cue_hash", "") or "")
    if not cue_hash:
        cues = _field(track, "cues", []) or []
        try:
            cue_hash = caption_engine.cue_hash(cues)
        except Exception:  # noqa: BLE001 - metadata only
            cue_hash = ""
    if not dry_run:
        try:
            saved_id = result.save(_job_dir(job_id))
        except Exception as exc:  # noqa: BLE001 - sidecar write before commit
            raise _http(
                409,
                "caption_rebuild_failed",
                f"The rebuilt caption track could not be saved: {exc}",
                current,
            ) from exc
        if saved_id:
            track_id = str(saved_id)
    return {
        "track_id": track_id,
        "clip_hash": track_hash or expected_hash,
        "cue_hash": cue_hash,
        "rebuilt": True,
        "counts": _counts(result),
    }


def _story_track_id(job: dict, set_id: str, story_id: str) -> str | None:
    key = _app()._story_key(set_id, story_id)
    value = (job.get("story_captions") or {}).get(key)
    return str(value) if value else None


def _old_track_id(job: dict, set_id: str, story_id: str, live: dict[str, dict]) -> str | None:
    value = _story_track_id(job, set_id, story_id)
    if value:
        return value
    for edit in live.values():
        track_id = (edit.get("captions") or {}).get("track_id")
        if track_id:
            return str(track_id)
    return None


# ---------------------------------------------------------------- result


def _invalidated(job_id: str, story_id: str, hashes: dict[str, str]) -> list[str]:
    values: list[str] = []
    try:
        manifests = artifacts.list_manifests(_job_dir(job_id))
    except Exception:  # noqa: BLE001 - metadata must not block a trim
        return values
    for manifest in manifests:
        if str(manifest.get("story_id") or "") != str(story_id):
            continue
        aspect = str(manifest.get("aspect") or "9:16")
        if str(manifest.get("edit_hash") or "") == hashes.get(aspect):
            continue
        artifact_id = str(manifest.get("artifact_id") or "")
        if artifact_id and artifact_id not in values:
            values.append(artifact_id)
    return values


def _result(
    story: dict,
    revision: int,
    edit_map: dict[str, dict],
    captions: dict,
    receipt: dict,
    invalidated: list[str],
    stale_aspects: list[str] | None = None,
) -> dict:
    return {
        "story": trim.story_summary(story),
        "revision": int(revision),
        "duration": round(float(story.get("dur") or 0.0), 3),
        "clip_hash": _clip_hash(story),
        "edits": {
            aspect: edits.public_edit(edit)
            for aspect, edit in edit_map.items()
        },
        "captions": {
            "track_id": captions.get("track_id"),
            "clip_hash": captions.get("clip_hash") or _clip_hash(story),
            "cue_hash": captions.get("cue_hash") or "",
            "rebuilt": bool(captions.get("rebuilt")),
        },
        "receipt": receipt,
        "undo_token": receipt["id"],
        "invalidated_artifacts": list(invalidated),
        "stale_aspects": list(stale_aspects or []),
    }


def _replace_record(job: dict, record: dict) -> None:
    current = job.get("clip_sets")
    if isinstance(current, list):
        job["clip_sets"] = [
            item for item in current
            if not (isinstance(item, dict) and item.get("id") == record["id"])
        ]
        job["clip_sets"].append(record)
    else:
        job["clip_sets"] = dict(current or {})
        job["clip_sets"][record["id"]] = record


def _set_tracks(job: dict, key: str, track_id: str | None) -> None:
    tracks = dict(job.get("story_captions") or {})
    if track_id:
        tracks[key] = track_id
    else:
        tracks.pop(key, None)
    job["story_captions"] = tracks


# ---------------------------------------------------------------- receipt io


def _receipt_dir(job_id: str) -> Path:
    return _job_dir(job_id) / "trims"


def _receipt_path(job_id: str, receipt_id: str) -> Path:
    receipt_id = trim.validate_receipt_id(receipt_id)
    return _receipt_dir(job_id) / f"{receipt_id}.json"


def _write_receipt(job_id: str, receipt: dict) -> Path:
    path = _receipt_path(job_id, str(receipt.get("id") or ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    temporary.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return path


def _load_receipt(job_id: str, token: str) -> dict:
    try:
        path = _receipt_path(job_id, token)
    except trim.TrimRangeError as exc:
        raise _http(422, "range_invalid", exc.message) from exc
    if not path.is_file():
        raise HTTPException(404, "Undo token not found.")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(404, "Undo token not found.") from exc
    if not isinstance(value, dict):
        raise HTTPException(404, "Undo token not found.")
    return value


# ---------------------------------------------------------------- trim plan


def _plan_range(job: dict, record: dict, story: dict, body: TrimBody):
    sentences, scenes, rows, bounds = _pool(job, record, story)
    try:
        selection = trim.validate_range(
            rows,
            body.start_sentence,
            body.end_sentence,
            before=bounds.get("_before"),
            after=bounds.get("_after"),
            min_s=MIN_S,
            max_s=MAX_S,
        )
    except trim.TrimRangeError as exc:
        raise _http(422, exc.code, exc.message) from exc
    wanted = [item.get("id") for item in selection["sentences"]]
    try:
        updated = clipset.apply_edits(
            record,
            sentences,
            scenes,
            float((job.get("source") or {}).get("duration") or 0.0),
            story_patches=[{"id": story["id"], "sentences": wanted}],
        )
    except clipset.ClipSetError as exc:
        code = "overlaps_neighbour" if "overlap" in str(exc).lower() else "range_invalid"
        raise _http(422, code, str(exc)) from exc
    new_story = next(
        (
            item for item in updated.get("stories") or []
            if isinstance(item, dict) and str(item.get("id") or "") == str(story.get("id"))
        ),
        None,
    )
    if new_story is None:
        raise _http(
            422,
            "range_invalid",
            "The trimmed range produced no story.",
        )
    old_by_id = {
        str(item.get("id")): item
        for item in record.get("stories") or []
        if isinstance(item, dict) and item.get("id") is not None
    }
    for item in updated.get("stories") or []:
        if not isinstance(item, dict):
            continue
        prior = old_by_id.get(str(item.get("id")))
        revision = trim.story_revision(prior)
        if prior is None:
            revision = 0
        elif trim.range_signature(prior) != trim.range_signature(item):
            revision += 1
        item["revision"] = revision
    new_story["revision"] = trim.story_revision(story) + 1
    return updated, new_story


# ---------------------------------------------------------------- routes


@router.get("/api/jobs/{job_id}/clip-sets/{set_id}/stories/{story_id}/trim")
def get_trim(job_id: str, set_id: str, story_id: str) -> dict:
    app = _app()
    with app.LOCK:
        job, record, story = _resolve(job_id, set_id, story_id)
        return _get_payload(job, record, story)


@router.post("/api/jobs/{job_id}/clip-sets/{set_id}/stories/{story_id}/trim")
def trim_story(
    job_id: str,
    set_id: str,
    story_id: str,
    body: TrimBody,
) -> dict:
    app = _app()
    with app.LOCK:
        job, record, story = _resolve(job_id, set_id, story_id)
        current = _get_payload(job, record, story)
        if trim.story_revision(story) != int(body.expected_revision):
            raise _http(
                409,
                "revision_mismatch",
                "This story changed in another window. Reload and try again.",
                current,
            )
        _check_expected(body.aspects, job, story, set_id, current)
        live = _load_live(job, story, set_id, current)
        updated, new_story = _plan_range(job, record, story, body)
        new_revision = trim.story_revision(story) + 1
        new_story["revision"] = new_revision
        story_ref = _story_ref(updated, new_story)

        graphics: dict[str, list[dict]] = {}
        layer_receipt = trim.empty_layer_receipt()
        for aspect, old_edit in live.items():
            values, counts = trim.ripple_graphics(
                old_edit.get("graphics") or [],
                story.get("clips") or [],
                new_story.get("clips") or [],
            )
            graphics[aspect] = values
            trim.merge_layer_receipt(layer_receipt, counts)

        old_track = _old_track_id(job, set_id, story_id, live)
        if old_track or live:
            caption_state = _rebuild_captions(
                job_id,
                job,
                set_id,
                story,
                new_story,
                old_track,
                dry_run=bool(body.dry_run),
                current=current,
            )
        else:
            caption_state = {
                "track_id": None,
                "clip_hash": _clip_hash(new_story),
                "cue_hash": "",
                "rebuilt": False,
                "counts": {key: 0 for key in CAPTION_COUNT_KEYS},
            }

        new_edits: dict[str, dict] = {}
        for aspect, old_edit in live.items():
            captions_layer = dict(old_edit.get("captions") or {})
            if caption_state.get("track_id"):
                captions_layer["track_id"] = caption_state["track_id"]
            new_edits[aspect] = _new_edit(
                old_edit,
                story_ref,
                graphics=graphics[aspect],
                captions=captions_layer,
                current=current,
            )

        receipt_id = trim.new_receipt_id()
        receipt = trim.make_receipt(
            receipt_id=receipt_id,
            at=time.time(),
            kind="trim",
            job_id=job_id,
            set_id=set_id,
            story_id=story_id,
            old_story=story,
            new_story=new_story,
            old_revision=trim.story_revision(story),
            new_revision=new_revision,
            layers=layer_receipt,
            captions=caption_state.get("counts") or {},
            before_edits=live,
            after_edits={aspect: edit["id"] for aspect, edit in new_edits.items()},
            before_caption=old_track,
            after_caption=caption_state.get("track_id"),
            invalidated_artifacts=_invalidated(
                job_id,
                story_id,
                {aspect: edit["hash"] for aspect, edit in new_edits.items()},
            ),
        )
        invalidated = list(receipt["invalidated_artifacts"])

        if body.dry_run:
            return _result(
                new_story, new_revision, new_edits, caption_state,
                receipt, invalidated,
            )

        job_dir = _job_dir(job_id)
        saved: dict[str, dict] = {}
        try:
            for aspect, edit in new_edits.items():
                saved[aspect] = edits.save_edit(job_dir, edit)
        except edits.EditError as exc:
            raise _http(
                409,
                "edit_changed",
                f"The trimmed Edit could not be saved: {exc}",
            ) from exc
        _write_receipt(job_id, receipt)

        conflict: dict[str, dict | None] = {"payload": None}

        def mutate(current_job: dict) -> None:
            current_record = app._clip_set_in_job(current_job, set_id)
            current_story = app._story_in_set(current_record, story_id)
            if trim.story_revision(current_story) != int(body.expected_revision):
                conflict["payload"] = _get_payload(
                    current_job, current_record, current_story,
                )
                raise _Conflict(
                    code="revision_mismatch",
                    message=(
                        "This story changed in another window. "
                        "Reload and try again."
                    ),
                )
            try:
                _check_expected(body.aspects, current_job, current_story, set_id, current)
            except HTTPException:
                conflict["payload"] = _get_payload(
                    current_job, current_record, current_story,
                )
                raise _Conflict() from None
            _replace_record(current_job, updated)
            for edit in saved.values():
                edits.set_pointer(current_job, edit)
            _set_tracks(
                current_job,
                app._story_key(set_id, story_id),
                caption_state.get("track_id"),
            )

        try:
            app.update_job(job_id, mutate)
        except _Conflict as exc:
            raise _http(
                409,
                exc.code,
                exc.message,
                conflict["payload"] or current,
            ) from exc
        for edit in saved.values():
            edits.append_history(job_dir, edit)
        return _result(
            new_story, new_revision, saved, caption_state, receipt, invalidated,
        )


@router.post("/api/jobs/{job_id}/clip-sets/{set_id}/stories/{story_id}/trim/undo")
def undo_trim(
    job_id: str,
    set_id: str,
    story_id: str,
    body: TrimUndoBody,
) -> dict:
    app = _app()
    with app.LOCK:
        job, record, story = _resolve(job_id, set_id, story_id)
        current = _get_payload(job, record, story)
        if trim.story_revision(story) != int(body.expected_revision):
            raise _http(
                409,
                "revision_mismatch",
                "This story changed in another window. Reload and try again.",
                current,
            )
        receipt = _load_receipt(job_id, body.undo_token)
        if (
            str(receipt.get("job_id") or "") != str(job_id)
            or str(receipt.get("set_id") or "") != str(set_id)
            or str(receipt.get("story_id") or "") != str(story_id)
        ):
            raise HTTPException(404, "Undo token not found.")
        produced = int(receipt.get("revision") or 0)
        if produced != trim.story_revision(story):
            raise _http(
                409,
                "revision_mismatch",
                "This story changed after the trim. Undo is no longer available.",
                current,
            )
        live = _load_live(job, story, set_id, current)
        after = (receipt.get("after") or {}).get("edits") or {}
        for aspect, edit_id in after.items():
            pointer = (current.get("aspects") or {}).get(aspect) or {}
            if pointer.get("edit_id") != edit_id:
                raise _http(
                    409,
                    "edit_changed",
                    "An Edit changed after the trim. Undo is no longer available.",
                    current,
                )
        for aspect in current.get("aspects") or {}:
            if aspect not in after:
                raise _http(
                    409,
                    "edit_changed",
                    "An Edit was created after the trim. Undo is no longer available.",
                    current,
                )

        before = receipt.get("before") or {}
        old_story = copy.deepcopy(before.get("story") or story)
        restored_story = trim.with_revision(old_story, trim.story_revision(story) + 1)
        old_story_ref = _story_ref(record, restored_story)
        before_edits = before.get("edits") or {}
        restored: dict[str, dict] = {}
        for aspect, target in before_edits.items():
            parent = live.get(aspect) or target
            restored[aspect] = _restore_edit(
                target, parent, old_story_ref, current=current,
            )
        old_track = before.get("caption_track")
        caption_state = _caption_state(job_id, old_track, _clip_hash(restored_story))

        layer_receipt = trim.empty_layer_receipt()
        for edit in live.values():
            _, counts = trim.ripple_graphics(
                edit.get("graphics") or [],
                story.get("clips") or [],
                restored_story.get("clips") or [],
            )
            trim.merge_layer_receipt(layer_receipt, counts)

        receipt_id = trim.new_receipt_id()
        new_receipt = trim.make_receipt(
            receipt_id=receipt_id,
            at=time.time(),
            kind="undo",
            job_id=job_id,
            set_id=set_id,
            story_id=story_id,
            old_story=story,
            new_story=restored_story,
            old_revision=trim.story_revision(story),
            new_revision=trim.story_revision(restored_story),
            layers=layer_receipt,
            captions={key: 0 for key in CAPTION_COUNT_KEYS},
            before_edits=live,
            after_edits={aspect: edit["id"] for aspect, edit in restored.items()},
            before_caption=_story_track_id(job, set_id, story_id),
            after_caption=old_track,
            invalidated_artifacts=_invalidated(
                job_id,
                story_id,
                {aspect: edit["hash"] for aspect, edit in restored.items()},
            ),
        )
        invalidated = list(new_receipt["invalidated_artifacts"])
        job_dir = _job_dir(job_id)
        saved: dict[str, dict] = {}
        try:
            for aspect, edit in restored.items():
                saved[aspect] = edits.save_edit(job_dir, edit)
        except edits.EditError as exc:
            raise _http(
                409,
                "edit_changed",
                f"The restored Edit could not be saved: {exc}",
            ) from exc
        _write_receipt(job_id, new_receipt)

        def mutate(current_job: dict) -> None:
            current_record = app._clip_set_in_job(current_job, set_id)
            current_story = app._story_in_set(current_record, story_id)
            if trim.story_revision(current_story) != int(body.expected_revision):
                raise _Conflict()
            _replace_record(current_job, {
                **current_record,
                "stories": [
                    restored_story
                    if isinstance(item, dict)
                    and str(item.get("id") or "") == str(story_id)
                    else item
                    for item in current_record.get("stories") or []
                ],
            })
            for edit in saved.values():
                edits.set_pointer(current_job, edit)
            _set_tracks(
                current_job,
                app._story_key(set_id, story_id),
                old_track,
            )

        try:
            app.update_job(job_id, mutate)
        except _Conflict as exc:
            raise _http(
                409,
                "revision_mismatch",
                "This story changed in another window. Reload and try again.",
                current,
            ) from exc
        for edit in saved.values():
            edits.append_history(job_dir, edit)
        return _result(
            restored_story,
            trim.story_revision(restored_story),
            saved,
            caption_state,
            new_receipt,
            invalidated,
        )


@router.post("/api/jobs/{job_id}/clip-sets/{set_id}/stories/{story_id}/rebind")
def rebind_story(
    job_id: str,
    set_id: str,
    story_id: str,
    body: TrimRebindBody,
) -> dict:
    app = _app()
    with app.LOCK:
        job, record, story = _resolve(job_id, set_id, story_id)
        current = _get_payload(job, record, story)
        if trim.story_revision(story) != int(body.expected_revision):
            raise _http(
                409,
                "revision_mismatch",
                "This story changed in another window. Reload and try again.",
                current,
            )
        _check_expected(body.aspects, job, story, set_id, current)
        live = _load_live(job, story, set_id, current)
        story_hash = _clip_hash(story)
        stale: list[str] = []
        for aspect, edit in live.items():
            if (edit.get("story_ref") or {}).get("clip_hash") != story_hash:
                stale.append(aspect)
                continue
            track_id = (edit.get("captions") or {}).get("track_id")
            if not track_id:
                continue
            track = caption_engine.load_track(_job_dir(job_id), str(track_id))
            if track is None or (track.clip_hash and track.clip_hash != story_hash):
                stale.append(aspect)
        stale = sorted(set(stale))

        old_track = _old_track_id(job, set_id, story_id, live)
        old_track_stale = False
        if old_track:
            track = caption_engine.load_track(_job_dir(job_id), old_track)
            old_track_stale = (
                track is None
                or bool(track.clip_hash and track.clip_hash != story_hash)
            )
        if old_track_stale or stale:
            caption_state = _rebuild_captions(
                job_id, job, set_id, story, story, old_track,
                dry_run=False, current=current,
            )
        else:
            caption_state = _caption_state(job_id, old_track, story_hash)

        story_ref = _story_ref(record, story)
        new_edits = dict(live)
        for aspect in stale:
            edit = live[aspect]
            captions_layer = dict(edit.get("captions") or {})
            if caption_state.get("track_id"):
                captions_layer["track_id"] = caption_state["track_id"]
            new_edits[aspect] = _new_edit(
                edit,
                story_ref,
                graphics=edit.get("graphics") or [],
                captions=captions_layer,
                current=current,
            )
        new_story = trim.with_revision(story, trim.story_revision(story) + 1)
        new_story["revision"] = trim.story_revision(story) + 1

        receipt_id = trim.new_receipt_id()
        receipt = trim.make_receipt(
            receipt_id=receipt_id,
            at=time.time(),
            kind="rebind",
            job_id=job_id,
            set_id=set_id,
            story_id=story_id,
            old_story=story,
            new_story=new_story,
            old_revision=trim.story_revision(story),
            new_revision=new_story["revision"],
            layers=trim.empty_layer_receipt(),
            captions={key: 0 for key in CAPTION_COUNT_KEYS},
            before_edits=live,
            after_edits={
                aspect: edit["id"]
                for aspect, edit in new_edits.items()
            },
            before_caption=old_track,
            after_caption=caption_state.get("track_id"),
            invalidated_artifacts=_invalidated(
                job_id,
                story_id,
                {aspect: edit["hash"] for aspect, edit in new_edits.items()},
            ),
        )
        invalidated = list(receipt["invalidated_artifacts"])
        job_dir = _job_dir(job_id)
        saved: dict[str, dict] = {}
        try:
            for aspect in stale:
                saved[aspect] = edits.save_edit(job_dir, new_edits[aspect])
        except edits.EditError as exc:
            raise _http(
                409,
                "edit_changed",
                f"The repaired Edit could not be saved: {exc}",
            ) from exc
        _write_receipt(job_id, receipt)

        def mutate(current_job: dict) -> None:
            current_record = app._clip_set_in_job(current_job, set_id)
            current_story = app._story_in_set(current_record, story_id)
            if trim.story_revision(current_story) != int(body.expected_revision):
                raise _Conflict()
            _replace_record(current_job, {
                **current_record,
                "stories": [
                    new_story
                    if isinstance(item, dict)
                    and str(item.get("id") or "") == str(story_id)
                    else item
                    for item in current_record.get("stories") or []
                ],
            })
            for edit in saved.values():
                edits.set_pointer(current_job, edit)
            _set_tracks(
                current_job,
                app._story_key(set_id, story_id),
                caption_state.get("track_id") or old_track,
            )

        try:
            app.update_job(job_id, mutate)
        except _Conflict as exc:
            raise _http(
                409,
                "revision_mismatch",
                "This story changed in another window. Reload and try again.",
                current,
            ) from exc
        for edit in saved.values():
            edits.append_history(job_dir, edit)
        result_edits = {
            aspect: saved.get(aspect, edit)
            for aspect, edit in new_edits.items()
        }
        return _result(
            new_story,
            new_story["revision"],
            result_edits,
            caption_state,
            receipt,
            invalidated,
            stale_aspects=[],
        )
