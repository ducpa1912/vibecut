# Branches, lanes and shipping

Method of 2026-10-29. It replaces the earlier rule that every lane merged and moved `main`.
That rule failed in practice: the lanes used each other's files, env, notes and test ports.

## The lanes

| Lane | Role | Worktree | Port | Data | Build |
|---|---|---|---|---|---|
| `studio` | Studio product and integration lane. Owns its page, voice client and releases. | `/Users/happynghia/Public/Project/Code/drop_eval/vibecut-studio` | **8795** | `~/vibecut-lanes/studio` | `VIBECUT_APP=studio`, `VIBECUT_EDITION=studio`, `VIBECUT_FEATURES=voice_room` |
| `classic` | Second supported product: Classic page and release. | `/Users/happynghia/Public/Project/Code/drop_eval/vibecut-classic` | **8796** | `~/vibecut-lanes/classic` | `VIBECUT_APP=classic`, `VIBECUT_EDITION=classic` |
| `voice-room` | Hidden voice feature lane, still independent. | `/Users/happynghia/Public/Project/Code/drop_eval/vibecut-voice-room` | **8797** | `~/vibecut-lanes/voice` | `VIBECUT_APP=classic`, `VIBECUT_EDITION=classic`, `VIBECUT_FEATURES=voice_room` |
| `main` | Archive. Only studio moves it. | `/Users/happynghia/Public/Project/Code/drop_eval/vibecut` | none | none | none |

- Port 8787 is the founder's own app. No lane uses it.
- Rollback worktrees are gone (`classic-prv`, `vibecut-studio-prv`). Use git history or tags to roll back.

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
| `scripts/serve-studio.sh` | Studio | Starts `studio_app.py`; port/data defaults live in the entrypoint (8795 / Application Support lane folder). |
| `scripts/serve-classic.sh` | Classic | Starts `classic_app.py`; port/data defaults live in the entrypoint (8796 / Application Support lane folder). |
| `scripts/serve.sh` | legacy lane helper | Kept for the old lane workflow; new work uses the per-app scripts. |
| `scripts/record.sh` | the founder | Opens a recorded browser on the running lane. It saves `trace.zip`, `network.har` and `storage.json`. |
| `scripts/ship-lane.sh` | classic, voice-room | Takes in its own branch from GitHub, runs the checks, and pushes that branch. It never moves `main`. |
| `scripts/ship.sh` | studio | Same checks, pushes studio, then fast-forwards and pushes `main`. |
| `scripts/release.sh --founder-passed` | classic | Tags a beta (below). |

The classic and voice-room branches still carry older copies of `ship.sh` that move `main`. They must not use them. They take this set at their next merge from studio.

## Merging: separate products, shared backend

`classic` and `studio` are separate **products**, not page toggles. Each ships
from its own entrypoint and tag. `scripts/integrate.sh` is removed: Classic no
longer merges into Studio at release.

```
classic ──ship-lane──► origin/classic ──► beta tag + Classic artifact
studio  ──ship───────► origin/studio  ──► main + Studio artifact
voice-room ──ship-lane► origin/voice-room (hidden feature lane)
```

Shared backend changes still need an explicit port or cherry-pick. Do not
assume a release merge carries them. If Classic needs a Studio backend change,
ask the Studio owner for the commit and port it into the Classic lane with
Classic tests. If Studio needs a Classic fix, do the same in reverse.

Every Studio edit is checked against its own tree. Classic is no longer mounted
inside Studio; do not test it through `/?classic=1`.

## Who owns what

| Area | Owner | Files |
|---|---|---|
| Studio view | `studio` | `static/index.html` (the Studio page), `static/studio/**`, `edits.py`, `routes_edits.py`, `compose_render.py`, `story_queue.py`, `routes_check.py`, `routes_library.py`, `routes_studio.py`, `scripts/` |
| Classic view | `classic` | `static/classic/**` (its own page, JS and CSS), `routes_classic.py` |
| Voice features | `voice-room` | `static/voice/**`, `static/voices.html`, `voice_clone.py`, `voice_extract.py`, `routes_voice_clone.py` |
| Shared core | any lane, small and additive | `app.py`, `pipeline.py`, `audio.py`, `tts.py`, `stt.py`, `music.py`, `render.py`, `settings_store.py`, `editions.py`, `workflow_config.py`, `admin/`, tests of shared code |

New HTTP routes go in the lane's route module, never in `app.py` (`tests/test_lane_routes.py`).

## Hiding features: switches, not branches

- `studio_app.py` owns the Studio page. `classic_app.py` owns the Classic page.
  They set their own app, edition, port and data defaults; the old
  `VIBECUT_EDITION=all` page toggle is a legacy lane helper, not the product
  split.
- `VIBECUT_FEATURES=voice_room` turns on the Voice Room. When it is off, `/voices` and the voice clone routes answer 404, and no link or clone control shows.

Never delete a feature to hide it. Deleting code on one lane deletes it everywhere at the next merge.

## Testing: the founder tests, by hand, with real files

- Only the founder tests the app. Claude and OpenCode never generate test videos, sounds or files. If media is needed, ask the founder.
- The founder records a real run:
  1. Run `scripts/serve-studio.sh` or `scripts/serve-classic.sh` in its worktree, if that product is not already running.
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

The current Studio plan and open items are in `docs/handoff/r3-review.md` ("Studio plan (revised 2026-11-01)"). Lane split decisions and the Classic/Studio matrix are in
`docs/handoff/lane-split-decisions.md` and `docs/handoff/classic-studio-matrix.md`.

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
