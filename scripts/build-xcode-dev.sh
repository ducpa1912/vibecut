#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEVELOPER="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
APP_OUT="${DUCK_XCODE_APP_OUT:-$ROOT/build/DuckSuite-Xcode.app}"

# The Xcode target embeds build/duckcore-dist, build/DuckSuite.app resources,
# helpers and the LaMa model. Build those once before the Xcode compile.
"$ROOT/scripts/build-duck-dev.sh"

if ! command -v xcodegen >/dev/null 2>&1; then
  printf 'xcodegen is required: brew install xcodegen\n' >&2
  exit 1
fi

cd "$ROOT/mac/DuckSuite"
xcodegen generate

DEVELOPER_DIR="$DEVELOPER" xcodebuild \
  -project DuckSuite.xcodeproj \
  -scheme DuckSuite \
  -configuration Release \
  -derivedDataPath "$ROOT/build/xcode-derived" \
  CODE_SIGNING_ALLOWED=NO \
  build

BUILT="$ROOT/build/xcode-derived/Build/Products/Release/DuckSuite.app"
rm -rf "$APP_OUT"
cp -R "$BUILT" "$APP_OUT"
# Local ad-hoc signature; App Store needs a real identity.
"$ROOT/scripts/sign-local-app.sh" "$APP_OUT"

printf 'Built %s\n' "$APP_OUT"
printf 'Run: open "%s"\n' "$APP_OUT"
