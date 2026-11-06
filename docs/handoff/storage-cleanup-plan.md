# Storage cleanup and refactor plan

Date: 2026-11-06
Status: cleanup done; refactor planned

## 1. What was removed

| Item | Freed | Regrows? |
|---|---:|---|
| `studio/cache/segments` | 881 MB | yes, on render |
| `studio/cache/masters` | 656 MB | yes, on render |
| `studio/cache/frames` | 52 MB | yes, on preview |
| `studio/jobs/*/previews` | ~100 MB | yes, on Review |
| All Studio jobs, sources and queue records | 3.5 GB | only on new import |
| Old Playwright trace folders | ~1 GB | only on new test run |
| Repo legacy `data/` jobs and caches | ~212 MB | no; lane data is authoritative |
| Classic lane jobs, sources and cache | ~857 MB | only on a new Classic import |

Studio lane after cleanup: **487 MB**, of which 484 MB is the AI model pack.
Classic lane: **104 KB**. Recordings: **4 KB**.
Disk free after cleanup: **25 GB**.

Kept:

- `studio/models` — STTN, LaMa, MI-GAN weights.
- `studio/logs` — 3.8 MB.
- `studio/admin` — settings and admin state.
- `studio/fill_rates.json` — measured fill speed.
- `classic/admin` and `classic/fill_rates.json`.

## 2. What is still removable

| Item | Size | Note |
|---|---:|---|
| Studio logs | 3.8 MB | safe to rotate |
| Model pack | 484 MB | keep; AI fill and speech need it |

## 3. Current storage problems

1. **Sources are copied per job.** Two jobs imported the same file and stored
   two source copies. A 58 MB video cost 116 MB.
2. **Fill caches are per job.** The same source and spans recompute and
   duplicate across jobs. One job held 2.0 GB of fill cache.
3. **Cache and state share a tree.** `cache/` is safe to delete; `jobs/` is not.
   A user cannot tell them apart from the folder names alone.
4. **Previews and proxies live inside the job.** They are regenerable but are
   counted as project data.
5. **No retention policy.** Nothing ages out. Deleting a job is manual.
6. **Queue records outlive their jobs.** Old queue rows point at deleted jobs.
7. **No storage panel.** The user cannot see what is using space or clear one
   category.

## 4. Target tree

```text
data/
  state/
    jobs/<job_id>/job.json          # document only
    jobs/<job_id>/edits/            # immutable edit versions
    jobs/<job_id>/transcript/
    story_queues/
    settings.json
  media/
    sources/<sha256>.mp4            # one copy per unique file
    jobs/<job_id>/artifacts/        # final renders and packets
    jobs/<job_id>/poster.jpg
  cache/
    sources/<sha256>/               # analysis, thumbs, tracking
    segments/<key>.mp4
    masters/<key>.mp4
    fill/<source_hash>/<key>/       # global, not per job
    proxies/<job_id>/<clip_hash>.mp4
    previews/<edit_id>_<mode>.mp4
  models/
```

Rules:

- `state/` and `media/` are user data. Never pruned automatically.
- `cache/` may be deleted at any time. The app rebuilds it.
- AI models live under `models/` and are never pruned.
- Queue records move to `state/story_queues/`.

## 5. Source deduplication

- Hash the original file (SHA-256, streaming).
- Store once at `media/sources/<hash>.<ext>`.
- A job references the hash, not a copy.
- Import of the same file again reuses the source and its analysis cache.
- Deleting a job checks reference counts; the source stays while another job
  uses it.

This removes the duplicate-source problem immediately. In the cleanup sample,
two pairs of jobs shared a source.

## 6. Global fill cache

- Key: source hash + source span + layer geometry + method + model signature.
- Location: `cache/fill/<source_hash>/<key>/`.
- Shared by every job that renders the same source and masks.
- Cache entry stores a manifest with source hash, span, method and model hash.
- A model change invalidates by signature, not by manual delete.

Result: rendering the same clip twice does not recompute AI fill, and deleting a
job does not throw away fills another job can reuse.

## 7. Retention

| Category | Default | Rule |
|---|---|---|
| Segments and masters | 8 GB, 14 days | LRU; keep hot recent |
| Fill cache | 6 GB, 30 days | LRU; keep last job's fills |
| Proxies | 7 days | rebuild on open |
| Previews | 7 days | rebuild on Review |
| Frames | 2 days | preview only |
| Artifacts | keep | until job delete or user prune |
| Sources | keep | reference counted |
| Logs | 14 days | rotate |
| Playwright traces | 3 runs | test only |

All limits are settings, not constants.

## 8. Delete and prune UI

Add a **Storage** panel under Setup:

- One bar per category: models, sources, artifacts, cache, logs.
- Buttons: Clear cache, Prune old previews, Delete old jobs.
- A job list with size, last opened, artifact count, pinned state.
- Pinned jobs and pinned artifacts are exempt.
- Deleting a job states what goes with it and what stays (shared sources,
  models).

Add a CLI for scripts and packaging:

```text
python -m vibecut storage usage
python -m vibecut storage prune --cache --older-than 14d
python -m vibecut storage delete-job <job_id>
```

## 9. Migration phases

| Phase | Work | Gate |
|---|---|---|
| 1 | Split `state/`, `media/`, `cache/` with a compatibility reader | Existing jobs still open |
| 2 | Content-addressed sources + reference counts | Import same file twice uses one copy |
| 3 | Global fill cache with manifest | Same source/mask reuses fills across jobs |
| 4 | Retention settings and a startup prune | Cache stays under budget |
| 5 | Storage panel and CLI | Usage matches `du` |
| 6 | Delete queue records with their jobs | No orphan queue rows |

Do not move files without a migration step. Read the old path when the new one
is absent, then move on first write.

## 10. Tests

- Import the same file twice: one source file, two jobs.
- Delete one job: the source stays while the other job exists.
- Delete the last job: the source is collected.
- Same source and mask in two jobs: second render reads the fill cache.
- Model hash change: fills recompute.
- Cache prune: artifacts and edits are untouched.
- Storage usage: category totals equal the files on disk.
- Queue delete: no orphan `story_queues` record after job delete.

## 11. Risks

- Moving user data needs a rollback path and a backup.
- Reference-count bugs can delete a source still in use; keep a dry-run.
- A global fill cache needs a correct key; a wrong key shows stale pixels.
- A prune running during a render must skip active jobs.
- Classic keeps its own lane and data; do not share its cache without a key
  namespace.
