# DuckClean memory

This is the request/response history for the DuckClean work session, from the
decision to spin DuckClean out of Classic through the M2 merge and the session
documentation. Dates: 2026-11-07 to 2026-11-11.

Current product branch before this documentation commit: `duckclean` at
`699b41d`. The session log covers everything through that commit.

## 1. Initial DuckClean request

**User request**

> The ui of clean is still so bad and not responsive, it's also not mobile first
> screen or something similar. Plan for a DuckClean (the clean only function to
> be another branch), it still need to be able to import/download the video, then
> detect text & remove it. Plan for distribution idealy using cloudflares pages
> then the local machine can run & render on their own. spin out 2 sub-agents:
> one senior fullstack backend developer with @impeccable together with a ui/ux
> product owner with @taste-skill to revamp the plan to perfect with 3 rounds of
> loop, independent assess, shared note, then discuss & draft the plan please
> include the no back on point they strongly believe in

**Assistant response**

- Ran in Plan mode: read-only, no edits, no server.
- Loaded the Impeccable skill for the backend agent and the taste-skill for the
  UI/product agent.
- Ran three rounds: independent assessment, cross-critique, final reconciliation.
- Produced a reconciled plan:
  - DuckClean = clean-only branch, separate from Classic.
  - Import, probe, detect, review, pre-render blur, AI fill, download.
  - 390-first responsive layout, desktop-first capability.
  - Static UI on Cloudflare Pages; local runner owns video bytes.
  - No fake media, no fake progress.
  - Backend no-back: source never leaves the machine.
  - UI no-back: 390 review is first-class.
- Did not write files in Plan mode.

## 2. Flow, detection check, roadmap and plan

**User request**

> Flow: Import a local video. Probe it. Detect text. Review & Edit detected
> ranges on a timeline. Review the pre-render with bluer. Remove text with AI
> fill. Download the cleaned full-length video. Write the roadmap and plan down.
> But check the file output, detect is bad. Attached file:
> `/Users/happynghia/Downloads/人好猫坏！.mp4`

**Assistant response**

- Probed the real file: 1440×2560, 5.572 s, 30 fps, HEVC/AAC, 13.8 MB,
  MD5 `57a6d164422eeb95a9517cf4727dd1b6`.
- Ran the real detector at 4 fps, 2 fps and all 167 frames.
- Apple Vision read every frame; **zero OCR lines**.
- Inspected full-resolution top/bottom strips; no text, watermark or caption.
- Conclusion: the clip is genuinely text-free. Zero detections are correct.
- `text.confirmed: true` only means OCR ran, not that text was found.
- Created branch `duckclean` from Classic `bb3e89e` and wrote:
  - `docs/duckclean/roadmap.md`
  - `docs/duckclean/plan.md`
  - `docs/duckclean/detection-report.md`
- Commit `f5d4603`.
- Flagged that a real known-text clip is required to calibrate detection.

## 3. Cloud-only pivot

**User request**

> commit & merge any ahead in classic to classic lane online, the focus on the
> duckclean tree. roadmap is wrong duckclean is cloud only with a single purpose
> auto clean the cleanest & best ai removal for text and logo or burnt image on
> video, generate the image if needed. The render is HF worker on CPU or on GPU
> (HF for now GPU cloud later). Commercial in render hour equivelant. Need an
> oauth for user management, and library and other stuff, render through cloud
> worker, and story in blob or other storage cloud. So that mean they can render
> a clip on their phone if they want since render is cloud worker. Forget
> non-negotiables, clean the full-length but dissect to smaller beat will help
> detecting frame by frame & render time to make sure only frame with text select
> and render.

**Assistant response**

- Verified Classic: local `classic` = `origin/classic` = `bb3e89e`; `main`
  stayed `510bee9`.
- Rewrote roadmap and plan cloud-only:
  - Pages SPA → Workers API.
  - Postgres + R2.
  - HF CPU/GPU worker, later dedicated GPU.
  - Clerk OAuth + per-user library.
  - Render-hour equivalent billing.
  - Beat dissection and selective render.
  - Phone support because rendering is remote.
- Replaced local-runner and local-custody assumptions.
- Commit `dc38cec` (`docs(duckclean): make the product cloud-only`).

