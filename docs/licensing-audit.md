# License audit · VibeCut Studio

Date: 2026-11-04
Scope: proprietary source tree, runtime Python closure, bundled assets, optional
local engines, model weights, system tools and the two intended distribution
profiles.
Status: engineering audit, not legal advice. Re-run against the clean release
environment and have counsel review before shipping.

## Verdict

| Area | Status | Why |
|---|---|---|
| VibeCut source/UI/prompts | Proprietary | Covered by root `LICENSE`; EULA still required. |
| Default Python runtime | Green | All direct requirements are permissive or public domain. |
| Frontend | Green with notice gap | No npm runtime; Lucide icon paths are ISC and are missing from the notice file. |
| Bundled media | Green | Stickers and LUTs are in-house; music folders are empty/user-supplied. |
| System ffmpeg | **Amber/red** | The development Homebrew binary is GPL-3.0-or-later. A bundled Mac app or a customer-hosted image inherits distribution duties. |
| Optional local engines | **Red if shipped** | Piper/phonemizer are GPL, minisbd is AGPL, and Demucs weights are not covered by the MIT code grant. |
| Model weights | Amber | STTN/LaMa/Kokoro/Whisper/DeepFilter/Silero/RoFormer paths are permissive; Demucs weights are unresolved. |
| Reproducibility | Amber | Requirements use floors, not a lockfile with hashes; versions and licenses can drift. |

**Bottom line:** a cloud service can be licensed cleanly with the default
runtime and GPL ffmpeg kept inside the hosted service. A distributed Apple
Silicon `.app` must not ship the current Homebrew ffmpeg or optional GPL
engines without a deliberate GPL-compliance decision. Do not put either build
on the Mac App Store while it contains GPLv3 ffmpeg.

## 1. Proprietary and in-house material

| Item | License | Notes |
|---|---|---|
| VibeCut source, UI, prompts, build scripts | Proprietary, all rights reserved | Root `LICENSE`. A written EULA is still required before paid distribution. |
| Sticker PNGs (`assets/stickers`) | In-house | No third-party artwork or emoji font used at render time. |
| Colour LUTs (`assets/luts`) | In-house | Generated from `edits.COLOR_PRESETS`. |
| Docs, tests, design demos | In-house | Check any copied screenshots or third-party screenshots before shipping. |

## 2. Default runtime closure

These are the components a clean `pip install -r requirements.txt` brings in.
Versions below are the audited development environment; the release build must
pin its own versions and generate an SBOM.

| Component | License (SPDX) | Role | Notice duty |
|---|---|---|---|
| Python 3.11 | PSF-2.0 | Runtime / Docker base | Include PSF license for distributed images/app. |
| fastapi | MIT | HTTP API | MIT notice. |
| starlette | BSD-3-Clause | ASGI framework | BSD notice. |
| pydantic, pydantic-core | MIT | Request models | MIT notice. |
| annotated-types, annotated-doc, typing-inspection | MIT | Pydantic/FastAPI transitive | MIT notice. |
| opentelemetry-api | Apache-2.0 | FastAPI transitive | Apache-2.0 notice. |
| typing_extensions | PSF-2.0 | Typing compatibility | PSF notice. |
| anyio | MIT | Async compatibility | MIT notice. |
| sniffio | MIT OR Apache-2.0 | Anyio transitive | Keep chosen license text. |
| idna | BSD-3-Clause | HTTP transitive | BSD notice. |
| h11 | MIT | Uvicorn transitive | MIT notice. |
| click | BSD-3-Clause | Uvicorn CLI | BSD notice. |
| uvicorn | BSD-3-Clause | ASGI server | BSD notice. |
| uvloop | MIT | Uvicorn standard extra (non-Windows) | MIT notice. |
| httptools | MIT | Uvicorn standard extra | MIT notice. |
| websockets | BSD-3-Clause | Uvicorn standard extra | BSD notice. |
| watchfiles | MIT | Uvicorn standard extra | MIT notice. |
| python-dotenv | BSD-3-Clause | Uvicorn standard extra | BSD notice. |
| colorama | BSD-3-Clause | Uvicorn Windows extra only | Not shipped on macOS/Linux. |
| PyYAML | MIT | Uvicorn standard extra | MIT notice. |
| python-multipart | Apache-2.0 | Upload forms | Apache-2.0 notice. |
| NumPy | BSD-3-Clause plus bundled permissive notices | Analysis math | Full NumPy notice/source bundle. |
| Pillow | MIT-CMU / HPND | Thumbnails/images | HPND notice. |
| yt-dlp | Unlicense | URL ingest | Include Unlicense text and installed version. |
| python-stretch (optional) | MIT | Optional voice fit | MIT notice; includes Signalsmith Stretch MIT. |

