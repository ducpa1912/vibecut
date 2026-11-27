# Media cleanup — 2026-11-17

The founder requested removal of generated media, test outputs, copied source
footage, old scratch projects, scenes, renders, and reproducible caches.

## What remains

- Written briefs, reviews, measured tables, test results, logs, and analysis.
- Test source code and application assets, including icons.
- Model weights and converted Core ML packages.
- The rebuilt `build/DuckSuite-Xcode.app` for local testing.
- App-container projects and original footage outside the repository, untouched.

## What was removed

198 tracked historical screenshots and media outputs under `docs/teams/` and
`docs/appstore/screenshots/` were removed from the current checkout. Historical
references to these images describe evidence available when each review was
written; they do not imply that the files still exist in the current checkout.
The images remain in earlier Git commits. No history was rewritten.

Scratch copies of footage, project data, frame extractions, rendered clips,
fill/ink caches, temporary model probes, browser profiles, build intermediates,
build environments, and redundant app/archive copies were removed from `build/`.
Python and pytest caches in the checkout were also removed.

`build/` shrank from approximately 9.8 GiB to 2.4 GiB. Free disk space increased
from approximately 8.9 GiB to 16 GiB. These rounded filesystem observations are
not a promise about future available space.

Measurement JSON, logs, and scripts remain in the evidence directories. Before
removing copied project folders, their render-check sidecars were preserved in
`build/cleanup-analysis/`. The local deletion manifest is
`build/cleanup-analysis/cleanup-manifest.json`. These artifacts are gitignored;
committed Markdown reviews retain the durable analysis.

## Rebuilding and repeating tests

The existing app can still run. A full rebuild recreates its Python build
environment and generated build outputs with `./scripts/build-xcode-dev.sh`.
Core ML conversion/benchmark environments must be recreated before those scripts
can run again. Old scratch measurement scripts can require a new, authorized
source copy and project setup because their footage/project paths were removed.

No app behavior or test code changed in this cleanup. No renders, downloads,
or model inference were run to validate deletion. The last code verification
remains 346 passing tests and a successful JavaScript syntax check; the rebuilt
app passed signature verification and a scratch-sidecar startup check.
