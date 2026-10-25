"""Tests for the URL ingest provider fallback chain."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from url_ingest.base import IngestError, IngestOptions, IngestResult, Provider
from url_ingest.fallback import (
    COBALT,
    XHS,
    YTDLP,
    Attempt,
    ChainError,
    ProviderChain,
    fallback_provider_ids,
    run_download,
    run_inspect,
)

SOURCE_URL = "https://youtube.com/watch?v=abc123"
XHS_URL = "https://www.xiaohongshu.com/explore/abc"


class FakeProvider(Provider):
    """Small Provider fake that records calls and can fail on demand."""

    def __init__(
        self,
        provider_id: str,
        *,
        fail_inspect: bool = False,
        fail_download: bool = False,
        inspect_error: str = "",
        download_error: str = "",
        inspect_result: dict | None = None,
        cancel_event: threading.Event | None = None,
        cancel_on_inspect: bool = False,
        cancel_on_download: bool = False,
        cancel_after_download: bool = False,
        result_meta: dict | None = None,
    ) -> None:
        super().__init__({})
        self.id = provider_id
        self.label = provider_id
        self.fail_inspect = fail_inspect
        self.fail_download = fail_download
        self.inspect_error = inspect_error or f"{provider_id} inspect failed"
        self.download_error = download_error or f"{provider_id} download failed"
        self.inspect_result = inspect_result
        self.cancel_event = cancel_event
        self.cancel_on_inspect = cancel_on_inspect
        self.cancel_on_download = cancel_on_download
        self.cancel_after_download = cancel_after_download
        self.result_meta = result_meta
        self.inspect_calls: list[tuple[str, IngestOptions]] = []
        self.download_calls: list[tuple[str, Path, IngestOptions]] = []
        self.status_calls: list[object] = []

    def status(self, settings=None):  # type: ignore[no-untyped-def]
        self.status_calls.append(settings)
        raise AssertionError("fallback must not consult provider status")

    def inspect(self, url: str, options: IngestOptions) -> dict:
        self.inspect_calls.append((url, options))
        if self.cancel_on_inspect and self.cancel_event is not None:
            self.cancel_event.set()
        if self.fail_inspect:
            raise IngestError(self.inspect_error)
        if self.inspect_result is not None:
            return dict(self.inspect_result)
        return {
            "provider": self.id,
            "label": self.id,
            "status": "video",
            "available": True,
            "title": f"{self.id} title",
            "options": options.as_dict(),
        }

    def download(self, url, dest, options, progress, cancel_event):  # type: ignore[no-untyped-def]
        self.download_calls.append((url, Path(dest), options))
        if self.cancel_on_download:
            cancel_event.set()
        if self.fail_download:
            target = Path(dest)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"partial video")
            target.with_name(target.name + ".part").write_bytes(b"partial sidecar")
            raise IngestError(self.download_error)
        target = Path(dest)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"video bytes")
        if self.cancel_after_download:
            cancel_event.set()
        return IngestResult(
            path=target,
            filename=f"{self.id}.mp4",
            provider=self.id,
            title=f"{self.id} title",
            meta=dict(self.result_meta or {"source": self.id}),
        )


def make_chain(
    *providers: FakeProvider,
    order: list[str] | None = None,
    factories: dict[str, object] | None = None,
) -> ProviderChain:
    sources: dict[str, object] = {provider.id: provider for provider in providers}
    if factories:
        sources.update(factories)
    selected = order if order is not None else list(sources)
    return ProviderChain(sources, order=selected)


# ---------------------------------------------------------------------------
# Chain selection


@pytest.mark.parametrize(
    ("configured", "detected", "ytdlp_available", "cobalt_configured", "expected"),
    [
        ("auto", YTDLP, True, False, [YTDLP]),
        ("auto", YTDLP, True, True, [YTDLP, COBALT]),
        ("", YTDLP, True, True, [YTDLP, COBALT]),
        ("auto", COBALT, True, True, [YTDLP, COBALT]),
        ("auto", YTDLP, False, True, [YTDLP, COBALT]),
        ("auto", YTDLP, False, False, [YTDLP]),
        ("auto", XHS, True, True, [XHS]),
        ("xhs", YTDLP, True, True, [XHS]),
        ("ytdlp", YTDLP, True, True, [YTDLP]),
        ("yt-dlp", XHS, True, True, [YTDLP]),
        ("cobalt", YTDLP, True, True, [COBALT]),
        ("rednote", YTDLP, True, True, [XHS]),
    ],
)
def test_fallback_provider_ids(
    configured: str,
    detected: str,
    ytdlp_available: bool,
    cobalt_configured: bool,
    expected: list[str],
) -> None:
    assert (
        fallback_provider_ids(
            configured, detected, ytdlp_available, cobalt_configured
        )
        == expected
    )


def test_explicit_provider_is_the_only_provider(tmp_path: Path) -> None:
    ytdlp = FakeProvider(YTDLP)
    cobalt = FakeProvider(COBALT)
    chain = make_chain(ytdlp, cobalt, order=fallback_provider_ids("cobalt", YTDLP, True, True))

    result = chain.download(SOURCE_URL, tmp_path / "video.mp4", IngestOptions())

    assert result.provider == COBALT
    assert ytdlp.download_calls == []
    assert len(cobalt.download_calls) == 1


def test_explicit_ytdlp_does_not_fall_back_to_cobalt(tmp_path: Path) -> None:
    ytdlp = FakeProvider(YTDLP, fail_download=True)
    cobalt = FakeProvider(COBALT)
    chain = make_chain(ytdlp, cobalt, order=fallback_provider_ids("ytdlp", YTDLP, True, True))

    with pytest.raises(ChainError) as info:
        chain.download(SOURCE_URL, tmp_path / "video.mp4", IngestOptions())

    assert str(info.value) == "ytdlp download failed"
    assert cobalt.download_calls == []
    assert [attempt.provider for attempt in info.value.attempts] == [YTDLP]


def test_xhs_is_not_a_cobalt_fallback(tmp_path: Path) -> None:
    ytdlp = FakeProvider(YTDLP)
    cobalt = FakeProvider(COBALT)
    xhs = FakeProvider(XHS)
    chain = make_chain(ytdlp, cobalt, xhs, order=fallback_provider_ids("auto", XHS, True, True))

    result = chain.download(XHS_URL, tmp_path / "note.mp4", IngestOptions())

    assert result.provider == XHS
    assert ytdlp.download_calls == []
    assert cobalt.download_calls == []


# ---------------------------------------------------------------------------
# Download fallback


def test_ytdlp_success_never_touches_cobalt(tmp_path: Path) -> None:
    ytdlp = FakeProvider(YTDLP)
    cobalt = FakeProvider(COBALT)
    constructed: list[str] = []

    def cobalt_factory() -> FakeProvider:
        constructed.append(COBALT)
        return cobalt

    chain = make_chain(ytdlp, factories={COBALT: cobalt_factory})
    result = chain.download(SOURCE_URL, tmp_path / "video.mp4", IngestOptions())

    assert result.provider == YTDLP
    assert cobalt.download_calls == []
    assert constructed == []
    assert ytdlp.status_calls == []
    assert cobalt.status_calls == []
    assert [attempt.as_dict() for attempt in chain.last_attempts] == [
        {
            "provider": YTDLP,
            "stage": "download",
            "ok": True,
            "error": "",
            "cancelled": False,
        }
    ]
    assert result.meta["fallback"]["used"] is False
    assert result.meta["fallback"]["primary"] == YTDLP
    assert result.meta["source"] == YTDLP
    assert result.path.parent == tmp_path
    assert result.path != tmp_path / "video.mp4"


def test_ytdlp_failure_falls_back_to_cobalt(tmp_path: Path) -> None:
    ytdlp = FakeProvider(YTDLP, fail_download=True, download_error="yt-dlp broke")
    cobalt = FakeProvider(COBALT, result_meta={"source": "cobalt"})
    chain = make_chain(ytdlp, cobalt)
    dest = tmp_path / "video.mp4"

    result = chain.download(SOURCE_URL, dest, IngestOptions())

    assert result.provider == COBALT
    assert [attempt.provider for attempt in chain.last_attempts] == [YTDLP, COBALT]
    assert chain.last_attempts[0].ok is False
    assert chain.last_attempts[0].error == "yt-dlp broke"
    assert chain.last_attempts[1].ok is True
    assert result.meta["source"] == "cobalt"

    attempts = result.meta["attempts"]
    assert [entry["provider"] for entry in attempts] == [YTDLP, COBALT]
    assert [entry["ok"] for entry in attempts] == [False, True]
    assert result.meta["fallback"]["used"] is True
    assert result.meta["fallback"]["provider"] == COBALT
    assert result.meta["fallback"]["primary"] == YTDLP
    assert [attempt.provider for attempt in result.attempts] == [YTDLP, COBALT]

    first_dest = ytdlp.download_calls[0][1]
    second_dest = cobalt.download_calls[0][1]
    assert first_dest != second_dest
    assert first_dest != dest
    assert second_dest != dest
    assert not first_dest.exists()
    assert not first_dest.with_name(first_dest.name + ".part").exists()
    assert second_dest.is_file()
    assert not dest.exists()


def test_both_providers_fail_preserves_primary_error(tmp_path: Path) -> None:
    ytdlp = FakeProvider(
        YTDLP, fail_download=True, download_error="yt-dlp exploded"
    )
    cobalt = FakeProvider(
        COBALT, fail_download=True, download_error="cobalt exploded"
    )
    chain = make_chain(ytdlp, cobalt)

    with pytest.raises(ChainError) as info:
        chain.download(SOURCE_URL, tmp_path / "video.mp4", IngestOptions())

    error = info.value
    assert str(error) == "yt-dlp exploded"
    assert error.primary_provider == YTDLP
    assert error.primary_error == "yt-dlp exploded"
    assert error.fallback_error == "cobalt exploded"
    assert error.cancelled is False
    assert [attempt.provider for attempt in error.attempts] == [YTDLP, COBALT]
    assert error.as_dict()["attempts"][0]["error"] == "yt-dlp exploded"
    assert [attempt[1] for attempt in ytdlp.download_calls]
    assert list(tmp_path.iterdir()) == []


def test_no_cobalt_configured_means_no_cobalt_attempt(tmp_path: Path) -> None:
    ytdlp = FakeProvider(YTDLP, fail_download=True, download_error="yt-dlp broke")
    cobalt = FakeProvider(COBALT)
    order = fallback_provider_ids("auto", YTDLP, True, False)
    chain = make_chain(ytdlp, cobalt, order=order)

    with pytest.raises(ChainError) as info:
        chain.download(SOURCE_URL, tmp_path / "video.mp4", IngestOptions())

    assert order == [YTDLP]
    assert str(info.value) == "yt-dlp broke"
    assert cobalt.download_calls == []
    assert [attempt.provider for attempt in info.value.attempts] == [YTDLP]


# ---------------------------------------------------------------------------
# Cancellation


def test_cancel_during_ytdlp_is_final(tmp_path: Path) -> None:
    event = threading.Event()
    ytdlp = FakeProvider(YTDLP, cancel_on_download=True, fail_download=True)
    cobalt = FakeProvider(COBALT)
    chain = make_chain(ytdlp, cobalt)

    with pytest.raises(ChainError) as info:
        chain.download(
            SOURCE_URL, tmp_path / "video.mp4", IngestOptions(), cancel_event=event
        )

    assert event.is_set()
    assert info.value.cancelled is True
    assert str(info.value) == "Download cancelled."
    assert cobalt.download_calls == []
    assert [attempt.provider for attempt in info.value.attempts] == [YTDLP]
    assert info.value.attempts[0].cancelled is True


def test_cancel_error_without_event_is_still_final(tmp_path: Path) -> None:
    ytdlp = FakeProvider(
        YTDLP, fail_download=True, download_error="Download cancelled."
    )
    cobalt = FakeProvider(COBALT)
    chain = make_chain(ytdlp, cobalt)

    with pytest.raises(ChainError) as info:
        chain.download(SOURCE_URL, tmp_path / "video.mp4", IngestOptions())

    assert info.value.cancelled is True
    assert cobalt.download_calls == []


def test_cancel_after_successful_provider_does_not_fall_back(tmp_path: Path) -> None:
    event = threading.Event()
    ytdlp = FakeProvider(YTDLP, cancel_after_download=True)
    cobalt = FakeProvider(COBALT)
    chain = make_chain(ytdlp, cobalt)

    with pytest.raises(ChainError) as info:
        chain.download(
            SOURCE_URL, tmp_path / "video.mp4", IngestOptions(), cancel_event=event
        )

    assert info.value.cancelled is True
    assert cobalt.download_calls == []
    assert ytdlp.download_calls[0][1].exists() is False


def test_cancel_before_start_attempts_nothing(tmp_path: Path) -> None:
    event = threading.Event()
    event.set()
    ytdlp = FakeProvider(YTDLP)
    cobalt = FakeProvider(COBALT)
    chain = make_chain(ytdlp, cobalt)

    with pytest.raises(ChainError) as info:
        chain.download(
            SOURCE_URL, tmp_path / "video.mp4", IngestOptions(), cancel_event=event
        )

    assert info.value.cancelled is True
    assert info.value.attempts == ()
    assert ytdlp.download_calls == []
    assert cobalt.download_calls == []


# ---------------------------------------------------------------------------
# Lazy construction and standalone API


def test_cobalt_construction_failure_does_not_block_ytdlp(tmp_path: Path) -> None:
    ytdlp = FakeProvider(YTDLP)

    def broken_cobalt() -> FakeProvider:
        raise IngestError("Cobalt is not installed")

    chain = make_chain(ytdlp, factories={COBALT: broken_cobalt})
    result = chain.download(SOURCE_URL, tmp_path / "video.mp4", IngestOptions())

    assert result.provider == YTDLP
    assert result.meta["fallback"]["used"] is False


def test_cobalt_construction_failure_after_ytdlp_failure_keeps_primary_error(
    tmp_path: Path,
) -> None:
    ytdlp = FakeProvider(YTDLP, fail_download=True, download_error="yt-dlp broke")

    def broken_cobalt() -> FakeProvider:
        raise IngestError("Cobalt is not installed")

    chain = make_chain(ytdlp, factories={COBALT: broken_cobalt})

    with pytest.raises(ChainError) as info:
        chain.download(SOURCE_URL, tmp_path / "video.mp4", IngestOptions())

    assert str(info.value) == "yt-dlp broke"
    assert [attempt.provider for attempt in info.value.attempts] == [YTDLP, COBALT]
    assert "not installed" in info.value.fallback_error


def test_run_download_accepts_mapping_and_order(tmp_path: Path) -> None:
    ytdlp = FakeProvider(YTDLP)
    cobalt = FakeProvider(COBALT)

    result = run_download(
        {YTDLP: ytdlp, COBALT: cobalt},
        SOURCE_URL,
        tmp_path / "video.mp4",
        IngestOptions(),
        order=[COBALT],
    )

    assert result.provider == COBALT
    assert ytdlp.download_calls == []
    assert result.meta["fallback"]["used"] is False


# ---------------------------------------------------------------------------
# Inspection fallback


def test_ytdlp_inspection_success_does_not_contact_cobalt() -> None:
    ytdlp = FakeProvider(YTDLP)
    cobalt = FakeProvider(COBALT)
    chain = make_chain(ytdlp, cobalt)

    inspected = chain.inspect(SOURCE_URL, IngestOptions())

    assert inspected["provider"] == YTDLP
    assert ytdlp.inspect_calls
    assert cobalt.inspect_calls == []
    assert [attempt.provider for attempt in chain.last_attempts] == [YTDLP]


def test_inspection_failure_falls_back_to_cobalt() -> None:
    ytdlp = FakeProvider(YTDLP, fail_inspect=True, inspect_error="yt-dlp inspect broke")
    cobalt = FakeProvider(COBALT)
    chain = make_chain(ytdlp, cobalt)

    inspected = chain.inspect(SOURCE_URL, IngestOptions())

    assert inspected["provider"] == COBALT
    assert len(ytdlp.inspect_calls) == 1
    assert len(cobalt.inspect_calls) == 1
    assert [attempt.provider for attempt in chain.last_attempts] == [YTDLP, COBALT]
    assert chain.last_attempts[0].ok is False
    assert chain.last_attempts[0].error == "yt-dlp inspect broke"
    assert chain.last_attempts[0].stage == "inspect"


def test_inspection_unavailable_result_falls_back_only_with_another_provider() -> None:
    ytdlp = FakeProvider(
        YTDLP,
        inspect_result={
            "provider": YTDLP,
            "available": False,
            "warning": "yt-dlp does not support this URL.",
        },
    )
    cobalt = FakeProvider(COBALT)
    chain = make_chain(ytdlp, cobalt)

    inspected = chain.inspect(SOURCE_URL, IngestOptions())

    assert inspected["provider"] == COBALT
    assert cobalt.inspect_calls


def test_inspection_failure_without_cobalt_raises_primary_error() -> None:
    ytdlp = FakeProvider(YTDLP, fail_inspect=True, inspect_error="yt-dlp inspect broke")
    chain = make_chain(ytdlp)

    with pytest.raises(ChainError) as info:
        chain.inspect(SOURCE_URL, IngestOptions())

    assert str(info.value) == "yt-dlp inspect broke"
    assert [attempt.provider for attempt in info.value.attempts] == [YTDLP]


def test_both_inspections_fail_preserves_primary_error() -> None:
    ytdlp = FakeProvider(YTDLP, fail_inspect=True, inspect_error="yt-dlp inspect broke")
    cobalt = FakeProvider(COBALT, fail_inspect=True, inspect_error="cobalt inspect broke")
    chain = make_chain(ytdlp, cobalt)

    with pytest.raises(ChainError) as info:
        chain.inspect(SOURCE_URL, IngestOptions())

    assert str(info.value) == "yt-dlp inspect broke"
    assert info.value.fallback_error == "cobalt inspect broke"
    assert [attempt.provider for attempt in info.value.attempts] == [YTDLP, COBALT]


def test_explicit_ytdlp_inspection_does_not_fall_back() -> None:
    ytdlp = FakeProvider(YTDLP, fail_inspect=True)
    cobalt = FakeProvider(COBALT)
    chain = make_chain(
        ytdlp, cobalt, order=fallback_provider_ids("ytdlp", YTDLP, True, True)
    )

    with pytest.raises(ChainError):
        chain.inspect(SOURCE_URL, IngestOptions())

    assert cobalt.inspect_calls == []


def test_cancelled_inspection_does_not_fall_back() -> None:
    event = threading.Event()
    ytdlp = FakeProvider(
        YTDLP, cancel_on_inspect=True, cancel_event=event, fail_inspect=True
    )
    cobalt = FakeProvider(COBALT)
    chain = make_chain(ytdlp, cobalt)

    with pytest.raises(ChainError) as info:
        chain.inspect(SOURCE_URL, IngestOptions(), cancel_event=event)

    assert info.value.cancelled is True
    assert cobalt.inspect_calls == []


def test_run_inspect_returns_provider_result() -> None:
    ytdlp = FakeProvider(YTDLP, fail_inspect=True)
    cobalt = FakeProvider(COBALT)

    inspected = run_inspect({YTDLP: ytdlp, COBALT: cobalt}, SOURCE_URL, IngestOptions())

    assert inspected["provider"] == COBALT
    assert cobalt.inspect_calls


def test_attempt_serializes() -> None:
    attempt = Attempt(YTDLP, "download", False, "boom", True)

    assert attempt.as_dict() == {
        "provider": YTDLP,
        "stage": "download",
        "ok": False,
        "error": "boom",
        "cancelled": True,
    }
