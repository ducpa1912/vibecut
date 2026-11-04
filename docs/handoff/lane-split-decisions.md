# Lane split decisions

Date: 2026-11-04
Matrix: [classic-studio-matrix.md](classic-studio-matrix.md)

## Locked decisions

| Decision | Answer | Consequence |
|---|---|---|
| Classic role | **Second supported product** | Classic keeps its own roadmap, beta tag and release gate. Studio does not absorb it. |
| Port scope | **Matrix first, then high-value** | Use `classic-studio-matrix.md`; no blind parity port. |
| Code structure | **Monorepo, separate apps, no core extraction** | Two app entrypoints and isolated page trees; shared `app.py` core stays for now. |
| Main/release | **Main tracks Studio; Classic keeps its own beta tag** | Studio remains integration/product branch; Classic releases from `classic` tags. |

## Phase status after decisions

| Phase | Item | Status |
|---|---|---|
| 0 | Build feature matrix | ✅ done — `classic-studio-matrix.md` |
| 0 | Decide Classic-only features to port | 🟡 recommended set ready; awaiting approval |
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
| 3 | Extract shared backend core | ✅ `core/` contract package: `CORE_VERSION=1.0.0`, `CONTRACT_VERSION=1` |
| 3 | Extract feature modules | ✅ feature routers compose through `AppProfile.routers`; physical module move stays deferred |
| 3 | Apps compose pinned features | ✅ `studio_app.py` / `classic_app.py` call `configure(STUDIO/CLASSIC)`; `app.py` includes profile routers |
| 3 | Pin core versions | ✅ health reports `core_version` and `profile_version` |
| 4 | Separate CI | ⏳ |
| 4 | Separate release artifacts | ⏳ |
| 4 | Separate repositories | ❌ rejected for this pass |

## Constraints

- Studio worktree currently has unrelated uncommitted Clean work. Do not mix
  port work into it.
- Classic worktree currently has uncommitted AI-fill work. Do not overwrite it.
- Do not create a `core/` package in this pass.
- Existing shared backend imports stay; isolate entrypoints and page trees.
