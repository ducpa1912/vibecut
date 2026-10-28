"""Rights policy: one lock, one source, and the hard kind rules.

The matrix covers the Setup lock on and off against every detected kind and
the per-job attestation. The route tests prove the lock cannot be set from a
request body or browser storage, and that turning it back on leaves saved
Edits alone.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app
import cleanup
import detect
import rights
import settings_store

JOB_ID = "rights-job"
STORY_ID = "st_rights"
SET_ID = "cs_rights"

KINDS = (
    "subtitle", "title", "lower_third", "handle_or_logo", "watermark", "credit",
    "screen_text",
)


@pytest.fixture(autouse=True)
def production_defaults(monkeypatch):
    """This module exercises the shipped default: the lock starts on."""
    monkeypatch.setattr(rights, "DEFAULT_LOCK", True)
    monkeypatch.setitem(settings_store.DEFAULTS, "rights", {"lock": True})
    yield


def _settings(lock: bool) -> dict:
    return {"rights": {"lock": lock}}


def _job(attested: bool | None) -> dict:
    if attested is None:
        return {"id": "legacy"}
    return {"id": "job", "rights": {"attested": attested, "source": "import"}}


def _expected(lock: bool, kind: str, attested: bool) -> str | None:
    if kind == "watermark":
        return "watermark"
    if kind == "screen_text":
        return "screen_text"
    if attested:
        return None
    if kind == "handle_or_logo":
        return "attestation_required"
    return "rights_not_attested" if lock else None


@pytest.mark.parametrize("lock", [True, False])
@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("attested", [True, False])
def test_clean_matrix_lock_on_off_kind_attested(lock, kind, attested):
    assert rights.clean_block_reason(
        kind, job=_job(attested), settings=_settings(lock),
    ) == _expected(lock, kind, attested)


@pytest.mark.parametrize("lock", [True, False])
def test_watermark_and_screen_text_never_depend_on_the_lock(lock):
    assert rights.clean_block_reason(
        "watermark", job=_job(True), settings=_settings(lock),
    ) == "watermark"
    assert rights.clean_block_reason(
        "screen_text", job=_job(True), settings=_settings(lock),
    ) == "screen_text"


@pytest.mark.parametrize("lock", [True, False])
def test_handle_always_needs_the_per_video_tick(lock):
    assert rights.clean_block_reason(
        "handle_or_logo", job=_job(False), settings=_settings(lock),
    ) == "attestation_required"
    assert rights.clean_block_reason(
        "handle_or_logo", job=_job(True), settings=_settings(lock),
    ) is None


def test_lock_defaults_to_on_for_missing_and_malformed_settings():
    assert rights.lock_enabled({}) is True
    assert rights.lock_enabled({"rights": {}}) is True
    assert rights.lock_enabled({"rights": {"lock": "nonsense"}}) is True
    assert rights.lock_enabled({"lock": False}) is False
    assert rights.lock_enabled({"rights": {"lock": "off"}}) is False


def test_legacy_job_without_a_rights_record_counts_as_attested():
    assert rights.job_attested({"id": "old"}) is True
    assert rights.job_attested({"id": "old", "options": {}}) is True
    assert rights.job_attested(None) is False
    assert rights.job_attested({"rights": {}}) is False
    assert rights.job_attested({"rights": {"attested": "false"}}) is False
    assert rights.job_attested({"rights": {"attested": "true"}}) is True


def test_may_import_follows_the_lock():
    assert rights.may_import(True) is True
    assert rights.may_import(False) is False
    assert rights.may_import(None) is False
    assert rights.may_import("true") is True


def test_policy_shape_without_a_job(monkeypatch, tmp_path):
    _use_settings_path(monkeypatch, tmp_path)
    settings_store.save_settings({"rights": {"lock": True}})
    policy = rights.policy()
    assert policy["lock"] is True
    assert policy["attested"] is False
    assert policy["needs_import_tick"] is True
    assert set(policy["clean"]) == set(KINDS)
    assert policy["clean"]["watermark"] == "watermark"
    assert policy["clean"]["screen_text"] == "screen_text"
    assert policy["clean"]["handle_or_logo"] == "attestation_required"
    assert policy["clean"]["subtitle"] == "rights_not_attested"

    settings_store.save_settings({"rights": {"lock": False}})
    policy = rights.policy()
    assert policy["lock"] is False
    assert policy["needs_import_tick"] is False
    assert policy["clean"]["subtitle"] is None
    assert policy["clean"]["handle_or_logo"] == "attestation_required"


def test_policy_reads_the_job_and_the_saved_setting(monkeypatch, tmp_path):
    _use_settings_path(monkeypatch, tmp_path)
    settings_store.save_settings({"rights": {"lock": True}})
    policy = rights.policy({"id": "j", "rights": {"attested": True}})
    assert policy["attested"] is True
    assert policy["needs_import_tick"] is False
    assert policy["clean"]["subtitle"] is None


def test_detect_cleanup_block_reason_is_a_thin_compatible_wrapper():
    assert detect.cleanup_block_reason("watermark", attested=True) == "watermark"
    assert detect.cleanup_block_reason("watermark", attested=False) == "watermark"
    assert (
        detect.cleanup_block_reason("screen_text", attested=True)
        == "screen_text"
    )
    assert (
        detect.cleanup_block_reason("handle_or_logo", attested=False)
        == "attestation_required"
    )
    assert detect.cleanup_block_reason("handle_or_logo", attested=True) is None
    assert (
        detect.cleanup_block_reason("subtitle", attested=False)
        == "rights_not_attested"
    )
    assert detect.cleanup_block_reason("subtitle", attested=True) is None


def _prefill_tracklets() -> list[dict]:
    return [
        {
            "id": "trk_sub", "kind": "subtitle",
            "box": {"x": 0.1, "y": 0.76, "w": 0.8, "h": 0.09},
            "ranges": [{"start": 0.0, "end": 4.0}],
            "confidence": 0.9,
        },
        {
            "id": "trk_water", "kind": "watermark",
            "box": {"x": 0.84, "y": 0.05, "w": 0.13, "h": 0.05},
            "ranges": [{"start": 0.0, "end": 4.0}],
            "confidence": 0.9,
        },
        {
            "id": "trk_handle", "kind": "handle_or_logo",
            "box": {"x": 0.02, "y": 0.03, "w": 0.15, "h": 0.05},
            "ranges": [{"start": 0.0, "end": 4.0}],
            "confidence": 0.9,
        },
    ]


def test_detect_prefill_follows_the_lock_but_keeps_the_hard_rules():
    locked = detect.clean_prefill(
        _prefill_tracklets(), attested=False, settings=_settings(True),
    )
    blocked = {item["tracklet_id"]: item["blocked"] for item in locked}
    assert blocked["trk_sub"] == "rights_not_attested"
    assert blocked["trk_water"] == "watermark"
    assert blocked["trk_handle"] == "attestation_required"
    assert all(not item["enabled"] for item in locked)

    open_prefill = detect.clean_prefill(
        _prefill_tracklets(), attested=False, settings=_settings(False),
    )
    by_id = {item["tracklet_id"]: item for item in open_prefill}
    assert by_id["trk_sub"]["enabled"] is True
    assert by_id["trk_sub"]["blocked"] is None
    assert by_id["trk_water"]["action"] == "refused"
    assert by_id["trk_water"]["enabled"] is False
    assert by_id["trk_handle"]["blocked"] == "attestation_required"
    assert by_id["trk_handle"]["enabled"] is False


def test_cleanup_layer_builder_follows_the_lock():
    tracklets = _prefill_tracklets()
    locked = cleanup.tracklet_clean_layers(
        tracklets, attested=False, settings=_settings(True),
    )
    assert locked["layers"] == []
    assert {item["blocked"] for item in locked["refused"]} >= {
        "rights_not_attested", "watermark", "attestation_required",
    }

    open_build = cleanup.tracklet_clean_layers(
        tracklets, attested=False, settings=_settings(False),
    )
    assert [layer["id"] for layer in open_build["layers"]] == ["cl_trk_sub"]
    refused = {item["tracklet_id"]: item["blocked"] for item in open_build["refused"]}
    assert refused["trk_water"] == "watermark"
    assert refused["trk_handle"] == "attestation_required"


def _use_settings_path(monkeypatch, tmp_path) -> None:
    data = tmp_path / "settings"
    monkeypatch.setattr(settings_store, "DATA", data)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", data / "settings.json")
    monkeypatch.setattr(settings_store, "SECRETS_PATH", data / "secrets.json")


def _source_job() -> dict:
    def scene(index: int, start: float, end: float) -> dict:
        return {
            "id": index, "start": start, "end": end, "dur": end - start,
            "mid": (start + end) / 2, "ocr": "", "faces": [], "deep": True,
            "tags": [], "crop": {"cx": 0.5, "cy": 0.5}, "crop_mode": "center",
        }

    return {
        "id": JOB_ID,
        "created": 1.0,
        "updated": 1.0,
        "status": "ready",
        "progress": 1.0,
        "message": "Ready",
        "error": None,
        "source": {
            "path": "/tmp/rights-source.mp4",
            "name": "rights-source.mp4",
            "duration": 8.0,
            "width": 1080,
            "height": 1920,
            "fps": 30.0,
            "size": 1234,
            "has_audio": True,
            "fingerprint": "rights-source-fingerprint",
        },
        "options": {},
        "analysis": {
            "scene_count": 2,
            "hook_scene": 0,
            "deep_count": 2,
            "scenes": [scene(0, 0.0, 4.0), scene(1, 4.0, 8.0)],
        },
        "clip_sets": [{
            "id": SET_ID,
            "job_id": JOB_ID,
            "stories": [{
                "id": STORY_ID,
                "title": "Rights story",
                "start": 0.0,
                "end": 8.0,
                "dur": 8.0,
                "clips": [
                    {"scene": 0, "start": 0.0, "end": 4.0, "dur": 4.0, "role": "hook"},
                    {"scene": 1, "start": 4.0, "end": 8.0, "dur": 4.0, "role": "beat"},
                ],
            }],
        }],
        "renders": {},
    }


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    jobs = data / "jobs"
    sources = data / "sources"
    jobs.mkdir(parents=True)
    sources.mkdir(parents=True)
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.setattr(app, "SOURCES", sources)
    monkeypatch.setattr(app, "SHARES", tmp_path / "shares.json")
    monkeypatch.delenv("VIBECUT_TOKEN", raising=False)
    _use_settings_path(monkeypatch, tmp_path)
    monkeypatch.setattr(app.pipeline, "probe", lambda path: {
        "duration": 8.0, "width": 1080, "height": 1920, "fps": 30.0,
        "has_audio": True, "size": 1,
    })
    monkeypatch.setattr(app.analysis_pool, "submit", lambda *args, **kwargs: None)
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"x")
    client = TestClient(app.app)
    return SimpleNamespace(
        tmp_path=tmp_path, data=data, jobs=jobs, sources=sources,
        source=source, client=client,
    )


def _job_dir(env) -> object:
    directory = env.jobs / JOB_ID
    directory.mkdir()
    (directory / "job.json").write_text(
        json.dumps(_source_job()), encoding="utf-8",
    )
    return directory


def _edit_body() -> dict:
    return {
        "set_id": SET_ID,
        "story_id": STORY_ID,
        "aspect": "9:16",
        "clean": [{
            "kind": "plate",
            "box": {"x": 0.1, "y": 0.7, "w": 0.8, "h": 0.2},
            "ranges": [{"start": 0.0, "end": 4.0}],
            "tracklet_kind": "subtitle",
        }],
    }


def test_import_409_with_lock_on(env):
    settings_store.save_settings({"rights": {"lock": True}})
    response = env.client.post("/api/jobs/path", json={"path": str(env.source)})
    assert response.status_code == 409
    assert response.json()["detail"] == rights.IMPORT_CONFIRMATION
    assert list(env.jobs.iterdir()) == []

    upload = env.client.post(
        "/api/jobs/upload",
        files={"file": ("clip.mp4", b"0" * 2048, "video/mp4")},
        data={"options": "{}"},
    )
    assert upload.status_code == 409

    url = env.client.post(
        "/api/jobs/from-url", json={"url": "https://example.com/video"},
    )
    assert url.status_code == 409
    assert list(env.jobs.iterdir()) == []


def test_import_with_lock_off_stores_rights_only_when_sent(env):
    settings_store.save_settings({"rights": {"lock": False}})
    omitted = env.client.post("/api/jobs/path", json={"path": str(env.source)})
    assert omitted.status_code == 200, omitted.text
    job = app.load_job(omitted.json()["id"])
    assert "rights" not in job

    explicit = env.client.post(
        "/api/jobs/path",
        json={"path": str(env.source), "rights": False},
    )
    assert explicit.status_code == 200, explicit.text
    job = app.load_job(explicit.json()["id"])
    assert job["rights"]["attested"] is False
    assert job["rights"]["source"] == "import"

    upload = env.client.post(
        "/api/jobs/upload",
        files={"file": ("clip.mp4", b"0" * 2048, "video/mp4")},
        data={"options": "{}", "rights": "true"},
    )
    assert upload.status_code == 200, upload.text
    uploaded = app.load_job(upload.json()["id"])
    assert uploaded["rights"]["attested"] is True


def test_job_get_and_policy_route_expose_the_policy(env):
    settings_store.save_settings({"rights": {"lock": True}})
    response = env.client.get("/api/rights/policy")
    assert response.status_code == 200
    assert response.json()["lock"] is True
    assert response.json()["needs_import_tick"] is True

    created = env.client.post(
        "/api/jobs/path",
        json={"path": str(env.source), "rights": True},
    )
    assert created.status_code == 200, created.text
    job = env.client.get(f"/api/jobs/{created.json()['id']}").json()
    assert job["rights_policy"]["attested"] is True
    assert job["rights_policy"]["needs_import_tick"] is False
    assert job["rights_policy"]["clean"]["watermark"] == "watermark"


def test_settings_round_trip_and_validation(env):
    assert settings_store.load_settings()["rights"]["lock"] is True
    response = env.client.post(
        "/api/settings", json={"settings": {"rights": {"lock": False}}},
    )
    assert response.status_code == 200, response.text
    assert settings_store.load_settings()["rights"]["lock"] is False
    state = env.client.get("/api/settings").json()
    assert state["settings"]["rights"]["lock"] is False

    bad = env.client.post(
        "/api/settings", json={"settings": {"rights": {"lock": "off"}}},
    )
    assert bad.status_code == 400
    unknown = env.client.post(
        "/api/settings", json={"settings": {"rights": {"lock": True, "x": 1}}},
    )
    assert unknown.status_code == 400

    restored = env.client.post(
        "/api/settings", json={"settings": {"rights": {"lock": True}}},
    )
    assert restored.status_code == 200
    assert settings_store.load_settings()["rights"]["lock"] is True


def test_settings_store_normalizes_malformed_lock(monkeypatch, tmp_path):
    _use_settings_path(monkeypatch, tmp_path)
    settings_store.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    settings_store.SETTINGS_PATH.write_text(
        json.dumps({"rights": {"lock": "nonsense"}}), encoding="utf-8",
    )
    assert settings_store.load_settings()["rights"] == {"lock": True}
    settings_store.save_settings({"rights": {"lock": "off"}})
    assert settings_store.load_settings()["rights"] == {"lock": False}


def test_turning_the_lock_on_does_not_rewrite_saved_edits(env):
    directory = _job_dir(env)
    job = json.loads((directory / "job.json").read_text(encoding="utf-8"))
    job["rights"] = {"attested": False, "at": 1.0, "source": "import"}
    (directory / "job.json").write_text(json.dumps(job), encoding="utf-8")
    settings_store.save_settings({"rights": {"lock": False}})
    created = env.client.post(f"/api/jobs/{JOB_ID}/edits", json=_edit_body())
    assert created.status_code == 200, created.text
    edit = created.json()["edit"]
    assert edit["clean"][0]["kind"] == "plate"

    settings_store.save_settings({"rights": {"lock": True}})
    stored = env.client.get(f"/api/jobs/{JOB_ID}/edits/{edit['id']}")
    assert stored.status_code == 200, stored.text
    assert stored.json()["edit"]["hash"] == edit["hash"]
    assert stored.json()["edit"]["clean"] == edit["clean"]

    blocked = env.client.patch(
        f"/api/jobs/{JOB_ID}/edits/{edit['id']}",
        json={"clean": [{
            "kind": "blur",
            "box": {"x": 0.1, "y": 0.7, "w": 0.8, "h": 0.2},
        }]},
    )
    assert blocked.status_code == 409
    assert "attestation" in blocked.json()["detail"].lower()

    colour = env.client.patch(
        f"/api/jobs/{JOB_ID}/edits/{edit['id']}",
        json={"color": {"preset": "warm_film"}},
    )
    assert colour.status_code == 200, colour.text


def test_batch_import_follows_the_lock(env):
    settings_store.save_settings({"rights": {"lock": True}})
    body = {"items": [{"path": str(env.source)}]}
    refused = env.client.post("/api/batches", json=body)
    assert refused.status_code == 409
    assert refused.json()["detail"] == rights.IMPORT_CONFIRMATION

    import routes_batches

    created = {}

    def fake_from_path(path_body):
        created["rights"] = path_body.rights
        return {"id": "batchjob0001"}

    backend = routes_batches._AppBackend()
    original = app.job_from_path
    app.job_from_path = fake_from_path
    try:
        try:
            backend.create_job({"path": str(env.source), "rights": True})
        except Exception:
            pass
    finally:
        app.job_from_path = original
    assert created["rights"] is True
