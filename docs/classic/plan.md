# Classic lane plan

Status: **active**, Classic lane only. Last reviewed at `classic` `ba31215`.

Classic is an independent lane. It owns `static/classic/**`, `routes_classic.py`,
and `docs/classic/**`. It does not import Studio or Voice Room UI state, and it
does not merge those lanes into itself. Shared backend modules change only when
the change is additive and tested from Classic.

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

- [x] Remove the global DOM translator and its `MutationObserver`.
- [ ] Translate only explicit `data-i18n` elements. *(load-time static walk
  remains; dynamic copy now falls back to English.)*
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
- [x] Fix `README` rewrite-context default (`6000` vs `10000`).
- [x] Rewrite `docs/classic/testing/classic-beta-pass-2.md` for the current
  labels, Clean confirmation, Vietnamese UI, voice fit and platform copy.
  *(scan-flow step remains for C0.)*

### E. Studio features embedded in Classic

The detailed port plan is in `docs/classic/design/embedded-studio.md`.

- [ ] C0: fixed Classic Edit frame, app bar, text scan and cancel.
- [ ] C1: Layers panel and editable Clean boxes on the preview.
- [ ] C2: found-text list, method picker and single-frame AI fill preview.
  This is a backend port: Classic currently has only work-file Clean.
- [ ] C3: spacing/type scale, icons, layer colours, shortcuts, undo/redo.
- [ ] C4: Import, Moments and Finish brought onto the same frame.

## Release gate

- [ ] No P0 or P1 open.
- [ ] Classic tests pass on the chosen tip.
- [ ] Founder pass recorded on the chosen tip.
- [ ] All commits and the beta tag are signed.
- [ ] `docs/classic/testing/classic-beta-pass-2.md` matches the build.
- [ ] Merge target confirmed: Classic lane only, or explicit merge to `main`.
