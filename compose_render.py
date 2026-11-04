"""Pure Edit -> ffmpeg filter compiler.

``compile_edit`` turns one stored Edit into deterministic per-segment filter
strings and a flat overlay layer list. It never starts ffmpeg, probes media,
reads a render, or writes a file. Wave 2 wires the strings into
``render._segment``; this module is the contract they are tested against.

Stage order per segment (matches ROADMAP.md, Product contracts still in force)::

    source -> [clean] -> crop/reframe -> scale -> [motion] -> [colour]

Clean boxes use source coordinates. Graphics and caption boxes use output
coordinates. Motion is compiled after the output scale as a ``zoompan`` crop
window, so the same compiled string drives preview and export.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Iterable

import edits
import fx
import overlays
from textfill import mask as textfill_mask

SCHEMA_VERSION = 1
OUT_FPS = 30
CANVAS = dict(overlays.CANVAS)
MOTION_SHAKE_HZ = 7.0
# Edit renders sample a subpixel perspective crop window. The legacy plan
# path keeps the original zoompan chain so old golden strings stay valid.
EDIT_MOTION_ENGINE = "perspective"
MOTION_ENGINES = ("zoompan", "perspective")
LAYER_SKIN = "layers-v1"


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


def path_value(points: list[tuple[float, float]], at: float) -> float:
    """Linearly sample a keyframe path; the render crop path uses this too."""
    if at <= points[0][0]:
        return points[0][1]
    for index in range(len(points) - 1):
        t0, v0 = points[index]
        t1, v1 = points[index + 1]
        if at <= t1:
            span = max(1e-6, t1 - t0)
            return v0 + (v1 - v0) * max(0.0, min(1.0, (at - t0) / span))
    return points[-1][1]


def path_expression(points: list[tuple[float, float]]) -> str:
    """Compile keyframes to one ffmpeg ``t`` expression with cosine easing."""
    expression = f"{points[-1][1]:.3f}"
    for index in range(len(points) - 2, -1, -1):
        t0, v0 = points[index]
        t1, v1 = points[index + 1]
        span = max(1e-6, t1 - t0)
        segment = (
            f"{v0:.3f}+({v1 - v0:.3f})*"
            f"(1-cos(PI*(t-{t0:.3f})/{span:.6f}))/2"
        )
        expression = f"if(lt(t,{t1:.3f}),{segment},{expression})"
    return f"if(lt(t,{points[0][0]:.3f}),{points[0][1]:.3f},{expression})"


def _canvas_size(
    aspect: str,
    size: tuple[int, int] | None,
) -> tuple[int, int]:
    if size is None:
        return _target_size(aspect)
    try:
        width = int(size[0])
        height = int(size[1])
    except (TypeError, ValueError, IndexError) as exc:
        raise ComposeInputError("size must be a (width, height) pair.") from exc
    if width < 2 or height < 2 or width % 2 or height % 2:
        raise ComposeInputError("size must contain positive even integers.")
    return width, height


def _source_dimensions(
    aspect: str,
    source: dict | None,
    out_w: int,
    out_h: int,
) -> tuple[int, int, str]:
    try:
        width = int((source or {}).get("width") or 0)
        height = int((source or {}).get("height") or 0)
    except (TypeError, ValueError):
        width = height = 0
    if width > 1 and height > 1:
        return width, height, "source"
    return out_w, out_h, "nominal"


def _base_crop(
    width: int,
    height: int,
    aspect: str,
    cx: float,
    cy: float,
    zoom: float,
    out_w: int,
    out_h: int,
) -> dict:
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
        if kind in {"crop_guard", "fill"}:
            # A fill layer is not an ffmpeg filter: see _fill_plan.
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
        elif kind == "mosaic":
            label = f"cl{index}"
            cell_w = max(2, rect["w"] // 12)
            cell_h = max(2, rect["h"] // 12)
            filters.append(
                f"split=2[{label}a][{label}b];"
                f"[{label}b]crop={rect['w']}:{rect['h']}:{rect['x']}:{rect['y']},"
                f"scale=w='max(1,trunc(iw/{cell_w}))':h='max(1,trunc(ih/{cell_h}))':flags=neighbor,"
                f"scale=w=iw*{cell_w}:h=ih*{cell_h}:flags=neighbor[{label}c];"
                f"[{label}a][{label}c]overlay={rect['x']}:{rect['y']}"
                f"{_enable_suffix(expression)}"
            )
            applied.append(layer["id"])
        elif kind == "blur":
            label = f"cl{index}"
            # boxblur refuses a radius above half the plane's short side, and
            # 4:2:0 chroma planes are half size, so cap both per box.
            short = min(rect["w"], rect["h"])
            radius = max(0, min(int(layer.get("radius") or 24), short // 2 - 1))
            chroma = max(0, min(radius, short // 4 - 1))
            filters.append(
                f"split=2[{label}a][{label}b];"
                f"[{label}b]crop={rect['w']}:{rect['h']}:{rect['x']}:{rect['y']},"
                f"boxblur=luma_radius={radius}:luma_power=2:"
                f"chroma_radius={chroma}:chroma_power=2[{label}c];"
                f"[{label}a][{label}c]overlay={rect['x']}:{rect['y']}"
                f"{_enable_suffix(expression)}"
            )
            applied.append(layer["id"])
        elif kind == "delogo":
            # Interpolate from the box border. Keep the box one pixel inside
            # the frame: delogo reads the surrounding ring.
            x = max(1, min(width - 3, rect["x"]))
            y = max(1, min(height - 3, rect["y"]))
            w = max(2, min(width - x - 1, rect["w"]))
            h = max(2, min(height - y - 1, rect["h"]))
            if w < 2 or h < 2:
                warnings.append({
                    "code": "clean_region_too_small",
                    "message": f"Clean layer {layer['id']} is too small to remove.",
                    "layer_id": layer["id"],
                })
                continue
            filters.append(
                f"delogo=x={x}:y={y}:w={w}:h={h}"
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


def _fill_plan(
    clean: list[dict],
    start: float,
    end: float,
    *,
    crop: dict | None = None,
    source_width: int | None = None,
    source_height: int | None = None,
    aspect: str = "",
    skip_hidden: bool = False,
) -> tuple[dict | None, list[dict]]:
    """Active AI fill layers of one segment, for the render's pre-pass.

    One method runs per segment: the topmost active layer's. The list is
    ordered by ``z`` (then id), so a mixed beat still has one deterministic
    engine and the layer the viewer sees on top decides it. With
    ``skip_hidden``, a layer fully outside the crop is left out: nobody would
    see the fill, and the layer itself stays in the Edit. Returns
    (plan, warnings).
    """
    def visible(layer: dict) -> bool:
        if not skip_hidden or not crop or not source_width or not source_height:
            return True
        return _intersects(
            _box_rect(layer["box"], source_width, source_height, even=False),
            crop,
        )

    def on_beat(layer: dict) -> bool:
        # The same time margin the fill uses (textfill.mask.layer_windows), so
        # text just outside a detected range is also caught on the next beat.
        margin = textfill_mask.DETECTED_TIME_MARGIN if layer.get("tracklet_id") else 0.0
        ranges = [
            {"start": float(item["start"]) - margin, "end": float(item["end"]) + margin}
            for item in layer.get("ranges") or []
        ]
        return _active_window({**layer, "ranges": ranges}, start, end)[0]

    active = sorted(
        (
            layer for layer in clean
            if layer["kind"] == "fill"
            and on_beat(layer)
            and visible(layer)
        ),
        key=lambda layer: (int(layer.get("z") or 0), str(layer.get("id") or "")),
    )
    if not active:
        return None, []
    method = active[-1].get("method") or edits.FILL_METHODS[0]
    warnings = []
    if any((layer.get("method") or method) != method for layer in active):
        warnings.append({
            "code": "fill_method_mixed",
            "message": (
                "Fill layers on one beat use different engines; "
                f"{method.upper()} fills them all."
            ),
        })
    def source_mask(layer: dict) -> dict | None:
        mask = layer.get("mask")
        if not mask or not crop or not source_width or not source_height:
            return None
        if isinstance(mask, dict):
            strokes = mask.get("strokes") or []
            space = str(mask.get("space") or "output")
            mask_aspect = str(mask.get("aspect") or "").strip()
            if space != "source" and mask_aspect and mask_aspect != str(aspect or ""):
                # An old mask saved on the cropped picture of another shape;
                # using it would fill the wrong pixels. Fall back to the box.
                # Source-space masks stay on the video whatever the crop.
                return None
        else:
            strokes = [{"r": 0.025, "points": mask}]
            space = "output"
        out_strokes = []
        for stroke in strokes:
            try:
                radius = float((stroke or {}).get("r", 0.02))
            except (TypeError, ValueError):
                radius = 0.02
            points = []
            for point in (stroke or {}).get("points") or []:
                try:
                    x = float(point.get("x", 0.0))
                    y = float(point.get("y", 0.0))
                except (TypeError, ValueError):
                    continue
                if space == "output":
                    sx = (float(crop["x"]) + x * float(crop["w"])) / source_width
                    sy = (float(crop["y"]) + y * float(crop["h"])) / source_height
                    sr = radius * float(crop["w"]) / source_width
                else:
                    sx, sy, sr = x, y, radius
                if sx < 0.0 or sx > 1.0 or sy < 0.0 or sy > 1.0:
                    continue
                points.append({"x": sx, "y": sy})
            if points:
                out_strokes.append({
                    "id": f"st{len(out_strokes) + 1}",
                    "r": max(0.002, min(0.2, sr)),
                    "points": points,
                })
        return {"space": "source", "strokes": out_strokes} if out_strokes else None

    return {
        "method": method,
        "ids": [layer["id"] for layer in active],
        "layers": [
            {
                "id": layer["id"],
                "box": dict(layer["box"]),
                "ranges": [dict(item) for item in layer.get("ranges") or []],
                **({"mask": source_mask(layer)} if source_mask(layer) else {}),
                **({"tracklet_id": layer["tracklet_id"]} if layer.get("tracklet_id") else {}),
            }
            for layer in active
        ],
    }, warnings


def _motion_filter(
    motion: dict,
    *,
    out_start: float,
    out_end: float,
    segment_frames: int,
    out_w: int,
    out_h: int,
    fps: int = OUT_FPS,
) -> str | None:
    """Compile one motion layer for one segment, or ``None``."""
    if motion.get("hidden"):
        return None
    motion_start = float(motion["start"])
    motion_end = float(motion["end"])
    if motion_end <= out_start + 1e-6 or motion_start >= out_end - 1e-6:
        return None
    local_start = max(0.0, motion_start - out_start)
    local_end = min(out_end - out_start, motion_end - out_start)
    first = _clamp_int(int(round(local_start * fps)), 0, segment_frames - 1)
    last = _clamp_int(int(round(local_end * fps)), first + 1, segment_frames)
    active = max(1, last - first)
    kind = motion["kind"]
    amount = float(motion["amount"])
    ramp_frames = max(1, int(round(float(motion.get("ramp") or 0.0) * fps)))
    if kind == "shake":
        seed = int(motion.get("seed") or 0)
        phase = (seed % 360) * math.pi / 180.0
        dx = max(1, int(round(amount * out_w)))
        dy = max(1, int(round(amount * out_h)))
        zoom = 1.0 + 2.0 * max(dx, dy) / max(1, min(out_w, out_h))
        gate = f"between(on,{first},{last})"
        x_expr = (
            f"(iw-iw/zoom)/2+{dx}*sin(2*PI*{MOTION_SHAKE_HZ:.3f}*on/"
            f"{fps}+{phase:.3f})*{gate}"
        )
        y_expr = (
            f"(ih-ih/zoom)/2+{dy}*cos(2*PI*{MOTION_SHAKE_HZ:.3f}*on/"
            f"{fps}+{phase:.3f})*{gate}"
        )
        return (
            f"zoompan=z='{zoom:.3f}':x='{x_expr}':y='{y_expr}':"
            f"d=1:s={out_w}x{out_h}:fps={fps}"
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
        f"y='ih/2-(ih/zoom/2)':d=1:s={out_w}x{out_h}:fps={fps}"
    )


def _frame_path_expression(points: list[tuple[float, float]], fps: int = OUT_FPS) -> str:
    """Compile a seconds keyframe path for filters that expose ``on`` only."""
    expression = path_expression(points)
    return re.sub(r"\bt\b", f"(on/{fps})", expression)


def _motion_perspective_filter(
    motion: dict,
    *,
    out_start: float,
    out_end: float,
    segment_frames: int,
    out_w: int,
    out_h: int,
    fps: int = OUT_FPS,
) -> str | None:
    """Compile motion as a subpixel perspective crop window.

    ``zoompan`` rounds its crop origin to a whole output pixel, which makes a
    slow push step by about a pixel per frame. ``perspective`` evaluates its
    corners per frame with cubic interpolation, so the same motion is smooth.
    """
    motion_start = float(motion["start"])
    motion_end = float(motion["end"])
    if motion_end <= out_start + 1e-6 or motion_start >= out_end - 1e-6:
        return None
    local_start = max(0.0, motion_start - out_start)
    local_end = min(out_end - out_start, motion_end - out_start)
    if local_end <= local_start + 1e-6:
        return None
    duration = segment_frames / fps
    first = _clamp_int(int(round(local_start * fps)), 0, segment_frames - 1)
    active = max(1, int(round(local_end * fps)) - first)
    kind = motion["kind"]
    amount = float(motion["amount"])
    ramp = max(1, int(round(float(motion.get("ramp") or 0.0) * fps)))
    if kind == "shake":
        seed = int(motion.get("seed") or 0)
        phase = (seed % 360) * math.pi / 180.0
        dx = max(1.0, amount * out_w)
        dy = max(1.0, amount * out_h)
        zoom = 1.0 + 2.2 * max(dx, dy) / max(1, min(out_w, out_h))
        gate = f"between(on,{first},{first + active})"
        z_expr = f"if({gate},{zoom:.4f},1.000)"
        dx_expr = (
            f"{dx:.3f}*sin(2*PI*{MOTION_SHAKE_HZ:.3f}*on/{fps}+"
            f"{phase:.3f})*{gate}"
        )
        dy_expr = (
            f"{dy:.3f}*cos(2*PI*{MOTION_SHAKE_HZ:.3f}*on/{fps}+"
            f"{phase:.3f})*{gate}"
        )
    else:
        if kind == "snap_zoom":
            z_expr = f"if(lt(on,{first}),1.000,{1.0 + amount:.4f})"
        else:
            start_seconds = first / fps
            points: list[tuple[float, float]] = [
                (0.0 if start_seconds <= 0.0005 else round(start_seconds, 3), 1.0),
            ]
            end_frame = first + active
            if kind == "punch_in":
                end_frame = min(first + ramp, first + active)
            end_seconds = end_frame / fps
            if end_seconds > points[-1][0] + 0.0005:
                points.append((round(end_seconds, 3), 1.0 + amount))
            if duration > end_seconds + 0.0005:
                points.append((round(duration, 3), 1.0 + amount))
            z_expr = _frame_path_expression(points, fps)
        dx_expr = "0"
        dy_expr = "0"
    center_x = f"((W-W/({z_expr}))/2)"
    center_y = f"((H-H/({z_expr}))/2)"
    left = f"({center_x}+{dx_expr})"
    right = f"(W-{center_x}+{dx_expr})"
    top = f"({center_y}+{dy_expr})"
    bottom = f"(H-{center_y}+{dy_expr})"
    return (
        f"perspective=x0='{left}':y0='{top}':x1='{right}':y1='{top}':"
        f"x2='{left}':y2='{bottom}':x3='{right}':y3='{bottom}':"
        f"interpolation=cubic:eval=frame"
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
    # The track's own outline width (1920-tall units; 0 means none), font and
    # a bold default weight reach the renderer; they used to be dropped.
    overlay_style["stroke_width"] = max(0.0, min(20.0, stroke_width))
    overlay_style["weight"] = 700
    font = str(style.get("font") or "").strip()
    if font:
        overlay_style["font"] = font[:200]
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


def _graphic_layers(edit: dict, warnings: list[dict]) -> list[dict]:
    layers: list[dict] = []
    for item in edit.get("graphics") or []:
        if item.get("hidden"):
            continue
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
                **({"video": dict(item["video"])} if item.get("video") else {}),
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
                if item["kind"] == "sticker":
                    resolved = _sticker_asset_path(item, warnings)
                    if resolved is None:
                        continue
                    value["asset_path"] = resolved
            layers.append(value)
    return layers


def _stuck_rect(video: dict, crop: dict, width: int, height: int) -> dict:
    """A layer's source box in one beat's output frame. It may leave the frame."""
    box = video["box"]
    crop_w = max(1.0, float(crop["w"]))
    crop_h = max(1.0, float(crop["h"]))
    return {
        "x": round((float(box["x"]) * width - float(crop["x"])) / crop_w, 6),
        "y": round((float(box["y"]) * height - float(crop["y"])) / crop_h, 6),
        "w": round(float(box["w"]) * width / crop_w, 6),
        "h": round(float(box["h"]) * height / crop_h, 6),
    }


def _stuck_style(style: dict, scale: float) -> dict:
    """The layer's text style at this beat's zoom."""
    out = dict(style)
    for key in ("size", "stroke_width"):
        if isinstance(out.get(key), (int, float)):
            out[key] = round(float(out[key]) * scale, 3)
    return out


def _stuck_pieces(layer: dict, beats: list[dict], warnings: list[dict]) -> list[dict]:
    """One timed piece of a layer per beat, placed on that beat's video.

    The output picture clips each piece, so nothing is cut or rewrapped at the
    crop edge. A piece on a beat with motion carries that beat's own motion
    filters, so it moves exactly as the video does. Beats with the same crop and
    no motion share a piece, so the layer is not redrawn at each cut.
    """
    video = layer["video"]
    base = {key: value for key, value in layer.items() if key != "video"}
    pieces: list[dict] = []
    hidden = 0
    for beat in beats:
        start = max(float(layer["start"]), beat["start"])
        end = min(float(layer["end"]), beat["end"])
        if end <= start + 1e-6:
            continue
        crop = beat["crop"]
        if crop is None:
            # A blank card has no video to stick to.
            rect, style = dict(layer["rect"]), dict(layer["style"])
        else:
            rect = _stuck_rect(video, crop, beat["width"], beat["height"])
            if (
                rect["x"] + rect["w"] <= 0 or rect["y"] + rect["h"] <= 0
                or rect["x"] >= 1 or rect["y"] >= 1
            ):
                hidden += 1
                continue
            scale = float(video["crop_h"]) / (float(crop["h"]) / beat["height"])
            style = _stuck_style(layer["style"], scale)
        previous = pieces[-1] if pieces else None
        if (
            previous is not None and not beat["motion"] and "motion" not in previous
            and previous["rect"] == rect and previous["style"] == style
            and abs(previous["end"] - start) < 1e-6
        ):
            previous["end"] = round(end, 6)
            continue
        piece = {
            **base,
            "id": f"{layer['id']}~{len(pieces) + 1}",
            "parent_id": layer["id"],
            "start": round(start, 6),
            "end": round(end, 6),
            "box": {"w": rect["w"], "h": rect["h"]},
            "rect": rect,
            "style": style,
            "stuck": True,
        }
        if beat["motion"]:
            piece["motion"] = {
                "filters": list(beat["motion"]),
                "start": round(beat["start"], 6),
                "frames": beat["frames"],
            }
        pieces.append(piece)
    if hidden:
        warnings.append({
            "code": "layer_hidden_by_crop",
            "message": (
                f"Text {layer['id']} sits outside the crop on {hidden} beat(s). "
                "It stays in the Edit and is hidden there."
            ),
            "layer_id": layer["id"],
        })
    return pieces


def _stick_to_beats(layers: list[dict], beats: list[dict], warnings: list[dict]) -> list[dict]:
    if not any(layer.get("video") for layer in layers):
        return layers
    out: list[dict] = []
    for layer in layers:
        if layer.get("video"):
            out.extend(_stuck_pieces(layer, beats, warnings))
        else:
            out.append(layer)
    return out


def _sticker_asset_path(item: dict, warnings: list[dict]) -> str | None:
    """Resolve a sticker's bundled PNG, refusing a different asset version."""
    asset = item.get("asset") or {}
    asset_id = str(asset.get("id") or "")
    try:
        path = fx.sticker_path(asset_id)
        digest = fx.sticker_file_hash(asset_id)
    except fx.FxError:
        warnings.append({
            "code": "sticker_unavailable",
            "message": f"Sticker asset {asset_id or '?'} is not bundled; layer skipped.",
            "layer_id": item["id"],
        })
        return None
    if digest != str(asset.get("hash") or "").lower():
        warnings.append({
            "code": "sticker_hash_mismatch",
            "message": (
                f"Sticker {asset_id} no longer matches the Edit's asset hash; "
                "layer skipped."
            ),
            "layer_id": item["id"],
        })
        return None
    return str(path)