`requirements-dev.txt` (pytest MIT, httpx2 BSD-3-Clause) is test-only and must
not enter a production artifact.

### yt-dlp extras caveat

`requirements.txt` intentionally installs plain `yt-dlp`, not `yt-dlp[default]`.
The `default` extra can pull **mutagen**, which is GPL-2.0-or-later. Do not add
that extra to a proprietary build without review. Some site extractors may be
weaker without optional extras; document the supported-site matrix.

## 3. Optional local engines and model packs

These are not in `requirements.txt`. They arrive through optional packs,
user installs, or cloud API keys.

| Component | Code license | Weights/data license | Distribution decision |
|---|---|---|---|
| STTN (`textfill/sttn.py`) | MIT (researchmm/STTN) | Subtitle-tuned weights from YaoFANGUK/video-subtitle-remover: Apache-2.0 | Permissive; include MIT + Apache notices and model source. |
| LaMa ONNX (`textfill/lama.py`) | Apache-2.0 (Carve/LaMa-ONNX port of big-lama) | Apache-2.0 | Permissive; include Apache notice and model source/hash. |
| PyTorch (STTN runtime) | BSD-3-Clause | n/a | Permissive; huge; separate optional pack. |
| ONNX Runtime (LaMa runtime) | MIT | n/a | Permissive. |
| Kokoro-82M / kokoro-onnx | Apache-2.0 package; Apache-2.0 weights | Apache-2.0 | Permissive; include notice and model card. |
| mlx / mlx-whisper | MIT | Whisper weights MIT | Permissive; include notice. |
| DeepFilterNet 3 | MIT; some files Apache-2.0 | MIT/Apache-2.0 | Permissive; include dual notice. |
| Silero VAD v5 | MIT | MIT | Permissive. |
| audio-separator | MIT wrapper | Checkpoint terms stay with each model | Keep wrapper notice; do not imply model clearance. |
| Mel-Band RoFormer (Kim vocal 2) | MLX conversion MIT | MIT since 2026-04-22 (verify pinned card) | Preferred separation path. |
| pyannote.audio 3.1 | MIT | 3.1 pipeline MIT; Community-1 weights CC-BY-4.0 | Optional; gated download; keep attribution. |
| Demucs htdemucs / htdemucs_ft | MIT code | **Not covered by MIT; research-oriented MUSDB terms** | **Do not bundle or host in a paid distribution until cleared.** Remove fallback or ship RoFormer only. |
| Piper TTS | GPL-3.0-or-later | Voice models vary | Exclude from proprietary builds. |
| phonemizer | GPL-3.0-or-later | n/a | Exclude; transitive GPL risk. |
| espeak-ng | GPL-3.0-or-later | n/a | Do not bundle without GPL review. |
| minisbd | AGPL-3.0 | n/a | Exclude; AGPL network-use duties. |
| MusicGen weights | CC-BY-NC-4.0 | Non-commercial | Removed from product; do not reintroduce. |
| Stable Audio Open weights | Stability Community License | Commercial threshold | Removed; do not reintroduce without review. |
| Cloud TTS/STT providers | Commercial API terms | No weights redistributed | Keys stay server-side/local; no model redistribution. |

### Current model provenance

| File | Size | SHA-256 | License |
|---|---:|---|---|
| `sttn_infer_model.pth` | 66,271,967 B | `c8408c9d…464675b` | Apache-2.0 (VSR weights), MIT code upstream |
| `lama_fp32.onnx` | 208,044,816 B | `1faef530…7a4eb68d6` | Apache-2.0 |

The model folder currently used by the live Studio server is
`~/vibecut-lanes/studio/models/fill`; models are **not** in the repository.
A release must either bundle them with notices or download them with a pinned
hash and license display.

## 4. System and platform dependencies

