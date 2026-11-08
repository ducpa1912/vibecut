# Product fixes after user test 01

Date: 2026-11-08
Status: pass on the fixed fixture; one App Store blocker remains outside the code.

## Clean

- LaMa run sizes round to 16 px. Fixes the ONNX FFC crash (`62 by 63`).
- The whole detected line box is the default hole. Fixes dark glyph halos.
- Edge OCR runs by default. It recovers large display type at the top and bottom edges.
- Stacked large-title lines merge into one fill block. The `wrong` + `room` title is now one layer.
- Proofs fill a 0.6 s window around the requested frame instead of the whole scene.

| Frame | Before | Now |
|---|---|---|
| 01 · 1.8 s | Title over sky | Clean |
| 01 · 3.5 s | `room` left behind | Clean, no ghost |
| 03 · 8.625 s | Dark seat hole / failed ONNX run | Clean, natural seat |
| 07 · 25.875 s | Control | Clean |

Proof/render parity at 3.5 s on a 3.6 s render: **MAD 2.30**, **99.1 % within 10 levels**. Proof time dropped from minutes to **14 s** for the title scene, **21 s** for the train scene.

## Captions

- Overlapping Whisper chunks with the same sentence merge into one cue.
- A sentence crossing an edit cut is emitted once, in the clip that holds most of it.
- No overlaps. Minimum cue is 0.6 s. Five-millisecond cues are gone.
- Fixed fixture: **22 cues, 22 unique, 0.6 s minimum**. Was 35 cues, 22 unique, 12 under 0.5 s.

## Edit and review flow

- **Fine trim is real.** In/Out fields write the edit clip; proof and render use the new range.
- **All clean layers are reachable.** `Show all N layers` expands the list.
- **All caption cues are reachable.** `Show all N cues` expands the list.
- **No stale editor after Re-check.** Starting Check clears the old edit, transcript, and proofs. Edit opens with scenes, a running banner, and `Waiting` layers.
- **One layer change only invalidates that scene's proof.** The server caches proofs by the layers active at that frame.
- **Processing blur removed.** The after frame dims; it no longer looks like a blur method.
- **Queue count is the real total.** Finished jobs can be cleared.
- **Terminology:** `Layered` for layers, `Proof` for proofs, `Scenes` for the scene list.
- **Current scene first** no longer looks like a disabled control.
- **Voice list** hides novelty voices and sorts English (US) first.

## Tests

- 38 tests pass, including:
  - duplicate transcript chunks
  - sentence across a cut
  - 5 ms cue removal
  - stacked title merge
  - active-layer proof key
  - clip trim API
  - queue clear API
  - 16 px LaMa run sizes

## Still open

- App Store signing identity and team.
- Support and privacy URLs.
- Screenshot footage rights.
- Preview still takes ~20 s per scene on the test Mac; acceptable for a local model, not instant.
