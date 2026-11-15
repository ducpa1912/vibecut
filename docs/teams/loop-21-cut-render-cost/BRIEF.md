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

## Revision 1 — 2026-11-15 (sub-leader review of `1b039c9`)

Verified by the sub-leader: 238 tests pass, `node --check` clean; diff of `render.py` and
`inkcheck.py` read. **A is accepted** (data_root reaches `build_inks`; second check builds 0 View
inks; 57.2 → 37.1 s; equal reports). **B's selection is correct** (one rule, `search_rect` with the
View) but item 5 failed: 11 → 10 layers saved nothing (+5.3 s, noise), all three spans went cold, and
the estimate is 148 % under the real short render — already 148 %-class on the baseline.

Root cause found in review: `textfill.prepare_span` passes the **whole** `layers` list to
`span_key` (`textfill/__init__.py` ≈ line 1704), while the mask comes only from layers with a rect in
the span (`masks.frame_rects`). So editing, toggling or dropping any one line changes the key of
every span and makes the whole render cold. Dropping a cropped-out line can only save LaMa time on
frames where no kept line is on screen.

### Revision acceptance

R1. **Key only what fills the span.** `span_key` receives only the layers that have at least one
    rect in the span's frames (the same `rect_table` the mask uses). Pixels do not change (the mask
    is the same), so `textfill.VERSION` stays 17; existing fill clips go cold once because every key
    changes — say so in the review. Test: two lines in two different spans; toggling line 1 leaves
    span 2's key unchanged and span 1's key changed. Measured on the scratch span: after toggling
    one line, the number of spans re-filled (must equal the spans that line is in).
R2. **Short-span estimate.** Find which fixed costs the estimate leaves out on a short render
    (model load, decode start, check, per-span overhead) and add them, so the scratch short render's
    real time is inside the stated range, before and after a cold cache. Report the range and the
    real time for a cold and a warm run. Do not change the full-render figure claimed in
    `MEMORY.md` (790.4 s against 847.2 s) without measuring it; a full render is not required.
R3. **Say what B buys.** In the review, state the rule: a dropped line saves fill only on frames
    where no kept line is on screen. Measure it with a crop that leaves a span with no kept line
    (fill seconds before/after for that span), or say plainly that the review project has no such
    span.
R4. No regression: pytest (238 today) and `node --check` pass. Update `review.md` (Revision 1
    section, pass/fail with numbers), `MEMORY.md` Outcome, `TODO.md`. One commit; do not push.

## Revision 2 — 2026-11-15 (sub-leader review of `551b677`)

Verified by the sub-leader: 242 tests pass, `node --check` clean; diff read.
**R1 accepted**: `frame_rects(active_layers=…)` keys a span only by layers with a rect in its
frames, in input order, the same set in `estimate_span` and `prepare_span`; `layer_scope` marker
makes old clips cold once. **R3 accepted** (as OpenCode's measured claim). The `device_problem` fix
(warm spans recognised 3/3) and `remember_render_time` keeping other keys are accepted.

**R2 rejected as built.** `_cost_samples` / `_remember_cost` / `_cost_key` and the sample-based
range only fire when the *identical* edit (clips, layers, Cut, cold-span count) was rendered
before: it memoises a repeat, it does not estimate a short edit. Its test feeds the estimate's own
key back in, so it never proves a render writes the key the estimate reads. And with it, R2 still
fails (cold 400.8–801.6 s against 171.3 s real; the same span measured 601.2 s an hour earlier).
The same short span varies 3.5× on this Mac; no range built from one machine's history can hold it.

### Revision 2 acceptance

R2a. Remove `_cost_samples`, `_remember_cost`, `_cost_key`, `render_costs.json`, the sample branch
     in `estimate_edit`, `cost_key` in its result and `test_short_estimate_separates_cold_and_warm_costs`.
     Keep R1, the `device_problem` fix and the rates-file fix, each with its test.
R2b. Record the limit instead of hiding it: in `review.md` and `TODO.md`, "a short edit's estimate
     is not reliable on this Mac: the same 3-clip span measured 171–601 s cold". Do not change UI.
R2c. pytest passes (241 expected after removing one test; state the number), `node --check` passes.
     Update `MEMORY.md` Outcome to the final state of loop 21 (A, B, R1, R3 shipped; R2 an open
     limit). One commit; do not push.
