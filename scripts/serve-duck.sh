#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA="${DUCK_DATA:-$HOME/vibecut-lanes/ducksuite}"
PORT="${DUCK_PORT:-8797}"
TOKEN="${DUCK_TOKEN:-$(python3 -c 'import secrets; print(secrets.token_hex(32))')}"

printf 'DuckSuite dev shell: http://127.0.0.1:%s/#t=%s\n' "$PORT" "$TOKEN"
printf 'Data: %s\n' "$DATA"

DUCK_TOKEN="$TOKEN" exec python3 "$ROOT/duck_app.py" --data-root "$DATA" --port "$PORT"
