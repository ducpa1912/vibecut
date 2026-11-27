# Classic lane plan

Status: **active**, Classic lane only. Phase 5 clean-video polish is built after
`classic` `fb433d7`. The 2026-11-18 Clean workspace revision and review queue are
built in the working tree on base `bb3e89e`. Founder acceptance is **PENDING**.

Classic is an independent lane. It owns `static/classic/**`, `routes_classic.py`,
and `docs/classic/**`. It does not import Studio or Voice Room UI state, and it
does not merge those lanes into itself. Shared backend modules change only when
the change is additive and tested from Classic.

### Scope of the build after the old pin

The previous pin was `193b60e`. The commits after it add the C0–C4 editor
work, the Clean layer and frame route, AI fill with LaMa and its
single-frame preview, the shared model cache, the shared-Python launcher, and
the UI review. They are in scope for this beta build. C0–C4 are built and
listed below; none has a founder pass yet. The two earlier admin commits
(`d064a9d`, `39be317`) remain in scope because Classic's Setup tests and cost
notices read their workflow routes.

## Product decisions

### Platform capability, not “local only”

“Local only” is a runtime mode, not the project identity.

- macOS Apple Silicon: native on-device STT, transcript, TTS and vision where
  available.
- macOS Intel: native where available; cloud for missing native AI.
- Windows / Linux: cloud for AI STT, transcript and TTS; local for render and
  ffmpeg work.

The UI says **On-device AI**, **Cloud AI**, or **Mixed AI** based on the active
capability. It does not promise “local only” to every platform.
See `docs/shared/platform-capabilities.md`.

### Vietnamese is UI/UX, not forced translation

Vietnamese is a curated interface language. Product names, acronyms and short
English terms stay English when that is the better UX. User content is never
translated. See `docs/shared/vi-glossary.md`.

### No Clean attestation in Classic

Classic has no rights gate, attestation tick, watermark refusal or per-video
settings lock. The founder is responsible for having permission to edit the
footage; the UI carries a plain responsibility notice. Every detected kind is
cleanable. Studio keeps its own gate.

### Cobalt removal

Cobalt is removed from the Classic lane. The supported URL paths are `yt-dlp`
and the optional `xhs_get` sidecar. This is a product decision, not an
accidental regression. If Studio still depends on Cobalt, that is a separate
integration decision.

### Voice fit

Preserve-pitch is the default for shared TTS. Classic exposes the effective
1.25× cap. Studio needs its own UI/test coverage before a shared release.

## Workstreams

### A. Documentation and lane ownership

- [x] Remove the old `docs/classic-plan.md`.
- [x] Put Classic docs under `docs/classic/`.
- [x] Put Studio and Voice Room docs under their own folders.
- [x] Add a docs index and a layout test.
- [x] Remove the deleted `classic-prv` worktree from shared docs.
- [x] Replace stale `ship.sh` references with `ship-lane.sh` where the lane
  ships independently.

### B. Platform copy

- [x] Add a capability snapshot to `/api/health`.
- [x] Replace the universal `Local by default` pill with capability-aware copy.
- [x] Update the hero, footer, Setup, render notes and founder scripts.
- [ ] Add tests for Apple Silicon, Intel, Windows and Linux profiles. *(health
  keys, Setup rows and label logic tested; full OS profile matrix still open.)*

### C. Vietnamese UI/UX

- [x] Remove the live `MutationObserver`.
- [ ] Replace the load-time whole-body walk with a `data-i18n` allowlist.
  *(dynamic copy now falls back to English; static walk remains.)*
- [x] Add `t(value)` / `tBlock(value)` for curated dynamic strings.
- [ ] Keep the glossary terms in English. *(glossary added; dictionary
  cleanup still open.)*
- [x] Cover result metadata, cost notices and native confirmations.
- [ ] Preserve unsaved edits across a language switch. *(warns before the
  reload; state restore still open.)*
- [ ] Add DOM-level tests for English, Vietnamese and user content. *(source
  tests added; browser DOM test still open.)*

### D. Outstanding fixes

