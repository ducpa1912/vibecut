"""Cobalt ingest provider.

VibeCut only talks HTTP to a self-hosted cobalt instance.  This module never
selects the hosted ``api.cobalt.tools`` API: the instance URL must come from
Setup (or settings passed by the registry).

Cobalt can answer with a tunnel/redirect URL, or with a ``local-processing``
response that requires ffmpeg on this machine.  Audio-only and GIF results are
rejected because the rest of VibeCut expects a video file.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import os
import socket
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from email.message import Message
from pathlib import Path
from typing import Any, Mapping

from .base import IngestError, IngestOptions, IngestResult, ProgressCallback, Provider
from .registry import safe_filename, validate_url

PROVIDER_ID = "cobalt"
PROVIDER_LABEL = "Cobalt"

POST_TIMEOUT = 30.0
DOWNLOAD_TIMEOUT = 60.0
STATUS_TIMEOUT = 3.0
FFMPEG_TIMEOUT = 3600.0

CHUNK_SIZE = 1024 * 1024
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_TUNNEL_PARTS = 32
MAX_DOWNLOAD_BYTES = int(
    float(os.environ.get("VIBECUT_URL_MAX_GB", "4") or 4) * 1024 ** 3
)

_HOSTED_HOSTS = frozenset({"api.cobalt.tools"})
_RESPONSE_STATUSES = frozenset(
    {"tunnel", "redirect", "local-processing", "picker", "error"}
)

_QUALITY_VALUES = frozenset(
    {"max", "4320", "2160", "1440", "1080", "720", "480", "360", "240", "144"}
)
_CODEC_VALUES = frozenset({"h264", "av1", "vp9"})
_LOCAL_PROCESSING_VALUES = frozenset({"preferred", "forced", "disabled"})
_LOCAL_KINDS = frozenset({"merge", "remux", "mute"})

_VIDEO_EXTENSIONS = frozenset(
    {".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi", ".mpg", ".mpeg", ".ts"}
)
_AUDIO_EXTENSIONS = frozenset(
    {".m4a", ".aac", ".mp3", ".opus", ".ogg", ".oga", ".wav", ".flac", ".wma"}
)
_SUBTITLE_EXTENSIONS = frozenset({".vtt", ".srt", ".ass", ".ssa", ".lrc"})
_HLS_EXTENSIONS = frozenset({".m3u8", ".mpd"})

_MIME_EXTENSIONS = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/x-matroska": ".mkv",
    "video/quicktime": ".mov",
    "video/x-m4v": ".m4v",
    "video/mp2t": ".ts",
    "video/x-msvideo": ".avi",
    "video/mpeg": ".mpg",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/aac": ".aac",
    "audio/ogg": ".ogg",
    "audio/opus": ".opus",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/flac": ".flac",
    "audio/webm": ".webm",
    "image/gif": ".gif",
    "application/vnd.apple.mpegurl": ".m3u8",
    "application/x-mpegurl": ".m3u8",
    "application/dash+xml": ".mpd",
    "text/vtt": ".vtt",
    "application/x-subrip": ".srt",
}
_HLS_MIMES = frozenset(
    {"application/vnd.apple.mpegurl", "application/x-mpegurl", "application/dash+xml"}
)

_ERROR_MESSAGES = {
    "error.api.link.invalid": (
        "Cobalt could not understand this link. Check the URL and try again."
    ),
    "error.api.link.unsupported": (
        "Cobalt does not support this service or link type."
    ),
    "error.api.link.unavailable": (
        "The video is unavailable, private, or has been removed."
    ),
    "error.api.link.rate_exceeded": (
        "Cobalt's rate limit was reached. Wait a moment and try again."
    ),
    "error.api.fetch.empty": "Cobalt could not fetch a file from this link.",
    "error.api.fetch.fail": (
        "Cobalt failed while downloading this video from the source service."
    ),
    "error.api.fetch.rate_exceeded": (
        "The source service rate-limited Cobalt. Wait a moment and try again."
    ),
    "error.api.fetch.critical": (
        "Cobalt hit an unexpected error while fetching this video."
    ),
    "error.api.fetch.short_link": (
        "Cobalt could not expand this shortened link."
    ),
    "error.api.content.too_long": (
        "This video is longer than the Cobalt instance allows."
    ),
    "error.api.content.video.only": (
        "This link does not contain a downloadable video."
    ),
    "error.api.service.unsupported": (
        "The Cobalt instance does not support this service."
    ),
    "error.api.service.disabled": (
        "The Cobalt instance has this service disabled."
    ),
    "error.api.auth.key.missing": (
        "This Cobalt instance requires an API key. Add it in Setup."
    ),
    "error.api.auth.key.invalid": (
        "Cobalt rejected the API key. Check it in Setup."
    ),
    "error.api.auth.bearer.missing": (
        "This Cobalt instance requires a session token."
    ),
    "error.api.auth.bearer.invalid": (
        "This Cobalt instance rejected the session token."
    ),
    "error.api.rate_exceeded": (
        "Cobalt's rate limit was reached. Wait a moment and try again."
    ),
}


# ---------------------------------------------------------------------------
# Errors and small helpers


def _error(
    message: str,
    *,
    code: str = "",
    context: Mapping[str, Any] | None = None,
    status: int | None = None,
) -> IngestError:
    """Build an IngestError with machine-readable details attached."""
    exc = IngestError(message)
    exc.code = code  # type: ignore[attr-defined]
    exc.context = dict(context or {})  # type: ignore[attr-defined]
    exc.status = status  # type: ignore[attr-defined]
    return exc


def _short_reason(exc: BaseException) -> str:
    reason = getattr(exc, "reason", None) or exc
    text = " ".join(str(reason).split())
    return text[:200] or exc.__class__.__name__


def _message_for_code(code: str, context: Mapping[str, Any]) -> str:
    message = _ERROR_MESSAGES.get(code)
    if message is None:
        lowered = code.lower()
        if "auth" in lowered and ("missing" in lowered or "invalid" in lowered):
            message = "Cobalt rejected the request. Check the API key in Setup."
        elif "rate" in lowered:
            message = "Cobalt's rate limit was reached. Wait a moment and try again."
        elif "too_long" in lowered:
            message = "This video is longer than the Cobalt instance allows."
        elif code:
            message = f"Cobalt could not process this link ({code})."
        else:
            message = "Cobalt could not process this link."

    limit = context.get("limit")
    if isinstance(limit, (int, float)) and not isinstance(limit, bool):
        message = message.rstrip(".") + f" (limit: {limit})."
    return message


def _error_from_payload(
    payload: Mapping[str, Any], *, status: int | None = None
) -> IngestError:
    code = ""
    context: dict[str, Any] = {}
    raw = payload.get("error")
    if isinstance(raw, Mapping):
        code = str(raw.get("code") or "").strip()
        nested = raw.get("context")
        if isinstance(nested, Mapping):
            context = dict(nested)
    elif isinstance(raw, str):
        code = raw.strip()
    if not code:
        code = str(payload.get("code") or "").strip()
    if not code:
        code = f"http.{status}" if status is not None else "response.error"
    return _error(
        _message_for_code(code, context), code=code, context=context, status=status
    )


def _decode_json(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _read_http_error(exc: urllib.error.HTTPError) -> bytes:
    try:
        return exc.read(MAX_JSON_BYTES)
    except Exception:
        return b""
    finally:
        try:
            exc.close()
        except Exception:
            pass


def _http_error(exc: urllib.error.HTTPError) -> IngestError:
    body = _read_http_error(exc)
    payload = _decode_json(body)
    if isinstance(payload, Mapping) and str(payload.get("status") or "") == "error":
        return _error_from_payload(payload, status=exc.code)

    code = f"http.{exc.code}"
    if exc.code == 401:
        message = (
            "Cobalt rejected the request (HTTP 401). "
            "Check the API key in Setup."
        )
    elif exc.code == 403:
        message = "Cobalt refused the request (HTTP 403)."
    elif exc.code == 404:
        message = "Cobalt returned HTTP 404. Check the cobalt URL in Setup."
    elif exc.code == 429:
        message = "Cobalt is rate-limited (HTTP 429). Wait and try again."
    elif exc.code >= 500:
        message = f"The Cobalt instance failed (HTTP {exc.code})."
    else:
        message = f"Cobalt returned HTTP {exc.code}."
    return _error(message, code=code, status=exc.code)


def _network_error(exc: BaseException, endpoint: str) -> IngestError:
    return _error(
        f"Cobalt is not reachable at {endpoint}. Start the cobalt service or "
        f"check the URL in Setup. ({_short_reason(exc)})",
        code="cobalt.unreachable",
    )


def _download_network_error(exc: BaseException) -> IngestError:
    return _error(
        "Cobalt download was interrupted. Check that the cobalt instance is "
        f"still running. ({_short_reason(exc)})",
        code="download.unreachable",
    )


def _read_json_object(response: Any) -> dict[str, Any]:
    try:
        raw = response.read(MAX_JSON_BYTES + 1)
    except (OSError, http.client.HTTPException) as exc:
        raise _error(
            "Cobalt response was interrupted.", code="cobalt.response"
        ) from exc
    if not isinstance(raw, (bytes, bytearray)):
        raise _error("Cobalt returned an invalid response.", code="response.invalid")
    raw = bytes(raw)
    if len(raw) > MAX_JSON_BYTES:
        raise _error(
            "Cobalt returned a response that was too large.",
            code="response.too_large",
        )
    payload = _decode_json(raw)
    if not isinstance(payload, dict):
        raise _error("Cobalt returned an invalid response.", code="response.invalid")
    return payload


def _close(response: Any) -> None:
    close = getattr(response, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def _header(headers: Any, name: str) -> str:
    if headers is None:
        return ""
    value: Any = None
    getter = getattr(headers, "get", None)
    if callable(getter):
        try:
            value = getter(name)
        except Exception:
            value = None
    if value is None:
        items = getattr(headers, "items", None)
        if callable(items):
            try:
                for key, candidate in items():
                    if str(key).lower() == name.lower():
                        value = candidate
                        break
            except Exception:
                value = None
    if value is None:
        return ""
    return str(value).strip()


def _positive_int(value: Any) -> int | None:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _content_type(headers: Any) -> str:
    return _header(headers, "Content-Type").split(";", 1)[0].strip().lower()


def _content_disposition_name(headers: Any) -> str:
    header = _header(headers, "Content-Disposition")
    if not header:
        return ""
    message = Message()
    try:
        message["Content-Disposition"] = header
        name = message.get_filename()
    except (TypeError, ValueError):
        name = None
    if name:
        return str(name)
    match = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)\"?", header, re.I)
    if not match:
        return ""
    return urllib.parse.unquote(match.group(1).strip())


def _url_filename(url: str) -> str:
    path = urllib.parse.urlsplit(url).path
    return urllib.parse.unquote(Path(path).name)


def _mime_extension(mime: str) -> str:
    return _MIME_EXTENSIONS.get((mime or "").split(";", 1)[0].strip().lower(), "")


def _media_error(kind: str) -> IngestError:
    if kind == "audio":
        return _error(
            "Cobalt returned an audio-only file. VibeCut needs a video file.",
            code="media.audio",
        )
    if kind == "gif":
        return _error(
            "Cobalt returned a GIF. VibeCut needs a video file.", code="media.gif"
        )
    if kind == "hls":
        return _error(
            "Cobalt returned an HLS stream. VibeCut needs a single video file.",
            code="media.hls",
        )
    return _error(
        "Cobalt returned a file that is not a video.", code="media.unsupported"
    )


def _output_name(
    hint: Any,
    mime: str,
    *,
    allow_audio: bool,
    default_ext: str,
    fallback: str,
) -> str:
    """Return a safe filename with a media extension.

    Direct downloads and the final output of local processing must be video.
    Tunnel *parts* may be audio or subtitle files, so ``allow_audio`` skips
    those checks for them.
    """
    raw = "" if hint is None else str(hint)
    name = safe_filename(raw, fallback=fallback, max_length=140)
    suffix = Path(name).suffix.lower()
    mime_ext = _mime_extension(mime)
    mime_base = (mime or "").split(";", 1)[0].strip().lower()

    if not allow_audio:
        if mime_base.startswith("audio/") or suffix in _AUDIO_EXTENSIONS:
            raise _media_error("audio")
        if mime_base == "image/gif" or suffix == ".gif":
            raise _media_error("gif")
        if mime_base in _HLS_MIMES or suffix in _HLS_EXTENSIONS:
            raise _media_error("hls")
        if mime_base.startswith("image/"):
            raise _error(
                "Cobalt returned an image, not a video.", code="media.image"
            )

    if suffix in _VIDEO_EXTENSIONS:
        return name
    if allow_audio and (
        suffix in _AUDIO_EXTENSIONS
        or suffix == ".gif"
        or suffix in _SUBTITLE_EXTENSIONS
        or suffix in _HLS_EXTENSIONS
    ):
        return name

    extension = mime_ext or default_ext
    if not allow_audio:
        if extension in _AUDIO_EXTENSIONS:
            raise _media_error("audio")
        if extension == ".gif":
            raise _media_error("gif")
        if extension in _HLS_EXTENSIONS:
            raise _media_error("hls")
    stem = Path(name).stem if suffix else name
    if not stem:
        stem = fallback
    return safe_filename(
        stem + extension, fallback=fallback + default_ext, max_length=140
    )


def _looks_like_directory(dest: Any) -> bool:
    text = str(dest)
    if text.endswith(("/", os.sep)):
        return True
    try:
        return Path(dest).is_dir()
    except OSError:
        return False


def _choose_target(
    dest: Any,
    remote_name: Any,
    mime: str,
    *,
    allow_audio: bool,
    default_ext: str,
    fallback: str,
) -> tuple[Path, str]:
    base = Path(dest).expanduser()
    directory_dest = _looks_like_directory(dest)
    name = _output_name(
        remote_name,
        mime,
        allow_audio=allow_audio,
        default_ext=default_ext,
        fallback=fallback,
    )

    if directory_dest:
        base.mkdir(parents=True, exist_ok=True)
        return base / name, name

    # An explicit file path is part of the provider contract. Keep it exactly
    # as given so the caller can move/link that path; the remote-safe filename
    # is still reported in IngestResult.filename.
    base.parent.mkdir(parents=True, exist_ok=True)
    return base, name


def _request_headers(api_key: str) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Api-Key {api_key}"
    return headers


def _api_key(values: Mapping[str, Any]) -> str:
    key = values.get("cobalt_api_key")
    if key is None or not str(key).strip():
        key = values.get("cobalt_key")
    text = "" if key is None else str(key).strip()
    if any(character in text for character in "\r\n\0"):
        raise _error(
            "Cobalt API key contains invalid characters.", code="config.invalid"
        )
    return text


def _normalize_endpoint(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error(
            "Cobalt URL is not set. Add your self-hosted cobalt instance in Setup.",
            code="config.missing",
        )
    try:
        endpoint = validate_url(value)
    except IngestError as exc:
        raise _error(f"Cobalt URL is invalid: {exc}", code="config.invalid") from exc

    parts = urllib.parse.urlsplit(endpoint)
    host = (parts.hostname or "").lower().rstrip(".")
    if host in _HOSTED_HOSTS:
        raise _error(
            "Hosted api.cobalt.tools is not supported. Configure your own "
            "cobalt instance in Setup.",
            code="config.hosted",
        )
    if parts.query or parts.fragment:
        raise _error(
            "Cobalt URL must not include a query or fragment.",
            code="config.invalid",
        )
    if parts.username or parts.password:
        raise _error(
            "Cobalt URL must not include credentials.", code="config.invalid"
        )
    path = parts.path or "/"
    if not path.endswith("/"):
        path += "/"
    return urllib.parse.urlunparse(
        (parts.scheme, parts.netloc, path, "", "", "")
    )


def _host_is_private(host: str) -> bool:
    host = (host or "").strip().lower().rstrip(".")
    if not host or host in {"localhost", "localhost.localdomain"}:
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
        # Let the HTTP client decide; unresolved names cannot be SSRF targets
        # in practice, and fake hosts are used by tests.
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


def _validate_remote_url(value: str, base: str, *, what: str, same_host_ok: bool = True) -> str:
    parsed = urllib.parse.urlsplit(value)
    base_parsed = urllib.parse.urlsplit(base)
    host = parsed.hostname or ""
    base_host = base_parsed.hostname or ""
    if parsed.username or parsed.password:
        raise _error(
            f"Cobalt returned an unsafe {what} URL with userinfo.",
            code="response.unsafe_url",
        )
    same_host = host.lower() == base_host.lower()
    loopback_pair = host in {"127.0.0.1", "::1", "localhost"} and base_host in {
        "127.0.0.1", "::1", "localhost"
    }
    if same_host_ok and (same_host or loopback_pair):
        return value
    if _host_is_private(host):
        raise _error(
            f"Cobalt returned an unsafe private-network {what} URL.",
            code="response.unsafe_url",
        )
    return value


def _absolute_http_url(raw: Any, base: str, *, what: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise _error(
            f"Cobalt returned an invalid {what} URL.", code="response.invalid"
        )
    value = urllib.parse.urljoin(base, raw.strip())
    try:
        value = validate_url(value)
        return _validate_remote_url(value, base, what=what)
    except IngestError as exc:
        raise _error(
            f"Cobalt returned an invalid {what} URL.", code="response.invalid"
        ) from exc


def _option_value(options: Any, name: str, default: Any = None) -> Any:
    if isinstance(options, Mapping):
        value = options.get(name)
    else:
        value = getattr(options, name, None)
    return default if value is None or value == "" else value


def _request_body(
    url: str, options: IngestOptions, values: Mapping[str, Any]
) -> dict[str, Any]:
    quality = str(
        _option_value(
            options, "quality", values.get("cobalt_quality") or "1080"
        )
    ).strip().lower()
    if quality in {"best", "source"}:
        quality = "max"
    if quality not in _QUALITY_VALUES:
        quality = "1080"

    codec = str(
        _option_value(
            options, "codec", values.get("cobalt_codec") or "h264"
        )
    ).strip().lower()
    if codec not in _CODEC_VALUES:
        codec = "h264"

    local_processing = str(
        _option_value(
            options,
            "local_processing",
            values.get("cobalt_local_processing") or "preferred",
        )
    ).strip().lower()
    if local_processing not in _LOCAL_PROCESSING_VALUES:
        local_processing = "preferred"

    return {
        "url": url,
        "videoQuality": quality,
        "youtubeVideoCodec": codec,
        "downloadMode": "auto",
        "localProcessing": local_processing,
        "filenameStyle": "basic",
    }


def _local_kind(payload: Mapping[str, Any]) -> str:
    return str(payload.get("type") or "").strip().lower()


def _output_object(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    output = payload.get("output")
    return output if isinstance(output, Mapping) else {}


def _output_mime(payload: Mapping[str, Any]) -> str:
    output = _output_object(payload)
    value = output.get("type") or output.get("mime") or ""
    return str(value).split(";", 1)[0].strip().lower()


def _output_filename(payload: Mapping[str, Any]) -> str:
    output = _output_object(payload)
    return str(output.get("filename") or "").strip()


def _metadata_title(payload: Mapping[str, Any]) -> str:
    output = _output_object(payload)
    metadata = output.get("metadata")
    if isinstance(metadata, Mapping):
        return str(metadata.get("title") or "").strip()
    return ""


def _is_hls(payload: Mapping[str, Any]) -> bool:
    if payload.get("isHLS") is True:
        return True
    output = _output_object(payload)
    return output.get("isHLS") is True


def _local_problem(
    kind: str, mime: str, is_hls: bool
) -> tuple[str, str] | None:
    if is_hls or mime in _HLS_MIMES:
        return (
            "Cobalt returned an HLS stream. VibeCut needs a single video file.",
            "local.hls",
        )
    if kind == "audio" or mime.startswith("audio/"):
        return (
            "Cobalt returned audio only. VibeCut can only ingest video files.",
            "local.audio",
        )
    if kind == "gif" or mime.startswith("image/gif"):
        return (
            "Cobalt returned a GIF. VibeCut can only ingest video files.",
            "local.gif",
        )
    if kind not in _LOCAL_KINDS:
        label = kind or "unknown"
        return (
            f"Cobalt returned an unsupported local processing type "
            f"({label}).",
            "local.unsupported",
        )
    return None


def _tunnel_urls(payload: Mapping[str, Any], endpoint: str) -> list[str]:
    raw = payload.get("tunnel")
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)) or not raw:
        raise _error(
            "Cobalt returned no tunnel files for local processing.",
            code="response.invalid",
        )
    if len(raw) > MAX_TUNNEL_PARTS:
        raise _error(
            "Cobalt returned too many files for local processing.",
            code="response.invalid",
        )
    urls = [
        _absolute_http_url(item, endpoint, what="tunnel")
        for item in raw
        if isinstance(item, str)
    ]
    if not urls:
        raise _error(
            "Cobalt returned no usable tunnel files for local processing.",
            code="response.invalid",
        )
    return urls


def _picker_choices(
    payload: Mapping[str, Any], endpoint: str
) -> list[dict[str, str]]:
    entries = payload.get("picker")
    if not isinstance(entries, list):
        raise _error(
            "Cobalt returned a picker response without items.",
            code="response.invalid",
        )
    choices: list[dict[str, str]] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        try:
            remote = _absolute_http_url(
                entry.get("url"), endpoint, what="picker item"
            )
        except IngestError:
            continue
        choice = {
            "type": str(entry.get("type") or "unknown").strip().lower(),
            "url": remote,
        }
        thumbnail = entry.get("thumb")
        if isinstance(thumbnail, str) and thumbnail.strip():
            try:
                choice["thumbnail"] = _absolute_http_url(
                    thumbnail, endpoint, what="thumbnail"
                )
            except IngestError:
                pass
        choices.append(choice)
    if not choices:
        raise _error(
            "Cobalt returned a picker with no usable items.",
            code="response.invalid",
        )
    return choices


# ---------------------------------------------------------------------------
# Media handling


@dataclass
class _Part:
    path: Path
    filename: str
    mime: str
    size: int

    @property
    def kind(self) -> str:
        mime = self.mime.lower()
        if mime.startswith("video/"):
            return "video"
        if mime.startswith("audio/"):
            return "audio"
        if mime == "image/gif":
            return "gif"
        if mime in _HLS_MIMES:
            return "hls"
        if mime.startswith("text/") or mime == "application/x-subrip":
            return "subtitle"

        suffix = self.path.suffix.lower()
        if suffix in _VIDEO_EXTENSIONS:
            return "video"
        if suffix in _AUDIO_EXTENSIONS:
            return "audio"
        if suffix in _SUBTITLE_EXTENSIONS:
            return "subtitle"
        if suffix == ".gif":
            return "gif"
        if suffix in _HLS_EXTENSIONS:
            return "hls"
        return "unknown"


def _merge_inputs(parts: list[_Part]) -> tuple[_Part, _Part]:
    videos = [part for part in parts if part.kind == "video"]
    audios = [part for part in parts if part.kind == "audio"]
    if videos and audios:
        return videos[0], audios[0]

    candidates = [
        part for part in parts if part.kind in {"video", "unknown"}
    ]
    if len(candidates) >= 2:
        return candidates[0], candidates[1]

    if any(part.kind == "hls" for part in parts):
        raise _media_error("hls")
    if any(part.kind == "gif" for part in parts):
        raise _media_error("gif")
    if any(part.kind == "audio" for part in parts):
        raise _media_error("audio")
    raise _error(
        "Cobalt returned incomplete files for merging. "
        "Video and audio parts were expected.",
        code="local.parts",
    )


def _video_input(parts: list[_Part]) -> _Part:
    for part in parts:
        if part.kind == "video":
            return part
    for part in parts:
        if part.kind == "unknown":
            return part
    if any(part.kind == "hls" for part in parts):
        raise _media_error("hls")
    if any(part.kind == "gif" for part in parts):
        raise _media_error("gif")
    if any(part.kind == "audio" for part in parts):
        raise _media_error("audio")
    raise _error(
        "Cobalt returned no video file for local processing.",
        code="local.parts",
    )


def _ffmpeg_path() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise _error(
            "Local processing needs ffmpeg, but it is not installed or not on PATH.",
            code="ffmpeg.missing",
        )
    return path


def _ffmpeg_command(
    ffmpeg: str,
    kind: str,
    video: _Part,
    audio: _Part | None,
    output: Path,
) -> list[str]:
    command = [ffmpeg, "-y", "-v", "error", "-i", str(video.path)]
    faststart: list[str] = []
    if output.suffix.lower() in {".mp4", ".m4v", ".mov"}:
        faststart = ["-movflags", "+faststart"]

    if kind == "merge" and audio is not None:
        return [
            *command,
            "-i",
            str(audio.path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c",
            "copy",
            *faststart,
            str(output),
        ]
    if kind == "mute":
        return [
            *command,
            "-map",
            "0:v:0",
            "-an",
            "-c:v",
            "copy",
            *faststart,
            str(output),
        ]
    return [
        *command,
        "-map",
        "0:v:0?",
        "-map",
        "0:a:0?",
        "-c",
        "copy",
        *faststart,
        str(output),
    ]


def _terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
    except OSError:
        pass
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except OSError:
            pass


def _run_ffmpeg(cmd: list[str], cancel_event: threading.Event) -> None:
    try:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=(os.name == "posix"),
        )
    except (OSError, ValueError) as exc:
        raise _error(
            "Could not start ffmpeg for Cobalt local processing.",
            code="ffmpeg.failed",
        ) from exc

    stderr = ""
    deadline = time.monotonic() + FFMPEG_TIMEOUT
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                _terminate_process(process)
                raise _error(
                    "Cobalt local processing was cancelled.", code="cancelled"
                )
            if time.monotonic() > deadline:
                _terminate_process(process)
                raise _error(
                    "Local ffmpeg processing timed out.", code="ffmpeg.timeout"
                )
            try:
                _, stderr = process.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                continue
    finally:
        if process.poll() is None:
            _terminate_process(process)

    if process.returncode != 0:
        tail = (stderr or "").strip()[-1200:]
        raise _error(
            "Local ffmpeg processing failed."
            + (f"\n{tail}" if tail else ""),
            code="ffmpeg.failed",
        )


def _video_extension(preferred_name: str, target: Path) -> str:
    # Cobalt's output filename describes the container it expects. Fall back
    # to the caller's path and then to mp4.
    for candidate in (Path(preferred_name).suffix, target.suffix):
        suffix = candidate.lower()
        if suffix in _VIDEO_EXTENSIONS:
            return suffix
    return ".mp4"


def _ffmpeg_action(kind: str) -> str:
    if kind == "merge":
        return "Merging video and audio with ffmpeg..."
    if kind == "mute":
        return "Removing audio from the video with ffmpeg..."
    return "Remuxing the video with ffmpeg..."


def _emit(
    progress: ProgressCallback | None, fraction: float, message: str
) -> None:
    if not callable(progress):
        return
    try:
        progress(max(0.0, min(1.0, float(fraction))), message)
    except Exception:
        # Progress reporting must never abort a download.
        pass


def _check_cancel(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise _error("Cobalt download cancelled.", code="cancelled")


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urljoin(req.full_url, newurl)
        _validate_remote_url(target, req.full_url, what="redirect", same_host_ok=True)
        forwarded = dict(req.headers or {})
        for name in list(forwarded):
            if name.lower() in {"authorization", "api-key", "cookie"}:
                forwarded.pop(name, None)
        return urllib.request.Request(
            target, headers=forwarded, method="GET",
        )


def _urlopen(request: urllib.request.Request, timeout: float) -> Any:
    opener = urllib.request.build_opener(_SafeRedirectHandler())
    return opener.open(request, timeout=timeout)


# ---------------------------------------------------------------------------
# Provider


class CobaltProvider(Provider):
    """Ingest through a self-hosted cobalt API instance."""

    id = PROVIDER_ID
    label = PROVIDER_LABEL
    required_settings = ("cobalt_url",)

    def _effective_settings(
        self, extra: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for source in (self.settings, extra):
            if not isinstance(source, Mapping):
                continue
            nested = source.get("ingest")
            if isinstance(nested, Mapping):
                merged.update(nested)
            for key, value in source.items():
                if key != "ingest":
                    merged[key] = value
        return merged

    def _post(
        self, endpoint: str, body: Mapping[str, Any], api_key: str
    ) -> dict[str, Any]:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=data,
            method="POST",
            headers=_request_headers(api_key),
        )
        try:
            response = _urlopen(request, timeout=POST_TIMEOUT)
        except urllib.error.HTTPError as exc:
            raise _http_error(exc) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise _network_error(exc, endpoint) from exc
        try:
            return _read_json_object(response)
        finally:
            _close(response)

    def _resolve(
        self, url: str, options: IngestOptions
    ) -> tuple[str, dict[str, Any], str]:
        target = validate_url(url)
        values = self._effective_settings()
        endpoint = _normalize_endpoint(values.get("cobalt_url"))
        api_key = _api_key(values)
        payload = self._post(
            endpoint, _request_body(target, options, values), api_key
        )
        status = str(payload.get("status") or "").strip().lower()
        if not status:
            raise _error(
                "Cobalt returned a response without a status.",
                code="response.invalid",
            )
        if status == "error":
            raise _error_from_payload(payload)
        if status not in _RESPONSE_STATUSES:
            raise _error(
                f"Cobalt returned an unsupported response status '{status}'.",
                code="response.status",
            )
        return endpoint, payload, status

    def inspect(self, url: str, options: IngestOptions) -> dict[str, Any]:
        endpoint, payload, status = self._resolve(url, options)
        base: dict[str, Any] = {"provider": self.id, "label": self.label}

        if status in {"tunnel", "redirect"}:
            remote = _absolute_http_url(
                payload.get("url"), endpoint, what="download"
            )
            raw_name = payload.get("filename") or _url_filename(remote)
            filename = _output_name(
                raw_name,
                "",
                allow_audio=False,
                default_ext=".mp4",
                fallback="cobalt-video",
            )
            return {
                **base,
                "status": status,
                "available": True,
                "warning": "",
                "filename": filename,
                "title": Path(filename).stem,
                "duration": None,
                "thumbnail": None,
            }

        if status == "local-processing":
            kind = _local_kind(payload)
            mime = _output_mime(payload)
            hls = _is_hls(payload)
            problem = _local_problem(kind, mime, hls)
            if problem is not None:
                warning, _code = problem
                return {
                    **base,
                    "status": status,
                    "available": False,
                    "warning": warning,
                    "filename": "",
                    "title": "",
                    "kind": kind,
                    "parts": 0,
                    "duration": None,
                    "thumbnail": None,
                }

            tunnels = _tunnel_urls(payload, endpoint)
            filename = _output_name(
                _output_filename(payload),
                mime,
                allow_audio=False,
                default_ext=".mp4",
                fallback="cobalt-video",
            )
            title = _metadata_title(payload) or Path(filename).stem
            return {
                **base,
                "status": status,
                "available": True,
                "warning": "",
                "filename": filename,
                "title": title,
                "kind": kind,
                "parts": len(tunnels),
                "duration": None,
                "thumbnail": None,
            }

        choices = _picker_choices(payload, endpoint)
        return {
            **base,
            "status": "picker",
            "available": False,
            "warning": (
                "This link contains multiple items. Open it and paste a link "
                "to a single video."
            ),
            "filename": "",
            "title": "",
            "choices": choices,
            "needs_choice": True,
            "duration": None,
            "thumbnail": None,
        }

    def download(
        self,
        url: str,
        dest: Path,
        options: IngestOptions,
        progress: ProgressCallback,
        cancel_event: threading.Event,
    ) -> IngestResult:
        _check_cancel(cancel_event)
        _emit(progress, 0.01, "Asking Cobalt to resolve the link...")
        endpoint, payload, status = self._resolve(url, options)
        _check_cancel(cancel_event)

        if status in {"tunnel", "redirect"}:
            return self._download_single(
                endpoint, payload, status, dest, progress, cancel_event
            )
        if status == "local-processing":
            return self._download_local(
                endpoint, payload, dest, progress, cancel_event
            )

        choices = _picker_choices(payload, endpoint)
        raise _error(
            "This Cobalt link contains multiple items. Open it and paste a "
            "link to a single video.",
            code="picker",
            context={"choices": choices},
        )

    def _download_single(
        self,
        endpoint: str,
        payload: Mapping[str, Any],
        status: str,
        dest: Path,
        progress: ProgressCallback,
        cancel_event: threading.Event,
    ) -> IngestResult:
        remote = _absolute_http_url(
            payload.get("url"), endpoint, what="download"
        )
        hint = payload.get("filename") or _url_filename(remote)
        part = self._download_stream(
            remote,
            dest,
            hint,
            progress,
            cancel_event,
            start=0.02,
            end=1.0,
            label="video",
            part_mode=False,
        )
        return IngestResult(
            path=part.path,
            filename=part.filename,
            provider=self.id,
            title=Path(part.filename).stem,
            meta={
                "status": status,
                "content_type": part.mime,
                "content_length": part.size,
            },
        )

    def _download_local(
        self,
        endpoint: str,
        payload: Mapping[str, Any],
        dest: Path,
        progress: ProgressCallback,
        cancel_event: threading.Event,
    ) -> IngestResult:
        kind = _local_kind(payload)
        mime = _output_mime(payload)
        hls = _is_hls(payload)
        problem = _local_problem(kind, mime, hls)
        if problem is not None:
            warning, code = problem
            raise _error(warning, code=code)

        tunnels = _tunnel_urls(payload, endpoint)
        filename = _output_name(
            _output_filename(payload),
            mime,
            allow_audio=False,
            default_ext=".mp4",
            fallback="cobalt-video",
        )
        target, display_name = _choose_target(
            dest,
            filename,
            mime,
            allow_audio=False,
            default_ext=".mp4",
            fallback="cobalt-video",
        )

        ffmpeg = _ffmpeg_path()
        work_dir = Path(
            tempfile.mkdtemp(prefix=".cobalt-", dir=str(target.parent))
        )
        try:
            parts: list[_Part] = []
            count = len(tunnels)
            span = 0.68
            for index, remote in enumerate(tunnels):
                start = 0.02 + span * index / count
                end = 0.02 + span * (index + 1) / count
                parts.append(
                    self._download_stream(
                        remote,
                        work_dir / f"part-{index + 1:02d}",
                        "",
                        progress,
                        cancel_event,
                        start=start,
                        end=end,
                        label=f"part {index + 1} of {count}",
                        part_mode=True,
                    )
                )

            _check_cancel(cancel_event)
            if kind == "merge":
                video, audio = _merge_inputs(parts)
            else:
                video = _video_input(parts)
                audio = None

            output = work_dir / f"output{_video_extension(filename, target)}"
            command = _ffmpeg_command(ffmpeg, kind, video, audio, output)
            _emit(progress, 0.78, _ffmpeg_action(kind))
            _run_ffmpeg(command, cancel_event)
            _check_cancel(cancel_event)

            if not output.is_file() or output.stat().st_size <= 0:
                raise _error(
                    "Local ffmpeg processing did not produce a video file.",
                    code="ffmpeg.failed",
                )
            os.replace(output, target)
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

        _emit(progress, 1.0, f"Downloaded {display_name}.")
        return IngestResult(
            path=target,
            filename=display_name,
            provider=self.id,
            title=_metadata_title(payload) or Path(display_name).stem,
            meta={
                "status": "local-processing",
                "type": kind,
                "content_type": mime,
                "parts": len(parts),
                "service": str(payload.get("service") or ""),
            },
        )

    def _download_stream(
        self,
        remote: str,
        dest: Path,
        filename_hint: Any,
        progress: ProgressCallback,
        cancel_event: threading.Event,
        *,
        start: float,
        end: float,
        label: str,
        part_mode: bool,
    ) -> _Part:
        _emit(progress, start, f"Downloading {label} from Cobalt...")
        _check_cancel(cancel_event)
        request = urllib.request.Request(
            remote, method="GET", headers={"Accept": "*/*"}
        )
        try:
            response = _urlopen(request, timeout=DOWNLOAD_TIMEOUT)
        except urllib.error.HTTPError as exc:
            raise _http_error(exc) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise _download_network_error(exc) from exc

        try:
            status = getattr(response, "status", 200)
            if not isinstance(status, int):
                status = 200
            if status < 200 or status >= 300:
                raise _error(
                    f"Cobalt download failed with HTTP {status}.",
                    code=f"download.http.{status}",
                    status=status,
                )

            headers = getattr(response, "headers", None)
            mime = _content_type(headers)
            remote_name = (
                str(filename_hint or "").strip()
                or _content_disposition_name(headers)
                or _url_filename(remote)
            )
            target, display_name = _choose_target(
                dest,
                remote_name,
                mime,
                allow_audio=part_mode,
                default_ext=".bin" if part_mode else ".mp4",
                fallback="cobalt-part" if part_mode else "cobalt-video",
            )

            content_length = _positive_int(_header(headers, "Content-Length"))
            estimated_length = _positive_int(
                _header(headers, "Estimated-Content-Length")
            )
            total = content_length or estimated_length
            temp = target.parent / f".{target.name}.{uuid.uuid4().hex}.part"
            received = 0
            try:
                with temp.open("wb") as handle:
                    while True:
                        _check_cancel(cancel_event)
                        try:
                            chunk = response.read(CHUNK_SIZE)
                        except (OSError, http.client.HTTPException) as exc:
                            raise _download_network_error(exc) from exc
                        if not chunk:
                            break
                        if not isinstance(chunk, (bytes, bytearray)):
                            chunk = bytes(chunk)
                        handle.write(chunk)
                        received += len(chunk)
                        if received > MAX_DOWNLOAD_BYTES:
                            raise _error(
                                "Cobalt download exceeded the configured URL ingest limit.",
                                code="download.too_large",
                            )

                        if total:
                            ratio = min(1.0, received / total)
                            detail = (
                                f"{received / (1024 * 1024):.1f} MB of "
                                f"{total / (1024 * 1024):.1f} MB"
                            )
                        else:
                            ratio = received / (
                                received + 32 * 1024 * 1024
                            )
                            detail = f"{received / (1024 * 1024):.1f} MB"
                        _emit(
                            progress,
                            start + (end - start) * ratio,
                            f"Downloading {display_name} - {detail}",
                        )
                        _check_cancel(cancel_event)

                _check_cancel(cancel_event)
                if content_length is not None and received != content_length:
                    raise _error(
                        "Cobalt download size mismatch "
                        f"({received} of {content_length} bytes received).",
                        code="download.incomplete",
                    )
                if received <= 0:
                    raise _error(
                        "Cobalt returned an empty file.", code="download.empty"
                    )
                os.replace(temp, target)
            finally:
                temp.unlink(missing_ok=True)
        finally:
            _close(response)

        _emit(progress, end, f"Downloaded {display_name}.")
        return _Part(
            path=target,
            filename=display_name,
            mime=mime,
            size=received,
        )

    def status(
        self, settings: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        values = self._effective_settings(settings)
        try:
            endpoint = _normalize_endpoint(values.get("cobalt_url"))
        except IngestError as exc:
            return self._status_result(False, False, str(exc))
        try:
            api_key = _api_key(values)
        except IngestError as exc:
            return self._status_result(False, False, str(exc))

        request = urllib.request.Request(
            endpoint, method="GET", headers=_request_headers(api_key)
        )
        try:
            response = _urlopen(request, timeout=STATUS_TIMEOUT)
        except urllib.error.HTTPError as exc:
            error = _http_error(exc)
            return self._status_result(True, False, str(error))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            error = _network_error(exc, endpoint)
            return self._status_result(True, False, str(error))
        except Exception as exc:
            return self._status_result(
                True, False, f"Cobalt status check failed: {_short_reason(exc)}"
            )

        try:
            status = getattr(response, "status", 200)
            if not isinstance(status, int):
                status = 200
            raw = response.read(MAX_JSON_BYTES + 1)
        except (OSError, http.client.HTTPException) as exc:
            return self._status_result(
                True,
                False,
                f"Cobalt status check failed: {_short_reason(exc)}",
            )
        except Exception as exc:
            return self._status_result(
                True, False, f"Cobalt status check failed: {_short_reason(exc)}"
            )
        finally:
            _close(response)

        if status < 200 or status >= 300:
            return self._status_result(
                True,
                False,
                f"Cobalt status endpoint returned HTTP {status}.",
            )
        if not isinstance(raw, (bytes, bytearray)):
            return self._status_result(
                True,
                False,
                "Cobalt returned an invalid status response.",
            )
        if len(raw) > MAX_JSON_BYTES:
            return self._status_result(
                True, False, "Cobalt returned a status response that was too large."
            )
        payload = _decode_json(bytes(raw))
        if not isinstance(payload, Mapping) or "cobalt" not in payload:
            return self._status_result(
                True,
                False,
                "Cobalt URL responded, but not like a cobalt API. "
                "Check the URL in Setup.",
            )
        return self._status_result(True, True, "")

    def _status_result(
        self, configured: bool, available: bool, error: str
    ) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "configured": configured,
            "available": available,
            "error": error,
        }