## 4. Fresh blank folder and handoff

**User request**

> now prepare for duckclean on a fresh blank folder, that mean delete current
> directory, and give a handoff prompt to another coding agent

**Assistant response**

- Deleted the old `vibecut-duckclean` worktree only; Classic untouched.
- Created `duckclean` at `/Users/happynghia/Public/Project/Code/drop_eval/duckclean`
  with docs and `HANDOFF.md`.
- Wrote a handoff prompt covering stack, flow, beat pipeline, data model, API,
  worker contract, milestones, acceptance and first tasks.

## 5. Delete Classic and investigate `vibecut-lanes`

**User request**

> wait not enough, the old vibecut-classic if already pushed should be deleted
> too, also check why vibecute need separate vibecut-lanes which stored all the
> media data & job?

**Assistant response**

- Verified Classic was pushed: `classic` = `origin/classic` = `bb3e89e`.
- Deleted the `vibecut-classic` worktree after confirming no tracked changes;
  ignored `.venv`/caches were the only local loss.
- Confirmed `main` stayed `510bee9`.
- Explained `vibecut-lanes`: per-lane runtime isolation for multiple worktrees
  share one backend. Each lane has its own port, data root, jobs, settings,
  packs, media, recordings and caches. `scripts/lane-env.sh` maps Classic 8796,
  Studio 8795, Voice 8797.
- Measured lanes: Classic 225 MB, Studio 484 MB, reset 3.9 MB, total 713 MB.
- Recommended deleting the orphaned Classic lane only if old jobs/media are not
  needed; did not delete it automatically.

## 6. GitHub target and Classic reuse

**User request**

> question with your handoff and the document, did other agent know which github
> repo they're working on, and will they repurpose the code from classic?

**Assistant response**

- No: the handoff had no remote/branch, and its Classic reference pointed at the
  deleted worktree.
- The plan still said “cut from Classic”.
- Recommended a new branch in `ducpa1912/vibecut`, separate from Classic.
- Gave exact `git archive origin/classic` extraction for `detect.py`,
  `clean_source.py`, `pipeline.py`, `textfill/`.
- Stated the intent was to port engine logic, not the Classic app.

## 7. New branch decision

**User request**

> A new branch separate from Classic

**Assistant response**

- Confirmed the target: same `ducpa1912/vibecut` repo, `duckclean` branch,
  orphan history, no shared ancestry with `classic` or `main`.
- Recommended orphan over branching from `main` to keep the tree clean.
- Later implemented and pushed the orphan branch.

## 8. Who is working in DuckClean?

**User request**

> are you the one who work in duckclean? check

**Assistant response**

- Checked the folder and found untracked `api/`, `web/`, configs and
  `.freebuff/project-id`.
- Confirmed: no, Freebuff was working in the same folder.
- Timeline: handoff created 12:36; Freebuff scaffold 12:55–13:14; repository
  still at the docs commit.
- Flagged two writers in one tree as a collision risk.

## 9. Review Freebuff’s first build

**User request**

> is there any problem with what they build?

**Assistant response**

- Reviewed M0/M1 scaffold. Found:
  - duplicate `Runtime` interfaces and test harness mismatch,
  - ESLint type-only import,
  - ffmpeg test hung on infinite `anullsrc` with no `-shortest`,
  - wrong HMAC test helper,
  - `/health` auth test wrong,
  - probe/proxy tests expected nonexistent fields,
  - Ruff/Mypy/Prettier failures,
  - stale repo/Classic paths.
- Fixed the build blockers, added local file-URL test seam, corrected tests.
- `make check` green: 63 API tests, 26 worker tests.
- Pushed orphan branch `duckclean` at `ac1e200`.
- Deleted the old local-only `duckclean` branch `dc38cec` from the shared repo.

## 10. Finish M1, explain Clerk/R2/Postgres

**User request**

> update the doc like above so they have the git repo and everything they need.
> then finish m1, what is clerk, which r2, it suppose to have postgres, where is
> it now?

**Assistant response**

- Explained:
  - Clerk = hosted identity/OAuth; not a database.
  - R2 = Cloudflare object storage, bucket `duckclean-media`; not created.
  - Postgres = not provisioned; only PGlite tests; Hyperdrive placeholder.