# ---------------------------------------------------------------- layers


def _layer_raster(layer: dict, out_w: int, out_h: int, fps: int = OUT_FPS) -> dict:
    """Describe how the renderer caches this layer's pixels."""
    animated = layer["type"] == "fx" and layer["kind"] == "progress_bar"
    duration = max(0.0, float(layer["end"]) - float(layer["start"]))
    frames = (
        max(1, int(math.ceil(duration * fps - 1e-6)))
        if animated else 1
    )
    payload = {
        "skin": LAYER_SKIN,
        "type": layer["type"],
        "kind": layer["kind"],
        "text": layer.get("text") or "",
        "rect": layer.get("rect"),
        "style": layer.get("style") or {},
        "color": layer.get("color"),
        "thickness": layer.get("thickness"),
        "opacity": layer.get("opacity", 1.0),
        "out": [int(out_w), int(out_h)],
        "fps": fps,
        "mode": "sequence" if animated else "static",
        "frames": frames,
    }
    # Asset keys stay conditional so existing text and progress-bar rasters
    # keep their exact hashes. The asset id + content hash identify a sticker;
    # its absolute path does not, so a moved install keeps the same hash.
    if layer.get("asset"):
        payload["asset"] = layer["asset"]
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"),
    ).hexdigest()[:24]
    return {
        "mode": "sequence" if animated else "static",
        "frames": frames,
        "fps": fps,
        "hash": "lyh_" + digest,
    }


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
            end = float(
                end if end is not None
                else start + float(raw.get("dur") or raw.get("duration") or 0.0)
            )
        except (TypeError, ValueError) as exc:
            raise ComposeInputError(f"Clip {index + 1} has invalid times.") from exc
        if not math.isfinite(start) or not math.isfinite(end) or end <= start:
            raise ComposeInputError(f"Clip {index + 1} has invalid times.")
        item = {
            "index": index,
            "scene": raw.get("scene"),
            "role": str(raw.get("role") or "beat"),
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(end - start, 3),
        }
        if raw.get("kind") == "blank":
            item["kind"] = "blank"
            item["color"] = str(raw.get("color") or "#000000")
        elif raw.get("kind") == "freeze":
            item["kind"] = "freeze"
        elif raw.get("kind") == "file":
            item["kind"] = "file"
            item["asset"] = dict(raw.get("asset") or {})
        if raw.get("reverse") is True:
            item["reverse"] = True
        result.append(item)
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
    size: tuple[int, int] | None = None,
    motion_engine: str = "zoompan",
    beats: object = None,
    fps: int = OUT_FPS,
) -> dict:
    """Compile one Edit. Pure: no media access and no ffmpeg call.

    ``size`` compiles for a draft or proxy canvas. ``motion_engine`` selects
    ``zoompan`` (legacy plans) or ``perspective`` (subpixel Edit renders).
    ``beats`` accepts ``audio.beat_grid``'s dict or a plain list of seconds;
    motion and graphic boundaries inside ±120 ms move onto the nearest beat.
    """
    try:
        normalized = edits.normalize_edit(edit)
    except edits.EditError as exc:
        raise ComposeError(str(exc)) from exc
    beat_list = fx.beat_times(beats)
    if beat_list:
        # Snap a copy; the stored Edit and its hash never change.
        normalized = {
            **normalized,
            "motion": fx.snap_motion(normalized["motion"], beat_list),
            "graphics": fx.snap_graphics(normalized["graphics"], beat_list),
        }
    fps = int(fps)
    if fps not in (24, 30, 60):
        raise ComposeInputError("fps must be 24, 30 or 60.")
    motion_engine = str(motion_engine or "zoompan").strip().lower()
    if motion_engine not in MOTION_ENGINES:
        raise ComposeInputError(
            "motion_engine must be one of: " + ", ".join(MOTION_ENGINES) + "."
        )
    story_clips = _clips(clips)
    aspect = normalized["aspect"]
    out_w, out_h = _canvas_size(aspect, size)
    width, height, dimensions_source = _source_dimensions(
        aspect, source, out_w, out_h,
    )
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
    stick_beats: list[dict] = []
    out_cursor = 0.0
    for clip in story_clips:
        frames = max(1, int(round(float(clip["duration"]) * fps)))
        duration = frames / fps
        segment_out_start = out_cursor
        segment_out_end = out_cursor + duration
        out_cursor = segment_out_end
        if clip.get("kind") == "blank":
            segments.append({
                "index": clip["index"],
                "scene": None,
                "blank": True,
                "blank_color": str(clip.get("color") or "#000000"),
                "role": clip.get("role") or "beat",
                "start": 0.0,
                "end": duration,
                "duration": round(duration, 6),
                "frames": frames,
                "out_start": round(segment_out_start, 3),
                "out_end": round(segment_out_end, 3),
                "crop": {"x": 0, "y": 0, "w": out_w, "h": out_h},
                "crop_path_ref": None,
                "clean_ids": [],
                "fill": None,
                "motion_ids": [],
                "motion_engine": "none",
                "pre_filters": [],
                "pre_filter": "",
                "crop_filter": "",
                "scale_filter": "",
                "post_filters": [],
                "post_filter": "",
                "filter": "",
            })
            stick_beats.append({
                "start": segment_out_start, "end": segment_out_end, "crop": None,
                "width": out_w, "height": out_h, "motion": [], "frames": frames,
            })
            continue
        asset = clip.get("asset") if clip.get("kind") == "file" else None
        scene = scene_map.get(str(clip.get("scene")))
        clip_width = int((asset or {}).get("width") or width)
        clip_height = int((asset or {}).get("height") or height)
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
        crop = _base_crop(clip_width, clip_height, aspect, cx, cy, zoom, out_w, out_h)
        clean_warnings: list[dict] = []
        clean_filter_list: list[str] = []
        clean_ids: list[str] = []
        skipped: list[dict] = []
        fill_plan = None
        fill_warnings: list[dict] = []
        if not asset:
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
            fill_plan, fill_warnings = _fill_plan(
                normalized["clean"], clip["start"], clip["end"],
                crop=crop, source_width=width, source_height=height,
                aspect=str(normalized.get("aspect") or ""),
                skip_hidden=not reframe.get("crop_path_ref"),
            )
        warnings.extend(clean_warnings)
        warnings.extend({
            **item,
            "segment": clip["index"],
        } for item in skipped + fill_warnings)

        pre_filter = ",".join(clean_filter_list)
        crop_filter = f"crop={crop['w']}:{crop['h']}:{crop['x']}:{crop['y']}"
        motion_filters: list[str] = []
        motion_ids: list[str] = []
        for motion in normalized["motion"]:
            compile_motion = (
                _motion_perspective_filter
                if motion_engine == "perspective"
                else _motion_filter
            )
            compiled = compile_motion(
                motion,
                out_start=segment_out_start,
                out_end=segment_out_end,
                segment_frames=frames,
                out_w=out_w,
                out_h=out_h,
                fps=fps,
            )
            if compiled:
                motion_filters.append(compiled)
                motion_ids.append(motion["id"])
        color_filters = _color_filters(normalized["color"])
        scale_filter = f"scale={out_w}:{out_h}:flags=lanczos"
        post_filter = ",".join(motion_filters + color_filters)
        chain = []
        if pre_filter:
            chain.append(pre_filter)
        output = normalized.get("output") or {}
        strength = float(output.get("strength") or 0.5)
        if output.get("stabilize"):
            radius = max(4, min(64, int(round(8 + strength * 40))))
            chain.extend([
                f"deshake=rx={radius}:ry={radius}:edge=mirror",
            ])
        if output.get("optical_flow"):
            chain.append(
                f"minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:vsbmc=1"
            )
        chain.extend([crop_filter, scale_filter, "setsar=1", f"fps={fps}", "format=yuv420p"])
        if post_filter:
            chain.append(post_filter)
        segments.append({
            "index": clip["index"],
            "scene": clip["scene"],
            "role": clip.get("role") or "beat",
            "reverse": bool(clip.get("reverse")),
            "freeze": bool(clip.get("kind") == "freeze"),
            **({"file": asset["path"], "asset": asset} if asset else {}),
            "start": clip["start"],
            "end": clip["start"] + duration,
            "duration": round(duration, 6),
            "frames": frames,
            "out_start": round(segment_out_start, 3),
            "out_end": round(segment_out_end, 3),
            "crop": crop,
            "crop_path_ref": reframe.get("crop_path_ref"),
            "clean_ids": clean_ids,
            "fill": fill_plan,
            "motion_ids": motion_ids,
            "motion_engine": motion_engine if motion_filters else "none",
            "pre_filters": clean_filter_list,
            "pre_filter": pre_filter,
            "crop_filter": crop_filter,
            "scale_filter": scale_filter,
            "post_filters": motion_filters + color_filters,
            "post_filter": post_filter,
            "filter": ",".join(chain),
        })
        stick_beats.append({
            "start": segment_out_start, "end": segment_out_end, "crop": crop,
            "width": clip_width, "height": clip_height,
            # A zoompan chain changes the stream it runs on, so only the
            # perspective engine can be repeated on a layer.
            "motion": motion_filters if motion_engine == "perspective" else [],
            "frames": frames,
        })

    graphic_layers = _stick_to_beats(
        _graphic_layers(normalized, warnings), stick_beats, warnings,
    )
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
        layer["raster"] = _layer_raster(layer, out_w, out_h, fps)

    return {
        "schema_version": SCHEMA_VERSION,
        "renderer_version": normalized["renderer_version"],
        "edit_id": normalized["id"],
        "edit_hash": normalized["hash"],
        "edit_version": normalized["version"],
        "aspect": aspect,
        "canvas": {"w": out_w, "h": out_h},
        "fps": fps,
        "motion_engine": motion_engine,
        "source": {
            "width": width,
            "height": height,
            "dimensions_source": dimensions_source,
        },
        "segments": segments,
        "overlays": overlay_layers,
        "captions": caption_metadata,
        "beat_snap": {
            "enabled": bool(beat_list),
            "beats": len(beat_list),
            "window": fx.BEAT_WINDOW,
        },
        "counts": {
            "segments": len(segments),
            "overlays": len(overlay_layers),
            "clean": sum(len(item["clean_ids"]) for item in segments),
            "motion": sum(len(item["motion_ids"]) for item in segments),
        },
        "warnings": warnings,
    }
