"""Mocked-API tests for the xhs_get URL ingest provider."""

from __future__ import annotations

import io
import json
import threading
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

import pytest

from url_ingest import registry
from url_ingest import xhs as xhs_module
from url_ingest.base import IngestError, IngestOptions
from url_ingest.xhs import XhsGetProvider

FULL_URL = (
    "https://www.xiaohongshu.com/explore/0123456789abcdef"
    "?xsec_token=abc123&xsec_source=pc_share"
)
TOKENLESS_URL = "https://www.xiaohongshu.com/explore/0123456789abcdef"
SHORT_URL = "https://xhslink.com/a/AbCdEf"


class _Response:
    def __init__(self, payload: object, status: int = 200) -> None:
        self.status = status
        self._body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def read(self, size: int = -1) -> bytes:
        return self._body if size < 0 else self._body[:size]

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> bool:
        return False


class _Api:
    """Tiny scripted xhs_get server for urllib."""

    def __init__(
        self,
        *,
        state: dict | None = None,
        create: dict | None = None,
        jobs: list[dict] | None = None,
        files: list[dict] | None = None,
        errors: dict[str, BaseException] | None = None,
    ) -> None:
        self.state = state if state is not None else _state()
        self.create = (
            create if create is not None else {"id": "job-1", "state": "pending"}
        )
        self.jobs = list(jobs or [])
        self.files = list(files or [])
        self.errors = dict(errors or {})
        self.requests = []

    def __call__(self, request, timeout=None):  # type: ignore[no-untyped-def]
        self.requests.append(request)
        path = urlsplit(request.full_url).path
        error = self.errors.get(path)
        if error is not None:
            raise error
        if path == "/api/state":
            return _Response(self.state)
        if request.get_method() == "POST" and path == "/api/jobs":
            return _Response(self.create)
        if path.startswith("/api/jobs/"):
            if not self.jobs:
                raise AssertionError(f"unexpected job poll: {request.full_url}")
            return _Response(self.jobs.pop(0))
        if path == "/api/files":
            return _Response(self.files)
        raise AssertionError(f"unexpected request: {request.get_method()} {path}")

    @property
    def paths(self) -> list[str]:
        return [urlsplit(request.full_url).path for request in self.requests]

    def method(self, name: str) -> list:
        return [request for request in self.requests if request.get_method() == name]

    def header(self, name: str) -> str | None:
        return self.requests[-1].get_header(name)


def _state(
    *,
    cookie_set: bool = True,
    session_ok: bool | None = True,
    auth_required: bool = False,
    name: str = "local",
) -> dict:
    return {
        "me": {
            "name": name,
            "admin": not auth_required,
            "auth_required": auth_required,
            "cookie_set": cookie_set,
            "cookie_hint": "a1b2...c3d4" if cookie_set else "",
            "session_ok": session_ok,
            "login_site": "rednote",
        },
        "cookie": {
            "set": cookie_set,
            "hint": "a1b2...c3d4" if cookie_set else "",
            "source": "local file",
            "path": "/Users/example/.config/xhs_get/cookie.txt",
        },
        "folder": "/Users/example/Videos/xhs",
    }


def _http_error(code: int, detail: str) -> HTTPError:
    return HTTPError(
        "http://xhs.local/api/jobs",
        code,
        "request failed",
        {},
        io.BytesIO(json.dumps({"detail": detail}).encode("utf-8")),
    )


def _provider(settings: dict | None = None) -> XhsGetProvider:
    values = {"xhs_url": "http://xhs.local", **(settings or {})}
    provider = XhsGetProvider(values)
    provider.poll_interval = 0
    return provider


# ---------------------------------------------------------------------------
# Contract and status


def test_registry_builds_xhs_provider() -> None:
    instance = registry.provider("xhs", {"ingest": {"xhs_url": "http://xhs.local"}})
    assert isinstance(instance, XhsGetProvider)
    assert instance.id == "xhs"
    assert instance.label == "XHS / RedNote"


def test_status_reads_state_and_sends_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _Api(state=_state(auth_required=True, name="alice"))
    monkeypatch.setattr(xhs_module, "urlopen", api)

    entry = _provider({"xhs_token": "secret-token"}).status()

    assert entry["configured"] is True
    assert entry["available"] is True
    assert entry["error"] == ""
    assert entry["cookie_set"] is True
    assert entry["session_ok"] is True
    assert entry["auth_required"] is True
    assert entry["user"] == "alice"
    assert entry["login_site"] == "rednote"
    assert entry["service_url"] == "http://xhs.local"
    assert api.paths == ["/api/state"]
    assert api.header("Authorization") == "Bearer secret-token"
    assert "secret-token" not in json.dumps(entry)


