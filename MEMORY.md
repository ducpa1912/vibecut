# MEMORY — DuckSuite current direction

**Read `AGENTS.md` first, then this file and `TODO.md`.** History is in `old_memory.md` (agents do
not read it). Keep this file under ~80 lines: direction, decisions in force, open requests.

## Direction

DuckSuite is an offline macOS video editor for one long video: Check finds the scenes, the
transcript and the burned-in text; Clean removes that text with a local fill; Edit writes script,
captions and voice; Render writes one 1080p MP4. Local only, one project at a time, one $29
purchase. Planning is closed — the next commits are code, one loop at a time.

## Decisions in force

- Merge target is `ducksuite`. `main` has no common ancestor, lives in another worktree, never merged.
- App Store, signing and TestFlight are paused by the founder. Do not start them.
- v1 is completely local: no account, no upload, no telemetry, no keys. A step may take a
  user-supplied local model; no step needs a download.
- LaMa is the only shipped model. GPU (MPS) is the default; CPU fill is a 198 MB pack. Bundle ≈ 981 MB.
- Translation ships no weights and hosts no download (user CTranslate2 folder). Packs live in app data.
- A line over a moving background is flagged `moves`, never silently switched to blur. Only a flash
  under 0.6 s read once defaults to blur.
- Do not hide a limit: measure it and say it in the UI. Old information is never deleted (`old_*.md`).
- Moving fill (2026-11-12): no video-inpaint engine has a commercial weight licence; LaMa and the
  `moves` warning stay. A user fill model folder (ONNX or TorchScript; the built sidecar imports onnxruntime, loop 24) replaces LaMa.
- Rewrite is Apple Intelligence, else basic cleanup; no Ollama fallback. `online_*` settings are gone.
- Cut (loops 14–19): `edit.cut` runs in ffmpeg as crop → scale → sharpen → grade → pad (bars stay
  black); enhance is Lanczos + unsharp only when drawn larger; the player grade is CSS, labelled
  approximate. The leftover check reads the source through the same filters (`render.check_view`).
- Output fps is automatic: 24 when the source is within 0.6 of 24, else 30; Render shows it.
- Native UI track planned (`PLAN.md`, N1–N8), three decisions open in `TODO.md`; not started.

## Where the build stands (2026-11-16)

| Fact | Value |
|---|---|
| Tests / JS | Last code verification: 346 pass · `node --check static/duck/app.js` clean |
| Review project | `prj_e95348a97316`, 160 s, 1080×1920, 35 clips, edit `ed_38a4c36a3aae` |
| Clean layers | 42 fill, 0 blur; 1 founder layer `auto: false` (`cl_7b144258ac`, 0.0–0.067 s) |
| Fill | `textfill.VERSION` 17; PyTorch GPU remains default. Core ML is opt-in and blocked from promotion by measured padding drift and native MPSGraph abort; a Core ML clip carries `:coreml-gpu`. |
| Leftover-text check | per letter, per frame, output against source; 40 of 42 lines checked, 68–81 s on a quiet Mac (170–190 s with the Mac under load); `inkcheck.SAME` 20 (untouched text measures 9–13.4, a fill 30+) |
| Last render | `ed_38a4c36a3aae_20261112-104149.mp4` (warm ink store, 24 of 24 spans reused): 0 leftover in 2,964 frame checks; 2 lines not checked, shown with the reason |
| Cold render | 620–847 s on this Mac (was 418 s): every frame is filled alone where something crosses the text. Model time is ≈ 64 % of it |
| Estimate | from the fill's own run plan: 790.4 s against 847.2 s real (6.7 % low), shown as a range. Warm call < 0.3 s; first ever for a project 144.8 s in the background; one queued job per edit (older saves never run); a starting render never waits in the queue |
| Ink store | `<data root>/ink`, one file per line with every `Ink` field, `ink.STORE_VERSION` 2, shared by estimate, queue and render, capped at 512 MiB |
| Layout | Render is two columns (320 px settings/start/estimate, queue right with finished cards); inspector shows `N of M layers` with a fade; empty timeline lanes are 32 px with a `+`; the player hugs the picture (9:16: 410x728 / 353x628, 15 px black; Edit 303x537 / 269x477, 0 black); the transcript sits above the player controls; every scroll area fades while more is below |

