# MEMORY — DuckSuite current direction

**Read `AGENTS.md` first, then this file and `TODO.md`.** History is in `old_memory.md`; agents do
not read that file. Keep this file under ~80 lines: current direction, decisions in force, open
questions. Detailed request history belongs in the archive and in the product report.

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
  `moves` warning stay. A user fill model folder (ONNX needs onnxruntime, not bundled) replaces LaMa.
- Rewrite is Apple Intelligence, else basic cleanup; no Ollama fallback. `online_*` settings are gone.
- Cut (loops 14–19): crop, aspect, fit, look, grade and enhance (`edit.cut`) run in ffmpeg as crop →
  scale → sharpen → grade → pad, so letterbox bars stay black. Enhance (Lanczos + unsharp) only when the
  kept picture is drawn larger; it invents no detail; a CoreML pack is research only. The player grade
  is CSS, labelled approximate. The leftover check reads the source through the same filters
  (`render.check_view`); a line the Cut crops away is "not checked".
- Independent QA 2026-11-13 (`docs/reviews/independent-qa-2026-11-13.md`): all 14 findings fixed
  (`qa-repair-2026-11-13`, `fix-04-qa-followup`). Output fps is automatic: 24 when the source is
  within 0.6 of 24, else 30; Render shows it, no selector. Each finished card plays its own job.
- Native UI track planned (`PLAN.md`, N1–N8): SwiftUI + AppKit, the Python core and its HTTP API stay,
  WKWebView goes at cutover; decisions open in `TODO.md`. No headless Chrome once N1 opens.

## Where the build stands (2026-11-13)

| Fact | Value |
|---|---|
| Tests / JS | 228 pass · `node --check static/duck/app.js` clean |
| Review project | `prj_e95348a97316`, 160 s, 1080×1920, 35 clips, edit `ed_38a4c36a3aae` |
| Clean layers | 42 fill, 0 blur; 1 founder layer `auto: false` (`cl_7b144258ac`, 0.0–0.067 s) |
| Fill | `textfill.VERSION` 17, GPU; hole = each letter's strokes grown 6 px, on the frames that letter is on screen; no fill is reused across something crossing the text |
| Leftover-text check | per letter, per frame, output against source; 40 of 42 lines checked, 68–81 s on a quiet Mac (170–190 s with the Mac under load); `inkcheck.SAME` 20 (untouched text measures 9–13.4, a fill 30+) |
| Last render | `ed_38a4c36a3aae_20261112-104149.mp4` (warm ink store, 24 of 24 spans reused): 0 leftover in 2,964 frame checks; 2 lines not checked, shown with the reason |
| Cold render | 620–847 s on this Mac (was 418 s): every frame is filled alone where something crosses the text. Model time is ≈ 64 % of it |
| Estimate | from the fill's own run plan: 790.4 s against 847.2 s real (6.7 % low), shown as a range. Warm call < 0.3 s; first ever for a project 144.8 s in the background; one queued job per edit (older saves never run); a starting render never waits in the queue |
| Ink store | `<data root>/ink`, one file per line with every `Ink` field, `ink.STORE_VERSION` 2, shared by estimate, queue and render, capped at 512 MiB |
| Layout | Render is two columns (320 px settings/start/estimate, queue right with finished cards); inspector shows `N of M layers` with a fade; empty timeline lanes are 32 px with a `+`; the player hugs the picture (9:16: 410x728 / 353x628, 15 px black; Edit 303x537 / 269x477, 0 black); the transcript sits above the player controls; every scroll area fades while more is below |

## Known limits that shape the next loops

- The leftover check judges only lines that have a clean layer and steady strokes. A line under
  5 frames long, or with no steady strokes, is counted as "not checked", never as clean. Text that
  Check never found has no layer and is not judged.
- A steady shot cut at both ends of a line: scenery in the box cannot be told from text by time, so
  the hole there is a little larger than the letters.
- Render time on this 8 GB Mac varies by about a third for the same edit, so the estimate is a range.
- Three wins are measured and not built: crop the fill decode (35–50 s), share the check's decode
  (52.8 s), fewer key frames (about a third of the model time, but it changes pixels).
- LaMa cannot rebuild a background it never saw; most lines sit on moving footage.
- Vietnamese transcription needs the 1.61 GB Whisper pack. macOS 26.0, Apple silicon only.

## Open questions for the founder

- None blocking. A loop starts when its `docs/teams/<loop>/BRIEF.md` exists.

## Request log

Only requests whose loop is still open stay here. A new request appends one entry before code; a
revision attaches to the request that created the thing. Closed entries move to `old_memory.md` with
the loop's commit. Open requests, one line each (open work in `TODO.md`):

- REQ-20261111-02 · $29 build readiness · PLAN loop 8.
- REQ-20261111-03 · local model slots · PLAN loop 7; fill slot shipped; registry + 3 slots left.
- REQ-20261111-11 · ink check · D8, D9, two unchecked lines, cold cost. Revised 2026-11-13: fix-01, fix-03.
- REQ-20261112-04 · Cut · CoreML research open. Revised 2026-11-13: fix-02.
- REQ-20261112-07 · story · loop 20, local VLM scene captions (roadmap).
