"""Routes the Classic view adds from now on (lane: ``classic``).

New Classic endpoints go here, not into ``app.py``, so the lanes stop
editing the same file (see ``docs/shared/branching.md``). Existing Classic routes
stay in ``app.py`` until someone has a reason to touch them. Use
``import app`` inside a handler when it needs app helpers; importing at
module level would be circular.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

import detect
import edits
import render

router = APIRouter()

# Sound previews are short, cached and local. A provider call is made only
# when the generated-music cache has no file for this prompt, and the request
# is hard-bounded by both the preview length and the provider timeout.
PREVIEW_SECONDS = 12.0
PREVIEW_MAX_SECONDS = 20.0
PREVIEW_TIMEOUT = 90
PREVIEW_LOCK = threading.Lock()
# One lock per preview file: a 90 s AI music call must not hold up a local BGM
# preview, or a different prompt. PREVIEW_LOCK only guards this table.
PREVIEW_LOCKS: dict[str, threading.Lock] = {}


def _preview_lock(target: Path) -> threading.Lock:
    with PREVIEW_LOCK:
        return PREVIEW_LOCKS.setdefault(target.name, threading.Lock())


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
# 2: Clean boxes are source-normalized and their ranges are cut time, which the
# server translates to the clips' source time. Version 1 boxes were drawn in
# frame space, so they are dropped with a count instead of being reinterpreted.
CLASSIC_TEXT_VERSION = 2
MAX_CLASSIC_OVERLAYS = 12
MAX_CLASSIC_EFFECTS = 6
MAX_CLASSIC_CUTS = 40
# Clean boxes are the C1/C2 layer: a rectangle on the source frame, optionally
# limited to some time ranges (cut time, translated per clip at build time).
# The method picks the Edit kind, so Classic never invents a second clean
# format.
CLASSIC_CLEAN_METHODS = ("blur", "crop", "fill")
CLASSIC_CLEAN_KINDS = {
    "blur": "blur",
    "crop": "crop_guard",
    "fill": "fill",
}
MAX_CLASSIC_CLEAN = 24
CLASSIC_CLEAN_DEFAULT_COLOR = "#0b0d12"
# A Classic box's `method` is what the founder picked (blur, crop or fill); a fill box also carries `engine` (which model runs). `edits` calls the
# engine "method" inside the Edit, so the two names must not be confused.
# Classic fills with LaMa only. A box saved earlier with a retired engine still
# opens and renders, as LaMa.
CLASSIC_FILL_ENGINES = ("lama",)
RETIRED_FILL_ENGINES = ("sttn",)
FILL_MODELS = {"LaMa": "lama_fp32.onnx"}
FILL_ENGINE_MODEL = {"lama": "LaMa"}
FILL_RUNTIME = {"lama": "onnxruntime"}
FILL_LICENSES = {
    "LaMa": "Apache-2.0 · github.com/Carve/LaMa-ONNX",
}
FILL_LOCK = threading.Lock()
FILL_LOCKS: dict[str, threading.Lock] = {}
FRAME_LOCK = threading.Lock()
FRAME_LOCKS: dict[str, threading.Lock] = {}

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
    clean: list[dict] = []


class ClassicFrameBody(BaseModel):
    """The cut on screen, including unsaved boxes, at one time."""

    model_config = {"extra": "forbid"}

    clips: list[dict]
    clean: list[dict] = []
    overlays: list[dict] = []
    effects: list[dict] = []
    t: float = 0.0
    aspect: str = "9:16"
    quality: str = "draft"


class ClassicFillBody(BaseModel):
    model_config = {"extra": "forbid"}

    clips: list[dict]
    clean: list[dict] = []
    overlays: list[dict] = []
    effects: list[dict] = []
    t: float = 0.0
    aspect: str = "9:16"


class ClassicFillEstimateBody(BaseModel):
    model_config = {"extra": "forbid"}

    clips: list[dict]
    clean: list[dict] = []
    aspect: str = "9:16"


class ClassicCleanLayersBody(BaseModel):
    model_config = {"extra": "forbid"}

    clips: list[dict]


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
    overlays_value, effects_value, total: float, clean_value=None,
    *, require_ready_fill: bool = True,
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
        "clean": normalize_classic_clean(
            clean_value, total, require_ready=require_ready_fill,
        ),
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


def _classic_store_version(job: dict) -> int:
    store = job.get("classic_text")
    try:
        return int((store or {}).get("version") or 0)
    except (AttributeError, TypeError, ValueError):
        return 0


def _classic_cut_payload(row, version: int = CLASSIC_TEXT_VERSION) -> dict | None:
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
    clean = [dict(item) for item in row.get("clean") or []
             if isinstance(item, dict)]
    reset = 0
    if clean and version < 2:
        reset = len(clean)
        clean = []
    return {
        "clips_hash": row.get("clips_hash"),
        "clip_count": int(row.get("clip_count") or 0),
        "duration": float(row.get("duration") or 0.0),
        "overlays": layers["overlays"],
        "effects": _classic_effects_payload(layers),
        "clean": clean,
        # Boxes drawn before version 2 used frame coordinates; they are reported
        # and dropped rather than drawn somewhere the founder never put them.
        "clean_reset": reset,
        "updated": row.get("updated"),
    }


def _classic_cuts(job: dict) -> dict:
    store = job.get("classic_text")
    cuts = store.get("cuts") if isinstance(store, dict) else None
    return cuts if isinstance(cuts, dict) else {}


def _classic_windows(clips: list[dict]) -> list[tuple[float, float, float, float]]:
    """Each clip's place in the cut: (cut_start, cut_end, source_start, source_end)."""
    windows: list[tuple[float, float, float, float]] = []
    cursor = 0.0
    for clip in clips:
        start = float(clip.get("start") or 0.0)
        end = float(clip.get("end") or start)
        span = max(0.0, end - start)
        windows.append((cursor, cursor + span, start, end))
        cursor += span
    return windows


