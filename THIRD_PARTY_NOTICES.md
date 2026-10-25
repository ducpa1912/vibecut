# Third-party notices

VibeCut is proprietary software. The components below remain under their own
licenses. This file is a release checklist entry point, not legal advice.
Resolve exact versions and full license texts from the release environment; see
[docs/licensing.md](docs/licensing.md).

## Runtime Python packages

| Component | License | Upstream |
|---|---|---|
| FastAPI | MIT | https://github.com/fastapi/fastapi |
| Uvicorn | BSD-3-Clause | https://github.com/encode/uvicorn |
| python-multipart | Apache-2.0 | https://github.com/Kludex/python-multipart |
| NumPy | BSD-3-Clause and bundled permissive notices | https://numpy.org |
| Pillow | MIT-CMU (HPND) | https://python-pillow.org |
| yt-dlp | Unlicense | https://github.com/yt-dlp/yt-dlp |

yt-dlp is the default URL downloader and is used through its public Python API.
A copy of the Unlicense text must be included in release artifacts. No
attribution is required by the Unlicense, but the inventory should still list
the installed version.

## System dependencies

- **ffmpeg / ffprobe** — a user-installed system dependency by default. Its
  license depends on the build. A Homebrew build with `--enable-gpl` and
  `--enable-version3` is GPL-3.0-or-later; do not bundle it without the
  corresponding notices and source or written offer.
- **Apple Vision / Speech / AVFoundation** — used through macOS frameworks.
  Apple SDK binaries are not redistributed with VibeCut.
- **swiftc / Xcode Command Line Tools** — used on the user's machine to build
  the Vision helper. Do not redistribute the toolchain.

## Optional external sidecars

Cobalt and xhs_get are not part of the proprietary VibeCut source tree or
default artifact. If a distribution ships them alongside VibeCut, keep them in
separate artifacts and comply with their licenses:

- **Cobalt API** — AGPL-3.0. Provide corresponding source or a written offer
  valid for three years, plus the license text and modification status.
- **Cobalt web UI/assets** — CC-BY-NC-SA-4.0 with branding excluded. Do not use
  Cobalt marks as VibeCut branding.
- **xhs_get** — GPL-3.0. Provide corresponding source or a written offer and the
  license text. Keep its cookies and session inside its own process.

No Cobalt or xhs_get source, comments, tests, or assets are copied into the
VibeCut URL-ingest modules. The integration is HTTP-only.
