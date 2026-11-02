"""Mocked contract tests for the native yt-dlp ingest provider.

No test touches the network. ``url_ingest.ytdlp._module`` is replaced with a
small fake exposing ``YoutubeDL`` and ``version``.
"""

from __future__ import annotations

import ast
import sys
import threading
import types
from pathlib import Path
from typing import Any, Callable

import pytest

from url_ingest import registry, ytdlp
from url_ingest.base import IngestError, IngestOptions

SOURCE_URL = "https://www.youtube.com/watch?v=abc123"
Handler = Callable[[Any, str, bool], Any]


class FakeYoutubeDL:
    """Minimal context-manager double for ``yt_dlp.YoutubeDL``."""

    instances: list["FakeYoutubeDL"] = []

    def __init__(self, opts: dict[str, Any]) -> None:
        self.opts = opts
        self.calls: list[tuple[str, bool]] = []
        type(self).instances.append(self)

    def __enter__(self) -> "FakeYoutubeDL":
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False

    def extract_info(self, url: str, download: bool) -> Any:
        self.calls.append((url, download))
        return self.handler(self, url, download)


def install(
    monkeypatch: pytest.MonkeyPatch,
    handler: Handler,
    *,
    version: str = "2026.10.21",
) -> type[FakeYoutubeDL]:
    class FakeYDL(FakeYoutubeDL):
        instances: list["FakeYDL"] = []

        def __init__(self, opts: dict[str, Any]) -> None:
            super().__init__(opts)
            self.handler = handler

    module = types.SimpleNamespace(
        YoutubeDL=FakeYDL,
        version=types.SimpleNamespace(__version__=version),
    )
    monkeypatch.setattr(ytdlp, "_module", lambda: module)
    return FakeYDL


def provider_and_options(
    settings: dict[str, Any] | None = None,
) -> tuple[Any, IngestOptions]:
    payload = {"ingest": dict(settings or {})}
    return registry.provider("ytdlp", payload), registry.options_from_settings(payload)


def video_info(**overrides: Any) -> dict[str, Any]:
    info: dict[str, Any] = {
        "_type": "video",
        "id": "abc123",
        "title": "Test clip",
        "duration": 12.5,
        "thumbnail": "https://i.test/thumb.jpg",
        "uploader": "Tester",
        "webpage_url": SOURCE_URL,
        "extractor": "youtube",
        "vcodec": "avc1.640028",
        "acodec": "mp4a.40.2",
    }
    info.update(overrides)
    return info


# ---------------------------------------------------------------------------
# Single-video inspection


def test_inspect_single_video_returns_metadata_and_safe_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def handler(ydl: FakeYoutubeDL, url: str, download: bool) -> dict[str, Any]:
        seen.update(ydl.opts)
        seen["url"] = url
        seen["download"] = download
        return video_info()

    fake = install(monkeypatch, handler)
    provider, options = provider_and_options(
        {
            "ytdlp_quality": "720",
            "ytdlp_codec": "h264",
            "ytdlp_container": "mp4",
            "ytdlp_audio": "best",
        }
    )

    result = provider.inspect(SOURCE_URL, options)

    assert result == {
        "provider": "ytdlp",
        "label": "yt-dlp",
        "status": "video",
        "available": True,
        "title": "Test clip",
        "filename": "Test clip",
        "duration": 12.5,
        "thumbnail": "https://i.test/thumb.jpg",
        "uploader": "Tester",
        "webpage_url": SOURCE_URL,
        "options": options.as_dict(),
    }
    assert seen["skip_download"] is True
    assert seen["download"] is False
    assert seen["noplaylist"] is False
    assert seen["extract_flat"] == "in_playlist"
    assert "[height<=720]" in seen["format"]
    assert "[vcodec^=avc1][ext=mp4]" in seen["format"]
    assert seen["merge_output_format"] == "mp4/mkv"
    assert fake.instances[0].calls == [(SOURCE_URL, False)]
    assert "outtmpl" not in seen


# ---------------------------------------------------------------------------
# Playlist picker


