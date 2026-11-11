#!/usr/bin/env python3
"""Find burned-in text in a render by OCRing every frame.

A render is checked against the Check report, not against a spot list. Each
frame is read, and a line of text that matches a Check tracklet's words near
that tracklet's time is a leak. Scene text, such as the print on a bowl, does
not match any tracklet and is reported apart.

Usage::

    python3 scripts/ocr_render.py --render path/to/render.mp4 \
        --project prj_... --out /tmp/leaks.json

    # a slice, for a quick check
    python3 scripts/ocr_render.py --render r.mp4 --project prj_... --from 0 --to 10
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from duckcore.engine import vision  # noqa: E402

DEFAULT_DATA = (
    Path.home()
    / "Library/Containers/com.ducksuite.app/Data/Library/Application Support/DuckSuite"
)
WIDTH = 960
BATCH = 160
MATCH = 0.62
TIME_SLACK = 0.2


def _ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    return str(ROOT / "build/DuckSuite-Xcode.app/Contents/Helpers/ffmpeg")


def _probe_duration(path: Path) -> float:
    ffprobe = str(Path(_ffmpeg()).with_name("ffprobe"))
    if not Path(ffprobe).is_file():
        ffprobe = shutil.which("ffprobe") or ffprobe
    out = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def _normal(value: str) -> str:
    return re.sub(r"[\s\W_]+", "", str(value or "").casefold())


def _same(left: str, right: str) -> float:
    left, right = _normal(left), _normal(right)
    if not left or not right:
        return 0.0
    if left in right or right in left:
        return 1.0
    return SequenceMatcher(None, left, right).ratio()


def _tracklets(project: Path) -> list[dict]:
    check = json.loads((project / "check.json").read_text())
    out = []
    for item in check["report"].get("tracklets") or []:
        text = str(item.get("text_sample") or "")
        if not text:
            continue
        box = item.get("box") or {}
        for span in item.get("ranges") or []:
            out.append({
                "id": item.get("id"),
                "kind": item.get("kind"),
                "text": text,
                "large": bool(item.get("large")) or float(box.get("h") or 0.0) >= 0.09,
                "start": float(span.get("start") or 0.0),
                "end": float(span.get("end") or 0.0),
                "y": float((item.get("box") or {}).get("y") or 0.0),
                "h": float((item.get("box") or {}).get("h") or 0.0),
            })
    return out


def run(render: Path, project: Path, start: float, end: float, out: Path) -> dict:
    duration = _probe_duration(render)
    end = min(duration, end) if end > 0 else duration
    start = max(0.0, start)
    temp = Path(tempfile.mkdtemp(prefix="ocr-render-"))
    try:
        subprocess.run(
            [
                _ffmpeg(), "-y", "-v", "error", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
                "-i", str(render),
                "-vf", f"fps=30,scale={WIDTH}:-2", "-q:v", "4", str(temp / "%06d.jpg"),
            ],
            check=True, capture_output=True,
        )
        files = sorted(temp.glob("*.jpg"))
        tracks = _tracklets(project)
        leaks = []
        scene_text = []
        read = 0
        for offset in range(0, len(files), BATCH):
            batch = files[offset:offset + BATCH]
            records = vision.probe_images(temp, files=batch)
            for index, path in enumerate(batch):
                record = records.get(path.name) or {}
                lines = record.get("text") or []
                if not lines:
                    continue
                read += 1
                at = start + (offset + index) / 30.0
                for line in lines:
                    text = str(line.get("text") or "")
                    if float(line.get("confidence") or 0.0) < 0.3:
                        continue
                    best = None
                    score = 0.0
                    for track in tracks:
                        # Display-size print in the scene, such as a bowl mark,
                        # is not a removed subtitle; report it apart.
                        if track.get("large"):
                            continue
                        if not (track["start"] - TIME_SLACK <= at <= track["end"] + TIME_SLACK):
                            continue
                        ratio = _same(text, track["text"])
                        if ratio > score:
                            score, best = ratio, track
                    if best is not None and score >= MATCH:
                        leaks.append({
                            "time": round(at, 3),
                            "text": text,
                            "confidence": round(float(line.get("confidence") or 0.0), 2),
                            "tracklet": best["id"],
                            "tracklet_text": best["text"],
                            "match": round(score, 2),
                        })
                    else:
                        scene_text.append({
                            "time": round(at, 3),
                            "text": text,
                            "confidence": round(float(line.get("confidence") or 0.0), 2),
                        })
        result = {
            "render": str(render),
            "range": [round(start, 3), round(end, 3)],
            "frames": len(files),
            "frames_with_text": read,
            "leaks": leaks,
            "leak_frames": sorted({item["time"] for item in leaks}),
            "scene_text": scene_text,
        }
    finally:
        shutil.rmtree(temp, ignore_errors=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render", type=Path, required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--from", dest="start", type=float, default=0.0)
    parser.add_argument("--to", dest="end", type=float, default=0.0)
    parser.add_argument("--out", type=Path, default=Path("/tmp/render-leaks.json"))
    args = parser.parse_args()
    project = args.data_root / "projects" / args.project
    result = run(args.render, project, args.start, args.end, args.out)
    print(json.dumps({
        "frames": result["frames"],
        "leak_frames": len(result["leak_frames"]),
        "leaks": result["leaks"],
    }, indent=1))
    return 0 if not result["leaks"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
