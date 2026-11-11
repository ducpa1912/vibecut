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
- LaMa is the only shipped model. GPU (PyTorch MPS) is the render default; CPU fill is an optional
  198 MB pack. Bundle ≈ 981 MB.
- Translation ships no weights and hosts no download: the user supplies a CTranslate2 folder.
- A line over a moving background is flagged `moves`, never silently switched to blur. Only a flash
  under 0.6 s read once defaults to blur.
- Do not hide a limit: measure it and say it in the UI.
- Old information is never deleted. The archives (`old_*.md`) and the HTML reports hold it.
- Model packs live in app data, never in a Hugging Face cache.

## Where the build stands (2026-11-12)

| Fact | Value |
|---|---|
| Tests / JS | 127 pass · `node --check static/duck/app.js` clean |
| Review project | `prj_e95348a97316`, 160 s, 1080×1920, 35 clips, edit `ed_38a4c36a3aae` |
| Clean layers | 42 fill, 0 blur; 1 founder layer `auto: false` (`cl_7b144258ac`, 0.0–0.067 s) |
| Fill | `textfill.VERSION` 15, GPU; hole = the line's ink, grown 6 px |
| Leftover-text check | 42 layers, ≈ 21–37 s after a render; `ink.HIT` 0.85 |
| Last render | `ed_38a4c36a3aae_20261111-235452.mp4`: 0 hits in 2,936 frames, 0 OCR leaks in 4,780 |
| Cold render | 418.2 s against a 420.8 s estimate |

## Known limits that shape the next loops

- The ink check reads whole lines: a partly filled line under 85 % is not reported, and a still
  scene edge inside a box can score as ink.
- A one-frame text flash and scenery are indistinguishable without OCR.
- LaMa cannot rebuild a background it never saw; most lines sit on moving footage.
- Vietnamese transcription needs the 1.61 GB Whisper pack. macOS 26.0, Apple silicon only.

## Open questions for the founder

- None blocking. New briefs arrive as `docs/teams/<loop>/BRIEF.md`; the loop starts when the brief
  exists.

## Request log

Only requests whose loop is still open stay here. A new request appends one entry before code; a
revision attaches to the request that created the thing. Closed entries move to `old_memory.md` with
the loop's commit.

_No open requests._
