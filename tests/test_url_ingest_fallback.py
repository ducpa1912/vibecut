"""Tests for the URL ingest provider fallback chain."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from url_ingest.base import IngestError, IngestOptions, IngestResult, Provider
from url_ingest.fallback import (
    XHS,
    YTDLP,
    ChainError,
    ProviderChain,
    fallback_provider_ids,
    run_download,
    run_inspect,
)

SOURCE_URL = "https://youtube.com/watch?v=abc123"
XHS_URL = "https://www.xiaohongshu.com/explore/abc"


class FakeProvider(Provider):
    def __init__(self, provider_id: str, *, fail_inspect: bool = False, fail_download: bool = False,
                 cancel_on_download: bool = False, result_meta: dict | None = None) -> None:
        super().__init__({})
        self.id = provider_id
        self.label = provider_id
        self.fail_inspect = fail_inspect
        self.fail_download = fail_download
        self.cancel_on_download = cancel_on_download
        self.result_meta = result_meta
        self.inspect_calls: list[str] = []
        self.download_calls: list[Path] = []

    def inspect(self, url: str, options: IngestOptions) -> dict:
        self.inspect_calls.append(url)
        if self.fail_inspect:
            raise IngestError(f"{self.id} inspect failed")
        return {"provider": self.id, "label": self.id, "status": "video", "available": True,
                "title": f"{self.id} title", "options": options.as_dict()}

    def download(self, url, dest, options, progress, cancel_event):  # type: ignore[no-untyped-def]
        self.download_calls.append(Path(dest))
        if self.cancel_on_download:
            cancel_event.set()
        if self.fail_download:
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            Path(dest).write_bytes(b"partial")
            raise IngestError(f"{self.id} download failed")
        target = Path(dest)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"video bytes")
        return IngestResult(path=target, filename=f"{self.id}.mp4", provider=self.id,
                            title=f"{self.id} title", meta=dict(self.result_meta or {"source": self.id}))


def make_chain(*providers: FakeProvider, order: list[str] | None = None) -> ProviderChain:
    sources = {provider.id: provider for provider in providers}
    return ProviderChain(sources, order=order if order is not None else list(sources))


@pytest.mark.parametrize(("configured", "detected", "expected"), [
    ("auto", YTDLP, [YTDLP]),
    ("", YTDLP, [YTDLP]),
    ("auto", XHS, [XHS]),
    ("xhs", YTDLP, [XHS]),
    ("ytdlp", YTDLP, [YTDLP]),
    ("yt-dlp", XHS, [YTDLP]),
    ("rednote", YTDLP, [XHS]),
])
def test_fallback_provider_ids(configured, detected, expected):
    assert fallback_provider_ids(configured, detected, True) == expected


def test_chain_uses_first_success(tmp_path):
    primary = FakeProvider(YTDLP)
    backup = FakeProvider("backup")
    chain = make_chain(primary, backup, order=[YTDLP, "backup"])
    result = chain.download(SOURCE_URL, tmp_path / "video.mp4", IngestOptions())
    assert result.provider == YTDLP
    assert backup.download_calls == []


def test_chain_falls_back_after_failure(tmp_path):
    primary = FakeProvider(YTDLP, fail_download=True)
    backup = FakeProvider("backup", result_meta={"source": "backup"})
    chain = make_chain(primary, backup, order=[YTDLP, "backup"])
    result = chain.download(SOURCE_URL, tmp_path / "video.mp4", IngestOptions())
    assert result.provider == "backup"
    assert result.meta["source"] == "backup"
    assert len(primary.download_calls) == 1


def test_chain_preserves_primary_error(tmp_path):
    primary = FakeProvider(YTDLP, fail_download=True)
    backup = FakeProvider("backup", fail_download=True)
    chain = make_chain(primary, backup, order=[YTDLP, "backup"])
    with pytest.raises(ChainError) as info:
        chain.download(SOURCE_URL, tmp_path / "video.mp4", IngestOptions())
    assert "ytdlp download failed" in str(info.value)
    assert [item.provider for item in info.value.attempts] == [YTDLP, "backup"]


def test_cancel_is_final(tmp_path):
    event = threading.Event()
    primary = FakeProvider(YTDLP, cancel_on_download=True)
    backup = FakeProvider("backup")
    chain = make_chain(primary, backup, order=[YTDLP, "backup"])
    with pytest.raises(ChainError):
        chain.download(SOURCE_URL, tmp_path / "video.mp4", IngestOptions(), cancel_event=event)
    assert backup.download_calls == []


def test_xhs_never_falls_back(tmp_path):
    chain = make_chain(FakeProvider(XHS), order=fallback_provider_ids("auto", XHS, True))
    result = chain.download(XHS_URL, tmp_path / "video.mp4", IngestOptions())
    assert result.provider == XHS


def test_run_inspect_uses_order():
    primary = FakeProvider(YTDLP, fail_inspect=True)
    backup = FakeProvider("backup")
    result = run_inspect({YTDLP: primary, "backup": backup}, SOURCE_URL, order=[YTDLP, "backup"])
    assert result["provider"] == "backup"
    assert len(primary.inspect_calls) == 1


def test_run_download_accepts_mapping_and_order(tmp_path):
    primary = FakeProvider(YTDLP)
    result = run_download({YTDLP: primary}, SOURCE_URL, tmp_path / "video.mp4", order=[YTDLP])
    assert result.provider == YTDLP
