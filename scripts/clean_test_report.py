#!/usr/bin/env python3
"""Report one run of the AI clean test: what the scan found, what was cleaned, how long it took.

Reads a job's scan report, latest Edit and latest finished render. It changes
nothing in the job and generates no media. Run it only on a job the founder
names. The numbers support the founder's review rather than replace it.

A golden file records the founder's choice for one video, so a later run, by hand
or automated, can be compared with it:

    {"video": "name.mp4", "keep": ["words to clean"], "skip": ["words to leave"]}

Usage:
    python3 scripts/clean_test_report.py JOB_ID
    python3 scripts/clean_test_report.py JOB_ID --write-golden golden.json
    python3 scripts/clean_test_report.py JOB_ID --golden golden.json --save
    python3 scripts/clean_test_report.py JOB_ID --json

``--save`` adds the result to ``<lane root>/test-results/studio-clean.jsonl``,
outside the repo. Exit status: 0 report written, 1 the golden file differs,
2 the job cannot be read.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

# Two boxes count as overlapping past this share of the smaller one.
OVERLAP_SHARE = 0.1
OVERLAP_SECONDS = 0.05


def _words(text: object) -> str:
    return re.sub(r"[^\w]+", "", str(text or "").casefold())


def _same_words(first: object, second: object) -> bool:
    a, b = _words(first), _words(second)
    if not a or not b:
        return False
    return a == b or (min(len(a), len(b)) >= 4 and (a in b or b in a))


def _ranges(item: dict) -> list[tuple[float, float]]:
    return [
        (float(span.get("start") or 0.0), float(span.get("end") or 0.0))
        for span in item.get("ranges") or []
        if isinstance(span, dict)
    ]


def covered_seconds(layers: list[dict]) -> float:
    """Seconds of video with at least one Clean layer on, counted once."""
    spans = sorted(span for layer in layers for span in _ranges(layer))
    total = 0.0
    end = None
    for low, high in spans:
        if end is None or low > end:
            total += max(0.0, high - low)
            end = high
        elif high > end:
            total += high - end
            end = high
    return round(total, 3)


def overlapping_pairs(layers: list[dict]) -> list[list[str]]:
    """Layers on at the same time whose boxes overlap."""
    pairs = []
    for index, first in enumerate(layers):
        a = first.get("box") or {}
        for second in layers[index + 1:]:
            b = second.get("box") or {}
            together = any(
                min(x[1], y[1]) - max(x[0], y[0]) > OVERLAP_SECONDS
                for x in _ranges(first) for y in _ranges(second)
            )
            if not together or not a or not b:
                continue
            width = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
            height = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
            smaller = min(a["w"] * a["h"], b["w"] * b["h"])
            if width > 0 and height > 0 and smaller > 0 and width * height / smaller > OVERLAP_SHARE:
                pairs.append([str(first.get("label") or first.get("id")), str(second.get("label") or second.get("id"))])
    return pairs


def summarize(report: dict, layers: list[dict], record: dict | None, fps: float) -> dict:
    """The numbers one run is judged on."""
    tracklets = [item for item in report.get("tracklets") or [] if isinstance(item, dict)]
    chosen = {str(layer.get("tracklet_id") or "") for layer in layers}
    boxes = [layer.get("box") or {} for layer in layers if layer.get("box")]
    seconds = covered_seconds(layers)
    frames = int(round(seconds * fps))
    timings = dict((record or {}).get("timings") or {})
    fill = float(timings.get("fill") or 0.0)
    return {
        "scan": {
            "seconds": (report.get("timings") or {}).get("total"),
            "frames_read": (report.get("text") or {}).get("frames_read"),
            "found": len(tracklets),
            "minor": sum(1 for item in tracklets if item.get("minor")),
            "left_out": [
                str(item.get("text_sample") or "") for item in tracklets
                if str(item.get("id") or "") not in chosen
            ],
        },
        "clean": {
            "layers": len(layers),
            "drawn": sum(1 for layer in layers if not layer.get("tracklet_id")),
            "engines": sorted({str(layer.get("method") or layer.get("kind")) for layer in layers}),
            "tallest_box": round(max((box.get("h", 0.0) for box in boxes), default=0.0), 4),
            "widest_box": round(max((box.get("w", 0.0) for box in boxes), default=0.0), 4),
            "overlaps": overlapping_pairs(layers),
            "seconds_on": seconds,
            "frames_on": frames,
        },
        "render": {
            "quality": (record or {}).get("quality"),
            "artifact_id": (record or {}).get("artifact_id"),
            "timings": timings,
            "fill_seconds_per_frame": round(fill / frames, 3) if fill and frames else None,
        },
    }


def compare(tracklets: list[dict], layers: list[dict], golden: dict) -> dict:
    """What differs from the founder's choice. Empty lists mean it matches."""
    found = [item.get("text_sample") for item in tracklets]
    cleaned = [layer.get("label") for layer in layers]
    return {
        "keep_not_found": [word for word in golden.get("keep") or [] if not any(_same_words(word, text) for text in found)],
        "keep_not_cleaned": [word for word in golden.get("keep") or [] if not any(_same_words(word, text) for text in cleaned)],
        "skip_cleaned": [word for word in golden.get("skip") or [] if any(_same_words(word, text) for text in cleaned)],
    }