| Component | License | Rule |
|---|---|---|
| ffmpeg / ffprobe (Homebrew 9.0.2, current dev) | **GPL-3.0-or-later** (`--enable-gpl --enable-version3`; includes libx264/x265) | Do not bundle in the Mac app without GPL source/notice compliance. Treat the Docker image as GPL too until its exact Debian build is recorded. |
| Debian ffmpeg (Dockerfile `apt-get install ffmpeg`) | Verify from image; likely GPL-2.0-or-later | A distributed image must include Debian copyright notices and source/written offer. Record `ffmpeg -L` and `dpkg-query -W`. |
| libx264 (Docker render) | GPL-2.0-or-later | Part of the GPL ffmpeg decision. |
| libx265 (Homebrew dependency) | GPL-2.0 | Same. |
| libdav1d | BSD-2-Clause | Permissive; notice. |
| libvpx | BSD-3-Clause | Permissive; notice. |
| OpenSSL | Apache-2.0 | Notice if bundled. |
| DejaVu fonts (Docker) | Bitstream Vera / Arev permissive | Include font copyright/license with the image. |
| Apple Vision / Speech / AVFoundation | Apple SDK and OS terms | Do not redistribute SDK binaries; use OS frameworks. |
| `bin/vision_probe`, `bin/transcribe_apple` | VibeCut code linked to Apple frameworks | Re-sign with the app; include own copyright. |

## 5. Current findings and required actions

1. **ffmpeg is the main blocker.** `ffmpeg -version` on this Mac reports
   Homebrew `--enable-gpl --enable-version3`; `ffmpeg -L` prints GPLv3.
   Decide per distribution: GPL compliance (source offer + notices) or an
   LGPL-only build using VideoToolbox/OpenH264.
2. **Optional engines must be excluded from release artifacts.** The current
   developer environment fails `scripts/check_proprietary_deps.py --all` on
   `piper-tts` (GPL), `phonemizer` (GPL) and `minisbd` (AGPL). Clean release
   venv passes direct requirements; never copy the dev environment.
3. **Demucs weights need a product decision.** Keep out of paid builds until
   permission is written, or make RoFormer the only separation engine.
4. **Add missing Lucide notice.** `static/studio/edit/icons.js` contains
   Lucide-derived ISC paths; `THIRD_PARTY_NOTICES.md` and `LICENSES/` do not
   currently carry it.
5. **Pin and lock.** Replace floors with a hash-locked lockfile; generate
   `pip-licenses` inventory, `pip freeze`, ffmpeg version/license, Debian
   package list and model SHA-256 in `sbom/`.
6. **Docker does not include fill runtimes/models.** `requirements.txt` lacks
   torch/onnxruntime, and the image has no models. Add build profiles for
   `--with-fill=sttn,lama` or disable Clean AI fill in that image explicitly.
7. **Model files are separate works.** Notices must name the model, source,
   license and hash, not only the Python package.
8. **No bundled music.** `assets/music/library` and `cc0` are empty. Do not
   ship user music or generated tracks in the app.
9. **Development environment is not the release environment.** It reports
   NumPy 1.23.5 while `requirements.txt` declares `>=1.26`, and it contains the
   GPL/AGPL optional engines above. Build the SBOM in a fresh venv/container.

---

# 6. Deep dive: what actually runs, and when

## 6.1 Runtime activation map

This is the important distinction between “installed in the development
environment” and “used by the shipped app”.

