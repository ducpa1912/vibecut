# P-E · Remove a Clean layer, select a layer by its box — review

Loop: `pe-layer-remove-select` (REQ-20261118-01, REQ-20261125-03)
Branch: `oc/pe-layer-remove-select` · Base: `e971c20` (`docs: P-D merged … P-E starts`)
Agent: OpenCode. Date: 2026-11-26.

## Verdict

**Good to go for PO review.** Remove and box select are built, the remove route is covered by four
tests, and the full suite passes. I could not look at the real screen: no app launch, no founder
media, per the brief. The numbered hand test below is the remaining gate.

## What changed

- `duckcore/edits.py`: `remove_clean_layer()` deletes the layer from `edit["clean"]` and records its
  id in `edit["removed_clean"]`; `drop_removed_layers()` keeps those ids out of a Clean re-plan.
  Unknown layer raises `KeyError`, which the route maps to 404.
- `duckcore/main.py`: new `DELETE /api/projects/{id}/edits/{id}/clean/{layer_id}`. The
  `clean/from-check` handler runs `edits.drop_removed_layers()` after `clean.apply_report()`.
- `static/duck/app.js`:
  - `removeLayerButton()` draws **Remove layer** in the Clean inspector (edit screen and Clean
    screen). `removeCleanLayer()` confirms once in plain words, sends the DELETE, clears the
    selection, invalidates that scene's proof, bumps `cleanVersion`, and re-renders. The estimate
    key already includes `edit.updated` and `cleanVersion`, so it re-measures.
  - `detectLayerAtPoint()` hit-tests the drawn boxes in normalized video coordinates and picks the
    **smallest** box containing the point. The inline detection overlay now marks the selected box
    and listens for `click` on the overlay; a hit sets `selectedLayerId`, switches the inspector to
    Clean, and re-renders.
- `static/duck/app.css`: overlay boxes accept pointer events inside the box only; hover and
  selected outline added. The layer list needed no new rule.
- `tests/test_clean_layer_remove.py` (new): 4 tests.

No `textfill` change, no `textfill.VERSION` bump, no fill cache key change.

## Behaviour notes

- **Detected and manual layers both remove.** Manual ids are recorded too; they are absent from the
  Check report, so the list filter only matters for detected ids.
- **Re-Check does not resurrect a removed layer in this branch.** A Check tracklet id is hashed to
  the same layer id every run, so the `removed_clean` id matches and the layer stays gone. A fresh
  edit (or a renamed/retracked block with a new id) starts without that memory. This is stronger
  than the brief required; it is written down here because the brief asked.
- **Fill cache.** Other layers keep their `fill_keys`, ranges and box in the tests. A span where the
  removed layer and another layer shared time re-fills on the next render, because the layer set for
  that span changed. That is a real re-plan of the span, not a cache invalidation, and no other
  layer's saved fill is rewritten or deleted.
- **Rendered edits.** `save_edit` sets `updated`, which is what the Render screen already uses to
  mark an edit changed. Remove behaves like every other Clean edit there.
- **Box select vs box editing.** The overlay listens on `click` only, not `pointerdown`, so it does
  not capture a drag. In this branch floating box editing is the inspector X/Y/W/H grid; there is no
  drag/handle code on the detection overlay to preserve. The compare-split drag is on another stage
  and is untouched. Clicking outside every box never reaches a box and keeps today's behaviour.
- **Keyboard.** The layer list stays the keyboard path: its rows are buttons, Tab reaches them, and
  Enter/Space fires `select-layer`. The video boxes are pointer-only by design.

## What was run

```
node --check static/duck/app.js                     pass
pytest -q tests/test_clean_layer_remove.py          4 passed
pytest -q tests                                    453 passed, 2 skipped
```

Covered by tests: layer gone from the saved edit; unknown layer 404 and edit untouched; other
layer's ranges and `fill_keys` unchanged; manual layer removable; removed detected layer absent
after `clean/from-check` while the other layer survives with its user choice and fill keys.

Not verified: the real window at 1440×900, real detection boxes on real footage, GPU/CPU fill
quality after a removal, and the render estimate text on a rendered edit. No founder project or
media was opened and no media was generated.

## Founder hand test

**Remove**

1. Open the project under work, run or open a finished Check, go to **Clean**.
2. Pick a scene with a detected box, click its row in the layer list.
3. Press **Remove layer** under the box grid. One plain dialog appears: the layer leaves the edit
   and the text comes back on render. Press OK.
4. The row leaves the list, its box leaves the preview, the layer count drops, and the render
   estimate re-measures (it may say the old figure changed until it finishes).
5. Prove that scene. The removed words should be back in the proof; the other layers should still
   be applied.
6. If this edit was rendered before, open **Render**: the edit is marked changed, like any Clean
   edit. Render a short span only if you want to see the text return.
7. Paint a manual brush mask, select it, and remove it the same way. It must leave the list too.
8. Press **Re-check & re-apply** on that scene (or run Check again). The removed box must not come
   back. A genuinely new text block may appear as a new layer; that is allowed.

**Box select**

9. On a Clean scene, start the source review so the drawn boxes are on the video.
10. Click inside a fill box. That layer's row highlights and its inspector opens.
11. Where a small box overlaps a big one, click the overlap. The small box must win.
12. Click the video outside every box. Nothing changes; the player keeps today's behaviour.
13. Click the numeric box grid, Apply box; and drag the compare handle on the proof. Both still
    work as before.
14. From the keyboard, Tab to the layer list and press Enter on a row. Selection still works; the
    list remains the keyboard path.

## Revisions / bugs

None known. If the founder wants removed layers restorable, that needs an explicit undo request:
the ids are kept in `removed_clean`, but no UI reads them back today.
