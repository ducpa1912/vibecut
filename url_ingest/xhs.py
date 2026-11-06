"""RedNote / Xiaohongshu ingest through a self-hosted ``xhs_get`` web API.

VibeCut never imports ``xhs_get`` and never reads its cookie file. The provider
speaks HTTP only, so the sidecar can run in another process, container, or on
another machine that shares a filesystem with VibeCut.

Settings used here (all optional except ``xhs_url``):

``xhs_url``
    Base URL of the xhs_get web UI, for example ``http://127.0.0.1:5789``.
``xhs_token`` / ``xhs_api_key``
    Access token for xhs_get friends mode. Sent as ``Authorization: Bearer``.
``xhs_no_record``
    Ask xhs_get for a fresh download instead of reusing its recorded history.
``xhs_interval``
    Delay in seconds between notes. A single note normally ignores it, but the
    API requires the field.
"""

from __future__ import annotations

import ipaddress
import json
import math
import os
import re
import socket
import tempfile
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlsplit
import urllib.request
from urllib.request import Request

from .base import (
    IngestError,
    IngestOptions,
    IngestResult,
    ProgressCallback,
    Provider,
)
from .registry import safe_filename, validate_url

# Hosts handled by xhs_get. Keep in sync with xhs_get's link extractor.
_XHS_HOSTS = (
    "rednote.com",
    "xiaohongshu.com",
    "xhslink.com",
    "xhslink.cn",
)
_SHORT_LINK_HOSTS = ("xhslink.com", "xhslink.cn")

_TOKEN_KEYS = ("xhs_token", "xhs_api_key", "xhs_access_token", "xhs_get_token")

_VIDEO_SUFFIXES = frozenset(
    {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".flv", ".avi", ".wmv", ".ts"}
)
_IMAGE_SUFFIXES = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".heic", ".avif", ".gif", ".bmp"}
)

_DONE_STATES = frozenset({"done", "completed", "complete", "success", "finished"})
_FAILED_STATES = frozenset({"failed", "error"})
_CANCELLED_STATES = frozenset({"cancelled", "canceled", "aborted"})
_FILE_DONE_STATES = frozenset({"completed", "complete", "done", "success", "finished"})
_FILE_FAILED_STATES = frozenset({"failed", "error", "cancelled", "canceled"})

_MAX_RESPONSE_BYTES = 8 * 1024 * 1024
_FILE_LIST_LIMIT = 200

_TOKEN_WARNING = (
    "This RedNote link has no xsec_token. Open the note in the RedNote app, "
    "use Share > Copy link, and paste the full share link."
)
_TOKEN_ERROR = (
    "RedNote needs a fresh xsec_token for this note. Open the note in the "
    "RedNote app, use Share > Copy link, and paste the full share link."
)
_NO_COOKIE = (
    "XHS has no signed-in cookie. Open xhs-get, sign in with the QR code, "
    "then retry."
)
_EXPIRED_SESSION = "XHS session looks expired. Open xhs-get, sign in again, then retry."
_CANCELLED = "XHS download was canceled."
_IMAGE_ONLY = (
    "XHS downloaded images only; this note has no video. Paste a RedNote "
    "video note link."
)
_SKIPPED = (
    "XHS skipped this note (already downloaded or it has no video). Enable "
    "fresh download (no_record) in Setup or use another note."
)


MAX_DOWNLOAD_BYTES = int(
    float(os.environ.get("VIBECUT_URL_MAX_GB", "2") or 2) * 1024 ** 3
)


def _private_host(host: str) -> bool:
    host = (host or "").lower().rstrip(".")
    if host in {"", "localhost", "localhost.localdomain"}:
        return True
    try:
        address = ipaddress.ip_address(host)
        return bool(
            address.is_private or address.is_loopback or address.is_link_local
            or address.is_reserved or address.is_multicast or address.is_unspecified
        )
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        try:
            address = ipaddress.ip_address(info[4][0])
        except (ValueError, IndexError, TypeError):
            continue
        if (
            address.is_private or address.is_loopback or address.is_link_local
            or address.is_reserved or address.is_multicast or address.is_unspecified
        ):
            return True
    return False


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        from urllib.parse import urljoin, urlsplit
        target = urljoin(req.full_url, newurl)
        old_host = (urlsplit(req.full_url).hostname or "").lower()
        new_host = (urlsplit(target).hostname or "").lower()
        if new_host != old_host and _private_host(new_host):
            raise IngestError("XHS redirect target is a private network address.")
        forwarded = dict(req.headers or {})
        for name in list(forwarded):
            if name.lower() in {"authorization", "cookie", "xhs-token"}:
                forwarded.pop(name, None)
        return urllib.request.Request(target, headers=forwarded, method="GET")


def urlopen(request, timeout=None):
    opener = urllib.request.build_opener(_SafeRedirectHandler())
    return opener.open(request, timeout=timeout)


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _as_float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
    return None