- [x] T2: add `X-VibeCut-Preview` to `/voice/sample`.
- [x] T5: persist the render baseline in the job, or show an explicit “no
  baseline” state.
- [x] Voice fit: disable or hide speeds above 1.25× while Preserve voice is on.
- [x] Cherry-pick the 16:10 share filter (`268fce8`) or add `_16x10` to
  `_find_share_render`.
- [x] CI: run on `classic` pushes and check all `static/**/*.js`.
- [x] Signatures: verify commits/tags in `ship-lane.sh` and `release.sh`.
  *(Verification goes through `scripts/verify-signatures.sh`, which supplies the
  tracked `scripts/allowed_signers` itself. Plain `git verify-commit` fails on a
  Mac where `gpg.ssh.allowedSignersFile` is unset even though the commits are
  signed, so the old check could not tell a missing setting from an unsigned
  commit. Two keys sign this lane's history; both are in the file with the
  committer principal. `tests/test_signed_commits.py` covers the signed, the
  unsigned, the recorded-exception and the wrong-key paths.)*
- [x] Signatures: stop the tag path from depending on a global Git setting.
  *`release.sh` verifies the range and the new tag through the same script; the
  recorded pre-signing `732254a` and `8186e2a` stay exceptions.*
- [x] Fix `README` rewrite-context default (`6000` vs `10000`).
- [x] Rewrite `docs/classic/testing/classic-beta-pass-2.md` for the current
  labels, Clean confirmation, Vietnamese UI, voice fit and platform copy.
  *(Re-checked against the build after the pin moved: Beta pass 2 now uses the
  real worktree path, describes back **Show all/Show less**, **Dub voice**,
  **New voice-over**, **New voice + music**, **Use my BGM / Choose BGM**,
  **Translating… / ✓ Translation ready**, the **Edit** section and
  **Generate voice sample · ▶**, states that Classic has no media files yet, and
  carries its own current T1–T6 trust table. The T1–T6 block in pass 1 stays
  historical at `1652c92`. Scan-flow step remains for C0.)*

### E. Studio features embedded in Classic

The detailed port plan is in `docs/classic/design/embedded-studio.md`. C0–C4
and AI fill are built; none is founder-passed.

- [x] C0: fixed Classic Edit frame, compact toolbar, text scan and cancel.
- [x] C1: Layers panel and editable Clean boxes on the drawn cut frame.
- [x] C2: found-text list, method picker, AI fill and a LaMa frame preview.
- [x] C3: type scale, one glyph toolbar, layer colours, shortcuts, undo/redo.
- [x] C4: Import, Moments and Finish brought onto the same frame. Classic
  keeps its own top bar instead of importing Studio's shared one.

### F. Clean video and Clean cut

Build contract: `docs/classic/design/clean-video-plan.md`. Phase 1–4 are built;
Phase 5 polish is built and automated suites are green. Founder acceptance is
still open.

- [x] Phase 1: source-clean backend, original-size render, source frame.
- [x] Phase 2: ingest `Clean video`, one-action Source Clean rail.
- [x] Phase 3: Make a reel handoff and source layer carry.
- [x] Phase 4: Cut Clean focus mode, one scan entry, one primary action.
- [x] Phase 5: responsive bottom sheet, reduced motion, focus rings, 11 px
  floor, plain error copy, Vietnamese entries, black-0:00 handling.
- [ ] Founder clean-video acceptance on real media.
  *(PENDING. Commands and checklist: `docs/classic/testing/clean-video-acceptance.md`.
  The automated run is not a founder pass.)*

### G. Clean workspace revision and review queue (2026-11-18)

Build contract: `PRODUCT.md` and `docs/classic/memory.md`. Base `bb3e89e`;
the change set is uncommitted.

- [x] Make Clean one bounded workspace: frame + region manager beside it +
  compact timeline. Remove the separate settings rail from Clean.
- [x] Size the canvas from `.clean-stage-body`, not the window or pane. The
  verified 1280×800 frame is 248×440.
- [x] Compress the timeline to 139 px: a 30 px header, one compact action line,
  16 px ruler and a 44 px lane viewport. Lanes scroll internally.
