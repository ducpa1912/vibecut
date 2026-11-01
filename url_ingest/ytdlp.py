"""Native yt-dlp ingest provider.

This is a clean-room Python integration using the public ``yt-dlp`` package
(Unlicense). It does not import, call, or copy xhs_get code, and it never
starts a subprocess.

The provider resolves one URL (or a playlist), downloads the selected video
into a VibeCut job temp path, and returns metadata. Playlist links return a
picker list; the client submits the chosen entry URL as a normal single-video
job.

All network work goes through ``yt_dlp.YoutubeDL`` so cookies, impersonation,
extractor updates, and fragment downloads behave exactly like the upstream
Python API.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from urllib.parse import urlsplit

from .base import IngestError, IngestOptions, IngestResult, ProgressCallback, Provider
from .rednote import NOTE_HOSTS, SHORT_HOSTS, prepare_rednote_url
from .registry import safe_filename

PROVIDER_ID = "ytdlp"
PROVIDER_LABEL = "yt-dlp"

_VIDEO_SUFFIXES = frozenset(
    {".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi", ".flv", ".ts"}
)
_AUDIO_SUFFIXES = frozenset({".m4a", ".mp3", ".opus", ".ogg", ".wav", ".flac"})
_REDNOTE_HOSTS = frozenset(
    host for host in NOTE_HOSTS | SHORT_HOSTS
    if not host.startswith("www.")
)
_QUALITY_LIMITS: dict[str, int | None] = {
    "max": None,
    "4320": 4320,
    "2160": 2160,
    "1440": 1440,
    "1080": 1080,
    "720": 720,
    "480": 480,
    "360": 360,
    "240": 240,
    "144": 144,
}
_CONTAINERS = frozenset({"mp4", "mkv", "webm"})
_CODECS = frozenset({"h264", "any"})
_AUDIO_CHOICES = frozenset({"best", "320", "192", "128"})
_COOKIE_MODES = frozenset({"none", "browser", "file"})
_PLAYLIST_TYPES = frozenset({"playlist", "multi_video"})
_MAX_PLAYLIST_CHOICES = 200


class _Cancelled(IngestError):
    """Internal signal used by the yt-dlp progress hook."""


def _module():
    try:
        import yt_dlp  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        raise IngestError(
            "yt-dlp is not installed. Install the yt-dlp Python package."
        ) from exc
    return yt_dlp


def _prepare_rednote(url: str):
    """Normalize RedNote links only; leave every other site untouched."""
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    if host not in _REDNOTE_HOSTS:
        return None
    return prepare_rednote_url(url)


def ytdlp_available() -> bool:
    """Return whether the yt-dlp Python package can be imported."""
    try:
        _module()
        return True
    except IngestError:
        return False


def _version(yt_dlp: Any) -> str:
    version = getattr(getattr(yt_dlp, "version", None), "__version__", "")
    if not version:
        try:
            from importlib import metadata  # noqa: PLC0415

            version = metadata.version("yt-dlp")
        except Exception:  # noqa: BLE001 - version is diagnostic only
            version = ""
    return str(version or "")


def _setting(settings: Mapping[str, Any], key: str, default: Any) -> Any:
    nested = settings.get("ingest")
    if isinstance(nested, Mapping) and nested.get(key) is not None:
        return nested.get(key)
    return settings.get(key, default)


def _option_text(options: IngestOptions | None, attribute: str) -> str:
    if options is None:
        return ""
    return str(getattr(options, attribute, "") or "").strip().lower()


def _quality(options: IngestOptions, settings: Mapping[str, Any]) -> str:
    value = _option_text(options, "quality") or str(
        _setting(settings, "ytdlp_quality", "max")
    ).lower()
    return value if value in _QUALITY_LIMITS else "max"


def _codec(options: IngestOptions, settings: Mapping[str, Any]) -> str:
    value = _option_text(options, "codec") or str(
        _setting(settings, "ytdlp_codec", "h264")
    ).lower()
    return value if value in _CODECS else "h264"


def _container(options: IngestOptions, settings: Mapping[str, Any]) -> str:
    value = _option_text(options, "container") or str(
        _setting(settings, "ytdlp_container", "mp4")
    ).lower()
    return value if value in _CONTAINERS else "mp4"


def _audio(options: IngestOptions, settings: Mapping[str, Any]) -> str:
    value = _option_text(options, "audio") or str(
        _setting(settings, "ytdlp_audio", "best")
    ).lower()
    return value if value in _AUDIO_CHOICES else "best"


def _cookie_config(
    options: IngestOptions | None, settings: Mapping[str, Any]
) -> tuple[str, str, str]:
    """Return ``(mode, browser, cookie_file)`` from options then settings.

    Cookie choice is provider configuration, so a saved browser/file setting
    still applies when a caller passes a fresh ``IngestOptions()``. A non-empty
    option mode overrides the saved setting.
    """
    option_mode = _option_text(options, "cookies")
    setting_mode = str(_setting(settings, "ytdlp_cookies", "none") or "none").lower()
    mode = option_mode if option_mode not in {"", "none"} else setting_mode
    option_browser = _option_text(options, "browser")
    setting_browser = str(
        _setting(settings, "ytdlp_browser", "safari") or "safari"
    ).lower()
    browser = (
        option_browser
        if option_browser and option_browser != "safari"
        else setting_browser
    )
    cookie_file = str(getattr(options, "cookie_file", "") or "").strip()
    if not cookie_file:
        cookie_file = str(_setting(settings, "ytdlp_cookie_file", "") or "").strip()

    if mode not in _COOKIE_MODES:
        mode = "none"
    if mode == "file":
        if not cookie_file:
            raise IngestError(
                "Choose a cookies.txt file in Setup, or use browser cookies."
            )
        path = Path(cookie_file).expanduser()
        if not path.is_file():
            raise IngestError("The configured yt-dlp cookies.txt file does not exist.")
        return mode, browser, str(path)
    return mode, browser, ""


def _cookies(settings: Mapping[str, Any]) -> tuple[str, str, str]:
    """Backward-compatible settings-only view of :func:`_cookie_config`."""
    return _cookie_config(None, settings)


def _format_selector(options: IngestOptions, settings: Mapping[str, Any]) -> str:
    """Build a quality-first, h264/mp4-first selector with safe fallbacks."""
    limit = _QUALITY_LIMITS.get(_quality(options, settings))
    height = "" if limit is None else f"[height<={limit}]"

    audio_mode = _audio(options, settings)
    audio_limit = "" if audio_mode == "best" else f"[abr<={audio_mode}]"
    # Keep the audio alternatives inside parentheses. Without grouping, a
    # slash would be parsed as a top-level fallback and could select audio-only.
    audio = f"(bestaudio[ext=m4a]{audio_limit}/bestaudio{audio_limit})"

    if _codec(options, settings) == "h264":
        preferred = f"bestvideo*[vcodec^=avc1][ext=mp4]{height}"
        branches = [
            f"{preferred}+{audio}",
            f"bestvideo*[vcodec^=avc1]{height}+{audio}",
        ]
    else:
        branches = [f"bestvideo*[ext=mp4]{height}+{audio}"]

    branches.extend(
        (
            f"bestvideo*{height}+{audio}",
            f"best[ext=mp4]{height}",
            f"best{height}",
        )
    )
    return "/".join(branches)


def _merge_output_format(options: IngestOptions, settings: Mapping[str, Any]) -> str:
    """Prefer the requested container, but let yt-dlp fall back to mkv.

    yt-dlp respects only the listed extensions when choosing a merge container.
    Listing mkv as a fallback prevents an mp4-only request from forcing an
    incompatible codec pair into mp4.
    """
    container = _container(options, settings)
    if container == "mp4":
        return "mp4/mkv"
    return f"{container}/mkv" if container != "mkv" else "mkv"


def _base_options(
    options: IngestOptions, settings: Mapping[str, Any]
) -> dict[str, Any]:
    mode, browser, cookie_file = _cookie_config(options, settings)
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "no_color": True,
        "noplaylist": True,
        "ignoreerrors": False,
        "retries": 2,
        "fragment_retries": 2,
        "socket_timeout": 30,
        "concurrent_fragment_downloads": 4,
        "format": _format_selector(options, settings),
        "merge_output_format": _merge_output_format(options, settings),
        "overwrites": True,
        "windowsfilenames": True,
        # A stale .part file from a different URL must never be resumed.
        "continuedl": False,
    }
    if mode == "file":
        opts["cookiefile"] = cookie_file
    elif mode == "browser":
        opts["cookiesfrombrowser"] = (browser,)
    return opts


def _error_text(exc: BaseException) -> str:
    text = " ".join(str(exc).split())
    if not text:
        return exc.__class__.__name__
    lowered = text.lower()
    if "private" in lowered:
        return "This video is private."
    if ("age" in lowered and ("gate" in lowered or "restrict" in lowered)) or (
        "confirm your age" in lowered
    ):
        return "This video is age-gated. Add cookies in Setup."
    if "login" in lowered or "sign in" in lowered or "cookies" in lowered:
        return "This video needs a signed-in session. Add cookies in Setup."
    if "unsupported" in lowered:
        return "yt-dlp does not support this URL."
    if "geo" in lowered and ("restrict" in lowered or "block" in lowered):
        return "This video is region-restricted."
    if "http error 404" in lowered or "not found" in lowered:
        return "The video was not found."
    if "drm" in lowered or "protected" in lowered:
        return "This video is DRM-protected and cannot be downloaded."
    if "ffmpeg" in lowered and (
        "not installed" in lowered or "not found" in lowered
    ):
        return "ffmpeg is required to merge this video, but it was not found."
    if "timed out" in lowered or "timeout" in lowered:
        return "The video site timed out. Try again."
    return text[:400]


def _entry_url(entry: Mapping[str, Any]) -> str:
    candidate = str(
        entry.get("webpage_url") or entry.get("original_url") or entry.get("url") or ""
    ).strip()
    if candidate.lower().startswith(("http://", "https://")):
        return candidate
    return ""


def _choice_thumbnail(entry: Mapping[str, Any]) -> str | None:
    thumbnail = entry.get("thumbnail")
    if isinstance(thumbnail, str) and thumbnail:
        return thumbnail
    thumbnails = entry.get("thumbnails")
    if isinstance(thumbnails, list):
        for item in reversed(thumbnails):
            if isinstance(item, Mapping):
                url = item.get("url")
                if isinstance(url, str) and url:
                    return url
    return None


def _choice(entry: Mapping[str, Any], index: int) -> dict[str, Any]:
    return {
        "id": str(entry.get("id") or index),
        "title": str(entry.get("title") or entry.get("id") or f"Item {index + 1}"),
        "url": _entry_url(entry),
        "duration": entry.get("duration"),
        "thumbnail": _choice_thumbnail(entry),
        "uploader": str(entry.get("uploader") or entry.get("channel") or ""),
    }


def _info_without_video(info: Mapping[str, Any]) -> bool:
    """Return True only when yt-dlp explicitly says there is no video stream."""
    if str(info.get("vcodec") or "").lower() == "none":
        return True
    formats = info.get("formats")
    if not isinstance(formats, list) or not formats:
        return False
    explicit_audio_only = True
    for item in formats:
        if not isinstance(item, Mapping):
            continue
        codec = str(item.get("vcodec") or "").lower()
        if codec and codec != "none":
            return False
        if codec != "none":
            # A direct MP4 / generic format may omit vcodec entirely. That is
            # unknown, not proof of an audio-only result.
            explicit_audio_only = False
        if str(item.get("video_ext") or "").lower() not in {"", "none"}:
            explicit_audio_only = False
    return explicit_audio_only


def _output_root(dest: Path) -> Path:
    root = dest.parent.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _output_base(dest: Path) -> str:
    """Return the safe, extension-free output stem for *dest*."""
    return safe_filename(dest.stem or "url-video", "url-video").replace("%", "_")


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _find_download(
    dest: Path,
    info: Mapping[str, Any] | None = None,
    *,
    root: Path | None = None,
) -> Path | None:
    """Find the file yt-dlp produced for *dest*.

    Only regular, non-empty video or audio files under *root* are eligible.
    Video files win over audio files when yt-dlp reports both merge inputs.
    """
    output_root = (root or dest.parent).resolve()
    candidates: list[Path] = []

    def add(candidate: Path | None) -> None:
        if candidate is None:
            return
        path = Path(candidate)
        if not path.is_absolute():
            path = output_root / path
        if not path.is_file() or path.stat().st_size <= 0:
            return
        if path.suffix.lower() not in _VIDEO_SUFFIXES | _AUDIO_SUFFIXES:
            return
        if not _inside(path, output_root):
            return
        if path not in candidates:
            candidates.append(path)

    add(dest)
    reported = (info or {})
    for item in reported.get("requested_downloads") or []:
        if isinstance(item, Mapping):
            add(Path(str(item["filepath"])) if item.get("filepath") else None)
    for key in ("filepath", "_filename"):
        value = reported.get(key)
        if value:
            add(Path(str(value)))

    prefix = f"{_output_base(dest)}."
    for path in sorted(
        output_root.glob(f"{prefix}*"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    ):
        add(path)

    videos = [path for path in candidates if path.suffix.lower() in _VIDEO_SUFFIXES]
    return (videos or candidates or [None])[0]


def _remove_partials(dest: Path, root: Path, keep: set[Path]) -> None:
    """Remove failed yt-dlp fragments without touching pre-existing files."""
    try:
        paths = list(root.glob(f"{_output_base(dest)}.*"))
    except OSError:
        paths = []
    if dest.is_file():
        paths.append(dest)
    for path in paths:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in keep or not path.is_file():
            continue
        if not _inside(path, root):
            continue
        try:
            path.unlink()
        except OSError:
            pass


class YtDlpProvider(Provider):
    id = PROVIDER_ID
    label = PROVIDER_LABEL
    required_settings = ()

    def _settings(self, extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
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

    def status(self, settings: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Report package health without contacting any network service."""
        merged = self._settings(settings)
        try:
            yt_dlp = _module()
        except IngestError as exc:
            return {
                "id": self.id,
                "label": self.label,
                "configured": False,
                "available": False,
                "error": str(exc),
                "version": "",
            }
        error = ""
        try:
            _cookie_config(None, merged)
        except IngestError as exc:
            error = str(exc)
        return {
            "id": self.id,
            "label": self.label,
            "configured": True,
            "available": not error,
            "error": error,
            "version": _version(yt_dlp),
        }

    def inspect(self, url: str, options: IngestOptions) -> dict[str, Any]:
        yt_dlp = _module()
        prepared = _prepare_rednote(url)
        if prepared is not None:
            url = prepared.url
        settings = self._settings()
        opts = _base_options(options, settings)
        opts.update(
            {
                "skip_download": True,
                "extract_flat": "in_playlist",
                # Inspect playlists too, even when a video URL also has a list.
                "noplaylist": False,
                # Do not resolve a 2,000-item playlist just to show 200 choices.
                "playlistend": _MAX_PLAYLIST_CHOICES + 1,
            }
        )
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as exc:  # noqa: BLE001
            raise IngestError(
                f"yt-dlp could not inspect this link: {_error_text(exc)}"
            ) from exc
        if not isinstance(info, Mapping):
            raise IngestError("yt-dlp returned no video information.")

        if str(info.get("_type") or "") in _PLAYLIST_TYPES:
            entries = [
                entry for entry in (info.get("entries") or []) if isinstance(entry, Mapping)
            ]
            choices: list[dict[str, Any]] = []
            for index, entry in enumerate(entries):
                choice = _choice(entry, index)
                if choice.get("url"):
                    choices.append(choice)
                if len(choices) >= _MAX_PLAYLIST_CHOICES:
                    break
            if not choices:
                raise IngestError("This playlist has no selectable videos.")
            warning = "This link contains multiple videos. Choose one to continue."
            if len(entries) > len(choices):
                warning = (
                    "This link contains multiple videos. "
                    f"Showing the first {len(choices)} choices."
                )
            if prepared is not None and prepared.warning:
                warning = f"{prepared.warning} {warning}"
            return {
                "provider": self.id,
                "label": self.label,
                "status": "picker",
                "available": True,
                "needs_choice": True,
                "title": str(info.get("title") or "Playlist"),
                "warning": warning,
                "choices": choices,
                "options": options.as_dict(),
            }

        if _info_without_video(info):
            raise IngestError("This link is audio-only; VibeCut needs a video file.")

        return {
            "provider": self.id,
            "label": self.label,
            "status": "video",
            "available": True,
            "title": str(info.get("title") or ""),
            "filename": str(info.get("title") or ""),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "uploader": str(info.get("uploader") or info.get("channel") or ""),
            "webpage_url": str(info.get("webpage_url") or url),
            **(
                {
                    "warning": prepared.warning,
                    "meta": {
                        "rednote_short_link": bool(prepared.was_short_link),
                        "cookies_may_be_needed": bool(prepared.cookies_may_be_needed),
                        "note_url": str(info.get("webpage_url") or url),
                    },
                }
                if prepared is not None else {}
            ),
            "options": options.as_dict(),
        }

    def download(
        self,
        url: str,
        dest: Path,
        options: IngestOptions,
        progress: ProgressCallback,
        cancel_event: threading.Event,
    ) -> IngestResult:
        yt_dlp = _module()
        prepared = _prepare_rednote(url)
        if prepared is not None:
            url = prepared.url
        settings = self._settings()
        dest = Path(dest).expanduser()
        root = _output_root(dest)
        if cancel_event.is_set():
            raise IngestError("Download cancelled.")

        base = safe_filename(dest.stem or "url-video", "url-video").replace("%", "_")
        target_name = f"{base}.%(ext)s"
        existing: set[Path] = set()
        for path in root.glob(f"{base}.*"):
            try:
                existing.add(path.resolve())
            except OSError:
                pass
        if dest.is_file():
            existing.add(dest.resolve())

        # Escape literal percent signs in the parent path: yt-dlp treats the
        # output template as a Python format string.
        root_template = str(root).replace("%", "%%")
        opts = _base_options(options, settings)
        opts.update(
            {
                "outtmpl": {"default": f"{root_template}/{target_name}"},
                "noplaylist": True,
                "progress_hooks": [],
            }
        )

        def hook(data: Mapping[str, Any]) -> None:
            if cancel_event.is_set():
                raise _Cancelled("Download cancelled.")
            status = str(data.get("status") or "")
            if status == "downloading":
                total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                downloaded = data.get("downloaded_bytes") or 0
                try:
                    fraction = float(downloaded) / float(total) if total else 0.0
                except (TypeError, ValueError, ZeroDivisionError):
                    fraction = 0.0
                detail = f"{float(downloaded) / (1024 * 1024):.1f} MB"
                if total:
                    detail += f" / {float(total) / (1024 * 1024):.1f} MB"
                progress(min(0.94, 0.02 + 0.92 * fraction), f"Downloading {detail}")
            elif status == "finished":
                progress(0.96, "Download finished; preparing video")

        opts["progress_hooks"] = [hook]
        progress(0.01, "Asking yt-dlp for the video")
        info: Mapping[str, Any] | None = None
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
            if cancel_event.is_set():
                raise _Cancelled("Download cancelled.")
            if not isinstance(info, Mapping):
                raise IngestError("yt-dlp returned no downloaded video.")
            if str(info.get("_type") or "") in _PLAYLIST_TYPES:
                raise IngestError(
                    "This link contains multiple videos. Choose one to continue."
                )
            if _info_without_video(info):
                raise IngestError(
                    "This link is audio-only; VibeCut needs a video file."
                )
            path = _find_download(dest, info, root=root)
            if path is None:
                raise IngestError("yt-dlp finished but no video file was produced.")
            if path.suffix.lower() in _AUDIO_SUFFIXES:
                raise IngestError(
                    "This link is audio-only; VibeCut needs a video file."
                )
            progress(1.0, "Download complete")
            title = str(info.get("title") or path.stem).strip() or path.stem
            display_name = safe_filename(
                f"{title}{path.suffix}", f"url-video{path.suffix}"
            )
            return IngestResult(
                path=path,
                filename=display_name,
                provider=self.id,
                title=title,
                duration=info.get("duration"),
                thumbnail=info.get("thumbnail"),
                meta={
                    "uploader": str(info.get("uploader") or info.get("channel") or ""),
                    "webpage_url": str(info.get("webpage_url") or url),
                    "extractor": str(info.get("extractor") or ""),
                    "quality": _quality(options, settings),
                    "container": _container(options, settings),
                    "codec": _codec(options, settings),
                    "audio": _audio(options, settings),
                    **(
                        {
                            "note_url": str(info.get("webpage_url") or url),
                            "rednote_short_link": bool(prepared.was_short_link),
                            "cookies_may_be_needed": bool(prepared.cookies_may_be_needed),
                        }
                        if prepared is not None else {}
                    ),
                },
            )
        except _Cancelled as exc:
            _remove_partials(dest, root, existing)
            raise IngestError("Download cancelled.") from exc
        except IngestError:
            _remove_partials(dest, root, existing)
            raise
        except Exception as exc:  # noqa: BLE001
            _remove_partials(dest, root, existing)
            raise IngestError(
                f"yt-dlp download failed: {_error_text(exc)}"
            ) from exc
