#!/usr/bin/env bash
# DuckClean M1 readiness check. Prints only missing names, never secret values.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_ENV="$ROOT/api/.dev.vars"
WEB_ENV="$ROOT/web/.env.local"
WEB_ENV_ALT="$ROOT/web/.env"
API_URL="${M1_API_URL:-http://127.0.0.1:8787/api/v1}"

ok=0
warn=0
fail=0

pass() { printf 'OK   %s\n' "$1"; ok=$((ok + 1)); }
note() { printf 'WARN %s\n' "$1"; warn=$((warn + 1)); }
bad()  { printf 'FAIL %s\n' "$1"; fail=$((fail + 1)); }

value_of() {
  local file="$1" key="$2"
  [ -f "$file" ] || return 1
  local line
  line="$(grep -E "^${key}=" "$file" | head -1 || true)"
  [ -n "$line" ] || return 1
  printf '%s' "${line#*=}" | sed -e 's/^["'\'']//' -e 's/["'\'']$//'
}

require_value() {
  local file="$1" key="$2" label="$3" allow_empty="${4:-0}"
  local value
  value="$(value_of "$file" "$key" || true)"
  if [ -z "$value" ] && [ "$allow_empty" = "1" ]; then
    note "$label is empty (allowed for M1)"
    return
  fi
  if [ -z "$value" ]; then
    bad "$label is missing in ${file#$ROOT/}"
    return
  fi
  case "$value" in
    *replace*|*example.clerk*|*your-app*) bad "$label still has a placeholder";;
    *) pass "$label is set";;
  esac
}

echo "DuckClean M1 doctor"
echo "root: $ROOT"
echo

echo "-- tooling --"
if command -v node >/dev/null 2>&1; then pass "node $(node --version)"; else bad "node is missing"; fi
if command -v npm >/dev/null 2>&1; then pass "npm $(npm --version)"; else bad "npm is missing"; fi
if command -v ffmpeg >/dev/null 2>&1; then pass "ffmpeg is installed"; else note "ffmpeg is missing on this machine (needed only on the worker host)"; fi
if [ -x "$ROOT/.venv/bin/python" ]; then pass "Python worker venv exists"; else note "run 'make setup' to create .venv"; fi
if command -v npx >/dev/null 2>&1; then pass "npx is available"; else note "npx is missing; Wrangler cannot run"; fi

echo
echo "-- API secret file --"
if [ -f "$API_ENV" ]; then
  pass "api/.dev.vars exists"
  if git -C "$ROOT" check-ignore -q "$API_ENV"; then pass "api/.dev.vars is gitignored"; else bad "api/.dev.vars is not gitignored"; fi
  require_value "$API_ENV" CLERK_ISSUER "CLERK_ISSUER"
  require_value "$API_ENV" CLERK_AUDIENCE "CLERK_AUDIENCE" 1
  require_value "$API_ENV" ALLOWED_ORIGINS "ALLOWED_ORIGINS"
  require_value "$API_ENV" WORKER_HMAC_SECRET "WORKER_HMAC_SECRET"
  require_value "$API_ENV" R2_ACCOUNT_ID "R2_ACCOUNT_ID"
  require_value "$API_ENV" R2_BUCKET "R2_BUCKET"
  require_value "$API_ENV" R2_ACCESS_KEY_ID "R2_ACCESS_KEY_ID"
  require_value "$API_ENV" R2_SECRET_ACCESS_KEY "R2_SECRET_ACCESS_KEY"
  require_value "$API_ENV" CPU_WORKER_URL "CPU_WORKER_URL"
  require_value "$API_ENV" GPU_WORKER_URL "GPU_WORKER_URL" 1
else
  bad "api/.dev.vars is missing; copy api/.dev.vars.example"
fi

echo
echo "-- web env --"
web_file=""
if [ -f "$WEB_ENV" ]; then web_file="$WEB_ENV"; elif [ -f "$WEB_ENV_ALT" ]; then web_file="$WEB_ENV_ALT"; fi
if [ -n "$web_file" ]; then
  pass "${web_file#$ROOT/} exists"
  require_value "$web_file" VITE_CLERK_PUBLISHABLE_KEY "VITE_CLERK_PUBLISHABLE_KEY"
  require_value "$web_file" VITE_API_BASE_URL "VITE_API_BASE_URL" 1
else
  bad "web/.env.local is missing; copy web/.env.example"
fi

echo
echo "-- Cloudflare --"
if command -v npx >/dev/null 2>&1; then
  if npx --yes wrangler whoami 2>&1 | grep -qi "not authenticated"; then
    bad "Wrangler is not logged in; run 'npx wrangler login'"
  else
    pass "Wrangler is authenticated"
  fi
fi

echo
echo "-- database migrations --"
if [ -x "$ROOT/.venv/bin/python" ]; then
  pass "migration files: $(ls "$ROOT"/api/migrations/*.sql 2>/dev/null | wc -l | tr -d ' ')"
else
  note "cannot inspect migrations without .venv"
fi

echo
echo "-- live services --"
if command -v curl >/dev/null 2>&1; then
  health="$(curl -sS --max-time 4 "$API_URL/health" 2>/dev/null || true)"
  if [ -n "$health" ]; then
    if printf '%s' "$health" | grep -q '"status":"ok"'; then
      pass "API health is ok"
    elif printf '%s' "$health" | grep -q '"status":"degraded"'; then
      note "API is reachable but degraded: $health"
    else
      note "API answered: $health"
    fi
  else
    note "API is not running at $API_URL"
  fi
  worker_url="$(value_of "$API_ENV" CPU_WORKER_URL || true)"
  if [ -n "$worker_url" ]; then
    worker_health="$(curl -sS --max-time 4 "${worker_url%/}/health" 2>/dev/null || true)"
    if printf '%s' "$worker_health" | grep -q '"status":"ok"'; then pass "CPU worker health is ok"; else note "CPU worker is not reachable"; fi
  fi
else
  note "curl is missing"
fi

echo
echo "-- summary: $ok ok, $warn warn, $fail fail --"
if [ "$fail" -gt 0 ]; then
  echo "M1 is not ready. Fix the FAIL lines, then run 'make check' and 'npm run m1:doctor' again."
  exit 1
fi
echo "M1 configuration looks ready. Start the API, worker and web, then upload a real clip."
