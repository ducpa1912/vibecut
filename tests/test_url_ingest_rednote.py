"""Unit tests for clean-room RedNote URL preparation.

Every network path is driven by an injected fetch function. These tests never
open a socket.
"""

from __future__ import annotations

from urllib.request import Request

import pytest

from url_ingest import rednote
from url_ingest.base import IngestError
from url_ingest.rednote import (
    CANONICAL_HOST,
    FetchHop,
    PreparedRednoteUrl,
    cookies_may_be_needed,
    normalize_rednote_url,
    prepare_for_ytdlp,
    prepare_rednote_url,
    resolve_rednote_url,
)

NOTE_ID = "0123456789abcdef"
DIRECT_URL = f"https://www.xiaohongshu.com/explore/{NOTE_ID}"


class _Fetcher:
    def __init__(self, *hops: FetchHop | tuple[int, str] | str) -> None:
        self.hops = list(hops)
        self.calls: list[tuple[str, float]] = []

    def __call__(self, url: str, timeout: float):
        self.calls.append((url, timeout))
        if not self.hops:
            raise AssertionError(f"unexpected fetch: {url}")
        return self.hops.pop(0)


# ---------------------------------------------------------------------------
# Direct mappings and query preservation


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "https://rednote.com/explore/abc123",
            "https://www.xiaohongshu.com/explore/abc123",
        ),
        (
            "https://www.rednote.com/explore/abc123",
            "https://www.xiaohongshu.com/explore/abc123",
        ),
        (
            "https://rednote.com/discovery/item/abc123",
            "https://www.xiaohongshu.com/discovery/item/abc123",
        ),
        (
            "https://www.rednote.com/discovery/item/abc123",
            "https://www.xiaohongshu.com/discovery/item/abc123",
        ),
        (
            "https://xiaohongshu.com/explore/abc123",
            "https://www.xiaohongshu.com/explore/abc123",
        ),
        (
            "https://www.xiaohongshu.com/explore/abc123/",
            "https://www.xiaohongshu.com/explore/abc123",
        ),
        (
            "http://rednote.com/explore/abc123",
            "https://www.xiaohongshu.com/explore/abc123",
        ),
        (
            "HTTPS://WWW.REDNOTE.COM/explore/AbC_123",
            "https://www.xiaohongshu.com/explore/AbC_123",
        ),
    ],
)
def test_direct_links_map_to_canonical_xiaohongshu(source: str, expected: str) -> None:
    assert normalize_rednote_url(source) == expected
    assert resolve_rednote_url(source) == expected


def test_query_parameters_are_preserved_verbatim() -> None:
    source = (
        "https://rednote.com/explore/abc123"
        "?xsec_token=TOKEN%2Bvalue%3D&xsec_source=pc_share&note=1&empty="
    )
    expected = (
        "https://www.xiaohongshu.com/explore/abc123"
        "?xsec_token=TOKEN%2Bvalue%3D&xsec_source=pc_share&note=1&empty="
    )
    assert normalize_rednote_url(source) == expected


def test_duplicate_query_keys_are_preserved() -> None:
    source = "https://rednote.com/discovery/item/abc123?tag=a&tag=b&xsec_token=t"
    expected = (
        "https://www.xiaohongshu.com/discovery/item/abc123"
        "?tag=a&tag=b&xsec_token=t"
    )
    assert normalize_rednote_url(source) == expected


def test_direct_normalization_does_not_fetch() -> None:
    def fail(url: str, timeout: float) -> FetchHop:
        raise AssertionError("direct links must not use the network")

    assert prepare_for_ytdlp(DIRECT_URL, fetch=fail) == DIRECT_URL
    prepared = prepare_rednote_url(DIRECT_URL, fetch=fail)
    assert prepared.url == DIRECT_URL
    assert prepared.was_short_link is False
    assert resolve_rednote_url(DIRECT_URL, fetch=fail) == DIRECT_URL


def test_normalize_rednote_url_rejects_short_links_without_network() -> None:
    with pytest.raises(IngestError, match="resolve_rednote_url"):
        normalize_rednote_url("https://xhslink.com/a/AbCdEf")


# ---------------------------------------------------------------------------
# Rejected URLs


