"""Routes the Classic view adds from now on (lane: ``classic``).

New Classic endpoints go here, not into ``app.py``, so the lanes stop
editing the same file (see ``docs/branching.md``). Existing Classic routes
stay in ``app.py`` until someone has a reason to touch them. Use
``import app`` inside a handler when it needs app helpers; importing at
module level would be circular.
"""

from __future__ import annotations

import math
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import edits
import render

router = APIRouter()


@router.get("/classic")
def classic_page():
    """Serve Classic's own page; Studio-only builds answer 404."""
    import editions

    if "classic" not in editions.views():
        raise HTTPException(404, "Not found")
    import app

    return app.page_response(app.STATIC / "classic" / "index.html")


class ExportCutBody(BaseModel):
    """A Classic export that carries the cut on screen, not just a target."""

    target: int = 30
    order: str = "source"
    hook_scene: int | None = None
    clips: list[dict] | None = None
    caption_track_id: str | None = None


@router.get("/api/classic/packs")
def classic_packs() -> dict:
    """Optional pack status for Classic Setup: on disk or not, no install."""
    import packs

    return {"packs": [{**pack, **_pack_usable(pack.get("id"))} for pack in packs.list_packs()]}


def _pack_usable(pack_id: str | None) -> dict:
    """Whether the engines a pack would add already work without the pack.

    A Mac with Whisper or Demucs installed some other way (pip, Homebrew) can
    transcribe or separate today; Setup must not tell a tester otherwise.
    """
    import audio
    import pipeline

    try:
        if pack_id == "speech":
            ready = any(item.get("cached") for item in pipeline.whisper_models())
            detail = "Whisper is already on this Mac."
        elif pack_id == "voice":
            ready = bool(((audio.engine_status().get("voices") or {}).get("kokoro") or {}).get("available"))
            detail = "Kokoro voices are already on this Mac."
        elif pack_id == "separation":
            engines = (audio.engine_status().get("separation") or {}).values()
            ready = any(bool((item or {}).get("available")) for item in engines)
            detail = "Voice separation is already on this Mac."
        else:
            return {"usable": False}
    except Exception:  # noqa: BLE001 - status only; never fail Setup over it
        return {"usable": False}
    return {"usable": ready, "usable_detail": detail if ready else ""}


@router.post("/api/classic/jobs/{job_id}/export/{kind}")
def export_edited_cut(job_id: str, kind: str, body: ExportCutBody):
    """Export SRT, VTT, EDL or XML from the edited clips the browser sends.

    The legacy GET takes only target/order/hook, so an edited cut or a loaded
    variant exported the automatic plan. This route reuses the same export
    builder with ``_custom_plan``.
    """
    import app

    if kind not in {"srt", "vtt", "edl", "xml"}:
        raise HTTPException(404, "Unknown export format.")
    job = app.load_job(job_id)
    target = app._valid_target(int(body.target))
    plan_body = app.PlanBody(
        target=target,
        hook_scene=body.hook_scene,
        order=body.order,
        clips=body.clips,
    )
    plan = app._plan_for_body(job, target, plan_body)
    return app._export_plan_response(
        job_id, job, plan, kind, target, body.caption_track_id,
    )


# ---------------------------------------------------------------- text and effects
#
# Classic has no story Edit document. The card stores Studio-shaped layers per
# cut in the job, then builds a throwaway Edit for the render. The Edit shape,
# hashes and validators are `edits` and `overlays`; Classic never invents a
# second layer format.

CLASSIC_EDIT_ASPECTS = ("9:16", "4:5")
CLASSIC_TEXT_VERSION = 1
MAX_CLASSIC_OVERLAYS = 12
MAX_CLASSIC_EFFECTS = 6
MAX_CLASSIC_CUTS = 40

