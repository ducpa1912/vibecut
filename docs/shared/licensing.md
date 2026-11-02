# Licensing and distribution · proprietary build

VibeCut is closed-source and proprietary. This document is an engineering
release checklist, not legal advice. Review it with counsel before shipping a
paid or publicly distributed build.

The URL-ingest design keeps every strong-copyleft downloader at arm's length:
yt-dlp runs in-process under the Unlicense, while xhs_get is an optional,
unmodified, separate process that VibeCut only calls over HTTP.

## 1. Product position

- VibeCut source, UI, model prompts and build scripts are proprietary. No
  open-source license is granted for them.
- Add a written proprietary EULA or license file before any distribution. Do
  not ship with no license file: default copyright reserves all rights, but a
  written agreement is still needed for a clean commercial release.
- Third-party components keep their own licenses. VibeCut's proprietary terms
  cannot override them.
- Every release artifact must include the notices described in section 5.
- Redistributing a sidecar is optional and is a separate compliance event.
  The default build does not include xhs_get.

## 2. Dependency inventory

### Runtime Python (requirements.txt)

| Component | Declared | Role | License | Notes |
|---|---|---|---|---|
| Python | 3.11+ | Runtime | PSF-2.0 | Dockerfile pins 3.11; CI uses 3.11. |
| fastapi | `>=0.110` | HTTP API | MIT | |
| uvicorn[standard] | `>=0.27` | ASGI server | BSD-3-Clause | `uvloop`/`httptools` extras carry their own permissive licenses. |
| python-multipart | `>=0.0.9` | Upload forms | Apache-2.0 | |
| numpy | `>=1.26` | Analysis math | BSD-3-Clause (bundled components also 0BSD, MIT, Zlib, CC0) | License expression varies by release; record the installed expression. |
| pillow | `>=10.0` | Thumbnails/images | MIT-CMU (HPND) | |
| yt-dlp | `>=2025.10.22` | Default URL ingest | Unlicense | Public Python API only. Keep current; extractors change often. |
| python-stretch (optional) | `>=0.3.1` | Signalsmith Stretch binding | MIT | Optional voice-fit backend; `requirements-optional.txt`. |
| Signalsmith Stretch (optional) | via python-stretch | Pitch/time stretch | MIT | Vendored inside the python-stretch wheel; keep the MIT notice. |
| STTN fill weights (optional) | AI text fill | MIT (STTN); Apache-2.0 for the subtitle-tuned variant | Not bundled. User installs `sttn_infer_model.pth`; include the STTN and variant notices if distributed. |
| LaMa ONNX fill weights (optional) | AI text fill | Apache-2.0 | Not bundled. User installs `lama_fp32.onnx`; include the Apache-2.0 notice if distributed. |

All direct requirements above are permissive or public-domain dedications; none
is GPL or AGPL. The audit script checks both the requirement names and the
installed package metadata. Copyleft packages can still appear in a developer
environment through optional engines (see below), so run the gate in the clean
release venv.

### System dependencies

| Component | Role | License | Distribution rule |
|---|---|---|---|
| ffmpeg / ffprobe | Probe, cut, merge, render | LGPL-2.1-or-later by default; GPL-2.0-or-later or GPL-3.0-or-later when built with `--enable-gpl` (Homebrew builds commonly do; check `ffmpeg -version`) | Treat as a user-installed system dependency. If you bundle a binary, include its license, exact build configuration, and source or a written offer valid for three years. The provided Dockerfile installs Debian ffmpeg, so distributing that image counts as binary distribution. |
| macOS Vision / Speech / AVFoundation | OCR, speech, media | Apple SDK and OS terms | Used through OS frameworks; not redistributed. Do not ship Apple SDK binaries. |
| `swiftc` / Xcode Command Line Tools | Builds Vision helper on first use | Apple license | Build on the user's machine; do not redistribute the toolchain. |
| DejaVu fonts (Docker image) | Caption fallback | Bitstream Vera / Arev permissive | Include font notices if the Docker image is distributed. |

Record the exact ffmpeg build in the release SBOM:

```bash
ffmpeg -version | sed -n '1,3p' > sbom/ffmpeg.txt
ffmpeg -L >> sbom/ffmpeg.txt
```

If the configuration line contains `--enable-gpl`, that binary is GPL. A
Homebrew ffmpeg with `--enable-gpl --enable-version3` is GPL-3.0-or-later.

### Optional sidecars (never bundled by default)

| Component | Role | License | Boundary |
|---|---|---|---|
| xhs_get | Optional RedNote/Xiaohongshu note downloader | GPL-3.0 | Separate self-hosted service. Cookie and session stay inside xhs_get. |

### Optional local engines and models (outside URL ingest)

These are not in `requirements.txt`. They are installed by the user or by
optional extras, and they are the most likely source of copyleft in a build.

