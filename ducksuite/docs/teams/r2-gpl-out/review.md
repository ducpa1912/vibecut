# R2 · Remove the retired voice runtime

**Verdict — release blocked.** The private dev build staged the app and passed the R1 helper check. The GPL gate exited 1 before signing. The remaining finding is the declaration `GPL-3.0-or-later WITH GCC-exception-3.1` on line 135 of NumPy 2.4.6's bundled license file. The app contains neither of the libgcc or libgfortran filenames named by that notice. The founder chose to retain the strict gate. The license is preserved in full.

## Build evidence

The generated PyInstaller spec excludes kokoro_onnx, phonemizer and espeakng_loader. Inspection of all 5,481 frozen archive entries found none of these modules. A separate filename search of the staged app found zero matches for Kokoro, phonemizer, espeak and pcaudio. The generated spec lives under the ignored build directory. The tracked build script regenerates it.

Final scanner output on the staged app:

```text
LGPL  Contents/Resources/Licenses/FFmpeg-LGPL-2.1.txt
BLOCKED  Contents/Resources/duckcore/_internal/numpy-2.4.6.dist-info/licenses/LICENSE.txt
LGPL  Contents/Resources/duckcore/_internal/_soundfile_data/COPYING
```

The first scan also flagged conditional GPL compatibility language in LLVM OpenMP and NVTX notices. A regression test now distinguishes that language from an actual license grant. The final scan above used the same assembled bundle. The scan covers known retired paths, license declarations, metadata, license titles and binary SPDX markers. It cannot establish the provenance of an unlabeled binary.

Measured with `du -sk build/DuckSuite.app`: R1 signed bundle 1,143,184 KiB, R2 staged bundle 1,137,420 KiB, a decrease of 5,764 KiB. The R2 measurement is before signing. The private build used the offline environment and recovered from an initial disk-space failure by replacing the measured R1 output earlier.

## Voice behavior and coverage

The optional voice pack is absent from listing and download. Saved pack selections resolve to the default macOS voice before cache lookup. Track and preview results include a plain fallback message. Saved workflow routes normalize to a single system voice route.

A self-contained user folder supplies its voice graph, styles archive and a text frontend named `tokenizer.onnx`. The frontend accepts one batch-of-one string input and emits positive unpadded integer phoneme IDs in the voice model's vocabulary. The voice graph accepts tokens, style and speed. The core runs both graphs through local ONNX Runtime. Existing two-file folders lack a GPL-free frontend. Settings reports the missing file, and those voices are withheld from the picker. A compatible production frontend and a listening test remain open.

A scratch test imported two minimal ONNX graphs, exercised both with real ONNX Runtime and verified the numerical output before audio writing. Pytest covered the fallback, saved workflow migration, slot status, fake license findings and helper checks. The full suite passed 411 tests in 50.58 seconds with five warnings. One test skipped because the PO's Xcode bundle is absent from this checkout. JavaScript syntax passed. No app launch, founder media access or listening test.

## PO handoff

- Resolve the NumPy distribution/notice finding and rerun the strict gate on the assembled bundle before release sign-off.
- Update PRODUCT.md lines 63 and 66, and retire the Kokoro publisher-hash TODO. The pack list drives the download UI. No hard-coded Kokoro download control was found in app.js.
- Route display of the API fallback message for voice generation and preview (app.js lines 4740 and 4761). The dub title at main.py line 1604 still uses the requested voice name. The Swift chooser at AppModel.swift line 167 copies the entire folder but currently prechecks only the original two files.
- Remove the retired developer dependency from requirements-duck.txt line 7 in the dependency-owner loop. The freezer excludes it even when installed in the build environment.

## PO review (2026-11-26)

- **Accepted and merged.** Kokoro, phonemizer, espeak-ng and pcaudio are gone, and the scan runs before signing.
- **NumPy finding:** the founder chose to allow it ("Yes, allow it"). The scan now allows a
  `GPL-3.0-or-later WITH GCC-exception-3.1` declaration, and the GPL-3 title in the same file,
  only while no `libgcc*`, `libgfortran*` or `libquadmath*` file is in the app. If one appears,
  the file blocks again. It prints an `EXCEPTION` line so the allowance stays visible.
  `tests/test_no_gpl.py` covers all three cases. On Codex's staged app the scan exits 0.
