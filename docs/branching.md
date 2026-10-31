# Branches, lanes and shipping

Method of 2026-10-29. It replaces the earlier rule that every lane merged and moved `main`.
That rule failed in practice: the lanes used each other's files, env, notes and test ports.

## The lanes

| Lane | Role | Worktree | Port | Data | Build |
|---|---|---|---|---|---|
| `studio` | Project main and integration lane. Studio embeds Classic and Voice Room. | `/Users/happynghia/Public/Project/Code/drop_eval/vibecut-studio` | **8795** | `~/vibecut-lanes/studio` | `VIBECUT_EDITION=all`, `VIBECUT_FEATURES=voice_room` |
| `classic` | Beta focus: the Classic view. | `/Users/happynghia/Public/Project/Code/drop_eval/vibecut-classic` | **8796** | `~/vibecut-lanes/classic` | `VIBECUT_EDITION=classic` |
| `voice-room` | Hidden voice features: voice library, clone, extraction. | `/Users/happynghia/Public/Project/Code/drop_eval/vibecut-voice-room` | **8797** | `~/vibecut-lanes/voice` | `VIBECUT_EDITION=classic`, `VIBECUT_FEATURES=voice_room` |
| `main` | Archive. Only studio moves it. | `/Users/happynghia/Public/Project/Code/drop_eval/vibecut` | none | none | none |

- Port 8787 is the founder's own app. No lane uses it.
- `vibecut-studio-prv` is a frozen rollback worktree, not a lane. The old `classic-prv` copy is gone.

## Lanes share nothing

Each lane has its own:

- **worktree and branch:** it edits only its own checkout.
- **port:** 8795, 8796 or 8797, never another lane's.
- **data:** `~/vibecut-lanes/<lane>`, so jobs, settings, keys and caches are per lane.
- **media:** `~/vibecut-lanes/media/<lane>`, real files the founder gave that lane.
- **recordings:** `~/vibecut-lanes/recordings/<lane>/`.
- **notes and logs:** in the lane's data folder or its worktree's ignored `.lane/` folder. No shared notes.
- **processes:** never stop or kill another lane's server or OpenCode, and never use a pattern kill (`pkill -f`).

## One set of lane scripts

| Script | Who | What |
|---|---|---|
| `scripts/lane-env.sh [lane]` | every lane | Prints the lane's environment: port, build, data, media and recordings. With no lane it reads this checkout's branch. |
| `scripts/serve.sh` | every lane | Starts this checkout's lane server; Ctrl-C stops it. It refuses a port already in use. The first time, it moves an old `<worktree>/data` into `~/vibecut-lanes/<lane>`. |
| `scripts/record.sh` | the founder | Opens a recorded browser on the running lane. It saves `trace.zip`, `network.har` and `storage.json`. |
| `scripts/ship-lane.sh` | classic, voice-room | Takes in its own branch from GitHub, runs the checks, and pushes that branch. It never moves `main`. |
| `scripts/ship.sh` | studio | Same checks, pushes studio, then fast-forwards and pushes `main`. |
| `scripts/integrate.sh` | studio | Merges `origin/classic` and `origin/voice-room` into studio, runs their guards, then ships studio. |
| `scripts/release.sh --founder-passed` | classic | Tags a beta (below). |

The classic and voice-room branches still carry older copies of `ship.sh` that move `main`. They must not use them. They take this set at their next merge from studio.

## Merging: classic and voice-room flow into studio

```
classic ──ship-lane──► origin/classic ──┐
                                        ├─► studio merges ─► origin/studio ─► main
voice-room ─ship-lane─► origin/voice-room ┘
```

1. **classic and voice-room** finish each change with `scripts/ship-lane.sh`. They never merge `main` or `studio` in, so the Classic beta never gets unfinished Studio work.
2. **studio** first finishes and ships its own latest change. When the founder says to merge, studio runs `scripts/integrate.sh` once:
   - it merges `origin/classic` and `origin/voice-room`;
   - it runs the Classic guard, edition, lane and Voice Room tests, then the full suite;
   - it pushes studio and moves `main`.

   If a merge conflicts, studio resolves it by hand, keeping both lanes working, then ships. The merge is manual, never on a timer or after every lane ship, so requests cannot stack and stall the lanes.
