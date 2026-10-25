"""Cobalt provider tests with mocked HTTP and ffmpeg."""

from __future__ import annotations

import io
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from url_ingest import cobalt
from url_ingest.base import IngestError, IngestOptions

PROVIDER_URL = "http://cobalt.test:9000"
SOURCE_URL = "https://youtube.com/watch?v=abc123"


# ---------------------------------------------------------------------------
# HTTP and response fakes


class FakeResponse:
    def __init__(
        self,
        body: bytes = b"",
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
        chunks: list[bytes] | None = None,
    ) -> None:
        self._body = body
        self._offset = 0
        self._chunks = list(chunks) if chunks is not None else None
        self.status = status
        self.headers = dict(headers or {})
        self.closed = False

    def read(self, size: int = -1) -> bytes:
        if self._chunks is not None:
            if not self._chunks:
                return b""
            if size < 0:
                data = b"".join(self._chunks)
                self._chunks.clear()
                return data
            return self._chunks.pop(0)
        if size < 0:
            data = self._body[self._offset :]
            self._offset = len(self._body)
            return data
        data = self._body[self._offset : self._offset + size]
        self._offset += len(data)
        return data

    def close(self) -> None:
        self.closed = True


class Transport:
    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.requests: list[urllib.request.Request] = []
        self.timeouts: list[float | None] = []

    def __call__(
        self, request: urllib.request.Request, timeout: float | None = None
    ) -> FakeResponse:
        self.requests.append(request)
        self.timeouts.append(timeout)
        if not self.responses:
            raise AssertionError(f"unexpected HTTP request: {request.full_url}")
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        assert isinstance(item, FakeResponse)
        return item


def json_response(payload: dict) -> FakeResponse:
    return FakeResponse(
        json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )


def media_response(
    chunks: list[bytes],
    *,
    content_type: str,
    content_length: int | None = None,
    estimated_length: int | None = None,
) -> FakeResponse:
    headers = {"Content-Type": content_type}
    if content_length is not None:
        headers["Content-Length"] = str(content_length)
    if estimated_length is not None:
        headers["Estimated-Content-Length"] = str(estimated_length)
    return FakeResponse(chunks=chunks, headers=headers)


def make_provider(**settings: object) -> cobalt.CobaltProvider:
    return cobalt.CobaltProvider({"cobalt_url": PROVIDER_URL, **settings})


def install(monkeypatch: pytest.MonkeyPatch, transport: Transport) -> None:
    monkeypatch.setattr(cobalt, "_urlopen", transport)


def request_headers(request: urllib.request.Request) -> dict[str, str]:
    return {key.lower(): value for key, value in request.headers.items()}


# ---------------------------------------------------------------------------
# inspect and request shape


def test_inspect_tunnel_returns_metadata_and_auth_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = Transport(
        json_response(
            {
                "status": "tunnel",
                "url": "http://cobalt.test:9000/tunnel/abc",
                "filename": "My Clip.mp4",
            }
        )
    )
    install(monkeypatch, transport)

    provider = make_provider(cobalt_api_key="secret-key")
    result = provider.inspect(
        SOURCE_URL,
        IngestOptions(quality="720", codec="av1", local_processing="forced"),
    )

    assert result == {
        "provider": "cobalt",
        "label": "Cobalt",
        "status": "tunnel",
        "available": True,
        "warning": "",
        "filename": "My Clip.mp4",
        "title": "My Clip",
        "duration": None,
        "thumbnail": None,
    }
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.full_url == PROVIDER_URL + "/"
    assert request.get_method() == "POST"
    headers = request_headers(request)
    assert headers["accept"] == "application/json"
    assert headers["content-type"] == "application/json"
    assert headers["authorization"] == "Api-Key secret-key"
    assert json.loads(request.data) == {
        "url": SOURCE_URL,
        "videoQuality": "720",
        "youtubeVideoCodec": "av1",
        "downloadMode": "auto",
        "localProcessing": "forced",
        "filenameStyle": "basic",
    }


