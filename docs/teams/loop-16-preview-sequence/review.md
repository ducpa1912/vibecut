# Loop 16 review — Preview sequence

**Verdict: pass.** Request REQ-20261112-06.

## Modes

The Preview actions show **Play all scenes** on the full edit and **Play story order** on a story
edit. Both open one `<video>` on the source and walk a list of segments, so a boundary is a seek, not
a new player.

| Probe | Full edit | Story edit |
|---|---|---|
| Segments | **35** | **3** |
| Total | **02:40** | **00:15** |
| First item | `All scenes · 1 of 35 · Scene 01` at 00:01 | `Story · 1 of 3 · S01` at 00:01, source **26.5 s** |
| Boundary | `2 of 35 · Scene 02` after the first cut, source 6.4 s | `2 of 3 · S02`, source **5.3 s** |
| Order | source order | clip order: scene 6 → scene 2 → scene 4, not source time |
| Seek 50 % | `15 of 35 · Scene 15`, clock **01:20**, still playing | — |
| Close | player gone, proof steps return | same |

The story edit was built through `POST /edits/story/scenes` with `[5, 1, 3]`; its clips are
25.271–30.917, 4.750–10.062 and 15.375–19.625. The sequence plays them in that order, which proves
story order is independent of source time.

Image beats are skipped and counted in the label (`N image beats skipped`); the fixture has none, so
that path is unproven.

## Bar

Play/pause, `elapsed / total`, scrubber, `mode · n of N · label`, close. Seek maps a sequence time
to a segment and a source offset.

## Layout

The bar is inside the picture, 24 px above the bottom; it does not add panel rows. Captures
`sequence-1440x900.jpg` and `story-order-1440x900.jpg` looked at. No layout measure was re-run:
the default Preview has no sequence bar, so the six-screen numbers are unchanged (bottoms
87.3–100 %, overlaps 0).

**188 tests**, `node --check`, Xcode build.

## What got worse

- The sequence bar covers the bottom of the picture while playing.
- A story's image beats are skipped, not played; the label says how many.
- The status card still names the source scene while a story clip plays.
- No audio mixing in this player; it plays the source track only.

## Not tested

- Image beats in a story, multi-clip audio, frame-accurate boundary check (verified by label and
  source time, not by OCR on the boundary frame).
- 1280×800 capture of the active sequence.
- Real clicks in the app window.
