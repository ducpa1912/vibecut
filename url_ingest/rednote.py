"""Clean-room RedNote / Xiaohongshu URL preparation for the yt-dlp path.

The module has one job: turn a pasted share link into a direct Xiaohongshu note
URL that yt-dlp can read, without touching the ``xhs_get`` service.

* Direct RedNote / Xiaohongshu note links are normalized locally. No network
  request is made.
* ``xhslink.com`` / ``xhslink.cn`` share links are resolved by following a
  small, bounded number of HTTP redirects. Every redirect target must stay on
  an allow-listed RedNote host, so a short link cannot bounce the resolver to
  an arbitrary or private address.

The module never reads browser cookies, cookie files, or ``xhs_get`` state.
Only :func:`cookies_may_be_needed` reports that a note has no ``xsec_token``;
the caller decides whether to use its own configured yt-dlp cookies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import (
    SplitResult,
    parse_qsl,
    urlencode,
    urljoin,
    urlsplit,
    urlunsplit,
)
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .base import IngestError
from .registry import validate_url

CANONICAL_HOST = "www.xiaohongshu.com"
NOTE_HOSTS = frozenset(
    {"rednote.com", "www.rednote.com", "xiaohongshu.com", "www.xiaohongshu.com"}
)
SHORT_HOSTS = frozenset(
    {"xhslink.com", "www.xhslink.com", "xhslink.cn", "www.xhslink.cn"}
)

DEFAULT_TIMEOUT = 10.0
DEFAULT_MAX_REDIRECTS = 5
MAX_REDIRECTS = 10

_COOKIE_WARNING = (
    "RedNote may require a signed-in cookie for this note. Add cookies in "
    "VibeCut Setup; VibeCut does not read browser cookies for RedNote."
)

_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
_SHORT_PATH = re.compile(r"(?:[A-Za-z0-9_-]{1,128}/){0,4}[A-Za-z0-9_-]{1,128}")


@dataclass(frozen=True)
class FetchHop:
    """One HTTP response in a short-link redirect chain."""

    status: int
    location: str = ""


# fetch(url, timeout) -> FetchHop, (status, location), or a redirect location.
RedirectFetcher = Callable[[str, float], FetchHop | tuple[int, str] | str]


@dataclass(frozen=True)
class PreparedRednoteUrl:
    """Result of :func:`prepare_rednote_url`.

    ``cookies_may_be_needed`` is guidance only. This module never reads or
    forwards cookies; a caller that has yt-dlp cookie settings may apply them.
    """

    url: str
    original_url: str
    was_short_link: bool
    cookies_may_be_needed: bool
    warning: str = ""

    @property
    def needs_cookies(self) -> bool:
        """Alias for :attr:`cookies_may_be_needed`."""

        return self.cookies_may_be_needed


class _NoRedirect(HTTPRedirectHandler):
    """Return 3xx responses to the resolver instead of following them."""

    def redirect_request(  # type: ignore[no-untyped-def]
        self, req, fp, code, msg, headers, newurl
    ):
        return None


def _default_fetch(url: str, timeout: float) -> FetchHop:
    """Fetch one redirect hop with urllib. No cookies are sent."""

    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; VibeCut-URLIngest/1.0)",
            "Accept": "*/*",
        },
        method="GET",
    )
    opener = build_opener(_NoRedirect())
    try:
        response = opener.open(request, timeout=timeout)
    except HTTPError as exc:
        try:
            return FetchHop(
                int(exc.code),
                str((exc.headers or {}).get("Location") or ""),
            )
        finally:
            exc.close()
    except (URLError, TimeoutError, OSError) as exc:
        raise IngestError(
            "RedNote short link could not be reached. Check the link or your "
            "connection."
        ) from exc
    try:
        status = int(getattr(response, "status", 200) or 200)
        location = str((response.headers or {}).get("Location") or "")
        return FetchHop(status, location)
    finally:
        response.close()


def _validated(url: object) -> tuple[str, SplitResult]:
    """Validate an HTTP(S) URL and return ``(cleaned, split_result)``."""

    try:
        value = validate_url(url)
    except IngestError as exc:
        raise IngestError(f"RedNote link is invalid: {exc}") from exc
    parts = urlsplit(value)
    if parts.username is not None or parts.password is not None:
        raise IngestError("RedNote links must not contain a username or password.")
    if parts.port is not None:
        raise IngestError("RedNote links must not include an explicit port.")
    return value, parts


def _host(parts: SplitResult) -> str:
    host = getattr(parts, "hostname", None) or ""
    return str(host).lower()


def _note_path(path: str) -> tuple[str, str] | None:
    parts = path.split("/")
    if parts and parts[-1] == "":
        parts.pop()
    if len(parts) == 2 and parts[0] == "" and parts[1] == "explore":
        return "/explore", ""
    if len(parts) == 3 and parts[0] == "" and parts[1] == "explore":
        return "/explore", parts[2]
    if (
        len(parts) == 3
        and parts[0] == ""
        and parts[1] == "discovery"
        and parts[2] == "item"
    ):
        return "/discovery/item", ""
    if (
        len(parts) == 4
        and parts[0] == ""
        and parts[1] == "discovery"
        and parts[2] == "item"
    ):
        return "/discovery/item", parts[3]
    return None


def _check_id(value: str) -> str:
    if not value:
        raise IngestError("RedNote link has an empty note ID.")
    if not _ID.fullmatch(value):
        raise IngestError("RedNote link has an invalid note ID.")
    return value


def _normalize_direct(url: str, extra_query: str = "", token: str = "") -> str:
    value, parts = _validated(url)
    host = _host(parts)
    if host not in NOTE_HOSTS:
        if host in SHORT_HOSTS:
            raise IngestError("Use resolve_rednote_url() for a RedNote short link.")
        raise IngestError(f"Untrusted RedNote host: {host or '(missing)'}.")
    prefix_and_id = _note_path(parts.path)
    if prefix_and_id is None:
        raise IngestError(
            "RedNote link must be /explore/<id> or /discovery/item/<id>."
        )
    prefix, note_id = prefix_and_id
    note_id = _check_id(note_id)
    query = _merge_query(parts.query, extra_query, token)
    return urlunsplit(
        ("https", CANONICAL_HOST, f"{prefix}/{note_id}", query, parts.fragment)
    )


def _merge_query(final_query: str, extra_query: str, token: str = "") -> str:
    if not extra_query and not token:
        return final_query
    final_pairs = parse_qsl(final_query, keep_blank_values=True)
    extra_pairs = parse_qsl(extra_query, keep_blank_values=True)
    has_token = any(key == "xsec_token" and value.strip() for key, value in final_pairs)
    if token and not has_token:
        final_pairs = [(key, value) for key, value in final_pairs if key != "xsec_token"]
        if not any(
            key == "xsec_token" and value.strip() for key, value in extra_pairs
        ):
            extra_pairs = [
                (key, value) for key, value in extra_pairs if key != "xsec_token"
            ]
            extra_pairs.append(("xsec_token", token))
    present = {key for key, _ in final_pairs}
    for key, value in extra_pairs:
        if key not in present:
            final_pairs.append((key, value))
    return urlencode(final_pairs)


def _token(url: str) -> str:
    query = urlsplit(url).query
    for key, value in parse_qsl(query, keep_blank_values=True):
        if key == "xsec_token" and value.strip():
            return value
    return ""


def _short_path(path: str) -> bool:
    trimmed = path.strip("/")
    return bool(trimmed) and ".." not in trimmed.split("/") and bool(
        _SHORT_PATH.fullmatch(trimmed)
    )


def normalize_rednote_url(url: str) -> str:
    """Normalize a direct note link to ``https://www.xiaohongshu.com/...``.

    ``rednote.com`` and ``xiaohongshu.com`` (with or without ``www``) are
    accepted. Query parameters, including ``xsec_token`` and ``xsec_source``,
    are preserved. This function never touches the network and raises
    :class:`IngestError` for a short link; use :func:`resolve_rednote_url`.
    """

    return _normalize_direct(url)


def cookies_may_be_needed(url: str) -> bool:
    """Return True when a note URL has no non-empty ``xsec_token``.

    This is guidance for yt-dlp cookie settings. The check reads only the URL;
    it does not read browser cookies, a cookie file, or ``xhs_get`` state.
    """

    return not bool(_token(url))


def _coerce_hop(result: object) -> FetchHop:
    if isinstance(result, FetchHop):
        try:
            status = int(result.status)
        except (TypeError, ValueError) as exc:
            raise IngestError("RedNote short link fetcher returned a bad status.") from exc
        return FetchHop(status, str(result.location or ""))
    if isinstance(result, str):
        return FetchHop(302, result)
    if isinstance(result, tuple) and len(result) == 2:
        try:
            status = int(result[0])
        except (TypeError, ValueError) as exc:
            raise IngestError("RedNote short link fetcher returned a bad status.") from exc
        return FetchHop(status, str(result[1] or ""))
    raise IngestError("RedNote short link fetcher returned an invalid result.")


def _resolve_short(
    url: str,
    *,
    timeout: float,
    max_redirects: int,
    fetch: RedirectFetcher | None,
) -> tuple[str, str]:
    """Return ``(normalized_url, original_short_query)``."""

    if not isinstance(max_redirects, int) or isinstance(max_redirects, bool):
        raise IngestError("RedNote redirect limit must be a whole number.")
    if not 0 <= max_redirects <= MAX_REDIRECTS:
        raise IngestError(f"RedNote redirect limit must be 0 to {MAX_REDIRECTS}.")
    try:
        timeout = float(timeout)
    except (TypeError, ValueError) as exc:
        raise IngestError("RedNote short-link timeout is invalid.") from exc
    if not 0 < timeout <= 60:
        raise IngestError("RedNote short-link timeout must be between 0 and 60 seconds.")
    if fetch is None:
        fetch = _default_fetch
    if not callable(fetch):
        raise IngestError("RedNote short-link fetcher must be callable.")

    current, current_parts = _validated(url)
    original_query = current_parts.query
    carried_token = _token(current)
    seen = {current}
    redirects = 0

    while True:
        host = _host(current_parts)
        if host in NOTE_HOSTS:
            return _normalize_direct(current, original_query, carried_token), original_query
        if host not in SHORT_HOSTS:
            raise IngestError(f"Untrusted RedNote host: {host or '(missing)'}.")
        if not _short_path(current_parts.path):
            raise IngestError("RedNote short link has an invalid path.")
        if redirects >= max_redirects:
            raise IngestError(
                f"RedNote short link exceeded {max_redirects} redirects."
            )

        try:
            hop = _coerce_hop(fetch(current, timeout))
        except IngestError:
            raise
        except (URLError, TimeoutError, OSError) as exc:
            raise IngestError(
                "RedNote short link could not be reached. Check the link or your "
                "connection."
            ) from exc
        except Exception as exc:  # noqa: BLE001 - fetcher is caller supplied
            raise IngestError(
                "RedNote short link could not be resolved because the fetcher failed."
            ) from exc

        if not 300 <= hop.status < 400:
            if 200 <= hop.status < 300:
                raise IngestError("RedNote short link did not redirect to a note.")
            raise IngestError(
                f"RedNote short link service returned HTTP {hop.status}."
            )
        if not hop.location:
            raise IngestError("RedNote short link redirect had no target.")

        target = urljoin(current, hop.location)
        current, current_parts = _validated(target)
        target_host = _host(current_parts)
        if target_host not in NOTE_HOSTS and target_host not in SHORT_HOSTS:
            raise IngestError(f"Untrusted RedNote redirect host: {target_host or '(missing)'}.")
        redirects += 1
        hop_token = _token(current)
        if hop_token:
            carried_token = hop_token
        if current in seen:
            raise IngestError("RedNote short link redirected in a loop.")
        seen.add(current)


def resolve_rednote_url(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    fetch: RedirectFetcher | None = None,
) -> str:
    """Return a direct Xiaohongshu note URL for *url*.

    Direct RedNote/Xiaohongshu links are normalized with no network. Short
    links use *fetch* (default urllib) and follow at most *max_redirects*
    redirects. Each redirect target must remain on ``xhslink`` or a direct
    RedNote host.
    """

    if not isinstance(url, str):
        raise IngestError("RedNote link must be text.")
    value, parts = _validated(url)
    host = _host(parts)
    if host in SHORT_HOSTS:
        normalized, _ = _resolve_short(
            value, timeout=timeout, max_redirects=max_redirects, fetch=fetch
        )
        return normalized
    return _normalize_direct(value)


def prepare_rednote_url(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    fetch: RedirectFetcher | None = None,
) -> PreparedRednoteUrl:
    """Resolve *url* and return the URL plus cookie guidance.

    The result is suitable for logging and display: it has no cookies and no
    response bodies. The caller remains responsible for any yt-dlp cookie
    configuration.
    """

    if not isinstance(url, str):
        raise IngestError("RedNote link must be text.")
    value, parts = _validated(url)
    host = _host(parts)
    if host in SHORT_HOSTS:
        normalized, _ = _resolve_short(
            value, timeout=timeout, max_redirects=max_redirects, fetch=fetch
        )
    else:
        normalized = _normalize_direct(value)
    needs_cookies = not bool(_token(normalized))
    return PreparedRednoteUrl(
        url=normalized,
        original_url=value,
        was_short_link=host in SHORT_HOSTS,
        cookies_may_be_needed=needs_cookies,
        warning=_COOKIE_WARNING if needs_cookies else "",
    )


def prepare_for_ytdlp(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    fetch: RedirectFetcher | None = None,
) -> str:
    """Return a URL ready for ``YoutubeDL.extract_info()``.

    Direct note links make no network request. Short links are resolved with
    the same bounds as :func:`resolve_rednote_url`. Call
    :func:`prepare_rednote_url` instead when the cookie warning is needed.
    """

    return prepare_rednote_url(
        url, timeout=timeout, max_redirects=max_redirects, fetch=fetch
    ).url


__all__ = [
    "CANONICAL_HOST",
    "DEFAULT_MAX_REDIRECTS",
    "DEFAULT_TIMEOUT",
    "MAX_REDIRECTS",
    "NOTE_HOSTS",
    "SHORT_HOSTS",
    "FetchHop",
    "PreparedRednoteUrl",
    "RedirectFetcher",
    "cookies_may_be_needed",
    "normalize_rednote_url",
    "prepare_for_ytdlp",
    "prepare_rednote_url",
    "resolve_rednote_url",
]
