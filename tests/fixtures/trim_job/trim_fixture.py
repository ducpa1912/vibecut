"""Synthetic ready job with a transcript, clip set and two aspects.

The fixture is deliberately small and deterministic: one unique sentence per
four-second scene, so a sentence boundary is also a clip boundary. Acceptance
tests create the clip set through the public API; the browser test writes the
same shape to a scratch data directory before uvicorn starts.

Nothing here renders, reads a pack or touches the network.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import artifacts
import captions as caption_engine
import clipset
import edits

SCENE_SECONDS = 4.0
SENTENCE_COUNT = 40
SOURCE_DURATION = SCENE_SECONDS * SENTENCE_COUNT

# Half-open sentence id ranges, kept apart so the middle story has pool room
# on both sides. Six sentences is 24 s at SCENE_SECONDS.
STORY_RANGES = ((5, 11), (14, 20), (23, 29))

# The story the acceptance tests trim: sentences 14..19, output time 0..24.
TRIM_STORY_RANGE = (14, 20)

# The browser story starts at source 0 so a short local video can drive the
# frame route; its six sentences are still 24 s of output.
BROWSER_STORY_RANGE = (0, 6)

# Browser fixture layer times in output seconds.
BROWSER_PREFIX_LAYER = ("prefix", 0.6, 2.6)
BROWSER_MOVED_LAYER = ("moved", 8.5, 10.5)
BROWSER_TAIL_LAYER = ("tail", 20.5, 22.0)


def make_scene(index: int) -> dict:
    return {
        "id": index,
        "start": index * SCENE_SECONDS,
        "end": index * SCENE_SECONDS + SCENE_SECONDS,
        "dur": SCENE_SECONDS,
        "mid": index * SCENE_SECONDS + SCENE_SECONDS / 2,
        "hook": 40 + index % 55,
        "score": 45 + index % 50,
        "deep": True,
        "visual_score": 40 + index % 55,
        "motion_score": 50.0,
        "audio_score": 40 + index % 55,
        "text_score": 0.0,
        "ocr": "",
        "speech": f"Sentence {index} says the build shipped on time.",
        "tags": [],
        "crop": {"cx": 0.5, "cy": 0.5},
        "crop_mode": "center",
        "face": index % 2 == 0,
    }


def make_scenes() -> list[dict]:
    return [make_scene(index) for index in range(SENTENCE_COUNT)]


def transcript_segments() -> list[dict]:
    return [
        {
            "start": index * SCENE_SECONDS,
            "end": index * SCENE_SECONDS + SCENE_SECONDS,
            "text": f"Sentence {index} says the build shipped on time.",
        }
        for index in range(SENTENCE_COUNT)
    ]


def make_job(job_id: str = "j1", *, source_path: str = "/tmp/none.mp4") -> dict:
    scenes = make_scenes()
    return {
        "id": job_id,
        "created": time.time(),
        "updated": time.time(),
        "status": "ready",
        "progress": 1.0,
        "message": "Ready",
        "error": None,
        "source": {
            "path": source_path,
            "name": "trim-fixture.mp4",
            "duration": SOURCE_DURATION,
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "has_audio": True,
            "size": 1,
        },
        "options": {},
        "analysis": {
            "scene_count": len(scenes),
            "scenes": scenes,
            "hook_scene": 3,
            "deep_count": len(scenes),
            "deep_scene_ids": [scene["id"] for scene in scenes],
            "plans": {},
        },
        "renders": {},
        "clip_sets": {},
    }


def write_transcript(job_dir: Path) -> Path:
    folder = job_dir / "transcript"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "transcript.json"
    path.write_text(
        json.dumps({"language": "en", "segments": transcript_segments()}),
        encoding="utf-8",
    )
    return path


def write_ready_job(jobs_dir: Path, job_id: str = "j1") -> Path:
    """Write a ready job and its transcript; the API builds the clip set."""
    directory = jobs_dir / job_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "job.json").write_text(
        json.dumps(make_job(job_id)), encoding="utf-8",
    )
    write_transcript(directory)
    return directory


def story_bounds(sentence_id: int) -> tuple[float, float]:
    start = sentence_id * SCENE_SECONDS
    return start, start + SCENE_SECONDS


def build_browser_job(
    data_dir: Path,
    job_id: str = "j1",
    *,
    source_path: str = "/tmp/none.mp4",
    source_duration: float | None = None,
) -> dict:
    """Write one ready job, clip set and 9:16 Edit for the browser spec.

    The Edit has a prefix layer that the first start trim must hide and a
    moved layer over sentence 2 that must ripple. Captions are a real track
    built from the transcript with the normal cue engine.
    """
    jobs_dir = data_dir / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    job = make_job(job_id, source_path=source_path)
    if source_duration is not None:
        job["source"]["duration"] = float(source_duration)
    job_dir = jobs_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    write_transcript(job_dir)

    scenes = job["analysis"]["scenes"]
    sentences = clipset.source_sentences(scenes, transcript_segments())
    chosen = sentences[BROWSER_STORY_RANGE[0]:BROWSER_STORY_RANGE[1]]
    story = clipset._story_from_sentences(
        chosen,
        scenes,
        float(job["source"]["duration"]),
        "st_trim_demo",
        title="Sentence 0 says the build shipped on time.",
    )
    if story is None:
        raise RuntimeError("The synthetic story could not be materialized.")
    record = {
        "id": "cs_trim_demo",
        "job_id": job_id,
        "created": round(time.time(), 3),
        "updated": round(time.time(), 3),
        "requested": 1,
        "min_s": clipset.MIN_STORY_S,
        "max_s": clipset.MAX_STORY_S,
        "order": "source",
        "locks": [],
        "ban_scenes": [],
        "excluded_sentences": [],
        "stories": [story],
        "available": 1,
        "complete": True,
        "sentence_count": len(sentences),
        "source_fingerprint": clipset.source_fingerprint(sentences),
        "sentence_timing": "text",
        "source": {
            "transcript": True,
            "scene_text": False,
            "fallback": "transcript",
            "partial_scene_fallback": 0,
            "sentence_total": len(sentences),
            "truncated": False,
        },
        "note": None,
        "warnings": [],
    }
    plan = clipset.story_to_plan(story, scenes, set_id=record["id"])
    track = caption_engine.build_track(job, plan, job_dir=job_dir)
    prefix_id, prefix_start, prefix_end = BROWSER_PREFIX_LAYER
    moved_id, moved_start, moved_end = BROWSER_MOVED_LAYER
    tail_id, tail_start, tail_end = BROWSER_TAIL_LAYER
    edit = edits.build_edit(
        story_ref={
            "set_id": record["id"],
            "story_id": story["id"],
            "clip_hash": edits.clip_snapshot_hash(story["clips"]),
            "title": story["title"],
            "duration": story["dur"],
            "clip_count": len(story["clips"]),
        },
        aspect="9:16",
        graphics=[
            {
                "id": prefix_id, "type": "text", "kind": "hook",
                "text": "Prefix hook", "start": prefix_start, "end": prefix_end,
            },
            {
                "id": moved_id, "type": "text", "kind": "lower_third",
                "text": "Moved lower third", "start": moved_start,
                "end": moved_end,
            },
            {
                "id": tail_id, "type": "text", "kind": "cta",
                "text": "Tail call to action", "start": tail_start,
                "end": tail_end,
            },
        ],
        captions={
            "track_id": track.id,
            "style_id": track.style_id,
            "enabled": True,
        },
    )
    edits.save_edit(job_dir, edit)

    key = edits.story_key(record["id"], story["id"], "9:16")
    job["clip_sets"] = [record]
    job["story_edits"] = {key: edit["id"]}
    job["story_captions"] = {f"{record['id']}:{story['id']}": track.id}
    artifacts.ensure_job_schema(job, job_dir)
    (job_dir / "job.json").write_text(json.dumps(job), encoding="utf-8")
    return {
        "job_id": job_id,
        "set_id": record["id"],
        "story_id": story["id"],
        "edit_id": edit["id"],
        "track_id": track.id,
        "duration": story["dur"],
    }
