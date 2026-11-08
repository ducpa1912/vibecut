#!/usr/bin/env bash
# Local ad-hoc signature for a DuckSuite build.
#
# Sign nested helpers first without the app's sandbox entitlements, then seal
# the app itself. A deep sign with --entitlements gives every helper the app
# sandbox, which breaks standalone ffmpeg/ffprobe/vision_probe runs.
#
# App Store distribution still needs a real identity and provisioning profile.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="${1:-$ROOT/build/DuckSuite.app}"
ENTITLEMENTS="$ROOT/mac/DuckSuite/DuckSuite/DuckSuite.entitlements"

if [ ! -d "$APP" ]; then
  printf 'not an app bundle: %s\n' "$APP" >&2
  exit 1
fi

codesign --force --deep --sign - "$APP" >/dev/null

for helpers in "$APP/Contents/Helpers" "$APP/Contents/Resources/Helpers"; do
  [ -d "$helpers" ] || continue
  for nested in "$helpers"/*; do
    [ -f "$nested" ] || continue
    codesign --force --sign - "$nested" >/dev/null 2>&1 || true
  done
done

for attempt in 1 2 3; do
  if codesign --force --sign - --entitlements "$ENTITLEMENTS" "$APP" >/dev/null 2>&1; then
    exit 0
  fi
  printf 'codesign attempt %s failed; retrying\n' "$attempt" >&2
  sleep 1
done

printf 'codesign failed for %s\n' "$APP" >&2
exit 1
