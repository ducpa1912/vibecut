# Distribution plan · cloud and Apple Silicon desktop

Date: 2026-11-04
Source audit: [licensing-audit.md](licensing-audit.md) · Cloud deep dive: [cloud-architecture.md](cloud-architecture.md)
Product license: proprietary (root `LICENSE`; EULA still required)

Two artifacts are planned:

1. **Cloud deployment** — hosted service, optional customer-hosted image.
2. **Mac Apple Silicon desktop app** — Developer ID signed and notarized `.app`
   inside a `.dmg`, arm64 only.

A public pay-per-render site is a third shape, planned in
[raas-distribution-plan.md](raas-distribution-plan.md). Its license position is
Profile A below, but it needs accounts and shared workers.

Both share the same rule: **VibeCut is proprietary; third-party licenses stay
third-party.** Every artifact ships an EULA, `THIRD_PARTY_NOTICES.md`,
`LICENSES/`, and an SBOM.

---

# 0. Quick classification

## Cloud-safe (hosted service)

These are safe to run in a hosted cloud service, provided notices and model
terms ship with the image/SBOM:

- Python, FastAPI, Uvicorn, python-multipart
- NumPy, Pillow
- yt-dlp (Unlicense; keep the optional GPL `mutagen` extra out)
- ffmpeg **server-side only**, when users never receive the binary
- STTN + LaMa (Apache-2.0 weights)
- PyTorch, ONNX Runtime
- Kokoro, Whisper, DeepFilterNet, Silero, Mel-Band RoFormer (permissive)
  - Kokoro package/weights are Apache-2.0, but the current worker loads
    **espeak-ng (GPL-3.0)** for phonemes. That is safe only while espeak-ng
    stays server-side; do not infer that Kokoro itself makes espeak GPL-free.
- pyannote 3.1 with MIT notice; Community-1 only with CC-BY-4.0 attribution
- In-house stickers/LUTs; Lucide ISC notice

## Cloud-conditional

- **ffmpeg in a customer-hosted image/VM:** binary distribution. Comply with
  GPL or ship LGPL-only.
- **Stable Audio Open weights:** Stability Community License; commercial
  threshold applies.
- **Demucs:** code MIT, weights unresolved. Do not host/bundle in a paid
  service until cleared.
- **xhs_get:** separate GPL process only; never inside the main image.

## Cloud hard stops

- **MusicGen weights** — CC-BY-NC-4.0. Not for commercial cloud.
- **Piper/phonemizer/espeak/minisbd** — GPL/AGPL; do not put them in a
  customer-distributed image. AGPL (`minisbd`) is also a network-service risk.
- **GPL ffmpeg in a distributed image** without source/offer.
- **xhs_get copied into the main image** instead of a separate service.

## Mac app: safe to bundle

- Python, FastAPI stack, yt-dlp, NumPy, Pillow
- STTN + LaMa weights (Apache-2.0, with notices and hashes)
- PyTorch/ONNX Runtime
- Whisper (MIT), DeepFilterNet (MIT/Apache), Silero (MIT),
  Mel-Band RoFormer (MIT)
- Kokoro (Apache weights) only if its phonemizer is not GPL espeak-ng, or the
  GPL question is reviewed.
- In-house stickers/LUTs, Lucide ISC
- Native Swift helpers built from this repo

## Mac app: hard stops

| Hard stop | Why | Fix |
|---|---|---|
| Bundling the current Homebrew ffmpeg | GPL-3.0-or-later, libx264/x265 | Ship LGPL ffmpeg + VideoToolbox, require user-installed ffmpeg, or accept GPL compliance (no App Store) |
| Bundling Piper/phonemizer/espeak | GPL-3.0-or-later | Exclude; use Apple `say` or cloud TTS. Kokoro in this build loads espeak-ng, so Kokoro + bundled espeak is also a GPL review item. |
| Bundling minisbd | AGPL-3.0 | Exclude entirely |
| Bundling Demucs weights | Weights not covered by MIT; research/MUSDB terms | Ship RoFormer only, get written permission, or omit separation |
| Bundling MusicGen / Stable Audio | Non-commercial / threshold license | Remove; use licensed/CC0 music or a commercial API |
| Bundling xhs_get inside `.app` | GPL-3.0 | Separate artifact/process, or omit |
| Mac App Store with GPLv3/GPL/AGPL | Apple DRM/terms conflict | Direct Developer ID + notarized DMG; or remove all GPL/AGPL first |
| Data written inside the `.app` | Read-only signed bundle | Set `VIBECUT_DATA` to Application Support |

