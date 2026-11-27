# DuckSuite — App Store readiness and the three-agent plan (REQ-20261125-03)

Founder, 2026-11-25: "First check how ready is DuckSuite to be published on Appstore, with all
licensing put in mind and the completeness of the product. Then derives a plan to finish it with
OpenCode & Codex." The App Store gate was paused by decision; this plan asks to lift it in stages
(Gate A below). Nothing here signs, uploads or submits.

Audited by the PO (Opus) against the built bundle `build/DuckSuite-Xcode.app` from `f5e75d3`,
the repo, and `PRODUCT.md`. Facts marked *(verify)* still need a citation from the researcher.

## Verdict

**Not ready.** Four blockers would fail review or break the licence terms today, six more
things must happen before an upload, and the product has broken promises a $29 buyer would hit.
Estimate: 3–4 weeks of agent work plus founder steps, if the blockers are taken in order.

## A. Blockers (would fail review or break a licence)

| # | Blocker | Evidence | Fix |
|---|---|---|---|
| B1 | **GPL-3 code inside the app.** `libespeak-ng.dylib` and `libpcaudio.0.dylib` ship in `duckcore/_internal`, pulled in by `kokoro_onnx` for phonemes. GPL-3 cannot ship in a closed-source paid App Store app. | bundle listing | Remove `kokoro_onnx` + espeak from the bundle. Voice stays on macOS voices and the user ONNX voice folder; the Kokoro pack returns only with a non-GPL phonemizer (English-only `misaki` rules, or none). |
| B2 | **No FFmpeg in the build.** Every build since 2026-11-23 printed `warning: LGPL ffmpeg not copied`; `build/ffmpeg-lgpl` is gone. The app falls back to `shutil.which("ffmpeg")`, so on a buyer's Mac Check and Render fail. AV1 (`libdav1d`) is missing too. | build logs, `media._tool` | Rebuild with `scripts/build-ffmpeg-lgpl.sh` (relative prefix, no home path strings), and make the build **fail** when FFmpeg, FFprobe or dav1d is missing. |
| B3 | **Signing is ad hoc and helpers lack sandbox entitlements.** `Signature=adhoc`, no team. `sign-local-app.sh` signs nested binaries with no entitlements; the Mac App Store needs every executable (duckcore, ffmpeg, ffprobe, five Swift helpers, every `.dylib`/`.so`) signed with the team identity, and each executable with `app-sandbox` + `inherit`. | `codesign -dv` | A Mac App Store signing script with a real identity and provisioning profile, then `xcrun` validation. Needs Gate A. |
| B4 | **The Whisper pack cannot run in the app.** The pack downloads weights only; `stt._whisper_command` looks for an `mlx_whisper` program (pack, PATH or Python module) and the bundle has none. Vietnamese transcription, which `PRODUCT.md` promises and dub depends on, does not work for a buyer. Shipping a downloaded runner would break guideline 2.5.2 (no downloaded executable code). | bundle listing, `stt.py:407-426` | Put a Whisper runtime **inside** the app (whisper.cpp with Metal, MIT, built from source and signed), keep the weights as a data pack. Or drop Vietnamese speech from v1 and say so. Founder decision D3. |

## B. Must happen before an upload

| # | Item | State | Fix |
|---|---|---|---|
| U1 | Third-party notices match the bundle | `THIRD_PARTY_NOTICES.md` lists about 20 components. The bundle also has PyTorch, coremltools, CTranslate2, SentencePiece, protobuf, uvloop, watchfiles, PyYAML, tqdm (MPL-2.0), OpenSSL, LLVM libomp, FreeType, libtiff, libjpeg, libpng, HarfBuzz, lcms2, OpenJPEG, libwebp, libavif, Brotli, xz, libxcb/libXau, zlib-ng, SQLite and mpdecimal, with none listed. The LaMa entry names `lama_fp32.onnx`, but the app ships `big-lama.pt` and a Core ML conversion. | Generate the notices from a scan of the bundle (dist-info licences + a dylib table), and add a test that fails when a bundled component has no notice. |
| U2 | Trim what the app does not use | X11 libs (`libxcb`, `libXau`), image codecs Pillow pulls in, `setuptools`, and the 112 MB Core ML package plus 13 MB coremltools while Core ML is a test engine | Drop what nothing imports; decide on Core ML (D4). Smaller bundle, fewer notices. |
| U3 | FFmpeg LGPL source offer | Contact address is still `<contact address>` in `duckcore/licenses.py` and `Licenses/FFmpeg-SOURCE.txt` | Founder gives the address (D5); ship the exact source tarball plus build script with the offer. *(verify: App Store terms vs LGPL-2.1 §10; common practice is to ship FFmpeg as a separate LGPL executable with a source offer)* |
| U4 | LaMa weights licence | Code Apache-2.0; `big-lama` was trained on Places365, whose terms are research-oriented *(verify)* | Researcher writes a one-page finding with citations; founder decides (D6). |
| U5 | Runtime compiling | `stt._apple_transcribe_helper` and peers compile Swift with `swiftc` when a helper is missing. A buyer has no `swiftc`, and compiling at runtime is not allowed. | In a release build, helpers must exist; remove the compile path from release. |
| U6 | Store listing | No privacy policy URL, support URL, screenshots, description, review notes, age rating or name check | PO drafts; founder hosts the two URLs (D7). |