def _cut_ranges_to_source(ranges, clips: list[dict]) -> list[dict]:
    """Translate cut-time ranges into the source time the renderer compares.

    Classic stores ranges in cut time because that is what the editor scrubs,
    but `compose_render._active_window` compares them with `clip["start"]` and
    `clip["end"]`, which are source times. A range that covers several clips
    becomes one source range per clip, and the part of a clip the cut does not
    carry never produces a range at all.
    """
    items = [item for item in (ranges or []) if isinstance(item, dict)]
    if not items:
        return []
    windows = _classic_windows(clips)
    out: list[dict] = []
    for item in items:
        try:
            low = float(item.get("start") or 0.0)
            high = float(item.get("end") or 0.0)
        except (TypeError, ValueError):
            continue
        for cut_start, cut_end, source_start, _source_end in windows:
            from_cut = max(low, cut_start)
            to_cut = min(high, cut_end)
            if to_cut - from_cut <= 1e-6:
                continue
            out.append({
                "start": round(source_start + (from_cut - cut_start), 3),
                "end": round(source_start + (to_cut - cut_start), 3),
            })
    out.sort(key=lambda entry: (entry["start"], entry["end"]))
    merged: list[dict] = []
    for entry in out:
        if merged and entry["start"] <= merged[-1]["end"] + 1e-6:
            merged[-1]["end"] = max(merged[-1]["end"], entry["end"])
        else:
            merged.append(dict(entry))
    if len(merged) > 64:
        raise ClassicTextError(
            "This box covers too many separate moments. Trim it to fewer ranges."
        )
    return merged


def _classic_clean_edit(layers: list[dict], clips: list[dict]) -> list[dict]:
    """Map Classic boxes onto the Edit's clean kinds, in source space.

    Boxes are already source-normalized; ranges are cut time and become source
    ranges here, where the clips are known.
    """
    edit_layers: list[dict] = []
    for layer in layers:
        if layer.get("hidden"):
            continue
        method = str(layer.get("method") or "blur")
        kind = CLASSIC_CLEAN_KINDS.get(method, "blur")
        entry = {
            "id": layer["id"],
            "kind": kind,
            **({"method": str(layer.get("engine") or "lama")} if kind == "fill" else {}),
            "box": dict(layer["box"]),
            "ranges": _cut_ranges_to_source(layer.get("ranges"), clips),
            "label": str(layer.get("label") or ""),
            "color": layer.get("color") or CLASSIC_CLEAN_DEFAULT_COLOR,
            "opacity": layer.get("opacity", 1.0),
            "radius": layer.get("radius", 24),
            "z": layer.get("z", 0),
        }
        for key in ("tracklet_id", "tracklet_kind", "mask", "text_key"):
            if layer.get(key):
                entry[key] = layer[key]
        edit_layers.append(entry)
    return edit_layers


def normalize_classic_clean(
    value, total: float, *, require_ready: bool = True,
) -> list[dict]:
    """Validate Clean boxes with the Edit validator, then keep Classic fields.

    ``edits.normalize_clean`` owns the box, range, colour and kind rules, so a
    Classic box can never be a shape the renderer does not understand. Classic
    adds only what the editor needs to draw and name it: the method the founder
    picked, the scan tracklet it came from, and an eye toggle.

    ``require_ready=False`` is for the frame preview: a cut saved on a Mac with
    the model pack must still show its box, with its range, on a Mac without
    it. The box is drawn, never filled, so the picture does not lie; the save
    and the render stay strict and say which engine is missing.
    """
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise ClassicTextError("clean must be a list of boxes.")
    if len(value) > MAX_CLASSIC_CLEAN:
        raise ClassicTextError(
            f"A cut supports at most {MAX_CLASSIC_CLEAN} Clean boxes."
        )
    raw_layers: list[dict] = []
    extras: dict[str, dict] = {}
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise ClassicTextError(f"clean[{index}] must be an object.")
        method = str(raw.get("method") or "blur").strip().lower()
        if method not in CLASSIC_CLEAN_METHODS:
            raise ClassicTextError(
                "A Clean box method must be blur, crop or AI fill."
            )
        engine = ""
        if method == "fill":
            engine = str(raw.get("engine") or "lama").strip().lower()
            if engine in RETIRED_FILL_ENGINES:
                engine = "lama"
            if engine not in CLASSIC_FILL_ENGINES:
                raise ClassicTextError("An AI fill box engine must be LaMa.")
            status = classic_fill_status() if require_ready else {}
            ready = (status.get("engines") or {}).get(engine) or {}
            if require_ready and not ready.get("ready"):
                raise ClassicTextError(
                    ready.get("reason")
                    or "AI fill needs its model pack. Use Blur or Crop."
                )
        layer_id = str(raw.get("id") or f"cl{index + 1:02d}").strip()
        # `kind` on a Classic box is the label the panel shows ("subtitle",
        # "manual"). Only a check kind may reach the Edit validator.
        tracklet_kind = raw.get("tracklet_kind")
        if not tracklet_kind:
            candidate = str(raw.get("kind") or "").strip().lower()
            tracklet_kind = candidate if candidate in edits.TRACKLET_KINDS else None
        raw_layers.append({
            "id": layer_id,
            "kind": CLASSIC_CLEAN_KINDS[method],
            # `edits` calls the engine "method"; Classic's own method is stored
            # beside it after validation, which would overwrite this key.
            **({"method": engine} if method == "fill" else {}),
            "box": raw.get("box"),
            "ranges": raw.get("ranges"),
            "label": raw.get("label"),
            "color": raw.get("color") or CLASSIC_CLEAN_DEFAULT_COLOR,
            "opacity": raw.get("opacity", 1.0),
            "radius": raw.get("radius", 24),
            "z": raw.get("z", index),
            "tracklet_id": raw.get("tracklet_id"),
            "tracklet_kind": tracklet_kind,
            "mask": raw.get("mask"),
            "text_key": raw.get("text_key"),
        })
        extras[layer_id] = {
            "method": method,
            "engine": engine,
            "hidden": bool(raw.get("hidden")),
            "source": "scan" if raw.get("source") == "scan" else "manual",
            "tracklet_kind": tracklet_kind,
        }
    try:
        normalized = edits.normalize_clean(raw_layers)
    except edits.EditError as exc:
        raise ClassicTextError(str(exc)) from exc
    total = max(0.0, float(total or 0.0))
    layers: list[dict] = []
    for layer in normalized:
        extra = extras.get(layer["id"], {})
        ranges = layer.get("ranges") or []
        if total > 0.0:
            ranges = [
                item for item in ranges
                if float(item.get("start") or 0.0) < total - 1e-6
            ]
        layers.append({
            **layer,
            "ranges": ranges,
            "method": extra.get("method", "blur"),
            "engine": extra.get("engine", ""),
            "hidden": bool(extra.get("hidden")),
            "source": extra.get("source", "manual"),
            "kind": str(extra.get("tracklet_kind") or layer.get("tracklet_kind") or "manual"),
        })
    return layers


