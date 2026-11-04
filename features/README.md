# Feature contracts

Each optional feature exposes a small public API and a `FEATURE` contract.
The contract pins a feature version and a core range; `core.features.verify_profile`
fails startup when a core change violates that range.

| Feature | Public API | Owner code |
|---|---|---|
| `ai_fill` | model status, span prep, one-frame fill, masks | `textfill/` |
| `captions` | track/style load, save, cue cards | `captions.py` |
| `voice_clone` | clone routes, clean reference, candidate search | `voice_clone.py`, `voice_extract.py`, `routes_voice_clone.py` |
| `url_ingest` | options, validation, providers, download chain | `url_ingest/` |

Rules:
- Feature UI stays in its app page tree. No `features/*` package imports
  `static/studio/**` or `static/classic/**`.
- App profiles list only the features they ship.
- Changing a public feature API requires a feature version bump and a matching
  core range review.