def test_inspect_playlist_returns_picker_choices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entries = [
        {
            "id": "one",
            "title": "First",
            "webpage_url": "https://www.youtube.com/watch?v=one",
            "duration": 10,
            "thumbnail": "https://i.test/one.jpg",
            "uploader": "Uploader",
        },
        {
            "id": "two",
            "title": "Second",
            "webpage_url": "https://www.youtube.com/watch?v=two",
            "duration": 20,
            "thumbnails": [
                {"url": "https://i.test/two-small.jpg"},
                {"url": "https://i.test/two-large.jpg"},
            ],
        },
        {"id": "missing-url", "title": "No link"},
        {"id": "relative", "title": "Relative", "url": "video-id-only"},
    ]

    def handler(ydl: FakeYoutubeDL, url: str, download: bool) -> dict[str, Any]:
        assert ydl.opts["extract_flat"] == "in_playlist"
        assert ydl.opts["noplaylist"] is False
        return {
            "_type": "playlist",
            "title": "Test playlist",
            "entries": entries,
        }

    install(monkeypatch, handler)
    provider, options = provider_and_options()

    result = provider.inspect("https://www.youtube.com/playlist?list=abc", options)

    assert result["provider"] == "ytdlp"
    assert result["status"] == "picker"
    assert result["available"] is True
    assert result["needs_choice"] is True
    assert result["title"] == "Test playlist"
    assert [choice["id"] for choice in result["choices"]] == ["one", "two"]
    assert result["choices"][0] == {
        "id": "one",
        "title": "First",
        "url": "https://www.youtube.com/watch?v=one",
        "duration": 10,
        "thumbnail": "https://i.test/one.jpg",
        "uploader": "Uploader",
    }
    assert result["choices"][1]["uploader"] == ""
    assert result["choices"][1]["thumbnail"] == "https://i.test/two-large.jpg"
    assert result["options"] == options.as_dict()


def test_inspect_playlist_caps_choices(monkeypatch: pytest.MonkeyPatch) -> None:
    entries = [
        {
            "id": str(index),
            "title": f"Item {index}",
            "webpage_url": f"https://example.test/v/{index}",
        }
        for index in range(205)
    ]

    def handler(ydl: FakeYoutubeDL, url: str, download: bool) -> dict[str, Any]:
        return {"_type": "playlist", "title": "Big", "entries": entries}

    install(monkeypatch, handler)
    provider, options = provider_and_options()

    result = provider.inspect("https://example.test/playlist", options)

    assert len(result["choices"]) == 200
    assert result["choices"][0]["id"] == "0"
    assert "first 200 choices" in result["warning"]


def test_inspect_empty_playlist_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(ydl: FakeYoutubeDL, url: str, download: bool) -> dict[str, Any]:
        return {"_type": "playlist", "title": "Empty", "entries": []}

    install(monkeypatch, handler)
    provider, options = provider_and_options()

    with pytest.raises(IngestError, match="no selectable videos"):
        provider.inspect("https://example.test/playlist", options)


# ---------------------------------------------------------------------------
# Progress, cancel, and download discovery