# Classic offers three positions; each maps to the Studio anchor and text
# kind whose default box and margins already fit that edge.
CLASSIC_TEXT_POSITIONS = {
    "top": ("top-center", "hook"),
    "center": ("center", "title"),
    "bottom": ("bottom-center", "lower_third"),
}
CLASSIC_ANCHOR_POSITIONS = {
    "top-center": "top",
    "center": "center",
    "bottom-center": "bottom",
}
CLASSIC_EFFECT_KINDS = ("punch_in", "shake", "circle")
CLASSIC_MOTION_DEFAULTS = {
    "punch_in": {"amount": 0.08, "ramp": 0.4},
    "shake": {"amount": 0.010, "ramp": 0.2},
}
CLASSIC_DEFAULT_EFFECT_SECONDS = 1.2
CLASSIC_TEXT_BOX = {
    "hook": {"w": 0.76, "h": 0.16},
    "title": {"w": 0.76, "h": 0.14},
    "lower_third": {"w": 0.64, "h": 0.14},
}


class ClassicTextError(ValueError):
    """A Classic text/effect payload cannot be normalized."""

    status_code = 422


class ClassicTextBody(BaseModel):
    clips: list[dict]
    overlays: list[dict] = []
    effects: list[dict] = []


class ClassicTextLookupBody(BaseModel):
    clips: list[dict]


def _classic_clips(value) -> list[dict]:
    """Keep only the clip windows the cut hash and captions understand."""
    if not isinstance(value, (list, tuple)) or not value:
        raise ClassicTextError("The cut needs at least one clip.")
    clips: list[dict] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise ClassicTextError(f"Clip {index + 1} must be an object.")
        try:
            start = float(raw.get("start") or 0.0)
            end = raw.get("end")
            end = float(
                end if end is not None
                else start + float(raw.get("dur") or raw.get("duration") or 0.0)
            )
        except (TypeError, ValueError) as exc:
            raise ClassicTextError(f"Clip {index + 1} has invalid times.") from exc
        if not math.isfinite(start) or not math.isfinite(end) or end <= start:
            raise ClassicTextError(f"Clip {index + 1} has invalid times.")
        clips.append({
            "scene": raw.get("scene"),
            "role": str(raw.get("role") or "beat"),
            "start": round(start, 3),
            "end": round(end, 3),
            "dur": round(end - start, 3),
        })
    return clips


def _classic_total(clips: list[dict]) -> float:
    total = sum(
        max(0.0, float(clip.get("end") or 0.0) - float(clip.get("start") or 0.0))
        for clip in clips
    )
    return round(total, 3)


