"""Core contract tests for URL ingest: detection, settings, lazy providers."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from url_ingest import registry
from url_ingest.base import IngestError, IngestOptions, IngestResult, Provider


# ---------------------------------------------------------------------------
# Detection


@pytest.mark.parametrize(
    "url",
    [
        "https://www.xiaohongshu.com/explore/0123456789abcdef",
        "https://xiaohongshu.com/discovery/item/abc",
        "https://www.rednote.com/explore/abc",
        "https://rednote.com/discovery/item/abc",
        "https://xhslink.com/a/AbCdEf",
        "https://share.xhslink.com/a/AbCdEf",
        "HTTPS://WWW.XIAOHONGSHU.COM/explore/abc",
    ],
)
def test_detect_xhs_domains(url: str) -> None:
    assert registry.detect(url) == registry.XHS


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://vimeo.com/123456",
        "https://example.com/video.mp4",
        "https://notrednote.com/video",
        "https://xiaohongshu.com.evil.example/explore/abc",
        "https://evil.example/explore/abc",
    ],
)
def test_detect_ytdlp_domains(url: str) -> None:
    assert registry.detect(url) == registry.YTDLP


def test_detect_explicit_override_wins() -> None:
    xhs_url = "https://www.xiaohongshu.com/explore/abc"
    video_url = "https://www.youtube.com/watch?v=abc"
    assert registry.detect(video_url, registry.XHS) == registry.XHS
    assert registry.detect(xhs_url, "xhs_get") == registry.XHS
    assert registry.detect(video_url, "yt-dlp") == registry.YTDLP
    assert registry.detect(xhs_url, "ytdlp") == registry.YTDLP
    assert registry.detect(xhs_url, registry.AUTO) == registry.XHS
    assert registry.detect(video_url, registry.AUTO) == registry.YTDLP


@pytest.mark.parametrize(
    "url",
    [
        None,
        123,
        "",
        "   ",
        "youtube.com/watch?v=abc",
        "ftp://example.com/video.mp4",
        "javascript:alert(1)",
        "https://",
        "http:///missing-host",
        "https://exa mple.com/video",
        "https://example.com\\@evil.example/video",
        "mailto:user@example.com",
        "https://user:pass@example.com/video",
        "https://user@example.com/video",
    ],
)
def test_detect_rejects_invalid_urls(url: object) -> None:
    with pytest.raises(IngestError):
        registry.detect(url)  # type: ignore[arg-type]


def test_detect_rejects_unknown_override() -> None:
    with pytest.raises(IngestError, match="Unknown ingest provider"):
        registry.detect("https://example.com/video", "nope")


def test_validate_url_strips_whitespace() -> None:
    assert (
        registry.validate_url("  https://example.com/watch?v=abc  ")
        == "https://example.com/watch?v=abc"
    )


def test_detection_does_not_import_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_import(provider_id: str) -> object:
        calls.append(provider_id)
        raise AssertionError("detection must not import a provider")

    monkeypatch.setattr(registry, "_import_provider_module", fake_import)
    assert registry.detect("https://youtube.com/watch?v=abc") == registry.YTDLP
    assert registry.detect("https://xhslink.com/a/abc") == registry.XHS
    assert calls == []


# ---------------------------------------------------------------------------
# Settings and options


def test_normalize_settings_defaults() -> None:
    assert registry.normalize_settings(None) == registry.DEFAULT_INGEST_SETTINGS
    assert registry.normalize_settings({}) == registry.DEFAULT_INGEST_SETTINGS
    assert registry.normalize_settings({"ingest": {}}) == registry.DEFAULT_INGEST_SETTINGS


def test_normalize_settings_accepts_full_app_settings() -> None:
    normalized = registry.normalize_settings(
        {
            "opencode": {"model": "unrelated"},
            "ingest": {
                "provider": "XHS_GET",
                "xhs_url": "  http://127.0.0.1:8123  ",
                "xhs_no_record": "false",
                "xhs_interval": "2.5",
                "xhs_token": "secret-value",
            },
        }
    )
    assert normalized["provider"] == registry.XHS
    assert normalized["xhs_url"] == "http://127.0.0.1:8123"
    assert normalized["xhs_no_record"] is False
    assert normalized["xhs_interval"] == 2.5
    # Provider extensions pass through untouched.
    assert normalized["xhs_token"] == "secret-value"


def test_normalize_settings_falls_back_on_invalid_values() -> None:
    normalized = registry.normalize_settings(
        {
            "ingest": {
                "provider": "bogus",
                "xhs_url": "   ",
                "xhs_no_record": "maybe",
                "xhs_interval": "nan",
            }
        }
    )
    assert normalized["provider"] == registry.AUTO
    # An explicitly cleared endpoint stays cleared.
    assert normalized["xhs_url"] == ""
    assert normalized["xhs_no_record"] is True
    assert normalized["xhs_interval"] == 12.0


def test_normalize_settings_rejects_non_mapping() -> None:
    with pytest.raises(IngestError, match="mapping"):
        registry.normalize_settings(["not", "a", "mapping"])  # type: ignore[arg-type]


def test_options_from_settings() -> None:
    settings = {
        "ingest": {
            "ytdlp_quality": "720",
            "ytdlp_codec": "any",
            "ytdlp_container": "mkv",
            "ytdlp_audio": "192",
            "ytdlp_cookies": "browser",
            "ytdlp_browser": "firefox",
            "ytdlp_cookie_file": "/tmp/cookies.txt",
            "xhs_no_record": False,
            "xhs_interval": "3",
        }
    }
    assert registry.options_from_settings(settings) == IngestOptions(
        quality="720",
        codec="any",
        container="mkv",
        audio="192",
        cookies="browser",
        browser="firefox",
        cookie_file="/tmp/cookies.txt",
        local_processing="preferred",
        no_record=False,
        interval=3.0,
    )

    overridden = registry.options_from_settings(
        settings,
        {
            "quality": "1080",
            "audio": "best",
            "cookies": "file",
            "cookie_file": "/tmp/other.txt",
            "no_record": True,
            "interval": "5.5",
        },
    )
    assert overridden == IngestOptions(
        quality="1080",
        codec="any",
        container="mkv",
        audio="best",
        cookies="file",
        browser="firefox",
        cookie_file="/tmp/cookies.txt",
        local_processing="preferred",
        no_record=True,
        interval=5.5,
    )


# ---------------------------------------------------------------------------
# Provider construction and status


class _FakeXhs(Provider):
    id = "xhs"
    label = "XHS / RedNote"

    def __init__(self, settings: dict | None = None) -> None:
        super().__init__(settings)
        self.seen_settings = dict(settings or {})

    def inspect(self, url: str, options: IngestOptions) -> dict:
        return {"url": url}

    def download(self, url, dest, options, progress, cancel_event):  # type: ignore[no-untyped-def]
        raise NotImplementedError


class _FakeYtdlp(Provider):
    id = "ytdlp"
    label = "yt-dlp"

    def inspect(self, url: str, options: IngestOptions) -> dict:
        return {"url": url}

    def download(self, url, dest, options, progress, cancel_event):  # type: ignore[no-untyped-def]
        raise NotImplementedError


def _install_fake_module(
    monkeypatch: pytest.MonkeyPatch, provider_id: str, class_name: str, cls: type
) -> None:
    module = types.ModuleType(f"url_ingest.{provider_id}")
    setattr(module, class_name, cls)
    monkeypatch.setitem(sys.modules, f"url_ingest.{provider_id}", module)


def test_provider_construction_is_lazy_and_passes_normalized_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_module(monkeypatch, "xhs", "XhsGetProvider", _FakeXhs)
    calls: list[str] = []
    real_import = registry._import_provider_module

    def tracked_import(provider_id: str) -> object:
        calls.append(provider_id)
        return real_import(provider_id)

    monkeypatch.setattr(registry, "_import_provider_module", tracked_import)
    instance = registry.provider(
        "xhs",
        {
            "ingest": {
                "xhs_url": "http://127.0.0.1:9999/",
                "xhs_token": "key-123",
            }
        },
    )
    assert isinstance(instance, _FakeXhs)
    assert instance.seen_settings["xhs_url"] == "http://127.0.0.1:9999/"
    assert instance.seen_settings["xhs_token"] == "key-123"
    assert calls == ["xhs"]


def test_provider_auto_uses_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_module(monkeypatch, "ytdlp", "YtDlpProvider", _FakeYtdlp)
    instance = registry.provider(
        registry.AUTO, {"ingest": {}}, url="https://youtube.com/watch?v=abc"
    )
    assert isinstance(instance, _FakeYtdlp)


def test_provider_auto_uses_url_for_xhs(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_module(monkeypatch, "xhs", "XhsGetProvider", _FakeXhs)
    instance = registry.provider(
        registry.AUTO,
        {"ingest": {}},
        url="https://www.xiaohongshu.com/explore/abc",
    )
    assert isinstance(instance, _FakeXhs)


def test_provider_ytdlp_builds_the_native_provider() -> None:
    instance = registry.provider("ytdlp", {"ingest": {}})
    assert instance.id == registry.YTDLP
    assert instance.label == "yt-dlp"
    assert hasattr(instance, "inspect")
    assert hasattr(instance, "download")
    assert hasattr(instance, "status")


def test_provider_auto_prefers_explicit_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_module(monkeypatch, "xhs", "XhsGetProvider", _FakeXhs)
    instance = registry.provider(
        registry.AUTO,
        {"ingest": {"provider": "xhs"}},
        url="https://youtube.com/watch?v=abc",
    )
    assert isinstance(instance, _FakeXhs)


def test_provider_auto_without_url_errors() -> None:
    with pytest.raises(IngestError, match="needs a URL"):
        registry.provider(registry.AUTO, {"ingest": {}})


def test_unknown_provider_errors() -> None:
    with pytest.raises(IngestError, match="Unknown ingest provider"):
        registry.provider("bogus", {"ingest": {}})


def test_missing_provider_module_is_an_ingest_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "url_ingest.xhs", None)
    with pytest.raises(IngestError, match="XHS / RedNote provider is unavailable"):
        registry.provider("xhs", {"ingest": {}})


def test_status_with_provider_modules_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "url_ingest.ytdlp", None)
    monkeypatch.setitem(sys.modules, "url_ingest.xhs", None)

    result = registry.status({"ingest": {}})
    assert set(result) == {registry.YTDLP, registry.XHS}
    for provider_id, entry in result.items():
        assert set(entry) == {"id", "label", "configured", "available", "error"}
        assert entry["id"] == provider_id
        assert entry["configured"] is True
        assert entry["available"] is False
        assert "module is unavailable" in entry["error"]
    assert result[registry.YTDLP]["label"] == "yt-dlp"
    assert result[registry.XHS]["label"] == "XHS / RedNote"


def test_status_reports_ytdlp_version_without_sidecars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class VersionedYtdlp(_FakeYtdlp):
        def status(self, settings: dict | None = None) -> dict:
            return {
                "id": "ytdlp",
                "label": "yt-dlp",
                "configured": True,
                "available": True,
                "error": "",
                "version": "2026.10.21",
            }

    _install_fake_module(monkeypatch, "ytdlp", "YtDlpProvider", VersionedYtdlp)
    monkeypatch.setitem(sys.modules, "url_ingest.xhs", None)

    result = registry.status({"ingest": {}})
    assert result[registry.YTDLP]["available"] is True
    assert result[registry.YTDLP]["version"] == "2026.10.21"
    assert result[registry.XHS]["available"] is False


def test_status_reports_invalid_configured_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "url_ingest.xhs", None)
    result = registry.status({"ingest": {"xhs_url": "ftp://example.com"}})
    entry = result[registry.XHS]
    assert entry["configured"] is False
    assert entry["available"] is False
    assert "URL is invalid" in entry["error"]


def test_status_uses_provider_health_check(monkeypatch: pytest.MonkeyPatch) -> None:
    class ReadyXhs(_FakeXhs):
        def status(self) -> dict:
            return {"configured": True, "available": True, "error": ""}

    _install_fake_module(monkeypatch, "xhs", "XhsGetProvider", ReadyXhs)
    result = registry.status({"ingest": {}})
    assert result[registry.XHS] == {
        "id": "xhs",
        "label": "XHS / RedNote",
        "configured": True,
        "available": True,
        "error": "",
    }


def test_safe_filename_blocks_paths_and_illegal_characters() -> None:
    name = registry.safe_filename('../../My: "Video"? 1080p.mp4')
    assert name.endswith(".mp4")
    assert "/" not in name
    assert "\\" not in name
    assert not any(character in name for character in '<>:"|?*')
    assert not name.startswith(".")


def test_safe_filename_limits_length_and_keeps_extension() -> None:
    name = registry.safe_filename("x" * 500 + ".mp4", max_length=40)
    assert len(name) <= 40
    assert name.endswith(".mp4")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", "video"),
        ("   ", "video"),
        ("...", "video"),
        ("CON", "_CON"),
        ("con.txt", "_con.txt"),
        ("  clip  ", "clip"),
    ],
)
def test_safe_filename_fallbacks(value: str, expected: str) -> None:
    assert registry.safe_filename(value) == expected


def test_ingest_result_normalizes_path_and_filename() -> None:
    result = IngestResult(path="/tmp/example.mp4", filename="", provider="ytdlp")
    assert result.path == Path("/tmp/example.mp4")
    assert result.filename == "example.mp4"
    assert result.meta == {}


def test_public_options_do_not_serialize_cookie_file_path():
    options = registry.options_from_settings(
        {"ingest": {"ytdlp_cookies": "file", "ytdlp_cookie_file": "/tmp/cookies.txt"}}
    )
    public = options.as_dict()
    assert public["cookies"] == "file"
    assert "cookie_file" not in public
    assert "/tmp/cookies.txt" not in str(public)