def test_download_reports_progress_and_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dest = tmp_path / "job" / ".ingest-abc.mp4"
    updates: list[tuple[float, str]] = []
    produced: dict[str, Path] = {}

    def handler(ydl: FakeYoutubeDL, url: str, download: bool) -> dict[str, Any]:
        assert download is True
        output = dest.with_suffix(".mp4")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"video bytes")
        produced["path"] = output
        hook = ydl.opts["progress_hooks"][0]
        hook(
            {
                "status": "downloading",
                "downloaded_bytes": 50,
                "total_bytes": 100,
            }
        )
        hook({"status": "finished", "filename": str(output)})
        return video_info(
            requested_downloads=[{"filepath": str(output)}],
        )

    fake = install(monkeypatch, handler)
    provider, options = provider_and_options(
        {
            "ytdlp_quality": "1080",
            "ytdlp_container": "mp4",
            "ytdlp_codec": "h264",
            "ytdlp_audio": "best",
        }
    )

    result = provider.download(
        SOURCE_URL, dest, options, lambda f, m: updates.append((f, m)), threading.Event()
    )

    assert result.path == produced["path"]
    assert result.path.is_relative_to(dest.parent)
    assert result.filename == "Test clip.mp4"
    assert result.provider == "ytdlp"
    assert result.title == "Test clip"
    assert result.duration == 12.5
    assert result.thumbnail == "https://i.test/thumb.jpg"
    assert result.meta == {
        "uploader": "Tester",
        "webpage_url": SOURCE_URL,
        "extractor": "youtube",
        "quality": "1080",
        "container": "mp4",
        "codec": "h264",
        "audio": "best",
    }

    assert updates[0] == (0.01, "Asking yt-dlp for the video")
    downloading = [item for item in updates if item[1].startswith("Downloading")]
    assert len(downloading) == 1
    assert downloading[0][0] == pytest.approx(0.48)
    assert (0.96, "Download finished; preparing video") in updates
    assert updates[-1] == (1.0, "Download complete")

    opts = fake.instances[0].opts
    outtmpl = Path(opts["outtmpl"]["default"]).parent
    assert outtmpl == dest.parent.resolve()
    assert opts["noplaylist"] is True
    assert opts["overwrites"] is True


