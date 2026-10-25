"""URL detection, provider construction, and Setup status for URL ingest.

The registry is the only place that knows about concrete provider modules.
Those imports happen inside :func:`provider` and :func:`status`, never at
package import time or during URL detection, so a missing provider module does
not break the rest of VibeCut.
"""

from __future__ import annotations

import importlib
import inspect
import math
import re
from dataclasses import dataclass
from typing import Any, Mapping, cast
from urllib.parse import urlsplit

from .base import IngestError, IngestOptions, Provider

YTDLP = "ytdlp"
COBALT = "cobalt"
XHS = "xhs"
AUTO = "auto"

PROVIDER_IDS = (YTDLP, XHS, COBALT)
XHS_DOMAINS = ("rednote.com", "xiaohongshu.com", "xhslink.com", "xhslink.cn")

# The public settings schema. Values here are copied, never mutated.
DEFAULT_INGEST_SETTINGS: dict[str, Any] = {
    "provider": AUTO,
    "ytdlp_quality": "max",
    "ytdlp_codec": "h264",
    "ytdlp_container": "mp4",
    "ytdlp_audio": "best",
    "ytdlp_cookies": "none",
    "ytdlp_browser": "safari",
    "ytdlp_cookie_file": "",
    "cobalt_fallback": False,
    "cobalt_url": "http://127.0.0.1:9000/",
    "cobalt_quality": "1080",
    "cobalt_codec": "h264",
    "cobalt_local_processing": "preferred",
    "xhs_url": "http://127.0.0.1:5789",
    "xhs_no_record": True,
    "xhs_interval": 12.0,
}
INGEST_DEFAULTS = DEFAULT_INGEST_SETTINGS

_PROVIDER_ALIASES = {
    AUTO: AUTO,
    "": AUTO,
    YTDLP: YTDLP,
    "yt-dlp": YTDLP,
    "yt_dlp": YTDLP,
    "youtube-dl": YTDLP,
    COBALT: COBALT,
    XHS: XHS,
    "xhs_get": XHS,
    "xhs-get": XHS,
    "xhsget": XHS,
    "rednote": XHS,
    "xiaohongshu": XHS,
}

_LOCAL_PROCESSING_VALUES = frozenset({"preferred", "forced"})

_ILLEGAL_FILENAME = re.compile(
    r'[\x00-\x1f\x7f<>:"/\\|?*\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]+'
)
_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)

_PACKAGE = __package__ or "url_ingest"


@dataclass(frozen=True)
class _ProviderSpec:
    id: str
    label: str
    module: str
    class_name: str
    class_aliases: tuple[str, ...]
    url_key: str


_SPECS: dict[str, _ProviderSpec] = {
    YTDLP: _ProviderSpec(
        id=YTDLP,
        label="yt-dlp",
        module=f"{_PACKAGE}.ytdlp",
        class_name="YtDlpProvider",
        class_aliases=("YtDlpProvider", "YTDLPProvider", "YtDlp"),
        url_key="",
    ),
    COBALT: _ProviderSpec(
        id=COBALT,
        label="Cobalt",
        module=f"{_PACKAGE}.cobalt",
        class_name="CobaltProvider",
        class_aliases=("CobaltProvider",),
        url_key="cobalt_url",
    ),
    XHS: _ProviderSpec(
        id=XHS,
        label="XHS / RedNote",
        module=f"{_PACKAGE}.xhs",
        class_name="XhsGetProvider",
        class_aliases=("XhsGetProvider", "XhsProvider", "XHSProvider"),
        url_key="xhs_url",
    ),
}


# ---------------------------------------------------------------------------
# URL and provider detection