- Built M1 web surface:
  - Clerk gate, library, upload with real bytes, probe facts, proxy playback,
    error/empty/loading states, real progress.
- Added:
  - `docs/duckclean/infrastructure.md`
  - `api/.dev.vars.example`
  - `web/.env.example`
  - `infra/r2-cors.json`
  - worker Dockerfile/README.
- Accepted `CLERK_AUDIENCE` empty by default; JWT template optional.
- Commit `c139d4a`; worker image commit `2f29f6e`.
- Stated live M1 blocked by Clerk, Postgres, R2, queues, Wrangler login, deploy.

## 11. Provider alternatives

**User request**

> review the alternative to clerk, r2 and postgrest, find online cloud solution &
> find all the best, affordable, cheapest solution for them

**Assistant response**

- Clarified PostgREST is a REST layer, not Postgres.
- Researched current prices and wrote `docs/duckclean/providers.md`.
- Findings:
  - Auth: Clerk free 50k MRU; WorkOS 1M MAU free; Supabase Auth; Better Auth;
    Logto; Firebase; Kinde; Auth0/Cognito expensive at B2C scale.
  - Storage: R2 best for video egress; B2 best storage-heavy/low-egress;
    Hetzner best EU; Wasabi bad below 1 TB/90 days; S3/Supabase Storage bad for
    video.
  - Postgres: Neon free/Launch cheapest idle; Supabase Pro best one-bill;
    Railway/Render/DO; avoid D1/Turso rewrite for M1.
- Recommendation: keep Clerk + Neon + R2 + Workers Paid for M1; re-evaluate auth
  at 50k–100k MRU; keep R2.
- Commit `da9aae3`.

## 12. Hosting and GPU missing from cost model

**User request**

> your planning above did not consider cloud hosting which can either subside the
> db cost & hosting or increase the cost of the plan at 3 scales

**Assistant response**

- Corrected the missing hosting/worker lines.
- Added `docs/duckclean/cost-model.md`:
  - Early: ~$6–30/mo.
  - Growth: ~$150–210/mo.
  - Scale: ~$1.4k–2.0k/mo before auth.
  - Clerk at 1M adds roughly $19k/mo.
  - GPU-minutes are the biggest unknown; 5 GPU-min at 20k renders ≈ $983.
- Updated plan, roadmap, infrastructure, providers.
- Added `npm run m1:doctor`.
- Commit `a1e37ba`.

## 13. LaMa must be CPU

**User request**

> why: FAIL api/.dev.vars is missing, FAIL web/.env.local is missing, FAIL
> Wrangler is not logged in. And LaMa must use CPU not GPU for clean job

**Assistant response**

- Explained the three FAILs are local setup, not code:
  - secrets file not created; example exists;
  - Vite env not created; example exists;
  - Wrangler never logged in.
- Enforced LaMa CPU:
  - `deviceClassForEngine('lama') === 'cpu'`;
  - render/preview reject `lama + gpu`;
  - worker `SelectionGroup`/`ManualRegion` reject it.
- Updated plan/contract/cost/roadmap/infrastructure.
- Tests: 64 API, 27 worker. Commit `b5e85d9`.

## 14. Build env and Vite key

**User request**

> build the env for me, how to get vite key?

**Assistant response**

- Created local:
  - `api/.dev.vars` with generated HMAC;
  - `web/.env.local` with placeholder Clerk key;
  - `worker/.env` with the same HMAC;
  - `worker/.env.example`.
- All ignored by git.
- Doctor then: 13 ok, 6 fail — Clerk issuer, Vite key, 3 R2 values, Wrangler.
- Explained Vite key = Clerk publishable key `pk_test_...` from Clerk Dashboard →
  API keys; issuer goes to `CLERK_ISSUER`; never use `sk_...` in Vite.
- Added docs/example at `3c09dfe`.

## 15. Clerk is not Next-only

**User request**

> note vite clerk only next, vue and some other

**Assistant response**

- Clarified Vite is the bundler; Clerk React works with Vite; Next is optional.
- Listed Clerk SDKs for React Router, Astro, TanStack, Vue, Nuxt, Expo,
  Electron, Android, iOS.