| Component | License | Release handling |
|---|---|---|
| piper-tts | GPL-3.0-or-later | Optional CLI/subprocess engine. Do not bundle in the proprietary installer without GPL compliance review. `phonemizer` may arrive as a transitive GPL package. |
| phonemizer | GPL-3.0-or-later | Same as piper; audit flag. |
| espeak-ng | GPL-3.0-or-later | System library used by Piper and the Kokoro worker. Dynamic loading still needs review before bundling. |
| minisbd | AGPL-3.0 | Audit flag in some environments; not declared by VibeCut. Keep out of release artifacts. |
| kokoro-onnx / Kokoro-82M | MIT package / Apache-2.0 weights | Verify model card at release. |
| python-stretch / Signalsmith Stretch | MIT | Optional voice-fit backend; include the MIT notice if installed. |
| mlx-whisper / Whisper weights | MIT | Verify model card at release. |
| Demucs | MIT | Verify at release. |
| stable-audio-tools | MIT | Package metadata may report `UNKNOWN`; include the upstream license text. |
| Stable Audio Open weights | Stability AI Community License | Commercial-use threshold applies; review before shipping weights. |
| MusicGen weights | CC-BY-NC-4.0 | Non-commercial weights; do not bundle in a paid build. |
| MiniMax / OpenRouter / OpenCode | Commercial API terms | No model weights are redistributed; keys stay local. |

## 3. Clean-room boundary

Rules for every contributor and release:

1. yt-dlp is the only downloader library linked into VibeCut. It is imported
   as the public `yt_dlp` package and is licensed under the Unlicense.
2. `url_ingest/xhs.py` is an original HTTP client. It may use public API
   documentation and observed HTTP behavior. It must not import, vendor, copy,
   or translate source from xhs_get.
3. Do not paste AGPL/GPL code, comments, tests, or assets into VibeCut. Record
   provenance in the commit message when behavior is derived from upstream
   documentation.
4. Do not add xhs_get as a git submodule, Python dependency, npm package,
   Docker layer, or app-bundle resource.
6. Do not add DRM removal, paywall bypass, private-content access, or
   credential harvesting. Cookies are user-supplied and only used to reach
   content the user can already access.
7. VibeCut must stay fully functional for common URLs with no Node, Docker or
   xhs_get installed.
8. Run the release gate before tagging. It fails on GPL/AGPL direct
   requirements, sidecar module imports, vendored sidecar paths, and an
   installed yt-dlp below the documented floor.

```bash
python3 scripts/check_proprietary_deps.py
```

Evidence to keep with the release: audit output, `pip freeze`, license
inventory, ffmpeg version block, and the artifact file list.

## 4. Optional sidecar distribution rules

The safe default is: do not distribute xhs_get. Tell users how to run it
separately, as `docs/shared/url-ingest.md` does.

If a build intentionally ships a sidecar, all of the following apply:

- **Separate process and artifact.** Put the sidecar in its own directory,
  archive, container, or installer step. Do not place its code inside the
  VibeCut `.app`, Python wheel, PyInstaller bundle, or main Docker image.
- **Separate source.** Ship the exact corresponding source, or a written offer
  valid for at least three years, with the same version and build scripts.
  AGPL-3.0 also requires a source offer to users who interact with a modified
  instance over a network (section 13).
- **License text.** Include `GPL-3.0.txt` for xhs_get, plus any upstream
  NOTICE/README attribution.
- **Modifications.** State whether the sidecar is unmodified. Publish patches
  or a source diff if it is modified.
- **No extra restrictions.** Do not add terms that forbid reverse engineering
  or redistribution of the sidecar beyond what GPL/AGPL allows.
- **Branding.** Do not imply VibeCut is endorsed by xhs_get. Do not ship
  xhs_get UI assets, logos, or naming in a commercial package.
- **No user data.** Never ship cookies, sessions, tokens, logs, or downloaded
  media with the sidecar.
- **Container notices.** A sidecar Docker image also distributes a base image,
  Debian packages, and often ffmpeg. Include those notices and source offers.
- **Independence review.** Keep the integration at documented HTTP endpoints.
  No shared memory, no linked libraries, no copied internal headers.

Suggested notice block:

```text
This distribution includes xhs_get <version>, licensed under GPL-3.0.
Source: <source archive or URL>
Written offer: <contact>, valid for three years from distribution.
License text: LICENSES/GPL-3.0.txt
Modifications: none
```

Use the same pattern for xhs_get with GPL-3.0.

## 5. Third-party notices checklist

Ship these at the root of every artifact:

- [ ] `LICENSE` or `EULA` with the proprietary VibeCut terms.
- [ ] `THIRD_PARTY_NOTICES.md` with one entry per component.
- [ ] `LICENSES/` containing the full license text for every non-permissive
      component, and for permissive components where attribution is required.
