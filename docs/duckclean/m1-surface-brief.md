# M1 surface brief — upload and library

Status: built in `web/src/App.tsx`. The surface is code-complete; the live
Clerk, Postgres and R2 resources are still unprovisioned. See
[`infrastructure.md`](./infrastructure.md).

Scope: the signed-in shell, the library list, the upload flow and the item view
for one uploaded clip. Mode: **Operate**. This is not the review timeline (M3)
and not the render screen (M5).

## Audience and job

A social editor with a clip already on their phone. They want to know three
things before doing anything else: did my file arrive intact, what is it, and can
I watch it here. The one action is **Upload**.

## Constraints

- Phone first: 390 px is the design width; the player, the status and the
  primary action fit one viewport.
- 44 px minimum targets, no horizontal scroll, safe-area padding.
- Real values only. Progress is bytes actually sent; facts come from the probe;
  statuses map to the contract's library state machine.
- The API is the only source of truth. Nothing is cached as "done" locally.
- No credentials exist yet, so M1 must render an honest setup state when Clerk
  is not configured, and a real empty state when the library is empty.

## Direction contract

**THESIS** — The surface is a broadcast as-run log for one person's clips: every
row carries measured evidence, and the upload reports bytes as they leave the
phone. It refuses the category default of a dark editor with a glowing timeline,
and it refuses a decorative dashboard card grid.

**OWN-WORLD** — Warm ink ground `#14171A`, panel `#1B2026`, hairline `#2B333A`,
warm paper text `#E9E4D9`, muted `#98A1A6`. Vermilion `#E4552B` is the single
action and the mark on a target; slate `#708CA2` is an included range; amber
`#C9963C` a low-confidence warning; green `#4E8F6B` ready; `#C4453C` failed.
Component language: rule-separated ledger rows, 6 px maximum radius, no
shadows, tabular numerals, a condensed uppercase label voice at 11 px with
`0.08em` tracking, and one monospaced evidence line per row.

**STORY** — The visitor sees their clip arrive, reads its real facts, and plays
it. They believe the file is intact because the numbers match the file, not
because a spinner finished.

**FIRST VIEWPORT (phone)** — Top rail: wordmark left, account right, one hairline
under it. Below: the library, either the real rows (poster thumb, title, status
word, as-run line) or the empty state that names the one action. The primary
action sits in a bottom bar above the safe area, full width, vermilion. On
desktop the same rail becomes a 2-column shell: library list left, selected item
and player right.

**FORM** — Operate, code-led; no comp. Position 1 of the ordered direction list:
the as-run log. Seed reference: none (unavailable — the skill launcher is not
installed in this workspace).

**FINISH** — unreviewed and undocumented is unfinished; this build ends with the
finish review, the verdict, DESIGN.md, and every shipping raster carrying its
provenance.

## Signature move

The **as-run line**: one monospaced line of measured values, never a mood.

```
UP 43% · 118.4/276.0 MB · 8.2 MB/s · ETA 00:19
PROBE 00:00:12 · 1440×2560 · 30.000 · HEVC/AAC · 13.8 MB
```

When there is nothing measured to say, the line is absent. It never fills space
with placeholders.

## States to build

| State | What is shown |
|---|---|
| Signed out | Sign-in is not configured (no Clerk key) or a real sign-in action |
| Library empty | One sentence about what DuckClean does, one upload action |
| Library loading | Skeleton rows at the real row height, no fabricated titles |
| Library error | The error envelope's message and its action (`retry`, `sign_in`) |
| Upload choosing | File facts from the picker: name, type, size; size limit stated |
| Uploading | Real bytes sent, rate, ETA, cancel |
| Upload failed | Reason, retry re-signing the same asset |
| Upload incomplete | The object is missing or differs; re-upload offered |
| Uploaded, preparing | Duration unknown; "preparing playback", no percentage |
| Playable | Poster, duration, resolution, player on tap |
| Probe failed | `failed` status, readable reason, re-upload offered |

## Not in this surface

Timeline, groups, include/exclude, masks, engines, estimate, render, download.
Their routes exist in the contract and stay unbuilt until M2–M5.
