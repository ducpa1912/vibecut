# DuckSuite Phase 1 — detailed build plan

Date: 2026-11-07
Status: active
Product record: `PRODUCT.md`
Roadmap: `ROADMAP.md`
Scope: DuckSuite for Mac only. DuckClean, DuckClassic and DuckStudio are later.

This plan is agent-native: one implementation day per phase is the target. External gates — App Review, StoreKit propagation, clean-Mac signing, model quality, HF capacity, license review — run in parallel and are not coding days.

---

## 0. Scope lock

### Must ship

- **Mac App Store app**, macOS 26+ on Apple Silicon.
- **$29 paid upfront.** No trial, no license key, no account.
- **Dissect:** scene cuts, transcript, local OCR, smart story candidates with hook/payoff evidence, manual moment builder.
- **Detect:** on-screen text, faces, saliency, speech, music, basic quality warnings.
- **Clean:** LaMa AI fill default; explicit Blur; one box per real text; before/after; manual box.
- **Voice-over:** local Apple voices + Kokoro; script editor; per-line preview.
- **Dub:** Apple Translation + local TTS; editable script; English, Vietnamese, Chinese; beta label allowed, cutting it is not.
- **Edit:** trim, split, reorder, remove silence; 9:16, 4:5, 1:1, 16:9; auto-frame; captions; text; music.
- **Render:** **1080p only**, **24 or 30 fps**, MP4 H.264/AAC.
- **Export:** MP4, SRT, cover JPG. **No publish kit.**
- **Models:** core bundled; optional data packs with SHA-256 and signature.
- **Cloud render:** optional free CPU, then paid CPU. GPU is a later gate.

### Hard cuts

- No 720p, 2K, 4K, 60 fps, HDR, ProRes, 10-bit.
- **No LUTs, no colour grading.**
- No effects, motion keyframes, borders, stickers, B-roll, stock, photo import, multi-video projects.
- **No publish kit**, review links, versions, apply-look, packet.
- No URL/XHS/path import.
- No voice cloning, cloud voices, generated music, provider keys.
- No multi-set comparison UI, strength score, queue-all from Moments. Smart story finding stays.
- No STTN/MI-GAN/Telea/Navier-Stokes picker, GPU toggle, follow-camera toggle.
- No admin, Classic, LAN review links, telemetry.

### Locked decisions

| Decision | Value |
|---|---|
| Distribution | Mac App Store only for Phase 1 |
| Price | $29 paid upfront |
| Minimum macOS | 26+ |
| Local runtime | ONNX only in the MAS build |
| Clean default | LaMa AI fill; Blur explicit |
| Render | 1080p; 24/30 fps; 4 aspects |
| Dub | Required; 3 languages |
| Cloud | Free CPU then paid CPU; GPU later |
| Render hour | 1 hour of worker wall-clock |
| DuckClean lane | **Classic lane**, not Studio |

---

## 1. One-day sequence

| Day | Build | Done when |
|---:|---|---|
| 0 | Freeze scope, prices, model list, App Store decisions | `PRODUCT.md`, `ROADMAP.md`, this file signed off |
| 1 | Sandboxed shell + bundled core + local API + StoreKit test | Clean Mac opens app; sample render; test purchase |
| 2 | Home/Projects + Import | 3 real clips import; copy-on-import; no path/URL |
| 3 | Analyze: Dissect + Detect | Scenes, transcript, text/face/music evidence on 3 clips |
| 4 | Edit + Clean | First clean render; no silent blur; 5 clips |
| 5 | Voice-over + Dub | Voice and dub preview; 3 languages; editable script |
| 6 | Render + Export + Queue + Model Manager + Settings | Full 1080p export; model verify; queue pause/cancel |
| 7 | App Store packaging + TestFlight | Build uploaded; privacy/IAP/review notes |
| 8–9 | HF free CPU broker + Space | Free CPU render; consent; retention; delete |
| 10–11 | Paid CPU + StoreKit subscription | Purchase/restore; 3 concurrent; quota |
| 12–13 | CUDA + GPU benchmark | T4/L4 numbers; Render Plus yes/no |
| 14 | Bugfix, docs, beta | 10 creators; launch gate |

---

## 2. Day 1 — App Store feasibility spike

This is the hard day. If it fails, stop and fix the shell before UI work.

### Tasks

