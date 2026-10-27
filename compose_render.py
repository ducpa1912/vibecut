"""Pure Edit -> ffmpeg filter compiler.

``compile_edit`` turns one stored Edit into deterministic per-segment filter
strings and a flat overlay layer list. It never starts ffmpeg, probes media,
reads a render, or writes a file. Wave 2 wires the strings into
``render._segment``; this module is the contract they are tested against.

Stage order per segment (matches REVAMP_PLAN §4)::

    source -> [clean] -> crop/reframe -> scale -> [motion] -> [colour]

Clean boxes use source coordinates. Graphics and caption boxes use output
coordinates. Motion is compiled after the output scale as a ``zoompan`` crop
window, so the same compiled string drives preview and export.
"""

from __future__ import annotations

import math
from typing import Any, Iterable

import edits
import overlays

SCHEMA_VERSION = 1
OUT_FPS = 30
CANVAS = dict(overlays.CANVAS)
MOTION_SHAKE_HZ = 7.0


class ComposeError(ValueError):
    """The Edit or the story context cannot be compiled."""

    status_code = 422


class ComposeInputError(ComposeError):
    """A required compile input is missing or malformed."""

    status_code = 400


# ---------------------------------------------------------------- geometry


def _even(value: float, minimum: int = 2) -> int:
    return max(minimum, int(round(float(value) / 2.0)) * 2)


def _even_int(value: int, low: int, high: int) -> int:
    value = int(value)
    value -= value % 2
    return max(low, min(high, value))