def _classic_runtime_installed(engine: str) -> tuple[bool, str]:
    """A model file without its runtime package is not ready."""
    import importlib.util

    package = FILL_RUNTIME.get(engine, "")
    if not package:
        return True, ""
    try:
        found = importlib.util.find_spec(package) is not None
    except (ImportError, ValueError):
        found = False
    if found:
        return True, ""
    return False, (
        f"AI fill with {engine.upper()} needs the {package} package on this Mac."
    )


def classic_fill_status() -> dict:
    """Whether LaMa, the AI-fill engine, is usable, and why not when it is not.

    Ready means the model file *and* its runtime package are both present.
    """
    import app

    override = (os.environ.get("VIBECUT_FILL_MODELS") or "").strip()
    directory = Path(override) if override else Path(app.DATA) / "models" / "fill"
    engines: dict[str, dict] = {}
    files = []
    missing = []
    for engine in CLASSIC_FILL_ENGINES:
        name = FILL_ENGINE_MODEL[engine]
        filename = FILL_MODELS[name]
        path = directory / filename
        installed = path.is_file() and path.stat().st_size > 0
        if not installed:
            missing.append(name)
        runtime_ok, runtime_reason = _classic_runtime_installed(engine)
        reason = ""
        if not installed:
            reason = (
                f"AI fill with {name} is missing {filename}. "
                f"Put it in {directory}."
            )
        elif not runtime_ok:
            reason = runtime_reason
        engines[engine] = {
            "id": engine,
            "label": name,
            "ready": installed and runtime_ok,
            "reason": reason,
            "model": installed,
            "runtime": FILL_RUNTIME.get(engine, ""),
            "runtime_installed": runtime_ok,
        }
        files.append({
            "name": name,
            "engine": engine,
            "file": filename,
            "license": FILL_LICENSES.get(name, ""),
            "installed": installed,
            "bytes": path.stat().st_size if path.is_file() else 0,
        })
    default = next(
        (engine for engine in CLASSIC_FILL_ENGINES if engines[engine]["ready"]),
        None,
    )
    ready_names = [FILL_ENGINE_MODEL[item] for item in CLASSIC_FILL_ENGINES
                   if engines[item]["ready"]]
    return {
        "available": default is not None,
        "path": str(directory),
        "missing": missing,
        "files": files,
        "engines": engines,
        "default": default,
        # The preview and the render use the same engine.
        "preview": default,
        "methods": ["blur", "crop"] + ([default] if default else []),
        "note": (
            "AI fill is ready with " + " and ".join(ready_names) + "."
            if default is not None
            else "AI fill needs its model pack in " + str(directory)
            + ". Until it is installed, Blur and Crop stay available."
        ),
    }


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
        "clean": list(layers.get("clean") or []),
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
            clean=_classic_clean_edit(layers.get("clean") or [], clips),
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
    clips = _classic_clips(plan.get("clips"))
    total = _classic_total(clips)
    try:
        layers = normalize_classic_layers(
            payload.get("overlays") or [],
            payload.get("effects") or [],
            total,
            payload.get("clean") or [],
        )
    except ClassicTextError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    # An empty payload is no Edit at all, so any shape may render it.
    if not (layers["overlays"] or layers["graphics"] or layers["motion"]
            or layers["clean"]):
        return None, None
    if aspect not in CLASSIC_EDIT_ASPECTS:
        raise HTTPException(
            422,
            "Text overlays and effects render on 9:16 and 4:5 only. "
            "Switch the shape or clear them.",
        )
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
        "cut": _classic_cut_payload(row, _classic_store_version(job)),
        "aspects": list(CLASSIC_EDIT_ASPECTS),
    }


