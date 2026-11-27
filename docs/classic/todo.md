# Classic TODO

Ordered follow-up work for the Classic lane. Do not start P1 while a P0 gate is
open unless the work is a direct blocker or a defect found by the founder pass.

Last updated: 2026-11-18. Base `bb3e89e`; current UI and review queue are
uncommitted. Full suite: **2171 passed, 104 skipped** in the working tree.

## P0 — release gate

### P0.1 Founder clean-video acceptance on real media

**Owner:** founder. **Blocker:** named real footage and a real LaMa pack.

- Serve Classic on `8796`.
- Walk `docs/classic/testing/clean-video-acceptance.md` in full.
- Record every row in its Result table. Do not accept from a synthetic run.
- Fix only defects the real run exposes.
- Record P0/P1 findings in `docs/classic/memory.md` and the acceptance file.

**Done when:** the founder signs the acceptance table, or the exact failing
steps are recorded with evidence and a fix plan.

### P0.2 Real LaMa GPU render and timing

**Owner:** developer + founder verdict. **Blocker:** none on this Mac
(`big-lama.pt`, PyTorch and ONNX Runtime are installed).

- Render one real clip on GPU and the same clip on CPU.
- Confirm the picture matches within normal encoder tolerance.
- Record wall time, source duration, resolution and engine in
  `docs/classic/design/ai-fill-clean-learnings.md` or `memory.md`.
- Verify the saved-fill threshold does not silently disable GPU caching:
  this Mac currently has less than 10 GB free, so saved fills are off by design.

**Done when:** a real GPU render finishes and the timing/picture evidence is
recorded. A ready status is not evidence.

### P0.3 Review queue end to end on a real folder

**Owner:** developer + founder.

- Drop several real videos, then repeat with **Add folder**.
- Confirm sequential upload, Check, source-review save, **Review** buttons and
  that **no render request** is sent.
- Reopen Classic and confirm completed job IDs and review rows survive.
- Confirm one bad file does not stop the rest.
- Record defects in the acceptance notes.

**Done when:** every prepared file opens with its detected layers and the raw
network log shows no `/clean/source/render` or `/render` call from the queue.

### P0.4 Commit and ship the current revision

**Owner:** developer, only after P0.1–P0.3 findings are resolved.

- Re-run the full checks.
- Re-pin the shared runtime if any pinned file changed.
- Commit with the founder's signing key. Never disable signing.
- Push only when asked, with `scripts/ship-lane.sh`. Never `scripts/ship.sh`.
- Do not merge into Studio or `main`.

**Done when:** the lane tip is signed, pushed, and the founder pass is recorded
against that tip.

## P1 — review queue robustness

### P1.1 Queue controls

Add per-row **Retry**, **Remove** and **Clear completed**; add **Pause after
current file** and **Cancel current**.

**Done when:** a failed file can be retried without re-adding the folder, and
cancelling leaves no `.part` file or phantom ready row.

### P1.2 Queue persistence clarity

File handles do not survive reload. Keep completed jobs, but show a plain note:
“Unprocessed files must be added again after a reload.”

**Done when:** reload never shows a queued file that cannot run, and every
visible row has a truthful state.

### P1.3 Queue progress and duplicate protection

- Show current file, index, per-file rows found and elapsed time.
- Detect the same file name + size already completed in the queue and skip it
  with a plain note.
- Add a maximum item count with a clear message.

**Done when:** two identical drops do not create two jobs, and progress is
visible without opening the console.

### P1.4 Review record surface

Show the prepared review count and engine on the queue row and in the Source
Clean header. Opening **Review** must load exactly the saved layers once.

**Done when:** reloading a prepared job shows the same number of rows and boxes
as the moment it was saved.

## P1 — Clean workspace usability

### P1.5 Brush and manual region management

- Verify manual boxes and brush masks appear in the region list after save and
  reload.
- Delete removes the saved box or mask and Undo restores it.
- Show one clear label: **Manual box** or **Manual brush**.
- Add a delete confirmation only if Undo is unavailable; otherwise keep the
  current Undo path.

**Done when:** a brush mask can be found, selected, deleted and restored without
guessing which row it belongs to.

### P1.6 Lane discoverability