def _clamp_int(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def _target_size(aspect: str) -> tuple[int, int]:
    canvas = CANVAS[aspect]
    return int(canvas["w"]), int(canvas["h"])


def _source_dimensions(
    aspect: str,
    source: dict | None,
) -> tuple[int, int, str]:
    try:
        width = int((source or {}).get("width") or 0)
        height = int((source or {}).get("height") or 0)
    except (TypeError, ValueError):
        width = height = 0
    if width > 1 and height > 1:
        return width, height, "source"
    out_w, out_h = _target_size(aspect)
    return out_w, out_h, "nominal"


def _base_crop(
    width: int,
    height: int,
    aspect: str,
    cx: float,
    cy: float,
    zoom: float,
) -> dict:
    out_w, out_h = _target_size(aspect)
    target_ar = out_w / out_h
    source_ar = width / max(1, height)
    if source_ar > target_ar:
        crop_h = _even(height)
        crop_w = min(_even(crop_h * target_ar), _even(width))
    else:
        crop_w = _even(width)
        crop_h = min(_even(crop_w / target_ar), _even(height))
    if zoom > 1.0:
        crop_w = min(crop_w, _even(crop_w / zoom))
        crop_h = min(crop_h, _even(crop_h / zoom))
    crop_w = _clamp_int(crop_w, 2, width if width % 2 == 0 else width - 1)
    crop_h = _clamp_int(crop_h, 2, height if height % 2 == 0 else height - 1)
    x = int(round(cx * width - crop_w / 2.0))
    y = int(round(cy * height - crop_h / 2.0))
    return {
        "x": _even_int(x, 0, width - crop_w),
        "y": _even_int(y, 0, height - crop_h),
        "w": crop_w,
        "h": crop_h,
    }


def _box_rect(box: dict, width: int, height: int, *, even: bool) -> dict:
    x = _clamp_int(int(round(float(box["x"]) * width)), 0, width - 1)
    y = _clamp_int(int(round(float(box["y"]) * height)), 0, height - 1)
    if even:
        x = min(x, max(0, width - 2))
        y = min(y, max(0, height - 2))
        x -= x % 2
        y -= y % 2
    w = max(1, int(round(float(box["w"]) * width)))
    h = max(1, int(round(float(box["h"]) * height)))
    w = min(w, width - x)
    h = min(h, height - y)
    if even:
        w = max(2, w - (w % 2))
        h = max(2, h - (h % 2))
        w = min(w, width - x)
        h = min(h, height - y)
    return {"x": x, "y": y, "w": max(1, w), "h": max(1, h)}


def _intersects(first: dict, second: dict) -> bool:
    return (
        first["x"] < second["x"] + second["w"]
        and second["x"] < first["x"] + first["w"]
        and first["y"] < second["y"] + second["h"]
        and second["y"] < first["y"] + first["h"]
    )


def _shift_away(crop: dict, guard: dict, width: int, height: int) -> dict | None:
    """Return the nearest even crop shift that clears one crop_guard box."""
    if not _intersects(crop, guard):
        return dict(crop)
    options: list[tuple[int, int, dict]] = []

    def shift_options(value: float, low: int, high: int) -> list[int]:
        base = int(math.floor(value))
        candidates = set()
        for number in (base, base + 2, base - 2):
            even = number - (number % 2)
            if low <= even <= high:
                candidates.add(even)
        return sorted(candidates)

    for new_x in shift_options(guard["x"] - crop["w"], 0, width - crop["w"]):
        candidate = {**crop, "x": new_x}
        if not _intersects(candidate, guard):
            options.append((abs(new_x - crop["x"]), 0, candidate))
    for new_x in shift_options(guard["x"] + guard["w"], 0, width - crop["w"]):
        candidate = {**crop, "x": new_x}
        if not _intersects(candidate, guard):
            options.append((abs(new_x - crop["x"]), 0, candidate))
    for new_y in shift_options(guard["y"] - crop["h"], 0, height - crop["h"]):
        candidate = {**crop, "y": new_y}
        if not _intersects(candidate, guard):
            options.append((abs(new_y - crop["y"]), 1, candidate))
    for new_y in shift_options(guard["y"] + guard["h"], 0, height - crop["h"]):
        candidate = {**crop, "y": new_y}
        if not _intersects(candidate, guard):
            options.append((abs(new_y - crop["y"]), 1, candidate))
    if not options:
        return None
    options.sort(key=lambda item: (item[0], item[1], item[2]["x"], item[2]["y"]))
    return options[0][2]


# ---------------------------------------------------------------- clean


def _draw_color(value: str, opacity: float) -> str:
    text = str(value or "#000000").lower()
    alpha = max(0.0, min(1.0, float(opacity)))
    if len(text) == 9 and text.startswith("#"):
        alpha = alpha * (int(text[7:9], 16) / 255.0)
        text = text[:7]
    if not (len(text) == 7 and text.startswith("#")):
        text = "#000000"
    return f"0x{text[1:7]}@{alpha:.3f}"


def _active_window(
    layer: dict,
    start: float,
    end: float,
) -> tuple[bool, str | None]:
    """Return (active, enable expression). ``None`` means the whole segment."""
    ranges = layer.get("ranges") or []
    if not ranges:
        return True, None
    local: list[tuple[float, float]] = []
    for item in ranges:
        range_start = max(start, float(item["start"]))
        range_end = min(end, float(item["end"]))
        if range_end <= range_start + 1e-6:
            continue
        if range_start <= start + 1e-6 and range_end >= end - 1e-6:
            return True, None
        local.append((range_start - start, range_end - start))
    if not local:
        return False, None
    expression = "+".join(
        f"between(t,{a:.3f},{b:.3f})" for a, b in local
    )
    return True, expression


def _enable_suffix(expression: str | None) -> str:
    return f":enable='{expression}'" if expression else ""


def _clean_filters(
    clean: Iterable[dict],
    start: float,
    end: float,
    width: int,
    height: int,
) -> tuple[list[str], list[str], list[dict]]:
    """Compile active clean layers. Returns (filters, ids, warnings)."""
    filters: list[str] = []
    applied: list[str] = []
    warnings: list[dict] = []
    for index, layer in enumerate(clean):
        active, expression = _active_window(layer, start, end)
        if not active:
            continue
        kind = layer["kind"]
        if kind == "crop_guard":
            continue
        rect = _box_rect(layer["box"], width, height, even=True)
        if kind in {"plate", "mask"}:
            color = _draw_color(layer.get("color") or "#000000", layer.get("opacity", 1.0))
            filters.append(
                f"drawbox=x={rect['x']}:y={rect['y']}:w={rect['w']}:"
                f"h={rect['h']}:color={color}:t=fill"
                f"{_enable_suffix(expression)}"
            )
            applied.append(layer["id"])
        elif kind == "blur":
            label = f"cl{index}"
            radius = int(layer.get("radius") or 24)
            filters.append(
                f"split=2[{label}a][{label}b];"
                f"[{label}b]crop={rect['w']}:{rect['h']}:{rect['x']}:{rect['y']},"
                f"boxblur={radius}:2[{label}c];"
                f"[{label}a][{label}c]overlay={rect['x']}:{rect['y']}"
                f"{_enable_suffix(expression)}"
            )
            applied.append(layer["id"])
        else:  # pragma: no cover - normalize_clean rejects unknown kinds
            warnings.append({
                "code": "unknown_clean_kind",
                "message": f"Clean layer {layer['id']} was skipped.",
                "layer_id": layer["id"],
            })
    return filters, applied, warnings


# ---------------------------------------------------------------- motion


def _motion_filter(
    motion: dict,
    *,
    out_start: float,
    out_end: float,
    segment_frames: int,
    out_w: int,
    out_h: int,
) -> str | None:
    """Compile one motion layer for one segment, or ``None``."""
    motion_start = float(motion["start"])
    motion_end = float(motion["end"])
    if motion_end <= out_start + 1e-6 or motion_start >= out_end - 1e-6:
        return None
    local_start = max(0.0, motion_start - out_start)
    local_end = min(out_end - out_start, motion_end - out_start)
    first = _clamp_int(int(round(local_start * OUT_FPS)), 0, segment_frames - 1)
    last = _clamp_int(int(round(local_end * OUT_FPS)), first + 1, segment_frames)
    active = max(1, last - first)
    kind = motion["kind"]
    amount = float(motion["amount"])
    ramp_frames = max(1, int(round(float(motion.get("ramp") or 0.0) * OUT_FPS)))
    if kind == "shake":
        seed = int(motion.get("seed") or 0)
        phase = (seed % 360) * math.pi / 180.0
        dx = max(1, int(round(amount * out_w)))
        dy = max(1, int(round(amount * out_h)))
        zoom = 1.0 + 2.0 * max(dx, dy) / max(1, min(out_w, out_h))
        gate = f"between(on,{first},{last})"
        x_expr = (
            f"(iw-iw/zoom)/2+{dx}*sin(2*PI*{MOTION_SHAKE_HZ:.3f}*on/"
            f"{OUT_FPS}+{phase:.3f})*{gate}"
        )
        y_expr = (
            f"(ih-ih/zoom)/2+{dy}*cos(2*PI*{MOTION_SHAKE_HZ:.3f}*on/"
            f"{OUT_FPS}+{phase:.3f})*{gate}"
        )
        return (
            f"zoompan=z='{zoom:.3f}':x='{x_expr}':y='{y_expr}':"
            f"d=1:s={out_w}x{out_h}:fps={OUT_FPS}"
        )
    if kind == "punch_in":
        z_expr = (
            f"if(lt(on,{first}),1.000,1.000+{amount:.3f}*"
            f"min(1,(on-{first})/{ramp_frames}))"
        )
    elif kind == "snap_zoom":
        z_expr = f"if(lt(on,{first}),1.000,{1.0 + amount:.3f})"
    else:  # push
        z_expr = (
            f"1.000+{amount:.3f}*min(1,max(0,on-{first})/{active})"
        )
    return (
        f"zoompan=z='{z_expr}':x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':d=1:s={out_w}x{out_h}:fps={OUT_FPS}"
    )


# ---------------------------------------------------------------- colour


def _escape_filter_path(path: str) -> str:
    return (
        str(path)
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
    )


def _color_filters(color: dict) -> list[str]:
    filters: list[str] = []
    lut = color.get("lut")
    if isinstance(lut, dict) and lut.get("path"):
        filters.append(f"lut3d=file='{_escape_filter_path(lut['path'])}'")
    exposure = float(color.get("exposure") or 0.0)
    contrast = float(color.get("contrast") or 0.0)
    saturation = float(color.get("saturation") or 0.0)
    if any(abs(value) > 1e-9 for value in (exposure, contrast, saturation)):
        filters.append(
            f"eq=brightness={exposure:.3f}:contrast={1.0 + contrast:.3f}:"
            f"saturation={1.0 + saturation:.3f}"
        )
    temperature = float(color.get("temperature") or 0.0)
    if abs(temperature) > 1e-9:
        kelvin = int(round(6600.0 - temperature * 2600.0))
        filters.append(f"colortemperature=temperature={kelvin}")
    vignette = float(color.get("vignette") or 0.0)
    if vignette > 1e-9:
        filters.append(f"vignette=angle={vignette * math.pi / 4.0:.4f}")
    grain = float(color.get("grain") or 0.0)
    if grain > 1e-9:
        filters.append(
            f"noise=alls={max(1, int(round(grain * 40)))}:allf=t+u"
        )
    sharpen = float(color.get("sharpen") or 0.0)
    if sharpen > 1e-9:
        filters.append(f"unsharp=5:5:{sharpen * 1.5:.3f}")
    return filters


# ---------------------------------------------------------------- overlays


def _overlay_rect(anchor: str, box: dict) -> dict:
    return overlays.normalize_rect(anchor, box)


def _caption_overlay_style(caption_track: dict) -> tuple[dict, str]:
    style = caption_track.get("style")
    style = style if isinstance(style, dict) else {}
    overlay_style = dict(overlays.STYLE_DEFAULTS)
    try:
        size = int(round(float(style.get("font_size") or overlay_style["size"])))
    except (TypeError, ValueError):
        size = int(overlay_style["size"])
    overlay_style["size"] = max(12, min(160, size))
    try:
        overlay_style["color"] = overlays.normalize_color(
            style.get("color") or overlay_style["color"],
        )
    except ValueError:
        overlay_style["color"] = "#ffffff"
    try:
        stroke_width = float(style.get("stroke_width") or 0.0)
    except (TypeError, ValueError):
        stroke_width = 0.0
    if stroke_width > 0:
        try:
            overlay_style["stroke"] = overlays.normalize_color(
                style.get("stroke_color") or "#000000",
            )
        except ValueError:
            overlay_style["stroke"] = "#000000"
    try:
        background_opacity = float(style.get("background_opacity") or 0.0)
    except (TypeError, ValueError):
        background_opacity = 0.0
    if background_opacity > 0:
        try:
            background = overlays.normalize_color(
                style.get("background") or "#000000",
            )
        except ValueError:
            background = "#000000"
        alpha = max(0, min(255, int(round(background_opacity * 255))))
        overlay_style["background"] = f"{background}{alpha:02x}"
    overlay_style["uppercase"] = bool(style.get("uppercase"))
    position = str(style.get("position") or "bottom").strip().lower()
    anchor = {
        "top": "top-center",
        "center": "center",
        "bottom": "bottom-center",
    }.get(position, "bottom-center")
    return overlay_style, anchor


def _caption_layers(
    edit: dict,
    caption_track: dict | None,
    warnings: list[dict],
) -> tuple[list[dict], dict]:
    captions = edit.get("captions") or {}
    track_id = captions.get("track_id")
    metadata = {
        "track_id": track_id,
        "style_id": captions.get("style_id"),
        "enabled": bool(captions.get("enabled", True)),
        "cue_count": 0,
        "compiled": False,
    }
    if not track_id or not metadata["enabled"]:
        return [], metadata
    if caption_track is None:
        warnings.append({
            "code": "caption_track_unavailable",
            "message": "Caption track is referenced but was not supplied to the compiler.",
            "track_id": track_id,
        })
        return [], metadata
    resolved = str(caption_track.get("track_id") or "")
    if resolved and resolved != track_id:
        raise ComposeError(
            f"Caption track {resolved} does not match Edit track {track_id}."
        )
    cues = [item for item in caption_track.get("cues") or [] if isinstance(item, dict)]
    style, anchor = _caption_overlay_style(caption_track)
    box = {"w": overlays.DEFAULT_BOX["caption"][0], "h": overlays.DEFAULT_BOX["caption"][1]}
    layers: list[dict] = []
    for index, cue in enumerate(cues):
        try:
            start = float(cue.get("start"))
            end = float(cue.get("end"))
        except (TypeError, ValueError) as exc:
            raise ComposeError(f"Caption cue {index + 1} has invalid times.") from exc
        if not math.isfinite(start) or not math.isfinite(end) or end <= start:
            raise ComposeError(f"Caption cue {index + 1} has invalid times.")
        try:
            text = overlays.normalize_text(str(cue.get("text") or ""))
        except ValueError as exc:
            raise ComposeError(f"Caption cue {index + 1}: {exc}") from exc
        layers.append({
            "id": f"cap{index + 1:02d}",
            "type": "caption",
            "kind": "caption",
            "text": text,
            "start": round(start, 3),
            "end": round(end, 3),
            "box": dict(box),
            "rect": _overlay_rect(anchor, box),
            "z": 50,
            "style": dict(style),
            "opacity": 1.0,
            "safe_zone": True,
        })
    metadata["cue_count"] = len(layers)
    metadata["compiled"] = True
    return layers, metadata


def _graphic_layers(edit: dict) -> list[dict]:
    layers: list[dict] = []
    for item in edit.get("graphics") or []:
        rect = _overlay_rect(item["anchor"], item["box"])
        if item["type"] == "text":
            layers.append({
                "id": item["id"],
                "type": "text",
                "kind": item["kind"],
                "text": item["text"],
                "start": item["start"],
                "end": item["end"],
                "box": dict(item["box"]),
                "rect": rect,
                "z": item["z"],
                "style": dict(item["style"]),
                "opacity": item["opacity"],
                "safe_zone": item["safe_zone"],
            })
        else:
            value = {
                "id": item["id"],
                "type": "fx",
                "kind": item["kind"],
                "start": item["start"],
                "end": item["end"],
                "box": dict(item["box"]),
                "rect": rect,
                "z": item["z"],
                "color": item["color"],
                "thickness": item["thickness"],
                "opacity": item["opacity"],
                "safe_zone": True,
            }
            if item.get("asset"):
                value["asset"] = dict(item["asset"])
            layers.append(value)
    return layers


# ---------------------------------------------------------------- clips


def _clips(clips: Any) -> list[dict]:
    if not isinstance(clips, (list, tuple)) or not clips:
        raise ComposeInputError("Story clips are required to compile an Edit.")
    result: list[dict] = []
    for index, raw in enumerate(clips):
        if not isinstance(raw, dict):
            raise ComposeInputError(f"Clip {index + 1} must be an object.")
        try:
            start = float(raw.get("start") or 0.0)
            end = raw.get("end")
            end = float(end if end is not None else start + float(raw.get("dur") or 0.0))
        except (TypeError, ValueError) as exc:
            raise ComposeInputError(f"Clip {index + 1} has invalid times.") from exc
        if not math.isfinite(start) or not math.isfinite(end) or end <= start:
            raise ComposeInputError(f"Clip {index + 1} has invalid times.")
        result.append({
            "index": index,
            "scene": raw.get("scene"),
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(end - start, 3),
        })
    return result


def _scene_crop(scene: dict | None, aspect: str) -> tuple[float, float] | None:
    if not isinstance(scene, dict):
        return None
    crop = (scene.get("crops") or {}).get(aspect)
    if not isinstance(crop, dict) and aspect == "9:16":
        # Legacy scenes store one 9:16 crop; 4:5 must not inherit it silently.
        crop = scene.get("crop") if isinstance(scene.get("crop"), dict) else None
    if not isinstance(crop, dict):
        return None
    try:
        cx = float(crop.get("cx", 0.5))
        cy = float(crop.get("cy", 0.5))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(cx) or not math.isfinite(cy):
        return None
    return min(max(cx, 0.0), 1.0), min(max(cy, 0.0), 1.0)


# ---------------------------------------------------------------- compile


def compile_edit(
    edit: dict,
    *,
    clips: Any,
    source: dict | None = None,
    scenes: Any = None,
    caption_track: dict | None = None,
    include_captions: bool = True,
) -> dict:
    """Compile one Edit. Pure: no media access and no ffmpeg call."""
    try:
        normalized = edits.normalize_edit(edit)
    except edits.EditError as exc:
        raise ComposeError(str(exc)) from exc
    story_clips = _clips(clips)
    aspect = normalized["aspect"]
    out_w, out_h = _target_size(aspect)
    width, height, dimensions_source = _source_dimensions(aspect, source)
    scene_map: dict[str, dict] = {}
    if isinstance(scenes, dict):
        scene_map = {str(key): value for key, value in scenes.items() if isinstance(value, dict)}
    elif isinstance(scenes, (list, tuple)):
        for scene in scenes:
            if isinstance(scene, dict) and scene.get("id") is not None:
                scene_map[str(scene["id"])] = scene

    warnings: list[dict] = []
    if dimensions_source == "nominal":
        warnings.append({
            "code": "source_dimensions_missing",
            "message": (
                "Source width and height are unavailable; clean and crop "
                f"geometry uses the nominal {out_w}x{out_h} frame."
            ),
        })

    reframe = normalized["reframe"]
    overrides = reframe.get("overrides") or {}
    segments: list[dict] = []
    out_cursor = 0.0
    for clip in story_clips:
        duration = float(clip["duration"])
        segment_out_start = out_cursor
        segment_out_end = out_cursor + duration
        out_cursor = segment_out_end
        scene = scene_map.get(str(clip["scene"]))
        if reframe["mode"] == "center":
            cx = cy = 0.5
        elif reframe["mode"] == "auto":
            scene_crop = _scene_crop(scene, aspect)
            cx, cy = scene_crop if scene_crop else (reframe["cx"], reframe["cy"])
        else:
            cx, cy = reframe["cx"], reframe["cy"]
        cx = float(overrides.get("cx", cx))
        cy = float(overrides.get("cy", cy))
        zoom = float(overrides.get("zoom", reframe["zoom"]))
        crop = _base_crop(width, height, aspect, cx, cy, zoom)
        clean_warnings: list[dict] = []
        for layer in normalized["clean"]:
            if layer["kind"] != "crop_guard":
                continue
            active, _expression = _active_window(
                layer, clip["start"], clip["end"],
            )
            if not active:
                continue
            guard = _box_rect(layer["box"], width, height, even=False)
            shifted = _shift_away(crop, guard, width, height)
            if shifted is None:
                clean_warnings.append({
                    "code": "crop_guard_unmet",
                    "message": (
                        f"Crop cannot clear clean guard {layer['id']} and keep "
                        f"the {aspect} frame."
                    ),
                    "layer_id": layer["id"],
                    "segment": clip["index"],
                })
            else:
                crop = shifted
        clean_filter_list, clean_ids, skipped = _clean_filters(
            normalized["clean"], clip["start"], clip["end"], width, height,
        )
        warnings.extend(clean_warnings)
        warnings.extend({
            **item,
            "segment": clip["index"],
        } for item in skipped)

        frames = max(1, int(round(duration * OUT_FPS)))
        pre_filter = ",".join(clean_filter_list)
        crop_filter = f"crop={crop['w']}:{crop['h']}:{crop['x']}:{crop['y']}"
        scale_filter = f"scale={out_w}:{out_h}:flags=lanczos"
        motion_filters: list[str] = []
        motion_ids: list[str] = []
        for motion in normalized["motion"]:
            compiled = _motion_filter(
                motion,
                out_start=segment_out_start,
                out_end=segment_out_end,
                segment_frames=frames,
                out_w=out_w,
                out_h=out_h,
            )
            if compiled:
                motion_filters.append(compiled)
                motion_ids.append(motion["id"])
        color_filters = _color_filters(normalized["color"])
        post_filter = ",".join(motion_filters + color_filters)
        chain = []
        if pre_filter:
            chain.append(pre_filter)
        chain.extend([crop_filter, scale_filter, "setsar=1", f"fps={OUT_FPS}", "format=yuv420p"])
        if post_filter:
            chain.append(post_filter)
        segments.append({
            "index": clip["index"],
            "scene": clip["scene"],
            "start": clip["start"],
            "end": clip["end"],
            "duration": clip["duration"],
            "frames": frames,
            "out_start": round(segment_out_start, 3),
            "out_end": round(segment_out_end, 3),
            "crop": crop,
            "crop_path_ref": reframe.get("crop_path_ref"),
            "clean_ids": clean_ids,
            "motion_ids": motion_ids,
            "pre_filters": clean_filter_list,
            "pre_filter": pre_filter,
            "crop_filter": crop_filter,
            "scale_filter": scale_filter,
            "post_filters": motion_filters + color_filters,
            "post_filter": post_filter,
            "filter": ",".join(chain),
        })

    graphic_layers = _graphic_layers(normalized)
    if include_captions:
        caption_layers, caption_metadata = _caption_layers(
            normalized, caption_track, warnings,
        )
    else:
        captions_value = normalized.get("captions") or {}
        caption_layers = []
        caption_metadata = {
            "track_id": captions_value.get("track_id"),
            "style_id": captions_value.get("style_id"),
            "enabled": bool(captions_value.get("enabled", True)),
            "cue_count": 0,
            "compiled": False,
        }
    overlay_layers = graphic_layers + caption_layers
    overlay_layers.sort(key=lambda item: (
        int(item["z"]),
        float(item["start"]),
        float(item["end"]),
        str(item["id"]),
    ))
    for layer in overlay_layers:
        layer["duration"] = round(float(layer["end"]) - float(layer["start"]), 3)

    return {
        "schema_version": SCHEMA_VERSION,
        "renderer_version": normalized["renderer_version"],
        "edit_id": normalized["id"],
        "edit_hash": normalized["hash"],
        "edit_version": normalized["version"],
        "aspect": aspect,
        "canvas": {"w": out_w, "h": out_h},
        "fps": OUT_FPS,
        "source": {
            "width": width,
            "height": height,
            "dimensions_source": dimensions_source,
        },
        "segments": segments,
        "overlays": overlay_layers,
        "captions": caption_metadata,
        "counts": {
            "segments": len(segments),
            "overlays": len(overlay_layers),
            "clean": sum(len(item["clean_ids"]) for item in segments),
            "motion": sum(len(item["motion_ids"]) for item in segments),
        },
        "warnings": warnings,
    }
