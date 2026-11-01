# Classic lane plan

Updated 2026-11-01, at `classic` `1afa403`. The lane rules are in `docs/branching.md`:
port 8796, data in `~/vibecut-lanes/classic`, ship with `scripts/ship-lane.sh`, signed commits,
and no merges of `main` or `studio`.

## Built

- **Phase A foundation:** edition switches, the Classic guard tests and `scripts/release.sh`.
- **Classic page:** its own page under `static/classic/`, on its own port and data folder.
- **First pass fixes:**
  - batch rights tick
  - speech failure notice and Retry speech
  - render blocked when the chosen engine is missing
  - History and Review link use the exact cut
  - edited-cut export
  - no-transcript export refusal
- **Beta setup:**
  - keys, with ElevenLabs added
  - voice-engine status
  - optional packs, including engines installed another way
  - rights lock
  - first-run banner
- **Translation:** the whole transcript is translated once, in 20-line batches. Later rewrites reuse it.
- **Layout:**
  - narrow-screen and touch layout
  - rendered cut first
  - three Edit cards, Story cut and a full-width script
- **Moments, from `classic-b`:**
  - select
  - explicit clip roles and order
  - vertical collage
- **Copy, from `classic-b`:** reuses transcripts and the translation state.
- **Sound tabs, from `classic-b`:** generate or upload, with bounded, cached previews.
- **Texts and effects, from `classic-b`:** per-cut text overlays and Studio effects, rendered as a real Edit on 9:16 and 4:5.

## Open

| # | Sev | Item | Plan |
|---|---|---|---|
| F4 | P2 | Changing a setting mid-rewrite stops the browser request; the server rewrite keeps running and later writes a History row. | Needs a cancel event through `audio.py` (rewrite subprocess and cloud call). Shared core: do it with Studio, additive, after the beta pass. The translation warm-up already cut the waste to one model call. |
| C1 | P3 | Caption cues of one word (`It`, `dump.`) when a story clip ends mid-sentence. | The split lives in shared `captions.py`. Fix with Studio: merge a cue under about 3 words into its neighbour. |
| C2 | P3 | At 1:1, 16:9 or 16:10 the Texts card says layers need 9:16 or 4:5, but Render still goes ahead and leaves the layers out without a word. | The render note should say "Text layers are left out at this shape." Classic only. |
| C3 | P3 | The new 16:10 shape is not in the old review-link file filter (`_find_share_render`), so a 9:16 file lookup could pick a 16:10 file. Classic shares by artifact now, so this is reachable only from the old route. | Add `_16x10` to the filter. Shared `app.py`, one line. |
| — | — | A second click on Expand | Settled: in the current build the button reads Collapse and closes the list. |
| — | — | Empty ElevenLabs voice list | Settled: with no key the list reads "Add the key in Setup". |

## Next build

1. C2, the render note, in Classic only. One signed commit, one ship.
2. A founder test script for Moments, Copy, Sound and Texts. These shipped from `classic-b` after the pass 1–3 recordings, so no founder script covers them yet. The script is written only from a new founder recording of those cards. No steps are invented.
3. C3, and later F4 and C1, as small additive core changes, agreed with the Studio lane.

## What the beta tag needs

- **A founder pass on the current `classic` tip:**
  - the recorded pass-1 script, re-run on the current build
  - a new recorded pass for Moments, Copy, Sound and Texts
- **No P1 open.** None is open today.
- **The founder's OK.** Then `scripts/release.sh --founder-passed`.
- **From the founder:**
  - whether pass 4 was meant to be recorded
  - a working OpenRouter key, or the OK for one test call
  - a real voice recording and a music file in `~/vibecut-lanes/media/classic/`
  - the Studio and Voice Room re-recordings