| Component | Role in VibeCut | Where invoked | Active on this machine? |
|---|---|---|---|
| Python 3.11 | The application runtime itself | `app.py` and all modules | **Yes** — every request, worker and subprocess that runs Python |
| FastAPI | HTTP routing, request validation, uploads, JSON responses | `app.py`, `routes_*.py` | **Yes** — production API, not just development |
| Uvicorn | ASGI web server | `app.py::uvicorn.run` | **Yes** — process that listens on 8787/8795 |
| python-multipart | Parses multipart file uploads | `File(...)`/`UploadFile` routes: source, photo, music, voice, video assets | **Yes** when an upload happens |
| NumPy | Scene scores, audio loudness, mask math, image arrays | `pipeline.py`, `detect.py`, `audio.py`, `textfill/*` | **Yes** — analysis, audio, fill |
| Pillow | Thumbnails, OCR frame images, text/sticker compositing | `pipeline.py`, `render.py`, `textfill/*` | **Yes** — scan, preview and render |
| yt-dlp | URL inspection and download | `url_ingest/ytdlp.py`, imported by the ingest worker | **Yes** when a URL is imported |
| ffprobe | Duration, codec, resolution, audio streams | `pipeline.py`, `render.py`, `audio.py` via subprocess | **Yes** — import, render, preview |
| ffmpeg | Frame extraction, scan, proxy, cuts, audio mix, subtitle burn, fill input/output, voice denoise | `pipeline.py`, `render.py`, `audio.py`, `voice_extract.py`, preview routes | **Yes** — nearly every media operation |
| PyTorch | Runs the STTN neural network | `textfill/sttn.py` | **Yes** — Clean fill with STTN |
| ONNX Runtime | Runs LaMa and Kokoro ONNX models | `textfill/lama.py`, `tools/tts_kokoro.py` | **Yes** for LaMa; Kokoro only when installed |
| STTN weights | Subtitle-tuned video inpainting | `render.py::_prepare_fills` → `textfill.prepare_span` | **Yes** — models present in the lane model folder |
| LaMa weights | Per-frame image inpainting and Before/After preview | same, and `routes_studio.fill_preview` | **Yes** — models present |
| Demucs | Vocal/instrumental separation for voice clone and clean voice | `audio._demucs_into` subprocess; `voice_extract._separate_voice` | **Yes, as the current fallback** when RoFormer is absent |
| mlx-whisper | Local speech-to-text | `stt._whisper_command`, `voice_pool` jobs | **Yes, installed**; Apple Speech may take priority |
| Kokoro / kokoro-onnx | Local TTS | `tts._kokoro_voice` → `tools/tts_kokoro.py` | **No** — model/runtime not installed |
| DeepFilterNet 3 | Optional denoise CLI | `voice_extract._deepfilter` | **No** — binary absent; falls back to ffmpeg `afftdn` |
| Silero VAD | Optional voice activity detection | `voice_extract` import | **No** — module absent; falls back to energy VAD |
| pyannote.audio | Optional speaker diarization | `voice_extract` import | **No** — module absent |
| Mel-Band RoFormer | Optional separation via `audio-separator` | `voice_extract._separate_roformer` | **No** — CLI/model absent; Demucs is used instead |
| Piper / espeak-ng | Removed TTS engine and its system dependency | Legacy adapter only; no active route | **No product route** — installed in dev, but not called by current TTS |
| Apple Vision | On-device OCR/face/salience | `bin/vision_probe` subprocess | **Yes on macOS 26** when the helper is available |
| Apple Speech | On-device transcription | `bin/transcribe_apple` subprocess | **Yes on macOS 26** when available |
| Cloud TTS/STT/LLM APIs | Optional remote providers | `tts.py`, `stt.py`, OpenRouter/OpenCode/OpenAI-compatible calls | Only when configured |

### How work is scheduled

VibeCut is one Python process with four in-process thread pools:

| Pool | Max workers | Work |
|---|---:|---|
| `analysis_pool` | 1 | Import analysis: probe, scene scan, thumbnails, transcript |
| `ingest_pool` | 2 | URL downloads / import preparation |
| `render_pool` | 1 | Full reel render, proxy build, fill pre-pass |
| `voice_pool` | 1 | Speech re-reads, scripts, voice-candidate search and clone prep |
| `CHECK_POOL` | 1 | Source Check / OCR pass |

These are **threads inside the FastAPI process**, not separate services. ffmpeg,
Demucs, mlx-whisper and the Swift helpers are subprocesses. PyTorch/ONNX work
runs in the render thread. This matters for cloud scaling: one container has
one analysis queue and one render queue, and cannot be horizontally scaled
naively without splitting state or adding an external queue.

## 6.2 ffmpeg deep dive

ffmpeg is not an optional utility in VibeCut. It is the media execution layer:

- `ffprobe` reads source metadata before a job exists.
- The first scan pass extracts frames for scene detection and OCR.
- Thumbnails and poster frames are ffmpeg stills.
- Proxy/preview generation cuts and concatenates segments.
- The render builds each beat, concatenates, burns captions/text/layers, and
  muxes audio.
- Audio uses ffmpeg for source decode, loudness, fades, ducking, music loops and
  voice fitting.
- Voice extraction uses ffmpeg `afftdn`, VAD input, stem conversion and final
  audio assembly.
- Clean fill sends ffmpeg-cut spans through STTN/LaMa and reads the result back.

