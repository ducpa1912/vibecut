# Branches, lanes and shipping

Method of 2026-10-29. It replaces the earlier rule that every lane merged `main`.
That rule failed in practice: the lanes used each other's files, env, notes and
test ports.

## The lanes

| Lane | Role | Worktree | Port | Build switches |
|---|---|---|---|---|
| `studio` | Integration lane. Studio embeds Classic and Voice Room. | `/Users/happynghia/Public/Project/Code/drop_eval/vibecut-studio` | **8795** | `VIBECUT_EDITION=all`, `VIBECUT_FEATURES=voice_room` |
| `classic` | Beta focus | `/Users/happynghia/Public/Project/Code/drop_eval/vibecut-classic` | **8796** | `VIBECUT_EDITION=classic` |
| `voice-room` | Hidden voice features: library, clone, extraction | `/Users/happynghia/Public/Project/Code/drop_eval/vibecut-voice-room` | **8797** | `VIBECUT_EDITION=classic`, `VIBECUT_FEATURES=voice_room` |
| `main` | Archive. Only studio moves it. | `/Users/happynghia/Public/Project/Code/drop_eval/vibecut` | none | none |

`scripts/lane.sh` holds this table.

## Fully separate

Each lane has its own:

- **worktree and branch:** it edits only its own checkout.
- **port:** 8795, 8796 or 8797. Never another lane's, and never 8787 (the founder's own app).
- **data:** `<worktree>/data`, so jobs, settings, keys and caches are per lane.
- **notes, briefs and logs:** `<worktree>/.lane/` (ignored by git). No shared notes folder.
- **OpenCode session:** each lane resumes its own, and never touches another lane's processes. No `pkill` that could hit another lane.

Start a lane's server with `scripts/serve.sh`. It refuses a port that is already in use.

## Merging: classic and voice-room flow into studio

```
classic ──ship──► origin/classic ─┐
                                  ├─► studio: scripts/integrate.sh ─► origin/studio ─► main
voice-room ─ship─► origin/voice-room ┘
```

1. **classic and voice-room** finish each change with `scripts/ship.sh`: check, test, push their own branch. They never merge `main` or `studio` in, so the Classic beta never gets unfinished Studio work.
2. **studio** finishes its own latest change and ships it. When the founder says to merge, run `scripts/integrate.sh` once. It:
   - merges `origin/classic` and `origin/voice-room` into studio
   - runs the Classic guard and Voice Room tests, then the full suite
   - pushes studio, then fast-forwards and pushes `main`
   Never run it on a timer, after every lane ship, or without the founder's instruction. It is manual, so merge requests cannot stack and stall the lanes.
3. **Every studio edit is checked against Classic and Voice Room,** because both run inside studio. Fix any break on studio. Never fix it by changing a classic or voice-room file from the studio lane; ask that lane.

Ownership still applies:

- `static/app.js`, `static/creator.js` and `routes_classic.py` belong to classic.
- `static/voice/**` and `routes_voice_clone.py` belong to voice-room.
- `static/studio/**` and `routes_studio.py` belong to studio.
- Shared core files take small, additive changes. New routes never go in `app.py` (`tests/test_lane_routes.py`).

## Testing: the founder tests, by hand, with real files

- Only the founder tests the app. Claude and OpenCode never generate test videos, sounds or files to stand in for real media. If media is needed, ask the founder.
- The founder records a run of a lane with Playwright, using real files:
  1. In the lane's worktree, run `scripts/serve.sh` if the lane is not already running.
  2. In the founder's own Terminal, run `scripts/record.sh`. Close the app tab or press Ctrl-C there when the flow is done. It saves `trace.zip`, `network.har` and `storage.json` to `~/vibecut-lanes/recordings/<lane>/<date-time>/`, which stays on the founder's Mac and out of the repo.
- Agents never open the recorded browser. Give the founder the command; the founder owns the terminal and the Ctrl-C.
- The lane studies the recording to learn the founder's real flow, and replays it only when the founder asks. No generated media or stand-in files.
- Automated tests stay code checks. They run on every ship and never replace the founder's test.

## Working with OpenCode

- Each lane's Claude session resumes the OpenCode session it used before (`opencode run -s <id> -m opencode-go/deepseek-v4.1-flash ...`).
- Run it so the lane is told when it ends: a background run that wakes the session on exit, or a done note in `.lane/`. Don't check on it every minute, and send no new request until it is done.
- OpenCode may have run ahead overnight. Before continuing, read what it did: its report, `git log` and uncommitted changes. Fix any issue, learn its plan, then give it the next step.
- When the founder must provide something (media, keys, a decision), ask. Never guess.

## Beta releases

When the founder's test pass on `classic` is clean, run `scripts/release.sh --founder-passed` from the classic worktree. It tags the shipped `classic` as `beta-YYYYMMDD-N`. Testers build from the tag, with `VIBECUT_EDITION=classic`.

## History

Phase A (foundation) is shipped:

- `editions.py` switches
- `static/voice/`
- lane route modules
- the Classic guard
- `scripts/release.sh`

Phase B ran on the earlier method; the Phase B items each lane shipped are in `docs/testing/` and `docs/handoff/r3-review.md`.