def test_api_key_alias_and_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = Transport(
        json_response(
            {
                "status": "redirect",
                "url": "https://cdn.test/video.mp4",
                "filename": "video.mp4",
            }
        ),
        json_response(
            {
                "status": "redirect",
                "url": "https://cdn.test/video.mp4",
                "filename": "video.mp4",
            }
        ),
    )
    install(monkeypatch, transport)

    make_provider(cobalt_key="legacy-key").inspect(SOURCE_URL, IngestOptions())
    assert (
        request_headers(transport.requests[0])["authorization"]
        == "Api-Key legacy-key"
    )

    make_provider().inspect(SOURCE_URL, IngestOptions())
    assert "authorization" not in request_headers(transport.requests[1])


# ---------------------------------------------------------------------------
# tunnel and redirect downloads


def test_tunnel_download_streams_with_progress(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    response = media_response(
        [b"hello ", b"world"],
        content_type="video/mp4",
        content_length=11,
    )
    transport = Transport(
        json_response(
            {
                "status": "tunnel",
                "url": "http://cobalt.test:9000/tunnel/abc",
                "filename": "My Clip.mp4",
            }
        ),
        response,
    )
    install(monkeypatch, transport)
    progress: list[tuple[float, str]] = []

    result = make_provider(cobalt_api_key="secret").download(
        SOURCE_URL,
        tmp_path / "download",
        IngestOptions(),
        lambda fraction, message: progress.append((fraction, message)),
        threading.Event(),
    )

    assert result.path == tmp_path / "download"
    assert result.path.read_bytes() == b"hello world"
    assert result.filename == "My Clip.mp4"
    assert result.provider == "cobalt"
    assert result.title == "My Clip"
    assert result.meta["status"] == "tunnel"
    assert result.meta["content_length"] == 11
    assert progress[0][0] <= 0.01
    assert progress[-1] == (1.0, "Downloaded My Clip.mp4.")
    assert any(0.0 < fraction < 1.0 for fraction, _ in progress)
    assert response.closed is True
    assert list(tmp_path.glob(".download.*.part")) == []

    # The API key stays on the cobalt POST; it must not leak to a tunnel host.
    assert len(transport.requests) == 2
    assert "authorization" not in request_headers(transport.requests[1])


def test_redirect_download_accepts_estimated_length(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    response = media_response(
        [b"one", b"two", b"three"],
        content_type="video/webm",
        estimated_length=50,
    )
    transport = Transport(
        json_response(
            {
                "status": "redirect",
                "url": "https://cdn.test/clip.webm",
                "filename": "clip.webm",
            }
        ),
        response,
    )
    install(monkeypatch, transport)
    progress: list[float] = []

    result = make_provider().download(
        SOURCE_URL,
        tmp_path / "out.webm",
        IngestOptions(),
        lambda fraction, _message: progress.append(fraction),
        threading.Event(),
    )

    assert result.path.read_bytes() == b"onetwothree"
    assert result.filename == "clip.webm"
    assert result.meta["status"] == "redirect"
    assert result.meta["content_type"] == "video/webm"
    assert progress[-1] == 1.0
    assert any(0.0 < fraction < 1.0 for fraction in progress)


def test_direct_download_uses_safe_filename_in_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    videos = tmp_path / "videos"
    videos.mkdir()
    transport = Transport(
        json_response(
            {
                "status": "tunnel",
                "url": "http://cobalt.test:9000/tunnel/abc",
                "filename": "../../evil: clip?.mp4",
            }
        ),
        media_response([b"data"], content_type="video/mp4", content_length=4),
    )
    install(monkeypatch, transport)

    result = make_provider().download(
        SOURCE_URL,
        videos,
        IngestOptions(),
        lambda _fraction, _message: None,
        threading.Event(),
    )

    assert result.path.parent == videos
    assert "/" not in result.filename
    assert ".." not in result.filename
    assert result.filename.endswith(".mp4")
    assert result.path.read_bytes() == b"data"


def test_tunnel_download_rejects_short_body(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    transport = Transport(
        json_response(
            {
                "status": "tunnel",
                "url": "http://cobalt.test:9000/tunnel/abc",
                "filename": "short.mp4",
            }
        ),
        media_response([b"abc"], content_type="video/mp4", content_length=6),
    )
    install(monkeypatch, transport)

    with pytest.raises(IngestError, match="size mismatch") as info:
        make_provider().download(
            SOURCE_URL,
            tmp_path / "short.mp4",
            IngestOptions(),
            lambda _fraction, _message: None,
            threading.Event(),
        )

    assert info.value.code == "download.incomplete"
    assert not (tmp_path / "short.mp4").exists()
    assert list(tmp_path.glob(".short.mp4.*.part")) == []


def test_cancel_during_stream_removes_partial_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    response = media_response(
        [b"one", b"two", b"three", b"four"],
        content_type="video/mp4",
        content_length=15,
    )
    transport = Transport(
        json_response(
            {
                "status": "tunnel",
                "url": "http://cobalt.test:9000/tunnel/abc",
                "filename": "My Clip.mp4",
            }
        ),
        response,
    )
    install(monkeypatch, transport)
    cancel_event = threading.Event()

    def on_progress(_fraction: float, message: str) -> None:
        if message.startswith("Downloading My Clip.mp4 -"):
            cancel_event.set()

    with pytest.raises(IngestError, match="cancelled") as info:
        make_provider().download(
            SOURCE_URL,
            tmp_path / "cancelled.mp4",
            IngestOptions(),
            on_progress,
            cancel_event,
        )

    assert info.value.code == "cancelled"
    assert not (tmp_path / "cancelled.mp4").exists()
    assert list(tmp_path.glob(".cancelled.mp4.*.part")) == []
    assert response.closed is True
    assert len(transport.requests) == 2


def test_cancel_before_request_makes_no_http_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    transport = Transport()
    install(monkeypatch, transport)
    cancel_event = threading.Event()
    cancel_event.set()

    with pytest.raises(IngestError, match="cancelled"):
        make_provider().download(
            SOURCE_URL,
            tmp_path / "never.mp4",
            IngestOptions(),
            lambda _fraction, _message: None,
            cancel_event,
        )

    assert transport.requests == []


# ---------------------------------------------------------------------------
# local processing


def test_local_processing_merges_parts_with_ffmpeg(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    transport = Transport(
        json_response(
            {
                "status": "local-processing",
                "type": "merge",
                "service": "youtube",
                "tunnel": [
                    "http://cobalt.test:9000/tunnel/video",
                    "http://cobalt.test:9000/tunnel/audio",
                ],
                "output": {
                    "type": "video/mp4",
                    "filename": "Merged Clip.mp4",
                    "metadata": {"title": "Real Title"},
                },
            }
        ),
        media_response([b"videobytes"], content_type="video/mp4"),
        media_response([b"audiobytes"], content_type="audio/mp4"),
    )
    install(monkeypatch, transport)
    monkeypatch.setattr(cobalt, "_ffmpeg_path", lambda: "/fake/ffmpeg")

    observed: dict[str, bytes] = {}
    commands: list[list[str]] = []

    def fake_ffmpeg(cmd: list[str], _cancel_event: threading.Event) -> None:
        commands.append(cmd)
        first = cmd.index("-i")
        second = cmd.index("-i", first + 1)
        observed["video"] = Path(cmd[first + 1]).read_bytes()
        observed["audio"] = Path(cmd[second + 1]).read_bytes()
        Path(cmd[-1]).write_bytes(b"merged-bytes")

    monkeypatch.setattr(cobalt, "_run_ffmpeg", fake_ffmpeg)
    progress: list[tuple[float, str]] = []

    result = make_provider().download(
        SOURCE_URL,
        tmp_path / "merged.mp4",
        IngestOptions(local_processing="forced"),
        lambda fraction, message: progress.append((fraction, message)),
        threading.Event(),
    )

    assert result.path == tmp_path / "merged.mp4"
    assert result.path.read_bytes() == b"merged-bytes"
    assert result.filename == "Merged Clip.mp4"
    assert result.title == "Real Title"
    assert result.meta["type"] == "merge"
    assert result.meta["parts"] == 2
    assert observed == {"video": b"videobytes", "audio": b"audiobytes"}
    assert len(commands) == 1
    command = commands[0]
    assert command[0] == "/fake/ffmpeg"
    assert "-map" in command
    assert command[command.index("-c") + 1] == "copy"
    assert "+faststart" in command
    assert command[-1].endswith("output.mp4")
    assert progress[-1][0] == 1.0
    assert any("Merging" in message for _fraction, message in progress)
    assert list(tmp_path.glob(".cobalt-*")) == []


def test_local_processing_rejects_audio_and_gif(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    audio_payload = {
        "status": "local-processing",
        "type": "audio",
        "tunnel": ["http://cobalt.test:9000/tunnel/audio"],
        "output": {"type": "audio/mp4", "filename": "Track.m4a"},
    }
    gif_payload = {
        "status": "local-processing",
        "type": "gif",
        "tunnel": ["http://cobalt.test:9000/tunnel/gif"],
        "output": {"type": "image/gif", "filename": "Anim.gif"},
    }

    for payload, expected in (
        (audio_payload, "audio only"),
        (gif_payload, "GIF"),
    ):
        transport = Transport(json_response(payload))
        install(monkeypatch, transport)
        provider = make_provider()

        inspected = provider.inspect(SOURCE_URL, IngestOptions())
        assert inspected["available"] is False
        assert expected in inspected["warning"]
        assert len(transport.requests) == 1

        transport = Transport(json_response(payload))
        install(monkeypatch, transport)
        with pytest.raises(IngestError, match=expected):
            provider.download(
                SOURCE_URL,
                tmp_path / "rejected.mp4",
                IngestOptions(),
                lambda _fraction, _message: None,
                threading.Event(),
            )
        assert len(transport.requests) == 1
        assert not (tmp_path / "rejected.mp4").exists()


def test_ffmpeg_commands_for_remux_and_mute(tmp_path: Path) -> None:
    video = cobalt._Part(tmp_path / "video.mp4", "video.mp4", "video/mp4", 4)
    audio = cobalt._Part(tmp_path / "audio.m4a", "audio.m4a", "audio/mp4", 4)

    remux = cobalt._ffmpeg_command(
        "/fake/ffmpeg", "remux", video, None, tmp_path / "remux.mp4"
    )
    assert "0:a:0?" in remux
    assert "-c" in remux and remux[remux.index("-c") + 1] == "copy"

    mute = cobalt._ffmpeg_command(
        "/fake/ffmpeg", "mute", video, None, tmp_path / "mute.mp4"
    )
    assert "-an" in mute
    assert mute[-1].endswith("mute.mp4")

    merge = cobalt._ffmpeg_command(
        "/fake/ffmpeg", "merge", video, audio, tmp_path / "merge.mp4"
    )
    assert "0:v:0" in merge and "1:a:0" in merge


# ---------------------------------------------------------------------------
# errors, picker, and status


def test_cobalt_error_payload_raises_with_code_and_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = Transport(
        json_response(
            {
                "status": "error",
                "error": {
                    "code": "error.api.link.invalid",
                    "context": {"service": "youtube"},
                },
            }
        )
    )
    install(monkeypatch, transport)

    with pytest.raises(IngestError, match="could not understand") as info:
        make_provider().inspect(SOURCE_URL, IngestOptions())

    assert info.value.code == "error.api.link.invalid"
    assert info.value.context == {"service": "youtube"}
    assert len(transport.requests) == 1


def test_http_auth_error_parses_cobalt_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = json.dumps(
        {
            "status": "error",
            "error": {"code": "error.api.auth.key.invalid"},
        }
    ).encode("utf-8")
    failure = urllib.error.HTTPError(
        PROVIDER_URL + "/", 401, "Unauthorized", {}, io.BytesIO(body)
    )
    transport = Transport(failure)
    install(monkeypatch, transport)

    with pytest.raises(IngestError, match="API key") as info:
        make_provider(cobalt_api_key="bad").inspect(SOURCE_URL, IngestOptions())

    assert info.value.code == "error.api.auth.key.invalid"
    assert info.value.status == 401


def test_picker_inspect_returns_choices_and_download_refuses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = {
        "status": "picker",
        "picker": [
            {
                "type": "video",
                "url": "https://cdn.test/one.mp4",
                "thumb": "https://cdn.test/one.jpg",
            },
            {"type": "photo", "url": "https://cdn.test/two.jpg"},
        ],
    }
    transport = Transport(json_response(payload))
    install(monkeypatch, transport)
    provider = make_provider()

    inspected = provider.inspect(SOURCE_URL, IngestOptions())
    assert inspected["status"] == "picker"
    assert inspected["choices"] == [
        {
            "type": "video",
            "url": "https://cdn.test/one.mp4",
            "thumbnail": "https://cdn.test/one.jpg",
        },
        {"type": "photo", "url": "https://cdn.test/two.jpg"},
    ]
    assert inspected["needs_choice"] is True
    assert "multiple" in inspected["warning"].lower()
    assert len(transport.requests) == 1

    transport = Transport(json_response(payload))
    install(monkeypatch, transport)
    with pytest.raises(IngestError, match="multiple items") as info:
        provider.download(
            SOURCE_URL,
            tmp_path / "picker.mp4",
            IngestOptions(),
            lambda _fraction, _message: None,
            threading.Event(),
        )
    assert info.value.code == "picker"
    assert len(info.value.context["choices"]) == 2
    assert len(transport.requests) == 1
    assert not (tmp_path / "picker.mp4").exists()


def test_status_available(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = Transport(
        json_response(
            {
                "cobalt": {"version": "10.0.0"},
                "git": {"branch": "main"},
            }
        )
    )
    install(monkeypatch, transport)

    status = make_provider(cobalt_api_key="secret").status()

    assert status == {
        "id": "cobalt",
        "label": "Cobalt",
        "configured": True,
        "available": True,
        "error": "",
    }
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.get_method() == "GET"
    assert request.full_url == PROVIDER_URL + "/"
    assert request_headers(request)["authorization"] == "Api-Key secret"
    assert transport.timeouts == [cobalt.STATUS_TIMEOUT]
    assert cobalt.STATUS_TIMEOUT <= 5


def test_status_unreachable_and_missing_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = urllib.error.URLError(ConnectionRefusedError(61, "Connection refused"))
    transport = Transport(failure)
    install(monkeypatch, transport)

    status = make_provider().status()
    assert status["configured"] is True
    assert status["available"] is False
    assert "not reachable" in status["error"]

    transport = Transport()
    install(monkeypatch, transport)
    missing = cobalt.CobaltProvider({}).status()
    assert missing["configured"] is False
    assert missing["available"] is False
    assert "not set" in missing["error"]
    assert transport.requests == []


def test_hosted_cobalt_endpoint_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = Transport()
    install(monkeypatch, transport)
    provider = cobalt.CobaltProvider({"cobalt_url": "https://api.cobalt.tools/"})

    with pytest.raises(IngestError, match="Hosted api.cobalt.tools") as info:
        provider.inspect(SOURCE_URL, IngestOptions())
    assert info.value.code == "config.hosted"
    assert transport.requests == []

    status = provider.status()
    assert status["configured"] is False
    assert status["available"] is False
    assert "Hosted api.cobalt.tools" in status["error"]
    assert transport.requests == []


def test_private_tunnel_url_rejected():
    from url_ingest import cobalt
    from url_ingest.base import IngestError
    import pytest

    with pytest.raises(IngestError):
        cobalt._absolute_http_url(
            "http://127.0.0.1:8000/private", "https://cobalt.example/", what="tunnel",
        )
    with pytest.raises(IngestError):
        cobalt._absolute_http_url(
            "http://169.254.169.254/latest/meta-data", "https://cobalt.example/", what="tunnel",
        )
    assert cobalt._absolute_http_url(
        "http://127.0.0.1:9000/tunnel/abc", "http://127.0.0.1:9000/", what="tunnel",
    ).endswith("/tunnel/abc")