## Known limits that shape the next loops

- Media cleanup 2026-11-17: old screenshots, scratch footage/projects and caches removed; analysis retained. `build/` 9.8 → 2.4 GiB; rebuilt app and model packages kept. App-container data untouched. See `docs/MEDIA-CLEANUP.md`.

- The leftover check judges only lines that have a clean layer and steady strokes. A line under
  5 frames long, or with no steady strokes, is counted as "not checked", never as clean. Text that
  Check never found has no layer and is not judged.
- A steady shot cut at both ends of a line: scenery in the box cannot be told from text by time, so
  the hole there is a little larger than the letters.
- Render time on this 8 GB Mac varies by a third for one edit (estimate is a range); a 3-clip span measured 171–601 s cold.
- Three wins are measured and not built: crop the fill decode (35–50 s), share the check's decode
  (52.8 s), fewer key frames (about a third of the model time, but it changes pixels). Loop 27 takes
  the first two and the early ink store; fewer key frames stays out.
- LaMa cannot rebuild a background it never saw. Vietnamese needs the 1.61 GB Whisper pack.

## Open questions for the founder

- Native UI decisions; FFmpeg offer contact address; a Vietnamese clip for the Whisper comparison.

## Request log

- REQ-20261116-02 · Core ML authorized; 11-size package merged; compiler/update/fallback-cache fixes. 3C review rejects promotion: exact drift 5–19/255, padding 169/255, native abort on the 9th function; PyTorch stays default, VERSION 17. See `docs/teams/loop-3c-coreml-review/review.md`.

Open requests only; a new request appends one entry before code, a revision attaches to its request,
closed entries move to `old_memory.md` with the loop's commit. Open work is in `TODO.md`.

- REQ-20261111-02 · $29 build readiness · PLAN loop 8 (REQ-20261115-02 P4). Loop 26 (2026-11-16, built by the sub-leader after an OpenCode 503): exact size + publisher digest per pack file (Kokoro has none published), FFmpeg source offer in Settings, fill repair line, creator import copy in the core; Whisper table only. Open on the founder: contact address, Vietnamese clip, microphone test.
- REQ-20261111-11 · ink check · D8, D9, two unchecked lines, cold cost (loop 27). Revised 2026-11-13: fix-01, fix-03.
- REQ-20261112-04 · Cut · CoreML research open. Revised 2026-11-13: fix-02.
- REQ-20261112-07 · story · loop 20, local VLM scene captions (roadmap).
- REQ-20261118-01 · 2026-11-18 · founder: the Clean layer list cannot be selected or removed, and Edit shows no transcript box. Read as: a visible, selectable layer list at every window size and a box that says why there is no transcript. Outcome: 3A/3B below; layer removal and box-click selection are founder proposals in TODO.
- REQ-20261116-01 · 2026-11-16 · "Now try the Core ML with LaMa GPU" → read as: convert the same LaMa weights to a Core ML package and measure speed and pixels against PyTorch GPU, in `build/coreml-lama/` (no app change). Outcome 2026-11-16: converts (99 MB FP16); Core ML CPU+GPU 406 ms vs PyTorch MPS 550 ms per 512 run (1.35×), max diff 3/255; Neural Engine rejects it. Open: flexible sizes, real footage, PyTorch still used by other fill slots (`docs/teams/coreml-lama-test/review.md`).

### REQ-20261115-02 · 2026-11-15
**Request:** "except the native UI, tell opencode to oneshot from 2 loop to 6 Layout odds and ends"
**Read as:** five phases: P1 review leftovers, P2 layout odds, P3 PLAN loop 7, P4 PLAN loop 8, P5 fill/check cost.
**Response:** brief `docs/teams/loop-23-oneshot/BRIEF.md`, then one loop per phase, each verified.
**Outcome:** P1 closed in loop 24 (`bc1894c`, accepted `b109e45`); P3 closed in loop 25 (`b9ad447`); P4 code shipped in loop 26 (`a20954b`), founder items open. P5 → loop 27, P2 → loop 28 (ordered 2026-11-16 by the Senior PO on the founder's word). 324 tests; VERSION 17.