def validate_url(url: Any) -> str:
    """Return a cleaned HTTP(S) URL or raise :class:`IngestError`.

    Only ``http`` and ``https`` links are accepted. Raw whitespace, control
    characters, and backslashes are rejected because they make URL parsing and
    provider detection ambiguous.
    """
    if not isinstance(url, str):
        raise IngestError("URL must be text.")
    value = url.strip()
    if not value:
        raise IngestError("URL is empty.")
    if len(value) > 8192:
        raise IngestError("URL is too long.")
    if "\\" in value:
        raise IngestError("URL contains invalid characters.")
    if any(
        character.isspace() or ord(character) < 32 or ord(character) == 127
        for character in value
    ):
        raise IngestError("URL contains spaces or control characters.")

    try:
        parts = urlsplit(value)
    except ValueError as exc:
        raise IngestError("URL could not be parsed.") from exc
    if parts.scheme.lower() not in {"http", "https"}:
        raise IngestError("URL must start with http:// or https://.")
    if not parts.netloc:
        raise IngestError("URL must include a host.")
    if parts.username is not None or parts.password is not None:
        raise IngestError("URL must not include a username or password.")
    try:
        host = parts.hostname
        parts.port  # noqa: B018 - force validation of malformed ports
    except ValueError as exc:
        raise IngestError("URL has an invalid host or port.") from exc
    if not host or host == ".":
        raise IngestError("URL must include a valid host.")
    return value


def normalize_provider_id(value: Any, *, strict: bool = False) -> str:
    """Normalize a provider setting/name to ``auto``, ``ytdlp``, ``cobalt``, or ``xhs``."""
    if value is None:
        return AUTO
    if not isinstance(value, str):
        if strict:
            raise IngestError(
                "Provider must be 'auto', 'ytdlp', 'cobalt', or 'xhs'."
            )
        return AUTO
    key = value.strip().lower()
    provider_id = _PROVIDER_ALIASES.get(key)
    if provider_id is not None:
        return provider_id
    if strict:
        raise IngestError(
            f"Unknown ingest provider {value!r}. "
            "Use 'auto', 'ytdlp', 'cobalt', or 'xhs'."
        )
    return AUTO


def _is_xhs_host(host: str) -> bool:
    host = (host or "").lower().rstrip(".")
    return any(
        host == domain or host.endswith("." + domain)
        for domain in XHS_DOMAINS
    )


def detect(url: str, override: str | None = None) -> str:
    """Return the provider id for *url*.

    RedNote/Xiaohongshu domains map to ``xhs``; every other valid HTTP(S) URL
    maps to the native ``ytdlp`` provider. Cobalt is never chosen automatically.
    An explicit provider override wins after the URL itself has been validated.
    """
    value = validate_url(url)
    if override is not None:
        provider_id = normalize_provider_id(override, strict=True)
        if provider_id != AUTO:
            return provider_id
    host = urlsplit(value).hostname or ""
    return XHS if _is_xhs_host(host) else YTDLP


# ---------------------------------------------------------------------------
# Settings normalization


