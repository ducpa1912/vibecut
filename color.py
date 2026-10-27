"""In-house colour looks: eight deterministic ``.cube`` LUTs plus planners.

The LUT files under ``assets/luts/`` are generated from the same numbers as
:data:`edits.COLOR_PRESETS`, so the slider look and the LUT look stay in step.
A LUT carries tone and colour only (exposure, contrast, saturation,
temperature); vignette, grain and sharpen stay as ffmpeg filters.

Nothing here starts ffmpeg or touches the network. ``ensure_luts`` is the only
writer, and it rewrites a file only when the bytes differ.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import edits

LUT_SIZE = 17
LUT_DIR = Path(__file__).resolve().parent / "assets" / "luts"
# ``none`` has no LUT: identity is not a look.
LUT_NAMES: tuple[str, ...] = tuple(
    name for name in edits.COLOR_PRESETS if name != "none"
)
TONAL_KEYS = ("exposure", "contrast", "saturation", "temperature")
SPATIAL_KEYS = ("vignette", "grain", "sharpen")


class ColorError(ValueError):
    """A colour preset or LUT asset is invalid."""

    status_code = 422


def preset_names() -> tuple[str, ...]:
    return LUT_NAMES


def _preset(name: object) -> str:
    value = str(name or "").strip().lower().replace("-", "_")
    if value not in edits.COLOR_PRESETS:
        raise ColorError(
            "Unknown colour preset; use one of: "
            + ", ".join(sorted(edits.COLOR_PRESETS))
            + "."
        )
    return value


def _clamp(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


def _look(rgb: tuple[float, float, float], numbers: dict[str, float]) -> tuple[float, float, float]:
    """Apply the tonal part of a preset to one normalized RGB triple."""
    red, green, blue = rgb
    luma = 0.2126 * red + 0.7152 * green + 0.0722 * blue
    saturation = 1.0 + float(numbers.get("saturation") or 0.0)
    red = luma + (red - luma) * saturation
    green = luma + (green - luma) * saturation
    blue = luma + (blue - luma) * saturation
    contrast = 1.0 + float(numbers.get("contrast") or 0.0)
    exposure = float(numbers.get("exposure") or 0.0) * 0.5
    red = (red - 0.5) * contrast + 0.5 + exposure
    green = (green - 0.5) * contrast + 0.5 + exposure
    blue = (blue - 0.5) * contrast + 0.5 + exposure
    temperature = float(numbers.get("temperature") or 0.0) * 0.08
    red += temperature
    blue -= temperature
    return _clamp(red), _clamp(green), _clamp(blue)


def lut_text(name: object) -> str:
    """Return the exact ``.cube`` text for one preset."""
    preset = _preset(name)
    if preset == "none":
        raise ColorError("The none preset has no LUT.")
    numbers = dict(edits.COLOR_PRESETS[preset])
    lines = [
        f'TITLE "{preset}"',
        f"LUT_3D_SIZE {LUT_SIZE}",
        "DOMAIN_MIN 0.0 0.0 0.0",
        "DOMAIN_MAX 1.0 1.0 1.0",
    ]
    step = 1.0 / (LUT_SIZE - 1)
    # .cube data runs blue slowest and red fastest.
    for blue_index in range(LUT_SIZE):
        blue = blue_index * step
        for green_index in range(LUT_SIZE):
            green = green_index * step
            for red_index in range(LUT_SIZE):
                red = red_index * step
                out = _look((red, green, blue), numbers)
                lines.append(f"{out[0]:.6f} {out[1]:.6f} {out[2]:.6f}")
    return "\n".join(lines) + "\n"


def lut_path(name: object) -> Path:
    preset = _preset(name)
    if preset == "none":
        raise ColorError("The none preset has no LUT.")
    return LUT_DIR / f"{preset}.cube"


def lut_bytes(name: object) -> bytes:
    return lut_text(name).encode("utf-8")


def lut_hash(name: object) -> str:
    return hashlib.sha256(lut_bytes(name)).hexdigest()[:32]


def lut_asset(name: object) -> dict:
    """Return the Edit ``color.lut`` reference for one preset."""
    path = lut_path(name)
    digest = lut_hash(name)
    try:
        on_disk = hashlib.sha256(path.read_bytes()).hexdigest()[:32]
    except OSError as exc:
        raise ColorError(
            f"LUT asset is missing: {path.name}. Run color.ensure_luts()."
        ) from exc
    if on_disk != digest:
        raise ColorError(
            f"LUT asset does not match its generator: {path.name}. "
            "Run color.ensure_luts()."
        )
    return {"path": str(path), "hash": digest}


def ensure_luts(directory: str | Path | None = None) -> list[Path]:
    """Write missing or stale LUT files. Returns the paths that changed."""
    target = Path(directory) if directory is not None else LUT_DIR
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name in LUT_NAMES:
        path = target / f"{name}.cube"
        payload = lut_bytes(name)
        try:
            if path.is_file() and path.read_bytes() == payload:
                continue
        except OSError:
            pass
        path.write_bytes(payload)
        written.append(path)
    return written


def _overrides(value: dict | None) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ColorError("Colour overrides must be an object.")
    unknown = set(value) - {"lut", *edits.COLOR_PRESETS.get("none", {})}
    if unknown:
        raise ColorError(
            "Unknown colour keys: " + ", ".join(sorted(str(key) for key in unknown)) + "."
        )
    return dict(value)


def preset_plan(
    name: object,
    *,
    use_lut: bool = False,
    overrides: dict | None = None,
) -> dict:
    """Return a normalized colour plan for one preset.

    ``use_lut`` swaps the tonal sliders for the bundled ``.cube`` so the same
    look is not applied twice. Spatial sliders stay as filters.
    """
    preset = _preset(name)
    raw: dict[str, Any] = {"preset": preset}
    numbers = dict(edits.COLOR_PRESETS[preset])
    if use_lut and preset != "none":
        raw["lut"] = lut_asset(preset)
        for key in TONAL_KEYS:
            numbers[key] = 0.0
    raw.update(numbers)
    raw.update(_overrides(overrides))
    if use_lut and preset != "none" and "lut" not in raw:
        raw["lut"] = lut_asset(preset)
    try:
        return edits.normalize_color(raw)
    except edits.EditError as exc:
        raise ColorError(str(exc)) from exc


def as_lut(color: dict) -> dict:
    """Return one stored colour plan in LUT mode.

    The preset keeps its identity, the tonal sliders move into the LUT, and
    any creator slider overrides are preserved on top.
    """
    if not isinstance(color, dict):
        raise ColorError("color must be an object.")
    preset = _preset(color.get("preset") or "none")
    # Stored plans hold absolute values, so a tonal value cannot be told apart
    # from the preset's own number. Only spatial sliders survive the swap.
    overrides = {key: color[key] for key in SPATIAL_KEYS if key in color}
    return preset_plan(preset, use_lut=True, overrides=overrides)
