# Append import — Loop B

Date: 2026-11-09
Scope: same-project append integrity. No new product surface.

## Reviewer findings fixed

| Issue | Fix |
|---|---|
| Append upload blocked the event loop | Upload route now streams to disk, then runs the join in the threadpool. |
| Append could delete another project's source | Source paths registered to another project are rejected. |
| Full import could delete a history master | Cleanup only removes files under `imports/`, and only when the caller marks the copy as owned. |
| Offset drifted after re-encode | Normalize only the new clip. Offset comes from the measured join boundary, checked against the old master. |
| Repeated appends re-encoded the old master | Copy path for matching streams; full re-encode only as fallback. Old master is kept. |
| Check/edit/source commit was not atomic | Commit marker with backups. Startup recovery rolls back an interrupted append. |
| Stale `analysis: pending` locked all imports | Pending reads expire after 15 minutes. Active reads heartbeat during analysis. |
| Preview request blocked behind a full encode | Forced preview writes to a side path and swaps when ready; old preview stays playable. |
| Corrupt upload returned 500 and leaked temp | All append failures return 400 and remove the request folder. |
| Append client timed out at 60 s | Append request timeout raised to 900 s. Job API remains Loop C work. |
| Appended speech missed captions | New caption cues are merged for appended scene ids only; existing cues stay. |
| Full-video append never read speech | Full mode now runs the same background analysis and transcript merge. |
| Check/render could race the append | Check and render reject while an append is in flight or analysis is pending. |
| Swift leaked its copied file on failure | Swift removes its request folder when the append call fails. |
| Native import failure was silent | Swift calls `window.duckImportError`; the web shows the failure toast. |
| Editor could keep the old short preview after append | Source URL is versioned by append id and analysis state, so the video reloads when analysis finishes. |

## Verification

| Check | Result |
|---|---|
| Python tests | **47 passed** |
| JS syntax | passes |
| Swift typecheck | passes |
| Append 1: 12 s + 4 s | offset `12.0`, duration `16.022`, audio continuous |
| Append 2: +12 s | offset `16.022`, duration `28.047`, transcript `5 -> 10` segments |
| Append 3: silent 1080p | offset `28.047`, duration `31.053`, audio padded, analysis done |
| Full-video append | analysis done, new source removed |
| Other-project source | `400 That video is another project's source.` |
| Corrupt upload | `400`, no import folder left |
| Stale pending | expired and allowed the next append |
| Atomic rollback | check, edit, and source unchanged after simulated edit-write failure |
| UI append | timeline `10 -> 15` clips; cues `10 -> 15`; import button re-enabled |
| Build | Xcode build succeeds |
| Archive | unsigned arm64 archive succeeds |

## Remaining for Loop C

- Replace the long append request with a job id and progress polling.
- Verify window-background drag does not steal brush or timeline gestures.
- Add a small cleanup policy for old masters kept after append.