Consequences:
- If ffmpeg is missing, most of the product is unavailable; the app should fail
  with a clear capability error, not a generic 500.
- ffmpeg is a **separate executable**. VibeCut does not link libavcodec into
  Python. This supports an “aggregate” distribution argument, but it does not
  erase the GPL obligations for the ffmpeg binary itself.
- The development binary is GPL-3.0-or-later. A Mac `.app` or customer-hosted
  image that contains it is a GPL binary distribution: include the license,
  exact build configuration, and source or a written offer.
- A hosted SaaS that never gives the binary to users does not trigger GPL
  distribution in the same way. This is why the cloud profile matters.
- The current Mac render default is `videotoolbox` when `VIBECUT_ENCODER=auto`;
  Linux defaults to `libx264`. The two concat/mux fallbacks were hard-coded to
  `libx264`; they now take the selected encoder (`render.py`), so a
  VideoToolbox-only/LGPL build can fall back correctly.

Alternatives:

| Option | Trade-off |
|---|---|
| System-installed ffmpeg | No bundled binary, but desktop users must install it; not acceptable for a polished `.app`. |
| LGPL ffmpeg build | No GPL code; use VideoToolbox on Mac, OpenH264/VAAPI on Linux. Requires a maintained build and notices/source. |
| GPL ffmpeg bundle | Fastest engineering; requires GPL source/offer and rules out Mac App Store. |
| AVFoundation/VideoToolbox native | Best Mac integration, no ffmpeg for basic operations; months of work because the pipeline is ffmpeg-filter based. |
| Cloud transcoding API | Simplifies desktop, adds latency, cost, privacy and network dependency. |

## 6.3 Demucs deep dive

Demucs is used for **voice extraction/separation**, not for normal editing:

- Voice-candidate search (`routes_voice_clone._run_candidate_search`) calls
  `find_voice_candidates(..., separate="best")` unless `fast=1`.
- `voice_extract._separate_voice` prefers RoFormer when `audio-separator` and a
  RoFormer model exist; otherwise it chooses `htdemucs_ft` and then `htdemucs`.
- `audio._demucs_into` runs `python -m demucs` (or the pack binary) with
  `--two-stems=vocals`. Demucs downloads its checkpoint on first use if it is
  not already cached.
- `audio.separate_vocals` also uses Demucs for the instrumental bed when an
  audio mode needs “music/SFX without voice”.

License facts:
- **Demucs code** is MIT.
- **Demucs weights** (`htdemucs`, `htdemucs_ft`) are not covered by that MIT
  grant. The author describes them as research-oriented because of MUSDB
  terms. There is no clean commercial redistribution grant in the repository.
- If the user installs Demucs and it downloads weights to their own cache,
  VibeCut is not necessarily redistributing the weights. If VibeCut’s pack
  manifest hosts or bundles them, VibeCut is.
- The current development machine has the `demucs` command installed and the
  app reports `demucs_available() == True`. Therefore a non-fast voice-clone
  search on this machine will use Demucs unless RoFormer is installed.

Safe choices:
1. **Recommended:** make Mel-Band RoFormer the only default separation engine;
   its MLX conversion/weights are MIT. Keep Demucs as an explicit user-installed
   optional engine with a prominent notice, not a hosted pack.
2. Remove separation entirely and use ffmpeg `afftdn` plus center-channel
   extraction. Lower quality on music-heavy footage but no model risk.
3. License Demucs weights in writing from the rights holder.
4. Use a cloud separation API with commercial terms (new vendor dependency).
5. Do **not** substitute MDX-Net/UVR/BS-RoFormer checkpoints without checking
   each checkpoint’s terms.

## 6.4 Every model in the product

