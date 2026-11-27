## Initial all-bucket measurements

Three warm timed calls per engine; three deterministic pictures compared per case.

| Area | PyTorch ms | Core ML ms | Speedup | Max RGB diff | Mean hole diff |
|---|---:|---:|---:|---:|---:|
| 64×512 | 205.0 | 83.4 | 2.46× | 5 | 0.25 |
| 128×512 | 260.6 | 127.5 | 2.04× | 5 | 0.33 |
| 192×512 | 333.8 | 198.7 | 1.68× | 9 | 0.52 |
| 256×512 | 411.3 | 249.3 | 1.65× | 8 | 0.55 |
| 384×512 | 564.7 | 393.8 | 1.43× | 8 | 0.65 |
| 512×64 | 208.7 | 82.6 | 2.53× | 6 | 0.45 |
| 512×128 | 276.7 | 128.5 | 2.15× | 7 | 0.47 |
| 512×192 | 372.8 | 208.0 | 1.79× | 12 | 0.56 |
| 512×256 | 414.8 | 313.6 | 1.32× | 9 | 0.68 |
| 512×384 | 555.3 | 748.9 | 0.74× | 16 | 0.71 |
| 512×512 | 2200.2 | 972.5 | 2.26× | 19 | 0.76 |
| 512×40 | 113.9 | 114.7 | 0.99× | 4 | 0.32 |
| 512×65 | 107.7 | 130.6 | 0.82× | 169 | 11.57 |
| 512×129 | 202.7 | 280.4 | 0.72× | 75 | 6.31 |
| 512×193 | 358.7 | 411.3 | 0.87× | 90 | 5.29 |
| 512×257 | 492.2 | 651.8 | 0.76× | 101 | 5.62 |
| 512×385 | 654.2 | 825.6 | 0.79× | 73 | 5.18 |
| 40×512 | 114.5 | 92.3 | 1.24× | 5 | 0.18 |
| 65×512 | 124.4 | 128.4 | 0.97× | 108 | 5.16 |
| 129×512 | 199.3 | 231.3 | 0.86× | 72 | 4.42 |
| 193×512 | 336.9 | 372.7 | 0.90× | 64 | 4.88 |
| 257×512 | 402.4 | 589.3 | 0.68× | 108 | 5.61 |
| 385×512 | 662.4 | 857.0 | 0.77× | 67 | 5.22 |

These are the unmodified coarse-padding results. The boundary rows fail equivalence.
The corrected runtime refuses coarse padding and falls back to PyTorch.

## Load and memory observations

Initial combined benchmark loads: PyTorch 2.792 s; Core ML cold 33.260 s; cached 2.998 s.

Separate Core ML memory probe: first load 24.772 s, cached load 2.395 s.
Highest recorded RSS before abort: 614,006,784 bytes; process peak RSS 854,654,976 bytes.
After eight bucket predictions, Apple MPSGraph aborted the process with SIGABRT:
`shape.count = 0 != strides.count = 4`.
This is a native assertion, not a catchable Python error. Default promotion is blocked.

Real source crop (15 frames / 0.5 s): PyTorch 13.737 s; guarded Core ML route 21.613 s.
Guarded route fell back because its native 512×240 padded size is absent; max diff 0 on all 15 frames.
Loads: PyTorch 3.136 s; guarded Core ML 52.968 s. This is not a Core ML speed win.
The 15-frame equality comes from PyTorch fallback, not numerical equivalence of coarse padding.

No whole-render/ink-mask claim; GPU memory outside process RSS is not fully measured.
