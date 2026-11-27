# Refactor sprint 01

Date: 2026-11-08
Team: product owner + engineer + tester.
Scope: behavior-preserving structure only. No new product surface.

## Product gate

Refactor only where it lowers release risk:

1. Proof cache scope and proof window are correctness-critical and repeated inline. Extract them and test them.
2. Local signing is duplicated in two build scripts and has already regressed once. One signer, one order.
3. Two inspector panes repeat the same layer list. One renderer, one toggle.
4. Delete dead code.

Exit: same UI, same outputs, same 39 tests plus new unit coverage, build and archive pass.

## Engineer changes

| Change | Before | After |
|---|---|---|
| Preview scope | `main.py` computed active layers and clip inline inside the endpoint | `_proof_scope(edit, when)` returns both; endpoint hashes the result |
| Proof window | `render.py` had the 0.6 s math inline | `proof_window(start, duration, when)`; same window, tested at clip edges |
| Caption dead code | `_slice_text` was unused after the majority-clip rule | Removed |
| Signing | `build-duck-dev.sh` and `build-xcode-dev.sh` each had their own deep/nested/app sequence | `scripts/sign-local-app.sh`, used by both |
| Layer list | Editor and Clean Focus each built the same six-row list and toggle | `layerListMarkup(active, layers, emptyText)` |

No endpoint, payload, CSS, or visible copy changed.

## Tester evidence

| Check | Result |
|---|---|
| `pytest` | **41 passed** |
| Layer toggle in browser | 6 → 7 rows, button changes state |
| Fine trim still works | `Scene trimmed.` |
| Signer on packaged app | strict verify passes |
| Helper entitlements | none on `vision_probe` |
| App entitlements | `com.apple.security.app-sandbox = true` |
| Build | Xcode build succeeds |
| Archive | unsigned arm64 archive succeeds |

## Measurements unchanged

| Operation | Result |
|---|---|
| Proof parity at 3.5 s | MAD 2.30, 99.1% within 10 |
| Cold proof | 8.9 s |
| Warm proof | 2.5 s |
| Full 20 s render | 65 s |

## Files

```text
duckcore/main.py                 _proof_scope
duckcore/render.py               proof_window
duckcore/captions.py             dead slice removed
static/duck/app.js               layerListMarkup
scripts/sign-local-app.sh        new signer
scripts/build-duck-dev.sh        uses signer
scripts/build-xcode-dev.sh       uses signer
tests/test_product_fixes.py      proof scope + window tests
```

## Remaining

- App Store signing identity and team.
- Support/privacy URLs.
- Screenshot footage rights.
- Render speed, unchanged by design.
