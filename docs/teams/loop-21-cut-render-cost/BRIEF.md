# Loop 21 — render cost with a Cut (REQ-20261115-01, items A and B)

Written by the sub-leader on 2026-11-15, after reviewing `eeec649..4c07225`. Revision: no.
Build team: OpenCode. Verifier: the sub-leader (Claude), who reruns every number on disk.

## Why

Two costs land on every render of an edit that has a Cut (crop, aspect, fit, enhance or grade):

- **A. The leftover check rebuilds every ink and never stores it.** `render._check_output` does not
  pass `data_root` to `inkcheck.check`, which calls `build_inks(edit, meta, source=…, size=…)` with
  no `data_root` (`inkcheck.py` ≈ line 481). With an `ink.View` (or any size that is not the
  source's) the inks the render already holds are not used, so the check reads the source again for
  every line, on a warm render too. One ink build of the review project measured 95–145 s earlier.
- **B. Lines the Cut leaves out of the frame are still filled.** `render_edit` and `estimate_edit`
  take `_fill_layers(edit)` with no regard to the Cut. LaMa is about 64 % of render time. The check
  then says "the Cut leaves this line out of the frame" for a line we paid to fill.

## What must exist after this loop

**A.** The leftover check stores and reuses its inks in the ink store, keyed by the View, exactly as
the estimate and queue already do. `data_root` reaches `inkcheck.check` → `build_inks`. The store
key already includes the size/View; confirm it distinguishes two different Cuts (crop vs grade).

**B.** A fill layer whose search rect is empty under the render's View is left out of the fill and
out of the estimate, for crop and for `fit: "fill"`. Use the **same geometry** the check uses
(`inkcheck.search_rect(layer, w, h, view)` and its "out of the frame" test) — do not write a second
rule. A line partly inside the kept picture stays filled. Pad (`fit: "fit"`) keeps every line.
Blur layers: unchanged in this loop. The check keeps reporting the dropped line as "not checked —
the Cut leaves this line out of the frame"; the Render screen count is unchanged.

`textfill.VERSION` stays 17 **only if** the fill cache key (`span_key` or equivalent) already
includes the set of layers in a span, so a span whose layer set changed can never reuse an old
clip. State which it is, with the line. If it does not, bump to 18 and say the next render is cold.
Either way, say in the review that edits whose layer set changes get a cold fill for those spans.

## Acceptance (each one pass/fail with a measured number)

Work in a **scratch data root** that is a copy of `prj_e95348a97316` (e.g. under `/tmp` or the
repo's gitignored `build/`), never the app's container data root, and never edit
`ed_38a4c36a3aae` itself — make a copy of the edit in the scratch root. Do not run a full 160 s
render to prove this; render a short span (3–6 clips, including at least one line the crop removes
and one it keeps). Set `DUCK_FILL_MODELS` as `AGENTS.md` says. GPU only.

1. **A, test.** A pytest that renders (or checks) the same Cut edit twice with one `data_root`: the
   second `inkcheck.check` reads no source frame for any ink (count `layer_inks` calls, or patch the
   frame reader). Must fail on `4c07225`, pass after.
2. **A, measured.** On the scratch span with a crop: check seconds on render 1 and render 2, before
   (on `4c07225`) and after. Report all four numbers.
3. **A, equality.** The check report of render 2 equals render 1 (hits, frames judged, not-checked
   list with reasons, flicker), field by field. A speed test alone does not pass this item. Every
   field of `ink.Ink` survives the store round trip with a View (glyphs, spans included).
4. **B, test.** A pytest with two fill layers, one wholly outside a crop and one inside: only the
   inside one enters the fill plan of `render_edit` and of `estimate_edit`. A third case: a line
   partly inside stays. A fourth: `fit: "fill"` to 9:16 on a 16:9 source drops a line at the far
   left. A fifth: `fit: "fit"` drops nothing.
5. **B, measured.** On the scratch span with a crop that removes at least one line: fill seconds and
   the number of filled layers before and after; the estimate's range against the real render
   (estimate must still bracket or be within its stated error).
6. **B, pixels.** The kept picture of the output is unchanged for a line that is kept: compare
   frames of the kept line's region before/after (max abs diff and mean). If LaMa's output inside
   the kept picture moves because the mask outside it changed, state the number; that is
   acceptable only if the cache key changed with the layer set (see VERSION above).
7. **No regression.** `python3 -m pytest -q tests` (228 today, more after) and
   `node --check static/duck/app.js` pass. No UI change in this loop.

## Out of scope

Grade/threshold calibration of the check and the fps message (loop 22). Blur layers outside the
crop. Any change to `inkcheck.SAME`, `ink.EDGE`, or the fill hole.

## Definition of done

Behaviour + tests + `MEMORY.md` (Outcome line on REQ-20261115-01 for A/B) + `TODO.md` (tick A/B) +
`docs/teams/loop-21-cut-render-cost/review.md` (verdict, pass/fail per item with numbers, what got
worse, what was not tested, commits) in one commit on `ducksuite`. Do not push; the sub-leader
verifies and pushes. Do not touch `old_*.md` or the HTML reports.