1. **New Xcode project**
   - `mac/DuckSuite.xcodeproj`
   - Bundle ID: `com.ducksuite.app`
   - Minimum macOS 26.0; Apple Silicon only.
   - SwiftUI app lifecycle; one window; native menu bar.
2. **Entitlements**
   - `com.apple.security.app-sandbox`
   - `com.apple.security.network.client`
   - `com.apple.security.network.server` (loopback only)
   - `com.apple.security.files.user-selected.read-write`
   - `com.apple.security.files.bookmarks.app-scope` only if direct bookmark access is used
   - `com.apple.security.device.audio-input` only if recording voice-over
3. **Bundled `duckcore`**
   - New `duck_app.py` entrypoint.
   - Add `DUCKSUITE` profile to `core/profiles.py`; gate routers.
   - Data root from `DUCK_DATA`; no `~/vibecut-lanes`.
   - Bundle Python 3.11 with `python-build-standalone` or `pyinstaller --onedir`; no runtime `pip`.
   - Bundle `ffmpeg`/`ffprobe` LGPL into `Contents/Helpers`.
   - Bundle LaMa ONNX into `Contents/Resources/base-models`.
   - Prebuild and sign `vision_probe`, `transcribe_apple`, `translate_apple`.
4. **Local API**
   - Bind `127.0.0.1:0`.
   - Handshake JSON on stdout: `{port, pid}`.
   - 256-bit per-launch token over a pipe, not argv.
   - `Authorization: Bearer` on every route; no loopback bypass.
   - CSP; no docs/openapi/admin.
5. **StoreKit test**
   - Add `.storekit` configuration.
   - Product IDs: `com.ducksuite.app.render.cpu.10h`, `com.ducksuite.app.render.gpu.10h`.
   - Test purchase, restore, pending, cancel.
6. **Clean-Mac test**
   - Copy `.app` to a fresh Mac or fresh user.
   - Launch without Terminal, without Homebrew, without network.
   - Import sample; render sample; export.

### Acceptance

- App launches on a clean Mac.
- No downloaded code, no runtime `swiftc`, no `pip`, no Homebrew.
- Local API rejects requests without the token.
- StoreKit test purchase unlocks the test entitlement.
- One sample 1080p render completes with bundled ffmpeg + LaMa.

---

## 3. Day 2 — Shell, Home, Import

### New UI

- `static/duck/` with `duck.css`, `shell.js`, `home.js`, `import.js`.
- Direction: “Daylight Bench.” Light chrome, dark canvas, amber accent.
- Native window titlebar; WKWebView editor below.
- Left sidebar: Projects, Analyze, Edit, Render, Export.
- Top: project name, save state, queue button, cloud status.
- Bottom: status strip.

### Home / Projects

- Project cards; sample project; free disk; model status.
- New project; rename; delete with receipt; search.
- No “Your videos” modal; projects and outputs live together.

### Import

- `NSOpenPanel` through Swift bridge; drag/drop fallback.
- Accepted: MP4, MOV, M4V.
- Copy into container on import; no path access later.
- Project name auto-fill; language auto-detect.
- Rights notice: “Clean text you own. Do not remove other creators’ watermarks.”
- Disk preflight with exact free/needed/shortfall.
- No URL, no path field, no analysis toggles, no 15-language picker.

### Acceptance

- 3 real clips import; source copied; app works offline.
- Cancel import leaves no partial project.
- Disk refusal shows exact shortfall.

---

## 4. Day 3 — Analyze: Dissect + Detect

### Dissect

- Reuse `pipeline.probe`, `scan_scenes`, `extract_thumbs`, `extract_text_frames`, `read_text_samples`, `analyze_source`.
- Reuse `stt.transcribe_source` with Apple Speech default and Whisper fallback.
- Build smart story candidates from scenes, transcript and OCR. This is DuckSuite’s USP, not a stripped feature.
- Reuse the story engine: `clipset.py`, `selection.py` and the relevant `pipeline.py`/`detect.py` story functions, adapted to one project and one source.
- Each story shows thumbnail, start/end, hook quote, payoff quote, duration.
- No strength score. No multi-set comparison picker. No queue-all.

### Detect

