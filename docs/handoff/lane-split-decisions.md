# Lane split decisions

Date: 2026-11-04
Matrix: [classic-studio-matrix.md](classic-studio-matrix.md)

## Locked decisions

| Decision | Answer | Consequence |
|---|---|---|
| Classic role | **Second supported product** | Classic keeps its own roadmap, beta tag and release gate. Studio does not absorb it. |
| Port scope | **Matrix first, then high-value** | Use `classic-studio-matrix.md`; no blind parity port. |
| Code structure | **Monorepo, separate apps, core contract + pinned profiles** | Phase 3 adds `core/` version/profile composition; backend modules stay at root until a later physical move. |
| Main/release | **Main tracks Studio; Classic keeps its own beta tag** | Studio remains integration/product branch; Classic releases from `classic` tags. |

## Phase status after decisions

| Phase | Item | Status |
|---|---|---|
| 0 | Build feature matrix | ✅ done — `classic-studio-matrix.md` |
| 0 | Decide Classic-only features to port | ✅ trust/clarity four approved; Vietnamese and preview lock deferred |
| 0 | Port wanted Classic work into Studio | ✅ approved trust/clarity set built: capability summary, cost/data notices, stale-render marker, 32-slot cap warning |
| 0 | Decide Classic role | ✅ second supported product |
| 1 | Remove Studio Voice Room import | ✅ done |
| 1 | Remove Studio links to Classic/Voice | ✅ Studio page has no Classic/Voice links; routes stay 404 in the Studio app |
| 1 | Remove editions from Studio boot | ✅ static/index.html is static Studio; Classic keeps its own boot |
| 1 | Prove standalone Studio boot | ✅ tests/test_studio_standalone.py |
| 1 | Studio JS import guard | ✅ |
| 2 | Studio entrypoint | ✅ `studio_app.py` |
| 2 | Classic entrypoint | ✅ `classic_app.py` |
| 2 | Own data/port defaults | ✅ entrypoints default 8795/8796 and lane data folders |
| 2 | Per-app scripts | ✅ `serve-studio.sh`, `serve-classic.sh`; legacy `serve.sh` kept |
| 2 | Remove integrate.sh from Studio release | ✅ removed; docs updated |
| 2 | Main/archive | ✅ main tracks Studio, not retired |
| 3 | Extract shared backend core | ✅ `core/` package: version, contracts, profiles, feature verification |
| 3 | Extract feature modules | ✅ `features/ai_fill`, `features/captions`, `features/voice_clone`, `features/url_ingest` |
| 3 | Apps compose pinned features | ✅ profiles list feature modules and router sets; `app.py` verifies features before mounting routers |
| 3 | Pin core versions | ✅ feature contracts require `>=1.0,<2.0`; health reports core/profile/feature versions |
| 4 | Separate CI | ⏳ |
| 4 | Separate release artifacts | ⏳ |
| 4 | Separate repositories | ❌ rejected for this pass |

## Constraints

- Studio worktree currently has unrelated uncommitted Clean work. Do not mix
  port work into it.
- Classic worktree currently has uncommitted AI-fill work. Do not overwrite it.
- `core/` is the stable contract. Root modules remain the implementation
  bodies behind `features/*`; a physical move can happen later without changing
  the app contracts.
- A core version change that violates a feature's `requires_core` range fails
  startup instead of silently shipping a broken Classic build.

## Feature contracts

| Feature | Version | Core range | Public API |
|---|---|---|---|
| `ai_fill` | 1.0.0 | `>=1.0,<2.0` | models, status, span prep/fill, mask |
| `captions` | 1.0.0 | `>=1.0,<2.0` | tracks, styles, cue build/load/save |
| `voice_clone` | 1.0.0 | `>=1.0,<2.0` | clone routes, clean voice, candidates |
| `url_ingest` | 1.0.0 | `>=1.0,<2.0` | providers, options, validation, download |
