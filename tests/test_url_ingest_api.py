"""API and background-worker tests for URL ingest (agent D)."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app
import settings_store
from url_ingest import registry
from url_ingest.base import IngestError, IngestOptions, IngestResult


class CapturePool:
    """Run nothing now; record what the background worker would analyse."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def submit(self, fn, *args, **kwargs):
        self.calls.append((fn, args, kwargs))
        return None


class FakeProvider:
    id = "cobalt"
    label = "Cobalt"

    def __init__(
        self,
        *,
        id: str | None = None,
        label: str | None = None,
        inspect_result: dict | None = None,
        inspect_error: Exception | None = None,
        status_result: dict | None = None,
        download_error: Exception | None = None,
        wait_for_cancel: bool = False,
    ) -> None:
        if id is not None:
            self.id = id
        if label is not None:
            self.label = label
        self.inspect_result = inspect_result
        self.inspect_error = inspect_error
        self.status_result = status_result
        self.download_error = download_error
        self.wait_for_cancel = wait_for_cancel
        self.started = threading.Event()
        self.temp_path: Path | None = None
        self.options: IngestOptions | None = None

    def inspect(self, url: str, options: IngestOptions) -> dict:
        if self.inspect_error is not None:
            raise self.inspect_error
        return dict(self.inspect_result or {})

    def status(self, settings=None) -> dict:
        return dict(
            self.status_result
            or {
                "id": self.id,
                "label": self.label,
                "configured": True,
                "available": True,
                "error": "",
            }
        )

    def download(self, url, dest, options, progress, cancel_event):
        self.temp_path = Path(dest)
        self.options = options
        self.started.set()
        progress(0.25, "Downloading test video")
        if self.wait_for_cancel:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if cancel_event.wait(0.01):
                    raise IngestError("Download cancelled.")
            raise AssertionError("cancel event was never set")
        if self.download_error is not None:
            raise self.download_error
        dest.write_bytes(b"fake video bytes")
        progress(0.9, "Saving test video")
        return IngestResult(
            path=dest,
            filename="clip.mp4",
            provider=self.id,
            title="Clip title",
            duration=12.5,
            thumbnail="https://example.test/thumb.jpg",
            meta={"service": "test", "parts": 1},
        )


def install_provider(monkeypatch, provider: FakeProvider, captured: dict | None = None):
    def fake_provider(provider_id: str, settings=None):
        if captured is not None:
            captured["provider"] = provider_id
            captured["settings"] = settings
        return provider

    monkeypatch.setattr(app.registry, "provider", fake_provider)