@pytest.mark.parametrize(
    "url",
    [
        "ftp://rednote.com/explore/abc123",
        "file:///tmp/note.html",
        "javascript:alert(1)",
        "data:text/html,hello",
        "mailto:user@example.com",
        "//rednote.com/explore/abc123",
        "rednote.com/explore/abc123",
        "https://",
    ],
)
def test_non_http_urls_are_rejected(url: str) -> None:
    with pytest.raises(IngestError):
        normalize_rednote_url(url)
    with pytest.raises(IngestError):
        resolve_rednote_url(url, fetch=_Fetcher())


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "https://rednote.com/explore/",
        "https://rednote.com/explore",
        "https://rednote.com/discovery/item/",
        "https://rednote.com/explore/../other",
        "https://rednote.com/explore/abc/def",
        "https://rednote.com/explore/abc.def",
        "https://rednote.com/explore/abc%2Fdef",
        "https://rednote.com/explore/abc def",
        "https://rednote.com/explore/" + "a" * 129,
        "https://rednote.com/user/profile/abc123",
        "https://rednote.com/",
    ],
)
def test_malformed_notes_are_rejected(url: str) -> None:
    with pytest.raises(IngestError):
        normalize_rednote_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://notrednote.com/explore/abc123",
        "https://rednote.com.evil.example/explore/abc123",
        "https://evilxiaohongshu.com/explore/abc123",
        "https://xiaohongshu.com.evil.example/explore/abc123",
        "https://rednote.com@evil.example/explore/abc123",
        "https://evil.example@rednote.com/explore/abc123",
        "https://share.xhslink.com/a/AbCdEf",
        "https://xhslink.com.evil.example/a/AbCdEf",
        "https://rednote.com:443/explore/abc123",
        "https://www.rednote.com./explore/abc123",
    ],
)
def test_untrusted_lookalike_hosts_are_rejected(url: str) -> None:
    with pytest.raises(IngestError):
        resolve_rednote_url(url, fetch=_Fetcher())


