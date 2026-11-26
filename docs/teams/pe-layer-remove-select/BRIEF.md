# P-E · Remove a Clean layer, select a layer by its box (REQ-20261118-01, REQ-20261125-03)

Owner: **OpenCode**. Folder `drop_eval/ducksuite-opencode`, branch `oc/pe-layer-remove-select`.
Founder, 2026-11-26: "P-E after P-D". This is the yes to both REQ-20261118-01 proposals.

**Queued.** Start only after the PO merges Codex's P-D (split + reorder). P-D owns
`static/duck/app.js` until then. Base on `ducksuite` at the P-D merge or later. The PO will
send the start.

## Why
- In Clean, a layer can only be turned **Off** today. It stays in the list, greyed. There is no
  way to drop a wrong box for good.
- The fill boxes drawn on the video can't be clicked, so the creator has to find the layer in the
  list instead.

## Files you own
- `static/duck/app.js`: the Clean layer list and inspector (`layerListMarkup`, `inspectorClean`,
  `cleanAction`) and the detection overlay (`layerBoxAt`, `detectionLayers`,
  `updateDetectionOverlay`).
- `static/duck/app.css`: only the rules for the overlay and the layer list.
- `duckcore/main.py`: only the clean layer handlers (about lines 2062–2100), plus one new route to
  remove a layer.
- `duckcore/edits.py`: only what removing a layer needs.
- `tests/test_clean_layer_remove.py` (new), `docs/teams/pe-layer-remove-select/review.md`.

## Done looks like
1. **Remove.** The layer inspector has a **Remove layer** action. It asks for confirmation once,
   in plain words, saying the layer leaves this edit and the text it covered comes back on render.
   - The layer is deleted from the edit. It is not just turned off.
   - The layer list, the overlay and the render estimate update.
   - The fill cache entries of other layers stay valid. Don't change `textfill` output or bump
     `textfill.VERSION`.
   - If the edit was already rendered, the Render screen shows the edit as changed, the same way
     any other Clean edit does.
2. **Same for every layer.** Detected and hand-drawn (manual) layers can both be removed. A
   removed detected layer does not come back when the creator changes something else in Clean.
   If running Check again brings it back, say so in the review: that's allowed, but it must be
   written down.
3. **Box select.** A click inside a drawn fill box on the video selects that layer in the list and
   opens its inspector.
   - Where boxes overlap, the smallest box under the pointer wins.
   - It does not break box editing: dragging a selected box or its handles still moves or resizes
     it. A click outside every box keeps today's behaviour.
   - Keyboard: the layer list stays the keyboard path. Say so in the review.
4. **Tests.** `tests/test_clean_layer_remove.py` covers the remove route:
   - the layer is gone from the saved edit;
   - an unknown layer gives 404;
   - other layers and their fill spans are unchanged;
   - a removed detected layer doesn't come back on a Clean patch.

   Use built-in edit data, not media files. `node --check static/duck/app.js` and the full
   suite pass.
5. **Hand test.** The review has numbered founder hand-test steps for remove and box select on the
   project under work. **Do not open the app.** Don't open founder projects. Don't make media.

## Notes
- Commit on `oc/pe-layer-remove-select` with `git -c commit.gpgsign=false commit`. Don't push.
  Don't edit `MEMORY.md`, `TODO.md`, `PLAN.md` or `PRODUCT.md`.
- If you check anything by hand, use port 8821 and `build/scratch-root` only.