| Model | What it does | Where it runs | Current machine | License | Paid-build decision |
|---|---|---|---|---|---|
| STTN | Removes subtitle/text bands across video frames | Python/PyTorch in render worker | Present and used | Code MIT; VSR weights Apache-2.0 | Bundle or download with Apache notice + hash |
| LaMa | Per-frame inpainting; single-frame Before/After | ONNX Runtime in render/preview | Present and used | Apache-2.0 | Bundle/download with notice |
| Demucs htdemucs / htdemucs_ft | Splits vocals from music/SFX | `python -m demucs` subprocess | Installed; active fallback | Code MIT; weights unresolved | **Do not host/bundle in paid builds until cleared** |
| Mel-Band RoFormer (Kim vocal 2) | Preferred vocal separation | `audio-separator` subprocess | Not installed | MIT (verify pinned model card) | Prefer this over Demucs |
| DeepFilterNet 3 | Speech denoise | `deep-filter` subprocess | Not installed | MIT/Apache-2.0 | Optional; include notice |
| Silero VAD | Speech/silence windows | Imported in `voice_extract` | Not installed | MIT | Optional; include notice |
| pyannote 3.1 / Community-1 | Speaker diarization | Imported in `voice_extract` | Not installed | Code/pipeline MIT; Community-1 CC-BY-4.0 | Optional; attribution + gated download |
| Kokoro-82M | Local TTS | `tools/tts_kokoro.py` + ONNX; loads `libespeak-ng` for phonemes | Not installed | Apache-2.0 weights/package; **espeak-ng GPL-3.0 runtime** | Optional Voice Pack; cloud safe, Mac bundle needs GPL review or a non-espeak phonemizer |
| Whisper large-v3-turbo | Local STT | `mlx_whisper` subprocess | Installed | MIT | Optional Speech Pack; include notice |
| Apple Vision OCR/faces | On-device vision | `bin/vision_probe` | Available on macOS 26 | Apple OS/SDK terms | macOS only; not in cloud |
| Apple Speech | On-device STT | `bin/transcribe_apple` | Available on macOS 26 | Apple OS/SDK terms | macOS only; not in cloud |
| MusicGen | Music generation | Removed | Absent | CC-BY-NC-4.0 weights | Do not reintroduce in paid builds |
| Stable Audio Open | Music/SFX generation | Removed | Absent | Stability Community License | Do not reintroduce without review |
| Piper | Removed TTS | Legacy only | Installed in dev | GPL-3.0-or-later | Exclude from release |
| minisbd | Not used by VibeCut | Not imported | Installed in dev | AGPL-3.0 | Exclude from release |
| phonemizer | Piper transitive | Not used | Installed in dev | GPL-3.0-or-later | Exclude from release |

“Not installed” means the feature falls back or is unavailable; the app does not
silently download those engines today, except yt-dlp/Demucs/Whisper model files
owned by their own tools when those tools are invoked.

## 6.5 What an SBOM is

A Software Bill of Materials is a machine-readable inventory of every component
in one artifact: name, version, supplier, license, hash, and dependency
relationship. It is not a license file and it does not replace notices. It lets
security and legal teams answer “is this build affected by CVE X?” and “which
license text belongs in this release?”.

Use **SPDX 2.3/3** or **CycloneDX 1.5+**. Include:
- Python distributions and versions, including transitive packages
- system binaries (ffmpeg/ffprobe), exact build configuration and hashes
- base image / Debian packages for cloud
- model files with SHA-256 and source URL
- bundled assets (Lucide, fonts, stickers, LUTs)
- the VibeCut application version and source commit

Suggested generation:

```bash
# Python
python -m pip freeze > sbom/python-freeze.txt
pip-licenses --format=json --with-license-file --with-urls \
  --output-file sbom/python-packages.json
# Optional SPDX/CycloneDX generator
cyclonedx-py environment -o sbom/python.cdx.json

# System
ffmpeg -version > sbom/ffmpeg.txt
ffmpeg -L >> sbom/ffmpeg.txt
dpkg-query -W -f='${Package}\t${Version}\n' > sbom/dpkg.txt  # cloud image

# Container
syft "$IMAGE" -o spdx-json > sbom/image.spdx.json

# Models/assets
sha256sum models/fill/*.pth models/fill/*.onnx > sbom/models.sha256
```

Keep the SBOM with the artifact digest, not only in the git repository.

## 6.6 FastAPI/Python: “did I use it for everything?”

Yes for the backend, no for the media engines:

- **Python** is the runtime for the web server, job scheduling, analysis,
  rendering orchestration, database/JSON storage, settings, scene detection,
  caption layout, audio planning and text fill.
- **FastAPI** owns HTTP only. Every browser action, upload, status poll,
  preview, render request and share link passes through it. It does not perform
  video work itself; it calls Python modules and subprocesses.
- **Uvicorn** is the production server. Development `run.sh` and Docker both
  start `app.py`, which runs Uvicorn.
- **ffmpeg/ffprobe** do media I/O as external processes.
- **PyTorch/ONNX Runtime** run inside the Python process for fill.
- **Demucs, mlx-whisper, Kokoro, DeepFilter, audio-separator** are separate
  processes spawned by Python.
