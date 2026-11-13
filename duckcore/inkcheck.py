"""Look for leftover text in a finished render, glyph by glyph, from pixels.

A glyph is leftover on an output frame when three things hold at once:

* the source shows that glyph on the matching frame (its strokes are there);
* the output still has those strokes;
* around the strokes the output is the source, untouched.

The third test is what makes this safe. A fill replaces the text with picture,
so the output cannot equal a source frame that shows text. A plate rim that the
fill redrew under a letter is an edge, but it is not the source's letter. So a
clean frame cannot be reported, and a frame nobody filled cannot be missed,
whatever range the layer had. Each glyph is judged alone: two letters left of
eleven are two hits, not a fifth of a line.

Output and source are lined up from the picture around the text, per clip, so
an edit that trims, reorders or rescales the video is checked the same way.

What it cannot see: text that no layer covers, and a line with no steady
strokes (a one-frame flash). Those lines are counted and reported as not
checked, never as clean.
"""

from __future__ import annotations

from pathlib import Path

import dataclasses
import hashlib
import json
import os
import zipfile

import numpy as np

from duckcore import ink as inkmod

# Seconds of output judged on each side of the line's real edges.
PAD = 0.5
# A glyph is in the source, or still in the output, at this share of its strokes.
SHOWN = inkmod.FADE
# Mean difference (0..255, worst channel) around a glyph's strokes between an
# untouched output frame and its source frame. Measured on the review project:
# re-encoding costs 9 to 13.4, a fill over text 30 or more.
SAME = 20.0
# Frames searched each way to line the output up with the source.
SLIDE = 3
# Above this mean difference around the text, output and source are not the
# same picture and nothing is concluded.
ALIGN_LIMIT = 30.0
FLICKER_LIMIT = 2.2


def search_rect(layer: dict, width: int, height: int,
                view: inkmod.View | None = None) -> inkmod.Rect:
    """Where a layer's strokes are looked for: its box and a margin.

    The OCR box is often a little tight; a clipped letter or an emoji at the
    end of the line still belongs to the line. ``width`` and ``height`` are the
    source's; with a ``view`` the box is carried into the output's pixels and
    cut to its frame, so a line the Cut crops away comes back empty.
    """
    box = layer.get("box") or {}
    x = float(box.get("x", 0.0)) * width
    y = float(box.get("y", 0.0)) * height
    w = float(box.get("w", 0.0)) * width
    h = float(box.get("h", 0.0)) * height
    side, top = 0.5 * h, 0.3 * h
    left, upper, right, lower = x - side, y - top, x + w + side, y + h + top
    out_w, out_h = width, height
    if view is not None:
        left, upper = view.point(left, upper)
        right, lower = view.point(right, lower)
        out_w, out_h = view.width, view.height
    x0 = max(0, int(left))
    y0 = max(0, int(upper))
    x1 = min(out_w, int(np.ceil(right)))
    y1 = min(out_h, int(np.ceil(lower)))
    return x0, y0, max(x0, x1), max(y0, y1)


def _clean_layers(edit: dict) -> list[dict]:
    return [
        layer for layer in edit.get("clean") or []
        if isinstance(layer, dict) and layer.get("enabled") is not False
        and layer.get("kind") in {"fill", "blur"}
    ]


