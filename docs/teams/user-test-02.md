# User test 02 — fixes after test 01

Date: 2026-11-08
Build: source core on `127.0.0.1:8766`, packaged core on `8767`, Xcode 27.2 app/archive.
Fixture: `check-smoke`, 45.833 s, 1080 × 1080, 24 fps.

## Verdict

**PASS on the tested defects.** One App Store blocker remains outside the app: no signing identity.

## Results

| Test | Result | Evidence |
|---|---|---|
| Scene 01 title at 3.5 s | Pass | `room` filled; no ghost. Edge OCR + stacked-title merge. |
| Scene 03 train text at 8.625 s | Pass | No dark hole; seat reconstructs. LaMa 16 px run sizes. |
| Scene 07 control | Pass | Clean. |
| Proof vs render at 3.5 s | Pass | MAD 2.30; 99.1 % within 10 levels. |
| Proof speed | Pass | 14 s title, 21 s train; was minutes per scene. |
| Duplicate captions | Pass | 22 cues, 22 unique; was 35/22. |
| Caption minimum | Pass | 0.6 s minimum; 5 ms cue gone. |
| Caption burn | Pass | 3.18 s cue burned into a 3.6 s H.264 render; SRT matches. |
| Fine trim | Pass | In 0.3 / Out 3.4 wrote the clip; toast confirmed; render uses it. |
| All layers reachable | Pass | `Show all 7 layers` expands from 6 to 7. |
| All cues reachable | Pass | `Show all N cues` control present. |
| Queue clear | Pass | 2 finished rows → 0; toast `Finished renders cleared.` |
| Re-check handoff | Pass | `Checking` spinner, running banner, no stale edit, `Waiting` layers, empty transcript. |
| One-layer proof invalidation | Pass | Server hashes only layers active at the proof frame. |
| Processing blur | Pass | Frame dims; no longer looks like the Blur method. |
| Voice list | Pass | 60 voices; novelty names removed; en-US first. |
| Packaged sidecar | Pass | PyInstaller core serves UI/API on 8767; helpers and model resolve. |
| Dev app icon/privacy | Pass | `AppIcon.icns`, `Assets.car`, `PrivacyInfo.xcprivacy` in the dev bundle. |
| Tests | Pass | 38 tests. |

## Notable UI evidence

- Edit: `Scenes` panel, `Layered` chips, all layer counts fit, real In/Out trim.
- Clean Focus: `6/6 layered`, layer expansion, clean after frame.
- Preview: `6/6 proofs`, `After` default, no disabled fake switch.
- Render: `Clear finished`, real total queue count, `DuckSuite Exports`.

## Remaining

1. **App Store signing.** 0 identities, team empty. Archive is unsigned.
2. **Support and privacy URLs.** TODO in review notes and metadata.
3. **Screenshot footage rights.** The current set uses the internal fixture.
4. **Preview latency.** ~20 s per scene with the local LaMa model on this Mac. Correct but not instant.
