"""Clean layers for DuckSuite.

Check finds one tracklet per real text block. This module turns those tracklets
into editable Clean layers: LaMa AI fill, explicit Blur, or excluded.
"""

from __future__ import annotations

import hashlib
from typing import Any

TEXT_KINDS = {"subtitle", "title", "lower_third", "credit", "screen_text"}
RISKY_KINDS = {"handle_or_logo", "watermark"}
# Mean change around a line, 0..255, measured by Check. Above this the picture
# under the text moves enough that a per-frame fill has to invent texture, so
# the layer is flagged for the user and reported before the render.
FILL_MOTION_LIMIT = 10.0
# A line this short has no calm neighbours to learn from, so a fill has nothing
# to rebuild the plate with. A flash of text is better hidden under Blur.
# Ranges reach a full reading back and a little forward (detect._run_range), so
# a line read once spans about 0.57 s and a line read twice about 0.82 s. The
# limit sits between them: one reading is a flash.
FILL_SHORT_SECONDS = 0.6


def _layer_id(tracklet: dict) -> str:
    raw = str(tracklet.get("id") or "").strip()
    if raw:
        return f"cl_{hashlib.sha1(raw.encode()).hexdigest()[:10]}"
    box = tracklet.get("box") or {}
    raw = f"{box.get('x')}:{box.get('y')}:{box.get('w')}:{box.get('h')}"
    return f"cl_{hashlib.sha1(raw.encode()).hexdigest()[:10]}"


def layers_from_report(report: dict, *, enabled: bool = True) -> list[dict]:
    layers = []
    seen: set[str] = set()
    for tracklet in report.get("tracklets") or []:
        if not isinstance(tracklet, dict):
            continue
        box = tracklet.get("box")
        ranges = [
            item for item in tracklet.get("ranges") or []
            if isinstance(item, dict)
            and float(item.get("end") or 0.0) > float(item.get("start") or 0.0)
        ]
        if not isinstance(box, dict) or not ranges:
            continue
        kind = str(tracklet.get("kind") or "screen_text")
        layer_id = _layer_id(tracklet)
        if layer_id in seen:
            continue
        seen.add(layer_id)
        fill = kind in TEXT_KINDS
        risky = kind in RISKY_KINDS
        fill_plan = tracklet.get("fill_plan") if isinstance(tracklet.get("fill_plan"), dict) else {}
        motion = fill_plan.get("motion")
        quality = "steady"
        if fill and motion is not None and float(motion or 0.0) > FILL_MOTION_LIMIT:
            quality = "moving"
        shown = sum(
            float(item.get("end") or 0.0) - float(item.get("start") or 0.0)
            for item in ranges
        )
        # A fill over a moving plate still beats Blur on real footage, so Fill
        # stays the default and the layer is flagged instead. A line that only
        # flashes on screen is the one case Blur wins: there is no calm frame
        # to rebuild from.
        use_fill = fill and shown >= FILL_SHORT_SECONDS
        layers.append({
            "id": layer_id,
            "kind": "fill" if use_fill else "blur",
            "method": "lama" if use_fill else "",
            "auto": True,
            "quality": quality,
            "motion": round(float(motion), 3) if motion is not None else None,
            "track": list(tracklet.get("track") or [])[:600],
            "large": bool(tracklet.get("large") or False),
            "fill_keys": fill_plan.get("keys"),
            "box": {
                "x": round(float(box.get("x") or 0.0), 6),
                "y": round(float(box.get("y") or 0.0), 6),
                "w": round(float(box.get("w") or 0.0), 6),
                "h": round(float(box.get("h") or 0.0), 6),
            },
            "ranges": [
                {"start": round(float(item.get("start") or 0.0), 3),
                 "end": round(float(item.get("end") or 0.0), 3)}
                for item in ranges
            ],
            "enabled": bool(enabled and not risky),
            "tracklet_id": str(tracklet.get("id") or ""),
            "tracklet_kind": kind,
            "text_sample": str(tracklet.get("text_sample") or "")[:160],
            "confidence": float(tracklet.get("confidence") or 0.0),
            "label": "Found text" if fill else "Handle or logo",
        })
    return _merge_stacked_titles(layers)


def _box_union(left: dict, right: dict) -> dict:
    x0 = min(float(left.get("x") or 0.0), float(right.get("x") or 0.0))
    y0 = min(float(left.get("y") or 0.0), float(right.get("y") or 0.0))
    x1 = max(float(left.get("x") or 0.0) + float(left.get("w") or 0.0),
             float(right.get("x") or 0.0) + float(right.get("w") or 0.0))
    y1 = max(float(left.get("y") or 0.0) + float(left.get("h") or 0.0),
             float(right.get("y") or 0.0) + float(right.get("h") or 0.0))
    return {
        "x": round(x0, 6),
        "y": round(y0, 6),
        "w": round(x1 - x0, 6),
        "h": round(y1 - y0, 6),
    }


