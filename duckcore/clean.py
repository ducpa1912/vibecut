"""Clean layers for DuckSuite.

Check finds one tracklet per real text block. This module turns those tracklets
into editable Clean layers: LaMa AI fill, explicit Blur, or excluded.
"""

from __future__ import annotations

import hashlib
from typing import Any

TEXT_KINDS = {"subtitle", "title", "lower_third", "credit", "screen_text"}
RISKY_KINDS = {"handle_or_logo", "watermark"}


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
        layers.append({
            "id": layer_id,
            "kind": "fill" if fill else "blur",
            "method": "lama" if fill else "",
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
    return layers


def merge_layers(existing: list[dict], fresh: list[dict]) -> list[dict]:
    by_id = {
        str(layer.get("id")): layer
        for layer in existing or []
        if isinstance(layer, dict) and layer.get("id")
    }
    merged = []
    for layer in fresh:
        previous = by_id.get(str(layer["id"]))
        if previous:
            layer = {
                **layer,
                "kind": previous.get("kind", layer["kind"]),
                "method": previous.get("method", layer["method"]),
                "enabled": previous.get("enabled", layer["enabled"]),
            }
        merged.append(layer)
    return merged


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
        return edit
    raise KeyError(layer_id)


def apply_report(edit: dict, report: dict) -> dict:
    fresh = layers_from_report(report)
    edit["clean"] = merge_layers(edit.get("clean") or [], fresh)
    return edit
