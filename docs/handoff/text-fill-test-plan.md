# Text fill test plan: STTN and LaMa (2026-11-01)

Goal: find out whether a local AI fill removes burned-in text better than
today's Clean kinds (blur, plate, mask, delogo), and whether it is fast enough
on the founder's Mac (Apple M1, 8 GB). This plan is a **bench test only**. It
adds no Clean kind, route or UI, and it does not change the rule in
`cleanup.py` and `edits.py` that refuses inpainting. That needs a founder
decision after the test (Part 5).

## 1. What we test

| Method | What it does | Code and license | Weights and license | Runs on |
|---|---|---|---|---|
| **Baseline: delogo** | ffmpeg fills the box from its border | existing `compose_render._clean_filters` | none | CPU |
| **STTN** | Video model. Fills each frame from up to ~10 nearby frames, so text that moves off a background shows the real pixels | `researchmm/STTN`, MIT. The subtitle variant in `YaoFANGUK/video-subtitle-remover` (Apache 2.0) is the reference for crop size and frame stride | STTN checkpoint, MIT (from the STTN or VSR release) | torch MPS, CPU fallback |
| **LaMa** | Image model. Paints each frame on its own; sharp on still or simple backgrounds, can flicker | `advimman/lama`, Apache 2.0 | `Carve/LaMa-ONNX` `lama_fp32.onnx`, Apache 2.0, fixed 512×512 input | onnxruntime (CoreML provider, CPU fallback) |
| **LaMa + borrow** (variant) | Before LaMa, copy pixels from the nearest frame where that pixel had no text (same position, static camera only). LaMa fills only what is left. Then blend each filled pixel 30% with the previous frame to cut flicker | our own code | same LaMa weights | numpy + onnxruntime |

ProPainter stays out (NTU S-Lab license, non-commercial only; 19 GB at 720p).
CLEAR (4.86 s per frame) and the diffusion models (minutes per clip, large GPU)
stay out for speed. Hosted services (fal VOID, Bria) are a separate decision:
they upload the founder's video.

### Downloads (founder approves each one first)

Founder approved both on 2026-11-01. Downloaded to
`~/vibecut-lanes/studio/models/fill/`, hashes in `SHA256SUMS` there:

| File | From | Size | SHA-256 |
|---|---|---|---|
| `lama_fp32.onnx` | huggingface.co/Carve/LaMa-ONNX (Apache 2.0) | 208,044,816 B | `1faef5301d78db7dda502fe59966957ec4b79dd64e16f03ed96913c7a4eb68d6` (matches the Hub etag) |
| `sttn_infer_model.pth` | YaoFANGUK/video-subtitle-remover `backend/models/sttn-auto/infer_model.pth` (repo Apache 2.0; STTN MIT) | 66,271,967 B | `c8408c9dd1300bd7000ea3a81b8236db89d9c0f185837781e38283c1e464675b` |

Load checks done:

- LaMa inputs `image [b,3,512,512]` and `mask [b,1,512,512]`, output
  `output [b,3,512,512]`. CoreML covers only 3984 of 7917 nodes in 585
  partitions, so the bench times **both** the CoreML and the CPU-only provider
  and keeps the faster one.
- STTN: a dict `{"netG": state_dict}`, 112 tensors, 16.6 M parameters,
  `transformer.*` keys as in VSR's `sttn-auto` network. Always load with
  `torch.load(..., weights_only=True)`; never unpickle full objects. MPS is
  available.

No model is committed to git, and no other lane reads this folder.

Python packages already present on the studio machine: `torch 2.14`,
`onnxruntime 1.31`, `numpy`, `Pillow`, `imageio`. No OpenCV: frames go in and
out through ffmpeg raw pipes. Nothing new is installed without asking.

## 2. Test media (founder's own files only)

Never generate test videos. Use:

1. **Job `77d072b8d44c`** (studio lane data, 720×1280, 30 fps, 88.8 s, Chinese
   subtitles). It already has Check tracklets.
2. The founder picks **two more real videos** with:
   - a moving or busy background behind the text (street, crowd, camera pan);
   - a still or flat background (talking head on a wall, screen recording).

   Each needs a Check run in the studio lane so it has tracklets.

From each video the founder names **one moment** (8–15 s) with text on screen.
That keeps every run short and comparable.

## 3. The bench script

New file `scripts/fill_bench.py`, plus a small package `fill/` with
`fill/mask.py`, `fill/sttn.py`, `fill/lama.py`, `fill/borrow.py`. Studio owns
them (`scripts/` and new studio modules). Nothing in `app.py`, the routes,
`compose_render.py`, `edits.py` or `cleanup.py` changes.