- Reuse `detect.run_check`, `build_tracklets`, `faces_signal`, `music_from_wav`, `quality_signal`.
- Footage check tab: text regions, speech status, music, warnings.
- “Clean found text” jumps to Edit > Clean.
- “Rescan text” secondary.
- No model names, no severity jargon.

### Acceptance

- 30-minute 1080p source analyzes on M1 8 GB within 15 minutes.
- Scenes, transcript, text boxes, faces, music reload after reboot.
- Cancel stops ffmpeg and vision helpers.
- No duplicate tracklets; one row per real text.

---

## 5. Day 4 — Edit and Clean

### Edit

Keep:

- Cut: trim in/out, split, delete section, reorder, remove silence.
- Frame: 9:16, 4:5, 1:1, 16:9; auto-frame on/off; manual position; safe zones.
- Captions: auto captions, edit text, three styles, top/middle/bottom, burn or SRT.
- Text: five title/lower-third templates; limited font/color; drag on preview.
- Music: add own audio; volume; duck under voice; fade.

Remove:

- Color/LUTs.
- Motion/effects/borders/stickers.
- Narrative/B-roll/voice clone.
- Multi-track pro controls.

Reuse `compose_render.py`, `edits.py`, `render.py`, `captions.py`, `overlays.py`, `audio.py` after gating.

### Clean

- `static/duck/clean.js`.
- Detected text list, grouped by text; checkboxes.
- Primary: “Clean all found text.”
- Method: “AI fill (best)” default; “Blur (fast)” explicit.
- No LaMa/MI-GAN/STTN/Telea/NS names; no GPU toggle; no layer cap.
- Manual box tool.
- Before/after preview; “Test 1 second.”
- Rights notice; “Undo clean.”
- No silent blur fallback. Missing LaMa fails visibly.

### Acceptance

- 5 real clips clean with LaMa.
- Static text has no visible distortion at 1080p.
- Moving shots are acceptable or the UI steers to Blur.
- One layer per text; no duplicate boxes.
- Cache is compressed; a 89-second job stays under 200 MB.

---

## 6. Day 5 — Voice-over and Dub

### Voice-over

- Reuse `audio.build_script`, `tts.py`, `voice_fit.py`.
- Local engines only: Apple voices + Kokoro.
- No cloud keys, no ElevenLabs/MiniMax/OpenRouter, no voice cloning.
- One script, one voice, per-line preview, apply, undo.
- No music generation.

### Dub

- Must ship.
- Reuse `audio.translate_lines`, `adapt_script`, `fit_dub_lines`, `build_bed`.
- Apple Translation helper `tools/translate_apple.swift` on macOS 26.
- Local TTS for the translated script.
- Languages: English, Vietnamese, Chinese.
- Editable translated script; per-line preview; apply; undo.
- Beta label allowed. If a line fails, show the line and the reason; do not drop it silently.
- No cloud translation keys in Phase 1.

### Acceptance

- 30-second voice-over fits; no drift after cut.
- Dub produces intelligible audio in 3 languages on 5 test clips.
- Export includes voice/dub; preview matches export.
- Offline voice-over works; offline dub works on macOS 26 with installed language packs.

---

## 7. Day 6 — Render, Export, Queue, Model Manager, Settings

### Render

- Force `1080p`.
- FPS: 24 or 30 only.
- Aspects: 9:16, 4:5, 1:1, 16:9.
- MP4 H.264/AAC; VideoToolbox on Mac.
- Local queue: one active render; pause/resume/cancel; no auto-resume.
- Cloud option: opt-in; free/paid; show cost, data, retention.
- Estimate from measured local rate; no fake ETA.

### Export

- Save MP4, SRT, cover JPG.
- Native `NSSavePanel`.
- Reveal in Finder, Share, Copy captions.
- No publish kit, no review links, no versions.

### Model Manager

- Core models show “Bundled.”
- Optional packs: size, version, license, source, SHA-256, verify, disk.
- No core model download.
- Verify signature, size, SHA-256 before activation.
- Fail closed; no “skip verification.”

### Settings

- Models, Storage, Cloud Render, Privacy, License, About.
- No API keys, no engine tables, no admin.

### Acceptance

- Full 1080p export opens in QuickTime.
- SRT matches burned captions.
- Queue pause/cancel works; no orphan ffmpeg.
- Model pack verify/remove works; disk math correct.

---

## 8. Day 7 — App Store packaging and TestFlight

### Tasks