def wait_for(callable_, timeout: float = 6.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            last = callable_()
        except Exception:  # noqa: BLE001
            last = None
        if last:
            return last
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting; last={last!r}")


def wait_status(client: TestClient, job_id: str, statuses: set[str]) -> dict:
    def check():
        response = client.get(f"/api/jobs/{job_id}/status")
        if response.status_code != 200:
            return None
        body = response.json()
        return body if body.get("status") in statuses else None

    return wait_for(check)


def wait_history(client: TestClient, job_id: str) -> list[dict]:
    def check():
        response = client.get(f"/api/jobs/{job_id}/history")
        if response.status_code != 200:
            return None
        entries = response.json().get("entries") or []
        return entries or None

    return wait_for(check)


@pytest.fixture
def api(tmp_path, monkeypatch):
    data = tmp_path / "data"
    jobs = data / "jobs"
    sources = data / "sources"
    jobs.mkdir(parents=True)
    sources.mkdir(parents=True)
    monkeypatch.setattr(settings_store, "DATA", data)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", data / "settings.json")
    monkeypatch.setattr(settings_store, "SECRETS_PATH", data / "secrets.json")
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.setattr(app, "SOURCES", sources)
    monkeypatch.setattr(app, "INGEST_CANCELS", {})
    import url_ingest.ytdlp as ytdlp_module
    monkeypatch.setattr(ytdlp_module, "ytdlp_available", lambda: True)
    monkeypatch.setattr(app, "_resolved_addresses", lambda host: ("93.184.216.34",))
    pool = CapturePool()
    monkeypatch.setattr(app, "analysis_pool", pool)

    for names in settings_store.ENV_KEYS.values():
        for env_name in names:
            monkeypatch.delenv(env_name, raising=False)

    client = TestClient(app.app)
    client.capture_pool = pool  # type: ignore[attr-defined]
    client.data_dir = data  # type: ignore[attr-defined]
    return client


def test_ingest_meta_redacts_tokens_from_url_fields():
    clean = app._redact_ingest_meta(
        {
            "webpage_url": "https://www.xiaohongshu.com/explore/x?xsec_token=secret",
            "note_url": "https://www.xiaohongshu.com/explore/x?xsec_token=secret",
            "service": "test",
        }
    )
    assert clean["service"] == "test"
    assert "secret" not in clean["webpage_url"]
    assert "secret" not in clean["note_url"]
    assert "redacted" in clean["webpage_url"]
    nested = app._redact_ingest_meta(
        {
            "attempts": [
                {"provider": "ytdlp", "error": "failed https://x.test/?xsec_token=nested-secret"},
            ],
            "api_key": "nested-api-key",
        }
    )
    assert "nested-secret" not in str(nested)
    assert "nested-api-key" not in str(nested)
    assert app._redact_ingest_meta({"cookie_set": True, "session_ok": False}) == {
        "cookie_set": True,
        "session_ok": False,
    }


def test_settings_defaults_match_registry(api):
    body = api.get("/api/settings")
    assert body.status_code == 200
    assert body.json()["settings"]["ingest"] == registry.DEFAULT_INGEST_SETTINGS
    assert "cobalt" in body.json()["secrets"]
    assert "xhs" in body.json()["secrets"]


@pytest.mark.parametrize(
    "patch",
    [
        {"provider": "bogus"},
        {"cobalt_quality": "8k"},
        {"cobalt_codec": "theora"},
        {"cobalt_local_processing": "disabled"},
        {"ytdlp_quality": "8k"},
        {"ytdlp_codec": "theora"},
        {"ytdlp_container": "avi"},
        {"ytdlp_audio": "lossless"},
        {"ytdlp_cookies": "keychain"},
        {"ytdlp_browser": "netscape"},
        {"xhs_interval": -1},
    ],
)
def test_settings_reject_invalid_ingest_values(api, patch):
    response = api.post("/api/settings", json={"settings": {"ingest": patch}})
    assert response.status_code == 400


def test_settings_save_masks_ingest_secrets(api):
    response = api.post(
        "/api/settings",
        json={
            "settings": {
                "ingest": {
                    "provider": "xhs_get",
                    "cobalt_url": "http://127.0.0.1:9000/",
                    "cobalt_quality": "720",
                    "cobalt_codec": "av1",
                    "cobalt_local_processing": "forced",
                    "xhs_url": "http://127.0.0.1:5789",
                    "xhs_no_record": False,
                    "xhs_interval": 3.5,
                    "cobalt_api_key": "must-not-persist",
                    "xhs_token": "must-not-persist",
                },
            },
            "secrets": {"cobalt": "cobalt-secret-value", "xhs": "xhs-secret-value"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    ingest = body["settings"]["ingest"]
    assert ingest["provider"] == "xhs"
    assert ingest["cobalt_quality"] == "720"
    assert ingest["cobalt_codec"] == "av1"
    assert ingest["cobalt_local_processing"] == "forced"
    assert ingest["xhs_no_record"] is False
    assert ingest["xhs_interval"] == 3.5
    assert "cobalt_api_key" not in ingest
    assert "xhs_token" not in ingest
    assert body["secrets"]["cobalt"] is True
    assert body["secrets"]["xhs"] is True
    assert body["sources"]["cobalt"] == "file"
    assert body["sources"]["xhs"] == "file"
    assert "cobalt-secret-value" not in response.text
    assert "xhs-secret-value" not in response.text
    assert "must-not-persist" not in response.text
    assert settings_store.get_secret("cobalt") == "cobalt-secret-value"
    assert settings_store.get_secret("xhs") == "xhs-secret-value"
    persisted = settings_store.SETTINGS_PATH.read_text()
    assert "cobalt-secret-value" not in persisted
    assert "xhs-secret-value" not in persisted
    assert "cobalt_api_key" not in persisted
    assert "xhs_token" not in persisted


def test_settings_save_ytdlp_defaults_and_cookie_mode(api):
    response = api.post(
        "/api/settings",
        json={
            "settings": {
                "ingest": {
                    "provider": "ytdlp",
                    "ytdlp_quality": "1440",
                    "ytdlp_codec": "any",
                    "ytdlp_container": "mkv",
                    "ytdlp_audio": "192",
                    "ytdlp_cookies": "file",
                    "ytdlp_browser": "chrome",
                    "ytdlp_cookie_file": "/tmp/vibecut-cookies.txt",
                }
            }
        },
    )
    assert response.status_code == 200
    ingest = response.json()["settings"]["ingest"]
    assert ingest["provider"] == "ytdlp"
    assert ingest["ytdlp_quality"] == "1440"
    assert ingest["ytdlp_codec"] == "any"
    assert ingest["ytdlp_container"] == "mkv"
    assert ingest["ytdlp_audio"] == "192"
    assert ingest["ytdlp_cookies"] == "file"
    assert ingest["ytdlp_browser"] == "chrome"
    assert ingest["ytdlp_cookie_file"] == "/tmp/vibecut-cookies.txt"


def test_settings_partial_ingest_patch_keeps_existing_values(api):
    first = api.post(
        "/api/settings",
        json={
            "settings": {
                "ingest": {
                    "provider": "xhs",
                    "cobalt_quality": "720",
                    "cobalt_codec": "vp9",
                    "cobalt_local_processing": "forced",
                    "xhs_interval": 4,
                }
            }
        },
    )
    assert first.status_code == 200

    second = api.post(
        "/api/settings", json={"settings": {"ingest": {"cobalt_quality": "480"}}}
    )
    assert second.status_code == 200
    ingest = second.json()["settings"]["ingest"]
    assert ingest["provider"] == "xhs"
    assert ingest["cobalt_quality"] == "480"
    assert ingest["cobalt_codec"] == "vp9"
    assert ingest["cobalt_local_processing"] == "forced"
    assert ingest["xhs_interval"] == 4.0


def test_inspect_returns_provider_status_meta_and_session(api, monkeypatch):
    provider = FakeProvider(
        id="cobalt",
        inspect_result={
            "provider": "cobalt",
            "label": "Cobalt",
            "available": True,
            "warning": "",
            "title": "Clip title",
            "filename": "clip.mp4",
            "status": "tunnel",
        },
    )
    captured: dict = {}
    install_provider(monkeypatch, provider, captured)

    response = api.post(
        "/api/url/inspect",
        json={"url": "https://youtube.com/watch?v=abc", "options": {"quality": "720"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "ytdlp"
    assert body["label"] == "Cobalt"
    assert body["available"] is True
    assert body["warning"] == ""
    assert body["session"] == {}
    assert body["meta"]["filename"] == "clip.mp4"
    assert body["meta"]["status"] == "tunnel"
    assert body["title"] == "Clip title"
    assert body["options"]["quality"] == "720"
    assert body["provider_status"]["available"] is True
    assert captured["provider"] == "ytdlp"
    assert captured["settings"]["ingest"]["cobalt_api_key"] == ""
    assert captured["settings"]["ingest"]["ytdlp_quality"] == "max"
    assert "cobalt_api_key" not in response.text


def enable_cobalt_fallback(api):
    response = api.post(
        "/api/settings",
        json={"settings": {"ingest": {"cobalt_fallback": True}}},
    )
    assert response.status_code == 200


def test_provider_order_only_adds_enabled_cobalt_fallback(monkeypatch):
    import url_ingest.ytdlp as ytdlp_module
    monkeypatch.setattr(ytdlp_module, "ytdlp_available", lambda: True)
    settings = {
        "ingest": {
            "provider": "auto",
            "cobalt_url": "http://127.0.0.1:9000/",
            "cobalt_fallback": False,
        }
    }
    assert app._ingest_provider_order("https://youtube.com/watch?v=abc", None, settings) == [
        "ytdlp"
    ]
    settings["ingest"]["cobalt_fallback"] = True
    assert app._ingest_provider_order("https://youtube.com/watch?v=abc", None, settings) == [
        "ytdlp",
        "cobalt",
    ]
    assert app._ingest_provider_order(
        "https://youtube.com/watch?v=abc", "ytdlp", settings
    ) == ["ytdlp"]
    assert app._ingest_provider_order(
        "https://www.xiaohongshu.com/explore/1?xsec_token=x", None, settings
    ) == ["xhs"]


def test_auto_inspect_falls_back_to_cobalt_after_ytdlp_failure(api, monkeypatch):
    enable_cobalt_fallback(api)
    primary = FakeProvider(
        id="ytdlp",
        label="yt-dlp",
        inspect_error=IngestError("yt-dlp does not support this URL."),
    )
    fallback = FakeProvider(
        id="cobalt",
        label="Cobalt",
        inspect_result={
            "provider": "cobalt",
            "label": "Cobalt",
            "available": True,
            "title": "Fallback clip",
            "status": "tunnel",
        },
    )
    calls: list[str] = []

    def fake_provider(provider_id: str, settings=None):
        calls.append(provider_id)
        return {"ytdlp": primary, "cobalt": fallback}[provider_id]

    monkeypatch.setattr(app.registry, "provider", fake_provider)
    response = api.post(
        "/api/url/inspect", json={"url": "https://example.com/video"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "cobalt"
    assert body["label"] == "Cobalt"
    assert body["title"] == "Fallback clip"
    assert calls == ["ytdlp", "cobalt"]
    assert [item["provider"] for item in body["attempts"]] == ["ytdlp", "cobalt"]


def test_explicit_ytdlp_does_not_fallback(api, monkeypatch):
    provider = FakeProvider(
        id="ytdlp",
        label="yt-dlp",
        inspect_error=IngestError("private video"),
    )
    calls: list[str] = []

    def fake_provider(provider_id: str, settings=None):
        calls.append(provider_id)
        return provider

    monkeypatch.setattr(app.registry, "provider", fake_provider)
    response = api.post(
        "/api/url/inspect",
        json={"url": "https://example.com/video", "provider": "ytdlp"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["provider"] == "ytdlp"
    assert calls == ["ytdlp"]


def test_inspect_detects_xhs_and_returns_session_warning(api, monkeypatch):
    provider = FakeProvider(
        id="xhs",
        inspect_result={
            "provider": "xhs",
            "label": "XHS / RedNote",
            "available": False,
            "warning": "XHS has no signed-in cookie.",
            "error": "XHS has no signed-in cookie.",
            "title": "",
            "has_xsec_token": True,
        },
        status_result={
            "id": "xhs",
            "label": "XHS / RedNote",
            "configured": True,
            "available": False,
            "error": "XHS has no signed-in cookie.",
            "cookie_set": False,
            "session_ok": None,
            "auth_required": False,
            "service_url": "http://127.0.0.1:5789",
            "session": {
                "cookie_set": False,
                "session_ok": None,
                "auth_required": False,
                "service_url": "http://127.0.0.1:5789",
            },
        },
    )
    captured: dict = {}
    install_provider(monkeypatch, provider, captured)

    response = api.post(
        "/api/url/inspect",
        json={"url": "https://www.xiaohongshu.com/explore/1?xsec_token=abc"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "xhs"
    assert body["available"] is False
    assert "signed-in cookie" in body["warning"]
    assert body["session"]["cookie_set"] is False
    assert body["session"]["service_url"] == "http://127.0.0.1:5789"
    assert captured["provider"] == "xhs"


def test_inspect_provider_error_is_inline_warning(api, monkeypatch):
    provider = FakeProvider(inspect_error=IngestError("Cobalt is not reachable."))
    install_provider(monkeypatch, provider)

    response = api.post(
        "/api/url/inspect", json={"url": "https://youtube.com/watch?v=down"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert "not reachable" in body["warning"]


def test_inspect_rejects_invalid_url_before_provider(api, monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("provider must not be built for an invalid URL")

    monkeypatch.setattr(app.registry, "provider", explode)
    response = api.post("/api/url/inspect", json={"url": "not a url"})
    assert response.status_code == 400


def test_from_url_uses_provider_that_succeeded_at_inspection(api, monkeypatch):
    enable_cobalt_fallback(api)
    primary = FakeProvider(
        id="ytdlp",
        label="yt-dlp",
        inspect_error=IngestError("yt-dlp cannot inspect."),
    )
    fallback = FakeProvider(
        id="cobalt",
        label="Cobalt",
        inspect_result={"available": True, "title": "Cobalt clip"},
    )
    calls: list[str] = []

    def fake_provider(provider_id: str, settings=None):
        calls.append(provider_id)
        return {"ytdlp": primary, "cobalt": fallback}[provider_id]

    monkeypatch.setattr(app.registry, "provider", fake_provider)
    monkeypatch.setattr(
        app.pipeline,
        "probe",
        lambda path: {
            "path": str(path),
            "duration": 12.5,
            "width": 1280,
            "height": 720,
            "fps": 30.0,
            "has_audio": True,
            "size": 16,
        },
    )

    response = api.post(
        "/api/jobs/from-url", json={"url": "https://example.com/video"}
    )
    assert response.status_code == 200
    job_id = response.json()["id"]
    wait_status(api, job_id, {"queued"})

    job = api.get(f"/api/jobs/{job_id}").json()
    assert job["ingest"]["provider"] == "cobalt"
    assert calls == ["ytdlp", "cobalt", "cobalt"]


def test_failed_ingest_redacts_tokens_from_attempts_and_history(api, monkeypatch):
    secret = "SECRET-TOKEN-123"
    provider = FakeProvider(
        download_error=IngestError(
            f"provider failed at https://example.test/x?xsec_token={secret}"
        )
    )
    install_provider(monkeypatch, provider)

    response = api.post(
        "/api/jobs/from-url",
        json={"url": f"https://example.test/x?xsec_token={secret}"},
    )
    assert response.status_code == 200
    job_id = response.json()["id"]
    wait_status(api, job_id, {"failed"})

    job_file = api.data_dir / "jobs" / job_id / "job.json"
    job_text = job_file.read_text()
    job = json.loads(job_text)
    attempts = job["ingest"]["attempts"]
    assert attempts
    assert all(secret not in json.dumps(attempt) for attempt in attempts)

    entries = wait_history(api, job_id)
    entry = entries[0]
    detail = api.get(f"/api/jobs/{job_id}/history/{entry['id']}").json()
    assert secret not in json.dumps(entry)
    assert secret not in json.dumps(detail)
    assert secret not in job_text
    assert "redacted" in json.dumps(attempts)


def test_from_url_download_falls_back_to_cobalt_and_records_attempts(api, monkeypatch):
    enable_cobalt_fallback(api)
    primary = FakeProvider(
        id="ytdlp",
        label="yt-dlp",
        download_error=IngestError("yt-dlp extractor failed."),
    )
    fallback = FakeProvider(id="cobalt", label="Cobalt")
    calls: list[str] = []

    def fake_provider(provider_id: str, settings=None):
        calls.append(provider_id)
        return {"ytdlp": primary, "cobalt": fallback}[provider_id]

    monkeypatch.setattr(app.registry, "provider", fake_provider)
    monkeypatch.setattr(
        app.pipeline,
        "probe",
        lambda path: {
            "path": str(path),
            "duration": 12.5,
            "width": 1280,
            "height": 720,
            "fps": 30.0,
            "has_audio": True,
            "size": 16,
        },
    )

    response = api.post(
        "/api/jobs/from-url", json={"url": "https://example.com/video"}
    )
    assert response.status_code == 200
    job_id = response.json()["id"]
    wait_status(api, job_id, {"queued"})

    job = api.get(f"/api/jobs/{job_id}").json()
    assert job["ingest"]["provider"] == "cobalt"
    assert job["ingest"]["label"] == "Cobalt"
    assert job["ingest"]["meta"]["fallback"]["used"] is True
    assert [item["provider"] for item in job["ingest"]["meta"]["attempts"]] == [
        "ytdlp",
        "cobalt",
    ]
    assert calls == ["ytdlp", "ytdlp", "cobalt"]


def test_from_url_rejects_playlist_picker_before_creating_job(api, monkeypatch):
    provider = FakeProvider(
        inspect_result={
            "provider": "ytdlp",
            "label": "yt-dlp",
            "available": False,
            "status": "picker",
            "needs_choice": True,
            "title": "Playlist",
            "choices": [
                {"id": "one", "title": "One", "url": "https://example.com/one"}
            ],
        }
    )
    install_provider(monkeypatch, provider)

    response = api.post(
        "/api/jobs/from-url",
        json={"url": "https://www.youtube.com/playlist?list=abc"},
    )

    assert response.status_code == 409
    assert "picker" in response.json()["detail"].lower()
    assert list((api.data_dir / "jobs").iterdir()) == []


def test_from_url_success_runs_background_ingest_and_history(api, monkeypatch):
    settings_store.save_secrets({"cobalt": "secret-cobalt"})
    provider = FakeProvider()
    captured: dict = {}
    install_provider(monkeypatch, provider, captured)

    def fake_probe(path):
        return {
            "path": str(path),
            "duration": 12.5,
            "width": 1280,
            "height": 720,
            "fps": 30.0,
            "has_audio": True,
            "size": 16,
        }

    monkeypatch.setattr(app.pipeline, "probe", fake_probe)

    response = api.post(
        "/api/jobs/from-url",
        json={
            "url": "https://youtube.com/watch?v=abc",
            "options": {"ocr": False, "transcribe": True},
            "ingest_options": {
                "quality": "720",
                "local_processing": "forced",
                "no_record": False,
                "interval": 3,
            },
        },
    )
    assert response.status_code == 200
    accepted = response.json()
    assert accepted["status"] == "downloading"
    assert accepted["provider"] == "ytdlp"
    assert "secret-cobalt" not in response.text
    job_id = accepted["id"]

    job_file = api.data_dir / "jobs" / job_id / "job.json"
    assert job_file.is_file(), "job directory must exist before download"
    wait_status(api, job_id, {"queued"})

    entries = wait_history(api, job_id)
    entry = entries[0]
    assert entry["type"] == "ingest"
    assert entry["status"] == "ok"
    assert entry["provider"] == "ytdlp"
    assert entry["name"] == "Clip title"
    assert entry["duration"] == 12.5
    assert entry["path"].endswith("source.mp4")
    assert entry["error"] is None

    detail = api.get(f"/api/jobs/{job_id}/history/{entry['id']}")
    assert detail.status_code == 200
    snapshot = detail.json()["snapshot"]
    assert snapshot["source_url"] == "https://youtube.com/watch?v=abc"
    assert snapshot["title"] == "Clip title"
    assert snapshot["path"].endswith("source.mp4")

    wait_for(lambda: api.capture_pool.calls or None)
    assert api.capture_pool.calls[0][0] is app.run_analysis
    assert api.capture_pool.calls[0][1][0] == job_id

    job = api.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "queued"
    assert job["source"]["name"] == "clip.mp4"
    assert job["source"]["duration"] == 12.5
    assert job["options"]["ocr"] is False
    assert job["options"]["transcribe"] is True
    assert job["ingest"]["provider"] == "ytdlp"
    assert job["ingest"]["meta"]["service"] == "test"
    assert job["ingest"]["options"]["quality"] == "720"
    assert job["ingest"]["options"]["local_processing"] == "forced"

    sent = captured["settings"]["ingest"]
    for key in (
        "ytdlp_quality",
        "ytdlp_codec",
        "ytdlp_container",
        "ytdlp_audio",
        "ytdlp_cookies",
        "ytdlp_browser",
        "ytdlp_cookie_file",
        "cobalt_fallback",
        "cobalt_url",
        "cobalt_api_key",
        "cobalt_quality",
        "cobalt_codec",
        "cobalt_local_processing",
        "xhs_url",
        "xhs_token",
        "xhs_no_record",
        "xhs_interval",
    ):
        assert key in sent
    assert sent["cobalt_api_key"] == "secret-cobalt"
    assert provider.options is not None
    assert provider.options.quality == "720"
    assert provider.options.local_processing == "forced"
    assert provider.options.no_record is False
    assert provider.options.interval == 3.0

    stored = list(api.data_dir.glob("sources/*/source.mp4"))
    assert len(stored) == 1
    assert stored[0].read_bytes() == b"fake video bytes"
    assert "secret-cobalt" not in job_file.read_text()


def test_from_url_failure_keeps_job_and_records_history(api, monkeypatch):
    provider = FakeProvider(download_error=IngestError("Cobalt is down."))
    install_provider(monkeypatch, provider)

    response = api.post(
        "/api/jobs/from-url", json={"url": "https://youtube.com/watch?v=down"}
    )
    assert response.status_code == 200
    job_id = response.json()["id"]

    status = wait_status(api, job_id, {"failed"})
    assert status["error"] == "Cobalt is down."
    assert status["progress"] == 1.0
    assert (api.data_dir / "jobs" / job_id / "job.json").is_file()
    assert provider.temp_path is not None
    assert not provider.temp_path.exists(), "temporary download must be removed"

    entries = wait_history(api, job_id)
    assert entries[0]["type"] == "ingest"
    assert entries[0]["status"] == "failed"
    assert entries[0]["provider"] == "ytdlp"
    assert entries[0]["error"] == "Cobalt is down."
    detail = api.get(f"/api/jobs/{job_id}/history/{entries[0]['id']}").json()
    assert detail["snapshot"]["source_url"] == "https://youtube.com/watch?v=down"


def test_cancel_sets_event_and_marks_download_failed(api, monkeypatch):
    provider = FakeProvider(wait_for_cancel=True)
    install_provider(monkeypatch, provider)

    response = api.post(
        "/api/jobs/from-url", json={"url": "https://youtube.com/watch?v=slow"}
    )
    assert response.status_code == 200
    job_id = response.json()["id"]
    wait_for(provider.started.is_set)

    cancelled = api.post(f"/api/jobs/{job_id}/url/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["ok"] is True
    assert cancelled.json()["cancelled"] is True

    status = wait_status(api, job_id, {"failed"})
    assert status["error"] == "Download cancelled."
    entries = wait_history(api, job_id)
    assert entries[0]["status"] == "failed"
    assert entries[0]["type"] == "ingest"
    assert entries[0]["error"] == "Download cancelled."
    assert not provider.temp_path.exists()
    wait_for(lambda: job_id not in app.INGEST_CANCELS or None)
    second = api.post(f"/api/jobs/{job_id}/url/cancel")
    assert second.status_code == 200
    assert second.json()["cancelled"] is False


def test_cancel_after_completion_is_noop(api, monkeypatch):
    provider = FakeProvider()
    install_provider(monkeypatch, provider)
    monkeypatch.setattr(
        app.pipeline,
        "probe",
        lambda path: {
            "path": str(path),
            "duration": 12.5,
            "width": 1280,
            "height": 720,
            "fps": 30.0,
            "has_audio": True,
            "size": 16,
        },
    )
    response = api.post(
        "/api/jobs/from-url", json={"url": "https://youtube.com/watch?v=done"}
    )
    assert response.status_code == 200
    job_id = response.json()["id"]
    wait_status(api, job_id, {"queued"})

    cancelled = api.post(f"/api/jobs/{job_id}/url/cancel")

    assert cancelled.status_code == 200
    assert cancelled.json()["cancelled"] is False
    assert api.get(f"/api/jobs/{job_id}/status").json()["status"] == "queued"


def test_ingest_status_includes_registry_and_xhs_session_fields(api, monkeypatch):
    settings_store.save_secrets({"cobalt": "cobalt-hidden", "xhs": "xhs-hidden"})
    provider = FakeProvider(
        id="xhs",
        label="XHS / RedNote",
        status_result={
            "id": "xhs",
            "label": "XHS / RedNote",
            "configured": True,
            "available": True,
            "error": "",
            "cookie_set": True,
            "session_ok": True,
            "auth_required": False,
            "user": "tester",
            "login_site": "rednote",
            "cookie_hint": "signed in",
            "service_url": "http://127.0.0.1:5789",
            "session": {
                "cookie_set": True,
                "session_ok": True,
                "auth_required": False,
                "user": "tester",
                "service_url": "http://127.0.0.1:5789",
            },
        },
    )
    install_provider(monkeypatch, provider)
    monkeypatch.setattr(
        app.registry,
        "status",
        lambda settings: {
            "cobalt": {
                "id": "cobalt",
                "label": "Cobalt",
                "configured": True,
                "available": True,
                "error": "",
            },
            "xhs": {
                "id": "xhs",
                "label": "XHS / RedNote",
                "configured": True,
                "available": True,
                "error": "",
                "session": {},
            },
        },
    )

    response = api.get("/api/ingest/status")
    assert response.status_code == 200
    body = response.json()
    assert body["cobalt"]["available"] is True
    assert body["providers"]["cobalt"]["id"] == "cobalt"
    assert body["xhs"]["cookie_set"] is True
    assert body["xhs"]["session_ok"] is True
    assert body["xhs"]["user"] == "tester"
    assert body["xhs"]["session"]["cookie_set"] is True
    assert body["settings"]["cobalt_url"] == "http://127.0.0.1:9000/"
    assert "cobalt-hidden" not in response.text
    assert "xhs-hidden" not in response.text


def test_settings_test_uses_live_provider_status_without_secrets(api, monkeypatch):
    settings_store.save_secrets({"cobalt": "cobalt-secret", "xhs": "xhs-secret"})
    provider = FakeProvider(
        id="xhs",
        label="XHS / RedNote",
        status_result={
            "id": "xhs",
            "label": "XHS / RedNote",
            "configured": True,
            "available": True,
            "error": "",
            "cookie_set": True,
            "session_ok": True,
            "user": "tester",
        },
    )
    captured: dict = {}
    install_provider(monkeypatch, provider, captured)

    response = api.post("/api/settings/test", json={"kind": "xhs"})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["kind"] == "xhs"
    assert body["provider"] == "xhs"
    assert body["status"]["available"] is True
    assert body["session"]["cookie_set"] is True
    assert response.text.count("xhs-secret") == 0
    assert captured["settings"]["ingest"]["xhs_token"] == "xhs-secret"
    assert captured["settings"]["ingest"]["cobalt_api_key"] == "cobalt-secret"


def test_settings_test_reports_provider_down(api, monkeypatch):
    provider = FakeProvider(
        status_result={
            "id": "cobalt",
            "label": "Cobalt",
            "configured": True,
            "available": False,
            "error": "Cobalt is not reachable.",
        }
    )
    install_provider(monkeypatch, provider)

    response = api.post("/api/settings/test", json={"kind": "cobalt"})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["available"] is False
    assert "not reachable" in body["detail"]


class EmptyOutputProvider(FakeProvider):
    def download(self, url, dest, options, progress, cancel_event):
        self.temp_path = Path(dest)
        dest.write_bytes(b"")
        return IngestResult(
            path=dest,
            filename="empty.mp4",
            provider=self.id,
            title="Empty clip",
        )


def test_empty_provider_output_fails_without_storing_source(api, monkeypatch):
    provider = EmptyOutputProvider()
    install_provider(monkeypatch, provider)

    response = api.post(
        "/api/jobs/from-url", json={"url": "https://youtube.com/watch?v=empty"}
    )
    assert response.status_code == 200
    job_id = response.json()["id"]
    status = wait_status(api, job_id, {"failed"})
    assert "empty" in status["error"].lower()

    job = api.get(f"/api/jobs/{job_id}").json()
    assert "source" not in job or not job["source"].get("path")
    entries = wait_history(api, job_id)
    assert entries[0]["status"] == "failed"
    assert not any((api.data_dir / "sources").glob(".ingest-*"))


def test_probe_failure_marks_job_failed(api, monkeypatch):
    provider = FakeProvider()
    install_provider(monkeypatch, provider)

    def fail_probe(path):
        raise app.pipeline.PipelineError("probe failed")

    monkeypatch.setattr(app.pipeline, "probe", fail_probe)
    response = api.post(
        "/api/jobs/from-url", json={"url": "https://youtube.com/watch?v=probe"}
    )
    assert response.status_code == 200
    job_id = response.json()["id"]
    status = wait_status(api, job_id, {"failed"})
    assert "probe" in status["error"].lower()

    entries = wait_history(api, job_id)
    assert entries[0]["status"] == "failed"
    assert not any((api.data_dir / "sources").glob(".ingest-*"))


def test_successful_job_redacts_source_url_in_job_and_history(api, monkeypatch):
    secret = "SUCCESS-TOKEN-456"
    provider = FakeProvider()
    install_provider(monkeypatch, provider)
    monkeypatch.setattr(
        app.pipeline,
        "probe",
        lambda path: {
            "path": str(path),
            "duration": 12.5,
            "width": 1280,
            "height": 720,
            "fps": 30.0,
            "has_audio": True,
            "size": 16,
        },
    )
    response = api.post(
        "/api/jobs/from-url",
        json={
            "url": (
                f"https://example.com/video?xsec_token={secret}"
                "&api_key=API-SECRET&sig=SIG-SECRET&key=KEY-SECRET"
                "&password=PASSWORD-SECRET"
            )
        },
    )
    assert response.status_code == 200
    job_id = response.json()["id"]
    wait_status(api, job_id, {"queued"})

    job = api.get(f"/api/jobs/{job_id}").json()
    job_file_text = (api.data_dir / "jobs" / job_id / "job.json").read_text()
    entries = wait_history(api, job_id)
    detail = api.get(f"/api/jobs/{job_id}/history/{entries[0]['id']}").json()
    for value in (secret, "API-SECRET", "SIG-SECRET", "KEY-SECRET", "PASSWORD-SECRET"):
        assert value not in json.dumps(job)
        assert value not in job_file_text
        assert value not in json.dumps(entries)
        assert value not in json.dumps(detail)
    assert "xsec_token=redacted" in job["ingest"]["source_url"]
    assert "api_key=redacted" in job["ingest"]["source_url"]


def test_ingest_temp_cleanup_handles_ytdlp_dot_stripping(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SOURCES", tmp_path)
    temp = tmp_path / ".ingest-job-123.mp4"
    temp.write_bytes(b"partial")
    dotless = tmp_path / "ingest-job-123.mp4.part"
    dotless.write_bytes(b"partial")

    app._cleanup_ingest_temp(temp)

    assert not temp.exists()
    assert not dotless.exists()


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/video",
        "http://localhost/video",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.5/video",
        "http://[::1]/video",
    ],
)
def test_url_ingest_rejects_local_and_link_local_targets(api, url):
    response = api.post("/api/url/inspect", json={"url": url})
    assert response.status_code == 400
    assert "public internet" in response.json()["detail"].lower()


def test_url_ingest_requires_token_on_non_loopback_bind(api, monkeypatch):
    monkeypatch.setattr(app, "HOST", "0.0.0.0")
    monkeypatch.delenv("VIBECUT_TOKEN", raising=False)

    for method, path, payload in (
        ("post", "/api/url/inspect", {"url": "https://example.com/video"}),
        ("get", "/api/settings", None),
        ("get", "/api/ingest/status", None),
        ("get", "/api/ingest/xhs/invite", None),
    ):
        response = getattr(api, method)(path, json=payload) if payload is not None else getattr(api, method)(path)
        assert response.status_code == 403
        assert "VIBECUT_TOKEN" in response.json()["detail"]
    assert api.get("/api/health").status_code == 200


@pytest.mark.parametrize(
    "url",
    [
        "http://127.1/private",
        "http://2130706433/private",
        "http://0x7f000001/private",
        "http://127.0.0.1.nip.io/private",
        "http://localtest.me/private",
    ],
)
def test_url_ingest_rejects_dns_and_legacy_ip_aliases(api, monkeypatch, url):
    monkeypatch.setattr(app, "_resolved_addresses", lambda host: ("127.0.0.1",))
    response = api.post("/api/url/inspect", json={"url": url})
    assert response.status_code == 400
    assert "public internet" in response.json()["detail"].lower()


def test_inspect_redacts_thumbnail_query_tokens(api, monkeypatch):
    provider = FakeProvider(
        inspect_result={
            "provider": "ytdlp",
            "label": "yt-dlp",
            "available": True,
            "title": "Clip",
            "thumbnail": "https://cdn.example/thumb.jpg?xsec_token=THUMB-SECRET&sig=SIG-SECRET",
        }
    )
    install_provider(monkeypatch, provider)
    response = api.post(
        "/api/url/inspect", json={"url": "https://example.com/video"}
    )
    assert response.status_code == 200
    body = response.json()
    assert "THUMB-SECRET" not in response.text
    assert "SIG-SECRET" not in response.text
    assert "redacted" in body["thumbnail"]