```
python scripts/fill_bench.py --job 77d072b8d44c --start 12.0 --end 24.0 \
    --methods delogo,sttn,lama,lama_borrow
```

It reads the job from the studio lane data folder (`scripts/lane-env.sh`), and
writes only to `~/vibecut-lanes/studio/fill-bench/<job>-<start>-<end>/`.

### 3.1 Mask from Check tracklets (`fill/mask.py`)

- Take the job's tracklets the same way `cleanup.tracklet_clean_layers` does,
  with the same rights gate: a tracklet the gate refuses (watermark, screen UI,
  handle without attestation) gets **no mask**. The bench must not become a way
  around the gate.
- Keep the tracklets that overlap the moment. Boxes are source-normalized;
  scale to source pixels.
- **Pad** each box by 6% of its height on every side (text edges, shadows and
  outlines sit outside the OCR box).
- **Time margin**: OCR samples run at 0.5 fps, so a range edge is only known to
  ±2 s. Extend each range by 1 s on both sides, clipped to the moment.
- Write one mask per frame as a 1-bit PNG sequence plus `mask.mp4` (white =
  fill) for viewing.

### 3.2 Work on a band, paste back only the mask

Both models work at low resolution (STTN 432×240, LaMa 512×512). Running them
on the full frame would blur the whole picture. So for each run:

1. Take the union of all mask boxes in the moment. Grow it to a band with
   context: at least 64 px or 50% of the box height above and below, full width
   if the text spans more than half the frame.
2. Crop that band from every frame, resize to the model's input, fill, resize
   back.
3. Paste back **only the masked pixels** with a 3 px feathered edge. Every
   other pixel is the original, bit for bit.

### 3.3 STTN runner (`fill/sttn.py`)

- Port the STTN inference code (MIT, keep its copyright header) into
  `fill/sttn.py`. No training code.
- Band resized to 432×240. Process in windows of 50 frames with 10 frames of
  overlap. Reference frames every 10 frames, as in STTN's `test.py`.
- Cross-fade the 10 overlap frames inside the mask, so no seam shows.
- Device: `mps`, fall back to `cpu` on any MPS error, and record which ran.

### 3.4 LaMa runner (`fill/lama.py`)

- `onnxruntime.InferenceSession(lama_fp32.onnx, providers=["CoreMLExecutionProvider", "CPUExecutionProvider"])`.
  Record which provider actually ran.
- Per frame: band to 512×512 (pad to keep aspect, do not stretch), image and
  mask in, output out, undo the pad, paste back.
- Skip frames whose mask is empty (copy the original).

### 3.5 LaMa + borrow (`fill/borrow.py`)

- For each masked pixel, look up to ±45 frames (±1.5 s at 30 fps) for the
  nearest frame where that pixel is **not** masked and the band's mean
  difference to the current frame is under a threshold (camera has not moved).
  Copy that pixel.
- LaMa fills the pixels still empty.
- Blend each filled pixel 70% current / 30% previous output.

### 3.6 Outputs per run

In the run folder:

- `original.mp4`: the moment, untouched (for side-by-side).
- `<method>.mp4`: the moment with the fill, original audio, H.264 CRF 18.
- `grid.mp4`: 2×2 grid (delogo, sttn, lama, lama_borrow) with labels, so the
  founder watches one file.
- `report.json` and `report.md` with, per method:
  - wall time, seconds per frame, real-time factor;
  - peak memory (RSS) and device or provider used;
  - **flicker**: mean absolute frame-to-frame change inside the mask, divided
    by the same value for the original outside the mask (1.0 = as steady as
    the scene; higher = flicker);
  - **leftover text**: run the same OCR the Check step uses on 1 frame per
    second of the output, inside the mask. Count lines found with confidence
    ≥ 0.4 (`detect.OCR_MIN_CONFIDENCE`);
  - the mask's frame count and pixel share.

## 4. Pass marks

For a 15 s moment of a 720×1280 video on the M1:

| Check | Pass |
|---|---|
| Leftover text | 0 OCR lines in every output frame sampled |
| Flicker | ≤ 1.5 |
| Speed | STTN ≤ 2 min, LaMa ≤ 5 min, LaMa + borrow ≤ 5 min |
| Memory | peak RSS ≤ 4 GB (the app and the browser also need room) |
| Outside the mask | bit-identical to the original (the script asserts this) |
| **Founder's eye** | Founder watches each `grid.mp4` and scores each method 1–5. A method passes at ≥ 4 on all three videos |