def test_non_string_url_is_rejected() -> None:
    with pytest.raises(IngestError, match="must be text"):
        normalize_rednote_url(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Short links


def test_short_link_redirects_to_direct_note() -> None:
    fetcher = _Fetcher(
        FetchHop(302, f"https://www.xiaohongshu.com/explore/{NOTE_ID}")
    )
    result = resolve_rednote_url(
        "https://xhslink.com/a/AbCdEf", timeout=3.5, fetch=fetcher
    )
    assert result == DIRECT_URL
    assert fetcher.calls == [("https://xhslink.com/a/AbCdEf", 3.5)]


def test_short_link_supports_relative_redirect_and_multiple_hops() -> None:
    fetcher = _Fetcher(
        (302, "/a/NextHop"),
        "https://xhslink.cn/a/FinalHop",
        (301, f"https://rednote.com/explore/{NOTE_ID}"),
    )
    result = resolve_rednote_url("https://xhslink.com/a/AbCdEf", fetch=fetcher)
    assert result == DIRECT_URL
    assert [call[0] for call in fetcher.calls] == [
        "https://xhslink.com/a/AbCdEf",
        "https://xhslink.com/a/NextHop",
        "https://xhslink.cn/a/FinalHop",
    ]


def test_short_link_token_and_source_are_carried_to_final_url() -> None:
    fetcher = _Fetcher(
        FetchHop(
            302,
            f"https://www.xiaohongshu.com/explore/{NOTE_ID}?source=share",
        )
    )
    result = resolve_rednote_url(
        "https://xhslink.com/a/AbCdEf?xsec_token=SHORT_TOKEN&xsec_source=pc_share",
        fetch=fetcher,
    )
    assert result == (
        f"{DIRECT_URL}?source=share&xsec_token=SHORT_TOKEN&xsec_source=pc_share"
    )
    assert cookies_may_be_needed(result) is False


def test_final_url_token_is_preserved() -> None:
    final = (
        f"https://www.xiaohongshu.com/explore/{NOTE_ID}"
        "?xsec_token=FINAL_TOKEN&xsec_source=pc_feed"
    )
    result = resolve_rednote_url(
        "https://xhslink.com/a/AbCdEf", fetch=_Fetcher(FetchHop(302, final))
    )
    assert result == final
    assert cookies_may_be_needed(result) is False


def test_final_url_token_wins_over_short_url_token() -> None:
    final = f"https://www.xiaohongshu.com/explore/{NOTE_ID}?xsec_token=FINAL"
    result = resolve_rednote_url(
        "https://xhslink.com/a/AbCdEf?xsec_token=SHORT", fetch=_Fetcher((302, final))
    )
    assert result == final


def test_token_on_intermediate_hop_is_carried() -> None:
    fetcher = _Fetcher(
        FetchHop(302, "https://xhslink.com/a/Next?xsec_token=HOP_TOKEN"),
        FetchHop(302, f"https://www.xiaohongshu.com/explore/{NOTE_ID}"),
    )
    result = resolve_rednote_url("https://xhslink.com/a/AbCdEf", fetch=fetcher)
    assert result == f"{DIRECT_URL}?xsec_token=HOP_TOKEN"


def test_short_link_without_token_is_allowed() -> None:
    fetcher = _Fetcher(FetchHop(302, f"https://rednote.com/explore/{NOTE_ID}"))
    prepared = prepare_rednote_url("https://xhslink.com/a/AbCdEf", fetch=fetcher)
    assert isinstance(prepared, PreparedRednoteUrl)
    assert prepared.url == DIRECT_URL
    assert prepared.was_short_link is True
    assert prepared.cookies_may_be_needed is True
    assert prepared.needs_cookies is True
    assert "cookie" in prepared.warning.lower()


@pytest.mark.parametrize(
    ("hop", "message"),
    [
        (FetchHop(200), "did not redirect"),
        (FetchHop(404), "HTTP 404"),
        (FetchHop(302, ""), "no target"),
    ],
)
def test_short_link_bad_response_is_clear(hop: FetchHop, message: str) -> None:
    with pytest.raises(IngestError, match=message):
        resolve_rednote_url(
            "https://xhslink.com/a/AbCdEf", fetch=_Fetcher(hop)
        )


def test_short_link_redirect_loop_is_rejected() -> None:
    fetcher = _Fetcher(
        FetchHop(302, "https://xhslink.com/a/Second"),
        FetchHop(302, "https://xhslink.com/a/AbCdEf"),
    )
    with pytest.raises(IngestError, match="loop"):
        resolve_rednote_url("https://xhslink.com/a/AbCdEf", fetch=fetcher)
    assert len(fetcher.calls) == 2


def test_short_link_too_many_hops_is_rejected() -> None:
    fetcher = _Fetcher(
        FetchHop(302, "https://xhslink.com/a/Second"),
        FetchHop(302, "https://xhslink.com/a/Third"),
    )
    with pytest.raises(IngestError, match="exceeded 1 redirects"):
        resolve_rednote_url(
            "https://xhslink.com/a/AbCdEf", max_redirects=1, fetch=fetcher
        )
    assert len(fetcher.calls) == 1


def test_short_link_zero_redirect_budget_is_rejected() -> None:
    fetcher = _Fetcher(FetchHop(302, DIRECT_URL))
    with pytest.raises(IngestError, match="exceeded 0 redirects"):
        resolve_rednote_url(
            "https://xhslink.com/a/AbCdEf", max_redirects=0, fetch=fetcher
        )
    assert fetcher.calls == []


@pytest.mark.parametrize(
    "target",
    [
        "https://evil.example/explore/abc123",
        "https://xiaohongshu.com.evil.example/explore/abc123",
        "http://127.0.0.1/explore/abc123",
        "file:///etc/passwd",
    ],
)
def test_short_link_untrusted_redirect_is_rejected_without_fetching_it(
    target: str,
) -> None:
    fetcher = _Fetcher(FetchHop(302, target))
    with pytest.raises(IngestError):
        resolve_rednote_url("https://xhslink.com/a/AbCdEf", fetch=fetcher)
    assert len(fetcher.calls) == 1


@pytest.mark.parametrize("error", [TimeoutError("timed out"), OSError("offline")])
def test_short_link_transport_errors_are_wrapped(error: BaseException) -> None:
    def fetch(url: str, timeout: float) -> FetchHop:
        raise error

    with pytest.raises(IngestError, match="could not be reached"):
        resolve_rednote_url("https://xhslink.com/a/AbCdEf", fetch=fetch)


def test_short_link_unexpected_fetcher_error_is_wrapped() -> None:
    def fetch(url: str, timeout: float) -> FetchHop:
        raise RuntimeError("boom")

    with pytest.raises(IngestError, match="fetcher failed"):
        resolve_rednote_url("https://xhslink.com/a/AbCdEf", fetch=fetch)


def test_short_link_fetcher_invalid_result_is_rejected() -> None:
    def fetch(url: str, timeout: float) -> object:
        return 42

    with pytest.raises(IngestError, match="invalid result"):
        resolve_rednote_url("https://xhslink.com/a/AbCdEf", fetch=fetch)


def test_short_link_bad_path_is_rejected_without_fetching() -> None:
    fetcher = _Fetcher()
    with pytest.raises(IngestError, match="invalid path"):
        resolve_rednote_url("https://xhslink.com/", fetch=fetcher)
    assert fetcher.calls == []


@pytest.mark.parametrize("timeout", [0, -1, 61, "soon", None])
def test_short_link_bad_timeout_is_rejected(timeout: object) -> None:
    with pytest.raises(IngestError, match="timeout"):
        resolve_rednote_url(
            "https://xhslink.com/a/AbCdEf",
            timeout=timeout,  # type: ignore[arg-type]
            fetch=_Fetcher(),
        )


@pytest.mark.parametrize("limit", [-1, 11, 1.5, True, "5"])
def test_short_link_bad_redirect_limit_is_rejected(limit: object) -> None:
    with pytest.raises(IngestError, match="redirect limit"):
        resolve_rednote_url(
            "https://xhslink.com/a/AbCdEf",
            max_redirects=limit,  # type: ignore[arg-type]
            fetch=_Fetcher(),
        )


# ---------------------------------------------------------------------------
# Cookie guidance


def test_tokenless_link_reports_cookie_guidance() -> None:
    assert cookies_may_be_needed(DIRECT_URL) is True
    prepared = prepare_rednote_url(DIRECT_URL)
    assert prepared.cookies_may_be_needed is True
    assert "does not read browser cookies" in prepared.warning


def test_tokenized_link_does_not_report_cookie_guidance() -> None:
    url = f"{DIRECT_URL}?xsec_token=TOKEN&xsec_source=pc_share"
    assert cookies_may_be_needed(url) is False
    prepared = prepare_rednote_url(url)
    assert prepared.cookies_may_be_needed is False
    assert prepared.warning == ""


def test_blank_token_does_not_count_as_token() -> None:
    url = f"{DIRECT_URL}?xsec_token=&xsec_source=pc_share"
    assert cookies_may_be_needed(url) is True


# ---------------------------------------------------------------------------
# Default urllib fetcher


class _FakeResponse:
    status = 302

    def __init__(self) -> None:
        self.headers = {"Location": "https://www.xiaohongshu.com/explore/abc"}
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_default_fetch_does_not_send_cookies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _FakeResponse()
    captured: dict[str, object] = {}

    class _Opener:
        def open(self, request: Request, timeout: float | None = None) -> _FakeResponse:
            captured["request"] = request
            captured["timeout"] = timeout
            return response

    monkeypatch.setattr(rednote, "build_opener", lambda handler: _Opener())
    hop = rednote._default_fetch("https://xhslink.com/a/AbCdEf", 4.0)

    assert hop == FetchHop(302, "https://www.xiaohongshu.com/explore/abc")
    assert response.closed is True
    request = captured["request"]
    assert isinstance(request, Request)
    assert request.get_method() == "GET"
    assert request.get_header("Cookie") is None
    assert not any(name.lower() == "cookie" for name in request.headers)
    assert captured["timeout"] == 4.0


def test_default_fetch_wraps_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Opener:
        def open(self, request: Request, timeout: float | None = None) -> object:
            raise TimeoutError("slow")

    monkeypatch.setattr(rednote, "build_opener", lambda handler: _Opener())
    with pytest.raises(IngestError, match="could not be reached"):
        rednote._default_fetch("https://xhslink.com/a/AbCdEf", 1.0)


def test_canonical_host_constant_matches_expected_output() -> None:
    assert CANONICAL_HOST == "www.xiaohongshu.com"
