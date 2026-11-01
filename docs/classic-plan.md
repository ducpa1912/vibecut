# Classic lane plan

Updated 2026-11-01 after the creator review, at `classic` `59de169`. The lane rules are in `docs/branching.md`:
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
| C2 | P3 | At 1:1, 16:9 or 16:10, Render leaves the text layers out without a word. | Now T4. |
| C3 | P3 | The new 16:10 shape is not in the old review-link file filter (`_find_share_render`), so a 9:16 file lookup could pick a 16:10 file. Classic shares by artifact now, so this is reachable only from the old route. | Add `_16x10` to the filter. Shared `app.py`, one line. |
| — | — | A second click on Expand | Settled: in the current build the button reads Collapse and closes the list. |
| — | — | Empty ElevenLabs voice list | Settled: with no key the list reads "Add the key in Setup". |

## Creator review, 2026-11-01

An outside creator review judged Classic "a promising rough-cut assistant, not yet a reliable
publish-ready Shorts editor". Its weak point is trust. Its points are folded in below.

## Next build

### Before the beta tag: trust fixes (Classic only, small)

| # | Fix | Done when |
|---|---|---|
| T1 | **Honest privacy copy.** Replace "No cloud. No account. No watermark." and the "local only" pills with "Local processing by default. Optional AI features may send data to external providers." Show "Online" while a cloud key or engine is active. | No screen promises "no cloud" while a cloud route can run. |
| T2 | **Cost and data notice before paid calls.** Generate music preview, a cloud voice sample, Rewrite or translate on a cloud route: before the first call, say the provider, what is sent (text or audio) and whether the result is cached. A cache hit says "cached, no new call". | No paid provider call happens without a visible notice on that click. |
| T3 | **Sample vs final.** Rename the buttons **Generate voice sample** and **Generate music preview**. State whether the chosen sample is used in the final render. | The founder can tell from the card what the render will use. |
| T4 | **Shape limit shown early** (was C2). The Texts card warns before anything is typed. Render at 1:1, 16:9 or 16:10 with layers says "Text layers are left out at this shape". | Layers are never dropped without a message. |
| T5 | **Changes not rendered yet.** After any edit to moments, text, effects or sound, the result card shows "Changed since this render". It clears on a new render. | The founder never mistakes an old render for the current edit. |
| T6 | **Plain Clean confirmation.** Before confirming, say in plain words what Clean deletes and what it keeps. | No destructive action has only a "Click to confirm" label. |

### After the beta: product work

1. **Hooks led by the transcript.** The spoken line comes first. Offer 2–3 hook candidates with a 3-second play, each labelled question, claim or outcome. Treat OCR text as uncertain, never as the title.
2. **Cut pacing.** Show transcript phrases on the timeline, flag cuts that start or end mid-sentence (this also covers C1), and offer Natural, Balanced and Fast pacing.
3. **Captions in the main edit flow.** Style, position and cue fixes beside the cut, with a safe-area preview against the video and a warning when the source already has subtitles.
4. **A simple path.** Review hook, then Refine cut, then Captions & sound, then Export. Scores go behind an "Explain" disclosure.
5. **Versions.** Named variants in Recent cuts and side-by-side compare of openings.
6. **Shared core, with Studio:** C3, F4, and C1 if pacing does not cover it.
7. A founder test script for Moments, Copy, Sound and Texts, from a new founder recording only.

## What the beta tag needs

- **Trust fixes T1–T6 shipped.**
- **A founder pass on the current `classic` tip** that checks these by hand:

| Priority | Check | Pass when |
|---|---|---|
| P0 | Hook and story | You watch the opening, the full cut and the ending: no misleading claim, no broken sentence. |
| P0 | Captions | Compared with the audio: names, numbers and timing are right, and captions sit inside the safe area. |
| P0 | Save and reload | Change moments, text and sound, reload, and the same choices are still there. |
| P0 | Export | You watch and listen to the downloaded file, including its first and last seconds. |
| P0 | Privacy and cost | With no keys, nothing calls a provider. Every online action showed its notice first. |
| P1 | Combinations | Captions + text + effect + your own audio, on a supported and an unsupported shape. |
| P1 | Recovery | A provider failure, a stopped render and a browser reload lose no finished work. |
| P1 | Phone | A real phone: tap targets, keyboard, scrolling. |

- **No P0 or P1 left open.**
- **Your OK.** Then `scripts/release.sh --founder-passed`.
- **From you:**
  - whether pass 4 was meant to be recorded
  - a working OpenRouter key, or your OK for one test call
  - a real voice recording and a music file in `~/vibecut-lanes/media/classic/`
  - the Studio and Voice Room re-recordings
