# engine/

Deliberate ports from Classic. Nothing here is imported by `api/` or `web/`, and
no Classic application module is copied wholesale.

DuckClean's cloud pipeline lives in `worker/`. This directory holds reference
implementations that were proven on real files and are being re-derived for the
cloud, one function at a time:

| Port | From Classic | What is taken |
|---|---|---|
| `pipeline.py` | `pipeline.py` | probe fields, frame sampling rules |
| `detect.py` | `detect.py` | tracklet merge, range building, fill planning |
| `clean_source.py` | `clean_source.py` | full-source fill, encode, audio mux, cancel, cache |
| `textfill/` | `textfill/` | LaMa wrapper, mask prep, estimate, cache keys |

Rules:

- Classic commit `bb3e89e` is the reference. The Classic lane is never merged.
- Apple Vision is macOS-only and stays out of the cloud path. The cloud OCR is
  PaddleOCR PP-OCRv5 or RapidOCR on ONNX.
- Any behaviour that changes the contract (`docs/duckclean/contract.md`) is
  updated there in the same change.
- No ported file may be a copy of a Classic route, job runner or UI module.

`PORT_LOG.md` records each port: source commit, file, functions taken, functions
deliberately dropped, and the test that covers it.
