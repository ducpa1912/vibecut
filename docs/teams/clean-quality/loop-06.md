# Self-check loop 06

Date: 2026-11-08
Scope: product-owner, engineer and tester pass over the current build.
Verdict: **pass on the tested defects**. Remaining work is signing and store copy.

## Tester findings

| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | P1 | A long spoken sentence could stay on screen for 8–12 s. The simple caption builder had no 4 s ceiling. | Fixed: cues split at word boundaries, max 4 s. |
| 2 | P1 | A layer change during an all-scene proof run could leave the selected scene `queued` forever; the old run kept writing after the new run started. | Fixed: run token cancels the old loop; cache writes check the token. |
| 3 | P1 | Render readiness counted only scenes with layers, so a text-free scene could block render; and it allowed render before any proof existed. | Fixed: a scene is ready when it has no text, all layers are Off, or its proof is ready. Render now waits for proofs. |
| 4 | P1 | A story edit showed every check scene in Edit/Render. | Fixed: `getScenes()` filters to the story clips; Check keeps all scenes. |
| 5 | P2 | App version was `0.1.0` in the core and settings while the bundle said `1.0`. | Fixed: core and UI report `1.0.0`. |
| 6 | P2 | Long captions could also overrun the clip end after splitting. | Covered by clip bounds in `_finish_cues`. |
| 7 | P2 | A canceled check had no UI recovery path. | No cancel control ships in v1; failed/cancelled state keeps the project on Check. |

## Performance measurements

Packaged PyInstaller core, `/tmp/duck-demo-data`, 20 s 1920 × 1080, 4 scenes, 1 text layer:

| Operation | Result |
|---|---|
| Core start to health | 1 s |
| Check (scene + Whisper + OCR + stories) | 29 s |
| Proof, cold | 8.9 s |
| Proof, warm (same scene) | 2.5 s |
| Proof, cached | 12 ms |
| Full 20 s render | 65 s |
| Tests | 39 pass |

Reference loop 5 on the 46 s fixture: proof fell from minutes to 14 s (title scene) and 21 s (train scene); render/proof MAD 2.30.

## Engineer changes

- Caption split: `_split_long_cues` and `_split_words`; 4 s ceiling.
- Preview run token: old proof runs cannot overwrite a new scene selection.
- Render gate: `sceneRenderReady` / `sceneReadyCount`; Render button disabled until every scene is ready.
- Scene scope: `checkScenes()` for Check, `getScenes()` for the active edit.
- Version: `1.0.0` in `duckcore`, API settings, and UI fallback.

## Remaining performance note

The local LaMa fill dominates render time on 1080p. A still title over a moving picture still needs key fills when the motion check trips. Further gains need a temporal background plate or a smaller model, and both change the quality contract. Do not lower the key rate without a fixed-frame parity test.

## Remaining release blockers

1. App Store signing identity and team.
2. Support and privacy URLs.
3. Screenshot footage rights.