def test_status_without_token_omits_authorization_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _Api(state=_state())
    monkeypatch.setattr(xhs_module, "urlopen", api)

    entry = _provider().status()

    assert entry["available"] is True
    assert api.header("Authorization") is None


def test_status_missing_url_does_not_call_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _Api()
    monkeypatch.setattr(xhs_module, "urlopen", api)

    entry = _provider({"xhs_url": ""}).status()

    assert entry["configured"] is False
    assert entry["available"] is False
    assert "URL is not set" in entry["error"]
    assert api.requests == []


def test_status_reports_missing_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    api = _Api(state=_state(cookie_set=False, session_ok=False))
    monkeypatch.setattr(xhs_module, "urlopen", api)

    entry = _provider().status()

    assert entry["configured"] is True
    assert entry["available"] is False
    assert entry["cookie_set"] is False
    assert "signed-in cookie" in entry["error"]


def test_status_reports_expired_session(monkeypatch: pytest.MonkeyPatch) -> None:
    api = _Api(state=_state(cookie_set=True, session_ok=False))
    monkeypatch.setattr(xhs_module, "urlopen", api)

    entry = _provider().status()

    assert entry["available"] is False
    assert "expired" in entry["error"].lower()


def test_status_handles_service_down(monkeypatch: pytest.MonkeyPatch) -> None:
    api = _Api(errors={"/api/state": URLError("connection refused")})
    monkeypatch.setattr(xhs_module, "urlopen", api)

    entry = _provider().status()

    assert entry["configured"] is True
    assert entry["available"] is False
    assert "not reachable" in entry["error"]
    assert "Start xhs-get web" in entry["error"]


# ---------------------------------------------------------------------------
# Inspect


def test_inspect_full_link_with_token(monkeypatch: pytest.MonkeyPatch) -> None:
    api = _Api(state=_state())
    monkeypatch.setattr(xhs_module, "urlopen", api)

    result = _provider({"xhs_token": "secret-token"}).inspect(
        FULL_URL, IngestOptions(no_record=False, interval=3)
    )

    assert result["provider"] == "xhs"
    assert result["label"] == "XHS / RedNote"
    assert result["available"] is True
    assert result["warning"] == ""
    assert result["has_xsec_token"] is True
    assert result["short_link"] is False
    assert result["session"]["cookie_set"] is True
    assert result["options"]["no_record"] is False
    assert result["options"]["interval"] == 3.0
    assert api.header("Authorization") == "Bearer secret-token"


def test_inspect_warns_when_full_link_has_no_xsec_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _Api(state=_state())
    monkeypatch.setattr(xhs_module, "urlopen", api)

    result = _provider().inspect(TOKENLESS_URL, IngestOptions())

    assert result["available"] is False
    assert result["has_xsec_token"] is False
    assert "xsec_token" in result["warning"]
    assert "Share" in result["warning"]


def test_inspect_allows_short_link_without_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _Api(state=_state())
    monkeypatch.setattr(xhs_module, "urlopen", api)

    result = _provider().inspect(SHORT_URL, IngestOptions())

    assert result["available"] is True
    assert result["short_link"] is True
    assert "xsec_token" not in result["warning"]


def test_inspect_returns_unavailable_when_service_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _Api(errors={"/api/state": URLError("connection refused")})
    monkeypatch.setattr(xhs_module, "urlopen", api)

    result = _provider().inspect(FULL_URL, IngestOptions())

    assert result["available"] is False
    assert "not reachable" in result["warning"]
    assert result["error"] == result["warning"]


def test_inspect_rejects_non_xhs_url() -> None:
    with pytest.raises(IngestError, match="Not a RedNote"):
        _provider().inspect("https://youtube.com/watch?v=abc", IngestOptions())


# ---------------------------------------------------------------------------
# Download