@router.put("/api/classic/jobs/{job_id}/text")
def classic_text_save(job_id: str, body: ClassicTextBody) -> dict:
    """Save Studio-shaped text layers, effects and Clean boxes for this cut."""
    import app

    job = app.load_job(job_id)
    try:
        clips = _classic_clips(body.clips)
        total = _classic_total(clips)
        layers = normalize_classic_layers(
            body.overlays, body.effects, total, body.clean,
        )
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
    # A finished run is not proof by itself: the transcript can change under
    # it. Only live or failed work wins over the flag check below.
    if running and running.get("status") in {"running", "failed"}:
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


# ---------------------------------------------------------------- sound previews


class MusicPreviewBody(BaseModel):
    """One bounded AI music preview for the Classic Sound card."""

    engine: str = "minimax-music"
    prompt: str = ""
    moods: list[str] = []
    seconds: float | None = None


def _preview_seconds(value: float | None, default: float = PREVIEW_SECONDS) -> float:
    try:
        seconds = float(value if value is not None else default)
    except (TypeError, ValueError):
        seconds = default
    return round(max(3.0, min(PREVIEW_MAX_SECONDS, seconds)), 2)


def _preview_cache_dir() -> Path:
    import audio

    directory = audio.CACHE / "classic-preview"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _preview_key(label: str, source: Path, seconds: float) -> str:
    try:
        stat = source.stat()
        stamp = f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    except OSError:
        stamp = str(source)
    return hashlib.sha1(f"{label}|{stamp}|{seconds:.2f}".encode()).hexdigest()[:24]


def _write_preview(source: Path, target: Path, seconds: float) -> Path:
    """Trim and fade a local file into a small WAV preview."""
    import audio

    duration = audio.media_duration(source)
    clip = seconds if duration <= 0.05 else min(seconds, duration)
    clip = max(0.25, clip)
    filters = ["aresample=48000"]
    if clip > 0.8:
        filters.insert(0, f"afade=t=out:st={clip - 0.35:.3f}:d=0.35")
    tmp = target.with_name(f".{target.stem}.{uuid.uuid4().hex}.part.wav")
    try:
        audio._run([
            audio._ffmpeg(), "-y", "-v", "error", "-i", str(source),
            "-t", f"{clip:.3f}", "-ac", "2", "-af", ",".join(filters),
            "-c:a", "pcm_s16le", str(tmp),
        ], timeout=PREVIEW_TIMEOUT)
        tmp.replace(target)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    return target


def _cached_preview(
    label: str, source: Path, seconds: float,
) -> tuple[Path, str]:
    """Return a cached preview or make one. Returns (path, cache state)."""
    cache = _preview_cache_dir()
    target = cache / f"{_preview_key(label, source, seconds)}.wav"
    if target.is_file() and target.stat().st_size > 512:
        return target, "hit"
    with _preview_lock(target):
        if target.is_file() and target.stat().st_size > 512:
            return target, "hit"
        try:
            _write_preview(source, target, seconds)
        except Exception as exc:  # noqa: BLE001 - route reports the reason
            raise HTTPException(400, f"Could not build the audio preview: {str(exc)[:240]}") from exc
    return target, "miss"


def _job_file(job_id: str, value: str) -> Path:
    import app

    root = app._job_dir(job_id).resolve()
    candidate = Path(str(value or ""))
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if resolved != root and root not in resolved.parents:
        raise HTTPException(400, "Music path must be inside this job.")
    if not resolved.is_file():
        raise HTTPException(404, "That BGM file is missing. Choose it again.")
    return resolved


def _library_track(source: str, track: str, moods: list[str]) -> Path:
    import audio

    if source not in audio.MUSIC_DIRS:
        raise HTTPException(400, "Choose the library or upload your own BGM.")
    directory = audio.MUSIC_DIRS[source].resolve()
    if track:
        candidate = Path(track)
        if not candidate.is_absolute():
            candidate = directory / candidate
        resolved = candidate.resolve()
        if resolved != directory and directory not in resolved.parents:
            raise HTTPException(400, "That track is outside the music library.")
        if not resolved.is_file():
            raise HTTPException(404, "That track is missing from the music library.")
        return resolved
    picked = audio.pick_music(audio.list_music(source), moods)
    if not picked:
        raise HTTPException(
            404,
            f"No tracks in {directory}. Drop an audio file there or upload your BGM.",
        )
    return Path(picked["id"])


def _bgm_preview_source(
    job_id: str, source: str, track: str, upload: str, moods: list[str],
) -> Path:
    source = str(source or "library").strip().lower()
    if source == "upload":
        if not upload:
            raise HTTPException(400, "Choose your BGM file first.")
        return _job_file(job_id, upload)
    return _library_track(source, track, moods)


