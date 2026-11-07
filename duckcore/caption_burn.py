"""Burn captions into a rendered video with Pillow.

Some consumer ffmpeg builds have no libass/drawtext. DuckSuite draws the cues
itself, then re-encodes with VideoToolbox and keeps the original audio.
"""

from __future__ import annotations

import re
import subprocess
import threading
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

from duckcore import caption_style

LATIN_FONT = Path("/System/Library/Fonts/SFNS.ttf")
CJK_FONT = Path("/System/Library/Fonts/Hiragino Sans GB.ttc")
_FONT_CACHE: dict[tuple[str, int, int], ImageFont.FreeTypeFont] = {}
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def _font(text: str, size: int) -> ImageFont.FreeTypeFont:
    path = CJK_FONT if _CJK_RE.search(text) and CJK_FONT.is_file() else LATIN_FONT
    key = (str(path), size, 0)
    if key not in _FONT_CACHE:
        try:
            _FONT_CACHE[key] = ImageFont.truetype(str(path), size, index=0)
        except OSError:
            _FONT_CACHE[key] = ImageFont.load_default()
    return _FONT_CACHE[key]


def active_cue(cues: Iterable[dict], when: float) -> dict | None:
    best = None
    for cue in cues:
        try:
            start = float(cue.get("start") or 0.0)
            end = float(cue.get("end") or 0.0)
        except (TypeError, ValueError):
            continue
        if start <= when < end and (best is None or start >= float(best.get("start") or 0.0)):
            best = cue
    return best


def _wrap(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    width: int,
    max_lines: int = 4,
) -> list[str]:
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and draw.textlength(candidate, font=font) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    # Long unbroken CJK/URL text: split by character.
    if len(lines) == 1 and draw.textlength(lines[0], font=font) > width:
        lines = []
        current = ""
        for char in text:
            candidate = current + char
            if current and draw.textlength(candidate, font=font) > width:
                lines.append(current)
                current = char
            else:
                current = candidate
        if current:
            lines.append(current)
    return lines[:max_lines]


def draw_caption(image: Image.Image, text: str, style: Any = None) -> Image.Image:
    text = " ".join(str(text or "").split())
    if not text:
        return image
    style = caption_style.normalize(style)
    width, height = image.size
    font = _font(text, max(22, int(height * float(style["font_scale"]))))
    probe = ImageDraw.Draw(image)
    lines = _wrap(probe, text, font, int(width * 0.82), int(style["max_lines"]))
    if not lines:
        return image
    line_height = int(font.size * 1.22)
    block_h = line_height * len(lines)
    pad_x = max(12, int(width * 0.018))
    pad_y = max(8, int(height * 0.012))
    max_line = max(probe.textlength(line, font=font) for line in lines)
    box_w = int(max_line) + pad_x * 2
    box_h = block_h + pad_y * 2
    x0 = (width - box_w) // 2
    margin = int(height * float(style["margin"]))
    if style["position"] == "top":
        y0 = margin
    elif style["position"] == "middle":
        y0 = (height - box_h) // 2
    else:
        y0 = height - margin - box_h
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rounded_rectangle(
        (x0, y0, x0 + box_w, y0 + box_h),
        radius=max(8, int(height * float(style["radius"]))),
        fill=(0, 0, 0, int(style["background"])),
    )
    image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(image)
    y = y0 + pad_y
    for line in lines:
        line_w = draw.textlength(line, font=font)
        draw.text(
            (width / 2 - line_w / 2, y),
            line,
            font=font,
            fill=(255, 255, 255),
            stroke_width=int(style["stroke"]),
            stroke_fill=(0, 0, 0),
        )
        y += line_height
    return image


def _drain(proc: subprocess.Popen, tail: list[str]) -> None:
    if proc.stderr is None:
        return
    try:
        for line in proc.stderr:
            tail.append(line.decode("utf-8", "replace")[-500:])
            if len(tail) > 20:
                tail.pop(0)
    except (OSError, ValueError):
        pass


def burn_captions(
    video: Path,
    track: dict,
    output: Path,
    *,
    width: int,
    height: int,
    fps: float,
    ffmpeg: str,
) -> Path:
    cues = [cue for cue in track.get("cues") or [] if str(cue.get("text") or "").strip()]
    if not cues:
        return video
    read_tail: list[str] = []
    write_tail: list[str] = []
    reader = subprocess.Popen(
        [
            ffmpeg, "-v", "error", "-i", str(video),
            "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{width}x{height}", "-r", f"{fps:.6f}", "pipe:1",
        ],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    writer = subprocess.Popen(
        [
            ffmpeg, "-y", "-v", "error",
            "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{width}x{height}", "-r", f"{fps:.6f}", "-i", "pipe:0",
            "-i", str(video), "-map", "0:v:0", "-map", "1:a?",
            "-c:v", "h264_videotoolbox", "-q:v", "65",
            "-c:a", "copy", "-shortest", "-movflags", "+faststart",
            str(output),
        ],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    threading.Thread(target=_drain, args=(reader, read_tail), daemon=True).start()
    threading.Thread(target=_drain, args=(writer, write_tail), daemon=True).start()
    size = width * height * 3
    index = 0
    try:
        while True:
            data = reader.stdout.read(size)
            if not data or len(data) < size:
                break
            frame = Image.frombytes("RGB", (width, height), data)
            cue = active_cue(cues, index / max(1e-6, fps))
            if cue:
                frame = draw_caption(frame, str(cue.get("text") or ""), track.get("style"))
            writer.stdin.write(frame.tobytes())
            index += 1
        writer.stdin.close()
        reader_code = reader.wait(timeout=30)
        writer_code = writer.wait(timeout=300)
        if reader_code != 0 or writer_code != 0:
            detail = (write_tail[-1] if write_tail else "")[-500:]
            raise RuntimeError(f"Caption burn failed. {detail}".strip())
        return output
    except Exception:
        for proc in (reader, writer):
            if proc.poll() is None:
                proc.kill()
        output.unlink(missing_ok=True)
        raise