def _settings_section(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    if settings is None:
        return {}
    if not isinstance(settings, Mapping):
        raise IngestError("Ingest settings must be a mapping.")
    nested = settings.get("ingest")
    if isinstance(nested, Mapping):
        return dict(nested)
    return dict(settings)


def _text(value: Any, default: str) -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _endpoint(value: Any, default: str) -> str:
    # An explicitly empty URL means "not configured"; do not silently restore
    # the default when the user clears a field in Setup.
    if value is None:
        return default
    return str(value).strip()


def _choice(value: Any, default: str, allowed: frozenset[str] | None = None) -> str:
    text = _text(value, default).lower()
    if allowed is not None and text not in allowed:
        return default
    return text


def _boolean(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip().lower()
        if not text:
            return default
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _interval(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number) or number < 0:
        return default
    return number


def normalize_settings(settings: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return ingest settings with schema defaults and safe value coercion.

    Accepts either the full application settings mapping (with an ``ingest``
    section) or the ingest section itself. Unknown keys are preserved so the
    caller can pass provider extensions such as an API key or token through to
    a concrete provider without this module needing to know about them.
    """
    raw = _settings_section(settings)
    result: dict[str, Any] = {**DEFAULT_INGEST_SETTINGS, **raw}

    result["provider"] = normalize_provider_id(result.get("provider"))
    for key in ("cobalt_url", "xhs_url"):
        result[key] = _endpoint(result.get(key), DEFAULT_INGEST_SETTINGS[key])
    result["ytdlp_quality"] = _choice(
        result.get("ytdlp_quality"), DEFAULT_INGEST_SETTINGS["ytdlp_quality"]
    )
    result["ytdlp_codec"] = _choice(
        result.get("ytdlp_codec"), DEFAULT_INGEST_SETTINGS["ytdlp_codec"]
    )
    result["ytdlp_container"] = _choice(
        result.get("ytdlp_container"), DEFAULT_INGEST_SETTINGS["ytdlp_container"]
    )
    result["ytdlp_audio"] = _choice(
        result.get("ytdlp_audio"), DEFAULT_INGEST_SETTINGS["ytdlp_audio"]
    )
    result["ytdlp_cookies"] = _choice(
        result.get("ytdlp_cookies"), DEFAULT_INGEST_SETTINGS["ytdlp_cookies"]
    )
    result["ytdlp_browser"] = _choice(
        result.get("ytdlp_browser"), DEFAULT_INGEST_SETTINGS["ytdlp_browser"]
    )
    result["ytdlp_cookie_file"] = _text(
        result.get("ytdlp_cookie_file"), DEFAULT_INGEST_SETTINGS["ytdlp_cookie_file"]
    )
    result["cobalt_fallback"] = _boolean(
        result.get("cobalt_fallback"), bool(DEFAULT_INGEST_SETTINGS["cobalt_fallback"])
    )
    result["cobalt_quality"] = _choice(
        result.get("cobalt_quality"), DEFAULT_INGEST_SETTINGS["cobalt_quality"]
    )
    result["cobalt_codec"] = _choice(
        result.get("cobalt_codec"), DEFAULT_INGEST_SETTINGS["cobalt_codec"]
    )
    result["cobalt_local_processing"] = _choice(
        result.get("cobalt_local_processing"),
        DEFAULT_INGEST_SETTINGS["cobalt_local_processing"],
        _LOCAL_PROCESSING_VALUES,
    )
    result["xhs_no_record"] = _boolean(
        result.get("xhs_no_record"), bool(DEFAULT_INGEST_SETTINGS["xhs_no_record"])
    )
    result["xhs_interval"] = _interval(
        result.get("xhs_interval"), float(DEFAULT_INGEST_SETTINGS["xhs_interval"])
    )
    return result


def options_from_settings(
    settings: Mapping[str, Any] | None = None,
    overrides: Mapping[str, Any] | IngestOptions | None = None,
) -> IngestOptions:
    """Build :class:`IngestOptions` from settings, with optional request overrides."""
    if isinstance(overrides, IngestOptions):
        return overrides
    if overrides is not None and not isinstance(overrides, Mapping):
        raise IngestError("Ingest options must be a mapping.")

    normalized = normalize_settings(settings)
    values: dict[str, Any] = {
        "quality": normalized["ytdlp_quality"],
        "codec": normalized["ytdlp_codec"],
        "container": normalized["ytdlp_container"],
        "audio": normalized["ytdlp_audio"],
        "cookies": normalized["ytdlp_cookies"],
        "browser": normalized["ytdlp_browser"],
        "cookie_file": normalized["ytdlp_cookie_file"],
        "local_processing": normalized["cobalt_local_processing"],
        "no_record": normalized["xhs_no_record"],
        "interval": normalized["xhs_interval"],
    }
    if overrides:
        if overrides.get("quality") is not None:
            values["quality"] = _choice(
                overrides["quality"], str(values["quality"])
            )
        if overrides.get("codec") is not None:
            values["codec"] = _choice(overrides["codec"], str(values["codec"]))
        for key in ("container", "audio", "cookies", "browser"):
            if overrides.get(key) is not None:
                values[key] = _choice(overrides[key], str(values[key]))
        if overrides.get("local_processing") is not None:
            values["local_processing"] = _choice(
                overrides["local_processing"], "preferred", _LOCAL_PROCESSING_VALUES
            )
        if overrides.get("no_record") is not None:
            values["no_record"] = _boolean(overrides["no_record"], True)
        if overrides.get("interval") is not None:
            values["interval"] = _interval(overrides["interval"], 12.0)
    return IngestOptions(**values)


# ---------------------------------------------------------------------------
# Provider construction


def _short_error(exc: BaseException) -> str:
    message = " ".join(str(exc).split())
    return (message or exc.__class__.__name__)[:400]


def _import_provider_module(provider_id: str) -> Any:
    spec = _SPECS.get(provider_id)
    if spec is None:
        raise IngestError(f"Unknown ingest provider {provider_id!r}.")
    return importlib.import_module(spec.module)


def _provider_class(module: Any, spec: _ProviderSpec) -> Any:
    for name in spec.class_aliases:
        candidate = getattr(module, name, None)
        if candidate is not None:
            return candidate
    raise IngestError(
        f"{spec.label} provider is unavailable: {spec.module} has no "
        f"{spec.class_name} class."
    )


def _instantiate_provider(provider_id: str, cls: Any, settings: Mapping[str, Any]) -> Any:
    spec = _SPECS[provider_id]
    try:
        signature = inspect.signature(cls)
    except (TypeError, ValueError):
        signature = None

    try:
        if signature is None:
            instance = cls(settings)
        else:
            parameters = list(signature.parameters.values())
            positional = [
                parameter
                for parameter in parameters
                if parameter.kind
                in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            ]
            has_varargs = any(
                parameter.kind is inspect.Parameter.VAR_POSITIONAL
                for parameter in parameters
            )
            keyword_settings = any(
                parameter.name == "settings"
                and parameter.kind is inspect.Parameter.KEYWORD_ONLY
                for parameter in parameters
            )
            has_varkw = any(
                parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in parameters
            )
            if positional or has_varargs:
                instance = cls(settings)
            elif keyword_settings:
                instance = cls(settings=settings)
            elif has_varkw:
                instance = cls(**settings)
            else:
                instance = cls()
    except IngestError:
        raise
    except Exception as exc:
        raise IngestError(
            f"{spec.label} provider could not be created: {_short_error(exc)}"
        ) from exc

    for attribute, value in (("id", spec.id), ("label", spec.label)):
        if not getattr(instance, attribute, ""):
            try:
                setattr(instance, attribute, value)
            except Exception:
                pass
    return instance


def provider(
    provider_id: str | None,
    settings: Mapping[str, Any] | None = None,
    *,
    url: str | None = None,
) -> Provider:
    """Construct a provider by id.

    ``provider_id=None`` or ``"auto"`` uses the ``provider`` setting; if that
    is also ``auto``, ``url`` is required so detection can choose. Missing
    provider modules raise :class:`IngestError` with an actionable message.
    """
    normalized = normalize_settings(settings)
    selected = normalize_provider_id(provider_id, strict=True)
    if selected == AUTO:
        selected = normalize_provider_id(normalized.get("provider"))
    if selected == AUTO:
        if url is None:
            raise IngestError(
                "Provider 'auto' needs a URL. Call detect(url) first, or pass url=."
            )
        selected = detect(url)

    spec = _SPECS[selected]
    try:
        module = _import_provider_module(selected)
    except Exception as exc:
        raise IngestError(
            f"{spec.label} provider is unavailable: {_short_error(exc)}"
        ) from exc
    cls = _provider_class(module, spec)
    return cast(Provider, _instantiate_provider(selected, cls, normalized))


# ---------------------------------------------------------------------------
# Setup status


def _configuration_status(
    spec: _ProviderSpec, settings: Mapping[str, Any]
) -> tuple[bool, str]:
    if not spec.url_key:
        return True, ""
    endpoint = str(settings.get(spec.url_key) or "").strip()
    if not endpoint:
        return False, f"{spec.label} URL is not set."
    try:
        validate_url(endpoint)
    except IngestError as exc:
        return False, f"{spec.label} URL is invalid: {exc}"
    return True, ""


def _custom_status(instance: Any) -> Any:
    method = getattr(instance, "status", None)
    if not callable(method):
        return None
    if getattr(method, "__func__", None) is Provider.status:
        return None
    return method


def _call_status(method: Any, settings: Mapping[str, Any]) -> Any:
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return method(settings)
    parameters = list(signature.parameters.values())
    positional = [
        parameter
        for parameter in parameters
        if parameter.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    has_varargs = any(
        parameter.kind is inspect.Parameter.VAR_POSITIONAL for parameter in parameters
    )
    if positional or has_varargs:
        return method(settings)
    settings_keyword = any(
        parameter.name == "settings"
        and parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for parameter in parameters
    )
    has_varkw = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters
    )
    if settings_keyword or has_varkw:
        return method(settings=settings)
    return method()


def _status_bool(value: Any, default: bool) -> bool:
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
    return bool(value)


def _provider_status(provider_id: str, settings: Mapping[str, Any]) -> dict[str, Any]:
    spec = _SPECS[provider_id]
    configured, configuration_error = _configuration_status(spec, settings)
    entry: dict[str, Any] = {
        "id": spec.id,
        "label": spec.label,
        "configured": configured,
        "available": False,
        "error": configuration_error,
    }

    try:
        module = _import_provider_module(provider_id)
    except Exception as exc:
        module_error = (
            f"{spec.label} provider module is unavailable ({_short_error(exc)})."
        )
        entry["error"] = " ".join(
            part for part in (configuration_error, module_error) if part
        )
        return entry

    try:
        cls = _provider_class(module, spec)
        instance = _instantiate_provider(provider_id, cls, settings)
    except IngestError as exc:
        entry["error"] = " ".join(
            part for part in (configuration_error, str(exc)) if part
        )
        return entry

    status_method = _custom_status(instance)
    if status_method is not None:
        try:
            reported = _call_status(status_method, settings)
        except Exception as exc:
            entry["error"] = " ".join(
                part
                for part in (
                    configuration_error,
                    f"{spec.label} status check failed: {_short_error(exc)}",
                )
                if part
            )
            return entry
        if not isinstance(reported, Mapping):
            entry["error"] = " ".join(
                part
                for part in (
                    configuration_error,
                    f"{spec.label} status check returned an invalid result.",
                )
                if part
            )
            return entry

        reported_configured = _status_bool(reported.get("configured"), configured)
        reported_available = _status_bool(reported.get("available"), reported_configured)
        reported_error = " ".join(str(reported.get("error") or "").split())

        # An invalid endpoint means the provider cannot be configured no matter
        # what a provider-local check says.
        if not configured:
            reported_configured = False
        if not reported_configured or reported_error:
            reported_available = False
        entry["configured"] = reported_configured
        entry["available"] = reported_available
        entry["error"] = reported_error or configuration_error
        # Keep optional diagnostics such as the yt-dlp package version. The
        # core five keys remain stable for every provider.
        version = " ".join(str(reported.get("version") or "").split())
        if version:
            entry["version"] = version[:120]
        return entry

    entry["available"] = configured
    entry["error"] = configuration_error
    return entry


def status(settings: Mapping[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Return Setup health for every provider.

    The result is keyed by provider id. Every value has the keys ``id``,
    ``label``, ``configured``, ``available``, and ``error``. A provider may add
    diagnostics such as ``version`` (yt-dlp reports its package version).
    Provider modules are optional; when one is missing its entry is simply
    unavailable with an explanation instead of raising. No sidecar service is
    contacted by this function.
    """
    normalized = normalize_settings(settings)
    return {
        provider_id: _provider_status(provider_id, normalized)
        for provider_id in PROVIDER_IDS
    }


# ---------------------------------------------------------------------------
# Filenames


def safe_filename(
    value: Any,
    fallback: str = "video",
    max_length: int = 120,
) -> str:
    """Turn remote metadata into a safe single path component.

    Removes directory separators, reserved characters, control/format
    characters, Windows reserved device names, and leading/trailing dots.
    The original extension is preserved when it is a short alphanumeric one.
    """
    try:
        max_length = int(max_length)
    except (TypeError, ValueError):
        max_length = 120
    max_length = max(8, max_length)

    raw = "" if value is None else str(value)
    name = _ILLEGAL_FILENAME.sub("_", raw)
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"\.{2,}", "_", name)
    name = re.sub(r"_+", "_", name).strip(" ._")

    if not name:
        name = _ILLEGAL_FILENAME.sub("_", str(fallback or "video"))
        name = re.sub(r"\s+", " ", name).strip(" ._")
        if not name:
            name = "video"

    suffix = ""
    dot = name.rfind(".")
    if 0 < dot < len(name) - 1:
        candidate = name[dot:]
        if len(candidate) <= 16 and re.fullmatch(r"\.[A-Za-z0-9]{1,15}", candidate):
            suffix = candidate
            name = name[:dot]

    if name.lower() in _WINDOWS_RESERVED:
        name = "_" + name

    if suffix:
        room = max_length - len(suffix)
        if room < 1:
            suffix = ""
            room = max_length
        name = name[:room].rstrip(" ._") or "video"
        return (name + suffix)[:max_length]
    return name[:max_length].rstrip(" ._") or "video"


# Convenience aliases used by the API layer.
sanitize_filename = safe_filename
validate_ingest_url = validate_url
normalize_ingest_settings = normalize_settings
ingest_options = options_from_settings