PyInstaller is **not** a hard stop: it is GPL-2.0-or-later with a bootloader
exception. py2app is MIT/PSF and simpler for a Mac-only bundle.

---

# 1. Cloud deployment

Architecture, storage, scaling and a single-VM runbook:
[cloud-architecture.md](cloud-architecture.md). This section is the license
plan; that document is the deployment plan.

## 1.1 Choose the legal profile first

| Profile | What customers receive | GPL/AGPL consequence |
|---|---|---|
| **A. Hosted SaaS** | Browser access only; no image, binary or source | GPL ffmpeg is not distributed to users. No GPL source offer is triggered by normal use. AGPL would still require a network source offer if AGPL code were used — none is in the default stack. |
| **B. Customer-hosted image** | Pullable container / VM image | The image is a distribution. GPL ffmpeg, GPL x264/x265, Debian packages and fonts need notices plus source or a written offer. AGPL sidecars must be absent or separately compliant. |

Default recommendation: start with **Profile A**. If Profile B is sold, either
accept GPL compliance for the container or build the LGPL-only variant in 1.4.

## 1.2 Runtime architecture

- Linux container, Python 3.11, non-root user.
- FastAPI/uvicorn behind TLS reverse proxy (Caddy/nginx/ALB).
- Persistent volume for `VIBECUT_DATA` (`/data`), object storage for renders.
- One API process plus a bounded render/analysis worker pool. ffmpeg is
  process-isolated; cap concurrency by CPU and RAM.
- `VIBECUT_TOKEN` required on any non-loopback bind; admin requires HTTPS.
- No `xhs_get`, no optional GPL/AGPL engines, no user cookies in the image.
- Models mounted read-only or fetched into the data volume with SHA checks.
- Apple Vision/Speech/AVFoundation are macOS-only. A Linux cloud worker must
  use a cloud OCR/STT/TTS provider or ship a reviewed local alternative; the
  product must not silently claim Apple-quality OCR in the cloud.

## 1.3 Image contents

| Layer | Contents | License action |
|---|---|---|
| Base | `python:3.11-slim` pinned by digest | Include PSF + Debian copyright notices. |
| OS packages | ffmpeg/ffprobe, fonts-dejavu-core, CA certificates | Record `dpkg-query -W`; include Debian copyright files. |
| Python | `requirements.lock` (hash-pinned) | Generate `pip-licenses` JSON/markdown and copy referenced license files. |
| App | proprietary source/static | EULA + proprietary `LICENSE`. |
| Optional fill | torch + onnxruntime + STTN/LaMa weights | BSD-3 + MIT + Apache-2.0 notices; model hashes and source URLs. |
| Optional speech | Kokoro/Whisper packs or cloud API keys | Apache-2.0/MIT notices or provider terms. |
| Optional separation | RoFormer only | MIT notice; keep Demucs out until weights are cleared. |

The current `Dockerfile` installs Debian ffmpeg and DejaVu fonts but **does not
install torch/onnxruntime or model weights**. Add build profiles rather than
silently shipping a Clean panel that cannot fill:

```dockerfile
ARG WITH_FILL=""
# WITH_FILL=sttn,lama installs the runtimes and expects models in /data/models/fill
```

## 1.4 ffmpeg decision for Profile B

Current Docker render path uses `libx264`; a Debian/Homebrew ffmpeg with
`--enable-gpl` is GPL. Two compliant paths:

1. **GPL-compliant container (fastest):** keep the GPL ffmpeg build, include
   its license, exact build configuration, Debian source package information,
   and a written offer/source archive valid for three years. The proprietary
   app calls ffmpeg as a separate process; do not copy GPL code into VibeCut.
2. **LGPL-only container (cleaner for OEM):** build/download ffmpeg without
   `--enable-gpl`, use OpenH264 (BSD-2-Clause) or hardware encoders instead of
   libx264, and avoid x265. Include LGPL notices, source, and relinking
   information for the shared libraries.

Do not mix: a GPL build with an “LGPL” label is the most common audit failure.

**Resolved code issue:** `render.py` previously had two hard-coded
`_encoder_args("libx264", ...)` fallbacks. They now receive the selected encoder
(`videotoolbox`, `libx264`, or OpenH264/VAAPI build), so an LGPL-only Mac build
does not silently fall back to GPL x264. A regression test covers the concat
fallback.

## 1.5 Model provisioning

- Bundle or mount **STTN** and **LaMa** only with Apache-2.0 notices, upstream
  source and pinned SHA-256:
  - `sttn_infer_model.pth`: `c8408c9d…464675b`
  - `lama_fp32.onnx`: `1faef530…7a4eb68d6`
