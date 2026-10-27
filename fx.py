"""Pure motion, graphic and beat-snap builders for the Edit layer catalogue.

Every helper returns a dict that :mod:`edits` accepts unchanged, so the editor,
the compiler and the renderer share one contract. Nothing here starts ffmpeg,
probes media, or touches the network.

Motion kinds map to the renderer's crop-window keyframes:
``punch_in``, ``snap_zoom``, ``push`` and ``shake``.

Graphic kinds map to the overlay pass: ``arrow``, ``circle``, ``underline``,
``progress_bar`` and ``sticker``. Emoji are bundled as sticker assets; no font
or platform emoji is required at render time.

Beat-snap moves layer boundaries onto the nearest beat inside a ±120 ms
window. It never invents a beat and never moves a layer outside the window.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable

import edits

BEAT_WINDOW = 0.120
MIN_MOTION_SPAN = 0.05
MIN_GRAPHIC_SPAN = 0.2

ASSET_DIR = Path(__file__).resolve().parent / "assets" / "stickers"

# In-house vector stickers, drawn at build time. ``id`` is the public asset id.
STICKERS: dict[str, str] = {
    "star": "star.png",
    "heart": "heart.png",
    "sparkle": "sparkle.png",
    "fire": "fire.png",
    "check": "check.png",
    "arrow_up": "arrow_up.png",
    "wow": "wow.png",
    "speech": "speech.png",
}

# A small, deterministic emoji set. The glyph is an editor label only: the
# render burns the bundled PNG, so output is identical on every machine.
EMOJI: dict[str, str] = {
    "⭐": "star",
    "🌟": "star",
    "❤️": "heart",
    "❤": "heart",
    "✨": "sparkle",
    "🔥": "fire",
    "✅": "check",
    "⬆️": "arrow_up",
    "⬆": "arrow_up",
    "😮": "wow",
    "💬": "speech",
}

MOTION_KINDS = edits.MOTION_KINDS
GRAPHIC_KINDS = edits.FX_KINDS


class FxError(ValueError):
    """A layer or asset cannot be built."""

    status_code = 422


# ---------------------------------------------------------------- stickers


def sticker_ids() -> tuple[str, ...]:
    return tuple(sorted(STICKERS))


def sticker_path(value: object) -> Path:
    """Resolve a sticker id (or emoji) to its bundled PNG path."""
    asset_id = sticker_id(value)
    return ASSET_DIR / STICKERS[asset_id]


def sticker_id(value: object) -> str:
    """Normalize a sticker id or emoji to one bundled sticker id."""
    text = str(value or "").strip()
    if not text:
        raise FxError("A sticker needs an asset id or an emoji.")
    candidate = EMOJI.get(text) or EMOJI.get(text.replace("\ufe0f", ""))
    if candidate is None:
        candidate = text.replace("\ufe0f", "").strip().lower().replace("-", "_")
    if candidate not in STICKERS:
        raise FxError(
            "Unknown sticker; use one of: " + ", ".join(sticker_ids()) + "."
        )
    return candidate


def sticker_file_hash(value: object) -> str:
    """Return the SHA-256 content hash of a bundled sticker."""
    path = sticker_path(value)
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise FxError(f"Sticker asset is missing: {path.name}.") from exc
    if not payload:
        raise FxError(f"Sticker asset is empty: {path.name}.")
    return hashlib.sha256(payload).hexdigest()[:32]


def sticker_asset(value: object) -> dict:
    """Return the Edit ``asset`` reference for a sticker id or emoji."""
    asset_id = sticker_id(value)
    return {"id": asset_id, "hash": sticker_file_hash(asset_id)}


# ---------------------------------------------------------------- motion


def _motion_layer(
    kind: str,
    start: float,
    end: float,
    *,
    amount: float | None = None,
    ramp: float | None = None,
    seed: int = 0,
    layer_id: str | None = None,
) -> dict:
    raw: dict[str, Any] = {
        "kind": kind,
        "start": start,
        "end": end,
        "seed": seed,
    }
    if amount is not None:
        raw["amount"] = amount
    if ramp is not None:
        raw["ramp"] = ramp
    if layer_id:
        raw["id"] = layer_id
    built = edits.normalize_motion([raw])[0]
    if not layer_id:
        # Let the final Edit assign the list-index id, so several builders can
        # be composed without colliding on ``mo01``.
        built.pop("id", None)
    return built


def motion(
    kind: object,
    start: float,
    end: float,
    *,
    amount: float | None = None,
    ramp: float | None = None,
    seed: int = 0,
    layer_id: str | None = None,
) -> dict:
    """Build one validated motion layer."""
    name = str(kind or "").strip().lower().replace("-", "_")
    if name not in MOTION_KINDS:
        raise FxError("motion kind must be one of: " + ", ".join(MOTION_KINDS) + ".")
    try:
        return _motion_layer(
            name, start, end,
            amount=amount, ramp=ramp, seed=seed, layer_id=layer_id,
        )
    except edits.EditError as exc:
        raise FxError(str(exc)) from exc


def punch_in(start: float, end: float, **kwargs: Any) -> dict:
    return motion("punch_in", start, end, **kwargs)


def snap_zoom(start: float, end: float, **kwargs: Any) -> dict:
    return motion("snap_zoom", start, end, **kwargs)


def push(start: float, end: float, **kwargs: Any) -> dict:
    return motion("push", start, end, **kwargs)


def shake(start: float, end: float, **kwargs: Any) -> dict:
    return motion("shake", start, end, **kwargs)


# ---------------------------------------------------------------- graphics


def _graphic_layer(raw: dict, layer_id: str | None = None) -> dict:
    try:
        built = edits.normalize_graphics([raw])[0]
    except edits.EditError as exc:
        raise FxError(str(exc)) from exc
    if not layer_id:
        # The final Edit assigns ids by list position; a builder alone would
        # otherwise always return ``fx01`` and collide when composed.
        built.pop("id", None)
    return built


def graphic(
    kind: object,
    start: float,
    end: float,
    *,
    box: dict | None = None,
    anchor: str | None = None,
    color: str | None = None,
    thickness: int | None = None,
    opacity: float | None = None,
    z: int | None = None,
    layer_id: str | None = None,
    asset: dict | None = None,
) -> dict:
    """Build one validated graphic FX layer."""
    name = str(kind or "").strip().lower().replace("-", "_")
    if name not in GRAPHIC_KINDS:
        raise FxError(
            "graphic kind must be one of: " + ", ".join(GRAPHIC_KINDS) + "."
        )
    raw: dict[str, Any] = {"type": "fx", "kind": name, "start": start, "end": end}
    if box is not None:
        raw["box"] = box
    if anchor is not None:
        raw["anchor"] = anchor
    if color is not None:
        raw["color"] = color
    if thickness is not None:
        raw["thickness"] = thickness
    if opacity is not None:
        raw["opacity"] = opacity
    if z is not None:
        raw["z"] = z
    if layer_id is not None:
        raw["id"] = layer_id
    if asset is not None:
        raw["asset"] = asset
    return _graphic_layer(raw, layer_id)


def arrow(start: float, end: float, **kwargs: Any) -> dict:
    return graphic("arrow", start, end, **kwargs)


def circle(start: float, end: float, **kwargs: Any) -> dict:
    return graphic("circle", start, end, **kwargs)


def underline(start: float, end: float, **kwargs: Any) -> dict:
    return graphic("underline", start, end, **kwargs)


def progress_bar(start: float, end: float, **kwargs: Any) -> dict:
    return graphic("progress_bar", start, end, **kwargs)


def sticker(
    value: object,
    start: float,
    end: float,
    *,
    asset: dict | None = None,
    **kwargs: Any,
) -> dict:
    """Build a sticker layer from a bundled id or emoji."""
    return graphic(
        "sticker", start, end, asset=asset or sticker_asset(value), **kwargs,
    )


def emoji(value: object, start: float, end: float, **kwargs: Any) -> dict:
    """Alias for :func:`sticker`; emoji resolve to bundled sticker PNGs."""
    return sticker(value, start, end, **kwargs)


# ---------------------------------------------------------------- beat snap


def beat_times(beats: object) -> list[float]:
    """Normalize a beat grid to sorted seconds.

    Accepts a list of numbers, a list of ``{"t"|"time"|"start"}`` dicts, or a
    grid dict such as ``audio.beat_grid``'s ``{"bpm", "beats"}``.
    """
    values: Iterable[Any]
    if beats is None:
        return []
    if isinstance(beats, dict):
        values = beats.get("beats") or beats.get("times") or ()
    elif isinstance(beats, (list, tuple)):
        values = beats
    else:
        return []
    result: list[float] = []
    for item in values:
        raw = item
        if isinstance(item, dict):
            raw = item.get("t", item.get("time", item.get("start")))
        try:
            number = float(raw)
        except (TypeError, ValueError):
            continue
        if number >= 0:
            result.append(round(number, 3))
    return sorted(result)


def beat_snap(
    value: float,
    beats: object,
    *,
    window: float = BEAT_WINDOW,
) -> float:
    """Move one time to the nearest beat inside ``window`` seconds."""
    times = beat_times(beats)
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise FxError("beat_snap needs a numeric time.") from exc
    if not times or window <= 0:
        return round(number, 3)
    nearest = min(times, key=lambda beat: abs(beat - number))
    if abs(nearest - number) <= window + 1e-9:
        return round(nearest, 3)
    return round(number, 3)


def snap_span(
    start: float,
    end: float,
    beats: object,
    *,
    window: float = BEAT_WINDOW,
    minimum: float = MIN_GRAPHIC_SPAN,
) -> tuple[float, float]:
    """Snap both edges of one span, keeping a usable duration."""
    original_end = round(float(end), 3)
    snapped_start = beat_snap(start, beats, window=window)
    snapped_end = beat_snap(end, beats, window=window)
    if snapped_end - snapped_start < minimum:
        snapped_end = round(max(original_end, snapped_start + minimum), 3)
    if snapped_end <= snapped_start:
        snapped_end = round(snapped_start + minimum, 3)
    return snapped_start, snapped_end


def snap_motion(
    layers: Iterable[dict],
    beats: object,
    *,
    window: float = BEAT_WINDOW,
) -> list[dict]:
    """Return motion layers with beat-snapped boundaries."""
    times = beat_times(beats)
    result: list[dict] = []
    for layer in layers:
        value = dict(layer)
        if times:
            value["start"], value["end"] = snap_span(
                value.get("start") or 0.0,
                value.get("end") or 0.0,
                times,
                window=window,
                minimum=MIN_MOTION_SPAN,
            )
        result.append(value)
    return result


def snap_graphics(
    layers: Iterable[dict],
    beats: object,
    *,
    window: float = BEAT_WINDOW,
) -> list[dict]:
    """Return graphic layers with beat-snapped boundaries."""
    times = beat_times(beats)
    result: list[dict] = []
    for layer in layers:
        value = dict(layer)
        if times and value.get("start") is not None and value.get("end") is not None:
            value["start"], value["end"] = snap_span(
                value.get("start"),
                value.get("end"),
                times,
                window=window,
                minimum=MIN_GRAPHIC_SPAN,
            )
        result.append(value)
    return result