1. `PrivacyInfo.xcprivacy`:
   - No tracking.
   - User content only when cloud render is used.
   - Purchase history for quota.
   - UserDefaults, file timestamp, disk space reasons.
2. App Privacy label; privacy policy URL; support URL.
3. StoreKit:
   - $29 paid app (no non-consumable).
   - Render subscription group: $5 CPU, $20 GPU.
   - `appAccountToken` for anonymous quota.
   - Restore purchases; manage subscription.
4. Review notes:
   - Bundled Python helper, no downloaded code.
   - Models are data; optional packs checksum-verified.
   - Local server is loopback only.
   - No account; StoreKit only.
5. Screenshots and metadata:
   - Home, Analyze, Clean, Dub, Render, Export.
   - State 1080p, 24/30 fps, local-first.
6. TestFlight build; internal testers; crash logs.
7. Submit for review.

### Acceptance

- Build uploads.
- TestFlight install on a clean Mac.
- Purchase/restore in sandbox.
- No App Review blocker from the checklist.
- Review submitted.

---

## 9. Day 8–9 — HF free CPU tunnel

### Broker

New `render_broker/` service (FastAPI + Postgres + R2):

```text
POST /v1/render/jobs
GET  /v1/render/jobs/{id}
POST /v1/render/jobs/{id}/cancel
POST /v1/entitlements/verify
POST /v1/appstore/notifications
```

- Holds HF token; app never does.
- Presigns R2 upload/download.
- Stores job manifest, provider ID, state, cost, retention.
- Idempotency = artifact ID.

### Free CPU worker

- Private Docker Space running `duck-render`.
- 1 concurrent; 1080p; 60 s source max; 20 min/month; standard queue.
- Cold start 30–90 s; show “Starting remote renderer.”
- Best effort; no SLA; no 3-concurrent promise.
- Temp files deleted after upload; input deleted after output; 24 h lifecycle.

### Consent

- Off by default.
- Sheet: what leaves, where, why, retention, cost, training (never).
- Checkbox unchecked by default.
- “Delete cloud copy” after download; receipt.

### Acceptance

- Free CPU renders a 60 s clip.
- Cost/hour measured.
- No token in app; no public bucket.
- Delete removes input/output; receipt saved.
- App falls back to local on provider failure with user confirmation.

---

## 10. Day 10–11 — Paid CPU + StoreKit subscription

### Tasks

- HF Jobs CPU Upgrade; one job per Job; 1080p; 10 h/month; 3 concurrent.
- StoreKit auto-renewable subscription; `appAccountToken`.
- App Store Server API validation; Server Notifications V2.
- Quota: deduct on submit; refund on provider failure; no refund after user cancel mid-run.
- Restore purchases; manage subscription.
- Rate limits; max source bytes/duration; abuse controls.
- Cloud queue priority; free vs paid visible.
- Cost meter: hours used, reset date, top-up.
- No auto-overage.

### Acceptance

- Purchase unlocks 10 h.
- Restore works on a second Mac.
- Refund/revoke blocks new jobs but keeps projects.
- 3 concurrent paid jobs run.
- Failed job does not consume quota.
- Margin >50% at measured cost.

---

## 11. Day 12–13 — CUDA and Render Plus gate

### Code

- `textfill/torch_fill.py`:
  - `resolve_device()`: `cuda` → `mps` → `cpu`.
  - `gpu_possible()` platform-agnostic.
  - CUDA OOM fallback to CPU for one span.
  - `torch.inference_mode()`; optional fp16; fp32 parity tests.
- `textfill/lama.py`:
  - `CUDAExecutionProvider` / `TensorrtExecutionProvider` behind env.
- `render.py`:
  - Remote Linux encoder: NVENC/VAAPI; no VideoToolbox.
- Worker image:
  - CUDA runtime, ONNX Runtime GPU, LaMa/MI-GAN/STTN.
  - Same manifest; pinned image digest.

### Benchmark

- 10 clips at 1080p: static, motion and occlusion cases.
- CPU baseline vs T4 vs L4.
- HF Jobs, Beam, Modal.
- Measure wall time, peak VRAM, quality, cost per 90 s.
- Quality: no visible regression vs CPU; no flicker.

### Gate

Launch Render Plus only if:

- GPU is **>2× faster** than CPU on 1080p.
- Cost per 90 s render **<$0.50**.
- Margin at $20/10 h **>50%**.
- Quality is equal or better.

Otherwise: no Render Plus. Keep CPU.

---

## 12. Day 14 — Beta and launch

- 10 creators; 3 real projects each.
- Metrics: activation, first export, clean quality, dub quality, render success, refunds, crash-free.
- Fix top 5 issues; freeze.
- Support docs: models, cloud consent, deletion, refunds, App Store subscription.
- Launch.

---

## 13. Architecture details

### 13.1 Shell

```text
DuckSuite.app/
  Contents/MacOS/DuckSuite
  Contents/Helpers/duckcore
  Contents/Helpers/ffmpeg
  Contents/Helpers/ffprobe
  Contents/Helpers/vision_probe
  Contents/Helpers/transcribe_apple
  Contents/Helpers/translate_apple
  Contents/Frameworks/Python.framework
  Contents/Frameworks/onnxruntime.dylib
  Contents/Resources/base-models/
  Contents/Resources/static/
  Contents/Resources/PrivacyInfo.xcprivacy
```

- Swift starts `duckcore` with `--data-root`, `--port 0`, token via pipe.
- `duckcore` prints `{port, pid}`.
- WKWebView loads `http://127.0.0.1:<port>/#t=<token>`; JS stores token in memory.
- `POST /api/session` sets HttpOnly `SameSite=Strict` cookie for media.
- Quit: SIGTERM group; 5 s; SIGKILL. No launchd.

### 13.2 Local API

- `127.0.0.1` only.
- Token every route.
- Origin allowlist.
- CSP; no remote assets.
- No docs/openapi/admin.
- Path guards; container root.
- Upload limits.

### 13.3 Data layout

```text
~/Library/Containers/com.ducksuite.app/Data/Library/Application Support/DuckSuite/
  models/
    manifest.json
    lama/1.0.0/lama_fp32.onnx
    optional/kokoro/1.0.0/...
  projects/<project_id>/
    project.json
    source/source.mp4
    analysis/scenes.json
    analysis/transcript_v2.json
    analysis/ocr.json
    edits/<edit_id>.json
    renders/<artifact_id>/
      manifest.json
      reel.mp4
      captions.srt
      cover.jpg
    cache/
  state.db
  logs/
```

SQLite tables: `projects`, `renders`, `remote_jobs`, `model_installs`, `settings`. WAL mode.

### 13.4 Manifest

One canonical manifest for local and remote:

```json
{
  "schema": 1,
  "job_id": "art_...",
  "idempotency_key": "art_...",
  "project_id": "prj_...",
  "source": {"sha256": "...", "bytes": 0, "duration": 0, "width": 1920, "height": 1080, "fps": 30},
  "edit": {"hash": "...", "aspect": "9:16", "quality": "1080", "fps": 30, "clean": [], "captions": {}, "audio": {}, "graphics": []},
  "models": [{"id": "lama", "version": "1.0.0", "sha256": "..."}],
  "renderer": {"version": "1.0.0", "image_digest": "sha256:...", "ffmpeg": "6.1-lgpl", "onnxruntime": "1.18.0"},
  "output": {"container": "mp4", "video": "h264", "audio": "aac", "width": 1080, "height": 1920},
  "consent": {"remote": true, "at": "..."},
  "expires_at": "..."
}
```

Artifact ID = SHA-256 of canonical manifest excluding provider, attempt, timestamps, local paths. Never overwrite a ready artifact.

### 13.5 Provider adapter

```python
class RenderProvider(Protocol):
    name: str
    capabilities: ProviderCapabilities
    def estimate(self, manifest: dict) -> dict: ...
    def submit(self, manifest: dict, artifacts: dict) -> dict: ...
    def status(self, remote: dict) -> dict: ...
    def result(self, remote: dict) -> dict: ...
    def cancel(self, remote: dict) -> None: ...
    def delete(self, remote: dict) -> None: ...
```

Implementations: `LocalProvider`, `HFSpacesProvider`, `HFJobsProvider`, `BeamProvider`, `ModalProvider`, `RunPodProvider`. Same `duck-render` image; only launcher differs.

---

## 14. Models and App Store compliance

### Bundle vs optional

