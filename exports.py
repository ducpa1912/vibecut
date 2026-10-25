"""Cut list exports: SRT, VTT, EDL (CMX3600) and FCP7 XML."""

from __future__ import annotations

from pathlib import Path

import captions as caption_engine
from pipeline import _clip_text  # reuse the same trimming used in notes


def _clean(text: str) -> str:
    value = " ".join(str(text or "").split())
    return value[:200]


def plan_cues(plan: dict, clips: list[dict], scenes: list[dict]) -> list[dict]:
    """Cue compatibility adapter for packet/legacy callers.

    A plan carrying an attached Caption Studio track returns those exact cues;
    otherwise the trust-core scene-level contract is used.
    """
    if plan.get("_caption_cues"):
        return caption_engine.cues_for_plan(plan, clips, scenes)
    return caption_engine.reel_cues(plan, clips, scenes)


def _stamp(seconds: float, decimal: bool) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours, rest = divmod(milliseconds, 3600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, millis = divmod(rest, 1000)
    if decimal:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def srt(cues: list[dict]) -> str:
    lines: list[str] = []
    for index, cue in enumerate(cues, 1):
        lines.append(str(index))
        lines.append(f"{_stamp(cue['start'], False)} --> {_stamp(cue['end'], False)}")
        lines.append(cue["text"])
        lines.append("")
    return "\n".join(lines)


def vtt(cues: list[dict]) -> str:
    lines = ["WEBVTT", ""]
    for index, cue in enumerate(cues, 1):
        lines.append(str(index))
        lines.append(f"{_stamp(cue['start'], True)} --> {_stamp(cue['end'], True)}")
        lines.append(cue["text"])
        lines.append("")
    return "\n".join(lines)


def _timecode(seconds: float, fps: int = 30) -> str:
    frames_total = max(0, int(round(seconds * fps)))
    frames = frames_total % fps
    whole = frames_total // fps
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}:{frames:02d}"


def edl(plan: dict, clips: list[dict], source_name: str, fps: int = 30) -> str:
    """CMX3600 so Resolve and Premiere can relink against the source."""
    title = Path(source_name).stem[:60]
    lines = [f"TITLE: {title}", "FCM: NON-DROP FRAME", ""]
    record_start = 0.0
    for index, clip in enumerate(clips, 1):
        start = float(clip.get("start") or 0.0)
        duration = float(clip.get("dur") or 0.0)
        record_end = record_start + duration
        lines.append(
            f"{index:03d}  AX       V     C        "
            f"{_timecode(start, fps)} {_timecode(start + duration, fps)} "
            f"{_timecode(record_start, fps)} {_timecode(record_end, fps)}"
        )
        lines.append(f"* FROM CLIP NAME: {source_name}")
        record_start = record_end
    lines.append("")
    return "\n".join(lines)


def _xml_escape(text: str) -> str:
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def fcp7_xml(plan: dict, clips: list[dict], source_path: str, fps: int = 30) -> str:
    name = Path(source_path).name
    url = "file://" + str(Path(source_path).resolve())
    items: list[str] = []
    record_start = 0.0
    for index, clip in enumerate(clips, 1):
        start = float(clip.get("start") or 0.0)
        duration = float(clip.get("dur") or 0.0)
        in_frame = int(round(start * fps))
        out_frame = int(round((start + duration) * fps))
        record_end = record_start + duration
        items.append(f"""        <clipitem id="clipitem-{index}">
          <name>{_xml_escape(Path(source_path).stem)} {index}</name>
          <rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate>
          <start>{int(round(record_start * fps))}</start>
          <end>{int(round(record_end * fps))}</end>
          <in>{in_frame}</in>
          <out>{out_frame}</out>
          <file id="file-1">
            <name>{_xml_escape(name)}</name>
            <pathurl>{_xml_escape(url)}</pathurl>
            <rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate>
          </file>
        </clipitem>""")
        record_start = record_end
    body = "\n".join(items)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xmeml>
<xmeml version="4">
  <sequence>
    <name>{_xml_escape(Path(source_path).stem)} cut</name>
    <rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate>
    <media>
      <video>
        <track>
{body}
        </track>
      </video>
    </media>
  </sequence>
</xmeml>
"""
