"""Flow 2 overlay planning: gated API, validation, warnings and determinism."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app
import artifacts
import overlays


def _job(job_id: str = "job1") -> dict:
    return {
        "id": job_id,
        "status": "ready",
        "created": 1.0,
        "updated": 1.0,
        "source": {
            "name": "source.mp4",
            "path": "/tmp/source.mp4",
            "duration": 60.0,
            "width": 1920,
            "height": 1080,
            "fingerprint": "source-fingerprint",
        },
        "analysis": {
            "scenes": [
                {
                    "id": 0,
                    "start": 0.0,
                    "end": 10.0,
                    "dur": 10.0,
                    "crops": {"9:16": {"cx": 0.5, "cy": 0.5}},
                },
                {
                    "id": 1,
                    "start": 10.0,
                    "end": 20.0,
                    "dur": 10.0,
                    "crops": {"9:16": {"cx": 0.5, "cy": 0.5}},
                },
            ],
        },
        "clip_sets": [
            {
                "id": "cs_1",
                "stories": [
                    {
                        "id": "s1",
                        "title": "Story one",
                        "dur": 30.0,
                        "start": 0.0,
                        "end": 30.0,
                        "clips": [
                            {
                                "scene": 0,
                                "start": 0.0,
                                "end": 10.0,
                                "dur": 10.0,
                                "role": "hook",
                            },
                        ],
                    },
                ],
            },
        ],
        "renders": {},
    }


def _write_job(directory: Path, job: dict) -> None:
    (directory / "job.json").write_text(
        json.dumps(job), encoding="utf-8",
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    jobs = data / "jobs"
    jobs.mkdir(parents=True)
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.setattr(app, "SOURCES", data / "sources")
    monkeypatch.setenv("VIBECUT_ENABLE_OVERLAYS", "1")
    job = _job()
    directory = jobs / job["id"]
    directory.mkdir()
    _write_job(directory, job)
    return SimpleNamespace(
        tmp_path=tmp_path,
        data=data,
        jobs=jobs,
        directory=directory,
        job=job,
        job_id=job["id"],
    )


def _post(client: TestClient, env, body: dict):
    return client.post(
        f"/api/jobs/{env.job_id}/overlays/plan", json=body,
    )


def _layer(**overrides) -> dict:
    value = {
        "kind": "hook",
        "text": "Stop scrolling",
        "start": 0.0,
        "end": 3.0,
    }
    value.update(overrides)
    return value


def test_feature_flag_off_returns_404_before_body_validation(env, monkeypatch):
    monkeypatch.delenv("VIBECUT_ENABLE_OVERLAYS", raising=False)
    client = TestClient(app.app)
    path = f"/api/jobs/{env.job_id}/overlays/plan"
    valid = {"aspect": "9:16", "layers": [_layer()]}
    assert _post(client, env, valid).status_code == 404
    assert _post(client, env, {}).status_code == 404
    assert _post(client, env, valid).json() == {"detail": "Not found."}

    malformed = client.post(
        path,
        content=b'{"aspect": "9:16", "layers": [',
        headers={"content-type": "application/json"},
    )
    assert malformed.status_code == 404
    assert malformed.json() == {"detail": "Not found."}

    wrong_type = client.post(
        path,
        content=b"aspect=9:16",
        headers={"content-type": "text/plain"},
    )
    assert wrong_type.status_code == 404
    assert wrong_type.json() == {"detail": "Not found."}


def test_malformed_body_with_flag_on_is_a_validation_error(env):
    client = TestClient(app.app)
    path = f"/api/jobs/{env.job_id}/overlays/plan"
    malformed = client.post(
        path,
        content=b'{"aspect": "9:16", "layers": [',
        headers={"content-type": "application/json"},
    )
    assert malformed.status_code == 422, malformed.text

    wrong_type = client.post(
        path,
        content=b"aspect=9:16",
        headers={"content-type": "text/plain"},
    )
    assert wrong_type.status_code in {400, 422}, wrong_type.text


def test_valid_plan_normalizes_and_returns_hash(env):
    client = TestClient(app.app)
    response = _post(client, env, {
        "aspect": "9:16",
        "layers": [
            _layer(text="  Stop\n  scrolling  "),
            _layer(kind="title", text="The real reason", start=0.5, end=4.0, z=2),
        ],
    })
    assert response.status_code == 200, response.text
    body = response.json()
    plan = body["plan"]
    assert body["warnings"] == []
    assert body["hash"] == plan["hash"]
    assert body["hash"].startswith("ov_")
    assert len(body["hash"]) == 35
    payload = {key: value for key, value in plan.items() if key != "hash"}
    assert plan["hash"] == overlays.overlay_hash(payload)
    assert plan["aspect"] == "9:16"
    assert plan["canvas"] == {"w": 1080, "h": 1920}
    assert plan["count"] == 2
    assert [layer["text"] for layer in plan["layers"]] == [
        "Stop\nscrolling", "The real reason",
    ]
    assert [layer["id"] for layer in plan["layers"]] == ["ov01", "ov02"]
    assert [layer["z"] for layer in plan["layers"]] == [0, 2]
    assert plan["layers"][0]["anchor"] == "top-center"
    assert plan["layers"][1]["anchor"] == "center"


def test_lower_third_and_cta_kinds(env):
    client = TestClient(app.app)
    response = _post(client, env, {
        "aspect": "9:16",
        "layers": [
            _layer(
                kind="lower_third", text="Reporter name",
                start=0.0, end=3.0,
            ),
            _layer(
                kind="cta", text="Follow for part two", start=4.0, end=6.0,
                anchor="bottom-right", z=1,
            ),
        ],
    })
    assert response.status_code == 200, response.text
    layers = response.json()["plan"]["layers"]
    assert [layer["kind"] for layer in layers] == ["lower_third", "cta"]
    assert layers[0]["anchor"] == "bottom-left"
    assert layers[1]["anchor"] == "bottom-right"


def test_opacity_and_box_bounds(env):
    client = TestClient(app.app)
    visible = _post(client, env, {
        "aspect": "4:5",
        "layers": [
            _layer(text="Clear", opacity=0.0),
            _layer(kind="cta", text="Solid", start=2.0, end=4.0, opacity=1.0),
        ],
    })
    assert visible.status_code == 200, visible.text
    assert [layer["opacity"] for layer in visible.json()["plan"]["layers"]] == [0.0, 1.0]

    for opacity in (-0.01, 1.01):
        response = _post(client, env, {
            "aspect": "9:16",
            "layers": [_layer(opacity=opacity)],
        })
        assert response.status_code == 422, response.text

    edge = _post(client, env, {
        "aspect": "4:5",
        "layers": [
            _layer(
                kind="cta", text="Edge box",
                box={"width": 1.0, "height": 1.0},
            ),
        ],
    })
    assert edge.status_code == 200, edge.text

    for box in ({"w": 0.049, "h": 0.2}, {"w": 0.5, "h": 0.029}):
        response = _post(client, env, {
            "aspect": "9:16",
            "layers": [_layer(text="Bad box", box=box)],
        })
        assert response.status_code == 422, response.text


def test_duplicate_layer_ids_are_rejected(env):
    client = TestClient(app.app)
    response = _post(client, env, {
        "aspect": "9:16",
        "layers": [
            _layer(id="hook_a", text="First"),
            _layer(id="hook_a", text="Second", start=4.0, end=6.0),
        ],
    })
    assert response.status_code == 422
    assert "Duplicate layer id" in response.json()["detail"]


def test_safe_zone_false_is_echoed_but_warnings_stay_advisory(env):
    client = TestClient(app.app)
    response = _post(client, env, {
        "aspect": "9:16",
        "layers": [
            _layer(
                kind="caption", text="Intentional overlap",
                anchor="center", box={"w": 0.9, "h": 0.5},
                safe_zone=False,
            ),
        ],
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["plan"]["layers"][0]["safe_zone"] is False
    assert any(item["code"] == "safe_zone" for item in body["warnings"])


def test_safe_zone_warning_for_reserved_chrome(env):
    client = TestClient(app.app)
    response = _post(client, env, {
        "aspect": "9:16",
        "layers": [
            _layer(
                kind="caption", text="Too wide", start=0.0, end=2.0,
                anchor="center", box={"w": 0.9, "h": 0.5},
            ),
        ],
    })
    assert response.status_code == 200, response.text
    warnings = response.json()["warnings"]
    safe = [item for item in warnings if item["code"] == "safe_zone"]
    assert len(safe) == 1
    assert safe[0]["layer_id"] == "ov01"
    assert safe[0]["zones"] == ["right-ui"]

    portrait = _post(client, env, {
        "aspect": "4:5",
        "layers": [
            _layer(
                kind="caption", text="Tall too", start=0.0, end=2.0,
                anchor="center", box={"w": 0.9, "h": 0.9},
            ),
        ],
    })
    assert portrait.status_code == 200, portrait.text
    zones = [
        item["zones"] for item in portrait.json()["warnings"]
        if item["code"] == "safe_zone"
    ]
    assert zones == [["bottom-ui", "right-ui"]]


def test_z_order_sorts_and_duplicate_z_is_rejected(env):
    client = TestClient(app.app)
    response = _post(client, env, {
        "aspect": "9:16",
        "layers": [
            _layer(text="Late", z=5),
            _layer(kind="title", text="Early", start=4.0, end=6.0, z=1),
        ],
    })
    assert response.status_code == 200, response.text
    assert [layer["z"] for layer in response.json()["plan"]["layers"]] == [1, 5]
    duplicate = _post(client, env, {
        "aspect": "9:16",
        "layers": [
            _layer(text="One", z=3),
            _layer(kind="title", text="Two", start=4.0, end=6.0, z=3),
        ],
    })
    assert duplicate.status_code == 422
    assert "Duplicate z-order" in duplicate.json()["detail"]


def test_duplicate_overlapping_text_is_rejected_but_repeat_later_is_allowed(env):
    client = TestClient(app.app)
    duplicate = _post(client, env, {
        "aspect": "9:16",
        "layers": [
            _layer(text="Same words"),
            _layer(text="  Same   words ", start=0.5, end=2.0),
        ],
    })
    assert duplicate.status_code == 422
    assert "Duplicate hook overlay text" in duplicate.json()["detail"]

    repeat = _post(client, env, {
        "aspect": "9:16",
        "layers": [
            _layer(text="Same words", start=0.0, end=1.0),
            _layer(text="Same words", start=2.0, end=3.0),
        ],
    })
    assert repeat.status_code == 200, repeat.text


def test_empty_text_and_layer_limit_are_rejected(env):
    client = TestClient(app.app)
    empty = _post(client, env, {
        "aspect": "9:16",
        "layers": [_layer(text=" \n \t ")],
    })
    assert empty.status_code == 422
    assert "empty" in empty.json()["detail"].lower()

    too_many = _post(client, env, {
        "aspect": "9:16",
        "layers": [
            _layer(text=f"Layer {index}")
            for index in range(overlays.MAX_LAYERS + 1)
        ],
    })
    assert too_many.status_code == 422
    assert "at most" in too_many.json()["detail"]


def test_invalid_timing_and_aspect_are_rejected(env):
    client = TestClient(app.app)
    for layer in (
        _layer(start=2.0, end=2.0),
        _layer(start=-1.0, end=2.0),
        _layer(start=59.0, end=61.0),
    ):
        response = _post(client, env, {"aspect": "9:16", "layers": [layer]})
        assert response.status_code == 422, response.text

    aspect = _post(client, env, {"aspect": "1:1", "layers": [_layer()]})
    assert aspect.status_code == 400
    assert "9:16 or 4:5" in aspect.json()["detail"]


def test_face_overlap_warning_uses_analysis_face_boxes(env):
    job = _job()
    job["analysis"]["scenes"] = [
        {
            "id": 7,
            "start": 0.0,
            "end": 5.0,
            "dur": 5.0,
            "attention": {
                "face": {
                    "x": 0.35, "y": 0.25, "w": 0.30, "h": 0.50,
                    "confidence": 0.92,
                },
            },
            "crops": {"9:16": {"cx": 0.5, "cy": 0.5}},
        },
    ]
    _write_job(env.directory, job)
    client = TestClient(app.app)
    response = _post(client, env, {
        "aspect": "9:16",
        "layers": [
            _layer(kind="title", text="Hello face", start=0.0, end=2.0),
        ],
    })
    assert response.status_code == 200, response.text
    face = [
        item for item in response.json()["warnings"]
        if item["code"] == "face_overlap"
    ]
    assert len(face) == 1
    assert face[0]["scene_id"] == 7
    assert face[0]["layer_id"] == "ov01"
    assert face[0]["face_count"] == 1
    assert face[0]["overlap"] > 0.05


def test_hash_is_deterministic_and_order_independent_with_explicit_z(env):
    client = TestClient(app.app)
    first = {
        "aspect": "9:16",
        "layers": [
            _layer(text="Alpha", z=2),
            _layer(kind="title", text="Beta", start=1.0, end=3.0, z=1),
        ],
    }
    second = {
        "aspect": "9:16",
        "layers": list(reversed(first["layers"])),
    }
    one = _post(client, env, first)
    two = _post(client, env, second)
    again = _post(client, env, first)
    assert one.status_code == two.status_code == again.status_code == 200
    assert one.json()["hash"] == two.json()["hash"] == again.json()["hash"]
    assert one.json()["plan"]["layers"] == two.json()["plan"]["layers"]

    changed = _post(client, env, {
        "aspect": "9:16",
        "layers": [
            _layer(text="Alpha changed", z=2),
            _layer(kind="title", text="Beta", start=1.0, end=3.0, z=1),
        ],
    })
    assert changed.status_code == 200
    assert changed.json()["hash"] != one.json()["hash"]


def test_plan_does_not_mutate_job_or_write_files(env):
    before = (env.directory / "job.json").read_bytes()
    children = sorted(path.name for path in env.directory.iterdir())
    client = TestClient(app.app)
    response = _post(client, env, {
        "aspect": "4:5",
        "layers": [_layer(kind="caption", text="Read only", start=0.0, end=2.0)],
    })
    assert response.status_code == 200, response.text
    assert (env.directory / "job.json").read_bytes() == before
    assert sorted(path.name for path in env.directory.iterdir()) == children
    assert not (env.directory / "overlays.json").exists()


def test_story_context_is_resolved_and_missing_story_is_404(env):
    client = TestClient(app.app)
    found = _post(client, env, {
        "story_id": "s1",
        "aspect": "9:16",
        "layers": [_layer()],
    })
    assert found.status_code == 200, found.text
    plan = found.json()["plan"]
    assert plan["story_id"] == "s1"
    assert plan["clip_set_id"] == "cs_1"
    assert plan["story_title"] == "Story one"
    assert plan["duration"] == 30.0

    missing = _post(client, env, {
        "story_id": "nope",
        "aspect": "9:16",
        "layers": [_layer()],
    })
    assert missing.status_code == 404


def test_duplicate_story_across_clip_sets_is_409(env):
    job = _job()
    job["clip_sets"].append({
        "id": "cs_2",
        "stories": [
            {
                "id": "s1",
                "title": "Duplicate story",
                "dur": 20.0,
                "start": 10.0,
                "end": 30.0,
                "clips": [],
            },
        ],
    })
    _write_job(env.directory, job)
    client = TestClient(app.app)
    response = _post(client, env, {
        "story_id": "s1",
        "aspect": "9:16",
        "layers": [_layer()],
    })
    assert response.status_code == 409
    assert "ambiguous" in response.json()["detail"].lower()


def _store_artifact(
    env,
    *,
    aspect: str = "9:16",
    story_id: str = "s1",
    legacy: bool = False,
) -> str:
    plan = {
        "target": 30,
        "clips": [
            {
                "scene": 0, "start": 0.0, "end": 10.0,
                "dur": 10.0, "role": "hook",
            },
        ],
        "hook_scene": 0,
    }
    spec = artifacts.build_spec(
        env.job, plan, aspect=aspect, cues=[], story_id=story_id,
    )
    if legacy:
        spec = replace(spec, story_id="")
    manifest = artifacts.make_manifest(
        env.job_id, spec, status="ready", record_key="30",
    )
    artifacts.save_manifest(env.directory, manifest)
    return manifest["artifact_id"]


def test_artifact_context_and_aspect_conflict(env):
    artifact_id = _store_artifact(env)
    client = TestClient(app.app)
    mismatch = _post(client, env, {
        "artifact_id": artifact_id,
        "aspect": "4:5",
        "layers": [_layer()],
    })
    assert mismatch.status_code == 409
    assert "aspect" in mismatch.json()["detail"].lower()

    matched = _post(client, env, {
        "artifact_id": artifact_id,
        "aspect": "9:16",
        "layers": [_layer()],
    })
    assert matched.status_code == 200, matched.text
    plan = matched.json()["plan"]
    assert plan["artifact_id"] == artifact_id
    assert plan["story_id"] == "s1"
    assert plan["duration"] == 30.0

    matched_story = _post(client, env, {
        "artifact_id": artifact_id,
        "story_id": "s1",
        "aspect": "9:16",
        "layers": [_layer()],
    })
    assert matched_story.status_code == 200, matched_story.text
    assert matched_story.json()["plan"]["story_id"] == "s1"


def test_artifact_story_mismatch_is_409(env):
    artifact_id = _store_artifact(env)
    job = _job()
    job["clip_sets"][0]["stories"].append({
        "id": "s2",
        "title": "Other story",
        "dur": 20.0,
        "start": 10.0,
        "end": 30.0,
        "clips": [],
    })
    _write_job(env.directory, job)
    client = TestClient(app.app)
    conflict = _post(client, env, {
        "artifact_id": artifact_id,
        "story_id": "s2",
        "aspect": "9:16",
        "layers": [_layer()],
    })
    assert conflict.status_code == 409
    assert "different story" in conflict.json()["detail"].lower()


def test_legacy_artifact_cannot_be_verified_against_explicit_story(env):
    artifact_id = _store_artifact(env, legacy=True)
    client = TestClient(app.app)
    conflict = _post(client, env, {
        "artifact_id": artifact_id,
        "story_id": "s1",
        "aspect": "9:16",
        "layers": [_layer()],
    })
    assert conflict.status_code == 409
    assert "cannot be verified" in conflict.json()["detail"]

    no_context = _post(client, env, {
        "artifact_id": artifact_id,
        "aspect": "9:16",
        "layers": [_layer()],
    })
    assert no_context.status_code == 200, no_context.text
    assert no_context.json()["plan"]["story_id"] is None


def test_missing_job_artifact_and_style_anchor_errors(env):
    client = TestClient(app.app)
    missing_job = client.post(
        "/api/jobs/nope/overlays/plan",
        json={"aspect": "9:16", "layers": [_layer()]},
    )
    assert missing_job.status_code == 404
    assert missing_job.json()["detail"] == "Job not found."

    missing_artifact = _post(client, env, {
        "artifact_id": "art_" + "0" * 24,
        "aspect": "9:16",
        "layers": [_layer()],
    })
    assert missing_artifact.status_code == 404

    invalid_anchor = _post(client, env, {
        "aspect": "9:16",
        "layers": [_layer(anchor="diagonal")],
    })
    assert invalid_anchor.status_code == 422

    styled = _post(client, env, {
        "aspect": "4:5",
        "layers": [
            _layer(
                anchor="bottom",
                style={"color": "#fff", "size": 52, "uppercase": True},
            ),
        ],
    })
    assert styled.status_code == 200, styled.text
    layer = styled.json()["plan"]["layers"][0]
    assert layer["anchor"] == "bottom-center"
    assert layer["style"]["color"] == "#ffffff"
    assert layer["style"]["size"] == 52
    assert layer["style"]["uppercase"] is True