- **Apple Vision/Speech** are separate Swift helpers.
- **yt-dlp** is a Python library imported into the ingest thread.

So: Python/FastAPI is not a development-only shell; it is the whole backend.
The neural/media engines are plugins around it.

## 6.7 Alternatives by engine/model

| Need | Current path | Permissive alternatives | Avoid / caveat |
|---|---|---|---|
| Subtitle-band video fill | STTN (Apache weights) | LaMa per frame; ProPainter (check code/weights); cloud inpainting | OpenCV/delogo produces visible smears; STTN is purpose-built for subtitle strips |
| General image fill / Before-After | LaMa ONNX (Apache) | STTN; ProPainter; OpenCV Telea | Telea is fast but weak on textured backgrounds |
| Vocal/music separation | Demucs htdemucs_ft (weights unresolved) | **Mel-Band RoFormer (MIT)**; MDX-Net/UVR (checkpoint terms); cloud stem API; no separation + `afftdn` | Do not bundle Demucs weights without permission |
| Speech denoise | DeepFilterNet 3 if installed; otherwise ffmpeg `afftdn` | RNNoise (BSD-3), ffmpeg `afftdn`, cloud denoise | DeepFilter is best quality but optional; ffmpeg fallback always available |
| Voice activity | Silero VAD if installed; otherwise energy | WebRTC VAD (BSD-3), energy VAD | Energy VAD is weak on music beds |
| Speaker diarization | pyannote 3.1 if installed | cloud diarization; no diarization + manual speaker labels; NVIDIA NeMo (check model terms) | Community-1 weights are CC-BY-4.0 and gated |
| Local TTS | Kokoro (Apache) / Apple `say` | Kokoro-82M; cloud TTS; Piper only with GPL compliance | Piper/phonemizer/espeak are GPL; not for proprietary bundles |
| Local STT | mlx-whisper (MIT) / Apple Speech | whisper.cpp (MIT), faster-whisper (MIT), cloud STT | Linux cloud has no Apple Speech; Whisper model files still need disk/CPU/GPU |
| Music generation | Removed | licensed library/CC0; cloud music API; user-provided track | MusicGen CC-BY-NC and Stable Audio terms are not for paid redistribution |
| Media encode/decode | ffmpeg subprocess | LGPL ffmpeg + VideoToolbox/OpenH264/VAAPI; AVFoundation; cloud transcode | Current Homebrew build is GPLv3; see 6.2 |

## 6.8 Decision summary for the two builds

**Cloud**
- Keep the default permissive Python stack.
- Use a single-tenant container + volume first; no Kubernetes.
- Keep ffmpeg server-side for SaaS. If customers receive the image, either
  comply with GPL or ship an LGPL build.
- Exclude Demucs, Piper, phonemizer, espeak, minisbd and xhs_get.
- Bundle STTN/LaMa only with Apache notices and hashes; use RoFormer if
  separation is needed; use cloud OCR/STT where Apple frameworks are absent.

**Mac Apple Silicon**
- Use a Swift/WKWebView shell + bundled Python sidecar.
- Prefer py2app (MIT/PSF); PyInstaller acceptable with its bootloader exception.
- Ship Data in Application Support, not the bundle.
- Use LGPL ffmpeg + VideoToolbox, or require user-installed ffmpeg.
- Do not ship Demucs weights or GPL/AGPL engines.
- Developer ID sign/notarize; do not target the Mac App Store while GPLv3
  ffmpeg or GPL/AGPL engines are present.

## 6.9 Transcription vs voice-reference extraction

These are different pipelines. Demucs does **not** transcribe and Whisper does
**not** remove music for a clone.

| Job | Pipeline | Engines | Output |
|---|---|---|---|
| Transcript / captions | decode → Apple Speech or Whisper | `bin/transcribe_apple`, `mlx_whisper`; cloud STT optional | timed text |
| Voice-clone reference | decode → separation → denoise → VAD → optional speaker filter → score/splice → loudness | RoFormer or Demucs, DeepFilterNet or `afftdn`, Silero or energy, pyannote if requested | clean mono WAV for the clone provider |
| Instrumental bed | source decode → vocal removal | Currently `audio.separate_vocals` uses Demucs only | music/SFX stem for a dub/voice mix |

