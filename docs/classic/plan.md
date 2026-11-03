# Classic lane plan

Status: **active**, Classic lane only. Last reviewed at `classic` `e38004a`.

Classic is an independent lane. It owns `static/classic/**`, `routes_classic.py`,
and `docs/classic/**`. It does not import Studio or Voice Room UI state, and it
does not merge those lanes into itself. Shared backend modules change only when
the change is additive and tested from Classic.

### Scope of the two admin commits after the old pin

The previous pin was `e38004a`. Two shared admin commits landed afterwards:
`d064a9d` (workflow routes are the only model source) and `39be317` (include the
current OpenRouter speech-to-text catalog). **Both are in scope for this beta
build.** They only make the admin workflow routes the single source for the
rewrite, TTS, music and STT models that Classic's Setup tests and cost notices
read; they are additive to shared core, no Classic page or route was reverted,
and the Classic suite is green with them. The beta pin therefore moves forward
to the tip that contains them instead of back to `e38004a`.

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
- [ ] All new commits and the beta tag are signed. `732254a` and `8186e2a`
  are recorded pre-signing exceptions; do not rewrite them casually.
- [ ] `docs/classic/testing/classic-beta-pass-2.md` matches the build.
- [ ] Merge target confirmed: Classic lane only, or explicit merge to `main`.
