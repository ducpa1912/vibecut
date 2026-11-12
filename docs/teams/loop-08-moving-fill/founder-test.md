# Founder test — a fill model of your own

Click-by-click on the built app (`build/DuckSuite-Xcode.app`). The founder runs this; the agent does
not. Project: `prj_e95348a97316`, edit `ed_38a4c36a3aae`. Time: about three minutes.

Prepare two folders on the Desktop:

- `GoodFill/` with a `model.onnx` (an inpainting graph taking `image` and `mask`) or a TorchScript
  `model.pt` that takes `(image, mask)` and returns a frame.
- `WrongFill/` with a text file renamed to `model.onnx` (it is not a graph), or no model file at all.

## 1. A good folder

1. Open DuckSuite, open the project, wait for Check to finish, go to **Settings**.
2. Under **Your fill model**, click **Choose**.
3. Pick `GoodFill`.
4. **Must see:** the field shows the copied folder under DuckSuite's data root, the line under it
   says **Using model.onnx in place of the default engine**, and a **Use the default engine** button
   appears. No model name is printed anywhere.
5. Close Settings, open **Render**, read the estimate.
6. **Must see:** the estimate still shows a time, and the progress message during a render says
   **Your fill model** instead of **AI fill (per frame)**. Do not start a full render for this test.

## 1b. The estimate while it measures

1. Set a good folder (step 1), then open **Render** and change one layer's range in Clean.
2. Go back to **Render**.
3. **Must see:** **Measuring the fill… N%** while the figure is worked out, and, if a figure
   exists, it is marked **Old figure: the edit changed since it was measured.**
4. When it finishes, **Must see:** one line with the whole-render time as a **range**
   (≈ a–b), and no model name.
5. Leave the screen and come back: the figure must appear at once, without the measuring line.

## 2. A wrong folder

1. **Settings → Your fill model → Choose**, pick `WrongFill`.
2. **Must see:** a red toast that names the problem in plain words ("That folder needs a
   model.onnx or model.pt file." or "Your fill model did not load: …"), and the saved setting is
   unchanged.
3. If the app accepted a file that only looks like a model, start a short render (one scene).
4. **Must see:** the render finishes on the default engine; the fill message falls back and a
   warning is logged. It must not fail the render.

## 3. Clear it

1. **Settings → Use the default engine**.
2. **Must see:** a toast **Fill will use the default engine**, the field empties, and the button
   disappears.
3. **Render** the same short scene again.
4. **Must see:** the estimate returns to the number it had before step 1, and the fill message says
   **AI fill (per frame)**.

## 4. What a warm store must not change

Nothing to click: a render after the first one must look the same. If you compare two renders of
the same edit, the leftover-text line must read the same count.

## What to report back

- The words of every toast you saw.
- Whether the estimate changed when the good model was set (it should not move much: the model runs
  on the CPU, and its speed is not learned into the default).
- Any crash, blank Settings panel, or a folder that could not be picked.
