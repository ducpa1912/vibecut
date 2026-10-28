"""GET /api/artifacts: the finished-video library route.

The route is mounted on a tiny FastAPI app with a temporary jobs root so the
tests never touch app.py, the founder's data directory or the network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import artifacts
import routes_library


def make_job(
    jobs: Path,
    job_id: str,
    *,
    title: str = "",
    source_name: str = "source.mp4",
    stories: dict[str, str] | None = None,
    created: float = 1_000.0,
    corrupt: bool = False,
) -> Path:
    directory = jobs / job_id
    directory.mkdir(parents=True)
    job = {
        "id": job_id,
        "created": created,
        "updated": created,
        "status": "ready",
        "source": {"name": source_name, "duration": 52.9},
        "ingest": {"title": title} if title else {},
        "clip_sets": {
            "set1": {
                "id": "set1",
                "stories": [
                    {"id": story_id, "title": story_title}
                    for story_id, story_title in (stories or {}).items()
                ],
            },
        },
        "renders": {},
        "artifacts": {},
    }
    (directory / "job.json").write_text(
        "{not json" if corrupt else json.dumps(job, ensure_ascii=False),
        encoding="utf-8",
    )
    return directory


def payload(
    *,
    story_id: str = "s1",
    aspect: str = "9:16",
    quality: str = "final",
    fingerprint: str = "src",
) -> dict:
    return {
        "schema_version": artifacts.SCHEMA_VERSION,
        "render_version": artifacts.RENDER_VERSION,
        "source_fingerprint": fingerprint,
        "clips": [
            {"scene": 0, "start": 0.0, "end": 2.5, "dur": 2.5, "role": "hook"},
        ],
        "order": "source",
        "hook_scene": 0,
        "hook_override": False,
        "caption": {
            "enabled": True,
            "style_hash": "style",
            "cue_hash": "cues",
            "text_hash": "text",
            "cue_count": 1,
            "margin": 0.075,
        },
        "audio_sig": "",
        "quality": quality,
        "aspect": aspect,
        "resolved_encoder": "libx264",
        "story_id": story_id,
        "target": 15,
        "generation": 0,
    }


def add_artifact(
    job_dir: Path,
    *,
    story_id: str = "s1",
    aspect: str = "9:16",
    quality: str = "final",
    created: float = 1_000.0,
    version: int | None = None,
    status: str = "ready",
    title: str | None = None,
    reel: bytes = b"reel-bytes",
    poster: bool = True,
    render: dict | None = None,
) -> dict:
    spec = artifacts.ArtifactSpec.from_payload(payload(
        story_id=story_id,
        aspect=aspect,
        quality=quality,
        fingerprint=f"{job_dir.name}-{story_id}-{aspect}",
    ))
    manifest = artifacts.make_manifest(
        job_dir.name, spec, status=status, title=title, created=created,
    )
    if version is not None:
        manifest["version"] = version
    if render is not None:
        manifest["render"] = render
    manifest = artifacts.save_manifest(job_dir, manifest)
    directory = artifacts.artifact_dir(job_dir, manifest["artifact_id"])
    directory.mkdir(parents=True, exist_ok=True)
    if reel:
        (directory / "reel.mp4").write_bytes(reel)
    if poster:
        (directory / "poster.jpg").write_bytes(b"poster")
    return manifest


def add_legacy_artifact(
    job_dir: Path,
    *,
    created: float = 1_000.0,
    reel: bytes = b"old-reel",
) -> str:
    """A pre-story/aspect/version manifest: valid id, missing display fields."""
    spec = {
        "schema_version": 1,
        "render_version": artifacts.RENDER_VERSION,
        "source_fingerprint": f"legacy-{job_dir.name}-{created:g}",
        "clips": [],
        "order": "source",
        "hook_scene": None,
        "hook_override": False,
        "caption": {"enabled": False},
        "audio_sig": "",
        "resolved_encoder": "libx264",
        "target": 20,
    }
    artifact_id = artifacts.artifact_id(spec)
    manifest = {
        "artifact_id": artifact_id,
        "job_id": job_dir.name,
        "schema_version": 1,
        "spec": spec,
        "status": "ready",
        "created": created,
        "media": dict(artifacts.MEDIA_FILES),
    }
    path = artifacts.manifest_path(job_dir, artifact_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    if reel:
        (path.parent / "reel.mp4").write_bytes(reel)
    return artifact_id


@pytest.fixture
def library(tmp_path: Path):
    jobs = tmp_path / "data" / "jobs"
    jobs.mkdir(parents=True)
    tiny = FastAPI()
    tiny.state.library_jobs_dir = jobs
    tiny.include_router(routes_library.router)
    client = TestClient(tiny)
    client.jobs = jobs  # type: ignore[attr-defined]
    return client


def test_lists_every_job_both_shapes_with_fields_and_newest_first(library):
    a = make_job(
        library.jobs, "jobA", title="JOYLO AV1 talking head",
        stories={"s1": "AI security test"},
    )
    b = make_job(
        library.jobs, "jobB", title="rednote garden",
        stories={"s2": "红笔记花园"},
    )
    first = add_artifact(
        a, story_id="s1", aspect="9:16", created=300.0, version=2,
        reel=b"x" * 4321, render={"duration": 52.9, "width": 1080, "height": 1920},
    )
    four_by_five = add_artifact(a, story_id="s1", aspect="4:5", created=200.0, version=1)
    second = add_artifact(b, story_id="s2", aspect="9:16", created=400.0, version=1)

    response = library.get("/api/artifacts")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert [row["artifact_id"] for row in body["artifacts"]] == [
        second["artifact_id"], first["artifact_id"], four_by_five["artifact_id"],
    ]

    latest = body["artifacts"][0]
    assert latest["job_id"] == "jobB"
    assert latest["job_title"] == "rednote garden"
    assert latest["source_label"] == "source.mp4"
    assert latest["story_id"] == "s2"
    assert latest["story_title"] == "红笔记花园"
    assert latest["aspect"] == "9:16"
    assert latest["status"] == "ready"
    assert latest["date"]
    assert latest["version_label"] == "v1"

    shapes = {row["aspect"] for row in body["artifacts"]}
    assert shapes == {"9:16", "4:5"}
    nine = next(row for row in body["artifacts"] if row["artifact_id"] == first["artifact_id"])
    assert nine["size"] == 4321
    assert nine["duration"] == 52.9
    assert nine["url"].endswith("/media/reel.mp4")
    assert nine["poster_url"].endswith("/media/poster.jpg")
    assert nine["download_url"] == nine["url"]
    assert nine["version"] == 2 and nine["version_label"] == "v2"
    assert nine["quality"] == "final"
    assert nine["story_title"] == "AI security test"


def test_failed_artifact_stays_visible_without_media(library):
    job = make_job(library.jobs, "job1", stories={"s1": "Failed render"})
    failed = add_artifact(
        job, story_id="s1", created=100.0, status="failed", reel=b"", poster=False,
    )
    row = library.get("/api/artifacts").json()["artifacts"][0]
    assert row["artifact_id"] == failed["artifact_id"]
    assert row["status"] == "failed"
    assert row["url"] is None and row["poster_url"] is None
    assert row["size"] is None


def test_old_artifact_without_new_fields_is_omitted_not_fatal(library):
    job = make_job(library.jobs, "oldjob", stories={"s1": "Old story"})
    legacy_id = add_legacy_artifact(job, created=100.0)
    add_artifact(job, story_id="s1", created=200.0, version=1)

    body = library.get("/api/artifacts?job_id=oldjob").json()
    assert body["total"] == 2
    legacy = next(row for row in body["artifacts"] if row["artifact_id"] == legacy_id)
    assert legacy["status"] == "ready"
    assert legacy["aspect"] == "" and legacy["shape"] == ""
    assert legacy["quality"] == ""
    assert legacy["story_id"] == "" and legacy["story_title"] == ""
    assert legacy["version"] == 1 and legacy["version_label"] == "v1"
    assert legacy["size"] == len(b"old-reel")
    assert legacy["poster_url"] is None
    assert legacy["url"].endswith("/media/reel.mp4")

    again = library.get("/api/artifacts?job_id=oldjob").json()
    assert next(
        row for row in again["artifacts"] if row["artifact_id"] == legacy_id
    )["version"] == 1


def test_corrupt_manifest_and_job_do_not_hide_the_rest(library):
    good = make_job(library.jobs, "good", stories={"s1": "Kept"})
    add_artifact(good, created=200.0)
    broken = make_job(library.jobs, "broken", corrupt=True, stories={"s1": "Lost"})
    add_artifact(broken, created=300.0)
    dead = broken / "artifacts" / ("art_" + "0" * 24)
    dead.mkdir()
    (dead / "manifest.json").write_text("{broken manifest", encoding="utf-8")
    (broken / "artifacts" / ("art_" + "1" * 24)).mkdir()

    body = library.get("/api/artifacts").json()
    assert body["total"] == 2
    assert {row["job_id"] for row in body["artifacts"]} == {"good", "broken"}
    assert all(row["artifact_id"] != "art_" + "0" * 24 for row in body["artifacts"])


def test_empty_library_and_pagination_filters(library):
    empty = library.get("/api/artifacts").json()
    assert empty == {
        "artifacts": [], "total": 0, "offset": 0, "limit": 60, "has_more": False,
        "q": "", "job_id": "", "shape": "",
    }

    job = make_job(
        library.jobs, "job1", title="Etsy tips",
        stories={"s1": "Pricing beats features", "s2": "Print on demand"},
    )
    add_artifact(job, story_id="s1", aspect="9:16", created=1.0)
    add_artifact(job, story_id="s1", aspect="4:5", created=2.0)
    add_artifact(job, story_id="s2", aspect="9:16", created=3.0)

    page = library.get("/api/artifacts?limit=2&offset=1").json()
    assert page["total"] == 3 and page["limit"] == 2 and page["offset"] == 1
    assert len(page["artifacts"]) == 2
    assert library.get("/api/artifacts?limit=999").json()["limit"] == routes_library.MAX_LIMIT
    assert library.get("/api/artifacts?limit=0").json()["limit"] == 1
    assert library.get("/api/artifacts?offset=-5").json()["offset"] == 0

    assert library.get("/api/artifacts?shape=4:5").json()["total"] == 1
    assert library.get("/api/artifacts?job_id=job1&q=pricing").json()["total"] == 2
    assert library.get("/api/artifacts?q=print demand").json()["total"] == 1
    assert library.get("/api/artifacts?job_id=missing").json()["total"] == 0


def test_deterministic_version_sequence_for_old_manifests(library):
    job = make_job(library.jobs, "job1", stories={"s1": "One"})
    first = add_legacy_artifact(job, created=100.0)
    second = add_legacy_artifact(job, created=200.0)
    body = library.get("/api/artifacts").json()
    by_id = {row["artifact_id"]: row for row in body["artifacts"]}
    assert by_id[first]["version"] == 1
    assert by_id[second]["version"] == 2
    again = library.get("/api/artifacts").json()
    assert {row["artifact_id"]: row["version"] for row in again["artifacts"]} == {
        first: 1, second: 2,
    }


def test_job_id_path_traversal_and_symlinks_are_not_followed(library, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "job.json").write_text(
        json.dumps({"id": "outside", "source": {"name": "secret.mp4"}}),
        encoding="utf-8",
    )
    (library.jobs / "link").symlink_to(outside, target_is_directory=True)

    for probe in ("../outside", "../../etc", "..%2Foutside", "link"):
        response = library.get(f"/api/artifacts?job_id={probe}")
        assert response.status_code == 200
        assert response.json()["total"] == 0
    assert library.get("/api/artifacts?q=../outside").json()["total"] == 0


def test_route_is_read_only_and_keeps_artifact_identity(library):
    job = make_job(library.jobs, "job1", stories={"s1": "Stable"})
    manifest = add_artifact(job, created=100.0, version=1)
    snapshot = {
        path: path.read_bytes()
        for path in (
            job / "job.json",
            artifacts.manifest_path(job, manifest["artifact_id"]),
            artifacts.index_path(job),
        )
        if path.is_file()
    }
    before = artifacts.load_manifest(job, manifest["artifact_id"])
    library.get("/api/artifacts")
    library.get("/api/artifacts?q=stable")
    after = artifacts.load_manifest(job, manifest["artifact_id"])
    assert after == before
    assert artifacts.artifact_id(after["spec"]) == manifest["artifact_id"]
    assert {path: path.read_bytes() for path in snapshot} == snapshot


def test_install_pins_the_host_data_root(tmp_path):
    data = tmp_path / "data"
    jobs = data / "jobs"
    jobs.mkdir(parents=True)
    job = make_job(jobs, "job1", title="Installed")
    add_artifact(job, created=100.0)

    tiny = FastAPI()
    tiny.DATA = data
    routes_library.install(tiny)
    response = TestClient(tiny).get("/api/artifacts")
    assert response.status_code == 200
    assert response.json()["artifacts"][0]["job_title"] == "Installed"