def _generated_music_preview(body: MusicPreviewBody) -> tuple[Path, str]:
    """Generate one short preview, cached by engine and prompt.

    The file is cached before the provider is called again. The provider is
    reached only on a cache miss, with a 90 s timeout and a bounded length.
    """
    import audio
    import music

    engine = str(body.engine or "").strip().lower()
    allowed = {"minimax-music", "lyria-clip"}
    if engine not in allowed:
        raise HTTPException(400, "Choose MiniMax Music or OpenRouter Lyria.")
    info = (audio.engine_status().get("music") or {}).get(engine) or {}
    if not info.get("available"):
        raise HTTPException(
            409,
            "AI music needs a MiniMax or OpenRouter key. Add one in Setup or use my BGM.",
        )
    seconds = _preview_seconds(body.seconds)
    moods = [str(mood).strip()[:40] for mood in (body.moods or []) if str(mood).strip()][:6]
    prompt = " ".join(str(body.prompt or "").split())[:300]
    if not prompt:
        prompt = audio.music_prompt(moods, seconds)
    if f"{seconds:.0f}" not in prompt:
        prompt = f"{prompt}, {seconds:.0f}-second instrumental preview"
    cache = _preview_cache_dir()
    key = hashlib.sha1(
        f"music|{engine}|{prompt}|{seconds:.2f}".encode(),
    ).hexdigest()[:24]
    target = cache / f"music-{key}.wav"
    if target.is_file() and target.stat().st_size > 1024:
        return target, "hit"
    with _preview_lock(target):
        if target.is_file() and target.stat().st_size > 1024:
            return target, "hit"
        try:
            raw = music.generate_music(
                engine, prompt, seconds, timeout=PREVIEW_TIMEOUT,
            )
        except audio.AudioError as exc:
            raise HTTPException(409, str(exc)[:400]) from exc
        if not raw or not Path(raw).is_file():
            raise HTTPException(502, "Music generation returned no file.")
        try:
            _write_preview(Path(raw), target, seconds)
        except Exception as exc:  # noqa: BLE001 - route reports the reason
            raise HTTPException(400, f"Could not build the music preview: {str(exc)[:240]}") from exc
    return target, "miss"


@router.get("/api/classic/jobs/{job_id}/sound/bgm-preview")
def classic_bgm_preview(
    job_id: str,
    source: str = "library",
    track: str = "",
    upload: str = "",
    moods: str = "",
    seconds: float = PREVIEW_SECONDS,
) -> FileResponse:
    """Play the chosen BGM as a bounded local preview, never a provider call."""
    import app

    app.load_job(job_id)
    mood_list = [item.strip()[:40] for item in str(moods or "").split(",") if item.strip()][:6]
    path = _bgm_preview_source(job_id, source, track, upload, mood_list)
    preview, cache_state = _cached_preview("bgm", path, _preview_seconds(seconds))
    return FileResponse(
        preview,
        media_type="audio/wav",
        filename="bgm-preview.wav",
        headers={
            "Cache-Control": "private, max-age=3600",
            "X-VibeCut-Preview": cache_state,
        },
    )


@router.post("/api/classic/jobs/{job_id}/sound/music-preview")
def classic_music_preview(job_id: str, body: MusicPreviewBody) -> FileResponse:
    """Generate or replay one short AI music preview, cached by prompt."""
    import app

    app.load_job(job_id)
    path, cache_state = _generated_music_preview(body)
    return FileResponse(
        path,
        media_type="audio/wav",
        filename="music-preview.wav",
        headers={
            "Cache-Control": "private, max-age=3600",
            "X-VibeCut-Preview": cache_state,
        },
    )


# ---------------------------------------------------------------- clean preview
#
# The founder edits boxes against the frame the renderer will actually produce.
# This route compiles the cut on screen — including boxes that are not saved
# yet — through the same `compose_render` graph the final render uses, so the
# picture in the preview and the picture in the reel cannot drift apart. No
# job state is written; `render_story_frame` caches by compiled hash.


def _frame_lock(job_id: str) -> threading.Lock:
    with FRAME_LOCK:
        return FRAME_LOCKS.setdefault(job_id, threading.Lock())


def _classic_crop_box(segment: dict, source: dict) -> tuple[float, float, float, float] | None:
    """The segment's crop as fractions of the source frame."""
    crop = segment.get("crop") if isinstance(segment, dict) else None
    if not isinstance(crop, dict):
        return None
    try:
        width = float(source.get("width") or 0.0)
        height = float(source.get("height") or 0.0)
        if width <= 0.0 or height <= 0.0:
            return None
        return (
            round(float(crop["x"]) / width, 6),
            round(float(crop["y"]) / height, 6),
            round(float(crop["w"]) / width, 6),
            round(float(crop["h"]) / height, 6),
        )
    except (KeyError, TypeError, ValueError):
        return None


@router.post(
    "/api/classic/jobs/{job_id}/frame",
    responses={200: {"content": {"image/jpeg": {}}}},
)
def classic_frame(job_id: str, body: ClassicFrameBody):
    """One JPEG of the current Classic cut at ``t``, boxes included."""
    import app
    import compose_render

    job = app.load_job(job_id)
    app.require_source(job)
    try:
        clips = _classic_clips(body.clips)
        total = _classic_total(clips)
        layers = normalize_classic_layers(
            body.overlays, body.effects, total, body.clean,
            require_ready_fill=False,
        )
    except ClassicTextError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    aspect = str(body.aspect or "9:16").strip()
    if aspect not in CLASSIC_EDIT_ASPECTS:
        raise HTTPException(
            422,
            "The preview renders on 9:16 and 4:5 only. Switch the shape.",
        )
    quality = str(body.quality or "draft").strip().lower()
    if quality not in {"draft", "final"}:
        raise HTTPException(422, "quality must be draft or final.")
    try:
        at = float(body.t)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "t must be a finite time in seconds.") from exc
    if not math.isfinite(at) or at < 0.0 or at > total + (1.0 / 30.0):
        raise HTTPException(
            422, f"t must be between 0 and the cut duration ({total:.3f}s).",
        )
    at = min(at, total)
    edit = _build_classic_edit(clips, aspect, layers)
    out_w, out_h = render._dims(aspect, quality)
    try:
        compiled = compose_render.compile_edit(
            edit,
            clips=clips,
            source=job.get("source") or {},
            scenes=(job.get("analysis") or {}).get("scenes") or [],
            size=(out_w, out_h),
            motion_engine=compose_render.EDIT_MOTION_ENGINE,
        )
    except compose_render.ComposeError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    with _frame_lock(job_id):
        try:
            payload = render.render_story_frame(
                str(job["source"]["path"]),
                job["source"],
                app._job_dir(job_id),
                compiled,
                at,
                quality=quality,
                aspect=aspect,
            )
        except render.PipelineError as exc:
            raise HTTPException(500, str(exc)) from exc
    # The frame is cropped, the boxes are source-normalized, so the browser
    # needs this segment's crop to draw and drag them in the right place. The
    # crop changes per clip, hence both the crop and the segment it belongs to.
    headers = {
        "Cache-Control": "no-store",
        "X-VibeCut-Frame": f"{at:.3f}",
        "X-VibeCut-Clean": str(
            (compiled.get("counts") or {}).get("clean") or 0
        ),
    }
    try:
        index, segment = render._compiled_segment_at(compiled, at)
    except render.PipelineError:
        index, segment = 0, {}
    crop = _classic_crop_box(segment, compiled.get("source") or {})
    if crop:
        headers["X-VibeCut-Segment"] = str(index)
        headers["X-VibeCut-Crop"] = ",".join(f"{value:.6f}" for value in crop)
    # A fill box is invisible in this picture on purpose: the fill happens in
    # the render. The client uses this count to say so instead of looking broken.
    headers["X-VibeCut-Fill"] = str(
        len((segment.get("fill") or {}).get("ids") or [])
    )
    return Response(content=payload, media_type="image/jpeg", headers=headers)