## C. Product completeness (what a $29 buyer would hit)

| # | Gap | Source |
|---|---|---|
| P1 | The founder hand test of loops 10–26 has never been run in one sitting | `docs/teams/founder-test-all.md` |
| P2 | Layout at 1024×700 and 200 % zoom never measured; the story player and render playback never opened | loop 28, `TODO.md` |
| P3 | Timeline split, reorder and remove-silence are not built ("Trim works, the rest does not") | `TODO.md` Later |
| P4 | Settings → Workflows shows empty text/music/script ladders with no reason; the "Engine:" prefix on the speech failure | REQ-20261118-02 leftovers |
| P5 | Clean layers cannot be removed (only Off); clicking a box does not select its layer | REQ-20261118-01 proposals |
| P6 | Render cost: a cold render is 620–847 s for 160 s of video; the estimate for short edits is unreliable | loop 27 |
| P7 | Saved fills stop below 10 GB free disk, so a stopped render restarts its clip | REQ-20261125-02 |
| P8 | Microphone test, Kokoro hash, the Vietnamese clip and the FFmpeg contact wait on the founder | `TODO.md` Waiting |

What is in good shape: local-only (no cloud route, network audit, `HF_HUB_OFFLINE`), App Sandbox on,
a privacy manifest with reasons, `ITSAppUsesNonExemptEncryption = false`, microphone usage string,
macOS 26 floor stated, 386 tests, no telemetry or account.

## D. Founder decisions (each blocks the step it names)

| # | Decision | Recommendation |
|---|---|---|
| D1 | Lift the App Store pause in stages: Gate A (signing + validation builds, no upload), Gate B (TestFlight), Gate C (submission) | Lift Gate A now |
| D2 | Apple Developer team, bundle id `com.ducksuite.app`, app name availability | Founder checks in App Store Connect |
| D3 | Vietnamese speech in v1: in-app whisper.cpp, or cut it from v1 | **Decided 2026-11-26: build whisper.cpp in-app** (founder chose P-B) |
| D4 | Core ML: ship it as a test engine or drop it (−125 MB) | Drop from v1 until its abort is fixed |
| D5 | FFmpeg source-offer contact address | — |
| D6 | LaMa weights licence finding | Read the researcher's page first |
| D7 | Privacy policy and support pages (host) | A plain static page |
| D8 | v1 scope: are split/reorder/remove-silence required | **Decided 2026-11-26: all three in v1** (founder: "Include remove-silence") |
| D9 | Kokoro: drop for v1 or rebuild without espeak | Drop for v1 |

## E. How the three agents work without stepping on each other

Today all three edit `ducksuite/` on one branch. From now on:

| Agent | Folder | Branch | Port | Data root |
|---|---|---|---|---|
| **Opus (PO)** | `drop_eval/ducksuite` | `ducksuite` (integration; only the PO commits here and pushes) | 8805 | founder's (read only, never re-Checked) |
| **OpenCode** | `drop_eval/ducksuite-opencode` (git worktree) | `oc/<loop>` | 8821 | `build/scratch-root` in its worktree |
| **Codex** | `drop_eval/ducksuite-codex` (git worktree) | `cx/<loop>` | 8831 | `build/scratch-root` in its worktree |

Rules:
1. One loop per agent at a time, from a brief in `docs/teams/<loop>/BRIEF.md` that names the
   files it owns. Two agents never own the same file in the same week; `static/duck/app.js` has
   one owner at a time.
2. An agent commits on its own branch only, never pushes, never merges, never switches the
   integration checkout. The PO reviews the diff, runs the full suite, then merges with
   `--no-ff` into `ducksuite` and pushes.