- Kokoro: Apache-2.0; Whisper: MIT; DeepFilter/Silero/RoFormer: permissive with
  notices.
- **Do not host Demucs weights** in a paid image or pack until written
  permission is obtained. Make RoFormer the only separation path.
- Do not reintroduce MusicGen (CC-BY-NC) or Stable Audio weights without a
  commercial license review.
- Cloud speech providers stay API-key based; no weights are redistributed.

## 1.6 Cloud release pipeline

1. Build in a clean Linux builder; no dev extras.
2. Pin base digest and apt package versions; record `ffmpeg -version`, `ffmpeg -L`,
   `dpkg-query -W`, Python freeze, `pip-licenses` inventory.
3. Run `python scripts/check_proprietary_deps.py --all` in the clean build
   environment; fail on GPL/AGPL unless the release is explicitly GPL-compliant.
4. Copy `LICENSE`, EULA, `THIRD_PARTY_NOTICES.md`, `LICENSES/`, `sbom/` into the
   image under `/usr/share/vibecut/`.
5. Smoke test: fresh volume, ffmpeg present, model status, token auth, one
   upload, one render, one Clean fill, one URL ingest.
6. Publish SBOM and source-offer URL with the image digest.

## 1.7 Cloud acceptance checklist

- [ ] Profile A or B chosen and reflected in the EULA/terms.
- [ ] No piper/phonemizer/minisbd/espeak/xhs_get in the image.
- [ ] ffmpeg build and license recorded; GPL source offer or LGPL path chosen.
- [ ] Debian/font/Python notices included.
- [ ] Models have licenses, source URLs and hashes.
- [ ] Demucs weights absent.
- [ ] Non-root, read-only root, writable `/data`, TLS, token.
- [ ] SBOM, pip freeze, dpkg list and model checksums archived.
- [ ] Customer-hosted image ships the same notices as a binary distribution.

---

# 2. Mac Apple Silicon desktop app

## 2.1 Product shape

Recommended: a native **SwiftUI + WKWebView** shell that launches a bundled
Python sidecar (FastAPI on loopback), shows the existing UI, and shuts the
server down on quit. This keeps the current web UI and avoids Electron.

Alternatives:
- **py2app** (MIT/PSF) — simplest license story for a Python `.app`.
- **PyInstaller** (GPL-2.0-or-later with bootloader exception) — acceptable if
  the exception text is included; verify the exact release.

Do **not** ship the Homebrew GPL ffmpeg inside the `.app` unless the release is
deliberately GPL-compliant. Recommended Mac build: **LGPL ffmpeg + Apple
VideoToolbox** (`h264_videotoolbox`) with no libx264/x265, or require the user
to install ffmpeg separately.

## 2.2 Bundle layout

```text
VibeCut.app/
  Contents/
    MacOS/VibeCut                 Swift shell
    Frameworks/Python.framework   Python 3.11 arm64 (PSF)
    Resources/
      server/                     VibeCut Python + static UI (proprietary)
      bin/ffmpeg, ffprobe         Only if LGPL-compliant
      bin/vision_probe            Swift helper, arm64, signed
      bin/transcribe_apple        Swift helper, arm64, signed
      LICENSES/
      THIRD_PARTY_NOTICES.md
      EULA.txt
      sbom/
    Info.plist
```

Data must not live in the read-only bundle. The launcher sets:

```bash
VIBECUT_DATA="$HOME/Library/Application Support/VibeCut"
VIBECUT_HOST=127.0.0.1
VIBECUT_PORT=<random free port>
VIBECUT_TOKEN=<per-launch random token>
VIBECUT_ENCODER=videotoolbox
```

Then it opens `http://127.0.0.1:<port>/?token=...` in WKWebView (cookie/local
storage), and kills the sidecar on quit. Use a single-instance lock.

## 2.3 Models and optional packs

Default offline build should choose one:

| Option | Contents | Size | License handling |
|---|---|---|---|
| **Lean** | No models; first-run download | small | Show license + SHA before download. |
| **Offline Clean** | STTN + LaMa + torch/onnxruntime | ~500 MB+ | Apache-2.0/MIT/BSD notices and model sources. |
| **Full local** | + Kokoro/Whisper/RoFormer | GBs | More notices; still exclude Demucs weights. |

Models are separate works. Do not bury their licenses inside the Python wheel
notices.

## 2.4 Signing and notarization

1. Build arm64 only (`CMAKE_OSX_ARCHITECTURES=arm64` / `arch -arm64`).
2. Sign every nested binary: Python framework, `.so`/`.dylib`, ffmpeg, Swift
   helpers, then the `.app` with **Developer ID Application**.