| Model | Size | Runtime | License | MAS |
|---|---:|---|---|---|
| LaMa ONNX | ~198 MB | ONNX Runtime | Apache-2.0 | **Bundle** |
| ffmpeg/ffprobe | 40–70 MB | native | LGPL build | **Bundle** |
| ONNX Runtime | ~20 MB | native | MIT | **Bundle** |
| Apple Vision/Speech/Translation | OS | macOS | Apple terms | **Prebuilt helpers** |
| Kokoro | ~300 MB | ONNX | Apache-2.0 | Optional data pack |
| Whisper | 0.9–1.6 GB | MLX/whisper.cpp | MIT | Not in v1; macOS 26 Speech |
| MI-GAN | ~26 MB | ONNX only | Verify | Optional if ONNX + license clear |
| STTN | ~63 MB | PyTorch | MIT/Apache | Remote GPU only |
| Demucs/RoFormer | large | PyTorch | mixed | Not in DuckSuite |
| ProPainter | large | PyTorch | S-Lab non-commercial | **Never** |

Rules:

- Core features must work offline after purchase. No first-run core download.
- Optional packs are data only: no `.so`, `.dylib`, wheels, frameworks or executable code.
- `models/manifest.json` is canonical JSON, Ed25519-signed. Verify signature, size, SHA-256 before activation.
- Download to `.partial`, fsync, verify, `os.replace`; keep `previous/` for rollback.
- Fail closed. No silent blur. No “skip verification.”
- Log license/source/hash in About and `THIRD_PARTY_NOTICES.md`.

### App Store blockers checklist

| Blocker | Fix |
|---|---|
| Runtime `swiftc` | Prebuild/sign `vision_probe`, `transcribe_apple`, `translate_apple` in CI |
| `packs.py` downloads wheels/MLX/torch | Replace with `core/model_store.py`; data only |
| GPL ffmpeg | LGPL build; VideoToolbox; no libx264/x265 |
| Sparkle / license key / Ed25519 activation | Remove; StoreKit only |
| Arbitrary path import | NSOpenPanel + copy into container |
| Local server token bypass | Token every route; 127.0.0.1 only |
| Missing privacy manifest | `PrivacyInfo.xcprivacy`; App Privacy label |
| Missing IAP | StoreKit 2; restore; manage subscription |
| Watermark removal marketing | Own-footage attestation; no platform watermark claims |
| macOS 26 requirement | Declare; test on 26+ |

---

## 15. Render broker and cloud

### Free CPU

- HF private Docker Space; 1 concurrent; 1080p; 60 s max; 20 min/month.
- Best effort; cold start; standard queue.
- No 3-concurrent free.

### Paid CPU

- HF Jobs CPU Upgrade; 1 job per Job; 1080p; 10 h/month; 3 concurrent.
- Quota on submit; refund on provider failure.
- Priority queue.

### Provider alternatives

| Provider | Role | Cost |
|---|---|---|
| HF Jobs/Spaces | primary cheap CPU | CPU Upgrade ~$0.03/hr; T4 ~$0.40/hr |
| Beam | CPU fallback / burst | shared 8 vCPU/16 GB ~$0.18/hr |
| Modal | concurrency/reliability | CPU ~$0.05/core-hr; T4 ~$0.59/hr |
| RunPod | GPU cost | L4 ~$0.59/hr; 3090 ~$0.50/hr |
| Contabo | fixed Linux worker | 16C/64 GB ~$155/mo |

### Data

- R2 for artifacts; zero egress; `$0.015/GB-month`.
- Presigned URLs; short TTL.
- Per-job encryption at rest; no cross-user cache/dedupe.
- Delete input after output; 24 h lifecycle free, 7 days paid.
- No content in logs.

---

## 16. Tests and gates

| Test | Gate |
|---|---|
| Clean-Mac install | G1 |
| Sandbox + token | G1 |
| StoreKit test purchase/restore | G1/G6 |
| Import 3 real clips | G2 |
| Analyze 30-minute source <15 min on M1 8 GB | G2 |
| Clean 20 clips; no visible distortion on static text | G3 |
| Dub 5 clips; 4/5 intelligibility in 3 languages | G3 |
| Render 1080p 24/30; 98% success | G3 |
| Export MP4/SRT; 99% success | G3 |
| App Privacy/review notes | G4 |
| Free CPU cost/time | G5 |
| Paid CPU purchase/refund; 3 concurrent | G6 |
| GPU >2× and <$0.50/render | G7 |
| 10 creators; crash-free ≥99.5% | G8 |