@router.post("/api/classic/jobs/{job_id}/fill/estimate")
def classic_fill_estimate(job_id: str, body: ClassicFillEstimateBody) -> dict:
    """Estimate the fill time before a render starts.

    The figure is this Mac's own time per frame from a finished fill. Until
    one finishes there is no figure, and ``seconds`` is null.
    """
    import app
    import compose_render

    job = app.load_job(job_id)
    try:
        clips = _classic_clips(body.clips)
        total = _classic_total(clips)
        layers = normalize_classic_layers([], [], total, body.clean)
    except ClassicTextError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    aspect = str(body.aspect or "9:16").strip()
    if aspect not in CLASSIC_EDIT_ASPECTS:
        raise HTTPException(422, "The preview renders on 9:16 and 4:5 only.")
    edit = _build_classic_edit(clips, aspect, layers)
    try:
        compiled = compose_render.compile_edit(
            edit, clips=clips, source=job.get("source") or {},
            scenes=(job.get("analysis") or {}).get("scenes") or [],
            size=render._dims(aspect, "draft"),
            motion_engine=compose_render.EDIT_MOTION_ENGINE,
        )
    except compose_render.ComposeError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    import textfill

    measured = textfill.fill_rate(app.DATA, "lama")
    per_frame = measured["seconds"]
    seconds = 0.0
    frames = 0
    methods: set[str] = set()
    for segment in compiled.get("segments") or []:
        fill = segment.get("fill") or {}
        if not fill:
            continue
        method = str(fill.get("method") or "lama").lower()
        methods.add(method)
        span = max(0.0, float(segment.get("out_end") or 0.0) - float(segment.get("out_start") or 0.0))
        count = max(1, int(round(span * render.OUT_FPS)))
        frames += count
        seconds += count * float(per_frame or 0.0)
    return {
        "method": next(iter(methods), None),
        "methods": sorted(methods),
        "frames": frames,
        "seconds": round(seconds, 1) if per_frame else None,
        "estimate_seconds": int(round(seconds)) if per_frame else None,
        "per_frame": {"lama": per_frame},
        "measured": bool(measured["measured"]),
    }


@router.post("/api/classic/jobs/{job_id}/fill/sample")
def classic_fill_sample(job_id: str, body: ClassicFillBody) -> dict:
    """Alias for the single-frame before/after sample."""
    return classic_fill_preview(job_id, body)


@router.post("/api/classic/jobs/{job_id}/fill/cancel")
def classic_fill_cancel(job_id: str) -> dict:
    """The fill pre-pass is cancelled through the render cancel route.

    A preview owns the fill lock only for one frame, so there is no separate
    long-running preview job to cancel. Say that instead of pretending.
    """
    import app

    app.load_job(job_id)
    return {
        "cancelled": False,
        "message": "No standalone fill job is running. Cancel the render instead.",
    }


@router.post("/api/classic/jobs/{job_id}/clean/layers")
def classic_clean_layers(job_id: str, body: ClassicCleanLayersBody) -> dict:
    """Return the saved Clean layers for the current cut."""
    import app

    job = app.load_job(job_id)
    try:
        clips = _classic_clips(body.clips)
        key = edits.clip_snapshot_hash(clips)
    except ClassicTextError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    row = _classic_cuts(job).get(key) or {}
    return {"clips_hash": key, "clean": list(row.get("clean") or [])}


@router.post("/api/classic/jobs/{job_id}/clean/plan")
def classic_clean_plan(job_id: str, body: ClassicCleanLayersBody) -> dict:
    """Return the Check rows and the current cut's Clean layers in one plan."""
    import app

    job = app.load_job(job_id)
    try:
        clips = _classic_clips(body.clips)
        key = edits.clip_snapshot_hash(clips)
    except ClassicTextError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    report_path = app._job_dir(job_id) / "check" / detect.REPORT_FILE
    report = {}
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        report = {}
    row = _classic_cuts(job).get(key) or {}
    return {
        "clips_hash": key,
        "rows": list(report.get("clean_prefill") or []),
        "layers": list(row.get("clean") or []),
        "note": "Rows are Check output; the browser joins them to this cut.",
    }