def _ranges_overlap(left: list[dict], right: list[dict]) -> bool:
    for a in left:
        for b in right:
            if (float(a.get("start") or 0.0) < float(b.get("end") or 0.0)
                    and float(b.get("start") or 0.0) < float(a.get("end") or 0.0)):
                return True
    return False


def _merge_ranges(layers: list[dict]) -> list[dict]:
    rows = sorted(
        (
            (float(item.get("start") or 0.0), float(item.get("end") or 0.0))
            for layer in layers for item in layer.get("ranges") or []
        ),
    )
    merged: list[list[float]] = []
    for start, end in rows:
        if end <= start:
            continue
        if merged and start <= merged[-1][1] + 0.04:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [{"start": round(start, 3), "end": round(end, 3)} for start, end in merged]


def _merge_stacked_titles(layers: list[dict]) -> list[dict]:
    """Join stacked large title lines into one fill block.

    The detector tracks each OCR line separately. A two-line display title can
    leave its second line outside the first line's box, so Fill removes only
    half the title. Two large layers that overlap horizontally, touch
    vertically and share time are one block. Subtitles and small labels keep
    their own boxes.
    """
    merged: list[dict] = []
    for layer in layers:
        if layer.get("kind") != "fill" or not layer.get("large"):
            merged.append(layer)
            continue
        target = None
        for candidate in merged:
            if candidate.get("kind") != "fill" or not candidate.get("large"):
                continue
            box = layer.get("box") or {}
            other = candidate.get("box") or {}
            left = max(float(box.get("x") or 0.0), float(other.get("x") or 0.0))
            right = min(float(box.get("x") or 0.0) + float(box.get("w") or 0.0),
                        float(other.get("x") or 0.0) + float(other.get("w") or 0.0))
            across = max(0.0, right - left)
            narrow = max(1e-6, min(float(box.get("w") or 0.0), float(other.get("w") or 0.0)))
            gap = max(
                float(other.get("y") or 0.0) - (float(box.get("y") or 0.0) + float(box.get("h") or 0.0)),
                float(box.get("y") or 0.0) - (float(other.get("y") or 0.0) + float(other.get("h") or 0.0)),
            )
            if across / narrow >= 0.5 and gap <= 0.025 and _ranges_overlap(
                layer.get("ranges") or [], candidate.get("ranges") or [],
            ):
                target = candidate
                break
        if target is None:
            merged.append(layer)
            continue
        target["box"] = _box_union(target.get("box") or {}, layer.get("box") or {})
        target["ranges"] = _merge_ranges([target, layer])
        target["text_sample"] = " ".join(
            item for item in (target.get("text_sample"), layer.get("text_sample")) if item
        )[:160]
        target["large"] = True
        target["track"] = []
        target["fill_keys"] = None
        target["tracklet_id"] = f"{target.get('tracklet_id') or ''}+{layer.get('tracklet_id') or ''}"
    return merged


def merge_layers(existing: list[dict], fresh: list[dict]) -> list[dict]:
    by_id = {
        str(layer.get("id")): layer
        for layer in existing or []
        if isinstance(layer, dict) and layer.get("id")
    }
    merged = []
    for layer in fresh:
        previous = by_id.get(str(layer["id"]))
        if previous and previous.get("auto") is False:
            # The user picked Fill, Blur or Off for this line, so keep it. A
            # layer DuckSuite planned itself may be re-planned by a better rule.
            layer = {
                **layer,
                "kind": previous.get("kind", layer["kind"]),
                "method": previous.get("method", layer["method"]),
                "enabled": previous.get("enabled", layer["enabled"]),
                "auto": False,
            }
        merged.append(layer)
    return merged


def plan_summary(edit: dict) -> dict:
    """Counts of what Clean will do, for an honest message after a re-plan."""
    fill = blur = off = moving = mine = 0
    for layer in edit.get("clean") or []:
        if layer.get("enabled") is False:
            off += 1
        elif layer.get("kind") == "blur":
            blur += 1
        else:
            fill += 1
        if layer.get("quality") == "moving":
            moving += 1
        if layer.get("auto") is False:
            mine += 1
    return {"fill": fill, "blur": blur, "off": off, "moving": moving, "mine": mine}


def patch_layer(edit: dict, layer_id: str, action: str) -> dict:
    action = str(action or "").strip().lower()
    if action not in {"fill", "blur", "exclude"}:
        raise ValueError("Action must be fill, blur or exclude.")
    for layer in edit.get("clean") or []:
        if str(layer.get("id")) != layer_id:
            continue
        if action == "exclude":
            layer["enabled"] = False
        elif action == "blur":
            layer["enabled"] = True
            layer["kind"] = "blur"
            layer["method"] = ""
        else:
            layer["enabled"] = True
            layer["kind"] = "fill"
            layer["method"] = "lama"
        layer["auto"] = False
        return edit
    raise KeyError(layer_id)


def apply_report(edit: dict, report: dict) -> dict:
    fresh = layers_from_report(report)
    edit["clean"] = merge_layers(edit.get("clean") or [], fresh)
    return edit