def _short(text: Any, limit: int = 400) -> str:
    value = " ".join(str(text or "").split())
    return value[:limit]


def _host_matches(host: str, domains: tuple[str, ...]) -> bool:
    host = (host or "").lower().rstrip(".")
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def _is_xhs_host(host: str) -> bool:
    return _host_matches(host, _XHS_HOSTS)


def _is_short_host(host: str) -> bool:
    return _host_matches(host, _SHORT_LINK_HOSTS)


def _has_xsec_token(url: str) -> bool:
    try:
        query = urlsplit(url).query
    except ValueError:
        return False
    values = parse_qs(query, keep_blank_values=True).get("xsec_token") or []
    return any(str(value).strip() for value in values)


def _is_video_name(name: Any) -> bool:
    return Path(str(name or "")).suffix.lower() in _VIDEO_SUFFIXES


def _is_image_name(name: Any) -> bool:
    return Path(str(name or "")).suffix.lower() in _IMAGE_SUFFIXES


def _size_text(value: int) -> str:
    number = max(0, int(value))
    if number < 1024:
        return f"{number} B"
    for unit in ("KB", "MB", "GB"):
        number /= 1024.0
        if number < 1024 or unit == "GB":
            return f"{number:.1f} {unit}"
    return f"{number:.1f} GB"