3. Enable hardened runtime. Minimal entitlements: audio input if recording,
   network client/server for localhost, user-selected files. Avoid
   `disable-library-validation` unless a bundled unsigned dylib forces it.
4. Notarize with `notarytool`, staple the ticket, verify with
   `spctl --assess --type execute` and `stapler validate`.
5. Produce a signed `.dmg`; optionally a `.zip` for Sparkle (MIT).
6. **Mac App Store: do not target it** while GPLv3 ffmpeg or GPL/AGPL engines
   are present. App Store DRM/terms conflict with GPLv3 and complicate
   subprocess/sandbox behavior. Revisit only after moving to AVFoundation /
   VideoToolbox and removing all GPL components.

## 2.5 Mac build pipeline

1. Clean macOS arm64 builder; Python 3.11 from python.org; `requirements.lock`.
2. Build the Swift helpers; compile `tools/vision_probe.swift` and
   `tools/transcribe_apple.swift` for arm64, or reuse the checked-in `bin/`.
3. Package Python + static UI with py2app (preferred) or PyInstaller (include
   bootloader exception).
4. Bundle ffmpeg only if LGPL-compliant; record `ffmpeg -L` and source offer.
5. Copy notices/SBOM/EULA; run `scripts/check_proprietary_deps.py --all` on the
   bundled Python environment.
6. Sign, notarize, staple, create DMG, checksum.
7. Test on a clean Apple Silicon Mac with no Python, ffmpeg, Node, Xcode or
   developer tools installed.

## 2.6 Mac acceptance checklist

- [ ] Launches on a clean Apple Silicon Mac with Gatekeeper enabled.
- [ ] No Python/ffmpeg/Node required from the user.
- [ ] Data writes only to `~/Library/Application Support/VibeCut`.
- [ ] Sidecar binds loopback only and dies with the app.
- [ ] All nested binaries signed; notarization stapled.
- [ ] ffmpeg is LGPL-compliant, or GPL compliance is explicit.
- [ ] No piper/phonemizer/minisbd/espeak/xhs_get/Demucs weights in the bundle.
- [ ] STTN/LaMa notices, hashes and source URLs included if bundled.
- [ ] Lucide ISC notice included for the icon set.
- [ ] EULA shown on first run and available in About.
- [ ] Update path signed (Sparkle optional, MIT notice).
- [ ] Uninstall removes app + optionally offers data removal.

---

# 3. Shared release checklist

- [ ] Lockfile with hashes; no version floors in release builds.
- [ ] `sbom/python-freeze.txt`, `sbom/python-packages.json`, `sbom/ffmpeg.txt`,
  `sbom/dpkg.txt` (cloud), model checksums.
- [ ] `LICENSES/` contains full texts for MIT/BSD/Apache/PSF/Unlicense/MPL if
  used, plus Lucide, DejaVu, ffmpeg and model notices.
- [ ] `THIRD_PARTY_NOTICES.md` updated with versions and upstream URLs.
- [ ] No dev-only packages, test data, cookies, tokens, user media or `data/`.
- [ ] Proprietary EULA reviewed by counsel.
- [ ] Export-control/crypto review (OpenSSL, HTTPS) if shipping outside the US.
- [ ] Privacy policy and data-retention terms for cloud.
- [ ] Trademark/branding review for third-party names.

## 4. Blockers before either public release

1. **ffmpeg licensing decision** — GPL compliance or LGPL-only build.
2. **Demucs weights** — remove from paid artifacts or obtain written permission.
3. **Optional engines** — ensure clean release environments contain none of
   Piper/phonemizer/minisbd/espeak.
4. **Missing notices** — add Lucide ISC and model-weight notices.
5. **Lockfile/SBOM** — floors are not a release inventory.
6. **Mac data path** — default `ROOT/data` is read-only inside a signed app;
   the launcher must set `VIBECUT_DATA`.
7. **Cloud fill runtime** — current image lacks torch/onnxruntime/models.
8. ~~Hard-coded libx264 fallbacks~~ — fixed in `render.py`; keep the regression
   test in the release gate.

## 5. Suggested sequence

1. Add Lucide notice + model notices; lock Python deps; generate first SBOM.
2. Cloud Profile A: clean image, no optional engines, ffmpeg source/notice pack.
3. Mac prototype: Swift/WKWebView shell + py2app sidecar + Application Support.
4. Mac ffmpeg: LGPL + VideoToolbox path; sign/notarize.
5. Cloud Profile B only after GPL/LGPL posture is signed off.
6. Remove or clear Demucs before any paid build.
