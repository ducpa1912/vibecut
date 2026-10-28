# Refactor round 1 review (Claude Code)

**Base:** `refactor-1-base` (`1eb472b`), with 1331 tests passing.
**Result:** merged T1 → T4 with no conflicts, plus the review fixes below.

**Checks on `main` (`a025b87`):**
- 1415 tests pass, 7 skipped.
- `compileall` passes.
- `node --check` passes for Studio and Classic.

| Track | Branch HEAD | Suite on branch |
|---|---|---|
| T1 Rights policy | `45b4ac5` | 1383 passed |
| T2 Studio rights UI | `93f61d4` | 1331 passed (JS only) |
| T3 Story picks + trim | `116d3e4` | 1345 passed |
| T4 Performance | `84645a2` | 1348 passed |

## Fixes on `main` (`a025b87`)

1. **P1: batch imports broke with the lock on.**
   - The problem: `POST /api/batches` called the import routes with no `rights`, so every item failed with 409 once the lock was on (the default).
   - The fix:
     - `BatchBody` now takes `rights`.
     - The route refuses up front with 409 while the lock is on.
     - The tick is stored on each batch item and passed to its job.
   - Test: `test_batch_import_follows_the_lock`.
2. **P1: Classic imports broke with the lock on.**
   - The problem: Classic `static/app.js` sent no `rights`, so all four of its import calls failed.
   - The fix: Classic reads `GET /api/rights/policy`. When `needs_import_tick` is set, it asks the user with a confirm dialog, then sends the answer.
3. **P2: Clean auto-fill selected handles.**
   - The problem: T2 dropped the `entry.enabled` filter, so handle/logo tracklets were sent to `cleanup/layers`. The server refused them, but the request was noisy.
   - The fix: the filter is restored. With T1's change, `enabled` already follows the policy.
4. **P2: AV1 decoder name was forced.**
   - The problem: T4 added `-c:v libdav1d`, which fails on an ffmpeg build without dav1d. Homebrew ffmpeg already picks dav1d.
   - The fix: only the thread budget is kept.

## Accepted

- **T1:**
  - `rights.py` is the single policy module.
  - `GET /api/rights/policy` and `job.rights_policy` are available.
  - `POST /api/settings` takes `rights.lock`.
  - Import returns 409 with the lock on.
  - The hard rules hold with the lock on or off: watermark refused, `screen_text` never cleaned, `handle_or_logo` needs the per-video tick.
  - Legacy jobs with no rights record still count as attested.
  - Test note: `tests/conftest.py` sets the lock off for older tests, and the rights tests set it explicitly.
- **T2:**
  - Setup → Rights has the lock switch.
  - Import, Check and Clean show the tick only when the server policy asks for it.
  - localStorage is no longer a policy source.
- **T3:**
  - Picks prefer closing sentences (punctuation plus a pause of at least 350 ms).
  - A spread penalty applies inside 15% of the source.
  - The Edit timeline has trim handles that snap to sentences. They can only shrink the story.
- **T4:**
  - Caption cues are burned as one timed overlay. The profile went from 112.7 s to 15.3 s for a 26 s story, 0.59× story length.
  - The fps filter now runs before scale.
  - Studio has a shared per-job read cache with write invalidation.

## Old branches (recorded as merged)

| Branch | Finding | Action |
|---|---|---|
| `release/paid-v1-flow1-flow2` (contains `feat/flow1-cleanup`, `feat/flow2-overlay`, `feat/paid-v1-build` and `release/paid-v1-flow1-flow2-code`) | Its tree equals the PR #1 squash `4c28f8c`, except `ci.yml` | `merge -s ours`, no code change |
| `feat/creator-captions` | Its one patch (`3b499cf`) is already on main, line for line | `merge -s ours` |
| `ci/macos-ci` | New: Linux and macOS CI jobs | Real merge, plus `node --check` over `static/studio` |

## Open items

- **T3 trim:**
  - Trimming the start doesn't shift layers.
  - Captions aren't rebuilt after a trim.
  - The Edit header keeps the old duration until the story is reopened.
  - Trim is shrink-only.
- **T4:**
  - The 60 fps path is unit-tested only.
  - Overlapping caption cues fall back to the slow overlay chain.
- **Founder tests:** the manual tables are in `docs/handoff/r1-t1.md` through `r1-t4.md`, each under "Founder manual test".
- **CI:** it hasn't run on GitHub yet. The suite there uses `pytest -q` on stock Python 3.11.