- [x] Add timeline zoom from 1× to 32×, Fit, horizontal scrolling, a stable
  playhead anchor and a right-aligned last ruler tick.
- [x] Slim timeline bars to 7 px with labels only on hover, selection or focus.
- [x] Restore the region manager: detected text, manual boxes and brush masks
  in one list; selected rows highlight without a rebuild.
- [x] Fix double-click detail: selection no longer re-renders the list.
- [x] Row click/Enter seeks to `start − 0.5 s`; outside-cut rows say
  **Not in this cut** and do not move.
- [x] Remove repeated row metadata: no lane number, no “Selected” badge; low
  confidence shows one **review** note on the confidence line.
- [x] Open AI-fill menus upward in Clean so the timeline cannot clip them.
- [x] Add a four-phase top-bar strip: **Scan → Review → Clean → Render**.
  Render is a shortcut to the reviewed primary action, not a second render
  path. At narrow widths only the active phase and Render stay visible.
- [x] Make selection two-way: a preview box selects its region row and timeline
  bar and scrolls both into view; the row keeps the time inputs.
- [x] Make auto-scanned boxes directly editable: click selects and shows
  handles + the two actions; first drag or resize creates the layer. The
  browser source spec drags and resizes a scanned box, then reloads cleanly.
- [x] Add the selected-box action cluster outside its top-right corner:
  **Unselect** and the **AI / Blur** method toggle.
- [x] Compact the scan rows: time + kind + confidence share one line, sample
  truncates, and the row height is 51 px at 1280×800.
- [x] Add the review queue: multiple files or a folder, sequential upload as
  `source_ready`, Check, AI-fill layer preparation, source review record.
  The queue never renders.
- [x] Add source review persistence:
  `POST/GET /api/classic/jobs/{id}/clean/source/review`, stored at
  `job.classic_text.source`, with `rendered: false`.
- [x] Hydrate prepared source layers in Source Clean from the public job record.
- [x] Keep completed queue job IDs across reloads; show per-file failure states.
- [x] Move `XhsCookieBody` above its route so `/openapi.json` resolves.
- [x] Update the stale browser specs to the manager layout and current AI-fill
  chip/menu UI.
- [x] Update saved-fill tests to control free-disk assumptions; production
  threshold stays 10 GB.

Acceptance for this revision:

- Full suite: **2171 passed, 104 skipped** (92 skips wait on absent real media).
- All four Classic browser specs pass.
- At 1280×800: page exactly 800 px, timeline 139 px, lanes 44 px, no page
  scroll, no console errors.
- No render request is sent by the review queue.
- Founder acceptance on real media is still **PENDING**. The review queue and
  brush-mask management have not been run on a real founder folder.
- Remaining gaps are tracked in `docs/classic/todo.md`: queue retry/remove,
  file-handle reload limits, brush management on real media, GPU timing and the
  language work.

## Release gate

- [ ] No P0 or P1 open. *(no sign-off recorded yet.)*
- [x] Classic tests pass on the current working tree. *(2,170 passed, 104
  skipped on 2026-11-18; 92 skips wait on absent `data/media` real files.
  All four Classic browser specs pass. `node --check` passes for every
  `static/**/*.js`. The revision is not committed yet.)*
- [ ] Founder pass recorded on the chosen tip. *(No pass at `bb3e89e` or on the
  current uncommitted revision; the record table is at the top of the beta
  pass.)*
- [x] All new commits are signed. *(Checked with
  `scripts/verify-signatures.sh`. `732254a` and `8186e2a` are recorded
  pre-signing exceptions; the tag is signed by `scripts/release.sh` when it
  exists. No beta tag exists yet.)*
- [ ] `docs/classic/testing/classic-beta-pass-2.md` matches the current build.
  *(Last re-checked at `c7032b8`. The 2026-11-18 workspace and review queue have
  not been walked against that document yet; update it after the founder pass.)*
- [ ] Merge target confirmed: Classic lane only, or explicit merge to `main`.
  *(Nothing is merged; the lane stays on `classic` until someone asks.)*