The timeline currently shows about two lanes in a 44 px area and scrolls for
more. Add a visible lane count or “scroll for more” cue only if the founder
misses rows during acceptance.

**Done when:** a multi-lane clip has no hidden rows without a visible cue.

### P1.7 Zoom and drag at high zoom

- Test 1×, 2×, 4×, 8×, 16×, 32× and Fit.
- Drag, trim and seek near both edges.
- Confirm the playhead stays anchored while zooming.

**Done when:** no drag escapes the timeline and no bar becomes unreachable.

### P1.8 Responsive and input matrix

- Re-run 1440×900, 1280×800, 1050×800, 900×800 and 734×751.
- Exercise pointer drag, touch drag and page scroll across the timeline.
- Confirm no page scroll in the normal populated case.

**Done when:** the Phase 5 browser spec and a manual pass agree.

## P1 — language and platform

### P1.9 Replace the whole-body language walk

Use `data-i18n` keys only. Do not translate user content, file names,
transcripts, OCR text or provider errors.

**Done when:** switching EN/VI leaves user content untouched and no English
sentence is machine-translated.

### P1.10 Keep glossary terms in English

Apply `docs/shared/vi-glossary.md`: product names, providers, models, units and
short editor terms stay unchanged.

**Done when:** a glossary test covers the kept terms.

### P1.11 Preserve unsaved edits across a language switch

Persist or restore Clean state instead of only warning before reload.

**Done when:** a test changes a box, switches language and gets the same box
back.

### P1.12 DOM-level language tests

Add browser coverage for English, Vietnamese and user content in Source Clean
and Cut Clean.

**Done when:** the spec runs in the normal browser suite, not only as a source
string check.

### P1.13 OS capability profiles

Add tests for Apple Silicon, Intel macOS, Windows and Linux profile logic:
health keys, Setup rows and capability labels.

**Done when:** each profile produces the correct **On-device AI / Cloud AI /
Mixed AI** label and no “local only” promise.

## P1 — engineering guards

### P1.14 OpenAPI regression test

`/openapi.json` failed when `XhsCookieBody` was declared after its route. Add a
test that builds `app.app.openapi()` and fails on any unresolved forward
reference.

**Done when:** the suite catches this class of error before runtime.

### P1.15 Compile check that ignores the venv

Use `python -m compileall -q -x '/\.venv/' .` in docs and CI. PyTorch ships a
Python 3.12-only file that makes a plain `compileall .` fail under 3.11.

**Done when:** the documented check passes on a clean developer machine.

### P1.16 Playwright availability

Document `npx playwright install chromium` and keep the browser specs runnable.
A skipped browser suite is not a pass.

**Done when:** a fresh machine can run all four Classic browser specs with the
commands in `AGENTS.md`.

## P2 — performance and scale

### P2.1 Long-source timeline

Test a 90-minute source with hundreds of bars at 1× and 8×. Keep pan, zoom,
seek and row selection responsive.

**Done when:** interaction stays usable and memory does not grow per paint.

### P2.2 Batch scale and storage

Define a queue cap and a disk preflight per file. Show free space before the
queue starts. Avoid holding decoded frames or model sessions between files.

**Done when:** a 10-file queue completes without leaking fill sessions and a
full disk fails one row, not the app.

### P2.3 Render queue separation

The review queue must never render. If a future “render approved” action is
added, it must use the normal render queue and an explicit confirmation.

**Done when:** a test asserts the review queue sends no render request.

## P2 — release mechanics

### P2.4 Merge target decision

Classic ships from its own branch. Decide explicitly whether this revision stays
lane-only or is merged to `main` by the release engineer.

### P2.5 Signed tag

After the founder pass, run `scripts/release.sh --founder-passed` from the
Classic worktree. Verify the range and tag through
`scripts/verify-signatures.sh`.

### P2.6 Documentation sync after acceptance

Update `PRODUCT.md`, `docs/classic/plan.md`, `docs/classic/memory.md` and the
acceptance table with the final tip, test count and founder verdict.

## Definition of done for any item

- Behaviour verified on the real UI or real media where the item requires it.
- Focused tests added or updated; no test weakened to match a number.
- Full suite green, JavaScript syntax green, diff check green.
- Server restarted and health checked after backend changes.
- Current tip, commands and evidence recorded in `memory.md`.