def test_cancel_in_progress_hook_stops_download_and_removes_partial(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dest = tmp_path / "job" / ".ingest-cancel.mp4"
    dest.parent.mkdir(parents=True)
    partial = dest.with_suffix(".mp4")
    cancel_event = threading.Event()

    def handler(ydl: FakeYoutubeDL, url: str, download: bool) -> dict[str, Any]:
        partial.write_bytes(b"partial bytes")
        hook = ydl.opts["progress_hooks"][0]
        hook(
            {
                "status": "downloading",
                "downloaded_bytes": 10,
                "total_bytes": 100,
            }
        )
        # The progress callback sets the cancel event after the first update.
        hook(
            {
                "status": "downloading",
                "downloaded_bytes": 20,
                "total_bytes": 100,
            }
        )
        raise AssertionError("cancelled hook must not return")

    install(monkeypatch, handler)
    provider, options = provider_and_options()

    def mark_cancel(fraction: float, message: str) -> None:
        cancel_event.set()

    with pytest.raises(IngestError, match="cancelled"):
        provider.download(SOURCE_URL, dest, options, mark_cancel, cancel_event)

    assert not partial.exists()


def test_cancel_before_download_does_not_call_ytdlp(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    called = False

    def handler(ydl: FakeYoutubeDL, url: str, download: bool) -> dict[str, Any]:
        raise AssertionError("yt-dlp must not be called")

    install(monkeypatch, handler)
    provider, options = provider_and_options()
    cancel_event = threading.Event()
    cancel_event.set()

    with pytest.raises(IngestError, match="cancelled"):
        provider.download(
            SOURCE_URL,
            tmp_path / "clip.mp4",
            options,
            lambda fraction, message: None,
            cancel_event,
        )
    assert called is False


def test_download_prefers_reported_video_over_audio_inputs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dest = tmp_path / "clip.mp4"
    audio = tmp_path / "clip.m4a"
    video = tmp_path / "clip.webm"
    audio.write_bytes(b"audio")
    video.write_bytes(b"video")

    def handler(ydl: FakeYoutubeDL, url: str, download: bool) -> dict[str, Any]:
        return video_info(
            requested_downloads=[
                {"filepath": str(audio)},
                {"filepath": str(video)},
            ]
        )

    install(monkeypatch, handler)
    provider, options = provider_and_options()

    result = provider.download(
        SOURCE_URL,
        dest,
        options,
        lambda fraction, message: None,
        threading.Event(),
    )

    assert result.path == video
    assert result.filename == "Test clip.webm"


def test_download_falls_back_to_filename_glob(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dest = tmp_path / "clip.mp4"
    output = dest.with_suffix(".mkv")

    def handler(ydl: FakeYoutubeDL, url: str, download: bool) -> dict[str, Any]:
        output.write_bytes(b"video")
        return video_info()

    install(monkeypatch, handler)
    provider, options = provider_and_options()

    result = provider.download(
        SOURCE_URL,
        dest,
        options,
        lambda fraction, message: None,
        threading.Event(),
    )

    assert result.path == output
    assert result.filename == "Test clip.mkv"


def test_download_rejects_paths_outside_dest_parent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dest = tmp_path / "job" / "clip.mp4"
    dest.parent.mkdir(parents=True)
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"not allowed")

    def handler(ydl: FakeYoutubeDL, url: str, download: bool) -> dict[str, Any]:
        return video_info(
            requested_downloads=[{"filepath": str(outside)}],
        )

    install(monkeypatch, handler)
    provider, options = provider_and_options()

    with pytest.raises(IngestError, match="no video file"):
        provider.download(
            SOURCE_URL,
            dest,
            options,
            lambda fraction, message: None,
            threading.Event(),
        )
    assert outside.read_bytes() == b"not allowed"


# ---------------------------------------------------------------------------
# Cookies


def test_browser_cookie_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(ydl: FakeYoutubeDL, url: str, download: bool) -> dict[str, Any]:
        return video_info()

    fake = install(monkeypatch, handler)
    provider, options = provider_and_options(
        {"ytdlp_cookies": "browser", "ytdlp_browser": "firefox"}
    )

    provider.inspect(SOURCE_URL, options)

    opts = fake.instances[0].opts
    assert opts["cookiesfrombrowser"] == ("firefox",)
    assert "cookiefile" not in opts


def test_saved_browser_cookies_apply_to_default_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(ydl: FakeYoutubeDL, url: str, download: bool) -> dict[str, Any]:
        return video_info()

    fake = install(monkeypatch, handler)
    provider = registry.provider(
        "ytdlp",
        {"ingest": {"ytdlp_cookies": "browser", "ytdlp_browser": "chrome"}},
    )

    provider.inspect(SOURCE_URL, IngestOptions())

    assert fake.instances[0].opts["cookiesfrombrowser"] == ("chrome",)


def test_cookie_file_mapping(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")

    def handler(ydl: FakeYoutubeDL, url: str, download: bool) -> dict[str, Any]:
        return video_info()

    fake = install(monkeypatch, handler)
    provider, options = provider_and_options(
        {"ytdlp_cookies": "file", "ytdlp_cookie_file": str(cookie_file)}
    )

    provider.inspect(SOURCE_URL, options)

    opts = fake.instances[0].opts
    assert opts["cookiefile"] == str(cookie_file)
    assert "cookiesfrombrowser" not in opts


def test_missing_cookie_file_is_a_clear_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def handler(ydl: FakeYoutubeDL, url: str, download: bool) -> dict[str, Any]:
        raise AssertionError("yt-dlp must not start without cookies")

    install(monkeypatch, handler)
    provider, options = provider_and_options(
        {
            "ytdlp_cookies": "file",
            "ytdlp_cookie_file": str(tmp_path / "missing.txt"),
        }
    )

    with pytest.raises(IngestError, match="cookies.txt file does not exist"):
        provider.inspect(SOURCE_URL, options)


def test_options_override_configured_cookies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def handler(ydl: FakeYoutubeDL, url: str, download: bool) -> dict[str, Any]:
        return video_info()

    fake = install(monkeypatch, handler)
    provider = registry.provider(
        "ytdlp",
        {
            "ingest": {
                "ytdlp_cookies": "file",
                "ytdlp_cookie_file": str(tmp_path / "configured.txt"),
            }
        },
    )
    options = IngestOptions(cookies="browser", browser="chrome")

    provider.inspect(SOURCE_URL, options)

    opts = fake.instances[0].opts
    assert opts["cookiesfrombrowser"] == ("chrome",)
    assert "cookiefile" not in opts


# ---------------------------------------------------------------------------
# Format selection


@pytest.mark.parametrize(
    ("settings", "expected_bits", "forbidden_bits"),
    [
        (
            {},
            (
                "bestvideo*[vcodec^=avc1][ext=mp4]+",
                "bestvideo*[vcodec^=avc1]+",
                "bestvideo*+",
                "bestaudio",
            ),
            ("[height<=",),
        ),
        (
            {"ytdlp_quality": "720"},
            (
                "[height<=720]",
                "[vcodec^=avc1][ext=mp4]",
            ),
            (),
        ),
        (
            {"ytdlp_codec": "any", "ytdlp_audio": "192"},
            (
                "bestvideo*[ext=mp4]",
                "bestaudio[ext=m4a][abr<=192]",
                "bestaudio[abr<=192]",
            ),
            ("avc1",),
        ),
    ],
)
def test_format_selector_prefers_h264_mp4_and_falls_back(
    monkeypatch: pytest.MonkeyPatch,
    settings: dict[str, Any],
    expected_bits: tuple[str, ...],
    forbidden_bits: tuple[str, ...],
) -> None:
    def handler(ydl: FakeYoutubeDL, url: str, download: bool) -> dict[str, Any]:
        return video_info()

    fake = install(monkeypatch, handler)
    provider, options = provider_and_options(settings)

    provider.inspect(SOURCE_URL, options)

    selector = fake.instances[0].opts["format"]
    for bit in expected_bits:
        assert bit in selector
    for bit in forbidden_bits:
        assert bit not in selector


@pytest.mark.parametrize(
    ("container", "expected"),
    [("mp4", "mp4/mkv"), ("mkv", "mkv"), ("webm", "webm/mkv")],
)
def test_merge_container_has_safe_fallback(
    monkeypatch: pytest.MonkeyPatch, container: str, expected: str
) -> None:
    def handler(ydl: FakeYoutubeDL, url: str, download: bool) -> dict[str, Any]:
        return video_info()

    fake = install(monkeypatch, handler)
    provider, options = provider_and_options({"ytdlp_container": container})

    provider.inspect(SOURCE_URL, options)

    assert fake.instances[0].opts["merge_output_format"] == expected


# ---------------------------------------------------------------------------
# Audio-only rejection


@pytest.mark.parametrize(
    "info",
    [
        video_info(vcodec="none", acodec="mp4a.40.2"),
        video_info(
            vcodec=None,
            acodec="opus",
            formats=[{"vcodec": "none", "acodec": "opus", "ext": "webm"}],
        ),
    ],
)
def test_inspect_rejects_audio_only_links(
    monkeypatch: pytest.MonkeyPatch, info: dict[str, Any]
) -> None:
    def handler(ydl: FakeYoutubeDL, url: str, download: bool) -> dict[str, Any]:
        return info

    install(monkeypatch, handler)
    provider, options = provider_and_options()

    with pytest.raises(IngestError, match="audio-only"):
        provider.inspect(SOURCE_URL, options)


def test_download_rejects_audio_only_output_and_cleans_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dest = tmp_path / "clip.mp4"
    audio = tmp_path / "clip.m4a"

    def handler(ydl: FakeYoutubeDL, url: str, download: bool) -> dict[str, Any]:
        audio.write_bytes(b"audio")
        return video_info(
            vcodec="none",
            acodec="mp4a.40.2",
            requested_downloads=[{"filepath": str(audio)}],
        )

    install(monkeypatch, handler)
    provider, options = provider_and_options()

    with pytest.raises(IngestError, match="audio-only"):
        provider.download(
            SOURCE_URL,
            dest,
            options,
            lambda fraction, message: None,
            threading.Event(),
        )
    assert not audio.exists()


# ---------------------------------------------------------------------------
# Status and errors


def test_status_reports_version_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(ydl: FakeYoutubeDL, url: str, download: bool) -> dict[str, Any]:
        raise AssertionError("status must not download")

    install(monkeypatch, handler, version="2026.10.21")
    provider = registry.provider("ytdlp", {"ingest": {}})

    status = provider.status()

    assert status == {
        "id": "ytdlp",
        "label": "yt-dlp",
        "configured": True,
        "available": True,
        "error": "",
        "version": "2026.10.21",
    }


def test_status_without_ytdlp_package(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "yt_dlp", None)
    provider = registry.provider("ytdlp", {"ingest": {}})

    status = provider.status()

    assert status["configured"] is False
    assert status["available"] is False
    assert "yt-dlp is not installed" in status["error"]
    assert status["version"] == ""
    assert ytdlp.ytdlp_available() is False


def test_status_reports_bad_cookie_file(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(ydl: FakeYoutubeDL, url: str, download: bool) -> dict[str, Any]:
        raise AssertionError("status must not download")

    install(monkeypatch, handler)
    provider = registry.provider(
        "ytdlp",
        {
            "ingest": {
                "ytdlp_cookies": "file",
                "ytdlp_cookie_file": "/definitely/missing/cookies.txt",
            }
        },
    )

    status = provider.status()

    assert status["configured"] is True
    assert status["available"] is False
    assert "does not exist" in status["error"]


def test_inspect_maps_private_video_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(ydl: FakeYoutubeDL, url: str, download: bool) -> dict[str, Any]:
        raise RuntimeError("ERROR: [youtube] abc: Private video. Sign in to watch")

    install(monkeypatch, handler)
    provider, options = provider_and_options()

    with pytest.raises(IngestError, match="This video is private"):
        provider.inspect(SOURCE_URL, options)


def test_provider_has_no_subprocess_or_sidecar_imports() -> None:
    source = Path(ytdlp.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "subprocess" not in imported
    assert "xhs" not in imported
    assert "xhs" not in imported


def test_inspect_normalizes_rednote_host_for_explicit_ytdlp(monkeypatch, tmp_path):
    seen: list[str] = []

    def handler(ydl, url: str, download: bool) -> dict[str, Any]:
        seen.append(url)
        return video_info(
            webpage_url="https://www.xiaohongshu.com/explore/abc123",
            title="RedNote clip",
        )

    install(monkeypatch, handler)
    provider, options = provider_and_options()
    result = provider.inspect(
        "https://rednote.com/explore/abc123?xsec_token=token-value", options
    )

    assert seen == [
        "https://www.xiaohongshu.com/explore/abc123?xsec_token=token-value"
    ]
    assert result["provider"] == "ytdlp"
    assert result["title"] == "RedNote clip"
    assert result["meta"]["note_url"].startswith("https://www.xiaohongshu.com/")


def test_download_uses_the_selected_entry_url(monkeypatch, tmp_path):
    seen: list[str] = []
    dest = tmp_path / "selected.mp4"

    def handler(ydl, url: str, download: bool) -> dict[str, Any]:
        seen.append(url)
        dest.write_bytes(b"video")
        return video_info(title="Selected clip")

    install(monkeypatch, handler)
    provider, options = provider_and_options()

    result = provider.download(
        "https://www.youtube.com/watch?v=selected123",
        dest,
        options,
        lambda fraction, message: None,
        threading.Event(),
    )

    assert seen == ["https://www.youtube.com/watch?v=selected123"]
    assert result.title == "Selected clip"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("ERROR: Private video. Sign in", "This video is private."),
        ("ERROR: This video is age-gated", "This video is age-gated. Add cookies in Setup."),
        ("ERROR: Sign in to confirm your age", "This video is age-gated. Add cookies in Setup."),
        ("ERROR: Unsupported URL", "yt-dlp does not support this URL."),
        ("ERROR: This video is geo restricted", "This video is region-restricted."),
        ("ERROR: HTTP Error 404: Not Found", "The video was not found."),
        ("ERROR: DRM protected stream", "This video is DRM-protected and cannot be downloaded."),
    ],
)
def test_error_text_maps_user_facing_failures(message: str, expected: str) -> None:
    assert ytdlp._error_text(RuntimeError(message)) == expected


def test_direct_mp4_with_unknown_vcodec_is_not_treated_as_audio_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def handler(ydl, url: str, download: bool) -> dict[str, Any]:
        return video_info(
            webpage_url="https://cdn.example/video.mp4",
            title="Direct video",
            vcodec=None,
            formats=[{"ext": "mp4", "video_ext": "mp4", "vcodec": None}],
        )

    install(monkeypatch, handler)
    provider, options = provider_and_options()

    result = provider.inspect("https://cdn.example/video.mp4", options)

    assert result["status"] == "video"
    assert result["title"] == "Direct video"
