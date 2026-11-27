# Append import — Loop C

Date: 2026-11-09
Scope: job API, native error surface, drag check, old-master cleanup.

## Changes

| Area | Change |
|---|---|
| Append job API | `POST /api/projects/{id}/append/job` returns `202` with a job id. |
| Job status | `GET /api/projects/{id}/append/job/{job_id}` reports stage, progress, scenes, offset, duration, warning, error. |
| Current job | `GET /api/projects/{id}/append/job` returns the active job for a project. |
| Upload job | `POST /api/projects/{id}/append/upload/job` streams the file, then starts the job. |
| Browser | Upload starts a job and polls until done or failed. |
| Swift | Import starts a job, polls, then reloads the editor. |
| Native errors | Swift calls `window.duckImportError`; the web shows the failure toast. |
| Preview version | Source URL is versioned by append id and analysis state, so stale preview video reloads. |
| Analysis failure | The video stays imported. Job finishes `done` with a warning instead of inviting a duplicate retry. |
| Old master | Moved into `projects/<id>/history/` after a successful commit when not shared. |
| Drag check | Empty toolbar drags the window. Timeline and brush content do not move it. |
| Job phases | Post-commit analysis failure returns `done` with a warning, never a duplicate-retry failure. |
| Busy guards | Check and render reject queued/running append jobs and active scene reads. |
| Upload race | Append revalidates Check/render state inside the project slot before joining. |
| Job recovery | Stale active jobs expire; committed markers are not rolled back. |
| History retention | The last five replaced masters stay in project history. |
| Client polling | Browser and Swift retry transient poll errors and have a deadline. |
| Cancel | Cancelling the file panel does not show an import error. |

## Verification

| Check | Result |
|---|---|
| Python tests | **52 passed** |
| JS syntax | passes |
| Swift typecheck | passes |
| JSON job | `202`, polls to `done`, offset exact |
| Upload job | `202`, polls to `done`, cleanup runs |
| Browser job | timeline `15 → 16`, stages `Joining → Reading → Done` |
| Drag | toolbar moves window; timeline does not |
| Build | Xcode build succeeds |
| Archive | unsigned arm64 archive succeeds |

## Remaining

- App Store signing identity and team.
- Support and privacy URLs.
- Screenshot footage rights.
- Real microphone test.
- Optional model engines are still not wired.
