# App Store screenshots

Captured from the real web UI at exact App Store Mac sizes.

| Set | Pixels | Viewport |
|---|---|---|
| `*-1280x800@2x.png` | 2560 × 1600 | 1280 × 800 at 2× |
| `*-1440x900@2x.png` | 2880 × 1800 | 1440 × 900 at 2× |

These are accepted Mac screenshot dimensions. Both sets show the same six
screens.

## Recapture

Start the local core against a populated data folder, then run:

```bash
node scripts/capture-appstore-shots.mjs \
  --base "http://127.0.0.1:8765/?t=token" \
  --project prj_... \
  --out docs/appstore/screenshots
```

The script drives headless Chrome through the DevTools protocol, waits for
Preview proofs to finish, and captures every route.

## Content check before submission

The current set uses the internal `check-smoke` fixture. Confirm the footage is
cleared for App Store use, or repeat the capture with a licensed demo project.
Do not ship screenshots that show a failed clean proof. Scene 01 at 3.5 s still
fails in the current clean build; the screenshot set uses a clean frame.
