# Core ML LaMa test — REQ-20261116-01 (2026-11-16)

Founder: "Now try the Core ML with LaMa GPU". Experiment only; no app code changed. Run by the
sub-leader on the dev Mac (M1, 8 GB). Scripts: `scripts/coreml/convert_lama.py`,
`scripts/coreml/bench_lama.py`; tools in a separate venv under `build/coreml-lama/` (coremltools 9.0,
torch 2.14.1, which coremltools has not tested; it worked).

## Verdict: promising — Core ML on the GPU is faster than PyTorch and matches its pixels to ±3/255

| Path (same `big-lama.pt` weights, 512×512, 10 runs, same 3 inputs) | Time per run | vs PyTorch | First load | Max pixel diff vs PyTorch | Mean diff in hole | Hole pixels > 2 off |
|---|---:|---:|---:|---:|---:|---:|
| PyTorch MPS (today) | 550.1 ms | 1.00× | — | — | — | — |
| **Core ML, CPU + GPU** | **406.0 ms** | **1.35×** | 11.3 s | 3 | 0.13 | 0.00 % |
| Core ML, all units | 714.3 ms | 0.77× | 558.3 s | 4 | 0.17 | 0.00 % |
| Core ML, CPU + Neural Engine | 966.3 ms | 0.57× | 446.0 s | 4 | 0.17 | 0.00 % |

- Conversion: TorchScript → trace → `ct.convert` mlprogram, FP16, fixed 512×512. The Fourier layers
  converted. 703 s to convert. Package **99 MB** (PyTorch 565 MB + `big-lama.pt` 197 MB today).
- The Neural Engine compiler rejects the model (`ANECCompile() FAILED`); asking for it costs a
  7–9 minute first load and is slower. Use CPU + GPU only.
- Inputs are synthetic arrays (gradients, blocks, caption-shaped holes), no media.

## Not yet known (needed before any app change)

1. The app runs LaMa at sizes that are multiples of 16 from 64 to 512, not only 512. Needs flexible
   shapes (enumerated or ranged) and the same table per size; small runs may lose the speed lead.
2. Real footage: pixel diff and look on the review project's spans, and a full cold render time.
3. Second-load time (Core ML caches the compiled model; 11.3 s is the first load only).
4. How the core calls it without PyTorch: `libcoremlpython.so` is 2 MB (coremltools 27 MB in all),
   or through the Swift shell.
5. PyTorch stays for now anyway: the user TorchScript fill slot (`textfill/custom.py`), MI-GAN and
   STTN (`torch_fill.py`, `sttn.py`) still import it. Dropping it means those move to ONNX or go.
6. Pixels change (≤ 3/255): shipping it bumps `textfill.VERSION` and the next render is cold.