3. **Every studio edit is checked against Classic and Voice Room,** because both run inside studio (`/?classic=1`, `/classic`, `/voices`). Fix a break on studio. Never fix it by changing a classic or voice-room file from the studio lane; ask that lane.

## Who owns what

| Area | Owner | Files |
|---|---|---|
| Studio view | `studio` | `static/index.html` (the Studio page), `static/studio/**`, `edits.py`, `routes_edits.py`, `compose_render.py`, `story_queue.py`, `routes_check.py`, `routes_library.py`, `routes_studio.py`, `scripts/` |
| Classic view | `classic` | `static/classic/**` (its own page, JS and CSS), `routes_classic.py` |
| Voice features | `voice-room` | `static/voice/**`, `static/voices.html`, `voice_clone.py`, `voice_extract.py`, `routes_voice_clone.py` |
| Shared core | any lane, small and additive | `app.py`, `pipeline.py`, `audio.py`, `tts.py`, `stt.py`, `music.py`, `render.py`, `settings_store.py`, `editions.py`, `workflow_config.py`, `admin/`, tests of shared code |

New HTTP routes go in the lane's route module, never in `app.py` (`tests/test_lane_routes.py`).

## Hiding features: switches, not branches

- `VIBECUT_EDITION=classic|studio|all` picks the pages a build serves:
  - `classic`: `/` is the Classic page.
  - `studio`: `/` is the Studio page, and `/classic` is a 404.
  - `all`: `/` is Studio, and `/?classic=1` or `/classic` is Classic. A saved Classic choice on `/` goes to `/?classic=1`.
- `VIBECUT_FEATURES=voice_room` turns on the Voice Room. When it is off, `/voices` and the voice clone routes answer 404, and no link or clone control shows.

Never delete a feature to hide it. Deleting code on one lane deletes it everywhere at the next merge.

## Testing: the founder tests, by hand, with real files

- Only the founder tests the app. Claude and OpenCode never generate test videos, sounds or files. If media is needed, ask the founder.
- The founder records a real run:
  1. Run `scripts/serve.sh` in the lane's worktree, if the lane is not already running.
  2. Run `scripts/record.sh` in the founder's own Terminal.
  3. Do the flow.
  4. Press Ctrl-C there, or close the app tab, and **wait until it prints "Saved …"** before closing anything else.

  The recording stays on the founder's Mac, out of the repo.
- Agents never open the recorded browser. The founder owns the terminal and the Ctrl-C.
- Founder test scripts in `docs/testing/` follow the founder's own recorded clicks. Never invent steps.
- Automated tests are code checks. They run on every ship and never replace the founder's test.

## Working with OpenCode

- Each lane's Claude session resumes the OpenCode session it used before: `opencode run -s <id> -m opencode-go/deepseek-v4.1-flash ...`.
- Run it so the lane is told when it ends, for example a background run that wakes the session on exit. Don't check on it every minute, and send no new request until it is done.
- OpenCode may run ahead. Before the next step, read its report, `git log` and uncommitted changes, and fix what is wrong.
- Commits are signed with the founder's SSH key. Never pass `commit.gpgsign=false` for real commits, and never rewrite history to sign old ones.

## Beta releases

When the founder's test pass on `classic` is clean, run `scripts/release.sh --founder-passed` from the classic worktree. It tags the shipped `classic` as `beta-YYYYMMDD-N`. Testers build from the tag, with `VIBECUT_EDITION=classic` and no `VIBECUT_FEATURES`.

## Studio plan

The current Studio plan and open items are in `docs/handoff/r3-review.md` ("Studio plan (revised 2026-10-29)").

## History

- **Phase A** (foundation) shipped:
  - `editions.py` switches
  - `static/voice/`
  - lane route modules
  - the Classic guard
  - `scripts/release.sh`
- **Phase B:** each lane's items are in `docs/testing/` and `docs/handoff/r3-review.md`.
- **2026-10-29:** the lanes were split:
  - Classic moved to `static/classic/`;
  - Studio became Import → Moments → Edit → Finish;
  - studio became the only lane that moves `main`.