@router.post("/api/classic/jobs/{job_id}/clean/residual")
def classic_clean_residual(job_id: str, body: ClassicCleanLayersBody) -> dict:
    """Residual OCR is not a separate render in Classic; report honestly."""
    import app

    job = app.load_job(job_id)
    try:
        _classic_clips(body.clips)
    except ClassicTextError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return {
        "residual": [],
        "residual_pct": 0.0,
        "frames": 0,
        "note": "Classic does not run a separate residual OCR pass.",
    }


@router.get("/api/classic/fill")
def classic_fill() -> dict:
    """AI-fill engine status. Never a fake ready state."""
    return classic_fill_status()


def _fill_http_error(status_code: int, code: str, message: str, **extra) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": code, "message": message, **extra},
        headers={"Cache-Control": "no-store"},
    )


def _data_url(path: Path) -> str:
    import base64

    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _read_source_frame(path: Path, width: int, height: int, at: float):
    """One RGB frame from the source at ``at`` seconds."""
    import subprocess

    import numpy as np

    command = [
        render._ffmpeg(), "-v", "error", "-nostdin",
        "-ss", f"{max(0.0, float(at)):.6f}", "-i", str(path),
        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{int(width)}x{int(height)}", "pipe:1",
    ]
    completed = subprocess.run(command, capture_output=True, timeout=60, check=False)
    expected = int(width) * int(height) * 3
    if completed.returncode != 0 or len(completed.stdout) < expected:
        tail = (completed.stderr or b"")[-800:].decode("utf-8", "replace")
        raise HTTPException(500, f"Could not read the preview frame. {tail}".strip())
    return np.frombuffer(
        completed.stdout[:expected], dtype=np.uint8,
    ).reshape((int(height), int(width), 3)).copy()


def _preview_filter_chain(segment: dict, out_w: int, out_h: int) -> str:
    """The source-side clean, crop, scale and colour chain for one frame."""
    parts = [str(item) for item in segment.get("pre_filters") or []]
    crop = segment.get("crop") or {}
    try:
        crop_w = int(crop.get("w") or 0)
        crop_h = int(crop.get("h") or 0)
        crop_x = int(crop.get("x") or 0)
        crop_y = int(crop.get("y") or 0)
    except (TypeError, ValueError):
        crop_w = crop_h = 0
    if crop_w > 1 and crop_h > 1:
        parts.append(f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}")
    parts.extend([f"scale={out_w}:{out_h}:flags=lanczos", "setsar=1"])
    parts.extend(str(item) for item in segment.get("post_filters") or [])
    return ",".join(part for part in parts if part)


def _render_preview_jpeg(png: Path, output: Path, chain: str) -> None:
    """Encode one PNG through the same crop/colour chain as the beat."""
    import subprocess

    command = [
        render._ffmpeg(), "-y", "-v", "error", "-i", str(png),
        "-vf", chain, "-frames:v", "1", "-q:v", "2", str(output),
    ]
    completed = subprocess.run(command, capture_output=True, timeout=90, check=False)
    if completed.returncode != 0 or not output.is_file():
        tail = (completed.stderr or b"")[-1200:].decode("utf-8", "replace")
        raise HTTPException(500, f"Could not prepare the fill preview. {tail}".strip())


