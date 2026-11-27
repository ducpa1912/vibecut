# Core ML GPU fill as the default — REQ-20261116-02 (2026-11-16)

Founder: "put CoreML GPU in as default option, i will use it for founder test later, build it
yourself". Built by the sub-leader (no OpenCode). Follows the 512 test in
`docs/teams/coreml-lama-test/review.md` (REQ-20261116-01).

## What ships

1. `duckcore/engine/textfill/coreml_fill.py`: `LamaCoreMLFiller` runs `lama_fill.mlpackage` on
   CPU + GPU (never the Neural Engine). The package is compiled once into `<models>/cache`.
2. Core ML cannot run LaMa's Fourier layers at a free size (coremltools 9.0 fails on the complex
   ops and on `irfftn`'s size), so the package holds one function per size bucket that shares
   one copy of the weights: the long side 512, the short side 64, 128, 192, 256, 384 or 512, both
   ways (11 sizes). A run pads up to the smallest bucket that holds it.
3. GPU = Core ML when the package is installed; PyTorch (`big-lama.pt`) when it is not, or when
   `DUCK_FILL_GPU_ENGINE=pytorch`. If Core ML fails to load or run mid-render, the fill moves to
   PyTorch on the GPU, then to the CPU engine, as before.
4. The cache stamp carries the engine (`:coreml-gpu`), so a Core ML clip is never reused as a
   PyTorch clip. Output changes (≤ 3/255 at 512): **`textfill.VERSION` 17 → 18; the next render of
   every edit is cold once.**
5. Build: `coremltools` in `requirements-duck.txt` and collected by PyInstaller; the package goes
   to `Contents/Resources/base-models/lama_fill.mlpackage` and is seeded into app data.
6. Settings line under GPU says "Apple GPU through Core ML" with the measured speed. No model name.

## Not in this change

PyTorch stays (TorchScript user slot, MI-GAN, STTN, the fallback). The fill estimate's unit still
counts the 16-step run size, not the bucket; the learned rate absorbs it.

## Done

Tests, a measured table per bucket against PyTorch, a founder hand test, MEMORY/TODO/review, one
commit, not pushed (bc89a5a is still unresolved).