def layer_inks(layer: dict, meta: dict, *, source: str | Path,
               size: "tuple[int, int] | inkmod.View | None" = None) -> tuple[list[inkmod.Ink], str]:
    """One ink for each range of a layer, and why there is none when there is none.

    ``size`` reads the source at another (width, height), or through the
    render's :class:`ink.View` (crop, pad, grade): the ink is then in those
    pixels, for a render that is not the source's picture.
    """
    width = int(meta.get("width") or 0)
    height = int(meta.get("height") or 0)
    fps = float(meta.get("fps") or 0.0)
    if width < 2 or height < 2 or fps <= 0:
        return [], "the video size is unknown"
    view = inkmod.as_view(size, (width, height))
    rect = search_rect(layer, width, height, view)
    if rect[2] - rect[0] < 4 or rect[3] - rect[1] < 4:
        whole = search_rect(layer, width, height)
        if view is not None and whole[2] - whole[0] >= 4 and whole[3] - whole[1] >= 4:
            return [], "the Cut leaves this line out of the frame"
        return [], "the box is empty"
    size = view
    out: list[inkmod.Ink] = []
    short = False
    try:
        for span in layer.get("ranges") or []:
            start = float(span.get("start") or 0.0)
            end = float(span.get("end") or 0.0)
            if end <= start:
                continue
            if inkmod.first_frame(end, fps) - inkmod.first_frame(start, fps) < inkmod.MIN_FRAMES:
                short = True
                continue
            built = inkmod.build(source, rect, start=start, end=end, fps=fps, size=size)
            if built is not None:
                out.append(built)
    except inkmod.InkError as exc:
        return [], f"the source could not be read ({exc})"
    if out:
        return out, ""
    if short:
        return [], f"it lasts under {inkmod.MIN_FRAMES} frames, too short to tell text from scenery"
    return [], "no steady strokes were found"


def _store_key(layer: dict, meta: dict, source: str | Path,
               size: "tuple[int, int] | inkmod.View | None") -> str:
    """What the stored ink depends on: the source, the size, and the layer."""
    stat = os.stat(source)
    payload = {
        "v": inkmod.STORE_VERSION,
        "source": [Path(source).name, stat.st_size, stat.st_mtime_ns],
        "size": (
            dataclasses.asdict(size) if isinstance(size, inkmod.View)
            else [int(size[0]), int(size[1])] if size
            else [int(meta.get("width") or 0), int(meta.get("height") or 0)]
        ),
        "fps": float(meta.get("fps") or 0.0),
        "layer": {
            "id": layer.get("id"),
            "box": layer.get("box"),
            "track": layer.get("track"),
            "mask": layer.get("mask"),
            "ink_rect": layer.get("ink_rect"),
            "ranges": layer.get("ranges") or [],
        },
    }
    return hashlib.sha1(
        json.dumps(payload, sort_keys=True, default=str).encode(),
    ).hexdigest()[:24]


def _save_field(payload: dict, name: str, value, index: int) -> None:
    """One field of ``ink.Ink``, written in a way ``_load_field`` reverses."""
    key = f"{name}_{index}"
    if name == "mask":
        payload[key] = np.asarray(value, dtype=bool)
    elif name == "rect":
        payload[key] = np.asarray(value, dtype=np.int32)
    elif name in {"first", "last"}:
        payload[key] = np.asarray(int(value), dtype=np.int64)
    elif name == "fps":
        payload[key] = np.asarray(float(value), dtype=np.float64)
    elif name == "settled":
        payload[key] = np.asarray(bool(value), dtype=bool)
    elif name in {"glyphs", "spans"}:
        payload[key] = np.asarray(value, dtype=np.int32).reshape(-1, 2)
    else:  # a new field needs a line here; the store test says so
        raise KeyError(name)


def _load_field(data, name: str, index: int):
    key = f"{name}_{index}"
    if name == "mask":
        return np.asarray(data[key], dtype=bool)
    if name == "rect":
        return tuple(int(value) for value in data[key])
    if name in {"first", "last"}:
        return int(data[key])
    if name == "fps":
        return float(data[key])
    if name == "settled":
        return bool(data[key])
    if name in {"glyphs", "spans"}:
        rows = np.asarray(data[key], dtype=np.int32)
        return tuple((int(a), int(b)) for a, b in rows.reshape(-1, 2))
    raise KeyError(name)


# Every field of ink.Ink. A new field must be added here and in _save_field and
# _load_field; tests/test_estimate_speed.py fails until it is.
STORE_FIELDS = ("mask", "rect", "first", "last", "fps", "settled", "glyphs", "spans")


