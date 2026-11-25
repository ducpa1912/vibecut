# Thin the data folder — REQ-20261125-02 (2026-11-25)

Founder: "Yes, build all three" — saved fills as lossless PNG, one copy of the fill models, and the
pre-re-key fill clips deleted. Built by the sub-leader. Pixels unchanged: `VERSION` stays 17, and
no cache key moves, so nothing renders cold.

## Measured before (founder's data folder, sizes only)

4.09 GiB (4.4 GB): saved fills 1.59 GB (1,765 raw `.npy`), Whisper pack 1.5 GB, fill models copied
from the app 0.30 GB, fill clips 0.14 GB (0.11 GB from before the Nov 15 re-key), imports 0.29 GB,
renders 0.19 GB, previews 0.08 GB, frames 0.04 GB.

## What changed

| Piece | Change |
|---|---|
| Saved fills | Written as lossless PNG (level 3). On 40 real fills: 0.30 of the raw bytes, 16 ms to write, 13 ms to read (raw `.npy` read 1.4 ms), every one identical. Old `.npy` fills of the same name are still read and touched. |
| Conversion | At start, a background thread rewrites old `.npy` fills as PNG, checks each round-trips to identical pixels, keeps the file time (so pruning order holds), and stops while a fill runs. |
| Prune scope (bug) | `_saved_folders` searched `jobs/` (the VibeCut layout); DuckSuite uses `projects/`. The 14-day / 2 GB limits only ever saw the project being rendered. Now every project. |
| Models | `seed_models` makes `models/fill/big-lama.pt` and `lama_fill.mlpackage` symlinks to the app bundle. An identical older copy (same size and SHA-256) is replaced after its stamp is pinned. A same-size file with other content is left alone. A moved app is followed on the next start. Falls back to a hard link or a copy. |
| Stamp pins | `models/fill/stamps.json`: a linked model's cache stamp is pinned to its content hash. The bundle's file time moves with every build or update; with a plain link that would have made every fill cache cold each time. Content hashes are remembered by path, size and time, so a start does not re-hash. |
| Fill clips | A reused clip is touched; clips no render used for 14 days are pruned at the next fill (same age as saved fills). The 24 clips from before Nov 15 (111 MB) were deleted by hand, as approved. |

## Acceptance

| # | Check | Result |
|---|---|---|
| 1 | PNG written, read back identical, counted as a hit | pass (test) |
| 2 | Old `.npy` reused and touched; non-8-bit results not saved | pass (tests) |
| 3 | Conversion: identical pixels, age kept, odd file kept, waits for a fill | pass (tests) |
| 4 | Identical copy → link, stamp unchanged; bundle time change keeps it; new content changes it | pass (test) |
| 5 | Same-size other content left alone; fresh folder links; moved app followed, stamp kept | pass (tests) |
| 6 | Core ML copy → link, `:coreml-gpu` stamp unchanged | pass (test) |
| 7 | Clip prune: old dropped, fresh and `.part` kept; limits cover every project | pass (tests) |
| 8 | Full suite | 386 passed |
| 9 | Founder folder after the rebuilt app starts | see "After" |

## Found, not changed

- The Mac has about 10 GB free, under `SAVED_MIN_FREE` (10 GB): saved fills are not written at all
  right now, so a stopped render starts its clip again. The app already says so on Render.
- Whisper pack 1.5 GB: the 0.46 GB turbo pack waits on the founder's Vietnamese clip (TODO).
- `frames/` has no cap (small: about 21 MB a project).

## Report row

- `docs/reports/ducksuite-product-progress.html`: not added; the insert anchor is not named.