3. Each worktree has its own `build/`; the 0.8 GB `build/duckcore-venv` is shared by symlink
   (read only). Only the PO builds `DuckSuite-Xcode.app` and opens it for the founder; agents
   never `open` the app (same bundle id, same container: it would use the founder's data).
4. Codex has no CLI here (desktop app). The founder starts a Codex loop by pasting one line:
   "Work in `drop_eval/ducksuite-codex` on branch `cx/<loop>`; do `docs/teams/<loop>/BRIEF.md`."
   OpenCode is driven by the PO as today (`#high`, one prompt at a time, background, logged).
5. `MEMORY.md`, `TODO.md` and `PLAN.md` are written only by the PO, on `ducksuite`, so agents
   never conflict there; agents write their loop's `review.md` and the PO folds it in.

## F. The plan

Lanes (rebalanced 2026-11-26, founder: "the heavy lifting should be on codex side"):
- **Codex** does the heavy work: release and licensing (build, signing, notices, bundle), the
  in-app Whisper runtime, and timeline split and reorder.
- **OpenCode** does small, bounded fixes, each with one or two files and a clear test: the
  Settings leftovers, layout measurements and fixes, and Clean layer remove.
- **The PO** writes briefs, reviews, merges, writes founder scripts and store copy.

Codex runs one loop at a time and its queue is long, so the order below is its order.

| Phase | Loop | Owner | What done looks like | Needs |
|---|---|---|---|---|
| 0 | S0 · separate the agents | PO | Two worktrees and branches, shared venv link, ports, `AGENTS.md` section "Three agents" | done `d3b8bdc` |
| 1 | R1 · FFmpeg back in, build fails without it | Codex | LGPL FFmpeg 7.1.1, ffprobe and dav1d in `Contents/Helpers`; no home-path strings; the build exits non-zero when one is missing; a test that the bundle has them | — |
| 1 | R2 · GPL out | Codex | `kokoro_onnx`, espeak-ng and pcaudio gone from the bundle; Kokoro pack hidden; a bundle scan test fails on any GPL/AGPL file | D9 |
| 1 | P-A · REQ-20261118-02 leftovers | OpenCode | Workflows ladders hidden or captioned; one plain speech failure | — |
| 2 | P-B · in-app Whisper | **Codex** | whisper.cpp (Metal) built from source and signed inside the app; the pack holds weights only; Vietnamese Check works on the founder's clip | D3, founder's clip |
| 2 | R3 · notices from the bundle | Codex | `scripts/scan-bundle-licences.py` writes the notices table; a test fails on an unlisted component; LaMa entry corrected | U4 finding |
| 2 | P-C · layout (loop 28) | OpenCode | 1024×700 and 200 % measured and fixed on six screens; story and render players opened | after P-A |
| 3 | R4 + R5 · trim, release mode | Codex | X11 and unused codecs gone; Core ML handled per D4; size measured before and after; no runtime `swiftc` and helpers must exist | D4 |
| 3 | P-D · timeline split + reorder | **Codex** | Done per D8, with tests and a founder script; owns `app.js` for the loop, so it starts after P-C merges | D8 |
| 3 | P-E · Clean layer remove + box select | OpenCode | The two REQ-20261118-01 proposals (founder yes 2026-11-26); runs after P-D releases `app.js` | after P-D |
| 4 | R6 · Mac App Store signing (Gate A) | Codex | Signed with the team identity; every nested executable sandboxed with inherit; `xcrun` validation passes; no upload | D1, D2 |
| 4 | F1 · founder hand test, one sitting | Founder (PO writes the script) | `founder-test-all.md` plus every new loop; bugs filed | P-A…P-E merged |
| 4 | S1 · store listing | PO | Description, screenshots list, review notes (local server, sandbox, packs are data), privacy policy text | D7 |
| 5 | R7 · TestFlight (Gate B) | Codex + founder | The uploaded build installs on a clean Mac; mic, packs and render work | D1 |
| 5 | Submit (Gate C) | Founder | — | all above |

`app.js` order: P-A (OpenCode) → P-C (OpenCode) → P-D (Codex) → P-E (OpenCode). OpenCode's
other work between loops is review and tests on a merged branch, never `app.js`.

Loop 27 (render cost) and the Native UI track stay after v1 unless the founder moves them.

## G. Order of the first week

1. PO: S0 today (worktrees, rules in `AGENTS.md`), briefs for R1, R2 and P-A.
2. Codex: R1, then R2. OpenCode: P-A in parallel (no shared files).
3. Founder: D1, D3, D4, D5, D9 — the rest can wait a week.