def _save_ink(path: Path, inks: list[inkmod.Ink], reason: str) -> None:
    """Every field of every ink, so a stored line has its letters back."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    payload: dict = {"count": np.array(len(inks)), "reason": np.array(reason)}
    for index, item in enumerate(inks):
        for name in STORE_FIELDS:
            _save_field(payload, name, getattr(item, name), index)
    with open(temporary, "wb") as handle:
        np.savez_compressed(handle, **payload)
    temporary.replace(path)


def _load_ink(path: Path) -> tuple[list[inkmod.Ink], str] | None:
    """The stored inks, or None when the file is old, cut or unreadable."""
    try:
        with np.load(path, allow_pickle=False) as data:
            count = int(data["count"])
            if count <= 0:
                return [], str(data["reason"].item() or "")
            out = []
            for index in range(count):
                values = {
                    name: _load_field(data, name, index) for name in STORE_FIELDS
                }
                out.append(inkmod.Ink(**values))
            return out, ""
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        return None


def build_inks(edit: dict, meta: dict, *, source: str | Path,
               size: "tuple[int, int] | inkmod.View | None" = None,
               data_root: str | Path | None = None,
               progress=None) -> dict:
    """``{layer id: {"inks": [...], "reason": str}}`` for every clean layer.

    With ``data_root`` each layer's ink is stored on disk, keyed by the source
    stamp, the size and that layer alone. The estimate, the queue and the render
    read the same store, so a second call reads no frame, and a changed layer
    rebuilds only itself.
    """
    out: dict = {}
    directory = Path(data_root) / "ink" if data_root is not None else None
    layers = _clean_layers(edit)
    for done, layer in enumerate(layers):
        if progress is not None:
            progress(done / max(1, len(layers)), f"Reading the text strokes · {done + 1}/{len(layers)}")
        path = None
        if directory is not None:
            try:
                path = directory / f"{_store_key(layer, meta, source, size)}.npz"
            except OSError:
                path = None
        stored = _load_ink(path) if path is not None and path.is_file() else None
        if stored is not None:
            inks, reason = stored
        else:
            inks, reason = layer_inks(layer, meta, source=source, size=size)
            if path is not None:
                try:
                    _save_ink(path, inks, reason)
                except OSError:
                    pass
        out[str(layer.get("id"))] = {"inks": inks, "reason": reason}
    if directory is not None:
        _prune_store(directory)
    if progress is not None:
        progress(1.0, "Text strokes ready")
    return out


INK_STORE_BYTES = 512 * 1024 ** 2


def _prune_store(directory: Path, *, limit: int = INK_STORE_BYTES) -> None:
    """Oldest files leave past the cap; a project needs one set of them."""
    try:
        entries = sorted(
            ((entry.stat().st_mtime, entry.stat().st_size, entry.path)
             for entry in os.scandir(directory) if entry.name.endswith(".npz")),
        )
    except OSError:
        return
    total = sum(size for _changed, size, _path in entries)
    for _changed, size, path in entries:
        if total <= limit:
            break
        try:
            os.unlink(path)
            total -= size
        except OSError:
            pass


def layer_strokes(inks: list[inkmod.Ink]) -> tuple[inkmod.Rect, list[tuple[int, int, np.ndarray]]] | None:
    """What to fill for a layer: the frame rect that holds every glyph's hole,
    and (first frame, last frame, hole in that rect) for each glyph."""
    pieces = [(item.rect, piece) for item in inks for piece in item.pieces()]
    boxes = []
    for rect, (_first, _last, hole) in pieces:
        box = inkmod.bbox(hole)
        if box is not None:
            boxes.append((rect[0] + box[0], rect[1] + box[1], rect[0] + box[2], rect[1] + box[3]))
    if not boxes:
        return None
    x0, y0 = min(box[0] for box in boxes), min(box[1] for box in boxes)
    x1, y1 = max(box[2] for box in boxes), max(box[3] for box in boxes)
    out = []
    for rect, (first, last, hole) in pieces:
        placed = np.zeros((y1 - y0, x1 - x0), dtype=bool)
        top, left = rect[1] - y0, rect[0] - x0
        # The hole's own rect can stick out of the union only where it is empty.
        ya, yb = max(0, top), min(y1 - y0, top + hole.shape[0])
        xa, xb = max(0, left), min(x1 - x0, left + hole.shape[1])
        placed[ya:yb, xa:xb] = hole[ya - top:yb - top, xa - left:xb - left]
        if placed.any():
            out.append((int(first), int(last), placed))
    return (x0, y0, x1, y1), out


def timeline(edit: dict, fps: float) -> list[tuple[float, float, int]]:
    """Source spans of the edit and the output frame each begins on."""
    out: list[tuple[float, float, int]] = []
    at = 0.0
    if not edit.get("clips"):
        # No cut list: the output is the source from its first frame.
        return [(0.0, float("inf"), 0)]
    for clip in edit.get("clips") or []:
        start = float(clip.get("start") or 0.0)
        end = float(clip.get("end") or 0.0)
        if end <= start:
            continue
        if str(clip.get("kind")) != "media":
            out.append((start, end, int(round(at * fps))))
        at += max(0.04, end - start)
    return out


def _line_up(source: np.ndarray, output: np.ndarray, around: np.ndarray) -> tuple[int, float]:
    """The slide of ``source`` (read ``SLIDE`` frames early) that matches ``output``."""
    count = output.shape[0]
    picks = range(0, count, max(1, count // 12))
    costs: dict[int, float] = {}
    for slide in range(-SLIDE, SLIDE + 1):
        total, used = 0.0, 0
        for index in picks:
            at = index + SLIDE + slide
            if 0 <= at < source.shape[0]:
                gap = np.abs(output[index].astype(np.int16) - source[at].astype(np.int16)).max(axis=-1)
                total += float(gap[around].mean())
                used += 1
        if used:
            costs[slide] = total / used
    if not costs:
        return 0, float("inf")
    best = min(costs.values())
    # A still shot matches at every slide: keep the timeline's own answer.
    slide = min((key for key, value in costs.items() if value <= best + 0.5), key=abs)
    return slide, costs[slide]


def _flicker(output: np.ndarray, hole: np.ndarray) -> float | None:
    """Frame-to-frame change inside the hole against the picture just around it."""
    if output.shape[0] < 3 or not hole.any():
        return None
    reach = max(8, hole.shape[0] // 3)
    ring = inkmod.dilate(hole, reach) & ~hole
    if not ring.any():
        return None
    change = np.abs(np.diff(inkmod.grey(output).astype(np.int16), axis=0))
    around = float(change[:, ring].mean())
    if around <= 1e-3:
        return None
    return round(float(change[:, hole].mean()) / around, 2)


def _judge(layer: dict, built: inkmod.Ink, output: str | Path, source: str | Path,
           spans: list[tuple[float, float, int]], *, fps: float,
           size: "inkmod.View | None") -> dict:
    """Judge one line on every output frame near it."""
    rect = built.rect
    hole = built.hole()
    around = ~inkmod.dilate(hole, 4)
    near = inkmod.dilate(hole, 0)
    glyphs = built.glyphs or ((0, built.mask.shape[1]),)
    zones = []
    for x0, x1 in glyphs:
        zone = np.zeros_like(near)
        zone[:, max(0, x0 - 2):x1 + 3] = near[:, max(0, x0 - 2):x1 + 3]
        zones.append(zone)
    frames = 0
    hits: list[dict] = []
    flicker: list[float] = []
    problem = ""
    reach = built.reach
    low, high = reach[0] / built.fps - PAD, (reach[1] + 1) / built.fps + PAD
    for start, end, begins in spans:
        a, b = max(low, start), min(high, end)
        if b <= a:
            continue
        first = inkmod.first_frame(a, fps)
        count = inkmod.first_frame(b, fps) - first
        if count <= 0:
            continue
        out_first = begins + first - inkmod.first_frame(start, fps)
        lead = min(SLIDE, first)
        src = inkmod.read_box(source, first - lead, count + lead + SLIDE, rect, fps, size=size, colour=True)
        out = inkmod.read_box(output, out_first, count, rect, fps, colour=True)
        if lead < SLIDE:
            src = np.concatenate([np.repeat(src[:1], SLIDE - lead, axis=0), src], axis=0)
        if out.shape[0] == 0 or src.shape[0] <= SLIDE:
            problem = "the render has no frames there"
            continue
        if not around.any():
            around = np.ones_like(around)
        slide, cost = _line_up(src, out, around)
        if cost > ALIGN_LIMIT:
            problem = "the render does not line up with the source there"
            continue
        out_shown = inkmod.presence(inkmod.strong(out), built)
        src_shown = inkmod.presence(inkmod.strong(src), built)
        for index in range(out.shape[0]):
            best: dict | None = None
            still = [number for number in range(len(zones)) if out_shown[index][number] >= SHOWN]
            # One frame either way: a still shot lines up at more than one slide.
            for nudge in (0, -1, 1) if still else ():
                at = index + SLIDE + slide + nudge
                if not 0 <= at < src.shape[0]:
                    continue
                wanted = [number for number in still if src_shown[at][number] >= SHOWN and zones[number].any()]
                if not wanted:
                    continue
                gap = np.abs(out[index].astype(np.int16) - src[at].astype(np.int16)).max(axis=-1)
                left = [number for number in wanted if float(gap[zones[number]].mean()) <= SAME]
                if left and (best is None or len(left) > len(best["left"])):
                    best = {"left": left, "score": float(max(out_shown[index][n] for n in left))}
            frames += 1
            if best is not None:
                hits.append({
                    "time": round((out_first + index) / fps, 3),
                    "source_time": round((first + index + slide) / fps, 3),
                    "layer": str(layer.get("id")),
                    "glyphs": len(best["left"]),
                    "of": len(glyphs),
                    "score": round(best["score"], 2),
                    "text": str(layer.get("text_sample") or "")[:40],
                })
        inside = slice(
            max(0, inkmod.first_frame(built.start, fps) - first),
            max(0, inkmod.first_frame(built.end, fps) - first),
        )
        value = _flicker(out[inside], hole)
        if value is not None:
            flicker.append(value)
    return {"frames": frames, "hits": hits, "flicker": flicker, "problem": problem}


def check(output: str | Path, edit: dict, meta: dict, *, source: str | Path,
          inks: dict | None = None, fps: float | None = None,
          size: "tuple[int, int] | inkmod.View | None" = None) -> dict:
    """Judge every clean layer of ``edit`` on ``output``.

    ``fps`` and ``size`` are the output's frame rate and picture; the source's
    when not given. ``size`` is a bare (width, height) stretch, or the render's
    :class:`ink.View` when the Cut crops, pads, sharpens or grades. Either way
    the source is read through the same picture filters as the render, so the
    ink is rebuilt in the output's pixels and ``inks`` made at the source's size
    is not used. Returns the frames judged, the hits, the lines that could not
    be judged and why, and a flicker number per line.
    """
    native = (int(meta.get("width") or 0), int(meta.get("height") or 0))
    if size is not None and not isinstance(size, inkmod.View):
        size = tuple(int(value) for value in size)
        size = None if size == native else inkmod.View.scaled(size, native)
    fps = float(fps or meta.get("fps") or 30.0)
    layers = _clean_layers(edit)
    if inks is None or size is not None:
        inks = build_inks(edit, meta, source=source, size=size)
    spans = timeline(edit, fps)
    frames = 0
    hits: list[dict] = []
    flicker: dict[str, float] = {}
    unchecked: list[dict] = []
    for layer in layers:
        layer_id = str(layer.get("id"))
        entry = inks.get(layer_id) or {}
        built = entry.get("inks") or []
        reason = str(entry.get("reason") or "")
        if not built:
            unchecked.append({"layer": layer_id, "reason": reason or "no steady strokes were found"})
            continue
        values: list[float] = []
        judged = 0
        try:
            for item in built:
                result = _judge(layer, item, output, source, spans, fps=fps, size=size)
                judged += result["frames"]
                hits.extend(result["hits"])
                values.extend(result["flicker"])
                reason = reason or result["problem"]
        except inkmod.InkError as exc:
            reason = f"the frames could not be read ({exc})"
        frames += judged
        if not judged:
            unchecked.append({"layer": layer_id, "reason": reason or "it is not in the render"})
        if values:
            flicker[layer_id] = max(values)
    return {
        "frames": int(frames),
        "hits": hits,
        "times": sorted({item["time"] for item in hits}),
        "flicker": flicker,
        "flicker_limit": FLICKER_LIMIT,
        "layers": len(layers),
        "checked": len(layers) - len(unchecked),
        "unchecked": unchecked,
    }
