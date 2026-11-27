# R4 product-owner review — Audio Focus

**Verdict: PASS** for the founder acceptance test after two fix loops.

## Round 1 findings (FAIL)

| Finding | Fix |
|---|---|
| P1: Audio Focus was a page, not a dock — dock 1194 px, document 1582 px in a 900 px window, Back to timeline scrolled away | The dock body is capped by height tier and scrolls inside itself; the header stays put. Dock bottom 819 at 1440 in a 900 window, 505 at 800 in 600. |
| P1: empty Audio Focus was a dead end and Preview mix taught nothing | Add music, Add sound and Preview mix sit in the card header, on screen with zero rows. Preview mix toasts what it mixed (`Preview mix · source 22% · 2 rows`). |
| P1: the dock told the user to drag blocks it does not contain | Copy now states Start/Length/M/S/play, and a placement strip draws each row over the project with scene ticks and start–end labels. |
| P1: the render's source-bed rule was hidden and the source could not be muted | The card states the rule, a readout shows Source bed / Voice or dub / Music, and "Mute original audio" is a real toggle. `render._mix_audio` drops the bed when muted and silences it when no row replaces it. |
| P1: the preview broke in Audio Focus — card 88 px above its block, transcript sliced or off the right edge | The transcript side is hidden in Audio Focus, as in Cut and Script, and the card stays inside its strip at every size. |
| P2: Original audio was an 805 px empty slab | Cards align to the top of the grid. |
| P2: Music had two doors and no home | The Audio tab lists the music row and its level with a track count; add doors are the header and the Music & SFX card. |
| P2: row controls below the usable floor, volume shown as 0.25 | Labels 10.5 px, inputs 26 px/11 px, icon buttons 24 px, volume as a percentage with a 0/100%/150% scale. |

## Round 2 finding (FAIL)

| Finding | Fix |
|---|---|
| P1: the music line read the legacy `edit.music` while rows are the model, so a real music row showed "Music — none" | Music comes from `rows.find(kind === 'music')`, with `edit.music` only as fallback, in both the dock readout and the Audio tab. Measured `Music · Kitchen bed 25%`. |
| P2: 35 scene ticks hatched the 8 px lane | Ticks draw at `z-index 0` at 8 % opacity under a `z-index 1` bar. |

## Measured after fix

| Viewport | Dock bottom | Page scroll | h-overflow | Back / Add / Preview | Card inside strip | Tracks = placement |
|---|---:|---:|---:|---|---|---|
| 800×600 | 505 | 0 | 0 | yes | yes | 2 = 2 |
| 960×640 | 545 | 0 | 0 | yes | yes | 2 = 2 |
| 1024×700 | 605 | 0 | 0 | yes | yes | 2 = 2 |
| 1100×800 | 715 | 0 | 0 | yes | yes | 2 = 2 |
| 1200×800 | 719 | 0 | 0 | yes | yes | 2 = 2 |
| 1280×800 | 719 | 0 | 0 | yes | yes | 2 = 2 |
| 1440×900 | 819 | 0 | 0 | yes | yes | 2 = 2 |
| 200 % (720×450) | 375 | 0 | 0 | yes | yes | 2 = 2 |

Source chip: `22% under voice` with a voice row, `100%` with none, `Muted here` when muted, `Removed · 0%` for solo, dub or voice-only. Mute toggles, persists across reload, and unmutes back to `22% under voice`.

## Render rule measured

`tests/test_audio_source_mute.py`: with `audio_source_muted` the mixed file measures < 40 RMS; without it > 200 RMS. The mute also silences the source when no voice or music row exists, instead of silently leaving the original in.

## Regression guard

`scripts/check-audio-focus-layout.cjs` fails on a dock leaving the viewport, page scroll, horizontal overflow, a hidden Back/Add/Preview action, the preview escaping its strip, an empty source chip, or placement rows disagreeing with the track list. Needs a live dev server and `NODE_PATH="$(npm root -g)"`; without puppeteer-core it exits 2 with that instruction.

```
NODE_PATH="$(npm root -g)" node scripts/check-audio-focus-layout.cjs \
  --base "http://127.0.0.1:8813/?t=scratch-3a" --project prj_e95348a97316 --out build/po-r4
```

## Limits kept in the open

- At 800×600 the Original audio, Voice & dub and Music & SFX cards sit below the dock-body fold; one internal scroll reaches them.
- The scratch project's test rows have no audio file behind them, so audition is silent there; audition with real files was not measured this round.
- No render with the mute was run on the project; the rule is proven on synthetic tones only.
- At 200 % the preview workspace is hidden by the same rule as Script Focus.