def test_download_posts_job_tracks_progress_and_copies_video(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "service" / "clip.mp4"
    source.parent.mkdir()
    source.write_bytes(b"01234567")

    api = _Api(
        create={"id": "job-1", "state": "pending"},
        jobs=[
            {
                "id": "job-1",
                "state": "running",
                "phase": "Note 1/1",
                "counts": {"all": 1, "success": 0, "fail": 0, "skip": 0},
                "files": [
                    {
                        "filename": "clip.mp4",
                        "completed_bytes": 4,
                        "total_bytes": 8,
                        "state": "downloading",
                    }
                ],
            },
            {
                "id": "job-1",
                "state": "done",
                "phase": "Note 1/1",
                "counts": {"all": 1, "success": 1, "fail": 0, "skip": 0},
                "files": [
                    {
                        "filename": "clip.mp4",
                        "completed_bytes": 8,
                        "total_bytes": 8,
                        "state": "completed",
                    }
                ],
                "created": time.time() - 1,
            },
        ],
        files=[
            {
                "name": "clip.mp4",
                "path": str(source),
                "size": 8,
                "mtime": time.time(),
            }
        ],
    )
    monkeypatch.setattr(xhs_module, "urlopen", api)

    updates: list[tuple[float, str]] = []
    dest = tmp_path / "dest"
    result = _provider({"xhs_token": "secret-token"}).download(
        FULL_URL,
        dest,
        IngestOptions(no_record=True, interval=4),
        lambda fraction, message: updates.append((fraction, message)),
        threading.Event(),
    )

    assert result.path == dest / "clip.mp4"
    assert result.path.read_bytes() == b"01234567"
    assert result.filename == "clip.mp4"
    assert result.provider == "xhs"
    assert result.meta["job_id"] == "job-1"
    assert result.meta["remote_path"] == str(source)
    assert updates[-1][0] == 1.0
    assert all(left[0] <= right[0] for left, right in zip(updates, updates[1:]))
    assert any(0.0 < fraction < 1.0 for fraction, _ in updates)

    post = api.method("POST")[0]
    body = json.loads(post.data.decode("utf-8"))
    assert body == {
        "kind": "links",
        "target": FULL_URL,
        "note_filter": "video",
        "no_record": True,
        "interval": 4.0,
    }
    assert post.get_header("Authorization") == "Bearer secret-token"
    assert api.paths == [
        "/api/jobs",
        "/api/jobs/job-1",
        "/api/jobs/job-1",
        "/api/files",
    ]
    assert all(
        request.get_header("Authorization") == "Bearer secret-token"
        for request in api.requests
    )


def test_download_matches_remote_file_when_extension_changes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "service" / "clip.mov"
    source.parent.mkdir()
    source.write_bytes(b"mov-data")
    api = _Api(
        jobs=[
            {
                "id": "job-1",
                "state": "done",
                "counts": {"all": 1, "success": 1, "fail": 0, "skip": 0},
                "files": [
                    {
                        "filename": "clip.mp4",
                        "completed_bytes": 100,
                        "total_bytes": 100,
                        "state": "completed",
                    }
                ],
                "created": time.time() - 1,
            }
        ],
        files=[{"name": "clip.mov", "path": str(source), "mtime": time.time()}],
    )
    monkeypatch.setattr(xhs_module, "urlopen", api)

    result = _provider().download(
        FULL_URL, tmp_path / "out", IngestOptions(), lambda *_: None, threading.Event()
    )

    assert result.path.name == "clip.mov"
    assert result.path.read_bytes() == b"mov-data"


def test_download_without_job_files_or_deliverables_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "service" / "fresh.mp4"
    source.parent.mkdir()
    source.write_bytes(b"fresh")
    api = _Api(
        jobs=[
            {
                "id": "job-1",
                "state": "done",
                "counts": {"all": 1, "success": 1, "fail": 0, "skip": 0},
                "files": [],
                "created": time.time() - 1,
            }
        ],
        files=[{"name": "fresh.mp4", "path": str(source), "mtime": time.time()}],
    )
    monkeypatch.setattr(xhs_module, "urlopen", api)

    with pytest.raises(IngestError, match="did not return a video file"):
        _provider().download(
            FULL_URL, tmp_path / "out", IngestOptions(),
            lambda *_: None, threading.Event(),
        )


def test_download_reports_image_only_note(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    image = tmp_path / "cover.jpg"
    image.write_bytes(b"jpg")
    api = _Api(
        jobs=[
            {
                "id": "job-1",
                "state": "done",
                "counts": {"all": 1, "success": 0, "fail": 0, "skip": 1},
                "files": [
                    {
                        "filename": "cover.jpg",
                        "completed_bytes": 3,
                        "total_bytes": 3,
                        "state": "completed",
                    }
                ],
            }
        ],
        files=[{"name": "cover.jpg", "path": str(image), "mtime": time.time()}],
    )
    monkeypatch.setattr(xhs_module, "urlopen", api)

    with pytest.raises(IngestError, match="images only"):
        _provider().download(
            FULL_URL,
            tmp_path / "out",
            IngestOptions(),
            lambda *_: None,
            threading.Event(),
        )


def test_download_reports_skipped_note(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    api = _Api(
        jobs=[
            {
                "id": "job-1",
                "state": "done",
                "counts": {"all": 1, "success": 0, "fail": 0, "skip": 1},
                "files": [],
            }
        ]
    )
    monkeypatch.setattr(xhs_module, "urlopen", api)

    with pytest.raises(IngestError, match="skipped"):
        _provider().download(
            FULL_URL,
            tmp_path / "out",
            IngestOptions(),
            lambda *_: None,
            threading.Event(),
        )


def test_download_maps_expired_session_job_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    api = _Api(
        jobs=[
            {
                "id": "job-1",
                "state": "failed",
                "error": "RuntimeError('XHS returned no note data three times in a row')",
            }
        ]
    )
    monkeypatch.setattr(xhs_module, "urlopen", api)

    with pytest.raises(IngestError, match="session"):
        _provider().download(
            FULL_URL,
            tmp_path / "out",
            IngestOptions(),
            lambda *_: None,
            threading.Event(),
        )


def test_download_maps_http_401_to_token_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    api = _Api(errors={"/api/jobs": _http_error(401, "Access token is missing")})
    monkeypatch.setattr(xhs_module, "urlopen", api)

    with pytest.raises(IngestError, match="access token"):
        _provider().download(
            FULL_URL,
            tmp_path / "out",
            IngestOptions(),
            lambda *_: None,
            threading.Event(),
        )


def test_download_requires_xsec_token_for_full_link(tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="xsec_token"):
        _provider().download(
            TOKENLESS_URL,
            tmp_path / "out",
            IngestOptions(),
            lambda *_: None,
            threading.Event(),
        )


def test_download_allows_short_link_without_xsec_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "short.mp4"
    source.write_bytes(b"short")
    api = _Api(
        create={"id": "job-2", "state": "pending"},
        jobs=[
            {
                "id": "job-2",
                "state": "done",
                "counts": {"all": 1, "success": 1, "fail": 0, "skip": 0},
                "files": [
                    {
                        "filename": "short.mp4",
                        "completed_bytes": 5,
                        "total_bytes": 5,
                        "state": "completed",
                    }
                ],
            }
        ],
        files=[{"name": "short.mp4", "path": str(source), "mtime": time.time()}],
    )
    monkeypatch.setattr(xhs_module, "urlopen", api)

    result = _provider().download(
        SHORT_URL, tmp_path / "out", IngestOptions(), lambda *_: None, threading.Event()
    )

    assert result.path.read_bytes() == b"short"


def test_download_cancel_after_submit_stops_polling(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    api = _Api(jobs=[{"id": "job-1", "state": "running"}])
    monkeypatch.setattr(xhs_module, "urlopen", api)
    cancel = threading.Event()

    def progress(fraction: float, _message: str) -> None:
        if fraction >= 0.02:
            cancel.set()

    with pytest.raises(IngestError, match="canceled"):
        _provider().download(
            FULL_URL, tmp_path / "out", IngestOptions(), progress, cancel
        )

    assert api.paths == ["/api/jobs"]
    assert cancel.is_set()


def test_download_cancel_before_start_makes_no_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    api = _Api()
    monkeypatch.setattr(xhs_module, "urlopen", api)
    cancel = threading.Event()
    cancel.set()

    with pytest.raises(IngestError, match="canceled"):
        _provider().download(
            FULL_URL, tmp_path / "out", IngestOptions(), lambda *_: None, cancel
        )

    assert api.requests == []


def test_stream_deliverable_is_downloaded(monkeypatch, tmp_path):
    from url_ingest import xhs as module

    payload = b"video-bytes"

    class Media:
        status = 200
        def read(self, size=-1):
            nonlocal payload
            if not payload:
                return b""
            chunk, payload = payload, b""
            return chunk
        def close(self):
            pass

    class Provider(module.XhsGetProvider):
        def _request_json(self, method, path, payload=None, **kwargs):
            if method == "POST":
                return {"id": "job-1", "state": "pending"}
            return {
                "id": "job-1", "state": "done",
                "counts": {"all": 1, "success": 1, "fail": 0, "skip": 0},
                "files": [],
                "deliverables": [{
                    "kind": "video", "filename": "rednote.mp4",
                    "title": "RedNote clip", "note": "123", "author": "a",
                }],
            }

    monkeypatch.setattr(module, "urlopen", lambda request, timeout=None: Media())
    provider = Provider({"xhs_url": "http://xhs.local", "xhs_token": "secret"})
    from url_ingest.base import IngestOptions
    result = provider.download(
        FULL_URL,
        tmp_path / "out.mp4",
        IngestOptions(no_record=True),
        lambda fraction, message: None,
        threading.Event(),
    )
    assert result.path.read_bytes() == b"video-bytes"
    assert result.meta["delivery"] == "stream"