Voice-clone flow:

```text
video/audio
  -> ffmpeg decode (48 kHz mono PCM)
  -> separation: RoFormer if installed, else htdemucs_ft, else htdemucs
  -> denoise: DeepFilterNet 3 if installed, else ffmpeg afftdn
  -> VAD: Silero if installed, else energy RMS
  -> optional pyannote speaker filter
  -> select/splice speech, loudness-normalise
  -> clean_voice.wav or candidate clips
  -> ElevenLabs / HeyGen / MiniMax / Fish / Gemini / local clone
```

`find_voice_candidates` and the upload/manual-range clone routes call this
pipeline. The provider receives the cleaned WAV; Demucs is only the cleaning
step before it.

### Separation quality

Secondary benchmark figures recorded in `docs/voice-extraction-research.md`
(vocals SDR on MUSDB-style material; not measured on this app's media):

| Engine | Approx. vocals SDR | Character |
|---|---:|---|
| Demucs `htdemucs` | ~8.1 dB | older/smaller, fastest fallback |
| Demucs `htdemucs_ft` | ~8.9 dB | strong general music separator, mature, MPS |
| BS-RoFormer | ~9.8 dB | newer transformer, better vocal isolation |
| Mel-Band RoFormer | ~+0.5 dB over BS-RoFormer | best vocal clarity in the recorded benchmarks; heavier |

Practical ranking for **voice cloning**: Mel-Band RoFormer > Demucs
`htdemucs_ft` > Demucs `htdemucs` > no separation. RoFormer generally leaves
less music bleed and preserves vocal detail; Demucs is more mature and simpler
to run. For an **instrumental bed**, Demucs is still the only wired path in
`audio.separate_vocals`; replacing it with RoFormer requires a new instrumental
output path.

### Denoise choice

| Engine | Strength | Weakness | Role |
|---|---|---|---|
| DeepFilterNet 3 | non-stationary noise, reverb, speech preservation | optional binary/model; slower | preferred when installed |
| ffmpeg `afftdn` | stationary hiss/hum; zero model; always available | dulls consonants; weak on music/babble; musical noise | fallback |
| RNNoise | tiny, fast, steady background noise | artifacts; no advantage here | not used; docs say skip |

`denoise="compare"` runs DeepFilterNet and `afftdn`, measures SNR/noise floor,
and keeps the better one; within 0.5 dB it warns the user to listen.

### VAD choice

| Engine | What it does | Strength | Weakness |
|---|---|---|---|
| Silero VAD v5 | neural speech/non-speech timestamps | robust with music/noise; avoids cutting quiet consonants | optional dependency/model |
| Energy RMS | amplitude threshold (`-38 dB`, min speech/silence) | zero dependency, fast | mistakes music/noise for speech; trims quiet speech |

VAD runs after denoise, before speaker filtering and candidate selection. It
does not produce the transcript and does not drive Whisper.

### pyannote speaker filter

Diarization answers “who spoke when”. It is used only when a caller passes
`speaker` (`auto`, a 1-based rank, or a label):

- keep the chosen speaker's turns
- warn about overlapping speech
- reject a clip with no speech from that speaker

Current product routes call `find_voice_candidates` and `extract_clean_voice`
**without** `speaker`, so pyannote is not active today even if installed. It is
an optional API capability for multi-speaker sources, not transcript
diarization. Community-1 weights need CC-BY-4.0 attribution; 3.1 is MIT.

### Other installed packages

| Package | Actual role | Current status |
|---|---|---|
| Piper | removed TTS engine | installed in dev, no product route |
| phonemizer | text-to-phoneme library used by Piper-style TTS | not imported; no role |
| espeak-ng | GPL phoneme engine loaded by Kokoro worker | not used unless Kokoro is enabled |
| minisbd | sentence-boundary detection package | not imported; not in requirements; no role |
| Stable Audio | removed music generation | not imported; no role |
| MusicGen | removed music generation | not imported; no role |

**Kokoro caveat:** Kokoro package/weights are Apache-2.0, but
`tools/tts_kokoro.py` loads `libespeak-ng` for phonemes. espeak-ng is
GPL-3.0. Kokoro is cloud-safe server-side; a Mac app that bundles Kokoro plus
espeak-ng needs GPL review or a non-espeak phonemizer. Apple `say` and cloud TTS
avoid that dependency.
