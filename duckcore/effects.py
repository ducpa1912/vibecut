"""Editable special effects for DuckSuite.

SFX is broader than sound: text blocks, stickers, GIFs, still layers, colour
filters and audio stingers live on the same timeline. Rendering is split into a
visual pass and an audio pass so the existing clean, captions and voice mix keep
working.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from pathlib import Path
from typing import Any

from duckcore import edits


class EffectError(ValueError):
    pass


TEXT_STYLES = {
    "headline": {"family": "Arial Bold.ttf", "size": 0.092, "weight": "bold"},
    "caption": {"family": "Arial.ttf", "size": 0.052, "weight": "normal"},
    "badge": {"family": "Arial Bold.ttf", "size": 0.046, "weight": "bold"},
}
FILTERS = {
    "warm": "colorbalance=rs=0.07:gs=0.02:bs=-0.06",
    "cool": "colorbalance=rs=-0.06:gs=0.00:bs=0.07",
    "bw": "hue=s=0",
    "vivid": "hue=s=1.24",
}
UPLOAD_KINDS = {"sound", "image", "gif", "sticker", "layer"}


def _project_dir(data_root: Path, project_id: str) -> Path:
    return Path(data_root) / "projects" / project_id


def _sfx_dir(data_root: Path, project_id: str) -> Path:
    path = _project_dir(data_root, project_id) / "sfx"
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_effects(edit: dict) -> list[dict]:
    return [item for item in edit.get("sfx") or [] if isinstance(item, dict)]


def _append(edit: dict, data_root: Path, effect: dict) -> dict:
    edit.setdefault("sfx", []).append(effect)
    edits.save_edit(edit, data_root)
    return effect


def add_text(
    edit: dict,
    data_root: Path,
    *,
    text: str,
    start: float,
    end: float,
    style: str = "headline",
    color: str = "#ffffff",
    x: float = 0.5,
    y: float = 0.84,
) -> dict:
    value = " ".join(str(text or "").split()).strip()
    if not value:
        raise EffectError("Type some text first.")
    style = style if style in TEXT_STYLES else "headline"
    start = max(0.0, float(start))
    end = max(start + 0.2, float(end))
    effect = {
        "id": f"fx_{secrets.token_hex(5)}",
        "kind": "text",
        "name": value[:80],
        "text": value[:240],
        "start": round(start, 3),
        "end": round(end, 3),
        "style": style,
        "color": color if color.startswith("#") and len(color) in {4, 7} else "#ffffff",
        "x": max(0.0, min(1.0, float(x))),
        "y": max(0.0, min(1.0, float(y))),
        "opacity": 1.0,
        "created": time.time(),
    }
    return _append(edit, data_root, effect)


def add_filter(
    edit: dict,
    data_root: Path,
    *,
    preset: str,
    start: float = 0.0,
    end: float | None = None,
) -> dict:
    preset = str(preset or "").strip().lower()
    if preset not in FILTERS:
        raise EffectError("Choose warm, cool, black and white, or vivid.")
    start = max(0.0, float(start))
    duration = max(0.0, float(edit.get("end") or 0.0))
    finish = max(start + 0.2, float(end if end is not None else duration))
    effect = {
        "id": f"fx_{secrets.token_hex(5)}",
        "kind": "filter",
        "name": {"warm": "Warm", "cool": "Cool", "bw": "Black & white", "vivid": "Vivid"}[preset],
        "preset": preset,
        "start": round(start, 3),
        "end": round(finish, 3),
        "opacity": 1.0,
        "created": time.time(),
    }
    return _append(edit, data_root, effect)


def add_upload(
    edit: dict,
    data_root: Path,
    *,
    kind: str,
    filename: str,
    raw: bytes,
    start: float,
    end: float,
    volume: float = 0.9,
) -> dict:
    kind = str(kind or "").strip().lower()
    if kind not in UPLOAD_KINDS:
        raise EffectError("Choose sound, image, GIF, sticker or layer.")
    if not raw:
        raise EffectError("The effect file is empty.")
    suffix = Path(filename).suffix.lower() or (".wav" if kind == "sound" else ".png")
    allowed = {
        "sound": {".wav", ".mp3", ".m4a", ".aac", ".aiff", ".aif"},
        "image": {".png", ".jpg", ".jpeg", ".webp", ".heic"},
        "gif": {".gif", ".webp"},
        "sticker": {".png", ".jpg", ".jpeg", ".webp", ".gif"},
        "layer": {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".mov", ".m4v"},
    }[kind]
    if suffix not in allowed:
        raise EffectError(f"Unsupported {kind} file type.")
    project_id = str(edit["project_id"])
    target = _sfx_dir(Path(data_root), project_id) / f"{kind}_{uuid_name()}{suffix}"
    target.write_bytes(raw)
    start = max(0.0, float(start))
    end = max(start + 0.2, float(end))
    effect = {
        "id": f"fx_{secrets.token_hex(5)}",
        "kind": kind,
        "name": Path(filename).name[:120],
        "file": str(target.relative_to(_project_dir(Path(data_root), project_id))),
        "start": round(start, 3),
        "end": round(end, 3),
        "volume": max(0.0, min(1.5, float(volume))),
        "x": 0.5,
        "y": 0.5,
        "width": 0.35,
        "opacity": 1.0,
        "created": time.time(),
    }
    return _append(edit, data_root, effect)


def uuid_name() -> str:
    return hashlib.sha1(f"{time.time()}-{secrets.token_hex(8)}".encode()).hexdigest()[:12]


def remove(edit: dict, data_root: Path, effect_id: str) -> dict:
    before = list_effects(edit)
    after = [item for item in before if str(item.get("id")) != effect_id]
    if len(after) == len(before):
        raise KeyError(effect_id)
    edit["sfx"] = after
    edits.save_edit(edit, data_root)
    return after


def _font_path(family: str) -> Path:
    candidates = [
        Path("/System/Library/Fonts/Supplemental") / family,
        Path("/System/Library/Fonts") / family,
        Path("/Library/Fonts") / family,
    ]
    for path in candidates:
        if path.is_file():
            return path
    return Path("/System/Library/Fonts/Supplemental/Arial.ttf")


def text_png(effect: dict, project_id: str, data_root: Path, width: int, height: int) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    style = TEXT_STYLES.get(str(effect.get("style")), TEXT_STYLES["headline"])
    size = max(18, int(height * float(style["size"])))
    font = ImageFont.truetype(str(_font_path(style["family"])), size)
    text = str(effect.get("text") or "").strip()
    if not text:
        raise EffectError("The text effect is empty.")

    max_width = int(width * 0.82)
    words = text.split()
    lines: list[str] = []
    current = ""
    probe = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    for word in words:
        candidate = f"{current} {word}".strip()
        box = draw.textbbox((0, 0), candidate, font=font)
        if box[2] - box[0] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)

    boxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
    line_height = int(size * 1.18)
    total_height = line_height * len(lines)
    canvas_w = max((box[2] - box[0] for box in boxes), default=0) + int(size * 0.7)
    canvas_h = total_height + int(size * 0.5)
    image = Image.new("RGBA", (max(1, canvas_w), max(1, canvas_h)), (0, 0, 0, 0))
    painter = ImageDraw.Draw(image)
    if effect.get("style") == "badge":
        painter.rounded_rectangle(
            (0, 0, canvas_w - 1, canvas_h - 1),
            radius=max(8, size // 4),
            fill=(17, 14, 11, 210),
        )
    color = str(effect.get("color") or "#ffffff")
    for index, line in enumerate(lines):
        box = painter.textbbox((0, 0), line, font=font)
        painter.text(
            ((canvas_w - (box[2] - box[0])) / 2, int(size * 0.22) + index * line_height),
            line, font=font, fill=color,
        )
    target = _sfx_dir(Path(data_root), project_id) / f"text_{effect['id']}.png"
    image.save(target, "PNG")
    return target


def visual_effects(edit: dict) -> list[dict]:
    return [
        item for item in list_effects(edit)
        if item.get("kind") in {"text", "image", "gif", "sticker", "layer", "filter"}
    ]


def sound_effects(edit: dict) -> list[dict]:
    return [item for item in list_effects(edit) if item.get("kind") == "sound"]