class XhsGetProvider(Provider):
    """Single-note RedNote download through the xhs_get job API."""

    id: ClassVar[str] = "xhs"
    label: ClassVar[str] = "XHS / RedNote"
    required_settings: ClassVar[tuple[str, ...]] = ("xhs_url",)

    poll_interval: float = 1.0
    job_timeout: float = 1800.0
    request_timeout: float = 10.0
    status_timeout: float = 5.0
    create_timeout: float = 30.0
    files_timeout: float = 15.0

    # ------------------------------------------------------------------
    # Settings and HTTP plumbing

    @staticmethod
    def _flatten_settings(settings: Mapping[str, Any] | None) -> dict[str, Any]:
        data: dict[str, Any] = dict(settings or {})
        nested = data.pop("ingest", None)
        if isinstance(nested, Mapping):
            data.update(nested)
        return data

    def _effective_settings(
        self, settings: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        # Settings passed to status() win over what the provider was built with.
        merged = self._flatten_settings(self.settings)
        merged.update(self._flatten_settings(settings))
        return merged

    def _base_url(self, settings: Mapping[str, Any]) -> str:
        raw = settings.get("xhs_url")
        value = "" if raw is None else str(raw).strip()
        if not value:
            raise IngestError("XHS service URL is not set. Set it in Setup first.")
        try:
            value = validate_url(value)
        except IngestError as exc:
            raise IngestError(f"XHS service URL is invalid: {exc}") from exc
        parts = urlsplit(value)
        if parts.query or parts.fragment:
            raise IngestError("XHS service URL must not include a query or fragment.")
        return value.rstrip("/")

    @staticmethod
    def _token(settings: Mapping[str, Any]) -> str:
        for key in _TOKEN_KEYS:
            value = settings.get(key)
            if not isinstance(value, str):
                continue
            token = value.strip()
            if not token:
                continue
            if "\r" in token or "\n" in token:
                raise IngestError("XHS access token contains invalid characters.")
            return token
        return ""

    @staticmethod
    def _api_url(base: str, path: str) -> str:
        return base + (path if path.startswith("/") else "/" + path)

    @staticmethod
    def _error_detail(exc: HTTPError) -> str:
        try:
            raw = exc.read(65536)
        except Exception:
            raw = b""
        text = raw.decode("utf-8", "replace") if raw else ""
        if text:
            try:
                payload = json.loads(text)
            except (TypeError, ValueError):
                payload = None
            if isinstance(payload, Mapping):
                for key in ("detail", "message", "error"):
                    value = payload.get(key)
                    if value:
                        text = str(value)
                        break
        if not text:
            text = str(getattr(exc, "reason", "") or exc)
        text = re.sub(r"<[^>]+>", " ", text)
        return _short(text, 320)

    def _http_error_message(self, code: int, path: str, detail: str, base: str) -> str:
        lower = detail.lower()
        if code in {401, 403}:
            return (
                "XHS access token is missing or invalid. Copy the access token "
                "from xhs-get into the XHS token setting in VibeCut."
            )
        if code == 404:
            if path.startswith("/api/jobs/"):
                return (
                    "XHS job was not found. The xhs-get service may have "
                    "restarted; try the link again."
                )
            return (
                f"XHS API was not found at {base}. Check that the URL is the "
                "xhs-get web address, for example http://127.0.0.1:5789."
            )
        if code == 429:
            return (
                "XHS is rate limiting this service. Wait a minute, then try "
                "the link again."
            )
        if code == 400 and any(
            word in lower
            for word in ("cookie", "sign in", "login", "qr code", "登录", "扫码")
        ):
            return _NO_COOKIE
        if code == 400:
            return (
                f"XHS rejected the request: {detail}"
                if detail
                else "XHS rejected the request. Check the URL and Setup values."
            )
        if code == 405:
            return "XHS API does not support this request. Update xhs-get."
        if code >= 500:
            return f"XHS service error (HTTP {code}). Check the xhs-get log." + (
                f" {detail}" if detail else ""
            )
        return f"XHS request failed (HTTP {code})." + (f" {detail}" if detail else "")

    def _unreachable(self, base: str, exc: BaseException) -> IngestError:
        reason = _short(getattr(exc, "reason", exc) or exc, 200)
        return IngestError(
            f"XHS service is not reachable at {base}"
            + (f": {reason}" if reason else "")
            + ". Start xhs-get web and check the URL in Setup."
        )

    def _request_json(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
        *,
        settings: Mapping[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        merged = self._effective_settings(settings)
        base = self._base_url(merged)
        url = self._api_url(base, path)
        data = None
        headers = {
            "Accept": "application/json",
            "User-Agent": "VibeCut/xhs-ingest",
        }
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        token = self._token(merged)
        if token:
            headers["Authorization"] = f"Bearer {token}"

        request = Request(url, data=data, headers=headers, method=method.upper())
        try:
            response = urlopen(
                request,
                timeout=timeout if timeout is not None else self.request_timeout,
            )
            try:
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
            finally:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
        except HTTPError as exc:
            detail = self._error_detail(exc)
            raise IngestError(
                self._http_error_message(exc.code, path, detail, base)
            ) from exc
        except (TimeoutError, URLError) as exc:
            raise self._unreachable(base, exc) from exc
        except OSError as exc:
            raise self._unreachable(base, exc) from exc

        if len(raw) > _MAX_RESPONSE_BYTES:
            raise IngestError("XHS service returned an unexpectedly large response.")
        if not raw.strip():
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise IngestError(
                "XHS service returned an invalid response. Check that the URL "
                "points to xhs-get."
            ) from exc

    # ------------------------------------------------------------------
    # State and status

    def _fetch_state(self, settings: Mapping[str, Any]) -> dict[str, Any]:
        payload = self._request_json(
            "GET", "/api/state", settings=settings, timeout=self.status_timeout
        )
        if not isinstance(payload, Mapping):
            raise IngestError("XHS service returned an invalid state response.")
        return dict(payload)

    def _session_info(self, state: Mapping[str, Any], base: str) -> dict[str, Any]:
        me = state.get("me") if isinstance(state.get("me"), Mapping) else {}
        cookie = state.get("cookie") if isinstance(state.get("cookie"), Mapping) else {}
        cookie_set = bool(me.get("cookie_set", state.get("cookie_set"))) or bool(
            cookie.get("set")
        )
        session_raw = me.get("session_ok")
        if session_raw is None:
            session_raw = state.get("session_ok")
        if session_raw is None:
            session_raw = cookie.get("session_ok")
        session_ok = _optional_bool(session_raw)
        auth_required = me.get("auth_required", state.get("auth_required", False))
        return {
            "cookie_set": cookie_set,
            "session_ok": session_ok,
            "auth_required": bool(auth_required),
            "user": str(me.get("name") or state.get("user") or ""),
            "login_site": str(me.get("login_site") or state.get("login_site") or ""),
            "cookie_hint": str(
                me.get("cookie_hint")
                or cookie.get("hint")
                or state.get("cookie_hint")
                or ""
            ),
            "service_url": base,
        }

    @staticmethod
    def _session_error(session: Mapping[str, Any]) -> str:
        if not session.get("cookie_set"):
            return _NO_COOKIE
        if session.get("session_ok") is False:
            return _EXPIRED_SESSION
        return ""

    def status(self, settings: Mapping[str, Any] | None = None) -> dict[str, Any]:
        merged = self._effective_settings(settings)
        entry: dict[str, Any] = {
            "id": self.id,
            "label": self.label,
            "configured": False,
            "available": False,
            "error": "",
            "cookie_set": False,
            "session_ok": None,
            "auth_required": False,
            "user": "",
            "login_site": "",
            "cookie_hint": "",
            "service_url": "",
            "session": {},
        }

        if not str(merged.get("xhs_url") or "").strip():
            entry["error"] = "XHS service URL is not set. Set it in Setup first."
            return entry
        try:
            base = self._base_url(merged)
        except IngestError as exc:
            entry["error"] = str(exc)
            return entry

        entry["configured"] = True
        entry["service_url"] = base
        try:
            state = self._fetch_state(merged)
        except IngestError as exc:
            entry["error"] = str(exc)
            token_problem = any(
                word in str(exc).lower()
                for word in ("token", "401", "unauthorized", "access")
            )
            entry["auth_required"] = token_problem
            entry["session"] = {
                "cookie_set": False,
                "session_ok": None,
                "auth_required": token_problem,
                "service_url": base,
            }
            return entry
        except Exception as exc:  # pragma: no cover - defensive boundary
            entry["error"] = f"XHS status check failed: {_short(exc)}"
            return entry

        session = self._session_info(state, base)
        error = self._session_error(session)
        entry.update(
            {
                "available": not error,
                "error": error,
                "cookie_set": session["cookie_set"],
                "session_ok": session["session_ok"],
                "auth_required": session["auth_required"],
                "user": session["user"],
                "login_site": session["login_site"],
                "cookie_hint": session["cookie_hint"],
                "service_url": base,
                "session": session,
            }
        )
        return entry

    def set_cookie(self, cookie: str, settings: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Forward a one-shot RedNote cookie to xhs_get; VibeCut does not store it."""
        value = str(cookie or "").strip()
        if not value:
            raise IngestError("RedNote cookie is empty.")
        payload = self._request_json(
            "POST", "/api/cookie", {"cookie": value}, settings=settings,
        )
        return dict(payload) if isinstance(payload, Mapping) else {"ok": True}

    # ------------------------------------------------------------------
    # Inspect

    def _require_xhs_url(self, url: str) -> str:
        value = validate_url(url)
        host = urlsplit(value).hostname or ""
        if not _is_xhs_host(host):
            raise IngestError(
                f"Not a RedNote/Xiaohongshu link: {host or value}. "
                "Use xhslink.com, xiaohongshu.com, or rednote.com."
            )
        return value

    def _default_options(self) -> IngestOptions:
        merged = self._effective_settings()
        return IngestOptions(
            no_record=_as_bool(merged.get("xhs_no_record"), True),
            interval=_as_float(merged.get("xhs_interval"), 12.0),
        )

    def _coerce_options(
        self, options: IngestOptions | Mapping[str, Any] | None
    ) -> IngestOptions:
        if isinstance(options, IngestOptions):
            return options
        base = self._default_options()
        values = options if isinstance(options, Mapping) else {}
        return IngestOptions(
            quality=str(values.get("quality") or base.quality),
            codec=str(values.get("codec") or base.codec),
            local_processing=str(
                values.get("local_processing") or base.local_processing
            ),
            no_record=_as_bool(values.get("no_record"), base.no_record),
            interval=_as_float(values.get("interval"), base.interval),
        )

    def _inspect_error(
        self,
        url: str,
        options: IngestOptions,
        message: str,
        *,
        token_present: bool,
        short_link: bool,
        session: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.id,
            "label": self.label,
            "url": url,
            "configured": True,
            "available": False,
            "warning": message,
            "error": message,
            "session": dict(session or {"available": False}),
            "title": "",
            "has_xsec_token": token_present,
            "short_link": short_link,
            "options": options.as_dict(),
        }

    def inspect(
        self, url: str, options: IngestOptions | Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        value = self._require_xhs_url(url)
        resolved = self._coerce_options(options)
        host = urlsplit(value).hostname or ""
        short_link = _is_short_host(host)
        token_present = _has_xsec_token(value)

        warnings: list[str] = []
        if not token_present and not short_link:
            warnings.append(_TOKEN_WARNING)

        merged = self._effective_settings()
        try:
            base = self._base_url(merged)
        except IngestError as exc:
            warnings.insert(0, str(exc))
            return self._inspect_error(
                value,
                resolved,
                " ".join(dict.fromkeys(warnings)),
                token_present=token_present,
                short_link=short_link,
            )

        try:
            state = self._fetch_state(merged)
        except IngestError as exc:
            warnings.append(str(exc))
            return self._inspect_error(
                value,
                resolved,
                " ".join(dict.fromkeys(warnings)),
                token_present=token_present,
                short_link=short_link,
                session={"cookie_set": False, "session_ok": None, "service_url": base},
            )

        session = self._session_info(state, base)
        session_error = self._session_error(session)
        if session_error:
            warnings.append(session_error)
        token_block = not token_present and not short_link
        warning = " ".join(dict.fromkeys(warnings))
        available = not session_error and not token_block
        return {
            "id": self.id,
            "provider": self.id,
            "label": self.label,
            "url": value,
            "configured": True,
            "available": available,
            "warning": warning,
            "error": "" if available else warning,
            "session": session,
            "title": "",
            "has_xsec_token": token_present,
            "short_link": short_link,
            "options": resolved.as_dict(),
        }

    # ------------------------------------------------------------------
    # Download job

    @staticmethod
    def _job_id(payload: Mapping[str, Any]) -> str:
        nested = payload.get("job")
        if isinstance(nested, Mapping):
            payload = nested
        value = payload.get("id") or payload.get("job_id") or ""
        job_id = str(value).strip()
        if not job_id:
            raise IngestError("XHS service did not return a job id.")
        return job_id

    @staticmethod
    def _file_entries(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, Mapping):
            for key in ("files", "items"):
                if key in value:
                    value = value.get(key)
                    break
        if isinstance(value, Mapping):
            items: list[dict[str, Any]] = []
            for key, item in value.items():
                if not isinstance(item, Mapping):
                    continue
                entry = dict(item)
                entry.setdefault("filename", str(key))
                items.append(entry)
            return items
        if not isinstance(value, list):
            return []
        items = []
        for item in value:
            if not isinstance(item, Mapping):
                continue
            entry = dict(item)
            name = entry.get("filename") or entry.get("name")
            if not name and entry.get("path"):
                name = Path(str(entry["path"])).name
            if name:
                entry.setdefault("filename", str(name))
            if not entry.get("name"):
                entry["name"] = entry.get("filename") or ""
            items.append(entry)
        return items

    def _list_files(self, settings: Mapping[str, Any]) -> list[dict[str, Any]]:
        payload = self._request_json(
            "GET",
            f"/api/files?limit={_FILE_LIST_LIMIT}",
            settings=settings,
            timeout=self.files_timeout,
        )
        if not isinstance(payload, (list, Mapping)):
            raise IngestError("XHS service returned an invalid file list.")
        return self._file_entries(payload)

    @staticmethod
    def _entry_path(entry: Mapping[str, Any]) -> Path | None:
        raw = entry.get("path") or entry.get("file") or entry.get("full_path")
        if not raw:
            return None
        path = Path(str(raw)).expanduser()
        try:
            if path.is_file():
                return path
        except OSError:
            return None
        return None

    @staticmethod
    def _entry_names(entry: Mapping[str, Any]) -> tuple[str, ...]:
        names: list[str] = []
        for value in (entry.get("filename"), entry.get("name")):
            if value:
                names.append(Path(str(value)).name.casefold())
        path = entry.get("path")
        if path:
            names.append(Path(str(path)).name.casefold())
        return tuple(dict.fromkeys(names))

    @staticmethod
    def _entry_mtime(entry: Mapping[str, Any]) -> float:
        return _as_float(entry.get("mtime"), 0.0)

    def _match_listed(
        self,
        entries: list[dict[str, Any]],
        wanted: Mapping[str, Any],
    ) -> Path | None:
        wanted_names = self._entry_names(wanted)
        if not wanted_names:
            return None
        wanted_stems = {Path(name).stem for name in wanted_names if Path(name).stem}

        exact: list[tuple[dict[str, Any], Path]] = []
        same_stem: list[tuple[dict[str, Any], Path]] = []
        for entry in entries:
            path = self._entry_path(entry)
            if path is None:
                continue
            names = self._entry_names(entry)
            if any(name in wanted_names for name in names):
                exact.append((entry, path))
            elif _is_video_name(path.name) and any(
                Path(name).stem in wanted_stems for name in names
            ):
                same_stem.append((entry, path))

        for pool in (exact, same_stem):
            if pool:
                pool.sort(key=lambda item: self._entry_mtime(item[0]), reverse=True)
                return pool[0][1]
        return None

    @staticmethod
    def _file_done(entry: Mapping[str, Any]) -> bool:
        state = str(entry.get("state") or "").strip().lower()
        if state in _FILE_DONE_STATES:
            return True
        if state in _FILE_FAILED_STATES or state in {
            "pending",
            "downloading",
            "running",
            "queued",
        }:
            return False
        total = _as_int(entry.get("total_bytes"), 0)
        completed = _as_int(entry.get("completed_bytes"), 0)
        return bool(total > 0 and completed >= total)

    def _resolve_output(
        self,
        snapshot: Mapping[str, Any],
        settings: Mapping[str, Any],
        progress: ProgressCallback,
    ) -> Path:
        files = self._file_entries(snapshot.get("files"))
        completed = [
            entry
            for entry in files
            if self._file_done(entry) or not str(entry.get("state") or "").strip()
        ]
        videos = [
            entry
            for entry in completed
            if _is_video_name(entry.get("filename") or entry.get("name"))
        ]
        completed_images = [
            entry
            for entry in completed
            if _is_image_name(entry.get("filename") or entry.get("name"))
        ]
        counts = snapshot.get("counts")
        counts = counts if isinstance(counts, Mapping) else {}
        if completed_images and not videos:
            raise IngestError(_IMAGE_ONLY)
        if _as_int(counts.get("skip"), 0) and not _as_int(counts.get("success"), 0):
            raise IngestError(_SKIPPED)

        listing: list[dict[str, Any]] = []
        listing_error: IngestError | None = None
        try:
            listing = self._list_files(settings)
        except IngestError as exc:
            listing_error = exc

        if videos:
            for candidate in reversed(videos):
                direct = self._entry_path(candidate)
                if direct is not None:
                    return direct
                match = self._match_listed(listing, candidate)
                if match is not None:
                    return match
            reported = ", ".join(
                str(entry.get("filename") or entry.get("name") or "video")
                for entry in videos[-3:]
            )
            if listing_error is not None:
                raise IngestError(
                    f"XHS downloaded {reported}, but VibeCut could not list the "
                    f"file: {listing_error}"
                ) from listing_error
            raise IngestError(
                f"XHS reported {reported}, but VibeCut cannot read that file. "
                "Run xhs_get and VibeCut on the same machine and check the "
                "xhs_get download folder."
            )

        entries = files + listing
        if any(
            _is_image_name(entry.get("filename") or entry.get("name"))
            for entry in entries
        ):
            raise IngestError(_IMAGE_ONLY)

        blob = " ".join(
            [
                str(snapshot.get("error") or ""),
                *[str(item) for item in (snapshot.get("logs") or [])[-8:]],
            ]
        ).lower()
        if any(word in blob for word in ("xsec_token", "share link", "token")):
            raise IngestError(_TOKEN_ERROR)
        if any(
            word in blob
            for word in (
                "cookie",
                "sign in",
                "login",
                "expired",
                "no note data",
                "rate-limited",
                "rate limited",
                "登录",
                "风控",
            )
        ):
            raise IngestError(_EXPIRED_SESSION)

        message = "XHS finished but did not return a video file."
        if listing_error is not None:
            message += f" The file list could not be read: {listing_error}"
        else:
            message += " Open xhs-get to check the job log."
        raise IngestError(message)

    def _fresh_videos(
        self, snapshot: Mapping[str, Any], listing: list[dict[str, Any]]
    ) -> list[Path]:
        videos: list[tuple[float, Path]] = []
        for entry in listing:
            path = self._entry_path(entry)
            if path is None or not _is_video_name(path.name):
                continue
            videos.append((self._entry_mtime(entry), path))
        if not videos:
            return []

        created = _as_float(snapshot.get("created"), 0.0)
        if created:
            recent = [(mtime, path) for mtime, path in videos if mtime >= created - 30]
            if recent:
                recent.sort(key=lambda item: item[0])
                return [path for _, path in recent]

        counts = snapshot.get("counts")
        counts = counts if isinstance(counts, Mapping) else {}
        success = _as_int(counts.get("success"), 0)
        if success and len(videos) == 1:
            return [videos[0][1]]
        return []

    def _job_progress(
        self, snapshot: Mapping[str, Any], last: float
    ) -> tuple[float, str]:
        files = self._file_entries(snapshot.get("files"))
        videos = [
            entry
            for entry in files
            if _is_video_name(entry.get("filename") or entry.get("name"))
        ]
        if videos:
            known = [
                entry for entry in videos if _as_int(entry.get("total_bytes"), 0) > 0
            ]
            fraction = last
            if known:
                completed = sum(
                    max(0, _as_int(entry.get("completed_bytes"), 0)) for entry in known
                )
                total = sum(
                    max(0, _as_int(entry.get("total_bytes"), 0)) for entry in known
                )
                if total:
                    fraction = min(0.97, completed / total)
                message = (
                    f"Downloading {Path(str(known[-1].get('filename'))).name} "
                    f"({_size_text(completed)} / {_size_text(total)})"
                )
            else:
                if any(self._file_done(entry) for entry in videos):
                    fraction = max(fraction, 0.95)
                active = next(
                    (
                        entry
                        for entry in videos
                        if str(entry.get("state") or "").lower()
                        in {"downloading", "running"}
                    ),
                    videos[-1],
                )
                message = (
                    f"Downloading {Path(str(active.get('filename') or 'video')).name}"
                )
            return max(last, fraction), message

        phase = _short(snapshot.get("phase") or "", 120)
        counts = snapshot.get("counts")
        counts = counts if isinstance(counts, Mapping) else {}
        total_notes = _as_int(counts.get("all"), 0)
        done_notes = sum(
            _as_int(counts.get(key), 0) for key in ("success", "fail", "skip")
        )
        fraction = last
        if total_notes > 0:
            fraction = max(fraction, min(0.95, 0.1 + 0.85 * done_notes / total_notes))
        match = re.search(r"Note\s+(\d+)\s*/\s*(\d+)", phase, re.IGNORECASE)
        if match:
            current, total = int(match.group(1)), int(match.group(2))
            if total > 0:
                fraction = max(
                    fraction, min(0.95, 0.1 + 0.85 * max(0, current - 1) / total)
                )
        if fraction <= last:
            fraction = max(last, 0.03)
        return fraction, phase or "XHS is downloading the note"

    @staticmethod
    def _job_failure(snapshot: Mapping[str, Any]) -> str:
        detail = _short(snapshot.get("error") or "", 320)
        logs = snapshot.get("logs") or []
        if not detail and logs:
            detail = _short(logs[-1], 320)
        blob = " ".join(
            [str(snapshot.get("error") or ""), *[str(item) for item in logs[-8:]]]
        ).lower()

        if any(word in blob for word in ("xsec_token", "share link")):
            return _TOKEN_ERROR
        if any(
            word in blob
            for word in (
                "cookie",
                "sign in",
                "login",
                "qr code",
                "session",
                "expired",
                "no note data",
                "登录",
                "扫码",
            )
        ):
            return _EXPIRED_SESSION
        if any(word in blob for word in ("no note link", "no note links found")):
            return (
                "XHS could not find a note in that link. Paste the full "
                "RedNote note URL from Share > Copy link."
            )
        if "low disk" in blob:
            return (
                f"xhs-get is low on disk space. {detail}"
                if detail
                else ("xhs-get is low on disk space. Free space, then retry.")
            )
        return (
            f"XHS download failed: {detail}"
            if detail
            else "XHS download failed. Open xhs-get to check the job log."
        )

    def _copy_output(
        self,
        source: Path,
        dest: Path,
        progress: ProgressCallback,
        cancel_event: threading.Event,
    ) -> Path:
        name = safe_filename(source.name, "rednote-video")
        destination = Path(dest).expanduser()
        if destination.exists():
            target = destination / name if destination.is_dir() else destination
        elif destination.suffix:
            target = destination
        else:
            destination.mkdir(parents=True, exist_ok=True)
            target = destination / name

        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            if source.resolve() == target.resolve():
                return target
        except OSError:
            pass

        fd, temp_name = tempfile.mkstemp(
            prefix=".xhs-", suffix=".part", dir=target.parent
        )
        temp = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as output:
                if cancel_event.is_set():
                    raise IngestError(_CANCELLED)
                size = source.stat().st_size
                copied = 0
                with source.open("rb") as input_file:
                    while True:
                        if cancel_event.is_set():
                            raise IngestError(_CANCELLED)
                        chunk = input_file.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
                        copied += len(chunk)
                        if size:
                            fraction = 0.98 + 0.019 * min(1.0, copied / size)
                            progress(
                                fraction, f"Saving {name} ({copied * 100 // size}%)"
                            )
            os.replace(temp, target)
        except IngestError:
            raise
        except OSError as exc:
            raise IngestError(
                f"Could not save the XHS video to {target}: {_short(exc)}"
            ) from exc
        finally:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
        return target

    @staticmethod
    def _deliverable_video(snapshot: Mapping[str, Any]) -> tuple[int, Mapping[str, Any]] | None:
        entries = snapshot.get("deliverables")
        if not isinstance(entries, list):
            return None
        for index, entry in enumerate(entries):
            if not isinstance(entry, Mapping):
                continue
            kind = str(entry.get("kind") or "").lower()
            filename = str(entry.get("filename") or entry.get("name") or "")
            if kind == "video" or _is_video_name(filename):
                return index, entry
        return None

    def _download_deliverable(
        self,
        job_id: str,
        index: int,
        entry: Mapping[str, Any],
        dest: Path,
        settings: Mapping[str, Any],
        progress: ProgressCallback,
        cancel_event: threading.Event,
    ) -> Path:
        """Stream a friends-mode deliverable from xhs_get to a local file."""
        base = self._base_url(settings)
        url = self._api_url(base, f"/api/jobs/{quote(job_id, safe='')}/file/{index}")
        headers = {"Accept": "*/*", "User-Agent": "VibeCut/xhs-ingest"}
        token = self._token(settings)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(url, headers=headers, method="GET")
        filename = safe_filename(
            str(entry.get("filename") or entry.get("name") or "rednote-video"),
            "rednote-video",
        )
        target = Path(dest)
        if target.is_dir() or not target.suffix:
            target = target / filename
        progress(0.94, f"Downloading {target.name} from xhs-get")
        temp = target.with_name(f".{target.name}.{os.urandom(4).hex()}.part")
        received = 0
        try:
            try:
                response = urlopen(request, timeout=self.request_timeout * 4)
            except HTTPError as exc:
                raise IngestError(
                    self._http_error_message(exc.code, "file", self._error_detail(exc), base)
                ) from exc
            try:
                with temp.open("wb") as handle:
                    while True:
                        if cancel_event.is_set():
                            raise IngestError(_CANCELLED)
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
                        received += len(chunk)
                        if received > MAX_DOWNLOAD_BYTES:
                            raise IngestError(
                                "XHS download exceeded the configured URL ingest limit."
                            )
                        progress(
                            min(0.99, 0.94 + received / max(received + 32 * 1024 * 1024, 1) * 0.05),
                            f"Downloading {target.name} - {received / (1024 * 1024):.1f} MB",
                        )
            finally:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
            if received <= 0:
                raise IngestError("xhs-get returned an empty video file.")
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temp, target)
        finally:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
        return target

    def download(
        self,
        url: str,
        dest: Path,
        options: IngestOptions | Mapping[str, Any] | None,
        progress: ProgressCallback,
        cancel_event: threading.Event,
    ) -> IngestResult:
        value = self._require_xhs_url(url)
        resolved = self._coerce_options(options)
        host = urlsplit(value).hostname or ""
        if not _has_xsec_token(value) and not _is_short_host(host):
            raise IngestError(_TOKEN_ERROR)
        if cancel_event.is_set():
            raise IngestError(_CANCELLED)

        settings = self._effective_settings()
        # Validate the endpoint and token before creating server-side work.
        self._base_url(settings)
        self._token(settings)

        interval = resolved.interval if math.isfinite(resolved.interval) else 12.0
        if interval < 0:
            interval = 0.0
        payload = {
            "kind": "links",
            "target": value,
            "note_filter": "video",
            "no_record": bool(resolved.no_record),
            "interval": interval,
        }
        progress(0.0, "Submitting RedNote link to xhs-get")
        created = self._request_json(
            "POST",
            "/api/jobs",
            payload,
            settings=settings,
            timeout=self.create_timeout,
        )
        if not isinstance(created, Mapping):
            raise IngestError("XHS service returned an invalid job response.")
        job_id = self._job_id(created)
        created_state = str(created.get("state") or "").lower()
        if created_state in _FAILED_STATES:
            raise IngestError(self._job_failure(created))
        if created_state in _CANCELLED_STATES:
            raise IngestError(_CANCELLED)

        progress(0.02, f"XHS job {job_id} queued")
        if cancel_event.is_set():
            raise IngestError(_CANCELLED)

        quoted_id = quote(job_id, safe="")
        deadline = (
            time.monotonic() + max(1.0, float(self.job_timeout))
            if self.job_timeout
            else None
        )
        last = 0.02
        snapshot: dict[str, Any] = {}
        while True:
            if cancel_event.is_set():
                raise IngestError(_CANCELLED)
            if deadline is not None and time.monotonic() >= deadline:
                raise IngestError(
                    f"XHS download timed out after {int(self.job_timeout)} seconds. "
                    "Open xhs-get to check the job."
                )
            payload = self._request_json(
                "GET", f"/api/jobs/{quoted_id}", settings=settings
            )
            if not isinstance(payload, Mapping):
                raise IngestError("XHS service returned an invalid job status.")
            snapshot = dict(payload)
            state = str(snapshot.get("state") or "").lower()

            if state in _FAILED_STATES:
                raise IngestError(self._job_failure(snapshot))
            if state in _CANCELLED_STATES:
                raise IngestError(_CANCELLED)
            if state in _DONE_STATES:
                break

            fraction, message = self._job_progress(snapshot, last)
            last = max(last, min(0.97, fraction))
            progress(last, message)

            delay = _as_float(self.poll_interval, 1.0)
            if delay > 0:
                if cancel_event.wait(delay):
                    raise IngestError(_CANCELLED)
            elif cancel_event.is_set():
                raise IngestError(_CANCELLED)

        if cancel_event.is_set():
            raise IngestError(_CANCELLED)

        deliverable = self._deliverable_video(snapshot)
        if deliverable is not None:
            index, entry = deliverable
            target = self._download_deliverable(
                job_id, index, entry, Path(dest), settings, progress, cancel_event,
            )
            display_name = safe_filename(
                str(entry.get("filename") or entry.get("name") or target.name),
                "rednote-video",
            )
            progress(1.0, "XHS video ready")
            return IngestResult(
                path=target,
                filename=display_name,
                provider=self.id,
                title=str(entry.get("title") or Path(display_name).stem),
                meta={
                    "job_id": job_id,
                    "note_url": value,
                    "delivery": "stream",
                    "remote_filename": display_name,
                    "note": entry.get("note"),
                    "author": entry.get("author"),
                },
            )

        source = self._resolve_output(snapshot, settings, progress)
        progress(0.98, f"Saving {source.name}")
        target = self._copy_output(source, Path(dest), progress, cancel_event)
        progress(1.0, "XHS video ready")

        display_name = safe_filename(source.name, "rednote-video")
        counts = snapshot.get("counts")
        return IngestResult(
            path=target,
            filename=display_name,
            provider=self.id,
            title=Path(display_name).stem,
            meta={
                "job_id": job_id,
                "note_url": value,
                "remote_path": str(source),
                "remote_filename": source.name,
                "counts": dict(counts) if isinstance(counts, Mapping) else {},
            },
        )
