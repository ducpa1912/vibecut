"""Caption style presets shared by the API and the burner."""

from __future__ import annotations

from typing import Any

PRESETS: dict[str, dict[str, Any]] = {
    "clean": {
        "id": "clean",
        "font_scale": 0.042,
        "position": "bottom",
        "margin": 0.065,
        "background": 170,
        "radius": 0.012,
        "stroke": 2,
        "max_lines": 4,
    },
    "bold": {
        "id": "bold",
        "font_scale": 0.055,
        "position": "bottom",
        "margin": 0.075,
        "background": 220,
        "radius": 0.010,
        "stroke": 3,
        "max_lines": 3,
    },
    "minimal": {
        "id": "minimal",
        "font_scale": 0.036,
        "position": "bottom",
        "margin": 0.050,
        "background": 110,
        "radius": 0.008,
        "stroke": 1,
        "max_lines": 4,
    },
}
POSITIONS = ("bottom", "middle", "top")


def normalize(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        style = dict(PRESETS["clean"])
        preset = str(value.get("id") or value.get("preset") or "clean")
        style.update(PRESETS.get(preset, PRESETS["clean"]))
        style.update({key: value[key] for key in style if key in value})
        style["id"] = preset if preset in PRESETS else "clean"
        style["position"] = str(style.get("position") or "bottom")
        if style["position"] not in POSITIONS:
            style["position"] = "bottom"
        return style
    preset = str(value or "clean")
    return dict(PRESETS.get(preset, PRESETS["clean"]))
