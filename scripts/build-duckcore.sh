#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${DUCK_BUILD_VENV:-$ROOT/build/duckcore-venv}"
OUT="${1:-$ROOT/build/duckcore-dist}"

if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r "$ROOT/requirements.txt" pyinstaller

rm -rf "$OUT" "$ROOT/build/pyinstaller-work" "$ROOT/build/pyinstaller-spec"
mkdir -p "$ROOT/build/pyinstaller-spec"

"$VENV/bin/pyinstaller" \
  --noconfirm \
  --clean \
  --onedir \
  --name duckcore \
  --distpath "$OUT" \
  --workpath "$ROOT/build/pyinstaller-work" \
  --specpath "$ROOT/build/pyinstaller-spec" \
  --paths "$ROOT" \
  --collect-submodules uvicorn \
  --hidden-import duckcore.store \
  "$ROOT/duck_app.py"

printf 'Built %s/duckcore\n' "$OUT"