def _classic_time(value, label: str, total: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ClassicTextError(f"{label} must be a number.") from exc
    if not math.isfinite(number):
        raise ClassicTextError(f"{label} must be a finite number.")
    if number < -1e-6:
        raise ClassicTextError(f"{label} cannot be negative.")
    # The card reads the plan's rounded total; the clip sum can differ by a
    # few milliseconds. Allow that much and clamp to the cut.
    if number > total + 0.05:
        raise ClassicTextError(
            f"{label} is after the cut ends ({total:.1f}s)."
        )
    return round(min(max(0.0, number), total), 3)


def _classic_anchor(value) -> tuple[str, str]:
    raw = str(value or "").strip().lower().replace("_", "-").replace(" ", "-")
    if raw in CLASSIC_TEXT_POSITIONS:
        return CLASSIC_TEXT_POSITIONS[raw]
    if raw in CLASSIC_ANCHOR_POSITIONS:
        return raw, CLASSIC_TEXT_POSITIONS[CLASSIC_ANCHOR_POSITIONS[raw]][1]
    raise ClassicTextError("Text position must be top, center or bottom.")


def _classic_overlay_layers(value, total: float) -> list[dict]:
    if not isinstance(value, (list, tuple)):
        raise ClassicTextError("overlays must be a list.")
    if len(value) > MAX_CLASSIC_OVERLAYS:
        raise ClassicTextError(
            f"A cut supports at most {MAX_CLASSIC_OVERLAYS} text overlays."
        )
    layers: list[dict] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise ClassicTextError(f"Text overlay {index + 1} must be an object.")
        text = " ".join(str(raw.get("text") or "").split())
        if not text:
            raise ClassicTextError(f"Text overlay {index + 1} needs words.")
        anchor, kind = _classic_anchor(raw.get("anchor") or raw.get("position"))
        start = _classic_time(
            raw.get("start", 0.0), f"Text overlay {index + 1} start", total,
        )
        end = _classic_time(
            raw.get("end"), f"Text overlay {index + 1} end", total,
        )
        if end <= start + 0.05:
            raise ClassicTextError(
                f"Text overlay {index + 1} end must be later than its start."
            )
        box = raw.get("box")
        if not isinstance(box, dict):
            box = dict(CLASSIC_TEXT_BOX[kind])
        layer = {
            "id": raw.get("id") or f"tx{index + 1:02d}",
            "type": "text",
            "kind": kind,
            "text": text,
            "start": start,
            "end": end,
            "anchor": anchor,
            "box": box,
            "z": raw.get("z", 10 + index),
            "style": raw.get("style") if isinstance(raw.get("style"), dict) else {},
            "safe_zone": raw.get("safe_zone", True),
            "opacity": raw.get("opacity", 1.0),
        }
        layers.append(layer)
    return layers


def _classic_effect_layers(
    value, total: float,
) -> tuple[list[dict], list[dict]]:
    if not isinstance(value, (list, tuple)):
        raise ClassicTextError("effects must be a list.")
    if len(value) > MAX_CLASSIC_EFFECTS:
        raise ClassicTextError(
            f"A cut supports at most {MAX_CLASSIC_EFFECTS} effects."
        )
    motion: list[dict] = []
    graphics: list[dict] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise ClassicTextError(f"Effect {index + 1} must be an object.")
        kind = str(raw.get("kind") or "").strip().lower().replace("-", "_")
        if kind not in CLASSIC_EFFECT_KINDS:
            raise ClassicTextError(
                "Effect kind must be one of: " + ", ".join(CLASSIC_EFFECT_KINDS) + "."
            )
        start = _classic_time(
            raw.get("start", 0.0), f"Effect {index + 1} start", total,
        )
        if raw.get("end") is not None:
            end = _classic_time(raw.get("end"), f"Effect {index + 1} end", total)
        else:
            try:
                seconds = float(raw.get("duration") or CLASSIC_DEFAULT_EFFECT_SECONDS)
            except (TypeError, ValueError) as exc:
                raise ClassicTextError(
                    f"Effect {index + 1} duration must be a number."
                ) from exc
            if not math.isfinite(seconds) or seconds <= 0:
                raise ClassicTextError(
                    f"Effect {index + 1} duration must be a positive number."
                )
            end = round(min(total, start + seconds), 3)
        if end <= start + 0.05:
            raise ClassicTextError(
                f"Effect {index + 1} end must be later than its start."
            )
        if kind == "circle":
            graphics.append({
                "id": raw.get("id") or f"fx{index + 1:02d}",
                "type": "fx",
                "kind": "circle",
                "start": start,
                "end": end,
                "anchor": raw.get("anchor") or "center",
                "box": raw.get("box") if isinstance(raw.get("box"), dict) else {
                    "w": 0.3, "h": 0.3,
                },
                "z": raw.get("z", 20 + index),
                "color": raw.get("color") or "#ffffff",
                "thickness": raw.get("thickness") or 6,
                "opacity": raw.get("opacity", 1.0),
            })
        else:
            defaults = CLASSIC_MOTION_DEFAULTS[kind]
            motion.append({
                "id": raw.get("id") or f"mo{index + 1:02d}",
                "kind": kind,
                "start": start,
                "end": end,
                "amount": raw.get("amount", defaults["amount"]),
                "ramp": raw.get("ramp", defaults["ramp"]),
                "seed": raw.get("seed", 0),
            })
    return motion, graphics


def normalize_classic_layers(
    overlays_value, effects_value, total: float,
) -> dict:
    """Normalize Classic layers through the Studio Edit validators."""
    graphics_raw = _classic_overlay_layers(overlays_value, total)
    motion_raw, effect_graphics = _classic_effect_layers(effects_value, total)
    try:
        graphics = edits.normalize_graphics(graphics_raw + effect_graphics)
        motion = edits.normalize_motion(motion_raw)
    except edits.EditError as exc:
        raise ClassicTextError(str(exc)) from exc
    return {
        "overlays": [layer for layer in graphics if layer["type"] == "text"],
        "graphics": [layer for layer in graphics if layer["type"] == "fx"],
        "motion": motion,
    }


def _classic_effects_payload(layers: dict) -> list[dict]:
    effects = [
        {
            "id": layer["id"],
            "kind": layer["kind"],
            "start": layer["start"],
            "end": layer["end"],
            "duration": round(float(layer["end"]) - float(layer["start"]), 3),
        }
        for layer in layers.get("motion") or []
    ] + [
        {
            "id": layer["id"],
            "kind": layer["kind"],
            "start": layer["start"],
            "end": layer["end"],
            "duration": round(float(layer["end"]) - float(layer["start"]), 3),
        }
        for layer in layers.get("graphics") or []
    ]
    effects.sort(key=lambda item: (
        float(item["start"]), float(item["end"]), str(item["id"]),
    ))
    return effects


def _classic_cut_payload(row) -> dict | None:
    if not isinstance(row, dict):
        return None
    layers = {
        "overlays": [dict(layer) for layer in row.get("overlays") or []
                     if isinstance(layer, dict)],
        "graphics": [dict(layer) for layer in row.get("graphics") or []
                     if isinstance(layer, dict)],
        "motion": [dict(layer) for layer in row.get("motion") or []
                   if isinstance(layer, dict)],
    }
    return {
        "clips_hash": row.get("clips_hash"),
        "clip_count": int(row.get("clip_count") or 0),
        "duration": float(row.get("duration") or 0.0),
        "overlays": layers["overlays"],
        "effects": _classic_effects_payload(layers),
        "updated": row.get("updated"),
    }


def _classic_cuts(job: dict) -> dict:
    store = job.get("classic_text")
    cuts = store.get("cuts") if isinstance(store, dict) else None
    return cuts if isinstance(cuts, dict) else {}


def store_classic_cut(
    job_id: str, clips: list[dict], layers: dict,
) -> dict:
    """Persist normalized layers under this cut's clip snapshot hash."""
    import app

    total = _classic_total(clips)
    row = {
        "clips_hash": edits.clip_snapshot_hash(clips),
        "clip_count": len(clips),
        "duration": total,
        "overlays": list(layers.get("overlays") or []),
        "graphics": list(layers.get("graphics") or []),
        "motion": list(layers.get("motion") or []),
        "updated": round(time.time(), 3),
    }

    def mutate(job: dict) -> None:
        cuts = dict(_classic_cuts(job))
        cuts[row["clips_hash"]] = row
        if len(cuts) > MAX_CLASSIC_CUTS:
            keep = sorted(
                cuts.items(),
                key=lambda item: float((item[1] or {}).get("updated") or 0.0),
                reverse=True,
            )[:MAX_CLASSIC_CUTS]
            cuts = dict(keep)
        job["classic_text"] = {
            "version": CLASSIC_TEXT_VERSION,
            "cuts": cuts,
        }

    app.update_job(job_id, mutate)
    return row


def _build_classic_edit(
    clips: list[dict],
    aspect: str,
    layers: dict,
    caption_track=None,
) -> dict:
    """Build the throwaway Edit the renderer understands."""
    total = _classic_total(clips)
    clip_hash = edits.clip_snapshot_hash(clips)
    captions = {
        "enabled": caption_track is not None,
        "track_id": caption_track.id if caption_track is not None else None,
    }
    try:
        return edits.build_edit(
            story_ref={
                "set_id": "classic",
                "story_id": f"cut_{clip_hash}",
                "clip_hash": clip_hash,
                "title": f"Classic {max(1, int(round(total)))}s cut",
                "duration": total,
                "clip_count": len(clips),
            },
            aspect=aspect,
            motion=layers.get("motion") or [],
            graphics=(layers.get("overlays") or []) + (layers.get("graphics") or []),
            captions=captions,
            audio=None,
        )
    except edits.EditError as exc:
        raise HTTPException(422, str(exc)) from exc


def prepare_classic_render(
    job_id: str,
    job: dict,
    plan: dict,
    aspect: str,
    payload,
    *,
    captions: bool,
    margin: float | None,
    audio_plan: dict | None,
) -> tuple[dict | None, object | None]:
    """Build the Edit and caption track for a Classic render, or ``(None, None)``.

    The caption track is built against the same frame-rounded clips the
    renderer uses, so the Edit's ``captions.track_id`` and the track handed to
    ``_queue_render`` describe the same cues.
    """
    if not isinstance(payload, dict):
        raise HTTPException(400, "edit must be an object of overlays and effects.")
    if aspect not in CLASSIC_EDIT_ASPECTS:
        raise HTTPException(
            422,
            "Text overlays and effects render on 9:16 and 4:5 only. "
            "Switch the shape or clear them.",
        )
    clips = _classic_clips(plan.get("clips"))
    total = _classic_total(clips)
    try:
        layers = normalize_classic_layers(
            payload.get("overlays") or [],
            payload.get("effects") or [],
            total,
        )
    except ClassicTextError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    if not (layers["overlays"] or layers["graphics"] or layers["motion"]):
        return None, None
    track = None
    if captions:
        import app

        prepared = render.prepare_render(plan, job.get("source") or {}, audio_plan)
        track_plan = {
            **plan,
            "clips": prepared["clips"],
            "total": prepared["total"],
        }
        track = app._default_caption_track(
            job_id, job, track_plan, margin=margin,
        )
    edit = _build_classic_edit(clips, aspect, layers, track)
    store_classic_cut(job_id, clips, layers)
    return edit, track


@router.post("/api/classic/jobs/{job_id}/text")
def classic_text_lookup(job_id: str, body: ClassicTextLookupBody) -> dict:
    """Return the saved text and effects for the cut the browser holds."""
    import app

    job = app.load_job(job_id)
    try:
        clips = _classic_clips(body.clips)
    except ClassicTextError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    key = edits.clip_snapshot_hash(clips)
    row = _classic_cuts(job).get(key)
    return {
        "cut": _classic_cut_payload(row),
        "aspects": list(CLASSIC_EDIT_ASPECTS),
    }


@router.put("/api/classic/jobs/{job_id}/text")
def classic_text_save(job_id: str, body: ClassicTextBody) -> dict:
    """Save Studio-shaped text layers and effects for this cut."""
    import app

    app.load_job(job_id)
    try:
        clips = _classic_clips(body.clips)
        total = _classic_total(clips)
        layers = normalize_classic_layers(body.overlays, body.effects, total)
    except ClassicTextError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    row = store_classic_cut(job_id, clips, layers)
    return {
        "cut": _classic_cut_payload(row),
        "aspects": list(CLASSIC_EDIT_ASPECTS),
    }


# ---------------------------------------------------------------- translation warm-up

TRANSLATION_BATCH = 20
TRANSLATION_RUNS: dict[tuple[str, str], dict] = {}
TRANSLATION_LOCK = __import__("threading").Lock()


class TranslateBody(BaseModel):
    target: str
    provider: str = "auto"


def _translation_texts(job_id: str) -> list[str]:
    import pipeline

    segments = pipeline.read_transcript(_translation_job_dir(job_id)) or []
    return [
        str(segment.get("text") or "").strip()
        for segment in segments
        if str(segment.get("text") or "").strip()
    ]


def _translation_job_dir(job_id: str):
    import app

    return app._job_dir(job_id)


def _translation_source(job_id: str) -> str:
    import app

    job = app.load_job(job_id)
    return str(
        ((job.get("analysis") or {}).get("engine") or {}).get("transcript_language")
        or "en"
    ).split("-")[0]


def _translation_hash(texts: list[str]) -> str:
    import hashlib

    return hashlib.sha1("\n".join(texts).encode("utf-8")).hexdigest()[:20]


def _translation_flag(job_id: str, target: str):
    return _translation_job_dir(job_id) / "translations" / f"{target}.json"


def _translation_state(job_id: str, target: str) -> dict:
    import json

    target = str(target or "").split("-")[0]
    source = _translation_source(job_id)
    texts = _translation_texts(job_id)
    total = len(texts)
    batches = (total + TRANSLATION_BATCH - 1) // TRANSLATION_BATCH
    key = (job_id, target)
    with TRANSLATION_LOCK:
        running = dict(TRANSLATION_RUNS.get(key) or {})
    if running:
        return running
    if not target or target == source:
        return {
            "job_id": job_id, "target": target, "status": "ready",
            "done": 0, "total": 0, "batch": 0, "batches": 0,
            "provider": "none", "error": None,
        }
    path = _translation_flag(job_id, target)
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = None
    if saved and saved.get("source_hash") == _translation_hash(texts):
        return {**saved, "status": "ready", "done": total, "total": total,
                "batch": batches, "batches": batches}
    return {
        "job_id": job_id, "target": target, "status": "idle",
        "done": 0, "total": total, "batch": 0, "batches": batches,
        "provider": "auto", "error": None,
    }


def _set_run(job_id: str, target: str, **values) -> dict:
    key = (job_id, target)
    with TRANSLATION_LOCK:
        current = dict(TRANSLATION_RUNS.get(key) or {})
        current.update(values)
        TRANSLATION_RUNS[key] = current
        return dict(current)


def _translation_worker(
    job_id: str, target: str, provider: str, source: str, texts: list[str],
) -> None:
    import json
    import time
    import uuid

    started = time.time()
    total = len(texts)
    batches = (total + TRANSLATION_BATCH - 1) // TRANSLATION_BATCH
    for index in range(batches):
        chunk = texts[index * TRANSLATION_BATCH:(index + 1) * TRANSLATION_BATCH]
        try:
            import audio

            audio.translate_lines(chunk, source, target, provider or "auto")
        except Exception as exc:  # noqa: BLE001 - status carries the reason
            _set_run(
                job_id, target, status="failed", done=index * TRANSLATION_BATCH,
                batch=index, batches=batches, error=str(exc)[:400],
                latency_ms=round((time.time() - started) * 1000),
            )
            return
        _set_run(
            job_id, target, status="running",
            done=min((index + 1) * TRANSLATION_BATCH, total),
            batch=index + 1, batches=batches, error=None,
        )
    finished = {
        "job_id": job_id, "target": target, "status": "ready",
        "done": total, "total": total, "batch": batches, "batches": batches,
        "provider": provider or "auto", "error": None,
        "source": source, "source_hash": _translation_hash(texts),
        "lines": total, "completed_at": round(time.time(), 3),
        "latency_ms": round((time.time() - started) * 1000),
    }
    try:
        path = _translation_flag(job_id, target)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(finished, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass
    _set_run(
        job_id, target,
        **{key: value for key, value in finished.items() if key not in ("job_id", "target")},
    )
    try:
        import app

        app._history_append(job_id, {
            "id": uuid.uuid4().hex[:12],
            "type": "translation",
            "created": round(time.time(), 3),
            "status": "ok",
            "target": 0,
            "style": None,
            "source_lang": source,
            "target_lang": target,
            "provider": provider or "auto",
            "fallback": False,
            "tried": [],
            "model": None,
            "latency_ms": finished["latency_ms"],
            "usage": {},
            "warning": None,
            "error": None,
            "path": None,
            "script_id": None,
            "clip_hash": None,
        })
    except Exception:  # noqa: BLE001 - history is best effort
        pass


@router.post("/api/classic/jobs/{job_id}/translate")
def classic_translate(job_id: str, body: TranslateBody) -> dict:
    """Translate the full transcript once, in 20-line batches, in the background."""
    import threading

    target = str(body.target or "").split("-")[0]
    if not target:
        raise HTTPException(400, "Choose a language first.")
    source = _translation_source(job_id)
    if target == source:
        return _translation_state(job_id, target)
    existing = _translation_state(job_id, target)
    if existing.get("status") == "ready":
        return existing
    texts = _translation_texts(job_id)
    if not texts:
        raise HTTPException(409, "This video has no transcript to translate.")
    key = (job_id, target)
    with TRANSLATION_LOCK:
        if key in TRANSLATION_RUNS and TRANSLATION_RUNS[key].get("status") == "running":
            return dict(TRANSLATION_RUNS[key])
        TRANSLATION_RUNS[key] = {
            "job_id": job_id, "target": target, "status": "running",
            "done": 0, "total": len(texts), "batch": 0,
            "batches": (len(texts) + TRANSLATION_BATCH - 1) // TRANSLATION_BATCH,
            "provider": body.provider or "auto", "error": None,
        }
    threading.Thread(
        target=_translation_worker,
        args=(job_id, target, body.provider or "auto", source, texts),
        name=f"translate-{job_id}-{target}",
        daemon=True,
    ).start()
    return _translation_state(job_id, target)


@router.get("/api/classic/jobs/{job_id}/translate/status")
def classic_translate_status(job_id: str, target: str = "") -> dict:
    return _translation_state(job_id, target)