- Noted the repo used `@clerk/clerk-react` (Core 2); current docs use
  `@clerk/react`.
- Commit `62d528c`.

## 16. Review Freebuff M2

**User request**

> checking the progress from freebuff, is there any issue, is the code good to
> commit and merge?

**Assistant response**

- Reviewed a large M2 diff: route split, local PGlite/MinIO, detect/dissect,
  components.
- Found P0/P1:
  - failed detection retry orphaned a run,
  - `scope` ignored,
  - engine truth mismatch (`paddleocr` recorded, RapidOCR ran),
  - stale beat state,
  - moving-text mask wrong,
  - 600-frame cap/effective fps lie,
  - OCR missing from setup/CI,
  - worker detection errors became 500s,
  - poster not HEAD-verified,
  - dev-db nested transactions,
  - tile/grouping gaps.
- Verdict: not mergeable without fixes.

## 17. Fix everything and hand off

**User request**

> fix everything so it can merge and then create a hand-over prompt so freebuff
> understand the project better

**Assistant response**

- Fixed:
  - retry via `createOrRetryJob`,
  - scoped detection + unread beats stay pending,
  - RapidOCR engine truth; PaddleOCR rejected,
  - beat reset per run,
  - real `effective_fps` on truncation,
  - union mask across moving ranges,
  - poster HEAD verification,
  - worker `DetectError` mapping,
  - 3×3 tiling,
  - multi-line area grouping,
  - OCR extra in `make setup`/CI,
  - dev-db migration transactions,
  - fontsource dependency placement,
  - library detection includes `beats`,
  - Clerk React 6 migration and clean audit.
- Added `FREEBUFF_HANDOFF.md`.
- Tests: 68 API, 40 worker; all gates pass.
- Commits:
  - `7639128` — M2 detection + local worker path;
  - `699b41d` — Clerk React 6 + audit fix.
- Pushed `origin/duckclean`.

## 18. Session documentation

**User request**

> review this conversation session log from the decision to start duckclean, to
> fully update the html without any information left out, include my initial
> request & how you response, then also write the agent.md (direction for any
> coding agent to work with this project duckclean in this local directory),
> memory.md (all my request & your response) & todo.md to list everything need
> to do, even things that done and not.

**Assistant response**

- Created this `memory.md`.
- Created `AGENTS.md` for coding agents.
- Created `todo.md` with done and pending work.
- Created `SESSION.html` as the full self-contained session log.
- Linked the documents from the repo.

## 19. REQ-20261111-01 — software factory workflow

**Class:** new capability (process)
**Status:** done for the workflow definition; enforced from the next new request
**Request**

> update the direction in agent.md that each time there is a new request that is
> totally new (not things like revise the ui/ux, but detailed like i want the
> transcript panel inside the video preview panel), and your response to that
> request need to be write in to memory.md and what you plan to do into todo.md,
> this to create a software factory system or a systemactic agent coding workflow

**Response / decision**

- Added a Software Factory Workflow to `AGENTS.md`:
  - Intake → Classify → Memory → Todo → Contract → Build → Verify → Ship →
    Reflect.
  - Defined **totally new** vs revision/bugfix.
  - Required a `REQ-YYYYMMDD-NN` entry in `memory.md` before work.
  - Required a linked checklist in `todo.md` before work.
  - Required contract updates before code when wire/data/state changes.
  - Required tests, `make check`, real-media acceptance where relevant.
  - Required code + memory + todo in the same commit.
- The example “transcript panel inside the video preview” is a new capability,
  not a UI polish revision.
- Revisions that only change spacing, colour, copy, layout or dependency patch
  do not create a new REQ unless they alter contract, data, acceptance or a
  user-visible capability.

**Artifacts**

- `AGENTS.md` — workflow, classification, templates, source-of-truth boundaries.
- `memory.md` — this entry.
- `todo.md` — workflow enforcement checklist.

**Verification**

- The next totally new request must produce a REQ entry in `memory.md` and a
  linked todo section before implementation.
- UI-only revisions remain lightweight.

**Commit**

This documentation commit; see `git log --oneline -1`.