@router.post("/api/classic/jobs/{job_id}/fill/preview")
def classic_fill_preview(job_id: str, body: ClassicFillBody) -> dict:
    """Before/after JPEGs of one frame, with LaMa filling the AI-fill boxes.

    One frame, not a render. Both pictures go through the same crop, colour
    and overlay pass, so the comparison is only the fill. The boxes come from
    the request, unsaved, exactly like the frame route.
    """
    import hashlib
    import shutil
    import uuid

    from PIL import Image

    import app
    import compose_render
    import textfill

    job = app.load_job(job_id)
    app.require_source(job)
    status = classic_fill_status()
    if not status["available"]:
        return _fill_http_error(
            409, "model_missing", status["note"], fill=status,
        )
    try:
        clips = _classic_clips(body.clips)
        total = _classic_total(clips)
        layers = normalize_classic_layers(
            body.overlays, body.effects, total, body.clean,
        )
    except ClassicTextError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    aspect = str(body.aspect or "9:16").strip()
    if aspect not in CLASSIC_EDIT_ASPECTS:
        raise HTTPException(
            422,
            "The preview renders on 9:16 and 4:5 only. Switch the shape.",
        )
    try:
        at = float(body.t)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "t must be a finite time in seconds.") from exc
    if not math.isfinite(at) or at < 0.0 or at > total + (1.0 / 30.0):
        raise HTTPException(
            422, f"t must be between 0 and the cut duration ({total:.3f}s).",
        )
    at = min(at, total)
    source = job.get("source") or {}
    source_path = Path(str(source.get("path") or ""))
    if not source_path.is_file():
        raise HTTPException(404, "The source video for this job is missing.")
    width = int(source.get("width") or 0)
    height = int(source.get("height") or 0)
    if width < 2 or height < 2:
        raise HTTPException(409, "The source size is not available for a fill preview.")
    edit = _build_classic_edit(clips, aspect, layers)
    out_w, out_h = render._dims(aspect, "draft")
    try:
        compiled = compose_render.compile_edit(
            edit,
            clips=clips,
            source=source,
            scenes=(job.get("analysis") or {}).get("scenes") or [],
            size=(out_w, out_h),
            motion_engine=compose_render.EDIT_MOTION_ENGINE,
        )
    except compose_render.ComposeError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    segments = compiled.get("segments") or []
    if not segments:
        raise HTTPException(422, "This cut has no frames to preview.")
    last_frame = max(0, int(round(float(segments[-1].get("out_end") or 0.0)
                                  * render.OUT_FPS)) - 1)
    frame_index = min(max(0, int(round(at * render.OUT_FPS))), last_frame)
    at = frame_index / render.OUT_FPS
    try:
        index, segment = render._compiled_segment_at(compiled, at)
    except render.PipelineError as exc:
        raise HTTPException(422, str(exc)) from exc
    fill_plan = segment.get("fill") or {}
    fill_layers = [item for item in fill_plan.get("layers") or []
                   if isinstance(item, dict)]
    if not fill_layers:
        raise HTTPException(
            422,
            "No AI fill box is active at this frame. Choose AI fill for a box "
            "and put the playhead inside its range.",
        )
    engine = str(fill_plan.get("method") or "lama").strip().lower()
    if engine not in CLASSIC_FILL_ENGINES:
        engine = "lama"
    engine_status = (status.get("engines") or {}).get(engine) or {}
    if not engine_status.get("ready"):
        return _fill_http_error(
            409,
            "model_missing",
            engine_status.get("reason") or status["note"],
            fill=status,
        )
    fps = float(source.get("fps") or render.OUT_FPS) or render.OUT_FPS
    source_time = float(segment.get("start") or 0.0) + max(
        0.0, at - float(segment.get("out_start") or 0.0),
    )
    rects = textfill.masks.frame_rects(
        fill_layers,
        start=source_time - (0.5 / max(1.0, fps)),
        fps=fps,
        frames=1,
        width=width,
        height=height,
    )[0]
    if not rects:
        raise HTTPException(422, "No AI fill region is active at this frame.")

    directory = textfill.models_dir(app.DATA)
    problem = textfill.missing_model(engine, directory)
    if problem:
        return _fill_http_error(409, "model_missing", problem, fill=status)
    model_path = textfill.model_path(engine, directory)
    stamp = model_path.stat()
    key = hashlib.sha1(
        (
            f"{compiled.get('edit_hash')}:{frame_index}:{out_w}x{out_h}:{engine}:"
            f"{stamp.st_size}:{stamp.st_mtime_ns}:"
            f"{source.get('fingerprint')}"
        ).encode("utf-8"),
    ).hexdigest()[:20]
    job_dir = app._job_dir(job_id)
    cache_dir = job_dir / "fill" / "preview"
    before_jpg = cache_dir / f"{key}_before.jpg"
    after_jpg = cache_dir / f"{key}_after.jpg"
    if before_jpg.is_file() and after_jpg.is_file():
        return {
            "before": _data_url(before_jpg),
            "after": _data_url(after_jpg),
            "width": out_w,
            "height": out_h,
            "time": round(at, 3),
            "method": engine,
            "render_method": engine,
            "cached": True,
        }

    # A render that is filling already holds this lock; a preview must not load
    # a second 208 MB model beside it on an 8 GB Mac.
    if not render.FILL_LOCK.acquire(blocking=False):
        return _fill_http_error(
            409,
            "fill_running",
            "A fill is already running. Wait for the render to finish, then "
            "preview. Cancel the render if you want to compare now.",
        )
    try:
        frame_rgb = _read_source_frame(source_path, width, height, source_time)
        try:
            # Scanned text narrows to its letters here too, so the preview
            # shows the hole the render will use.
            tight_rects = textfill.masks.frame_rects(
                [
                    layer for layer in fill_layers
                    if textfill.masks.uses_text_mask(layer, width, height)
                ],
                start=source_time - (0.5 / max(1.0, fps)),
                fps=fps,
                frames=1,
                width=width,
                height=height,
            )[0]
            filled_rgb = textfill.fill_frame(
                frame_rgb, rects, data_root=job_dir.parent.parent, method=engine,
                tight_rects=tight_rects,
            )
        except textfill.FillError as exc:
            return _fill_http_error(409, "fill_failed", str(exc))
        tmp = job_dir / "renders" / f"tmp_fill_preview_{uuid.uuid4().hex}"
        tmp.mkdir(parents=True, exist_ok=True)
        try:
            before_png = tmp / "before.png"
            after_png = tmp / "after.png"
            Image.fromarray(frame_rgb).save(before_png)
            Image.fromarray(filled_rgb).save(after_png)
            chain = _preview_filter_chain(segment, out_w, out_h)
            before_raw = tmp / "before_raw.jpg"
            after_raw = tmp / "after_raw.jpg"
            _render_preview_jpeg(before_png, before_raw, chain)
            _render_preview_jpeg(after_png, after_raw, chain)
            before_final = tmp / "before_final.jpg"
            after_final = tmp / "after_final.jpg"
            layer_cache = job_dir.parent.parent / "cache" / "layers"
            render._burn_frame(
                before_raw, compiled.get("overlays") or [], before_final,
                out_w, out_h, at, layer_cache,
            )
            render._burn_frame(
                after_raw, compiled.get("overlays") or [], after_final,
                out_w, out_h, at, layer_cache,
            )
            cache_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(before_final, before_jpg)
            shutil.copyfile(after_final, after_jpg)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    finally:
        # The preview is one frame: keeping LaMa loaded would cost a render's
        # worth of memory for nothing.
        textfill.release_fillers()
        render.FILL_LOCK.release()
    return {
        "before": _data_url(before_jpg),
        "after": _data_url(after_jpg),
        "width": out_w,
        "height": out_h,
        "time": round(at, 3),
        "method": engine,
        "render_method": engine,
        "cached": False,
    }