- [ ] `sbom/python-packages.json` and `sbom/python-freeze.txt`.
- [ ] `sbom/ffmpeg.txt` when ffmpeg is bundled or its version is pinned.

Each notice entry records:

| Field | Example |
|---|---|
| Name | yt-dlp |
| Version | 2026.10.21 |
| License (SPDX) | Unlicense |
| Copyright | yt-dlp contributors |
| Upstream | https://github.com/yt-dlp/yt-dlp |
| Modified? | No |
| License text | `LICENSES/Unlicense.txt` |

Additional rules:

- yt-dlp is Unlicense: no attribution is required, but list it anyway so the
  inventory is complete. Include the Unlicense text.
- If ffmpeg is not shipped, say "ffmpeg is a user-installed system dependency"
  in the README and installer. Do not imply it is included.
- If ffmpeg is shipped, include the exact `--enable-gpl`/`--enable-version3`
  state, the license text, and the source or written offer.
- Frozen Python apps (PyInstaller, py2app, zipapp) must include the license
  files of every bundled wheel, including transitive dependencies. Use
  `pip-licenses --with-license-file` and copy the referenced files.
- Docker images distribute the base image and apt packages. Generate a package
  list (`dpkg-query -W`) and include Debian/ffmpeg/font notices.
- Model weights are separate works. List the model license and source, not
  just the Python package license.
- Show the yt-dlp version in Setup or About so support can correlate extractor
  failures with a version.

## 6. SBOM and license audit commands

Run in a clean release virtual environment, not a developer environment with
optional engines installed.

```bash
python3.11 -m venv .venv-release
. .venv-release/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pip-licenses

python -m pip show yt-dlp
ffmpeg -version | sed -n '1,3p'

python scripts/check_proprietary_deps.py
mkdir -p sbom
python -m pip freeze > sbom/python-freeze.txt
pip-licenses --format=json --with-license-file --with-urls \
  --output-file sbom/python-packages.json
pip-licenses --format=markdown --with-urls \
  --output-file sbom/python-packages.md
pip-licenses --summary
```

Coarse copyleft gate (review any LGPL false positives; the audit script is the
authoritative per-package check):

```bash
pip-licenses --partial-match \
  --fail-on "AGPL;GNU Affero General Public License;GNU General Public License;GPL-3.0;GPL-2.0"
```

`pip-licenses` reports `UNKNOWN` when a package ships no usable metadata. Open
the package's `LICENSE`/`COPYING` file, record the real license in the notices,
and do not ship until it is resolved.

To check the whole installed environment, not only direct requirements:

```bash
python scripts/check_proprietary_deps.py --all
```

A developer machine may legitimately contain optional GPL engines such as
`piper-tts`, `phonemizer`, or `minisbd`. That is why the clean release venv is
the gate: those packages must not be copied into the artifact.

## 7. Release checklist

Copy this into the release ticket and attach evidence.

- [ ] Version and changelog updated; no debug flags or test data in the build.
- [ ] Clean Python 3.11+ virtual environment; `pip install -r requirements.txt`
      succeeds from scratch.
- [ ] `python -m pip show yt-dlp` meets the `requirements.txt` floor; record the
      version.
- [ ] `ffmpeg -version` and `ffmpeg -L` recorded; GPL/LGPL state understood.
- [ ] `python scripts/check_proprietary_deps.py --all` passes in the clean
      release environment.
- [ ] `pip-licenses` inventory generated; every `UNKNOWN`, GPL, and AGPL row
      resolved or removed from the artifact.
- [ ] `THIRD_PARTY_NOTICES.md`, `LICENSES/`, and the proprietary EULA included.
- [ ] Artifact contains no `xhs_get/`, `node_modules/`, sidecar container, or
      copied upstream source.
- [ ] Artifact contains no `data/`, cookies, tokens, logs, or user media.
- [ ] No Node, Docker or xhs_get required for YouTube, TikTok, Instagram, X,
      Reddit, or Vimeo ingest.
- [ ] ffmpeg is either a declared system dependency or a compliant bundled
      binary with source/written offer.
- [ ] Optional Piper/Kokoro/espeak/minisbd binaries and models are excluded
      unless reviewed and noticed.
- [ ] If a sidecar is shipped: separate artifact, source or written offer,
      license texts, branding rules, and no extra restrictions.
- [ ] `docs/shared/url-ingest-qa.md` phase 6 matrix passes.
- [ ] Source archive, checksums, and SBOM archived with the release.

## 8. Release caveats to repeat in the shipping notes

- VibeCut is proprietary; yt-dlp is Unlicense; ffmpeg is the user's system
  dependency unless explicitly bundled.
- xhs_get (GPL-3.0) is an optional external process, not part of VibeCut, and
  is not downloaded automatically.
- No DRM, private-content, or paywall bypass is supported.
- Local Piper/espeak and some optional models carry copyleft or
  non-commercial terms; they are not part of the default URL-ingest build.