def golden_from(job: dict, tracklets: list[dict], layers: list[dict]) -> dict:
    """The founder's choice on this run, as a golden file."""
    chosen = {str(layer.get("tracklet_id") or "") for layer in layers}
    return {
        "video": str((job.get("source") or {}).get("name") or ""),
        "keep": sorted({str(layer.get("label") or "") for layer in layers if layer.get("tracklet_id")} - {""}),
        "skip": sorted({
            str(item.get("text_sample") or "") for item in tracklets
            if str(item.get("id") or "") not in chosen
        } - {""}),
    }


def latest_edit(job_dir: Path, wanted_layers: bool = True) -> dict:
    """The newest saved Edit, preferring one that holds Clean layers."""
    paths = sorted((job_dir / "edits").glob("ed_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    edits = (json.loads(path.read_text(encoding="utf-8")) for path in paths)
    first = None
    for edit in edits:
        first = first or edit
        if not wanted_layers or edit.get("clean"):
            return edit
    return first or {}


def latest_render(job: dict) -> dict | None:
    records = [
        value for value in (job.get("renders") or {}).values()
        if isinstance(value, dict) and value.get("status") == "ready"
    ]
    return max(records, key=lambda value: float(value.get("created") or value.get("updated") or 0.0), default=None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("job_id")
    parser.add_argument("--data", default=os.environ.get("VIBECUT_DATA") or "~/vibecut-lanes/studio")
    parser.add_argument("--golden", help="compare with this golden file")
    parser.add_argument("--write-golden", help="save this run's choice as a golden file")
    parser.add_argument("--save", action="store_true", help="add the result to the results file")
    parser.add_argument("--json", action="store_true", help="print JSON only")
    args = parser.parse_args(argv)

    data = Path(args.data).expanduser()
    job_dir = data / "jobs" / args.job_id
    try:
        job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
        report = json.loads((job_dir / "check" / "source_report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"Cannot read job {args.job_id}: {exc}", file=sys.stderr)
        return 2
    layers = [layer for layer in latest_edit(job_dir).get("clean") or [] if isinstance(layer, dict)]
    tracklets = [item for item in report.get("tracklets") or [] if isinstance(item, dict)]
    fps = float((job.get("source") or {}).get("fps") or 30.0)
    result = {
        "job": args.job_id,
        "video": (job.get("source") or {}).get("name"),
        "at": round(time.time(), 1),
        **summarize(report, layers, latest_render(job), fps),
    }
    status = 0
    if args.golden:
        golden = json.loads(Path(args.golden).expanduser().read_text(encoding="utf-8"))
        result["golden"] = compare(tracklets, layers, golden)
        if any(result["golden"].values()):
            status = 1
    if args.write_golden:
        Path(args.write_golden).expanduser().write_text(
            json.dumps(golden_from(job, tracklets, layers), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.save:
        results = data.parent / "test-results"
        results.mkdir(parents=True, exist_ok=True)
        with (results / "studio-clean.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=None if args.json else 2))
    return status


if __name__ == "__main__":
    sys.exit(main())
