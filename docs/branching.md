# Branches, lanes and shipping

Updated 2026-11-07. This supersedes the older lane map.

## Active lane

| Lane | Role | Worktree | Branch | Status |
|---|---|---|---|---|
| **DuckSuite** | The only active build: Mac App Store app, DuckSuite brand. | `/Users/happynghia/Public/Project/Code/drop_eval/ducksuite` | `ducksuite` | **Active** |

The old `vibecut-studio` folder was moved to `ducksuite`. The branch and folder now match.

## Frozen lanes

| Lane | Role | Worktree | Status |
|---|---|---|---|
| `studio` | Legacy VibeCut Studio docs and integration history. | none | **Frozen.** No builds, no commits. |
| `classic` | Legacy VibeCut Classic product. | none | **Frozen.** No builds, no commits. |
| `main` | Archive. | `/Users/happynghia/Public/Project/Code/drop_eval/vibecut` | **Archive.** Do not build from it. |
| `voice-room` | Separate Voice product. | `/Users/happynghia/Public/Project/Code/drop_eval/vibecut-voice-room` | Separate lane. Not part of DuckSuite. |

“Clean” means **no uncommitted changes**. It does not mean active. A frozen branch can be clean.

## DuckClean

DuckClean is **not** built from this repo worktree.

- Folder owned by the founder: `/Users/happynghia/Public/Project/Code/drop_eval/duckclean`
- It is a separate folder and is not this session’s worktree.
- Do not edit or delete it from the DuckSuite session.
- Product rule: DuckClean ships from the **Classic lane**, not Studio.
- In this repo, the local `duckclean` branch exists only as docs/history. It has no worktree.

## Deleted branches

| Branch | Action |
|---|---|
| `fix/review-mediums` | Local branch deleted. It was fully behind `main`. |
| `origin/studio-standalone` | Remote branch deleted. It was behind `studio`. |

## Worktrees

```text
/Users/happynghia/Public/Project/Code/drop_eval/vibecut          main
/Users/happynghia/Public/Project/Code/drop_eval/ducksuite        ducksuite
/Users/happynghia/Public/Project/Code/drop_eval/vibecut-voice-room voice-room
```

The old `vibecut-split` worktree metadata was pruned on 2026-11-07.

## Rules

- **This session works only on `ducksuite`.**
- Do not commit to `studio`, `classic`, `main` or `voice-room`.
- Do not create a new `studio` or `classic` worktree.
- Do not build DuckClean from `ducksuite`.
- Do not edit `/Users/happynghia/Public/Project/Code/drop_eval/duckclean`.
- DuckSuite app data lives in `~/vibecut-lanes/ducksuite` for dev and in the sandbox container for the Mac app.
- DuckClean data, when built, belongs to its own folder and Classic lane.

## History

The older lane map (Studio/Classic/Voice Room ports, scripts and merge rules) is historical. It described the pre-DuckSuite product. The current product is DuckSuite; only this branch moves forward.