The founder's score decides. The numbers only flag problems.

## 5. After the test: decisions for the founder

Only when a method passes:

1. **Drop the no-inpainting rule?** Today `cleanup.py` refuses methods named
   inpaint, remove or repair, and `edits.py` refuses those words in labels.
   Adding a fill needs this changed on purpose, with the rights gate kept:
   watermarks and screen-recording UI never get a fill, handles and logos
   need attestation.
2. **How it reaches the render.** Proposed: a new Clean kind `fill` with
   `method: sttn|lama`. Before `compile_edit`, a pre-pass job renders the
   cleaned span of the source once to
   `jobs/<id>/fill/<hash>.mp4` (hash = source hash, span, masks, method,
   model SHA-256). `compile_edit` reads that file in place of the source for
   the span. It is a queued job with progress and Cancel, never a live
   preview.
3. **Which method is the default**, and whether the other stays as a choice.

## 6. Order of work

1. Founder approves the two downloads and names the three moments.
2. Build `fill/mask.py` and the band crop and paste back, with unit tests on
   synthetic **arrays** only (no media files): mask padding, time margin, rights
   gate, band maths, bit-identical paste back.
3. Build `fill/lama.py` and `fill/borrow.py`; run on moment 1.
4. Build `fill/sttn.py`; run on moment 1.
5. Run all four methods on the three moments. Write `report.md` per run and a
   one-page summary in this folder.
6. Founder watches the grids and scores. Then Part 5.

Steps 2–5 are one OpenCode run, resumed in the studio session, after the
founder approves step 1.

## 7. Built into Studio (2026-11-01)

The founder chose to build the feature in Studio before any test run, so the
bench script in Part 3 was not written. What exists now:

- **Edit kind `fill`** (`edits.py`): Clean layers take `kind: "fill"` and
  `method: "sttn" | "lama"` (default `sttn`). Other kinds carry no method.
  Label words like "inpaint" stay refused, as before.
- **Studio Clean panel** (`static/studio/edit/layers/clean.js`): "AI fill" in
  the kind list, an Engine picker, a note that the preview shows only the box,
  and a "Use AI fill for all N detected layers" button that turns detected
  remove, blur, plate and mask layers into a fill. Manual boxes keep their
  kind. Auto-clean still adds "Remove (interpolate)" layers; the button
  switches them.
- **Compile** (`compose_render.py`): a fill layer adds no ffmpeg filter. Each
  segment gets `fill: {method, ids, layers}` when a fill layer is active on it
  (`fill_method_mixed` warns when one beat mixes engines; the topmost layer's
  engine wins).
- **Render pre-pass** (`render._prepare_fills`): before the beats are cut, each
  beat with a fill gets a filled clip from `textfill.prepare_span`, cached in
  `jobs/<id>/fill/<key>.mp4` (key: source, span, layers, engine, model file).
  The beat reads that clip instead of the source; other Clean layers, crop,
  motion and colour apply on top. Progress shows "Filling text, beat i/n"
  from 2% to 45%. Cancel stops it.
- **`textfill/`**: `mask.py` (pad 6% of box height, +1 s on detected ranges,
  feathered paste-back, pixels outside the feather untouched), `sttn.py`
  (STTN generator, 640x120 strips, 50-frame chunks with 10-frame cross-fade),
  `lama.py` (512x512, one fixed work area per beat, 30% carry from the
  previous frame).
- **Tests**: `tests/test_textfill.py`, arrays and fake fillers only.

Knobs: `VIBECUT_FILL_MODELS` (model folder), `VIBECUT_FILL_DEVICE`
(`auto|mps|cpu`, STTN), `VIBECUT_FILL_LAMA_PROVIDER` (`cpu|coreml`, LaMa).

### First speed reading (not a test of quality)

Both models ran once on random in-memory arrays, no video. The Mac had 7.7 GB
of swap in use and about 60 MB free, so these numbers are swap-bound:

| Engine | Device | Per frame |
|---|---|---|
| STTN, 50 strips of 720x135 | MPS | 4.1 s |
| LaMa, 720x200 area | CPU | 16.1 s |

At these speeds a 15 s moment (450 frames) takes about 30 minutes with STTN
and about 2 hours with LaMa. Measure again on the founder's first real render
with other apps closed. If it stays slow, the next steps are LaMa on CoreML or
fp16, and STTN on fewer frames (text-only frames, lower strip count).

Knob added 2026-11-04: `VIBECUT_FILL_TEXT_MASK` (`on` by default, `off` fills whole scan boxes). See `clean-fill-revision-plan.md`, R1.