---

## 17. File map

### New

```text
mac/DuckSuite.xcodeproj
mac/DuckSuite/…
duck_app.py
core/paths.py
core/model_store.py
core/queue.py
core/manifest.py
core/providers/base.py
core/providers/local.py
core/providers/hf_spaces.py
core/providers/hf_jobs.py
core/providers/beam.py
core/providers/modal.py
core/providers/runpod.py
static/duck/…
static/duckclean/…            # Phase 2
duck_dub/…                    # only if the dub helper needs its own module
render_broker/…
render_worker/…
docs/handoff/ducksuite-phase1-plan.md
```

### Modify

```text
core/profiles.py              # DUCKSUITE, DUCKCLEAN
app.py                        # profile gating, paths, token
render.py                     # 1080p/24/30 policy; VideoToolbox
textfill/torch_fill.py        # CUDA
textfill/__init__.py          # compressed cache, model SHA
vision.py                     # prebuilt helper
stt.py                        # prebuilt helper
audio.py                      # prebuilt translation helper
static/studio/*               # reuse tokens/components only
Dockerfile                    # new duck-render worker, not legacy app.py
```

### Do not touch for Phase 1

```text
classic_app.py                # except DuckClean profile later
routes_classic.py
static/classic/*
admin/*
batch.py
packet.py
shares.py
preflight.py
url_ingest/*
```

---

## 18. DuckClean from the Classic lane

DuckClean is **not** a Studio profile.

### Lane rule

- Branch/lane: `classic`.
- Entry point: `classic_app.py` or new `duckclean_app.py` configuring `DUCKCLEAN` before importing `app`.
- Profile: `DUCKCLEAN` composed from `CLASSIC` in `core/profiles.py`.
- Features: `classic_page`, `check`, `cleanup`, `ai_fill`.
- Routers: `classic_page`, `check`, `cleanup`; no `studio_edit`, no `packet`, no `preflight`.
- UI: new `static/duckclean/`; no Studio page, no stories, no Edit document, no timeline.
- Flow: upload → detect → AI fill/Blur → download.

### Phase 2 sequence

| Day | Work |
|---:|---|
| 1 | `DUCKCLEAN` profile + entrypoint + upload page |
| 2 | Classic Check + Clean wiring; one row per text |
| 3 | Free HF CPU worker + queue + consent |
| 4 | Linux OCR benchmark (PaddleOCR/EasyOCR/Florence-2/Qwen-VL) |
| 5 | Paid CPU + quota |
| 6 | Express T4 waitlist + beta |

### Linux OCR gate

- 40–60 real clips.
- ≥90% text regions clean.
- No false positives.
- Temporal stability.
- If fail: Mac OCR worker or stay Mac-assisted.

---

## 19. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Sandbox + Python sidecar rejected | Critical | Day 1 spike; sign nested code; clean-Mac test; fallback direct DMG only if approved |
| Core model download rejected | Critical | Bundle core; optional packs data only |
| GPL ffmpeg | Critical | LGPL build; VideoToolbox; `ffmpeg -L` proof |
| StoreKit/IAP rejection | High | StoreKit 2; no external links; review notes |
| Dub quality | High | 5-clip blind test; editable script; beta label; no silent drop |
| Clean quality | High | 20-clip gate; LaMa default; blur explicit |
| HF free CPU too slow | High | 60 s cap; MI-GAN? No; free tier best effort; local fallback |
| GPU not faster enough | Medium | Benchmark before Render Plus; CPU only otherwise |
| Support at $29 | Medium | Docs, diagnostics, no phone, self-serve |
| App size | Medium | ONNX only; no PyTorch; base <1 GB |
| DuckSuite/DuckStudio name confusion | Medium | Always use descriptors; distinct accents |

---

## 20. Open decisions

1. $29.00 or $29.99?
2. macOS 26 only, or 14+ with bundled Whisper/translation?
3. Free CPU: permanent or launch-only?
4. Dub languages: English, Vietnamese, Chinese — confirm.
5. GPU provider order: HF, Beam, Modal, RunPod.
6. Family Sharing for $29 app?
7. Existing VibeCut projects: migration at launch or later?
8. Direct DMG fallback if App Review rejects the sidecar?
